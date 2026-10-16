/* fastseal.c - seal1995.py's arrays: which corners MAY lie on the inside of which edge (the filter, on every core), and since
   2026-10-16 the whole of seal1995's numpy (places, clusters, joints, the quads to cut; further down). fastseal.py loads it.
   seal1995 walked every edge of the built meshes in Python and measured, with numpy, every corner whose x lies within the edge's x range: 390 000
   edges, 6 s of an R1 build. Nearly none of those corners is anywhere near the edge. This file only THROWS AWAY the ones that are clearly not on
   it; what is left (a few thousand corners) is measured by seal1995's own lines as before, so every joint and every place along an edge is
   decided by the same expressions.
   A corner c is kept for edge (a, b) when it is neither end, its place along the edge t = (c - a) . (b - a) / |b - a|^2 lies between 0.99 e and
   1 - 0.99 e (e = tol / |b - a| ; seal1995 asks e < t < 1 - e) and its distance from the line is under 1.01 tol (seal1995: under tol). The
   margins of 1 % are a million times any rounding of these numbers.
     U[nu * 3] the places ; E[ne * 2] the edges ; xo[nx] corners in the order of their x ; i0 / i1[ne] the part of xo to look at per edge
     (seal1995's own searchsorted) ; an edge with i1 - i0 <= 2 or shorter than 2 tol x 0.999 has none.
   seal_count -> cnt[ne] ; seal_fill writes them at off[e] (the running sum of cnt), in the order of xo. */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <omp.h>
#define EXPORT __declspec(dllexport)
typedef long long i64;

static inline i64 scan(const double *U, const i64 *E, const i64 *xo, const i64 *i0, const i64 *i1, i64 e, double tol, i64 *out)
{
    i64 a = E[2 * e], b = E[2 * e + 1], n = 0;
    if (i1[e] - i0[e] <= 2) return 0;
    const double *A = U + 3 * a, *B = U + 3 * b; double ab[3] = { B[0] - A[0], B[1] - A[1], B[2] - A[2] }, L2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2];
    if (L2 < 4.0 * tol * tol * 0.999) return 0;
    double ee = 0.99 * tol / sqrt(L2), lim = 1.01 * tol * 1.01 * tol;
    for (i64 k = i0[e]; k < i1[e]; k++) {
        i64 c = xo[k]; if (c == a || c == b) continue;
        const double *C = U + 3 * c; double q[3] = { C[0] - A[0], C[1] - A[1], C[2] - A[2] }, t = (q[0] * ab[0] + q[1] * ab[1] + q[2] * ab[2]) / L2;
        if (!(t > ee && t < 1.0 - ee)) continue;
        double r[3] = { q[0] - t * ab[0], q[1] - t * ab[1], q[2] - t * ab[2] };
        if (!(r[0] * r[0] + r[1] * r[1] + r[2] * r[2] < lim)) continue;
        if (out) out[n] = c;
        n++;
    }
    return n;
}
EXPORT void seal_count(const double *U, const i64 *E, i64 ne, const i64 *xo, const i64 *i0, const i64 *i1, double tol, i64 *cnt)
{
    #pragma omp parallel for schedule(dynamic, 1024)
    for (i64 e = 0; e < ne; e++) cnt[e] = scan(U, E, xo, i0, i1, e, tol, 0);
}
EXPORT void seal_fill(const double *U, const i64 *E, i64 ne, const i64 *xo, const i64 *i0, const i64 *i1, double tol, const i64 *cnt, const i64 *off, i64 *out)
{
    #pragma omp parallel for schedule(dynamic, 1024)
    for (i64 e = 0; e < ne; e++) if (cnt[e]) scan(U, E, xo, i0, i1, e, tol, out + off[e]);
}

/* ================================================================ seal1995.seal's numpy steps on buffers (2026-10-16, kb 31)
   The unit is built with -ffp-contract=off since then (cbuild): these give seal1995's own numbers; the filter above keeps its 1 %
   margins either way. seal1995.py calls them in this order and quotes the numpy each one replaced. */
