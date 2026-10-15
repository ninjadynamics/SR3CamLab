"""SEGA Rally 2 course gameplay tables (stage table 0xE8408 -> banked CROM section / collision data)."""
import struct, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2common import *
BK = np.memmap(B + "sr_classic/out/m3/banked_crom.bin", dtype=np.uint8, mode='r')
STAGE_TAB = 0xE8408; NSTAGE = 8
SURF = ['TARMAC', 'TARMAC2', 'GRAVEL', 'GRAVEL2', 'WATER', 'WATER2', 'DIRT', 'DIRT2', 'TUNNEL', 'TUNNEL2', 'SNOW', 'SNOW2', 'WET', 'WET2']
COURSE_NAME = {2: 'FOREST', 3: 'MOUNTAIN', 4: 'DESERT', 5: 'RIVIERA', 6: 'SNOWY'}   # course id -> name (id - 2 = table index)

class Bank:
    def __init__(self, bank): self.o = bank * 0x800000
    def off(self, a): return self.o + (a & 0x7FFFFF)
    def u32(self, a): return struct.unpack_from('>I', BK, self.off(a))[0]
    def s32(self, a): return struct.unpack_from('>i', BK, self.off(a))[0]
    def f32(self, a): return struct.unpack_from('>f', BK, self.off(a))[0]
    def words(self, a, n, dt='>u4'): return np.frombuffer(BK, dtype=dt, count=n, offset=self.off(a))

def stage(s):
    a = STAGE_TAB + 96 * s
    w = [u32(a + 4 * i) for i in range(24)]; f = [f32(a + 4 * i) for i in range(24)]
    return dict(stage=s, addr=a, id0=w[0], course_id=w[1], w2=w[2], w3=w[3], w4=w[4], w5=s32(a + 20), light=f[6:9], f9_13=f[9:14], w14=w[14], f15=f[15], colour=w[16], w17=w[17],
                fog=f[18], f19=f[19], bank=w[20] & 0xFF, sect=w[21], lines=w[22], notes=w[23], words=w)

def sections(s):
    """-> dict(n, quads (n,4,2) x,z, polylist [list of poly indices], polys ndarray (N,76) float view + raw u32 view)"""
    st = stage(s); bk = Bank(st['bank']); h = st['sect']
    n = bk.u32(h); pA = bk.u32(h + 4); pB = bk.u32(h + 8)
    A = bk.words(pA, n * 11, '>f4').reshape(n, 11); Au = bk.words(pA, n * 11).reshape(n, 11)
    quads = A[:, :8].reshape(n, 4, 2).astype(float)
    lines = bk.words(st['lines'], n * 9, '>f4').reshape(n, 3, 3).astype(float)
    lists = []; mx = -1
    for i in range(n):
        p = int(Au[i, 10]); L = []
        while True:
            v = bk.s32(p)
            if v < 0: break
            L.append(v); p += 4
        lists.append(L); mx = max(mx, max(L) if L else -1)
    npoly = mx + 1
    Pu = bk.words(pB, npoly * 76).reshape(npoly, 76); Pf = bk.words(pB, npoly * 76, '>f4').reshape(npoly, 76)
    return dict(stage=st, n=n, pA=pA, pB=pB, quads=quads, lines=lines, lists=lists, Pu=Pu, Pf=Pf, bank=bk)

def pace_notes(s):
    st = stage(s); a = st['notes']; out = []
    while True:
        sec = s32(a)
        if sec < 0: break
        out.append(dict(section=sec, cond=s32(a + 4), dist=s32(a + 8), icon1=s32(a + 12), icon2=s32(a + 16), req=s32(a + 20), addr=a)); a += 24
    return out

if __name__ == '__main__':
    for s in range(NSTAGE):
        st = stage(s)
        print(s, {k: (('%X' % v) if isinstance(v, int) and v > 0xFFFF else v) for k, v in st.items() if k != 'words'})
    from collections import Counter
    for s in (1, 2, 3, 4, 5, 6, 0):
        S = sections(s); Pu = S['Pu']
        print('stage', s, 'n', S['n'], 'polys', len(Pu), 'A %X B %X' % (S['pA'], S['pB']), 'list len', min(map(len, S['lists'])), max(map(len, S['lists'])))
        for col in (70, 71, 72, 73, 74, 75):
            c = Counter(int(x) for x in Pu[:, col]); print('   word', col, 'off', col * 4, len(c), [('%X' % k, v) for k, v in c.most_common(14)])
