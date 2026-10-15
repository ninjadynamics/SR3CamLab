/* fastgeo.c - the importer's per-polygon loops in C (fastgeo.py loads it; compiled on first use like rays.c).
   Every function here is a line-for-line port of a Python function of the importer and must give the SAME numbers:
   compile with -ffp-contract=off (no fused multiply-add) and never with -ffast-math. The sums run in the order the
   Python code (or numpy) adds them.
     fg_prep        overlay_bake._newell / fill1995._normal for every polygon + centre + box
     fg_far         overlay_bake.find_pairs: largest distance of every polygon from the road (capped)
     fg_pairs       overlay_bake.find_pairs: the grid, the candidate tests, the overlap in the plane
     fg_index_*     fill1995.Index: lying triangles and upright plan segments in a grid, heights(), uprights()
     fg_lying_*     gapfill_weld.Lying: lying polygons in a 4 m grid, near()
     fg_mindist2    smallest squared plan distance of points from a set of points
   polygons: X = corners (3 doubles each), off[i] .. off[i + 1] = the corners of polygon i. */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <omp.h>
#define EXPORT __declspec(dllexport)
typedef long long i64;
#define MAXC 96

EXPORT int fg_threads(void) { return omp_get_max_threads(); }

/* Python's  x ** 0.5  is the C runtime's pow(x, 0.5), which is not sqrt(x) to the last bit (2 in 1000 differ). The importer's normals are made
   with ** 0.5, so the same pow is used here: the one of ucrtbase.dll, the runtime python.exe uses. fg_init() looks it up; without it, sqrt. */
#include <windows.h>
#undef far
#undef near
typedef double (*pow_t)(double, double);
static pow_t upow = NULL;
EXPORT int fg_init(void)
{
    HMODULE h = GetModuleHandleA("ucrtbase.dll");
    if (h) upow = (pow_t)(void *)GetProcAddress(h, "pow");
    return upow != NULL;
}
static inline double root(double x) { return upow ? upow(x, 0.5) : sqrt(x); }
static inline double sqr(double x) { return upow ? upow(x, 2.0) : x * x; }      /* Python's  x ** 2  (not x * x to the last bit either) */

/* ------------------------------------------------------------------ per polygon numbers */
EXPORT void fg_prep(const double *X, const i64 *off, i64 n, double *nr, double *ar, double *cen, double *lo, double *hi)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        const double *P = X + 3 * off[i]; int k = (int)(off[i + 1] - off[i]); double x = 0.0, y = 0.0, z = 0.0;
        if (k > 0) {
            const double *a = P + 3 * (k - 1);
            for (int q = 0; q < k; q++) { const double *b = P + 3 * q; x += a[1] * b[2] - a[2] * b[1]; y += a[2] * b[0] - a[0] * b[2]; z += a[0] * b[1] - a[1] * b[0]; a = b; }
        }
        double l = root(x * x + y * y + z * z);
        if (l > 1e-12) { nr[3 * i] = x / l; nr[3 * i + 1] = y / l; nr[3 * i + 2] = z / l; } else { nr[3 * i] = x; nr[3 * i + 1] = y; nr[3 * i + 2] = z; }
        if (ar) ar[i] = 0.5 * l;
        if (k > 0) {
            double s0 = P[0], s1 = P[1], s2 = P[2], l0 = P[0], l1 = P[1], l2 = P[2], h0 = P[0], h1 = P[1], h2 = P[2];
            for (int q = 1; q < k; q++) {
                const double *b = P + 3 * q; s0 += b[0]; s1 += b[1]; s2 += b[2];
                if (b[0] < l0) l0 = b[0]; if (b[1] < l1) l1 = b[1]; if (b[2] < l2) l2 = b[2];
                if (b[0] > h0) h0 = b[0]; if (b[1] > h1) h1 = b[1]; if (b[2] > h2) h2 = b[2];
            }
            if (cen) { cen[3 * i] = s0 / k; cen[3 * i + 1] = s1 / k; cen[3 * i + 2] = s2 / k; }
            if (lo) { lo[3 * i] = l0; lo[3 * i + 1] = l1; lo[3 * i + 2] = l2; }
            if (hi) { hi[3 * i] = h0; hi[3 * i + 1] = h1; hi[3 * i + 2] = h2; }
        }
    }
}

/* far[i] = min(largest plan distance of centre i from the road points, maxview) */
EXPORT void fg_far(const double *cen, i64 n, const double *road, i64 m, double maxview, double *far)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        double cx = cen[3 * i], cz = cen[3 * i + 2], best = -1.0;
        for (i64 j = 0; j < m; j++) { double dx = cx - road[2 * j], dz = cz - road[2 * j + 1], d = dx * dx + dz * dz; if (d > best) best = d; }
        best = sqrt(best); far[i] = best < maxview ? best : maxview;
    }
}

/* out[i] = smallest squared plan distance of point i (x, z) from the points R (x, z):  ((R - p) ** 2).sum(1).min() */
EXPORT void fg_mindist2(const double *P, i64 n, const double *R, i64 m, double *out)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        double px = P[2 * i], pz = P[2 * i + 1], best = INFINITY;
        for (i64 j = 0; j < m; j++) { double dx = R[2 * j] - px, dz = R[2 * j + 1] - pz, d = dx * dx + dz * dz; if (d < best) best = d; }
        out[i] = best;
    }
}

/* connected groups: items that share a node belong together. m pairs (item[q], node[q]) -> label[i] = one item of the group of item i */
static i64 uf_find(i64 *par, i64 x) { while (par[x] != x) { par[x] = par[par[x]]; x = par[x]; } return x; }
EXPORT int fg_components(i64 nitem, const i64 *item, const i64 *node, i64 m, i64 nnode, i64 *label)
{
    i64 *first = malloc(sizeof(i64) * (nnode + 1)); if (!first) return -1;
    for (i64 i = 0; i < nnode; i++) first[i] = -1;
    for (i64 i = 0; i < nitem; i++) label[i] = i;
    for (i64 q = 0; q < m; q++) {
        i64 f = item[q], v = node[q];
        if (first[v] < 0) first[v] = f; else { i64 a = uf_find(label, f), b = uf_find(label, first[v]); if (a != b) { if (a < b) label[b] = a; else label[a] = b; } }
    }
    for (i64 i = 0; i < nitem; i++) label[i] = uf_find(label, i);
    free(first); return 0;
}

