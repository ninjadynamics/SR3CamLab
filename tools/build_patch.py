"""Builds the chase camera patch (the code cave at 0x673C80 and the hooks) and writes patch.json.
patch.ps1's $Patches table holds these bytes (the cave tunables are filled in per profile).
Needs keystone-engine and capstone; set SR3_EXE (see sr3.py)."""
import struct, json, hashlib, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from sr3 import data, off, dis, md

ks = Ks(KS_ARCH_X86, KS_MODE_32)
CAVE = 0x673C80
# ---- tunable constant block (offsets are fixed; the toggle script rewrites the values) ----
C = dict(MAGIC=CAVE+0x00, STRENGTH=CAVE+0x08, VMIN=CAVE+0x0C, VINV=CAVE+0x10, SLIP=CAVE+0x14,
         KMIN=CAVE+0x18, KMAX=CAVE+0x1C, DAMP=CAVE+0x20, ZERO=CAVE+0x24, ONE=CAVE+0x28,
         EPS=CAVE+0x2C, SPDEPS=CAVE+0x30,
         CANARY=CAVE+0x34, CALLS=CAVE+0x38, APPLIED=CAVE+0x3C,   # diagnostics (cave page kept writable)
         DELTA=CAVE+0x40, TAX=CAVE+0x44, TAZ=CAVE+0x48, DOT=CAVE+0x4C,  # runtime scratch
         MULT=CAVE+0x50,                                           # replaces the x7.5 stiffness multiplier
         KNEE=CAVE+0x54, RANGE=CAVE+0x58, INVRANGE=CAVE+0x5C,       # soft angle limit (radians, tunable)
         ABSMASK=CAVE+0x60, SIGNMASK=CAVE+0x64,
         FRAMING=CAVE+0x68, DIST=CAVE+0x6C, HEIGHT=CAVE+0x70, FOV=CAVE+0x74,   # framing override (tunable; FRAMING=0 keeps SR3's own)
         FARD=CAVE+0x78, FARH=CAVE+0x7C,                                       # far chase view keeps its 1.25/1.15 factors
         DBG_DIST=CAVE+0x80, DBG_HEIGHT=CAVE+0x84, DBG_FOV=CAVE+0x88)         # SR3's own framing, recorded each frame
consts = struct.pack('<4sI', b'SR3C', 1) + struct.pack('<11f',
         0.70,        # STRENGTH : 0 = original (follow heading), 1 = follow direction of travel
         4.0,         # VMIN     : m/s where the effect starts fading in
         1/8.0,       # VINV     : 1/(fade range) -> full effect at 12 m/s (~43 km/h)
         2.0,         # SLIP     : effect fades out between 60 and 90 deg of slip (spins/reversing)
         18.0,        # KMIN     : spring stiffness (orig 15)
         30.0,        # KMAX     : spring stiffness (orig 90)
         -9.0,        # DAMP     : angular damping (orig -15)
         0.0, 1.0, 1e-4, 0.5)
