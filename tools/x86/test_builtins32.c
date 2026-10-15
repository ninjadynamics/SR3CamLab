/* The 32-bit test program of tools/x86/test_builtins.py (which writes vectors.h and builds this with gcc -m32 -nostdlib,
 * builtins.o and implib.py's import library). Exit code 0 = every check passed; the failures are printed.
 *   arithmetic: every vector through the C operators (gcc's own calls to the helpers) and the helpers called directly
 *   stack:      frames of 4095 B to 3 MB, nested, in a thread whose stack is only reserved (one page committed), each
 *               frame touched at its lowest byte first: only a probe that walks every page down to it gets there
 *   registers:  ___chkstk_ms changes no register (EAX included) and not the stack pointer */
#include <windows.h>
#include "vectors.h"

typedef unsigned long long u64;
typedef long long s64;
extern u64 __udivmoddi4(u64, u64, u64 *);
extern u64 __udivdi3(u64, u64);
extern u64 __umoddi3(u64, u64);
extern s64 __divmoddi4(s64, s64, s64 *);
extern s64 __divdi3(s64, s64);
extern s64 __moddi3(s64, s64);
extern int __ctzdi2(u64), __clzdi2(u64), __popcountdi2(u64), __ffsdi2(s64), __paritydi2(u64);

static HANDLE out;
static int fails;
static void say(const char *s) { DWORD w; WriteFile(out, s, (DWORD)lstrlenA(s), &w, 0); }
static void hex(u64 v) {                            /* shifts only: no division in the code that checks division */
    char b[19]; int i; b[0] = '0'; b[1] = 'x';
    for (i = 0; i < 16; i++) b[2 + i] = "0123456789abcdef"[(v >> (60 - 4 * i)) & 15];
    b[18] = 0; say(b);
}
static void bad(const char *what, int i, u64 x, u64 y, u64 got, u64 want) {
    if (fails++ < 20) { say(what); say(" #"); hex((u64)i); say(" "); hex(x); say(" "); hex(y); say(" got "); hex(got); say(" want "); hex(want); say("\r\n"); }
}
#define CHECK(what, got, want) do { u64 g_ = (u64)(got), w_ = (u64)(want); if (g_ != w_) bad(what, i, x, y, g_, w_); } while (0)

static void arithmetic(void) {
    const volatile struct UV *u = UVEC; const volatile struct SV *s = SVEC; const volatile struct BV *c = BVEC; int i;
    for (i = 0; i < NU; i++) {
        u64 x = u[i].a, y = u[i].b, r;
        CHECK("u /", x / y, u[i].q); CHECK("u %", x % y, u[i].r);
        CHECK("udivdi3", __udivdi3(x, y), u[i].q); CHECK("umoddi3", __umoddi3(x, y), u[i].r);
        CHECK("udivmoddi4 q", __udivmoddi4(x, y, &r), u[i].q); CHECK("udivmoddi4 r", r, u[i].r);
    }
    for (i = 0; i < NS; i++) {
        s64 x = s[i].a, y = s[i].b, r;
        CHECK("s /", x / y, s[i].q); CHECK("s %", x % y, s[i].r);
        CHECK("divdi3", __divdi3(x, y), s[i].q); CHECK("moddi3", __moddi3(x, y), s[i].r);
        CHECK("divmoddi4 q", __divmoddi4(x, y, &r), s[i].q); CHECK("divmoddi4 r", r, s[i].r);
    }
    for (i = 0; i < NB; i++) {
        u64 x = c[i].x, y = 0;
        if (x) { CHECK("ctz", __ctzdi2(x), c[i].ctz); CHECK("clz", __clzdi2(x), c[i].clz); }
        CHECK("popcount", __popcountdi2(x), c[i].pop); CHECK("ffs", __ffsdi2((s64)x), c[i].ffs); CHECK("parity", __paritydi2(x), c[i].par);
    }
    { int i = -1; u64 x = 0, y = 0; CHECK("ctz(0)", __ctzdi2(0), 64); CHECK("clz(0)", __clzdi2(0), 64); }
}

/* Big frames: the lowest byte first (the one furthest below the caller), then the rest. */
#define FRAME(n) static int __attribute__((noinline)) f##n(int k) { volatile char a[n]; int j, t = 0; a[0] = (char)k; \
    for (j = 0; j < n; j += 4096) a[j] = (char)(j + k); a[n - 1] = 1; for (j = 0; j < n; j += 4096) t += a[j]; return t + a[n - 1]; }
FRAME(4095) FRAME(4096) FRAME(4097) FRAME(8191) FRAME(8192) FRAME(8193) FRAME(65553) FRAME(1048576) FRAME(3145728)
static int __attribute__((noinline)) nest(int d) { volatile char a[700000]; a[0] = (char)d; a[699999] = 2; return d ? nest(d - 1) + a[0] + a[699999] : a[0]; }
static DWORD WINAPI stack(LPVOID p) {
    (void)p;
    return (DWORD)(f4095(1) + f4096(2) + f4097(3) + f8191(4) + f8192(5) + f8193(6) + f65553(7) + f1048576(8) + f3145728(9) + nest(5));
}

/* ___chkstk_ms with every register set to a known value, then compared; the stack pointer too. */
unsigned int before[7], after[7];                  /* not static: the asm below names them (_before, _after) */
static void __attribute__((noinline)) registers(void) {
    __asm__ volatile(
        "pushal\n"
        "movl $0x11111111, %%ebx\n movl $0x22222222, %%ecx\n movl $0x33333333, %%edx\n"
        "movl $0x44444444, %%esi\n movl $0x55555555, %%edi\n movl $0x2345, %%eax\n"
        "movl %%ebx, _before+0\n movl %%ecx, _before+4\n movl %%edx, _before+8\n movl %%esi, _before+12\n"
        "movl %%edi, _before+16\n movl %%eax, _before+20\n movl %%esp, _before+24\n"
        "call ___chkstk_ms\n"
        "movl %%ebx, _after+0\n movl %%ecx, _after+4\n movl %%edx, _after+8\n movl %%esi, _after+12\n"
        "movl %%edi, _after+16\n movl %%eax, _after+20\n movl %%esp, _after+24\n"
        "popal\n" ::: "memory");
}

void __stdcall start(void) {
    HANDLE t; DWORD code = 0; int i;
    out = GetStdHandle(STD_OUTPUT_HANDLE);
#ifndef STACK_ONLY
    arithmetic();
    registers();
    for (i = 0; i < 7; i++) { u64 x = before[i], y = 0; CHECK("chkstk keeps the register", after[i], before[i]); }
#endif
    t = CreateThread(0, 8 << 20, stack, 0, STACK_SIZE_PARAM_IS_A_RESERVATION, 0);   /* 8 MB reserved, not committed */
    if (!t) { say("CreateThread failed\r\n"); ExitProcess(1000); }
    WaitForSingleObject(t, INFINITE); GetExitCodeThread(t, &code);
    { u64 x = 0, y = 0; i = 0; CHECK("stack frames' sum", code, EXPECT_STACK); }
    say(fails ? "FAILED\r\n" : "PASS\r\n");
    ExitProcess((UINT)fails);
}
