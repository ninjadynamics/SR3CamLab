/* round1995.c - round1995.round_outward's arrays without numpy (kb 31), the same numbers as its numpy code (round1995._old_round_outward,
   the reference). round1995.py calls the stages in order; each quotes the numpy it replaced and keeps its order of operations:
     (x * y).sum(1) / np.linalg.norm(x, axis=1) over three: (p0 + p1) + p2 ; mean(1) of k corners: in order from 0, / k ;
     np.cross: (a1 b2 - a2 b1, a2 b0 - a0 b2, a0 b1 - a1 b0) ; np.bincount(weights) / np.add.at: in index order from 0 ;
     np.maximum / np.minimum: a NaN wins ; np.unique / np.argsort(kind='stable'): the same sorted order and inverse.
   The kernels fastround.py already has (fastgeo.c: subdivision, weld keys, gap / order limits, corner / canon keys) are called through it;
   the bend angles of the O3 loop are fastgeo.c fg_bends + fg_round_angles' arithmetic, copied here to run inside the loop on every core.
   Built with -ffp-contract=off (cbuild 'round1995'). */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <windows.h>
#include <omp.h>
#define EXPORT __declspec(dllexport)
typedef long long i64;

static inline double red3(double a, double b, double c) { return (a + b) + c; }
static inline double npmax(double a, double b) { return (a >= b || a != a) ? a : b; }       /* np.maximum: a NaN wins */
static inline double npmin(double a, double b) { return (a <= b || a != a) ? a : b; }
static inline void cross3(const double *a, const double *b, double *o) { o[0] = a[1] * b[2] - a[2] * b[1]; o[1] = a[2] * b[0] - a[0] * b[2]; o[2] = a[0] * b[1] - a[1] * b[0]; }
static inline double norm3(const double *v) { return sqrt(red3(v[0] * v[0], v[1] * v[1], v[2] * v[2])); }
static inline double dot3(const double *a, const double *b) { return red3(a[0] * b[0], a[1] * b[1], a[2] * b[2]); }
static uint64_t quant(double x)
{   /* np.round(x).astype(np.int64) + (1 << 20), int64 wrap kept (fastgeo.c round_quantize) */
    double q = nearbyint(x); i64 v = isfinite(q) && q >= -9223372036854775808.0 && q < 9223372036854775808.0 ? (i64)q : INT64_MIN;
    return (uint64_t)v + UINT64_C(1048576);
}
static inline i64 pack(const double *p, double weld) { return (i64)((quant(p[0] / weld) << 42) | (quant(p[1] / weld) << 21) | quant(p[2] / weld)); }      /* round1995._pack */
typedef int (*cmp_t)(i64, i64, const void *);
static void msort(i64 *a, i64 n, cmp_t cmp, const void *ctx)
{   /* stable merge sort of an index array */
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
static int cmp_i64(i64 a, i64 b, const void *ctx) { const i64 *K = (const i64 *)ctx; return K[a] < K[b] ? -1 : (K[a] > K[b] ? 1 : 0); }
static int cmp_x(i64 a, i64 b, const void *ctx) { const double *X = (const double *)ctx; return X[3 * a] < X[3 * b] ? -1 : (X[3 * a] > X[3 * b] ? 1 : 0); }
static i64 unique_inv(i64 n, const i64 *K, i64 *uk, i64 *inv)
{   /* uk, inv = np.unique(K, return_inverse=True) -> len(uk) */
    i64 *o = (i64 *)malloc(sizeof(i64) * (n > 0 ? n : 1)), m = 0;
    for (i64 i = 0; i < n; i++) o[i] = i;
    msort(o, n, cmp_i64, K);
    for (i64 s = 0; s < n; s++) { if (!m || K[o[s]] != uk[m - 1]) uk[m++] = K[o[s]]; inv[o[s]] = m - 1; }
    free(o); return m;
}

/* ---------------------------------------------------------------- (O2) the edges of everything not rounded: hard
   for every polygon not rounded (corners C from coff[f] to coff[f + 1]): its corners' _pack keys, each side (min, max). -> the sorted
   unique pairs in pairs (2 x count), count returned (the Python set `hard`) */
static int cmp_pair(i64 a, i64 b, const void *ctx) { const i64 *P = (const i64 *)ctx; return P[2 * a] != P[2 * b] ? (P[2 * a] < P[2 * b] ? -1 : 1) : P[2 * a + 1] != P[2 * b + 1] ? (P[2 * a + 1] < P[2 * b + 1] ? -1 : 1) : 0; }
EXPORT i64 ro_hard(i64 nf, const i64 *coff, const double *C, double weld, i64 *pairs)
{
    i64 ne = 0;
    for (i64 f = 0; f < nf; f++) { i64 k = coff[f + 1] - coff[f]; if (k >= 2) ne += k; }
    i64 *E = (i64 *)malloc(sizeof(i64) * 2 * (ne > 0 ? ne : 1)), *o = (i64 *)malloc(sizeof(i64) * (ne > 0 ? ne : 1)), q = 0;
    for (i64 f = 0; f < nf; f++) {
        i64 k = coff[f + 1] - coff[f]; if (k < 2) continue;
        for (i64 a = 0; a < k; a++) { i64 x = pack(C + 3 * (coff[f] + a), weld), y = pack(C + 3 * (coff[f] + (a + 1) % k), weld); E[2 * q] = x < y ? x : y; E[2 * q + 1] = x < y ? y : x; o[q] = q; q++; }
    }
    msort(o, ne, cmp_pair, E); i64 m = 0;
    for (i64 s = 0; s < ne; s++) { const i64 *e = E + 2 * o[s]; if (!m || e[0] != pairs[2 * m - 2] || e[1] != pairs[2 * m - 1]) { pairs[2 * m] = e[0]; pairs[2 * m + 1] = e[1]; m++; } }
    free(E); free(o); return m;
}
static int has_pair(const i64 *pairs, i64 m, i64 a, i64 b)
{
    i64 lo = 0, hi = m;
    while (lo < hi) { i64 md = (lo + hi) / 2; const i64 *p = pairs + 2 * md; if (p[0] < a || (p[0] == a && p[1] < b)) lo = md + 1; else hi = md; }
    return lo < m && pairs[2 * lo] == a && pairs[2 * lo + 1] == b;
}

/* ---------------------------------------------------------------- (2.) the lying surfaces: S
   fan triangles (P0, Pa, Pa+1) of the polygons given; nS = np.cross(S1 - S0, S2 - S0), ln = np.linalg.norm(nS, axis=1); kept where
   ln > 1e-9 and |nS_y| > 0.5 * np.maximum(ln, 1e-12); then the road's (np.roll(R, -1, axis=0): a b c and a c d of every slice and column).
   out: (count, 3, 3); call with out NULL for the count */
EXPORT i64 ro_lying(i64 nf, const i64 *coff, const double *C, i64 ns, i64 nc, const double *R, double *out)
{
    i64 m = 0;
    for (i64 f = 0; f < nf; f++) {
        const double *P = C + 3 * coff[f]; i64 k = coff[f + 1] - coff[f];
        for (i64 a = 1; a < k - 1; a++) {
            const double *p0 = P, *p1 = P + 3 * a, *p2 = P + 3 * (a + 1); double e1[3] = { p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2] }, e2[3] = { p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2] }, n[3];
            cross3(e1, e2, n); double ln = norm3(n);
            if (!(ln > 1e-9 && fabs(n[1]) > 0.5 * npmax(ln, 1e-12))) continue;
            if (out) { memcpy(out + 9 * m, p0, 24); memcpy(out + 9 * m + 3, p1, 24); memcpy(out + 9 * m + 6, p2, 24); }
            m++;
        }
    }
    for (int h = 0; h < 2; h++)
        for (i64 i = 0; i < ns; i++)
            for (i64 j = 0; j + 1 < nc; j++) {
                const double *a = R + 3 * (i * nc + j), *b = R + 3 * (i * nc + j + 1), *c = R + 3 * (((i + 1) % ns) * nc + j + 1), *d = R + 3 * (((i + 1) % ns) * nc + j);
                if (out) { double *o = out + 9 * m; memcpy(o, a, 24); memcpy(o + 3, h ? c : b, 24); memcpy(o + 6, h ? d : c, 24); }
                m++;
            }
    return m;
}

