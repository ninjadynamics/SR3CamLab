/* rtg5prep.c - what numpy did around the rays in rt_bake_game5.py, in C (2026-10-15, kb 31: the stack without numpy).
   rtg5.c casts the rays; this file builds what they are given and stores what they found:
     rp_tris, rp_keep        the scene's triangles out of the dump's faces; the kept ones (no tree or lamp boards) and their bounds
     rp_edges                the edges that belong to one polygon only (the skirts under hanging wall feet)
     rp_normals, rp_dot3     the triangles' normals; a normal @ the sun, @ the design direction
     rp_grid, rp_carpage     a car page's texel centres; the page's bytes from lm5_cars' answers
     rp_rects, rp_cells      per rectangle its sides in metres, distance from the road and lattice; the lattice's cells
     rp_texels, rp_angles, rp_facing, rp_pick, rp_merge, rp_store, rp_perpoly
                             per batch of texels: their places, their fan turns, the facing, the other side of polygons the road never
                             sees, the bytes; and the per-polygon table of pack.npz
   Every number is the numpy code's, in numpy's order; each function quotes the numpy lines it replaced. Built with -ffp-contract=off
   (cbuild.py FOC: a fused multiply-add rounds differently from numpy's separate steps), never with -ffast-math.
   numpy 1.24.3's orders, measured on the author's PC (kb 31): np.linalg.norm(A, axis=1) of an (n, 3) array is sqrt((x*x + y*y) + z*z);
   A @ s (matrix x vector, OpenBLAS on 1 to 16 threads) is (p0 + p2) + p1; a sum over a few corners adds them one after the other from 0;
   np.round is rint (half to even); np.cos / np.sin are the C runtime's (ucrtbase.dll), so rp_angles calls those very functions.
   Why C and not numpy: the toolchain zip no longer carries numpy for this process, and every loop here runs on every core. */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <omp.h>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#define EXPORT __declspec(dllexport)
typedef long long i64;

extern void lm5_mind(const double *X, i64 n, const double *C, i64 m, double *out);           /* rtg5.c */

static inline void cross3(const double *a, const double *b, double *c) { c[0] = a[1] * b[2] - a[2] * b[1]; c[1] = a[2] * b[0] - a[0] * b[2]; c[2] = a[0] * b[1] - a[1] * b[0]; }
static inline double clip01(double x) { return x < 0.0 ? 0.0 : (x > 1.0 ? 1.0 : x); }          /* np.clip(x, 0, 1): a NaN passes */
static inline float clip01f(float x) { return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x); }
#define MATVEC3(a, s)  (0.0 + (((a)[0] * (s)[0] + (a)[2] * (s)[2]) + (a)[1] * (s)[1]))      /* A @ s, OpenBLAS's order, added to y = 0 (a -0.0 comes out +0.0) */

/* ------------------------------------------------------------------ the scene's triangles
   As the game draws a face: one of four corners is two triangles, along corners 0 - 2.
     q_ = NC >= 4; TI[ts_] = FST[:, None] + [0, 1, 2]; TI[ts_[q_] + 1] = FST[q_][:, None] + [0, 2, 3]
     T = CO[TI]; TU = UO[TI]; TM = np.repeat(FM, nt_); ONE0 = np.repeat(FONE, nt_)
   nf faces: FST first corner, NC corners, FM material, FONE (the road sees it on its winding side only); CO[3 * corners], UO[2 * corners].
   -> T[9 * ntri], TU[6 * ntri], TM[ntri], ONE0[ntri], TF[ntri] the face each comes from (arrays sized by the caller). Returns ntri. */
EXPORT i64 rp_tris(i64 nf, const i64 *FST, const i64 *NC, const int *FM, const unsigned char *FONE, const double *CO, const double *UO,
                   double *T, double *TU, int *TM, unsigned char *ONE0, int *TF)
{
    static const int C[2][3] = { { 0, 1, 2 }, { 0, 2, 3 } };
    i64 t = 0;
    for (i64 f = 0; f < nf; f++)
        for (int q = 0; q < (NC[f] >= 4 ? 2 : 1); q++, t++) {
            for (int c = 0; c < 3; c++) {
                i64 k = FST[f] + C[q][c];
                memcpy(T + 9 * t + 3 * c, CO + 3 * k, 3 * sizeof(double)); memcpy(TU + 6 * t + 2 * c, UO + 2 * k, 2 * sizeof(double));
            }
            TM[t] = FM[f]; ONE0[t] = FONE[f]; TF[t] = (int)f;
        }
    return t;
}

