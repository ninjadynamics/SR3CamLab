/* Entry point for our plain-C x86 console tests, without MinGW CRT startup. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
extern int main(int argc,char **argv);
/* These C-only test programs have no global constructors. */
void __main(void) {}
void test_entry(void) {
    int argc=0,i,result;LPWSTR *wide=CommandLineToArgvW(GetCommandLineW(),&argc);
    char **argv;HANDLE heap=GetProcessHeap();
    if(!wide)ExitProcess(125);
    argv=HeapAlloc(heap,HEAP_ZERO_MEMORY,(argc+1)*sizeof(*argv));
    if(!argv)ExitProcess(125);
    for(i=0;i<argc;i++){
        int n=WideCharToMultiByte(CP_UTF8,0,wide[i],-1,NULL,0,NULL,NULL);
        argv[i]=HeapAlloc(heap,0,n);if(!argv[i])ExitProcess(125);
        if(!WideCharToMultiByte(CP_UTF8,0,wide[i],-1,argv[i],n,NULL,NULL))ExitProcess(125);
    }
    result=main(argc,argv);
    for(i=0;i<argc;i++)HeapFree(heap,0,argv[i]);
    HeapFree(heap,0,argv);LocalFree(wide);ExitProcess((UINT)result);
}
