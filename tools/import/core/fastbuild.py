"""fastbuild.py - the slow loops of build_classic.py on whole arrays / in C (fastgeo.c). Nothing here decides anything new: every
function is a port of the build_classic function of the same name and must return what that one returns.

    import fastbuild; fastbuild.install(build_classic)      # once, before the build starts (e.g. the last line of build_classic.py)

install() replaces these names in build_classic (the originals stay reachable as build_classic._old_<name>):
    Near             class: nearest centre-line point (the ring search of the original, in C, all points of a call at once)
    AttrField        class: at2 / at (the triangle under a point) in C
    road_height      at(pts) on arrays instead of a loop per point
    split_faces      pieces of at most maxlen: the grid of each face in one go
    drape            the same, laid on the road: all faces of a call in one go
    oriented_normals, smooth_normals      per polygon sums and the mean per corner on arrays
    uv_split         faces that fit (nearly all) are recognised on arrays; the others go through the original's own steps
    world_area       plain arithmetic instead of np.cross per corner
SR3_FASTGEO=0 makes install() do nothing; SR3_FASTGEO_CHECK=1 runs old and new side by side and counts differences (fastgeo.REPORT).

NOT installed, because faces_to_mesh is one long function that is still being worked on - three helpers for its three per-face / per-vertex
loops, each tested against the loop it stands for (same bytes):
    quads, uvs, clamp = mesh_uv(faces, uv_mode)      the first loop (None = keep the loop); make_verts_safe takes the quads array as it is
    apply_smooth(nv_, v['p'], SMOOTH_N)              the SMOOTH_N loop
    v['uv0'] = pack_uv(uvs)                          the last loop

Measured 2026-10-08, Mountain, plain build: with everything above installed the built files are the original's byte for byte. Where the
original takes np.linalg.norm of three numbers, numpy goes through BLAS, which adds them as (x*x + z*z) + y*y for a freshly made array:
norm3() below does the same (see there)."""
import math, collections, ctypes
import numpy as np
import fastgeo
from fastgeo import _p

def norm3(v):
    """np.linalg.norm of every row of v (n x 3) as numpy returns it for ONE freshly made 3-vector: sqrt((x*x + z*z) + y*y).
    That order is what numpy's BLAS does with three numbers that start on a 16-byte boundary (every array numpy allocates does); measured
    2026-10-08 with numpy 1.24.3: 60 000 of 60 000 equal to the last bit, against 53 000 for x*x + y*y + z*z. With it the pieces below give
    the bytes of the original; if another numpy adds in another order the results differ in the last bit only."""
    return np.sqrt((v[:, 0] * v[:, 0] + v[:, 2] * v[:, 2]) + v[:, 1] * v[:, 1])

# ---------------------------------------------------------------- Near
class Near:
    """build_classic.Near: nearest2d with the bucket grid built once"""
    def __init__(self, P, cell=8.0):
        self.P = np.asarray(P, float); self.cell = cell; self._P = np.ascontiguousarray(self.P[:, :2], np.float64); self.L = fastgeo.lib()
        self.h = self.L.fg_near_build(_p(self._P), len(self._P), float(cell))
        if not self.h: raise ValueError('fastbuild.Near: grid too large')
    def __del__(self):
        try:
            if self.h: self.L.fg_near_free(self.h); self.h = None
        except Exception: pass
    def __call__(self, Q):
        Q = np.asarray(Q, float); m = len(Q); out = np.zeros(m, np.int64)
        if m: q = np.ascontiguousarray(Q[:, :2], np.float64); self.L.fg_near_query(self.h, _p(q), m, _p(out))
        return out.astype(int)