/* keep = not a tree or lamp board:  T[keep], TU[keep], TM[keep], ONE0[keep] ; lo = T[keep].reshape(-1, 3).min(0), hi = .max(0)
   (np.min / np.max pass a NaN on, so these do). Returns how many were kept. */
EXPORT i64 rp_keep(i64 n, const unsigned char *keep, const double *T, const double *TU, const int *TM, const unsigned char *ONE0,
                   double *Tk, double *TUk, int *TMk, unsigned char *ONEk, double *lo, double *hi)
{
    i64 k = 0;
    for (int a = 0; a < 3; a++) { lo[a] = INFINITY; hi[a] = -INFINITY; }
    for (i64 i = 0; i < n; i++) {
        if (!keep[i]) continue;
        memcpy(Tk + 9 * k, T + 9 * i, 9 * sizeof(double)); memcpy(TUk + 6 * k, TU + 6 * i, 6 * sizeof(double)); TMk[k] = TM[i]; ONEk[k] = ONE0[i];
        for (int c = 0; c < 9; c++) {
            double v = T[9 * i + c]; int a = c % 3;
            if (!isnan(lo[a]) && (isnan(v) || v < lo[a])) lo[a] = v;
            if (!isnan(hi[a]) && (isnan(v) || v > hi[a])) hi[a] = v;
        }
        k++;
    }
    return k;
}

/* ------------------------------------------------------------------ the edges that belong to ONE polygon (skirts)
   In the order a walk over the faces first meets them. A corner's place to 5 mm is one whole number, an edge the pair of its ends' numbers:
     kf_ = np.where((NC[fi_] == 4) & (CO[FST[fi_] + 2] != CO[np.minimum(FST[fi_] + 3, len(CO) - 1)]).any(1), 4, 3)
     KQ = np.rint(CO * 200).astype(np.int64) + (1 << 20); assert KQ.min() >= 0 and KQ.max() < (1 << 21); pk_ = (KQ[:, 0] << 42) | (KQ[:, 1] << 21) | KQ[:, 2]
     the edges (FST + j, FST + (j + 1) % kf), j < kf, face by face ; those whose two ends have one number dropped ; e2_ = (lower, higher)
     o_ = np.lexsort((np.arange(len(e2_)), e2_[:, 1], e2_[:, 0])) ; once_ = np.sort(the places of the groups of one)
   Here: the same sort (qsort on lower, higher, place), the groups of one marked, read back in place order.
   fi[nfi] the faces looked at. -> per once-edge ia, ib (its corners), ef (its face), ek (that face's kf), arrays of 4 * nfi.
   Returns how many; -1 when a corner lies outside the 21-bit range (numpy's assert, over every corner as there). */