/* ---------------------------------------------------------------- the 1995 polygons: normals, smooth edges, fan normals, curves, hollowness
   P: the polygons' corners, nf polygons of K[f] corners (3 or 4) at 4 slots each (P[f][c] for c < K[f]), in round1995's order (the
   triangles, then the quads). -> D1, D2 (nf x 4 x 3), cav2 (nf), st[3] = (edges, smooth edges, sharp or open edges) */
typedef struct { const i64 *ek; } ekctx;
static int cmp_ek(i64 a, i64 b, const void *ctx) { const i64 *K = ((const ekctx *)ctx)->ek; return K[a] < K[b] ? -1 : (K[a] > K[b] ? 1 : 0); }
static i64 findm(i64 *par, i64 x) { while (par[x] != x) { par[x] = par[par[x]]; x = par[x]; } return x; }
static double (*u_acos)(double) = NULL;
static int acos_init(void) { if (!u_acos) { HMODULE h = GetModuleHandleA("ucrtbase.dll"); if (h) u_acos = (double (*)(double))(void *)GetProcAddress(h, "acos"); } return u_acos != NULL; }
static inline double degacos(double c) { return u_acos(c) * 57.295779513082323; }      /* np.degrees(np.arccos(c)): UCRT acos, x the rounded 180 / pi */
EXPORT int ro_faces(i64 nf, const int *K, const double *P, double weld, const i64 *hard, i64 nhard, double cos_crease, double *D1, double *D2, double *cav2, i64 *st)
{
    if (!acos_init()) return -1;
    /* VK = _pack(P); uk, inv = np.unique(concatenated keys, return_inverse=True); VI[f][c] */
    i64 nk = 0; for (i64 f = 0; f < nf; f++) nk += K[f];
    i64 *key = (i64 *)malloc(sizeof(i64) * (nk + 1)), *uk = (i64 *)malloc(sizeof(i64) * (nk + 1)), *inv = (i64 *)malloc(sizeof(i64) * (nk + 1)), *VI = (i64 *)malloc(sizeof(i64) * 4 * (nf + 1));
    /* the order of the concatenation: per group (k = 3, then 4) VK[k].ravel(): polygon after polygon, corner after corner */
    i64 q = 0;
    for (int k = 3; k <= 4; k++) for (i64 f = 0; f < nf; f++) if (K[f] == k) for (int c = 0; c < k; c++) key[q++] = pack(P + 12 * f + 3 * c, weld);
    i64 nvc = unique_inv(nk, key, uk, inv); q = 0;
    for (int k = 3; k <= 4; k++) for (i64 f = 0; f < nf; f++) if (K[f] == k) for (int c = 0; c < k; c++) VI[4 * f + c] = inv[q++];
    /* FN: k 3: np.cross(P1 - P0, P2 - P0); k 4: np.cross(P2 - P0, P3 - P1); FL = norm; FU = FN / np.maximum(FL, 1e-12) */
    double *FN = (double *)malloc(sizeof(double) * 3 * (nf + 1)), *FL = (double *)malloc(sizeof(double) * (nf + 1)), *FU = (double *)malloc(sizeof(double) * 3 * (nf + 1));
    for (i64 f = 0; f < nf; f++) {
        const double *p = P + 12 * f; double a[3], b[3];
        if (K[f] == 3) for (int c = 0; c < 3; c++) { a[c] = p[3 + c] - p[c]; b[c] = p[6 + c] - p[c]; }
        else for (int c = 0; c < 3; c++) { a[c] = p[6 + c] - p[c]; b[c] = p[9 + c] - p[3 + c]; }
        cross3(a, b, FN + 3 * f); FL[f] = norm3(FN + 3 * f); double d = npmax(FL[f], 1e-12);
        for (int c = 0; c < 3; c++) FU[3 * f + c] = FN[3 * f + c] / d;
    }
    /* the edges EA EB EF EC EK, in the order: group, corner c, polygon; ek = lo * nvc + hi (or -1 - edge for a collapsed one) */
    i64 ne = nk, *EA = (i64 *)malloc(sizeof(i64) * (ne + 1)), *EB = (i64 *)malloc(sizeof(i64) * (ne + 1)), *EF = (i64 *)malloc(sizeof(i64) * (ne + 1)), *ek = (i64 *)malloc(sizeof(i64) * (ne + 1)), *o = (i64 *)malloc(sizeof(i64) * (ne + 1));
    int *EC = (int *)malloc(sizeof(int) * (ne + 1)), *EK = (int *)malloc(sizeof(int) * (ne + 1)); q = 0;
    for (int k = 3; k <= 4; k++) for (int c = 0; c < k; c++) for (i64 f = 0; f < nf; f++) if (K[f] == k) { EA[q] = VI[4 * f + c]; EB[q] = VI[4 * f + (c + 1) % k]; EF[q] = f; EC[q] = c; EK[q] = k; q++; }
    for (i64 e = 0; e < ne; e++) { i64 lo = EA[e] < EB[e] ? EA[e] : EB[e], hi = EA[e] < EB[e] ? EB[e] : EA[e]; ek[e] = EA[e] != EB[e] ? lo * nvc + hi : -1 - e; o[e] = e; }
    ekctx cx = { ek }; msort(o, ne, cmp_ek, &cx);
    /* runs of equal ek: ue, st, cnt; pairs (cnt == 2, ue >= 0): i1 = o[st], i2 = o[st + 1]; smooth_e ; hk: (uk[lo], uk[hi]) in hard */
    unsigned char *smooth = (unsigned char *)calloc(ne + 1, 1); i64 nue = 0, nsm = 0; double *cav = (double *)calloc(nf + 1, sizeof(double));
    i64 *pa = (i64 *)malloc(sizeof(i64) * 2 * (ne + 1)), *pb = (i64 *)malloc(sizeof(i64) * 2 * (ne + 1)), np_ = 0;
    i64 *s1 = (i64 *)malloc(sizeof(i64) * (ne + 1)), *s2 = (i64 *)malloc(sizeof(i64) * (ne + 1)), ns = 0;
    for (i64 s = 0; s < ne; ) {
        i64 t = s; while (t < ne && ek[o[t]] == ek[o[s]]) t++;
        nue++;
        if (t - s == 2 && ek[o[s]] >= 0) {
            i64 i1 = o[s], i2 = o[s + 1], f1 = EF[i1], f2 = EF[i2];
            int sm = EA[i1] == EB[i2] && FL[f1] > 1e-12 && FL[f2] > 1e-12 && dot3(FU + 3 * f1, FU + 3 * f2) >= cos_crease;
            if (sm) { i64 lo = EA[i1] < EB[i1] ? EA[i1] : EB[i1], hi = EA[i1] < EB[i1] ? EB[i1] : EA[i1]; if (has_pair(hard, nhard, uk[lo], uk[hi])) sm = 0; }
            if (sm) { smooth[i1] = smooth[i2] = 1; nsm++; s1[ns] = i1; s2[ns] = i2; ns++; }
        }
        s = t;
    }
    st[0] = nue; st[1] = nsm; st[2] = nue - nsm;
    /* fans: node(f, c) = 4 f + c; pa = node(EF[s1], EC[s1]) ++ node(EF[s1], (EC[s1] + 1) % EK[s1]), pb = node(EF[s2], (EC[s2] + 1) % EK[s2]) ++
       node(EF[s2], EC[s2]): the label propagation ends with the lowest node of every joined set (union to the lower root, the same) */
    i64 nn = 4 * nf, *lab = (i64 *)malloc(sizeof(i64) * (nn + 1));
    for (i64 i = 0; i < nn; i++) lab[i] = i;
    for (i64 h = 0; h < ns; h++) {
        i64 a1 = 4 * EF[s1[h]] + EC[s1[h]], b1 = 4 * EF[s2[h]] + (EC[s2[h]] + 1) % EK[s2[h]], a2 = 4 * EF[s1[h]] + (EC[s1[h]] + 1) % EK[s1[h]], b2 = 4 * EF[s2[h]] + EC[s2[h]];
        i64 x = findm(lab, a1), y = findm(lab, b1); if (x != y) { if (x < y) lab[y] = x; else lab[x] = y; }
        x = findm(lab, a2); y = findm(lab, b2); if (x != y) { if (x < y) lab[y] = x; else lab[x] = y; }
    }
    for (i64 i = 0; i < nn; i++) lab[i] = findm(lab, i);
    /* fanN = 0; np.add.at(fanN, lab_, np.repeat(FN, 4, axis=0)) (node order); CN = fanN[lab_] / np.maximum(norm, 1e-12) */
    double *fan = (double *)calloc(3 * (nn + 1), sizeof(double)), *CN = (double *)malloc(sizeof(double) * 3 * (nn + 1));
    for (i64 i = 0; i < nn; i++) for (int c = 0; c < 3; c++) fan[3 * lab[i] + c] += FN[3 * (i / 4) + c];
    for (i64 i = 0; i < nn; i++) { const double *v = fan + 3 * lab[i]; double d = npmax(norm3(v), 1e-12); for (int c = 0; c < 3; c++) CN[3 * i + c] = v[c] / d; }
    /* D1[f, c] = -((b - a) * na).sum(1) * na / 3.0 ; D2[f, c] = -((a - b) * nb).sum(1) * nb / 3.0 ; zero where the edge is not smooth */
    memset(D1, 0, sizeof(double) * 12 * nf); memset(D2, 0, sizeof(double) * 12 * nf);
    for (i64 e = 0; e < ne; e++) {
        if (!smooth[e]) continue;
        i64 f = EF[e]; int c = EC[e], k = EK[e]; const double *a = P + 12 * f + 3 * c, *b = P + 12 * f + 3 * ((c + 1) % k), *na = CN + 3 * (4 * f + c), *nb = CN + 3 * (4 * f + (c + 1) % k);
        double ba[3] = { b[0] - a[0], b[1] - a[1], b[2] - a[2] }, ab[3] = { a[0] - b[0], a[1] - b[1], a[2] - b[2] }, s1v = -dot3(ba, na), s2v = -dot3(ab, nb);
        for (int j = 0; j < 3; j++) { D1[12 * f + 3 * c + j] = s1v * na[j] / 3.0; D2[12 * f + 3 * c + j] = s2v * nb[j] / 3.0; }
    }
    /* (O3) cen = mean(1); cv = np.where(((cen[f2] - cen[f1]) * FU[f1]).sum(1) > 0, degrees(arccos(clip(FU[f1] . FU[f2]))), 0); cav = max over
       both; vmax = max over the polygons at a corner; cav2 = max over the polygon's corners */
    double *cen = (double *)malloc(sizeof(double) * 3 * (nf + 1)), *vmax = (double *)calloc(nvc + 1, sizeof(double));
    for (i64 f = 0; f < nf; f++) for (int c = 0; c < 3; c++) { double s = 0.0; for (int j = 0; j < K[f]; j++) s += P[12 * f + 3 * j + c]; cen[3 * f + c] = s / K[f]; }
    for (i64 h = 0; h < ns; h++) {
        i64 f1 = EF[s1[h]], f2 = EF[s2[h]]; double d[3] = { cen[3 * f2] - cen[3 * f1], cen[3 * f2 + 1] - cen[3 * f1 + 1], cen[3 * f2 + 2] - cen[3 * f1 + 2] };
        double cv = 0.0;
        if (dot3(d, FU + 3 * f1) > 0) { double x = dot3(FU + 3 * f1, FU + 3 * f2); x = x < -1.0 ? -1.0 : (x > 1.0 ? 1.0 : x); cv = degacos(x); }
        cav[f1] = npmax(cav[f1], cv); cav[f2] = npmax(cav[f2], cv);
    }
    for (i64 f = 0; f < nf; f++) for (int c = 0; c < K[f]; c++) { i64 v = VI[4 * f + c]; vmax[v] = npmax(vmax[v], cav[f]); }
    for (i64 f = 0; f < nf; f++) { double m = vmax[VI[4 * f]]; for (int c = 1; c < K[f]; c++) m = npmax(m, vmax[VI[4 * f + c]]); cav2[f] = m; }
    free(key); free(uk); free(inv); free(VI); free(FN); free(FL); free(FU); free(EA); free(EB); free(EF); free(ek); free(o); free(EC); free(EK); free(smooth); free(cav);
    free(pa); free(pb); free(s1); free(s2); free(lab); free(fan); free(CN); free(cen); free(vmax); (void)np_;
    return 0;
}

