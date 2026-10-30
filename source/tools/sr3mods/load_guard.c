/* Race-load and exit guard, on its own thread beside the live loop.
 *
 * Quick Race loads have stalled with the loading screen up (2026-10-20, before
 * the frontend existed, and 2026-10-28). Quitting then left a windowless
 * process that only Task Manager could end, and fullscreen hides Task Manager.
 *  - Every race load is logged: menus left, then race running after N s.
 *  - A loading screen still up after LG_STALL_MS writes a minidump: every
 *    thread's stack, the game's globals and open handles.
 *  - A process still alive LG_EXIT_MS after its game window closed writes the
 *    same, then ends itself.
 * At most two dumps per session. Nothing here changes the game's state. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dbghelp.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include "patchcore.h"
#include "frontend_video.h"
#include "load_guard.h"
#ifndef LG_TEST
#define LG_PHASE ((volatile unsigned char *)0x9D6E3C)   /* 1 = menus (pc_live.c) */
#define LG_STATE ((volatile int *)0x7ECE10)             /* current, next game state (pc_live.c GAME_STATE) */
#define LG_STALL_MS 150000u
#define LG_EXIT_MS 15000u
#define LG_POLL_MS 250
#endif
#define LG_RACING 0x27                                  /* race running, both words */
#define LG_EXIT_CODE 0x5352u
typedef BOOL (WINAPI *WriteDump)(HANDLE,DWORD,HANDLE,MINIDUMP_TYPE,PMINIDUMP_EXCEPTION_INFORMATION,
                                 PMINIDUMP_USER_STREAM_INFORMATION,PMINIDUMP_CALLBACK_INFORMATION);
static WriteDump write_dump;
static char folder[MAX_PATH];
static int dumps;

/* Globals are kept for the game and our own modules only; driver and system
   data segments would make the file large without explaining a stall. */
