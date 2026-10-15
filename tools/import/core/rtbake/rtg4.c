/* rtg4.c = rtg2.c + lm4_light (rt_bake_game4.py, 2026-10-13): WHERE on its polygon a texel is lit from.
   lm2_light took the texel's own point, 2 cm off the surface. Three things came of that (owner's screenshots, 2026-10-13):
     - a texel on a polygon's EDGE lies exactly in the plane of the wall that stands on that edge; 2 cm up it was behind any wall that leans
       over the road at all, in full sun: a lit strip along the foot of such a wall, inside the wall's own shadow ;
     - where the ground goes on behind a wall, the texel behind it is in the sun and the game blends it into the one in front ;
     - one point per texel is 0 or 1: blended by the game, a slanted shadow edge came out in steps.
   lm4_light: the point is kept a few centimetres inside its polygon's edges ; short feelers along the surface (one texel) find what crosses
   it, and a point that stands BEHIND something whose back the road never sees is moved in front of it ; the sun is asked from points spread
   over the texel's own square (those cut off from the texel's point by something are not used).
   (made by mk_rtg4.py from rtg2.c and rtg4_tail.c)
   ----- the text of rtg2.c:
 rtg2.c - the per-ray work of rt_bake_game2.py (functions cast / sun_seen / light) and its last loop (the 3 x 3 smoothing of every
   polygon's rectangle) in C, for rt_bake_game2_fast.py.  Nothing here decides anything new: every number is computed by the formula
   the numpy code uses, in numpy's order (a row sum of three is (x + y) + z, a mean over k adds one after the other).
   Compile with -ffp-contract=off and never with -ffast-math.  The rays: rtg2_rays.c (rays.c + fastlm_rays.c + rx_any_from).

   What numpy still does and hands over: the texel positions and normals, the "faces the sun" flag ((n @ SUN) > 0.02), cos / sin of
   every texel's fan turn, and per scene triangle its normal, normal @ SUN and normal @ design (so the BLAS products stay numpy's).

   mode 0   every ray through cast_one of rays.c (the reference walk)
   mode 1   nearest hits through rx_near (the same answer as cast_one, see fastlm_rays.c)
   mode 2   as 1, and a ray that only asks "is the sun hidden?" first asks rx_any_from: is ANYTHING hit 0.11 m out or farther?
            Yes -> hidden (the chain of cast() only ever goes on through hits nearer than 0.10 m, so it must arrive at that hit or stop
            before it).  No -> the chain as written, with nothing to find beyond 0.12 m.  */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <omp.h>
#define EXPORT __declspec(dllexport)
typedef long long i64;

extern int rx_ref(void *h, const double *o, const double *d, double tmax, double *tout);
extern int rx_near(void *h, const double *o, const double *d, double tmax, double *tout, long long *fell);
extern int rx_any_from(void *h, const double *o, const double *d, double tmin, double tlim);

#define DOT3(a, b)  (((a)[0] * (b)[0] + (a)[1] * (b)[1]) + (a)[2] * (b)[2])        /* (a * b).sum(1) */
#define NORM3(a)    sqrt(((a)[0] * (a)[0] + (a)[1] * (a)[1]) + (a)[2] * (a)[2])     /* np.linalg.norm(a, axis=1) */
static inline void cross3(const double *a, const double *b, double *c) { c[0] = a[1] * b[2] - a[2] * b[1]; c[1] = a[2] * b[0] - a[0] * b[2]; c[2] = a[0] * b[1] - a[1] * b[0]; }
static inline double clip01(double x) { return x < 0.0 ? 0.0 : (x > 1.0 ? 1.0 : x); }

typedef struct {
    void *sc; int mode; const double *TN, *TNS, *TND; const int *TMA; const double *alb, *SUN, *SD, *HEMI; int nsd, ks, turns; double lift;
} ctx;
typedef struct { i64 rays, fell, quick; } cnt_t;

