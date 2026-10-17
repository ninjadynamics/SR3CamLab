/* patchcore: the in-game patches, written once; sr3mods.dll (inside the game) and sr3mods.exe (from outside) both run
 * it, each with its own GameMem (patchcore.h). Each part names the sr3mods.ps1 lines it does; the bytes come from
 * sr3mods.ps1 (blobs.h, gen_blobs.py). Step 1 (2026-10-15): the cameras - the chase camera's cave and hooks ($Patches)
 * and the camera cycle block (Install-Cycle). */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <locale.h>
#include "settings.h"
#include "blobs.h"
#include "patchcore.h"

#define CAVE_VA     0x673C80u
#define TUNABLE_LO  0x08
#define LIMIT_OFF   0x54
#define FRAMING_OFF 0x68
#define MULT_OFF    0x50
#define DIAG_LO     0x34

void (*pc_log)(const char *line);
static _locale_t cloc;                /* numbers are read in the C locale whatever the game sets */

void pc_logf(const char *fmt, ...) {
    char b[1024]; va_list a;
    if (!pc_log) return;
    va_start(a, fmt); vsnprintf(b, sizeof b, fmt, a); va_end(a); pc_log(b);
}
void pc_init(void) { if (!cloc) cloc = _create_locale(LC_NUMERIC, "C"); }
const char *pc_source(void) { return SR3MODS_SOURCE; }

/* ---------------------------------------------------------------- profiles.yaml (sr3mods.ps1 Read-ProfilesYaml)
 * Its YAML subset: top-level "default:" and "profiles:", one mapping per profile, "key: value" below it, '#' comments
 * (cut at the first '#' of a line), quotes trimmed off both ends of keys and values, keys case-insensitive. */
#define MAXP 48
#define MAXK 32
typedef struct { char name[64]; int n; char k[MAXK][32], v[MAXK][96]; } Prof;
typedef struct { char def[64]; int np, ntop; Prof p[MAXP]; char tk[MAXK][32], tv[MAXK][96]; } Yaml;

static void trim(char *s, const char *chars) {
    size_t n = strlen(s), i = 0;
    while (n && strchr(chars, s[n - 1])) s[--n] = 0;
    while (s[i] && strchr(chars, s[i])) i++;
    if (i) memmove(s, s + i, n - i + 1);
}
static void lower(char *s) { for (; *s; s++) if (*s >= 'A' && *s <= 'Z') *s += 32; }
static int read_yaml(const char *path, Yaml *y) {
    FILE *f = fopen(path, "rb"); char line[512]; int inprof = 0, pind = -1; Prof *cur = NULL;
    memset(y, 0, sizeof *y);
    if (!f) return 0;
    while (fgets(line, sizeof line, f)) {
        char *h = strchr(line, '#'), *c, key[64], val[128]; int ind = 0;
        if (h) *h = 0;
        { size_t n = strlen(line); while (n && strchr(" \t\r\n", line[n - 1])) line[--n] = 0; }
        if (!line[strspn(line, " \t")]) continue;
        while (line[ind] == ' ') ind++;
        c = strchr(line + ind, ':');
        if (!c) continue;
        snprintf(key, sizeof key, "%.*s", (int)(c - (line + ind)), line + ind); snprintf(val, sizeof val, "%s", c + 1);
        trim(key, " \t"); trim(key, "\"'"); trim(val, " \t"); trim(val, "\"'");
        if (ind == 0) {
            inprof = !_stricmp(key, "profiles");
            if (!_stricmp(key, "default")) snprintf(y->def, sizeof y->def, "%s", val);
            else if (!inprof && y->ntop < MAXK) { lower(key); snprintf(y->tk[y->ntop], 32, "%s", key); snprintf(y->tv[y->ntop++], 96, "%s", val); }
            cur = NULL; continue;
        }
        if (!inprof) continue;
        if (pind < 0) pind = ind;
        if (ind == pind) { if (y->np < MAXP) { cur = &y->p[y->np++]; memset(cur, 0, sizeof *cur); snprintf(cur->name, sizeof cur->name, "%s", key); } else cur = NULL; }
        else if (cur && ind > pind && cur->n < MAXK) { lower(key); snprintf(cur->k[cur->n], 32, "%s", key); snprintf(cur->v[cur->n++], 96, "%s", val); }
    }
    fclose(f); return 1;
}
static const char *pget(const Prof *p, const char *key) {
    int i; for (i = 0; i < p->n; i++) if (!_stricmp(p->k[i], key)) return p->v[i];
    return "";
}
static const char *tget(const Yaml *y, const char *key) {
    int i; for (i = 0; i < y->ntop; i++) if (!_stricmp(y->tk[i], key)) return y->tv[i];
    return "";
}
/* [double]::TryParse(s, Float, Invariant): white space, a sign, digits with a point, an exponent. (Infinity and NaN,
 * which .NET also takes, are refused here: no tuning value means them.) */
