/* pc_live: patches.ps1's live part, after the cameras: Release-StuckKeys' Set-MenuTimers, Set-CarLists, Set-Handling and
 * Watch-Tracks (the alternative tracks, their sounds / tune / checkpoint times / shadows / road / shader test, the popups,
 * START = screenshot, VIEW CHANGE held = race exit, the handling keys), until the game exits. Each function is the
 * patches.ps1 function of the same name and does what it does in the same order, write for write and log line for log
 * line: tools\patches\live_lockstep.py runs both on the same fake games and compares (Bruno, 2026-10-15: the .ps1 and the
 * .dll in lockstep, automated).
 * PowerShell's ways that show in the writes, kept on purpose:
 *   - string -eq / -ne and hashtable keys ignore case: ieq(), _stricmp;
 *   - Read-GameString decodes ASCII (a byte past 0x7F is '?'), Str encodes ASCII (a UTF-16 unit past 0x7F is '?');
 *   - addresses are [long]: a sum past 4 GB is no address (the read fails), never a wrap: long long (ll) here;
 *   - Read-GameInt is signed, Read-GamePtr unsigned; "$x" of a double is .NET's G15 (%.15G), -f is avoided;
 *   - TimeSpan.TotalSeconds = ticks x (1 / 1e7), DateTime ticks of 100 ns: the host's now() gives a FILETIME (local).
 * This can actually be done in C++ the following way:
 *     std::map<std::string, Slot, CaseLess> slots; std::regex sp("^SP_[A-Za-z0-9_]{1,40}$", std::regex::icase);
 *     if (std::regex_match(track.speech, sp)) ...
 * it's done with fixed arrays and hand-written matchers because the data is tiny (16 slots, 10 cars), the 32-bit DLL
 * has no C++ runtime (lean: kernel32 / user32 / ucrtbase only), and each matcher sits next to the pattern it stands for. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define PC_LIVE_BLOBS
#include "blobs.h"
#include "patchcore.h"
#include "pc_json.h"

typedef long long ll;
static GameMem *G;
static char GAMEDIR[1024], MODDIR[1024];
#define TICKS_S 10000000LL
#define SECS(t) ((double)(t) * (1.0 / 10000000.0))        /* TimeSpan.TotalSeconds */
#define HOOK_DRAW 0x591C4D
#define CYCLE_DRAW 0x1000

/* ---------------------------------------------------------------- the game's memory, the way patches.ps1 reads it */
static int rd(ll va, void *d, unsigned n) { return va >= 0 && va + n <= 0x100000000LL && G->read(G, (unsigned)va, d, n); }
static void wr(ll va, const void *s, unsigned n, int keep) { if (va >= 0 && va + n <= 0x100000000LL) G->write(G, (unsigned)va, s, n, keep); }
static int gi(ll va) { int v; return rd(va, &v, 4) ? v : 0; }                         /* Read-GameInt */
static ll gp(ll va) { unsigned v; return rd(va, &v, 4) ? (ll)v : 0; }                 /* Read-GamePtr */
static void wi(ll va, ll v) { unsigned u = (unsigned)v; wr(va, &u, 4, 1); }          /* Write-GameInt, GetBytes([int]..) with $true */
static void w1(ll va, int b, int keep) { unsigned char c = (unsigned char)b; wr(va, &c, 1, keep); }
static int same(ll va, const unsigned char *b, unsigned n) { unsigned char t[64]; return n <= sizeof t && rd(va, t, n) && !memcmp(t, b, n); }
static void gstr(ll va, int max, char *o) {                                          /* Read-GameString (o: max + 1 bytes) */
    unsigned char b[256]; int i; o[0] = 0;
    if (max > 255 || !rd(va, b, (unsigned)max)) return;
    for (i = 0; i < max && b[i]; i++) o[i] = b[i] < 0x80 ? (char)b[i] : '?';
    o[i] = 0;
}
static void pstr(unsigned char *d, const char *u, int n) {                           /* Str $t $n */
    const unsigned char *s = (const unsigned char *)u; int k = 0;
    memset(d, 0, (size_t)n);
    while (*s && k < n - 1) {
        if (*s < 0x80) { d[k++] = *s++; continue; }
        d[k++] = '?'; if (*s >= 0xF0 && k < n - 1) d[k++] = '?';                     /* past U+FFFF: two UTF-16 units, two '?' */
        s++; while ((*s & 0xC0) == 0x80) s++;
    }
}
static void wstr(ll va, const char *u, int n) { unsigned char b[256]; pstr(b, u, n); wr(va, b, (unsigned)n, 1); }
static void call_to(unsigned char *b, ll from, ll to) { int r = (int)(to - (from + 5)); b[0] = 0xE8; memcpy(b + 1, &r, 4); }

/* ---------------------------------------------------------------- strings and files */
static int ieq(const char *a, const char *b) { return !_stricmp(a, b); }
static void lower(char *s) { for (; *s; s++) if (*s >= 'A' && *s <= 'Z') *s += 32; }
static int cp(char *d, size_t cap, const char *s) { size_t n = strlen(s); if (n >= cap) { d[0] = 0; return 0; } memcpy(d, s, n + 1); return 1; }   /* too long = "" (never a cut that passes a check) */
static int alnum_(int c) { return (c >= '0' && c <= '9') || ((c | 32) >= 'a' && (c | 32) <= 'z'); }
static int digits(const char *s, int lo, int hi) { int n = 0; while (s[n] >= '0' && s[n] <= '9') n++; return !s[n] && n >= lo && n <= hi; }   /* -match '^\d{lo,hi}$' (ASCII digits) */
static void trim(char *s) {                                                           /* String.Trim */
    size_t n = strlen(s), i = 0;
    while (n && strchr(" \t\r\n\v\f", s[n - 1])) s[--n] = 0;
    while (s[i] && strchr(" \t\r\n\v\f", s[i])) i++;
    if (i) memmove(s, s + i, n - i + 1);
}
static void jp(char *o, size_t cap, const char *a, const char *b) {                 /* Join-Path */
    size_t n = strlen(a); snprintf(o, cap, "%s%s%s", a, n && (a[n - 1] == '\\' || a[n - 1] == '/') ? "" : "\\", b);
}
static void wpath(const char *u, wchar_t *w) { if (!MultiByteToWideChar(CP_UTF8, 0, u, -1, w, 1100)) w[0] = 0; }
static int exists(const char *u) { wchar_t w[1100]; wpath(u, w); return w[0] && GetFileAttributesW(w) != INVALID_FILE_ATTRIBUTES; }   /* Test-Path -LiteralPath */
static ll fsize(const char *u) { WIN32_FILE_ATTRIBUTE_DATA a; wchar_t w[1100]; wpath(u, w); if (!GetFileAttributesExW(w, GetFileExInfoStandard, &a)) return -1; return ((ll)a.nFileSizeHigh << 32) | a.nFileSizeLow; }
static char *slurp(const char *u, ll *len) {                                         /* ReadAllBytes (+ a 0 after) */
    wchar_t w[1100]; HANDLE f; DWORD sz, got = 0; char *b;
    wpath(u, w); f = CreateFileW(w, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) return NULL;
    sz = GetFileSize(f, NULL); b = (char *)malloc((size_t)sz + 1);
    if (!b || (sz && !ReadFile(f, b, sz, &got, NULL)) || got != sz) { CloseHandle(f); free(b); return NULL; }
    CloseHandle(f); b[sz] = 0; if (len) *len = sz; return b;
}
static int text_of(const char *u, char *o, size_t cap) {                             /* ReadAllText(..).Trim().ToLower() */
    char *b = slurp(u, NULL), *s; if (!b) return 0;
    s = b; if (!strncmp(s, "\xEF\xBB\xBF", 3)) s += 3;
    snprintf(o, cap, "%s", s); free(b); trim(o); return 1;
}
static int put_file(const char *u, const char *s) {                                  /* WriteAllText (UTF-8, no BOM) */
    wchar_t w[1100]; HANDLE f; DWORD n;
    wpath(u, w); f = CreateFileW(w, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) return 0;
    WriteFile(f, s, (DWORD)strlen(s), &n, NULL); CloseHandle(f); return 1;
}
/* Get-ChildItem -LiteralPath dir -Filter pat: the names, in the order the folder gives them (NTFS: sorted), files and
 * folders alike, the pattern matched the way FindFirstFile matches it (short 8.3 names too), as PowerShell does. */
static int list_dir(const char *dir, const char *pat, char (*names)[260], int max) {
    char q[1100]; wchar_t w[1100]; WIN32_FIND_DATAW d; HANDLE h; int n = 0;
    jp(q, sizeof q, dir, pat); wpath(q, w);
    if ((h = FindFirstFileW(w, &d)) == INVALID_HANDLE_VALUE) return 0;
    do {
        if (!wcscmp(d.cFileName, L".") || !wcscmp(d.cFileName, L"..")) continue;
        if (names && n < max) WideCharToMultiByte(CP_UTF8, 0, d.cFileName, -1, names[n], 260, NULL, NULL);
        n++;
    } while (FindNextFileW(h, &d));
    FindClose(h); return n;
}

/* ---------------------------------------------------------------- the camera block (Find-Cycle) */
static ll find_cycle(void) {
    unsigned char b[5]; char m[5]; ll base;
    if (!rd(HOOK_DRAW, b, 5) || b[0] != 0xE8) return 0;
    base = HOOK_DRAW + 5 + (ll)*(int *)(b + 1) - CYCLE_DRAW;
    if (rd(base, m, 4) && !memcmp(m, "SR3V", 4)) return base;
    return 0;
}

/* ---------------------------------------------------------------- Set-MenuTimers */
static void set_menu_timers(void) {
    int i, n = 0, hidden;
    for (i = 0; i < (int)(sizeof MENU_TIMERS / sizeof *MENU_TIMERS); i++) {
        int v;
        if (!rd(MENU_TIMERS[i].va, &v, 4)) continue;
        if (v == MENU_TIMERS[i].ms || v == 120000) { wi(MENU_TIMERS[i].va, 0x7FFFFFFF); n++; }           /* 120000: set by an older PLAY.bat */
        else if (v == 0x7FFFFFFF) n++;
    }
    if (same(0x61827A, TIMER_DRAW_ORIG, 6)) { G->suspend(G); wr(0x61827A, TIMER_DRAW_NEW, 6, 0); G->resume(G); }
    hidden = same(0x61827A, TIMER_DRAW_NEW, 6);
    pc_logf("Menu timers: %d of %d off; countdown %s.", n, (int)(sizeof MENU_TIMERS / sizeof *MENU_TIMERS), hidden ? "hidden" : "NOT hidden (unexpected bytes)");
}