static inline int near1(const ctx *c, const double *o, const double *d, double tmax, double *t, cnt_t *k)
{
    double tt = tmax; int h = c->mode ? rx_near(c->sc, o, d, tmax, &tt, &k->fell) : rx_ref(c->sc, o, d, tmax, &tt);
    k->rays++; *t = h < 0 ? tmax : tt; return h;
}
/* cast() of rt_bake_game2.py for one ray: the nearest hit, going on through layers nearly parallel to the face the ray left and within 10 cm */
static inline int chain(const ctx *c, const double *o, const double *d, const double *nsrc, double tmax, double *tout, cnt_t *k)
{
    double t; int hit = near1(c, o, d, tmax, &t, k);
    for (int rnd = 0; rnd < 3; rnd++) {
        if (!(hit >= 0 && t < 0.10)) break;
        const double *tn = c->TN + 3 * (size_t)hit; if (!(fabs(DOT3(tn, nsrc)) > 0.9)) break;
        double s = t + 0.003, o2[3] = { o[0] + d[0] * s, o[1] + d[1] * s, o[2] + d[2] * s }, t2;
        int h2 = near1(c, o2, d, tmax, &t2, k); hit = h2; t = h2 >= 0 ? s + t2 : t2;
    }
    if (tout) *tout = t; return hit;
}
/* 1 = cast(o, d, nsrc) reports a hit (tmax 1e9) */
static inline int hidden(const ctx *c, const double *o, const double *d, const double *nsrc, cnt_t *k)
{
    if (c->mode >= 2) {
        k->rays++; if (rx_any_from(c->sc, o, d, 0.11, 1e9)) { k->quick++; return 1; }
        return chain(c, o, d, nsrc, 0.12, NULL, k) >= 0;
    }
    return chain(c, o, d, nsrc, 1e9, NULL, k) >= 0;
}

/* sun_seen + light of rt_bake_game2.py for n points.
   pt[n*3], nrm[n*3] unit facing, fsun[n] = (nrm @ SUN) > 0.02, CA / SA [n * turns] cos / sin of the fan's turn,
   TN[nt*3], TNS[nt] = TN @ SUN, TND[nt] = TN @ design, TMA[nt] material, alb[nmat*3]
   -> V[n], sky[n], back[n*3] ; stats[3] = rays cast, rays rx_near handed to cast_one, sun questions answered by rx_any_from */
EXPORT void lm2_light(void *sc, int mode, i64 n, const double *pt, const double *nrm, const unsigned char *fsun, const double *CA, const double *SA, int turns,
                      const double *TN, const double *TNS, const double *TND, const int *TMA, const double *alb,
                      const double *SUN, const double *SD, int nsd, const double *HEMI, int ks, double lift,
                      double *V, double *sky, double *back, i64 *stats)
{
    ctx c = { sc, mode, TN, TNS, TND, TMA, alb, SUN, SD, HEMI, nsd, ks, turns, lift }; i64 nray = 0, nfell = 0, nquick = 0;
    #pragma omp parallel for schedule(dynamic, 64) reduction(+: nray, nfell, nquick)
    for (i64 i = 0; i < n; i++) {
        const double *P = pt + 3 * i, *nn = nrm + 3 * i; cnt_t k = { 0, 0, 0 };
        double o[3] = { P[0] + nn[0] * lift, P[1] + nn[1] * lift, P[2] + nn[2] * lift };
        double v = 0.0;
        if (fsun[i]) {
            int open = 0;
            for (int j = 0; j < nsd; j++) {
                const double *dd = SD + 3 * j; double oo[3] = { o[0] + dd[0] * lift, o[1] + dd[1] * lift, o[2] + dd[2] * lift };
                open += !hidden(&c, oo, dd, nn, &k);
            }
            v = (double)open / (double)nsd;
        }
        V[i] = v;
        double ax[3] = { 0.0, 1.0, 0.0 }; if (!(fabs(nn[1]) < 0.9)) { ax[0] = 1.0; ax[1] = 0.0; }
        double t[3], b[3]; cross3(nn, ax, t); double l = NORM3(t); if (!(l > 1e-12)) l = 1e-12; t[0] /= l; t[1] /= l; t[2] /= l; cross3(nn, t, b);
        double skyacc = 0.0, bacc[3] = { 0.0, 0.0, 0.0 };
        for (int turn = 0; turn < turns; turn++) {
            double ca = CA[i * turns + turn], sa = SA[i * turns + turn], acc[3] = { 0.0, 0.0, 0.0 }; int open = 0;
            for (int j = 0; j < ks; j++) {
                const double *H = HEMI + 3 * j; double hx = H[0] * ca - H[1] * sa, hy = H[0] * sa + H[1] * ca, d[3], oo[3], dist;
                for (int a = 0; a < 3; a++) { d[a] = (t[a] * hx + b[a] * hy) + nn[a] * H[2]; oo[a] = o[a] + d[a] * lift; }
                int hit = chain(&c, oo, d, nn, 1e9, &dist, &k);
                if (hit < 0) { open++; continue; }
                const double *tn = TN + 3 * (size_t)hit; int keep = DOT3(tn, d) < 0; double sg = keep ? 1.0 : -1.0, hn[3] = { keep ? tn[0] : -tn[0], keep ? tn[1] : -tn[1], keep ? tn[2] : -tn[2] };
                double litv = 0.34 * (0.5 + 0.5 * clip01(hn[1]));
                if (sg * TNS[hit] > 0.05) {
                    double o2[3];
                    for (int a = 0; a < 3; a++) { double loc = oo[a] + d[a] * dist; o2[a] = (loc + hn[a] * lift) + SUN[a] * lift; }
                    if (!hidden(&c, o2, SUN, hn, &k)) litv += 0.66 * clip01((sg * TND[hit] + 0.2) / 0.907);
                }
                if (!(litv < 1.0)) litv = 1.0;
                const double *al = alb + 3 * (size_t)TMA[hit]; acc[0] += al[0] * litv; acc[1] += al[1] * litv; acc[2] += al[2] * litv;
            }
            skyacc += (double)open / (double)ks; bacc[0] += acc[0] / ks; bacc[1] += acc[1] / ks; bacc[2] += acc[2] / ks;
        }
        sky[i] = skyacc / turns; back[3 * i] = bacc[0] / turns; back[3 * i + 1] = bacc[1] / turns; back[3 * i + 2] = bacc[2] / turns;
        nray += k.rays; nfell += k.fell; nquick += k.quick;
    }
    if (stats) { stats[0] = nray; stats[1] = nfell; stats[2] = nquick; }
}

