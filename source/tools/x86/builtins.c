/* The helpers 32-bit code built by gcc -m32 -nostdlib calls, in place of libgcc (which our 64-bit gcc has no 32-bit
 * copy of). Each one is what gcc's own output asks for (nm on gcc -m32 objects, SDL3's included):
 *   ___udivdi3 ___umoddi3 ___udivmoddi4 ___divdi3 ___moddi3 ___divmoddi4   64-bit divide and remainder
 *   ___ctzdi2 ___clzdi2 ___popcountdi2 ___ffsdi2 ___paritydi2              64-bit bit counts (no POPCNT assumed)
 *   ___chkstk_ms                                                           the stack probe for frames over 4 KB
 * Semantics as libgcc's: quotients truncate toward zero, a remainder has the dividend's sign, INT64_MIN / -1 wraps to
 * INT64_MIN, a zero divisor faults like the hardware division does. Tests: tools/x86/test_builtins.py.
 * Build: gcc -m32 -O2 -c builtins.c (nothing here may need a 64-bit divide or POPCNT itself, or it would call itself). */
typedef unsigned int u32;
typedef unsigned long long u64;
typedef long long s64;

/* (hi:lo) / d with the CPU's 64-by-32 divide; needs hi < d, which every caller below guarantees. */
static inline u32 div64by32(u32 hi, u32 lo, u32 d, u32 *rem) {
    u32 q, r;
    __asm__("divl %4" : "=a"(q), "=d"(r) : "a"(lo), "d"(hi), "rm"(d) : "cc");
    *rem = r; return q;
}

u64 __udivmoddi4(u64 n, u64 d, u64 *rem) {
    u32 dh = (u32)(d >> 32);
    if (!dh) {                                       /* a 32-bit divisor: two hardware divides, exact */
        u32 dl = (u32)d, nh = (u32)(n >> 32), r, qh, ql;
        qh = div64by32(0, nh, dl, &r);              /* (a zero divisor faults here, as a hardware divide does) */
        ql = div64by32(r, (u32)n, dl, &r);
        if (rem) *rem = r;
        return (u64)qh << 32 | ql;
    }
    /* A divisor of 2^32 or more: the quotient fits in 32 bits. Normalise the divisor so its top bit is set, divide
       n/2 by its top 32 bits (no overflow: n/2 < 2^63 and that top word is >= 2^31), undo both shifts; the estimate is
       then the quotient or one above it, and one correction step fixes it (Hacker's Delight, 9-5). */
    {
        int s = __builtin_clz(dh);                   /* 0..31, a plain BSR */
        u32 v1 = (u32)((d << s) >> 32), r;
        u64 n1 = n >> 1, q;
        q = div64by32((u32)(n1 >> 32), (u32)n1, v1, &r);
        q = (q << s) >> 31;
        if (q) q--;
        if (n - q * d >= d) q++;
        if (rem) *rem = n - q * d;
        return q;
    }
}
u64 __udivdi3(u64 n, u64 d) { return __udivmoddi4(n, d, 0); }
u64 __umoddi3(u64 n, u64 d) { u64 r; __udivmoddi4(n, d, &r); return r; }

/* Signed: divide the magnitudes (0 - (u64)x is right for INT64_MIN too), then put the signs back. */
s64 __divmoddi4(s64 a, s64 b, s64 *rem) {
    u64 ua = a < 0 ? 0 - (u64)a : (u64)a, ub = b < 0 ? 0 - (u64)b : (u64)b, r, q = __udivmoddi4(ua, ub, &r);
    if (rem) *rem = (s64)(a < 0 ? 0 - r : r);
    return (s64)((a < 0) != (b < 0) ? 0 - q : q);
}
s64 __divdi3(s64 a, s64 b) { return __divmoddi4(a, b, 0); }
s64 __moddi3(s64 a, s64 b) { s64 r; __divmoddi4(a, b, &r); return r; }

/* Bit counts. Only 32-bit BSF / BSR (always inline) and shifts: never the 64-bit builtins, which would call these. */
static inline int pop32(u32 x) {
    x = x - ((x >> 1) & 0x55555555u);
    x = (x & 0x33333333u) + ((x >> 2) & 0x33333333u);
    x = (x + (x >> 4)) & 0x0f0f0f0fu;
    return (int)((x * 0x01010101u) >> 24);
}
int __ctzdi2(u64 x) { u32 lo = (u32)x, hi = (u32)(x >> 32); return lo ? __builtin_ctz(lo) : hi ? 32 + __builtin_ctz(hi) : 64; }
int __clzdi2(u64 x) { u32 lo = (u32)x, hi = (u32)(x >> 32); return hi ? __builtin_clz(hi) : lo ? 32 + __builtin_clz(lo) : 64; }
int __popcountdi2(u64 x) { return pop32((u32)x) + pop32((u32)(x >> 32)); }
int __ffsdi2(s64 x) { return x ? __ctzdi2((u64)x) + 1 : 0; }
int __paritydi2(u64 x) { return __popcountdi2(x) & 1; }

/* ___chkstk_ms: gcc calls it before taking EAX bytes off the stack for a frame over 4 KB, and subtracts them itself
 * afterwards. It touches one byte in every 4 KB page from the caller's stack pointer down, top first, so that each
 * touch lands on the guard page Windows moves down as the stack grows. It changes no register but the flags (EAX
 * included: the caller uses it next). */
__asm__(
    "    .text\n"
    "    .globl ___chkstk_ms\n"
    "    .def ___chkstk_ms; .scl 2; .type 32; .endef\n"
    "___chkstk_ms:\n"
    "    pushl %ecx\n"
    "    pushl %eax\n"
    "    leal 12(%esp), %ecx\n"                    /* the caller's stack pointer: above our two pushes and the return */
    "1:  cmpl $0x1000, %eax\n"
    "    jb 2f\n"
    "    subl $0x1000, %ecx\n"                      /* a whole page further down: touch it */
    "    orl $0, (%ecx)\n"
    "    subl $0x1000, %eax\n"
    "    jmp 1b\n"
    "2:  subl %eax, %ecx\n"                         /* the rest, less than a page */
    "    orl $0, (%ecx)\n"
    "    popl %eax\n"
    "    popl %ecx\n"
    "    ret\n");