/* the corners' places in and out of the meshes' 48-byte vertex records (meshgen.VTX: position f4 x 4 first) */
EXPORT void seal_gather(i64 nv, const unsigned char *V, float *P) { for (i64 v = 0; v < nv; v++) memcpy(P + 3 * v, V + 48 * v, 12); }
EXPORT void seal_scatter(i64 nv, unsigned char *V, const float *P, const i64 *first, const i64 *cid) { for (i64 v = 0; v < nv; v++) memcpy(V + 48 * v, P + 3 * first[cid[v]], 12); }
EXPORT void seal_places(i64 nu, const float *P, const i64 *first, double *U) { for (i64 u = 0; u < nu; u++) for (int c = 0; c < 3; c++) U[3 * u + c] = (double)P[3 * first[u] + c]; }
typedef int (*cmp_t)(i64, i64, const void *);
static void msort(i64 *a, i64 n, cmp_t cmp, const void *ctx)
{   /* stable merge sort of the index array a (numpy's kind='mergesort' / 'stable') */
    i64 *t = (i64 *)malloc(sizeof(i64) * (n > 0 ? n : 1));
    for (i64 w = 1; w < n; w *= 2) {
        for (i64 lo = 0; lo < n; lo += 2 * w) {
            i64 mid = lo + w < n ? lo + w : n, hi = lo + 2 * w < n ? lo + 2 * w : n, i = lo, j = mid, k = lo;
            while (i < mid && j < hi) t[k++] = cmp(a[j], a[i], ctx) < 0 ? a[j++] : a[i++];
            while (i < mid) t[k++] = a[i++];
            while (j < hi) t[k++] = a[j++];
        }
        memcpy(a, t, sizeof(i64) * n);
    }
    free(t);
}
static int cmp12(i64 a, i64 b, const void *ctx) { const unsigned char *P = (const unsigned char *)ctx; return memcmp(P + 12 * a, P + 12 * b, 12); }
/* allp = <the corners' float32 x, y, z> + np.float32(0.0) (a -0.0 becomes 0.0, here in place);
   np.unique(<its 12-byte rows as void>, return_index, return_inverse, return_counts): numpy sorts void rows by their bytes (memcmp),
   stable, so `first` is the first row of each place in the input order. -> the number of places */
EXPORT i64 seal_unique(i64 n, float *P, i64 *inv, i64 *first, i64 *cnt)
{
    for (i64 i = 0; i < 3 * n; i++) P[i] = P[i] + 0.0f;
    i64 *o = (i64 *)malloc(sizeof(i64) * (n > 0 ? n : 1)), nu = 0;
    for (i64 i = 0; i < n; i++) o[i] = i;
    msort(o, n, cmp12, P);
    for (i64 k = 0; k < n; k++) {
        if (k == 0 || memcmp(P + 3 * o[k], P + 3 * o[k - 1], 12)) { first[nu] = o[k]; cnt[nu] = 0; nu++; }
        inv[o[k]] = nu - 1; cnt[nu - 1]++;
    }
    free(o); return nu;
}
typedef struct { const i64 *K; } kctx;
static int cmpk(i64 a, i64 b, const void *ctx)
{
    const i64 *K = ((const kctx *)ctx)->K;
    for (int c = 0; c < 3; c++) { if (K[3 * a + c] != K[3 * b + c]) return K[3 * a + c] < K[3 * b + c] ? -1 : 1; }
    return 0;
}
static i64 findp(i64 *par, i64 x) { while (par[x] != x) { par[x] = par[par[x]]; x = par[x]; } return x; }
/* _clusters(U, tol): places closer than tol, through a chain too, share a label: the lowest number among them (the union keeps the
   lower root, so the label does not depend on the order of the pairs). Cells of tol a side, K = np.floor(U / tol).astype(np.int64);
   each place against its own cell and the 13 cells 'after' it; a pair when ((U[i] - U[j]) ** 2).sum(1) < tol * tol = (dx dx + dy dy) + dz dz */
