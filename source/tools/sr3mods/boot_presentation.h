/* Standalone state 9: suppress the cabinet-info screen completely.
 * State 4 still performs the real loader; state 9 keeps its original prologue
 * and shared update call (0x646CC0). Replace only the following 56-byte span:
 * reset the display text queue, retain the lazy network getter (0x404070), then
 * return the original machine/calibration choice (10 or 13) with the native
 * epilogue. No BeginScene, blue Clear, text draw, EndScene or Present executes.
 * The skipped network-info copies/IP strings are display temporaries only.
 * Install synchronously before WinMain's boot state loop, never from live code.
 * The earlier hold-only patch is no longer needed; its site is unreachable.
 * This does not modify the real loader, initial logo, or startup_gate.h. */
#pragma once
#define BOOT_INFO_ENTRY 0x649E50u
#define BOOT_INFO_BODY  0x649E64u
static const unsigned char boot_info_original[76] = {
    0x55,0x8B,0xEC,0x83,0xE4,0xF8,0x81,0xEC,0xDC,0x00,0x00,0x00,
    0x53,0x56,0x57,0xE8,0x5C,0xCE,0xFF,0xFF,0xA1,0xBC,0x23,0x81,
    0x00,0x8B,0xC8,0xC1,0xE9,0x08,0x83,0xE1,0x01,0x89,0x4C,0x24,
    0x24,0x75,0x0A,0x0D,0x01,0x01,0x00,0x00,0xA3,0xBC,0x23,0x81,
    0x00,0x8B,0xC8,0xC1,0xE9,0x07,0x83,0xE1,0x01,0x89,0x4C,0x24,
    0x1C,0x74,0x0D,0x25,0x7F,0xFF,0xFF,0xFF,0x83,0xC8,0x01,0xA3,
    0xBC,0x23,0x81,0x00
};
/* Assembly at 0x649E64:
 * mov [0x9EB598],0; call 0x404070;
 * if ([0x9EB888] == 0 && [0x9EB8B4] != 0) eax=10; else eax=13;
 * pop edi; pop esi; pop ebx; mov esp,ebp; pop ebp; ret; padding.
 * The original prologue and shared update call before this span stay intact. */
static const unsigned char boot_info_fast[56] = {
    0xC7,0x05,0x98,0xB5,0x9E,0x00,0x00,0x00,0x00,0x00,0xE8,0xFD,
    0xA1,0xDB,0xFF,0x83,0x3D,0x88,0xB8,0x9E,0x00,0x00,0x75,0x10,
    0x83,0x3D,0xB4,0xB8,0x9E,0x00,0x00,0x74,0x07,0xB8,0x0A,0x00,
    0x00,0x00,0xEB,0x05,0xB8,0x0D,0x00,0x00,0x00,0x5F,0x5E,0x5B,
    0x8B,0xE5,0x5D,0xC3,0x90,0x90,0x90,0x90
};
static int boot_bytes_equal(const unsigned char *a, const unsigned char *b, unsigned n) {
    unsigned i; for(i=0;i<n;++i) if(a[i]!=b[i]) return 0;
    return 1;
}
/* 0 = refused/failed; 1 = installed; 2 = already installed. */
static int startup_skip_info_screen(GameMem *m) {
    unsigned char actual[76];
    if (!m->read(m, BOOT_INFO_ENTRY, actual, sizeof actual)) return 0;
    if (!boot_bytes_equal(actual, boot_info_original, 20)) return 0;
    if (boot_bytes_equal(actual+20, boot_info_fast, sizeof boot_info_fast)) return 2;
    if (!boot_bytes_equal(actual+20, boot_info_original+20, sizeof boot_info_fast)) return 0;
    return m->write(m, BOOT_INFO_BODY, boot_info_fast, sizeof boot_info_fast, 0) ? 1 : 0;
}


/* State 10 still runs its real cabinet calibration poll (62DED0), records its
 * result (9C4398/9C439C), and chooses state 10 or 11 exactly as before. The only
 * callers of 63EE60 are its two presentation calls. Replace that helper with
 * its original display-frame counter increment and return: no blue rendering.
 * State 11 is only shared-update, blue presentation and a 120-update dwell.
 * Keep its shared-update call and return the same completed state13 immediately.
 * This does not fake hardware readiness or skip a pending calibration poll. */
#define BOOT_CAL_DRAW_ENTRY 0x63EE60u
#define BOOT_CAL_DONE_ENTRY 0x64AB40u
static const unsigned char boot_cal_draw_original[9] = {
    0xA1,0xB4,0x53,0xB4,0x00,0xA8,0x01,0x75,0x12
};
static const unsigned char boot_cal_draw_fast[9] = {
    0x83,0x05,0x4C,0x31,0xAE,0x00,0x01,0xC3,0x90
};
static const unsigned char boot_cal_done_original[31] = {
    0xE8,0x7B,0xC1,0xFF,0xFF,0xE8,0xC6,0x41,0xFF,0xFF,0x8B,0x4C,
    0x24,0x04,0xB8,0x78,0x00,0x00,0x00,0x3B,0x41,0x08,0x1B,0xC0,
    0x83,0xE0,0x02,0x83,0xC0,0x0B,0xC3
};
static const unsigned char boot_cal_done_fast[26] = {
    0xB8,0x0D,0x00,0x00,0x00,0xC3,0x90,0x90,0x90,0x90,0x90,0x90,
    0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,
    0x90,0x90
};
static int startup_skip_calibration_presentation(GameMem *m) {
    unsigned char draw[9],done[31]; int draw_ready,done_ready;
    if(!m->read(m,BOOT_CAL_DRAW_ENTRY,draw,sizeof draw) ||
       !m->read(m,BOOT_CAL_DONE_ENTRY,done,sizeof done) ||
       !boot_bytes_equal(done,boot_cal_done_original,5))return 0;
    draw_ready=boot_bytes_equal(draw,boot_cal_draw_fast,sizeof draw);
    done_ready=boot_bytes_equal(done+5,boot_cal_done_fast,sizeof boot_cal_done_fast);
    if((!draw_ready && !boot_bytes_equal(draw,boot_cal_draw_original,sizeof draw)) ||
       (!done_ready && !boot_bytes_equal(done,boot_cal_done_original,sizeof done)))return 0;
    if(draw_ready && done_ready)return 2;
    if(!draw_ready && !m->write(m,BOOT_CAL_DRAW_ENTRY,boot_cal_draw_fast,sizeof draw,0))return 0;
    if(!done_ready && !m->write(m,BOOT_CAL_DONE_ENTRY+5,boot_cal_done_fast,sizeof boot_cal_done_fast,0)) {
        if(!draw_ready)m->write(m,BOOT_CAL_DRAW_ENTRY,draw,sizeof draw,0);
        return 0;
    }
    return 1;
}