/* ------------------------------------------------------------------ plane polygons (overlay_bake) */
static double np_sum(const double *b, int m)                           /* numpy's np.sum of a short 1-D array (its pairwise sum; checked against numpy 1.24 for 3 .. 20 numbers) */
{
    double res;
    if (m < 8) { res = 0.0; for (int i = 0; i < m; i++) res += b[i]; }
    else {
        double r[8]; int i;
        for (i = 0; i < 8; i++) r[i] = b[i];
        for (i = 8; i < m - (m % 8); i += 8) for (int q = 0; q < 8; q++) r[q] += b[i + q];
        res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < m; i++) res += b[i];
    }
    return res;
}
static double area2(const double *Q, int n)                           /* overlay_bake._area */
{
    double t[MAXC];
    for (int i = 0; i < n; i++) { int j = (i + 1) % n; t[i] = Q[2 * i] * Q[2 * j + 1] - Q[2 * j] * Q[2 * i + 1]; }
    return 0.5 * np_sum(t, n);
}
static int ccw2(double *Q, int n)                                     /* overlay_bake._ccw, in place */
{
    if (!(area2(Q, n) >= 0)) for (int i = 0, j = n - 1; i < j; i++, j--) { double x = Q[2 * i], y = Q[2 * i + 1]; Q[2 * i] = Q[2 * j]; Q[2 * i + 1] = Q[2 * j + 1]; Q[2 * j] = x; Q[2 * j + 1] = y; }
    return n;
}
static int clip2(const double *Q, int n, const double *a, const double *b, double *out, int *err)      /* overlay_bake._clip, inside=True */
{
    if (n < 3) return 0;
    double ex = b[0] - a[0], ey = b[1] - a[1], s[MAXC]; int m = 0;
    for (int i = 0; i < n; i++) s[i] = -((Q[2 * i] - a[0]) * ey - (Q[2 * i + 1] - a[1]) * ex);
    for (int i = 0; i < n; i++) {
        int j = (i + 1) % n;
        if (m > MAXC - 3) { *err = 1; return 0; }
        if (s[i] >= 0) { out[2 * m] = Q[2 * i]; out[2 * m + 1] = Q[2 * i + 1]; m++; }
        if ((s[i] > 0 && s[j] < 0) || (s[i] < 0 && s[j] > 0)) { double t = s[i] / (s[i] - s[j]); out[2 * m] = Q[2 * i] + (Q[2 * j] - Q[2 * i]) * t; out[2 * m + 1] = Q[2 * i + 1] + (Q[2 * j + 1] - Q[2 * i + 1]) * t; m++; }
    }
    return m >= 3 ? m : 0;
}
static int tidy2(const double *Q, int n, double *out)                 /* overlay_bake._tidy, tol 1e-4 */
{
    const double tol = 1e-4; int m = 1;
    if (n < 3) return 0;
    out[0] = Q[0]; out[1] = Q[1];
    for (int i = 1; i < n; i++) {
        double dx = fabs(Q[2 * i] - out[2 * m - 2]), dy = fabs(Q[2 * i + 1] - out[2 * m - 1]);
        if ((dx > dy ? dx : dy) > tol) { out[2 * m] = Q[2 * i]; out[2 * m + 1] = Q[2 * i + 1]; m++; }
    }
    if (m > 1) { double dx = fabs(out[0] - out[2 * m - 2]), dy = fabs(out[1] - out[2 * m - 1]); if ((dx > dy ? dx : dy) <= tol) m--; }
    return m >= 3 ? m : 0;
}
static int inter2(const double *A, int na, const double *B, int nb, double *c, int *err)      /* overlay_bake._inter */
{
    double t[2 * MAXC]; int n = na; memcpy(c, A, sizeof(double) * 2 * na);
    for (int k = 0; k < nb; k++) {
        int m = clip2(c, n, B + 2 * k, B + 2 * ((k + 1) % nb), t, err); n = tidy2(t, m, c);
        if (!n) break;
    }
    return n;
}
static void basis3(const double *P, int k, const double *n, double *o, double *u, double *w)      /* overlay_bake._basis (n = _newell(P)[0]) */
{
    int best = 0; double bl = -1.0;
    for (int q = 0; q < k; q++) { const double *a = P + 3 * q, *b = P + 3 * ((q + 1) % k); double dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2], l = dx * dx + dy * dy + dz * dz; if (l > bl) { bl = l; best = q; } }
    const double *a = P + 3 * best, *b = P + 3 * ((best + 1) % k);
    u[0] = b[0] - a[0]; u[1] = b[1] - a[1]; u[2] = b[2] - a[2];
    /* THE ORDER OF ADDING IN A DOT PRODUCT.  The Python original computes u @ n, norm(u), d @ u, (p - c) @ n with numpy's @, which goes through
       BLAS; for three numbers in a freshly made array BLAS adds (x + z) + y, not (x + y) + z.  Written the second way (as this port was
       until 2026-10-08) the gap / need / overlap of 342 of 1005 pairs of a Mountain build differed from the original's in the last bits
       (SR3_FASTGEO_CHECK did not show it: it compares them to 1e-9).  Written the BLAS way all 1005 are the original's bit for bit. */
    double un = (u[0] * n[0] + u[2] * n[2]) + u[1] * n[1];
    u[0] -= n[0] * un; u[1] -= n[1] * un; u[2] -= n[2] * un;
    double l = sqrt((u[0] * u[0] + u[2] * u[2]) + u[1] * u[1]); if (l < 1e-12) l = 1e-12;
    u[0] /= l; u[1] /= l; u[2] /= l;
    double s0 = P[0], s1 = P[1], s2 = P[2];
    for (int q = 1; q < k; q++) { s0 += P[3 * q]; s1 += P[3 * q + 1]; s2 += P[3 * q + 2]; }
    o[0] = s0 / k; o[1] = s1 / k; o[2] = s2 / k;
    w[0] = n[1] * u[2] - n[2] * u[1]; w[1] = n[2] * u[0] - n[0] * u[2]; w[2] = n[0] * u[1] - n[1] * u[0];
}
static void to2(const double *P, int k, const double *o, const double *u, const double *w, double *Q)
{
    for (int q = 0; q < k; q++) { double d0 = P[3 * q] - o[0], d1 = P[3 * q + 1] - o[1], d2 = P[3 * q + 2] - o[2]; Q[2 * q] = (d0 * u[0] + d2 * u[2]) + d1 * u[1]; Q[2 * q + 1] = (d0 * w[0] + d2 * w[2]) + d1 * w[1]; }      /* ((x + z) + y: see basis3) */
}

typedef struct { i64 key; i64 i, j; double gap, spread, need, ov; } rec_t;
static rec_t *g_rec = NULL; static i64 g_nrec = 0;
static int rec_cmp(const void *a, const void *b)
{
    const rec_t *p = a, *q = b;
    if (p->key != q->key) return p->key < q->key ? -1 : 1;
    if (p->i != q->i) return p->i < q->i ? -1 : 1;
    if (p->j != q->j) return p->j < q->j ? -1 : 1;
    return 0;
}
typedef struct { const double *X; const i64 *off; const double *nr, *ar, *cen, *lo3, *hi3, *need0, *far; const unsigned char *sg, *act; double margin, floor_, kdepth, focal, pixels; } pctx;

