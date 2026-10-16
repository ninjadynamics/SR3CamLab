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

/* roadsight.orient's set-up for the numpy-free path (2026-10-15, kb 31): n polygons packed by geobuf.pack (X corners, off[n + 1],
   lens[n]), opaque[n], judged[n] (0 / 1; a judged polygon is opaque). The numpy lines it replaces:
     Q = np.zeros((n, 4, 3)); Q[op, k] = X[off[op] + k] (k < 3); Q[q4, 3] = X[off[q4] + 3]; Q[tri, 3] = Q[tri, 2]
     T = np.concatenate([Q[opaque][:, [0, 1, 3]], Q[opaque & ~tri][:, [1, 2, 3]]])
     Pj = Q[idx]; nrm = np.cross(Pj, np.roll(Pj, -1, axis=1)).sum(1); ln = np.linalg.norm(nrm, axis=1); nrm /= np.maximum(ln, 1e-12)[:, None]
     S1 = (Pj[:, 0] + Pj[:, 1] + Pj[:, 3]) / 3.0; S2 = np.where(tri[idx][:, None], S1, (Pj[:, 1] + Pj[:, 2] + Pj[:, 3]) / 3.0); cen = Pj.mean(1)
   numpy's order kept: the sum and the mean over the four corners add them one after the other from 0 (an outer axis, kb 31), the norm
   is (x*x + y*y) + z*z, np.maximum passes a NaN on. -> T[9 * ntri] (the caller sizes it: opaque + opaque four-corner polygons),
   idx[nj] the judged polygons, cen / S1 / S2 / nrm [3 * nj]; returns nj. */
EXPORT i64 lm_rs_prep(i64 n, const double *X, const i64 *off, const i64 *lens, const unsigned char *opaque, const unsigned char *judged,
                      double *T, i64 *idx, double *cen, double *S1, double *S2, double *nrm)
{
    i64 t = 0, nj = 0;
    #define CORNER(i, k, q) do { i64 kk_ = (k) == 3 && lens[i] == 3 ? 2 : (k); memcpy((q), X + 3 * (off[i] + kk_), 3 * sizeof(double)); } while (0)
    for (i64 i = 0; i < n; i++) if (opaque[i]) { CORNER(i, 0, T + 9 * t); CORNER(i, 1, T + 9 * t + 3); CORNER(i, 3, T + 9 * t + 6); t++; }
    for (i64 i = 0; i < n; i++) if (opaque[i] && lens[i] == 4) { CORNER(i, 1, T + 9 * t); CORNER(i, 2, T + 9 * t + 3); CORNER(i, 3, T + 9 * t + 6); t++; }
    for (i64 i = 0; i < n; i++) if (judged[i]) idx[nj++] = i;
    #pragma omp parallel for schedule(static)
    for (i64 j = 0; j < nj; j++) {
        i64 i = idx[j]; double Q[4][3], s[3] = { 0.0, 0.0, 0.0 }, c[3];
        for (int k = 0; k < 4; k++) CORNER(i, k, Q[k]);
        for (int k = 0; k < 4; k++) { cross3(Q[k], Q[(k + 1) % 4], c); s[0] += c[0]; s[1] += c[1]; s[2] += c[2]; }
        double l = NORM3(s), d = isnan(l) ? l : (l > 1e-12 ? l : 1e-12);
        for (int a = 0; a < 3; a++) {
            nrm[3 * j + a] = s[a] / d;
            S1[3 * j + a] = ((Q[0][a] + Q[1][a]) + Q[3][a]) / 3.0;
            S2[3 * j + a] = lens[i] == 3 ? S1[3 * j + a] : ((Q[1][a] + Q[2][a]) + Q[3][a]) / 3.0;
            cen[3 * j + a] = ((((0.0 + Q[0][a]) + Q[1][a]) + Q[2][a]) + Q[3][a]) / 4.0;
        }
    }
    #undef CORNER
    return nj;
}

/* seenside.orient's set-up for the numpy-free path (2026-10-15, kb 31): n polygons packed (X, off, lens: geobuf.pack), use[n] (opaque or
   judged: their corners are filled in), opaque[n], judged[n]. The numpy lines:
     Q[i, :len(P)] = P[:, :3]; Q[i, 3] = Q[i, 2] for three corners ; tri = np.linalg.norm(Q[:, 2] - Q[:, 3], axis=1) < 1e-9
     T = np.concatenate([Q[opaque][:, [0, 1, 2]], Q[opaque & ~tri][:, [0, 2, 3]]])
     Pj = Q[idx]; nrm = np.cross(P1 - P0, P2 - P0) + np.cross(P2 - P0, P3 - P0); nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
     mix = lambda a, b, c, w: w * Pj[:, a] + (1 - w) / 2 * (Pj[:, b] + Pj[:, c]); cen = (P0 + P2) / 2
     pairs: (mix(1, 0, 2, 1/3), tri ? mix(0, 1, 2, 1/3) : mix(3, 0, 2, 1/3)), (mix(1, 0, 2, 0.6), tri ? mix(0, 1, 2, 0.6) : mix(3, 0, 2, 0.6)),
            (mix(0, 1, 2, 0.6), tri ? mix(2, 0, 1, 0.6) : mix(2, 0, 3, 0.6))
     area = 0.5 * (np.linalg.norm(np.cross(P1 - P0, P2 - P0), axis=1) + np.linalg.norm(np.cross(P2 - P0, P3 - P0), axis=1))
   -> T[9 * ntri] (sized by the caller: opaque + opaque non-tri; returns ntri through *nt), idx[nj], Pj[12 * nj], tri_j[nj], nrm / cen [3 nj],
      S[6][3 nj] (the three pairs), area[nj]; returns nj. */
