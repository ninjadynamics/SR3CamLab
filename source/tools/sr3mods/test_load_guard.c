/* Drives load_guard.c in its own small process; no game is involved.
 * LG_TEST_MODE: load = stalled loads (two dumps, then the cap); exit = the
 * window closes and the process hangs (dump, then self-termination); quit =
 * the window closes and the process exits normally (no dump).
 * LG_TEST_DIR receives guard.log and the dumps. test_load_guard.py checks them. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static volatile unsigned char test_phase;
static volatile int test_state[2];
static volatile unsigned test_loading_age=0xFFFFFFFFu;
#define LG_TEST
#define LG_PHASE (&test_phase)
#define LG_STATE (test_state)
#define LG_STALL_MS 600u
#define LG_EXIT_MS 600u
#define LG_POLL_MS 20
static HANDLE log_file;
void pc_logf(const char *fmt,...){
    char line[1024];va_list a;DWORD n;int k;
    va_start(a,fmt);k=vsnprintf(line,sizeof line-2,fmt,a);va_end(a);
    if(k<0)return;
    if(k>(int)sizeof line-3)k=(int)sizeof line-3;
    line[k++]='\n';WriteFile(log_file,line,(DWORD)k,&n,NULL);
}
unsigned fe_video_loading_age(void){return test_loading_age;}
int fe_video_hooked(void){return 1;}
#include "load_guard.c"
static void load(int state){test_phase=2;test_state[0]=test_state[1]=state;}
void load_guard_test_entry(void){
    char mode[16]="",dir[MAX_PATH]="",path[MAX_PATH+16];WNDCLASSA kind;HWND w;
    GetEnvironmentVariableA("LG_TEST_MODE",mode,sizeof mode);GetEnvironmentVariableA("LG_TEST_DIR",dir,sizeof dir);
    snprintf(path,sizeof path,"%s\\guard.log",dir);
    log_file=CreateFileA(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(log_file==INVALID_HANDLE_VALUE)ExitProcess(2);
    pc_logf("phase at %08X",(unsigned)(uintptr_t)&test_phase);
    test_phase=1;
    if(!strcmp(mode,"load")){
        lg_start(dir);Sleep(100);
        load(0x1B);test_loading_age=0;Sleep(900);                 /* loading screen up: warn, then dump */
        test_state[0]=test_state[1]=0x27;Sleep(200);               /* the race starts after all */
        test_phase=1;Sleep(100);load(0x1B);Sleep(900);             /* second stall: second dump */
        test_phase=1;Sleep(100);load(0x1B);Sleep(900);             /* third: the cap */
        test_phase=1;Sleep(100);test_loading_age=0xFFFFFFFFu;load(0x1B);Sleep(900);test_phase=1;Sleep(100); /* no animation: no dump yet */
        ExitProcess(0);
    }
    memset(&kind,0,sizeof kind);kind.lpfnWndProc=DefWindowProcA;kind.hInstance=GetModuleHandleA(NULL);kind.lpszClassName="LoadGuardTest";
    RegisterClassA(&kind);
    w=CreateWindowExA(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE,"LoadGuardTest","load guard test",WS_POPUP|WS_VISIBLE,0,0,1,1,NULL,NULL,kind.hInstance,NULL);
    if(!w)ExitProcess(3);
    lg_start(dir);Sleep(200);
    DestroyWindow(w);
    if(!strcmp(mode,"quit")){Sleep(250);ExitProcess(0);}
    Sleep(INFINITE);
}
