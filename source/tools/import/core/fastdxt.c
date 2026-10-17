/* fastdxt.c - build_classic.dxt1_rgb in C, on every core (fastdxt.py loads it; compiled with gcc on first use).
   Nothing here decides anything new: every block gets the bytes the numpy code gives it.
     - a block's two end colours are its brightest and its darkest texel (sum of the three channels; the first of equals), holes not counted ;
     - a block without holes: c0 > c1, four colours (c0, c1, (2 c0 + c1) / 3, (c0 + 2 c1) / 3 on the 5-6-5 values widened to 8 bits) ; when both
       ends are the same 5-6-5 number c0 is raised by one (or c1 lowered when c0 is 0xFFFF) so that the block stays in four-colour mode ;
     - a block with holes: c0 <= c1, three colours (c0, c1, (c0 + c1) / 2), index 3 = see-through, and the holes take index 3 ;
     - every texel takes the nearest of the block's colours (squared distance over the channels, the first of equals).
   Measured 2026-10-13 on a 2048 x 2048 light-map page: numpy 0.42 s, here 0.005 s on 8 threads, the same bytes (and on 330 small pictures with
   and without holes, flat blocks, greys and ramps). */
#include <stdint.h>
#include <string.h>
#include <omp.h>
#define EXPORT __declspec(dllexport)

static inline int c565(const int *c) { return ((c[0] >> 3) << 11) | ((c[1] >> 2) << 5) | (c[2] >> 3); }
static inline void un565(int v, int *p) { p[0] = ((v >> 11) & 31) * 255 / 31; p[1] = ((v >> 5) & 63) * 255 / 63; p[2] = (v & 31) * 255 / 31; }

/* img: h x w x 3 bytes (h, w multiples of 4) ; hole: h x w bytes (0 / 1) or NULL ; out: (h / 4) * (w / 4) blocks of 8 bytes */
EXPORT void dxt1_rgb(const uint8_t *img, int h, int w, const uint8_t *hole, uint8_t *out)
{
    int bw = w / 4, bh = h / 4;
    #pragma omp parallel for schedule(static)
    for (int by = 0; by < bh; by++) {
        for (int bx = 0; bx < bw; bx++) {
            int b[16][3], m[16], lum[16], anyh = 0;
            for (int y = 0; y < 4; y++) for (int x = 0; x < 4; x++) {
                const uint8_t *s = img + ((size_t)(by * 4 + y) * w + (bx * 4 + x)) * 3; int k = y * 4 + x;
                b[k][0] = s[0]; b[k][1] = s[1]; b[k][2] = s[2]; lum[k] = s[0] + s[1] + s[2];
                m[k] = hole ? (hole[(size_t)(by * 4 + y) * w + (bx * 4 + x)] != 0) : 0; anyh |= m[k];
            }
            int ihi = 0, ilo = 0, vhi = m[0] ? -1 : lum[0], vlo = m[0] ? 99999 : lum[0];
            for (int k = 1; k < 16; k++) {
                int a = m[k] ? -1 : lum[k], z = m[k] ? 99999 : lum[k];
                if (a > vhi) { vhi = a; ihi = k; }
                if (z < vlo) { vlo = z; ilo = k; }
            }
            int ch = c565(b[ihi]), cl = c565(b[ilo]), mx = ch > cl ? ch : cl, mn = ch > cl ? cl : ch;
            int c0 = anyh ? mn : mx, c1 = anyh ? mx : mn, same = (c0 == c1) && !anyh;
            if (same && c0 < 0xffff) c0 = c0 + 1;
            if (same && c0 == 0xffff && c1 == 0xffff) c1 = 0xfffe;
            int pal[4][3]; un565(c0, pal[0]); un565(c1, pal[1]);
            for (int a = 0; a < 3; a++) {
                pal[2][a] = anyh ? (pal[0][a] + pal[1][a]) / 2 : (2 * pal[0][a] + pal[1][a]) / 3;
                pal[3][a] = anyh ? 0 : (pal[0][a] + 2 * pal[1][a]) / 3;
            }
            uint32_t bits = 0;
            for (int k = 0; k < 16; k++) {
                int ix = 0; long long best = -1;
                for (int q = 0; q < 4; q++) {
                    long long d;
                    if (q == 3 && anyh) d = 1000000000LL;
                    else { int d0 = b[k][0] - pal[q][0], d1 = b[k][1] - pal[q][1], d2 = b[k][2] - pal[q][2]; d = (long long)d0 * d0 + (long long)d1 * d1 + (long long)d2 * d2; }
                    if (best < 0 || d < best) { best = d; ix = q; }
                }
                if (m[k]) ix = 3;
                bits |= (uint32_t)ix << (2 * k);
            }
            uint8_t *o = out + ((size_t)by * bw + bx) * 8;
            o[0] = (uint8_t)(c0 & 255); o[1] = (uint8_t)(c0 >> 8); o[2] = (uint8_t)(c1 & 255); o[3] = (uint8_t)(c1 >> 8);
            o[4] = (uint8_t)(bits & 255); o[5] = (uint8_t)((bits >> 8) & 255); o[6] = (uint8_t)((bits >> 16) & 255); o[7] = (uint8_t)(bits >> 24);
        }
    }
}