typedef struct { i64 a, b, pos; } edge_t;
static int edge_cmp(const void *x, const void *y)
{
    const edge_t *p = (const edge_t *)x, *q = (const edge_t *)y;
    if (p->a != q->a) return p->a < q->a ? -1 : 1;
    if (p->b != q->b) return p->b < q->b ? -1 : 1;
    return (p->pos > q->pos) - (p->pos < q->pos);
}
EXPORT i64 rp_edges(i64 nfi, const i64 *fi, const i64 *FST, const i64 *NC, const double *CO, i64 nco, i64 *ia, i64 *ib, i64 *ef, i64 *ek)
{
    i64 *pk = (i64 *)malloc((size_t)(nco ? nco : 1) * sizeof(i64)); int bad = 0;
    #pragma omp parallel for schedule(static) reduction(|: bad)
    for (i64 i = 0; i < nco; i++) {
        i64 k[3];
        for (int a = 0; a < 3; a++) { k[a] = (i64)rint(CO[3 * i + a] * 200.0) + (1 << 20); bad |= k[a] < 0 || k[a] >= (1 << 21); }
        pk[i] = (k[0] << 42) | (k[1] << 21) | k[2];
    }
    if (bad) { free(pk); return -1; }
    size_t cap = (size_t)(4 * nfi ? 4 * nfi : 1);
    edge_t *E = (edge_t *)malloc(cap * sizeof(edge_t)); i64 *EA = (i64 *)malloc(cap * sizeof(i64)), *EB = (i64 *)malloc(cap * sizeof(i64)), *EF = (i64 *)malloc(cap * sizeof(i64));
    int *EK = (int *)malloc(cap * sizeof(int)); unsigned char *once = (unsigned char *)calloc(cap, 1); i64 m = 0, out = 0;
    for (i64 j = 0; j < nfi; j++) {
        i64 f = fi[j], s = FST[f], c3 = s + 3 < nco - 1 ? s + 3 : nco - 1; int kf = 3;
        if (NC[f] == 4) { const double *p2 = CO + 3 * (s + 2), *p3 = CO + 3 * c3; if (p2[0] != p3[0] || p2[1] != p3[1] || p2[2] != p3[2]) kf = 4; }
        for (int c = 0; c < kf; c++) {
            i64 a = s + c, b = s + (c + 1) % kf;
            if (pk[a] == pk[b]) continue;
            E[m].a = pk[a] < pk[b] ? pk[a] : pk[b]; E[m].b = pk[a] < pk[b] ? pk[b] : pk[a]; E[m].pos = m;
            EA[m] = a; EB[m] = b; EF[m] = f; EK[m] = kf; m++;
        }
    }
    qsort(E, (size_t)m, sizeof(edge_t), edge_cmp);
    for (i64 g = 0; g < m; ) {
        i64 h = g + 1;
        while (h < m && E[h].a == E[g].a && E[h].b == E[g].b) h++;
        if (h - g == 1) once[E[g].pos] = 1;
        g = h;
    }
    for (i64 p = 0; p < m; p++) if (once[p]) { ia[out] = EA[p]; ib[out] = EB[p]; ef[out] = EF[p]; ek[out] = EK[p]; out++; }
    free(pk); free(E); free(EA); free(EB); free(EF); free(EK); free(once);
    return out;
}

/* ------------------------------------------------------------------ normals and products
   TN = np.cross(TA[:, 1] - TA[:, 0], TA[:, 2] - TA[:, 0]); TN /= np.maximum(np.linalg.norm(TN, axis=1), 1e-12)[:, None]
   (np.cross: cp0 = a1 * b2 - a2 * b1 ... each product rounded on its own; the norm (x*x + y*y) + z*z; np.maximum passes a NaN on) */
EXPORT void rp_normals(i64 n, const double *TA, double *TN)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        const double *t = TA + 9 * i; double a[3], b[3], c[3];
        for (int k = 0; k < 3; k++) { a[k] = t[3 + k] - t[k]; b[k] = t[6 + k] - t[k]; }
        cross3(a, b, c);
        double l = sqrt((c[0] * c[0] + c[1] * c[1]) + c[2] * c[2]), d = isnan(l) ? l : (l > 1e-12 ? l : 1e-12);
        for (int k = 0; k < 3; k++) TN[3 * i + k] = c[k] / d;
    }
}

/* out = A @ s for an (n, 3) A: 0 + ((a0 * s0 + a2 * s2) + a1 * s1), OpenBLAS's matrix x vector - numpy's own answer on 1 to 16 threads
   (dgemv adds each row's sum to y, which it set to 0 first: so a row summing to -0.0 gives +0.0; 2 of 408,164 normals on Mountain).
   (kb 31: on 32 threads some thread chunks of a big product take another kernel and other last bits, so numpy's answer depends on the
   PC; this is the fixed formula, the same bits on every PC. The bake's files are the same either way, checked 2026-10-15.) */
EXPORT void rp_dot3(i64 n, const double *A, const double *s, double *out)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) out[i] = MATVEC3(A + 3 * i, s);
}

/* ------------------------------------------------------------------ the cars' pages
   gx, gz = np.meshgrid(X, Z); np.stack([gx.ravel(), gz.ravel()], 1): row r (z), column c (x) -> XZ[2 * (r * res + c)] = (X[c], Z[r]) */
EXPORT void rp_grid(int res, const double *X, const double *Z, double *XZ)
{
    for (int r = 0; r < res; r++) for (int c = 0; c < res; c++) { XZ[2 * ((i64)r * res + c)] = X[c]; XZ[2 * ((i64)r * res + c) + 1] = Z[r]; }
}