# ---------------------------------------------------------------- AttrField
def _attrfield_class(BC):
    import build_more as BM
    class AttrField(BM.HeightField):
        """build_classic.AttrField / build_more.HeightField: the grid and the look-up in C"""
        def __init__(self, tris, cell=8.0):
            self.t = np.array([t for a, t in tris]); self.attr = [a for a, t in tris]; self.cell = cell; self.L = fastgeo.lib(); self.h = None
            self._T = np.ascontiguousarray(self.t, np.float64).reshape(-1, 9); self.h = self.L.fg_hf_build(_p(self._T), len(self._T), float(cell))
            if not self.h: raise ValueError('fastbuild.AttrField: grid too large')
            self._y = ctypes.c_double(0.0); self._py = ctypes.byref(self._y); self._f = self.L.fg_hf_at
        def __del__(self):
            try:
                if self.h: self.L.fg_hf_free(self.h); self.h = None
            except Exception: pass
        def at2(self, x, z, yref):
            i = self._f(self.h, x, z, yref, 0, self._py)
            return None if i < 0 else (np.float64(self._y.value), self.attr[i])
        def at(self, x, z, yref=None):
            i = self._f(self.h, x, z, 0.0 if yref is None else yref, 1 if yref is None else 0, self._py)
            return None if i < 0 else np.float64(self._y.value)
    return AttrField

# ---------------------------------------------------------------- road_height
def _road_height(BC):
    def road_height(rd):
        """-> function (points n x 3) -> height of the SR3 road surface (bilinear in the slice / column grid)"""
        V = rd['V']; hw = rd['hw']; cen = V[:, hw]; n = len(V); D = rd['D']; lat = rd['lat']
        near = BC.Near(cen[:, [0, 2]]); Vy = np.ascontiguousarray(V[:, :, 1])
        def at(pts):
            pts = np.asarray(pts, float); i = near(pts[:, [0, 2]])
            if not len(pts): return np.zeros(0)
            d0 = pts[:, 0] - cen[i, 0]; d1 = pts[:, 2] - cen[i, 2]; a = d0 * D[i, 0] + d1 * D[i, 2]; c = (d0 * lat[i, 0] + d1 * lat[i, 2]) + hw
            c = np.minimum(np.maximum(c, 0.0), 2 * hw - 1e-6); k = c.astype(np.int64); fc = c - k; j = (i + np.where(a >= 0, 1, -1)) % n; fa = np.minimum(np.abs(a), 1.0)
            y0 = Vy[i, k] * (1 - fc) + Vy[i, k + 1] * fc; y1 = Vy[j, k] * (1 - fc) + Vy[j, k + 1] * fc
            return y0 * (1 - fa) + y1 * fa
        return at
    return road_height

# ---------------------------------------------------------------- split_faces / drape
def _quads(faces):
    """corners and uv of every face as (n, 4, 3) and (n, 4, 2): the first four corners, a triangle's third corner twice"""
    X, off, lens = fastgeo.pack(faces, 2); U = np.array([u for fc in faces for u in fc[3]], np.float64).reshape(-1, 2); lu = np.fromiter((len(fc[3]) for fc in faces), np.int64, len(faces))
    if (lens < 3).any() or (lu != lens).any(): return None
    uo = np.zeros(len(faces) + 1, np.int64); np.cumsum(lu, out=uo[1:]); ix = np.stack([np.zeros(len(faces), np.int64), np.ones(len(faces), np.int64), np.full(len(faces), 2, np.int64), np.where(lens == 3, 2, 3)], 1)
    return X[off[:-1][:, None] + ix], U[uo[:-1][:, None] + ix]