EXPORT void seal_clusters(i64 nu, const double *U, double tol, i64 *lab)
{
    i64 *K = (i64 *)malloc(sizeof(i64) * 3 * (nu > 0 ? nu : 1)), *o = (i64 *)malloc(sizeof(i64) * (nu > 0 ? nu : 1)); double t2 = tol * tol;
    for (i64 i = 0; i < 3 * nu; i++) K[i] = (i64)floor(U[i] / tol);
    for (i64 i = 0; i < nu; i++) { o[i] = i; lab[i] = i; }
    kctx cx = { K }; msort(o, nu, cmpk, &cx);
    static const int OFF[14][3] = { {0,0,0}, {0,0,1}, {0,1,-1}, {0,1,0}, {0,1,1}, {1,-1,-1}, {1,-1,0}, {1,-1,1}, {1,0,-1}, {1,0,0}, {1,0,1}, {1,1,-1}, {1,1,0}, {1,1,1} };
    for (i64 i = 0; i < nu; i++) {
        for (int q = 0; q < 14; q++) {
            i64 tg[3] = { K[3 * i] + OFF[q][0], K[3 * i + 1] + OFF[q][1], K[3 * i + 2] + OFF[q][2] }, lo = 0, hi = nu;
            while (lo < hi) { i64 m = (lo + hi) / 2, *k = K + 3 * o[m]; int c = (k[0] != tg[0]) ? (k[0] < tg[0] ? -1 : 1) : (k[1] != tg[1]) ? (k[1] < tg[1] ? -1 : 1) : (k[2] != tg[2]) ? (k[2] < tg[2] ? -1 : 1) : 0; if (c < 0) lo = m + 1; else hi = m; }
            for (i64 s = lo; s < nu; s++) {
                i64 j = o[s], *k = K + 3 * j;
                if (k[0] != tg[0] || k[1] != tg[1] || k[2] != tg[2]) break;
                if (j == i) continue;
                double dx = U[3 * i] - U[3 * j], dy = U[3 * i + 1] - U[3 * j + 1], dz = U[3 * i + 2] - U[3 * j + 2];
                if ((dx * dx + dy * dy) + dz * dz < t2) { i64 a = findp(lab, i), b = findp(lab, j); if (a != b) { if (a < b) lab[b] = a; else lab[a] = b; } }
            }
        }
    }
    for (i64 i = 0; i < nu; i++) lab[i] = findp(lab, i);
    free(K); free(o);
}
/* order = np.lexsort((np.arange(nu), -cnt, lab)); the head of each label = the place most vertices have (the lowest number of equals):
   rep[u] = that place of u's label. Then per vertex cid = rep[inv]; -> moved = (cid != inv).sum() */
EXPORT i64 seal_reps(i64 nu, const i64 *lab, const i64 *cnt, i64 *rep, i64 nv, const i64 *inv, i64 *cid)
{
    i64 *best = (i64 *)malloc(sizeof(i64) * (nu > 0 ? nu : 1)), moved = 0;
    for (i64 u = 0; u < nu; u++) best[u] = -1;
    for (i64 u = 0; u < nu; u++) { i64 l = lab[u]; if (best[l] < 0 || cnt[u] > cnt[best[l]]) best[l] = u; }
    for (i64 u = 0; u < nu; u++) rep[u] = best[lab[u]];
    for (i64 v = 0; v < nv; v++) { cid[v] = rep[inv[v]]; moved += cid[v] != inv[v]; }
    free(best); return moved;
}
static int cmpe(i64 a, i64 b, const void *ctx) { const i64 *E = (const i64 *)ctx; return E[2 * a] != E[2 * b] ? (E[2 * a] < E[2 * b] ? -1 : 1) : E[2 * a + 1] != E[2 * b + 1] ? (E[2 * a + 1] < E[2 * b + 1] ? -1 : 1) : 0; }
static int cmpx(i64 a, i64 b, const void *ctx) { const double *U = (const double *)ctx; return U[3 * a] < U[3 * b] ? -1 : (U[3 * a] > U[3 * b] ? 1 : 0); }
/* The meshes' triangles in place numbers: per mesh the quads of its strip, s = np.concatenate([idx, [0, 0]]).reshape(-1, 6)[:, :4],
   triangles c[s[:, [0, 1, 2]]] and c[s[:, [2, 1, 3]]] (c = the mesh's cid), those with two equal corners dropped. Edges: each side
   sorted, np.unique(axis=0). used = np.unique(T); xo = used[np.argsort(U[used, 0], kind='stable')]; per edge i0 / i1 =
   np.searchsorted(xs, min(x_a, x_b) - tol) / (max + tol). Then every edge's joints: the filter above, then seal1995's own test:
     ab = U[b] - A; L2 = ab @ ab = (ab0 ab0 + ab2 ab2) + ab1 ab1 (a fresh 3-vector: OpenBLAS's order); skip when L2 < 4 * tol * tol
     t = (Q @ ab) / L2 = (0 + ((q0 ab0 + q2 ab2) + q1 ab1)) / L2 ; e = tol / sqrt(L2) ; e < t < 1 - e
     d = np.linalg.norm(Q - t * ab, axis=1) = sqrt((r0 r0 + r1 r1) + r2 r2) < tol
   meshes: nm, per mesh its indices idx[ioff[m] .. ioff[m + 1]) and its vertices' cid from voff[m]. Output: ne and the edges (E, 2 x ne),
   the joints sorted per edge by (t, place): jn joints as je (edge), jt, jv. Call with E = NULL to get ne and jn (counts) first. */