static BOOL CALLBACK dump_filter(PVOID context,PMINIDUMP_CALLBACK_INPUT in,PMINIDUMP_CALLBACK_OUTPUT out){
    (void)context;
    if(in->CallbackType==ModuleCallback){
        const WCHAR *name=wcsrchr(in->Module.FullPath,L'\\');name=name?name+1:in->Module.FullPath;
        if(in->Module.BaseOfImage!=(ULONG64)(uintptr_t)GetModuleHandleA(NULL)&&
           _wcsicmp(name,L"sr3mods.dll")&&_wcsicmp(name,L"dinput8.dll"))out->ModuleWriteFlags&=~ModuleWriteDataSeg;
    }
    return TRUE;
}
static void dump(const char *reason){
    char path[MAX_PATH+64];SYSTEMTIME t;HANDLE f;BOOL ok;DWORD error=0;
    MINIDUMP_CALLBACK_INFORMATION filter={dump_filter,NULL};
    if(dumps>=2){pc_logf("Diagnostics: %s dump skipped; two were written this session.",reason);return;}
    if(!write_dump){pc_logf("Diagnostics: dbghelp.dll is unavailable; no %s dump.",reason);return;}
    GetLocalTime(&t);
    snprintf(path,sizeof path,"%s\\sr3lab-%s-%04u%02u%02u-%02u%02u%02u.dmp",folder,reason,
             t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond);
    f=CreateFileA(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(f==INVALID_HANDLE_VALUE){pc_logf("Diagnostics: cannot create %s (%lu).",path,GetLastError());return;}
    ++dumps;
    ok=write_dump(GetCurrentProcess(),GetCurrentProcessId(),f,(MINIDUMP_TYPE)(MiniDumpWithDataSegs|MiniDumpWithHandleData|
        MiniDumpWithIndirectlyReferencedMemory|MiniDumpWithUnloadedModules|MiniDumpWithThreadInfo),NULL,NULL,&filter);
    if(!ok)error=GetLastError();
    CloseHandle(f);
    if(ok)pc_logf("Diagnostics: %s dump written: %s",reason,path);
    else pc_logf("Diagnostics: %s dump failed (%08lX): %s",reason,error,path);
}
/* InternalGetWindowText reads a title without messaging a possibly hung owner. */
static BOOL CALLBACK find_window(HWND w,LPARAM out){
    DWORD pid=0;char kind[64]="";WCHAR title[64]=L"";
    GetWindowThreadProcessId(w,&pid);
    if(pid!=GetCurrentProcessId()||!IsWindowVisible(w))return TRUE;
    GetClassNameA(w,kind,sizeof kind);InternalGetWindowText(w,title,64);
    if(!_stricmp(kind,"IME")||!_stricmp(kind,"MSCTFIME UI")||!wcscmp(title,L"D3DProxyWindow"))return TRUE;
    *(HWND *)out=w;return FALSE;
}
static DWORD WINAPI guard(LPVOID unused){
    HWND window=NULL;DWORD now,load_at=0,gone_at=0;int was_menu=0,loading=0,warned=0,stalled=0;
    (void)unused;
    for(;;){
        int menu=*LG_PHASE==1,state=LG_STATE[0],next=LG_STATE[1];
        now=GetTickCount();
        if(was_menu&&!menu){loading=1;warned=stalled=0;load_at=now;pc_logf("Race load: menus left (game state 0x%X/0x%X).",state,next);}
        else if(loading&&menu){loading=0;pc_logf("Race load: back in the menus after %.1f s without a race.",(now-load_at)/1000.0);}
        else if(loading&&state==LG_RACING&&next==LG_RACING){loading=0;pc_logf("Race load: race running after %.1f s.",(now-load_at)/1000.0);}
        else if(loading){
            /* The loading animation drawn within 2 s identifies the loading
               screen; without that evidence wait twice as long. */
            DWORD elapsed=now-load_at;unsigned age=fe_video_loading_age();
            int screen=age<2000;
            if(!warned&&elapsed>=LG_STALL_MS/2){warned=1;
                pc_logf("Race load: still loading after %u s (game state 0x%X/0x%X, loading animation %s).",
                        (unsigned)(elapsed/1000),state,next,screen?"on screen":"not seen");}
            if(!stalled&&(elapsed>=LG_STALL_MS*2||(screen&&elapsed>=LG_STALL_MS))){stalled=1;
                pc_logf("Race load: no race after %u s (game state 0x%X/0x%X); recording every game thread.",(unsigned)(elapsed/1000),state,next);
                dump("load");}
        }
        was_menu=menu;
        if(!window||!IsWindow(window)){
            HWND found=NULL;EnumWindows(find_window,(LPARAM)&found);
            if(found){if(gone_at)pc_logf("Game window replaced; still running.");window=found;gone_at=0;}
            else if(window&&!gone_at){gone_at=now;pc_logf("Game window closed; waiting for the process to exit.");}
            else if(window&&now-gone_at>=LG_EXIT_MS){
                pc_logf("The game is still running %u s after its window closed; recording every thread, then ending the process.",
                        (unsigned)((now-gone_at)/1000));
                dump("exit");
                TerminateProcess(GetCurrentProcess(),LG_EXIT_CODE);
            }
        }
        Sleep(LG_POLL_MS);
    }
    return 0;
}
void lg_start(const char *dir){
    char off[4];HMODULE dbghelp;HANDLE t;
    if(GetEnvironmentVariableA("SR3LAB_GUARD",off,sizeof off)&&off[0]=='0'){pc_logf("Load guard: off (SR3LAB_GUARD=0).");return;}
    snprintf(folder,sizeof folder,"%s",dir);
    /* Loaded now: a stalled game may hold locks that LoadLibrary needs later. */
    dbghelp=LoadLibraryA("dbghelp.dll");
    write_dump=dbghelp?(WriteDump)(void (*)(void))GetProcAddress(dbghelp,"MiniDumpWriteDump"):NULL;
    t=CreateThread(NULL,0,guard,NULL,0,NULL);
    if(t)CloseHandle(t);
    pc_logf("Load guard: %s.",!t?"could not start":write_dump?"race loads and exit watched; a stall or stuck exit writes a dump here":
            "race loads and exit watched; dbghelp.dll unavailable, no dumps");
}
