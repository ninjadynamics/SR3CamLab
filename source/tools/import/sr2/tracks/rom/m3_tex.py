"""SEGA Rally 2 texture records (texture-FIFO form {length, header, texels}) in VROM / banked CROM -> texture sheets.
Rules: Supermodel Real3D.cpp (UploadTexture, StoreTexture)."""
import numpy as np, pickle, re, os, sys, collections
O = '../../out/m3/'
D8 = np.array([1,0,5,4,9,8,13,12,3,2,7,6,11,10,15,14,17,16,21,20,25,24,29,28,19,18,23,22,27,26,31,30,33,32,37,36,41,40,45,44,35,34,39,38,43,42,47,46,49,48,53,52,57,56,61,60,51,50,55,54,59,58,63,62])
MIPX = [0, 1024, 1536, 1792, 1920, 1984, 2016, 2032, 2040, 2044, 2046, 2047]; MIPY = [0, 512, 768, 896, 960, 992, 1008, 1016, 1020, 1022, 1023]
SETS = {'common_p0': ('vrom_le.bin', 0x720000, 110), 'v_90d2ba': ('vrom_le.bin', 0x90d2ba, 55), 'v_a06d8c': ('vrom_le.bin', 0xa06d8c, 77), 'v_ad8312': ('vrom_le.bin', 0xad8312, 78),
        'v_b9b602': ('vrom_le.bin', 0xb9b602, 52), 'c_a00000': ('banked_crom.bin', 0xa00000, 58), 'c_ac4032': ('banked_crom.bin', 0xac4032, 184)}
_mem = {}
def words(name):
    if name not in _mem: _mem[name] = np.fromfile(O + name, '<u4' if name.startswith('vrom') else '>u4')
    return _mem[name]
def hdr(H): return dict(x=32 * (H & 0x3F), y=32 * ((H >> 7) & 0x1F), page=(H >> 20) & 1, w=32 << ((H >> 14) & 7), h=32 << ((H >> 17) & 7), s16=(H >> 23) & 1, typ=H >> 24)
def records(setname):
    name, a, n = SETS[setname]; w = words(name); out = []
    for _ in range(n):
        L, H = int(w[a]), int(w[a + 1]); nw = (2 + L // 2) // 4; out.append((a, H, nw)); a += nw
    return out
def texels16(name, a, count):
    """16-bit texel words of a record: the 32-bit words hold two texels each (low half first, as Supermodel reads a uint16 array on a little-endian host)"""
    w = words(name)[a:a + (count + 1) // 2].astype('<u4'); return w.view('<u2')[:count]
def store(sheet, x, y, w, h, t):
    """StoreTexture for 16-bit data: 8x8 tiles, texel order per decode8x8"""
    tx = min(8, w); ty = min(8, h)
    if tx != 8 or ty != 8: return w * h
    n = (w // 8) * (h // 8); tiles = t[:n * 64].reshape(n, 64)[:, D8].reshape(h // 8, w // 8, 8, 8)
    sheet[y:y + h, x:x + w] = tiles.transpose(0, 2, 1, 3).reshape(h, w); return w * h
def upload(sheets, name, a, H):
    h = hdr(H)
    if not h['s16'] or h['typ'] not in (0, 1): return False
    x, y, w, ht = h['x'], h['y'], h['w'], h['h']; total = w * ht * 2; t = texels16(name, a + 2, total); sh = sheets[h['page']]
    off = store(sh, x, y, w, ht, t)
    if h['typ'] == 0:
        i = 1
        while w >= 4 and ht >= 4:
            w //= 2; ht //= 2; off += store(sh, MIPX[i] + x // (1 << i), MIPY[i] + y // (1 << i), w, ht, t[off:]); i += 1
    return True
def build(setnames):
    sheets = np.zeros((2, 1024, 2048), np.uint16); placed = []
    for s in setnames:
        for a, H, nw in records(s):
            if upload(sheets, SETS[s][0], a, H): placed.append((s, a, hdr(H)))
    return sheets, placed
def rgb(sheet):
    return np.dstack([((sheet >> 10) & 31) * 255 // 31, ((sheet >> 5) & 31) * 255 // 31, (sheet & 31) * 255 // 31]).astype(np.uint8)
def course_rects(ci):
    out = set()
    for ln in open('../../obj/sr2_course%d_lod0.mtl' % ci):
        m = re.match(r'newmtl tex_p(\d)_x(\d+)_y(\d+)_(\d+)x(\d+)_f(\d)', ln)
        if m: out.add(tuple(int(v) for v in m.groups()))
    return out
if __name__ == '__main__':
    place = {s: {(h['page'], h['x'], h['y'], h['w'], h['h']) for a, H, nw in records(s) for h in [hdr(H)]} for s in SETS}
    for ci in range(5):
        R = course_rects(ci); r5 = {r[:5] for r in R}
        print('course %d: %d rectangles (page0 %d, page1 %d), formats %s' % (ci, len(r5), sum(1 for r in r5 if r[0] == 0), sum(1 for r in r5 if r[0] == 1), dict(collections.Counter(r[5] for r in R))))
        print('    exact matches per set:', {s: len(r5 & place[s]) for s in SETS})