/* ---------------------------------------------------------------- Set-CarLists, Complete-CarLists, Open-CarCards */
static struct { int on; ll cave; int todo[2], ntodo; } CLP;                           /* $script:CarListPending */
static int complete_car_lists(void) {
    int done = 0, sc, sp, i;
    if (!CLP.on) return 1;
    G->suspend(G);
    if (rd(0x9D6E3C, &sc, 4) && rd(0x9D6E50, &sp, 4) && sc == 0 && sp == 0) {
        for (i = 0; i < CLP.ntodo; i++) { unsigned char j[5]; int k = CLP.todo[i]; call_to(j, CARLIST_SITES[k].site, CLP.cave + CARLIST_SITES[k].entry); j[0] = 0xE9; wr(CARLIST_SITES[k].site, j, 5, 0); }
        done = 1;
    }
    G->resume(G);
    if (done) CLP.on = 0;
    return done;
}
static void set_car_lists(void) {
    int n = 0, late = 0, i, ns = (int)(sizeof CARLIST_SITES / sizeof *CARLIST_SITES);
    CLP.on = 0; CLP.ntodo = 0;
    for (i = 0; i < ns; i++) {
        unsigned char cur[5];
        if (same(CARLIST_SITES[i].site, CARLIST_SITES[i].bytes, 5)) CLP.todo[CLP.ntodo++] = i;
        else if (rd(CARLIST_SITES[i].site, cur, 5) && cur[0] == 0xE9) n++;                  /* already ours (PLAY.bat run again on a running game) */
        else pc_logf("Car lists: unexpected bytes at 0x%X; that list is left as it is.", CARLIST_SITES[i].site);
    }
    if (CLP.ntodo) {
        CLP.cave = G->alloc(G, 0x1000); wr(CLP.cave, CARLIST_CODE, sizeof CARLIST_CODE, 1); CLP.on = 1;
        if (complete_car_lists()) n += CLP.ntodo; else late = 1;
    }
    { static const unsigned char cmp[4] = {0x3b, 0xc8, 0x75, 0x10}, nop[2] = {0x90, 0x90};      /* the speedo's top speed for an added car (0x599A20) */
      if (same(0x599D78, cmp, 4)) wr(0x599D7A, nop, 2, 0); }
    if (same(0x61C30B, CARDHOOK_EXIT, sizeof CARDHOOK_EXIT)) {                              /* a card on the car select for the cars of EXTRA_CARDS */
        static unsigned char blob[sizeof CARDHOOK_CODE + 36 * 8 + 36]; size_t k = sizeof CARDHOOK_CODE; ll cc; unsigned char j[5];
        memset(blob, 0, sizeof blob); memcpy(blob, CARDHOOK_CODE, sizeof CARDHOOK_CODE);
        for (i = 0; i < (int)(sizeof EXTRA_CARDS / sizeof *EXTRA_CARDS); i++) { memcpy(blob + k, EXTRA_CARDS[i].name, strlen(EXTRA_CARDS[i].name)); memcpy(blob + k + 32, &EXTRA_CARDS[i].cell, 4); k += 36; }
        k += 36;
        cc = G->alloc(G, 0x1000); wr(cc, blob, (unsigned)k, 1);
        call_to(j, 0x61C30B, cc); j[0] = 0xE9; G->suspend(G); wr(0x61C30B, j, 5, 0); G->resume(G);
    }
    if (late) pc_logf("Car lists: a game was started before the launcher was ready, so its car selects keep their own cars; every car in every mode from the next game on.");
    else if (n == ns) pc_logf("Car lists: every car in every mode (each mode's own cars first).");
    else pc_logf("Car lists: %d of %d changed.", n, ns);
}
static int wmv_name(const char *p) {                    /* -match '\\[A-Za-z0-9_]+\.wmv$' */
    size_t n = strlen(p); const char *e;
    if (n < 6 || _stricmp(p + n - 4, ".wmv")) return 0;
    e = p + n - 4; while (e > p && (alnum_((unsigned char)e[-1]) || e[-1] == '_')) e--;
    return e < p + n - 4 && e > p && e[-1] == '\\';
}
static int open_car_cards(ll base) {                    /* 0 = $false (the game's videos not loaded yet), 1 = anything else */
    unsigned char j[5]; ll cc, list; int obj = 19, i;
    if (!rd(0x61C30B, j, 5) || j[0] != 0xE9) return 1;
    cc = 0x61C30B + 5 + (ll)*(int *)(j + 1); list = cc + (ll)sizeof CARDHOOK_CODE;
    for (i = 0; i < (int)(sizeof EXTRA_CARDS / sizeof *EXTRA_CARDS); i++) {
        char s[256], path[600], disk[1100]; ll entry = list + 36 * i; int stand, have = -1, k, t; size_t n;
        if (!EXTRA_CARDS[i].file[0]) continue;
        gstr(entry, 32, s);
        if (!ieq(s, EXTRA_CARDS[i].name)) { pc_logf("Car cards: the card list in the game isn't this launcher's; %s keeps its stand-in.", EXTRA_CARDS[i].name); return 1; }
        stand = gi(EXTRA_CARDS[i].cell);
        if (stand == -1) {                                                                   /* the game hasn't loaded its videos yet: have it do so now */
            wi(base + 0x2264, 1);
            for (t = 0; t < 400 && gi(EXTRA_CARDS[i].cell) == -1; t++) G->sleep(G, 25);
            stand = gi(EXTRA_CARDS[i].cell);
        }
        if (stand < 0 || stand >= 20) return 0;                                              /* still not loaded: tried again when the menus come up */
        gstr(0xAD2F90 + 0x16C * (ll)stand + 0xC, 255, s);
        snprintf(path, sizeof path, "%s", s); n = strlen(path);                              /* -replace '[^\\]+\.wmv$', <file> */
        if (n >= 4 && !_stricmp(path + n - 4, ".wmv")) { char *b = strrchr(path, '\\'); size_t at = b ? (size_t)(b - path) + 1 : 0; if (at < n - 4) snprintf(path + at, sizeof path - at, "%s", EXTRA_CARDS[i].file); }
        if (path[0] == '\\' || path[0] == '/' || (path[0] && path[1] == ':')) snprintf(disk, sizeof disk, "%s", path); else jp(disk, sizeof disk, GAMEDIR, path);
        if (!wmv_name(path) || !exists(disk)) continue;
        for (k = 18; k < 20; k++) { char q[256]; gstr(0xAD2F90 + 0x16C * k + 0xC, 255, q); if (gi(0xAD2F90 + 0x16C * k + 4) && ieq(q, path)) have = k; }
        if (have < 0) {
            while (obj >= 18 && gi(0xAD2F90 + 0x16C * (ll)obj + 4)) obj--;
            if (obj < 18) { pc_logf("Car cards: no spare video object for %s; the card keeps its stand-in.", EXTRA_CARDS[i].file); return 1; }
            wstr(base + 0x2500, path, 256); wi(base + 0x2274, base + 0x2500); wi(base + 0x2270, obj + 1);
            for (t = 0; t < 300 && gi(base + 0x2270) != 0; t++) G->sleep(G, 10);
            if (!gi(0xAD2F90 + 0x16C * (ll)obj + 4)) { pc_logf("Car cards: the game didn't open %s; the card keeps its stand-in.", path); continue; }
            have = obj; obj--;
        }
        wi(cc + 0x800 + 4 * i, have); wi(entry + 32, cc + 0x800 + 4 * i);
        pc_logf("Car cards: %s plays %s.", EXTRA_CARDS[i].name, path);
    }
    return 1;
}

/* ---------------------------------------------------------------- handling (Read-Handling .. Remove-SrcPort) */
typedef struct { char name[32], digit, dir[1100]; int grip; } Flv;
typedef struct { char car[64], file[260], f[32]; } Pl;
static struct { int on, nfl, np; Flv fl[8]; Pl p[64]; } HD;                            /* $script:Handling: Flavors, Plan (in order) */
static ll CARPATH_CAVE, SRCPORT_CAVE;
static char RACE_FLAVOR[128], RACE_FLAVOR_NAME[32];                                   /* "" = $null */
static const char *const FLAVOR_KEYS[3] = {"sr3", "src", "realism"}, *const FLAVOR_TITLES[3] = {"SEGA Rally 3's own", "SEGA Rally Championship", "Realism"};
static const char *flavor_title(const char *f) { int i; for (i = 0; i < 3; i++) if (ieq(f, FLAVOR_KEYS[i])) return FLAVOR_TITLES[i]; return ""; }
static Flv *flv(const char *k) { int i; for (i = 0; i < HD.nfl; i++) if (ieq(HD.fl[i].name, k)) return &HD.fl[i]; return NULL; }
static Pl *plan(const char *c) { int i; for (i = 0; i < HD.np; i++) if (ieq(HD.p[i].car, c)) return &HD.p[i]; return NULL; }
static Pl *plan_set(const char *c, const char *f) { Pl *p = plan(c); if (!p && HD.np < 64) { p = &HD.p[HD.np++]; memset(p, 0, sizeof *p); snprintf(p->car, sizeof p->car, "%s", c); } if (p) snprintf(p->f, sizeof p->f, "%s", f); return p; }
static int known_car(const char *c) { int i; for (i = 0; i < 10; i++) if (ieq(c, HANDLING_CAR_NAMES[i])) return 1; return 0; }
static void car_title(const char *car, char *o, size_t cap) {                        /* Get-CarTitle: the menu's names, else TextInfo.ToTitleCase */
    static const char *const T[10] = {"Citroen C4 WRC", "Ford Focus RS WRC 07", "Subaru Impreza WRC2008", "Suzuki SX4 WRC", "Mitsubishi Lancer Evolution X",
                                      "Peugeot 207 Super 2000", "Toyota Celica ST205", "Lancia Super Delta HF integrale", "Bowler Nemesis", "McRae Enduro"};
    int i; size_t k = 0, w;
    for (i = 0; i < 10; i++) if (ieq(car, HANDLING_CAR_NAMES[i])) { snprintf(o, cap, "%s", T[i]); return; }
    snprintf(o, cap, "%s", car);
    while (o[k]) {                       /* a word that is all capitals stays (an acronym); else its first letter up, the rest down */
        int up = 1; size_t e;
        if (!alnum_((unsigned char)o[k])) { k++; continue; }
        for (e = k; o[e] && alnum_((unsigned char)o[e]); e++) if (o[e] >= 'a' && o[e] <= 'z') up = 0;
        if (!up) for (w = k; w < e; w++) { if (w == k && o[w] >= 'a' && o[w] <= 'z') o[w] -= 32; else if (w > k && o[w] >= 'A' && o[w] <= 'Z') o[w] += 32; }
        k = e;
    }
}
static int cmp_s(const void *a, const void *b) { return _stricmp(*(const char *const *)a, *(const char *const *)b); }
/* Sort-Object -Unique of a list of flavor names (they are lowercase words: _stricmp orders them as the culture does) */
static int uniq(const char **v, int n) { int i, k = 0; qsort(v, (size_t)n, sizeof *v, cmp_s); for (i = 0; i < n; i++) if (!k || !ieq(v[k - 1], v[i])) v[k++] = v[i]; return k; }
static void flavor_path(char *o, size_t cap, const Flv *f, const char *car, const char *suffix) { char c[64]; char nm[128]; snprintf(c, sizeof c, "%s", car); lower(c); snprintf(nm, sizeof nm, "%s%s", c, suffix); jp(o, cap, f->dir, nm); }