static inline void ss_corners(const double *X, const i64 *off, const i64 *lens, i64 i, double Q[4][3])
{
    for (int k = 0; k < 4; k++) { int kk = k < lens[i] ? k : (int)lens[i] - 1; memcpy(Q[k], X + 3 * (off[i] + kk), 3 * sizeof(double)); }
}
static inline void ss_mix(double Q[4][3], int a, int b, int c, double w, double *out)
{
    double v = (1.0 - w) / 2.0;
    for (int k = 0; k < 3; k++) out[k] = w * Q[a][k] + v * (Q[b][k] + Q[c][k]);
}
EXPORT i64 lm_ss_prep(i64 n, const double *X, const i64 *off, const i64 *lens, const unsigned char *use, const unsigned char *opaque, const unsigned char *judged,
                      double *T, i64 *nt, i64 *idx, double *Pj, unsigned char *trij, double *nrm, double *cen, double *S, double *area)
{
    i64 t = 0, nj = 0;
    unsigned char *tri = (unsigned char *)malloc((size_t)(n ? n : 1));
    for (i64 i = 0; i < n; i++) {
        tri[i] = 1;                                                     /* (Q stays zero for the others: |0 - 0| < 1e-9) */
        if (!use[i]) continue;
        double Q[4][3]; ss_corners(X, off, lens, i, Q); double d[3] = { Q[2][0] - Q[3][0], Q[2][1] - Q[3][1], Q[2][2] - Q[3][2] };
        tri[i] = NORM3(d) < 1e-9;
    }
    for (i64 i = 0; i < n; i++) if (opaque[i]) { double Q[4][3]; ss_corners(X, off, lens, i, Q); memcpy(T + 9 * t, Q[0], 24); memcpy(T + 9 * t + 3, Q[1], 24); memcpy(T + 9 * t + 6, Q[2], 24); t++; }
    for (i64 i = 0; i < n; i++) if (opaque[i] && !tri[i]) { double Q[4][3]; ss_corners(X, off, lens, i, Q); memcpy(T + 9 * t, Q[0], 24); memcpy(T + 9 * t + 3, Q[2], 24); memcpy(T + 9 * t + 6, Q[3], 24); t++; }
    for (i64 i = 0; i < n; i++) if (judged[i]) idx[nj++] = i;
    *nt = t;
    #pragma omp parallel for schedule(static)
    for (i64 j = 0; j < nj; j++) {
        i64 i = idx[j]; double Q[4][3], e1[3], e2[3], e3[3], c1[3], c2[3], s[3]; ss_corners(X, off, lens, i, Q); int tj = tri[i]; trij[j] = (unsigned char)tj;
        memcpy(Pj + 12 * j, Q, 12 * sizeof(double));
        for (int k = 0; k < 3; k++) { e1[k] = Q[1][k] - Q[0][k]; e2[k] = Q[2][k] - Q[0][k]; e3[k] = Q[3][k] - Q[0][k]; }
        cross3(e1, e2, c1); cross3(e2, e3, c2);
        for (int k = 0; k < 3; k++) s[k] = c1[k] + c2[k];
        double l = NORM3(s), dd = isnan(l) ? l : (l > 1e-12 ? l : 1e-12);
        for (int k = 0; k < 3; k++) { nrm[3 * j + k] = s[k] / dd; cen[3 * j + k] = (Q[0][k] + Q[2][k]) / 2.0; }
        double *S0 = S + 3 * j, *S1 = S + 3 * (nj + j), *S2 = S + 3 * (2 * nj + j), *S3 = S + 3 * (3 * nj + j), *S4 = S + 3 * (4 * nj + j), *S5 = S + 3 * (5 * nj + j);
        ss_mix(Q, 1, 0, 2, 1.0 / 3.0, S0); if (tj) ss_mix(Q, 0, 1, 2, 1.0 / 3.0, S1); else ss_mix(Q, 3, 0, 2, 1.0 / 3.0, S1);
        ss_mix(Q, 1, 0, 2, 0.6, S2);        if (tj) ss_mix(Q, 0, 1, 2, 0.6, S3);       else ss_mix(Q, 3, 0, 2, 0.6, S3);
        ss_mix(Q, 0, 1, 2, 0.6, S4);        if (tj) ss_mix(Q, 2, 0, 1, 0.6, S5);       else ss_mix(Q, 2, 0, 3, 0.6, S5);
        area[j] = 0.5 * (NORM3(c1) + NORM3(c2));
    }
    free(tri);
    return nj;
}

/* seenside._open_sides: the share of each polygon's rays that reach the sky, on its winding side (fo) and its other side (bo).
     ax = np.where((np.abs(nrm[:, 1]) < 0.9)[:, None], [0, 1, 0], [1, 0, 0]); t = np.cross(nrm, ax) / np.maximum(norm, 1e-12); b = np.cross(nrm, t)
     for sgn in (1, -1): n_ = nrm * sgn; D = H0 * t + H1 * b + H2 * n_ ; up = D[:, :, 1] > 0.02
         for P in pts: o = P + n_ * lift; hit = rx_any(o, D, 4000) ; esc += ((hit < 0) & up).sum(0) ; m += 24      -> esc / m
   pts: np sets of 3 nj (the six sample points). A ray whose direction is not up is not counted, so it is not cast (the count is the same). */