assert len(consts) == 0x34
HOOK = CAVE + 0x90
NORMALIZE = 0x401E00
asm_hook = f"""
    inc dword ptr [{C['CALLS']:#x}]
    push dword ptr [esp+8]
    push dword ptr [esp+8]
    call {NORMALIZE:#x}
    add esp, 8
    mov eax, dword ptr [esp+4]
    movss xmm0, dword ptr [eax]
    movss dword ptr [{C['TAX']:#x}], xmm0
    movss xmm0, dword ptr [eax+8]
    movss dword ptr [{C['TAZ']:#x}], xmm0
    movss xmm0, dword ptr [esp+0x30]
    movss xmm1, dword ptr [esp+0x38]
    movaps xmm2, xmm0
    mulss xmm2, xmm0
    movaps xmm3, xmm1
    mulss xmm3, xmm1
    addss xmm2, xmm3
    sqrtss xmm2, xmm2
    comiss xmm2, dword ptr [{C['SPDEPS']:#x}]
    jbe done
    movaps xmm3, xmm2
    subss xmm3, dword ptr [{C['VMIN']:#x}]
    mulss xmm3, dword ptr [{C['VINV']:#x}]
    maxss xmm3, dword ptr [{C['ZERO']:#x}]
    minss xmm3, dword ptr [{C['ONE']:#x}]
    divss xmm0, xmm2
    divss xmm1, xmm2
    movss xmm4, dword ptr [eax]
    movss xmm5, dword ptr [eax+8]
    movaps xmm6, xmm4
    mulss xmm6, xmm0
    movaps xmm7, xmm5
    mulss xmm7, xmm1
    addss xmm6, xmm7
    mulss xmm6, dword ptr [{C['SLIP']:#x}]
    maxss xmm6, dword ptr [{C['ZERO']:#x}]
    minss xmm6, dword ptr [{C['ONE']:#x}]
    mulss xmm3, xmm6
    mulss xmm3, dword ptr [{C['STRENGTH']:#x}]
    subss xmm0, xmm4
    mulss xmm0, xmm3
    addss xmm0, xmm4
    subss xmm1, xmm5
    mulss xmm1, xmm3
    addss xmm1, xmm5
    movaps xmm2, xmm0
    mulss xmm2, xmm0
    movaps xmm3, xmm1
    mulss xmm3, xmm1
    addss xmm2, xmm3
    sqrtss xmm2, xmm2
    comiss xmm2, dword ptr [{C['EPS']:#x}]
    jbe done
    divss xmm0, xmm2
    divss xmm1, xmm2
    movss dword ptr [eax], xmm0
    movss dword ptr [eax+8], xmm1
    inc dword ptr [{C['APPLIED']:#x}]
done:
    cmp dword ptr [{C['CANARY']:#x}], 0
    je out
    mov eax, dword ptr [esp+4]
    movss xmm0, dword ptr [eax]
    movss xmm1, dword ptr [eax+8]
    xorps xmm2, xmm2
    subss xmm2, xmm1
    movss dword ptr [eax], xmm2
    movss dword ptr [eax+8], xmm0
out:
    mov eax, dword ptr [esp+4]
    movss xmm0, dword ptr [eax]
    mulss xmm0, dword ptr [{C['TAZ']:#x}]
    movss xmm1, dword ptr [eax+8]
    mulss xmm1, dword ptr [{C['TAX']:#x}]
    subss xmm0, xmm1
    movss dword ptr [{C['DELTA']:#x}], xmm0
    movss xmm0, dword ptr [eax]
    mulss xmm0, dword ptr [{C['TAX']:#x}]
    movss xmm1, dword ptr [eax+8]
    mulss xmm1, dword ptr [{C['TAZ']:#x}]
    addss xmm0, xmm1
    movss dword ptr [{C['DOT']:#x}], xmm0
    fld dword ptr [{C['DELTA']:#x}]
    fld dword ptr [{C['DOT']:#x}]
    fpatan
    fstp dword ptr [{C['DELTA']:#x}]
    ret
"""
hook, _ = ks.asm(asm_hook, HOOK); hook = bytes(hook)
GET_KMAX = HOOK + ((len(hook) + 15) & ~15)
g1, _ = ks.asm(f"fld dword ptr [{C['KMAX']:#x}]; ret", GET_KMAX); g1 = bytes(g1)
GET_KMIN = GET_KMAX + 0x10
g2, _ = ks.asm(f"fld dword ptr [{C['KMIN']:#x}]; ret", GET_KMIN); g2 = bytes(g2)
cave = bytearray((consts.ljust(0x50, b'\0') + struct.pack('<4f', 1.0, 3.14, 1e-4, 1e4) + struct.pack('<2I', 0x7FFFFFFF, 0x80000000)
                   + struct.pack('<I3f', 0, 7.0, 2.3, 60.0) + struct.pack('<2f', 1.25, 1.15)).ljust(0x90, b'\0')) + hook
cave = cave.ljust(GET_KMAX - CAVE, b'\xcc') + g1
cave = cave.ljust(GET_KMIN - CAVE, b'\xcc') + g2
EYEWRAP = GET_KMIN + 0x10
ew, _ = ks.asm(f"""
    movss xmm0, dword ptr [esp+8]
    movss dword ptr [{C['DBG_DIST']:#x}], xmm0
    movss xmm0, dword ptr [esp+0xc]
    movss dword ptr [{C['DBG_HEIGHT']:#x}], xmm0
    movss xmm0, dword ptr [ecx+0x3b0]
    movss dword ptr [{C['DBG_FOV']:#x}], xmm0
    cmp dword ptr [{C['FRAMING']:#x}], 0
    je angle
    movss xmm1, dword ptr [{C['ONE']:#x}]
    movss xmm2, dword ptr [{C['ONE']:#x}]
    cmp dword ptr [ecx], 0x6eb8b8
    jne nearcam
    movss xmm1, dword ptr [{C['FARD']:#x}]
    movss xmm2, dword ptr [{C['FARH']:#x}]
nearcam:
    movss xmm0, dword ptr [{C['DIST']:#x}]
    mulss xmm0, xmm1
    addss xmm0, dword ptr [ecx+0x30]
    movss dword ptr [esp+8], xmm0
    movss xmm0, dword ptr [{C['HEIGHT']:#x}]
    mulss xmm0, xmm2
    movss dword ptr [esp+0xc], xmm0
    movss xmm0, dword ptr [{C['FOV']:#x}]
    movss dword ptr [ecx+0x3b0], xmm0
angle:
    movss xmm0, dword ptr [esp+4]
    addss xmm0, dword ptr [{C['DELTA']:#x}]
    ucomiss xmm0, xmm0
    jnp notnan
    xorps xmm0, xmm0
notnan:
    movss xmm2, dword ptr [{C['ABSMASK']:#x}]
    movaps xmm1, xmm0
    andps xmm1, xmm2
    movss xmm3, dword ptr [{C['SIGNMASK']:#x}]
    andps xmm3, xmm0
    comiss xmm1, dword ptr [{C['KNEE']:#x}]
    jbe store
    subss xmm1, dword ptr [{C['KNEE']:#x}]
    mulss xmm1, dword ptr [{C['INVRANGE']:#x}]
    movaps xmm4, xmm1
    mulss xmm4, xmm1
    addss xmm4, dword ptr [{C['ONE']:#x}]
    sqrtss xmm4, xmm4
    divss xmm1, xmm4
    mulss xmm1, dword ptr [{C['RANGE']:#x}]
    addss xmm1, dword ptr [{C['KNEE']:#x}]
    orps xmm1, xmm3
    movaps xmm0, xmm1
store:
    movss dword ptr [esp+4], xmm0
    jmp 0x5f2600""", EYEWRAP)
