#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "launch.h"
#define CHECK(x) do{if(!(x)){printf("Command line failed at %d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(int argc,char **argv){
    Sr3LaunchOptions o;char error[512],expected[SR3_PATH],default_path[SR3_PATH];int i;
    const wchar_t *bad[]={L"app --settings",L"app --settings --watchdog",L"app --settings \"\"",L"app --settings a --settings b",L"app --watchdog --no-watchdog",L"app --watcdog",L"app extra",L"app --preview x"};
    (void)argc;(void)argv;
    CHECK(sr3_settings_path(default_path,sizeof default_path));
    CHECK(sr3_parse_options(L"\"C:\\a folder\\launch.exe\"",0,&o,error,sizeof error));
    CHECK(!strcmp(o.settings,default_path) && o.watchdog==-1);
    CHECK(GetFullPathNameA("settings with spaces.yaml",sizeof expected,expected,NULL));
    CHECK(sr3_parse_options(L"app --settings \"settings with spaces.yaml\" --no-watchdog",0,&o,error,sizeof error));
    CHECK(!strcmp(o.settings,expected) && o.watchdog==0);
    CHECK(sr3_parse_options(L"app --watchdog --settings \"C:\\a folder\\windowed.yaml\"",0,&o,error,sizeof error));
    CHECK(!strcmp(o.settings,"C:\\a folder\\windowed.yaml") && o.watchdog==1);
    for(i=0;i<(int)(sizeof bad/sizeof bad[0]);i++)CHECK(!sr3_parse_options(bad[i],0,&o,error,sizeof error));
    CHECK(sr3_parse_options(L"app --settings \"settings with spaces.yaml\" --preview preview.png 3",1,&o,error,sizeof error));
    CHECK(!strcmp(o.settings,expected) && o.preview_tab==3 && strstr(o.preview,"preview.png"));
    CHECK(sr3_parse_options(L"app --preview preview.png 1 --settings \"settings with spaces.yaml\"",1,&o,error,sizeof error));
    CHECK(!strcmp(o.settings,expected) && o.preview_tab==1);
    CHECK(!sr3_parse_options(L"app --watchdog",1,&o,error,sizeof error));
    CHECK(!sr3_parse_options(L"app --preview x 4",1,&o,error,sizeof error));
    {
        Sr3Settings settings;FILE *f;char base[SR3_PATH],yaml[SR3_PATH];
        memset(&settings,0,sizeof settings);
        CHECK(GetCurrentDirectoryA(sizeof base,base));
        CreateDirectoryA("source",NULL);CreateDirectoryA("source\\tools",NULL);CreateDirectoryA("source\\tools\\workspace",NULL);
        snprintf(yaml,sizeof yaml,"%s\\settings.yaml",base);
        f=fopen("source\\tools\\workspace\\play.ps1","wb");CHECK(f);
        fputs("param([string]$Workspace)\nif ($Workspace -ne $pwd.Path) { exit 7 }\n[IO.File]::WriteAllText((Join-Path $Workspace 'routed.txt'),'ok')\nexit 0\n",f);fclose(f);
        CHECK(sr3_launch(yaml,&settings,error,sizeof error));
        CHECK(GetFileAttributesA("routed.txt")!=INVALID_FILE_ATTRIBUTES);
        f=fopen("source\\tools\\workspace\\play.ps1","wb");CHECK(f);fputs("param([string]$Workspace)\nexit 3\n",f);fclose(f);
        CHECK(!sr3_launch(yaml,&settings,error,sizeof error));CHECK(strstr(error,"Workspace launch failed"));
        DeleteFileA("source\\tools\\workspace\\play.ps1");DeleteFileA("routed.txt");
        RemoveDirectoryA("source\\tools\\workspace");RemoveDirectoryA("source\\tools");RemoveDirectoryA("source");
    }
    puts("Command line: default/explicit/quoted/relative settings, watcher overrides, preview and malformed arguments PASS.");return 0;
}
