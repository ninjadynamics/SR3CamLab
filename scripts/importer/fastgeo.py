"""fastgeo.py - the importer's per-polygon loops on whole arrays (fastgeo.c, compiled with gcc on first use, like rays.py).

Nothing here decides anything new: every function is a port of a loop in overlay_bake / fill1995 / gapfill_weld / lightside and
must return what that loop returned. The callers keep their old code as _old_<name>.

    SR3_FASTGEO=0        every caller uses its old Python code (to time or compare a build without this module)
    SR3_FASTGEO_CHECK=1  every caller runs BOTH and counts the differences; the counts are printed when the build ends

    X, off = pack(faces)                       corners of all polygons in one array; polygon i = X[off[i]:off[i + 1]]
    G = prep(faces)                            G.nr (unit normal, Newell), G.ar (area), G.cen (mean corner), G.lo / G.hi (box), G.X, G.off, G.lens
    pairs = find_pairs(...)                    overlay_bake.find_pairs (None = this code cannot do it, use the old one)
    IndexC(faces, cell)                        fill1995.Index: heights(x, z, opaque_only), uprights(x, z, r)
    LyingC(faces, skip)                        gapfill_weld.Lying: near(p3, reach, dy)
    lstsq_batch(A, B)                          np.linalg.lstsq(a, b, rcond=None)[0] for a stack of small systems (the same LAPACK routine)
"""
import os, sys, ctypes, subprocess, itertools, collections, atexit
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.join(HERE, 'fastgeo.c'); GCC = r'C:\mingw64\bin\gcc.exe'
ON = os.environ.get('SR3_FASTGEO', '1') != '0'
CHECK = os.environ.get('SR3_FASTGEO_CHECK', '0') == '1'
REPORT = collections.Counter()                                          # CHECK: 'name: calls' / 'name: DIFFERENT ...'
EXAMPLES = []
def note(name, same, detail=None):
    REPORT[name + ': calls'] += 1
    if not same:
        REPORT[name + ': DIFFERENT'] += 1
        if len(EXAMPLES) < 60: EXAMPLES.append((name, detail))
def _report():
    if CHECK:
        print('fastgeo check: %s' % dict(sorted(REPORT.items())))
        for e in EXAMPLES: print('   fastgeo difference: %s %s' % (e[0], str(e[1])[:600]))
atexit.register(_report)

_lib = None
def lib():
    global _lib
    if _lib is None:
        import hashlib, glob
        DLL = os.path.join(HERE, 'fastgeo.%s.dll' % hashlib.md5(open(SRC, 'rb').read()).hexdigest()[:8])      # one file per version of the source: a running build keeps its DLL loaded (Windows will not replace it), a build started after an edit gets its own
        if not os.path.exists(DLL):
            tmp = DLL + '.%d.tmp' % os.getpid(); r = subprocess.run([GCC, '-O3', '-march=native', '-ffp-contract=off', '-fopenmp', '-shared', '-o', tmp, SRC], capture_output=True, text=True)
            if r.returncode != 0: raise RuntimeError('fastgeo.c does not compile: ' + r.stderr[-1500:])
            try: os.replace(tmp, DLL)
            except OSError: os.remove(tmp)                                # (another build got there first and has it loaded)
            for old in glob.glob(os.path.join(HERE, 'fastgeo.*.dll')) + [os.path.join(HERE, 'fastgeo.dll')]:      # versions nobody has loaded any more
                if old != DLL:
                    try: os.remove(old)
                    except OSError: pass
        os.add_dll_directory(os.path.dirname(GCC)); L = ctypes.CDLL(DLL); P = ctypes.c_void_p; LL = ctypes.c_longlong; D = ctypes.c_double; I = ctypes.c_int
        L.fg_threads.restype = I; L.fg_init.restype = I; L.fg_init()
        L.fg_prep.argtypes = [P, P, LL, P, P, P, P, P]; L.fg_prep.restype = None
        L.fg_far.argtypes = [P, LL, P, LL, D, P]; L.fg_far.restype = None
        L.fg_mindist2.argtypes = [P, LL, P, LL, P]; L.fg_mindist2.restype = None
        L.fg_components.argtypes = [LL, P, P, LL, LL, P]; L.fg_components.restype = I
        L.fg_init2.restype = I; L.fg_init2(); L.fg_argmin2.argtypes = [P, LL, P, LL, P]; L.fg_argmin2.restype = None
        L.fg_near_build.argtypes = [P, LL, D]; L.fg_near_build.restype = P; L.fg_near_free.argtypes = [P]; L.fg_near_free.restype = None; L.fg_near_query.argtypes = [P, P, LL, P]; L.fg_near_query.restype = None
        L.fg_hf_build.argtypes = [P, LL, D]; L.fg_hf_build.restype = P; L.fg_hf_free.argtypes = [P]; L.fg_hf_free.restype = None; L.fg_hf_at.argtypes = [P, D, D, D, I, P]; L.fg_hf_at.restype = LL
        L.fg_pairs.argtypes = [P, P, LL, P, P, P, P, P, P, P, P, P, P, D, D, D, D, D, D]; L.fg_pairs.restype = LL
        L.fg_pairs_get.argtypes = [P, P]; L.fg_pairs_get.restype = None
        L.fg_index_build.argtypes = [P, P, LL, P, P, D]; L.fg_index_build.restype = P
        L.fg_index_free.argtypes = [P]; L.fg_index_free.restype = None
        L.fg_index_heights.argtypes = [P, D, D, I, P, P, LL]; L.fg_index_heights.restype = LL
        L.fg_index_uprights.argtypes = [P, D, D, D, P, LL]; L.fg_index_uprights.restype = LL
        L.fg_index_segs.argtypes = [P]; L.fg_index_segs.restype = P; L.fg_index_segfi.argtypes = [P]; L.fg_index_segfi.restype = P; L.fg_index_segcut.argtypes = [P]; L.fg_index_segcut.restype = P
        L.fg_index_counts.argtypes = [P, I]; L.fg_index_counts.restype = LL
        L.fg_lying_build.argtypes = [P, P, LL, P, P, P, P]; L.fg_lying_build.restype = P
        L.fg_lying_free.argtypes = [P]; L.fg_lying_free.restype = None
        L.fg_lying_near.argtypes = [P, D, D, D, D, D, P]; L.fg_lying_near.restype = LL
        _lib = L
    return _lib

