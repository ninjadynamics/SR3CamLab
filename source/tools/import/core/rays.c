/* rays.c - a small ray caster for the importer (side detection, baked light).  Triangles in a BVH, rays cast on every core.
   Build:  gcc -O3 -march=native -fopenmp -shared -o rays.dll rays.c        (rays.py does it when rays.dll is older than this file)
   Why: the same rays cast through Blender's Python took 150 .. 200 s of a build (28 million calls into ray_cast, one by one).
   All numbers are doubles; triangles are hit from both sides; a triangle with a see-through mask lets a ray through its holes. */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <float.h>
#include <omp.h>

#define EXPORT __declspec(dllexport)
#define LEAF 4

typedef struct { double lo[3], hi[3]; int left, right, first, count; } Node;      /* count > 0: a leaf over tri index [first, first + count) */
typedef struct {
    int ntri, nnode; double *v;          /* ntri x 9, reordered */
    int *orig;                           /* reordered position -> the caller's triangle number */
    Node *nodes;
    /* see-through masks (optional) */
    const int *tmat; const double *tuv;  /* per ORIGINAL triangle: material, 3 x (u, v) */
    const int *mw, *mh; const long long *moff; const unsigned char *mbits; int nmat;
} Scene;

static void tri_box(const double *t, double *lo, double *hi) {
    for (int a = 0; a < 3; a++) { double x = t[a], y = t[3 + a], z = t[6 + a]; lo[a] = fmin(x, fmin(y, z)); hi[a] = fmax(x, fmax(y, z)); }
}

static int build(Scene *s, double *cen, int first, int count) {
    int me = s->nnode++; Node *n = &s->nodes[me];
    for (int a = 0; a < 3; a++) { n->lo[a] = DBL_MAX; n->hi[a] = -DBL_MAX; }
    double clo[3] = { DBL_MAX, DBL_MAX, DBL_MAX }, chi[3] = { -DBL_MAX, -DBL_MAX, -DBL_MAX };
    for (int i = first; i < first + count; i++) {
        double lo[3], hi[3]; tri_box(s->v + 9 * (size_t)i, lo, hi);
        for (int a = 0; a < 3; a++) { if (lo[a] < n->lo[a]) n->lo[a] = lo[a]; if (hi[a] > n->hi[a]) n->hi[a] = hi[a];
                                      double c = cen[3 * (size_t)i + a]; if (c < clo[a]) clo[a] = c; if (c > chi[a]) chi[a] = c; }
    }
    n->left = n->right = -1; n->first = first; n->count = count;
    if (count <= LEAF) return me;
    int ax = 0; if (chi[1] - clo[1] > chi[ax] - clo[ax]) ax = 1; if (chi[2] - clo[2] > chi[ax] - clo[ax]) ax = 2;
    double mid = 0.5 * (clo[ax] + chi[ax]); int i = first, j = first + count - 1;
    while (i <= j) {
        if (cen[3 * (size_t)i + ax] < mid) i++;
        else {
            double tv[9], tc[3]; int to;
            memcpy(tv, s->v + 9 * (size_t)i, sizeof tv); memcpy(s->v + 9 * (size_t)i, s->v + 9 * (size_t)j, sizeof tv); memcpy(s->v + 9 * (size_t)j, tv, sizeof tv);
            memcpy(tc, cen + 3 * (size_t)i, sizeof tc); memcpy(cen + 3 * (size_t)i, cen + 3 * (size_t)j, sizeof tc); memcpy(cen + 3 * (size_t)j, tc, sizeof tc);
            to = s->orig[i]; s->orig[i] = s->orig[j]; s->orig[j] = to; j--;
        }
    }
    int nl = i - first;
    if (nl == 0 || nl == count) nl = count / 2;                       /* all centres on one side (many triangles in one place): halve */
    n->count = 0;
    int l = build(s, cen, first, nl); int r = build(s, cen, first + nl, count - nl);
    s->nodes[me].left = l; s->nodes[me].right = r;                     /* (s->nodes does not move: it was sized for the worst case) */
    return me;
}