def _pieces(faces, maxlen, hfun=None, lift=0.0):
    """split_faces (hfun None) / drape: -> list of faces, or None when the input is not what this code expects"""
    nf = len(faces)
    if not nf: return []
    try: r = _quads(faces)
    except (ValueError, TypeError): r = None
    if r is None: return None
    P, U = r; L = lambda a, b: norm3(P[:, a] - P[:, b])
    lu = np.maximum(L(1, 0), L(2, 3)); lv = np.maximum(L(3, 0), L(2, 1)); n = np.maximum(1, np.ceil(lu / maxlen).astype(np.int64)); m = np.maximum(1, np.ceil(lv / maxlen).astype(np.int64))
    for f in np.nonzero(n * m > 900)[0].tolist():
        n_, m_ = int(n[f]), int(m[f]); sc = (900.0 / (n_ * m_)) ** 0.5; n[f] = max(1, int(n_ * sc)); m[f] = max(1, int(m_ * sc))
    cnt = n * m; off = np.zeros(nf + 1, np.int64); np.cumsum(cnt, out=off[1:]); tot = int(off[-1]); OP = np.zeros((tot, 4, 3)); OU = np.zeros((tot, 4, 2)); key = n * 100000 + m
    for kv in np.unique(key).tolist():
        ff = np.nonzero(key == kv)[0]; n_, m_ = kv // 100000, kv % 100000; a = (np.arange(n_ + 1) / n_)[None, :, None, None]; b = (np.arange(m_ + 1) / m_)[None, None, :, None]
        def grid(A): return (A[:, 0][:, None, None, :] * (1 - a) + A[:, 1][:, None, None, :] * a) * (1 - b) + (A[:, 3][:, None, None, :] * (1 - a) + A[:, 2][:, None, None, :] * a) * b
        G = grid(P[ff]); T = grid(U[ff])
        if hfun is not None: G[..., 1] = np.asarray(hfun(G.reshape(-1, 3))).reshape(G.shape[:3]) + lift
        rows = (off[ff][:, None, None] + (np.arange(n_) * m_)[None, :, None] + np.arange(m_)[None, None, :]).ravel()
        OP[rows] = np.stack([G[:, :-1, :-1], G[:, 1:, :-1], G[:, 1:, 1:], G[:, :-1, 1:]], 3).reshape(-1, 4, 3); OU[rows] = np.stack([T[:, :-1, :-1], T[:, 1:, :-1], T[:, 1:, 1:], T[:, :-1, 1:]], 3).reshape(-1, 4, 2)
    tp = list(map(tuple, OP.reshape(-1, 3))); tu = list(map(tuple, OU.reshape(-1, 2))); out = []; q = 0     # (tuples of numpy numbers, as the original makes them)
    for fc, c in zip(faces, cnt.tolist()):
        mat = fc[0]; sec = fc[1]
        for _ in range(c): out.append((mat, sec, tp[q:q + 4], tu[q:q + 4])); q += 4
    return out
def _same_faces(a, b, tol=0.0):
    if len(a) != len(b): return False
    for x, y in zip(a, b):
        if x[0] != y[0] or x[1] != y[1] or len(x[2]) != len(y[2]) or len(x[3]) != len(y[3]): return False
        if tol:
            if not (np.allclose(np.asarray(x[2], float), np.asarray(y[2], float), rtol=0, atol=tol) and np.allclose(np.asarray(x[3], float), np.asarray(y[3], float), rtol=0, atol=tol)): return False
        elif x[2] != y[2] or x[3] != y[3]: return False
    return True
def _split_faces(BC):
    def split_faces(faces, maxlen):
        """faces cut to quads of at most maxlen per side, uv interpolated (triangles become quads with a repeated corner)"""
        out = _pieces(faces, maxlen)
        if out is None: return BC._old_split_faces(faces, maxlen)
        if fastgeo.CHECK: old = BC._old_split_faces(faces, maxlen); fastgeo.note('build_classic.split_faces', _same_faces(old, out), (len(old), len(out))); fastgeo.note('build_classic.split_faces: number of pieces', len(old) == len(out), (len(old), len(out)))
        return out
    return split_faces
def _drape(BC):
    def drape(faces, hfun, lift, maxlen=1.0):
        """cut faces to pieces of at most maxlen (uv interpolated) and lay them on the SR3 road, lift metres above it"""
        out = _pieces(faces, maxlen, hfun, lift)
        if out is None: return BC._old_drape(faces, hfun, lift, maxlen)
        if fastgeo.CHECK: old = BC._old_drape(faces, hfun, lift, maxlen); fastgeo.note('build_classic.drape', _same_faces(old, out), (len(old), len(out))); fastgeo.note('build_classic.drape: number of pieces', len(old) == len(out), (len(old), len(out)))
        return out
    return drape

