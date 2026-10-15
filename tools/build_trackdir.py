"""Builds the track-folder routine of patches.ps1 (Install-TrackDir): the folder an alternative track is read from is
chosen inside the game's own path code, at the moment a path is made, instead of by the launcher's polling.

Why: the launcher switched folders by polling. It rewrote the 's' of "\\main_release\\tracks\\%s\\..." in six format strings
into the folder's digit ("track1" = alternative 1) whenever the track it saw changed. The game starts reading a track's
files before the poll sees the change: on 2026-10-14 the attract demo loaded Tropical's route from "tracks" and its road
slices from "track1" (Tropical 2, left over from the Mountain race before) and crashed in the start-grid placement
(0x5AF329: slice 2796 of 2732). See docs\\kb\\09_authoring_status.md.

The game makes those paths in three routines, each starting from the current track's name [[0x9DBDB0] + 0x18]:
    0x5C5C90  <name>_master_xdata          first instruction  mov eax, [0x9DBDB0]   (A1 B0 BD 9D 00, 5 bytes)
    0x5C5770  <name>_master_gfx_xdata      first instruction  sub esp, 0x118        (81 EC 18 01 00 00, 6 bytes)
    0x61B3B0  <name>_track_route<n>_...    first instruction  sub esp, 0x100        (81 EC 00 01 00 00, 6 bytes)
Each gets a jump to an entry of this routine: it looks the name up in a table the launcher keeps (track name -> folder
character), writes that character into the six format strings (the game's own and the three unused copies), and goes on
with the instruction it replaced. A name that is not in the table gets 's' (the game's own folder). So every file of a
load comes from one folder, however late the launcher's poll is.

Layout of the block (patches.ps1 allocates it, 0x1000 bytes): code at 0; at TABLE (0x200) a dword count, then up to 16
entries of 0x20 bytes: the name (zero-terminated, at most 23 characters), the folder character at +0x18; at LAST (0x1F0)
the character written last. Position independent (call / pop; jumps back with push / ret).
    python build_trackdir.py        prints the bytes as hex, the entry offsets and the disassembly"""
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
TABLE, LAST, ENTRIES = 0x200, 0x1F0, 16
SITES = (0x6C607B, 0x6C60A3, 0x6D57C3, 0x6E034F, 0x6E03A3, 0x6E055B)     # the 's' of "tracks" in the six format strings
HOOKS = ((0x5C5C90, 'a1b0bd9d00', 'mov eax, dword ptr [0x9dbdb0]', 0x5C5C95),
         (0x5C5770, '81ec18010000', 'sub esp, 0x118', 0x5C5776),
         (0x61B3B0, '81ec00010000', 'sub esp, 0x100', 0x61B3B6))
SETDIR = """setdir:
    pushfd
    pushad
    call sd_here
sd_here:
    pop ebp
    sub ebp, {here}
    mov eax, dword ptr [0x9dbdb0]
    test eax, eax
    jz sd_done
    mov esi, dword ptr [eax + 0x18]
    test esi, esi
    jz sd_done
    mov dl, 0x73
    lea edi, [ebp + {table}]
    mov ecx, dword ptr [edi]
    cmp ecx, {n}
    jbe sd_count
    mov ecx, {n}
sd_count:
    add edi, 4
sd_next:
    test ecx, ecx
    jz sd_write
    push esi
    push edi
    mov ebx, 23
sd_cmp:
    mov al, byte ptr [esi]
    cmp al, byte ptr [edi]
    jne sd_no
    test al, al
    jz sd_yes
    inc esi
    inc edi
    dec ebx
    jz sd_no
    jmp sd_cmp
sd_yes:
    pop edi
    pop esi
    mov dl, byte ptr [edi + 0x18]
    jmp sd_write
sd_no:
    pop edi
    pop esi
    add edi, 0x20
    dec ecx
    jmp sd_next
sd_write:
{writes}
    mov byte ptr [ebp + {last}], dl
sd_done:
    popad
    popfd
    ret
"""
def asm(here):
    a = SETDIR.format(here=here, table=TABLE, n=ENTRIES, last=LAST, writes='\n'.join('    mov byte ptr [0x%X], dl' % s for s in SITES))
    for k, (site, orig, ins, back) in enumerate(HOOKS):
        a += 'entry%d:\n    call setdir\n    %s\n    push 0x%X\n    ret\n' % (k, ins, back)
    return a
def build():
    ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)
    def find(code):
        ins = list(cs.disasm(code, 0))
        here = next(i.address + i.size for i in ins if i.mnemonic == 'call' and int(i.op_str, 16) == i.address + i.size)
        entries = [i.address for i in ins if i.mnemonic == 'call' and int(i.op_str, 16) == 0]
        return here, entries
    code = bytes(ks.asm(asm(0), 0)[0]); here, _ = find(code)
    code = bytes(ks.asm(asm(here), 0)[0]); here2, entries = find(code)
    assert here2 == here and len(entries) == len(HOOKS) and len(code) <= LAST, (here, here2, entries, len(code))
    return code, entries
if __name__ == '__main__':
    code, entries = build(); print(code.hex()); print('%d bytes; entries %s; table at 0x%X, last at 0x%X' % (len(code), ' '.join('0x%X' % e for e in entries), TABLE, LAST))
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, 0): print('  %04x  %-8s %s' % (i.address, i.mnemonic, i.op_str))