EXPORT void lm_open_sides(void *sc, i64 nj, const double *pts, int np_, const double *nrm, double lift, const double *H, int nh, double *fo, double *bo)
{
    #pragma omp parallel for schedule(dynamic, 64)
    for (i64 j = 0; j < nj; j++) {
        const double *n = nrm + 3 * j; double ax[3] = { 0.0, 1.0, 0.0 }, t[3], b[3];
        if (!(fabs(n[1]) < 0.9)) { ax[0] = 1.0; ax[1] = 0.0; }
        cross3(n, ax, t); double l = NORM3(t), dd = isnan(l) ? l : (l > 1e-12 ? l : 1e-12); t[0] /= dd; t[1] /= dd; t[2] /= dd; cross3(n, t, b);
        for (int side = 0; side < 2; side++) {
            double sg = side ? -1.0 : 1.0, nn[3] = { n[0] * sg, n[1] * sg, n[2] * sg }; i64 esc = 0;
            for (int h = 0; h < nh; h++) {
                const double *hh = H + 3 * h; double d[3];
                for (int k = 0; k < 3; k++) d[k] = (hh[0] * t[k] + hh[1] * b[k]) + hh[2] * nn[k];
                if (!(d[1] > 0.02)) continue;
                for (int p = 0; p < np_; p++) {
                    const double *P = pts + 3 * ((i64)p * nj + j); double o[3] = { P[0] + nn[0] * lift, P[1] + nn[1] * lift, P[2] + nn[2] * lift };
                    esc += !rx_any(sc, o, d, 4000.0);
                }
            }
            (side ? bo : fo)[j] = (double)esc / (double)(nh * np_);
        }
    }
}

/* lightmap1995.key: one key per polygon, its four corners to the millimetre (2026-10-15, kb 31):
     np.round(np.asarray(P4, np.float64).reshape(-1, 12) * 1000.0).astype(np.int32)          (np.round = rint, half to even) */
EXPORT void lm_key12(i64 n, const double *P, int *K)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < 12 * n; i++) K[i] = (int)rint(P[i] * 1000.0);
}

/* rows picked out of a C-ordered array: dst[k] = src[sel[k]], each row `rb` bytes (numpy's A[sel]) */
EXPORT void lm_gather(i64 k, const i64 *sel, i64 rb, const unsigned char *src, unsigned char *dst)
{
    #pragma omp parallel for schedule(static)
    for (i64 j = 0; j < k; j++) memcpy(dst + j * rb, src + sel[j] * rb, (size_t)rb);
}

/* numpy's pairwise sum of n doubles (np.add.reduce of a contiguous array): below 8 one after the other, up to 128 eight running sums,
   above that the two halves cut at a multiple of 8 */
static double np_pairwise(const double *v, i64 n)
{
    if (n < 8) { double s = 0.0; for (i64 i = 0; i < n; i++) s += v[i]; return s; }
    if (n <= 128) {
        double r[8]; i64 i, e = n - n % 8;
        for (int j = 0; j < 8; j++) r[j] = v[j];
        for (i = 8; i < e; i += 8) for (int j = 0; j < 8; j++) r[j] += v[i + j];
        double s = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++) s += v[i];
        return s;
    }
    i64 h = n / 2; h -= h % 8; return np_pairwise(v, h) + np_pairwise(v + h, n - h);
}

/* bake1995.save_scene's albedo of a tile (2026-10-15, kb 31):
     rgb = np.asarray(rgb, float), an (h, w) grey picture taken three times; x = (rgb[keep] / 255.0) ** 2.2
     a_ = float(x.mean()); c_ = tuple(x.mean(0))
   x.mean(): numpy's pairwise sum over the k x 3 values in their order (pixel by pixel, the channels within), / 3k ; x.mean(0): per channel
   the k values one after the other from 0 (an outer axis, kb 31), / k. pow is ucrtbase's (np.power calls it; lm_init finds it).
   rgb: npx pixels of ch (1 or 3) values, kind 0 = u8, 1 = f8, 2 = f4; keep[npx] or NULL (every pixel). -> out = a_, c_[3]; returns k */
static f2_t upow = NULL;
EXPORT i64 lm_albedo(i64 npx, const void *rgb, int kind, int ch, const unsigned char *keep, double *out)
{
    if (!upow) { HMODULE h = GetModuleHandleA("ucrtbase.dll"); if (h) upow = (f2_t)(void *)GetProcAddress(h, "pow"); if (!upow) return -1; }
    double *x = (double *)malloc((size_t)(npx ? npx : 1) * 3 * sizeof(double)), c[3] = { 0.0, 0.0, 0.0 }; i64 k = 0;
    for (i64 p = 0; p < npx; p++) {
        if (keep && !keep[p]) continue;
        for (int a = 0; a < 3; a++) {
            i64 q = p * ch + (ch == 3 ? a : 0); double v = kind == 0 ? (double)((const unsigned char *)rgb)[q] : kind == 1 ? ((const double *)rgb)[q] : (double)((const float *)rgb)[q];
            x[3 * k + a] = upow(v / 255.0, 2.2); c[a] += x[3 * k + a];
        }
        k++;
    }
    out[0] = (0.0 + np_pairwise(x, 3 * k)) / (double)(3 * k);
    for (int a = 0; a < 3; a++) out[1 + a] = c[a] / (double)k;
    free(x); return k;
}