/* the last loop of rt_bake_game2.py: every polygon's rectangle (w x h texels of 7 bytes at page / x0 / y0): channels 1..4 take the mean
   of the 3 x 3 texels round them (the rectangle's own edge repeated; only when w >= 3 and h >= 3), then the rectangle is grown to whole
   4 x 4 blocks by repeating its edge.  (The sums are whole numbers below 2296, exact in a float: the float32 arithmetic of numpy.) */
EXPORT void lm2_smooth(unsigned char *RAW, int PAGE, i64 np, const int *page, const int *x0, const int *y0, const i64 *nu, const i64 *nv)
{
    #pragma omp parallel for schedule(dynamic, 64)
    for (i64 i = 0; i < np; i++) {
        int w = (int)nu[i], h = (int)nv[i], w4 = (w + 3) / 4 * 4, h4 = (h + 3) / 4 * 4;
        unsigned char *pg = RAW + (size_t)page[i] * PAGE * PAGE * 7 + ((size_t)y0[i] * PAGE + x0[i]) * 7;
        #define PX(x, y) (pg + ((size_t)(y) * PAGE + (x)) * 7)
        if (w >= 3 && h >= 3) {
            unsigned char *src = (unsigned char *)malloc((size_t)w * h * 4);
            for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) memcpy(src + ((size_t)y * w + x) * 4, PX(x, y) + 1, 4);
            for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) for (int ch = 0; ch < 4; ch++) {
                float s = 0.0f;
                for (int dy = -1; dy <= 1; dy++) { int yy = y + dy; yy = yy < 0 ? 0 : (yy >= h ? h - 1 : yy);
                    for (int dx = -1; dx <= 1; dx++) { int xx = x + dx; xx = xx < 0 ? 0 : (xx >= w ? w - 1 : xx); s += (float)src[((size_t)yy * w + xx) * 4 + ch]; } }
                PX(x, y)[1 + ch] = (unsigned char)rintf(s / 9.0f);
            }
            free(src);
        }
        for (int y = 0; y < h4; y++) {
            if (y >= h) { memcpy(PX(0, y), PX(0, h - 1), (size_t)w4 * 7); continue; }
            for (int x = w; x < w4; x++) memcpy(PX(x, y), PX(w - 1, y), 7);
        }
        #undef PX
    }
}