static char ADDED[48][64], ADDED_FILE[48][260]; static int NADDED;
static void added_cars(void) {                          /* *gravel_data.sbf in Main_release\cars, but SEGA's ten: car names and their files */
    static char raw[48][260]; char dir[1100]; int k, m;
    jp(dir, sizeof dir, GAMEDIR, "Main_release\\cars");
    m = list_dir(dir, "*gravel_data.sbf", raw, 48); if (m > 48) m = 48;
    for (k = NADDED = 0; k < m; k++) {
        size_t L = strlen(raw[k]); char nm[260];
        snprintf(nm, sizeof nm, "%s", raw[k]);
        if (L >= 15 && !_stricmp(nm + L - 15, "gravel_data.sbf")) nm[L - 15] = 0;           /* -replace '(?i)gravel_data\.sbf$', '' */
        if (!known_car(nm) && strlen(nm) < 64) { snprintf(ADDED[NADDED], 64, "%s", nm); snprintf(ADDED_FILE[NADDED], 260, "%s", raw[k]); NADDED++; }
    }
}
static int read_handling(void) {                        /* Read-Handling: 1 = a plan with a car on a flavor */
    char file[1100], err[200], def[64] = "sr3", want_c[64][64], want_f[64][32]; Pj *j, *m; int nw = 0, k, any = 0;
    jp(file, sizeof file, MODDIR, "handling.json");
    if (!exists(file)) return 0;
    if (!(j = pj_load(file, err, sizeof err))) { pc_logf("Handling: %s can't be read; every car keeps SEGA's handling.", file); return 0; }
    memset(&HD, 0, sizeof HD);
    if (pj_truthy(pj_get(j, "default"))) { snprintf(def, sizeof def, "%s", pj_str(pj_get(j, "default"))); lower(def); }
    m = pj_get(j, "flavors");
    if (pj_truthy(m) && m->type == PJ_OBJ) for (m = m->kid; m; m = m->next) {
        char kk[64], d[64], dir[1100], g[1100]; Flv *f;
        snprintf(kk, sizeof kk, "%s", m->key); lower(kk); snprintf(d, sizeof d, "%s", pj_str(pj_get(m, "digit")));
        if (ieq(kk, "sr3")) continue;
        if (!(d[0] >= '1' && d[0] <= '9' && !d[1])) { pc_logf("Handling: flavor %s has no folder digit 1..9; skipped.", kk); continue; }
        snprintf(g, sizeof g, "Main_release\\car%s", d); jp(dir, sizeof dir, GAMEDIR, g);
        if (!exists(dir)) { pc_logf("Handling: flavor %s's folder Main_release\\car%s is missing; skipped.", kk, d); continue; }
        if (!(f = flv(kk))) { if (HD.nfl >= 8) continue; f = &HD.fl[HD.nfl++]; }
        memset(f, 0, sizeof *f); snprintf(f->name, sizeof f->name, "%s", kk); f->digit = d[0]; snprintf(f->dir, sizeof f->dir, "%s", dir);
        if (pj_truthy(pj_get(m, "grip_file"))) {
            snprintf(g, sizeof g, "SurfacePairEffect%s\\surfacepairdata_xdata.sbf", d); jp(dir, sizeof dir, GAMEDIR, g);
            if (exists(dir)) f->grip = 1;
            else pc_logf("Handling: flavor %s's grip file SurfacePairEffect%s\\surfacepairdata_xdata.sbf is missing; its cars keep SEGA's tyre grip.", kk, d);
        }
    }
    m = pj_get(j, "cars");
    if (pj_truthy(m) && m->type == PJ_OBJ) for (m = m->kid; m; m = m->next) {
        int w; char kk[64]; snprintf(kk, sizeof kk, "%s", m->key); lower(kk);
        for (w = 0; w < nw && strcmp(want_c[w], kk); w++) ;
        if (w == nw) { if (nw >= 64) continue; nw++; }
        snprintf(want_c[w], 64, "%s", kk); snprintf(want_f[w], 32, "%s", pj_str(m)); lower(want_f[w]);
    }
    pj_free(j);
    for (k = 0; k < 10; k++) { Pl *p = plan_set(HANDLING_CAR_NAMES[k], ""); char c[64]; snprintf(c, sizeof c, "%s", HANDLING_CAR_NAMES[k]); lower(c); snprintf(p->file, sizeof p->file, "%sbespoke_data.sbf", c); }
    added_cars();
    for (k = 0; k < NADDED; k++) { Pl *p = plan_set(ADDED[k], ""); if (p) snprintf(p->file, sizeof p->file, "%s", ADDED_FILE[k]); }
    for (k = 0; k < HD.np; k++) {
        Pl *p = &HD.p[k]; char lc[64], f[32]; int w; Flv *fl;
        snprintf(f, sizeof f, "%s", def); snprintf(lc, sizeof lc, "%s", p->car); lower(lc);
        for (w = 0; w < nw; w++) if (!strcmp(want_c[w], lc)) snprintf(f, sizeof f, "%s", want_f[w]);
        if (!ieq(f, "sr3")) {
            char path[1100];
            if (!(fl = flv(f))) { pc_logf("Handling: %s asks for flavor %s, which is not available; it keeps SEGA's handling.", p->car, f); snprintf(f, sizeof f, "sr3"); }
            else { jp(path, sizeof path, fl->dir, p->file); if (!exists(path)) { pc_logf("Handling: Main_release\\car%c has no %s; %s keeps SEGA's handling.", fl->digit, p->file, p->car); snprintf(f, sizeof f, "sr3"); } }
        }
        snprintf(p->f, sizeof p->f, "%s", f); if (!ieq(f, "sr3")) any = 1;
    }
    HD.on = any; return any;
}
static int new_handling_live(void) {                   /* New-HandlingLive: the built flavors, every car on SEGA's; 0 = none built */
    static const struct { const char *k; char d; int grip; } DEF[2] = {{"src", '1', 1}, {"realism", '2', 0}};
    int i;
    memset(&HD, 0, sizeof HD);
    for (i = 0; i < 2; i++) {
        char g[64], dir[1100], gp_[1100];
        snprintf(g, sizeof g, "Main_release\\car%c", DEF[i].d); jp(dir, sizeof dir, GAMEDIR, g);
        if (list_dir(dir, "*_data.sbf", NULL, 0)) {
            Flv *f = &HD.fl[HD.nfl++]; memset(f, 0, sizeof *f);
            snprintf(f->name, sizeof f->name, "%s", DEF[i].k); f->digit = DEF[i].d; snprintf(f->dir, sizeof f->dir, "%s", dir);
            snprintf(g, sizeof g, "SurfacePairEffect%c\\surfacepairdata_xdata.sbf", DEF[i].d); jp(gp_, sizeof gp_, GAMEDIR, g);
            f->grip = DEF[i].grip && exists(gp_);
        }
    }
    if (!HD.nfl) return 0;
    for (i = 0; i < 10; i++) plan_set(HANDLING_CAR_NAMES[i], "sr3");
    added_cars();
    for (i = 0; i < NADDED; i++) plan_set(ADDED[i], "sr3");
    HD.on = 1; return 1;
}
static void jesc(char *o, size_t cap, const char *s);
static void save_handling(void) {                       /* Save-Handling (written as JSON; ConvertTo-Json's layout is not kept, live_lockstep.py compares the values) */
    const char *known[10], *def = "sr3"; int i, best = 0; char path[1100], *t; size_t n = 0, cap = 8192; const char *keys[64]; int nk = 0;
    if (!HD.on) return;
    for (i = 0; i < 10; i++) { Pl *p = plan(HANDLING_CAR_NAMES[i]); known[i] = p ? p->f : ""; }
    for (i = 0; i < 10; i++) {                          /* Group-Object | Sort-Object Count -Descending: the largest group, the first one met on a tie */
        int c = 0, k; for (k = 0; k < 10; k++) if (ieq(known[k], known[i])) c++;
        if (c > best) { best = c; def = known[i]; }
    }
    for (i = 0; i < HD.np; i++) if (!ieq(HD.p[i].f, def)) keys[nk++] = HD.p[i].car;
    qsort(keys, (size_t)nk, sizeof *keys, cmp_s);
    t = (char *)malloc(cap);
    { char e[200]; jesc(e, sizeof e, def); n += snprintf(t + n, cap - n, "{\n    \"version\": 1,\n    \"default\": %s,\n    \"cars\": {", e); }
    for (i = 0; i < nk; i++) { char a[200], b[200]; jesc(a, sizeof a, keys[i]); jesc(b, sizeof b, plan(keys[i])->f); n += snprintf(t + n, cap - n, "%s\n        %s: %s", i ? "," : "", a, b); }
    n += snprintf(t + n, cap - n, "%s},\n    \"flavors\": {\n        \"src\": {\"digit\": \"1\", \"grip_file\": true},\n        \"realism\": {\"digit\": \"2\", \"grip_file\": false}\n    }\n}\n", nk ? "\n    " : "");
    jp(path, sizeof path, MODDIR, "handling.json");
    if (!put_file(path, t)) pc_logf("Handling: handling.json can't be written: %lu", GetLastError());
    free(t);
}
static void set_dir_char(ll va, int ch, const char *what) {   /* Set-DirChar */
    unsigned char cur;
    if (!rd(va, &cur, 1) || !(cur == 0x73 || (cur >= 0x31 && cur <= 0x39))) { pc_logf("%s: unexpected byte at 0x%llX; left as it is.", what, va); return; }
    if (cur != (unsigned char)ch) w1(va, ch, 1);
}
static void remove_steer_hook(void) {
    unsigned char a[5];
    if (!rd(0x5CFF32, a, 5) || !memcmp(a, STEER_BYTES, 5) || a[0] != 0xE8) return;
    G->suspend(G); wr(0x5CFF32, STEER_BYTES, 5, 0); G->resume(G);
    pc_logf("Steering: the steering-rate routine of an earlier launcher taken out; SEGA's own steering.");
}
#define SRCPORT_SITE 0x678878
#define SRCPORT_STOCK 0x45C820
#define SRCPORT_DATA 0x23E0
static void install_src_port(void) {
    ll cur = gp(SRCPORT_SITE), cave; static unsigned char b[sizeof SRCPORT_CODE]; unsigned i; unsigned v;
    if (cur != SRCPORT_STOCK) {
        if (gi(cur + SRCPORT_DATA) != 0x50435253) { pc_logf("SRC turning: the vehicle step (0x%X) points to code that isn't ours; not installed.", SRCPORT_SITE); return; }
        if (gi(cur + SRCPORT_DATA + 4) == 1) { SRCPORT_CAVE = cur; pc_logf("SRC turning: already in this game (an earlier PLAY.bat); kept."); return; }
    }
    cave = G->alloc(G, 0x10000);
    memcpy(b, SRCPORT_CODE, sizeof b);
    for (i = 0; i < sizeof SRCPORT_RELOCS / sizeof *SRCPORT_RELOCS; i++) { unsigned o = SRCPORT_RELOCS[i], x; memcpy(&x, b + o, 4); x += (unsigned)cave; memcpy(b + o, &x, 4); }
    wr(cave, b, sizeof b, 1);
    v = (unsigned)cave; G->suspend(G); wr(SRCPORT_SITE, &v, 4, 0); G->resume(G);
    if (gp(SRCPORT_SITE) != cave) { pc_logf("SRC turning: the hook did not take; SR3's own turning."); return; }
    SRCPORT_CAVE = cave;
    pc_logf("SRC turning: in (0x%llX): cars on the SRC handling turn by SEGA Rally Championship's own equations (the player's car).", cave);
}
static void remove_src_port(void) {
    ll cur = gp(SRCPORT_SITE); unsigned v = SRCPORT_STOCK;
    SRCPORT_CAVE = 0;
    if (cur == SRCPORT_STOCK || gi(cur + SRCPORT_DATA) != 0x50435253) return;
    G->suspend(G); wr(SRCPORT_SITE, &v, 4, 0); G->resume(G);
    pc_logf("SRC turning: taken out (SEGA's vehicle step).");
}
#define CARPATH_SITE 0x5C6144
#define CARPATH_ENTRY 0xA0
#define CAR_DIR_SITE 0x6C631D
#define ADDED_CAR_DIR_SITE 0x6C6371
#define GRIP_DIR_SITE 0x6C6176
static void set_handling(void) {
    unsigned char site[5]; int hooked, i, site_ok;
    int have = read_handling();
    CARPATH_CAVE = 0; RACE_FLAVOR[0] = 0;
    if (!have) have = new_handling_live();             /* nothing asked for, but a flavor is built: every car on SEGA's, ready for the keys */
    remove_steer_hook();
    if (have && flv("src")) install_src_port(); else remove_src_port();
    site_ok = rd(CARPATH_SITE, site, 5);
    hooked = site_ok && site[0] == 0xE8;                /* ours already (PLAY.bat run again on a running game) */
    if (!have) {                                        /* nothing asked for: SEGA's paths (also undoes an earlier run) */
        set_dir_char(CAR_DIR_SITE, 's', "Handling"); set_dir_char(ADDED_CAR_DIR_SITE, 's', "Handling"); set_dir_char(GRIP_DIR_SITE, 's', "Handling");
        if (hooked) { ll cave = CARPATH_SITE + 5 + (ll)*(int *)(site + 1) - CARPATH_ENTRY; for (i = 0; i < 10; i++) w1(cave + 8 + 12 * i, 0, 1); }
        return;
    }
    {   const char *one[10]; int n1;
        for (i = 0; i < 10; i++) one[i] = plan(HANDLING_CAR_NAMES[i])->f;
        n1 = uniq(one, 10);
        if (n1 == 1 && !hooked && !HD.nfl) {
            int ch = 's'; if (!ieq(one[0], "sr3")) { ch = flv(one[0])->digit; pc_logf("Handling: every known car on flavor %s (Main_release\\car%c).", one[0], ch); }
            set_dir_char(CAR_DIR_SITE, ch, "Handling (known cars)");
        } else {
            ll cave = 0;
            if (hooked) {
                cave = CARPATH_SITE + 5 + (ll)*(int *)(site + 1) - CARPATH_ENTRY;
                if (!same(cave + CARPATH_ENTRY, CARPATH_CODE + CARPATH_ENTRY, 8)) { pc_logf("Handling: the car path code holds a call that is not ours; per-car flavors are off."); cave = 0; }
            } else if (site_ok && !memcmp(site, CARPATH_BYTES, 5)) {
                unsigned char c5[5];
                cave = G->alloc(G, 0x1000); wr(cave, CARPATH_CODE, sizeof CARPATH_CODE, 1);
                call_to(c5, CARPATH_SITE, cave + CARPATH_ENTRY); G->suspend(G); wr(CARPATH_SITE, c5, 5, 0); G->resume(G);
            } else pc_logf("Handling: unexpected bytes at 0x%X; per-car flavors are off.", CARPATH_SITE);
            if (cave) {
                char line[1024]; size_t n = 0;
                set_dir_char(CAR_DIR_SITE, 's', "Handling (known cars)");
                for (i = 0; i < 10; i++) { const char *f = plan(CAR_PATH_ORDER[i])->f; w1(cave + 8 + 12 * i, ieq(f, "sr3") ? 0 : flv(f)->digit, 1); }
                n += snprintf(line + n, sizeof line - n, "Handling per car: ");
                for (i = 0; i < 10; i++) n += snprintf(line + n, sizeof line - n, "%s%s %s", i ? ", " : "", HANDLING_CAR_NAMES[i], plan(HANDLING_CAR_NAMES[i])->f);
                pc_logf("%s. A race runs every car on the player's car's handling.", line);
                CARPATH_CAVE = cave;
            }
        }
    }
    {   const char *ao[64]; char names[1024] = ""; int na = 0, nao; size_t n = 0;
        for (i = 0; i < HD.np; i++) if (!known_car(HD.p[i].car)) { ao[na++] = HD.p[i].f; n += snprintf(names + n, sizeof names - n, "%s%s", na > 1 ? ", " : "", HD.p[i].car); }
        if (na) {
            nao = uniq(ao, na);
            if (nao == 1) { int ch = 's'; if (!ieq(ao[0], "sr3")) { ch = flv(ao[0])->digit; pc_logf("Handling: added cars (%s) on flavor %s.", names, ao[0]); } set_dir_char(ADDED_CAR_DIR_SITE, ch, "Handling (added cars)"); }
            else { set_dir_char(ADDED_CAR_DIR_SITE, 's', "Handling (added cars)"); pc_logf("Handling: the added cars (%s) ask for different flavors; they keep SEGA's handling (they share one path pattern).", names); }
        }
    }
    {   const char *used[64], *grip[64]; int nu = 0, ng = 0, gch = 's';
        for (i = 0; i < HD.np; i++) if (!ieq(HD.p[i].f, "sr3")) used[nu++] = HD.p[i].f;
        nu = uniq(used, nu);
        for (i = 0; i < nu; i++) { Flv *f = flv(used[i]); if (f && f->grip) grip[ng++] = used[i]; }
        if (ng) {
            gch = flv(grip[0])->digit;
            if (ng > 1) { char j[256] = ""; size_t n = 0; for (i = 0; i < ng; i++) n += snprintf(j + n, sizeof j - n, "%s%s", i ? " and " : "", grip[i]); pc_logf("Handling: %s each have a grip file; one is read per race: %s's.", j, grip[0]); }
        }
        set_dir_char(GRIP_DIR_SITE, gch, "Handling (grip file)");
    }
    if (HD.nfl) {
        char line[512]; size_t n = 0;
        for (i = 0; i < 3; i++) n += snprintf(line + n, sizeof line - n, "%s%s%s", i ? " / " : "", FLAVOR_TITLES[i], i && !flv(FLAVOR_KEYS[i]) ? " (not built)" : "");
        pc_logf("Handling keys (game window in front): 1 / 2 / 3 = %s for the highlighted car (car select) or your car; 0 = show.", line);
    }
}
static int added_name_ok(const char *s) { if (!*s) return 0; for (; *s; s++) if (!(alnum_((unsigned char)*s) || *s == '_')) return 0; return 1; }   /* '^[A-Za-z0-9_]+$' */
static const char *added_car_name(ll node, char *o) {    /* Get-AddedCarName (o: 33+ bytes) */
    int i;
    gstr(node + 0x40, 32, o);
    if (!added_name_ok(o)) { ll q = gp(node + 0x40); if (q) gstr(q, 32, o); }
    if (!_strnicmp(o, "LANG_ID_", 8)) memmove(o, o + 8, strlen(o + 8) + 1);
    for (i = 0; i < HD.np; i++) if (ieq(HD.p[i].car, o)) return HD.p[i].car;
    lower(o); return o;
}
static const char *handling_car_name(int id, char *o) {   /* Get-HandlingCarName: NULL = $null */
    ll p, n; int i;
    if (id >= 0 && id < 10) return HANDLING_CAR_NAMES[id];
    if (!(p = gp(0xB2A850))) return NULL;
    n = gp(p + 4) + 8;
    for (i = 0; i < 64 && n > 8; i++) { if (gi(n + 4) == id) return added_car_name(n, o); n = gp(n); }
    return NULL;
}
static const char *key_car(ll base, int menu, char *o) {   /* Get-KeyCar */
    ll node;
    if (menu) { int id = gi(base + 0x227C); if (id >= 0) return handling_car_name(id, o); }
    if (!(node = gp(0x9DBDA0 + 0xC))) return NULL;
    return handling_car_name(gi(node + 4), o);
}
static void set_car_handling_live(const char *car_, const char *f, char *l0, char *l1) {   /* Set-CarHandlingLive: the label's two lines */
    char car[64], t[128], path[1100]; Flv *fl = flv(f); int i;
    const char *g[64]; int ng = 0, gch = 's';
    snprintf(car, sizeof car, "%s", car_);
    if (!ieq(f, "sr3") && !fl) { snprintf(l0, 64, "%s isn't built", flavor_title(f)); snprintf(l1, 96, "build it in the settings app: Options, Handling..."); return; }
    car_title(car, t, sizeof t);
    if (known_car(car)) {
        int idx = -1;
        if (!CARPATH_CAVE) { snprintf(l0, 64, "Handling per car is off"); snprintf(l1, 96, "see play.log"); return; }
        for (i = 0; i < 10; i++) if (!strcmp(CAR_PATH_ORDER[i], car)) idx = i;              /* [Array]::IndexOf: exact case */
        if (!ieq(f, "sr3")) { flavor_path(path, sizeof path, fl, car, "bespoke_data.sbf"); if (!exists(path)) { snprintf(l0, 64, "%s: no file", flavor_title(f)); snprintf(l1, 96, "%s keeps its handling", t); return; } }
        w1(CARPATH_CAVE + 8 + 12 * idx, ieq(f, "sr3") ? 0 : fl->digit, 1);
    } else {
        if (!ieq(f, "sr3")) { flavor_path(path, sizeof path, fl, car, "gravel_data.sbf"); if (!exists(path)) { snprintf(l0, 64, "%s: no file", flavor_title(f)); snprintf(l1, 96, "%s keeps its handling", t); return; } }
        for (i = 0; i < HD.np; i++) if (!known_car(HD.p[i].car)) snprintf(HD.p[i].f, sizeof HD.p[i].f, "%s", f);   /* (the added cars share one path pattern) */
        set_dir_char(ADDED_CAR_DIR_SITE, ieq(f, "sr3") ? 's' : fl->digit, "Handling (added cars)");
    }
    plan_set(car, f);
    for (i = 0; i < HD.np; i++) { Flv *x = flv(HD.p[i].f); if (!ieq(HD.p[i].f, "sr3") && x && x->grip) g[ng++] = HD.p[i].f; }
    ng = uniq(g, ng); if (ng) gch = flv(g[0])->digit;
    set_dir_char(GRIP_DIR_SITE, gch, "Handling (grip file)");
    RACE_FLAVOR[0] = 0;                                  /* Sync-RaceFlavor writes the race's flags again */
    save_handling(); pc_logf("Handling: %s on %s (from its next race).", car, f);
    snprintf(l0, 64, "Handling: %s", flavor_title(f)); snprintf(l1, 96, "%s, from its next race", t);
}
static void sync_race_flavor(void) {
    ll node; const char *car; char o[64], f[32], key[128], path[1100]; Pl *p; Flv *fl; int i, ch = 's', gch = 's';
    if (!HD.on || !CARPATH_CAVE) return;
    if (!(node = gp(0x9DBDA0 + 0xC))) return;
    if (!(car = handling_car_name(gi(node + 4), o))) return;
    p = plan(car); snprintf(f, sizeof f, "%s", p ? p->f : "");
    if (!f[0] || (!ieq(f, "sr3") && !flv(f))) snprintf(f, sizeof f, "sr3");
    snprintf(key, sizeof key, "%s/%s", car, f);
    if (RACE_FLAVOR[0] && ieq(key, RACE_FLAVOR)) return;
    fl = flv(f);
    for (i = 0; i < 10; i++) {
        int b = 0;
        if (!ieq(f, "sr3")) { flavor_path(path, sizeof path, fl, CAR_PATH_ORDER[i], "bespoke_data.sbf"); if (exists(path)) b = fl->digit; }
        w1(CARPATH_CAVE + 8 + 12 * i, b, 1);
    }
    if (!ieq(f, "sr3")) {                               /* the added cars share one pattern: the flavor only if it has a file for each */
        int miss = 0;
        for (i = 0; i < HD.np; i++) if (!known_car(HD.p[i].car)) { flavor_path(path, sizeof path, fl, HD.p[i].car, "gravel_data.sbf"); if (!exists(path)) miss++; }
        if (!miss) ch = fl->digit;
    }
    set_dir_char(ADDED_CAR_DIR_SITE, ch, "Handling (added cars)");
    if (!ieq(f, "sr3") && fl->grip) gch = fl->digit;
    set_dir_char(GRIP_DIR_SITE, gch, "Handling (grip file)");
    snprintf(RACE_FLAVOR, sizeof RACE_FLAVOR, "%s", key); snprintf(RACE_FLAVOR_NAME, sizeof RACE_FLAVOR_NAME, "%s", f);
}

