/* livetest: pc_live on a scripted fake game, for live_lockstep.py (live_ps1.ps1 runs patches.ps1 on the same one).
 *   livetest <scenario.json> <game exe> <mod dir> <profiles.yaml> <trace out>
 * The fake game is the same as live_ps1.ps1's MockGame (keep the two alike):
 *   memory: bytes as written; a read that touches a byte never written fails (an unmapped page);
 *   alloc: 0x20000000, then every 0x10000 further, zeroed (the first is the camera block);
 *   a frame: each 1-byte read of 0x9D6E3C (the menus flag, the loop's first read of a pass) starts the next one: the popup
 *     count at block + 0x10 goes down by one, then the frame's writes (START and View Change are the game's own inputs
 *     0x9DBBA4 / 0x9DBB0C among them), time, keys and window in front; after the last
 *     frame the game has "exited" (the read fails, alive() is 0);
 *   the game's part: a 1 written at block + 0x2264 loads every video of the table 0x728630.. that has no handle (-1),
 *     handles from next_handle on; a non-zero value at block + 0x2270 opens video object (value - 1) on the name block +
 *     0x2274 points to (its name at 0xAD2F90 + 0x16C x object + 0xC, +4 = 1) and goes back to 0.
 * The trace: W <va> <keep> <bytes> | S | R | A <size> <va> | L <log line> | G grab / G save <file> <info> / G close | F <frame>
 * Built by live_lockstep.py with build.py's flags (32-bit, as the DLL); never shipped. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "patchcore.h"
#include "pc_json.h"
#include "blobs.h"

typedef struct Pg { unsigned va; struct Pg *next; unsigned char b[4096], d[4096]; } Pg;
static Pg *H[4096];
static Pg *page(unsigned va, int make) {
    unsigned k = (va >> 12) & 4095; Pg *p;
    for (p = H[k]; p; p = p->next) if (p->va == (va & ~4095u)) return p;
    if (!make) return NULL;
    p = (Pg *)calloc(1, sizeof *p); p->va = va & ~4095u; p->next = H[k]; H[k] = p; return p;
}
static int mread(unsigned va, void *dst, unsigned n) {
    unsigned i; unsigned char *o = (unsigned char *)dst;
    for (i = 0; i < n; i++) { Pg *p = page(va + i, 0); if (!p || !p->d[(va + i) & 4095]) return 0; o[i] = p->b[(va + i) & 4095]; }
    return 1;
}
static void mwrite(unsigned va, const void *src, unsigned n) {
    unsigned i; const unsigned char *s = (const unsigned char *)src;
    for (i = 0; i < n; i++) { Pg *p = page(va + i, 1); p->b[(va + i) & 4095] = s[i]; p->d[(va + i) & 4095] = 1; }
}
static int I(unsigned va) { int v = 0; mread(va, &v, 4); return v; }
static void PutI(unsigned va, int v) { mwrite(va, &v, 4); }
static void S(unsigned va, char *o, int cap) { int k = 0; unsigned char c; while (k < cap - 1 && mread(va + (unsigned)k, &c, 1) && c) o[k++] = (char)c; o[k] = 0; }
static void PutS(unsigned va, const char *s) { mwrite(va, s, (unsigned)strlen(s) + 1); }
static int hx(int c) { return c <= '9' ? c - '0' : (c | 32) - 'a' + 10; }
static int hexb(const char *h, unsigned char *o) { int n = 0; while (h[0] && h[1]) { o[n++] = (unsigned char)(hx(h[0]) << 4 | hx(h[1])); h += 2; } return n; }

static FILE *T; static int TRACE, STEP, NF, NEXTH = 14; static unsigned BASE, NEXTA = 0x20000000u, FRONT; static long long T0, NOW; static unsigned char KEYS[256];
static Pj *FR;
static void tline(const char *s) { if (TRACE) { fputs(s, T); fputc('\n', T); } }
static void to_log(const char *s) { if (TRACE) fprintf(T, "L %s\n", s); }
static unsigned num(const Pj *v) { return v ? (unsigned)(long long)v->num : 0; }
static void writes(const Pj *list, unsigned add) {
    const Pj *w; static unsigned char b[0x20000];
    for (w = list ? list->kid : NULL; w; w = w->next) { int n = hexb(pj_str(pj_at(w, 1)), b); mwrite(add + num(pj_at(w, 0)), b, (unsigned)n); }
}
static void next_frame(void) {
    const Pj *f = pj_at(FR, STEP++), *k; char l[32];
    if (BASE && I(BASE + 0x10) > 0) PutI(BASE + 0x10, I(BASE + 0x10) - 1);                 /* the block counts the popup's frames down */
    writes(pj_get(f, "set"), 0); writes(pj_get(f, "setb"), BASE);
    NOW = T0 + (long long)num(pj_get(f, "t")) * 10000; FRONT = num(pj_get(f, "front"));
    memset(KEYS, 0, sizeof KEYS);
    for (k = pj_get(f, "keys") ? pj_get(f, "keys")->kid : NULL; k; k = k->next) KEYS[num(k) & 255] = 1;
    snprintf(l, sizeof l, "F %d", STEP); tline(l);
}
static int t_read(GameMem *m, unsigned va, void *dst, unsigned n) {
    (void)m;
    if (va == 0x9D6E3C && n == 1) { if (STEP >= NF) return 0; next_frame(); }
    return mread(va, dst, n);
}
static int t_write(GameMem *m, unsigned va, const void *src, unsigned n, int keep) {
    (void)m;
    if (TRACE) { unsigned i; fprintf(T, "W %X %d ", va, keep ? 1 : 0); for (i = 0; i < n; i++) fprintf(T, "%02x", ((const unsigned char *)src)[i]); fputc('\n', T); }
    mwrite(va, src, n);
    if (BASE && va == BASE + 0x2264 && ((const unsigned char *)src)[0] == 1) {              /* the game loads its videos */
        unsigned e; for (e = 0x728630; e < 0x728750; e += 16) if (I(e + 12) == -1) PutI(e + 12, NEXTH++);
        PutI(BASE + 0x2264, 0);
    }
    if (BASE && va == BASE + 0x2270 && I(va) != 0) {                                         /* the game reopens a video object */
        int h = I(va) - 1; char p[300]; S((unsigned)I(BASE + 0x2274), p, sizeof p);
        PutS(0xAD2F90u + 0x16Cu * (unsigned)h + 0xC, p); PutI(0xAD2F90u + 0x16Cu * (unsigned)h + 4, 1); PutI(BASE + 0x2270, 0);
    }
    return 1;
}
static unsigned t_alloc(GameMem *m, unsigned n) {
    unsigned a = NEXTA; static unsigned char z[0x10000]; char l[64]; (void)m;
    NEXTA += 0x10000; mwrite(a, z, n > sizeof z ? (unsigned)sizeof z : n);
    snprintf(l, sizeof l, "A %X %X", n, a); tline(l);
    return a;
}
static void t_suspend(GameMem *m) { (void)m; tline("S"); }
static void t_resume(GameMem *m) { (void)m; tline("R"); }
static int t_alive(GameMem *m) { (void)m; return STEP < NF; }
static long long t_now(GameMem *m) { (void)m; return NOW; }
static void t_sleep(GameMem *m, int ms) { (void)m; (void)ms; }
static int t_key(GameMem *m, int vk) { (void)m; return KEYS[vk & 255]; }
static unsigned t_front(GameMem *m) { (void)m; return FRONT; }
static int t_shot(GameMem *m, int act, const char *path, const char *info) {
    (void)m;
    if (act == 1) tline("G grab");
    else if (act == 2) { const char *leaf = strrchr(path, '\\'); if (TRACE) fprintf(T, "G save %s %s\n", leaf ? leaf + 1 : path, info ? info : "-"); }
    else tline("G close");
    return 1;
}
static GameMem fake = {t_read, t_write, t_alloc, t_suspend, t_resume, t_alive, t_now, t_sleep, t_key, t_front, t_shot, NULL, NULL};