def _p(a): return a.ctypes.data_as(ctypes.c_void_p)

# ---------------------------------------------------------------- polygons as arrays
def pack(faces, col=2):
    """-> X (corners x 3, float64), off (n + 1, int64), lens (n). faces: importer faces, or (col=None) a list of corner lists"""
    Ps = faces if col is None else [f[col] for f in faces]; n = len(Ps)
    lens = np.fromiter(map(len, Ps), np.int64, n); off = np.zeros(n + 1, np.int64); np.cumsum(lens, out=off[1:])
    ch = itertools.chain.from_iterable
    try: X = np.fromiter(ch(ch(Ps)), np.float64, 3 * int(off[-1])).reshape(-1, 3)
    except (ValueError, TypeError): X = np.ascontiguousarray(np.array(list(ch(Ps)), np.float64).reshape(-1, 3))
    if len(X) != off[-1] or (n and len(Ps[-1]) and len(Ps[-1][-1]) != 3): raise ValueError('fastgeo.pack: corners are not xyz triples')
    return X, off, lens

class Geo: pass
def prep(faces, col=2, packed=None):
    """normal (overlay_bake._newell: unit, or the raw sum when it is shorter than 1e-12), area, centre, box of every polygon"""
    G = Geo(); G.X, G.off, G.lens = packed if packed is not None else pack(faces, col); n = len(G.lens); G.n = n
    G.nr = np.zeros((n, 3)); G.ar = np.zeros(n); G.cen = np.zeros((n, 3)); G.lo = np.zeros((n, 3)); G.hi = np.zeros((n, 3))
    if n: lib().fg_prep(_p(G.X), _p(G.off), n, _p(G.nr), _p(G.ar), _p(G.cen), _p(G.lo), _p(G.hi))
    return G

def mindist2(P, R):
    """((R - p) ** 2).sum(1).min() for every row p of P (n x 2); R (m x 2)"""
    P = np.ascontiguousarray(P, np.float64).reshape(-1, 2); R = np.ascontiguousarray(R, np.float64).reshape(-1, 2); out = np.empty(len(P))
    if len(P): lib().fg_mindist2(_p(P), len(P), _p(R), len(R), _p(out))
    return out

def argmin2(P, R):
    """((p - R) ** 2).sum(1).argmin() for every row p of P (n x 2); R (m x 2)"""
    P = np.ascontiguousarray(P, np.float64).reshape(-1, 2); R = np.ascontiguousarray(R, np.float64).reshape(-1, 2); out = np.zeros(len(P), np.int64)
    if len(P): lib().fg_argmin2(_p(P), len(P), _p(R), len(R), _p(out))
    return out

def components(nitem, item, node):
    """items that share a node are one group -> label per item (the smallest item of its group)"""
    item = np.ascontiguousarray(item, np.int64); node = np.ascontiguousarray(node, np.int64); label = np.zeros(nitem, np.int64)
    if lib().fg_components(nitem, _p(item), _p(node), len(item), int(node.max()) + 1 if len(node) else 0, _p(label)): raise MemoryError('fastgeo.components')
    return label

