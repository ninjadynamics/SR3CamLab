"""Builds the car-list routine of patch.ps1 (Set-CarLists): every car of the arcade's car library in every car select.

The game fills its car selector from the car library ([[0xB2A850] + 4] + 8, a linked list made from
ArcadeDatabase\\arcadedatabase_xdata.sbf; node +4 car id, +0x10 Classic flag, +0x14 bonus flag, +0x40 name) with one of three
routines, each taking edi = the selector:
    0x600790  cars with neither flag   (Championship, Quick Race: C4, Focus, Impreza, SX4, Evo, 207)
    0x6006F0  cars with the Classic flag (Classic: ST205, Delta)
    0x600740  cars with the bonus flag   (the secret-car page: Bowler, Enduro)
Each clears the selector (vtable +0x58) and adds a car with AddEntry (vtable +0x54: name, car id, -1, 0, 0). The routine
built here does the same for one class and then adds every other car, so each mode lists its own cars first. patch.ps1
puts a jump to it at the start of 0x600790 and 0x6006F0 (the secret-car page keeps its two). The selector holds up to 38
entries (0x5464D0 refuses more), the library has no fixed size.
The code is position independent (only the game's own absolute addresses), so it runs wherever patch.ps1 allocates it.
    python build_carlist.py        prints the bytes as hex and the disassembly"""
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
ASM = """
s_normal:   mov edx, 0
            jmp common
s_classic:  mov edx, 1
            jmp common
s_bonus:    mov edx, 2
            jmp common
common:     test edi, edi
            jz done
            push esi
            push ebx
            push ebp
            mov ebx, edx
            mov eax, dword ptr [edi]
            mov ecx, edi
            call dword ptr [eax + 0x58]
            xor ebp, ebp
pass:       mov eax, dword ptr [0xB2A850]
            mov esi, dword ptr [eax + 4]
            add esi, 8
            jz next_pass
node:       xor eax, eax
            cmp dword ptr [esi + 0x14], 0
            je c1
            mov eax, 2
c1:         cmp dword ptr [esi + 0x10], 0
            je c2
            mov eax, 1
c2:         xor ecx, ecx
            cmp eax, ebx
            setne cl
            cmp ecx, ebp
            jne skip
            mov eax, dword ptr [esi + 4]
            mov ecx, dword ptr [esi + 0x40]
            mov edx, dword ptr [edi]
            push 0
            push 0
            push -1
            push eax
            push ecx
            mov ecx, edi
            call dword ptr [edx + 0x54]
skip:       mov esi, dword ptr [esi]
            test esi, esi
            jnz node
next_pass:  inc ebp
            cmp ebp, 2
            jb pass
            pop ebp
            pop ebx
            pop esi
done:       ret
"""
def build():
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(ASM, 0); return bytes(code)
if __name__ == '__main__':
    b = build(); print(b.hex()); print('%d bytes; entries: normal +0, Classic +7, bonus +14' % len(b))
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(b, 0): print('  %04x  %-8s %s' % (i.address, i.mnemonic, i.op_str))
    except ImportError: pass
