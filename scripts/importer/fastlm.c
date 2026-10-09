/* fastlm.c - the per-texel work of lightmap1995.bake / _light and the per-ray work of roadsight.orient, in C (fastlm.py loads it).
   Nothing here decides anything new: every number is computed by the formula the numpy code computes it with, in numpy's order
   (checked operation by operation, 2026-10-08, numpy 1.24: a row sum of three is (x + y) + z, np.cross is a1 b2 - a2 b1 ..., a mean
   over 16 adds them one after the other, np.cos / np.sin / % are the C runtime's (ucrtbase.dll, looked up here as fastgeo.c does for pow)).
   Compile with -ffp-contract=off and never with -ffast-math.

   ONE thing numpy does not pin down:  (n, 3) @ sun  goes through BLAS (dgemv), which adds the three products in an order that depends
   on the length of the array and on the row (measured: (x + z) + y up to about 2000 rows, mixed above).  DOT3S below is (x + z) + y.
   It is the same number whenever one component of the sun is exactly 0 (Mountain: light_dir 0, -9.4, 3.4), else it can differ from
   numpy's in the last bit - which only matters where it is compared with 0.02 / 0.05.

   The rays: fastlm_rays.c (rays.c with two more walks through the same tree). */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <omp.h>
#include <windows.h>
#undef far
#undef near
#define EXPORT __declspec(dllexport)
typedef long long i64;

extern int rx_ref(void *h, const double *o, const double *d, double tmax, double *tout);
extern int rx_any(void *h, const double *o, const double *d, double tlim);
extern int rx_near(void *h, const double *o, const double *d, double tmax, double *tout, long long *fell);
extern int rx_nearer(void *h, const double *o, const double *d, double tmax, double tlim, long long *fell);

typedef double (*f1_t)(double); typedef double (*f2_t)(double, double);
static f1_t usin = NULL, ucos = NULL; static f2_t ufmod = NULL;
EXPORT int lm_init(void)
{
    HMODULE h = GetModuleHandleA("ucrtbase.dll");
    if (h) { usin = (f1_t)(void *)GetProcAddress(h, "sin"); ucos = (f1_t)(void *)GetProcAddress(h, "cos"); ufmod = (f2_t)(void *)GetProcAddress(h, "fmod"); }
    return usin != NULL && ucos != NULL && ufmod != NULL;
}

#define DOT3(a, b)  (((a)[0] * (b)[0] + (a)[1] * (b)[1]) + (a)[2] * (b)[2])        /* (a * b).sum(1) */
#define DOT3S(a, s) (((a)[0] * (s)[0] + (a)[2] * (s)[2]) + (a)[1] * (s)[1])        /* a @ sun (see the top) */
#define NORM3(a)    sqrt(((a)[0] * (a)[0] + (a)[1] * (a)[1]) + (a)[2] * (a)[2])     /* np.linalg.norm(a, axis=1) */
static inline void cross3(const double *a, const double *b, double *c)             /* np.cross */
{
    c[0] = a[1] * b[2] - a[2] * b[1]; c[1] = a[2] * b[0] - a[0] * b[2]; c[2] = a[0] * b[1] - a[1] * b[0];
}
static inline double max2(double a, double b) { return a > b ? a : b; }

typedef struct {
    void *sc; int ordered;                                               /* ordered: rx_near / rx_any may be used (the tree is shallow enough) */
    const double *TN; const int *TM; const double *alb; int nmat;        /* per scene triangle: unit normal, material ; per material: colour */
    const double *SUN, *SD, *HEMI; int nsd, ks; double smax;             /* sun (unit), nsd directions round it, ks directions over the half space ; max(SUN[1], 0.3) */
} lctx;

typedef struct { double n[3], t[3], b[3], dsun; } face_t;               /* a facing: normal, frame(normal), normal @ sun */
static void make_face(const lctx *c, const double *n, face_t *f)
{
    double ax[3] = { 0.0, 1.0, 0.0 }; if (!(fabs(n[1]) < 0.9)) { ax[0] = 1.0; ax[1] = 0.0; }
    memcpy(f->n, n, sizeof f->n); cross3(n, ax, f->t); double l = max2(NORM3(f->t), 1e-12); f->t[0] /= l; f->t[1] /= l; f->t[2] /= l; cross3(n, f->t, f->b);
    f->dsun = DOT3S(n, c->SUN);
}