def round_keys(X, obj_at, digits=2):
    """the importer's corner keys  round(p[0], 2), round(p[1], 2), round(p[2], 2)  as whole numbers (hundredths) for all corners at once.
    Python rounds a float to the nearest decimal exactly, numpy (which is what round() of a numpy.float64 does) rounds x * 100: the two differ
    only when x * 100 lands on a half, so only those corners are rounded one by one, each as its own type: obj_at(row, axis) -> the number."""
    s = 10.0 ** digits; Y = X * s; N = np.rint(Y); tie = np.abs(np.abs(Y - np.floor(Y)) - 0.5) < 1e-6
    for r, a in zip(*[t.tolist() for t in np.nonzero(tie)]): N[r, a] = np.rint(float(round(obj_at(r, a), digits)) * s)
    return N.astype(np.int64)

def lstsq_batch(A, B):
    """A (m, k, n), B (m, k) -> (m, n): np.linalg.lstsq(A[i], B[i], rcond=None)[0] for every i, by the gufunc np.linalg.lstsq itself calls"""
    A = np.ascontiguousarray(A, np.float64); B = np.ascontiguousarray(B, np.float64); m, k, n = A.shape
    if not m: return np.zeros((0, n))
    try:
        from numpy.linalg import _umath_linalg as U
        g = getattr(U, 'lstsq', None) or (U.lstsq_m if k <= n else U.lstsq_n)
        x = g(A, B[..., None], np.finfo(np.float64).eps * max(n, k), signature='ddd->ddid')[0]
        return np.array(x[..., 0], np.float64)
    except Exception:
        return np.array([np.linalg.lstsq(a, b, rcond=None)[0] for a, b in zip(A, B)])

def by_len(lens):
    """-> [(k, indices of the polygons with k corners)]"""
    return [(int(k), np.nonzero(lens == k)[0]) for k in np.unique(lens)]

# ---------------------------------------------------------------- overlay_bake.find_pairs
def find_pairs(faces, road_xz, single, active, skip_sections, floor, margin, OB, G=None):
    """overlay_bake.find_pairs; None when fastgeo.c cannot take the input (a polygon of more than 24 corners, a grid too large)"""
    road_xz = np.asarray(road_xz, float); n = len(faces)
    if not n: return []
    L = lib(); G = G or prep(faces); ok = G.ar > OB.EPS_AREA
    rd = np.ascontiguousarray(road_xz[::8], np.float64).reshape(-1, 2); far = np.zeros(n)
    if not len(rd): return None
    L.fg_far(_p(G.cen), n, _p(rd), len(rd), float(OB.MAX_VIEW), _p(far)); need0 = OB.K_DEPTH * far ** 2
    sg = np.fromiter(((id(f) in single) or str(f[1]).endswith('~s') for f in faces), np.uint8, n)
    ing = (ok & ~np.fromiter((f[1] in skip_sections for f in faces), bool, n)).astype(np.uint8)
    act = None
    if active is not None: act = np.zeros(n, np.uint8); act[list(active)] = 1
    r = L.fg_pairs(_p(G.X), _p(G.off), n, _p(G.nr), _p(G.ar), _p(G.cen), _p(G.lo), _p(G.hi), _p(need0), _p(far), _p(sg), None if act is None else _p(act), _p(ing),
                   8.0, float(margin), float(floor), float(OB.K_DEPTH), float(OB.FOCAL), float(OB.PIXELS))
    if r == -1: raise MemoryError('fastgeo.find_pairs')
    if r < 0: return None
    ij = np.zeros((max(r, 1), 2), np.int64); v = np.zeros((max(r, 1), 4)); L.fg_pairs_get(_p(ij), _p(v))
    return [(a[0], a[1], b[0], b[1], b[2], b[3]) for a, b in zip(ij[:r].tolist(), v[:r].tolist())]

