#include "settings.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL %d: %s (%s)\n",__LINE__,#x,error);return 1;}}while(0)
int main(int argc,char **argv){
    Sr3Settings a,b;char error[512]="";FILE *f;
    if(argc==2){CHECK(sr3_load(argv[1],&a,error,sizeof(error)));printf("Valid: %dx%d windowed=%d up=%s down=%s curve=%d\n",a.width,a.height,a.windowed,sr3_buttons[a.up],sr3_buttons[a.down],a.curve);return 0;}
    sr3_defaults(&a);a.width=3840;a.height=2160;a.windowed=0;a.up=22;a.down=20;
    strcpy(a.game_path,"C:/Bruno's games/#1/Rally.exe");
    CHECK(sr3_save("test-settings.yaml",&a,error,sizeof(error)));
    CHECK(sr3_load("test-settings.yaml",&b,error,sizeof(error)));CHECK(!memcmp(&a,&b,sizeof(a)));
    f=fopen("test-settings.yaml","ab");CHECK(f);fprintf(f,"  cores: 3\n");fclose(f);
    CHECK(!sr3_load("test-settings.yaml",&b,error,sizeof(error)));
    f=fopen("test-settings.yaml","wb");CHECK(f);
    fprintf(f,"version: 1\npatches:\n  enabled: auto\n  mod_folder: 'C:/Bruno''s games/#mods'\n  camera_blend: -1\n  mouse_smoothing: 0.08\n  camera_profile: ''\n  watchdog: false\n");fclose(f);
    CHECK(sr3_load("test-settings.yaml",&a,error,sizeof(error)));
    CHECK(!strcmp(sr3_patch_value(&a,"mod_folder"),"C:/Bruno's games/#mods"));
    CHECK(!strcmp(sr3_patch_value(&a,"camera_profile"),""));
    CHECK(sr3_patch_value(&a,"profiles_file")==NULL);
    CHECK(sr3_save("test-settings.yaml",&a,error,sizeof(error)));
    CHECK(sr3_load("test-settings.yaml",&b,error,sizeof(error)));CHECK(!memcmp(&a,&b,sizeof(a)));
    {char contents[8192];size_t size;f=fopen("test-settings.yaml","rb");CHECK(f);size=fread(contents,1,sizeof(contents)-1,f);fclose(f);contents[size]=0;
     CHECK(strstr(contents,"  steering:")==NULL);CHECK(strstr(contents,"  up:")==NULL);CHECK(strstr(contents,"  gas:")==NULL);}
    strcpy(a.patches[0],"maybe");CHECK(!sr3_validate(&a,error,sizeof(error)));
#ifdef _WIN32
    f=_wfopen(L"test-\u00e9-settings.yaml",L"wb");CHECK(f);fputs("version: 1\n",f);fclose(f);
    CHECK(sr3_load_utf8("test-\xc3\xa9-settings.yaml",&a,error,sizeof(error)));
    CHECK(!sr3_load_utf8("test-\xff-settings.yaml",&a,error,sizeof(error)));
    _wremove(L"test-\u00e9-settings.yaml");
#endif
    f=fopen("test-settings.yaml","wb");CHECK(f);fprintf(f,"version: 1\ndisplay:\n  width: 999999999999999999\n");fclose(f);
    CHECK(!sr3_load("test-settings.yaml",&b,error,sizeof(error)));
    f=fopen("test-settings.yaml","wb");CHECK(f);fprintf(f,"version: 1\ndisplay:\n  typo: true\n");fclose(f);
    CHECK(!sr3_load("test-settings.yaml",&b,error,sizeof(error)));
    remove("test-settings.yaml");remove("test-settings.yaml.bak");
    puts("Settings: roundtrip, patch scalars, omitted default bindings, quoted paths, duplicate/invalid rejection pass.");return 0;
}
