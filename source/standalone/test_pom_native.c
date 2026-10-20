#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pom_native.h"
#include "pom_native_layout.h"
#define CHECK(x) do {if(!(x)){printf("FAIL line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static BYTE *load(const char *name) {
 FILE *f=fopen(name,"rb");DWORD n,nfix,i,*fix;BYTE *p;
 if(!f)return 0;fread(&n,4,1,f);fread(&nfix,4,1,f);
 p=VirtualAlloc(0,n,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);fix=malloc(nfix*4);
 if(!p||!fix)return 0;
 fread(fix,4,nfix,f);fread(p,1,n,f);fclose(f);
 for(i=0;i<nfix;i++)*(DWORD*)(p+fix[i])+=(DWORD)p;
 free(fix);return p;
}
static void config(const char *text){FILE *f=fopen("native-test.yaml","wb");fputs(text,f);fclose(f);}
int main(void) {
 BYTE *u,*a;int i,n,e;DWORD *r;void *before[2];
 CHECK(VirtualAlloc((void*)0x30000000,0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)==(void*)0x30000000);
 u=load("uber.fixture");a=load("controls.fixture");CHECK(u&&a);
 *(DWORD*)0x30001280=2;
 ((DWORD*)0x30001080)[0]=1;((DWORD*)0x30001080)[1]=(DWORD)u+POM_NATIVE_UBER_NAME_OFFSET;
 ((DWORD*)0x30001080)[2]=2;((DWORD*)0x30001080)[3]=(DWORD)a+POM_NATIVE_AUX_NAME_OFFSET;
 for(i=0;i<11;i++) {
  r=(DWORD*)(a+POM_NATIVE_AUX_TECH_OFFSET+24*i+4);
  *(DWORD*)(r[0]+16)=123;*(DWORD*)(r[1]+16)=456;
 }
 sr3_pom_native_init(1);sr3_pom_native_controls(&e,&n);CHECK(e&&n==6);
 sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==6);
 for(i=0;i<20;i++)sr3_pom_native_adjust(-1);
 sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==0);
 r=(DWORD*)(a+POM_NATIVE_AUX_TECH_OFFSET+4);
 CHECK(!memcmp(u+POM_NATIVE_TARGET_OFFSET+4,r,8));
 for(i=1;i<=10;i++){sr3_pom_native_adjust(1);sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==i);CHECK(!memcmp(u+POM_NATIVE_TARGET_OFFSET+4,a+POM_NATIVE_AUX_TECH_OFFSET+24*i+4,8));}
 sr3_pom_native_adjust(1);sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==10);
 memcpy(before,u+POM_NATIVE_TARGET_OFFSET+4,8);
 for(i=0;i<20000;i++)sr3_pom_native_frame(0);
 CHECK(!memcmp(before,u+POM_NATIVE_TARGET_OFFSET+4,8));
 sr3_pom_native_reset();sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==10);
 sr3_pom_native_init(0);sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==0);

 config("global_depth_initial: 0.3\nlive_tuner: true\nfps_overlay: false\nfps_measurement: false\n");
 sr3_pom_native_init(1);CHECK(sr3_pom_native_configure("native-test.yaml"));
 sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==3);
 sr3_pom_native_adjust(1);sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==4);
 config("global_depth_initial: 0.0\nlive_tuner: false\n");
 CHECK(sr3_pom_native_configure("native-test.yaml"));CHECK(!sr3_pom_native_adjust(1));
 sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==0);
 config("global_depth_initial: 1.1\nlive_tuner: true\n");
 CHECK(!sr3_pom_native_configure("native-test.yaml"));
 config("global_depth_initial: nan\nlive_tuner: true\n");
 CHECK(!sr3_pom_native_configure("native-test.yaml"));
 config("global_depth_initial: 0.35\nlive_tuner: true\n");
 CHECK(!sr3_pom_native_configure("native-test.yaml"));
 config("global_depth_initial: 0.6\n global_depth_initial: 0.9\nlive_tuner: true\nfamilies:\n  family: 3\n");
 sr3_pom_native_init(1);CHECK(sr3_pom_native_configure("native-test.yaml"));
 sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==6);
 CHECK(!sr3_pom_native_configure("missing-native.yaml"));sr3_pom_native_frame(0);CHECK(sr3_pom_native_applied()==0);
 remove("native-test.yaml");
 puts("PASS YAML startup depth, live controls, missing/invalid config disabled.");
 puts("PASS native library controls: initial0.6, all gains, exact original pair at0, clamp, idle and reset. No GPU resources or draw hooks.");
 VirtualFree(u,0,MEM_RELEASE);VirtualFree(a,0,MEM_RELEASE);VirtualFree((void*)0x30000000,0,MEM_RELEASE);return 0;
}