static int pair_test(const pctx *c, i64 i, i64 j, rec_t *r, int *err)
{
    const double *ni = c->nr + 3 * i, *nj = c->nr + 3 * j;
    double dn = (nj[0] * ni[0] + nj[2] * ni[2]) + nj[1] * ni[1];      /* ((x + z) + y in the three dot products here: see basis3) */
    if (!(fabs(dn) > 0.99939)) return 0;
    double g = (c->need0[i] > c->need0[j] ? c->need0[i] : c->need0[j]) + 0.02;
    for (int q = 0; q < 3; q++) if (c->lo3[3 * j + q] > c->hi3[3 * i + q] + g || c->lo3[3 * i + q] > c->hi3[3 * j + q] + g) return 0;
    if (c->act && !c->act[i] && !c->act[j]) return 0;
    const double *pi = c->X + 3 * c->off[i], *pj = c->X + 3 * c->off[j]; int ki = (int)(c->off[i + 1] - c->off[i]), kj = (int)(c->off[j + 1] - c->off[j]);
    const double *ci = c->cen + 3 * i, *cj = c->cen + 3 * j; double damin = INFINITY, damax = -INFINITY, dbmin = INFINITY, dbmax = -INFINITY;
    for (int q = 0; q < kj; q++) { double d = fabs(((pj[3 * q] - ci[0]) * ni[0] + (pj[3 * q + 2] - ci[2]) * ni[2]) + (pj[3 * q + 1] - ci[1]) * ni[1]); if (d < damin) damin = d; if (d > damax) damax = d; }
    for (int q = 0; q < ki; q++) { double d = fabs(((pi[3 * q] - cj[0]) * nj[0] + (pi[3 * q + 2] - cj[2]) * nj[2]) + (pi[3 * q + 1] - cj[1]) * nj[1]); if (d < dbmin) dbmin = d; if (d > dbmax) dbmax = d; }
    double gap = damin > dbmin ? damin : dbmin, lim = c->need0[i] > c->need0[j] ? c->need0[i] : c->need0[j], th = lim * c->margin > c->floor_ ? lim * c->margin : c->floor_;
    if (gap >= th) return 0;
    if (c->sg[i] && c->sg[j] && dn < 0) return 0;
    double o[3], u[3], w[3], A[2 * MAXC], B[2 * MAXC], C[2 * MAXC];
    basis3(pi, ki, ni, o, u, w); to2(pi, ki, o, u, w, A); to2(pj, kj, o, u, w, B); ccw2(A, ki); ccw2(B, kj);
    int nc = inter2(A, ki, B, kj, C, err);
    if (!nc) return 0;
    double ov = area2(C, nc), ami = c->ar[i] < c->ar[j] ? c->ar[i] : c->ar[j], t2 = 0.01 * ami > 0.02 ? 0.01 * ami : 0.02;
    if (ov < t2) return 0;
    double fm = c->far[i] > c->far[j] ? c->far[i] : c->far[j], v = c->focal * sqrt(ov) / c->pixels, d = fm < v ? fm : v, need = c->kdepth * sqr(d);      /* (the original squares a numpy NUMBER with ** 2 = the C runtime's pow: 4 of 1005 pairs differed with d * d) */
    th = need * c->margin > c->floor_ ? need * c->margin : c->floor_;
    if (gap >= th) return 0;
    r->i = i; r->j = j; r->gap = gap; r->spread = damax > dbmax ? damax : dbmax; r->need = need; r->ov = ov; return 1;
}

/* -> number of pairs (fetch them with fg_pairs_get), -1 = out of memory, -2 = a polygon / the grid too big for this code (use the Python version)
   ing[i] = polygon i goes into the grid (area ok, not a skipped section) */
EXPORT i64 fg_pairs(const double *X, const i64 *off, i64 n, const double *nr, const double *ar, const double *cen, const double *lo3, const double *hi3,
                    const double *need0, const double *far, const unsigned char *sg, const unsigned char *act, const unsigned char *ing,
                    double cell, double margin, double floor_, double kdepth, double focal, double pixels)
{
    free(g_rec); g_rec = NULL; g_nrec = 0;
    if (n <= 0) return 0;
    int *cl = malloc(sizeof(int) * 4 * n); unsigned char *in = malloc(n);
    if (!cl || !in) { free(cl); free(in); return -1; }
    i64 x0 = 0, x1 = -1, z0 = 0, z1 = -1; int first = 1, bad = 0;
    for (i64 i = 0; i < n; i++) {
        in[i] = 0;
        if (off[i + 1] - off[i] > 24) bad = 1;
        if (!ing[i]) continue;
        i64 lx = (i64)floor(lo3[3 * i] / cell), lz = (i64)floor(lo3[3 * i + 2] / cell), hx = (i64)floor(hi3[3 * i] / cell), hz = (i64)floor(hi3[3 * i + 2] / cell);
        if (hx - lx > 40 || hz - lz > 40) continue;
        in[i] = 1; cl[4 * i] = (int)lx; cl[4 * i + 1] = (int)lz; cl[4 * i + 2] = (int)hx; cl[4 * i + 3] = (int)hz;
        if (first) { x0 = lx; x1 = hx; z0 = lz; z1 = hz; first = 0; }
        else { if (lx < x0) x0 = lx; if (hx > x1) x1 = hx; if (lz < z0) z0 = lz; if (hz > z1) z1 = hz; }
    }
    if (bad) { free(cl); free(in); return -2; }
    if (first) { free(cl); free(in); return 0; }
    i64 NX = x1 - x0 + 1, NZ = z1 - z0 + 1;
    if (NX * NZ > 40000000) { free(cl); free(in); return -2; }
    i64 *start = calloc(NX * NZ + 1, sizeof(i64));
    if (!start) { free(cl); free(in); return -1; }
    for (i64 i = 0; i < n; i++) if (in[i]) for (i64 x = cl[4 * i]; x <= cl[4 * i + 2]; x++) for (i64 z = cl[4 * i + 1]; z <= cl[4 * i + 3]; z++) start[(x - x0) * NZ + (z - z0) + 1]++;
    for (i64 q = 0; q < NX * NZ; q++) start[q + 1] += start[q];
    i64 tot = start[NX * NZ]; i64 *items = malloc(sizeof(i64) * (tot + 1)), *fill = malloc(sizeof(i64) * (NX * NZ + 1));
    if (!items || !fill) { free(cl); free(in); free(start); free(items); free(fill); return -1; }
    memcpy(fill, start, sizeof(i64) * (NX * NZ + 1));
    for (i64 i = 0; i < n; i++) if (in[i]) for (i64 x = cl[4 * i]; x <= cl[4 * i + 2]; x++) for (i64 z = cl[4 * i + 1]; z <= cl[4 * i + 3]; z++) items[fill[(x - x0) * NZ + (z - z0)]++] = i;
    free(fill);
    pctx c = { X, off, nr, ar, cen, lo3, hi3, need0, far, sg, act, margin, floor_, kdepth, focal, pixels };
    int nt = omp_get_max_threads(), fail = 0; rec_t **buf = calloc(nt, sizeof(rec_t *)); i64 *cnt = calloc(nt, sizeof(i64)), *cap = calloc(nt, sizeof(i64));
    #pragma omp parallel
    {
        int t = omp_get_thread_num(), err = 0;
        #pragma omp for schedule(dynamic, 16)
        for (i64 q = 0; q < NX * NZ; q++) {
            i64 a = start[q], b = start[q + 1];
            if (b - a < 2 || err) continue;
            i64 cx = q / NZ + x0, cz = q % NZ + z0;
            for (i64 s = a; s < b - 1; s++) {
                i64 i = items[s];
                for (i64 e = s + 1; e < b; e++) {
                    i64 j = items[e];
                    if ((cl[4 * i] > cl[4 * j] ? cl[4 * i] : cl[4 * j]) != cx || (cl[4 * i + 1] > cl[4 * j + 1] ? cl[4 * i + 1] : cl[4 * j + 1]) != cz) continue;      /* the pair is handled in the first cell (sorted order) that holds both */
                    rec_t r;
                    if (!pair_test(&c, i, j, &r, &err)) continue;
                    if (cnt[t] == cap[t]) { i64 nc = cap[t] ? cap[t] * 2 : 256; rec_t *nb = realloc(buf[t], sizeof(rec_t) * nc); if (!nb) { err = 2; break; } buf[t] = nb; cap[t] = nc; }
                    r.key = q; buf[t][cnt[t]++] = r;
                }
                if (err) break;
            }
        }
        if (err) {
            #pragma omp critical
            fail = err > fail ? err : fail;
        }
    }
    i64 total = 0; for (int t = 0; t < nt; t++) total += cnt[t];
    rec_t *all = malloc(sizeof(rec_t) * (total + 1));
    if (!all) fail = 2;
    if (!fail) { i64 p = 0; for (int t = 0; t < nt; t++) { if (cnt[t]) memcpy(all + p, buf[t], sizeof(rec_t) * cnt[t]); p += cnt[t]; } qsort(all, total, sizeof(rec_t), rec_cmp); }
    for (int t = 0; t < nt; t++) free(buf[t]);
    free(buf); free(cnt); free(cap); free(cl); free(in); free(start); free(items);
    if (fail) { free(all); return fail == 1 ? -2 : -1; }
    g_rec = all; g_nrec = total; return total;
}
EXPORT void fg_pairs_get(i64 *ij, double *vals)
{
    for (i64 k = 0; k < g_nrec; k++) { ij[2 * k] = g_rec[k].i; ij[2 * k + 1] = g_rec[k].j; vals[4 * k] = g_rec[k].gap; vals[4 * k + 1] = g_rec[k].spread; vals[4 * k + 2] = g_rec[k].need; vals[4 * k + 3] = g_rec[k].ov; }
    free(g_rec); g_rec = NULL; g_nrec = 0;
}

