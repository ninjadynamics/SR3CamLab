"""Shared paths and small helpers for the SR3 track-format work."""
import os, sys, struct, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sbf3 import Sbf, hexd, raw
GAME = r"F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally"
TRACKS = os.path.join(GAME, "Main_release", "tracks")
DEMO = r"F:\Jogos\_revodemo_dl\extracted\program files\SEGA\SEGA Rally Revo Demo\Main_release\tracks"
CONV = r"F:\Jogos\_revo_ps3_converted\main_release\tracks"
WORK = os.path.dirname(HERE)
OUT = os.path.join(WORK, "out")
TMP = os.path.join(WORK, "tmp")
SR3 = ['Tropical4', 'Canyon4', 'Alpine4', 'Lakeside4', 'Desert4', 'Stadium4']

def track_files(folder):
    """returns dict suffix -> path for the 6 sbf files (+ 'proc')"""
    r = {}
    for f in os.listdir(folder):
        l = f.lower()
        for suf in ('pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata', 'game_objects_gfx_data', 'gameobj_gfx_dis_data', 'master_gfx_xdata', 'master_xdata'):
            if l.endswith('_' + suf + '.sbf'): r[suf] = os.path.join(folder, f); break
        if l.endswith('_proc_cached.bin'): r['proc'] = os.path.join(folder, f)
    return r

def u32s(b, off=0, n=None):
    if n is None: n = (len(b) - off) // 4
    return struct.unpack_from('<%dI' % n, b, off)
def f32s(b, off=0, n=None):
    if n is None: n = (len(b) - off) // 4
    return struct.unpack_from('<%df' % n, b, off)

def dump(b, off, n, fix=()):
    """hex + float dump, marks pointer words with *"""
    fs = set(fix)
    for i in range(off, min(off + n, len(b)) // 4 * 4, 16):
        ws = []; fl = []
        for j in range(i, min(i + 16, len(b) - 3), 4):
            w = struct.unpack_from('<I', b, j)[0]; f = struct.unpack_from('<f', b, j)[0]
            ws.append(('*' if j in fs else ' ') + '%08x' % w)
            fl.append('%10.4g' % f if (1e-4 < abs(f) < 1e7) else '         .')
        row = b[i:i+16]
        print('%06x %s | %s | %s' % (i, ''.join(ws), ' '.join(fl), ''.join(chr(c) if 32 <= c < 127 else '.' for c in row)))

def nearest2d(P, Q, cell=4.0):
    """for each point of Q (m,2) the index of and distance to the nearest point of P (n,2); numpy only (bucket grid)."""
    import numpy as np, collections
    P = np.asarray(P, float); Q = np.asarray(Q, float)
    b = collections.defaultdict(list)
    for i, (x, z) in enumerate(np.floor(P / cell).astype(int)): b[(x, z)].append(i)
    idx = np.zeros(len(Q), int); dist = np.full(len(Q), np.inf)
    for j, q in enumerate(Q):
        cx, cz = int(np.floor(q[0] / cell)), int(np.floor(q[1] / cell)); r = 1
        while True:
            cand = [i for dx in range(-r, r + 1) for dz in range(-r, r + 1) for i in b.get((cx + dx, cz + dz), ())]
            if cand:
                d = np.hypot(P[cand, 0] - q[0], P[cand, 1] - q[1]); k = int(np.argmin(d))
                if d[k] <= r * cell or r > 64: idx[j] = cand[k]; dist[j] = d[k]; break
            r += 1
            if r > 200: break
    return idx, dist