static int num(const char *s, double *out) {
    char *e; double v; const char *p = s;
    while (*p == ' ' || *p == '\t') p++;
    if (!*p || strpbrk(p, "xXnNiI")) return 0;
    v = _strtod_l(p, &e, cloc);
    while (*e == ' ' || *e == '\t') e++;
    if (*e || e == p) return 0;
    *out = v; return 1;
}
static int has(const Prof *p, const char *k) { char t[96]; snprintf(t, sizeof t, "%s", pget(p, k)); trim(t, " \t"); return t[0] != 0; }

/* ---------------------------------------------------------------- the cave image of one profile (Get-CaveImage) */
static int cave_image(const Prof *r, int stock, unsigned char *b, char *err, size_t cap) {
    double S, F0, F1, K0, K1, Dm, MA = 180, CS = 0.4, kn, rg, v[7], lim[3]; int fr, i;
    const char *need[6] = {"strength", "fadeinstartkmh", "fadeinfullkmh", "stiffnessmin", "stiffnessmax", "damping"}; double *dst[6] = {&S, &F0, &F1, &K0, &K1, &Dm};
    for (i = 0; i < 6; i++) if (!num(pget(r, need[i]), dst[i])) { snprintf(err, cap, "Profile '%s': '%s' is missing or not a number (use a dot as decimal separator).", r->name, need[i]); return 0; }
    if (has(r, "maxangle") && !num(pget(r, "maxangle"), &MA)) { snprintf(err, cap, "Profile '%s': 'MaxAngle' is not a number.", r->name); return 0; }
    if (has(r, "capstiffness") && !num(pget(r, "capstiffness"), &CS)) { snprintf(err, cap, "Profile '%s': 'CapStiffness' is not a number.", r->name); return 0; }
    fr = has(r, "distance") && has(r, "height") && has(r, "fov");
    if (S < 0 || S > 1) { snprintf(err, cap, "%s: Strength must be between 0 and 1.", r->name); return 0; }
    if (F0 < 0 || F1 <= F0) { snprintf(err, cap, "%s: FadeInFullKmh must be greater than FadeInStartKmh (both >= 0).", r->name); return 0; }
    if (K0 <= 0 || K1 < K0 || K1 > 500) { snprintf(err, cap, "%s: need 0 < StiffnessMin <= StiffnessMax <= 500.", r->name); return 0; }
    if (Dm <= 0 || Dm > 100) { snprintf(err, cap, "%s: Damping must be between 0 and 100.", r->name); return 0; }
    if (MA < 1 || MA > 180) { snprintf(err, cap, "%s: MaxAngle must be between 1 and 180 degrees.", r->name); return 0; }
    if (CS < 0 || CS > 1) { snprintf(err, cap, "%s: CapStiffness must be between 0 and 1.", r->name); return 0; }
    if (MA >= 180) { kn = 3.14159265358979323846; rg = 1e-4; }
    else { double m = MA * 3.14159265358979323846 / 180; kn = CS * m; rg = m - kn > 1e-4 ? m - kn : 1e-4; }
    memcpy(b, PATCHES[0].neu, PATCHES[0].len);
    v[0] = S; v[1] = F0 / 3.6; v[2] = 1.0 / ((F1 - F0) / 3.6); v[3] = 2.0; v[4] = K0; v[5] = K1; v[6] = -Dm;
    for (i = 0; i < 7; i++) { float f = (float)v[i]; memcpy(b + TUNABLE_LO + 4 * i, &f, 4); }
    lim[0] = kn; lim[1] = rg; lim[2] = 1.0 / rg;
    for (i = 0; i < 3; i++) { float f = (float)lim[i]; memcpy(b + LIMIT_OFF + 4 * i, &f, 4); }
    memcpy(b + FRAMING_OFF, &fr, 4);
    if (fr) {
        double d, h, fv; float f3[3];
        if (!num(pget(r, "distance"), &d) || !num(pget(r, "height"), &h) || !num(pget(r, "fov"), &fv)) { snprintf(err, cap, "Profile '%s': framing is not a number.", r->name); return 0; }
        if (d < 1 || d > 30 || h < 0 || h > 15 || fv < 20 || fv > 120) { snprintf(err, cap, "%s: framing out of range (distance 1-30 m, height 0-15 m, fov 20-120).", r->name); return 0; }
        f3[0] = (float)d; f3[1] = (float)h; f3[2] = (float)fv; memcpy(b + FRAMING_OFF + 4, f3, 12);
    }
    if (stock) { float f = 7.5f; memcpy(b + MULT_OFF, &f, 4); }
    return 1;
}

static void call_to(unsigned char *b, unsigned from, unsigned to) { int r = (int)(to - (from + 5)); b[0] = 0xE8; memcpy(b + 1, &r, 4); }
static void str_(unsigned char *dst, const char *t, int n) { int k = (int)strlen(t); memset(dst, 0, n); memcpy(dst, t, k < n - 1 ? k : n - 1); }
static void f32(unsigned char *dst, double v) { float f = (float)v; memcpy(dst, &f, 4); }
static void i32(unsigned char *dst, int v) { memcpy(dst, &v, 4); }
static int same(GameMem *m, unsigned va, const unsigned char *b, unsigned n) {
    unsigned char t[1024];
    if (n > sizeof t || !m->read(m, va, t, n)) return 0;
    return !memcmp(t, b, n);
}