/* lightmap1995._light for ONE point: V, A, B[3].  k0 = the texel's number (turns the fan) */
static void light_one(const lctx *c, const double *P, const face_t *f, double k0, double *V, double *A, double *B, i64 *nray, i64 *fell)
{
    const double *n = f->n; double o[3] = { P[0] + n[0] * 0.03, P[1] + n[1] * 0.03, P[2] + n[2] * 0.03 }; i64 nr = 0;
    *V = 0.0;
    if (f->dsun > 0.02) {
        int open = 0;
        for (int j = 0; j < c->nsd; j++) {
            const double *dd = c->SD + 3 * j; double oo[3] = { o[0] + dd[0] * 0.12, o[1] + dd[1] * 0.12, o[2] + dd[2] * 0.12 };
            int hit = c->ordered ? rx_any(c->sc, oo, dd, 1e9) : (rx_ref(c->sc, oo, dd, 1e9, NULL) >= 0);
            open += !hit;
        }
        nr += c->nsd; *V = (double)open / (double)c->nsd;
    }
    double ang = ufmod(k0 * 0.618034, 1.0) * 2 * 3.141592653589793, ca = ucos(ang), sa = usin(ang);
    int sky = 0; double acc[3] = { 0.0, 0.0, 0.0 };
    for (int j = 0; j < c->ks; j++) {
        const double *H = c->HEMI + 3 * j; double hx = H[0] * ca - H[1] * sa, hy = H[0] * sa + H[1] * ca, d[3], oo[3], back[3] = { 0.0, 0.0, 0.0 };
        for (int a = 0; a < 3; a++) { d[a] = (f->t[a] * hx + f->b[a] * hy) + n[a] * H[2]; oo[a] = o[a] + d[a] * 0.12; }
        double dist = 1e9; int hit = c->ordered ? rx_near(c->sc, oo, d, 1e9, &dist, fell) : rx_ref(c->sc, oo, d, 1e9, &dist);
        nr++;
        if (hit < 0) sky++;
        else {
            double hn[3] = { c->TN[3 * (size_t)hit], c->TN[3 * (size_t)hit + 1], c->TN[3 * (size_t)hit + 2] };
            if (!(DOT3(hn, d) < 0)) { hn[0] = -hn[0]; hn[1] = -hn[1]; hn[2] = -hn[2]; }
            double lit = 0.3, hs = DOT3S(hn, c->SUN);
            if (hs > 0.05) {
                double o2[3];
                for (int a = 0; a < 3; a++) { double loc = oo[a] + d[a] * dist; o2[a] = (loc + hn[a] * 0.03) + c->SUN[a] * 0.12; }
                int h2 = c->ordered ? rx_any(c->sc, o2, c->SUN, 1e9) : (rx_ref(c->sc, o2, c->SUN, 1e9, NULL) >= 0);
                nr++;
                if (!h2) lit = 0.3 + 0.7 * hs / c->smax;
            }
            if (!(lit < 1.0)) lit = 1.0;                                 /* np.minimum(lit, 1.0) */
            const double *al = c->alb + 3 * (size_t)c->TM[hit]; back[0] = al[0] * lit; back[1] = al[1] * lit; back[2] = al[2] * lit;
        }
        if (j == 0) { acc[0] = back[0]; acc[1] = back[1]; acc[2] = back[2]; } else { acc[0] += back[0]; acc[1] += back[1]; acc[2] += back[2]; }
    }
    *A = (double)sky / (double)c->ks; B[0] = acc[0] / c->ks; B[1] = acc[1] / c->ks; B[2] = acc[2] / c->ks; *nray += nr;
}

/* lightmap1995.bake, the loop over the polygons:
   P[np * 12] corners, N[np * 3] unit facing, I[np * 4] brightness of the corners, U[np] unsure (lit as the brighter side),
   page / x0 / y0 / nu / nv [np] the polygon's rectangle, k0[np] the number of its first texel (texels are numbered in the order
   the Python loop lights them), pages[(npage + 1) * PAGE * PAGE * 3].  rt: 1 = mode 'rt', 0 = 'shadows'.
   use_ordered: 0 = every ray through cast_one (the reference walk).  -> rays cast ; fell[0] = rays rx_near handed to cast_one */