# ---------------------------------------------------------------- normals
def _wn(X, off, lens):
    """per polygon: sum over the corners of (A[1,2,0] - B[1,2,0]) * (A[2,0,1] + B[2,0,1]), B = the next corner (added corner by corner, as numpy adds the rows), and the mean corner"""
    n = np.zeros((len(lens), 3)); c = np.zeros((len(lens), 3))
    for k, ii in fastgeo.by_len(lens):
        P = X[off[ii][:, None] + np.arange(k)[None, :]]; B = np.roll(P, -1, axis=1); T = (P[:, :, [1, 2, 0]] - B[:, :, [1, 2, 0]]) * (P[:, :, [2, 0, 1]] + B[:, :, [2, 0, 1]]); w = T[:, 0].copy(); s = P[:, 0].copy()
        for i in range(1, k): w = w + T[:, i]; s = s + P[:, i]
        n[ii] = w; c[ii] = s / k
    return n, c
def _oriented(BC, X, off, lens, n, c):
    n = n / np.maximum(np.sqrt(n[:, 0] * n[:, 0] + n[:, 1] * n[:, 1] + n[:, 2] * n[:, 2]), 1e-12)[:, None]
    lying = np.abs(n[:, 1]) > 0.3; n[lying & (n[:, 1] < 0)] *= -1.0
    up_ = np.nonzero(~lying)[0]; ROADPTS = BC.ROADPTS
    if BC.GROUND_AT is not None and len(up_):                         # (as the original; see there for what this rule is)
        h = n[up_][:, [0, 2]]; h /= np.maximum(np.linalg.norm(h, axis=1), 1e-9)[:, None]; base = np.minimum.reduceat(X[:, 1], off[:-1])[up_]
        ya = BC.GROUND_AT(c[up_][:, 0] + 2.0 * h[:, 0], c[up_][:, 2] + 2.0 * h[:, 1], base); yb = BC.GROUND_AT(c[up_][:, 0] - 2.0 * h[:, 0], c[up_][:, 2] - 2.0 * h[:, 1], base)
        ha = ya > -900.0; hb = yb > -900.0
        flip = hb & (~ha | (yb > ya + 0.3)); same = (~ha & ~hb) | (ha & hb & (np.abs(ya - yb) <= 0.3)); n[up_[flip]] *= -1.0; up_ = up_[same]
    if len(up_):                                                       # the nearest road point of every upright polygon (the original: a distance table per 2000 polygons)
        ix = up_; to = ROADPTS[fastgeo.argmin2(c[ix][:, [0, 2]], ROADPTS)] - c[ix][:, [0, 2]]
        flip = (n[ix, 0] * to[:, 0] + n[ix, 2] * to[:, 1]) < 0; n[ix[flip]] *= -1.0
    return n
def _oriented_normals(BC):
    def oriented_normals(quads):
        """unit normal per polygon, turned to the side that is SEEN (build_classic.oriented_normals)"""
        if not len(quads): return np.zeros((0, 3))
        X, off, lens = fastgeo.pack(quads, None); w, c = _wn(X, off, lens); out = _oriented(BC, X, off, lens, w, c)
        if fastgeo.CHECK: old = BC._old_oriented_normals(quads); fastgeo.note('build_classic.oriented_normals', np.allclose(old, out, rtol=0, atol=1e-12), float(np.abs(old - out).max()))
        return out
    return oriented_normals
def _smooth_normals(BC):
    def smooth_normals(faces):
        """-> {corner: unit normal}: the area-weighted mean of the oriented normals of the given faces round each corner"""
        if not len(faces): return {}
        X, off, lens = fastgeo.pack(faces, 2); w, c = _wn(X, off, lens); n = _oriented(BC, X, off, lens, w, c); ar = norm3(w)
        R = np.round(X, 2); N = np.rint(R * 100.0).astype(np.int64)
        if int(np.abs(N).max()) >= (1 << 20): return BC._old_smooth_normals(faces)
        code = ((N[:, 0] + (1 << 20)) << 42) | ((N[:, 1] + (1 << 20)) << 21) | (N[:, 2] + (1 << 20)); uq, first, inv = np.unique(code, return_index=True, return_inverse=True)
        order = np.argsort(first, kind='stable'); rank = np.zeros(len(uq), np.int64); rank[order] = np.arange(len(uq)); inv = rank[inv]; first = first[order]      # keys in the order they first appear, as a dict keeps them
        W = (n * ar[:, None])[np.repeat(np.arange(len(lens)), lens)]; acc = np.stack([np.bincount(inv, weights=W[:, q], minlength=len(uq)) for q in range(3)], 1)      # (bincount adds in the order of the corners, as the original's loop)
        acc = acc / np.maximum(norm3(acc), 1e-12)[:, None]
        out = dict(zip(map(tuple, R[first]), acc))
        if fastgeo.CHECK:
            old = BC._old_smooth_normals(faces); same = list(old) == list(out) and np.allclose(np.array(list(old.values())), np.array(list(out.values())), rtol=0, atol=1e-9)
            fastgeo.note('build_classic.smooth_normals', same, (len(old), len(out)))
        return out
    return smooth_normals