/* ---------------------------------------------------------------- the alternative tracks (Read-TrackSwitch .. Set-CardTrack) */
typedef struct { int stream; ll off, bytes, loop; } Tune;
typedef struct { char title[128], dir, video[64], speech[64], snd[3][32], path[260]; int has_path, has_tune; Tune tune; } Trk;
typedef struct { char name[64]; int n, choice, vid_on, vid_handle; char vid_path[260]; Trk t[16]; } Slot;
static Slot SL[16]; static int NSL, ART;
static Slot *slot(const char *name) { int i; if (!name[0]) return NULL; for (i = 0; i < NSL; i++) if (ieq(SL[i].name, name)) return &SL[i]; return NULL; }
static int is_id_track(const char *s) {                 /* -match '^ID_TRACK_[A-Z]{1,12}_[0-9]$' (any case, as -match) */
    int n = 0;
    if (_strnicmp(s, "ID_TRACK_", 9)) return 0;
    for (s += 9; (*s | 32) >= 'a' && (*s | 32) <= 'z'; s++) n++;
    return n >= 1 && n <= 12 && s[0] == '_' && s[1] >= '0' && s[1] <= '9' && !s[2];
}
static int is_sp(const char *s) {                       /* -match '^SP_[A-Za-z0-9_]{1,40}$' */
    int n = 0;
    if (_strnicmp(s, "SP_", 3)) return 0;
    for (s += 3; *s; s++, n++) if (!(alnum_((unsigned char)*s) || *s == '_')) return 0;
    return n >= 1 && n <= 40;
}
static void title_cp(char *d, const char *s) { size_t n = strlen(s); if (n > 127) { n = 127; while (n && ((unsigned char)s[n] & 0xC0) == 0x80) n--; } memcpy(d, s, n); d[n] = 0; }
static int read_track_switch(void) {                    /* Read-TrackSwitch: the number of slots with alternatives */
    char file[1100], err[200], vids[1100]; Pj *j, *p;
    NSL = 0; ART = 0;
    jp(file, sizeof file, GAMEDIR, "Main_release\\tracks\\_SR3Extras\\switch.json");
    if (!exists(file)) return 0;
    if (!(j = pj_load(file, err, sizeof err))) { pc_logf("Alternative tracks: %s can't be read; ignoring it.", file); return 0; }
    jp(vids, sizeof vids, GAMEDIR, "frontend\\PC\\Videos");
    p = pj_get(j, "slots");
    if (p && p->type == PJ_OBJ) for (p = p->kid; p; p = p->next) {
        static Slot s; Pj *ts = pj_get(p, "tracks"), *a; int k, single;
        if (strlen(p->key) >= sizeof s.name) continue;
        memset(&s, 0, sizeof s); snprintf(s.name, sizeof s.name, "%s", p->key);
        title_cp(s.t[0].title, pj_str(pj_get(p, "title"))); s.t[0].dir = 's'; cp(s.t[0].speech, sizeof s.t[0].speech, pj_str(pj_get(p, "speech"))); s.n = 1;
        single = !ts || ts->type != PJ_ARR;                                                    /* @($p.Value.tracks): one value is a list of one */
        for (a = single ? ts : ts->kid, k = 0; (single ? k < 1 : a != NULL) && s.n < 16; a = single ? NULL : a->next, k++) {
            Trk *t = &s.t[s.n]; const char *d = pj_str(pj_get(a, "dir")), *v = pj_str(pj_get(a, "video")); char sub[200], path[1100]; Pj *tu; int q;
            if (!(d[0] >= '1' && d[0] <= '9' && !d[1])) continue;
            snprintf(sub, sizeof sub, "Main_release\\track%s\\%s", d, s.name); jp(path, sizeof path, GAMEDIR, sub);
            if (!exists(path)) { pc_logf("Alternative tracks: %s is listed but Main_release\\track%s\\%s is missing; skipped.", pj_str(pj_get(a, "title")), d, s.name); continue; }
            memset(t, 0, sizeof *t);
            if (v[0] && cp(t->video, sizeof t->video, v)) { char pat[100]; snprintf(pat, sizeof pat, "*_%s.wmv", v); if (list_dir(vids, pat, NULL, 0) < 1) t->video[0] = 0; }   /* stage cards LANG_<language>_<video>.wmv, the Classic card classic_<video>.wmv */
            for (q = 0; q < 3; q++) { static const char *const K[3] = {"ambience", "music", "events"}; const char *x = pj_str(pj_get(a, K[q])); if (is_id_track(x)) cp(t->snd[q], sizeof t->snd[q], x); }
            tu = pj_get(a, "tune");                    /* a tune of its own, appended to the game's stream file by SR3 Extras (Set-CourseTune): only when it really is there */
            if (pj_truthy(tu) && digits(pj_str(pj_get(tu, "stream")), 1, 4) && digits(pj_str(pj_get(tu, "offset")), 3, 10) && digits(pj_str(pj_get(tu, "bytes")), 3, 10) && digits(pj_str(pj_get(tu, "loopstart")), 1, 10)) {
                char df[1100]; ll fs;
                t->has_tune = 1; t->tune.stream = atoi(pj_str(pj_get(tu, "stream"))); t->tune.off = _atoi64(pj_str(pj_get(tu, "offset")));
                t->tune.bytes = _atoi64(pj_str(pj_get(tu, "bytes"))); t->tune.loop = _atoi64(pj_str(pj_get(tu, "loopstart")));
                jp(df, sizeof df, GAMEDIR, "Audio\\EnglishStreamData.stm"); fs = fsize(df);
                if ((t->tune.bytes % 4) || (t->tune.loop % 4) || t->tune.loop >= t->tune.bytes || fs < 0 || t->tune.off + 0xC0 + t->tune.bytes > fs || t->tune.off + 0xC0 + t->tune.bytes > 0x7FFFFFFF) {
                    pc_logf("Alternative tracks: the tune of %s is not in the game's sound file; it plays its slot's own music.", pj_str(pj_get(a, "title"))); t->has_tune = 0;
                }
            }
            title_cp(t->title, pj_str(pj_get(a, "title"))); t->dir = d[0]; cp(t->speech, sizeof t->speech, pj_str(pj_get(a, "speech"))); s.n++;
        }
        if (s.n > 1) { Slot *o = slot(s.name); if (o) { char keep[64]; snprintf(keep, sizeof keep, "%s", o->name); *o = s; snprintf(o->name, sizeof o->name, "%s", keep); } else if (NSL < 16) SL[NSL++] = s; }
    }
    ART = pj_truthy(pj_get(j, "art"));
    pj_free(j);
    return NSL;
}
static struct { int n, id[64]; char name[64][25]; } IDS;     /* Read-TrackNames: id -> name of the game's tracks */
static void read_track_names(void) {
    ll p, n; int i;
    IDS.n = 0;
    if (!(p = gi(0xB2A850))) return;
    if (!(p = gi(p + 8))) return;
    n = p + 8;
    for (i = 0; i < 64 && n; i++) {
        ll s = gi(n + 0x18);
        if (s) { int id = gi(n + 4), k; for (k = 0; k < IDS.n && IDS.id[k] != id; k++) ; if (k == IDS.n) IDS.n++; IDS.id[k] = id; gstr(s, 24, IDS.name[k]); }
        n = gi(n);
    }
}
static const char *track_name(int id) { int k; for (k = 0; k < IDS.n; k++) if (IDS.id[k] == id) return IDS.name[k]; return NULL; }
static ll video_entry(const char *s) {                  /* $TrackVideoEntry; Desert4 (the Classic slot): the mode menu's Classic card */
    static const struct { const char *s; ll e; } E[4] = {{"Tropical4", 0x728710}, {"Alpine4", 0x728720}, {"Canyon4", 0x728730}, {"Desert4", 0x728650}};
    int i; for (i = 0; i < 4; i++) if (ieq(s, E[i].s)) return E[i].e;
    return 0;
}
static void initialize_track_videos(ll base) {          /* each card's video object and the file it plays; the alternatives' files are next to it */
    int i, k;
    for (i = 0; i < NSL; i++) {
        Slot *s = &SL[i]; ll entry = video_entry(s->name); int own; char path[256];
        s->vid_on = 0;
        if (!entry) continue;
        own = gi(entry + 12);
        if (own == -1) { int t; wi(base + 0x2264, 1); for (t = 0; t < 400 && gi(entry + 12) == -1; t++) G->sleep(G, 25); own = gi(entry + 12); }
        if (own < 0 || own >= 20) { pc_logf("Alternative tracks: the game didn't load the card video of %s; the card keeps its own picture.", s->name); continue; }
        gstr(0xAD2F90 + 0x16C * (ll)own + 0xC, 255, path);
        if (!wmv_name(path)) { pc_logf("Alternative tracks: the card video of %s isn't where expected; the card keeps its own picture.", s->name); continue; }
        s->vid_on = 1; s->vid_handle = own; snprintf(s->vid_path, sizeof s->vid_path, "%s", path);
        snprintf(s->t[0].path, sizeof s->t[0].path, "%s", path); s->t[0].has_path = 1;
        for (k = 1; k < s->n; k++) {
            Trk *a = &s->t[k]; size_t n = strlen(path); const char *e = path + n - 4;
            a->has_path = 1;
            if (!a->video[0]) { snprintf(a->path, sizeof a->path, "%s", path); continue; }
            while (e > path && alnum_((unsigned char)e[-1])) e--;             /* LANG_ENGLISH_TRO.wmv -> LANG_ENGLISH_TR1.wmv; classic.wmv -> classic_MTN.wmv */
            if (e < path + n - 4 && e > path && e[-1] == '_') snprintf(a->path, sizeof a->path, "%.*s_%s.wmv", (int)(e - 1 - path), path, a->video);
            else snprintf(a->path, sizeof a->path, "%.*s_%s.wmv", (int)(n - 4), path, a->video);
        }
    }
}
static ll speech_site(const char *s, ll *own, ll *text) {
    if (ieq(s, "Tropical4")) { *own = 0x6CF084; *text = 0x2600; return 0x610E10; }
    if (ieq(s, "Alpine4")) { *own = 0x6CF098; *text = 0x2640; return 0x610E3B; }
    if (ieq(s, "Canyon4")) { *own = 0x6CF0AC; *text = 0x2680; return 0x610E67; }
    return 0;
}
static void set_card_track(ll base, Slot *s, const Trk *t, int own) {   /* the card's video and the announcer's clip */
    ll site, gown, text;
    if (s->vid_on && t->has_path && t->path[0] && !ieq(t->path, s->vid_path)) {
        int i;
        wstr(base + 0x2500, t->path, 256); wi(base + 0x2274, base + 0x2500); wi(base + 0x2270, s->vid_handle + 1);
        for (i = 0; i < 300 && gi(base + 0x2270) != 0; i++) G->sleep(G, 10);
        snprintf(s->vid_path, sizeof s->vid_path, "%s", t->path);
    }
    if ((site = speech_site(s->name, &gown, &text))) {
        ll name = gown;
        if (!own && is_sp(t->speech)) { name = base + text; wstr(name, t->speech, 48); }
        wi(site, name);
    }
}
static unsigned char TD_LAST[4 + 0x20 * 16]; static int TD_LAST_ON;                     /* $script:TrackDirLast */
static ll install_trackdir(void) {                      /* Install-TrackDir: 0 = folders switched by polling */
    unsigned char first[5]; ll cave; int k;
    if (rd(TRACKDIR_HOOKS[0].site, first, 5) && first[0] == 0xE9) {                        /* PLAY.bat run again on a running game: ours already */
        cave = TRACKDIR_HOOKS[0].site + 5 + (ll)*(int *)(first + 1) - TRACKDIR_HOOKS[0].entry;
        if (same(cave, TRACKDIR_CODE, 8)) return cave;
        pc_logf("Track folders: the path code holds a jump that is not ours; folders are switched by polling."); return 0;
    }
    for (k = 0; k < 3; k++) if (!same(TRACKDIR_HOOKS[k].site, TRACKDIR_HOOKS[k].bytes, TRACKDIR_HOOKS[k].len)) { pc_logf("Track folders: unexpected bytes at 0x%X; folders are switched by polling.", TRACKDIR_HOOKS[k].site); return 0; }
    cave = G->alloc(G, 0x1000); wr(cave, TRACKDIR_CODE, sizeof TRACKDIR_CODE, 1);
    { unsigned z = 0; wr(cave + 0x200, &z, 4, 1); }
    for (k = 0; k < 6; k++) w1(TRACK_DIR_SITES[k], 's', 1);                                 /* (and the strings stay writable for the routine) */
    G->suspend(G);
    for (k = 0; k < 3; k++) { unsigned char j[6]; call_to(j, TRACKDIR_HOOKS[k].site, cave + TRACKDIR_HOOKS[k].entry); j[0] = 0xE9; j[5] = 0x90; wr(TRACKDIR_HOOKS[k].site, j, TRACKDIR_HOOKS[k].len > 5 ? 6 : 5, 0); }
    G->resume(G);
    return cave;
}
static int cmp_slot(const void *a, const void *b) { return _stricmp((*(Slot *const *)a)->name, (*(Slot *const *)b)->name); }
static int sorted_slots(Slot **v) { int i; for (i = 0; i < NSL; i++) v[i] = &SL[i]; qsort(v, (size_t)NSL, sizeof *v, cmp_slot); return NSL; }
static void write_trackdir_table(ll cave) {             /* every slot with alternatives and the folder character of its chosen track ('s' = the game's own) */
    unsigned char b[4 + 0x20 * 16]; Slot *v[16]; int i, n = 0, m = sorted_slots(v);
    memset(b, 0, sizeof b);
    for (i = 0; i < m && n < 16; i++) {
        unsigned char nm[64]; size_t L; pstr(nm, v[i]->name, 64); L = strlen((char *)nm);   /* [Text.Encoding]::ASCII.GetBytes */
        if (L > 23) continue;
        memcpy(b + 4 + 0x20 * n, nm, L); b[4 + 0x20 * n + 0x18] = (unsigned char)v[i]->t[v[i]->choice].dir; n++;
    }
    memcpy(b, &n, 4);
    if (!TD_LAST_ON || memcmp(b, TD_LAST, sizeof b)) { wr(cave + 0x200, b, sizeof b, 1); memcpy(TD_LAST, b, sizeof b); TD_LAST_ON = 1; }
}
static struct { int on, stream; ll rb, info, off, bytes, loop, lp; } TUNE_OWN;           /* $script:TuneOwn */
static int set_course_tune(const Tune *t) {
    ll hdr, ta, tb, ra, rb, info;
    if (!t && !TUNE_OWN.on) return 1;
    hdr = gp(0x9C4EC0); ta = gp(0x9C4EC4); tb = gp(0x9C4EC8);
    if (!hdr || !ta || !tb) return 0;
    if (TUNE_OWN.on && (!t || t->stream != TUNE_OWN.stream)) {                               /* the game's own values back */
        wi(TUNE_OWN.rb + 0xC4, TUNE_OWN.off); wi(TUNE_OWN.info + 0xC8, TUNE_OWN.bytes); wi(TUNE_OWN.info + 0xCC, TUNE_OWN.loop); wi(TUNE_OWN.info + 0xD0, TUNE_OWN.lp);
        TUNE_OWN.on = 0;
    }
    if (!t) return 1;
    ra = ta + 200LL * t->stream; rb = tb + 200LL * t->stream; info = hdr + gp(ra + 0xC4);
    if (gp(ra + 0xC0) != t->stream || gp(rb + 0xC0) != t->stream || gp(info + 0xC0) != 2 || gp(info + 0xC4) != 32000) {
        pc_logf("A track's own tune: stream %d is not the stereo 32000 Hz stream expected; the slot's own music plays.", t->stream); return 1;
    }
    if (!TUNE_OWN.on) { TUNE_OWN.on = 1; TUNE_OWN.stream = t->stream; TUNE_OWN.rb = rb; TUNE_OWN.info = info; TUNE_OWN.off = gp(rb + 0xC4); TUNE_OWN.bytes = gp(info + 0xC8); TUNE_OWN.loop = gp(info + 0xCC); TUNE_OWN.lp = gp(info + 0xD0); }
    wi(rb + 0xC4, t->off); wi(info + 0xC8, t->bytes); wi(info + 0xCC, t->loop); wi(info + 0xD0, 1);
    return 1;
}
static void track_file(char *o, size_t cap, const char *slot_, int dir, const char *leaf) { char s[200]; snprintf(s, sizeof s, "Main_release\\track%c\\%s\\%s", dir, slot_, leaf); jp(o, cap, GAMEDIR, s); }
static struct { int on; ll at; unsigned char b[0xC60]; } ARCADE_ORIG;
static void set_arcade_times(const char *s, int dir) {  /* checkpoint times: an added track's arcade_times.bin, written into the loaded table while it is chosen */
    static const char *const IX[6] = {"Tropical4", "Canyon4", "Alpine4", "Lakeside4", "Desert4", "Stadium4"};
    char file[1100]; int ix = -1, i, p, tab; ll len; char *nb;
    if (ARCADE_ORIG.on) { wr(ARCADE_ORIG.at, ARCADE_ORIG.b, 0xC60, 1); ARCADE_ORIG.on = 0; }
    for (i = 0; i < 6; i++) if (ieq(s, IX[i])) ix = i;
    if (dir == 's' || ix < 0) return;
    track_file(file, sizeof file, s, dir, "arcade_times.bin");
    if (!exists(file)) return;
    if (!(nb = slurp(file, &len))) return;
    p = gi(0xB2A850); tab = p ? gi((ll)p + 0xC) : 0;
    if (len != 0xC60 || !tab) { pc_logf("Checkpoint times: %s not used (size %lld, table %d).", file, len, tab); free(nb); return; }
    { ll at = (ll)tab + 4 + 0xC60LL * ix;
      if (!rd(at, ARCADE_ORIG.b, 0xC60)) { free(nb); return; }
      ARCADE_ORIG.on = 1; ARCADE_ORIG.at = at;
      wr(at, nb, 0xC60, 1); }
    free(nb);
    pc_logf("Checkpoint times: %s uses the times of Main_release\\track%c\\%s.", s, dir, s);
}
static int dnum(const char *s, double *v) {             /* [double]::TryParse(s, Float, Invariant), NaN and the infinities refused (patches.ps1 refuses them by range) */
    char *e;
    if (!*s || strpbrk(s, "xXnNiI")) return 0;
    *v = strtod(s, &e); return !*e;
}
static struct { int on; unsigned char b[8]; int blur; } SHADOW;
static void set_shadow_params(const char *s, int dir) {  /* car shadows: shadow.txt "<variance floor> <power> [noblur]" */
    static const unsigned char blur_orig[5] = {0xE8, 0xF4, 0x84, 0xF6, 0xFF}, nop5[5] = {0x90, 0x90, 0x90, 0x90, 0x90};
    char file[1100], t[512], *tok[4]; int n = 0; double a = 0, b = 0; unsigned char nb[8]; float fa, fb; const char *blur = "";
    if (SHADOW.on) { wr(0x9F106C, SHADOW.b, 8, 1); SHADOW.on = 0; }
    if (SHADOW.blur) { wr(0x5A5467, blur_orig, 5, 0); SHADOW.blur = 0; }
    if (dir == 's') return;
    track_file(file, sizeof file, s, dir, "shadow.txt");
    if (!exists(file) || !text_of(file, t, sizeof t)) return;
    { char *c = t; while (*c && n < 4) { tok[n++] = c; while (*c && !strchr(" \t\r\n\v\f", *c)) c++; if (*c) { *c++ = 0; while (*c && strchr(" \t\r\n\v\f", *c)) c++; } } }
    if (n < 2 || !dnum(tok[0], &a) || !dnum(tok[1], &b) || a <= 0 || a > 0.01 || b < 1 || b > 200) { pc_logf("Car shadows: %s not used (expected two numbers, e.g. 0.0002 30).", file); return; }
    if (!rd(0x9F106C, SHADOW.b, 8)) return;
    SHADOW.on = 1; fa = (float)a; fb = (float)b; memcpy(nb, &fa, 4); memcpy(nb + 4, &fb, 4);
    wr(0x9F106C, nb, 8, 1);
    if (n >= 3 && !strcmp(tok[2], "noblur")) {
        if (same(0x5A5467, blur_orig, 5)) { wr(0x5A5467, nop5, 5, 0); SHADOW.blur = 1; blur = ", blur pass off"; }
        else blur = ", blur pass NOT touched (unexpected bytes at its call)";
    }
    pc_logf("Car shadows: %s uses variance floor %.15G, power %.15G%s (Main_release\\track%c\\%s\\shadow.txt).", s, a, b, blur, dir, s);
}
static int ROAD_HIDDEN, ROAD_CAR_HIDDEN;
static void set_road_hide(const char *s, int dir) {      /* road.txt "hide" / "hide all": the game's road not drawn (0x4EEF70, 0x4EE920) */
    static const unsigned char draw_orig[6] = {0x55, 0x8B, 0xEC, 0x83, 0xE4, 0xF0}, car_orig[6] = {0x83, 0xEC, 0x3C, 0x8B, 0x00, 0x6B};
    char file[1100], w[512]; unsigned char now[6]; const char *more = "";
    if (ROAD_HIDDEN) { w1(0x4EEF70, 0x55, 0); ROAD_HIDDEN = 0; pc_logf("Game's road: drawn again."); }
    if (ROAD_CAR_HIDDEN) { w1(0x4EE920, 0x83, 0); ROAD_CAR_HIDDEN = 0; }
    if (dir == 's') return;
    track_file(file, sizeof file, s, dir, "road.txt");
    if (!exists(file) || !text_of(file, w, sizeof w)) return;
    lower(w);
    if (strcmp(w, "hide") && strcmp(w, "hide all")) { pc_logf("Game's road: %s not used (expected: hide, or: hide all).", file); return; }
    if (!rd(0x4EEF70, now, 6) || memcmp(now, draw_orig, 6)) {
        char hx[24] = ""; int i, ok = rd(0x4EEF70, now, 6); size_t n = 0;
        for (i = 0; ok && i < 6; i++) n += (size_t)snprintf(hx + n, sizeof hx - n, i ? " %02X" : "%02X", now[i]);
        pc_logf("Game's road: NOT hidden, unexpected bytes at its drawing routine (%s).", hx);
        return;
    }
    w1(0x4EEF70, 0xC3, 0); ROAD_HIDDEN = 1;
    if (!strcmp(w, "hide all")) {
        if (same(0x4EE920, car_orig, 6)) { w1(0x4EE920, 0xC3, 0); ROAD_CAR_HIDDEN = 1; more = ", nor its patch around each car"; }
        else more = " (the patch around each car NOT touched: unexpected bytes)";
    }
    pc_logf("Game's road: not drawn on %s%s (Main_release\\track%c\\%s\\road.txt); it still carries the driving.", s, more, dir, s);
}
static struct { int on; ll va; unsigned char old[4]; } SHADER_SWAP;
static int u32(ll va, ll *v) { unsigned x; if (!rd(va, &x, 4)) return 0; *v = x; return 1; }
static void hexn(char *o, int ok, ll v) { if (ok) snprintf(o, 20, "%llX", v); else o[0] = 0; }      /* {0:X} of a value or of $null */
static void set_shader_test(const char *s, int dir) {    /* SHADER EXPERIMENT: shader.txt "untextured" / "untextured-own" */
    char file[1100], w[512]; ll rec, code, n = 0, base = 0, c1, c2, c3, c4; int i, hn, has_base = 0, k1, k2, k3, k4;
    unsigned char a[4], b[4], back[4];
    if (SHADER_SWAP.on) { wr(SHADER_SWAP.va, SHADER_SWAP.old, 4, 1); pc_logf("Shader experiment: the wall shader is back (pointer restored)."); SHADER_SWAP.on = 0; }
    if (dir == 's') return;
    track_file(file, sizeof file, s, dir, "shader.txt");
    if (!exists(file) || !text_of(file, w, sizeof w)) return;
    lower(w);
    if (strcmp(w, "untextured") && strcmp(w, "untextured-own")) { pc_logf("Shader experiment: %s not used (expected the word: untextured or untextured-own).", file); return; }
    rec = strcmp(w, "untextured-own") ? 0xABFC : 0xAB48; code = strcmp(w, "untextured-own") ? 0x1122B8 : 0x10E420;
    hn = u32(0x9F1280, &n);
    if (!hn || n < 1 || n > 64) { if (hn) pc_logf("Shader experiment: the effect list could not be read (count %lld).", n); else pc_logf("Shader experiment: the effect list could not be read (count )."); return; }
    for (i = 0; i < n; i++) {
        ll np; char q[18];
        if (!u32(0x9F1084 + 8 * i, &np) || np < 0x10000) continue;
        if (!rd(np, q, 18)) continue;
        if (!_strnicmp(q, "ubershadergame.fx", 17) && !q[17]) { base = np - 0xACB0; has_base = 1; break; }   /* (-eq: any case) */
    }
    if (!has_base) { pc_logf("Shader experiment: ubershadergame.fx is not in the effect list (%lld effects): nothing changed.", n); return; }
    k1 = u32(base, &c1); k2 = u32(base + 0x70E4 + 8, &c2); k3 = u32(base + rec, &c3); k4 = k3 && c3 ? u32(base + code, &c4) : 0;
    if (!k1 || c1 != 0x02D604CD || !k2 || c2 != base + 0xABFC || !k3 || c3 != base + code || !k4 || c4 != 0xFFFF0300) {
        char h1[20], h2[20], h3[20], h4[20]; hexn(h1, k1, c1); hexn(h2, k2, c2); hexn(h3, k3, c3); hexn(h4, k4, c4);
        pc_logf("Shader experiment: the effect at 0x%llX is not the one this was written for (checks %s %s %s %s; shader library 2 instead of 3?): nothing changed.", base, h1, h2, h3, h4); return;
    }
    { ll va = base + rec + 0x10; unsigned wa = 0, wb = 0, wk = 0;
      if (rd(va, a, 4)) memcpy(&wa, a, 4);
      if (rd(base + 0x8DFC + 0x10, b, 4)) memcpy(&wb, b, 4);
      if (!wa || !wb) { pc_logf("Shader experiment: a shader pointer is empty (walls %u, plain %u): nothing changed.", wa, wb); return; }
      wr(va, b, 4, 1); SHADER_SWAP.on = 1; SHADER_SWAP.va = va; memcpy(SHADER_SWAP.old, a, 4);
      if (rd(va, back, 4)) memcpy(&wk, back, 4);
      pc_logf("Shader experiment: effect at 0x%llX; wall pixel shader 0x%X replaced by the untextured one 0x%X (read back 0x%X). Imported scenery should show without its pictures.", base, wa, wb, wk); }
}

