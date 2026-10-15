"""SEGA Rally Championship colour translation table (colorxlat, 0x01810000 R / 0x01814000 G / 0x01818000 B) recovered by
running the game's own fill routine (maincpu 0x4350, uses i960 floating point) in the interpreter.
    python m2xlat.py   -> ../tmp/m2/colorxlat.npy  (3, 32, 64) uint8 : [channel][5-bit colour][luma 0..63]
The routine reads a key table at RAM 0x5A2EB0 (= program ROM 0x3EB0, initialised data copied at boot).
Without numpy since 2026-10-15 (kb 31): the table is bytes, written by npyio (the same file np.save wrote); table() still hands the
callers that use numpy (m2colour.colour_tile) a numpy array, importing numpy only then."""
import os, struct
import i960, npyio

class Mem2(i960.Mem):
    def r8(self, a):
        a &= 0xffffffff
        if a not in self.ram and 0x5a0000 <= a < 0x5a0000 + 0x160000: return self.prog[a - 0x59f000]     # boot copy of initialised data
        return i960.Mem.r8(self, a)

def run(entry=0x4350, maxsteps=30000000):
    m = Mem2(); c = i960.Cpu(m); c.r[30] = 0xdead0000
    res = c.run(entry, maxsteps=maxsteps, stop_at=(0xdead0000,))
    return m, c, res

def table_bytes():
    """the table as 3 x 32 x 64 bytes, [channel][level][luma] in that order (np.zeros((3, 32, 64), np.uint8) filled as the numpy
    version did; a bytearray needs no numpy). Order as in the game's init (0x3720: call 0x3C80, call 0x4350): the general table
    first, then the ten key-frame gradients that replace rows 1, 3, .. 19 (palette entries with r = g = b = odd select them)."""
    p = os.path.join(i960.M2, 'colorxlat.npy')
    if os.path.exists(p): return bytes(npyio.load(p).buf)
    m = Mem2(); t = bytearray(3 * 32 * 64); hi = 0
    for entry in (0x3c80, 0x4350):
        c = i960.Cpu(m); c.r[30] = 0xdead0000; res = c.run(entry, maxsteps=40000000, stop_at=(0xdead0000,)); n = len(m.log)
        print('routine %x: %s after %d steps; %d table bytes written so far' % (entry, res, c.steps, n))
    for a, v in m.log.items():
        if 0x01810000 <= a < 0x0181c000:
            o = a - 0x01810000; ch = o >> 14; o &= 0x3fff; lvl = o >> 9; e = o & 0x1ff
            if e & 1: hi += 1 if v else 0
            elif (e >> 1) < 64: t[(ch * 32 + lvl) * 64 + (e >> 1)] = v & 0xff      # (numpy's uint8 store keeps the low byte too)
    print('non-zero high bytes: %d' % hi)
    npyio.save(p, npyio.Arr('|u1', (3, 32, 64), t)); return bytes(t)

def table():
    """(3, 32, 64) uint8 numpy array, for the callers that compute with numpy"""
    import numpy as np
    return np.frombuffer(bytearray(table_bytes()), np.uint8).reshape(3, 32, 64)

def keys():
    """the ten gradients of 0x4350: list of [(position 0..1, r, g, b)] read from program ROM 0x3EB0"""
    prog = open(os.path.join(i960.M2, 'maincpu.bin'), 'rb').read(); o = 0x3eb0; out = []
    for _ in range(10):
        n = int(struct.unpack_from('<f', prog, o)[0]); o += 4
        out.append([struct.unpack_from('<4f', prog, o + 16 * k) for k in range(n)]); o += 16 * n
    return out

if __name__ == '__main__':
    tb = table_bytes(); t = lambda ch, lvl, l: tb[(ch * 32 + lvl) * 64 + l]
    for lvl in (31, 16, 8):
        print('general row, colour level %2d, luma 0,4,..60,63:' % lvl, [t(0, lvl, l) for l in range(0, 64, 4)], t(0, lvl, 63))
    ev = [l for l in range(32) if not (l & 1 and l < 20)]
    print('R = G = B on the general rows:', all(t(0, v, l) == t(1, v, l) == t(2, v, l) for v in ev for l in range(64)))
    lin = lambda v, l: min(max(round(v * 255 / 31 * l / 63), 0), 255)  # np.clip(np.round(np.arange(32)[:, None] * 255 / 31 * np.arange(64)[None, :] / 63), 0, 255)
    print('max difference of the general rows from the old linear assumption:', max(abs(t(0, v, l) - lin(v, l)) for v in ev for l in range(64)))
    for k, ks in enumerate(keys()):
        r = 2 * k + 1; print('gradient row %2d: %d keys %s -> luma 0 %s, luma 32 %s, luma 63 %s' % (r, len(ks), [tuple(round(x, 2) for x in q) for q in ks], [t(c, r, 0) for c in range(3)], [t(c, r, 32) for c in range(3)], [t(c, r, 63) for c in range(3)]))