# ---------------------------------------------------------------- uv_split
def _uv_fits(faces, maxspan):
    """per face: (lo - floor(lo + 1e-6) + span).max() <= maxspan with v turned (the test uv_split makes twice per face), on arrays; None = cannot"""
    n = len(faces); lu = np.fromiter((len(fc[3]) for fc in faces), np.int64, n)
    try: U = np.array([u for fc in faces for u in fc[3]], np.float64).reshape(-1, 2)
    except (ValueError, TypeError): return None
    if len(U) != int(lu.sum()) or (n and int(lu.min()) < 1): return None
    U[:, 1] = 1.0 - U[:, 1]; st = np.zeros(n, np.int64); np.cumsum(lu[:-1], out=st[1:]); lo = np.minimum.reduceat(U, st, axis=0); hi = np.maximum.reduceat(U, st, axis=0)
    return (lo - np.floor(lo + 1e-6) + (hi - lo)).max(1) <= maxspan
def _uv_split(BC):
    def uv_split(faces, maxspan=1.999):
        """faces whose uv span exceeds what the u16 uv (0..2 repeats) can hold are cut along their edges until every piece fits
        (the original, with its test made for all faces at once: nearly all fit and are passed on untouched)"""
        ok = _uv_fits(faces, maxspan) if len(faces) else None
        if ok is None: return BC._old_uv_split(faces, maxspan)
        out = []; n = 0; known = []
        def fits(UV):
            u = np.array(UV, float); u[:, 1] = 1.0 - u[:, 1]; lo = u.min(0); return (lo - np.floor(lo + 1e-6) + np.ptp(u, axis=0)).max() <= maxspan
        for (mat, sec, P, UV), f in zip(faces, ok.tolist()):
            if f: out.append((mat, sec, P, UV)); known.append(True); continue
            u = np.array(UV, float); u[:, 1] = 1.0 - u[:, 1]; sp = np.ptp(u, axis=0)
            k = int(np.ceil(sp.max() / 0.999)); n += 1
            if len(P) == 3: P = list(P) + [P[2]]; UV = list(UV) + [UV[2]]
            Pa = np.array(P[:4], float); Ua = np.array(UV[:4], float)
            def pt(A, a, b): return (A[0] * (1 - a) + A[1] * a) * (1 - b) + (A[3] * (1 - a) + A[2] * a) * b
            for i in range(k):
                for j in range(k):
                    c = [(i / k, j / k), ((i + 1) / k, j / k), ((i + 1) / k, (j + 1) / k), (i / k, (j + 1) / k)]
                    out.append((mat, sec, [tuple(pt(Pa, a, b)) for a, b in c], [tuple(pt(Ua, a, b)) for a, b in c])); known.append(None)
        done = []; todo = []
        for fc, kn in zip(out, known): (done if (kn or (kn is None and fits(fc[3]))) else todo).append(fc)
        todo = [(m_, s_, [P_[i] for i in t_], [UV_[i] for i in t_]) for m_, s_, P_, UV_ in todo for t_ in (((0, 1, 2), (0, 2, 3)) if len(P_) >= 4 else ((0, 1, 2),))]
        for depth in range(12):
            nxt = []
            for m_, s_, P_, UV_ in todo:
                if fits(UV_): done.append((m_, s_, P_, UV_)); continue
                P3 = np.array(P_, float); U3 = np.array(UV_, float); k_ = int(np.argmax([np.abs(U3[(i + 1) % 3] - U3[i]).max() for i in range(3)])); a_, b_, c_ = k_, (k_ + 1) % 3, (k_ + 2) % 3
                pm = tuple((P3[a_] + P3[b_]) / 2); um = tuple((U3[a_] + U3[b_]) / 2)
                nxt += [(m_, s_, [P_[a_], pm, P_[c_]], [UV_[a_], um, UV_[c_]]), (m_, s_, [pm, P_[b_], P_[c_]], [um, UV_[b_], UV_[c_]])]
            todo = nxt
            if not todo: break
        res = (done + todo, n)
        if fastgeo.CHECK: old = BC._old_uv_split(faces, maxspan); fastgeo.note('build_classic.uv_split', old[1] == res[1] and _same_faces(old[0], res[0]), (len(old[0]), len(res[0]), old[1], res[1]))
        return res
    return uv_split

