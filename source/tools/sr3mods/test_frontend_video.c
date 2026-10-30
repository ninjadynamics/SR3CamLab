#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objbase.h>
#include <stdint.h>
#include <stdarg.h>
#include <string.h>
#include "patchcore.h"
static DWORD clock_,thread_=1;
static unsigned opens,releases,events,uninit,rendered;
static int fail_open,fail_stop;
static DWORD test_clock(void){return clock_;}
static DWORD test_thread(void){return thread_;}
static BOOL test_close(HANDLE h){if(!h)ExitProcess(90);++events;return TRUE;}
static void test_uninit(void){++uninit;}
static int fe_video_test_open(void *,const char *);
void pc_logf(const char *fmt,...){(void)fmt;}
#define FE_VIDEO_TEST
#define GetTickCount test_clock
#define GetCurrentThreadId test_thread
#define CloseHandle test_close
#define CoUninitialize test_uninit
#include "frontend_video.c"
typedef struct { void **table; unsigned id; } FakeObject;
static void *table[10];
static FakeObject objects[64][6];
static unsigned char data[64*VP_STRIDE];
static ULONG __stdcall release_(void *p){FakeObject *o=p;if(o->id>=640)ExitProcess(91);++releases;return 0;}
static HRESULT __stdcall stop_(void *p){(void)p;return fail_stop?E_FAIL:S_OK;}
static int fe_video_test_open(void *object,const char *path){
    unsigned char *p=object;unsigned h=(unsigned)(p-data)/VP_STRIDE,i;
    static const unsigned off[]={0x11c,0x120,0x124,0x128,0x12c,0x144};
    if(path==(const char*)p+0xC||!path[0])ExitProcess(92);
    ++opens;
    for(i=0;i<6;++i){objects[h][i].table=table;objects[h][i].id=h*10+i;*word(p,off[i])=(unsigned)(uintptr_t)&objects[h][i];}
    *word(p,0x134)=1001+h*2;*word(p,0x138)=1002+h*2;*word(p,0x13c)=1;
    return !fail_open;
}
static uintptr_t __cdecl render_(int h,int pause,int flags){
    (void)flags;
    /* Match the native playback-state transition, not just its return pointer.
       Open alone leaves the graph stopped and cannot produce a video frame. */
    if(h>=20&&!rendered&&(*word(record(h),0)!=1||pause))ExitProcess(93);
    if(!pause)*word(record(h),0)=0;
    ++rendered;return (uintptr_t)(record(h)+0x140);
}
static void reset_(void){
    memset(&pool,0,sizeof(pool));memset(use,0,sizeof(use));memset(data,0,sizeof(data));memset(blank,0,sizeof(blank));
    memset(ours,0,sizeof(ours));loading_at=loading_seen=0;
    pool.base=(unsigned)(uintptr_t)data;pool.capacity=64;pool.installed=1;
    table[2]=(void*)release_;table[9]=(void*)stop_;original_frame=render_;
    opens=releases=events=uninit=rendered=0;clock_=0;thread_=1;fail_open=fail_stop=0;ready=0;
}
#define CHECK(x,c) do{if(!(x))ExitProcess(c);}while(0)
void frontend_video_test_entry(void){
    int h,j;uintptr_t descriptor;
    reset_();h=fe_video_register(".\\frontend\\PC\\Videos\\classic_MTN.wmv");CHECK(h==20,1);
    CHECK(fe_video_register(".\\frontend\\PC\\Videos\\classic_MTN.wmv")==h,2);
    CHECK(opens==0&&*word(record(h),4)==1,3);
    fe_video_ready();descriptor=frame(h,0,0);CHECK(descriptor&&(opens==1)&&(rendered==1),4);
    clock_=500;fe_video_tick();CHECK(releases==0,5);
    clock_=800;fe_video_tick();CHECK(releases==6&&events==2&&uninit==1,6);
    CHECK(*word(record(h),4)==1&&!*word(record(h),0x144),7);
    CHECK(!strcmp((const char*)record(h)+0xC,".\\frontend\\PC\\Videos\\classic_MTN.wmv"),8);
    CHECK(frame(h,0,0)==descriptor&&opens==2,9);
    /* A video touched by a newly opened menu stays live. */
    clock_=1400;frame(h,0,0);clock_=1800;fe_video_tick();CHECK(releases==6,10);
    j=fe_video_register(".\\frontend\\PC\\Videos\\loading.wmv");frame(j,0,0);
    clock_=2600;fe_video_tick();CHECK(releases==12&&*word(record(j),0x11c),11);
    fe_video_reset();CHECK(releases==18&&events==6&&uninit==3,12);
    CHECK(!frame(-1,0,0)&&!frame(64,0,0),13);
    reset_();h=fe_video_register("fixture.wmv");fe_video_ready();fail_open=1;
    CHECK(!frame(h,0,0)&&opens==1&&releases==6&&events==2&&uninit==1,14);
    clock_=500;CHECK(!frame(h,0,0)&&opens==1,15);
    clock_=1100;fail_open=0;CHECK(frame(h,0,0)&&opens==2,16);
    fail_stop=1;clock_=2000;fe_video_tick();CHECK(releases==6&&*word(record(h),0x11c),17);
    fail_stop=0;thread_=2;clock_=2200;fe_video_tick();CHECK(releases==6,18);
    thread_=1;clock_=2400;fe_video_tick();CHECK(releases==12&&events==4&&uninit==2,19);
    /* Logical registration capacity and invalid input do not overwrite records. */
    reset_();CHECK(fe_video_register("")==-1,20);
    for(j=20;j<64;++j){char name[]="video00.wmv";name[5]=(char)('0'+j/10);name[6]=(char)('0'+j%10);CHECK(fe_video_register(name)==j,21);}
    CHECK(fe_video_register("overflow.wmv")==-1,22);
    reset_();h=fe_video_register("first.wmv");j=fe_video_register("second.wmv");
    {int menu[]={h,j};fe_video_ready();fe_video_menu(menu,2);fe_video_tick();fe_video_tick();
     CHECK(opens==2,23);clock_=2000;fe_video_tick();CHECK(releases==0,24);
     CHECK(fe_video_open()==2,26);
     fe_video_menu(NULL,0);clock_=2800;fe_video_tick();CHECK(releases==12&&fe_video_open()==0,25);}
    /* A native record beyond 20 is never evicted, and does not keep the
       release sweep alive; the loading animation's draws are timed. */
    reset_();fe_video_ready();CHECK(fe_video_loading_age()==0xFFFFFFFFu,27);
    memcpy(record(40)+0xC,"native.wmv",11);*word(record(40),4)=1;frame(40,0,0);CHECK(opens==1,28);
    clock_=5000;fe_video_tick();CHECK(releases==0&&*word(record(40),0x11c)&&fe_video_open()==0,29);
    strcpy((char *)record(41)+0xC,"C:\\Rally\\frontend\\PC\\Videos\\LOADING.WMV");*word(record(41),4)=1;
    clock_=6000;frame(41,0,0);CHECK(fe_video_loading_age()==0,30);
    clock_=6500;CHECK(fe_video_loading_age()==500,31);clock_=9000;fe_video_tick();CHECK(releases==0,32);
    ExitProcess(0);
}
