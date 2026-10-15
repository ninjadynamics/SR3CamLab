/* sr3mods.exe: patchcore from outside the game (the TeknoParrot route, and any game started by something else).
 *   sr3mods attach [<pid>] [--settings <settings.yaml>] [--mod <SR3CamLab folder>] [--delay <s>]
 *                   [--camera-profile <name>] [--profiles-file <yaml>] [--overlay <px>] [--mouse-smoothing <s>]
 *                   [--camera-blend <s>] [--canary] [--watchdog | --no-watchdog] [--no-live] [--log <file>]
 *   sr3mods plan <out.json> [the same settings switches]          (what a fresh install writes: lockstep.py)
 * attach patches the cameras, then runs the live loop (pc_live.c: menu timers, car lists, handling, the track switcher,
 * START screenshots, the race exit) until the game closes, and exits 0 then; --no-live stops after the cameras.
 * No pid: the running Rally.exe. The switches are sr3mods.ps1's (CamLab passes them) and win over settings.yaml's
 * patches: section. --delay: seconds to wait after the game's data has loaded (TeknoParrot's checks: sr3mods.ps1 waits
 * 20). The game memory here is ReadProcessMemory / WriteProcessMemory; suspending = NtSuspendProcess, as sr3mods.ps1. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "patchcore.h"
#include "watch_launcher.h"

static HANDLE game, logh = INVALID_HANDLE_VALUE;
static const char *watch_mod;
typedef LONG (NTAPI *NtProc)(HANDLE);
static NtProc ntsuspend, ntresume;

static void to_log(const char *s) {
    char b[1100]; SYSTEMTIME t; DWORD w; int n;
    GetLocalTime(&t); n = snprintf(b, sizeof b - 2, "[%02d:%02d:%02d] %s", t.wHour, t.wMinute, t.wSecond, s);
    if (n < 0 || n > (int)sizeof b - 3) n = (int)sizeof b - 3;
    b[n++] = '\r'; b[n++] = '\n';
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), b, (DWORD)n, &w, NULL);
    if (logh != INVALID_HANDLE_VALUE) WriteFile(logh, b, (DWORD)n, &w, NULL);
}

/* ---------------------------------------------------------------- the game's memory, from outside */
static int ex_read(GameMem *m, unsigned va, void *dst, unsigned n) { SIZE_T got = 0; (void)m; return ReadProcessMemory(game, (LPCVOID)(uintptr_t)va, dst, n, &got) && got == n; }
static int ex_write(GameMem *m, unsigned va, const void *src, unsigned n, int keep) {
    DWORD old, x; SIZE_T w = 0; int ok; (void)m;
    if (!VirtualProtectEx(game, (LPVOID)(uintptr_t)va, n, PAGE_EXECUTE_READWRITE, &old)) return 0;
    ok = WriteProcessMemory(game, (LPVOID)(uintptr_t)va, src, n, &w) && w == n;
    if (!keep) VirtualProtectEx(game, (LPVOID)(uintptr_t)va, n, old, &x);
    FlushInstructionCache(game, (LPCVOID)(uintptr_t)va, n); return ok;
}
static unsigned ex_alloc(GameMem *m, unsigned n) { (void)m; return (unsigned)(uintptr_t)VirtualAllocEx(game, NULL, n, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE); }
static void ex_suspend(GameMem *m) { (void)m; if (ntsuspend) ntsuspend(game); }
static void ex_resume(GameMem *m) { (void)m; if (ntresume) ntresume(game); }
static int ex_alive(GameMem *m) { (void)m; return WaitForSingleObject(game, 0) == WAIT_TIMEOUT; }
static void ex_news(GameMem *m) { (void)m; sr3_watch_poll(pc_log); }
static int ex_watch(GameMem *m, char *line, int cap) {
    (void)m;
    if (!sr3_watch_start(game, watch_mod, line, (size_t)cap)) return 0;
    snprintf(line, (size_t)cap, "Recorder requested; reports in crash\\."); return 1;
}
static GameMem outside = {ex_read, ex_write, ex_alloc, ex_suspend, ex_resume, ex_alive, ph_now, ph_sleep, ph_key, ph_front, ph_shot, ex_news, ex_watch, NULL};

