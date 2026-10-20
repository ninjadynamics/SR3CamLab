#define WIN32_LEAN_AND_MEAN
#include "cpu_affinity.h"
#include <stddef.h>
/* This pinned MinGW header names byte 1 Reserved[0]. Modern Windows uses
   that same ABI byte for EfficiencyClass (higher values = faster cores). */
_Static_assert(offsetof(PROCESSOR_RELATIONSHIP,GroupCount)==22,"processor topology ABI");

unsigned sr3_cpu_topology(Sr3CpuCore *cores,unsigned capacity) {
    DWORD bytes=0,offset=0;unsigned count=0;BYTE *buffer;
    GROUP_AFFINITY current;
    if(!cores || !capacity || !GetThreadGroupAffinity(GetCurrentThread(),&current))return 0;
    GetLogicalProcessorInformationEx(RelationProcessorCore,NULL,&bytes);
    if(!bytes || bytes>1024*1024)return 0;
    buffer=HeapAlloc(GetProcessHeap(),0,bytes);if(!buffer)return 0;
    if(!GetLogicalProcessorInformationEx(RelationProcessorCore,(void*)buffer,&bytes))goto done;
    while(offset<bytes) {
        SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX *info=(void*)(buffer+offset);
        unsigned g;size_t base=offsetof(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX,Processor.GroupMask);
        if(bytes-offset<base || info->Size<base || info->Size>bytes-offset){count=0;break;}
        if(info->Relationship==RelationProcessorCore) {
            if(info->Processor.GroupCount>(info->Size-base)/sizeof(GROUP_AFFINITY)){count=0;break;}
            for(g=0;g<info->Processor.GroupCount;g++) {
                GROUP_AFFINITY *a=&info->Processor.GroupMask[g];
                if(a->Group==current.Group && a->Mask) {
                    if(count==capacity){count=0;goto done;}
                    cores[count].mask=a->Mask;
                    cores[count++].efficiency=((const BYTE*)&info->Processor)[1];
                }
            }
        }
        offset+=info->Size;
    }
done:
    HeapFree(GetProcessHeap(),0,buffer);return count;
}

static DWORD_PTR first_bit(DWORD_PTR mask){return mask & ((DWORD_PTR)0-mask);}
DWORD_PTR sr3_cpu_select(const Sr3CpuCore *cores,unsigned count,DWORD_PTR available,unsigned limit) {
    DWORD_PTR selected=0;unsigned n=0,i;
    if(!limit)return available; /* zero retains the user's unrestricted setting */
    /* One thread per physical core, preferring performance cores on hybrid CPUs.
       Never assume adjacent logical IDs are different cores or widen affinity. */
    while(n<limit) {
        DWORD_PTR best=0;unsigned efficiency=0;
        for(i=0;i<count;i++) {
            DWORD_PTR mask=cores[i].mask & available;
            if(!mask || (cores[i].mask & selected))continue;
            mask=first_bit(mask);
            if(!best || cores[i].efficiency>efficiency ||
               (cores[i].efficiency==efficiency && mask<best)) {
                best=mask;efficiency=cores[i].efficiency;
            }
        }
        if(!best)break;
        selected|=best;n++;
    }
    /* Only use siblings if the budget exceeds the available physical cores.
       This also safely handles unavailable topology without guessing SMT IDs. */
    while(n<limit && (available & ~selected)){selected|=first_bit(available & ~selected);n++;}
    return selected;
}
unsigned sr3_cpu_physical_count(const Sr3CpuCore *cores,unsigned count,DWORD_PTR mask) {
    unsigned i,n=0;for(i=0;i<count;i++)if(cores[i].mask & mask)n++;return n;
}
