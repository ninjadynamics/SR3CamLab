/* nplapack.c: np.linalg.lstsq of small systems without numpy, the same bits as numpy 1.24.3 with the OpenBLAS 0.3.21 it ships, on
   the author's PC (kb 31). numpy's lstsq is LAPACK's dgelsd (umath_linalg: A and B copied column-major into ONE malloc'ed block, A
   first, B right after it, rcond = eps x max(m, n)). OpenBLAS does not know this PC's CPU and runs its Prescott kernels; the LAPACK
   routines are the reference ones of LAPACK 3.10 compiled in. Each routine below is a line-for-line translation, each kernel the
   order it was measured to have (scratch probes against the same routines called inside numpy's DLL, 100% bit for bit):
     dnrm2      x87 (the process's precision: 53 bits), the squares added one after another (fitted for n < 8)
     dgemv 'T'  A 8 bytes off 16 -> row 0 peeled into the low lane of the first accumulator; columns in groups of 4 (lda odd: then
                of 2) with one 2-lane accumulator a column, rows in pairs, a single row left into the low lane, lo + hi; the columns
                left one by one with two 2-lane accumulators, four rows a round, (acc0lo + acc1lo) + (acc0hi + acc1hi); y = 0 + that
     dgemv 'N'  y_i = 0 + the products added one after another; dger A_ij += (alpha y_j) x_i; drot c x + s y, c y - s x
     dgemm TN   0 + the products added one after another (fitted k < 8; dlalsd's 8 x 8 checked through whole dgelsd calls)
     dlartg     LAPACK 3.10's: d = sqrt(f f + g g), p = 1 / d, c = |f| p, s = g sign(p, f), r = sign(d, f)
   np.linalg.svd (dgesdd, JOBZ 'A') the same way: np_svd, for m >= n below dgesdd's QR threshold (every square matrix).
   Sizes: m <= 8 rows (dnrm2's order is known below 8), n <= m (the overdetermined / square path, the one numpy takes for these).
   Plain C, no SIMD: the cost is a few hundred flops a system; -ffp-contract=off (no fused multiply-add, like the kernels). */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

#define EPS_E 1.1102230246251565e-16      /* dlamch('E') */
#define EPS_P 2.220446049250313e-16       /* dlamch('P') */
#define SFMIN 2.2250738585072014e-308     /* dlamch('S') */
#define HUGEV 1.7976931348623157e+308     /* dlamch('O') */
#define MAXM 8
#define MAXRHS 8

static double sgn(double a, double b) { return copysign(fabs(a), b); }        /* Fortran SIGN (gfortran: -0.0 counts as negative) */
static int imin(int a, int b) { return a < b ? a : b; }
static int imax(int a, int b) { return a > b ? a : b; }

/* ---------------------------------------------------------------- the BLAS kernels, as OpenBLAS's Prescott ones add */
__attribute__((noinline)) static double k_nrm2_x87(int n, const double *x, int inc)
{
    long double s = 0.0L;
    for (int i = 0; i < n; i++) { long double v = x[(long)i * inc]; s += v * v; }
    __asm__("fsqrt" : "+t"(s));
    return (double)s;
}
static double k_nrm2(int n, const double *x, int inc)
{   /* nrm2.S: x87 registers (their wide exponent), squares summed in order, fsqrt; at the x87 precision numpy runs it with: 53
       bits (Python's threads start with control word 0x27F). Set here for the call: OpenMP's worker threads start at 64 bits, and
       there the sums came out other in 1,399 of 8,911 real systems (2026-10-16). */
    unsigned short cw, cw53;
    __asm__ __volatile__("fnstcw %0" : "=m"(cw) : : "memory");
    cw53 = (unsigned short)((cw & ~0x0F00) | 0x0200);                 /* precision 53 bits, round to nearest */
    __asm__ __volatile__("fldcw %0" : : "m"(cw53) : "memory");
    double r = k_nrm2_x87(n, x, inc);
    __asm__ __volatile__("fldcw %0" : : "m"(cw) : "memory");
    return r;
}
static void k_scal(int n, double a, double *x, int inc)
{
    for (int i = 0; i < n; i++) x[(long)i * inc] = a == 0.0 ? 0.0 : a * x[(long)i * inc];
}
static void k_swap(int n, double *x, int incx, double *y, int incy)
{
    for (int i = 0; i < n; i++) { double t = x[(long)i * incx]; x[(long)i * incx] = y[(long)i * incy]; y[(long)i * incy] = t; }
}
static void k_rot(int n, double *x, int incx, double *y, int incy, double c, double s)
{
    for (int i = 0; i < n; i++) { double a = x[(long)i * incx], b = y[(long)i * incy]; x[(long)i * incx] = c * a + s * b; y[(long)i * incy] = c * b - s * a; }
}
static int k_iamax(int n, const double *x, int inc)
{
    int k = 1; double m = n > 0 ? fabs(x[0]) : 0.0;
    for (int i = 1; i < n; i++) if (fabs(x[(long)i * inc]) > m) { m = fabs(x[(long)i * inc]); k = i + 1; }
    return n > 0 ? k : 0;
}
static void k_gemv_t(int m, int n, const double *A, int lda, const double *x, int incx, double *y)
{   /* y = A^T x (alpha 1, beta 0); numpy's: dgemv_t of OpenBLAS Prescott (see the head) */
    if (m <= 0 || n <= 0) return;
    int peel = (int)(((uintptr_t)A >> 3) & 1), ns = (n / 4) * 4;
    if (lda & 1) ns += ((n - ns) / 2) * 2;
#define X_(i) x[(long)(i) * incx]
    for (int j = 0; j < n; j++) {
        const double *a = A + (long)j * lda; double s; int r = 0;
        if (j < ns) {
            double lo = 0.0, hi = 0.0;
            if (peel) { lo += a[0] * X_(0); r = 1; }
            for (; m - r >= 2; r += 2) { lo += a[r] * X_(r); hi += a[r + 1] * X_(r + 1); }
            if (r < m) lo += a[r] * X_(r);
            s = lo + hi;
        } else {
            double a0l = 0.0, a0h = 0.0, a1l = 0.0, a1h = 0.0;
            if (peel) { a0l += a[0] * X_(0); r = 1; }
            for (; m - r >= 4; r += 4) { a0l += a[r] * X_(r); a0h += a[r + 1] * X_(r + 1); a1l += a[r + 2] * X_(r + 2); a1h += a[r + 3] * X_(r + 3); }
            if (m - r >= 2) { a0l += a[r] * X_(r); a0h += a[r + 1] * X_(r + 1); r += 2; }
            if (r < m) a0l += a[r] * X_(r);
            s = (a0l + a1l) + (a0h + a1h);
        }
        y[j] = 0.0 + s;
    }
#undef X_
}
static void k_gemv_n(int m, int n, const double *A, int lda, const double *x, int incx, double *y)
{   /* y = A x (alpha 1, beta 0) */
    if (m <= 0 || n <= 0) return;
    for (int i = 0; i < m; i++) {
        double s = 0.0;
        for (int j = 0; j < n; j++) s += A[i + (long)j * lda] * x[(long)j * incx];
        y[i] = s;
    }
}
static void k_ger(int m, int n, double alpha, const double *x, int incx, const double *y, int incy, double *A, int lda)
{
    if (m <= 0 || n <= 0 || alpha == 0.0) return;
    for (int j = 0; j < n; j++) {
        double t = alpha * y[(long)j * incy];
        for (int i = 0; i < m; i++) A[i + (long)j * lda] += t * x[(long)i * incx];
    }
}
static void k_gemm_tn(int m, int n, int k, const double *A, int lda, const double *B, int ldb, double *C, int ldc)
{   /* C = A^T B (alpha 1, beta 0), k < 8 */
    for (int j = 0; j < n; j++)
        for (int i = 0; i < m; i++) {
            double s = 0.0;
            for (int l = 0; l < k; l++) s += A[l + (long)i * lda] * B[l + (long)j * ldb];
            C[i + (long)j * ldc] = s;
        }
}