/* ---------------------------------------------------------------- START = a screenshot, VIEW CHANGE held = the race left */
#define HOLD 1.2                                         /* $StartHoldSeconds */
typedef struct { int was, armed, vwas, varmed, lng, race, wasmenu, held; ll at, vat, heldat, shotat; } StartSt;   /* New-StartState */
enum { A_GRAB = 1, A_SAVE, A_DROP, A_EXIT };
static int step_start(StartSt *s, int down, int view, int menu, ll now, int *acts) {   /* Step-Start: what to do now, in order */
    int n = 0;
    if (s->wasmenu && !menu) s->race = 1;
    if (s->held) {
        if (menu) { s->held = 0; s->race = 0; acts[n++] = A_DROP; }                         /* that START began a new game */
        else if (SECS(now - s->heldat) >= 1.5) { s->held = 0; acts[n++] = A_SAVE; }
    }
    if (menu) { s->armed = 0; s->varmed = 0; }                                               /* a press that sees the menus does nothing */
    if (down && !s->was) { s->armed = s->race && !menu; s->at = now; }
    else if (!down && s->was) {
        if (s->armed && SECS(now - s->at) < HOLD && !s->held && SECS(now - s->shotat) > 2) { s->held = 1; s->heldat = now; s->shotat = now; acts[n++] = A_GRAB; }
        s->armed = 0;
    }
    if (view && !s->vwas) { s->varmed = s->race && !menu; s->vat = now; s->lng = 0; }
    else if (view && s->varmed && !s->lng && SECS(now - s->vat) >= HOLD) { s->lng = 1; acts[n++] = A_EXIT; }
    else if (!view) s->varmed = 0;
    s->was = down; s->vwas = view; s->wasmenu = menu;
    return n;
}
/* ConvertTo-Json -Compress's text (Windows PowerShell 5.1, JavaScriptSerializer): " \ and control characters escaped, and
 * ' < > & as \u0027 \u003c \u003e \u0026; numbers as .NET's "R" (15 digits, 17 when 15 do not give the value back), -0 as 0. */
