/* fastlm_rays.c - rays.c plus quicker ways to the answers of its cast_one, for fastlm.c (light maps, road sight).  fastlm.py builds
   both files into one DLL; this file is compiled with the flags rays.py uses for rays.c (so the arithmetic of a ray against a box and
   a triangle is the arithmetic of rays.dll - compared bit for bit by fastlm.selftest), fastlm.c with -ffp-contract=off.

     rx_ref     cast_one of rays.c, as it is: the reference
     rx_any     is ANYTHING hit (nearer than tmax)?  Stops at the first hit.
     rx_nearer  is the nearest hit nearer than tlim?  Stops at the first hit that clearly is.
     rx_near    the nearest hit, the nearer boxes first (cast_one takes the right child first whatever the ray's direction)

   cast_one = "the walk": depth first, right child first; a node is dropped when the ray enters its box later than it leaves it or
   later than the nearest hit so far; in a leaf (up to 4 triangles) every triangle is tested.

   1. WHICH LEAVES ARE REACHED DOES NOT DEPEND ON THE TREE ABOVE THEM.  A box of rays.c is the exact min / max of the boxes below it,
      and the entry / leave distances are (corner - origin) x 1/direction, which rounding keeps in order: a child's entry is never
      earlier and its leave never later than its parent's, in the computed numbers.  So a leaf passes the test of every box above it
      whenever it passes its own, for any limit.  The three quick walks therefore use ANOTHER tree over the SAME leaves (rx_open):
      surface-area splits instead of rays.c's split at the middle of the longest side, and four boxes to a node, tested in one go
      (AVX2: the same subtraction, multiplication, min and max per box as cast_one, so the same numbers).  The leaves' own boxes and
      the order of the triangles in them are untouched.
   2. rx_any: the walk finds a hit if and only if some triangle that passes its tests lies in a leaf whose box passes for tmax (the
      walk's limit is still tmax until its first hit).  By 1. that does not depend on tree or order.  Exact, no assumption.
   3. rx_near / rx_nearer rest on ONE assumption, (A): a triangle that passes the tests is never computed more than HALF A DELTA
      NEARER than the entry of the ray into the box of its leaf.  DELTA = 1e-6 x (1 + distance); the rounding in question is about 1e-13.
        rx_near drops a box only when it begins more than 2 DELTA behind the nearest hit so far, and notes the second nearest hit.  By
        (A) every triangle within DELTA of the nearest hit has then been tested.  If there is such a second, the ray is given to
        cast_one (two triangles at one distance: which one it reports depends on its order).  If not, every other triangle lies more
        than DELTA behind the one found, so cast_one never has a nearer limit when it comes to that triangle's leaf, and by (A) cannot
        drop it: it finds the same triangle at the same distance (the same expressions).
        rx_nearer: a hit more than DELTA nearer than tlim -> yes (by (A) the walk cannot have dropped its leaf without holding a hit
        nearer than tlim already); nothing nearer than tlim + DELTA in any box that begins before tlim + 2 DELTA -> no (by (A) nothing
        else can be nearer); a hit within DELTA of tlim and none clearly nearer -> cast_one decides.
   4. cast_one skips a push when its stack of 96 is nearly full: a tree of rays.c deeper than 93 levels silently loses triangles
      (rx_depth; fastlm.py then sends every ray through rx_ref, the only walk that loses the same ones). */
#include "rays.c"
#ifdef __AVX2__
#include <immintrin.h>
#endif

typedef struct { double lo[3][4], hi[3][4]; int child[4], n, pad[3]; } QNode;      /* child >= 0: a QNode ; < 0: ~child = a leaf in RX.x */
typedef struct { Scene *s; Node *x; QNode *q; int nx, nq, depth, own; } RX;         /* x: binary tree over the leaves of s (own = 1: built here) ; q: the same, four to a node */

static int depth_of(const Node *nodes, int node, int d) {
    const Node *n = &nodes[node]; if (n->count > 0) return d;
    int a = depth_of(nodes, n->left, d + 1), b = depth_of(nodes, n->right, d + 1); return a > b ? a : b;
}
/* the deepest leaf of the tree of rays.c (root = 0); cast_one is complete while this is below 94 */
EXPORT int rx_depth(void *h) { const Scene *s = ((const RX *)h)->s; return s->ntri > 0 ? depth_of(s->nodes, 0, 0) : 0; }
EXPORT int rx_depth2(void *h) { const RX *X = (const RX *)h; return X->depth; }      /* of the binary tree the quick walks' tree was made from */
EXPORT int rx_nodes(void *h) { return ((const RX *)h)->s->nnode; }