/* ---------------------------------------------------------------- LAPACK 3.10 (reference), 1-based as written there */
#define A_(i, j) a[((i) - 1) + (long)((j) - 1) * lda]
#define C_(i, j) c[((i) - 1) + (long)((j) - 1) * ldc]

static double dlapy2(double x, double y)
{
    int xn = isnan(x), yn = isnan(y); double r = 0.0;
    if (xn) r = x;
    if (yn) r = y;
    if (!(xn || yn)) {
        double xa = fabs(x), ya = fabs(y), w = xa > ya ? xa : ya, z = xa < ya ? xa : ya;
        if (z == 0.0 || w > HUGEV) r = w;
        else { double t = z / w; r = w * sqrt(1.0 + t * t); }
    }
    return r;
}
static void dlarfg(int n, double *alpha, double *x, int incx, double *tau)
{
    if (n <= 1) { *tau = 0.0; return; }
    double xnorm = k_nrm2(n - 1, x, incx);
    if (xnorm == 0.0) { *tau = 0.0; return; }
    double beta = -sgn(dlapy2(*alpha, xnorm), *alpha), safmin = SFMIN / EPS_E, rsafmn = 1.0 / safmin; int knt = 0;
    if (fabs(beta) < safmin) {
        do { knt++; k_scal(n - 1, rsafmn, x, incx); beta *= rsafmn; *alpha *= rsafmn; } while (fabs(beta) < safmin && knt < 20);
        xnorm = k_nrm2(n - 1, x, incx); beta = -sgn(dlapy2(*alpha, xnorm), *alpha);
    }
    *tau = (beta - *alpha) / beta;
    k_scal(n - 1, 1.0 / (*alpha - beta), x, incx);
    for (int j = 0; j < knt; j++) beta *= safmin;
    *alpha = beta;
}
static int iladlc(int m, int n, const double *a, int lda)
{
    if (n == 0) return n;
    if (A_(1, n) != 0.0 || A_(m, n) != 0.0) return n;
    for (int j = n; j >= 1; j--)
        for (int i = 1; i <= m; i++) if (A_(i, j) != 0.0) return j;
    return 0;
}
static int iladlr(int m, int n, const double *a, int lda)
{
    if (m == 0) return m;
    if (A_(m, 1) != 0.0 || A_(m, n) != 0.0) return m;
    int r = 0;
    for (int j = 1; j <= n; j++) {
        int i = m;
        while (i >= 1 && A_(imax(i, 1), j) == 0.0) i--;
        r = imax(r, i);
    }
    return r;
}
static void dlarf(char side, int m, int n, const double *v, int incv, double tau, double *c, int ldc, double *work)
{
    int left = side == 'L', lastv = 0, lastc = 0;
    if (tau != 0.0) {
        lastv = left ? m : n; int i = incv > 0 ? 1 + (lastv - 1) * incv : 1;
        while (lastv > 0 && v[i - 1] == 0.0) { lastv--; i -= incv; }
        lastc = left ? iladlc(lastv, n, c, ldc) : iladlr(m, lastv, c, ldc);
    }
    if (lastv <= 0) return;
    if (left) { k_gemv_t(lastv, lastc, c, ldc, v, incv, work); k_ger(lastv, lastc, -tau, v, incv, work, 1, c, ldc); }
    else { k_gemv_n(lastc, lastv, c, ldc, v, incv, work); k_ger(lastc, lastv, -tau, work, 1, v, incv, c, ldc); }
}
static void dgeqr2(int m, int n, double *a, int lda, double *tau, double *work)
{
    int k = imin(m, n);
    for (int i = 1; i <= k; i++) {
        dlarfg(m - i + 1, &A_(i, i), &A_(imin(i + 1, m), i), 1, &tau[i - 1]);
        if (i < n) { double aii = A_(i, i); A_(i, i) = 1.0; dlarf('L', m - i + 1, n - i, &A_(i, i), 1, tau[i - 1], &A_(i, i + 1), lda, work); A_(i, i) = aii; }
    }
}
static void dorm2r_lt(int m, int n, int k, double *a, int lda, const double *tau, double *c, int ldc, double *work)
{   /* SIDE 'L', TRANS 'T': H(1) first */
    for (int i = 1; i <= k; i++) {
        double aii = A_(i, i); A_(i, i) = 1.0; dlarf('L', m - i + 1, n, &A_(i, i), 1, tau[i - 1], &C_(i, 1), ldc, work); A_(i, i) = aii;
    }
}
static void dorml2_lt(int m, int n, int k, double *a, int lda, const double *tau, double *c, int ldc, double *work)
{   /* SIDE 'L', TRANS 'T': H(k) first */
    for (int i = k; i >= 1; i--) {
        double aii = A_(i, i); A_(i, i) = 1.0; dlarf('L', m - i + 1, n, &A_(i, i), lda, tau[i - 1], &C_(i, 1), ldc, work); A_(i, i) = aii;
    }
}
static void dgebd2_up(int m, int n, double *a, int lda, double *d, double *e, double *tauq, double *taup, double *work)
{   /* m >= n: upper bidiagonal */
    for (int i = 1; i <= n; i++) {
        dlarfg(m - i + 1, &A_(i, i), &A_(imin(i + 1, m), i), 1, &tauq[i - 1]);
        d[i - 1] = A_(i, i); A_(i, i) = 1.0;
        if (i < n) dlarf('L', m - i + 1, n - i, &A_(i, i), 1, tauq[i - 1], &A_(i, i + 1), lda, work);
        A_(i, i) = d[i - 1];
        if (i < n) {
            dlarfg(n - i, &A_(i, i + 1), &A_(i, imin(i + 2, n)), lda, &taup[i - 1]);
            e[i - 1] = A_(i, i + 1); A_(i, i + 1) = 1.0;
            dlarf('R', m - i, n - i, &A_(i, i + 1), lda, taup[i - 1], &A_(i + 1, i + 1), lda, work);
            A_(i, i + 1) = e[i - 1];
        } else taup[i - 1] = 0.0;
    }
}
static void dlartg(double f, double g, double *c, double *s, double *r)
{
    const double safmin = SFMIN, safmax = 1.0 / SFMIN, rtmin = sqrt(safmin), rtmax = sqrt(safmax / 2);
    double f1 = fabs(f), g1 = fabs(g);
    if (g == 0.0) { *c = 1.0; *s = 0.0; *r = f; }
    else if (f == 0.0) { *c = 0.0; *s = sgn(1.0, g); *r = g1; }
    else if (f1 > rtmin && f1 < rtmax && g1 > rtmin && g1 < rtmax) {
        double d = sqrt(f * f + g * g), p = 1.0 / d; *c = f1 * p; *s = g * sgn(p, f); *r = sgn(d, f);
    } else {
        double u = fmin(safmax, fmax(safmin, fmax(f1, g1))), fs = f / u, gs = g / u, d = sqrt(fs * fs + gs * gs), p = 1.0 / d;
        *c = fabs(fs) * p; *s = gs * sgn(p, f); *r = sgn(d, f) * u;
    }
}
static void dlas2(double f, double g, double h, double *ssmin, double *ssmax)
{
    double fa = fabs(f), ga = fabs(g), ha = fabs(h), fhmn = fmin(fa, ha), fhmx = fmax(fa, ha);
    if (fhmn == 0.0) {
        *ssmin = 0.0;
        if (fhmx == 0.0) *ssmax = ga;
        else { double t = fmin(fhmx, ga) / fmax(fhmx, ga); *ssmax = fmax(fhmx, ga) * sqrt(1.0 + t * t); }
    } else if (ga < fhmx) {
        double as = 1.0 + fhmn / fhmx, at = (fhmx - fhmn) / fhmx, au = (ga / fhmx) * (ga / fhmx), c = 2.0 / (sqrt(as * as + au) + sqrt(at * at + au));
        *ssmin = fhmn * c; *ssmax = fhmx / c;
    } else {
        double au = fhmx / ga;
        if (au == 0.0) { *ssmin = (fhmn * fhmx) / ga; *ssmax = ga; }
        else {
            double as = 1.0 + fhmn / fhmx, at = (fhmx - fhmn) / fhmx, p = as * au, q = at * au, c = 1.0 / (sqrt(1.0 + p * p) + sqrt(1.0 + q * q));
            *ssmin = (fhmn * c) * au; *ssmin = *ssmin + *ssmin; *ssmax = ga / (c + c);
        }
    }
}
static void dlasv2(double f, double g, double h, double *ssmin, double *ssmax, double *snr, double *csr, double *snl, double *csl)
{
    double ft = f, fa = fabs(ft), ht = h, ha = fabs(h), gt, ga, clt = 0, crt = 0, slt = 0, srt = 0, tsign = 1.0; int pmax = 1, swap = ha > fa;
    if (swap) { pmax = 3; double t = ft; ft = ht; ht = t; t = fa; fa = ha; ha = t; }
    gt = g; ga = fabs(gt);
    if (ga == 0.0) { *ssmin = ha; *ssmax = fa; clt = 1.0; crt = 1.0; slt = 0.0; srt = 0.0; }
    else {
        int gasmal = 1;
        if (ga > fa) {
            pmax = 2;
            if (fa / ga < EPS_E) {
                gasmal = 0; *ssmax = ga;
                *ssmin = ha > 1.0 ? fa / (ga / ha) : (fa / ga) * ha;
                clt = 1.0; slt = ht / gt; srt = 1.0; crt = ft / gt;
            }
        }
        if (gasmal) {
            double d = fa - ha, l = d == fa ? 1.0 : d / fa, m = gt / ft, t = 2.0 - l, mm = m * m, tt = t * t, s = sqrt(tt + mm);
            double r = l == 0.0 ? fabs(m) : sqrt(l * l + mm), a = 0.5 * (s + r);
            *ssmin = ha / a; *ssmax = fa * a;
            if (mm == 0.0) t = l == 0.0 ? sgn(2.0, ft) * sgn(1.0, gt) : gt / sgn(d, ft) + m / t;
            else t = (m / (s + t) + m / (r + l)) * (1.0 + a);
            l = sqrt(t * t + 4.0); crt = 2.0 / l; srt = t / l; clt = (crt + srt * m) / a; slt = (ht / ft) * srt / a;
        }
    }
    if (swap) { *csl = srt; *snl = crt; *csr = slt; *snr = clt; }
    else { *csl = clt; *snl = slt; *csr = crt; *snr = srt; }
    if (pmax == 1) tsign = sgn(1.0, *csr) * sgn(1.0, *csl) * sgn(1.0, f);
    if (pmax == 2) tsign = sgn(1.0, *snr) * sgn(1.0, *csl) * sgn(1.0, g);
    if (pmax == 3) tsign = sgn(1.0, *snr) * sgn(1.0, *snl) * sgn(1.0, h);
    *ssmax = sgn(*ssmax, tsign);
    *ssmin = sgn(*ssmin, tsign * sgn(1.0, f) * sgn(1.0, h));
}
static void dlasr_lv(char direct, int m, int n, const double *cs, const double *sn, double *a, int lda)
{   /* SIDE 'L', PIVOT 'V' */
    for (int jj = 1; jj <= m - 1; jj++) {
        int j = direct == 'F' ? jj : m - jj;
        double ct = cs[j - 1], st = sn[j - 1];
        if (ct != 1.0 || st != 0.0)
            for (int i = 1; i <= n; i++) { double t = A_(j + 1, i); A_(j + 1, i) = ct * t - st * A_(j, i); A_(j, i) = st * t + ct * A_(j, i); }
    }
}
static void dlasr_rv(char direct, int m, int n, const double *cs, const double *sn, double *a, int lda)
{   /* SIDE 'R', PIVOT 'V': A P^T, the rotations between columns j and j + 1 */
    for (int jj = 1; jj <= n - 1; jj++) {
        int j = direct == 'F' ? jj : n - jj;
        double ct = cs[j - 1], st = sn[j - 1];
        if (ct != 1.0 || st != 0.0)
            for (int i = 1; i <= m; i++) { double t = A_(i, j + 1); A_(i, j + 1) = ct * t - st * A_(i, j); A_(i, j) = st * t + ct * A_(i, j); }
    }
}
/* dbdsqr, UPLO 'U': the singular values of the n x n upper bidiagonal (d, e) with VT (ncvt columns), U (nru rows) and C (ncc
   columns) updated; work >= 4 (n - 1). Returns info (0 = converged). */
