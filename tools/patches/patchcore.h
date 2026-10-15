/* patchcore: SR3Lab's in-game patches, written once (Bruno, 2026-10-15: the .ps1 and the .dll in lockstep; option B,
 * one implementation). Everything it does to the game goes through a GameMem: patches.dll gives it the game's own
 * memory (it runs inside the game), sr3mods.exe gives it ReadProcessMemory / WriteProcessMemory on a game it attached
 * to. The same code, the same bytes, either way. */
#pragma once
#include <stddef.h>

typedef struct GameMem GameMem;
struct GameMem {
    int (*read)(GameMem *, unsigned va, void *dst, unsigned n);                     /* 1 = read */
    int (*write)(GameMem *, unsigned va, const void *src, unsigned n, int keep);    /* keep = leave the page writable */
    unsigned (*alloc)(GameMem *, unsigned n);                                       /* zeroed, read-write-execute, 64 KB aligned; 0 = none */
    void (*suspend)(GameMem *);                                                     /* the game's threads (but the caller's) */
    void (*resume)(GameMem *);
    int (*alive)(GameMem *);                                                        /* the game still running */
    /* the world outside the game's memory, for the live loop (pc_live.c; patches.ps1's Get-Now, Start-Sleep,
       Test-KeyDown, Get-FrontWindow, New- / Save- / Close-ScreenGrab, Show-WatchdogNews) */
    long long (*now)(GameMem *);                                                    /* local time, 100 ns ticks since 1601 (a FILETIME) */
    void (*sleep)(GameMem *, int ms);
    int (*key)(GameMem *, int vk);                                                  /* 1 = held */
    unsigned (*front)(GameMem *);                                                   /* the foreground window */
    int (*shot)(GameMem *, int act, const char *path, const char *info);            /* 1 grab the screen, 2 save it as PNG (+ tEXt "SR3Lab" info), 3 let it go; 1 = done */
    void (*news)(GameMem *);                                                        /* the watchdog's lines, if one runs (NULL = none) */
    void *ctx;
};

typedef struct {                                   /* settings.yaml's patches: section, or sr3mods.exe's switches */
    char mod[260], profile[256], profiles_file[260];
    int overlay, canary, watchdog;                 /* overlay -1 = the profiles file's or 48 */
    double mouse, blend;                           /* -1 = the profiles file's or the default */
} PcCfg;

extern void (*pc_log)(const char *line);           /* the front end's log (patches.log, the console) */
void pc_logf(const char *fmt, ...);
void pc_init(void);                                /* once, before anything else (the C locale for numbers) */
int pc_load_cfg(const char *settings_path, const char *default_mod, PcCfg *c, char *err, size_t cap);
int pc_prepare_cameras(const PcCfg *c, char *err, size_t cap);          /* profiles.yaml -> the cave image and the camera list */
int pc_check_sites(GameMem *m, char *err, size_t cap);                  /* every site still holds the game's own bytes */
int pc_install_cameras(GameMem *m, const PcCfg *c);                     /* 1 = active */
int pc_plan(const char *out_path);                                      /* the writes of a fresh install as JSON (lockstep.py) */
const char *pc_source(void);                                            /* the SHA-256 of the patches.ps1 the bytes came from */
void pc_live(GameMem *m, const PcCfg *c, const char *game_exe);        /* after the cameras: menu timers, car lists, handling, then
                                                                           the track switcher / START / race-exit loop until the game exits */
/* pc_host.c: the real world for GameMem's now .. shot (both front ends use these; the lockstep test has its own) */
long long ph_now(GameMem *); void ph_sleep(GameMem *, int ms); int ph_key(GameMem *, int vk);
unsigned ph_front(GameMem *); int ph_shot(GameMem *, int act, const char *path, const char *info);
extern int (__cdecl *ph_grab_hook)(void **bgra, int *w, int *h);       /* the runtime's back buffer grab (patches.dll), else GDI */
#define PC_LOADED_FLAG 0x9EB81Cu                   /* non-zero once the game's system data is loaded */
