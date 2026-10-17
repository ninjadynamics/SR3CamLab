/* Native launcher helpers, shared with the raylib companion. MIT. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <string.h>
#include "launch.h"
#include "watch_launcher.h"
static int to_utf8(const char *s,char *out,int cap){
    wchar_t w[SR3_PATH*2];
    return MultiByteToWideChar(CP_ACP,0,s,-1,w,SR3_PATH*2) && WideCharToMultiByte(CP_UTF8,0,w,-1,out,cap,NULL,NULL);
}
int sr3_settings_path(char *path,size_t cap){
    char *end;DWORD n=GetModuleFileNameA(NULL,path,(DWORD)cap);
    if(!n || n>=cap || !(end=strrchr(path,'\\')))return 0;
    if((size_t)(end-path)+15>=cap)return 0;
    strcpy(end+1,"settings.yaml");return 1;
}
int sr3_launch_mode(const char *yaml,const Sr3Settings *s,int watch,char *error,size_t cap){
    char folder[SR3_PATH],combined[SR3_PATH*2],exe[SR3_PATH],command[SR3_PATH+4],dll[SR3_PATH];
    STARTUPINFOA si={0};PROCESS_INFORMATION pi;HANDLE snapshot;PROCESSENTRY32 entry={0};char *end;
    if(!sr3_validate(s,error,cap))return 0;
    if(strlen(yaml)>=sizeof(folder))goto pathError;
    strcpy(folder,yaml);end=strrchr(folder,'\\');if(!end)goto pathError;*end=0;
    if((strlen(s->game_path)>2 && s->game_path[1]==':') || s->game_path[0]=='\\' || s->game_path[0]=='/')snprintf(combined,sizeof(combined),"%s",s->game_path);
    else snprintf(combined,sizeof(combined),"%s\\%s",folder,s->game_path);
    {DWORD n=GetFullPathNameA(combined,sizeof(exe),exe,NULL);if(!n || n>=sizeof(exe))goto pathError;}
    end=strrchr(exe,'\\');if(!end || _stricmp(end+1,"Rally.exe")){snprintf(error,cap,"game_path must select Rally.exe.");return 0;}
    strcpy(folder,exe);*strrchr(folder,'\\')=0;
    snprintf(dll,sizeof(dll),"%s\\dinput8.dll",folder);
    if(GetFileAttributesA(exe)==INVALID_FILE_ATTRIBUTES || GetFileAttributesA(dll)==INVALID_FILE_ATTRIBUTES){snprintf(error,cap,"Rally.exe or the SR3Lab dinput8.dll is missing in the selected game folder.");return 0;}
    snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);entry.dwSize=sizeof(entry);
    if(snapshot==INVALID_HANDLE_VALUE){snprintf(error,cap,"Cannot check for a running game.");return 0;}
    if(Process32First(snapshot,&entry))do{
        if(!_stricmp(entry.szExeFile,"Rally.exe")){CloseHandle(snapshot);snprintf(error,cap,"Close the running Rally 3 instance first.");return 0;}
    }while(Process32Next(snapshot,&entry));
    CloseHandle(snapshot);
    if(watch<0){const char *v=sr3_patch_value(s,"watchdog");watch=!(v && (!_stricmp(v,"off") || !_stricmp(v,"false") || !strcmp(v,"0") || !_stricmp(v,"no")));}
    /* Per-launch auto override; the DLL hotkey remains independent. */
    if(!SetEnvironmentVariableA("SR3LAB_WATCHDOG",watch?"1":"0")){snprintf(error,cap,"Cannot set watchdog launch mode.");return 0;}
    if(watch){
        char mod[SR3_PATH],base[SR3_PATH],utfmod[SR3_PATH*3],utfexe[SR3_PATH*3],utfyaml[SR3_PATH*3];
        const char *v=sr3_patch_value(s,"mod_folder");DWORD n;
        strcpy(base,yaml);end=strrchr(base,'\\');if(!end)goto pathError;*end=0;
        if(v && *v){
            if((strlen(v)>2 && v[1]==':') || v[0]=='\\' || v[0]=='/')snprintf(combined,sizeof combined,"%s",v);
            else snprintf(combined,sizeof combined,"%s\\%s",base,v);
        }else snprintf(combined,sizeof combined,"%s",base);
        n=GetFullPathNameA(combined,sizeof mod,mod,NULL);if(!n || n>=sizeof mod)goto pathError;
        snprintf(combined,sizeof combined,"%s\\standalone\\watchdog.exe",mod);
        if(GetFileAttributesA(combined)==INVALID_FILE_ATTRIBUTES){
            snprintf(error,cap,"Watchdog host missing. Set patches.mod_folder to your SR3CamLab folder, or patches.watchdog: off.");return 0;
        }
        if(!to_utf8(mod,utfmod,sizeof utfmod) || !to_utf8(exe,utfexe,sizeof utfexe) || !to_utf8(yaml,utfyaml,sizeof utfyaml))goto pathError;
        return sr3_watch_launch(utfexe,utfyaml,utfmod,error,cap);
    }
    /* Child inherits only our settings location; the game directory is always explicit. */
    if(!SetEnvironmentVariableA("SR3LAB_SETTINGS",yaml)){snprintf(error,cap,"Cannot set settings location.");return 0;}
    snprintf(command,sizeof(command),"\"%s\"",exe);si.cb=sizeof(si);
    if(!CreateProcessA(exe,command,NULL,NULL,FALSE,0,NULL,folder,&si,&pi)){
        snprintf(error,cap,"Cannot launch Rally.exe (Windows error %lu).",GetLastError());return 0;
    }
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);return 1;
pathError:
    snprintf(error,cap,"Invalid or too long settings/game path.");return 0;
}
int sr3_launch(const char *yaml,const Sr3Settings *s,char *error,size_t cap){
    char root[SR3_PATH],script[SR3_PATH*2],ps[SR3_PATH],cmd[SR3_PATH*4],*end;
    STARTUPINFOA si={0}; PROCESS_INFORMATION pi; DWORD code;
    if(strlen(yaml)>=sizeof root){snprintf(error,cap,"Settings path too long.");return 0;}
    strcpy(root,yaml);end=strrchr(root,'\\');if(!end)return sr3_launch_mode(yaml,s,-1,error,cap);*end=0;
    snprintf(script,sizeof script,"%s\\source\\tools\\workspace\\play.ps1",root);
    if(GetFileAttributesA(script)==INVALID_FILE_ATTRIBUTES)return sr3_launch_mode(yaml,s,-1,error,cap);
    if(!GetSystemDirectoryA(ps,sizeof ps)){snprintf(error,cap,"Cannot locate PowerShell.");return 0;}
    if(strlen(ps)+48>=sizeof ps){snprintf(error,cap,"System path too long.");return 0;}
    strcat(ps,"\\WindowsPowerShell\\v1.0\\powershell.exe");
    snprintf(cmd,sizeof cmd,"\"%s\" -NoProfile -ExecutionPolicy Bypass -File \"%s\" -Workspace \"%s\"",ps,script,root);
    si.cb=sizeof si;si.dwFlags=STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;
    if(!CreateProcessA(ps,cmd,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,root,&si,&pi)){
        snprintf(error,cap,"Cannot start workspace launcher (%lu).",GetLastError());return 0;
    }
    CloseHandle(pi.hThread);WaitForSingleObject(pi.hProcess,INFINITE);
    if(!GetExitCodeProcess(pi.hProcess,&code))code=1;CloseHandle(pi.hProcess);
    if(code){snprintf(error,cap,"Workspace launch failed. Run PLAY.bat for the detailed error.");return 0;}
    return 1;
}
