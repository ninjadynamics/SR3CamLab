"""writes ../tmp/rally.asm: linear disassembly of Rally.exe .text for grep (read-only on the exe)"""
import os, x86
out = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tmp', 'rally.asm'), 'w')
a, end = x86.TEXT
while a < end:
    got = False
    for i in x86.md.disasm(x86.rd(a, min(0x10000, end - a)), a):
        out.write('%08x  %-8s %s\n' % (i.address, i.mnemonic, i.op_str)); a = i.address + i.size; got = True
    if not got: a += 1
out.close()