/* A car page from lm5_cars' answers G, R, ASK (res x res) -> img[res * res * 3] (red, green, blue 0) ; returns nshd, the texels asked
   that are in shadow (int(((G64 < 0.5) & (ASK > 0)).sum())).
     Gm = G64.astype(np.float32); Rm = R64.astype(np.float32)
     def blur(a_): q_ = np.pad(a_, 1, mode='edge'); return sum(q_[1 + dy:1 + dy + CAR_RES, 1 + dx:1 + dx + CAR_RES] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
     Gi = blur(Gm); Ri = blur(Rm); Gi[:4] = 1; Gi[-4:] = 1; Gi[:, :4] = 1; Gi[:, -4:] = 1; Ri[:4] = 0; ... (the outermost four texels: open sun)
     imgs[k, ..., 0] = np.round(np.clip(Ri, 0, 1) * 255); imgs[k, ..., 1] = np.round(np.clip(Gi, 0, 1) * 255)
   float32 all through, as numpy 1.24 keeps a float32 array float32 with a Python number: Python's sum starts from 0 and adds the nine
   shifted pages in that order, then / 9 ; clip, * 255, rint (half to even). */
EXPORT i64 rp_carpage(int res, const double *G, const double *R, const unsigned char *ASK, unsigned char *img)
{
    i64 nsh = 0;
    #pragma omp parallel for schedule(static) reduction(+: nsh)
    for (int y = 0; y < res; y++)
        for (int x = 0; x < res; x++) {
            i64 i = (i64)y * res + x; float g = 0.0f, r = 0.0f;
            nsh += G[i] < 0.5 && ASK[i] > 0;
            for (int dy = -1; dy <= 1; dy++) {
                int yy = y + dy < 0 ? 0 : (y + dy >= res ? res - 1 : y + dy);
                for (int dx = -1; dx <= 1; dx++) { int xx = x + dx < 0 ? 0 : (x + dx >= res ? res - 1 : x + dx); g += (float)G[(i64)yy * res + xx]; r += (float)R[(i64)yy * res + xx]; }
            }
            g = g / 9.0f; r = r / 9.0f;
            if (y < 4 || y >= res - 4 || x < 4 || x >= res - 4) { g = 1.0f; r = 0.0f; }
            img[3 * i] = (unsigned char)rintf(clip01f(r) * 255.0f); img[3 * i + 1] = (unsigned char)rintf(clip01f(g) * 255.0f); img[3 * i + 2] = 0;
        }
    return nsh;
}

/* ------------------------------------------------------------------ the rectangles
   n polygons: P[12 * n] four corners, AB[8 * n] their places in the rectangle's square, rinv[n] the rectangle of each (0 .. nr - 1, as
   np.unique(R, return_inverse=True) numbers them), U[n] the road never sees it, GRP[n] its material group, I[4 * n] the importer's brightness
   at its corners (I.astype(float)); cen[2 * m] the road's middle (every second point).
   -> per polygon: tri[n] (corners 2 and 3 are one place), dpoly[n] its distance from the road, sea[n], imean[n] ;
      per rectangle: cnt, first (its first polygon), lu, lv (its sides in metres), dr, un, grp, minext, multi, pn (lattice size), and
      roff[nr + 1] (where its lattice's cells start in CELL: two numbers a cell).
   The numpy lines, in the order done here:
     tri_p = np.linalg.norm(P[:, 2] - P[:, 3], axis=1) < 1e-9
     for X in [P.mean(1)] + [P[:, k] for k in range(4)]: d_p = min(d_p, distance from the road)       (lm5_mind, rtg5.c)
     sea_poly = (P[:, :, 1].max(1) < -0.3) & (P[:, :, 1].min(1) > -0.7)                 (= every corner below -0.3 and above -0.7, NaN too)
     Imean = I.mean(1)                                                                  (I.astype(float); ((0 + i0) + i1 + i2) + i3, / 4)
     cnt_r = np.bincount(rinv); first_r = np.full(nrect, len(P)); np.minimum.at(first_r, rinv, np.arange(len(P)))
     for j in range(4): dab = ABp[:, (j + 1) % 4] - ABp[:, j]; L_ = np.linalg.norm(P[:, (j + 1) % 4] - P[:, j], axis=1); ua = np.abs(dab[:, 0]); ub = np.abs(dab[:, 1])
         ma_ = (ua >= ub) & (ua > 1e-9); mb_ = (ub > ua) & (ub > 1e-9); np.maximum.at(lu_r, rinv[ma_], L_[ma_] / ua[ma_]); np.maximum.at(lv_r, rinv[mb_], L_[mb_] / ub[mb_])
     lu_r = np.where(lu_r > 1e-6, lu_r, np.maximum(lv_r, 0.05)); lv_r = np.where(lv_r > 1e-6, lv_r, np.maximum(lu_r, 0.05))
     d_r = np.full(nrect, 1e9); np.minimum.at(d_r, rinv, d_p); un_r = np.ones(nrect, bool); np.logical_and.at(un_r, rinv, U2); grp_r = GRP[first_r]
     ext_ = np.maximum(np.ptp(ABp[:, :, 0], axis=1), np.ptp(ABp[:, :, 1], axis=1)); minext = np.ones(nrect); np.minimum.at(minext, rinv, np.where(ext_ > 1e-9, ext_, 1.0))
     multi = (cnt_r > 1) | (minext < 0.999); pn_r = np.where(multi, np.clip(np.round(1.0 / minext), 1, 64), 0).astype(np.int32)
     roff[1:] = np.cumsum(2 * pn_r.astype(np.int64) ** 2) */