/* ---------------------------------------------------------------- the pieces' curve offsets DD (n pieces of k corners; parent face PF, place AB)
   k 4: (1 - v) E(f, 0, u) + v E(f, 2, 1 - u) + (1 - u) E(f, 3, 1 - v) + u E(f, 1, v), E(f, c, s) = 3.0 ((1 - s)**2 s) D1[f, c] + 3.0 ((1 - s) s s) D2[f, c]
   k 3: w, u, v = 1 - A0, A0 - A1, A1; the cubic triangle's seven terms, d111 = 1.5 (the six summed in order) / 6.0 */
static inline void E_(const double *D1, const double *D2, i64 f, int c, double s, double *o)
{
    double r = 1 - s, a = 3.0 * ((r * r) * s), b = 3.0 * ((r * s) * s);
    for (int j = 0; j < 3; j++) o[j] = a * D1[12 * f + 3 * c + j] + b * D2[12 * f + 3 * c + j];
}
EXPORT void ro_dd(i64 n, int k, const i64 *PF, const double *AB, const double *D1, const double *D2, double *DD)
{
    #pragma omp parallel for schedule(static) if(n > 4096)
    for (i64 p = 0; p < n; p++)
        for (int c = 0; c < k; c++) {
            i64 f = PF[p]; const double *A = AB + 2 * (k * p + c); double *o = DD + 3 * (k * p + c);
            if (k == 4) {
                double u = A[0], v = A[1], e0[3], e2[3], e3[3], e1[3];
                E_(D1, D2, f, 0, u, e0); E_(D1, D2, f, 2, 1 - u, e2); E_(D1, D2, f, 3, 1 - v, e3); E_(D1, D2, f, 1, v, e1);
                for (int j = 0; j < 3; j++) o[j] = (((1 - v) * e0[j] + v * e2[j]) + (1 - u) * e3[j]) + u * e1[j];
            } else {
                double w = 1 - A[0], u = A[0] - A[1], v = A[1];
                const double *d210 = D1 + 12 * f, *d120 = D2 + 12 * f, *d021 = D1 + 12 * f + 3, *d012 = D2 + 12 * f + 3, *d102 = D1 + 12 * f + 6, *d201 = D2 + 12 * f + 6;
                for (int j = 0; j < 3; j++) {
                    double d111 = 1.5 * (((((d210[j] + d120[j]) + d021[j]) + d012[j]) + d102[j]) + d201[j]) / 6.0;
                    o[j] = (((((3 * ((w * w) * u) * d210[j] + 3 * ((w * u) * u) * d120[j]) + 3 * ((u * u) * v) * d021[j]) + 3 * ((u * v) * v) * d012[j]) + 3 * ((v * v) * w) * d102[j]) + 3 * ((v * w) * w) * d201[j]) + 6 * ((w * u) * v) * d111;
                }
            }
        }
}