# ---------------------------------------------------------------- pieces of faces_to_mesh
def mesh_uv(faces, uv_mode):
    """the first loop of build_classic.faces_to_mesh on arrays: -> (quads n x 4 x 3, uv n x 4 x 2 in repeats, number of clamped faces); None = cannot
    (a face of other than 3 or 4+ corners, or with another number of uv than corners). meshgen.make_verts_safe takes the quads array as it is."""
    n = len(faces)
    if not n: return np.zeros((0, 4, 3)), np.zeros((0, 4, 2)), 0
    try: r = _quads(faces)
    except (ValueError, TypeError): r = None
    if r is None: return None
    Q, u = r; clamp = 0
    if uv_mode == 'given': pass
    elif uv_mode == 'tile':
        u[:, :, 1] = 1.0 - u[:, :, 1]; u -= np.floor(u.min(1) + 1e-6)[:, None, :]; big = u.max((1, 2)) > 1.999; clamp = int(big.sum()); u[big] = np.clip(u[big], 0, 1.999)
    else: u = np.tile(np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float), (n, 1, 1))
    over = u.max(1) > 1.00002; u -= np.where(over, 1.0, 0.0)[:, None, :]
    return Q, u, clamp
def pack_uv(u):
    """the last loop of faces_to_mesh: uv in repeats (n x 4 x 2) -> the u16 pairs of v['uv0'] (4 n x 2)"""
    return np.clip(np.round(np.asarray(u, float).reshape(-1, 2) * 32768), -32768, 32767).astype(np.int16).view(np.uint16)
_SM = {}
def apply_smooth(nv_, p, SMOOTH_N):
    """the SMOOTH_N loop of faces_to_mesh: nv_ (n x 3 float64, changed in place) takes the smooth normal of its corner, on its own side.
    p = v['p'] (float32 positions). The corner table is made into sorted whole numbers once per SMOOTH_N dict."""
    if not SMOOTH_N or not len(nv_): return nv_
    t = _SM.get('t')
    if t is None or t[0] is not SMOOTH_N or t[1] != len(SMOOTH_N):
        K = np.array(list(SMOOTH_N.keys()), np.float64).reshape(-1, 3); Vv = np.array(list(SMOOTH_N.values()), np.float64).reshape(-1, 3); N = np.rint(K * 100.0).astype(np.int64)
        big = int(np.abs(N).max()) >= (1 << 20); code = ((N[:, 0] + (1 << 20)) << 42) | ((N[:, 1] + (1 << 20)) << 21) | (N[:, 2] + (1 << 20)); o = np.argsort(code, kind='stable')
        t = (SMOOTH_N, len(SMOOTH_N), code[o], Vv[o], big); _SM['t'] = t
    P_ = np.round(np.asarray(p)[:, :3].astype(np.float64), 2); N = np.rint(P_ * 100.0).astype(np.int64)
    if t[4] or int(np.abs(N).max()) >= (1 << 20):                      # (coordinates beyond 10 km: the original loop)
        for k_ in range(len(P_)):
            q_ = SMOOTH_N.get((P_[k_, 0], P_[k_, 1], P_[k_, 2]))
            if q_ is not None: nv_[k_] = q_ if float(q_ @ nv_[k_]) >= 0.0 else -q_
        return nv_
    code = ((N[:, 0] + (1 << 20)) << 42) | ((N[:, 1] + (1 << 20)) << 21) | (N[:, 2] + (1 << 20)); i = np.searchsorted(t[2], code); i[i >= len(t[2])] = len(t[2]) - 1; hit = t[2][i] == code
    q = t[3][i[hit]]; s = (q * nv_[hit]).sum(1); nv_[hit] = np.where((s >= 0.0)[:, None], q, -q)
    return nv_

