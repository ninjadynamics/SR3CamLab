/* Copyright (c) 2026 Ninja Dynamics. MIT. */
#define WIN32_LEAN_AND_MEAN
#include "patch_loader.h"
#include "settings.h"
#include <stdio.h>
#include <string.h>
#include <wchar.h>

int sr3_load_patches(HMODULE owner,const char *settings_path_acp,int mode,char *error,size_t cap){
    WCHAR dll[SR3_PATH],wide[SR3_PATH],*end;char absolute[SR3_PATH],utf8[SR3_PATH*4];
    DWORD n,attributes,code;HMODULE module;int result;
    typedef int (__cdecl *Start)(const char*);Start start;
    if(mode==2)return 0;
    n=GetModuleFileNameW(owner,dll,SR3_PATH);
    if(!n || n>=SR3_PATH || !(end=wcsrchr(dll,L'\\')) || (end-dll)+13>=SR3_PATH)goto path_error;
    wcscpy(end+1,L"sr3mods.dll");
    attributes=GetFileAttributesW(dll);
    if(attributes==INVALID_FILE_ATTRIBUTES){
        code=GetLastError();
        if(mode==0 && (code==ERROR_FILE_NOT_FOUND || code==ERROR_PATH_NOT_FOUND))return 0;
        snprintf(error,cap,"Adjacent sr3mods.dll unavailable (Windows error %lu).",code);return -1;
    }
    /* The current launcher uses Win32 ANSI paths. Convert ACP -> UTF-16 ->
       UTF-8 explicitly for the plugin ABI; relabeling bytes corrupts accents.
       GetFullPathName also makes a direct/manual launch unambiguous. */
    n=GetFullPathNameA(settings_path_acp,sizeof(absolute),absolute,NULL);
    if(!n || n>=sizeof(absolute) || !MultiByteToWideChar(CP_ACP,0,absolute,-1,wide,SR3_PATH) ||
       !WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,-1,utf8,sizeof(utf8),NULL,NULL))goto path_error;
    /* Load by this module's directory, irrespective of process CWD/PATH.
       Dependencies may come from that directory or Windows, never the CWD. */
    module=LoadLibraryExW(dll,NULL,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
    if(!module){snprintf(error,cap,"Cannot load adjacent sr3mods.dll (Windows error %lu).",GetLastError());return -1;}
    start=(Start)GetProcAddress(module,"sr3mods_start");
    if(!start){snprintf(error,cap,"sr3mods.dll has no sr3mods_start export.");return -1;}
    result=start(utf8);
    if(result){snprintf(error,cap,"sr3mods_start failed (%d). See sr3mods.log beside sr3mods.dll.",result);return -1;}
    return 1;
path_error:
    snprintf(error,cap,"Cannot resolve sr3mods.dll or its UTF-8 settings path.");return -1;
}