static int dbdsqr_u(int n, int ncvt, int nru, int ncc, double *d, double *e, double *vt, int ldvt, double *u, int ldu, double *c, int ldc, double *work)
{
    const int maxitr = 6; int info = 0;
    if (n == 0) return 0;
    if (n > 1) {
        int nm1 = n - 1, nm12 = nm1 + nm1, nm13 = nm12 + nm1, idir = 0;
        /* TOLMUL = MAX(10, MIN(100, EPS**(-1/8))): 98.70149282610821 by every pow here (numpy's DLL takes the UCRT's), written out
           so that no C runtime's pow can move its last bit */
        double eps = EPS_E, unfl = SFMIN, tolmul = 98.70149282610821, tol = tolmul * eps, smax = 0.0, sminl = 0.0, sminoa, mu, thresh;
        for (int i = 1; i <= n; i++) smax = fmax(smax, fabs(d[i - 1]));
        for (int i = 1; i <= n - 1; i++) smax = fmax(smax, fabs(e[i - 1]));
        sminoa = fabs(d[0]);
        if (sminoa != 0.0) {
            mu = sminoa;
            for (int i = 2; i <= n; i++) { mu = fabs(d[i - 1]) * (mu / (mu + fabs(e[i - 2]))); sminoa = fmin(sminoa, mu); if (sminoa == 0.0) break; }
        }
        sminoa = sminoa / sqrt((double)n);
        thresh = fmax(tol * sminoa, maxitr * (n * (n * unfl)));
        int maxitdivn = maxitr * n, iterdivn = 0, iter = -1, oldll = -1, oldm = -1, m = n, ll = 0;
        for (;;) {                                                    /* label 60 */
            if (m <= 1) break;
            if (iter >= n) { iter -= n; iterdivn++; if (iterdivn >= maxitdivn) goto fail; }
            double abss, abse; int split = 0;
            smax = fabs(d[m - 1]);
            for (int lll = 1; lll <= m - 1; lll++) {
                ll = m - lll; abss = fabs(d[ll - 1]); abse = fabs(e[ll - 1]);
                if (abse <= thresh) { split = 1; break; }
                smax = fmax(smax, fmax(abss, abse));
            }
            if (split) {
                e[ll - 1] = 0.0;
                if (ll == m - 1) { m = m - 1; continue; }
            } else ll = 0;
            ll = ll + 1;
            if (ll == m - 1) {                                        /* 2 x 2 block */
                double sigmn, sigmx, sinr, cosr, sinl, cosl;
                dlasv2(d[m - 2], e[m - 2], d[m - 1], &sigmn, &sigmx, &sinr, &cosr, &sinl, &cosl);
                d[m - 2] = sigmx; e[m - 2] = 0.0; d[m - 1] = sigmn;
                if (ncvt > 0) k_rot(ncvt, &vt[(m - 2)], ldvt, &vt[(m - 1)], ldvt, cosr, sinr);
                if (nru > 0) k_rot(nru, &u[(long)(m - 2) * ldu], 1, &u[(long)(m - 1) * ldu], 1, cosl, sinl);
                if (ncc > 0) k_rot(ncc, &c[(m - 2)], ldc, &c[(m - 1)], ldc, cosl, sinl);
                m = m - 2; continue;
            }
            if (ll > oldm || m < oldll) idir = fabs(d[ll - 1]) >= fabs(d[m - 1]) ? 1 : 2;
            if (idir == 1) {
                if (fabs(e[m - 2]) <= fabs(tol) * fabs(d[m - 1])) { e[m - 2] = 0.0; continue; }
                mu = fabs(d[ll - 1]); sminl = mu; int conv = 0;
                for (int lll = ll; lll <= m - 1; lll++) {
                    if (fabs(e[lll - 1]) <= tol * mu) { e[lll - 1] = 0.0; conv = 1; break; }
                    mu = fabs(d[lll]) * (mu / (mu + fabs(e[lll - 1]))); sminl = fmin(sminl, mu);
                }
                if (conv) continue;
            } else {
                if (fabs(e[ll - 1]) <= fabs(tol) * fabs(d[ll - 1])) { e[ll - 1] = 0.0; continue; }
                mu = fabs(d[m - 1]); sminl = mu; int conv = 0;
                for (int lll = m - 1; lll >= ll; lll--) {
                    if (fabs(e[lll - 1]) <= tol * mu) { e[lll - 1] = 0.0; conv = 1; break; }
                    mu = fabs(d[lll - 1]) * (mu / (mu + fabs(e[lll - 1]))); sminl = fmin(sminl, mu);
                }
                if (conv) continue;
            }
            oldll = ll; oldm = m;
            double shift, r, sll;
            if (n * tol * (sminl / smax) <= fmax(eps, 0.01 * tol)) shift = 0.0;
            else {
                if (idir == 1) { sll = fabs(d[ll - 1]); dlas2(d[m - 2], e[m - 2], d[m - 1], &shift, &r); }
                else { sll = fabs(d[m - 1]); dlas2(d[ll - 1], e[ll - 1], d[ll], &shift, &r); }
                if (sll > 0.0) { double q = shift / sll; if (q * q < eps) shift = 0.0; }
            }
            iter = iter + m - ll;
            if (shift == 0.0) {
                if (idir == 1) {
                    double cs = 1.0, oldcs = 1.0, sn = 0.0, oldsn = 0.0, h;
                    for (int i = ll; i <= m - 1; i++) {
                        dlartg(d[i - 1] * cs, e[i - 1], &cs, &sn, &r);
                        if (i > ll) e[i - 2] = oldsn * r;
                        dlartg(oldcs * r, d[i] * sn, &oldcs, &oldsn, &d[i - 1]);
                        work[i - ll] = cs; work[i - ll + nm1] = sn; work[i - ll + nm12] = oldcs; work[i - ll + nm13] = oldsn;
                    }
                    h = d[m - 1] * cs; d[m - 1] = h * oldcs; e[m - 2] = h * oldsn;
                    if (ncvt > 0) dlasr_lv('F', m - ll + 1, ncvt, &work[0], &work[n - 1], &vt[ll - 1], ldvt);
                    if (nru > 0) dlasr_rv('F', nru, m - ll + 1, &work[nm12], &work[nm13], &u[(long)(ll - 1) * ldu], ldu);
                    if (ncc > 0) dlasr_lv('F', m - ll + 1, ncc, &work[nm12], &work[nm13], &c[ll - 1], ldc);
                    if (fabs(e[m - 2]) <= thresh) e[m - 2] = 0.0;
                } else {
                    double cs = 1.0, oldcs = 1.0, sn = 0.0, oldsn = 0.0, h;
                    for (int i = m; i >= ll + 1; i--) {
                        dlartg(d[i - 1] * cs, e[i - 2], &cs, &sn, &r);
                        if (i < m) e[i - 1] = oldsn * r;
                        dlartg(oldcs * r, d[i - 2] * sn, &oldcs, &oldsn, &d[i - 1]);
                        work[i - ll - 1] = cs; work[i - ll - 1 + nm1] = -sn; work[i - ll - 1 + nm12] = oldcs; work[i - ll - 1 + nm13] = -oldsn;
                    }
                    h = d[ll - 1] * cs; d[ll - 1] = h * oldcs; e[ll - 1] = h * oldsn;
                    if (ncvt > 0) dlasr_lv('B', m - ll + 1, ncvt, &work[nm12], &work[nm13], &vt[ll - 1], ldvt);
                    if (nru > 0) dlasr_rv('B', nru, m - ll + 1, &work[0], &work[n - 1], &u[(long)(ll - 1) * ldu], ldu);
                    if (ncc > 0) dlasr_lv('B', m - ll + 1, ncc, &work[0], &work[n - 1], &c[ll - 1], ldc);
                    if (fabs(e[ll - 1]) <= thresh) e[ll - 1] = 0.0;
                }
            } else {
                double f, g, cosr, sinr, cosl, sinl;
                if (idir == 1) {
                    f = (fabs(d[ll - 1]) - shift) * (sgn(1.0, d[ll - 1]) + shift / d[ll - 1]); g = e[ll - 1];
                    for (int i = ll; i <= m - 1; i++) {
                        dlartg(f, g, &cosr, &sinr, &r);
                        if (i > ll) e[i - 2] = r;
                        f = cosr * d[i - 1] + sinr * e[i - 1]; e[i - 1] = cosr * e[i - 1] - sinr * d[i - 1];
                        g = sinr * d[i]; d[i] = cosr * d[i];
                        dlartg(f, g, &cosl, &sinl, &r);
                        d[i - 1] = r; f = cosl * e[i - 1] + sinl * d[i]; d[i] = cosl * d[i] - sinl * e[i - 1];
                        if (i < m - 1) { g = sinl * e[i]; e[i] = cosl * e[i]; }
                        work[i - ll] = cosr; work[i - ll + nm1] = sinr; work[i - ll + nm12] = cosl; work[i - ll + nm13] = sinl;
                    }
                    e[m - 2] = f;
                    if (ncvt > 0) dlasr_lv('F', m - ll + 1, ncvt, &work[0], &work[n - 1], &vt[ll - 1], ldvt);
                    if (nru > 0) dlasr_rv('F', nru, m - ll + 1, &work[nm12], &work[nm13], &u[(long)(ll - 1) * ldu], ldu);
                    if (ncc > 0) dlasr_lv('F', m - ll + 1, ncc, &work[nm12], &work[nm13], &c[ll - 1], ldc);
                    if (fabs(e[m - 2]) <= thresh) e[m - 2] = 0.0;
                } else {
                    f = (fabs(d[m - 1]) - shift) * (sgn(1.0, d[m - 1]) + shift / d[m - 1]); g = e[m - 2];
                    for (int i = m; i >= ll + 1; i--) {
                        dlartg(f, g, &cosr, &sinr, &r);
                        if (i < m) e[i - 1] = r;
                        f = cosr * d[i - 1] + sinr * e[i - 2]; e[i - 2] = cosr * e[i - 2] - sinr * d[i - 1];
                        g = sinr * d[i - 2]; d[i - 2] = cosr * d[i - 2];
                        dlartg(f, g, &cosl, &sinl, &r);
                        d[i - 1] = r; f = cosl * e[i - 2] + sinl * d[i - 2]; d[i - 2] = cosl * d[i - 2] - sinl * e[i - 2];
                        if (i > ll + 1) { g = sinl * e[i - 3]; e[i - 3] = cosl * e[i - 3]; }
                        work[i - ll - 1] = cosr; work[i - ll - 1 + nm1] = -sinr; work[i - ll - 1 + nm12] = cosl; work[i - ll - 1 + nm13] = -sinl;
                    }
                    e[ll - 1] = f;
                    if (fabs(e[ll - 1]) <= thresh) e[ll - 1] = 0.0;
                    if (ncvt > 0) dlasr_lv('B', m - ll + 1, ncvt, &work[nm12], &work[nm13], &vt[ll - 1], ldvt);
                    if (nru > 0) dlasr_rv('B', nru, m - ll + 1, &work[0], &work[n - 1], &u[(long)(ll - 1) * ldu], ldu);
                    if (ncc > 0) dlasr_lv('B', m - ll + 1, ncc, &work[0], &work[n - 1], &c[ll - 1], ldc);
                }
            }
        }
    }
    for (int i = 1; i <= n; i++)                                       /* label 160: make them positive */
        if (d[i - 1] < 0.0) { d[i - 1] = -d[i - 1]; if (ncvt > 0) k_scal(ncvt, -1.0, &vt[i - 1], ldvt); }
    for (int i = 1; i <= n - 1; i++) {                                 /* decreasing order */
        int isub = 1; double smin = d[0];
        for (int j = 2; j <= n + 1 - i; j++) if (d[j - 1] <= smin) { isub = j; smin = d[j - 1]; }
        if (isub != n + 1 - i) {
            d[isub - 1] = d[n - i]; d[n - i] = smin;
            if (ncvt > 0) k_swap(ncvt, &vt[isub - 1], ldvt, &vt[n - i], ldvt);
            if (nru > 0) k_swap(nru, &u[(long)(isub - 1) * ldu], 1, &u[(long)(n - i) * ldu], 1);
            if (ncc > 0) k_swap(ncc, &c[isub - 1], ldc, &c[n - i], ldc);
        }
    }
    return info;
fail:
    for (int i = 1; i <= n - 1; i++) if (e[i - 1] != 0.0) info++;
    return info;
}
static int dlasdq_u(int n, int ncvt, int nru, int ncc, double *d, double *e, double *vt, int ldvt, double *u, int ldu, double *c, int ldc, double *work)
{   /* SQRE 0, UPLO 'U': dbdsqr, then the singular values sorted (one transposition per vector) */
    int info = dbdsqr_u(n, ncvt, nru, ncc, d, e, vt, ldvt, u, ldu, c, ldc, work);
    for (int i = 1; i <= n; i++) {
        int isub = i; double smin = d[i - 1];
        for (int j = i + 1; j <= n; j++) if (d[j - 1] < smin) { isub = j; smin = d[j - 1]; }
        if (isub != i) {
            d[isub - 1] = d[i - 1]; d[i - 1] = smin;
            if (ncvt > 0) k_swap(ncvt, &vt[isub - 1], ldvt, &vt[i - 1], ldvt);
            if (nru > 0) k_swap(nru, &u[(long)(isub - 1) * ldu], 1, &u[(long)(i - 1) * ldu], 1);
            if (ncc > 0) k_swap(ncc, &c[isub - 1], ldc, &c[i - 1], ldc);
        }
    }
    return info;
}
static void dlascl_g(double cfrom, double cto, int m, int n, double *a, int lda)
{
    double smlnum = SFMIN, bignum = 1.0 / smlnum, cfromc = cfrom, ctoc = cto, mul; int done = 0;
    while (!done) {
        double cfrom1 = cfromc * smlnum, cto1;
        if (cfrom1 == cfromc) { mul = ctoc / cfromc; done = 1; }
        else {
            cto1 = ctoc / bignum;
            if (cto1 == ctoc) { mul = ctoc; done = 1; cfromc = 1.0; }
            else if (fabs(cfrom1) > fabs(ctoc) && ctoc != 0.0) { mul = smlnum; cfromc = cfrom1; }
            else if (fabs(cto1) > fabs(cfromc)) { mul = bignum; ctoc = cto1; }
            else { mul = ctoc / cfromc; done = 1; if (mul == 1.0) return; }
        }
        for (int j = 1; j <= n; j++) for (int i = 1; i <= m; i++) A_(i, j) = A_(i, j) * mul;
    }
}
static double dlanst_m(int n, const double *d, const double *e)
{
    if (n <= 0) return 0.0;
    double an = fabs(d[n - 1]);
    for (int i = 1; i <= n - 1; i++) {
        double s = fabs(d[i - 1]); if (an < s || isnan(s)) an = s;
        s = fabs(e[i - 1]); if (an < s || isnan(s)) an = s;
    }
    return an;
}
/* dlalsd, UPLO 'U', n <= SMLSIZ (25): the bidiagonal least squares problem; b (n x nrhs) is overwritten by the solution */
static int dlalsd_small(int n, int nrhs, double *d, double *e, double *b, int ldb, double rcond, int *rank, double *work)
{
    double eps = EPS_E, rcnd = (rcond <= 0.0 || rcond >= 1.0) ? eps : rcond; int info = 0;
    *rank = 0;
    if (n == 0) return 0;
    if (n == 1) {
        if (d[0] == 0.0) { for (int j = 0; j < nrhs; j++) b[(long)j * ldb] = 0.0; }
        else { *rank = 1; dlascl_g(d[0], 1.0, 1, nrhs, b, ldb); d[0] = fabs(d[0]); }
        return 0;
    }
    int nm1 = n - 1; double orgnrm = dlanst_m(n, d, e);
    if (orgnrm == 0.0) { for (int j = 0; j < nrhs; j++) for (int i = 0; i < n; i++) b[i + (long)j * ldb] = 0.0; return 0; }
    dlascl_g(orgnrm, 1.0, n, 1, d, n); dlascl_g(orgnrm, 1.0, nm1, 1, e, nm1);
    int nwork = n * n;                                                /* WORK(1 + N*N) */
    for (int j = 0; j < n; j++) for (int i = 0; i < n; i++) work[i + j * n] = i == j ? 1.0 : 0.0;
    info = dlasdq_u(n, n, 0, nrhs, d, e, work, n, NULL, 1, b, ldb, work + nwork);
    if (info != 0) return info;
    double tol = rcnd * fabs(d[k_iamax(n, d, 1) - 1]);
    for (int i = 1; i <= n; i++) {
        if (d[i - 1] <= tol) { for (int j = 0; j < nrhs; j++) b[(i - 1) + (long)j * ldb] = 0.0; }
        else { dlascl_g(d[i - 1], 1.0, 1, nrhs, &b[i - 1], ldb); (*rank)++; }
    }
    k_gemm_tn(n, nrhs, n, work, n, b, ldb, work + nwork, n);
    for (int j = 0; j < nrhs; j++) for (int i = 0; i < n; i++) b[i + (long)j * ldb] = work[nwork + i + j * n];
    dlascl_g(1.0, orgnrm, n, 1, d, n);
    for (int i = 1; i < n; i++)                                       /* dlasrt 'D' (insertion sort, n <= 20) */
        for (int j = i; j >= 1 && d[j] > d[j - 1]; j--) { double t = d[j]; d[j] = d[j - 1]; d[j - 1] = t; }
    dlascl_g(orgnrm, 1.0, n, nrhs, b, ldb);
    return 0;
}
static double dlange_m(int m, int n, const double *a, int lda)
{
    double v = 0.0;
    for (int j = 1; j <= n; j++) for (int i = 1; i <= m; i++) { double t = fabs(A_(i, j)); if (v < t || isnan(t)) v = t; }
    return v;
}
/* dgelsd for m >= n (paths 1 and 1a); a (lda >= m) and b (ldb >= m) as numpy lays them out; s gets the singular values.
   Returns info; -100 = outside what this file models (m < n, m > MAXM, nrhs > MAXRHS, a scaled matrix). */