EXPORT void *rt_build(const double *tris, int ntri) {
    Scene *s = (Scene *)calloc(1, sizeof(Scene)); s->ntri = ntri;
    s->v = (double *)malloc(sizeof(double) * 9 * (size_t)(ntri > 0 ? ntri : 1)); memcpy(s->v, tris, sizeof(double) * 9 * (size_t)ntri);
    s->orig = (int *)malloc(sizeof(int) * (size_t)(ntri > 0 ? ntri : 1)); for (int i = 0; i < ntri; i++) s->orig[i] = i;
    s->nodes = (Node *)malloc(sizeof(Node) * (size_t)(2 * ntri + 2));
    double *cen = (double *)malloc(sizeof(double) * 3 * (size_t)(ntri > 0 ? ntri : 1));
    for (int i = 0; i < ntri; i++) for (int a = 0; a < 3; a++) cen[3 * (size_t)i + a] = (tris[9 * (size_t)i + a] + tris[9 * (size_t)i + 3 + a] + tris[9 * (size_t)i + 6 + a]) / 3.0;
    if (ntri > 0) build(s, cen, 0, ntri);
    free(cen); return s;
}

EXPORT void rt_free(void *h) { Scene *s = (Scene *)h; if (!s) return; free(s->v); free(s->orig); free(s->nodes); free(s); }

/* masks: tmat[ntri] material of every triangle (the caller's numbering), tuv[ntri * 6], and for every material a bitmap of w x h bytes
   (1 = see-through) at mbits + moff[m], or moff[m] < 0 for none.  The arrays must stay alive while the scene is used. */
EXPORT void rt_masks(void *h, const int *tmat, const double *tuv, int nmat, const int *mw, const int *mh, const long long *moff, const unsigned char *mbits) {
    Scene *s = (Scene *)h; s->tmat = tmat; s->tuv = tuv; s->nmat = nmat; s->mw = mw; s->mh = mh; s->moff = moff; s->mbits = mbits;
}

static inline int through_hole(const Scene *s, int tri, double b1, double b2) {
    int m = s->tmat[tri]; if (m < 0 || m >= s->nmat || s->moff[m] < 0) return 0;
    const double *uv = s->tuv + 6 * (size_t)tri; double b0 = 1.0 - b1 - b2;
    double u = uv[0] * b0 + uv[2] * b1 + uv[4] * b2, v = uv[1] * b0 + uv[3] * b1 + uv[5] * b2;
    u -= floor(u); v = 1.0 - v; v -= floor(v);
    int w = s->mw[m], hh = s->mh[m]; int x = (int)(u * w); int y = (int)(v * hh); if (x >= w) x = w - 1; if (y >= hh) y = hh - 1; if (x < 0) x = 0; if (y < 0) y = 0;
    return s->mbits[s->moff[m] + (long long)y * w + x] != 0;
}

static inline int cast_one(const Scene *s, const double *o, const double *d, double tmax, double *tout) {
    if (s->ntri == 0) return -1;
    double inv[3]; for (int a = 0; a < 3; a++) inv[a] = 1.0 / (fabs(d[a]) > 1e-300 ? d[a] : (d[a] < 0 ? -1e-300 : 1e-300));
    int stack[1024], sp = 0, best = -1;      /* (it was 96 with pushes skipped above 94: a tree deeper than that silently lost triangles - shown with 120 stacked blades, 2026-10-08; Mountain is 31 deep) */ double tb = tmax; stack[sp++] = 0;
    while (sp) {
        const Node *n = &s->nodes[stack[--sp]];
        double t0 = 0.0, t1 = tb;
        for (int a = 0; a < 3; a++) {
            double x0 = (n->lo[a] - o[a]) * inv[a], x1 = (n->hi[a] - o[a]) * inv[a];
            if (x0 > x1) { double q = x0; x0 = x1; x1 = q; }
            if (x0 > t0) t0 = x0; if (x1 < t1) t1 = x1;
        }
        if (t0 > t1) continue;
        if (n->count > 0) {
            for (int i = n->first; i < n->first + n->count; i++) {
                const double *v = s->v + 9 * (size_t)i;
                double e1[3] = { v[3] - v[0], v[4] - v[1], v[5] - v[2] }, e2[3] = { v[6] - v[0], v[7] - v[1], v[8] - v[2] };
                double p[3] = { d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0] };
                double det = e1[0] * p[0] + e1[1] * p[1] + e1[2] * p[2];
                if (fabs(det) < 1e-18) continue;
                double id = 1.0 / det, tv[3] = { o[0] - v[0], o[1] - v[1], o[2] - v[2] };
                double b1 = (tv[0] * p[0] + tv[1] * p[1] + tv[2] * p[2]) * id; if (b1 < -1e-9 || b1 > 1.0 + 1e-9) continue;
                double q[3] = { tv[1] * e1[2] - tv[2] * e1[1], tv[2] * e1[0] - tv[0] * e1[2], tv[0] * e1[1] - tv[1] * e1[0] };
                double b2 = (d[0] * q[0] + d[1] * q[1] + d[2] * q[2]) * id; if (b2 < -1e-9 || b1 + b2 > 1.0 + 1e-9) continue;
                double t = (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) * id;
                if (t <= 1e-9 || t >= tb) continue;
                if (s->tmat && through_hole(s, s->orig[i], b1, b2)) continue;
                tb = t; best = s->orig[i];
            }
        } else if (sp < 1022) { stack[sp++] = n->left; stack[sp++] = n->right; }
    }
    if (tout) *tout = tb; return best;
}