/* ---------------------------------------------------------------- the pieces' corners welded
   allp / alld (n x 3, the groups' corners in order) -> nv, winv (n), start / D (nv x 3) = np.bincount(winv, weights) / np.bincount(winv);
   call once with start NULL for nv (winv and the keys kept for the second call) */
static i64 *g_key = 0, *g_uk = 0, *g_inv = 0, g_n = 0, g_nv = 0;
EXPORT i64 ro_weld(i64 n, const double *allp, const double *alld, double weld, i64 *winv, double *start, double *D)
{
    if (!start) {
        free(g_key); free(g_uk); free(g_inv); g_n = n;
        g_key = (i64 *)malloc(sizeof(i64) * (n + 1)); g_uk = (i64 *)malloc(sizeof(i64) * (n + 1)); g_inv = (i64 *)malloc(sizeof(i64) * (n + 1));
        for (i64 i = 0; i < n; i++) g_key[i] = pack(allp + 3 * i, weld);
        g_nv = unique_inv(n, g_key, g_uk, g_inv); return g_nv;
    }
    i64 nv = g_nv; double *cnt = (double *)calloc(nv + 1, sizeof(double));
    memset(start, 0, sizeof(double) * 3 * nv); memset(D, 0, sizeof(double) * 3 * nv);
    for (i64 i = 0; i < n; i++) { i64 v = g_inv[i]; winv[i] = v; cnt[v] += 1.0; }
    for (int c = 0; c < 3; c++) for (i64 i = 0; i < n; i++) { start[3 * g_inv[i] + c] += allp[3 * i + c]; D[3 * g_inv[i] + c] += alld[3 * i + c]; }
    for (i64 v = 0; v < nv; v++) for (int c = 0; c < 3; c++) { start[3 * v + c] /= cnt[v]; D[3 * v + c] /= cnt[v]; }
    free(cnt); free(g_key); free(g_uk); free(g_inv); g_key = g_uk = g_inv = 0; return nv;
}
/* dl = np.linalg.norm(D, axis=1); D *= np.minimum(1.0, cap / np.maximum(dl, 1e-12)) -> capped = (dl > cap).sum(); dl out */
EXPORT i64 ro_cap(i64 nv, double *D, double cap, double *dl)
{
    i64 capped = 0;
    for (i64 v = 0; v < nv; v++) { double l = norm3(D + 3 * v), f = npmin(1.0, cap / npmax(l, 1e-12)); dl[v] = l; capped += l > cap; for (int c = 0; c < 3; c++) D[3 * v + c] *= f; }
    return capped;
}
/* xo = np.argsort(X[:, 0], kind='stable') */
EXPORT void ro_argsort_x(i64 n, const double *X, i64 *xo) { for (i64 i = 0; i < n; i++) xo[i] = i; msort(xo, n, cmp_x, X); }
/* D[keep] = 0; X = start + D; movable = np.linalg.norm(D, axis=1) > 1e-9 */
EXPORT void ro_keep(i64 nv, const unsigned char *keep, const double *start, double *D, double *X, unsigned char *movable)
{
    for (i64 v = 0; v < nv; v++) { if (keep[v]) D[3 * v] = D[3 * v + 1] = D[3 * v + 2] = 0.0; for (int c = 0; c < 3; c++) X[3 * v + c] = start[3 * v + c] + D[3 * v + c]; movable[v] = norm3(D + 3 * v) > 1e-9; }
}
/* (2.) bad = lo > hi; y = np.clip(X[:, 1], lo, np.maximum(hi, lo)); held = (|y - X1| > 1e-6).sum() + bad.sum(); D[:, 1] = y - start[:, 1]; D[bad] = 0 */
EXPORT i64 ro_order(i64 nv, const double *lo, const double *hi, const double *start, const double *X, double *D)
{
    i64 held = 0;
    for (i64 v = 0; v < nv; v++) {
        int bad = lo[v] > hi[v]; double y = npmin(npmax(X[3 * v + 1], lo[v]), npmax(hi[v], lo[v]));
        held += (fabs(y - X[3 * v + 1]) > 1e-6) + bad; D[3 * v + 1] = y - start[3 * v + 1];
        if (bad) D[3 * v] = D[3 * v + 1] = D[3 * v + 2] = 0.0;
    }
    return held;
}