/* ------------------------------------------------------------------ fill1995.Index */
typedef struct {
    double cell; i64 x0, z0, NX, NZ;
    i64 nt; double *T; i64 *tfi; unsigned char *tcut; i64 *tstart, *titems;       /* lying triangles: 9 doubles each, face index, cut-out */
    i64 ns; double *S; i64 *sfi; unsigned char *scut; i64 *sstart, *sitems;       /* upright faces: a.x a.z b.x b.z ymin ymax */
} index_t;

static i64 cfloor(double v, double cell) { return (i64)floor(v / cell); }
EXPORT void fg_index_free(index_t *h)
{
    if (!h) return;
    free(h->T); free(h->tfi); free(h->tcut); free(h->tstart); free(h->titems); free(h->S); free(h->sfi); free(h->scut); free(h->sstart); free(h->sitems); free(h);
}
/* nr = fg_prep normals; cut[i] = cut-out material. -> handle (NULL = the grid would be too big: use the Python version) */
EXPORT index_t *fg_index_build(const double *X, const i64 *off, i64 n, const double *nr, const unsigned char *cut, double cell)
{
    index_t *h = calloc(1, sizeof(index_t)); if (!h) return NULL;
    h->cell = cell; i64 nt = 0, ns = 0;
    for (i64 i = 0; i < n; i++) { i64 k = off[i + 1] - off[i]; if (fabs(nr[3 * i + 1]) < 0.3) ns++; else if (k > 2) nt += k - 2; }
    h->nt = nt; h->ns = ns;
    h->T = malloc(sizeof(double) * 9 * (nt + 1)); h->tfi = malloc(sizeof(i64) * (nt + 1)); h->tcut = malloc(nt + 1);
    h->S = malloc(sizeof(double) * 6 * (ns + 1)); h->sfi = malloc(sizeof(i64) * (ns + 1)); h->scut = malloc(ns + 1);
    i64 *tc = malloc(sizeof(i64) * 4 * (nt + 1)), *sc = malloc(sizeof(i64) * 4 * (ns + 1));
    if (!h->T || !h->tfi || !h->tcut || !h->S || !h->sfi || !h->scut || !tc || !sc) { free(tc); free(sc); fg_index_free(h); return NULL; }
    i64 it = 0, is = 0, x0 = 0, x1 = -1, z0 = 0, z1 = -1; int first = 1;
    for (i64 i = 0; i < n; i++) {
        const double *P = X + 3 * off[i]; int k = (int)(off[i + 1] - off[i]); i64 c4[4];
        if (fabs(nr[3 * i + 1]) < 0.3) {
            int bi = 0, bj = 0; double bd = -1.0;                     /* the two plan corners furthest apart (first largest, row by row, as np.argmax) */
            for (int a = 0; a < k; a++) for (int b = 0; b < k; b++) { double dx = P[3 * a] - P[3 * b], dz = P[3 * a + 2] - P[3 * b + 2], d = sqrt(dx * dx + dz * dz); if (d > bd) { bd = d; bi = a; bj = b; } }
            double ax = P[3 * bi], az = P[3 * bi + 2], bx = P[3 * bj], bz = P[3 * bj + 2], y0 = P[1], y1 = P[1];
            for (int q = 1; q < k; q++) { if (P[3 * q + 1] < y0) y0 = P[3 * q + 1]; if (P[3 * q + 1] > y1) y1 = P[3 * q + 1]; }
            double *S = h->S + 6 * is; S[0] = ax; S[1] = az; S[2] = bx; S[3] = bz; S[4] = y0; S[5] = y1; h->sfi[is] = i; h->scut[is] = cut[i];
            c4[0] = cfloor((ax < bx ? ax : bx) - 0.6, cell); c4[1] = cfloor((az < bz ? az : bz) - 0.6, cell); c4[2] = cfloor((ax > bx ? ax : bx) + 0.6, cell); c4[3] = cfloor((az > bz ? az : bz) + 0.6, cell);
            memcpy(sc + 4 * is, c4, sizeof(c4)); is++;
            if (first) { x0 = c4[0]; z0 = c4[1]; x1 = c4[2]; z1 = c4[3]; first = 0; } else { if (c4[0] < x0) x0 = c4[0]; if (c4[1] < z0) z0 = c4[1]; if (c4[2] > x1) x1 = c4[2]; if (c4[3] > z1) z1 = c4[3]; }
        } else {
            for (int q = 1; q < k - 1; q++) {
                double *T = h->T + 9 * it; memcpy(T, P, 24); memcpy(T + 3, P + 3 * q, 24); memcpy(T + 6, P + 3 * q + 3, 24); h->tfi[it] = i; h->tcut[it] = cut[i];
                double lx = T[0], hx = T[0], lz = T[2], hz = T[2];
                for (int e = 1; e < 3; e++) { if (T[3 * e] < lx) lx = T[3 * e]; if (T[3 * e] > hx) hx = T[3 * e]; if (T[3 * e + 2] < lz) lz = T[3 * e + 2]; if (T[3 * e + 2] > hz) hz = T[3 * e + 2]; }
                c4[0] = cfloor(lx, cell); c4[1] = cfloor(lz, cell); c4[2] = cfloor(hx, cell); c4[3] = cfloor(hz, cell);
                memcpy(tc + 4 * it, c4, sizeof(c4)); it++;
                if (first) { x0 = c4[0]; z0 = c4[1]; x1 = c4[2]; z1 = c4[3]; first = 0; } else { if (c4[0] < x0) x0 = c4[0]; if (c4[1] < z0) z0 = c4[1]; if (c4[2] > x1) x1 = c4[2]; if (c4[3] > z1) z1 = c4[3]; }
            }
        }
    }
    i64 NX = first ? 0 : x1 - x0 + 1, NZ = first ? 0 : z1 - z0 + 1; h->x0 = x0; h->z0 = z0; h->NX = NX; h->NZ = NZ;
    if (NX * NZ > 40000000) { free(tc); free(sc); fg_index_free(h); return NULL; }
    for (int pass = 0; pass < 2; pass++) {
        i64 m = pass ? ns : nt, *cc = pass ? sc : tc, *start = calloc(NX * NZ + 1, sizeof(i64)), tot = 0;
        if (!start) { free(tc); free(sc); fg_index_free(h); return NULL; }
        for (i64 i = 0; i < m; i++) for (i64 x = cc[4 * i]; x <= cc[4 * i + 2]; x++) for (i64 z = cc[4 * i + 1]; z <= cc[4 * i + 3]; z++) start[(x - x0) * NZ + (z - z0) + 1]++;
        for (i64 q = 0; q < NX * NZ; q++) start[q + 1] += start[q];
        tot = NX * NZ ? start[NX * NZ] : 0;
        i64 *items = malloc(sizeof(i64) * (tot + 1)), *fill = malloc(sizeof(i64) * (NX * NZ + 1));
        if (!items || !fill) { free(start); free(items); free(fill); free(tc); free(sc); fg_index_free(h); return NULL; }
        memcpy(fill, start, sizeof(i64) * (NX * NZ + 1));
        for (i64 i = 0; i < m; i++) for (i64 x = cc[4 * i]; x <= cc[4 * i + 2]; x++) for (i64 z = cc[4 * i + 1]; z <= cc[4 * i + 3]; z++) items[fill[(x - x0) * NZ + (z - z0)]++] = i;
        free(fill);
        if (pass) { h->sstart = start; h->sitems = items; } else { h->tstart = start; h->titems = items; }
    }
    free(tc); free(sc); return h;
}
static i64 cell_of(const index_t *h, double x, double z)
{
    i64 cx = (i64)floor(x / h->cell) - h->x0, cz = (i64)floor(z / h->cell) - h->z0;
    if (cx < 0 || cz < 0 || cx >= h->NX || cz >= h->NZ) return -1;
    return cx * h->NZ + cz;
}
/* number of triangles in the cell of (x, z): the size the output of fg_index_heights can need */
EXPORT i64 fg_index_ntri(const index_t *h, double x, double z) { i64 q = cell_of(h, x, z); return q < 0 ? 0 : h->tstart[q + 1] - h->tstart[q]; }
EXPORT i64 fg_index_nseg(const index_t *h, double x, double z) { i64 q = cell_of(h, x, z); return q < 0 ? 0 : h->sstart[q + 1] - h->sstart[q]; }
/* fill1995.Index.heights -> count; -(needed) when the output is too small */
EXPORT i64 fg_index_heights(const index_t *h, double x, double z, int opaque_only, double *oy, i64 *ofi, i64 cap)
{
    i64 q = cell_of(h, x, z), m = 0; if (q < 0) return 0;
    if (h->tstart[q + 1] - h->tstart[q] > cap) return -(h->tstart[q + 1] - h->tstart[q]);
    for (i64 s = h->tstart[q]; s < h->tstart[q + 1]; s++) {
        i64 t = h->titems[s];
        if (opaque_only && h->tcut[t]) continue;
        const double *a = h->T + 9 * t, *b = a + 3, *c = a + 6;
        double d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]);
        if (fabs(d) < 1e-9) continue;
        double u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d, v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d;
        if (u < -1e-6 || v < -1e-6 || u + v > 1 + 1e-6) continue;
        oy[m] = u * a[1] + v * b[1] + (1 - u - v) * c[1]; ofi[m] = h->tfi[t]; m++;
    }
    return m;
}
/* fill1995.Index.uprights -> count (indices into the segment table: y0 = S[6 k + 4], y1 = S[6 k + 5], sfi, scut); -(needed) when too small */
EXPORT i64 fg_index_uprights(const index_t *h, double x, double z, double r, i64 *ok, i64 cap)
{
    i64 q = cell_of(h, x, z), m = 0; if (q < 0) return 0;
    if (h->sstart[q + 1] - h->sstart[q] > cap) return -(h->sstart[q + 1] - h->sstart[q]);
    for (i64 s = h->sstart[q]; s < h->sstart[q + 1]; s++) {
        i64 k = h->sitems[s]; const double *S = h->S + 6 * k;
        double ex = S[2] - S[0], ez = S[3] - S[1], ee = ex * ex + ez * ez; if (ee < 1e-12) ee = 1e-12;
        double t = ((x - S[0]) * ex + (z - S[1]) * ez) / ee; t = t < 0 ? 0 : (t > 1 ? 1 : t);
        double vx = S[0] + ex * t - x, vz = S[1] + ez * t - z;
        if (sqrt(vx * vx + vz * vz) <= r) ok[m++] = k;
    }
    return m;
}
EXPORT const double *fg_index_segs(const index_t *h) { return h->S; }
EXPORT const i64 *fg_index_segfi(const index_t *h) { return h->sfi; }
EXPORT const unsigned char *fg_index_segcut(const index_t *h) { return h->scut; }
EXPORT i64 fg_index_counts(const index_t *h, int which) { return which ? h->ns : h->nt; }

