#define WIN32_LEAN_AND_MEAN
#include "cpu_affinity.h"
#include <stdio.h>
#define CHECK(x) do{if(!(x)){printf("FAIL CPU line %d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(void) {
    Sr3CpuCore hybrid[]={{3,1},{12,1},{48,1},{192,1},{256,0},{512,0}};
    Sr3CpuCore unusual[]={{0x11,1},{0x22,1},{0x44,1},{0x88,1}};
    Sr3CpuCore reversed[]={{1,0},{2,0},{12,1},{48,1}};
    Sr3CpuCore physical[64];DWORD_PTR available,system,chosen,observed,oldmask=0;
    unsigned count,i,n=0;
    CHECK(sr3_cpu_select(hybrid,6,1023,4)==0x55);
    CHECK(sr3_cpu_select(hybrid,6,1023,6)==0x355);
    CHECK(sr3_cpu_select(hybrid,6,1023,7)==0x357);
    CHECK(sr3_cpu_select(hybrid,6,1023,32)==1023);
    CHECK(sr3_cpu_select(hybrid,6,0xaa,4)==0xaa);
    CHECK(sr3_cpu_select(hybrid,6,0x0c,4)==0x0c);
    CHECK(sr3_cpu_select(hybrid,6,1023,0)==1023);
    CHECK(sr3_cpu_select(hybrid,6,0,4)==0);
    CHECK(sr3_cpu_select(unusual,4,255,4)==15);
    CHECK(sr3_cpu_select(reversed,4,63,2)==0x14);
    CHECK(sr3_cpu_select(NULL,0,0x92,2)==0x12);
    CHECK(sr3_cpu_physical_count(hybrid,6,15)==2);
    CHECK(sr3_cpu_physical_count(hybrid,6,0x55)==4);
    CHECK(GetProcessAffinityMask(GetCurrentProcess(),&available,&system));
    count=sr3_cpu_topology(physical,64);CHECK(count>0);
    chosen=sr3_cpu_select(physical,count,available,4);CHECK(chosen && !(chosen & ~available));
    for(i=0;i<sizeof(DWORD_PTR)*8 && n<4;i++)if(available & ((DWORD_PTR)1<<i)){oldmask|=(DWORD_PTR)1<<i;n++;}
    printf("Host topology: %u physical cores; old mask 0x%lx covers %u; new mask 0x%lx covers %u.\n",count,
        (unsigned long)oldmask,sr3_cpu_physical_count(physical,count,oldmask),
        (unsigned long)chosen,sr3_cpu_physical_count(physical,count,chosen));
    /* Affect this disposable fixture only, then restore its inherited mask. */
    CHECK(SetProcessAffinityMask(GetCurrentProcess(),chosen));
    CHECK(GetProcessAffinityMask(GetCurrentProcess(),&observed,&system));
    CHECK(observed==chosen);CHECK(SetProcessAffinityMask(GetCurrentProcess(),available));
    puts("CPU affinity: hybrid/SMT, sparse restrictions, nonadjacent siblings, zero/unlimited and native OS selection PASS.");
    return 0;
}