/* ---------------------------------------------------------------- (O3, 7.) the triangles the game draws and their shared edges
   per group (k, its pieces' welded corners vi (n x k), their uncut positions O (n x k x 3), parent face PF): the triangles (0 1 2) or (0 1 2), (0 2 3),
   in the order group, triangle, piece; those with two equal corners dropped (T, TO, TP). Their edges U -> V (W the third), all first sides, then
   second, then third; ek2 = min * nv + max, np.argsort(kind='stable'), runs of two that run opposite ways: TA, TB, and the parent faces of both.
   Two calls: with the outputs NULL for the counts (nt, ne2) */
static i64 *t_T = 0, t_nt = 0; static double *t_TO = 0; static i64 *t_TP = 0;
EXPORT i64 ro_tris(int ng, const int *ks, const i64 *ns, const i64 *const *vis, const double *const *Os, const i64 *const *PFs, i64 nv, i64 *counts,
                   i64 *T, double *TO, i64 *TP, i64 *TA, i64 *TB, i64 *TPA, i64 *TPB)
{
    if (!T) {
        free(t_T); free(t_TO); free(t_TP); i64 cap = 0;
        for (int g = 0; g < ng; g++) cap += ns[g] * (ks[g] == 3 ? 1 : 2);
        t_T = (i64 *)malloc(sizeof(i64) * 3 * (cap + 1)); t_TO = (double *)malloc(sizeof(double) * 9 * (cap + 1)); t_TP = (i64 *)malloc(sizeof(i64) * (cap + 1)); i64 m = 0;
        static const int TR[2][3] = { {0, 1, 2}, {0, 2, 3} };
        for (int g = 0; g < ng; g++) {
            int k = ks[g];
            for (int tr = 0; tr < (k == 3 ? 1 : 2); tr++)
                for (i64 p = 0; p < ns[g]; p++) {
                    i64 a = vis[g][k * p + TR[tr][0]], b = vis[g][k * p + TR[tr][1]], c = vis[g][k * p + TR[tr][2]];
                    if (a == b || b == c || a == c) continue;
                    t_T[3 * m] = a; t_T[3 * m + 1] = b; t_T[3 * m + 2] = c; t_TP[m] = PFs[g][p];
                    for (int j = 0; j < 3; j++) memcpy(t_TO + 9 * m + 3 * j, Os[g] + 3 * (k * p + TR[tr][j]), 24);
                    m++;
                }
        }
        t_nt = m; i64 n3 = 3 * m, *ek = (i64 *)malloc(sizeof(i64) * (n3 + 1)), *o = (i64 *)malloc(sizeof(i64) * (n3 + 1)), ne = 0;
        for (i64 e = 0; e < n3; e++) { i64 t = e % m, s = e / m, u = t_T[3 * t + s], v = t_T[3 * t + (s + 1) % 3]; ek[e] = (u < v ? u : v) * nv + (u < v ? v : u); o[e] = e; }
        ekctx cx = { ek }; msort(o, n3, cmp_ek, &cx);
        for (i64 s = 0; s < n3; ) { i64 t = s; while (t < n3 && ek[o[t]] == ek[o[s]]) t++; if (t - s == 2) { i64 j1 = o[s], j2 = o[s + 1]; if (t_T[3 * (j1 % m) + j1 / m] == t_T[3 * (j2 % m) + (j2 / m + 1) % 3]) ne++; } s = t; }
        free(ek); free(o); counts[0] = m; counts[1] = ne; return 0;
    }
    i64 m = t_nt, n3 = 3 * m, *ek = (i64 *)malloc(sizeof(i64) * (n3 + 1)), *o = (i64 *)malloc(sizeof(i64) * (n3 + 1)), ne = 0;
    memcpy(T, t_T, sizeof(i64) * 3 * m); memcpy(TO, t_TO, sizeof(double) * 9 * m); memcpy(TP, t_TP, sizeof(i64) * m);
    for (i64 e = 0; e < n3; e++) { i64 t = e % m, s = e / m, u = t_T[3 * t + s], v = t_T[3 * t + (s + 1) % 3]; ek[e] = (u < v ? u : v) * nv + (u < v ? v : u); o[e] = e; }
    ekctx cx = { ek }; msort(o, n3, cmp_ek, &cx);
    for (i64 s = 0; s < n3; ) {
        i64 t = s; while (t < n3 && ek[o[t]] == ek[o[s]]) t++;
        if (t - s == 2) {
            i64 j1 = o[s], j2 = o[s + 1], t1 = j1 % m, a1 = j1 / m, t2 = j2 % m, a2 = j2 / m;
            if (t_T[3 * t1 + a1] == t_T[3 * t2 + (a2 + 1) % 3]) {
                TA[3 * ne] = t_T[3 * t1 + a1]; TA[3 * ne + 1] = t_T[3 * t1 + (a1 + 1) % 3]; TA[3 * ne + 2] = t_T[3 * t1 + (a1 + 2) % 3];
                TB[3 * ne] = t_T[3 * t2 + a2]; TB[3 * ne + 1] = t_T[3 * t2 + (a2 + 1) % 3]; TB[3 * ne + 2] = t_T[3 * t2 + (a2 + 2) % 3];
                TPA[ne] = t_TP[t1]; TPB[ne] = t_TP[t2]; ne++;
            }
        }
        s = t;
    }
    free(ek); free(o); free(t_T); free(t_TO); free(t_TP); t_T = 0; t_TO = 0; t_TP = 0; return 0;
}