/* ------------------------------------------------------------------ gapfill_weld.Lying */
typedef struct { i64 n; const double *H; const i64 *off; const double *Y, *pl, *box; const unsigned char *pos; i64 x0, z0, NX, NZ; i64 *start, *items; } lying_t;
EXPORT void fg_lying_free(lying_t *h) { if (!h) return; free(h->start); free(h->items); free(h); }
/* records: plan corners H (2 doubles each, off as for polygons), heights Y (one per corner), pos (area sign > 0), plane pl (3 per record),
   box (xmin zmin xmax zmax per record). The arrays must stay alive as long as the handle. */
EXPORT lying_t *fg_lying_build(const double *H, const i64 *off, i64 n, const double *Y, const unsigned char *pos, const double *pl, const double *box)
{
    lying_t *h = calloc(1, sizeof(lying_t)); if (!h) return NULL;
    h->n = n; h->H = H; h->off = off; h->Y = Y; h->pl = pl; h->box = box; h->pos = pos;
    i64 *cc = malloc(sizeof(i64) * 4 * (n + 1)), x0 = 0, x1 = -1, z0 = 0, z1 = -1; if (!cc) { free(h); return NULL; }
    for (i64 i = 0; i < n; i++) {
        i64 *c4 = cc + 4 * i; c4[0] = (i64)floor((box[4 * i] - 1.6) / 4); c4[1] = (i64)floor((box[4 * i + 1] - 1.6) / 4); c4[2] = (i64)floor((box[4 * i + 2] + 1.6) / 4); c4[3] = (i64)floor((box[4 * i + 3] + 1.6) / 4);
        if (!i) { x0 = c4[0]; z0 = c4[1]; x1 = c4[2]; z1 = c4[3]; } else { if (c4[0] < x0) x0 = c4[0]; if (c4[1] < z0) z0 = c4[1]; if (c4[2] > x1) x1 = c4[2]; if (c4[3] > z1) z1 = c4[3]; }
    }
    i64 NX = n ? x1 - x0 + 1 : 0, NZ = n ? z1 - z0 + 1 : 0; h->x0 = x0; h->z0 = z0; h->NX = NX; h->NZ = NZ;
    if (NX * NZ > 40000000) { free(cc); free(h); return NULL; }
    i64 *start = calloc(NX * NZ + 1, sizeof(i64)); if (!start) { free(cc); free(h); return NULL; }
    for (i64 i = 0; i < n; i++) for (i64 x = cc[4 * i]; x <= cc[4 * i + 2]; x++) for (i64 z = cc[4 * i + 1]; z <= cc[4 * i + 3]; z++) start[(x - x0) * NZ + (z - z0) + 1]++;
    for (i64 q = 0; q < NX * NZ; q++) start[q + 1] += start[q];
    i64 tot = NX * NZ ? start[NX * NZ] : 0, *items = malloc(sizeof(i64) * (tot + 1)), *fill = malloc(sizeof(i64) * (NX * NZ + 1));
    if (!items || !fill) { free(cc); free(start); free(items); free(fill); free(h); return NULL; }
    memcpy(fill, start, sizeof(i64) * (NX * NZ + 1));
    for (i64 i = 0; i < n; i++) for (i64 x = cc[4 * i]; x <= cc[4 * i + 2]; x++) for (i64 z = cc[4 * i + 1]; z <= cc[4 * i + 3]; z++) items[fill[(x - x0) * NZ + (z - z0)]++] = i;
    free(fill); free(cc); h->start = start; h->items = items; return h;
}
/* gapfill_weld.Lying.near -> record index or -1; out = g, d, x, z, y */
EXPORT i64 fg_lying_near(const lying_t *h, double px, double py, double pz, double reach, double dy, double *out)
{
    i64 cx = (i64)floor(px / 4) - h->x0, cz = (i64)floor(pz / 4) - h->z0, best = -1; double bg = 0.0;
    if (cx < 0 || cz < 0 || cx >= h->NX || cz >= h->NZ) return -1;
    i64 q = cx * h->NZ + cz;
    for (i64 s = h->start[q]; s < h->start[q + 1]; s++) {
        i64 k = h->items[s]; const double *bx = h->box + 4 * k;
        if (px < bx[0] - reach || px > bx[2] + reach || pz < bx[1] - reach || pz > bx[3] + reach) continue;
        const double *H = h->H + 2 * h->off[k], *Y = h->Y + h->off[k]; int m = (int)(h->off[k + 1] - h->off[k]), ins = 1, pos = h->pos[k];
        double bd = 1e9, qbx = 0.0, qbz = 0.0, qby = 0.0; const double *a = H + 2 * (m - 1); double ya = Y[m - 1];
        for (int i = 0; i < m; i++) {
            const double *b = H + 2 * i; double yb = Y[i], ex = b[0] - a[0], ez = b[1] - a[1], L2 = ex * ex + ez * ez;
            if (L2 < 1e-12) L2 = 1e-12;
            double t = ((px - a[0]) * ex + (pz - a[1]) * ez) / L2; t = t < 0.0 ? 0.0 : (t > 1.0 ? 1.0 : t);
            double qx = a[0] + t * ex, qz = a[1] + t * ez, d = root(sqr(px - qx) + sqr(pz - qz));
            if (d < bd) { bd = d; qbx = qx; qbz = qz; qby = ya + t * (yb - ya); }
            double cr = ex * (pz - a[1]) - ez * (px - a[0]);
            if (pos ? (cr < 0) : (cr > 0)) ins = 0;
            a = b; ya = yb;
        }
        double d, x, z, y;
        if (ins) { const double *pl = h->pl + 3 * k; d = 0.0; x = px; z = pz; y = pl[0] * px + pl[1] * pz + pl[2]; } else { d = bd; x = qbx; z = qbz; y = qby; }
        if (d > reach || fabs(y - py) > dy) continue;
        double g = root(d * d + sqr(y - py));
        if (best < 0 || g < bg) { best = k; bg = g; out[0] = g; out[1] = d; out[2] = x; out[3] = z; out[4] = y; }
    }
    return best;
}