# ---------------------------------------------------------------- world_area
def _world_area(BC):
    def world_area(P):
        """area of a polygon in space (build_classic.world_area: np.cross per corner, 110 microseconds a polygon; here plain arithmetic)"""
        Q = P.tolist() if isinstance(P, np.ndarray) else [(float(p[0]), float(p[1]), float(p[2])) for p in P]; x = y = z = 0.0; k = len(Q)
        for i in range(k): a = Q[i]; b = Q[(i + 1) % k]; x += a[1] * b[2] - a[2] * b[1]; y += a[2] * b[0] - a[0] * b[2]; z += a[0] * b[1] - a[1] * b[0]
        r = 0.5 * math.sqrt((x * x + z * z) + y * y)                   # (the order numpy's norm adds in, see norm3)
        if fastgeo.CHECK: o = BC._old_world_area(P); fastgeo.note('build_classic.world_area', abs(o - r) <= 1e-12 * max(1.0, abs(o)), (o, r))
        return r
    return world_area

# ---------------------------------------------------------------- install
NAMES = ('Near', 'AttrField', 'road_height', 'split_faces', 'drape', 'oriented_normals', 'smooth_normals', 'uv_split', 'world_area')
def install(BC, names=NAMES):
    """replace the slow functions of build_classic (module BC) by the ones above; the originals stay as BC._old_<name>"""
    if not fastgeo.ON or getattr(BC, '_fastbuild', False): return False
    new = dict(Near=Near, AttrField=_attrfield_class(BC), road_height=_road_height(BC), split_faces=_split_faces(BC), drape=_drape(BC), oriented_normals=_oriented_normals(BC), smooth_normals=_smooth_normals(BC), uv_split=_uv_split(BC), world_area=_world_area(BC))
    for k in names:
        setattr(BC, '_old_' + k, getattr(BC, k)); setattr(BC, k, new[k])
    if fastgeo.CHECK: _check_classes(BC)
    BC._fastbuild = True; return True

def _check_classes(BC):
    """SR3_FASTGEO_CHECK=1: Near and AttrField answer from the old and the new class and compare"""
    NewNear, OldNear, NewAF, OldAF = BC.Near, BC._old_Near, BC.AttrField, BC._old_AttrField
    class CNear:
        def __init__(self, P, cell=8.0): self.a = OldNear(P, cell); self.b = NewNear(P, cell); self.P = self.b.P; self.cell = cell
        def __call__(self, Q): a = self.a(Q); b = self.b(Q); fastgeo.note('build_classic.Near', a.dtype == b.dtype and np.array_equal(a, b), int((a != b).sum()) if len(a) == len(b) else -1); return b
    class CAF(OldAF):
        def __init__(self, tris, cell=8.0): OldAF.__init__(self, tris, cell); self.n_ = NewAF(tris, cell)
        def at2(self, x, z, yref): a = OldAF.at2(self, x, z, yref); b = self.n_.at2(x, z, yref); fastgeo.note('build_classic.AttrField.at2', a == b and (a is None or type(a[0]) is type(b[0])), (a, b)); return b
        def at(self, x, z, yref=None): a = OldAF.at(self, x, z, yref); b = self.n_.at(x, z, yref); fastgeo.note('build_more.HeightField.at', a == b, (a, b)); return b
    BC.Near = CNear; BC.AttrField = CAF