static int dgelsd_(int m, int n, int nrhs, double *a, int lda, double *b, int ldb, double *s, double rcond, int *rank)
{
    if (m < n || m > MAXM || nrhs > MAXRHS || n < 1) return -100;
    double work[4 * MAXM + MAXM * MAXM + MAXM * MAXRHS + 8 * MAXM], *tau = work, *ie = work + MAXM, *tauq = ie + MAXM, *taup = tauq + MAXM, *wk = taup + MAXM;
    double smlnum = SFMIN / EPS_P, bignum = 1.0 / smlnum;
    double anrm = dlange_m(m, n, a, lda);
    if (anrm == 0.0) { for (int j = 0; j < nrhs; j++) for (int i = 0; i < imax(m, n); i++) b[i + (long)j * ldb] = 0.0; for (int i = 0; i < n; i++) s[i] = 0.0; *rank = 0; return 0; }
    if (anrm < smlnum || anrm > bignum) return -100;
    double bnrm = dlange_m(m, nrhs, b, ldb);
    if ((bnrm > 0.0 && bnrm < smlnum) || bnrm > bignum) return -100;
    int mm = m, mnthr = (int)((float)imin(m, n) * 1.6f), info;       /* ilaenv(6, 'DGELSD'): INT(REAL(MIN(M,N)) * 1.6E0) */
    if (m >= mnthr) {
        mm = n;
        dgeqr2(m, n, a, lda, tau, wk);
        dorm2r_lt(m, nrhs, n, a, lda, tau, b, ldb, wk);
        for (int j = 1; j <= n - 1; j++) for (int i = j + 1; i <= n; i++) A_(i, j) = 0.0;
    }
    dgebd2_up(mm, n, a, lda, s, ie, tauq, taup, wk);
    dorm2r_lt(mm, nrhs, n, a, lda, tauq, b, ldb, wk);                /* dormbr 'Q' 'L' 'T': nq = mm >= k = n -> dormqr -> dorm2r */
    info = dlalsd_small(n, nrhs, s, ie, b, ldb, rcond, rank, wk);
    if (info != 0) return info;
    if (n > 1) dorml2_lt(n - 1, nrhs, n - 1, &A_(1, 2), lda, taup, &b[1], ldb, wk);   /* dormbr 'P' 'L' 'N': nq = k -> dormlq 'T' on rows 2.. -> dorml2 */
    return 0;
}