static i64 *g_E = 0, g_ne = 0, *g_je = 0, *g_jv = 0, g_jn = 0; static double *g_jt = 0;
EXPORT i64 seal_joints(i64 nu, const double *U, double tol, i64 nm, const unsigned short *idx, const i64 *ioff, const i64 *cid, const i64 *voff, i64 *counts)
{
    free(g_E); free(g_je); free(g_jv); free(g_jt); g_E = g_je = g_jv = 0; g_jt = 0; g_ne = g_jn = 0;
    i64 nt = 0;
    for (i64 m = 0; m < nm; m++) nt += 2 * ((ioff[m + 1] - ioff[m] + 2) / 6);
    i64 *T = (i64 *)malloc(sizeof(i64) * 3 * (nt > 0 ? nt : 1)), k = 0;
    for (i64 m = 0; m < nm; m++) {                                     /* all first triangles of a mesh, then all its second ones */
        const unsigned short *s = idx + ioff[m]; const i64 *c = cid + voff[m]; i64 nq = (ioff[m + 1] - ioff[m] + 2) / 6;
        for (int h = 0; h < 2; h++)
            for (i64 q = 0; q < nq; q++) {
                const unsigned short *r = s + 6 * q; i64 a = c[h ? r[2] : r[0]], b = c[r[1]], d = c[h ? r[3] : r[2]];
                if (a != b && b != d && a != d) { T[3 * k] = a; T[3 * k + 1] = b; T[3 * k + 2] = d; k++; }
            }
    }
    nt = k;
    i64 *E0 = (i64 *)malloc(sizeof(i64) * 6 * (nt > 0 ? nt : 1)), *eo = (i64 *)malloc(sizeof(i64) * 3 * (nt > 0 ? nt : 1));
    for (i64 t = 0; t < nt; t++)
        for (int s = 0; s < 3; s++) { i64 a = T[3 * t + s], b = T[3 * t + (s + 1) % 3]; E0[2 * (3 * t + s)] = a < b ? a : b; E0[2 * (3 * t + s) + 1] = a < b ? b : a; eo[3 * t + s] = 3 * t + s; }
    msort(eo, 3 * nt, cmpe, E0);
    i64 ne = 0; g_E = (i64 *)malloc(sizeof(i64) * 6 * (nt > 0 ? nt : 1));
    for (i64 q = 0; q < 3 * nt; q++) { i64 *e = E0 + 2 * eo[q]; if (!ne || e[0] != g_E[2 * ne - 2] || e[1] != g_E[2 * ne - 1]) { g_E[2 * ne] = e[0]; g_E[2 * ne + 1] = e[1]; ne++; } }
    free(E0); free(eo);
    unsigned char *isu = (unsigned char *)calloc(nu > 0 ? nu : 1, 1); i64 nx = 0;
    for (i64 q = 0; q < 3 * nt; q++) isu[T[q]] = 1;
    i64 *xo = (i64 *)malloc(sizeof(i64) * (nu > 0 ? nu : 1));
    for (i64 u = 0; u < nu; u++) if (isu[u]) xo[nx++] = u;
    free(isu); free(T); msort(xo, nx, cmpx, U);
    double *xs = (double *)malloc(sizeof(double) * (nx > 0 ? nx : 1));
    for (i64 q = 0; q < nx; q++) xs[q] = U[3 * xo[q]];
    i64 *i0 = (i64 *)malloc(sizeof(i64) * (ne > 0 ? ne : 1)), *i1 = (i64 *)malloc(sizeof(i64) * (ne > 0 ? ne : 1)), *cnt = (i64 *)malloc(sizeof(i64) * (ne > 0 ? ne : 1));
    for (i64 e = 0; e < ne; e++) {
        double xa = U[3 * g_E[2 * e]], xb = U[3 * g_E[2 * e + 1]], lo = (xa < xb ? xa : xb) - tol, hi = (xa > xb ? xa : xb) + tol; i64 l = 0, h = nx;
        while (l < h) { i64 m = (l + h) / 2; if (xs[m] < lo) l = m + 1; else h = m; }
        i0[e] = l; l = 0; h = nx;
        while (l < h) { i64 m = (l + h) / 2; if (xs[m] < hi) l = m + 1; else h = m; }
        i1[e] = l;
    }
    free(xs);
    seal_count(U, g_E, ne, xo, i0, i1, tol, cnt);
    i64 *off = (i64 *)malloc(sizeof(i64) * (ne + 1)); off[0] = 0;
    for (i64 e = 0; e < ne; e++) off[e + 1] = off[e] + cnt[e];
    i64 *cand = (i64 *)malloc(sizeof(i64) * (off[ne] > 0 ? off[ne] : 1));
    seal_fill(U, g_E, ne, xo, i0, i1, tol, cnt, off, cand);
    g_je = (i64 *)malloc(sizeof(i64) * (off[ne] > 0 ? off[ne] : 1)); g_jv = (i64 *)malloc(sizeof(i64) * (off[ne] > 0 ? off[ne] : 1)); g_jt = (double *)malloc(sizeof(double) * (off[ne] > 0 ? off[ne] : 1));
    i64 jn = 0;
    for (i64 e = 0; e < ne; e++) {
        if (!cnt[e]) continue;
        i64 a = g_E[2 * e], b = g_E[2 * e + 1]; const double *A = U + 3 * a, *B = U + 3 * b; double ab[3] = { B[0] - A[0], B[1] - A[1], B[2] - A[2] };
        double L2 = (ab[0] * ab[0] + ab[2] * ab[2]) + ab[1] * ab[1];
        if (L2 < 4 * tol * tol) continue;
        double ee = tol / sqrt(L2); i64 j0 = jn;
        for (i64 q = off[e]; q < off[e + 1]; q++) {
            i64 v = cand[q]; const double *C = U + 3 * v; double Q[3] = { C[0] - A[0], C[1] - A[1], C[2] - A[2] };
            double t = (0.0 + ((Q[0] * ab[0] + Q[2] * ab[2]) + Q[1] * ab[1])) / L2;
            if (!(t > ee && t < 1 - ee)) continue;
            double r0 = Q[0] - t * ab[0], r1 = Q[1] - t * ab[1], r2 = Q[2] - t * ab[2], d = sqrt((r0 * r0 + r1 * r1) + r2 * r2);
            if (!(d < tol) || v == a || v == b) continue;
            i64 p = jn++;                                              /* sorted((t, v)): insertion, a few per edge */
            while (p > j0 && (g_jt[p - 1] > t || (g_jt[p - 1] == t && g_jv[p - 1] > v))) { g_jt[p] = g_jt[p - 1]; g_jv[p] = g_jv[p - 1]; g_je[p] = g_je[p - 1]; p--; }
            g_jt[p] = t; g_jv[p] = v; g_je[p] = e;
        }
    }
    free(i0); free(i1); free(cnt); free(off); free(cand); free(xo);
    g_ne = ne; g_jn = jn; counts[0] = ne; counts[1] = jn; return 0;
}
EXPORT void seal_joints_get(i64 *E, i64 *je, double *jt, i64 *jv)
{
    if (E) memcpy(E, g_E, sizeof(i64) * 2 * g_ne);
    if (g_jn) { memcpy(je, g_je, sizeof(i64) * g_jn); memcpy(jt, g_jt, sizeof(double) * g_jn); memcpy(jv, g_jv, sizeof(i64) * g_jn); }
    free(g_E); free(g_je); free(g_jv); free(g_jt); g_E = g_je = g_jv = 0; g_jt = 0; g_ne = g_jn = 0;
}
/* seal's new corners (2026-10-16; was newvert, struct by struct in Python): corner e = nv0 + e lies at place v[e] on the edge from corner
   p[e] to corner r[e] (either an old one, in Vk, or a new one made before it, in out), at t[e] along it.  Its 48-byte record (seal1995.py,
   the numpy lines it replaced):
     w['p'][:3] = U32[v]; w['p'][3] = a['p'][3]
     n, t: x = a * (1 - t) + b * t in float64; l = np.linalg.norm(x) of a fresh 3-vector = sqrt((x0 x0 + x2 x2) + x1 x1) (OpenBLAS's ddot,
           npexact.ddot); (x / l if l > 1e-9 else a) as float32
     uv0 (int16): np.clip(np.round(a * (1 - t) + b * t), -32768, 32767) ; uv1 (uint16): the same, 0 .. 65535 (np.round: half to even, rint)
   U32 = the places as float32 (12 bytes each), first[v] the first vertex at place v. */
