/* Shared Windows command-line parsing. Explicit settings paths use the caller's
 * working directory; game_path continues to resolve beside the selected YAML. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>
#include "launch.h"
static int absolute_path(const wchar_t *value,char *path,size_t cap){
    wchar_t full[SR3_PATH];DWORD n;BOOL substituted=FALSE;int utf8=GetACP()==CP_UTF8;
    if(!*value)return 0;
    n=GetFullPathNameW(value,SR3_PATH,full,NULL);if(!n || n>=SR3_PATH)return 0;
    return WideCharToMultiByte(CP_ACP,utf8?0:WC_NO_BEST_FIT_CHARS,full,-1,path,(int)cap,NULL,utf8?NULL:&substituted) && !substituted;
}
int sr3_parse_options(const wchar_t *command,int companion,Sr3LaunchOptions *out,char *error,size_t cap){
    int argc,i,have_settings=0,have_watch=0,have_preview=0,ok=0;
    wchar_t **args=CommandLineToArgvW(command,&argc);
    memset(out,0,sizeof *out);out->watchdog=-1;
    if(!args){snprintf(error,cap,"Cannot read command line.");return 0;}
    for(i=1;i<argc;i++){
        if(!wcscmp(args[i],L"--settings")){
            if(have_settings++ || ++i>=argc || !wcsncmp(args[i],L"--",2))goto usage;
            if(!absolute_path(args[i],out->settings,sizeof out->settings))goto path_error;
        }else if(!companion && (!wcscmp(args[i],L"--watchdog") || !wcscmp(args[i],L"--no-watchdog"))){
            if(have_watch++)goto usage;
            out->watchdog=!wcscmp(args[i],L"--watchdog");
        }else if(companion && !wcscmp(args[i],L"--preview")){
            if(have_preview++ || ++i>=argc || !wcsncmp(args[i],L"--",2))goto usage;
            if(!absolute_path(args[i],out->preview,sizeof out->preview))goto path_error;
            if(i+1<argc && args[i+1][0]>=L'0' && args[i+1][0]<=L'3' && !args[i+1][1])out->preview_tab=args[++i][0]-L'0';
        }else goto usage;
    }
    if(!have_settings && !sr3_settings_path(out->settings,sizeof out->settings))goto path_error;
    ok=1;goto done;
path_error:
    snprintf(error,cap,"Settings/preview path is empty, too long, or cannot be represented by the Windows file encoding.");goto done;
usage:
    snprintf(error,cap,companion?"Usage: settings.exe [--settings <file>] [--preview <image> [0..3]]":"Usage: launch.exe [--settings <file>] [--watchdog | --no-watchdog]");
done:
    LocalFree(args);return ok;
}
int sr3_current_options(int companion,Sr3LaunchOptions *out,char *error,size_t cap){return sr3_parse_options(GetCommandLineW(),companion,out,error,cap);}
void sr3_option_error(const char *error){MessageBoxA(NULL,error,"SR3Lab Settings",MB_ICONERROR);}