static void jesc(char *o, size_t cap, const char *s) {
    size_t n = 0;
    o[n++] = '"';
    for (; *s && n + 8 < cap; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') { o[n++] = '\\'; o[n++] = (char)c; }
        else if (c == '\b') { o[n++] = '\\'; o[n++] = 'b'; } else if (c == '\f') { o[n++] = '\\'; o[n++] = 'f'; }
        else if (c == '\n') { o[n++] = '\\'; o[n++] = 'n'; } else if (c == '\r') { o[n++] = '\\'; o[n++] = 'r'; } else if (c == '\t') { o[n++] = '\\'; o[n++] = 't'; }
        else if (c < 0x20 || c == '\'' || c == '<' || c == '>' || c == '&') n += (size_t)snprintf(o + n, cap - n, "\\u%04x", c);
        else o[n++] = (char)c;
    }
    o[n++] = '"'; o[n] = 0;
}
static void jnum(char *o, double v) { if (v == 0) v = 0; snprintf(o, 40, "%.15G", v); if (strtod(o, NULL) != v) snprintf(o, 40, "%.17G", v); }       /* (o: 40 bytes) */
static double round_even(double v, double p) { return __builtin_rint(v * p) / p; }     /* [Math]::Round(v, digits): x 10^digits, to even, / 10^digits */
static int floats(ll va, int n, double *o) { float f[16]; int i; if (!rd(va, f, 4u * n)) return 0; for (i = 0; i < n; i++) o[i] = round_even((double)f[i], 10000.0); return 1; }
static void jarr(char *o, const double *v) { char a[40], b[40], c[40]; jnum(a, v[0]); jnum(b, v[1]); jnum(c, v[2]); snprintf(o, 130, "[%s,%s,%s]", a, b, c); }
static void fmt_time(char *o, size_t cap, ll t, const char *f) { FILETIME ft; SYSTEMTIME s; ft.dwLowDateTime = (DWORD)t; ft.dwHighDateTime = (DWORD)(t >> 32); FileTimeToSystemTime(&ft, &s);
    if (!strcmp(f, "iso")) snprintf(o, cap, "%04d-%02d-%02dT%02d:%02d:%02d.%03d", s.wYear, s.wMonth, s.wDay, s.wHour, s.wMinute, s.wSecond, s.wMilliseconds);
    else snprintf(o, cap, "SR3_%04d%02d%02d_%02d%02d%02d.png", s.wYear, s.wMonth, s.wDay, s.wHour, s.wMinute, s.wSecond); }
