/* The recorder stays outside Rally, with file-backed output so it can finish
 * after the game (and its DLL) exits. No shell, inherited game handles or UI. MIT. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "watch_launcher.h"

static HANDLE host, output = INVALID_HANDLE_VALUE;
static char partial[4096];
static size_t used;
static DWORD last_poll;

static int wide(const char *s, wchar_t *w, int cap) {
    return MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, w, cap) != 0;
}
static void close_host(void) {
    if (host) CloseHandle(host);
    if (output != INVALID_HANDLE_VALUE) CloseHandle(output);
    host = NULL; output = INVALID_HANDLE_VALUE; used = 0;
}
void sr3_watch_poll(void (*log)(const char *)) {
    char bytes[2048]; DWORD n, i, code;
    if (!host || !log) return;
    if (GetTickCount() - last_poll < 200 && WaitForSingleObject(host, 0) == WAIT_TIMEOUT) return;
    last_poll = GetTickCount();
    while (ReadFile(output, bytes, sizeof bytes, &n, NULL) && n) {
        for (i = 0; i < n; ++i) {
            if (bytes[i] == '\n' || used == sizeof partial - 1) {
                partial[used] = 0; if (used) log(partial); used = 0;
            }
            if (bytes[i] != '\r' && bytes[i] != '\n') partial[used++] = bytes[i];
        }
    }
    if (WaitForSingleObject(host, 0) == WAIT_OBJECT_0) {
        char line[128];
        if (used) { partial[used] = 0; log(partial); }
        if (GetExitCodeProcess(host, &code) && code) {
            snprintf(line, sizeof line, "Watchdog host exited with code %lu; inspect its host log.", code); log(line);
        }
        close_host();
    }
}
void sr3_watch_finish(void (*log)(const char *)) {
    DWORD start = GetTickCount();
    while (host && GetTickCount() - start < 5000) { sr3_watch_poll(log); if (host) Sleep(50); }
    if (host && log) log("Watchdog is still finishing; its separate process retains the report.");
    close_host();
}
static int spawn_host(HANDLE game, const char *launch, const char *yaml, const char *mod, char *error, size_t cap) {
    wchar_t root[1024], exe[1024], ps[1200], script[1200], crash[1200], path[1400], cmd[8192], mutex_name[160];
    char numbers[128]; wchar_t wn[128], settings[2048];
    FILETIME created, exited, kernel, user; ULARGE_INTEGER stamp;
    DWORD pid = game ? GetProcessId(game) : 0, count = 1024, failure = ERROR_INVALID_PARAMETER;
    HANDLE write = INVALID_HANDLE_VALUE, input = INVALID_HANDLE_VALUE, mutex;
    SECURITY_ATTRIBUTES sa = {sizeof sa, NULL, TRUE};
    STARTUPINFOEXW si; PROCESS_INFORMATION pi; SIZE_T attr_size = 0;
    BOOL wow = FALSE; HANDLE inherit[2]; int i, initialized = 0;
    if (cap) error[0] = 0;
    if (host && WaitForSingleObject(host, 0) == WAIT_TIMEOUT) return 1;
    close_host(); memset(&si, 0, sizeof si); memset(&pi, 0, sizeof pi);
    if (!wide(mod, root, 1024) || !((root[0] && root[1] == L':') || (root[0] == L'\\' && root[1] == L'\\'))) goto fail;
    stamp.QuadPart = 0;
    if (launch) {
        if (!wide(launch, exe, 1024) || !wide(yaml, settings, 2048)) goto fail;
    } else {
        if (!pid || !GetProcessTimes(game, &created, &exited, &kernel, &user) ||
            !QueryFullProcessImageNameW(game, 0, exe, &count)) goto fail;
        stamp.LowPart = created.dwLowDateTime; stamp.HighPart = created.dwHighDateTime;
        snprintf(numbers, sizeof numbers, "%lu-%llu", pid, (unsigned long long)stamp.QuadPart);
        wide(numbers, wn, 128); swprintf(mutex_name, 160, L"Local\\SR3LabWatchdog-%ls", wn);
        mutex = OpenMutexW(SYNCHRONIZE | MUTEX_MODIFY_STATE, FALSE, mutex_name);
        if (mutex) { DWORD state = WaitForSingleObject(mutex, 0);
            if (state == WAIT_TIMEOUT) { CloseHandle(mutex); return 1; }
            /* We only inspect ownership; an abandoned or currently free mutex is not a recorder. */
            if (state == WAIT_OBJECT_0 || state == WAIT_ABANDONED) ReleaseMutex(mutex);
            CloseHandle(mutex);
        }
    }
    swprintf(script, 1200, L"%ls\\standalone\\watch.ps1", root);
    swprintf(crash, 1200, L"%ls\\crash", root);
    if (GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) { failure = ERROR_FILE_NOT_FOUND; goto fail; }
    if (!CreateDirectoryW(crash, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) goto fail;
    if (!GetWindowsDirectoryW(ps, 1024) || !IsWow64Process(GetCurrentProcess(), &wow)) goto fail;
    wcscat(ps, wow ? L"\\Sysnative\\WindowsPowerShell\\v1.0\\powershell.exe" : L"\\System32\\WindowsPowerShell\\v1.0\\powershell.exe");
    for (i = 0; i < 100; ++i) {
        swprintf(path, 1400, L"%ls\\watch-host-%lu-%lu-%lu-%d.log", crash, pid, GetCurrentProcessId(), GetTickCount(), i);
        write = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, &sa, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
        if (write != INVALID_HANDLE_VALUE || GetLastError() != ERROR_FILE_EXISTS) break;
    }
    if (write == INVALID_HANDLE_VALUE) goto fail;
    output = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    input = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, NULL);
    if (output == INVALID_HANDLE_VALUE || input == INVALID_HANDLE_VALUE) goto fail;
    InitializeProcThreadAttributeList(NULL, 1, 0, &attr_size);
    si.lpAttributeList = HeapAlloc(GetProcessHeap(), 0, attr_size);
    if (!si.lpAttributeList || !InitializeProcThreadAttributeList(si.lpAttributeList, 1, 0, &attr_size)) goto fail;
    initialized = 1; inherit[0] = write; inherit[1] = input;
    if (!UpdateProcThreadAttribute(si.lpAttributeList, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherit, sizeof inherit, NULL, NULL)) goto fail;
    snprintf(numbers, sizeof numbers, "%llu", (unsigned long long)stamp.QuadPart); wide(numbers, wn, 128);
    if (launch) swprintf(cmd, 8192, L"\"%ls\" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%ls\" -LaunchExe \"%ls\" -SettingsPath \"%ls\" -CrashDirectory \"%ls\"", ps, script, exe, settings, crash);
    else swprintf(cmd, 8192, L"\"%ls\" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%ls\" -ProcessId %lu -ExpectedExePath \"%ls\" -ExpectedStartFileTime %ls -CrashDirectory \"%ls\"", ps, script, pid, exe, wn, crash);
    si.StartupInfo.cb = sizeof si; si.StartupInfo.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.StartupInfo.wShowWindow = SW_HIDE; si.StartupInfo.hStdInput = input;
    si.StartupInfo.hStdOutput = write; si.StartupInfo.hStdError = write;
    if (!CreateProcessW(ps, cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT, NULL, root, &si.StartupInfo, &pi)) goto fail;
    host = pi.hProcess; CloseHandle(pi.hThread);
    DeleteProcThreadAttributeList(si.lpAttributeList); HeapFree(GetProcessHeap(), 0, si.lpAttributeList);
    CloseHandle(input); CloseHandle(write); last_poll = 0; return 1;
fail:
    if (GetLastError()) failure = GetLastError();
    if (initialized) DeleteProcThreadAttributeList(si.lpAttributeList);
    if (si.lpAttributeList) HeapFree(GetProcessHeap(), 0, si.lpAttributeList);
    if (input != INVALID_HANDLE_VALUE) CloseHandle(input);
    if (write != INVALID_HANDLE_VALUE) CloseHandle(write);
    close_host(); snprintf(error, cap, "Cannot start watchdog host (Windows error %lu).", failure); return 0;
}

int sr3_watch_start(HANDLE game, const char *mod, char *error, size_t cap) {
    return spawn_host(game, NULL, NULL, mod, error, cap);
}
int sr3_watch_launch(const char *exe, const char *yaml, const char *mod, char *error, size_t cap) {
    return spawn_host(NULL, exe, yaml, mod, error, cap);
}