/* ---- the second tree: binned surface-area splits over the leaves of the first */
static inline double half_area(const double *lo, const double *hi) { double a = hi[0] - lo[0], b = hi[1] - lo[1], c = hi[2] - lo[2]; return a * b + b * c + a * c; }
#define XBINS 16
static int xbuild(RX *X, int *prim, int a, int b, int depth) {
    const Node *L = X->s->nodes; int me = X->nx++; Node *n = &X->x[me]; if (depth > X->depth) X->depth = depth;
    if (b - a == 1) { *n = L[prim[a]]; n->left = n->right = -1; return me; }            /* a leaf of rays.c: its box, its triangles */
    double clo[3] = { DBL_MAX, DBL_MAX, DBL_MAX }, chi[3] = { -DBL_MAX, -DBL_MAX, -DBL_MAX };
    for (int q = 0; q < 3; q++) { n->lo[q] = DBL_MAX; n->hi[q] = -DBL_MAX; }
    for (int i = a; i < b; i++) { const Node *p = &L[prim[i]];
        for (int q = 0; q < 3; q++) { if (p->lo[q] < n->lo[q]) n->lo[q] = p->lo[q]; if (p->hi[q] > n->hi[q]) n->hi[q] = p->hi[q];
                                      double c = p->lo[q] + p->hi[q]; if (c < clo[q]) clo[q] = c; if (c > chi[q]) chi[q] = c; } }
    n->first = 0; n->count = 0;
    int bax = -1, bsp = 0; double bcost = DBL_MAX;
    for (int ax = 0; ax < 3; ax++) {
        double ext = chi[ax] - clo[ax]; if (!(ext > 0)) continue;
        double blo[XBINS][3], bhi[XBINS][3], rr[XBINS]; int cnt[XBINS], rc[XBINS];
        for (int k = 0; k < XBINS; k++) { cnt[k] = 0; for (int q = 0; q < 3; q++) { blo[k][q] = DBL_MAX; bhi[k][q] = -DBL_MAX; } }
        for (int i = a; i < b; i++) { const Node *p = &L[prim[i]]; int k = (int)((p->lo[ax] + p->hi[ax] - clo[ax]) / ext * XBINS); if (k >= XBINS) k = XBINS - 1; if (k < 0) k = 0;
            cnt[k] += p->count + 1; for (int q = 0; q < 3; q++) { if (p->lo[q] < blo[k][q]) blo[k][q] = p->lo[q]; if (p->hi[q] > bhi[k][q]) bhi[k][q] = p->hi[q]; } }
        double lo[3] = { DBL_MAX, DBL_MAX, DBL_MAX }, hi[3] = { -DBL_MAX, -DBL_MAX, -DBL_MAX }; int c = 0;
        for (int k = XBINS - 1; k > 0; k--) { c += cnt[k]; for (int q = 0; q < 3; q++) { if (blo[k][q] < lo[q]) lo[q] = blo[k][q]; if (bhi[k][q] > hi[q]) hi[q] = bhi[k][q]; } rc[k] = c; rr[k] = c ? half_area(lo, hi) : 0.0; }
        for (int q = 0; q < 3; q++) { lo[q] = DBL_MAX; hi[q] = -DBL_MAX; } c = 0;
        for (int k = 0; k < XBINS - 1; k++) {
            c += cnt[k]; for (int q = 0; q < 3; q++) { if (blo[k][q] < lo[q]) lo[q] = blo[k][q]; if (bhi[k][q] > hi[q]) hi[q] = bhi[k][q]; }
            if (!c || !rc[k + 1]) continue;
            double cost = half_area(lo, hi) * c + rr[k + 1] * rc[k + 1]; if (cost < bcost) { bcost = cost; bax = ax; bsp = k; }
        }
    }
    int mid = a;
    if (bax >= 0) {
        double ext = chi[bax] - clo[bax]; int i = a, j = b - 1;
        while (i <= j) { const Node *p = &L[prim[i]]; int k = (int)((p->lo[bax] + p->hi[bax] - clo[bax]) / ext * XBINS); if (k >= XBINS) k = XBINS - 1; if (k < 0) k = 0;
            if (k <= bsp) i++; else { int t = prim[i]; prim[i] = prim[j]; prim[j] = t; j--; } }
        mid = i;
    }
    if (mid == a || mid == b) mid = (a + b) / 2;                       /* all centres in one place: halve */
    int l = xbuild(X, prim, a, mid, depth + 1), r = xbuild(X, prim, mid, b, depth + 1);
    X->x[me].left = l; X->x[me].right = r; return me;
}
/* four to a node: the two children of binary node b, the larger inner ones of them replaced by their own children */
static int qbuild(RX *X, int b) {
    const Node *B = X->x; int me = X->nq++, ch[4], n = 0;
    if (B[b].count > 0) ch[n++] = b;                                   /* (a scene of one leaf) */
    else { ch[n++] = B[b].left; ch[n++] = B[b].right; }
    while (n < 4) {
        int k = -1; double ba = -1.0;
        for (int i = 0; i < n; i++) if (B[ch[i]].count == 0) { double ar = half_area(B[ch[i]].lo, B[ch[i]].hi); if (ar > ba) { ba = ar; k = i; } }
        if (k < 0) break;
        int c = ch[k]; ch[k] = B[c].left; ch[n++] = B[c].right;
    }
    for (int i = 0; i < 4; i++) for (int a = 0; a < 3; a++) { X->q[me].lo[a][i] = i < n ? B[ch[i]].lo[a] : 0.0; X->q[me].hi[a][i] = i < n ? B[ch[i]].hi[a] : 0.0; }
    X->q[me].n = n;
    for (int i = 0; i < 4; i++) { int r = i >= n ? 0 : (B[ch[i]].count > 0 ? ~ch[i] : qbuild(X, ch[i])); X->q[me].child[i] = r; }
    return me;
}