/* lightmap1995.lookup's arithmetic (2026-10-15, kb 31): idx[n] the table row of each polygon (-1: on no page) -> opage[n], ouv[4n][2]:
     x0 = tab['x0'][j].astype(float) ... ; cu = np.stack([x0 + 0.5, x0 + nu - 0.5, x0 + nu - 0.5, x0 + 0.5], 1) / PAGE ; cv likewise with y0, nv
     with ab: cu = (x0[:, None] + 0.5 + ab[:, :, 0] * (nu[:, None] - 1.0)) / PAGE ; cv = (y0[:, None] + 0.5 + ab[:, :, 1] * (nv[:, None] - 1.0)) / PAGE
     uv = np.where(ok, uv, 0.5); page = np.where(ok, tab['page'][j], 0); np.clip(np.round(uv * 32768), 0, 32767).astype(np.uint16) */
EXPORT void lm_lookup(i64 n, const i64 *idx, const int *pg, const int *x0, const int *y0, const int *nu, const int *nv, const double *ab, int PAGE,
                      int *opage, unsigned short *ouv)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        i64 j = idx[i] < 0 ? 0 : idx[i]; int ok = idx[i] >= 0; double X = (double)x0[j], Y = (double)y0[j], U = (double)nu[j], V = (double)nv[j], cu[4], cv[4];
        if (ab) for (int c = 0; c < 4; c++) { cu[c] = ((X + 0.5) + ab[8 * j + 2 * c] * (U - 1.0)) / PAGE; cv[c] = ((Y + 0.5) + ab[8 * j + 2 * c + 1] * (V - 1.0)) / PAGE; }
        else {
            cu[0] = (X + 0.5) / PAGE; cu[1] = ((X + U) - 0.5) / PAGE; cu[2] = cu[1]; cu[3] = cu[0];
            cv[0] = (Y + 0.5) / PAGE; cv[1] = cv[0]; cv[2] = ((Y + V) - 0.5) / PAGE; cv[3] = cv[2];
        }
        opage[i] = ok ? pg[j] : 0;
        for (int c = 0; c < 4; c++)
            for (int a = 0; a < 2; a++) {
                double v = rint((ok ? (a ? cv[c] : cu[c]) : 0.5) * 32768.0); v = v < 0.0 ? 0.0 : (v > 32767.0 ? 32767.0 : v);
                ouv[8 * i + 2 * c + a] = (unsigned short)v;
            }
    }
}

/* ------------------------------------------------------------------ sky1995 (2026-10-15, kb 31: its own numpy operations in C)
   sky_dirs = directions(V, tris, W, H): for each triangle in order (a later one overwrites), the texels of its uv box inside it get the
   point of the dome there; then D[M] /= np.linalg.norm(D, axis=2)[M]. P[3 nv] = V['p'].astype(float), UV[2 nv] = V['uv'] / 32768.0 * [W, H].
     x0, y0 = np.floor(u.min(0) - 1).astype(int); x1, y1 = np.ceil(u.max(0) + 1).astype(int) (clamped) ; X, Y = the texel centres (+ 0.5)
     den = (u1y - u2y) * (u0x - u2x) + (u2x - u1x) * (u0y - u2y); w0 = ((u1y - u2y) * (X - u2x) + (u2x - u1x) * (Y - u2y)) / den
     w1 = ((u2y - u0y) * (X - u2x) + (u0x - u2x) * (Y - u2y)) / den; w2 = 1 - w0 - w1; ins = all >= -0.02; p = w0 * Pa + w1 * Pb + w2 * Pc */
EXPORT void sky_dirs(const double *P, const double *UV, i64 nt, const i64 *tris, int W, int H, double *D, unsigned char *M)
{
    memset(D, 0, sizeof(double) * 3 * (size_t)W * H); memset(M, 0, (size_t)W * H);
    for (i64 t = 0; t < nt; t++) {
        i64 a = tris[3 * t], b = tris[3 * t + 1], c = tris[3 * t + 2]; const double *u0 = UV + 2 * a, *u1 = UV + 2 * b, *u2 = UV + 2 * c;
        double mnx = fmin(fmin(u0[0], u1[0]), u2[0]), mny = fmin(fmin(u0[1], u1[1]), u2[1]), mxx = fmax(fmax(u0[0], u1[0]), u2[0]), mxy = fmax(fmax(u0[1], u1[1]), u2[1]);
        i64 x0 = (i64)floor(mnx - 1), y0 = (i64)floor(mny - 1), x1 = (i64)ceil(mxx + 1), y1 = (i64)ceil(mxy + 1);
        if (x0 < 0) x0 = 0; if (y0 < 0) y0 = 0; if (x1 > W - 1) x1 = W - 1; if (y1 > H - 1) y1 = H - 1;
        if (x1 < x0 || y1 < y0) continue;
        double den = (u1[1] - u2[1]) * (u0[0] - u2[0]) + (u2[0] - u1[0]) * (u0[1] - u2[1]);
        if (fabs(den) < 1e-9) continue;
        for (i64 y = y0; y <= y1; y++)
            for (i64 x = x0; x <= x1; x++) {
                double X = (double)x + 0.5, Y = (double)y + 0.5;
                double w0 = ((u1[1] - u2[1]) * (X - u2[0]) + (u2[0] - u1[0]) * (Y - u2[1])) / den, w1 = ((u2[1] - u0[1]) * (X - u2[0]) + (u0[0] - u2[0]) * (Y - u2[1])) / den, w2 = (1 - w0) - w1;
                if (!(w0 >= -0.02 && w1 >= -0.02 && w2 >= -0.02)) continue;
                double *d = D + 3 * (y * W + x);
                for (int k = 0; k < 3; k++) d[k] = (w0 * P[3 * a + k] + w1 * P[3 * b + k]) + w2 * P[3 * c + k];
                M[y * W + x] = 1;
            }
    }
    for (i64 i = 0; i < (i64)W * H; i++) if (M[i]) { double *d = D + 3 * i, n = NORM3(d); d[0] /= n; d[1] /= n; d[2] /= n; }
}