EXPORT i64 lm_bake(void *sc, int use_ordered, const double *P, const double *N, const double *I, const unsigned char *U,
                   const int *page, const int *x0, const int *y0, const int *nu, const int *nv, const i64 *k0, i64 np,
                   const double *TN, const int *TM, const double *alb, int nmat, const double *SUN, const double *SD, int nsd, const double *HEMI, int ks,
                   int rt, double strength, double shade, unsigned char *pages, int PAGE, i64 *fell_out)
{
    lctx c = { sc, use_ordered, TN, TM, alb, nmat, SUN, SD, HEMI, nsd, ks, max2(SUN[1], 0.3) };
    i64 nray = 0, fell = 0;
    #pragma omp parallel for schedule(dynamic, 8) reduction(+: nray, fell)
    for (i64 i = 0; i < np; i++) {
        const double *Q0 = P + 12 * i, *Q1 = Q0 + 3, *Q2 = Q0 + 6, *Q3 = Q0 + 9, *Ni = N + 3 * i, *Ii = I + 4 * i;
        int w = nu[i], h = nv[i], u = U[i] != 0;
        double e10[3], e30[3], e32[3], e12[3], e21[3], e31[3], n1[3], n2[3];
        for (int a = 0; a < 3; a++) { e10[a] = Q1[a] - Q0[a]; e30[a] = Q3[a] - Q0[a]; e32[a] = Q3[a] - Q2[a]; e12[a] = Q1[a] - Q2[a]; e21[a] = Q2[a] - Q1[a]; e31[a] = Q3[a] - Q1[a]; }
        cross3(e10, e30, n1); cross3(e21, e31, n2); double l1 = NORM3(n1), l2 = NORM3(n2);
        if (!(l2 > 1e-9)) { n2[0] = n1[0]; n2[1] = n1[1]; n2[2] = n1[2]; l2 = l1; }
        double m1 = max2(l1, 1e-12), m2 = max2(l2, 1e-12); face_t F[2][2];                    /* [lower / upper triangle][seen side / the other] */
        for (int k = 0; k < 2; k++) {
            const double *nn = k ? n2 : n1; double m = k ? m2 : m1, tn[3] = { nn[0] / m, nn[1] / m, nn[2] / m };
            if (DOT3(tn, Ni) < 0) { tn[0] = -tn[0]; tn[1] = -tn[1]; tn[2] = -tn[2]; }
            const double *n = NORM3(tn) > 0.5 ? tn : Ni; double neg[3] = { -n[0], -n[1], -n[2] };
            make_face(&c, n, &F[k][0]); if (u) make_face(&c, neg, &F[k][1]);
        }
        unsigned char *pg = pages + (size_t)page[i] * PAGE * PAGE * 3;
        for (int iv = 0; iv < h; iv++) {
            unsigned char *row = pg + ((size_t)(y0[i] + iv) * PAGE + x0[i]) * 3;
            for (int iu = 0; iu < w; iu++) {
                double a = (double)iu / (double)(w - 1), b = (double)iv / (double)(h - 1), pt[3]; int lowr = (a + b) <= 1.0;
                if (lowr) for (int q = 0; q < 3; q++) pt[q] = (Q0[q] + a * e10[q]) + b * e30[q];
                else for (int q = 0; q < 3; q++) pt[q] = (Q2[q] + (1 - a) * e32[q]) + (1 - b) * e12[q];
                double ir = ((((1 - a) * (1 - b)) * Ii[0] + (a * (1 - b)) * Ii[1]) + (a * b) * Ii[2]) + ((1 - a) * b) * Ii[3];
                double kk = (double)(k0[i] + (i64)iv * w + iu), V, A, B[3]; const face_t *f = &F[lowr ? 0 : 1][0];
                light_one(&c, pt, f, kk, &V, &A, B, &nray, &fell);
                if (u) {
                    double V2, A2, B2[3]; light_one(&c, pt, &F[lowr ? 0 : 1][1], kk, &V2, &A2, B2, &nray, &fell);
                    if ((V2 + A2) > (V + A)) { V = V2; A = A2; B[0] = B2[0]; B[1] = B2[1]; B[2] = B2[2]; }
                }
                int away = (f->dsun <= 0.02) && !u; ir = max2(ir, 1e-3);
                double Dd = (away || ir <= shade) ? ir : shade + (ir - shade) * V;
                for (int q = 0; q < 3; q++) {
                    double col = rt ? Dd + strength * (((Dd * (0.45 + 0.55 * A)) + 0.6 * B[q]) - Dd) : Dd, val = col / ir;
                    val = val < 0.0 ? 0.0 : val; val = val > 1.0 ? 1.0 : val; row[3 * iu + q] = (unsigned char)rint(val * 255);
                }
            }
        }
        /* the rest of the rectangle (whole 4 x 4 blocks) repeats the edge: np.pad(mode='edge') */
        int w4 = (w + 3) / 4 * 4, h4 = (h + 3) / 4 * 4;
        for (int iv = 0; iv < h4; iv++) {
            unsigned char *row = pg + ((size_t)(y0[i] + iv) * PAGE + x0[i]) * 3;
            if (iv >= h) { memcpy(row, pg + ((size_t)(y0[i] + h - 1) * PAGE + x0[i]) * 3, (size_t)w4 * 3); continue; }
            for (int iu = w; iu < w4; iu++) { row[3 * iu] = row[3 * (w - 1)]; row[3 * iu + 1] = row[3 * (w - 1) + 1]; row[3 * iu + 2] = row[3 * (w - 1) + 2]; }
        }
    }
    if (fell_out) *fell_out = fell;
    return nray;
}