static void dorm2r_ln(int m, int n, int k, double *a, int lda, const double *tau, double *c, int ldc, double *work)
{   /* SIDE 'L', TRANS 'N': H(k) first */
    for (int i = k; i >= 1; i--) {
        double aii = A_(i, i); A_(i, i) = 1.0; dlarf('L', m - i + 1, n, &A_(i, i), 1, tau[i - 1], &C_(i, 1), ldc, work); A_(i, i) = aii;
    }
}
static void dorml2_rn(int m, int n, int k, double *a, int lda, const double *tau, double *c, int ldc, double *work)
{   /* SIDE 'R', TRANS 'N': H(k) first */
    for (int i = k; i >= 1; i--) {
        double aii = A_(i, i); A_(i, i) = 1.0; dlarf('R', m, n - i + 1, &A_(i, i), lda, tau[i - 1], &C_(1, i), ldc, work); A_(i, i) = aii;
    }
}
/* dbdsdc, UPLO 'U', COMPQ 'I', n <= SMLSIZ (25): U and VT start as identities, dlasdq, then the selection sort (decreasing) */
static int dbdsdc_ui(int n, double *d, double *e, double *u, int ldu, double *vt, int ldvt, double *work)
{
    if (n == 1) { u[0] = sgn(1.0, d[0]); vt[0] = 1.0; d[0] = fabs(d[0]); return 0; }
    for (int j = 0; j < n; j++) for (int i = 0; i < n; i++) { u[i + (long)j * ldu] = i == j ? 1.0 : 0.0; vt[i + (long)j * ldvt] = i == j ? 1.0 : 0.0; }
    int info = dlasdq_u(n, n, n, 0, d, e, vt, ldvt, u, ldu, NULL, 1, work);
    for (int ii = 2; ii <= n; ii++) {                                  /* label 40 */
        int i = ii - 1, kk = i; double p = d[i - 1];
        for (int j = ii; j <= n; j++) if (d[j - 1] > p) { kk = j; p = d[j - 1]; }
        if (kk != i) { d[kk - 1] = d[i - 1]; d[i - 1] = p; k_swap(n, &u[(long)(i - 1) * ldu], 1, &u[(long)(kk - 1) * ldu], 1); k_swap(n, &vt[i - 1], ldvt, &vt[kk - 1], ldvt); }
    }
    return info;
}
/* dgesdd, JOBZ 'A', m >= n with m < MNTHR = INT(n 11 / 6) (path 5a: no QR first; every square matrix): A = U S VT. Returns info;
   -100 = outside what this file models. */