/* sky_tile: the 1995 sky picture laid on the dome (sky_mode 'tile'), for n directions dirs[3 n] (OBJ axes); im[th * tw * 3] the picture
   (float), flat[3] the median of its top row. The numpy lines (asin / atan2 / tan are ucrtbase's, as numpy calls them; % as numpy's):
     el = np.arcsin(np.clip(dirs[:, 1], -1, 1)); az = np.arctan2(dirs[:, 2], dirs[:, 0])
     fx = (((np.pi / 2 - az) / (2 * np.pi) * rep) % 1.0) * tw; fy = (1.0 - np.clip(np.tan(np.clip(el, 0.0, 1.5)) / np.tan(top), 0.0, 1.0)) * (th - 1)
     x0 = np.floor(fx).astype(int) % tw; x1 = (x0 + 1) % tw; y0 = np.clip(np.floor(fy).astype(int), 0, th - 1); y1 = np.clip(y0 + 1, 0, th - 1)
     col = (im_[y0, x0] * (1 - ax) + im_[y0, x1] * ax) * (1 - ay) + (im_[y1, x0] * (1 - ax) + im_[y1, x1] * ax) * ay
     k_ = np.clip((el - 0.97 * top) / (0.03 * top), 0.0, 1.0); col = col * (1 - k_) + flat_ * k_ */
static f1_t uasin = NULL, utan = NULL; static f2_t uatan2 = NULL;
static inline double clipd(double x, double lo, double hi) { return x < lo ? lo : (x > hi ? hi : x); }
EXPORT int sky_tile(i64 n, const double *dirs, int tw, int th, const double *im, double rep, double top, const double *flat, double *col)
{
    if (!uasin) { HMODULE h = GetModuleHandleA("ucrtbase.dll"); if (h) { uasin = (f1_t)(void *)GetProcAddress(h, "asin"); utan = (f1_t)(void *)GetProcAddress(h, "tan"); uatan2 = (f2_t)(void *)GetProcAddress(h, "atan2"); } }
    if (!uasin || !utan || !uatan2) return 0;
    const double PI = 3.141592653589793, ttop = utan(top), c97 = 0.97 * top, c03 = 0.03 * top;
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        const double *d = dirs + 3 * i; double el = uasin(clipd(d[1], -1, 1)), az = uatan2(d[2], d[0]);
        double r = ((PI / 2 - az) / (2 * PI)) * rep, m = fmod(r, 1.0); if (m != 0.0 && m < 0.0) m += 1.0; if (m == 0.0) m = 0.0;
        double fx = m * tw, fy = (1.0 - clipd(utan(clipd(el, 0.0, 1.5)) / ttop, 0.0, 1.0)) * (th - 1);
        i64 fxi = (i64)floor(fx), x0 = ((fxi % tw) + tw) % tw, x1 = (x0 + 1) % tw, y0 = (i64)floor(fy); y0 = y0 < 0 ? 0 : (y0 > th - 1 ? th - 1 : y0);
        i64 y1 = y0 + 1 > th - 1 ? th - 1 : y0 + 1; double ax = fx - floor(fx), ay = fy - floor(fy), k = clipd((el - c97) / c03, 0.0, 1.0);
        for (int c = 0; c < 3; c++) {
            double v = (im[(y0 * tw + x0) * 3 + c] * (1 - ax) + im[(y0 * tw + x1) * 3 + c] * ax) * (1 - ay) + (im[(y1 * tw + x0) * 3 + c] * (1 - ax) + im[(y1 * tw + x1) * 3 + c] * ax) * ay;
            col[3 * i + c] = v * (1 - k) + flat[c] * k;
        }
    }
    return 1;
}

/* sky_fill = fill(img, mask): a texel without a value takes the nearest valid one along its row (the earlier one on a tie), then along its
   column, as fill()'s maximum / minimum.accumulate do; img[H * W * 3], mask[H * W] (both changed in place) */
EXPORT void sky_fill(int H, int W, double *img, unsigned char *mask)
{
    for (int pass = 0; pass < 2; pass++) {                           /* pass 0: along each row (numpy's axis 1), pass 1: along each column */
        int lines = pass ? W : H, n = pass ? H : W; i64 st = pass ? (i64)W : 1, ls = pass ? 1 : (i64)W;
        #pragma omp parallel for schedule(static)
        for (int l = 0; l < lines; l++) {
            int *fw = (int *)malloc(sizeof(int) * n), *bw = (int *)malloc(sizeof(int) * n); unsigned char *got = (unsigned char *)malloc(n); int last = -1;
            for (int i = 0; i < n; i++) { if (mask[l * ls + i * st]) last = i; fw[i] = last; }
            last = 1000000000; for (int i = n - 1; i >= 0; i--) { if (mask[l * ls + i * st]) last = i; bw[i] = last; }
            double *tmp = (double *)malloc(sizeof(double) * 3 * n);
            for (int i = 0; i < n; i++) {
                int uf = fw[i] >= 0 && (bw[i] >= 1000000000 || i - fw[i] <= bw[i] - i), src = uf ? fw[i] : (bw[i] < 1000000000 ? bw[i] : 0);
                got[i] = fw[i] >= 0 || bw[i] < 1000000000; memcpy(tmp + 3 * i, img + 3 * (l * ls + (i64)src * st), 3 * sizeof(double));
            }
            for (int i = 0; i < n; i++) { i64 q = l * ls + i * st; if (!mask[q] && got[i]) memcpy(img + 3 * q, tmp + 3 * i, 3 * sizeof(double)); }
            for (int i = 0; i < n; i++) if (got[i]) mask[l * ls + i * st] = 1;
            free(fw); free(bw); free(got); free(tmp);
        }
    }
}

