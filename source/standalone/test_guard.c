#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
int main(int argc,char **argv){
    HMODULE module;DWORD error;
    if(argc!=2){fputs("Pass the test runtime DLL path.\n",stderr);return 2;}
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOOPENFILEERRORBOX);
    module=LoadLibraryA(argv[1]);error=GetLastError();
    if(module){FreeLibrary(module);fputs("Runtime accepted an unsupported host.\n",stderr);return 1;}
    if(error!=ERROR_DLL_INIT_FAILED){fprintf(stderr,"Unexpected loader error %lu\n",error);return 1;}
    puts("Runtime guard refused the unsupported host before patching.");return 0;
}