static DWORD find_game(void) {
    HANDLE s = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0); PROCESSENTRY32W e; DWORD pid = 0; e.dwSize = sizeof e;
    if (Process32FirstW(s, &e)) do { if (!lstrcmpiW(e.szExeFile, L"Rally.exe")) { pid = e.th32ProcessID; break; } } while (Process32NextW(s, &e));
    CloseHandle(s); return pid;
}
static void utf8(const wchar_t *w, char *out, int cap) { WideCharToMultiByte(CP_UTF8, 0, w, -1, out, cap, NULL, NULL); }

static int run(void);
void __stdcall entry(void) { ExitProcess((UINT)run()); }                  /* (no C runtime start-up: -nostartfiles) */
static int run(void) {
    int argc, i; wchar_t **av = CommandLineToArgvW(GetCommandLineW(), &argc); char a[1024], settings[1024] = "", mod[MAX_PATH], err[512] = "", plan[1024] = "";
    PcCfg c, sw; DWORD pid = 0; double delay = 0; char *s; int live = 1, watch = -1;
    pc_log = to_log; pc_init();
    SetProcessDPIAware();             /* the screen's own pixels for the START screenshot (sr3mods.ps1's Initialize-Host; 2560x1440 of a 4K screen at 150 % without it) */
    GetModuleFileNameA(NULL, mod, MAX_PATH); if ((s = strrchr(mod, '\\'))) *s = 0;          /* (default mod folder: beside the exe) */
    memset(&sw, 0, sizeof sw); sw.overlay = -1; sw.mouse = -1; sw.blend = -1; sw.canary = -1;
    if (argc >= 2 && !wcscmp(av[1], L"source")) { pc_logf("%s", pc_source()); return 0; }   /* the SHA-256 of the sr3mods.ps1 it was built from (PLAY.bat uses it only when that is today's) */
    if (argc < 2 || (wcscmp(av[1], L"attach") && wcscmp(av[1], L"plan"))) {
        pc_logf("sr3mods attach [<pid>] [--settings <yaml>] [--mod <dir>] [--delay <s>] [--camera-profile <n>] [--profiles-file <f>] [--overlay <px>] [--mouse-smoothing <s>] [--camera-blend <s>] [--canary] [--watchdog | --no-watchdog] [--no-live] [--log <f>]  |  sr3mods plan <out.json> [the same]");
        return 4;
    }
    for (i = 2; i < argc; i++) {
        utf8(av[i], a, sizeof a);
        #define NEXT() (i + 1 < argc ? (utf8(av[++i], a, sizeof a), a) : "")
        if (!strcmp(a, "--settings")) snprintf(settings, sizeof settings, "%s", NEXT());
        else if (!strcmp(a, "--mod")) snprintf(mod, sizeof mod, "%s", NEXT());
        else if (!strcmp(a, "--delay")) delay = atof(NEXT());
        else if (!strcmp(a, "--camera-profile")) snprintf(sw.profile, sizeof sw.profile, "%s", NEXT());
        else if (!strcmp(a, "--profiles-file")) snprintf(sw.profiles_file, sizeof sw.profiles_file, "%s", NEXT());
        else if (!strcmp(a, "--overlay")) sw.overlay = atoi(NEXT());
        else if (!strcmp(a, "--mouse-smoothing")) sw.mouse = atof(NEXT());
        else if (!strcmp(a, "--camera-blend")) sw.blend = atof(NEXT());
        else if (!strcmp(a, "--canary")) sw.canary = 1;
        else if (!strcmp(a, "--no-live")) live = 0;
        else if (!strcmp(a, "--watchdog")) watch = 1;
        else if (!strcmp(a, "--no-watchdog")) watch = 0;
        else if (!strcmp(a, "--log")) logh = CreateFileA(NEXT(), GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        else if (!wcscmp(av[1], L"plan") && !plan[0]) snprintf(plan, sizeof plan, "%s", a);
        else if (!wcscmp(av[1], L"attach") && !pid && a[0] >= '0' && a[0] <= '9') pid = (DWORD)strtoul(a, NULL, 10);
        else { pc_logf("Unknown argument: %s", a); return 4; }
    }
    if (!pc_load_cfg(settings[0] ? settings : NULL, mod, &c, err, sizeof err)) { pc_logf("Settings: %s", err); return 1; }
    if (sw.profile[0]) snprintf(c.profile, sizeof c.profile, "%s", sw.profile);              /* the switches win, as sr3mods.ps1's do */
    if (sw.profiles_file[0]) snprintf(c.profiles_file, sizeof c.profiles_file, "%s", sw.profiles_file);
    if (sw.overlay >= 0) c.overlay = sw.overlay;
    if (sw.mouse >= 0) c.mouse = sw.mouse;
    if (sw.blend >= 0) c.blend = sw.blend;
    if (sw.canary > 0) c.canary = 1;
    if (watch >= 0) c.watchdog = watch;
    watch_mod = c.mod;
    if (!pc_prepare_cameras(&c, err, sizeof err)) { pc_logf("Cameras: %s", err); return 1; }
    if (!wcscmp(av[1], L"plan")) return plan[0] ? pc_plan(plan) : 4;
    if (!pid && !(pid = find_game())) { pc_logf("Rally.exe is not running."); return 2; }
    game = OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION | PROCESS_SUSPEND_RESUME | SYNCHRONIZE, FALSE, pid);
    if (!game) { pc_logf("Cannot open the game (pid %lu): %lu", pid, GetLastError()); return 3; }
    { HMODULE nt = GetModuleHandleA("ntdll.dll"); ntsuspend = (NtProc)GetProcAddress(nt, "NtSuspendProcess"); ntresume = (NtProc)GetProcAddress(nt, "NtResumeProcess"); }
    pc_logf("Rally.exe running (pid %lu). Waiting for the game to finish booting...", pid);
    { DWORD t0 = GetTickCount(); unsigned f = 0;
      while (!outside.read(&outside, PC_LOADED_FLAG, &f, 4) || !f) {
          if (!outside.alive(&outside)) { pc_logf("The game closed before it finished booting."); return 3; }
          if (GetTickCount() - t0 > 180000) { pc_logf("Timed out waiting for the game to boot."); return 3; }
          Sleep(250);
      }
      pc_logf("Game data loaded after %u s.%s", (unsigned)((GetTickCount() - t0) / 1000), delay > 0 ? " Waiting for TeknoParrot's checks..." : "");
      if (delay > 0) Sleep((DWORD)(delay * 1000)); }
    if (!outside.alive(&outside)) { pc_logf("The game closed during start-up (before any patching)."); return 3; }
    if (!pc_install_cameras(&outside, &c)) return 2;
    if (!live) { CloseHandle(game); return 0; }
    if (c.watchdog) { char line[512]; if (!ex_watch(&outside, line, sizeof line)) pc_logf("%s", line); }
    {   /* sr3mods.ps1's Release-StuckKeys: the live loop until the game closes, then key-ups for Alt, Ctrl, Shift and Win
           (leaving the game sometimes leaves one "held" in Windows, its key-up never arrived) */
        static const BYTE vk[11] = {0x12, 0xA4, 0xA5, 0x11, 0xA2, 0xA3, 0x10, 0xA0, 0xA1, 0x5B, 0x5C};
        wchar_t w[1024]; DWORD n = 1024; char exe[2048] = ""; int k;
        if (QueryFullProcessImageNameW(game, 0, w, &n)) utf8(w, exe, sizeof exe);
        pc_logf("Leave this window open: when the game closes it releases any stuck Alt/Ctrl/Shift/Win key.");
        pc_live(&outside, &c, exe);
        for (k = 0; k < 11; k++) keybd_event(vk[k], 0, KEYEVENTF_KEYUP, 0);
        pc_logf("Game closed. Modifier keys released.");
    }
    sr3_watch_finish(pc_log);
    CloseHandle(game); return 0;
}