/* ---------------------------------------------------------------- the settings (settings.yaml's patches: section) */
static int cfg_bool(const char *v, int def) { if (!v || !*v) return def; return !_stricmp(v, "true") || !_stricmp(v, "on") || !_stricmp(v, "yes") || !strcmp(v, "1"); }
int pc_load_cfg(const char *path, const char *default_mod, PcCfg *c, char *err, size_t cap) {
    static Sr3Settings s; const char *v; double d;
    memset(c, 0, sizeof *c); c->overlay = -1; c->mouse = -1; c->blend = -1; c->watchdog = 1; snprintf(c->mod, sizeof c->mod, "%s", default_mod);
    if (!path) return 1;
    if (!sr3_load_utf8(path, &s, err, cap)) return 0;              /* (1 = read, 0 = refused with the reason in err) */
    if ((v = sr3_patch_value(&s, "mod_folder")) && *v) snprintf(c->mod, sizeof c->mod, "%s", v);
    v = sr3_patch_value(&s, "camera_profile"); snprintf(c->profile, sizeof c->profile, "%s", v ? v : "");
    v = sr3_patch_value(&s, "profiles_file"); snprintf(c->profiles_file, sizeof c->profiles_file, "%s", v ? v : "");
    if ((v = sr3_patch_value(&s, "overlay")) && *v) { if (!num(v, &d)) { snprintf(err, cap, "patches.overlay: not a number"); return 0; } c->overlay = (int)d; }
    if ((v = sr3_patch_value(&s, "mouse_smoothing")) && *v) { if (!num(v, &c->mouse)) { snprintf(err, cap, "patches.mouse_smoothing: not a number"); return 0; } }
    if ((v = sr3_patch_value(&s, "camera_blend")) && *v) { if (!num(v, &c->blend)) { snprintf(err, cap, "patches.camera_blend: not a number"); return 0; } }
    c->canary = cfg_bool(sr3_patch_value(&s, "canary"), 0); c->watchdog = cfg_bool(sr3_patch_value(&s, "watchdog"), 1);
    return 1;
}

/* ---------------------------------------------------------------- the camera patch, made ready before the game is touched */
#define CYCLE_SIZE 0x4000
#define CYCLE_DRAW 0x1000
#define CYCLE_LOST 0x1d5d
#define CYCLE_ROT  0x1d27
#define CYCLE_FREE 0x1d42
#define CYCLE_CODE2_AT 0x2800
#define CYCLE_BLEND 0x308c
#define CYCLE_QOL  0x2280
#define MAX_SLOTS  21
#define SLOT_BYTES 0x5C
#define GAME_CAMS  12
static const unsigned HOOK_DRAW = 0x591C4D, HOOK_LOST = 0x591B01, HOOK_BLEND = 0x5C948C;
static const unsigned char DRAW_ORIG[5] = {0xa1, 0x0c, 0xd1, 0x7e, 0x00}, LOST_ORIG[5] = {0xe8, 0x1a, 0xf7, 0xff, 0xff}, BLEND_ORIG[5] = {0xe8, 0xff, 0x81, 0x02, 0x00};
static const struct { unsigned site, stock; int rot; } CAM_UPDATE[3] = {{0x6EBB3C, 0x5F1E00, 1}, {0x6ECBA4, 0x5F3FE0, 0}, {0x6ECC94, 0x5F3FE0, 0}};
#define WHITE 0xFFFFFFFFu
#define ORANGE 0xFFFF9A2Eu
#define LIME 0xFF9CFF3Au
static const struct { unsigned off; const char *name; unsigned color; } GAMECAM[9] = {
    {0x1700, "Game: Bumper cam", WHITE}, {0x189C, "Game: Bonnet cam", WHITE}, {0x8C4, "Debug: Chase cam far", ORANGE},
    {0x1A38, "Debug: Cockpit cam", ORANGE}, {0x80001A38, "Debug: Cockpit cam (patched)", ORANGE}, {0x1BD0, "Debug: Wheel cam", ORANGE},
    {0xEEC, "Debug: Car rotate cam", ORANGE}, {0xC78, "Debug: Free cam", ORANGE}, {0x1D68, "Debug: Car free cam", ORANGE}};
static const unsigned HIDDEN[7] = {0x8C4, 0x1A38, 0x80001A38, 0x1BD0, 0xEEC, 0xC78, 0x1D68};
static const Prof BASELINE = {"SR3 Chase", 8, {"strength", "fadeinstartkmh", "fadeinfullkmh", "stiffnessmin", "stiffnessmax", "damping", "maxangle", "capstiffness"},
                              {"0", "14", "43", "15", "90", "15", "180", "0.25"}};

typedef struct { char name[32], prof[64]; unsigned color; unsigned char image[1024]; } Slot;
static struct {
    unsigned char cave[1024]; Slot slot[MAX_SLOTS]; int nslot, start, overlay, hidden; double look, blend; char profile[64];
} cam;

