"""Callers (b / bal / call and 32-bit literals) of Model 2 program addresses:  python m2calls.py 3c80 4350 ..."""
import os, sys, struct
import i960
def callers(t):
    prog = open(os.path.join(i960.M2, 'maincpu.bin'), 'rb').read(); out = []
    for o in range(0, 0x80000, 4):
        w = struct.unpack_from('<I', prog, o)[0]; op = w >> 24
        if op in (0x08, 0x09, 0x0b) and ((o + i960.sx(w & 0xfffffc, 24)) & 0xffffffff) == t: out.append((o, i960.CTRL[op]))
        if w == t or w == t + 0x59f000: out.append((o, 'literal %x' % w))
    return out
if __name__ == '__main__':
    for a in sys.argv[1:]: print(a, [(hex(o), k) for o, k in callers(int(a, 16))])
