"""Find 32-bit literals in a range inside the Model 2 program ROM and show the instruction that holds them.
    python m2xref.py 210800 213900        (hex range, RAM addresses)"""
import os, sys, struct
import i960
def main(lo, hi):
    prog = open(os.path.join(i960.M2, 'maincpu.bin'), 'rb').read(); out = []
    for o in range(0, len(prog) - 3, 4):
        v = struct.unpack_from('<I', prog, o)[0]
        if lo <= v < hi: out.append((o, v))
    for o, v in out:
        w = struct.unpack_from('<I', prog, o - 4)[0] if o >= 4 else 0
        try: d = i960.fmt(i960.decode(w, v, o - 4))
        except Exception as e: d = '?'
        print('%06x: literal %08x   prev word %08x  -> %s' % (o, v, w, d))
    return out
if __name__ == '__main__':
    main(int(sys.argv[1], 16), int(sys.argv[2], 16))