static double seconds(const Yaml *y, const Yaml *own, const char *key, double sw, double def, double max) {
    double v = def, n; char t[96]; snprintf(t, sizeof t, "%s", tget(y, key)); trim(t, " \t");
    if (!t[0] && own) { snprintf(t, sizeof t, "%s", tget(own, key)); trim(t, " \t"); }
    if (!_stricmp(t, "off") || !_stricmp(t, "false") || !_stricmp(t, "no")) v = 0;
    else if (t[0] && num(t, &n)) v = n;
    if (sw >= 0) v = sw;
    return v < 0 ? 0 : v > max ? max : v;
}

/* sr3mods.ps1 lines 110-158 (which profile), 309-347 (slots, overlay, smoothing, blend) */
int pc_prepare_cameras(const PcCfg *c, char *err, size_t cap) {
    static Yaml y, own; char path[MAX_PATH], e2[256]; const Prof *row = NULL; int i, baseline, far_, haveown = 0;
    if (c->profiles_file[0]) snprintf(path, sizeof path, "%s", c->profiles_file); else snprintf(path, sizeof path, "%s\\profiles.yaml", c->mod);
    if (!read_yaml(path, &y)) { snprintf(err, cap, "Profile file not found: %s", path); return 0; }
    if (!y.np) { snprintf(err, cap, "%s has no profiles.", path); return 0; }
    if (c->profiles_file[0]) { char o[MAX_PATH]; snprintf(o, sizeof o, "%s\\profiles.yaml", c->mod); haveown = read_yaml(o, &own); }
    { const char *want = c->profile[0] ? c->profile : (y.def[0] ? y.def : y.p[0].name);
      far_ = !_stricmp(want, "SR3 Chase Far"); baseline = far_ || !_stricmp(want, "SR3 Chase") || !_stricmp(want, "Baseline");
      if (baseline) row = &BASELINE;
      else for (i = 0; i < y.np; i++) if (!_stricmp(y.p[i].name, want)) { row = &y.p[i]; break; }
      if (!row) { snprintf(err, cap, "Profile '%s' not found.", want); return 0; }
      snprintf(cam.profile, sizeof cam.profile, "%s", row->name); }
    if (!cave_image(row, baseline, cam.cave, err, cap)) return 0;
    if (c->canary) cam.cave[DIAG_LO] = 1;
    { char t[96]; snprintf(t, sizeof t, "%s", tget(&y, "hiddencameras")); trim(t, " \t");
      cam.hidden = !(!_stricmp(t, "false") || !_stricmp(t, "no") || !_stricmp(t, "off") || !strcmp(t, "0")); }
    cam.nslot = 0; snprintf(cam.slot[0].name, 32, "Game: Chase cam"); snprintf(cam.slot[0].prof, 64, "SR3 Chase"); cam.slot[0].color = WHITE;
    if (!cave_image(&BASELINE, 1, cam.slot[0].image, err, cap)) return 0;
    cam.nslot = 1;
    for (i = 0; i < y.np; i++) {
        const Prof *r = &y.p[i];
        if (!_stricmp(r->name, "Baseline") || !_stricmp(r->name, "SR3 Chase") || !_stricmp(r->name, "SR3 Chase Far")) continue;
        if (cam.nslot >= MAX_SLOTS - 2 - (cam.hidden ? 7 : 0)) { pc_logf("Too many profiles for the camera cycle; '%s' is left out.", r->name); continue; }
        if (!cave_image(r, 0, cam.slot[cam.nslot].image, e2, sizeof e2)) { pc_logf("Profile '%s' is left out of the camera cycle: %s", r->name, e2); continue; }
        snprintf(cam.slot[cam.nslot].name, 32, "CamLab: %s", r->name); snprintf(cam.slot[cam.nslot].prof, 64, "%s", r->name); cam.slot[cam.nslot].color = LIME; cam.nslot++;
    }
    cam.start = 0;
    for (i = 0; i < cam.nslot; i++) if (!_stricmp(cam.slot[i].prof, row->name)) cam.start = i;
    if (far_) cam.start = -2;
    { const char *o = tget(&y, "overlay"); char *e; long v; cam.overlay = 48;                 /* [int]::TryParse: a whole number */
      while (*o == ' ') o++;
      v = strtol(o, &e, 10); while (*e == ' ') e++;
      if (*o && !*e && e != o) cam.overlay = (int)v;
      if (c->overlay >= 0) cam.overlay = c->overlay;
      if (cam.overlay < 0) cam.overlay = 0;
      if (cam.overlay > 200) cam.overlay = 200; }
    cam.look = seconds(&y, haveown ? &own : NULL, "mousesmoothing", c->mouse, 0.08, 1.0);
    cam.blend = seconds(&y, haveown ? &own : NULL, "camerablend", c->blend, 0.5, 3.0);
    return 1;
}

