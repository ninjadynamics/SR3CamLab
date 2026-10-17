/* Plain-C GUI startup; no constructors or private C runtime initialization. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
extern int WINAPI WinMain(HINSTANCE,HINSTANCE,LPSTR,int);
void launcher_entry(void) {
    ExitProcess((UINT)WinMain(GetModuleHandleA(NULL),NULL,GetCommandLineA(),SW_SHOWNORMAL));
}