/* ---------------------------------------------------------------- the bends (round1995._bends = fastgeo.c fg_bends + fg_round_angles)
   n1 = cross(TA1 - TA0, TA2 - TA0), n2 = cross(TB1 - TB0, TB2 - TB0); c = clip((n1 . n2) / np.maximum(l1 l2, 1e-30), -1, 1);
   angle = degrees(arccos(c)), + when ((TB2 - TA0) . n1) > 0; ok = l1 > 1e-12 and l2 > 1e-12 */
static inline void bend(const double *X, const i64 *A, const i64 *B, double *ang, unsigned char *ok)
{
    const double *a = X + 3 * A[0], *b = X + 3 * A[1], *w = X + 3 * A[2], *p = X + 3 * B[0], *q = X + 3 * B[1], *r = X + 3 * B[2];
    double e0 = b[0] - a[0], e1 = b[1] - a[1], e2 = b[2] - a[2], f0 = w[0] - a[0], f1 = w[1] - a[1], f2 = w[2] - a[2];
    double n10 = e1 * f2 - e2 * f1, n11 = e2 * f0 - e0 * f2, n12 = e0 * f1 - e1 * f0;
    double g0 = q[0] - p[0], g1 = q[1] - p[1], g2 = q[2] - p[2], h0 = r[0] - p[0], h1 = r[1] - p[1], h2 = r[2] - p[2];
    double n20 = g1 * h2 - g2 * h1, n21 = g2 * h0 - g0 * h2, n22 = g0 * h1 - g1 * h0;
    double l1 = sqrt(red3(n10 * n10, n11 * n11, n12 * n12)), l2 = sqrt(red3(n20 * n20, n21 * n21, n22 * n22));
    double pr = l1 * l2; if (!(pr >= 1e-30)) pr = 1e-30;
    if (l1 != l1 || l2 != l2) pr = l1 * l2;
    double c = red3(n10 * n20, n11 * n21, n12 * n22) / pr;
    if (c < -1.0) c = -1.0; else if (c > 1.0) c = 1.0;
    *ok = (l1 > 1e-12) && (l2 > 1e-12);
    double s0 = r[0] - a[0], s1 = r[1] - a[1], s2 = r[2] - a[2], an = degacos(c);
    *ang = red3(s0 * n10, s1 * n11, s2 * n12) > 0 ? an : -an;
}
/* b0 = np.maximum(np.maximum(bends(start), 0.0), np.maximum(cav2[TPA], cav2[TPB])); ok0 */
EXPORT int ro_b0(i64 ne, const double *start, const i64 *TA, const i64 *TB, const i64 *TPA, const i64 *TPB, const double *cav2, double *b0, unsigned char *ok0)
{
    if (!acos_init()) return -1;
    #pragma omp parallel for schedule(static) if(ne > 4096)
    for (i64 e = 0; e < ne; e++) { double a; bend(start, TA + 3 * e, TB + 3 * e, &a, ok0 + e); b0[e] = npmax(npmax(a, 0.0), npmax(cav2[TPA[e]], cav2[TPB[e]])); }
    return 0;
}
/* the O3 loop (up to 40 rounds): X = start + D * scale; hol = ok0 & ok1 & (b1 > b0 + tol); fold = (l0 > 1e-9) & ((n0 . n1) < FOLD * l0 * l1)
   (n0 / l0 from the uncut triangles TO, n1 / l1 from X[T]); the corners of TA[hol], TB[hol, 2] and T[fold] with a scale > 0 have it halved (rounds
   0 .. 15) or set to 0. -> st: rounds, corners cut, new hollows / turned over before, new hollows left; X = the final places */