static int run(int argc, char **argv);
void __stdcall entry(void) {                            /* (no C runtime start-up: -nostartfiles) the arguments as UTF-8 */
    int n, i; wchar_t **w = CommandLineToArgvW(GetCommandLineW(), &n); static char a[8][1100]; char *v[8];
    for (i = 0; i < n && i < 8; i++) { WideCharToMultiByte(CP_UTF8, 0, w[i], -1, a[i], sizeof a[i], NULL, NULL); v[i] = a[i]; }
    ExitProcess((UINT)run(n < 8 ? n : 8, v));
}
static int run(int argc, char **argv) {
    static const unsigned char DRAW[5] = {0xa1, 0x0c, 0xd1, 0x7e, 0x00}, LOST[5] = {0xe8, 0x1a, 0xf7, 0xff, 0xff}, BLEND[5] = {0xe8, 0xff, 0x81, 0x02, 0x00};
    static const unsigned CAMS[3][2] = {{0x6EBB3C, 0x5F1E00}, {0x6ECBA4, 0x5F3FE0}, {0x6ECC94, 0x5F3FE0}};
    char err[300]; Pj *sc; PcCfg c; int i; SYSTEMTIME st = {2026, 10, 4, 15, 12, 0, 0, 0}; FILETIME ft;
    if (argc != 6) { fprintf(stderr, "livetest <scenario.json> <game exe> <mod dir> <profiles.yaml> <trace out>\n"); return 4; }
    if (!(sc = pj_load(argv[1], err, sizeof err))) { fprintf(stderr, "%s\n", err); return 1; }
    if (!(T = fopen(argv[5], "wb"))) return 3;
    SystemTimeToFileTime(&st, &ft); T0 = NOW = ((long long)ft.dwHighDateTime << 32) | ft.dwLowDateTime;
    FR = pj_get(sc, "frames"); NF = FR ? FR->n : 0;
    if (pj_get(sc, "next_handle")) NEXTH = (int)num(pj_get(sc, "next_handle"));
    pc_log = to_log; pc_init();
    for (i = 0; i < 9; i++) mwrite(PATCHES[i].va, PATCHES[i].orig, PATCHES[i].len);           /* a freshly started game */
    mwrite(0x591C4D, DRAW, 5); mwrite(0x591B01, LOST, 5); mwrite(0x5C948C, BLEND, 5);
    for (i = 0; i < 3; i++) mwrite(CAMS[i][0], &CAMS[i][1], 4);
    writes(pj_get(sc, "mem"), 0);
    pc_load_cfg(NULL, argv[3], &c, err, sizeof err);
    snprintf(c.profiles_file, sizeof c.profiles_file, "%s", argv[4]);
    if (!pc_prepare_cameras(&c, err, sizeof err)) { fprintf(stderr, "cameras: %s\n", err); return 1; }
    if (!pc_install_cameras(&fake, &c)) { fprintf(stderr, "cameras not installed\n"); return 1; }
    BASE = 0x20000000u;
    writes(pj_get(sc, "after"), BASE);
    TRACE = 1;
    snprintf(c.profiles_file, sizeof c.profiles_file, "%s", "");
    pc_live(&fake, &c, argv[2]);
    fclose(T); pj_free(sc);
    return 0;
}
