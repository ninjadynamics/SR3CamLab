"""Execute the supported game's initializer/allocator/destructor after relocation.

The actual decoder and COM texture release are stubbed; no game is launched.
"""
from pathlib import Path
import json
import re
import struct
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EDI, UC_X86_REG_ESP, UC_X86_REG_EIP

ROOT = Path(__file__).resolve().parents[3]
PE = pefile.PE(str(ROOT / 'game/Rally/Rally.exe'))
IMAGE = PE.get_memory_mapped_image()
BASE = PE.OPTIONAL_HEADER.ImageBase
POOL, COM, STACK, END = 0x20000040, 0x20010000, 0x20020000, 0x20040000


def main():
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(BASE, (len(IMAGE) + 4095) & ~4095)
    mu.mem_write(BASE, IMAGE)
    mu.mem_map(0x20000000, 0x50000)
    mu.mem_write(POOL, bytes([0xCC]) * (64 * 364))
    sentinel = bytes(range(32))
    mu.mem_write(0xAD4C00, sentinel)
    u32 = lambda v: struct.pack('<I', v & 0xffffffff)
    rd = lambda a: struct.unpack('<I', mu.mem_read(a, 4))[0]
    rows = re.findall(r'\{0x([0-9a-f]+),(\d+),(\d+),(\d+),(\d+),(-?\d+),\{([^}]+)\}\}',
                      Path(__file__).with_name('video_pool_sites.h').read_text())
    assert len(rows) == 18
    for va, size, offset, width, kind, delta, data in rows:
        va, size, offset, width, kind, delta = int(va, 16), *map(int, (size, offset, width, kind, delta))
        original = bytes(int(v, 16) for v in data.split(','))
        assert bytes(mu.mem_read(va, size)) == original
        value = {0: POOL + delta, 1: 64 * 364, 2: 64 + delta,
                 3: 2 - 64, 4: POOL + 64 * 364 + delta}[kind]
        patched = bytearray(original)
        patched[offset:offset+width] = u32(value)[:width]
        mu.mem_write(va, bytes(patched))

    opened, released = [], []

    def return_(value=0, extra=0):
        sp = mu.reg_read(UC_X86_REG_ESP)
        mu.reg_write(UC_X86_REG_EAX, value)
        mu.reg_write(UC_X86_REG_EIP, rd(sp))
        mu.reg_write(UC_X86_REG_ESP, sp + 4 + extra)

    def callback(mu, address, size, user):
        if address == 0x4AEFBF:
            return_(0)
        elif address == 0x4DDC80:
            obj = mu.reg_read(UC_X86_REG_EDI)
            assert POOL <= obj < POOL + 64 * 364 and (obj - POOL) % 364 == 0
            opened.append((obj - POOL) // 364)
            mu.mem_write(obj + 4, u32(1))
            return_(1)
        else:
            sp = mu.reg_read(UC_X86_REG_ESP)
            released.append((rd(sp + 4) - COM) // 16)
            return_(0, 4)

    for address in (0x4AEFBF, 0x4DDC80, 0x20041000):
        mu.hook_add(UC_HOOK_CODE, callback, begin=address, end=address)

    def call(address, *args):
        sp = STACK + 0x8000
        mu.mem_write(sp, b''.join(u32(x) for x in [END, *args]))
        mu.reg_write(UC_X86_REG_ESP, sp)
        mu.emu_start(address, END, count=200000)
        assert mu.reg_read(UC_X86_REG_ESP) == sp + 4

    call(0x671D30)
    for i in range(64):
        assert rd(POOL + i * 364 + 4) == rd(POOL + i * 364 + 0x11c) == 0
    out, path = STACK + 0x100, STACK + 0x200
    mu.mem_write(path, b'fixture.wmv\0')
    for i in range(64):
        call(0x4DE430, out, path)
        assert rd(out) == i
    call(0x4DE430, out, path)
    assert rd(out) == 0xffffffff and opened == list(range(64))
    mu.mem_write(COM + 0x1000 + 8, u32(0x20041000))
    for i in range(64):
        mu.mem_write(COM + i * 16, u32(COM + 0x1000))
        mu.mem_write(POOL + i * 364 + 0x144, u32(COM + i * 16))
    call(0x6738C0)
    assert released == list(reversed(range(64)))
    assert bytes(mu.mem_read(0xAD4C00, len(sentinel))) == sentinel
    print(json.dumps(dict(status='PASS', initialized=64, allocated=64,
                          rejected_overflow=True, released=64, shader_globals_unchanged=True)))


if __name__ == '__main__':
    main()