static void shot_info(ll base, const char *track, int dir, const char *title, ll at, char *o, size_t cap) {   /* Get-ShotInfo: one line of JSON */
    char t[40], e[300], cam[2400], car[300] = "", tr[700], x[120]; double v[16], fov, p[3], f[3]; int pl, hv, hf; ll mgr; size_t n = 0;
    fmt_time(t, sizeof t, at, "iso");
    pl = gi(0x9F05F0); if (pl < 0 || pl > 3) pl = 0;
    hv = floats(0x9EB970 + 0x4D0LL * pl, 16, v); hf = floats(0x9EBDA8 + 0x4D0LL * pl, 1, &fov);
    jesc(e, sizeof e, "view matrix 0x9EB970 (the frame's camera to world)"); n += (size_t)snprintf(cam + n, sizeof cam - n, "{\"source\":%s", e);
    if (hv) { double a[3] = {v[12], v[13], v[14]}, b[3] = {v[8], v[9], v[10]}, c[3] = {v[4], v[5], v[6]}; char s1[130], s2[130], s3[130]; jarr(s1, a); jarr(s2, b); jarr(s3, c); n += (size_t)snprintf(cam + n, sizeof cam - n, ",\"eye\":%s,\"forward\":%s,\"up\":%s", s1, s2, s3); }
    if (hf) { jnum(x, round_even(fov * 180 / 3.141592653589793, 100.0)); n += (size_t)snprintf(cam + n, sizeof cam - n, ",\"fov_deg\":%s", x); }
    if ((mgr = gp(0x9EB4EC))) {
        ll drawn; int idx; char nm[40] = "";
        mgr += 0x18; drawn = gp(mgr + 0x184); idx = gi(mgr + 0x230);
        n += (size_t)snprintf(cam + n, sizeof cam - n, ",\"vtable\":\"0x%llX\",\"list_index\":%d", gp(drawn), idx);
        if (base && idx >= 0 && idx < 21 && drawn == gp(mgr + 0x234 + 4LL * idx)) {          /* the race list's camera (the block's popup naming) */
            int ng = gi(base + 0x2260), ns = gi(base + 0x20), i;
            if (idx == 0) gstr(base + 0x100, 32, nm);
            else if (idx > ng && (idx - ng) < ns) gstr(base + 0x100 + 32LL * (idx - ng), 32, nm);
            else { ll off = drawn - mgr; if (idx == gi(base + 0x225C)) off |= 0x80000000LL; for (i = 0; i < 12; i++) if (gp(base + 0x21B0 + 4LL * i) == off) gstr(base + 0x2000 + 32LL * i, 32, nm); }
        }
        jesc(e, sizeof e, nm[0] ? nm : "not a race-list camera (intro, replay, trackside)"); n += (size_t)snprintf(cam + n, sizeof cam - n, ",\"name\":%s", e);
        { ll c = gp(mgr + 0x1C8); if (c && floats(c + 0xAC, 3, p) && floats(c + 0x135C + 0x20, 3, f)) { char s1[130], s2[130]; jarr(s1, p); jarr(s2, f); snprintf(car, sizeof car, ",\"car\":{\"pos\":%s,\"forward\":%s}", s1, s2); } }
    }
    snprintf(cam + n, sizeof cam - n, "}");
    { char a[200], b[200], c[300], fo[200];
      if (!track[0]) fo[0] = 0; else if (dir == 's') snprintf(fo, sizeof fo, "tracks\\%s", track); else snprintf(fo, sizeof fo, "track%c\\%s", dir, track);
      jesc(a, sizeof a, track); jesc(b, sizeof b, fo); jesc(c, sizeof c, title); snprintf(tr, sizeof tr, "{\"name\":%s,\"folder\":%s,\"title\":%s}", a, b, c); }
    snprintf(o, cap, "{\"time\":\"%s\",\"coords\":\"game (y up)\"%s,\"camera\":%s,\"track\":%s}", t, car, cam, tr);
}
/* Leaving a race the way the game itself does (FINDINGS.md, "Leaving a race"; patches.ps1 Request-RaceExit .. Step-RaceExit) */
#define RACE_EXIT_FLAG 0x9DB4F4
#define GAME_STATE 0x7ECE10
#define GAME_MODE 0x728598
#define FADE 0x9DB490
#define GAME_CLOCK 0x9C4A08
#define CHAMP_STAGE 0x9DB820
#define PLAYER_POS 0x9DD61C
static struct { int on, mode, taken, has_stage, stage, has_fade, pos; ll at; unsigned char fade[0x1C]; } RX;   /* $script:RaceExit */
static const char *race_mode(int m) { return m == 5 ? "Quick Race" : m == 6 ? "Championship" : m == 7 ? "Classic race" : NULL; }
static void undo_view_step(ll base) {
    ll mgr = gp(0x9EB4EC), cam; int n, i, p;
    if (!mgr || !base) return;
    mgr += 0x18; n = gi(mgr + 0x22C); i = gi(mgr + 0x230);
    if (n < 2 || n > 21 || i < 0 || i >= n) return;
    p = (i - 1 + n) % n; cam = gp(mgr + 0x234 + 4LL * p);
    if (!cam) return;
    G->suspend(G);
    wi(mgr + 0x190, cam); wi(base + 0xB0, 1); wi(mgr + 0x230, p); wi(base + 0x1C, -1);
    G->resume(G);
}
static void undo_race_exit(const char *why) {
    wi(RACE_EXIT_FLAG, 0);
    if (RX.has_stage) wi(CHAMP_STAGE, RX.stage);
    if (RX.has_fade) wr(FADE, RX.fade, 0x1C, 1);                                             /* the fade as it was: the picture is back at once */
    pc_logf("Race exit: %s; nothing changed in the game.", why);
    RX.on = 0;
}
static void request_race_exit(ll now) {
    int st[2], mode = gi(GAME_MODE); unsigned char f[0x1C]; ll c1, c2;
    if (!rd(GAME_STATE, st, 8)) { pc_logf("Race exit: the game state could not be read; nothing done."); return; }
    if (st[0] != 0x27 || st[1] != 0x27 || !race_mode(mode)) { pc_logf("Race exit: VIEW CHANGE was held, but no race is running (game state 0x%X / 0x%X, mode %d); nothing done.", st[0], st[1], mode); return; }
    memset(&RX, 0, sizeof RX); RX.at = now; RX.mode = mode;
    if (mode == 6) {
        int n = gi((ll)gi((ll)gi(0xB2A850) + 0x10) + 4);
        if (n < 1 || n > 16) { pc_logf("Race exit: the championship's number of stages could not be read (%d); nothing done.", n); return; }
        RX.has_stage = 1; RX.stage = gi(CHAMP_STAGE); wi(CHAMP_STAGE, n);
    }
    if (rd(FADE, f, 0x1C) && rd(GAME_CLOCK, &c1, 8) && rd(GAME_CLOCK, &c2, 8) && *(int *)(f + 8) != 0 && (int)(c1 >> 32) == (int)(c2 >> 32)) {   /* the fade to black as 0x5FBB10(500 ms, 0, 1) starts it, in one write */
        ll ms = (c2 - (c2 % 1000)) / 1000; int z = 0, o = 1; float h = 500;
        RX.has_fade = 1; memcpy(RX.fade, f, 0x1C);
        memcpy(f, &ms, 8); memcpy(f + 8, &z, 4); memcpy(f + 0xC, &o, 4); memcpy(f + 0x10, &z, 4); memcpy(f + 0x18, &h, 4);
        wr(FADE, f, 0x1C, 1);
    }
    if (!rd(GAME_STATE, st, 8) || st[0] != 0x27 || st[1] != 0x27) { undo_race_exit("the race ended just then"); return; }   /* a load must never be cut short */
    wi(RACE_EXIT_FLAG, 1);
    RX.on = 1;
    pc_logf("Race exit: VIEW CHANGE held %.15G s: leaving the %s for the main menu.", HOLD, race_mode(mode));
}
static void step_race_exit(ll now) {
    double t; int st[2], cur, next, stopped;
    if (!RX.on) return;
    t = SECS(now - RX.at);
    if (!rd(GAME_STATE, st, 8)) { RX.on = 0; return; }
    cur = st[0]; next = st[1];
    if (!RX.taken) {
        if (gi(RACE_EXIT_FLAG) == 0 || next == 0x1B || cur == 0x1B || cur == 0x2A) RX.taken = 1;
        else if (cur == 0x27 && next == 0x27) { if (t >= 2) undo_race_exit("the game did not take the request within 2 s"); return; }
        else { char w[160]; snprintf(w, sizeof w, "the race ended another way before the game read the request (state 0x%X / 0x%X)", cur, next); undo_race_exit(w); return; }
    }
    stopped = (cur == 0x27 && next != 0x27) || cur == 0x1B || cur == 0x2A;
    if (RX.mode == 6 && stopped && gi(PLAYER_POS) == 1) {
        wi(PLAYER_POS, 2);
        if (!RX.pos) { RX.pos = 1; pc_logf("Race exit: you were leading the championship; the bonus stage is skipped."); }
    }
    if (cur == 0x2A && t > 4 && gi(FADE + 8) == 0) { wi(FADE + 8, 1); pc_logf("Race exit: the fade to black did not finish; the game goes on without it."); }
    if (!stopped && cur != 0x27) { pc_logf("Race exit: done, the game is on its way to the menus (state 0x%X).", cur); RX.on = 0; return; }
    if (t > 15) { pc_logf("Race exit: the game is still in state 0x%X / 0x%X after 15 s; no longer followed.", cur, next); RX.on = 0; }
}

/* ---------------------------------------------------------------- Wait-GameExit, Watch-Tracks */
static void wait_game_exit(void) {
    while (G->alive(G)) {
        if (CLP.on && complete_car_lists()) pc_logf("Car lists: every car in every mode from this game on.");
        if (G->news) G->news(G);
        G->sleep(G, 250);
    }
    if (G->news) G->news(G);
}
static const struct { ll site, own, text; int kind; const char *fmt; } SOUNDS[3] = {
    {0x644EA5, 0x6D5EF0, 0x2700, 0, "SFX_AMBIENT_%s"}, {0x6451C5, 0x6D5E7C, 0x2740, 1, "MU_RACE_%s"}, {0x63382B, 0x6D5EA0, 0x2780, 2, "\\Audio\\%s_Events.bin"}};