cave = cave.ljust(EYEWRAP - CAVE, b'\xcc') + bytes(ew)
cave = bytes(cave)
assert CAVE + len(cave) <= 0x674000

patches = []  # (file_offset, original, new, description)
def P(va_or_off, new, desc, is_off=False):
    o = va_or_off if is_off else off(va_or_off)
    orig = data[o:o+len(new)]
    patches.append((o, orig, new, desc))

# 1) .text VirtualSize 0x272C80 -> 0x273000 so the cave (already in the file) is guaranteed mapped.
#    Only for an on-disk patch (abandoned: TeknoParrot rejects a modified Rally.exe); patch.ps1 skips it,
#    the cave is mapped in memory anyway because pages are 4 KB.
pe = struct.unpack_from('<I', data, 0x3C)[0]
sec0 = pe + 4 + 20 + struct.unpack_from('<H', data, pe + 4 + 16)[0]
assert data[sec0:sec0+5] == b'.text'
P(sec0 + 8, struct.pack('<I', 0x273000), ".text VirtualSize (map the code cave)", True)
# 2) cave contents
P(CAVE, cave, "code cave: tuning constants + hook + stiffness getters")
# 3) redirect chase-cam's normalize call to our hook
CALLSITE = 0x5F72DD
assert data[off(CALLSITE)] == 0xE8
P(CALLSITE, b'\xE8' + struct.pack('<i', HOOK - (CALLSITE + 5)), "chase cam: target-direction hook")
# 3b) eye placement: add our heading offset to the angle passed to the eye-offset helper
EYECALL = 0x5F7E29
assert data[off(EYECALL)] == 0xE8 and EYECALL + 5 + struct.unpack('<i', data[off(EYECALL)+1:off(EYECALL)+5])[0] == 0x5F2600
P(EYECALL, b'\xE8' + struct.pack('<i', EYEWRAP - (EYECALL + 5)), "chase cam: eye placement uses bent heading")
# 3c) the x7.5 stiffness multiplier -> our MULT (1.0)
assert data[off(0x5F7249):off(0x5F7249)+4] == bytes.fromhex('f30f100d')
P(0x5F724D, struct.pack('<I', C['MULT']), "chase cam: stiffness multiplier x7.5 -> cave (1.0)")
# 4) damping constant operand
assert data[off(0x5F76AC):off(0x5F76AC)+4] == bytes.fromhex('f30f5905')
P(0x5F76B0, struct.pack('<I', C['DAMP']), "chase cam: damping constant -> cave")
# 5) stiffness getters in both chase-cam vtables (normal + far)
for vt in (0x6EB808, 0x6EB8B8):
    assert struct.unpack('<I', data[off(vt+0xA0):off(vt+0xA0)+4])[0] == 0x5EC4C0
    assert struct.unpack('<I', data[off(vt+0xA4):off(vt+0xA4)+4])[0] == 0x5EC4B0
    P(vt+0xA0, struct.pack('<I', GET_KMAX), f"vtable {vt:#x}: max stiffness getter")
    P(vt+0xA4, struct.pack('<I', GET_KMIN), f"vtable {vt:#x}: min stiffness getter")

for o, a, b, d in patches:
    print(f"{o:#08x} len {len(b):3d}  {d}")
print("eyewrap", hex(EYEWRAP), "hook", hex(HOOK), "kmax", hex(GET_KMAX), "kmin", hex(GET_KMIN), "cave bytes", hex(len(cave)))
json.dump({"orig_md5": hashlib.md5(data).hexdigest(),
           "consts_off": off(CAVE),
           "patches": [dict(off=o, orig=a.hex(), new=b.hex(), desc=d) for o, a, b, d in patches]},
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "patch.json"), "w"), indent=1)