/* ------------------------------------------------------------------ build_classic.Near (fastbuild.Near) */
typedef double (*hyp_t)(double, double);
static hyp_t uhyp = NULL;                                              /* numpy's np.hypot is the C runtime's hypot: the same one here */
EXPORT int fg_init2(void)
{
    HMODULE h = GetModuleHandleA("ucrtbase.dll");
    if (h) { uhyp = (hyp_t)(void *)GetProcAddress(h, "hypot"); if (!uhyp) uhyp = (hyp_t)(void *)GetProcAddress(h, "_hypot"); }
    return uhyp != NULL;
}
typedef struct { const double *P; i64 n; double cell; i64 x0, z0, NX, NZ; i64 *start, *items; } near_t;
EXPORT void fg_near_free(near_t *h) { if (!h) return; free(h->start); free(h->items); free(h); }
/* P: n points (x, z), kept alive by the caller */
EXPORT near_t *fg_near_build(const double *P, i64 n, double cell)
{
    near_t *h = calloc(1, sizeof(near_t)); if (!h) return NULL;
    h->P = P; h->n = n; h->cell = cell; i64 x0 = 0, x1 = -1, z0 = 0, z1 = -1;
    for (i64 i = 0; i < n; i++) { i64 x = (i64)floor(P[2 * i] / cell), z = (i64)floor(P[2 * i + 1] / cell); if (!i) { x0 = x1 = x; z0 = z1 = z; } else { if (x < x0) x0 = x; if (x > x1) x1 = x; if (z < z0) z0 = z; if (z > z1) z1 = z; } }
    i64 NX = n ? x1 - x0 + 1 : 0, NZ = n ? z1 - z0 + 1 : 0; h->x0 = x0; h->z0 = z0; h->NX = NX; h->NZ = NZ;
    if (NX * NZ > 40000000) { free(h); return NULL; }
    h->start = calloc(NX * NZ + 1, sizeof(i64)); h->items = malloc(sizeof(i64) * (n + 1)); i64 *fill = malloc(sizeof(i64) * (NX * NZ + 1));
    if (!h->start || !h->items || !fill) { free(fill); fg_near_free(h); return NULL; }
    for (i64 i = 0; i < n; i++) h->start[((i64)floor(P[2 * i] / cell) - x0) * NZ + ((i64)floor(P[2 * i + 1] / cell) - z0) + 1]++;
    for (i64 q = 0; q < NX * NZ; q++) h->start[q + 1] += h->start[q];
    memcpy(fill, h->start, sizeof(i64) * (NX * NZ + 1));
    for (i64 i = 0; i < n; i++) h->items[fill[((i64)floor(P[2 * i] / cell) - x0) * NZ + ((i64)floor(P[2 * i + 1] / cell) - z0)]++] = i;
    free(fill); return h;
}
/* the search of Near.__call__: rings of cells r = 1, 2, ..; the nearest candidate (first of equals, in the order dx, dz, bucket) is taken when it is
   within r cells or r > 64; nothing found up to r = 200 leaves 0 */
