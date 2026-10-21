#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "patchcore.h"
#include "boot_presentation.h"
static unsigned char bytes[76],cal_draw[9],cal_done[31];
static unsigned writes, read_fail, write_fail;
static int read_mock(GameMem *m, unsigned va, void *dst, unsigned n) {
    unsigned i; (void)m;
    const unsigned char *src=0;
    if(read_fail)return 0;
    if(va==BOOT_INFO_ENTRY && n==76)src=bytes;
    if(va==BOOT_CAL_DRAW_ENTRY && n==9)src=cal_draw;
    if(va==BOOT_CAL_DONE_ENTRY && n==31)src=cal_done;
    if(!src)return 0;
    for(i=0;i<n;++i) ((unsigned char *)dst)[i]=src[i];
    return 1;
}
static int write_mock(GameMem *m, unsigned va, const void *src, unsigned n, int keep) {
    unsigned i; (void)m; ++writes;
    /* Do not permit widening into the prologue/shared update or other code. */
    unsigned char *dst=0;
    if(keep || write_fail==1 || (write_fail==2 && va==BOOT_CAL_DONE_ENTRY+5))return 0;
    if(va==BOOT_INFO_BODY && n==56)dst=bytes+20;
    if(va==BOOT_CAL_DRAW_ENTRY && n==9)dst=cal_draw;
    if(va==BOOT_CAL_DONE_ENTRY+5 && n==26)dst=cal_done+5;
    if(!dst)return 0;
    for(i=0;i<n;++i) dst[i]=((const unsigned char *)src)[i];
    return 1;
}
static GameMem memory = {read_mock,write_mock};
static void reset(void) {
    unsigned i; for(i=0;i<76;++i) bytes[i]=boot_info_original[i];
    for(i=0;i<9;++i)cal_draw[i]=boot_cal_draw_original[i];
    for(i=0;i<31;++i)cal_done[i]=boot_cal_done_original[i];
    writes=read_fail=write_fail=0;
}
#define CHECK(condition, code) do { if (!(condition)) ExitProcess(code); } while(0)
void boot_test_entry(void) {
    unsigned i;
    reset(); CHECK(startup_skip_info_screen(&memory)==1 && writes==1,1);
    CHECK(boot_bytes_equal(bytes,boot_info_original,20),2);
    CHECK(boot_bytes_equal(bytes+20,boot_info_fast,56),3);
    CHECK(startup_skip_info_screen(&memory)==2 && writes==1,4);
    reset(); read_fail=1; CHECK(!startup_skip_info_screen(&memory) && writes==0,5);
    reset(); write_fail=1; CHECK(!startup_skip_info_screen(&memory) && writes==1,6);
    CHECK(boot_bytes_equal(bytes,boot_info_original,76),7);
    for(i=0;i<76;++i) {
        reset(); bytes[i]^=1;
        CHECK(!startup_skip_info_screen(&memory) && writes==0,10+i);
    }
    /* A partial body patch must not be accepted as a completed installation. */
    reset(); bytes[20]=boot_info_fast[0];
    CHECK(!startup_skip_info_screen(&memory) && writes==0,90);
    /* Even an intact patched body is rejected if the original update changed. */
    reset(); CHECK(startup_skip_info_screen(&memory)==1,91);
    bytes[15]^=1;
    CHECK(!startup_skip_info_screen(&memory) && writes==1,92);
    reset(); CHECK(startup_skip_calibration_presentation(&memory)==1 && writes==2,100);
    CHECK(boot_bytes_equal(cal_draw,boot_cal_draw_fast,9),101);
    CHECK(boot_bytes_equal(cal_done,boot_cal_done_original,5),102);
    CHECK(boot_bytes_equal(cal_done+5,boot_cal_done_fast,26),103);
    CHECK(startup_skip_calibration_presentation(&memory)==2 && writes==2,104);
    reset();read_fail=1;CHECK(!startup_skip_calibration_presentation(&memory) && !writes,105);
    reset();write_fail=1;CHECK(!startup_skip_calibration_presentation(&memory) && writes==1,106);
    reset();write_fail=2;CHECK(!startup_skip_calibration_presentation(&memory) && writes==3,107);
    CHECK(boot_bytes_equal(cal_draw,boot_cal_draw_original,9) && boot_bytes_equal(cal_done,boot_cal_done_original,31),108);
    for(i=0;i<9;++i){reset();cal_draw[i]^=1;CHECK(!startup_skip_calibration_presentation(&memory) && !writes,110+i);}
    for(i=0;i<31;++i){reset();cal_done[i]^=1;CHECK(!startup_skip_calibration_presentation(&memory) && !writes,125+i);}
    /* Mixed exact original/installed sites can finish installation safely. */
    reset();for(i=0;i<9;++i)cal_draw[i]=boot_cal_draw_fast[i];
    CHECK(startup_skip_calibration_presentation(&memory)==1 && writes==1,160);
    ExitProcess(0);
}
