/* lockstep.py's runner: loads patches.dll (32-bit, so this is too) and asks it for its plan.
 *   plan32 <patches.dll> <settings.yaml> <plan.json>      exit code = patches_plan's result */
#include <windows.h>
#include <shellapi.h>
typedef int (__cdecl *Plan)(const char *, const char *);
typedef const char *(__cdecl *Source)(void);
void __stdcall start(void) {
    int argc; LPWSTR *av = CommandLineToArgvW(GetCommandLineW(), &argc); char a[MAX_PATH], b[MAX_PATH]; HMODULE m; Plan f;
    if (argc == 2) {                                              /* plan32 <patches.dll>: print the patches.ps1 hash it was built from */
        Source s; DWORD w; const char *h;
        if (!(m = LoadLibraryW(av[1])) || !(s = (Source)GetProcAddress(m, "patches_source"))) ExitProcess(5);
        h = s(); WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), h, lstrlenA(h), &w, 0); ExitProcess(0);
    }
    if (argc < 4) ExitProcess(4);
    WideCharToMultiByte(CP_UTF8, 0, av[2], -1, a, MAX_PATH, 0, 0); WideCharToMultiByte(CP_UTF8, 0, av[3], -1, b, MAX_PATH, 0, 0);
    if (!(m = LoadLibraryW(av[1])) || !(f = (Plan)GetProcAddress(m, "patches_plan"))) ExitProcess(5);
    ExitProcess((UINT)f(a, b));
}
