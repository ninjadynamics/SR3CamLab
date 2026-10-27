/* Relocate the supported game's video records before native boot opens graphs.
 * The records keep stable addresses for widgets; menu eviction frees resources,
 * never the records themselves. GameMem makes guards/rollback testable offline. */
#pragma once
#include <stdint.h>
#include <string.h>
#include "video_pool_sites.h"

#define VP_ORIGINAL_BASE 0xAD2F90u
#define VP_ORIGINAL_COUNT 20u
#define VP_STRIDE 0x16Cu
#define VP_CAPACITY 64u
#define VP_MAGIC 0x56524C55u
typedef struct { unsigned base, allocation, capacity; int installed; } VideoPool;

static unsigned vp_value(const VpSite *s,unsigned base,unsigned capacity) {
    if(s->kind==1)return capacity*VP_STRIDE;
    if(s->kind==2)return capacity+s->delta;
    if(s->kind==3)return (unsigned)(2-(int)capacity);
    if(s->kind==4)return base+capacity*VP_STRIDE+s->delta;
    return base+s->delta;
}
static void vp_instruction(const VpSite *s,unsigned base,unsigned capacity,unsigned char *out) {
    unsigned value=vp_value(s,base,capacity);
    memcpy(out,s->bytes,s->size);memcpy(out+s->offset,&value,s->width);
}
/* Read only the allocator operand and our allocation header. Legacy helpers can
 * discover a relocated pool without trusting arbitrary patched instruction data. */
static unsigned vp_current_base(GameMem *m,unsigned *capacity) {
    unsigned char opcode;unsigned base,header[3];
    if(!m->read(m,0x4DE43Au,&opcode,1)||opcode!=0xBF||
       !m->read(m,0x4DE43Bu,&base,4))return 0;
    if(base==VP_ORIGINAL_BASE){if(capacity)*capacity=VP_ORIGINAL_COUNT;return base;}
    if(base<16||!m->read(m,base-16,header,sizeof(header))||
       header[0]!=VP_MAGIC||header[1]!=VP_CAPACITY||header[2]!=VP_STRIDE)return 0;
    if(capacity)*capacity=header[1];
    return base;
}
/* 1 installed, 2 already installed, 0 refused/rolled back, -1 rollback failed.
 * Must run synchronously before boot, not while decoder/game threads are active. */
static int vp_install(GameMem *m,VideoPool *pool) {
    unsigned i,k,done=0,n=(unsigned)(sizeof(vp_sites)/sizeof(vp_sites[0]));
    unsigned capacity=0,base=vp_current_base(m,&capacity),header[3]={VP_MAGIC,VP_CAPACITY,VP_STRIDE};
    unsigned char actual[10],next[10],original[VP_ORIGINAL_COUNT*VP_STRIDE];
    unsigned char records[VP_CAPACITY*VP_STRIDE];
    if(pool->installed)return base==pool->base&&capacity==pool->capacity?2:0;
    if(base!=VP_ORIGINAL_BASE||capacity!=VP_ORIGINAL_COUNT)return 0;
    for(i=0;i<n;++i)if(!m->read(m,vp_sites[i].va,actual,vp_sites[i].size)||
        memcmp(actual,vp_sites[i].bytes,vp_sites[i].size))return 0;
    if(!m->read(m,VP_ORIGINAL_BASE,original,sizeof(original)))return 0;
    for(i=0;i<VP_ORIGINAL_COUNT;++i){
        unsigned used,graph;memcpy(&used,original+i*VP_STRIDE+4,4);
        memcpy(&graph,original+i*VP_STRIDE+0x11C,4);if(used||graph)return 0;
    }
    if(!m->alloc||(pool->allocation=m->alloc(m,64+sizeof(records)))==0)return 0;
    pool->base=pool->allocation+64;pool->capacity=VP_CAPACITY;
    memcpy(records,original,sizeof(original));
    for(i=VP_ORIGINAL_COUNT;i<VP_CAPACITY;++i)memcpy(records+i*VP_STRIDE,original,VP_STRIDE);
    if(!m->write(m,pool->base,records,sizeof(records),1)||
       !m->write(m,pool->base-16,header,sizeof(header),1))return 0;
    for(i=0;i<n;++i){
        vp_instruction(&vp_sites[i],pool->base,VP_CAPACITY,next);
        /* Include a failed/partial write in rollback too. */
        done=i+1;
        if(!m->write(m,vp_sites[i].va,next,vp_sites[i].size,0))goto rollback;
    }
    for(i=0;i<n;++i){
        vp_instruction(&vp_sites[i],pool->base,VP_CAPACITY,next);
        if(!m->read(m,vp_sites[i].va,actual,vp_sites[i].size)||memcmp(actual,next,vp_sites[i].size))goto rollback;
    }
    pool->installed=1;return 1;
rollback:
    k=0;while(done){--done;if(!m->write(m,vp_sites[done].va,vp_sites[done].bytes,vp_sites[done].size,0))k=1;}
    pool->installed=0;return k?-1:0;
}
