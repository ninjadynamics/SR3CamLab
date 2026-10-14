"""Runs the track-folder routine (build_trackdir.py) on an emulated CPU against a made-up game: the current track's name
at [[0x9DBDB0] + 0x18], the six format strings, a table. Each entry is run the way the game reaches it (a jump at the
start of the path routine) up to the address it must go on at, and checked: the character written into all six strings,
'' for a name not in the table, registers and flags as the game left them (apart from what the replaced instruction
does), the stack as it was.   python trackdir_emu.py"""
import struct, sys, os
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_trackdir as B
code, entries = B.build()
CAVE = 0x10000000; STACK = 0x20000000; GAME = 0x30000000
u = Uc(UC_ARCH_X86, UC_MODE_32)
for a, n in ((0x9D0000, 0x10000), (0x6C0000, 0x30000), (CAVE, 0x1000), (STACK - 0x10000, 0x20000), (GAME, 0x1000), (0x5C0000, 0x10000), (0x610000, 0x10000)): u.mem_map(a, n)
u.mem_write(CAVE, code)
FMT = {0x6C607B: b'\\main_release\\tracks\\%s', 0x6C60A3: b'x', 0x6D57C3: b'x', 0x6E034F: b'x', 0x6E03A3: b'x', 0x6E055B: b'x'}
def table(rows):
    b = struct.pack('<I', len(rows))
    for name, ch in rows: b += name.encode().ljust(0x18, b'\0') + ch.encode() + b'\0' * 7
    u.mem_write(CAVE + B.TABLE, b.ljust(4 + 0x20 * 16, b'\0'))
def current(name):
    if name is None: u.mem_write(0x9DBDB0, struct.pack('<I', 0)); return
    u.mem_write(GAME + 0x100, name.encode() + b'\0'); u.mem_write(GAME, b'\0' * 0x18 + struct.pack('<I', GAME + 0x100)); u.mem_write(0x9DBDB0, struct.pack('<I', GAME))
def sites(): return ''.join(chr(u.mem_read(s, 1)[0]) for s in B.SITES)
REGS = (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)
def run(k):
    vals = (0x11111111, 0x22222222, 0x33333333, 0x44444444, 0x55555555, 0x66666666, 0x77777777)
    for r, v in zip(REGS, vals): u.reg_write(r, v)
    esp = STACK - 0x100; u.reg_write(UC_X86_REG_ESP, esp); u.reg_write(UC_X86_REG_EFLAGS, 0x2 | 0x1 | 0x40 | 0x800)   # CF, ZF, OF set
    back = B.HOOKS[k][3]; u.emu_start(CAVE + entries[k], back, count=2000)
    got = {r: u.reg_read(r) for r in REGS}; e = u.reg_read(UC_X86_REG_ESP); fl = u.reg_read(UC_X86_REG_EFLAGS) & 0xCD5
    want = dict(zip(REGS, vals)); want_esp = esp
    if k == 0: want[UC_X86_REG_EAX] = struct.unpack('<I', u.mem_read(0x9DBDB0, 4))[0]
    else: want_esp = esp - (0x118 if k == 1 else 0x100)
    ok_regs = got == want and e == want_esp and u.reg_read(UC_X86_REG_EIP) == back
    flags_ok = fl == (0x1 | 0x40 | 0x800) if k == 0 else True        # sub esp sets the flags itself, as in the game
    return ok_regs and flags_ok
npass = nfail = 0
def check(what, ok):
    global npass, nfail
    npass += ok; nfail += not ok; print('  %s %s' % ('ok    ' if ok else 'FAILED', what))
for s in B.SITES: u.mem_write(s, b's')
table([('Desert4', '1'), ('Tropical4', '2'), ('Canyon4', '1')])
for k in range(3):
    current('Desert4'); r = run(k); check('entry %d (%s), track Desert4 in the table as "1": all six strings say "%s", registers / stack / flags as the game expects: %s' % (k, hex(B.HOOKS[k][0]), sites(), r), sites() == '111111' and r)
    current('Tropical4'); r = run(k); check('entry %d, track Tropical4 -> "2": %s, %s' % (k, sites(), r), sites() == '222222' and r)
    current('Lakeside4'); r = run(k); check('entry %d, track Lakeside4 not in the table -> the game\'s own folder "s": %s, %s' % (k, sites(), r), sites() == 'ssssss' and r)
current('Desert44'); run(0); check('a name that only starts like an entry (Desert44) is not taken for it: %s' % sites(), sites() == 'ssssss')
current('Desert'); run(0); check('a name that is the start of an entry (Desert) is not taken for it: %s' % sites(), sites() == 'ssssss')
current(None); u.mem_write(0x6C607B, b'1'); r = run(0); check('no current track (pointer 0): nothing written (strings as they were), registers as the game expects: %s' % r, u.mem_read(0x6C607B, 1) == b'1' and r)
table([]); current('Desert4'); run(1); check('empty table: every track from the game\'s own folder: %s' % sites(), sites() == 'ssssss')
u.mem_write(CAVE + B.TABLE, struct.pack('<I', 999)); current('Zzz'); run(2); check('a count beyond 16 is held to 16 (no reading past the table): %s' % sites(), sites() == 'ssssss')
table([('Desert4', '3')]); current('Desert4'); run(2); check('the last character written is kept for the launcher at +0x%X: %r' % (B.LAST, bytes(u.mem_read(CAVE + B.LAST, 1))), bytes(u.mem_read(CAVE + B.LAST, 1)) == b'3')
print('TRACKDIR CHECKS: %d passed, %d failed' % (npass, nfail))