/* n rays: org[n*3], dir[n*3] (unit), tmax -> hit[n] = the caller's triangle number or -1, t[n] = distance (tmax when nothing was hit) */
EXPORT void rt_cast(void *h, const double *org, const double *dir, long long n, double tmax, int *hit, double *t) {
    const Scene *s = (const Scene *)h; long long i;
    #pragma omp parallel for schedule(dynamic, 4096)
    for (i = 0; i < n; i++) { double tt = tmax; hit[i] = cast_one(s, org + 3 * i, dir + 3 * i, tmax, &tt); t[i] = hit[i] < 0 ? tmax : tt; }
}

/* a FAN of k directions from every point, in the point's own frame (z = its normal n, x = t, y = b): what side detection and the sky
   part of the baked light need.  fan[k*3] local unit directions; turn[np] an angle about the normal per point (0 for none).
   -> hit[np*k], t[np*k].  The rays start `lift` along the normal and `skip` along themselves. */
EXPORT void rt_fan(void *h, const double *p, const double *nrm, long long np, const double *fan, int k, const double *turn, double lift, double skip, double tmax, int *hit, double *t) {
    const Scene *s = (const Scene *)h; long long i;
    #pragma omp parallel for schedule(dynamic, 512)
    for (i = 0; i < np; i++) {
        const double *n = nrm + 3 * i; double ax[3] = { 0, 1, 0 }; if (fabs(n[1]) >= 0.9) { ax[0] = 1; ax[1] = 0; }
        double tx[3] = { n[1] * ax[2] - n[2] * ax[1], n[2] * ax[0] - n[0] * ax[2], n[0] * ax[1] - n[1] * ax[0] };
        double l = sqrt(tx[0] * tx[0] + tx[1] * tx[1] + tx[2] * tx[2]); if (l < 1e-12) l = 1; tx[0] /= l; tx[1] /= l; tx[2] /= l;
        double b[3] = { n[1] * tx[2] - n[2] * tx[1], n[2] * tx[0] - n[0] * tx[2], n[0] * tx[1] - n[1] * tx[0] };
        double ca = 1.0, sa = 0.0; if (turn) { ca = cos(turn[i]); sa = sin(turn[i]); }
        for (int j = 0; j < k; j++) {
            double hx = fan[3 * j] * ca - fan[3 * j + 1] * sa, hy = fan[3 * j] * sa + fan[3 * j + 1] * ca, hz = fan[3 * j + 2];
            double d[3] = { tx[0] * hx + b[0] * hy + n[0] * hz, tx[1] * hx + b[1] * hy + n[1] * hz, tx[2] * hx + b[2] * hy + n[2] * hz };
            double o[3] = { p[3 * i] + n[0] * lift + d[0] * skip, p[3 * i + 1] + n[1] * lift + d[1] * skip, p[3 * i + 2] + n[2] * lift + d[2] * skip };
            double tt = tmax; int r = cast_one(s, o, d, tmax, &tt); hit[i * k + j] = r; t[i * k + j] = r < 0 ? tmax : tt;
        }
    }
}

EXPORT int rt_threads(void) { return omp_get_max_threads(); }
