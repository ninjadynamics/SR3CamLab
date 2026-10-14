"""Two position-independent routines for the launcher's handling flavors (put in memory like build_carlist.py's routine).
Layout of each blob: data first, then code, so no forward label arithmetic is needed.

1) CARPATH: per-car car-data path. 0x5C6144 `push 0x6C630C` (68 0C 63 6C 00: the format "\\main_release\\cars\\%s%s_data" of
   the race loader 0x5C5D30, run once per car of the race, ebp = the car's name) becomes `call <blob + ENTRY>` (E8 rel32).
   The routine compares ebp with the ten names the game itself uses (same strings and lengths as 0x5C6000, compare
   function 0x4AF410) and leaves on the stack, for a car whose flag is not 0, the blob's own format
   "\\main_release\\car1\\%s%s_data" (digit at DIGIT_AT, written by the launcher), else SEGA's 0x6C630C. eax, ecx, edx
   are free at that point (sprintf follows at 0x5C614E). Data: 10 x {u32 name, u32 length, u32 flag}, then a 0 terminator.
   All cars: every flag 1, or just the one-character switch at 0x6C631D ('s' -> digit) without this routine.
2) STEER: steering return for the player. The human driver's update (0x5E9D20, driver vtable 0x6ED0C8) hands the
   steering to the vehicle in 0x5CFE90:  fld [esi+0x18] ; push ecx ; mov ecx, [esi+4] ; fstp [esp] ;
     0x5CFF32  E8 C9 8C E7 FF   call 0x448C00   (the vehicle's SetSteer: controls + 8 and the wheel angles)
   in every input mode (mode 1, the TeknoParrot pad, gets its value from 0x5E0B20, not 0x5D4D10: a hook on 0x5D4D10's
   exits never ran, in game 2026-10-14). The call becomes `call <blob + ENTRY>`. Only the player's vehicle is limited:
   ecx (the physics wrapper, controls + 4) must be [[0x9DBAC8 + 4] + 0x858], record 0's driver, a human driver (vtable
   0x6ED0C8); every other caller (the Classic opponent runs this code too) passes unchanged. The routine takes s at
   [esp+4], keeps the player's last output o, passes s at once when it lies farther from the centre on the same side
   (pressing stays instant), else moves o toward s by at most RATE per call, and hands the result to the vehicle only:
   controls + 0x18 stays the game's own raw value (mode 1's 0x5E0B20 builds its next value from it, so writing it back
   held the steering, in game 2026-10-14). ecx is untouched; eax, edx and xmm0..5 are free there.
   RATE = 1 / (return seconds x 60): full lock to centre in that time; 0 = off (SEGA's behaviour).
   LINEAR (float at +8, 2026-10-14; the owner: "the wheels tracking the analog pad 1:1 (as much as possible) just like
   SRC"): when above 0 the player's value is made from the stick itself, s = clamp((b1 - b0) x LINEAR, -1, 1) with the
   pad's two steering bytes at driver + 0x1C84 / + 0x1C85 (0..255 each, left / right, linear in the stick: 0.25 -> 63,
   0.5 -> 127, 1.0 -> 253..255, in game), instead of SEGA's 0x5E0B20 value (b1 - b0) / 300 x lock (0.8 .. 0.6 with
   speed) x the car's speed table (1.5 at rest .. 0.5 from 110 mph), which leaves a full stick a quarter of the lock at
   180 km/h. LINEAR = 1/255: full stick = full lock (wheel + 0x184, 0.345 rad) at every speed. 0 = SEGA's value. The
   return limit then works on that value as before. Constants 1.0 / -1.0 at +0xC / +0x10.
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
    data = struct.pack('<fffff', 0.0, 0.0, 0.0, 1.0, -1.0)                # RATE +0, last output +4, LINEAR +8, 1.0, -1.0
    entry = len(data); here = entry + 5                                   # call l2 (5 bytes)
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
        movss xmm0, dword ptr [esp + 4]
        movss xmm1, dword ptr [eax - %d]
        xorps xmm2, xmm2
        comiss xmm1, xmm2
        jbe nolin
        push ecx
        movzx ecx, byte ptr [edx + 0x1C85]
        movzx edx, byte ptr [edx + 0x1C84]
        sub ecx, edx
        cvtsi2ss xmm0, ecx
        pop ecx
        mulss xmm0, xmm1
        minss xmm0, dword ptr [eax - %d]
        maxss xmm0, dword ptr [eax - %d]
    nolin:
        movss xmm1, dword ptr [eax - %d]
        xorps xmm2, xmm2
        comiss xmm1, xmm2
        jbe sto
        movss xmm3, dword ptr [eax - %d]
        movaps xmm4, xmm0
        mulss xmm4, xmm3
        comiss xmm4, xmm2
        jb lm
        movaps xmm4, xmm0
        mulss xmm4, xmm0
        movaps xmm5, xmm3
        mulss xmm5, xmm3
        comiss xmm4, xmm5
        jae sto
    lm: movaps xmm4, xmm0
        subss xmm4, xmm3
        minss xmm4, xmm1
        xorps xmm5, xmm5
        subss xmm5, xmm1
        maxss xmm4, xmm5
        addss xmm3, xmm4
        movaps xmm0, xmm3
    sto: movss dword ptr [eax - %d], xmm0
        movss dword ptr [esp + 4], xmm0
    pass: mov eax, 0x448C00
        jmp eax
    """ % (here - 8, here - 0xC, here - 0x10, here - 0, here - 4, here - 4))
    return data + code, entry

if __name__ == '__main__':
    blob, entry, digit = carpath()
    print('CARPATH %d bytes: entry +0x%X; flag of car i at +0x%X + 12 x i = its folder digit (ASCII, 0 = SEGA files) (%s)' % (len(blob), entry, 8, ', '.join(LABELS)))
    print(blob.hex())
    s, e = steer()
    print('STEER %d bytes: entry +0x%X (called from 0x5CFF32 instead of 0x448C00); RATE float at +0x0 (0 = off), last output at +0x4, LINEAR at +0x8 (0 = the game value)' % (len(s), e))
    print(s.hex())
