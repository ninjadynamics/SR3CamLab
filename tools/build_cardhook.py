"""Car-select cards for cars the game has no video for (in-memory patch for patches.ps1; proposal, 2026-10-14).

How the game picks a card (Rally.exe, read in the code):
  0x61BCE0 builds "CARSLIDE_" + upper(car folder) + "_GRAVEL_1"; the card widget (0x6271C0) then looks that name up twice:
  as a named frontend texture (0x5822D0; the arcade cars have none, it falls back to MENU_ANIM_DOWN_ARROW) and in the menu
  video table 0x728630 (0x61C2C0: 18 entries {ptr name, ptr file, per-language flag, video handle}, bound 0x728750; the
  memory after it belongs to other data, so the table cannot grow in place). A name that is not in the table gets
  handle -1: blank placeholder card (seen in game for the Hornet, 2026-10-14).
The hook: the not-found exit of 0x61C2C0 (0x61C30B: 8B 44 24 14 5F 5E 5D C7 00 FF FF FF FF 5B C3) becomes a jump to
the block built here. The block compares the name with its own list of {char name[32], u32 ptr to a handle} and returns
that handle, else -1 as before. Nothing else changes: names the game knows never reach the not-found exit.
  - stand-in card: point the handle pointer at an existing table entry's handle field, e.g. 0x72870C
    (ID_STATIC_LOOP_VID, the TV-static loop), 0x7286BC (Bowler), 0x7286CC (ST205);
  - own card: load a WMV into one of the two spare video objects the way the launcher already does for track cards
    (game-runtime-and-frontend.md: 18 of 20 objects used) and point the handle pointer at the cell holding its handle.
The code is position independent; the list sits right after it.
    python build_cardhook.py [hook address hex]     prints the bytes, the 5-byte jump for that address, and tests the
                                                    hook on the real 0x61C2C0 of Rally.exe in unicorn
"""
import struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

LOOKUP = 0x61C2C0
EXIT = 0x61C30B
EXIT_BYTES = bytes.fromhex("8b442414 5f 5e 5d c700ffffffff 5b c3".replace(" ", ""))
CARDS = [("CARSLIDE_HORNET_GRAVEL_1", 0x72870C)]      # name, address of the handle to return (stand-in: static loop)
NAME_LEN = 32
ENTRY = NAME_LEN + 4

ASM = """
hook:       test ebp, ebp
            jz notfound
            call getpc
getpc:      pop esi
            add esi, %d
next:       cmp byte ptr [esi], 0
            je notfound
            mov ecx, ebp
            mov edx, esi
cmpl:       mov al, byte ptr [ecx]
            cmp al, byte ptr [edx]
            jne nomatch
            inc ecx
            inc edx
            test al, al
            jnz cmpl
            mov ecx, dword ptr [esi + %d]
            mov ecx, dword ptr [ecx]
            mov eax, dword ptr [esp + 0x14]
            pop edi
            pop esi
            pop ebp
            mov dword ptr [eax], ecx
            pop ebx
            ret
nomatch:    add esi, %d
            jmp next
notfound:   mov eax, dword ptr [esp + 0x14]
            pop edi
            pop esi
            pop ebp
            mov dword ptr [eax], 0xffffffff
            pop ebx
            ret
"""


def build(cards=CARDS):
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    # two passes: the offset from getpc to the list depends on the code length
    off = 0
    for _ in range(3):
        code = bytes(ks.asm(ASM % (off, NAME_LEN, ENTRY), 0)[0])
        getpc = 2 + 2 + 5          # test (2) + jz short (2) + call (5) -> getpc label offset
        off2 = len(code) - getpc
        if off2 == off: break
        off = off2
    table = b""
    for name, ptr in cards:
        n = name.encode("ascii"); assert len(n) < NAME_LEN
        table += n + bytes(NAME_LEN - len(n)) + struct.pack("<I", ptr)
    table += bytes(ENTRY)          # terminator (empty name)
    return code, table


def jump(at, to):
    return b"\xE9" + struct.pack("<i", to - (at + 5))


def test(code, table, base=0x20000000):
    """run the game's own 0x61C2C0 (sections of Rally.exe mapped as the loader would) with the jump at 0x61C30B"""
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EIP
    d = open(r"F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally\Rally.exe", "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]; ns = struct.unpack_from("<H", d, pe + 6)[0]
    so = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    secs = [struct.unpack_from("<8sIIII", d, so + 40 * i) for i in range(ns)]
    top = max(0x400000 + va + max(vs, rs) for n, vs, va, rs, ra in secs)
    mu.mem_map(0x400000, (top - 0x400000 + 0xFFFF) & ~0xFFFF)
    for n, vs, va, rs, ra in secs:
        mu.mem_write(0x400000 + va, d[ra:ra + min(rs, vs if vs else rs)])
    mu.mem_map(base, 0x10000); mu.mem_write(base, code + table)
    mu.mem_write(EXIT, jump(EXIT, base))
    stack = 0x30000000; mu.mem_map(stack, 0x10000)
    for k in range(18): mu.mem_write(0x728630 + 16 * k + 12, struct.pack("<i", 100 + k))     # fake loaded handles

    def strnicmp(uc, addr, size, user):           # the CRT routine the lookup calls (0x4AF410); done in Python
        if addr != 0x4AF410: return
        esp = uc.reg_read(UC_X86_REG_ESP)
        ret, a, b, n = struct.unpack("<4I", uc.mem_read(esp, 16))
        sa = bytes(uc.mem_read(a, n)).split(b"\0")[0][:n].lower(); sb = bytes(uc.mem_read(b, n)).split(b"\0")[0][:n].lower()
        uc.reg_write(UC_X86_REG_EAX, 0 if sa == sb else 1)
        uc.reg_write(UC_X86_REG_ESP, esp + 4); uc.reg_write(UC_X86_REG_EIP, ret)
    mu.hook_add(UC_HOOK_CODE, strnicmp, begin=0x4AF410, end=0x4AF410)
    results = {}
    for name in ("CARSLIDE_C4_GRAVEL_1", "CARSLIDE_HORNET_GRAVEL_1", "CARSLIDE_NOBODY_GRAVEL_1", "ID_STATIC_LOOP_VID", None):
        sp = stack + 0x8000
        nameaddr = stack + 0x100; out = stack + 0x80
        if name: mu.mem_write(nameaddr, name.encode() + b"\0")
        mu.mem_write(out, struct.pack("<i", 12345))
        sentinel = 0x7FFF0000
        mu.mem_write(sp, struct.pack("<3I", sentinel, out, nameaddr if name else 0))
        mu.reg_write(UC_X86_REG_ESP, sp)
        try: mu.emu_start(LOOKUP, sentinel, count=20000)
        except Exception as e:
            if mu.reg_read(UC_X86_REG_EIP) != sentinel: raise
        results[name] = (struct.unpack("<i", mu.mem_read(out, 4))[0], mu.reg_read(UC_X86_REG_ESP) - sp)
    return results


if __name__ == "__main__":
    code, table = build()
    at = int(sys.argv[1], 16) if len(sys.argv) > 1 else None
    print("block (%d bytes code + %d bytes list):" % (len(code), len(table)))
    print((code + table).hex(" "))
    if at is not None:
        print("jump at 0x%X for a block at 0x%X: %s" % (EXIT, at, jump(EXIT, at).hex(" ")))
    for k, v in test(code, table).items():
        print("lookup %-26r -> handle %d (stack %+d)" % (k, v[0], v[1]))