/* ---------------------------------------------------------------- the camera cycle block (sr3mods.ps1 Find-Cycle .. Restore-CockpitSeat)
 * Written the way Install-Cycle writes it, write for write and in the same order, so a fresh game, a game this or an
 * older launcher already patched (PLAY.bat run again: the block kept, its settings rewritten) and a newer build (the
 * block's code differs: a fresh block, its state carried over) all end the same as with sr3mods.ps1
 * (live_lockstep.py's re-attach scenarios compare the writes). */
#define SETTINGS_HI 0x90
static int u32at(GameMem *m, unsigned va, unsigned *v) { return m->read(m, va, v, 4); }
static int sig_at(GameMem *m, unsigned va, const char *s) { char b[4]; return m->read(m, va, b, 4) && !memcmp(b, s, 4); }
static int same_big(GameMem *m, unsigned va, const unsigned char *b, unsigned n) {
    static unsigned char t[CYCLE_SIZE];
    if (n > sizeof t || !m->read(m, va, t, n)) return 0;
    return !memcmp(t, b, n);
}
static unsigned find_cycle(GameMem *m) {
    unsigned char b[5]; unsigned base;
    if (!m->read(m, HOOK_DRAW, b, 5) || b[0] != 0xE8) return 0;
    base = HOOK_DRAW + 5 + (unsigned)*(int *)(b + 1) - CYCLE_DRAW;
    return sig_at(m, base, "SR3V") ? base : 0;
}
static int blend_site(GameMem *m) {                     /* Test-BlendSite: the game's own call, or a call into a block of ours */
    unsigned char c[5]; unsigned to;
    if (same(m, HOOK_BLEND, BLEND_ORIG, 5)) return 1;
    if (!m->read(m, HOOK_BLEND, c, 5) || c[0] != 0xE8) return 0;
    to = HOOK_BLEND + 5 + (unsigned)*(int *)(c + 1);
    return sig_at(m, to & 0xFFFF0000u, "SR3V");
}
static void restore_cockpit_seat(GameMem *m, unsigned base) {   /* the cockpit cam's eye back at the game's data if it uses this block's copy */
    unsigned mgr = 0, vt, p, back;
    if (!u32at(m, base + 0x58, &mgr) || !mgr) return;
    if (u32at(m, mgr + 0x1A38, &vt) && u32at(m, mgr + 0x1A38 + 0x194, &p) && vt == 0x6EBDF0 && p == base + 0x2240 && u32at(m, base + 0x2240 + 0x18, &back))
        m->write(m, mgr + 0x1A38 + 0x194, &back, 4, 0);
}
static int BLEND_HOOKED;
/* Install-Cycle: installs or updates the block; the game held. 0 = not installed, *why says why */
static unsigned install_cycle(GameMem *m, const char **why) {
    unsigned char b[0x2A0]; unsigned base = find_cycle(m); int i, site;
    if (!base) {
        if (!same(m, HOOK_DRAW, DRAW_ORIG, 5) || !same(m, HOOK_LOST, LOST_ORIG, 5)) { *why = "unexpected bytes at its hook sites"; return 0; }
        if (!(base = m->alloc(m, CYCLE_SIZE))) { *why = "no memory for its block"; return 0; }
        m->write(m, base + CYCLE_DRAW, CYCLE_CODE, sizeof CYCLE_CODE, 1);
        m->write(m, base + CYCLE_CODE2_AT, CYCLE_CODE2, sizeof CYCLE_CODE2, 1);
    } else if (!same_big(m, base + CYCLE_DRAW, CYCLE_CODE, sizeof CYCLE_CODE) || !same_big(m, base + CYCLE_CODE2_AT, CYCLE_CODE2, sizeof CYCLE_CODE2)) {
        /* a newer build: never rewrite code the game may be running; a fresh block, the state (font, camera list) kept */
        static unsigned char keep[CYCLE_DRAW]; unsigned old = base; unsigned char list[4 * GAME_CAMS];
        restore_cockpit_seat(m, old);
        if (!(base = m->alloc(m, CYCLE_SIZE))) { *why = "no memory for its block"; return 0; }
        memset(keep, 0, sizeof keep); m->read(m, old, keep, CYCLE_DRAW); m->write(m, base, keep, CYCLE_DRAW, 1);
        memset(b, 0, 0x10); m->write(m, base + 0xF98, b, 0x10, 1);                         /* hint font, hint flag, text: start empty */
        memset(list, 0, sizeof list); m->read(m, old + 0x2180, list, sizeof list); m->write(m, base + 0x2180, list, sizeof list, 1);
        m->write(m, base + CYCLE_DRAW, CYCLE_CODE, sizeof CYCLE_CODE, 1);
        m->write(m, base + CYCLE_CODE2_AT, CYCLE_CODE2, sizeof CYCLE_CODE2, 1);              /* its state (0x2280 ..) starts empty */
    }
    f32(b, cam.look); f32(b + 4, 2 * cam.look); f32(b + 8, cam.blend); m->write(m, base + CYCLE_QOL, b, 12, 1);   /* seconds; the keys twice the mouse's */
    i32(b, 120); i32(b + 4, cam.overlay); i32(b + 8, -1); i32(b + 12, cam.nslot); i32(b + 16, cam.start); i32(b + 20, 0); m->write(m, base + 0x14, b, 0x18, 1);
    i32(b, 1); m->write(m, base + 0xB0, b, 4, 1);                                            /* quiet: no popup for this */
    str_(b, "d3dx9_41.dll", 16); str_(b + 0x10, "D3DXCreateFontA", 16); str_(b + 0x20, "Arial", 32); m->write(m, base + 0x60, b, 0x40, 1);
    m->write(m, base, "SR3V", 4, 1);
    str_(b, "Camera", 16); m->write(m, base + 0xE0, b, 16, 1);                              /* the name of an unknown camera */
    memset(b, 0, 0x240);                                                                     /* 0x2000: names, 0x21B0: offsets, 0x21E0: extras, 0x2210: colours */
    for (i = 0; i < GAME_CAMS; i++) {
        int known = i < 9;
        if (known) { str_(b + i * 32, GAMECAM[i].name, 32); i32(b + 0x210 + 4 * i, (int)GAMECAM[i].color); }
        i32(b + 0x1B0 + 4 * i, known ? (int)GAMECAM[i].off : -1);
        i32(b + 0x1E0 + 4 * i, cam.hidden && i < 7 ? (int)HIDDEN[i] : -1);
    }
    m->write(m, base + 0x2000, b, 0x180, 1); m->write(m, base + 0x21B0, b + 0x1B0, 0x90, 1);
    memset(b, 0, MAX_SLOTS * 4); for (i = 0; i < cam.nslot; i++) i32(b + 4 * i, (int)cam.slot[i].color); m->write(m, base + 0xE00, b, MAX_SLOTS * 4, 1);
    memset(b, 0, 0x70); str_(b, "user32.dll", 16); str_(b + 0x10, "GetCursorPos", 16); str_(b + 0x20, "SetCursorPos", 16);
    str_(b + 0x30, "GetAsyncKeyState", 32); str_(b + 0x50, "GetForegroundWindow", 32); m->write(m, base + 0xEA0, b, 0x70, 1);
    memset(b, 0, 0x50); str_(b, "GetWindowThreadProcessId", 32); str_(b + 0x20, "kernel32.dll", 16); str_(b + 0x30, "GetCurrentProcessId", 32); m->write(m, base + 0xF40, b, 0x50, 1);
    f32(b, -0.01); m->write(m, base + 0xFD0, b, 4, 1);                                      /* car rotate tilt per mouse pixel */
    f32(b, 1.5706); f32(b + 4, -1.5706); m->write(m, base + 0xF90, b, 8, 1);                 /* free cams look at most this far up / down */
    f32(b, 3); f32(b + 4, 30); f32(b + 8, 0.5); f32(b + 12, 20); m->write(m, base + 0xFE0, b, 16, 1);   /* car rotate cam limits */
    str_(b, "Use mouse/WASD to navigate", 32); m->write(m, base + 0xFB0, b, 32, 1);
    f32(b, 0.0025); f32(b + 4, 3.14159265358979323846 / 2); f32(b + 8, 10); f32(b + 12, 1); m->write(m, base + 0xF10, b, 16, 1);
    {   static unsigned char names[MAX_SLOTS * 32], params[MAX_SLOTS * SLOT_BYTES];
        memset(names, 0, sizeof names); memset(params, 0, sizeof params);
        for (i = 0; i < cam.nslot; i++) {
            str_(names + 32 * i, cam.slot[i].name, 32);
            memcpy(params + SLOT_BYTES * i, cam.slot[i].image + 0x08, 0x2C); memcpy(params + SLOT_BYTES * i + 0x2C, cam.slot[i].image + 0x50, 0x30);
        }
        m->write(m, base + 0x100, names, sizeof names, 1); m->write(m, base + 0x500, params, sizeof params, 1); }
    for (i = 0; i < 3; i++) {                                                                /* the original method, or a wrapper of ours */
        unsigned cur = 0, to = base + (CAM_UPDATE[i].rot ? CYCLE_ROT : CYCLE_FREE);
        u32at(m, CAM_UPDATE[i].site, &cur);
        if (cur == CAM_UPDATE[i].stock || sig_at(m, cur & 0xFFFF0000u, "SR3V")) m->write(m, CAM_UPDATE[i].site, &to, 4, 0);
    }
    call_to(b, HOOK_LOST, base + CYCLE_LOST); m->write(m, HOOK_LOST, b, 5, 0);
    call_to(b, HOOK_DRAW, base + CYCLE_DRAW); m->write(m, HOOK_DRAW, b, 5, 0);
    site = blend_site(m); BLEND_HOOKED = site && cam.blend > 0;                             /* the blend's hook only while there is a blend to do */
    if (BLEND_HOOKED) { call_to(b, HOOK_BLEND, base + CYCLE_BLEND); m->write(m, HOOK_BLEND, b, 5, 0); }
    else if (site) m->write(m, HOOK_BLEND, BLEND_ORIG, 5, 0);
    else *why = "blend";                                                                     /* (logged after the game is let go) */
    return base;
}