/* ------------------------------------------------------------------ lm4_light */
typedef struct { const double *Q; double n1[3], n2[3]; int tri; double ma, mb; } poly_t;

static inline void poly_make(const double *Q, int tri, double ma, double mb, double side, poly_t *p)
{
    double e1[3], e2[3], e3[3];
    for (int a = 0; a < 3; a++) { e1[a] = Q[3 + a] - Q[a]; e2[a] = Q[6 + a] - Q[a]; e3[a] = Q[9 + a] - Q[a]; }
    cross3(e1, e2, p->n1); cross3(e2, e3, p->n2); double l1 = NORM3(p->n1), l2 = NORM3(p->n2);
    if (l1 > 1e-9) { for (int a = 0; a < 3; a++) p->n1[a] *= side / l1; }
    else if (l2 > 1e-9) { for (int a = 0; a < 3; a++) p->n1[a] = p->n2[a] * side / l2; }
    else { p->n1[0] = 0.0; p->n1[1] = side; p->n1[2] = 0.0; }
    if (l2 > 1e-9 && !tri) { for (int a = 0; a < 3; a++) p->n2[a] *= side / l2; } else { for (int a = 0; a < 3; a++) p->n2[a] = p->n1[a]; }
    p->Q = Q; p->tri = tri; p->ma = ma; p->mb = mb;
}
/* the place of grid point (a, b) on the two triangles the game draws (corners 1 0 2 and 0 2 3) and the normal of the one it lies on */
static inline void poly_pos(const poly_t *p, double a, double b, double *x, const double **n)
{
    const double *Q = p->Q;
    if (b <= a) { for (int k = 0; k < 3; k++) x[k] = Q[k] + (a - b) * (Q[3 + k] - Q[k]) + b * (Q[6 + k] - Q[k]); *n = p->n1; }
    else        { for (int k = 0; k < 3; k++) x[k] = Q[k] + a * (Q[6 + k] - Q[k]) + (b - a) * (Q[9 + k] - Q[k]); *n = p->n2; }
}
/* into the polygon: mirrored at its edges, kept the margin away from them ; a three-corner polygon is the half b <= a */
static inline void poly_clamp(const poly_t *p, double *a, double *b)
{
    double A = *a, B = *b;
    if (A < 0.0) A = -A;
    if (A > 1.0) A = 2.0 - A;
    if (B < 0.0) B = -B;
    if (B > 1.0) B = 2.0 - B;
    if (p->tri && B > A) { double t = A; A = B; B = t; }
    if (A < p->ma) A = p->ma;
    if (A > 1.0 - p->ma) A = 1.0 - p->ma;
    if (B < p->mb) B = p->mb;
    if (B > 1.0 - p->mb) B = 1.0 - p->mb;
    if (p->tri) {
        double md = 0.5 * (p->ma + p->mb);
        if (A - B < md) {
            double e = 0.5 * (md - (A - B)); A += e; B -= e;
            if (A > 1.0 - p->ma) A = 1.0 - p->ma;
            if (B < p->mb) B = p->mb;
        }
    }
    *a = A; *b = B;
}
/* what stands between two points just off the surface: the nearest triangle that is not a layer lying along the surface (-1: nothing).
   -> *t its distance, d[3] the unit direction, *L the whole length */
static inline int between(const ctx *c, const double *o, const double *e, const double *nsrc, double *t, double *d, double *L, cnt_t *k)
{
    double v[3] = { e[0] - o[0], e[1] - o[1], e[2] - o[2] }, len = NORM3(v); *L = len; *t = len;
    if (!(len > 1e-6)) return -1;
    d[0] = v[0] / len; d[1] = v[1] / len; d[2] = v[2] / len;
    double tt; int h = near1(c, o, d, len, &tt, k);
    if (h >= 0 && !(tt < len)) h = -1;
    for (int rnd = 0; rnd < 3 && h >= 0; rnd++) {
        const double *tn = c->TN + 3 * (size_t)h;
        if (!(fabs(DOT3(tn, nsrc)) > 0.9)) break;
        double s = tt + 0.003;
        if (!(s < len)) { h = -1; break; }
        double o2[3] = { o[0] + d[0] * s, o[1] + d[1] * s, o[2] + d[2] * s }, t2; int h2 = near1(c, o2, d, len - s, &t2, k);
        if (h2 >= 0 && !(t2 < len - s)) h2 = -1;
        h = h2; tt = s + t2;
    }
    if (h >= 0) *t = tt;
    return h;
}

