/* Copyright (c) 2026 Ninja Dynamics. MIT. */
#include "settings.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif
const char *const sr3_buttons[]={"none","south","east","west","north","back","guide","start","left_stick","right_stick","left_shoulder","right_shoulder","dpad_up","dpad_down","dpad_left","dpad_right","left_x_minus","left_x_plus","left_y_minus","left_y_plus","right_x_minus","right_x_plus","right_y_minus","right_y_plus","left_trigger","right_trigger",NULL};
const char *const sr3_axes[]={"left_x","left_y","right_x","right_y","left_trigger","right_trigger",NULL};
const char *const sr3_languages[]={"English","French","Italian","German","Spanish",NULL};
const char *const sr3_patch_keys[SR3_PATCH_FIELDS]={"enabled","mod_folder","camera_profile","profiles_file","overlay","mouse_smoothing","camera_blend","canary","watchdog"};
const char *sr3_patch_value(const Sr3Settings *s,const char *key){
    int i;for(i=0;i<SR3_PATCH_FIELDS;i++)if(!strcmp(key,sr3_patch_keys[i]))
        return (s->patches_present&(1u<<i))?s->patches[i]:NULL;
    return NULL;
}
static const char *const booleans[]={"false","true",NULL};
static const char *const curves[]={"linear","teknoparrot",NULL};
#define F(sec,key,label,member,lo,hi,def,step,opts) {sec,key,label,offsetof(Sr3Settings,member),lo,hi,def,step,opts}
const Sr3Field sr3_fields[]={
 F("","version","Version",version,1,1,1,1,NULL),
 F("display","width","Width",width,640,7680,1280,160,NULL),
 F("display","height","Height",height,480,4320,720,90,NULL),
 F("display","windowed","Windowed",windowed,0,1,1,1,booleans),
 F("display","hud_adjust","In-race HUD adjustment",hud_adjust,0,1,1,1,booleans),
 F("display","vsync","VSync",vsync,0,1,1,1,booleans),
 F("display","refresh_rate","Fullscreen refresh (Hz)",refresh_rate,0,360,60,1,NULL),
 F("game","freeplay","Free play",freeplay,0,1,1,1,booleans),
 F("game","language","Language",language,0,4,0,1,sr3_languages),
 F("game","music","Music volume",music,0,100,80,5,NULL),
 F("game","sfx","Effects volume",sfx,0,100,70,5,NULL),
 F("game","voice","Voice volume",voice,0,100,80,5,NULL),
 F("game","attract_music","Attract music",attract_music,0,1,1,1,booleans),
 F("input","controller","Controller index",controller,0,15,0,1,NULL),
 F("input","deadzone","Steering deadzone",deadzone,0,30000,4096,512,NULL),
 F("input","threshold","Stick button threshold",threshold,1,32767,15000,1000,NULL),
 F("input","background","Input while unfocused",background,0,1,0,1,booleans),
 F("input","steering","Steering axis",steering,0,3,0,1,sr3_axes),
 F("input","invert","Invert steering",invert,0,1,0,1,booleans),
 F("input","gas","Accelerator",gas,4,5,5,1,sr3_axes),
 F("input","brake","Brake",brake,4,5,4,1,sr3_axes),
 F("input","start","Start",start,0,25,7,1,sr3_buttons),
 F("input","view","Change view",view,0,25,1,1,sr3_buttons),
 F("input","handbrake","Handbrake",handbrake,0,25,11,1,sr3_buttons),
 F("input","up","Shift up",up,0,25,22,1,sr3_buttons),
 F("input","down","Shift down",down,0,25,20,1,sr3_buttons),
 F("input","coin","Coin",coin,0,25,5,1,sr3_buttons),
 F("input","dpad","D-pad steering",dpad,0,1,0,1,booleans),
 F("input","curve","Steering curve",curve,0,1,0,1,curves),
 F("runtime","cores","CPU cores (0 = all)",cores,0,32,4,1,NULL)
};
const int sr3_field_count=(int)(sizeof(sr3_fields)/sizeof(sr3_fields[0]));
int *sr3_value(Sr3Settings *s,int field){return (int*)((char*)s+sr3_fields[field].offset);}
void sr3_defaults(Sr3Settings *s){int i;memset(s,0,sizeof(*s));strcpy(s->game_path,"Rally.exe");for(i=0;i<sr3_field_count;i++)*sr3_value(s,i)=sr3_fields[i].initial;}
static int fail(char *error,size_t cap,int line,const char *why){snprintf(error,cap,"Settings%s%d: %s",line?" line ":" error ",line,why);return 0;}
static char *trim(char *p){char *end;while(isspace((unsigned char)*p))p++;end=p+strlen(p);while(end>p && isspace((unsigned char)end[-1]))*--end=0;return p;}
static int scalar(char *p){
    char *r=p,*w=p;int quote=0;
    if(*r=='\'' || *r=='"')quote=*r++;
    while(*r){
        if(quote && *r==quote){
            if(quote=='\'' && r[1]=='\''){*w++='\'';r+=2;continue;}
            r++;while(isspace((unsigned char)*r))r++;
            if(*r && *r!='#')return 0;
            *w=0;return 1;
        }
        if(!quote && *r=='#' && (r==p || isspace((unsigned char)r[-1])))break;
        /* No YAML escapes: use single-quoted literal paths, emitted by the writer. */
        if(quote=='"' && *r=='\\')return 0;
        *w++=*r++;
    }
    *w=0;if(quote)return 0;trim(p);return 1;
}
int sr3_validate(const Sr3Settings *s,char *error,size_t cap){
    int i;for(i=0;i<sr3_field_count;i++){
        const Sr3Field *f=&sr3_fields[i];int v=*(const int*)((const char*)s+f->offset);
        if(v<f->min || v>f->max)return fail(error,cap,0,f->key);
    }
    if(!s->game_path[0] || strpbrk(s->game_path,"\r\n\t"))return fail(error,cap,0,"invalid game_path");
    for(i=0;i<SR3_PATCH_FIELDS;i++)if(s->patches_present&(1u<<i)){
        if(strpbrk(s->patches[i],"\r\n\t"))return fail(error,cap,0,"invalid patch scalar");
        if(i==0 && strcmp(s->patches[i],"auto") && strcmp(s->patches[i],"on") && strcmp(s->patches[i],"off"))
            return fail(error,cap,0,"patches.enabled must be auto, on or off");
    }
    return 1;
}
static int read_settings(FILE *file,Sr3Settings *s,char *error,size_t cap){
    Sr3Settings result;char line[2048],section[64]="";int number=0,seen[64]={0},pathSeen=0,versionSeen=0;
    sr3_defaults(&result);
    if(!file)return fail(error,cap,0,"cannot open settings.yaml");
    while(fgets(line,sizeof(line),file)){
        char *p=line,*colon,*value;int indent,i,found=-1;number++;
        if(number==1 && strlen(p)>=3 && (unsigned char)p[0]==0xef && (unsigned char)p[1]==0xbb && (unsigned char)p[2]==0xbf)p+=3;
        if(!strchr(p,'\n') && !feof(file))goto syntax;
        if(strchr(p,'\t'))goto syntax;
        indent=(int)(trim(p)-p);p=trim(p);if(!*p || *p=='#')continue;
        colon=strchr(p,':');if(!colon)goto syntax;*colon=0;trim(p);value=trim(colon+1);
        if(indent==0 && (!*value || *value=='#')){
            if(strcmp(p,"launch") && strcmp(p,"display") && strcmp(p,"input") && strcmp(p,"game") && strcmp(p,"runtime") && strcmp(p,"patches"))goto syntax;
            strcpy(section,p);continue;
        }
        if(indent!=2 && !(indent==0 && !strcmp(p,"version")))goto syntax;
        if(!scalar(value))goto syntax;
        if(indent==0)section[0]=0;
        if(!strcmp(section,"launch") && !strcmp(p,"game_path")){
            if(pathSeen++ || strlen(value)>=sizeof(result.game_path))goto syntax;
            strcpy(result.game_path,value);continue;
        }
        if(!strcmp(section,"patches")){
            for(i=0;i<SR3_PATCH_FIELDS;i++)if(!strcmp(p,sr3_patch_keys[i]))break;
            if(i==SR3_PATCH_FIELDS || (result.patches_present&(1u<<i)) || strlen(value)>=SR3_PATH)goto syntax;
            result.patches_present|=1u<<i;strcpy(result.patches[i],value);continue;
        }
        for(i=0;i<sr3_field_count;i++)if(!strcmp(section,sr3_fields[i].section) && !strcmp(p,sr3_fields[i].key)){found=i;break;}
        if(found<0 || seen[found]++)goto syntax;
        {const Sr3Field *f=&sr3_fields[found];int v=-1;
            if(f->choices){for(i=f->min;i<=f->max;i++)if(!strcmp(value,f->choices[i])){v=i;break;}}
            else {char *end;long n;errno=0;n=strtol(value,&end,10);if(errno || end==value || *end || n<f->min || n>f->max)goto syntax;v=(int)n;}
            if(v<f->min || v>f->max)goto syntax;
            *sr3_value(&result,found)=v;if(found==0)versionSeen=1;
        }
    }
    if(ferror(file)){fclose(file);return fail(error,cap,number,"read failed");}
    fclose(file);
    if(!versionSeen)return fail(error,cap,0,"version: 1 is required");
    if(!sr3_validate(&result,error,cap))return 0;
    *s=result;return 1;
syntax:
    fclose(file);return fail(error,cap,number,"unknown, duplicate or invalid field; expected schema 1 scalar YAML");
}
int sr3_load(const char *path,Sr3Settings *s,char *error,size_t cap){return read_settings(fopen(path,"rb"),s,error,cap);}
int sr3_load_utf8(const char *path,Sr3Settings *s,char *error,size_t cap){
#ifdef _WIN32
    WCHAR wide[SR3_PATH];
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,wide,SR3_PATH))return fail(error,cap,0,"invalid UTF-8 settings path");
    return read_settings(_wfopen(wide,L"rb"),s,error,cap);