/* h = the scene of rt_build.  own_tree 1: the quick walks' tree is made from surface-area splits ; 0: from the tree of rays.c (four to a node either way) */
EXPORT void *rx_open(void *h, int own_tree) {
    Scene *s = (Scene *)h; RX *X = (RX *)calloc(1, sizeof(RX)); if (!X) return NULL;
    X->s = s; X->x = s->nodes; X->nx = s->nnode; X->depth = s->ntri > 0 ? depth_of(s->nodes, 0, 0) : 0;
    if (s->ntri <= 0) return X;
    int nl = 0; for (int i = 0; i < s->nnode; i++) nl += s->nodes[i].count > 0;
    if (own_tree) {
        int *prim = (int *)malloc(sizeof(int) * (size_t)(nl + 1)); Node *x = (Node *)malloc(sizeof(Node) * (size_t)(2 * nl + 2));
        if (prim && x) { nl = 0; for (int i = 0; i < s->nnode; i++) if (s->nodes[i].count > 0) prim[nl++] = i;
                         X->x = x; X->nx = 0; X->depth = 0; X->own = 1; xbuild(X, prim, 0, nl, 0); }
        else free(x);
        free(prim);
    }
    X->q = (QNode *)malloc(sizeof(QNode) * (size_t)(nl + 1));
    if (!X->q) { if (X->own) free(X->x); free(X); return NULL; }
    X->nq = 0; qbuild(X, 0); return X;
}
EXPORT void rx_close(void *h) { RX *X = (RX *)h; if (!X) return; if (X->own) free(X->x); free(X->q); free(X); }

EXPORT int rx_ref(void *h, const double *o, const double *d, double tmax, double *tout) { return cast_one(((const RX *)h)->s, o, d, tmax, tout); }

#ifndef RXC
#define RXC(x)                                                         /* (a test build counts boxes and triangles here) */
#endif
/* the four boxes of a node against the ray: e[k] = entry distance of box k as cast_one computes it (max of 0 and the three slab entries);
   -> bit k set when the ray does not leave box k before it enters it and enters it no later than lim */
