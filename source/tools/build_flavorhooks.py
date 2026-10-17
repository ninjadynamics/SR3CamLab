"""Two position-independent routines for the launcher's handling flavors (put in memory like build_carlist.py's routine).
Layout of each blob: data first, then code, so no forward label arithmetic is needed.

1) CARPATH: per-car car-data path. 0x5C6144 `push 0x6C630C` (68 0C 63 6C 00: the format "\\main_release\\cars\\%s%s_data" of
   the race loader 0x5C5D30, run once per car of the race, ebp = the car's name) becomes `call <blob + ENTRY>` (E8 rel32).
   The routine compares ebp with the ten names the game itself uses (same strings and lengths as 0x5C6000, compare
   function 0x4AF410) and leaves on the stack, for a car whose flag is not 0, the blob's own format
   "\\main_release\\car1\\%s%s_data" (digit at DIGIT_AT, written by the launcher), else SEGA's 0x6C630C. eax, ecx, edx
   are free at that point (sprintf follows at 0x5C614E). Data: 10 x {u32 name, u32 length, u32 flag}, then a 0 terminator.
   All cars: every flag 1, or just the one-character switch at 0x6C631D ('s' -> digit) without this routine.
2) STEER: the player's steering as a turn rate (the owner, 2026-10-15: "replace those knobs with rad/s steering rate.
   let's try 1.5. 1:1 was a bad idea"; the steering return before it is gone). The human driver's update (0x5E9D20, driver
   vtable 0x6ED0C8) hands the steering to the vehicle in 0x5CFE90:  fld [esi+0x18] ; push ecx ; mov ecx, [esi+4] ; fstp [esp]
     0x5CFF32  E8 C9 8C E7 FF   call 0x448C00   (the vehicle's SetSteer: controls + 8 and the wheel angles)
   in every input mode. The call becomes `call <blob + ENTRY>`. Only the player's vehicle: ecx (the physics wrapper,
   controls + 4) must be [[0x9DBAC8 + 4] + 0x858], record 0's driver, a human driver (vtable 0x6ED0C8); every other caller
   (the Classic opponent runs this code too) passes unchanged, and so does the player while A = 0 (SEGA's own chain).
   With A > 0 the value handed on is  u x min(1, A / v + B x v):  u = the stick, (b1 - b0) / 255 from the pad's two steering
   bytes (driver + 0x1C84 / + 0x1C85), clamped to +-1; v = the car's speed in m/s, |vector| of the wrapper's vtable + 0x30
   (what 0x5E0B20 itself calls for its speed), at least 1. The value is a fraction of the full lock (wheel + 0x184), so with
   A = R x L / lock and B = R x K / lock (the launcher writes them: R the rate at full stick in rad/s, L the wheelbase, K the
   understeer term) the wheel angle at full stick is min(lock, R x (L + K v^2) / v): a steady turn of about R rad/s at full
   stick at any speed, linear in the stick. Data: +0 A (0 = off), +4 B, +8 1/255, +0xC 1.0, +0x10 -1.0, +0x14 1.0 (lowest
   speed), +0x18 the last speed and +0x1C the last full-stick fraction (for tests). ecx is kept; eax, edx, xmm0..2 are free.
    python build_flavorhooks.py      prints both blobs (hex) with their entry and data offsets"""
import struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
NAMES = [(0x6C6280, 2), (0x6C6284, 8), (0x6C6290, 5), (0x6C6298, 6), (0x6C62A0, 7), (0x6C62A8, 3), (0x6C62AC, 13), (0x6C62BC, 3), (0x6C62C0, 6), (0x6C62C8, 13)]
LABELS = ['C4', 'Delta_HF', 'ST205', 'Enduro', 'RSFocus', '207', 'SubaruImpreza', 'SX4', 'Bowler', 'MitsubishiEvo']
KS = Ks(KS_ARCH_X86, KS_MODE_32)
def asm(s): return bytes(KS.asm(s, 0)[0])