#else
    return sr3_load(path,s,error,cap);
#endif
}
int sr3_save(const char *path,const Sr3Settings *s,char *error,size_t cap){
    FILE *file;char temp[SR3_PATH+80],backup[SR3_PATH+32];const char *section="";int i,ok;
    if(!sr3_validate(s,error,cap))return 0;
    snprintf(temp,sizeof(temp),"%s.tmp-%lu",path,
#ifdef _WIN32
      (unsigned long)GetCurrentProcessId()
#else
      0ul
#endif
    );
    file=fopen(temp,"wb");if(!file)return fail(error,cap,0,"cannot create temporary settings file");
    fprintf(file,"# SR3Lab settings. Saved by the companion; changes apply on next launch.\nversion: 1\nlaunch:\n  game_path: '");
    for(i=0;s->game_path[i];i++){fputc(s->game_path[i],file);if(s->game_path[i]=='\'')fputc('\'',file);}
    fprintf(file,"'\n");
    for(i=1;i<sr3_field_count;i++){
        const Sr3Field *f=&sr3_fields[i];int v=*(const int*)((const char*)s+f->offset);
        /* Defaults need no binding overrides. Saving display/audio changes must
           not put cleared controller mappings back into settings.yaml. */
        if(!strcmp(f->section,"input") && v==f->initial &&
           (f->offset>=offsetof(Sr3Settings,steering) && f->offset<=offsetof(Sr3Settings,dpad)))continue;
        if(strcmp(section,f->section)){section=f->section;fprintf(file,"%s:\n",section);}
        if(f->choices)fprintf(file,"  %s: %s\n",f->key,f->choices[v]);
        else fprintf(file,"  %s: %d\n",f->key,v);
    }
    if(s->patches_present){
        fprintf(file,"patches:\n");
        for(i=0;i<SR3_PATCH_FIELDS;i++)if(s->patches_present&(1u<<i)){
            const char *p=s->patches[i];fprintf(file,"  %s: '",sr3_patch_keys[i]);
            while(*p){fputc(*p,file);if(*p=='\'')fputc('\'',file);p++;}
            fprintf(file,"'\n");
        }
    }
    ok=!ferror(file);if(fclose(file)!=0)ok=0;
    if(!ok){remove(temp);return fail(error,cap,0,"write failed; original kept");}
#ifdef _WIN32
    snprintf(backup,sizeof(backup),"%s.bak",path);
    if(GetFileAttributesA(path)!=INVALID_FILE_ATTRIBUTES){
        if(!CopyFileA(path,backup,FALSE)){remove(temp);return fail(error,cap,0,"cannot back up settings; original kept");}
    }
    if(!MoveFileExA(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)){remove(temp);return fail(error,cap,0,"cannot replace settings; original kept");}
#else
    if(rename(temp,path)){remove(temp);return fail(error,cap,0,"cannot replace settings");}
#endif
    return 1;
}
unsigned long sr3_fingerprint(const char *path){FILE *f=fopen(path,"rb");unsigned long h=2166136261u;int c;if(!f)return 0;while((c=fgetc(f))!=EOF)h=((h^(unsigned char)c)*16777619u)&0xffffffffu;fclose(f);return h;}
