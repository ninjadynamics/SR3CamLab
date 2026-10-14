"""i960 disassembly / interpretation of the Daytona USA program, using the project's i960.py (scripts/importer).

Memory map (MAME model2.cpp, model2o_mem):
    0x00000000  program ROM (maincpu.bin, 0x40000 bytes)        0x00220000  program ROM second half (maincpu + 0x20000)
    0x00200000  RAM 128 KB                                      0x00500000  work RAM 1 MB
    0x02000000  main data ROM (main_data.bin; 0x02800000 = the EPROM pair epr-16724a/16725a, mirrored up to 0x02FFFFFF)

    python daytona_i960.py dis <addr hex> [count]         disassemble
    python daytona_i960.py xref <lo hex> <hi hex>         32-bit literals in [lo, hi) in program + data EPROM, with the
                                                          instruction that holds them
"""
import os, sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "importer"))
import i960
from daytona_paths import OUT


class Mem(i960.Mem):
    def __init__(self):
        self.prog = open(os.path.join(OUT, "maincpu.bin"), "rb").read()
        self.data = open(os.path.join(OUT, "main_data.bin"), "rb").read()
        self.ram = {}; self.log = {}; self.unk = {}; self.wlog = None

    def r8(self, a):
        a &= 0xffffffff
        if a in self.ram: return self.ram[a]
        if a < 0x40000: return self.prog[a]
        if 0x220000 <= a < 0x240000: return self.prog[a - 0x200000]
        if 0x02000000 <= a < 0x03000000:
            o = a - 0x02000000
            if o >= 0x900000: o = 0x800000 + (o & 0xFFFFF)      # ROM_COPY mirrors of the EPROM pair
            return self.data[o]
        self.unk[a & ~0xfff] = self.unk.get(a & ~0xfff, 0) + 1
        return 0

    def w8(self, a, v):
        a &= 0xffffffff; self.ram[a] = v & 255
        if self.wlog is not None: self.wlog.append((a, v & 255))


def dis(addr, count=40, mem=None):
    return i960.dis(addr, count, mem or Mem())


def xref(lo, hi):
    m = Mem(); out = []
    for base, blob in ((0, m.prog), (0x02800000, m.data[0x800000:0x900000])):
        for o in range(0, len(blob) - 3, 4):
            v = struct.unpack_from("<I", blob, o)[0]
            if lo <= v < hi:
                w = struct.unpack_from("<I", blob, o - 4)[0] if o >= 4 else 0
                try: d = i960.fmt(i960.decode(w, v, base + o - 4))
                except Exception: d = "?"
                out.append("%08x: literal %08x   prev word %08x  -> %s" % (base + o, v, w, d))
    return out


if __name__ == "__main__":
    if sys.argv[1] == "dis":
        print("\n".join(dis(int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 40)))
    elif sys.argv[1] == "xref":
        print("\n".join(xref(int(sys.argv[2], 16), int(sys.argv[3], 16))))
