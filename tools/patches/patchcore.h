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
#define PC_LOADED_FLAG 0x9EB81Cu                   /* non-zero once the game's system data is loaded */