# ---------------------------------------------------------------- fill1995.Index
class IndexC:
    """fill1995.Index on arrays: the same triangles / segments in the same cells in the same order"""
    def __init__(self, faces, cell=8.0, G=None):
        L = lib(); n = len(faces); G = G or prep(faces); self.L = L; self.h = None
        cut = np.fromiter((f[0].endswith('_t') for f in faces), np.uint8, n)
        self.h = L.fg_index_build(_p(G.X), _p(G.off), n, _p(G.nr), _p(cut), float(cell))
        if not self.h: raise ValueError('fastgeo.IndexC: grid too large')
        ns = L.fg_index_counts(self.h, 1)
        if ns:
            S = np.ctypeslib.as_array(ctypes.cast(L.fg_index_segs(self.h), ctypes.POINTER(ctypes.c_double)), (ns, 6)).copy()
            self.sy0 = list(S[:, 4]); self.sy1 = list(S[:, 5])       # (numpy scalars, as the old code returned them)
            self.sfi = np.ctypeslib.as_array(ctypes.cast(L.fg_index_segfi(self.h), ctypes.POINTER(ctypes.c_longlong)), (ns,)).tolist()
            self.scut = [bool(c) for c in np.ctypeslib.as_array(ctypes.cast(L.fg_index_segcut(self.h), ctypes.POINTER(ctypes.c_ubyte)), (ns,)).tolist()]
        else: self.sy0 = []; self.sy1 = []; self.sfi = []; self.scut = []
        self._grow(512); self.fh = L.fg_index_heights; self.fu = L.fg_index_uprights
    def _grow(self, cap):
        self.cap = cap; self.oy = np.empty(cap); self.ofi = np.empty(cap, np.int64); self.poy = _p(self.oy); self.pofi = _p(self.ofi)
    def __del__(self):
        try:
            if self.h: self.L.fg_index_free(self.h); self.h = None
        except Exception: pass
    def heights(self, x, z, opaque_only=False):
        x = float(x); z = float(z); m = self.fh(self.h, x, z, 1 if opaque_only else 0, self.poy, self.pofi, self.cap)
        if m < 0: self._grow(-m * 2); m = self.fh(self.h, x, z, 1 if opaque_only else 0, self.poy, self.pofi, self.cap)
        if not m: return []
        return list(zip(self.oy[:m], self.ofi[:m].tolist()))
    def uprights(self, x, z, r=0.5):
        x = float(x); z = float(z); m = self.fu(self.h, x, z, r, self.pofi, self.cap)
        if m < 0: self._grow(-m * 2); m = self.fu(self.h, x, z, r, self.pofi, self.cap)
        if not m: return []
        y0 = self.sy0; y1 = self.sy1; fi = self.sfi; cut = self.scut
        return [(y0[k], y1[k], fi[k], cut[k]) for k in self.ofi[:m].tolist()]

# ---------------------------------------------------------------- gapfill_weld.Lying
class LyingC:
    """gapfill_weld.Lying on arrays: lying opaque faces in a 4 m grid, near()"""
    def __init__(self, faces, skip=()):
        L = lib(); self.L = L; self.h = None
        sel = [fc for fc in faces if not (str(fc[0]).endswith('_t') or str(fc[1]).startswith(skip))]
        G = prep(sel); keep = ~((np.abs(G.nr[:, 1]) < 0.3) | (G.ar < 0.01)) if G.n else np.zeros(0, bool)
        kc = np.repeat(keep, G.lens); Xk = G.X[kc]; lens = G.lens[keep]; n = len(lens); off = np.zeros(n + 1, np.int64); np.cumsum(lens, out=off[1:])
        self.H = np.ascontiguousarray(Xk[:, [0, 2]]); self.Y = np.ascontiguousarray(Xk[:, 1]); self.off = off; self.n = n
        self.mat = [fc[0] for fc, k in zip(sel, keep.tolist()) if k]
        self.pos = np.zeros(n, np.uint8); self.pl = np.zeros((n, 3)); self.box = np.zeros((n, 4)); self.C = np.zeros((n, 2))
        for k, ii in by_len(lens):
            idx = off[ii][:, None] + np.arange(k)[None, :]; Q = self.H[idx]; Yq = self.Y[idx]; s = np.zeros(len(ii)); c = Q[:, 0].copy()
            for i in range(k): j = (i + 1) % k; s = s + (Q[:, i, 0] * Q[:, j, 1] - Q[:, j, 0] * Q[:, i, 1])
            for i in range(1, k): c = c + Q[:, i]
            self.pos[ii] = s > 0; self.C[ii] = c / k; self.box[ii, :2] = Q.min(1); self.box[ii, 2:] = Q.max(1)
            self.pl[ii] = lstsq_batch(np.concatenate([Q, np.ones((len(ii), k, 1))], 2), Yq)
        self.h = L.fg_lying_build(_p(self.H), _p(self.off), n, _p(self.Y), _p(self.pos), _p(self.pl), _p(self.box))
        if not self.h: raise ValueError('fastgeo.LyingC: grid too large')
        self.out = np.zeros(5); self.pout = _p(self.out); self.fn = L.fg_lying_near
    def __del__(self):
        try:
            if self.h: self.L.fg_lying_free(self.h); self.h = None
        except Exception: pass
    def near(self, p3, reach=1.5, dy=1.0):
        k = self.fn(self.h, float(p3[0]), float(p3[1]), float(p3[2]), reach, dy, self.pout)
        if k < 0: return None
        g, d, x, z, y = self.out.tolist(); return (g, d, x, z, y, self.mat[k], self.C[k])
