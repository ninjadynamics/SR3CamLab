#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>
#include "launch.h"
int WINAPI WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show){
    char error[512];Sr3Settings settings;Sr3LaunchOptions options;
    (void)instance;(void)previous;(void)show;(void)command;
    if(!sr3_parse_options(GetCommandLineW(),0,&options,error,sizeof error) ||
       !sr3_load(options.settings,&settings,error,sizeof(error)) ||
       !sr3_launch_mode(options.settings,&settings,options.watchdog,error,sizeof(error))){MessageBoxA(NULL,error,"SR3Lab",MB_ICONERROR);return 1;}
    return 0;
}