static inline int box4(const QNode *q, const double *o, const double *inv, double lim, double *e) {
    RXC(rxc_box += q->n;)
#ifdef __AVX2__
    __m256d t0 = _mm256_setzero_pd(), t1 = _mm256_set1_pd(INFINITY);
    for (int a = 0; a < 3; a++) {
        __m256d vo = _mm256_set1_pd(o[a]), vi = _mm256_set1_pd(inv[a]);
        __m256d x0 = _mm256_mul_pd(_mm256_sub_pd(_mm256_loadu_pd(q->lo[a]), vo), vi), x1 = _mm256_mul_pd(_mm256_sub_pd(_mm256_loadu_pd(q->hi[a]), vo), vi);
        t0 = _mm256_max_pd(t0, _mm256_min_pd(x0, x1)); t1 = _mm256_min_pd(t1, _mm256_max_pd(x0, x1));
    }
    _mm256_storeu_pd(e, t0);
    return _mm256_movemask_pd(_mm256_and_pd(_mm256_cmp_pd(t0, t1, _CMP_LE_OQ), _mm256_cmp_pd(t0, _mm256_set1_pd(lim), _CMP_LE_OQ))) & ((1 << q->n) - 1);
#else
    int m = 0;
    for (int k = 0; k < q->n; k++) {
        double t0 = 0.0, t1 = INFINITY;
        for (int a = 0; a < 3; a++) {
            double x0 = (q->lo[a][k] - o[a]) * inv[a], x1 = (q->hi[a][k] - o[a]) * inv[a];
            if (x0 > x1) { double w = x0; x0 = x1; x1 = w; }
            if (x0 > t0) t0 = x0; if (x1 < t1) t1 = x1;
        }
        e[k] = t0; if (!(t0 > t1) && !(t0 > lim)) m |= 1 << k;
    }
    return m;
#endif
}

/* the triangle test of cast_one, word for word (the same expressions, so the same rounding): continue = not hit */
#define RX_TRI(i) \
    RXC(rxc_tri++;) \
    const double *v = s->v + 9 * (size_t)(i); \
    double e1[3] = { v[3] - v[0], v[4] - v[1], v[5] - v[2] }, e2[3] = { v[6] - v[0], v[7] - v[1], v[8] - v[2] }; \
    double p[3] = { d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0] }; \
    double det = e1[0] * p[0] + e1[1] * p[1] + e1[2] * p[2]; \
    if (fabs(det) < 1e-18) continue; \
    double id = 1.0 / det, tv[3] = { o[0] - v[0], o[1] - v[1], o[2] - v[2] }; \
    double b1 = (tv[0] * p[0] + tv[1] * p[1] + tv[2] * p[2]) * id; if (b1 < -1e-9 || b1 > 1.0 + 1e-9) continue; \
    double q[3] = { tv[1] * e1[2] - tv[2] * e1[1], tv[2] * e1[0] - tv[0] * e1[2], tv[0] * e1[1] - tv[1] * e1[0] }; \
    double b2 = (d[0] * q[0] + d[1] * q[1] + d[2] * q[2]) * id; if (b2 < -1e-9 || b1 + b2 > 1.0 + 1e-9) continue; \
    double t = (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) * id;

#define RX_STACK 512                                                   /* (three boxes can wait at every level; fastlm.py asks for a binary depth below 100) */
#define RX_INV double inv[3]; for (int a = 0; a < 3; a++) inv[a] = 1.0 / (fabs(d[a]) > 1e-300 ? d[a] : (d[a] < 0 ? -1e-300 : 1e-300));
/* the boxes of node Q that passed (mask m, entries e) go on the stack, the farthest first: the nearest is taken next */
#define RX_PUSH(Q, m, e) \
    while (m) { \
        int kk = -1; double ee = -1.0; \
        for (int k = 0; k < 4; k++) if ((m >> k & 1) && e[k] > ee) { ee = e[k]; kk = k; } \
        m &= ~(1 << kk); stack[sp] = (Q)->child[kk]; se[sp++] = ee; \
    }

/* 1 = a triangle is hit nearer than tlim = the tmax of the walk (the tests of cast_one with its limit fixed there) */
EXPORT int rx_any(void *h, const double *o, const double *d, double tlim) {
    const RX *X = (const RX *)h; const Scene *s = X->s; if (s->ntri == 0) return 0;
    RX_INV
    int stack[RX_STACK], sp = 0; double se[RX_STACK]; stack[sp] = 0; se[sp++] = 0.0;
    while (sp) {
        int r = stack[--sp];
        if (r < 0) {
            const Node *n = &X->x[~r];
            for (int i = n->first; i < n->first + n->count; i++) {
                RX_TRI(i)
                if (t <= 1e-9 || t >= tlim) continue;
                if (s->tmat && through_hole(s, s->orig[i], b1, b2)) continue;
                return 1;
            }
        } else { double e[4]; const QNode *Q = &X->q[r]; int m = box4(Q, o, inv, tlim, e); RX_PUSH(Q, m, e) }
    }
    return 0;
}