int pc_check_sites(GameMem *m, char *err, size_t cap) {
    int i;
    for (i = 0; i < 9; i++) if (!same(m, PATCHES[i].va, PATCHES[i].orig, PATCHES[i].len)) {
        snprintf(err, cap, "Unexpected bytes at 0x%X (%s) - not the expected game version, or patched already. Nothing changed.", PATCHES[i].va, PATCHES[i].what); return 0; }
    return 1;
}

/* sr3mods.ps1 Test-CameraSites + Install-CameraPatch: every site the game's bytes or ours (an older build too, by the cave's
 * "SR3C"), then with the game held the old build unhooked, every site written, the block made or updated, then read back.
 * Nothing is logged while the game is held (inside the game a held thread may own a lock the log needs). */
int pc_install_cameras(GameMem *m, const PcCfg *c) {
    unsigned char cur[1024]; int i, ours, already = 1, older = 0; unsigned base; const char *why = NULL;
    ours = sig_at(m, CAVE_VA, "SR3C");
    for (i = 0; i < 9; i++) {
        const unsigned char *neu = i == 0 ? cam.cave : PATCHES[i].neu; unsigned n = PATCHES[i].len, k; int ok = n <= sizeof cur && m->read(m, PATCHES[i].va, cur, n);
        if (ok && !memcmp(cur, PATCHES[i].orig, n)) { already = 0; continue; }
        if (i == 0 && ok) { int eq = 1; for (k = 0; k < n; k++) if (cur[k] != neu[k] && !(k >= TUNABLE_LO && k < SETTINGS_HI)) eq = 0; if (eq) continue; }   /* the cave, with other tuning */
        else if (ok && !memcmp(cur, neu, n)) continue;
        if (ours) { older = 1; continue; }
        pc_logf("Unexpected bytes at 0x%X (%s) - not the expected game version. Nothing changed.", PATCHES[i].va, PATCHES[i].what); return 0;
    }
    if (older) pc_logf("An older build of the camera patch is active; replacing it.");
    else if (already) pc_logf("Camera patch was already applied; updating the tuning values.");
    m->suspend(m);
    if (older) for (i = 8; i >= 1; i--) m->write(m, PATCHES[i].va, PATCHES[i].orig, PATCHES[i].len, 0);   /* unhook the old build */
    for (i = 0; i < 9; i++) m->write(m, PATCHES[i].va, i == 0 ? cam.cave : PATCHES[i].neu, PATCHES[i].len, PATCHES[i].va == CAVE_VA);
    base = install_cycle(m, &why);
    m->resume(m);
    if (base && why) pc_logf("Camera blend not installed (View Change cuts as before): unexpected bytes at 0x%X.", HOOK_BLEND);
    /* as sr3mods.ps1: every site as written, the cave without the parts its code changes while running
       (counters and scratch DIAG_LO+4 .. 0x50, SR3's framing recorded every frame 0x80 .. 0x8C) */
    for (i = 0; i < 9; i++) {
        const unsigned char *want = i == 0 ? cam.cave : PATCHES[i].neu; unsigned k;
        if (!m->read(m, PATCHES[i].va, cur, PATCHES[i].len)) { pc_logf("Verification failed at 0x%X (unreadable).", PATCHES[i].va); return 0; }
        for (k = 0; k < PATCHES[i].len; k++)
            if (cur[k] != want[k] && !(i == 0 && ((k >= DIAG_LO + 4 && k < 0x50) || (k >= 0x80 && k < 0x8C)))) { pc_logf("Verification failed at 0x%X.", PATCHES[i].va + k); return 0; }
    }
    if (c->canary) pc_logf("CANARY MODE: in a race the chase camera should look at your car from the SIDE.");
    pc_logf("Camera mod is ACTIVE for this session. Profile '%s'.", cam.profile);
    if (!base) pc_logf("  Camera cycle NOT installed: %s", why ? why : "?");
    else {
        char list[1024] = ""; size_t n = 0;
        for (i = 1; i < cam.nslot && n < sizeof list - 40; i++) n += snprintf(list + n, sizeof list - n, "%s%s", i > 1 ? ", " : "", cam.slot[i].name);
        pc_logf("  Camera cycle block at %08X; View Change: Game: Chase cam, Bumper cam, Bonnet cam, then %s%s", base, list, cam.hidden ? ", then the Debug cameras" : "");
        pc_logf("  Camera name popup: %d px (at 1080p); steerable cameras: mouse %d ms, keys %d ms; View Change %s", cam.overlay,
                (int)(1000 * cam.look + 0.5), (int)(2000 * cam.look + 0.5), BLEND_HOOKED ? "blends" : "cuts");
    }
    return 1;
}

