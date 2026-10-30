"""Replay native card construction for repeated slots and Classic game cards.

Allocator/frontend-service/CRT boundaries and the registry fill are stubbed.
The supported executable's scene constructor, selector count/data accessors,
track-node lookup loop and card-name builder run.
No game is launched or installed.
"""
from pathlib import Path
import struct
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESI, UC_X86_REG_EDI

R = Path(__file__).resolve().parents[3]
pe = pefile.PE(str(R / 'game/Rally/Rally.exe'))
base = pe.OPTIONAL_HEADER.ImageBase
im = pe.get_memory_mapped_image()
H, STACK, END = 0x20000000, 0x20100000, 0x20200000
u32 = lambda x: struct.pack('<I', x & 0xffffffff)


def main():
    m = Uc(UC_ARCH_X86, UC_MODE_32)
    m.mem_map(base, (len(im)+4095)&~4095)
    m.mem_write(base, im)
    m.mem_map(H, 0x210000)
    rd = lambda a: struct.unpack('<I', m.mem_read(a, 4))[0]
    def wr(a, n): m.mem_write(a, u32(n))
    def string(a): return bytes(m.mem_read(a, 128)).split(b'\0')[0].decode()
    def ret(value=0, extra=0):
        sp = m.reg_read(UC_X86_REG_ESP)
        m.reg_write(UC_X86_REG_EAX, value)
        m.reg_write(UC_X86_REG_EIP, rd(sp))
        m.reg_write(UC_X86_REG_ESP, sp+4+extra)
    count, scene, db, lib = 14, H+0x1000, H+0x2000, H+0x3000
    wr(0xb2a850, db); wr(db+8, lib)
    for i in range(count):
        node, text = lib+8+i*28, H+0x5000+i*128
        wr(node, node+28 if i+1<count else 0); wr(node+4, i); wr(node+0x18, text)
        m.mem_write(text, f'URL_{i:02}'.encode()+b'\0')
    wr(scene+0xa4, scene+0xa8)
    names, nodes = [], []
    def helper(mu, at, size, user):
        sp = mu.reg_read(UC_X86_REG_ESP)
        if at == 0x552f60:
            obj = mu.reg_read(UC_X86_REG_EAX); wr(obj, 0x6ea220); ret(obj,4)
        elif at == 0x600660:
            # Publish the registry layout; the constructor below executes the
            # actual selector count and entry-data accessors against it.
            obj = mu.reg_read(UC_X86_REG_EDI)
            wr(obj+0xc0, count)
            for i in range(count):
                wr(obj+0x104+i*0x50, i)
            ret()
        elif at == 0x62ca50:
            parent, index = rd(sp+4), rd(sp+8)
            card, link = H+0x10000+index*0x200, H+0x20000+index*16
            tail, prev = parent+0xa8, rd(parent+0xac) or parent+0xa4
            wr(link, tail); wr(link+4, prev); wr(link+12, card)
            wr(prev, link); wr(parent+0xac, link)
            wr(card+0xa4, card+0xa8)
            nodes.append(card); ret(card, 8)
        elif at == 0x62aa30:
            # Keep the real native lookup's result, then run its real name
            # builder with the same EAX=node / stack=card convention.
            node = rd(sp+8)
            assert rd(node+4) == len(names)
            mu.reg_write(UC_X86_REG_EAX, node)
            mu.reg_write(UC_X86_REG_EIP, 0x628f60)
        elif at == 0x6271c0:
            names.append(string(rd(sp+8))); ret()
        elif at == 0x4af4d0:
            dst, src, n = rd(sp+4), rd(sp+8), rd(sp+12)
            mu.mem_write(dst, bytes(mu.mem_read(src, n))); ret(dst)
        elif at == 0x4b079f:
            ptr = rd(sp+4); mu.mem_write(ptr, string(ptr).upper().encode()+b'\0'); ret(ptr)
        elif at == 0x4afd00:
            dst, src, n = rd(sp+4), rd(sp+8), rd(sp+12)
            mu.mem_write(dst, (string(dst)+string(src)[:n]).encode()+b'\0'); ret(dst)
        elif at == 0x622e40: ret(extra=20)
        elif at == 0x61b170: ret(extra=4)
        else: ret()
    for at in (0x552f60,0x600660,0x62ca50,0x62aa30,0x6271c0,0x4af4d0,0x4b079f,0x4afd00,0x61b170,0x4077b0,0x622270,0x622e40,0x552730):
        m.hook_add(UC_HOOK_CODE, helper, begin=at, end=at)
    sp = STACK+0x80000
    m.mem_write(sp,u32(END)+u32(scene));m.reg_write(UC_X86_REG_ESP,sp)
    m.emu_start(0x62d1c0,END,count=1000000)
    assert m.reg_read(UC_X86_REG_ESP)==sp+8
    assert names == [f'TRACKSLIDE_URL_{i:02}' for i in range(count)]
    assert len(nodes)==count
    print('PASS: actual native constructor/lookup/name builder creates all 14 UI cards; stack and scene count agree')


if __name__ == '__main__': main()