def carpath():
    data = bytearray()
    for a, n in NAMES: data += struct.pack('<III', a, n, 0)
    data += b'\0' * 4
    fmt_off = len(data); fmt = b'\\main_release\\car1\\%s%s_data\0'; data += fmt
    data += b'\0' * (-len(data) % 16); entry = len(data)
    here = entry + 7                                                     # push esi (1) + push edi (1) + call (5)
    code = asm("""
        push esi
        push edi
        call l1
    l1: pop edi
        lea esi, [edi - %d]
    nx: mov eax, dword ptr [esi]
        test eax, eax
        jz df
        push dword ptr [esi + 4]
        push eax
        push ebp
        mov eax, 0x4AF410
        call eax
        add esp, 12
        test eax, eax
        jnz sk
        mov al, byte ptr [esi + 8]
        test al, al
        jz df
        mov byte ptr [edi - %d], al
        lea eax, [edi - %d]
        jmp ot
    sk: add esi, 12
        jmp nx
    df: mov eax, 0x6C630C
    ot: pop edi
        pop esi
        xchg eax, dword ptr [esp]
        jmp eax
    """ % (here, here - (fmt_off + fmt.index(b'car1') + 3), here - fmt_off))
    return bytes(data) + code, entry, fmt_off + fmt.index(b'car1') + 3

def steer():
    data = struct.pack('<8f', 0.0, 0.0, 1 / 255.0, 1.0, -1.0, 1.0, 0.0, 0.0)
    entry = len(data); here = entry + 5                                   # call l2 (5 bytes): eax = blob + here
    d = lambda o: here - o
    code = asm("""
        call l2
    l2: pop eax
        mov edx, dword ptr [0x9DBACC]
        test edx, edx
        jz pass
        cmp dword ptr [edx], 0x6ED0C8
        jne pass
        cmp dword ptr [edx + 0x858], ecx
        jne pass
        movss xmm1, dword ptr [eax - %d]
        xorps xmm2, xmm2
        comiss xmm1, xmm2
        jbe pass
        push ecx
        push eax
        push edx
        mov eax, dword ptr [ecx]
        call dword ptr [eax + 0x30]
        movss xmm0, dword ptr [eax]
        mulss xmm0, xmm0
        movss xmm1, dword ptr [eax + 4]
        mulss xmm1, xmm1
        addss xmm0, xmm1
        movss xmm1, dword ptr [eax + 8]
        mulss xmm1, xmm1
        addss xmm0, xmm1
        sqrtss xmm0, xmm0
        pop edx
        pop eax
        pop ecx
        maxss xmm0, dword ptr [eax - %d]
        movss dword ptr [eax - %d], xmm0
        movss xmm1, dword ptr [eax - %d]
        divss xmm1, xmm0
        movss xmm2, dword ptr [eax - %d]
        mulss xmm2, xmm0
        addss xmm1, xmm2
        minss xmm1, dword ptr [eax - %d]
        movss dword ptr [eax - %d], xmm1
        push ecx
        movzx ecx, byte ptr [edx + 0x1C85]
        movzx edx, byte ptr [edx + 0x1C84]
        sub ecx, edx
        cvtsi2ss xmm0, ecx
        pop ecx
        mulss xmm0, dword ptr [eax - %d]
        minss xmm0, dword ptr [eax - %d]
        maxss xmm0, dword ptr [eax - %d]
        mulss xmm0, xmm1
        movss dword ptr [esp + 4], xmm0
    pass: mov eax, 0x448C00
        jmp eax
    """ % (d(0), d(0x14), d(0x18), d(0), d(4), d(0xC), d(0x1C), d(8), d(0xC), d(0x10)))
    return data + code, entry

if __name__ == '__main__':
    blob, entry, digit = carpath()
    print('CARPATH %d bytes: entry +0x%X; flag of car i at +0x%X + 12 x i = its folder digit (ASCII, 0 = SEGA files) (%s)' % (len(blob), entry, 8, ', '.join(LABELS)))
    print(blob.hex())
    s, e = steer()
    print('STEER %d bytes: entry +0x%X (called from 0x5CFF32 instead of 0x448C00); A at +0x0 (0 = the game value), B at +0x4' % (len(s), e))
    print(s.hex())