/* n texels: pidx[n] their polygon, iu / iv[n] their place in its grid ; per polygon PQ[12] corners, PNU / PNV grid size, PTRI (corners 2 and 3
   are one place), PM[2] margins in grid units ; side +1 = the winding side, -1 the other ; TONE[nt] = 1: the back of that scene triangle is
   never looked at ; FOOT[nsd * 2] where in the texel's square (-0.5 .. 0.5) each sun ray starts ; inreach = the feelers' length in texels.
   -> V, sky, back[n * 3] as lm2_light, NOUT[n * 3] the normal at the point used ; stats[5] = rays, handed to cast_one, quick sun answers,
      texels moved in front of something, texels with something crossing their square */
EXPORT void lm4_light(void *sc, int mode, i64 n, const int *pidx, const int *iu, const int *iv,
                      const double *PQ, const int *PNU, const int *PNV, const unsigned char *PTRI, const double *PM, double side,
                      const double *CA, const double *SA, int turns,
                      const double *TN, const double *TNS, const double *TND, const int *TMA, const unsigned char *TONE, const double *alb,
                      const double *SUN, const double *SD, int nsd, const double *FOOT, const double *HEMI, int ks, double lift, double inreach,
                      double *V, double *sky, double *back, double *NOUT, i64 *stats)
{
    ctx c = { sc, mode, TN, TNS, TND, TMA, alb, SUN, SD, HEMI, nsd, ks, turns, lift }; i64 nray = 0, nfell = 0, nquick = 0, nmoved = 0, ncross = 0;
    static const double PR[8][2] = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 0.7, 0.7 }, { -0.7, 0.7 }, { 0.7, -0.7 }, { -0.7, -0.7 } };
    #pragma omp parallel for schedule(dynamic, 64) reduction(+: nray, nfell, nquick, nmoved, ncross)
    for (i64 i = 0; i < n; i++) {
        cnt_t k = { 0, 0, 0 }; size_t pi = (size_t)pidx[i]; poly_t p; poly_make(PQ + 12 * pi, PTRI[pi], PM[2 * pi], PM[2 * pi + 1], side, &p);
        double da = 1.0 / (double)(PNU[pi] - 1), db = 1.0 / (double)(PNV[pi] - 1), a0 = iu[i] * da, b0 = iv[i] * db, ar = a0, br = b0;
        poly_clamp(&p, &ar, &br);
        double xr[3], orr[3]; const double *nr; poly_pos(&p, ar, br, xr, &nr);
        for (int a = 0; a < 3; a++) orr[a] = xr[a] + nr[a] * lift;
        /* feelers: one texel along the surface in eight directions */
        int crossed = 0, moved = 0; double best = 1e30, am = ar, bm = br;
        for (int q = 0; q < 8; q++) {
            double at = ar + PR[q][0] * da * inreach, bt = br + PR[q][1] * db * inreach, xt[3], ot[3], t, d[3], L; const double *nt;
            poly_clamp(&p, &at, &bt); poly_pos(&p, at, bt, xt, &nt);
            for (int a = 0; a < 3; a++) ot[a] = xt[a] + nt[a] * lift;
            int h = between(&c, orr, ot, nr, &t, d, &L, &k);
            if (h < 0) continue;
            crossed = 1;
            if (TONE[h] && DOT3(d, TN + 3 * (size_t)h) > 0.0 && t < best) {
                double s = (t + 0.05) / L;
                if (s > 1.0) s = 1.0;
                best = t; am = ar + (at - ar) * s; bm = br + (bt - br) * s; moved = 1;
            }
        }
        if (moved) {
            ar = am; br = bm; poly_clamp(&p, &ar, &br); poly_pos(&p, ar, br, xr, &nr);
            for (int a = 0; a < 3; a++) orr[a] = xr[a] + nr[a] * lift;
            a0 = ar; b0 = br; nmoved++;
        }
        ncross += crossed;
        NOUT[3 * i] = nr[0]; NOUT[3 * i + 1] = nr[1]; NOUT[3 * i + 2] = nr[2];
        /* the sun, from points spread over the texel's square */
        int open = 0;
        for (int j = 0; j < nsd; j++) {
            double aj = a0 + FOOT[2 * j] * da, bj = b0 + FOOT[2 * j + 1] * db, xj[3], oj[3]; const double *nj;
            poly_clamp(&p, &aj, &bj); poly_pos(&p, aj, bj, xj, &nj);
            for (int a = 0; a < 3; a++) oj[a] = xj[a] + nj[a] * lift;
            if (crossed && j) {
                double t, d[3], L;
                if (between(&c, orr, oj, nr, &t, d, &L, &k) >= 0) { for (int a = 0; a < 3; a++) oj[a] = orr[a]; nj = nr; }
            }
            if (!(DOT3(nj, SUN) > 0.02)) continue;
            const double *dd = SD + 3 * j; double oo[3] = { oj[0] + dd[0] * lift, oj[1] + dd[1] * lift, oj[2] + dd[2] * lift };
            open += !hidden(&c, oo, dd, nj, &k);
        }
        V[i] = (double)open / (double)nsd;
        /* the sky and what comes back, from the texel's point (as lm2_light) */
        const double *nn = nr; const double *o = orr;
        double ax[3] = { 0.0, 1.0, 0.0 };
        if (!(fabs(nn[1]) < 0.9)) { ax[0] = 1.0; ax[1] = 0.0; }
        double t[3], b[3]; cross3(nn, ax, t); double l = NORM3(t);
        if (!(l > 1e-12)) l = 1e-12;
        t[0] /= l; t[1] /= l; t[2] /= l; cross3(nn, t, b);
        double skyacc = 0.0, bacc[3] = { 0.0, 0.0, 0.0 };
        for (int turn = 0; turn < turns; turn++) {
            double ca = CA[i * turns + turn], sa = SA[i * turns + turn], acc[3] = { 0.0, 0.0, 0.0 }; int opn = 0;
            for (int j = 0; j < ks; j++) {
                const double *H = HEMI + 3 * j; double hx = H[0] * ca - H[1] * sa, hy = H[0] * sa + H[1] * ca, d[3], oo[3], dist;
                for (int a = 0; a < 3; a++) { d[a] = (t[a] * hx + b[a] * hy) + nn[a] * H[2]; oo[a] = o[a] + d[a] * lift; }
                int hit = chain(&c, oo, d, nn, 1e9, &dist, &k);
                if (hit < 0) { opn++; continue; }
                const double *tn = TN + 3 * (size_t)hit; int keep = DOT3(tn, d) < 0; double sg = keep ? 1.0 : -1.0, hn[3] = { keep ? tn[0] : -tn[0], keep ? tn[1] : -tn[1], keep ? tn[2] : -tn[2] };
                double litv = 0.34 * (0.5 + 0.5 * clip01(hn[1]));
                if (sg * TNS[hit] > 0.05) {
                    double o2[3];
                    for (int a = 0; a < 3; a++) { double loc = oo[a] + d[a] * dist; o2[a] = (loc + hn[a] * lift) + SUN[a] * lift; }
                    if (!hidden(&c, o2, SUN, hn, &k)) litv += 0.66 * clip01((sg * TND[hit] + 0.2) / 0.907);
                }
                if (!(litv < 1.0)) litv = 1.0;
                const double *al = alb + 3 * (size_t)TMA[hit]; acc[0] += al[0] * litv; acc[1] += al[1] * litv; acc[2] += al[2] * litv;
            }
            skyacc += (double)opn / (double)ks; bacc[0] += acc[0] / ks; bacc[1] += acc[1] / ks; bacc[2] += acc[2] / ks;
        }
        sky[i] = skyacc / turns; back[3 * i] = bacc[0] / turns; back[3 * i + 1] = bacc[1] / turns; back[3 * i + 2] = bacc[2] / turns;
        nray += k.rays; nfell += k.fell; nquick += k.quick;
    }
    if (stats) { stats[0] = nray; stats[1] = nfell; stats[2] = nquick; stats[3] = nmoved; stats[4] = ncross; }
}

EXPORT int lm2_threads(void) { return omp_get_max_threads(); }

