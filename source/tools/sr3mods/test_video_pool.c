#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>
#include "patchcore.h"
#include "video_pool.h"
static unsigned char image[0x750000],allocation[65536];
static unsigned allocs,writes,fail_at,code_writes;
static void *at(unsigned va,unsigned n){
    if(va>=0x400000u&&va-0x400000u+n<=sizeof(image))return image+va-0x400000u;
    if(va>=0x20000000u&&va-0x20000000u+n<=sizeof(allocation))return allocation+va-0x20000000u;
    return 0;
}
static int read_(GameMem *m,unsigned va,void *dst,unsigned n){void *p=at(va,n);(void)m;if(!p)return 0;memcpy(dst,p,n);return 1;}
static int write_(GameMem *m,unsigned va,const void *src,unsigned n,int keep){
    void *p=at(va,n);(void)m;(void)keep;++writes;
    if(va>=0x400000u&&va<0xB50000u&&++code_writes==fail_at){
        if(p&&n)memcpy(p,src,n/2);
        return 0;
    }
    if(!p)return 0;
    memcpy(p,src,n);return 1;
}
static unsigned alloc_(GameMem *m,unsigned n){(void)m;++allocs;return n<=sizeof(allocation)?0x20000000u:0;}
static GameMem memory={read_,write_,alloc_};
static void reset(void){unsigned i,v=0xD00DFEEDu;memset(image,0,sizeof(image));memset(allocation,0,sizeof(allocation));allocs=writes=fail_at=code_writes=0;
    for(i=0;i<sizeof(vp_sites)/sizeof(*vp_sites);++i)memcpy(at(vp_sites[i].va,vp_sites[i].size),vp_sites[i].bytes,vp_sites[i].size);
    /* Stand in for an initialized, unopened native record. */
    for(i=0;i<20;++i){unsigned a=VP_ORIGINAL_BASE+i*VP_STRIDE;memcpy(at(a+0x140,4),&v,4);}
    memset(at(VP_ORIGINAL_BASE+20*VP_STRIDE,32),0xA5,32);
}
static int original_code(void){unsigned i;for(i=0;i<sizeof(vp_sites)/sizeof(*vp_sites);++i)if(memcmp(at(vp_sites[i].va,vp_sites[i].size),vp_sites[i].bytes,vp_sites[i].size))return 0;return 1;}
#define CHECK(x,c) do{if(!(x))ExitProcess(c);}while(0)
void video_pool_test_entry(void){
    VideoPool p;unsigned i,j,cap,v,base;
    reset();memset(&p,0,sizeof(p));CHECK(vp_install(&memory,&p)==1,1);
    CHECK(p.capacity==64&&p.base==0x20000040u&&allocs==1,2);
    base=vp_current_base(&memory,&cap);CHECK(base==p.base&&cap==64,3);
    for(i=0;i<64;++i){read_(&memory,base+i*VP_STRIDE+0x140,&v,4);CHECK(v==0xD00DFEEDu,4);}
    for(i=0;i<32;++i)CHECK(*(unsigned char*)at(0xAD4C00u+i,1)==0xA5,5);
    j=writes;CHECK(vp_install(&memory,&p)==2&&writes==j,6);
    /* Every byte of every guarded instruction must be checked before mutation. */
    for(i=0;i<sizeof(vp_sites)/sizeof(*vp_sites);++i)for(j=0;j<vp_sites[i].size;++j){
        reset();memset(&p,0,sizeof(p));*(unsigned char*)at(vp_sites[i].va+j,1)^=1;
        CHECK(vp_install(&memory,&p)==0&&writes==0&&allocs==0,10);
    }
    for(i=1;i<=sizeof(vp_sites)/sizeof(*vp_sites);++i){
        reset();memset(&p,0,sizeof(p));fail_at=i;
        CHECK(vp_install(&memory,&p)==0&&!p.installed&&original_code(),11);
    }
    reset();memset(&p,0,sizeof(p));v=1;memcpy(at(VP_ORIGINAL_BASE+4,4),&v,4);
    CHECK(vp_install(&memory,&p)==0&&writes==0&&allocs==0,12);
    reset();memset(&p,0,sizeof(p));memcpy(at(VP_ORIGINAL_BASE+0x11C,4),&v,4);
    CHECK(vp_install(&memory,&p)==0&&writes==0&&allocs==0,13);
    ExitProcess(0);
}
