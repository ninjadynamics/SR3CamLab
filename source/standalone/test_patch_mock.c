/* Test-only plugin. No game access. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>
#include <stdlib.h>
__declspec(dllexport) int __cdecl sr3mods_start(const char *path){
    char mode[20];HANDLE file;DWORD written;
    file=CreateFileA("patch-path.bin",GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
    if(file==INVALID_HANDLE_VALUE)return 3;
    WriteFile(file,path,(DWORD)strlen(path),&written,NULL);CloseHandle(file);
    if(GetEnvironmentVariableA("SR3_TEST_PATCH_RETURN",mode,sizeof(mode)))return atoi(mode);
    return 0;
}
BOOL WINAPI DllMain(HINSTANCE self,DWORD why,LPVOID reserved){(void)self;(void)why;(void)reserved;return TRUE;}