EXPORT void fg_near_query(const near_t *h, const double *Q, i64 m, i64 *idx)
{
    #pragma omp parallel for schedule(dynamic, 256)
    for (i64 j = 0; j < m; j++) {
        double qx = Q[2 * j], qz = Q[2 * j + 1]; i64 cx = (i64)floor(qx / h->cell), cz = (i64)floor(qz / h->cell), r = 1; idx[j] = 0;
        while (1) {
            i64 best = -1; double bd = 0.0;
            if (!(cx + r < h->x0 || cx - r > h->x0 + h->NX - 1 || cz + r < h->z0 || cz - r > h->z0 + h->NZ - 1))
                for (i64 dx = -r; dx <= r; dx++) {
                    i64 gx = cx + dx - h->x0; if (gx < 0 || gx >= h->NX) continue;
                    i64 za = cz - r - h->z0, zb = cz + r - h->z0; if (za < 0) za = 0; if (zb > h->NZ - 1) zb = h->NZ - 1;
                    for (i64 gz = za; gz <= zb; gz++)
                        for (i64 s = h->start[gx * h->NZ + gz]; s < h->start[gx * h->NZ + gz + 1]; s++) {
                            i64 i = h->items[s]; double d = uhyp ? uhyp(h->P[2 * i] - qx, h->P[2 * i + 1] - qz) : hypot(h->P[2 * i] - qx, h->P[2 * i + 1] - qz);
                            if (best < 0 || d < bd) { best = i; bd = d; }
                        }
                }
            if (best >= 0 && (bd <= r * h->cell || r > 64)) { idx[j] = best; break; }
            r++;
            if (r > 200) break;
        }
    }
}

/* ------------------------------------------------------------------ build_more.HeightField / build_classic.AttrField (fastbuild.AttrField) */
typedef struct { const double *T; i64 n; double cell; i64 x0, z0, NX, NZ; i64 *start, *items; } hfield_t;
EXPORT void fg_hf_free(hfield_t *h) { if (!h) return; free(h->start); free(h->items); free(h); }
/* T: n triangles, 9 doubles each, kept alive by the caller */
EXPORT hfield_t *fg_hf_build(const double *T, i64 n, double cell)
{
    hfield_t *h = calloc(1, sizeof(hfield_t)); if (!h) return NULL;
    h->T = T; h->n = n; h->cell = cell; i64 *cc = malloc(sizeof(i64) * 4 * (n + 1)), x0 = 0, x1 = -1, z0 = 0, z1 = -1; if (!cc) { free(h); return NULL; }
    for (i64 i = 0; i < n; i++) {
        const double *t = T + 9 * i; double lx = t[0], hx = t[0], lz = t[2], hz = t[2];
        for (int e = 1; e < 3; e++) { if (t[3 * e] < lx) lx = t[3 * e]; if (t[3 * e] > hx) hx = t[3 * e]; if (t[3 * e + 2] < lz) lz = t[3 * e + 2]; if (t[3 * e + 2] > hz) hz = t[3 * e + 2]; }
        i64 *c4 = cc + 4 * i; c4[0] = (i64)floor(lx / cell); c4[1] = (i64)floor(lz / cell); c4[2] = (i64)floor(hx / cell); c4[3] = (i64)floor(hz / cell);
        if (!i) { x0 = c4[0]; z0 = c4[1]; x1 = c4[2]; z1 = c4[3]; } else { if (c4[0] < x0) x0 = c4[0]; if (c4[1] < z0) z0 = c4[1]; if (c4[2] > x1) x1 = c4[2]; if (c4[3] > z1) z1 = c4[3]; }
    }
    i64 NX = n ? x1 - x0 + 1 : 0, NZ = n ? z1 - z0 + 1 : 0; h->x0 = x0; h->z0 = z0; h->NX = NX; h->NZ = NZ;
    if (NX * NZ > 40000000) { free(cc); free(h); return NULL; }
    i64 *start = calloc(NX * NZ + 1, sizeof(i64)); if (!start) { free(cc); free(h); return NULL; }
    for (i64 i = 0; i < n; i++) for (i64 x = cc[4 * i]; x <= cc[4 * i + 2]; x++) for (i64 z = cc[4 * i + 1]; z <= cc[4 * i + 3]; z++) start[(x - x0) * NZ + (z - z0) + 1]++;
    for (i64 q = 0; q < NX * NZ; q++) start[q + 1] += start[q];
    i64 tot = NX * NZ ? start[NX * NZ] : 0, *items = malloc(sizeof(i64) * (tot + 1)), *fill = malloc(sizeof(i64) * (NX * NZ + 1));
    if (!items || !fill) { free(cc); free(start); free(items); free(fill); free(h); return NULL; }
    memcpy(fill, start, sizeof(i64) * (NX * NZ + 1));
    for (i64 i = 0; i < n; i++) for (i64 x = cc[4 * i]; x <= cc[4 * i + 2]; x++) for (i64 z = cc[4 * i + 1]; z <= cc[4 * i + 3]; z++) items[fill[(x - x0) * NZ + (z - z0)]++] = i;
    free(fill); free(cc); h->start = start; h->items = items; return h;
}
/* mode 0: AttrField.at2 / HeightField.at with yref (the height nearest yref); mode 1: HeightField.at without yref (the highest).
   -> triangle index or -1; *y = the height */