EXPORT void rp_rects(i64 n, const double *P, const double *AB, const i64 *rinv, i64 nr, const unsigned char *U, const int *GRP, const double *I,
                     const double *cen, i64 m, unsigned char *tri, double *dpoly, unsigned char *sea, double *imean,
                     i64 *cnt, i64 *first, double *lu, double *lv, double *dr, unsigned char *un, i64 *grp, double *minext, unsigned char *multi, int *pn, i64 *roff)
{
    double *X = (double *)malloc((size_t)(n ? n : 1) * 3 * sizeof(double));
    for (i64 i = 0; i < n; i++) dpoly[i] = 1e9;
    for (int k = -1; k < 4; k++) {                                     /* the corners' mean, then each corner */
        #pragma omp parallel for schedule(static)
        for (i64 i = 0; i < n; i++)
            for (int a = 0; a < 3; a++) {
                const double *p = P + 12 * i + a;
                X[3 * i + a] = k < 0 ? (((0.0 + p[0]) + p[3]) + p[6] + p[9]) / 4.0 : p[3 * k];
            }
        lm5_mind(X, n, cen, m, dpoly);
    }
    free(X);
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        const double *p = P + 12 * i; double dx = p[6] - p[9], dy = p[7] - p[10], dz = p[8] - p[11];
        tri[i] = sqrt((dx * dx + dy * dy) + dz * dz) < 1e-9;
        sea[i] = p[1] < -0.3 && p[4] < -0.3 && p[7] < -0.3 && p[10] < -0.3 && p[1] > -0.7 && p[4] > -0.7 && p[7] > -0.7 && p[10] > -0.7;
        imean[i] = ((((0.0 + I[4 * i]) + I[4 * i + 1]) + I[4 * i + 2]) + I[4 * i + 3]) / 4.0;
    }
    for (i64 r = 0; r < nr; r++) { cnt[r] = 0; first[r] = n; lu[r] = 0.0; lv[r] = 0.0; dr[r] = 1e9; un[r] = 1; minext[r] = 1.0; }
    for (i64 i = 0; i < n; i++) {                                      /* (the .at updates: one after the other, as numpy) */
        i64 r = rinv[i]; const double *p = P + 12 * i, *ab = AB + 8 * i;
        cnt[r]++; if (i < first[r]) first[r] = i;
        for (int j = 0; j < 4; j++) {
            int j1 = (j + 1) % 4; double ua = fabs(ab[2 * j1] - ab[2 * j]), ub = fabs(ab[2 * j1 + 1] - ab[2 * j + 1]);
            double ex = p[3 * j1] - p[3 * j], ey = p[3 * j1 + 1] - p[3 * j + 1], ez = p[3 * j1 + 2] - p[3 * j + 2], L = sqrt((ex * ex + ey * ey) + ez * ez);
            if (ua >= ub && ua > 1e-9) { double v = L / ua; if (!isnan(lu[r]) && (isnan(v) || v > lu[r])) lu[r] = v; }
            if (ub > ua && ub > 1e-9) { double v = L / ub; if (!isnan(lv[r]) && (isnan(v) || v > lv[r])) lv[r] = v; }
        }
        double d = dpoly[i]; if (!isnan(dr[r]) && (isnan(d) || d < dr[r])) dr[r] = d;
        un[r] = un[r] && U[i];
        double a0 = ab[0], a1 = ab[0], b0 = ab[1], b1 = ab[1];
        for (int c = 1; c < 4; c++) {                                  /* np.ptp: max - min (a NaN passes) */
            double a = ab[2 * c], b = ab[2 * c + 1];
            if (!isnan(a0) && (isnan(a) || a < a0)) a0 = a;
            if (!isnan(a1) && (isnan(a) || a > a1)) a1 = a;
            if (!isnan(b0) && (isnan(b) || b < b0)) b0 = b;
            if (!isnan(b1) && (isnan(b) || b > b1)) b1 = b;
        }
        double pa = a1 - a0, pb = b1 - b0, ext = (isnan(pa) || isnan(pb)) ? NAN : (pa > pb ? pa : pb), e = ext > 1e-9 ? ext : 1.0;
        if (!isnan(minext[r]) && (isnan(e) || e < minext[r])) minext[r] = e;
    }
    roff[0] = 0;
    for (i64 r = 0; r < nr; r++) {
        double a = lu[r], b = lv[r];
        lu[r] = a > 1e-6 ? a : (isnan(b) ? b : (b > 0.05 ? b : 0.05));
        lv[r] = b > 1e-6 ? b : (isnan(lu[r]) ? lu[r] : (lu[r] > 0.05 ? lu[r] : 0.05));
        grp[r] = first[r] < n ? GRP[first[r]] : 0;
        multi[r] = cnt[r] > 1 || minext[r] < 0.999;
        double q = rint(1.0 / minext[r]); q = q < 1.0 ? 1.0 : (q > 64.0 ? 64.0 : q);
        pn[r] = multi[r] ? (int)q : 0;
        roff[r + 1] = roff[r] + 2 * (i64)pn[r] * pn[r];
    }
}