/* ------------------------------------------------------------------ facadebake.compose (2026-10-15, kb 31)
   fb_paint: one source triangle painted into img[H][W][3] (row 0 = v 0 while painting), the texels i0..i1-1 x j0..j1-1 (np.searchsorted
   bounds, found by the caller). T: the tile, th x tw texels of tc channels, kind 0 = u8, 1 = f8 (numpy's cast to uint8 truncates). The
   numpy lines: X, Y = np.meshgrid(px[i0:i1], py[j0:j1]); den = (P1y - P2y) * (P0x - P2x) + (P2x - P1x) * (P0y - P2y)
     l0 = ((P1y - P2y) * (X - P2x) + (P2x - P1x) * (Y - P2y)) / den; l1 = ((P2y - P0y) * (X - P2x) + (P0x - P2x) * (Y - P2y)) / den; l2 = 1 - l0 - l1
     m = all >= -1e-4; uu = l0 * U0x + l1 * U1x + l2 * U2x; vv likewise
     tx = np.floor(uu * tw + 1e-6).astype(int) % tw; ty = (th - 1) - np.floor(vv * th + 1e-6).astype(int) % th; img[m] = T[ty, tx][:, :3]
   (% as numpy's: the result has the sign of the divisor). Returns the texels painted. */
static inline i64 pymod(i64 a, i64 b) { i64 r = a % b; return r < 0 ? r + b : r; }
EXPORT i64 fb_paint(int W, int H, unsigned char *img, unsigned char *got, const double *px, const double *py, int i0, int i1, int j0, int j1,
                    const double *P, const double *U, const void *T, int th, int tw, int tc, int kind)
{
    double den = (P[3] - P[5]) * (P[0] - P[4]) + (P[4] - P[2]) * (P[1] - P[5]); i64 cnt = 0;
    if (fabs(den) < 1e-12) return 0;
    for (int j = j0; j < j1; j++)
        for (int i = i0; i < i1; i++) {
            double X = px[i], Y = py[j];
            double l0 = ((P[3] - P[5]) * (X - P[4]) + (P[4] - P[2]) * (Y - P[5])) / den, l1 = ((P[5] - P[1]) * (X - P[4]) + (P[0] - P[4]) * (Y - P[5])) / den, l2 = (1 - l0) - l1;
            if (!(l0 >= -1e-4 && l1 >= -1e-4 && l2 >= -1e-4)) continue;
            double uu = (l0 * U[0] + l1 * U[2]) + l2 * U[4], vv = (l0 * U[1] + l1 * U[3]) + l2 * U[5];
            i64 tx = pymod((i64)floor(uu * tw + 1e-6), tw), ty = (th - 1) - pymod((i64)floor(vv * th + 1e-6), th);
            unsigned char *o = img + 3 * ((i64)j * W + i);
            for (int c = 0; c < 3; c++) { i64 q = (ty * tw + tx) * tc + c; o[c] = kind == 0 ? ((const unsigned char *)T)[q] : (unsigned char)(i64)((const double *)T)[q]; }
            got[(i64)j * W + i] = 1; cnt++;
        }
    return cnt;
}

/* fb_fill: one round of compose's fill: every texel not painted takes the nearest painted one in its column (dv) or its row (dh),
   the column on a tie, an earlier one on a tie within the line (_nearest: (idx - up) <= (dn - idx)); then it counts as painted.
     usev = (dv <= dh) & (dv < 10 ** 5); useh = ~usev & (dh < 10 ** 5); img[a] = img[pv, col]; img[b] = img[row, ph]; got |= a | b
   Returns 1 when something was filled. */