/* lightmap1995._light for n points (the old function's interface: bake1995-style callers, and the comparison with the numpy code):
   P[n * 3], Nn[n * 3] unit facing, K0[n] -> V[n], A[n], B[n * 3] */
EXPORT i64 lm_light(void *sc, int use_ordered, const double *P, const double *Nn, const double *K0, i64 n,
                    const double *TN, const int *TM, const double *alb, int nmat, const double *SUN, const double *SD, int nsd, const double *HEMI, int ks,
                    double *V, double *A, double *B, i64 *fell_out)
{
    lctx c = { sc, use_ordered, TN, TM, alb, nmat, SUN, SD, HEMI, nsd, ks, max2(SUN[1], 0.3) }; i64 nray = 0, fell = 0;
    #pragma omp parallel for schedule(dynamic, 256) reduction(+: nray, fell)
    for (i64 i = 0; i < n; i++) { face_t f; make_face(&c, Nn + 3 * i, &f); light_one(&c, P + 3 * i, &f, K0[i], V + i, A + i, B + 3 * i, &nray, &fell); }
    if (fell_out) *fell_out = fell;
    return nray;
}

/* roadsight.orient, the loop over the judged polygons:
   cen / S1 / S2 / nrm [nj * 3]: plan centre, the two sample points, the unit normal ; C[nrow * 3] road centre points ;
   E[nrow * per * 3] the viewpoints (viewpoint k of road point r = E[r + nrow * k]).  A polygon is looked at from every road point
   nearer than reach (plan distance).  -> rays cast ; front[nj], back[nj] = samples reached on the winding side / on the other side */
EXPORT i64 lm_roadsight(void *sc, int use_ordered, const double *cen, const double *S1, const double *S2, const double *nrm, i64 nj,
                        const double *C, i64 nrow, const double *E, int per, double reach, int *front, int *back, i64 *fell_out)
{
    i64 nray = 0, fell = 0;
    #pragma omp parallel for schedule(dynamic, 32) reduction(+: nray, fell)
    for (i64 p = 0; p < nj; p++) {
        const double *c = cen + 3 * p, *n = nrm + 3 * p; int fr = 0, bk = 0;
        for (i64 r = 0; r < nrow; r++) {
            double dx = c[0] - C[3 * r], dz = c[2] - C[3 * r + 2];
            if (!(sqrt(dx * dx + dz * dz) < reach)) continue;
            for (int k = 0; k < per; k++) {
                const double *e = E + 3 * (r + nrow * k);
                for (int smp = 0; smp < 2; smp++) {
                    const double *q = (smp ? S2 : S1) + 3 * p; double v[3] = { q[0] - e[0], q[1] - e[1], q[2] - e[2] }, L = NORM3(v), m = max2(L, 1e-9);
                    double dr[3] = { v[0] / m, v[1] / m, v[2] / m }, cs = -DOT3(dr, n);
                    if (!(fabs(cs) > 0.05 && L > 0.5)) continue;
                    nray++;
                    int seen;
                    if (use_ordered) seen = !rx_nearer(sc, e, dr, 1e9, L - 0.08, &fell);
                    else { double tt = 1e9; int hh = rx_ref(sc, e, dr, 1e9, &tt); if (hh < 0) tt = 1e9; seen = tt >= L - 0.08; }
                    if (seen) { if (cs > 0) fr++; else if (cs < 0) bk++; }
                }
            }
        }
        front[p] = fr; back[p] = bk;
    }
    if (fell_out) *fell_out = fell;
    return nray;
}

EXPORT int lm_threads(void) { return omp_get_max_threads(); }