/* The lattice's cells, and which half a rectangle draws (CELL comes filled with -1):
     cab = np.where(tri_p[:, None], ABp[:, :3].mean(1), ABp.mean(1)); pm_ = np.nonzero(multi[rinv])[0]; pnp = pn_r[rinv[pm_]].astype(np.int64)
     ci = np.clip(np.floor(cab[pm_, 0] * pnp).astype(np.int64), 0, pnp - 1); cj = np.clip(np.floor(cab[pm_, 1] * pnp).astype(np.int64), 0, pnp - 1)
     half_ = ((cab[pm_, 1] * pnp - cj) > (cab[pm_, 0] * pnp - ci)); base_ = roff[rinv[pm_]] + (cj * pnp + ci) * 2; tq_ = tri_p[pm_]
     CELL[base_[tq_] + half_[tq_]] = pm_[tq_]; CELL[base_[~tq_]] = pm_[~tq_]; CELL[base_[~tq_] + 1] = pm_[~tq_]
     above_ = np.zeros(nrect, bool); np.logical_or.at(above_, rinv, cab[:, 1] > cab[:, 0] + 1e-6); tri_r = np.where(multi, ~above_, tri_p[first_r])
   The three writes in numpy's order, a later one winning: the three-corner pieces, then the others' first halves, then their second. */