static int dgesdd_a(int m, int n, double *a, int lda, double *s, double *u, int ldu, double *vt, int ldvt)
{
    if (n < 1 || m < n || m > MAXM || m >= (int)(imin(m, n) * 11.0 / 6.0)) return -100;
    double smlnum = sqrt(SFMIN) / EPS_P, bignum = 1.0 / smlnum, anrm = dlange_m(m, n, a, lda);
    if (isnan(anrm)) return -4;
    if ((anrm > 0.0 && anrm < smlnum) || anrm > bignum) return -100;
    double e[MAXM], tauq[MAXM], taup[MAXM], wk[8 * MAXM * MAXM];
    dgebd2_up(m, n, a, lda, s, e, tauq, taup, wk);
    for (int j = 0; j < m; j++) for (int i = 0; i < m; i++) u[i + (long)j * ldu] = 0.0;
    int info = dbdsdc_ui(n, s, e, u, ldu, vt, ldvt, wk);
    for (int j = n; j < m; j++) u[j + (long)j * ldu] = 1.0;           /* U's lower right corner: identity */
    dorm2r_ln(m, m, n, a, lda, tauq, u, ldu, wk);                      /* dormbr 'Q' 'L' 'N': nq = m >= k = n -> dormqr -> dorm2r */
    if (n > 1) dorml2_rn(n, n - 1, n - 1, &A_(1, 2), lda, taup, &vt[ldvt], ldvt, wk);   /* dormbr 'P' 'R' 'T': nq = n <= k -> dormlq 'N' on columns 2.. -> dorml2 */
    return info;
}