/* The plan (tools\sr3mods\lockstep.py): what a fresh install writes, as JSON - the same file plan_ps1.ps1 makes from
 * sr3mods.ps1 against a fake game. It is pc_install_cameras itself, run on a fake memory holding the game's original
 * bytes (so the plan and the install are one code path); hooks and pointers into the block are given as block+offset. */
typedef struct { unsigned va, n; unsigned char *b; } Rg;
static Rg RG[64]; static int NRG; static unsigned NEXT_A;
static Rg *rg_of(unsigned va, unsigned n) { int i; for (i = 0; i < NRG; i++) if (va >= RG[i].va && va + n <= RG[i].va + RG[i].n) return &RG[i]; return NULL; }
static int f_read(GameMem *m, unsigned va, void *d, unsigned n) { Rg *r = rg_of(va, n); (void)m; if (!r) return 0; memcpy(d, r->b + (va - r->va), n); return 1; }
static int f_write(GameMem *m, unsigned va, const void *s, unsigned n, int keep) {
    Rg *r = rg_of(va, n); (void)m; (void)keep;
    if (!r) { if (NRG >= 64) return 0; r = &RG[NRG++]; r->va = va; r->n = n; r->b = (unsigned char *)calloc(1, n); }
    memcpy(r->b + (va - r->va), s, n); return 1;
}
static unsigned f_alloc(GameMem *m, unsigned n) { unsigned a = NEXT_A; void *z = calloc(1, n); NEXT_A += 0x10000; f_write(m, a, z, n, 1); free(z); return a; }
static void f_nop(GameMem *m) { (void)m; }
static int f_alive(GameMem *m) { (void)m; return 1; }
static void jstr(FILE *f, const char *s) {
    fputc('"', f);
    for (; *s; s++) { if (*s == '"' || *s == '\\') fputc('\\', f); fputc(*s, f); }
    fputc('"', f);
}
static void jhex(FILE *f, const unsigned char *b, unsigned n) { unsigned k; fputc('"', f); for (k = 0; k < n; k++) fprintf(f, "%02x", b[k]); fputc('"', f); }
int pc_plan(const char *out_path) {
    static const unsigned HOOKS[3] = {0x591C4D, 0x591B01, 0x5C948C};
    GameMem fm; FILE *f; unsigned base; int i; unsigned char b[1024]; void (*keep_log)(const char *) = pc_log; PcCfg c;
    memset(&fm, 0, sizeof fm); fm.read = f_read; fm.write = f_write; fm.alloc = f_alloc; fm.suspend = f_nop; fm.resume = f_nop; fm.alive = f_alive;
    for (i = 0; i < NRG; i++) free(RG[i].b);
    NRG = 0; NEXT_A = 0x20000000u;
    for (i = 0; i < 9; i++) f_write(&fm, PATCHES[i].va, PATCHES[i].orig, PATCHES[i].len, 0);   /* a freshly started game */
    f_write(&fm, HOOK_DRAW, DRAW_ORIG, 5, 0); f_write(&fm, HOOK_LOST, LOST_ORIG, 5, 0); f_write(&fm, HOOK_BLEND, BLEND_ORIG, 5, 0);
    for (i = 0; i < 3; i++) f_write(&fm, CAM_UPDATE[i].site, &CAM_UPDATE[i].stock, 4, 0);
    memset(&c, 0, sizeof c); pc_log = NULL;
    pc_install_cameras(&fm, &c);
    pc_log = keep_log;
    base = find_cycle(&fm);
    if (!(f = fopen(out_path, "wb"))) return 3;
    fputs("{\"profile\": ", f); jstr(f, cam.profile); fputs(", \"slots\": [", f);
    for (i = 0; i < cam.nslot; i++) { if (i) fputs(", ", f); jstr(f, cam.slot[i].name); }
    fputs("], \"sites\": {", f);
    for (i = 0; i < 9; i++) { fprintf(f, "%s\"0x%X\": ", i ? ", " : "", PATCHES[i].va); f_read(&fm, PATCHES[i].va, b, PATCHES[i].len); jhex(f, b, PATCHES[i].len); }
    fputs("}, \"hooks\": {", f);
    for (i = 0; i < 3; i++) {
        fprintf(f, "%s\"0x%X\": ", i ? ", " : "", HOOKS[i]); f_read(&fm, HOOKS[i], b, 5);
        if (base && b[0] == 0xE8 && memcmp(b, BLEND_ORIG, 5) && memcmp(b, LOST_ORIG, 5)) fprintf(f, "\"call block+0x%x\"", HOOKS[i] + 5 + (unsigned)*(int *)(b + 1) - base);
        else jhex(f, b, 5);
    }
    fputs("}, \"vtables\": {", f);
    for (i = 0; i < 3; i++) {
        unsigned d = 0; u32at(&fm, CAM_UPDATE[i].site, &d);
        fprintf(f, "%s\"0x%X\": ", i ? ", " : "", CAM_UPDATE[i].site);
        if (base && d >= base && d < base + CYCLE_SIZE) fprintf(f, "\"block+0x%x\"", d - base); else fprintf(f, "\"0x%x\"", d);
    }
    fputs("}, \"block\": ", f);
    if (base) { static unsigned char blk[CYCLE_SIZE]; f_read(&fm, base, blk, CYCLE_SIZE); jhex(f, blk, CYCLE_SIZE); } else fputs("\"\"", f);
    fputs("}\n", f);
    fclose(f); return 0;
}