EXPORT int ro_o3(i64 nv, const double *start, const double *D, double *scale, i64 nt, const i64 *T, const double *TO, i64 ne, const i64 *TA, const i64 *TB,
                 const double *b0, const unsigned char *ok0, double tol, double FOLD, double *X, i64 *st)
{
    if (!acos_init()) return -1;
    double *n0 = (double *)malloc(sizeof(double) * 3 * (nt + 1)), *l0 = (double *)malloc(sizeof(double) * (nt + 1)), *b1 = (double *)malloc(sizeof(double) * (ne + 1));
    unsigned char *ok1 = (unsigned char *)malloc(ne + 1), *hol = (unsigned char *)malloc(ne + 1), *fold = (unsigned char *)malloc(nt + 1), *mark = (unsigned char *)malloc(nv + 1);
    for (i64 t = 0; t < nt; t++) { const double *O = TO + 9 * t; double a[3] = { O[3] - O[0], O[4] - O[1], O[5] - O[2] }, b[3] = { O[6] - O[0], O[7] - O[1], O[8] - O[2] }; cross3(a, b, n0 + 3 * t); l0[t] = norm3(n0 + 3 * t); }
    i64 rounds = 0, cut = 0; st[2] = st[3] = 0;
    for (int rnd = 0; rnd < 40; rnd++) {
        for (i64 v = 0; v < nv; v++) for (int c = 0; c < 3; c++) X[3 * v + c] = start[3 * v + c] + D[3 * v + c] * scale[v];
        i64 nh = 0, nf = 0;
        #pragma omp parallel for schedule(static) reduction(+:nh) if(ne > 4096)
        for (i64 e = 0; e < ne; e++) { bend(X, TA + 3 * e, TB + 3 * e, b1 + e, ok1 + e); hol[e] = ok0[e] && ok1[e] && (b1[e] > b0[e] + tol); nh += hol[e]; }
        #pragma omp parallel for schedule(static) reduction(+:nf) if(nt > 4096)
        for (i64 t = 0; t < nt; t++) {
            const double *p0 = X + 3 * T[3 * t], *p1 = X + 3 * T[3 * t + 1], *p2 = X + 3 * T[3 * t + 2]; double a[3] = { p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2] }, b[3] = { p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2] }, n1[3];
            cross3(a, b, n1); double l1 = norm3(n1); fold[t] = (l0[t] > 1e-9) && (dot3(n0 + 3 * t, n1) < FOLD * l0[t] * l1); nf += fold[t];
        }
        if (rnd == 0) { st[2] = nh; st[3] = nf; }
        memset(mark, 0, nv);
        for (i64 e = 0; e < ne; e++) if (hol[e]) { mark[TA[3 * e]] = mark[TA[3 * e + 1]] = mark[TA[3 * e + 2]] = 1; mark[TB[3 * e + 2]] = 1; }
        for (i64 t = 0; t < nt; t++) if (fold[t]) mark[T[3 * t]] = mark[T[3 * t + 1]] = mark[T[3 * t + 2]] = 1;
        i64 nm = 0;
        for (i64 v = 0; v < nv; v++) { mark[v] = mark[v] && scale[v] > 0; nm += mark[v]; }
        if (!nm) break;
        rounds++; cut += nm;
        for (i64 v = 0; v < nv; v++) if (mark[v]) scale[v] = rnd < 16 ? scale[v] * 0.5 : 0.0;
    }
    for (i64 v = 0; v < nv; v++) for (int c = 0; c < 3; c++) X[3 * v + c] = start[3 * v + c] + D[3 * v + c] * scale[v];
    i64 left = 0;
    #pragma omp parallel for schedule(static) reduction(+:left) if(ne > 4096)
    for (i64 e = 0; e < ne; e++) { double b; unsigned char ok; bend(X, TA + 3 * e, TB + 3 * e, &b, &ok); left += ok0[e] && ok && (b > b0[e] + tol); }
    st[0] = rounds; st[1] = cut; st[4] = left;
    free(n0); free(l0); free(b1); free(ok1); free(hol); free(fold); free(mark); return 0;
}

/* ---------------------------------------------------------------- (4.) flat stays coarse
   per group: the pieces' corners vi (n x k) and uncut places O; a polygon (nper pieces) is flat when every piece corner's distance across the
   piece, |((Xn[vi] - O) * nn).sum(2)| with nn = cross(O1 - O0, O2 - O0) / np.maximum(norm, 1e-12), stays under FLAT; up to 4 rounds with the
   corners of the flat polygons back at start (Xn); X = np.where(back, start, X). flat[g] per polygon of the group (at foff[g]); -> how many flat */