/* build_classic.make_texture's mip chain and its DXT1 blocks (2026-10-16; was a numpy loop per level). rgb = the picture after vivid,
   h x w (both powers of two: the caller checks), hole = h x w bytes for the top level or NULL. The numpy lines it replaces:
     g = rgb.astype(np.float32)
     loop: pad = np.zeros((max(4, hh), max(4, ww), 3), np.float32); pad[:hh, :ww] = g; rows / columns below 4 repeat the last one
           blocks += dxt1_rgb(np.clip(pad, 0, 255).astype(np.uint8), hole on the first level)
           until 1 x 1: g = (g[0::2] + g[1::2]) / 2 (rows, when more than one), then g = (g[:, 0::2] + g[:, 1::2]) / 2 (columns)
   in float: a float32 sum, / 2 (no extra precision on x86-64); the clip as np.clip (min of max), the byte by truncation as astype.
   -> the levels' blocks one after the other in out, the number of levels; *first = the top level's length */
EXPORT int dxt1_mips(const uint8_t *rgb, int h, int w, const uint8_t *hole, uint8_t *out, int *first)
{
    int hh = h, ww = w, n = 0, H0 = h < 4 ? 4 : h, W0 = w < 4 ? 4 : w; size_t o = 0;
    float *g = (float *)malloc(sizeof(float) * (size_t)h * w * 3), *t = (float *)malloc(sizeof(float) * (size_t)h * w * 3); uint8_t *pad = (uint8_t *)malloc((size_t)H0 * W0 * 3);
    for (size_t i = 0; i < (size_t)h * w * 3; i++) g[i] = (float)rgb[i];
    for (;;) {
        int H = hh < 4 ? 4 : hh, W = ww < 4 ? 4 : ww;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                const float *s = g + ((size_t)(y < hh ? y : hh - 1) * ww + (x < ww ? x : ww - 1)) * 3; uint8_t *d = pad + ((size_t)y * W + x) * 3;
                for (int c = 0; c < 3; c++) { float v = s[c]; v = v > 0.0f ? v : 0.0f; v = v < 255.0f ? v : 255.0f; d[c] = (uint8_t)v; }
            }
        dxt1_rgb(pad, H, W, n == 0 ? hole : NULL, out + o);
        size_t len = (size_t)(H / 4) * (W / 4) * 8; if (n == 0) *first = (int)len; o += len; n++;
        if (hh == 1 && ww == 1) break;
        int nh = hh > 1 ? hh / 2 : 1, nw = ww > 1 ? ww / 2 : 1;
        if (hh > 1) { for (int y = 0; y < nh; y++) for (int x = 0; x < ww * 3; x++) t[(size_t)y * ww * 3 + x] = (g[(size_t)(2 * y) * ww * 3 + x] + g[(size_t)(2 * y + 1) * ww * 3 + x]) / 2.0f; }
        else memcpy(t, g, sizeof(float) * (size_t)ww * 3);
        if (ww > 1) { for (int y = 0; y < nh; y++) for (int x = 0; x < nw; x++) for (int c = 0; c < 3; c++) g[((size_t)y * nw + x) * 3 + c] = (t[((size_t)y * ww + 2 * x) * 3 + c] + t[((size_t)y * ww + 2 * x + 1) * 3 + c]) / 2.0f; }
        else memcpy(g, t, sizeof(float) * (size_t)nh * 3);
        hh = nh; ww = nw;
    }
    free(g); free(t); free(pad); return n;
}
EXPORT int fd_threads(void) { return omp_get_max_threads(); }
