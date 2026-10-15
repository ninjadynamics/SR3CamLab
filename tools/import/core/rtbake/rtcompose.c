/* rt_compose_game.py's arithmetic: which light-map polygons are road, the light-map pages from the raw bake, the table's
 * keys. The same bits as the numpy version it replaced (2026-10-15; the numpy lines are quoted at each function), built
 * with -ffp-contract=off (cbuild.py FOC): a fused multiply-add would round differently from numpy's separate steps.
 * Why C and not numpy: the toolchain zip no longer carries numpy for this process, and the pages are 22 x 4 million
 * texels: one page per thread here, where numpy's version ran 8 pages at a time through temporary float arrays. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define EXPORT __declspec(dllexport)
typedef long long i64;

/* road[i] = 1 for a lying polygon whose corner mean (x, z) is within 9 m of the centre line (every second point of it).
 *   c = P.mean(1)[:, [0, 2]]
 *   lying = N[:, 1] / np.maximum(np.linalg.norm(N, axis=1), 1e-9) > 0.9
 *   d[li] = np.sqrt(((c[li, None] - cen[None, ::2]) ** 2).sum(2).min(1));   road = (d < 9.0) & lying
 * numpy's order, kept: the mean adds the corners one after another and divides by their number; the norm is
 * sqrt((x*x + y*y) + z*z); a distance is dx*dx + dz*dz; the smallest is taken, then its root. np.maximum and np.min
 * pass a NaN on, so they do here too. Returns the number of road polygons. */
EXPORT i64 rtc_road(const double *P, i64 n, int k, const double *N, const double *cen, i64 m, unsigned char *road) {
    i64 i, cnt = 0;
    #pragma omp parallel for schedule(dynamic, 512) reduction(+:cnt)
    for (i = 0; i < n; i++) {
        const double *nn = N + 3 * i, *p = P + (i64)k * 3 * i;
        double len = sqrt((nn[0] * nn[0] + nn[1] * nn[1]) + nn[2] * nn[2]), den = isnan(len) ? len : (len > 1e-9 ? len : 1e-9);
        double cx = p[0], cz = p[2], best = INFINITY; i64 j; int c;
        road[i] = 0;
        if (!(nn[1] / den > 0.9)) continue;
        for (c = 1; c < k; c++) { cx += p[3 * c]; cz += p[3 * c + 2]; }
        cx /= k; cz /= k;
        for (j = 0; j < m; j += 2) {
            double dx = cx - cen[2 * j], dz = cz - cen[2 * j + 1], s = dx * dx + dz * dz;
            if (isnan(s)) { best = s; break; }
            if (s < best) best = s;
        }
        if (sqrt(best) < 9.0) { road[i] = 1; cnt++; }
    }
    return cnt;
}

/* The pages, one per thread (numpy's one(p)):
 *   r = RAW[p].astype(np.float32) / 255.0
 *   V, A, B, F, I = r[..., 0], r[..., 1], r[..., 2:5] / 4.0, r[..., 5], np.maximum(r[..., 6], 0.05)
 *   L = (1 - AMB) * (V * F)[..., None] + AMB * (0.35 + 0.65 * A)[..., None] + BOUNCE * B
 *   lum = (L * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(2);  L[road] = lum[road][:, None]
 *   val = L / I[..., None];  page = np.round(np.clip(val, 0, 1) * 255).astype(np.uint8)
 * numpy 1.24 turns each Python float into a float32 before using it with a float32 array, so every constant below is
 * the float of the double and every step rounds to float, in numpy's order: (t1 + t2) + t3, the luminance sum
 * (p0 + p1) + p2, round half to even. road: the rectangles of the road polygons on the page, their sides rounded up to
 * whole 4 x 4 blocks and cut at the page edge (numpy's slices). Statistics for the log: texels over 1.02 and the mean
 * of the clipped light (its sum in double here; numpy summed in float32, so the logged mean may differ in its last
 * digit; nothing else uses it). */
EXPORT void rtc_pages(const unsigned char *raw, int npg, int side, const int *pg, const int *x0, const int *y0, const int *nu,
                      const int *nv, const unsigned char *road, i64 n, double AMB, double BOUNCE, unsigned char *pages,
                      i64 *over, double *lsum) {
    const float k255 = 255.0f, k4 = 4.0f, c1 = (float)(1.0 - AMB), cA = (float)AMB, c35 = 0.35f, c65 = 0.65f, cB = (float)BOUNCE,
                c05 = 0.05f, w0 = 0.2126f, w1 = 0.7152f, w2 = 0.0722f, lim = 1.02f;
    i64 npx = (i64)side * side; int p;
    #pragma omp parallel for schedule(dynamic, 1)
    for (p = 0; p < npg; p++) {
        unsigned char *mask = (unsigned char *)calloc((size_t)npx, 1); const unsigned char *R = raw + (i64)p * npx * 7;
        unsigned char *O = pages + (i64)p * npx * 3; i64 i, ov = 0; double ls = 0;
        for (i = 0; i < n; i++) {
            int ya, yb, xa, xb, y;
            if (!road[i] || pg[i] - 1 != p) continue;
            ya = y0[i]; yb = y0[i] + (nv[i] + 3) / 4 * 4; xa = x0[i]; xb = x0[i] + (nu[i] + 3) / 4 * 4;
            if (yb > side) yb = side;
            if (xb > side) xb = side;
            for (y = ya; y < yb; y++) if (xb > xa) memset(mask + (i64)y * side + xa, 1, (size_t)(xb - xa));
        }
        for (i = 0; i < npx; i++) {
            const unsigned char *r = R + 7 * i; float V = r[0] / k255, A = r[1] / k255, F = r[5] / k255, I = r[6] / k255, L[3], t1, t2;
            int c;
            if (!(I >= c05)) I = c05;
            t1 = c1 * (V * F); t2 = cA * (c35 + c65 * A);
            for (c = 0; c < 3; c++) L[c] = (t1 + t2) + cB * ((r[2 + c] / k255) / k4);
            if (mask[i]) { float lum = (L[0] * w0 + L[1] * w1) + L[2] * w2; L[0] = L[1] = L[2] = lum; }
            {
                float v0 = L[0] / I, v1 = L[1] / I, v2 = L[2] / I, mx = v0 > v1 ? v0 : v1;
                if (v2 > mx) mx = v2;
                if (mx > lim) ov++;
                for (c = 0; c < 3; c++) {
                    float v = c == 0 ? v0 : c == 1 ? v1 : v2, l = L[c];
                    v = v < 0.0f ? 0.0f : v > 1.0f ? 1.0f : v; O[3 * i + c] = (unsigned char)rintf(v * k255);
                    ls += l < 0.0f ? 0.0 : l > 1.0f ? 1.0 : (double)l;
                }
            }
        }
        free(mask);
        #pragma omp atomic
        *over += ov;
        #pragma omp critical
        *lsum += ls / (double)(npx * 3);
    }
}

/* The table's key of each polygon: its four corners to the millimetre (lightmap1995.key):
 *   np.round(P.reshape(-1, 12) * 1000.0).astype(np.int32)   (np.round = half to even, as rint) */
EXPORT void rtc_key(const double *P, i64 n, int32_t *K) {
    i64 i;
    #pragma omp parallel for schedule(static)
    for (i = 0; i < n * 12; i++) K[i] = (int32_t)rint(P[i] * 1000.0);
}