static void fb_nearest(const unsigned char *got, int n, i64 stride, int *pick, int *dist)
{
    int up = -1000000;
    for (int r = 0; r < n; r++) { if (got[r * stride]) up = r; pick[r] = up; }
    int dn = 1000000;
    for (int r = n - 1; r >= 0; r--) {
        if (got[r * stride]) dn = r;
        int u = pick[r]; pick[r] = (r - u) <= (dn - r) ? u : dn; dist[r] = abs(pick[r] - r);
    }
}
EXPORT int fb_fill(int W, int H, unsigned char *img, unsigned char *got)
{
    int *pv = (int *)malloc(sizeof(int) * (size_t)W * H), *dv = (int *)malloc(sizeof(int) * (size_t)W * H), *ph = (int *)malloc(sizeof(int) * (size_t)W * H), *dh = (int *)malloc(sizeof(int) * (size_t)W * H);
    int *t1 = (int *)malloc(sizeof(int) * (size_t)(W > H ? W : H)), *t2 = (int *)malloc(sizeof(int) * (size_t)(W > H ? W : H));
    for (int c = 0; c < W; c++) { fb_nearest(got + c, H, W, t1, t2); for (int r = 0; r < H; r++) { pv[(i64)r * W + c] = t1[r]; dv[(i64)r * W + c] = t2[r]; } }
    for (int r = 0; r < H; r++) { fb_nearest(got + (i64)r * W, W, 1, t1, t2); for (int c = 0; c < W; c++) { ph[(i64)r * W + c] = t1[c]; dh[(i64)r * W + c] = t2[c]; } }
    unsigned char *src = (unsigned char *)malloc((size_t)W * H * 3); memcpy(src, img, (size_t)W * H * 3); int any = 0;
    for (i64 k = 0; k < (i64)W * H; k++) {
        if (got[k]) continue;
        int r = (int)(k / W), c = (int)(k % W), usev = dv[k] <= dh[k] && dv[k] < 100000, useh = !usev && dh[k] < 100000;
        if (usev) { int rr = pv[k] < 0 ? 0 : (pv[k] > H - 1 ? H - 1 : pv[k]); memcpy(img + 3 * k, src + 3 * ((i64)rr * W + c), 3); }
        else if (useh) { int cc = ph[k] < 0 ? 0 : (ph[k] > W - 1 ? W - 1 : ph[k]); memcpy(img + 3 * k, src + 3 * ((i64)r * W + cc), 3); }
    }
    for (i64 k = 0; k < (i64)W * H; k++) if (!got[k]) { int usev = dv[k] <= dh[k] && dv[k] < 100000, useh = !usev && dh[k] < 100000; if (usev || useh) { got[k] = 1; any = 1; } }
    free(pv); free(dv); free(ph); free(dh); free(t1); free(t2); free(src);
    return any;
}

/* crowd.classic_spots' nearest centre-line point: int(np.argmin(np.hypot(X - x, Z - z))) - hypot is ucrtbase's (np.hypot calls it), the
   first of equals wins, a NaN distance wins at once (as argmin) */
static f2_t uhypot = NULL;
EXPORT i64 lm_nearest_xz(i64 n, const double *X, const double *Z, double x, double z)
{
    if (!uhypot) { HMODULE h = GetModuleHandleA("ucrtbase.dll"); if (h) uhypot = (f2_t)(void *)GetProcAddress(h, "hypot"); if (!uhypot) return -1; }
    i64 best = 0; double bd = INFINITY;
    for (i64 i = 0; i < n; i++) { double d = uhypot(X[i] - x, Z[i] - z); if (isnan(d)) return i; if (d < bd) { bd = d; best = i; } }
    return best;
}

/* bsp_build.build_corridor's in_corridor: is (x, z) in one of the corridor's triangles T (ntri x 3 corners x (x, z))? The numpy it
   replaces: TB = np.roll(T, -1, axis=1); cr = (TB[:, :, 0] - T[:, :, 0]) * (z - T[:, :, 1]) - (TB[:, :, 1] - T[:, :, 1]) * (x - T[:, :, 0]);
   ((cr >= -1e-9).all(1) | (cr <= 1e-9).all(1)).any() - the same products, every triangle (no early filter: a triangle of three equal
   corners counts everywhere, as in numpy) */
EXPORT int bc_inside(const double *T, i64 ntri, double x, double z)
{
    for (i64 t = 0; t < ntri; t++) {
        const double *a = T + 6 * t; double cr[3];
        for (int k = 0; k < 3; k++) {
            const double *p = a + 2 * k, *q = a + 2 * ((k + 1) % 3);
            cr[k] = (q[0] - p[0]) * (z - p[1]) - (q[1] - p[1]) * (x - p[0]);
        }
        if ((cr[0] >= -1e-9 && cr[1] >= -1e-9 && cr[2] >= -1e-9) || (cr[0] <= 1e-9 && cr[1] <= 1e-9 && cr[2] <= 1e-9)) return 1;
    }
    return 0;
}
/* build_corridor's limits(cell): the corridor quads whose box meets the cell's box, Q (nq x 6: x0 x1 z0 z1 lo hi; numpy:
   m = (qx1 >= min(xs)) & (qx0 <= max(xs)) & (qz1 >= min(zs)) & (qz0 <= max(zs))) -> out (qlo[m].min(), qhi[m].max()); returns m.any() */
EXPORT int bc_limits(const double *Q, i64 nq, double x0, double x1, double z0, double z1, double *out)
{
    int any = 0; double lo = 0.0, hi = 0.0;
    for (i64 i = 0; i < nq; i++) {
        const double *q = Q + 6 * i;
        if (q[1] >= x0 && q[0] <= x1 && q[3] >= z0 && q[2] <= z1) {
            if (!any || q[4] < lo) lo = q[4];
            if (!any || q[5] > hi) hi = q[5];
            any = 1;
        }
    }
    out[0] = lo; out[1] = hi; return any;
}

/* overlay_bake._recipe's painting: the composed tile (w x h) of tile `lo` (rl W x H x 3, hl its holes or NULL) with tile `up` (ru, hu;
   w2 x h2) painted over, T the 3 x 2 map (upper uv = [u v 1] T). The numpy it replaces, texel for texel:
     uu = u0 + (np.arange(w) + 0.5) / w * (u1 - u0); vv = v1 - (np.arange(h) + 0.5) / h * (v1 - v0); U, Vv = np.meshgrid(uu, vv)
     cl = np.floor(U * W).astype(int) % W; rw = np.floor((1.0 - Vv) * H).astype(int) % H; rgb = rl[rw, cl]; hole = hl[rw, cl] (else 0)
     uv2 = np.stack([U, Vv, 1], -1) @ T (0 + ((U T0 + Vv T1) + 1 T2), the matmul's order); c2 = np.floor(uv2[..., 0] * w2) % w2;
     r2 = np.floor((1.0 - uv2[..., 1]) * h2) % h2; op = ~hu[r2, c2] (else all); rgb[op] = ru[r2, c2][op]; hole &= ~op
   -> hole.any() */