EXPORT i64 ro_flat(i64 nv, const double *start, double *X, int ng, const int *ks, const i64 *ns, const i64 *const *vis, const double *const *Os, i64 nper, double FLAT, unsigned char *flat, const i64 *foff)
{
    unsigned char *back = (unsigned char *)calloc(nv + 1, 1), *nb = (unsigned char *)malloc(nv + 1); double *Xn = (double *)malloc(sizeof(double) * 3 * (nv + 1));
    for (int rnd = 0; rnd < 4; rnd++) {
        for (i64 v = 0; v < nv; v++) for (int c = 0; c < 3; c++) Xn[3 * v + c] = back[v] ? start[3 * v + c] : X[3 * v + c];
        for (int g = 0; g < ng; g++) {
            int k = ks[g]; i64 npoly = ns[g] / nper;
            #pragma omp parallel for schedule(static) if(npoly > 1024)
            for (i64 f = 0; f < npoly; f++) {
                double mx = -INFINITY; int nan_ = 0;
                for (i64 p = f * nper; p < (f + 1) * nper; p++) {
                    const double *O = Os[g] + 3 * k * p; double a[3] = { O[3] - O[0], O[4] - O[1], O[5] - O[2] }, b[3] = { O[6] - O[0], O[7] - O[1], O[8] - O[2] }, nn[3];
                    cross3(a, b, nn); double l = npmax(norm3(nn), 1e-12); for (int c = 0; c < 3; c++) nn[c] /= l;
                    for (int c = 0; c < k; c++) {
                        const double *x = Xn + 3 * vis[g][k * p + c], *o = O + 3 * c; double d[3] = { x[0] - o[0], x[1] - o[1], x[2] - o[2] }, s = fabs(dot3(d, nn));
                        if (s != s) nan_ = 1; else if (s > mx) mx = s;
                    }
                }
                flat[foff[g] + f] = !nan_ && mx < FLAT;
            }
        }
        memset(nb, 0, nv);
        for (int g = 0; g < ng; g++) { int k = ks[g]; for (i64 p = 0; p < ns[g]; p++) if (flat[foff[g] + p / nper]) for (int c = 0; c < k; c++) nb[vis[g][k * p + c]] = 1; }
        int same = !memcmp(nb, back, nv); memcpy(back, nb, nv);
        if (same) break;
    }
    i64 nflat = 0;
    for (int g = 0; g < ng; g++) for (i64 f = 0; f < ns[g] / nper; f++) nflat += flat[foff[g] + f];
    for (i64 v = 0; v < nv; v++) if (back[v]) for (int c = 0; c < 3; c++) X[3 * v + c] = start[3 * v + c];
    free(back); free(nb); free(Xn); return nflat;
}

/* np.linalg.norm(X - start, axis=1) */
EXPORT void ro_moves(i64 nv, const double *X, const double *start, double *out) { for (i64 v = 0; v < nv; v++) { double d[3] = { X[3 * v] - start[3 * v], X[3 * v + 1] - start[3 * v + 1], X[3 * v + 2] - start[3 * v + 2] }; out[v] = norm3(d); } }
/* X[vi] (n indices -> n x 3) */
EXPORT void ro_gather(i64 n, const i64 *vi, const double *X, double *out) { for (i64 i = 0; i < n; i++) memcpy(out + 3 * i, X + 3 * vi[i], 24); }

/* ---------------------------------------------------------------- _emit's arrays
   per piece of one group: whether it has 3 distinct corners at np.round(P, 3) (good), and the edge stretch ratios l1 / l0 of its sides where
   l0 > 1e-6 (np.linalg.norm of O and P sides), all first sides of the group, then the second ... (ratio out; -> how many) */
EXPORT i64 ro_stretch(i64 n, int k, const double *O, const double *Pk, double *ratio)
{
    i64 m = 0;
    for (int a = 0; a < k; a++)
        for (i64 p = 0; p < n; p++) {
            const double *o0 = O + 3 * (k * p + a), *o1 = O + 3 * (k * p + (a + 1) % k), *p0 = Pk + 3 * (k * p + a), *p1 = Pk + 3 * (k * p + (a + 1) % k);
            double d0[3] = { o1[0] - o0[0], o1[1] - o0[1], o1[2] - o0[2] }, d1[3] = { p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2] }, l0 = norm3(d0), l1 = norm3(d1);
            if (l0 > 1e-6) ratio[m++] = l1 / npmax(l0, 1e-9);
        }
    return m;
}
/* the stretch figures' two counts (2026-10-16): out[0] = how many r with |r - 1| <= 0.10, out[1] = how many r > 1.25 (Python's
   sum(1 for v in sr if abs(v - 1) <= 0.10) and sum(1 for v in sr if v > 1.25): the same comparisons, a NaN in neither) */
EXPORT void ro_tally(i64 n, const double *r, i64 *out)
{
    i64 a = 0, b = 0;
    for (i64 i = 0; i < n; i++) { if (fabs(r[i] - 1.0) <= 0.10) a++; if (r[i] > 1.25) b++; }
    out[0] = a; out[1] = b;
}
/* the good pieces for the light-map table: 4 corners a piece (a triangle's last one twice, as the mesh writer has it), their places X and
   their places AB in the polygon's square -> how many */
EXPORT i64 ro_patch(i64 n, int k, const double *X, const double *AB, const unsigned char *good, double *PG, double *PA)
{
    i64 m = 0;
    for (i64 p = 0; p < n; p++) {
        if (!good[p]) continue;
        for (int c = 0; c < 4; c++) { int cc = c < k ? c : 2; memcpy(PG + 12 * m + 3 * c, X + 3 * (k * p + cc), 24); memcpy(PA + 8 * m + 2 * c, AB + 2 * (k * p + cc), 16); }
        m++;
    }
    return m;
}
static inline double npround3(double x) { return nearbyint(x * 1000.0) / 1000.0; }      /* np.round(x, 3) */
EXPORT void ro_good(i64 n, int k, const double *Pk, const unsigned char *skip, unsigned char *good)
{
    for (i64 p = 0; p < n; p++) {
        if (skip && skip[p]) { good[p] = 0; continue; }
        double r[4][3]; int distinct = 1;
        for (int a = 0; a < k; a++) for (int c = 0; c < 3; c++) r[a][c] = npround3(Pk[3 * (k * p + a) + c]);
        for (int a = 1; a < k; a++) { int seen = 0; for (int b = 0; b < a; b++) if (r[a][0] == r[b][0] && r[a][1] == r[b][1] && r[a][2] == r[b][2]) seen = 1; distinct += !seen; }
        good[p] = distinct >= 3;
    }
}
