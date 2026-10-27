#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include "patchcore.h"
#include "video_pool.h"
#include "frontend_video.h"

typedef uintptr_t (__cdecl *GetFrame)(int,int,int);
typedef ULONG (__stdcall *Release)(void *);
typedef HRESULT (__stdcall *Control)(void *);
typedef struct { DWORD touched,attempt,thread; int failed,thread_warning; } VideoUse;
static VideoPool pool;
static VideoUse use[VP_CAPACITY];
static unsigned char blank[VP_STRIDE];
static GetFrame original_frame;
static int ready;
static DWORD last_sweep;

static unsigned *word(unsigned char *p,unsigned offset){return (unsigned *)(p+offset);}
static unsigned char *record(int h){return (unsigned char *)(uintptr_t)(pool.base+(unsigned)h*VP_STRIDE);}
static void release_interface(unsigned char *p,unsigned offset){
    void *object=(void *)(uintptr_t)*word(p,offset);
    if(object){void **table=*(void ***)object;*word(p,offset)=0;((Release)table[2])(object);}
}
/* The original ABI passes the object in EDI and its path in ECX. */
#ifdef FE_VIDEO_TEST
static int native_open(void *object,const char *path){return fe_video_test_open(object,path);}
#else
__attribute__((naked)) static int native_open(void *object,const char *path){
    __asm__("pushl %edi\n\tmovl 8(%esp),%edi\n\tmovl 12(%esp),%ecx\n\t"
            "movl $0x4ddc80,%eax\n\tcall *%eax\n\tpopl %edi\n\tret");
}
#endif
static int close_video(int h){
    unsigned char *p=record(h);unsigned a,b;int initialized;
    void *control=(void *)(uintptr_t)*word(p,0x120);
    if(use[h].thread&&use[h].thread!=GetCurrentThreadId()){
        if(!use[h].thread_warning){pc_logf("Frontend video %d: retained on another COM owner thread.",h);use[h].thread_warning=1;}
        return 0;
    }
    if(control){void **table=*(void ***)control;if(FAILED(((Control)table[9])(control)))return 0;}
    a=*word(p,0x134);b=*word(p,0x138);initialized=*word(p,0x13C)!=0;
    /* Stop first; release the source/control interfaces before the graph that
     * owns the renderer. Events belong to this open, not to the pool record. */
    release_interface(p,0x12C);release_interface(p,0x128);
    release_interface(p,0x124);release_interface(p,0x120);release_interface(p,0x11C);
    release_interface(p,0x144);
    if(a)CloseHandle((HANDLE)(uintptr_t)a);
    if(b&&b!=a)CloseHandle((HANDLE)(uintptr_t)b);
    if(initialized&&use[h].thread)CoUninitialize();
    /* Keep the path and reserved flag: widgets retain this descriptor's stable
     * address and the next draw reopens the same logical video. */
    memcpy(p+0x11C,blank+0x11C,VP_STRIDE-0x11C);
    *word(p,0)=0;*word(p,4)=1;*word(p,8)=0;
    use[h].thread=0;return 1;
}
static uintptr_t __cdecl frame(int h,int pause,int flags){
    unsigned char *p;DWORD now=GetTickCount();char path[256];
    if(!pool.installed||h<0||(unsigned)h>=pool.capacity)return 0;
    p=record(h);use[h].touched=now;
    if(!*word(p,0x11C)){
        if(!p[0xC]||(use[h].failed&&(DWORD)(now-use[h].attempt)<1000))return 0;
        use[h].attempt=now;use[h].thread=GetCurrentThreadId();
        /* Native open copies the path into this record; do not give its CRT
         * string copy overlapping source and destination buffers. */
        memcpy(path,p+0xC,sizeof(path));path[255]=0;
        if(!native_open(p,path)){
            close_video(h);use[h].failed=1;return 0;
        }
        use[h].failed=0;
    }else if(!use[h].thread)use[h].thread=GetCurrentThreadId();
    return original_frame(h,pause,flags);
}
unsigned fe_video_memory_address(unsigned address,unsigned size){
    if(pool.installed&&address>=VP_ORIGINAL_BASE&&
       address-VP_ORIGINAL_BASE+size<=VP_ORIGINAL_COUNT*VP_STRIDE)
        return pool.base+address-VP_ORIGINAL_BASE;
    return address;
}
int fe_video_adjust_camera(const void *source,unsigned size,void *destination){
    const unsigned char *src=source;unsigned char *out=destination;unsigned i,j,n=0,base=pool.base;
    static const unsigned char add[]={0x81,0xC7,0x90,0x2F,0xAD,0};
    if(!pool.installed||size<64)return 0;
    for(i=0;i+sizeof(add)<=size;++i)if(!memcmp(src+i,add,sizeof(add))){
        for(j=i>32?i-32:0;j+3<i;++j)if(src[j]==0x83&&src[j+1]==0xF8&&src[j+2]==20)break;
        if(j+3>=i)return -1;
        if(!n)memcpy(out,source,size);
        memcpy(out+i+2,&base,4);out[j+2]=VP_CAPACITY;++n;
    }
    return n==1?1:n?-1:0;
}
int fe_video_install(GameMem *m){
    unsigned char actual[5],jump[5],trampoline[10];unsigned cave;int32_t rel;
    static const unsigned char original[]={0x56,0x8B,0x74,0x24,0x08};
    if(pool.installed)return 1;
    if(!m->read(m,0x4DE370,actual,5)||memcmp(actual,original,5))return 0;
    /* Allocate everything before committing the relocation. */
    cave=m->alloc(m,sizeof(trampoline));if(!cave)return 0;
    memcpy(trampoline,original,5);trampoline[5]=0xE9;
    rel=(int32_t)(0x4DE375u-(cave+10));memcpy(trampoline+6,&rel,4);
    if(!m->write(m,cave,trampoline,sizeof(trampoline),1))return 0;
    if(vp_install(m,&pool)!=1)return 0;
    memcpy(blank,record(0),VP_STRIDE);
    original_frame=(GetFrame)(uintptr_t)cave;
    jump[0]=0xE9;rel=(int32_t)((uintptr_t)frame-(0x4DE370u+5));memcpy(jump+1,&rel,4);
    if(!m->write(m,0x4DE370,jump,5,0))return -1;
    pc_logf("Frontend videos: relocated to %08X, capacity %u; lazy menu playback staged.",pool.base,pool.capacity);
    return 1;
}
void fe_video_ready(void){ready=1;last_sweep=GetTickCount();}
void fe_video_tick(void){
    DWORD now=GetTickCount();unsigned i;
    if(!ready||(DWORD)(now-last_sweep)<100)return;
    last_sweep=now;
    for(i=0;i<pool.capacity;++i){
        unsigned char *p=record((int)i);const char *path=(const char *)p+0xC;
        const char *file=strrchr(path,'\\');file=file?file+1:path;
        /* The loading animation is shared with races; keep its decoder alive. */
        if(*word(p,0x11C)&&_stricmp(file,"loading.wmv")&&
           (DWORD)(now-use[i].touched)>750)close_video((int)i);
    }
}
int fe_video_register(const char *path){
    unsigned i;size_t n;
    if(!pool.installed||!path||(n=strlen(path))==0||n>=256)return -1;
    /* Leave native boot and Hornet's reserved records 0..19 available. */
    for(i=20;i<pool.capacity;++i)if(!_stricmp((const char *)record((int)i)+0xC,path))return (int)i;
    for(i=20;i<pool.capacity;++i){unsigned char *p=record((int)i);if(*word(p,4))continue;
        memcpy(p,blank,VP_STRIDE);memcpy(p+0xC,path,n+1);*word(p,4)=1;return (int)i;}
    return -1;
}
void *fe_video_texture(int h){
    if(!frame(h,0,0))return 0;
    return (void *)(uintptr_t)*word(record(h),0x144);
}
void fe_video_reset(void){
    unsigned i;if(!ready)return;
    for(i=0;i<pool.capacity;++i)if(*word(record((int)i),0x11C))close_video((int)i);
}