static double clipd(double x, double lo, double hi) { double m = lo > x ? lo : x; return hi < m ? hi : m; }      /* min(max(x, lo), hi) as Python takes them */
EXPORT void seal_newverts(i64 nv0, const unsigned char *Vk, i64 n, const i64 *pp, const i64 *rr, const double *tt, const i64 *vv, const unsigned char *U32, const i64 *first, unsigned char *out)
{
    for (i64 e = 0; e < n; e++) {
        const unsigned char *a = pp[e] < nv0 ? Vk + 48 * pp[e] : out + 48 * (pp[e] - nv0), *b = rr[e] < nv0 ? Vk + 48 * rr[e] : out + 48 * (rr[e] - nv0);
        unsigned char *w = out + 48 * e; double t = tt[e], u = 1.0 - t;
        memcpy(w, U32 + 12 * first[vv[e]], 12); memcpy(w + 12, a + 12, 4);
        for (int o = 16; o <= 28; o += 12) {
            float xa[3], xb[3]; memcpy(xa, a + o, 12); memcpy(xb, b + o, 12);
            double x[3]; for (int c = 0; c < 3; c++) x[c] = (double)xa[c] * u + (double)xb[c] * t;
            double l = sqrt((x[0] * x[0] + x[2] * x[2]) + x[1] * x[1]); float f[3];
            for (int c = 0; c < 3; c++) f[c] = l > 1e-9 ? (float)(x[c] / l) : xa[c];
            memcpy(w + o, f, 12);
        }
        short ua[2], ub[2], uw[2]; memcpy(ua, a + 40, 4); memcpy(ub, b + 40, 4);
        for (int c = 0; c < 2; c++) uw[c] = (short)clipd(rint((double)ua[c] * u + (double)ub[c] * t), -32768.0, 32767.0);
        memcpy(w + 40, uw, 4);
        unsigned short va[2], vb[2], vw[2]; memcpy(va, a + 44, 4); memcpy(vb, b + 44, 4);
        for (int c = 0; c < 2; c++) vw[c] = (unsigned short)clipd(rint((double)va[c] * u + (double)vb[c] * t), 0.0, 65535.0);
        memcpy(w + 44, vw, 4);
    }
}
/* the quads to cut: any of the sides (0,1) (1,2) (2,0) (1,3) (3,2) of c4 = cid[s] that is a joint edge (np.isin(lo * nu + hi, Jk) &
   (lo != hi)); Jk sorted. flag[quad] per mesh, quads numbered on from qoff[m] */
EXPORT void seal_flags(i64 nu, const i64 *Jk, i64 nk, i64 nm, const unsigned short *idx, const i64 *ioff, const i64 *cid, const i64 *voff, const i64 *qoff, unsigned char *flag)
{
    static const int S[5][2] = { {0, 1}, {1, 2}, {2, 0}, {1, 3}, {3, 2} };
    for (i64 m = 0; m < nm; m++) {
        const unsigned short *s = idx + ioff[m]; const i64 *c = cid + voff[m]; i64 nq = (ioff[m + 1] - ioff[m] + 2) / 6;
        for (i64 q = 0; q < nq; q++) {
            const unsigned short *r = s + 6 * q; unsigned char f = 0;
            for (int k = 0; k < 5 && !f; k++) {
                i64 x = c[r[S[k][0]]], y = c[r[S[k][1]]], lo = x < y ? x : y, hi = x < y ? y : x, code = lo * nu + hi, l = 0, h = nk;
                if (lo == hi) continue;
                while (l < h) { i64 mm = (l + h) / 2; if (Jk[mm] < code) l = mm + 1; else h = mm; }
                f = l < nk && Jk[l] == code;
            }
            flag[qoff[m] + q] = f;
        }
    }
}
