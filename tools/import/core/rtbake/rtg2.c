/* rtg2.c - the per-ray work of rt_bake_game2.py (functions cast / sun_seen / light) and its last loop (the 3 x 3 smoothing of every
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

EXPORT int lm2_threads(void) { return omp_get_max_threads(); }