EXPORT i64 fg_hf_at(const hfield_t *h, double x, double z, double yref, int mode, double *y)
{
    i64 cx = (i64)floor(x / h->cell) - h->x0, cz = (i64)floor(z / h->cell) - h->z0, best = -1; double by = 0.0;
    if (cx < 0 || cz < 0 || cx >= h->NX || cz >= h->NZ) return -1;
    i64 q = cx * h->NZ + cz;
    for (i64 s = h->start[q]; s < h->start[q + 1]; s++) {
        i64 i = h->items[s]; const double *a = h->T + 9 * i, *b = a + 3, *c = a + 6;
        double d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]);
        if (fabs(d) < 1e-9) continue;
        double u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d, v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d, w = 1 - u - v;
        if (u < -1e-4 || v < -1e-4 || w < -1e-4) continue;
        double yy = u * a[1] + v * b[1] + w * c[1];
        if (best < 0 || (mode == 0 ? fabs(yy - yref) < fabs(by - yref) : yy > by)) { best = i; by = yy; }
    }
    *y = by; return best;
}

/* out[i] = index of the point of R (x, z) nearest to point i of P (x, z): ((P[i] - R) ** 2).sum(1).argmin(), the first of equals */
EXPORT void fg_argmin2(const double *P, i64 n, const double *R, i64 m, i64 *out)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        double px = P[2 * i], pz = P[2 * i + 1], best = INFINITY; i64 bj = 0;
        for (i64 j = 0; j < m; j++) { double dx = px - R[2 * j], dz = pz - R[2 * j + 1], d = dx * dx + dz * dz; if (d < best) { best = d; bj = j; } }
        out[i] = bj;
    }
}

/* ------------------------------------------------------------------ round1995._order_limits / _gap_over (fastround.py) */
typedef struct { i64 x0, z0, NX, NZ; i64 *start, *items; } pgrid_t;
static int pgrid_build(pgrid_t *g, const double *X, i64 n, const unsigned char *use, double cell)
{
    i64 x0 = 0, x1 = -1, z0 = 0, z1 = -1; int first = 1; g->start = NULL; g->items = NULL;
    for (i64 i = 0; i < n; i++) {
        if (use && !use[i]) continue;
        i64 x = (i64)floor(X[3 * i] / cell), z = (i64)floor(X[3 * i + 2] / cell);
        if (first) { x0 = x1 = x; z0 = z1 = z; first = 0; } else { if (x < x0) x0 = x; if (x > x1) x1 = x; if (z < z0) z0 = z; if (z > z1) z1 = z; }
    }
    g->x0 = x0; g->z0 = z0; g->NX = first ? 0 : x1 - x0 + 1; g->NZ = first ? 0 : z1 - z0 + 1;
    if (g->NX * g->NZ > 40000000) return -2;
    g->start = calloc(g->NX * g->NZ + 1, sizeof(i64)); g->items = malloc(sizeof(i64) * (n + 1)); i64 *fill = malloc(sizeof(i64) * (g->NX * g->NZ + 1));
    if (!g->start || !g->items || !fill) { free(g->start); free(g->items); free(fill); return -1; }
    for (i64 i = 0; i < n; i++) if (!use || use[i]) g->start[((i64)floor(X[3 * i] / cell) - x0) * g->NZ + ((i64)floor(X[3 * i + 2] / cell) - z0) + 1]++;
    for (i64 q = 0; q < g->NX * g->NZ; q++) g->start[q + 1] += g->start[q];
    memcpy(fill, g->start, sizeof(i64) * (g->NX * g->NZ + 1));
    for (i64 i = 0; i < n; i++) if (!use || use[i]) g->items[fill[((i64)floor(X[3 * i] / cell) - x0) * g->NZ + ((i64)floor(X[3 * i + 2] / cell) - z0)]++] = i;
    free(fill); return 0;
}
/* mode 0: _gap_over (X0 unused, out1 = gap, start inf); mode 1: _order_limits (out1 = lo, start -inf; out2 = hi, start inf; use = movable).
   S: m triangles (9 doubles). The arrays out1 / out2 come in filled with their start values. -> 0, -1 no memory, -2 grid too large */
EXPORT int fg_tri_points(int mode, const double *X0, const double *X1, i64 n, const unsigned char *use, const double *S, i64 m, double keep, double cell, double *out1, double *out2)
{
    pgrid_t g; int r = pgrid_build(&g, X1, n, use, cell); if (r) return r;
    if (g.NX * g.NZ == 0) { free(g.start); free(g.items); return 0; }
    for (i64 t = 0; t < m; t++) {
        const double *A = S + 9 * t, *B = A + 3, *C = A + 6;
        double e1[3] = { B[0] - A[0], B[1] - A[1], B[2] - A[2] }, e2[3] = { C[0] - A[0], C[1] - A[1], C[2] - A[2] };
        double n0 = e1[1] * e2[2] - e1[2] * e2[1], n1 = e1[2] * e2[0] - e1[0] * e2[2], n2 = e1[0] * e2[1] - e1[1] * e2[0];
        if (!(fabs(n1) > 1e-9)) continue;
        double lx = A[0], hx = A[0], lz = A[2], hz = A[2];
        for (int e = 1; e < 3; e++) { if (A[3 * e] < lx) lx = A[3 * e]; if (A[3 * e] > hx) hx = A[3 * e]; if (A[3 * e + 2] < lz) lz = A[3 * e + 2]; if (A[3 * e + 2] > hz) hz = A[3 * e + 2]; }
        i64 xa = (i64)floor(lx / cell) - g.x0, xb = (i64)floor(hx / cell) - g.x0, za = (i64)floor(lz / cell) - g.z0, zb = (i64)floor(hz / cell) - g.z0;
        if (xa < 0) xa = 0; if (za < 0) za = 0; if (xb > g.NX - 1) xb = g.NX - 1; if (zb > g.NZ - 1) zb = g.NZ - 1;
        double d = (B[2] - C[2]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[2] - C[2]);
        for (i64 x = xa; x <= xb; x++) for (i64 z = za; z <= zb; z++) for (i64 s = g.start[x * g.NZ + z]; s < g.start[x * g.NZ + z + 1]; s++) {
            i64 v = g.items[s]; const double *p = X1 + 3 * v;
            double w0 = ((B[2] - C[2]) * (p[0] - C[0]) + (C[0] - B[0]) * (p[2] - C[2])) / d, w1 = ((C[2] - A[2]) * (p[0] - C[0]) + (A[0] - C[0]) * (p[2] - C[2])) / d;
            if (!(w0 >= -1e-6 && w1 >= -1e-6 && w0 + w1 <= 1 + 1e-6)) continue;
            double yp = A[1] - (n0 * (p[0] - A[0]) + n2 * (p[2] - A[2])) / n1;
            if (mode == 0) { double gg = fabs(p[1] - yp); if (gg < out1[v] || gg != gg) out1[v] = gg; }
            else {
                const double *q = X0 + 3 * v; double g0 = q[1] - (A[1] - (n0 * (q[0] - A[0]) + n2 * (q[2] - A[2])) / n1); int nearby = fabs(g0) < 6.0;
                if (fabs(g0) < keep) { double h = yp + g0; if (h < out2[v] || h != h) out2[v] = h; }
                else if (g0 >= keep && nearby) { double l = yp + keep; if (l > out1[v] || l != l) out1[v] = l; }
                else if (g0 <= -keep && nearby) { double h = yp - keep; if (h < out2[v] || h != h) out2[v] = h; }
            }
        }
    }
    free(g.start); free(g.items); return 0;
}