/* ---------------------------------------------------------------- what Python calls */
/* np.linalg.lstsq(A, B, rcond=None)[0] for `count` systems of one shape: A (count, m, n) and B (count, m, nrhs) row-major
   (numpy's C order), X (count, n, nrhs). info per system (0 = done, -100 = not modelled, else dbdsqr's count). Each system gets
   numpy's memory layout: one 16-byte aligned block, A column-major first, B column-major (ldb = max(m, n)) right after. */
__declspec(dllexport) int np_lstsq(int count, int m, int n, int nrhs, const double *A, const double *B, double *X, double *S, int *rank, int *info)
{
    if (m < n || m > MAXM || nrhs > MAXRHS || n < 1 || nrhs < 1) return -100;
    int bad = 0;
#pragma omp parallel for schedule(static) reduction(+:bad) if(count > 4000)
    for (int k = 0; k < count; k++) {
        double blk[MAXM * MAXM + MAXM * MAXRHS + MAXM] __attribute__((aligned(16))), *a = blk, *b = blk + m * n, s[MAXM]; int rk = 0;
        const double *Ak = A + (long)k * m * n, *Bk = B + (long)k * m * nrhs;
        for (int j = 0; j < n; j++) for (int i = 0; i < m; i++) a[i + j * m] = Ak[i * n + j];
        for (int j = 0; j < nrhs; j++) for (int i = 0; i < m; i++) b[i + j * m] = Bk[i * nrhs + j];
        int r = dgelsd_(m, n, nrhs, a, m, b, m, s, EPS_P * m, &rk);
        for (int i = 0; i < n; i++) for (int j = 0; j < nrhs; j++) X[(long)k * n * nrhs + i * nrhs + j] = b[i + j * m];
        if (S) for (int i = 0; i < n; i++) S[(long)k * n + i] = s[i];
        if (rank) rank[k] = rk;
        if (info) info[k] = r;
        bad += r != 0;
    }
    return bad;
}
/* np.linalg.svd(A) (full_matrices, compute_uv) for `count` systems of one shape: A (count, m, n) row-major -> U (count, m, m),
   S (count, n), Vh (count, n, n) row-major. numpy's layout: one 16-byte aligned block of A, S, U, VT (column-major). */
