/* patches.dll: patchcore inside the game. Started by the TeknoParrot-free runtime (Codex's standalone\) through
 *     int __cdecl patches_start(const char *utf8_absolute_settings_path)      0 = started, 1 settings, 2 game bytes, 3 internal
 * after its own check of Rally.exe, outside the loader lock, before the first race. It returns at once; a thread of
 * its own waits for the game's data (the non-zero dword at 0x9EB81C, as patches.ps1 waits) and then patches.
 *     int __cdecl patches_plan(const char *utf8_settings_path, const char *out_json)   the plan (lockstep.py)
 *     const char *__cdecl patches_source(void)                                       the patches.ps1 it was built from
 * The game memory here is the game's own: reads and writes are plain copies (a page made writable for the write),
 * suspending means every other thread of the process. Log: patches.log beside this DLL. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <string.h>
#include "patchcore.h"

#define EXPORT __declspec(dllexport)
static char here[MAX_PATH];
static HANDLE logh = INVALID_HANDLE_VALUE;
static PcCfg cfg;

static void to_log(const char *s) {
    char b[1100]; SYSTEMTIME t; DWORD w; int n;
    if (logh == INVALID_HANDLE_VALUE) return;
    GetLocalTime(&t); n = snprintf(b, sizeof b - 2, "[%02d:%02d:%02d] %s", t.wHour, t.wMinute, t.wSecond, s);
    if (n < 0 || n > (int)sizeof b - 3) n = (int)sizeof b - 3;
    b[n++] = '\r'; b[n++] = '\n'; WriteFile(logh, b, (DWORD)n, &w, NULL);
}

/* ---------------------------------------------------------------- the game's memory, from inside */
static int in_read(GameMem *m, unsigned va, void *dst, unsigned n) {
    MEMORY_BASIC_INFORMATION q; (void)m;
    if (!VirtualQuery((void *)(uintptr_t)va, &q, sizeof q) || q.State != MEM_COMMIT || (q.Protect & (PAGE_NOACCESS | PAGE_GUARD))) return 0;
    if ((uintptr_t)va + n > (uintptr_t)q.BaseAddress + q.RegionSize) return 0;
    memcpy(dst, (void *)(uintptr_t)va, n); return 1;
}
static int in_write(GameMem *m, unsigned va, const void *src, unsigned n, int keep) {
    DWORD old, x; (void)m;
    if (!VirtualProtect((void *)(uintptr_t)va, n, PAGE_EXECUTE_READWRITE, &old)) return 0;
    memcpy((void *)(uintptr_t)va, src, n);
    if (!keep) VirtualProtect((void *)(uintptr_t)va, n, old, &x);
    FlushInstructionCache(GetCurrentProcess(), (void *)(uintptr_t)va, n); return 1;
}
static unsigned in_alloc(GameMem *m, unsigned n) { (void)m; return (unsigned)(uintptr_t)VirtualAlloc(NULL, n, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE); }
static DWORD held[512]; static int nheld;
static void in_suspend(GameMem *m) {                 /* nothing in between may need a lock a held thread has (no heap, no stdio) */
    HANDLE s = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0); THREADENTRY32 te; DWORD me = GetCurrentThreadId(), pid = GetCurrentProcessId(); (void)m;
    nheld = 0; te.dwSize = sizeof te;
    if (s == INVALID_HANDLE_VALUE) return;
    if (Thread32First(s, &te)) do {
        if (te.th32OwnerProcessID == pid && te.th32ThreadID != me && nheld < 512) {
            HANDLE t = OpenThread(THREAD_SUSPEND_RESUME, FALSE, te.th32ThreadID);
            if (t) { if (SuspendThread(t) != (DWORD)-1) held[nheld++] = te.th32ThreadID; CloseHandle(t); }
        }
    } while (Thread32Next(s, &te));
    CloseHandle(s);
}
static void in_resume(GameMem *m) {
    int i; (void)m;
    for (i = 0; i < nheld; i++) { HANDLE t = OpenThread(THREAD_SUSPEND_RESUME, FALSE, held[i]); if (t) { ResumeThread(t); CloseHandle(t); } }
    nheld = 0;
}
static int in_alive(GameMem *m) { (void)m; return 1; }
static GameMem inside = {in_read, in_write, in_alloc, in_suspend, in_resume, in_alive, ph_now, ph_sleep, ph_pad, ph_key, ph_front, ph_shot, NULL, NULL};

/* ---------------------------------------------------------------- the thread */
static DWORD WINAPI worker(LPVOID p) {
    DWORD t0 = GetTickCount(); unsigned f = 0; (void)p;
    while (!inside.read(&inside, PC_LOADED_FLAG, &f, 4) || !f) {
        if (GetTickCount() - t0 > 180000) { pc_logf("Timed out waiting for the game to boot; nothing patched."); return 0; }
        Sleep(50);
    }
    pc_logf("Game data loaded after %u s.", (unsigned)((GetTickCount() - t0) / 1000));
    pc_install_cameras(&inside, &cfg);
    return 0;
}

EXPORT int __cdecl patches_start(const char *settings_path) {
    static LONG once; char err[512] = ""; HANDLE t;
    if (InterlockedExchange(&once, 1)) return 0;                            /* idempotent */
    { char lp[MAX_PATH]; snprintf(lp, sizeof lp, "%s\\patches.log", here);
      logh = CreateFileA(lp, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL); }
    pc_log = to_log; pc_init();
    pc_logf("patches.dll started; settings %s", settings_path ? settings_path : "(none)");
    if (!settings_path || !pc_load_cfg(settings_path, here, &cfg, err, sizeof err)) { pc_logf("Settings: %s", err); return 1; }
    if (!pc_prepare_cameras(&cfg, err, sizeof err)) { pc_logf("Cameras: %s", err); return 1; }
    if (!pc_check_sites(&inside, err, sizeof err)) { pc_logf("%s", err); return 2; }
    t = CreateThread(NULL, 0, worker, NULL, 0, NULL);
    if (!t) { pc_logf("Could not start the patch thread (%lu).", GetLastError()); return 3; }
    CloseHandle(t); return 0;
}

EXPORT int __cdecl patches_plan(const char *settings_path, const char *out_path) {
    char err[512] = ""; FILE *f;
    pc_init();
    if (!pc_load_cfg(settings_path, here, &cfg, err, sizeof err) || !pc_prepare_cameras(&cfg, err, sizeof err)) {
        if ((f = fopen(out_path, "wb"))) { fprintf(f, "{\"error\": \"%s\"}\n", err); fclose(f); }
        return 1;
    }
    return pc_plan(out_path);
}

EXPORT const char *__cdecl patches_source(void) { return pc_source(); }

BOOL WINAPI DllMain(HINSTANCE self, DWORD why, LPVOID r) {
    (void)r;
    if (why == DLL_PROCESS_ATTACH) {
        char *s; DisableThreadLibraryCalls(self); GetModuleFileNameA(self, here, MAX_PATH);
        if ((s = strrchr(here, '\\'))) *s = 0;
    }
    return TRUE;
}
