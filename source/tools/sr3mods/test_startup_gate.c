#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "patchcore.h"
#include "startup_gate.h"
static unsigned handles[18], graphs[20], controls[20], fail_address, boot_busy, boot_reads, busy_on_recheck;
static int read_mock(GameMem *m, unsigned va, void *dst, unsigned n) {
    unsigned i; (void)m;
    if (n != 4 || va == fail_address) return 0;
    if (va == 0x9D6F7Cu) { *(unsigned *)dst=boot_busy || (busy_on_recheck && ++boot_reads>1); return 1; }
    for (i=0;i<18;++i) if(va==0x72863Cu+i*16) { *(unsigned *)dst=handles[i]; return 1; }
    for (i=0;i<20;++i) {
        if(va==0xAD2F90u+i*0x16C+0x11C) { *(unsigned *)dst=graphs[i]; return 1; }
        if(va==0xAD2F90u+i*0x16C+0x120) { *(unsigned *)dst=controls[i]; return 1; }
    }
    return 0;
}
static GameMem memory = {read_mock};
#define CHECK(condition, code) do { if (!(condition)) ExitProcess(code); } while(0)
void gate_entry(void) {
    unsigned i;
    CHECK(!startup_videos_ready(&memory), 1); /* zeroed table is not ready */
    for(i=0;i<18;++i) handles[i]=~0u;
    CHECK(!startup_videos_ready(&memory), 2);
    for(i=0;i<18;++i) { handles[i]=i; graphs[i]=controls[i]=0x1000+i*4; }
    handles[17]=~0u; CHECK(!startup_videos_ready(&memory), 3); /* partial native load */
    handles[17]=17; CHECK(startup_videos_ready(&memory), 4);
    graphs[17]=0; CHECK(!startup_videos_ready(&memory), 5); graphs[17]=1;
    controls[17]=0; CHECK(!startup_videos_ready(&memory), 6); controls[17]=1;
    handles[17]=20; CHECK(!startup_videos_ready(&memory), 7);
    handles[17]=0; CHECK(!startup_videos_ready(&memory), 8); handles[17]=17;
    fail_address=0x72863C; CHECK(!startup_videos_ready(&memory), 9);
    fail_address=0xAD2F90+0x120; CHECK(!startup_videos_ready(&memory), 10);
    fail_address=0; CHECK(startup_videos_ready(&memory), 11);
    boot_busy=1; CHECK(!startup_videos_ready(&memory), 12);
    boot_busy=0; CHECK(startup_videos_ready(&memory), 13);
    fail_address=0x9D6F7C; CHECK(!startup_videos_ready(&memory), 14); fail_address=0;
    boot_reads=0; busy_on_recheck=1; CHECK(!startup_videos_ready(&memory), 15);
    busy_on_recheck=0; CHECK(startup_videos_ready(&memory), 16);
    ExitProcess(0);
}