static const int KEY_CODES[8] = {0x31, 0x32, 0x33, 0x61, 0x62, 0x63, 0x30, 0x60};           /* $HandlingKeyCodes */
static const char *key_flavor(int vk) { return vk == 0x31 || vk == 0x61 ? "sr3" : vk == 0x32 || vk == 0x62 ? "src" : vk == 0x33 || vk == 0x63 ? "realism" : NULL; }
#define LIME_ 0xFF9CFF3Au
#define WHITE_ 0xFFFFFFFFu
static void popup(ll base, ll first, unsigned color, ll second) { wi(base + 0x50, first); wi(base + 0xE60, color); wi(base + 0x2268, second); wi(base + 0xFA0, 1); wi(base + 0x10, 20); }
static void watch_tracks(void) {
    StartSt st; ll base, text, tdcave = 0, shot_until = 0, label_until = 0; int cards_open, i, keys_down[8] = {0};
    char sound_now[120] = "//", tune_now[80] = "", name_was[32] = "", times_now[120] = "", shown[200] = "", shot_name[64] = "", l0[64] = "", l1[96] = "", dir_now = 's';
    char *shot_info_s = NULL; int shot_held = 0, pvs_held = 0, pvs_was = 0, mode_seen_on = 0, mode_seen = 0, mode_last_on = 0, mode_last = 0, classic_on = 0, classic_val = 0;
    int was_down = 0, was_menu = 0, deep = 0, showing = 0;
    char classic_file[1100];
    memset(&st, 0, sizeof st); RX.on = 0;
    read_track_switch();
    if (!(base = find_cycle())) { pc_logf("Alternative tracks, the START screenshot and the VIEW CHANGE race exit need the camera patch; it is not in the game."); wait_game_exit(); return; }
    TD_LAST_ON = 0;
    if (NSL) {
        char line[1024]; size_t n = 0; Slot *v[16]; int m = sorted_slots(v);
        for (i = 0; i < m; i++) n += (size_t)snprintf(line + n, sizeof line - n, "%s%s +%d", i ? ", " : "", v[i]->name, v[i]->n - 1);
        pc_logf("Alternative tracks: %s. On the stage-select screen, View Change steps through them.", line);
        initialize_track_videos(base);
        if ((tdcave = install_trackdir())) pc_logf("Track folders: chosen in the game's own path code (each load reads one folder).");
    }
    cards_open = open_car_cards(base) != 0;                                                  /* before the first menus: the car select looks its cards up when they are built */
    text = base + 0x2400;
    wstr(text + 0x40, "Press VIEW CHANGE to select alternative tracks", 64);
    for (i = 0; i < NSL; i++) SL[i].choice = 0;
    TUNE_OWN.on = 0; IDS.n = 0;
    jp(classic_file, sizeof classic_file, GAMEDIR, "Main_release\\tracks\\_SR3Extras\\classic_mode.txt");
    if (exists(classic_file)) { char t[64]; if (text_of(classic_file, t, sizeof t)) { const char *q = t[0] == '-' ? t + 1 : t; if (digits(q, 1, 10)) { classic_on = 1; classic_val = atoi(t); } } }
    while (G->alive(G)) {
        unsigned char g, vb; int menu, count, stage, p1, hi, down, mode, mode_val, n_acts, acts[4], buttons, all_visible, a;
        char name[32] = "", hi_name[32] = "", sound[120], tune_key[80], key[120];
        Slot *hlist, *list, *classic = slot("Desert4"); Trk *cur; int dir;
        if (!rd(0x9D6E3C, &g, 1)) break;
        menu = g == 1;
        if (CLP.on && !menu && complete_car_lists()) pc_logf("Car lists: every car in every mode from this game on.");   /* (Set-CarLists: the menus were up when it ran) */
        if (menu && !was_menu) {                                                             /* a new game: every card back to its own track */
            if (!cards_open) cards_open = open_car_cards(base) != 0;
            deep = 0;
            for (i = 0; i < NSL; i++) { if (SL[i].choice != 0) set_card_track(base, &SL[i], &SL[i].t[0], 1); SL[i].choice = 0; }
        }
        count = gi(0x9C442C);
        if (menu && (count >= 6 || count == 2)) deep = 1;                                    /* past the mode menu, which also has 3 entries */
        stage = menu && deep && count == 3;
        if ((p1 = gi(0x9DBDB0))) { int p2 = gi((ll)p1 + 0x18); if (p2) gstr(p2, 24, name); }
        hi = gi(base + 0x226C);                                                              /* the card the stage selector is on */
        if (hi != -1) { const char *nm; if (!track_name(hi)) read_track_names(); if ((nm = track_name(hi))) snprintf(hi_name, sizeof hi_name, "%s", nm); }
        stage = stage && hi_name[0];
        hlist = stage ? slot(hi_name) : NULL;
        down = rd(0x9DBB0C, &vb, 1) && vb != 0;
        if (hlist && down && !was_down) { hlist->choice = (hlist->choice + 1) % hlist->n; set_card_track(base, hlist, &hlist->t[hlist->choice], hlist->choice == 0); }
        mode = menu && !deep && count == 3 && classic;                                       /* Classic: its tracks (the Desert4 slot) are stepped through on the first menu */
        mode_val = gi(base + 0x2278);
        if (mode && mode_val != -1) { if (!mode_seen_on || mode_val != mode_seen) { pc_logf("Alternative tracks: first menu is on entry %d.", mode_val); mode_seen = mode_val; mode_seen_on = 1; } mode_last = mode_val; mode_last_on = 1; }
        if (ieq(name, "Desert4") && name_was[0] && !ieq(name_was, "Desert4") && mode_last_on && !classic_on) {     /* learnt once: a value already kept is never overwritten */
            char t[16]; classic_val = mode_last; classic_on = 1; pc_logf("Alternative tracks: Classic is entry %d of the first menu.", classic_val);
            snprintf(t, sizeof t, "%d", classic_val); put_file(classic_file, t);
        }
        if (name[0]) snprintf(name_was, sizeof name_was, "%s", name);
        if (mode && classic_on && mode_val != classic_val) mode = 0;
        if (mode && down && !was_down) { classic->choice = (classic->choice + 1) % classic->n; set_card_track(base, classic, &classic->t[classic->choice], classic->choice == 0); }
        if (stage) snprintf(name, sizeof name, "%s", hi_name);                               /* the game reads the files of the chosen track */
        list = slot(name);
        dir = list ? list->t[list->choice].dir : 's';
        if (tdcave) write_trackdir_table(tdcave);
        if (dir != dir_now) {
            if (!tdcave) for (i = 0; i < 6; i++) w1(TRACK_DIR_SITES[i], dir, 1);
            if (ART) { w1(0x6BCF0F, dir == 's' ? 'D' : dir, 1); for (i = 0; i < 5; i++) w1(TRACK_BANNER_SITES[i], dir == 's' ? 'R' : dir, 1); }
            dir_now = (char)dir;
        }
        snprintf(key, sizeof key, "%s/%c", name, dir);
        if (_stricmp(key, times_now)) { set_arcade_times(name, dir); set_shadow_params(name, dir); set_shader_test(name, dir); set_road_hide(name, dir); snprintf(times_now, sizeof times_now, "%s", key); }
        cur = list ? &list->t[list->choice] : NULL;
        if (cur) snprintf(sound, sizeof sound, "%s/%s/%s", cur->snd[0], cur->snd[1], cur->snd[2]); else snprintf(sound, sizeof sound, "//");
        if (_stricmp(sound, sound_now)) {
            for (i = 0; i < 3; i++) {
                const char *id = cur ? cur->snd[SOUNDS[i].kind] : ""; ll to = SOUNDS[i].own;
                if (id[0]) { char nm[96]; to = base + SOUNDS[i].text; snprintf(nm, sizeof nm, SOUNDS[i].fmt, id); wstr(to, nm, 64); }
                wi(SOUNDS[i].site, to);
            }
            snprintf(sound_now, sizeof sound_now, "%s", sound);
        }
        if (cur && cur->has_tune) snprintf(tune_key, sizeof tune_key, "%d/%lld/%lld/%lld", cur->tune.stream, cur->tune.off, cur->tune.bytes, cur->tune.loop); else tune_key[0] = 0;
        if (_stricmp(tune_key, tune_now) && set_course_tune(cur && cur->has_tune ? &cur->tune : NULL)) snprintf(tune_now, sizeof tune_now, "%s", tune_key);
        all_visible = !menu && dir != 's';                                                   /* an added track: every scenery node visible ([0xA65794]) */
        if (all_visible) { int v = gi(0xA65794); if (!pvs_held) { pvs_was = v; pvs_held = 1; } if (v != 1) wi(0xA65794, 1); }
        else if (pvs_held) { wi(0xA65794, pvs_was); pvs_held = 0; }
        buttons = (gi(0x9DBBA4) & 0x7FFF ? 0x10 : 0) | (gi(0x9DBB0C) & 0x7FFF ? 0x1000 : 0);   /* Get-GameButtons: the game's own START (entry 53) and View Change (15) */
        n_acts = step_start(&st, (buttons & 0x10) != 0, (buttons & 0x1000) != 0, menu, G->now(G), acts);
        for (a = 0; a < n_acts; a++) {
            if (acts[a] == A_GRAB) {
                if (G->shot(G, 1, NULL, NULL)) {
                    static char info[4096];
                    shot_held = 1; shot_info(base, name, dir, cur ? cur->title : "", G->now(G), info, sizeof info); shot_info_s = info;
                } else { pc_logf("Screenshot failed: the screen could not be read"); shot_held = 0; st.held = 0; }
            } else if (acts[a] == A_SAVE && shot_held) {
                char dirp[1100], path[1200], *s; wchar_t w[1100];
                snprintf(dirp, sizeof dirp, "%s", MODDIR); if ((s = strrchr(dirp, '\\'))) *s = 0; jp(dirp, sizeof dirp, dirp, "Screenshots");
                wpath(dirp, w); CreateDirectoryW(w, NULL);
                fmt_time(shot_name, sizeof shot_name, st.shotat, "png"); jp(path, sizeof path, dirp, shot_name);
                if (G->shot(G, 2, path, shot_info_s)) { shot_until = G->now(G) + 3 * TICKS_S; pc_logf("Screenshot: %s", shot_name); }
                else pc_logf("Screenshot failed: %s could not be written", shot_name);
                G->shot(G, 3, NULL, NULL); shot_held = 0;
            } else if (acts[a] == A_DROP && shot_held) { G->shot(G, 3, NULL, NULL); shot_held = 0; }
            else if (acts[a] == A_EXIT) { request_race_exit(G->now(G)); if (RX.on) undo_view_step(base); }
        }
        if (RX.on) step_race_exit(G->now(G));
        if (G->news) G->news(G);
        if (HD.on && HD.nfl && (ll)G->front(G) == gp(0x728CF4)) {                            /* the handling keys (Set-Handling) */
            for (i = 0; i < 8; i++) {
                int dn = G->key(G, KEY_CODES[i]) != 0;
                if (dn && !keys_down[i]) {
                    char o[64]; const char *car = key_car(base, menu, o);
                    if (!car) { snprintf(l0, sizeof l0, "No car yet"); snprintf(l1, sizeof l1, "pick one on the car select"); }
                    else if (key_flavor(KEY_CODES[i])) set_car_handling_live(car, key_flavor(KEY_CODES[i]), l0, l1);
                    else { Pl *p = plan(car); char t[128]; car_title(car, t, sizeof t); snprintf(l0, sizeof l0, "Handling: %s", flavor_title(p && p->f[0] ? p->f : "sr3")); snprintf(l1, sizeof l1, "%s", t); }   /* Show-CarHandling */
                    label_until = G->now(G) + 25000000LL;                                    /* 2.5 s */
                }
                keys_down[i] = dn;
            }
        }
        if (label_until > G->now(G)) {                                                       /* a handling key's label, over everything else for 2.5 s */
            char lt[200]; snprintf(lt, sizeof lt, "%s|%s", l0, l1);
            if (_stricmp(lt, shown)) { wstr(text, l0, 48); wstr(text + 0x80, l1, 64); snprintf(shown, sizeof shown, "%s", lt); }
            popup(base, text, LIME_, text + 0x80); showing = 1;
        } else if (mode) {
            char title[200]; snprintf(title, sizeof title, "Classic: %s", classic->t[classic->choice].title);
            if (_stricmp(title, shown)) { wstr(text, title, 48); snprintf(shown, sizeof shown, "%s", title); }
            popup(base, text, classic->choice ? LIME_ : WHITE_, text + 0x40); showing = 1;
        } else if (stage && list) {
            const char *title = list->t[list->choice].title;
            if (_stricmp(title, shown)) { wstr(text, title, 48); snprintf(shown, sizeof shown, "%s", title); }
            popup(base, text, list->choice ? LIME_ : WHITE_, text + 0x40); showing = 1;
        } else if (shot_until > G->now(G)) {
            static const unsigned char z2[2] = {0, 0};
            if (_stricmp(shot_name, shown)) { wstr(text, shot_name, 48); snprintf(shown, sizeof shown, "%s", shot_name); }
            wi(base + 0x50, text); wi(base + 0xE60, WHITE_);
            wr(text + 0x78, z2, 2, 1);                                                       /* an empty second line (0 here would bring the popup's own hint back) */
            wi(base + 0x2268, text + 0x78); wi(base + 0xFA0, 1); wi(base + 0x10, 20); showing = 1;
        } else if (showing) { wi(base + 0x10, 0); wi(base + 0xFA0, 0); wi(base + 0x2268, 0); showing = 0; }
        sync_race_flavor();                                                                  /* every car of the next race on the player's car's handling */
        if (was_menu && !menu && RACE_FLAVOR[0]) {                                          /* a race starts */
            char c[128], *s; snprintf(c, sizeof c, "%s", RACE_FLAVOR); if ((s = strchr(c, '/'))) *s = 0;
            pc_logf("Handling: this race on %s, the player's car's (%s); every car in it loads that handling.", flavor_title(RACE_FLAVOR_NAME), c);
        }
        was_down = down; was_menu = menu;
        G->sleep(G, 15);
    }
    wait_game_exit();
}

void pc_live(GameMem *m, const PcCfg *c, const char *game_exe) {
    char *s;
    G = m;
    snprintf(GAMEDIR, sizeof GAMEDIR, "%s", game_exe ? game_exe : ""); if ((s = strrchr(GAMEDIR, '\\'))) *s = 0; else GAMEDIR[0] = 0;
    snprintf(MODDIR, sizeof MODDIR, "%s", c->mod);
    set_menu_timers();
    set_car_lists();
    set_handling();
    watch_tracks();
}
