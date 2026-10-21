/* The resource loader starts two native threads and joins them from its window
 * thread. Its progress helper can still be in SendMessage(WM_COPYDATA) when the
 * worker sets done. A plain infinite join then deadlocks sender and receiver.
 * Drain only synchronous sent messages while waiting for the real thread to
 * finish. Queued keyboard/mouse/game-state messages remain queued. The original
 * native join still obtains the exit code, closes the handle and clears it.
 * Install before the native startup loop; this is never a per-frame hook. */
#pragma once
#define LOADER_JOIN_SITE 0x5C6D3Fu
#define LOADER_NATIVE_JOIN 0x5877E0u
static const unsigned char loader_join_original[20] = {
    0xBE,0x5C,0x49,0x9C,0x00,0xE8,0x97,0x0A,0xFC,0xFF,
    0xBE,0x64,0x49,0x9C,0x00,0xE8,0x8D,0x0A,0xFC,0xFF
};
/* Guard the ESI-based ABI and the original successful completion/close path. */
static const unsigned char loader_native_join_original[71] = {
    0x51,0x8B,0x46,0x04,0x85,0xC0,0x75,0x11,0x68,0xAC,0x9B,0x6B,
    0x00,0xE8,0x3E,0xDF,0xE8,0xFF,0x83,0xC4,0x04,0x33,0xC0,0x59,
    0xC3,0x6A,0xFF,0x50,0xFF,0x15,0xC8,0x41,0x67,0x00,0x85,0xC0,
    0x75,0x21,0x8B,0x4E,0x04,0x8D,0x04,0x24,0x50,0x51,0xFF,0x15,
    0xC4,0x41,0x67,0x00,0x8B,0x56,0x04,0x52,0xFF,0x15,0x08,0x42,
    0x67,0x00,0xC7,0x46,0x04,0x00,0x00,0x00,0x00,0x59,0xC3
};
static DWORD loader_wait_for_thread(HANDLE thread) {
    DWORD result;
    if (!thread) return WAIT_FAILED;
    for (;;) {
        result = MsgWaitForMultipleObjectsEx(1, &thread, INFINITE,
                                            QS_SENDMESSAGE, MWMO_INPUTAVAILABLE);
        if (result != WAIT_OBJECT_0 + 1) return result;
        /* PeekMessage dispatches incoming sent messages internally. Restrict
           the queue category and do not remove/dispatch posted input. */
        { MSG message;
          PeekMessageA(&message, NULL, 0, 0, PM_NOREMOVE | PM_QS_SENDMESSAGE); }
    }
}
static __attribute__((used,noinline)) void loader_pump_before_join(const unsigned *group) {
    HANDLE thread = (HANDLE)(uintptr_t)group[1];
    if (thread) loader_wait_for_thread(thread);
}
/* Native callers pass a {thread id, handle} pair in ESI, not on the stack.
   Preserve their registers and tail-call the unchanged native join. */
static __attribute__((used,naked)) void loader_join_thunk(void) {
    __asm__ __volatile__(
        "pushal\n\t"
        "pushl %esi\n\t"
        "call _loader_pump_before_join\n\t"
        "addl $4, %esp\n\t"
        "popal\n\t"
        "pushl $0x5877e0\n\t"
        "ret\n\t");
}
static int loader_bytes_equal(const unsigned char *a, const unsigned char *b, unsigned n) {
    unsigned i; for (i=0;i<n;++i) if (a[i]!=b[i]) return 0;
    return 1;
}
/* 0 = refused/failed; 1 = installed; 2 = already installed. Both call sites
   are checked and written together while startup is still single-threaded. */
static int loader_install_message_wait(GameMem *m) {
    unsigned char actual[71], patch[20]; unsigned i, rel;
    if (!m->read(m, LOADER_NATIVE_JOIN, actual, sizeof actual) ||
        !loader_bytes_equal(actual, loader_native_join_original, sizeof actual)) return 0;
    for (i=0;i<20;++i) patch[i]=loader_join_original[i];
    for (i=5;i<20;i+=10) {
        rel=(unsigned)(uintptr_t)loader_join_thunk-(LOADER_JOIN_SITE+i+5);
        patch[i+1]=(unsigned char)rel; patch[i+2]=(unsigned char)(rel>>8);
        patch[i+3]=(unsigned char)(rel>>16); patch[i+4]=(unsigned char)(rel>>24);
    }
    if (!m->read(m, LOADER_JOIN_SITE, actual, 20)) return 0;
    if (loader_bytes_equal(actual, patch, 20)) return 2;
    if (!loader_bytes_equal(actual, loader_join_original, 20)) return 0;
    return m->write(m, LOADER_JOIN_SITE, patch, 20, 0) ? 1 : 0;
}