/* 1 = cast_one(tmax) would report a hit nearer than tlim (road sight: "is the polygon hidden?").  *fell counts the rays given to cast_one */
EXPORT int rx_nearer(void *h, const double *o, const double *d, double tmax, double tlim, long long *fell) {
    const RX *X = (const RX *)h; const Scene *s = X->s; if (s->ntri == 0) return 0;
    RX_INV
    double delta = 1e-6 * (1.0 + fabs(tlim)), far = tlim + 2.0 * delta, sure = tlim - delta, near = tlim + delta; if (far > tmax) far = tmax;
    int stack[RX_STACK], sp = 0, close = 0; double se[RX_STACK]; stack[sp] = 0; se[sp++] = 0.0;
    while (sp) {
        int r = stack[--sp];
        if (r < 0) {
            const Node *n = &X->x[~r];
            for (int i = n->first; i < n->first + n->count; i++) {
                RX_TRI(i)
                if (t <= 1e-9 || t >= tmax || !(t < near)) continue;
                if (s->tmat && through_hole(s, s->orig[i], b1, b2)) continue;
                if (t < sure) return 1;
                close = 1;
            }
        } else { double e[4]; const QNode *Q = &X->q[r]; int m = box4(Q, o, inv, far, e); RX_PUSH(Q, m, e) }
    }
    if (close) { double tt = tmax; int r = cast_one(s, o, d, tmax, &tt); if (fell) (*fell)++; return r >= 0 && tt < tlim; }
    return 0;
}

/* the nearest hit: the answer of cast_one (see the top of this file).  *fell (when given) counts the rays handed to cast_one */
EXPORT int rx_near(void *h, const double *o, const double *d, double tmax, double *tout, long long *fell) {
    const RX *X = (const RX *)h; const Scene *s = X->s; if (s->ntri == 0) return -1;
    RX_INV
    int stack[RX_STACK], sp = 0, best = -1; double se[RX_STACK], tb = tmax, lim = tmax, second = INFINITY;      /* lim: boxes that begin later are dropped (tmax, then the hit + 2 DELTA) */
    stack[sp] = 0; se[sp++] = 0.0;
    while (sp) {
        --sp; if (se[sp] > lim) continue;
        int r = stack[sp];
        if (r < 0) {
            const Node *n = &X->x[~r];
            for (int i = n->first; i < n->first + n->count; i++) {
                RX_TRI(i)
                if (t <= 1e-9) continue;
                if (t >= tb) {                                         /* not nearer: it only matters as a close second */
                    if (best >= 0 && t < second && t <= lim && !(s->tmat && through_hole(s, s->orig[i], b1, b2))) second = t;
                    continue;
                }
                if (s->tmat && through_hole(s, s->orig[i], b1, b2)) continue;
                if (best >= 0 && tb < second) second = tb;
                tb = t; best = s->orig[i]; lim = tb + 2e-6 * (1.0 + tb);
            }
        } else { double e[4]; const QNode *Q = &X->q[r]; int m = box4(Q, o, inv, lim, e); RX_PUSH(Q, m, e) }
    }
    if (best >= 0 && second <= tb + 1e-6 * (1.0 + tb)) { if (fell) (*fell)++; return cast_one(s, o, d, tmax, tout); }
    if (tout) *tout = tb; return best;
}

/* n rays, for fastlm.selftest: hit / t as rt_cast gives them (t = tmax when nothing is hit).
   how 0: cast_one ; 1: rx_near ; 2: rx_nearer, t[i] holds the limit of ray i on entry and keeps it (hit 0 = nearer, -1 = not) ; 3: rx_any (hit 0 / -1) */
EXPORT void rx_cast(void *h, int how, const double *org, const double *dir, long long n, double tmax, int *hit, double *t, long long *fell) {
    long long i, f = 0;
    #pragma omp parallel for schedule(dynamic, 4096) reduction(+: f)
    for (i = 0; i < n; i++) {
        double tt = tmax; int r;
        if (how == 0) r = cast_one(((const RX *)h)->s, org + 3 * i, dir + 3 * i, tmax, &tt);
        else if (how == 1) r = rx_near(h, org + 3 * i, dir + 3 * i, tmax, &tt, &f);
        else if (how == 2) { tt = t[i]; r = rx_nearer(h, org + 3 * i, dir + 3 * i, tmax, tt, &f) ? 0 : -1; }
        else { r = rx_any(h, org + 3 * i, dir + 3 * i, tmax) ? 0 : -1; if (r < 0) tt = tmax; }
        hit[i] = r; t[i] = (r < 0 && how != 2) ? tmax : tt;
    }
    if (fell) *fell = f;
}
