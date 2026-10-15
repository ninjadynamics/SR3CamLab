#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>
#include "launch.h"
int WINAPI WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show){
    char path[SR3_PATH],error[512];Sr3Settings settings;int watch=-1;
    (void)instance;(void)previous;(void)show;
    if(!strcmp(command,"--watchdog"))watch=1;
    else if(!strcmp(command,"--no-watchdog"))watch=0;
    else if(*command){MessageBoxA(NULL,"Usage: launch.exe [--watchdog | --no-watchdog]","SR3Lab",MB_ICONERROR);return 1;}
    if(!sr3_settings_path(path,sizeof(path))){MessageBoxA(NULL,"Cannot locate settings.yaml","SR3Lab",MB_ICONERROR);return 1;}
    if(!sr3_load(path,&settings,error,sizeof(error)) || !sr3_launch_mode(path,&settings,watch,error,sizeof(error))){MessageBoxA(NULL,error,"SR3Lab",MB_ICONERROR);return 1;}
    return 0;
}
