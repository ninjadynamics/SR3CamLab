/* Native library POM: no D3D draw/Release hooks and no owned GPU resources.
   The engine creates, binds, resets and releases its own shader records.
   A queued key change only selects a precompiled technique at a frame boundary. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include "pom_native.h"
#include "pom_native_layout.h"
#ifndef POM_REGISTRY_BASE
#define POM_REGISTRY_BASE 0x9f0000u
#endif
static volatile LONG gain=6, enabled=1;
static int applied=-1, tuning=1;
static BYTE *uber,*aux;
int sr3_pom_native_applied(void) {return applied;}
static int readmem(const void *p,void *out,SIZE_T n) {
 SIZE_T got=0;return ReadProcessMemory(GetCurrentProcess(),p,out,n,&got)&&got==n;
}
static BYTE *find_effect(const char *name,unsigned offset) {
 DWORD count,i;char text[32];DWORD entry[2],header[2];
 if(!readmem((void*)(POM_REGISTRY_BASE+0x1280),&count,4)||count>128)return 0;
 for(i=0;i<count;i++) {
  if(!readmem((void*)(POM_REGISTRY_BASE+0x1080+8*i),entry,8)||!entry[1])continue;
  memset(text,0,sizeof(text));
  if(!readmem((void*)entry[1],text,strlen(name)+1)||strcmp(text,name))continue;
  if(entry[1]<offset)return 0;
  if(!readmem((void*)(entry[1]-offset),header,8))return 0;
  if(!strcmp(name,"ubershadergame.fx") && header[0]!=(1229u|(POM_NATIVE_RECORD_COUNT<<16)))return 0;
  if(!strcmp(name,"url_pom_controls_v1.fx") && header[0]!=(11u|(13u<<16)))return 0;
  if(header[1]!=41)return 0;
  return (BYTE*)(entry[1]-offset);
 }
 return 0;
}
void sr3_pom_native_init(int on) {enabled=on!=0;gain=6;tuning=1;applied=-1;uber=aux=0;}

/* Read startup controls once, never from a draw/frame callback. Family gains
   and exclusions are baked by stage_pom_wide and checked by PLAY preflight. */
int sr3_pom_native_configure(const char *path) {
 FILE *f=fopen(path,"rb");char line[1024],*p,*v,*end,*comment;int seen=0,n=0,live=0,ok=1;
 if(!f){enabled=0;gain=0;tuning=0;return 0;}
 while(fgets(line,sizeof(line),f)) {
  if(!strchr(line,'\n')&&!feof(f)){ok=0;break;}
  if(line[0]==' '||line[0]=='\t')continue;
  comment=strchr(line,'#');if(comment)*comment=0;
  p=strchr(line,':');if(!p)continue;*p=0;v=p+1;
  while(isspace((unsigned char)*v))v++;
  end=v+strlen(v);while(end>v&&isspace((unsigned char)end[-1]))*--end=0;
  if(!strcmp(line,"global_depth_initial")){
   double d=strtod(v,&end);int candidate;
   if((seen&1)||end==v||*end||!(d>=0&&d<=1)){ok=0;break;}
   candidate=(int)(d*10+.5);
   if(d-candidate/10.0>0.000001||candidate/10.0-d>0.000001){ok=0;break;}
   n=candidate;seen|=1;
  } else if(!strcmp(line,"live_tuner")){
   if((seen&2)||(strcmp(v,"true")&&strcmp(v,"false"))){ok=0;break;}
   live=!strcmp(v,"true");seen|=2;
  } else if(!strcmp(line,"global_depth_min")||!strcmp(line,"global_depth_max")){
   double d=strtod(v,&end);double expected=!strcmp(line,"global_depth_max")?1:0;
   if(end==v||*end||d!=expected){ok=0;break;}
  } else if(!strcmp(line,"fps_overlay")||!strcmp(line,"fps_measurement")){
   if(strcmp(v,"false")){ok=0;break;} /* Native integration has no FPS overlay. */
  }
 }
 if(ferror(f))ok=0;fclose(f);
 if(!ok||seen!=3){enabled=0;gain=0;tuning=0;applied=-1;return 0;}
 gain=n;tuning=live;applied=-1;return 1;
}

void sr3_pom_native_reset(void) {applied=-1;uber=aux=0;}
void sr3_pom_native_controls(int *on,int *tenths) {
 *on=InterlockedCompareExchange(&enabled,0,0);*tenths=InterlockedCompareExchange(&gain,0,0);
}
int sr3_pom_native_adjust(int delta) {
 LONG old,next;
 if(!tuning)return 0;
 if(!delta){do{old=InterlockedCompareExchange(&enabled,0,0);}while(InterlockedCompareExchange(&enabled,!old,old)!=old);}
 else {do{old=InterlockedCompareExchange(&gain,0,0);next=old+(delta>0?1:-1);if(next<0)next=0;if(next>10)next=10;}while(InterlockedCompareExchange(&gain,next,old)!=old);}
 return 1;
}
void sr3_pom_native_frame(IDirect3DDevice9 *device) {
 int on,n;DWORD records[2],objects[2];(void)device;
 sr3_pom_native_controls(&on,&n);if(!on)n=0;
 if(applied==n)return;
 if(!uber)uber=find_effect("ubershadergame.fx",POM_NATIVE_UBER_NAME_OFFSET);
 if(!aux)aux=find_effect("url_pom_controls_v1.fx",POM_NATIVE_AUX_NAME_OFFSET);
 if(!uber||!aux)return;
 if(!readmem(aux+POM_NATIVE_AUX_TECH_OFFSET+24*n+4,records,8))return;
 if(!readmem((BYTE*)records[0]+16,&objects[0],4)||!objects[0])return;
 if(!readmem((BYTE*)records[1]+16,&objects[1],4)||!objects[1])return;
 /* Runtime technique fields are engine-owned writable data. Never replace the
    COM pointer in a shader record: that would upset native resource ownership. */
 InterlockedExchangePointer((void**)(uber+POM_NATIVE_TARGET_OFFSET+4),(void*)records[0]);
 InterlockedExchangePointer((void**)(uber+POM_NATIVE_TARGET_OFFSET+8),(void*)records[1]);
 applied=n;
}