EXPORT int ob_recipe(const unsigned char *rl, const unsigned char *hl, int W, int H, const unsigned char *ru, const unsigned char *hu, int w2, int h2,
                     const double *T, double u0, double v0, double u1, double v1, int w, int h, unsigned char *rgb, unsigned char *hole)
{
    int any = 0;
    for (int j = 0; j < h; j++) {
        double V = v1 - (j + 0.5) / h * (v1 - v0); long long rw = pymod((long long)floor((1.0 - V) * H), H);
        for (int i = 0; i < w; i++) {
            double Uu = u0 + (i + 0.5) / w * (u1 - u0); long long cl = pymod((long long)floor(Uu * W), W);
            const unsigned char *s = rl + 3 * (rw * W + cl); unsigned char *d = rgb + 3 * ((long long)j * w + i); d[0] = s[0]; d[1] = s[1]; d[2] = s[2];
            unsigned char ho = hl ? (hl[rw * W + cl] != 0) : 0;
            double a = 0.0 + ((Uu * T[0] + V * T[2]) + 1.0 * T[4]), b = 0.0 + ((Uu * T[1] + V * T[3]) + 1.0 * T[5]);
            long long c2 = pymod((long long)floor(a * w2), w2), r2 = pymod((long long)floor((1.0 - b) * h2), h2);
            if (!(hu && hu[r2 * w2 + c2])) { const unsigned char *t = ru + 3 * (r2 * w2 + c2); d[0] = t[0]; d[1] = t[1]; d[2] = t[2]; ho = 0; }
            hole[(long long)j * w + i] = ho; any |= ho;
        }
    }
    return any;
}

/* coursepatch.remove / apply: where the corners of a patch are among the build's corners. X: n corners (x, y, z), order: their x order
   (np.argsort(kind='stable')), xs: their x in that order. For each of nq points b: the corners whose x lies in [b0 - wlo, b0 + whi)
   (np.searchsorted(xs, ., side='left')) and whose np.linalg.norm(C - b, axis=1) = sqrt((dx dx + dy dy) + dz dz) < tol, in x order.
   cnt[q]; with out NULL the counts only, else written at off[q] */
static i64 lower_x(const double *xs, i64 n, double v) { i64 lo = 0, hi = n; while (lo < hi) { i64 m = (lo + hi) / 2; if (xs[m] < v) lo = m + 1; else hi = m; } return lo; }
EXPORT void cp_near(i64 nq, const double *Qp, const double *X, const i64 *order, const double *xs, i64 n, double wlo, double whi, double tol, i64 *cnt, const i64 *off, i64 *out)
{
    #pragma omp parallel for schedule(dynamic, 256) if(nq > 2000)
    for (i64 q = 0; q < nq; q++) {
        const double *b = Qp + 3 * q; i64 a = lower_x(xs, n, b[0] - wlo), e = lower_x(xs, n, b[0] + whi), m = 0;
        for (i64 s = a; s < e; s++) {
            i64 i = order[s]; double dx = X[3 * i] - b[0], dy = X[3 * i + 1] - b[1], dz = X[3 * i + 2] - b[2];
            if (sqrt((dx * dx + dy * dy) + dz * dz) < tol) { if (out) out[off[q] + m] = i; m++; }
        }
        cnt[q] = m;
    }
}
/* the corners of the triangles to remove in a polygon's box: Bs (by x) rows lo .. hi (the x window), kept when (c >= mn - tol) & (c <= mx + tol)
   in all three; the first cap of them into out, in x order -> how many in all */
EXPORT i64 cp_cand(const double *Bs, i64 lo, i64 hi, const double *mn, const double *mx, double tol, double *out, i64 cap)
{
    i64 m = 0;
    for (i64 i = lo; i < hi; i++) {
        const double *c = Bs + 3 * i; int ok = 1;
        for (int k = 0; k < 3; k++) if (!(c[k] >= mn[k] - tol && c[k] <= mx[k] + tol)) ok = 0;
        if (ok) { if (m < cap) memcpy(out + 3 * m, c, 24); m++; }
    }
    return m;
}
/* any(np.linalg.norm(Q - c, axis=1).min() < tol and np.linalg.norm(P - c, axis=1).min() >= tol for c in cand) (a NaN distance makes the min NaN) */
static double mindist(const double *A, i64 na, const double *c, int *nan_)
{
    double m = INFINITY; *nan_ = 0;
    for (i64 j = 0; j < na; j++) { double dx = A[3 * j] - c[0], dy = A[3 * j + 1] - c[1], dz = A[3 * j + 2] - c[2], d = sqrt((dx * dx + dy * dy) + dz * dz); if (d != d) *nan_ = 1; else if (d < m) m = d; }
    return m;
}
EXPORT int cp_cut(const double *cand, i64 nc, const double *Q, i64 nq, const double *P, i64 np_, double tol)
{
    for (i64 k = 0; k < nc; k++) {
        int n1, n2; double a = mindist(Q, nq, cand + 3 * k, &n1);
        if (n1 || !(a < tol)) continue;
        double b = mindist(P, np_, cand + 3 * k, &n2);
        if (!n2 && b >= tol) return 1;
    }
    return 0;
}

EXPORT int lm_threads(void) { return omp_get_max_threads(); }
