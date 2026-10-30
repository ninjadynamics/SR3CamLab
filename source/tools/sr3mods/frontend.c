#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "frontend.h"
#include "frontend_model.h"
#include "frontend_video.h"
#include "frontend_native.h"
#include "pc_frontend.h"
static FeCatalog catalog;
static FeMenu menu;
static volatile LONG active,input_buttons,input_edges,key_edges,modal;
static unsigned input_previous,tap_at[2];
static int tap_source[2];
static int classic_done,quick_open,view_ready;
static volatile int confirm_active,selected_id;
static unsigned route,route_at,release_until;static int chosen=-1,release_warned;static char videos[260],message[180];
typedef int (__cdecl *State)(void *);
typedef unsigned (__fastcall *Hash)(const char *);
static unsigned buttons(void){return (unsigned)InterlockedCompareExchange(&input_buttons,0,0);}
static void show(const char *name){unsigned hash=((Hash)(uintptr_t)0x54A810)(name);((void (__cdecl *)(unsigned,int))(uintptr_t)0x54D5E0)(hash,1);}
static void set_modal(int on){InterlockedExchange(&modal,on);if(!on){fe_native_detach_view();release_until=GetTickCount()+10000;release_warned=0;}}
static void begin(int classic){fe_menu_begin(&menu,classic);route=0;message[0]=0;set_modal(1);
    InterlockedExchange(&input_edges,0);InterlockedExchange(&key_edges,0);tap_source[0]=tap_source[1]=0;
    view_ready=0;show(classic?"ID_PAGE_CARSELECT":"ID_PAGE_TRACKSELECT");
    pc_logf("Frontend: opened native %s.",classic?"Classic games":"Quick Race tracks");}
int fe_input(const Sr3Input *in){unsigned b=0;
    if(!active)return 0;
    if(in->steering < -12000)b|=FE_LEFT;
    if(in->steering>12000)b|=FE_RIGHT;
    if((in->buttons&SR3_START)||in->gas>96)b|=FE_SELECT;
    if((in->buttons&SR3_VIEW)||in->brake>96)b|=FE_BACK;
    if(modal)InterlockedOr(&input_edges,(LONG)(b&~input_previous));
    input_previous=b;InterlockedExchange(&input_buttons,(LONG)b);return modal!=0;
}
void fe_key(unsigned key){unsigned b=0;if(!active||!modal)return;
    if(key==VK_LEFT)b=FE_LEFT;else if(key==VK_RIGHT)b=FE_RIGHT;
    else if(key==VK_UP||key==VK_RETURN)b=FE_SELECT;
    else if(key==VK_DOWN||key==VK_BACK||key=='V')b=FE_BACK;
    if(b)InterlockedOr(&key_edges,(LONG)b);
}
/* These bridges preserve the executable's nonstandard register arguments. */
__attribute__((naked)) static void bind_track(int id){__asm__("movl 4(%esp),%ecx\n\tpushl $0x9dbda0\n\tmovl $0x5af700,%eax\n\tcall *%eax\n\tret");}
__attribute__((naked)) static void confirm_track(void){__asm__("subl $4,%esp\n\tmovl $1,(%esp)\n\tmovl %esp,%eax\n\tmovl $0x6669c0,%edx\n\tcall *%edx\n\taddl $4,%esp\n\tret");}
/* Original GetSelection expects EDI hash. Tail-call preserves that convention. */
__attribute__((naked)) static int choose_native(void){__asm__(
    "cmpl $0,_confirm_active\n\tje 1f\n\tmovl _selected_id,%eax\n\tret\n1:\n\tmovl $0x606490,%eax\n\tjmp *%eax");}
static __attribute__((used,noinline)) int suppress_car_callback(void){return modal||(!classic_done&&*(unsigned*)0x9dbdb4==7);}
__attribute__((naked)) static int car_callback(void){__asm__("pushal\n\tcall _suppress_car_callback\n\ttestl %eax,%eax\n\tpopal\n\tjne 1f\n\tmovl $0x6622e0,%eax\n\tjmp *%eax\n1:\n\txorl %eax,%eax\n\tret");}
__attribute__((naked)) static int track_callback(void){__asm__("cmpl $0,_modal\n\tjne 1f\n\tmovl $0x666be0,%eax\n\tjmp *%eax\n1:\n\txorl %eax,%eax\n\tret");}
/* A keyboard press reaches the menu twice: as WM_KEYDOWN and as the polled,
   pulse-stretched level, in either order. Pair them within 150 ms so one press
   is one card. A gamepad press has only the polled edge. */
