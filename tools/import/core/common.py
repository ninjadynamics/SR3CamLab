"""Shared paths and small helpers for the SR3 track-format work. Every path comes from tools/import/settings.json (written by the
stack window, example in settings.example.json); what it leaves out has a default inside the repository."""
import os, sys, struct, zlib, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sbf3 import Sbf, hexd, raw
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))     # tools/import/core/common.py -> the repository
IMPORT = os.path.join(REPO, 'tools', 'import')
def _settings():
    p = os.environ.get('SR3_SETTINGS') or os.path.join(IMPORT, 'settings.json')
    try: return json.load(open(p, encoding='utf-8-sig'))
    except (OSError, ValueError): return {}
SETTINGS = {k: (os.path.normpath(v) if isinstance(v, str) and v and k in ('data_root', 'work_root', 'classic_root', 'roms', 'sr3_game', 'blender', 'mame', 'revo_demo_tracks', 'revo_ps3_converted_tracks', 'ps3_usrdir') else v)
            for k, v in _settings().items()}        # one spelling of every folder, however the file writes it
def _game():
    """SEGA Rally 3's folder (the one with Rally.exe): settings 'sr3_game', else the launcher's own setup.yaml (PLAY.bat writes it)"""
    if SETTINGS.get('sr3_game'): return SETTINGS['sr3_game']
    try:
        for ln in open(os.path.join(REPO, 'setup.yaml'), encoding='utf-8-sig'):
            if ln.startswith('game:'): return os.path.dirname(ln.split(':', 1)[1].strip().strip('\'"'))
    except OSError: pass
    return os.path.join(REPO, 'game')
GAME = _game()
TRACKS = os.path.join(GAME, "Main_release", "tracks")
DEMO = SETTINGS.get('revo_demo_tracks', '')                    # research only: the SEGA Rally Revo PC demo's Main_release\tracks
CONV = SETTINGS.get('revo_ps3_converted_tracks', '')           # research only: the PS3 -> PC converter's output
DATA = SETTINGS.get('data_root') or os.path.join(REPO, 'data')  # builds, ROM extracts, textures: never in git
WORK = SETTINGS.get('work_root') or os.path.join(DATA, 'work')
CLASSIC = SETTINGS.get('classic_root') or os.path.join(DATA, 'classic')
OUT = os.path.join(WORK, "out")
TMP = os.path.join(WORK, "tmp")
ROMS = SETTINGS.get('roms') or os.path.join(REPO, 'roms')     # the folder with your own srallyc.zip (and daytona.zip, srally2.zip)
BLENDER = SETTINGS.get('blender', '')
def rom_zip(name): return os.path.join(ROMS, name + '.zip')
PATCHZIP_AUTO = True; _PATCHZIP_SEEN = set()
def courses_dir(game):
    """course settings and patch files of one game: tools/import/<game>/tracks/courses. The patch files ship zipped (patchzip.py): the
    first call of a process for a folder unpacks what is missing or out of date there (a few milliseconds when nothing is; the stack
    does it in its own first step)"""
    d = os.path.join(IMPORT, game, 'tracks', 'courses')
    if PATCHZIP_AUTO and d not in _PATCHZIP_SEEN:
        _PATCHZIP_SEEN.add(d); import patchzip; patchzip.unpack(d, print)
    return d
def threads():
    """worker count: settings 'threads' = "all", "all_but_one" (default) or a number"""
    n = os.cpu_count() or 1; t = SETTINGS.get('threads', 'all_but_one')
    if t == 'all': return n
    if isinstance(t, int) or str(t).isdigit(): return max(1, min(n, int(t)))
    return max(1, n - 1)
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

_HYPOT = []
def hypot(x, y):
    """the C runtime's hypot (ucrtbase), as np.hypot is: Python's math.hypot gives other last bits in 17% of cases (kb 31)"""
    if not _HYPOT:
        import ctypes
        f = ctypes.CDLL('ucrtbase').hypot; f.argtypes = [ctypes.c_double, ctypes.c_double]; f.restype = ctypes.c_double; _HYPOT.append(f)
    return _HYPOT[0](x, y)
def nearest2d_plain(P, Q, cell=4.0):
    """nearest2d on Python numbers: P, Q rows of (x, z); -> (indices, distances) as lists, the same as nearest2d's"""
    import collections, math
    P = [(float(p[0]), float(p[1])) for p in P]; b = collections.defaultdict(list)
    for i, (x, z) in enumerate(P): b[(math.floor(x / cell), math.floor(z / cell))].append(i)
    idx = []; dist = []
    for q in Q:
        qx, qz = float(q[0]), float(q[1]); cx, cz = math.floor(qx / cell), math.floor(qz / cell); r = 1; got = (0, math.inf)
        while True:
            cand = [i for dx in range(-r, r + 1) for dz in range(-r, r + 1) for i in b.get((cx + dx, cz + dz), ())]
            if cand:
                d = [hypot(P[i][0] - qx, P[i][1] - qz) for i in cand]; k = d.index(min(d))      # np.argmin: the first of equals
                if d[k] <= r * cell or r > 64: got = (cand[k], d[k]); break
            r += 1
            if r > 200: break
        idx.append(got[0]); dist.append(got[1])
    return idx, dist

if __name__ == '__main__':      # python common.py --paths tracks out ... : those folders, one per line (for the PowerShell and shell scripts)
    _named = dict(game=GAME, tracks=TRACKS, work=WORK, out=OUT, tmp=TMP, classic=CLASSIC, data=DATA, roms=ROMS, blender=BLENDER, repo=REPO, threads=str(threads()))
    for _k in sys.argv[2:] if sys.argv[1:2] == ['--paths'] else sorted(_named): print(_named[_k] if sys.argv[1:2] == ['--paths'] else '%s = %s' % (_k, _named[_k]))