EXPORT void rp_cells(i64 n, const double *AB, const unsigned char *tri, const i64 *rinv, i64 nr, const unsigned char *multi, const int *pn, const i64 *roff,
                     const i64 *first, int *CELL, unsigned char *trir)
{
    double *cab = (double *)malloc((size_t)(n ? n : 1) * 2 * sizeof(double)); unsigned char *above = (unsigned char *)calloc((size_t)(nr ? nr : 1), 1);
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++)
        for (int a = 0; a < 2; a++) {
            const double *ab = AB + 8 * i + a;
            cab[2 * i + a] = tri[i] ? ((0.0 + ab[0]) + ab[2] + ab[4]) / 3.0 : (((0.0 + ab[0]) + ab[2] + ab[4]) + ab[6]) / 4.0;
        }
    for (int pass = 0; pass < 3; pass++)
        for (i64 i = 0; i < n; i++) {
            i64 r = rinv[i];
            if (!multi[r] || (pass == 0) != (tri[i] != 0)) continue;
            i64 q = pn[r]; double u = cab[2 * i] * (double)q, v = cab[2 * i + 1] * (double)q;
            i64 ci = (i64)floor(u), cj = (i64)floor(v); ci = ci < 0 ? 0 : (ci > q - 1 ? q - 1 : ci); cj = cj < 0 ? 0 : (cj > q - 1 ? q - 1 : cj);
            i64 base = roff[r] + (cj * q + ci) * 2;
            if (pass == 0) CELL[base + ((v - (double)cj) > (u - (double)ci))] = (int)i;
            else CELL[base + (pass == 2)] = (int)i;
        }
    for (i64 i = 0; i < n; i++) if (cab[2 * i + 1] > cab[2 * i] + 1e-6) above[rinv[i]] = 1;
    for (i64 r = 0; r < nr; r++) trir[r] = multi[r] ? !above[r] : tri[first[r]];
    free(cab); free(above);
}

/* ------------------------------------------------------------------ a batch of texels
   ii[nb] its rectangles in order, each nu x nv texels row by row:
     f = np.repeat(np.arange(len(ii)), cnt); loc = np.arange(tot_) - np.repeat(np.cumsum(cnt) - cnt, cnt)
     iu = loc % nu[ii][f]; iv = loc // nu[ii][f]; ri = ii[f]; k0 = (np.arange(tot_) + ntex).astype(float)
   -> ri, iu, iv, k0 [tot]; returns tot */
EXPORT i64 rp_texels(i64 nb, const i64 *ii, const int *nu, const int *nv, i64 ntex, int *ri, int *iu, int *iv, double *k0)
{
    i64 t = 0;
    for (i64 b = 0; b < nb; b++) {
        i64 r = ii[b], w = nu[r], c = w * nv[r];
        for (i64 l = 0; l < c; l++, t++) { ri[t] = (int)r; iu[t] = (int)(l % w); iv[t] = (int)(l / w); k0[t] = (double)(t + ntex); }
    }
    return t;
}

/* The fan turns of every texel's sky rays (light()):
     ang = ((k0 + turn / TURNS) * 0.618034) % 1.0 * 2 * math.pi; CA[:, turn] = np.cos(ang); SA[:, turn] = np.sin(ang)
   % 1.0 of a number >= 0 is x - floor(x), exact (numpy's remainder is fmod there, also exact). cos and sin are ucrtbase.dll's, the
   functions numpy calls: the compiler's or mingw's own could differ in the last bit. */
typedef double (__cdecl *crt1_t)(double);
static crt1_t crt_cos, crt_sin;
EXPORT void rp_angles(i64 m, const double *k0, int turns, double *CA, double *SA)
{
    if (!crt_cos) { HMODULE h = LoadLibraryA("ucrtbase.dll"); crt_sin = (crt1_t)GetProcAddress(h, "sin"); crt_cos = (crt1_t)GetProcAddress(h, "cos"); }
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < m; i++)
        for (int t = 0; t < turns; t++) {
            double x = (k0[i] + (double)t / (double)turns) * 0.618034, a = (x - floor(x)) * 2.0 * 3.141592653589793;
            CA[i * turns + t] = crt_cos(a); SA[i * turns + t] = crt_sin(a);
        }
}

/* facing(n):  ns = n @ SUN; face = np.clip((ns - 0.02) / 0.13, 0.0, 1.0); face = face * face * (3 - 2 * face)
               return np.clip((n @ design + 0.2) / 0.907, 0.0, 1.0) * face                      (n @ v as rp_dot3) */
EXPORT void rp_facing(i64 m, const double *NO, const double *SUN, const double *design, double *F)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < m; i++) {
        const double *n = NO + 3 * i; double face = clip01((MATVEC3(n, SUN) - 0.02) / 0.13);
        face = face * face * (3.0 - 2.0 * face);
        F[i] = clip01((MATVEC3(n, design) + 0.2) / 0.907) * face;
    }
}

