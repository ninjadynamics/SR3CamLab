"""SEGA Rally Championship colour translation table (colorxlat, 0x01810000 R / 0x01814000 G / 0x01818000 B) recovered by
running the game's own fill routine (maincpu 0x4350, uses i960 floating point) in the interpreter.
    python m2xlat.py   -> ../tmp/m2/colorxlat.npy  (3, 32, 64) uint8 : [channel][5-bit colour][luma 0..63]
The routine reads a key table at RAM 0x5A2EB0 (= program ROM 0x3EB0, initialised data copied at boot)."""
import os, struct, numpy as np
import i960

class Mem2(i960.Mem):
    def r8(self, a):
        a &= 0xffffffff
        if a not in self.ram and 0x5a0000 <= a < 0x5a0000 + 0x160000: return self.prog[a - 0x59f000]     # boot copy of initialised data
        return i960.Mem.r8(self, a)

def run(entry=0x4350, maxsteps=30000000):
    m = Mem2(); c = i960.Cpu(m); c.r[30] = 0xdead0000
    res = c.run(entry, maxsteps=maxsteps, stop_at=(0xdead0000,))
    return m, c, res

def table():
    """(3, 32, 64) uint8. Order as in the game's init (0x3720: call 0x3C80, call 0x4350): the general table first, then the
    ten key-frame gradients that replace rows 1, 3, .. 19 (palette entries with r = g = b = odd select them)."""
    p = os.path.join(i960.M2, 'colorxlat.npy')
    if os.path.exists(p): return np.load(p)
    m = Mem2(); t = np.zeros((3, 32, 64), np.uint8); hi = 0
    for entry in (0x3c80, 0x4350):
        c = i960.Cpu(m); c.r[30] = 0xdead0000; res = c.run(entry, maxsteps=40000000, stop_at=(0xdead0000,)); n = len(m.log)
        print('routine %x: %s after %d steps; %d table bytes written so far' % (entry, res, c.steps, n))
    for a, v in m.log.items():
        if 0x01810000 <= a < 0x0181c000:
            o = a - 0x01810000; ch = o >> 14; o &= 0x3fff; lvl = o >> 9; e = o & 0x1ff
            if e & 1: hi += 1 if v else 0
            elif (e >> 1) < 64: t[ch, lvl, e >> 1] = v
    print('non-zero high bytes: %d' % hi)
    np.save(p, t); return t

def keys():
    """the ten gradients of 0x4350: list of [(position 0..1, r, g, b)] read from program ROM 0x3EB0"""
    prog = open(os.path.join(i960.M2, 'maincpu.bin'), 'rb').read(); o = 0x3eb0; out = []
    for _ in range(10):
        n = int(struct.unpack_from('<f', prog, o)[0]); o += 4
        out.append([struct.unpack_from('<4f', prog, o + 16 * k) for k in range(n)]); o += 16 * n
    return out

if __name__ == '__main__':
    t = table()
    for lvl in (31, 16, 8):
        print('general row, colour level %2d, luma 0,4,..60,63:' % lvl, t[0, lvl, ::4].tolist(), int(t[0, lvl, 63]))
    ev = [l for l in range(32) if not (l & 1 and l < 20)]
    print('R = G = B on the general rows:', bool((t[0, ev] == t[1, ev]).all() and (t[1, ev] == t[2, ev]).all()))
    lin = np.clip(np.round(np.arange(32)[:, None] * 255 / 31 * np.arange(64)[None, :] / 63), 0, 255)
    print('max difference of the general rows from the old linear assumption:', int(np.abs(t[0, ev].astype(int) - lin[ev]).max()))
    for k, ks in enumerate(keys()):
        r = 2 * k + 1; print('gradient row %2d: %d keys %s -> luma 0 %s, luma 32 %s, luma 63 %s' % (r, len(ks), [tuple(round(x, 2) for x in q) for q in ks], t[:, r, 0].tolist(), t[:, r, 32].tolist(), t[:, r, 63].tolist()))