__declspec(dllexport) int np_svd(int count, int m, int n, const double *A, double *U, double *S, double *Vh, int *info)
{
    if (n < 1 || m < n || m > MAXM) return -100;
    int bad = 0;
#pragma omp parallel for schedule(static) reduction(+:bad) if(count > 4000)
    for (int k = 0; k < count; k++) {
        double blk[MAXM * MAXM * 3 + MAXM] __attribute__((aligned(16))), *a = blk, *s = a + m * n, *u = s + n, *vt = u + m * m;
        const double *Ak = A + (long)k * m * n;
        for (int j = 0; j < n; j++) for (int i = 0; i < m; i++) a[i + j * m] = Ak[i * n + j];
        int r = dgesdd_a(m, n, a, m, s, u, m, vt, n);
        for (int i = 0; i < m; i++) for (int j = 0; j < m; j++) U[(long)k * m * m + i * m + j] = u[i + j * m];
        for (int i = 0; i < n; i++) S[(long)k * n + i] = s[i];
        for (int i = 0; i < n; i++) for (int j = 0; j < n; j++) Vh[(long)k * n * n + i * n + j] = vt[i + j * n];
        if (info) info[k] = r;
        bad += r != 0;
    }
    return bad;
}
/* the pieces, for the tests against numpy's DLL (column-major, the caller's memory) */
__declspec(dllexport) void npl_dlarfg(int n, double *alpha, double *x, int incx, double *tau) { dlarfg(n, alpha, x, incx, tau); }
__declspec(dllexport) void npl_dgeqr2(int m, int n, double *a, int lda, double *tau) { double w[MAXM * 4]; dgeqr2(m, n, a, lda, tau, w); }
__declspec(dllexport) void npl_dgebd2(int m, int n, double *a, int lda, double *d, double *e, double *tq, double *tp) { double w[MAXM * 4]; dgebd2_up(m, n, a, lda, d, e, tq, tp, w); }
__declspec(dllexport) void npl_dlasv2(double f, double g, double h, double *o) { dlasv2(f, g, h, o, o + 1, o + 2, o + 3, o + 4, o + 5); }
__declspec(dllexport) void npl_dlas2(double f, double g, double h, double *o) { dlas2(f, g, h, o, o + 1); }
__declspec(dllexport) void npl_dlartg(double f, double g, double *o) { dlartg(f, g, o, o + 1, o + 2); }
__declspec(dllexport) int npl_dbdsqr(int n, int ncvt, int ncc, double *d, double *e, double *vt, int ldvt, double *c, int ldc) { double w[4 * MAXM * 4]; return dbdsqr_u(n, ncvt, 0, ncc, d, e, vt, ldvt, NULL, 1, c, ldc, w); }
__declspec(dllexport) int npl_dlasdq(int n, int ncvt, int ncc, double *d, double *e, double *vt, int ldvt, double *c, int ldc) { double w[4 * MAXM * 4]; return dlasdq_u(n, ncvt, 0, ncc, d, e, vt, ldvt, NULL, 1, c, ldc, w); }
__declspec(dllexport) int npl_dbdsqr_u(int n, int ncvt, int nru, int ncc, double *d, double *e, double *vt, int ldvt, double *u, int ldu, double *c, int ldc) { double w[4 * MAXM * 4]; return dbdsqr_u(n, ncvt, nru, ncc, d, e, vt, ldvt, u, ldu, c, ldc, w); }
__declspec(dllexport) int npl_dbdsdc(int n, double *d, double *e, double *u, int ldu, double *vt, int ldvt) { double w[4 * MAXM * 4]; return dbdsdc_ui(n, d, e, u, ldu, vt, ldvt, w); }
__declspec(dllexport) int npl_dgesdd(int m, int n, double *a, int lda, double *s, double *u, int ldu, double *vt, int ldvt) { return dgesdd_a(m, n, a, lda, s, u, ldu, vt, ldvt); }
__declspec(dllexport) int npl_dlalsd(int n, int nrhs, double *d, double *e, double *b, int ldb, double rcond, int *rank) { double w[MAXM * MAXM + MAXM * MAXRHS + 64]; return dlalsd_small(n, nrhs, d, e, b, ldb, rcond, rank, w); }
__declspec(dllexport) int npl_dgelsd(int m, int n, int nrhs, double *a, int lda, double *b, int ldb, double *s, double rcond, int *rank) { return dgelsd_(m, n, nrhs, a, lda, b, ldb, s, rcond, rank); }
__declspec(dllexport) double npl_dnrm2(int n, const double *x, int inc) { return k_nrm2(n, x, inc); }
__declspec(dllexport) void npl_dorm2r(int m, int n, int k, double *a, int lda, const double *tau, double *c, int ldc) { double w[MAXRHS * 4]; dorm2r_lt(m, n, k, a, lda, tau, c, ldc, w); }
__declspec(dllexport) void npl_dorml2(int m, int n, int k, double *a, int lda, const double *tau, double *c, int ldc) { double w[MAXRHS * 4]; dorml2_lt(m, n, k, a, lda, tau, c, ldc, w); }