/* u = U2[PO]: the texels whose point lies on a polygon the road never sees -> sel[] their numbers, and ri[u], iu[u], iv[u], k0[u]
   gathered for the other side's light; returns how many. */
EXPORT i64 rp_pick(i64 m, const int *PO, const unsigned char *U, const int *ri, const int *iu, const int *iv, const double *k0,
                   i64 *sel, int *ri2, int *iu2, int *iv2, double *k02)
{
    i64 k = 0;
    for (i64 i = 0; i < m; i++) if (U[PO[i]]) { sel[k] = i; ri2[k] = ri[i]; iu2[k] = iu[i]; iv2[k] = iv[i]; k02[k] = k0[i]; k++; }
    return k;
}

/* bet = (0.66 * V2 * F2 + 0.22 * A2 + B2.mean(1)) > (0.66 * V[u] * Fc[u] + 0.22 * A[u] + B[u].mean(1))
   for arr, alt in ((V, V2), (A, A2), (Fc, F2)): arr[u][bet] = alt[bet] ; B[u][bet] = B2[bet]          (B.mean(1): ((0 + b0) + b1) + b2, / 3) */
EXPORT void rp_merge(i64 k, const i64 *sel, double *V, double *A, double *B, double *F, const double *V2, const double *A2, const double *B2, const double *F2)
{
    #pragma omp parallel for schedule(static)
    for (i64 j = 0; j < k; j++) {
        i64 i = sel[j]; const double *b2 = B2 + 3 * j, *b = B + 3 * i;
        double o = ((0.66 * V2[j]) * F2[j] + 0.22 * A2[j]) + (((0.0 + b2[0]) + b2[1]) + b2[2]) / 3.0;
        double s = ((0.66 * V[i]) * F[i] + 0.22 * A[i]) + (((0.0 + b[0]) + b[1]) + b[2]) / 3.0;
        if (o > s) { V[i] = V2[j]; A[i] = A2[j]; F[i] = F2[j]; B[3 * i] = b2[0]; B[3 * i + 1] = b2[1]; B[3 * i + 2] = b2[2]; }
    }
}

/* sp = sea_poly[PO]; V[sp] = 1.0; A[sp] = 1.0; B[sp] = 0.0; Fc[sp] = 1.0; ir = Imean[PO]
   RAW[page[ri], y0[ri] + iv, x0[ri] + iu] = np.round(np.clip(np.c_[V, A, B * 4.0, Fc, ir], 0, 1) * 255).astype(np.uint8) */
EXPORT void rp_store(i64 m, const int *ri, const int *iu, const int *iv, const int *PO, const unsigned char *sea, const double *imean,
                     const double *V, const double *A, const double *B, const double *F, const int *page, const int *x0, const int *y0, int PAGE, unsigned char *RAW)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < m; i++) {
        int r = ri[i], p = PO[i], s = sea[p] != 0; double v[7];
        v[0] = s ? 1.0 : V[i]; v[1] = s ? 1.0 : A[i];
        for (int c = 0; c < 3; c++) v[2 + c] = (s ? 0.0 : B[3 * i + c]) * 4.0;
        v[5] = s ? 1.0 : F[i]; v[6] = imean[p];
        unsigned char *o = RAW + (((size_t)page[r] * PAGE + (size_t)(y0[r] + iv[i])) * PAGE + (size_t)(x0[r] + iu[i])) * 7;
        for (int c = 0; c < 7; c++) o[c] = (unsigned char)rint(clip01(v[c]) * 255.0);
    }
}

/* per POLYGON, as the importer's table wants it: page[rinv], x0[rinv], y0[rinv], nu[rinv], nv[rinv], d_r[rinv] */
EXPORT void rp_perpoly(i64 n, const i64 *rinv, const int *page, const int *x0, const int *y0, const int *nu, const int *nv, const double *dr,
                       int *opage, int *ox0, int *oy0, int *onu, int *onv, double *odr)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) { i64 r = rinv[i]; opage[i] = page[r]; ox0[i] = x0[r]; oy0[i] = y0[r]; onu[i] = nu[r]; onv[i] = nv[r]; odr[i] = dr[r]; }
}