static unsigned taps(unsigned keys,unsigned polled,unsigned now){
    unsigned out=0;int i,source;
    for(i=0;i<2;++i)for(source=1;source<=2;++source)if((source==1?keys:polled)&(i?FE_RIGHT:FE_LEFT)){
        if(tap_source[i]&&tap_source[i]!=source&&now-tap_at[i]<=150)tap_source[i]=0;
        else{out|=i?FE_TAP_RIGHT:FE_TAP_LEFT;tap_source[i]=source;tap_at[i]=now;}
    }
    return out;
}
static int step(void){
    unsigned keys=(unsigned)InterlockedExchange(&key_edges,0),polled=(unsigned)InterlockedExchange(&input_edges,0);
    unsigned b=buttons()|((keys|polled)&(FE_SELECT|FE_BACK))|taps(keys,polled,GetTickCount());int event;if(GetAsyncKeyState(VK_BACK)&0x8000)b|=FE_BACK;
    /* ShowPage queues a transition. Its selector is not necessarily in the
       active-page tree until a later tick. Do not consume navigation against
       an unbound placeholder selector. */
    if(!view_ready){
        if(fe_native_view(&menu)){view_ready=1;fe_native_activate();menu.await_release=buttons()!=0;menu.previous=(int)buttons();}
        return FE_IDLE;
    }
    if(route){int status=pc_frontend_status(route);
        if(status<0||(DWORD)(GetTickCount()-route_at)>10000){
            pc_logf("Frontend: track preparation for %s %s after %u ms; choose again or go back.",catalog.tracks[chosen].title,status<0?"failed":"timed out",(unsigned)(GetTickCount()-route_at));
            route=0;menu.pending=0;menu.await_release=1;snprintf(message,sizeof message,"Track preparation failed. Choose again or go back.");return FE_IDLE;}
        if(status>0&&!b){pc_logf("Frontend: %s prepared after %u ms.",catalog.tracks[chosen].title,(unsigned)(GetTickCount()-route_at));route=0;return FE_CHOSEN;}return FE_IDLE;
    }
    {int page=menu.page;menu.busy=fe_native_busy();menu.blocked=fe_native_blocked();event=fe_menu_step(&catalog,&menu,b,GetTickCount());
     if(event==FE_CHANGED){if(menu.page!=page){view_ready=fe_native_view(&menu);if(view_ready)fe_native_activate();}else fe_native_cursor(menu.cursor,menu.moved);}}
    if(event==FE_CHOSEN){FeTrack *t=&catalog.tracks[menu.track];chosen=menu.track;
        pc_logf("Frontend: chose %s (%s, folder %c, native track %d); waiting for the track worker.",t->title,t->slot,t->directory,t->native_id);
        selected_id=t->native_id;route=pc_frontend_select(t->native_id,t->directory);route_at=GetTickCount();snprintf(message,sizeof message,"Preparing %s...",t->title);return FE_IDLE;}
    return event;
}
static int __cdecl mode_state(void *ctx){
    if(!*(unsigned *)((char*)ctx+8)){classic_done=0;quick_open=0;menu.page=FE_NONE;set_modal(0);fe_native_leave();pc_frontend_cancel();}
    return ((State)(uintptr_t)0x64E170)(ctx);
}
static int __cdecl classic_state(void *ctx){int event;
    if(classic_done)return ((State)(uintptr_t)0x648060)(ctx);
    if(!modal)begin(1);
    event=step();
    if(event==FE_CANCELLED){pc_logf("Frontend: left Classic.");set_modal(0);pc_frontend_cancel();*(unsigned*)0x9c432c=0;show("ID_PAGE_MODESELECT");return 0;}
    if(event==FE_CHOSEN){pc_logf("Frontend: Classic bound %s; car selection follows.",catalog.tracks[chosen].title);bind_track(selected_id);classic_done=1;menu.page=FE_NONE;set_modal(0);show("ID_PAGE_CARSELECT");*(unsigned*)((char*)ctx+8)=0;return ((State)(uintptr_t)0x648060)(ctx);}
    ((void (__cdecl *)(void))(uintptr_t)0x5c77c0)();return 14;
}
static int __cdecl quick_state(void *ctx){int event;(void)ctx;
    if(!quick_open){begin(0);quick_open=1;}
    event=step();
    if(event==FE_CANCELLED){pc_logf("Frontend: left Quick Race tracks.");quick_open=0;set_modal(0);pc_frontend_cancel();show("ID_PAGE_TRANSSELECT");return 9;}
    if(event==FE_CHOSEN){confirm_active=1;confirm_track();confirm_active=0;quick_open=0;menu.page=FE_NONE;set_modal(0);
        pc_logf("Frontend: Quick Race confirmed %s; the race loads next.",catalog.tracks[chosen].title);return 11;}
    ((void (__cdecl *)(void))(uintptr_t)0x5c77c0)();return 10;
}
int fe_frame(void *device){
    int open;(void)device;
    if(!active)return 0;
    fe_video_tick();
    if(modal)return 1;
    /* This callback runs only while requested. After a menu closes it keeps
     * running until the preview decoders are released (about a second), so a
     * race never loads with menu videos holding graphs, textures and decoder
     * threads. It never runs on into a race for longer than 10 s. */
    open=fe_video_open();
    if(open&&(int)(GetTickCount()-release_until)<0)return 1;
    if(open&&!release_warned){release_warned=1;pc_logf("Frontend videos: %d preview decoder%s still open 10 s after the menus closed.",open,open==1?"":"s");}
    return 0;
}
void fe_reset(void){if(active)fe_video_reset();}
int fe_install(GameMem *m,const char *mod){
    char path[512],error[256],env[8];unsigned v;int i;
    struct {unsigned va,expected,value;} sites[]={
        {0x7246c8,0x64e170,(unsigned)(uintptr_t)mode_state},
        {0x7246f0,0x648270,(unsigned)(uintptr_t)quick_state},
        {0x724700,0x648060,(unsigned)(uintptr_t)classic_state},
        {0x657b67,0x666be0,(unsigned)(uintptr_t)track_callback},
        {0x657b92,0x6622e0,(unsigned)(uintptr_t)car_callback},
        {0x666a12,0xfff9fa7a,(unsigned)((uintptr_t)choose_native-0x666a16u)}
    };
    if(GetEnvironmentVariableA("SR3LAB_FRONTEND",env,sizeof env)&&env[0]=='0')return 0;
    snprintf(path,sizeof path,"%s\\frontend-tracks.json",mod);
    if(GetFileAttributesA(path)==INVALID_FILE_ATTRIBUTES)return 0;
    if(!fe_catalog_load(path,&catalog,error,sizeof error)){pc_logf("Frontend: %s",error);return -1;}
    GetModuleFileNameA(NULL,videos,sizeof videos);{char *p=strrchr(videos,'\\');if(!p)return -1;*p=0;}
    if(strlen(videos)+20>=sizeof videos)return -1;
    strcat(videos,"\\frontend\\PC\\Videos");
    for(i=0;i<(int)(sizeof sites/sizeof sites[0]);++i)if(!m->read(m,sites[i].va,&v,4)||v!=sites[i].expected){pc_logf("Frontend: byte guard refused %08X",sites[i].va);return -1;}
    if(fe_video_install(m)!=1)return -1;
    if(!fe_native_install(m,&catalog))return -1;
    for(i=0;i<(int)(sizeof sites/sizeof sites[0]);++i)if(!m->write(m,sites[i].va,&sites[i].value,4,0))return -1;
    pc_frontend_enable();InterlockedExchange(&active,1);pc_logf("Frontend: %d catalog tracks; native game/track pages enabled.",catalog.count);return 1;
}
