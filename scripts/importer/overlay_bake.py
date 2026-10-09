"""Coplanar and near-coplanar 1995 polygons without offsets (user: zero z-fighting; a lift that is right next to the road
flickers when the same rock is seen from across the course). The Model 2 paints by priority, so its data lays polygons in
ONE plane: ivy on rock (same corners), a window on a wall, a crown board over a trunk board. Here every stack is resolved
IN the plane:

    resolve(faces, pixels, save, road_xz, log) -> faces
      same corners        : opaque on opaque = one of them goes; a cut-out on anything = one face with a composed texture
      upper face opaque   : the lower face is cut back to what the upper one does not cover (nothing hidden is drawn)
      upper face cut-out  : the shared region becomes ONE face with a composed texture (lower texels, upper's opaque texels
                            painted over); what is left of each face stays as it was
      parallel, a few cm..dm apart (a sign in front of a wall): the face behind loses what the opaque face in front covers;
                            a cut-out in front is moved off until the gap is safe (the only offsets left, a handful)
    gate(faces, road_xz, ...) -> what could still z-fight

faces = importer list [(material, section, [xyz], [uv])], SR3 coordinates. pixels(name) -> (rgb uint8 h x w x 3, hole bool
h x w or None) or None; save(name, rgb, hole) registers a composed tile (build_classic.BAKED + a PNG).
Which of two faces in one plane is the upper one is layers.py's guess (cut-out over opaque, smaller over larger, later over
earlier). Of two parallel faces apart, the front one is the one on the side of the nearest road point (lying faces: the higher).
Composed tiles: when the two uv mappings differ by a symmetry of the tile (identity, mirror, quarter turn, any shift) and the
tiles have one size, ONE tile-sized, repeating picture serves every face of that combination (all ivy on rock: a few tiles);
otherwise the picture covers just the shared region (its uv rectangle in the lower face's mapping) and identical cases share
it. Names: bake_<8 hex of the recipe>[_t]. Deterministic: no random numbers, sorted iteration, names from the recipe.

When do two faces count (find_pairs): both are drawn towards one viewer, their normals are within 2 degrees, they overlap in
their plane by more than a sliver, and the gap between them is below  K_DEPTH x d^2 , d = the largest distance they are looked
at from: the farthest road point, at most MAX_VIEW, and no further than where the overlap is still PIXELS wide on screen."""
import collections, hashlib, sys
import numpy as np

EPS_AREA = 2e-3                                                        # m2: smaller pieces are slivers, not drawn
K_DEPTH = 1.0e-6                                                       # needed gap = K d^2 (24-bit depth, near plane about 0.1 m: 0.6e-6; x 1.7)
MAX_VIEW = 600.0
PIXELS = 6.0; FOCAL = 935.0                                            # 1080 lines, 60 degrees: size on screen = FOCAL x metres / distance
COPLANAR = 0.05                                                        # faces whose corners stay within 5 cm of each other's plane are treated as one plane
INFO = {}
ORIGIN = {}                                                            # composed tile -> the tile under it (what kind of surface it is)

def _newell(P):
    # (plain arithmetic: np.cross / np.linalg.norm on three numbers cost 100 microseconds a polygon, 1.2 million times a build = 140 s; profile 2026-10-08)
    Q = P.tolist() if isinstance(P, np.ndarray) else [(float(p[0]), float(p[1]), float(p[2])) for p in P]; x = y = z = 0.0; a = Q[-1]
    for b in Q: x += a[1] * b[2] - a[2] * b[1]; y += a[2] * b[0] - a[0] * b[2]; z += a[0] * b[1] - a[1] * b[0]; a = b
    l = (x * x + y * y + z * z) ** 0.5; n = np.array((x, y, z)); return (n / l if l > 1e-12 else n), 0.5 * l
def _basis(P):
    P = np.asarray(P, float); n, _ = _newell(P); D_ = np.roll(P, -1, axis=0) - P; k = int(np.argmax((D_ * D_).sum(1)))
    u = P[(k + 1) % len(P)] - P[k]; u -= n * (u @ n); u /= max(np.linalg.norm(u), 1e-12); return P.mean(0), u, np.cross(n, u), n
def _to2(P, B): o, u, w, n = B; d = np.asarray(P, float) - o; return np.stack([d @ u, d @ w], 1)
def _to3(Q, B): o, u, w, n = B; return o + Q[:, :1] * u + Q[:, 1:2] * w
def _area(Q): x, y = Q[:, 0], Q[:, 1]; return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
def _ccw(Q): return Q if _area(Q) >= 0 else Q[::-1]
def _affine(Q, UV):
    """least-squares uv = [x y 1] M over the corners -> (M 3x2, largest residual)"""
    A = np.c_[Q, np.ones(len(Q))]; M = np.linalg.lstsq(A, np.asarray(UV, float), rcond=None)[0]; return M, float(np.abs(A @ M - UV).max())
def _clip(Q, a, b, inside=True):
    """convex polygon Q cut by the line a -> b: the part on its left (inside) or on its right"""
    if len(Q) < 3: return Q[:0]
    e = b - a; s = (Q[:, 0] - a[0]) * e[1] - (Q[:, 1] - a[1]) * e[0]; s = -s if inside else s      # >= 0 = kept
    out = []
    for i in range(len(Q)):
        j = (i + 1) % len(Q)
        if s[i] >= 0: out.append(Q[i])
        if (s[i] > 0 and s[j] < 0) or (s[i] < 0 and s[j] > 0): t = s[i] / (s[i] - s[j]); out.append(Q[i] + (Q[j] - Q[i]) * t)
    return np.array(out) if len(out) >= 3 else Q[:0]
def _tidy(Q, tol=1e-4):
    if len(Q) < 3: return Q[:0]
    keep = [Q[0]]
    for q in Q[1:]:
        if np.abs(q - keep[-1]).max() > tol: keep.append(q)
    if len(keep) > 1 and np.abs(keep[0] - keep[-1]).max() <= tol: keep.pop()
    return np.array(keep) if len(keep) >= 3 else Q[:0]
def _inter(A, B):
    c = A
    for k in range(len(B)):
        c = _tidy(_clip(c, B[k], B[(k + 1) % len(B)], True))
        if not len(c): break
    return c
def _cut(A, B):
    """convex A, B (ccw) -> (pieces of A outside B, A inside B)"""
    pieces = []; rem = A
    for i in range(len(B)):
        a, b = B[i], B[(i + 1) % len(B)]; o = _tidy(_clip(rem, a, b, False))
        if len(o) and _area(o) > EPS_AREA: pieces.append(o)
        rem = _tidy(_clip(rem, a, b, True))
        if not len(rem): break
    return pieces, (rem if len(rem) and _area(rem) > EPS_AREA else rem[:0])
def _emit(mat, sec, Q, B, M, out):
    """convex plan polygon -> faces of 3 or 4 corners in the plane B with uv from the affine M"""
    k = 1
    while k < len(Q) - 1:
        idx = [0, k, k + 1] + ([k + 2] if k + 2 < len(Q) else []); q = Q[idx]
        if abs(_area(q)) > EPS_AREA: out.append((mat, sec, [tuple(map(float, p)) for p in _to3(q, B)], [tuple(map(float, t)) for t in np.c_[q, np.ones(len(q))] @ M]))
        k += 2
def _key(P): return frozenset((round(p[0], 2), round(p[1], 2), round(p[2], 2)) for p in P)

def _recipe(lo, up, T, pix, rect=None):
    """composed picture of tile `lo` with tile `up` painted over; T (3x2): upper uv = [u v 1] T of the lower uv.
    rect None: tile-sized, repeating. rect (u0, v0, u1, v1): that uv rectangle of the lower mapping, not repeating."""
    rl, hl = pix(lo); ru, hu = pix(up); H, W = rl.shape[:2]; h2, w2 = ru.shape[:2]
    if rect is None: w, h = W, H; u0, v0, u1, v1 = 0.0, 0.0, 1.0, 1.0
    else: u0, v0, u1, v1 = rect; w = int(2 ** np.clip(np.ceil(np.log2(max((u1 - u0) * W, 1.0))), 3, 9)); h = int(2 ** np.clip(np.ceil(np.log2(max((v1 - v0) * H, 1.0))), 3, 9))      # power-of-two sides like every 1995 tile (DXT blocks, mip chain)
    if rect is not None:                                              # ... and as fine as the UPPER tile needs: the size used to come from the lower tile alone, so the CHECK POINT letters (256 x 64) painted over their
        cr_ = np.array([[u0, v0, 1.0], [u1, v0, 1.0], [u0, v1, 1.0], [u1, v1, 1.0]]) @ T; ex_ = np.ptp(cr_, axis=0) * [w2, h2]          # blue panel (64 x 32, repeated) came out at the panel's size, half as fine as their own picture
        w = int(max(w, 2 ** np.clip(np.ceil(np.log2(max(ex_[0], 1.0))), 3, 11))); h = int(max(h, 2 ** np.clip(np.ceil(np.log2(max(ex_[1], 1.0))), 3, 11)))      # (user, 2026-10-08: "why does it look so bad in-game, the source itself isn't half bad")
    uu = u0 + (np.arange(w) + 0.5) / w * (u1 - u0); vv = v1 - (np.arange(h) + 0.5) / h * (v1 - v0); U, Vv = np.meshgrid(uu, vv)   # picture row 0 = top = largest v
    cl = np.floor(U * W).astype(int) % W; rw = np.floor((1.0 - Vv) * H).astype(int) % H; rgb = rl[rw, cl].copy(); hole = hl[rw, cl].copy() if hl is not None else np.zeros((h, w), bool)
    uv2 = np.stack([U, Vv, np.ones_like(U)], -1) @ T; c2 = np.floor(uv2[..., 0] * w2).astype(int) % w2; r2 = np.floor((1.0 - uv2[..., 1]) * h2).astype(int) % h2
    op = ~hu[r2, c2] if hu is not None else np.ones((h, w), bool); rgb[op] = ru[r2, c2][op]; hole &= ~op
    return rgb, (hole if hole.any() else None)

RECIPES = {}                                                          # composed tile -> (lower, upper, mapping, region): texfast.py composes it again when one of its tiles is re-authored
class _Baker:
    def __init__(self, pixels, save): self.pixels = pixels; self.save = save; self.pix = {}; self.names = {}; self.stat = collections.Counter()
    def px(self, name):
        if name not in self.pix: self.pix[name] = self.pixels(name)
        return self.pix[name]
    def compose(self, ml, mu, uvl, uvu):
        """lower / upper tile and the two uv sets at the SAME points (>= 3, not in a line) -> (name, f) with f(uv of the lower
        mapping) = uv on the composed tile; None when it cannot be done"""
        pl_, pu_ = self.px(ml), self.px(mu); uvl = np.asarray(uvl, float); uvu = np.asarray(uvu, float)
        if pl_ is None or pu_ is None: self.stat['left alone: a tile has no picture'] += 1; return None
        A = np.c_[uvl, np.ones(len(uvl))]
        if np.linalg.matrix_rank(A, tol=1e-6) < 3: self.stat['left alone: lower face has no uv area'] += 1; return None
        T = np.linalg.lstsq(A, uvu, rcond=None)[0]
        if np.abs(A @ T - uvu).max() > 0.03: self.stat['left alone: the two mappings are not affine to each other'] += 1; return None
        L = T[:2]; Lr = np.round(L)
        if pl_[0].shape == pu_[0].shape and np.abs(L - Lr).max() < 0.01 and abs(abs(np.linalg.det(Lr)) - 1) < 1e-6:
            Tk = np.vstack([Lr, np.round(T[2] % 1.0, 3) % 1.0]); key = (ml, mu, tuple(Tk.ravel()), None); rect = None; f = lambda uv: np.asarray(uv, float)
        else:
            H, W = pl_[0].shape[:2]; lo_ = uvl.min(0); hi_ = uvl.max(0); sh = np.floor(lo_ + 1e-6); a0 = np.round((lo_ - sh) * [W, H]) / [W, H]; sz = np.maximum(np.round((hi_ - lo_) * [W, H]), 2) / [W, H]
            Tk = T.copy(); Tk[2] = Tk[2] + sh @ T[:2]; Tk = np.round(Tk, 3); Tk[2] = Tk[2] % 1.0                       # recipe in uv relative to the whole-tile shift
            rect = (a0[0], a0[1], a0[0] + sz[0], a0[1] + sz[1]); key = (ml, mu, tuple(Tk.ravel()), tuple(np.round(rect, 4))); org = sh + a0
            f = lambda uv, org=org, sz=sz: (np.asarray(uv, float) - org) / sz
        if key not in self.names:
            rgb, hole = _recipe(ml, mu, np.array(key[2]).reshape(3, 2), self.px, rect)
            nm = 'bake_' + hashlib.md5(repr(key).encode()).hexdigest()[:8] + ('_t' if hole is not None else ''); self.names[key] = nm; RECIPES[nm] = key; self.save(nm, rgb, hole); ORIGIN[nm] = ORIGIN.get(ml, ml)
            self.stat['composed tiles: repeating' if rect is None else 'composed tiles: one region'] += 1
        return self.names[key], f

# ---------------------------------------------------------------- which faces can fight
def _prep(faces):
    n = len(faces); P3 = [np.asarray(f[2], float) for f in faces]; nr = np.zeros((n, 3)); ar = np.zeros(n)
    for i, p in enumerate(P3): nr[i], ar[i] = _newell(p)
    cen = np.array([p.mean(0) for p in P3]) if n else np.zeros((0, 3)); return P3, nr, ar, cen
def _prep_fast(faces):
    """normals, areas and centres of _prep for all polygons at once (fastgeo.prep); None = not available, use _prep"""
    import fastgeo
    if not fastgeo.ON or not len(faces): return None
    G = fastgeo.prep(faces)
    if fastgeo.CHECK: P3, nr, ar, cen = _prep(faces); fastgeo.note('overlay_bake._prep', np.array_equal(nr, G.nr) and np.array_equal(cen, G.cen) and np.allclose(ar, G.ar, rtol=1e-14, atol=0), (float(np.abs(nr - G.nr).max()), float(np.abs(cen - G.cen).max()), float(np.abs(ar - G.ar).max())))
    return G
def _same_pairs(a, b, tol=1e-9):
    return len(a) == len(b) and all(p[:2] == q[:2] and all(abs(x - y) <= tol * max(1.0, abs(x), abs(y)) for x, y in zip(p[2:], q[2:])) for p, q in zip(a, b))
def find_pairs(faces, road_xz, single=(), active=None, skip_sections=('sea',), floor=0.015, margin=1.0, _G=None):
    """-> [(i, j, gap, spread, need, overlap m2)]: gap = smallest distance of a corner of one face from the other's plane,
    spread = largest; need = K d^2 (see the module text). A pair is listed when gap < max(need, 1.5 cm).
    (fastgeo.c does the work: the same grid, tests and order as _old_find_pairs below, on every core; 2026-10-08)"""
    import fastgeo
    out = fastgeo.find_pairs(faces, road_xz, single, active, skip_sections, floor, margin, sys.modules[__name__], _G) if fastgeo.ON else None
    if out is None: return _old_find_pairs(faces, road_xz, single, active, skip_sections, floor, margin)
    if fastgeo.CHECK: old = _old_find_pairs(faces, road_xz, single, active, skip_sections, floor, margin); fastgeo.note('overlay_bake.find_pairs', _same_pairs(old, out), (len(old), len(out), sorted(set(p[:2] for p in old) ^ set(p[:2] for p in out))[:8]))
    return out
def _old_find_pairs(faces, road_xz, single=(), active=None, skip_sections=('sea',), floor=0.015, margin=1.0):      # (the Python original of find_pairs: fallback and reference)
    road_xz = np.asarray(road_xz, float); n = len(faces); P3, nr, ar, cen = _prep(faces); ok = ar > EPS_AREA
    far = np.zeros(n)
    for s in range(0, n, 2000): d = np.sqrt(((cen[s:s + 2000, None, [0, 2]] - road_xz[None, ::8]) ** 2).sum(2)); far[s:s + 2000] = np.minimum(d.max(1), MAX_VIEW)
    need0 = K_DEPTH * far ** 2; cell = 8.0; grid = collections.defaultdict(list); sg = np.array([(id(f) in single) or str(f[1]).endswith('~s') for f in faces])            # '~s' = single-sided cut-out (build_classic.SINGLE): a tree blade's front or back
    for i, p in enumerate(P3):
        if not ok[i] or faces[i][1] in skip_sections: continue
        lo = np.floor(p[:, [0, 2]].min(0) / cell).astype(int); hi = np.floor(p[:, [0, 2]].max(0) / cell).astype(int)
        if (hi - lo).max() > 40: continue                              # huge backdrop faces
        for x in range(lo[0], hi[0] + 1):
            for z in range(lo[1], hi[1] + 1): grid[(x, z)].append(i)
    lo3 = np.array([p.min(0) for p in P3]); hi3 = np.array([p.max(0) for p in P3]); seen = set(); out = []; act = None
    if active is not None: act = np.zeros(n, bool); act[list(active)] = True
    for key in sorted(grid):
        L = np.array(grid[key])
        if len(L) < 2 or (act is not None and not act[L].any()): continue
        for a_ in range(len(L) - 1):
            i = L[a_]; J = L[a_ + 1:]; g = np.maximum(need0[i], need0[J]) + 0.02
            m = (np.abs(nr[J] @ nr[i]) > 0.99939) & ~((lo3[J] > hi3[i] + g[:, None]).any(1) | (lo3[i] > hi3[J] + g[:, None]).any(1))
            if act is not None and not act[i]: m &= act[J]
            for j in J[m]:
                if (i, j) in seen: continue
                seen.add((i, j)); pi, pj = P3[i], P3[j]; da = np.abs((pj - cen[i]) @ nr[i]); db = np.abs((pi - cen[j]) @ nr[j]); gap = float(max(da.min(), db.min())); lim = max(need0[i], need0[j])
                if gap >= max(lim * margin, floor): continue
                if sg[i] and sg[j] and nr[i] @ nr[j] < 0: continue                         # back to back, each seen from its own side only
                B = _basis(pi); c = _inter(_ccw(_to2(pi, B)), _ccw(_to2(pj, B)))
                if not len(c): continue
                ov = _area(c)
                if ov < max(0.02, 0.01 * min(ar[i], ar[j])): continue
                need = K_DEPTH * min(max(far[i], far[j]), FOCAL * np.sqrt(ov) / PIXELS) ** 2
                if gap >= max(need * margin, floor): continue
                out.append((int(i), int(j), gap, float(max(da.max(), db.max())), float(need), float(ov)))
    return out

def resolve(faces, pixels, save, road_xz, log=print, rounds=10):
    import layers
    faces = list(faces); bk = _Baker(pixels, save); stat = bk.stat; road_xz = np.asarray(road_xz, float)
    # ---- 1. polygons on the same corners (flat or warped, no geometry needed)
    by = collections.defaultdict(list)
    def _side(fc):                                                     # a single-sided cut-out only meets faces on ITS side: front and back of a tree blade share their corners but are two boards
        if not str(fc[1]).endswith('~s'): return 0
        P = np.asarray(fc[2], float); n_ = np.cross(P[1] - P[0], P[2] - P[0]); k_ = int(np.argmax(np.abs(n_))); return 1 if n_[k_] > 0 else -1
    for i, fc in enumerate(faces): by[(_key(fc[2]), _side(fc))].append(i)
    gone = set(); repl = {}
    for k in sorted(by, key=lambda k: by[k][0]):
        ii = by[k]
        if len(ii) < 2: continue
        P0 = [tuple(np.round(p, 2)) for p in faces[ii[0]][2]]
        if len(set(P0)) < 3: continue
        op = [i for i in ii if not str(faces[i][0]).endswith('_t')]; ct = [i for i in ii if str(faces[i][0]).endswith('_t')]
        for i in op[:-1]: gone.add(i); stat['same corners: opaque polygon under another opaque one dropped'] += 1      # the later one is the upper (layers.py)
        base = op[-1] if op else ct[0]; cur = faces[base]
        for j in ([c for c in ct if c != base]):
            a = dict(zip([tuple(np.round(p, 2)) for p in cur[2]], cur[3])); b = dict(zip([tuple(np.round(p, 2)) for p in faces[j][2]], faces[j][3])); ks = list(a)
            if cur[0] == faces[j][0] and all(np.allclose(a[q], b[q], atol=1e-3) for q in ks): gone.add(j); continue
            r = bk.compose(cur[0], faces[j][0], [a[q] for q in ks], [b[q] for q in ks])
            if r is None: continue
            nm, f = r; cur = (nm, cur[1], cur[2], [tuple(map(float, t)) for t in f(cur[3])]); gone.add(j); stat['same corners: cut-out baked into the polygon under it'] += 1
        repl[base] = cur
    faces = [repl.get(i, fc) for i, fc in enumerate(faces) if i not in gone]
    # ---- 2. overlapping polygons in one plane, and parallel ones too close
    active = None
    for rnd in range(rounds):
        G_ = _prep_fast(faces); pairs = find_pairs(faces, road_xz, active=active, _G=G_)
        if not pairs: break
        P3, nr, ar, cen = (None, G_.nr, G_.ar, G_.cen) if G_ is not None else _prep(faces); cut = np.array([str(f[0]).endswith('_t') for f in faces])
        rank = {i: k for k, i in enumerate(sorted({i for p in pairs for i in p[:2]}, key=lambda i: (cut[i], -ar[i], i)))}      # layers.py's order: later = upper
        busy = set(); new = []; gone = set(); later = set()
        for i, j, gap, spread, need, ov in sorted(pairs, key=lambda p: (min(rank[p[0]], rank[p[1]]), max(rank[p[0]], rank[p[1]]))):
            if i in busy or j in busy: later.update((i, j)); continue
            busy.update((i, j))
            if spread < COPLANAR: lo, up = (i, j) if rank[i] < rank[j] else (j, i); apart = False
            else:                                                       # parallel, apart: the front one is on the side of the nearest road point (lying faces: the higher one)
                c = (cen[i] + cen[j]) / 2; r = road_xz[np.argmin(((road_xz - c[[0, 2]]) ** 2).sum(1))]; to = np.array([r[0] - c[0], 0.0, r[1] - c[2]]); n = nr[i]
                side = np.array([0.0, 1.0, 0.0]) if abs(n[1]) > 0.5 else to
                fi = (cen[i] - cen[j]) @ n * np.sign(side @ n if abs(side @ n) > 1e-9 else 1.0) > 0; up, lo = (i, j) if fi else (j, i); apart = True
            ml, sl, Pl, Ul = faces[lo]; mu, su, Pu, Uu = faces[up]; Bl = _basis(Pl); Bu = _basis(Pu)
            def push(reason):
                """the cut-out (else the upper) face is moved off the other one until the gap is safe"""
                k_, o_ = (up, lo) if (cut[up] or not cut[lo]) else (lo, up); n_ = nr[o_]; s_ = np.sign((cen[k_] - cen[o_]) @ n_) or 1.0
                d_ = (need * 1.15 + 0.01) - gap; mat_, sec_, P_, U_ = faces[k_]; gone.add(k_); new.append((mat_, sec_, [tuple(map(float, np.asarray(p) + s_ * d_ * n_)) for p in P_], U_)); stat['moved apart (%s)' % reason] += 1
            Ml, rl_ = _affine(_to2(Pl, Bl), Ul); Mu, ru_ = _affine(_to2(Pu, Bu), Uu)
            if rl_ > 0.06 or ru_ > 0.06: push('uv not affine on a quad'); continue
            Ql = _ccw(_to2(Pl, Bl)); pieces, inter = _cut(Ql, _ccw(_to2(Pu, Bl)))
            if not len(inter): continue
            if not cut[up]:                                             # opaque on top / in front: the lower face loses what is covered
                gone.add(lo)
                for q in pieces: _emit(ml, sl, q, Bl, Ml, new)
                stat['face behind cut back (opaque face %s)' % ('in front, apart' if apart else 'on it')] += 1; continue
            if apart: push('cut-out in front of a face'); continue
            uvl = np.c_[inter, np.ones(len(inter))] @ Ml; uvu = np.c_[_to2(_to3(inter, Bl), Bu), np.ones(len(inter))] @ Mu
            r = bk.compose(ml, mu, uvl, uvu)
            if r is None: push('no composed tile'); continue
            nm, f = r; gone.update((lo, up))
            for q in pieces: _emit(ml, sl, q, Bl, Ml, new)
            k = 1; q3 = _to3(inter, Bl); uvn = f(uvl)
            while k < len(inter) - 1:
                idx = [0, k, k + 1] + ([k + 2] if k + 2 < len(inter) else [])
                if abs(_area(inter[idx])) > EPS_AREA: new.append((nm, sl, [tuple(map(float, p)) for p in q3[idx]], [tuple(map(float, t)) for t in uvn[idx]]))
                k += 2
            pu2, _ = _cut(_ccw(_to2(Pu, Bu)), _ccw(_to2(_to3(inter, Bl), Bu)))
            for q in pu2: _emit(mu, su, q, Bu, Mu, new)
            stat['shared region baked (cut-out on top)'] += 1
        if not gone: break
        keep = [k for k in range(len(faces)) if k not in gone]; pos = {k: q for q, k in enumerate(keep)}; faces = [faces[k] for k in keep]
        active = set(range(len(faces), len(faces) + len(new))) | {pos[k] for k in later if k in pos}; faces += new; stat['rounds'] = rnd + 1
    stat['pairs left'] = len(find_pairs(faces, road_xz)); INFO.clear(); INFO.update(stat)
    log('       coplanar / near-coplanar polygons resolved without lift: %s' % dict(sorted(stat.items())))
    return faces

# ---------------------------------------------------------------- the gate
def gate(faces, road_xz, pairs_single=(), top=10, skip=None):
    """-> dict(exact, near, within_30m_of_road, worst, by_section, pairs): what can still z-fight (find_pairs).
    exact = gap below 1.5 cm, near = gap below the needed one. pairs_single: id() of faces drawn single-sided."""
    road_xz = np.asarray(road_xz, float); pr = find_pairs(faces, road_xz, pairs_single)
    if skip is not None: pr = [p for p in pr if not skip(p[0], p[1])]
    cen = {i: np.asarray(faces[i][2], float).mean(0) for p in pr for i in p[:2]}
    dr = {i: float(np.sqrt(((road_xz - c[[0, 2]]) ** 2).sum(1).min())) for i, c in cen.items()}
    rows = [(round(g, 3), round(nd, 3), faces[i][0][-16:], faces[i][1], faces[j][0][-16:], faces[j][1], tuple(np.round(cen[i], 0).tolist()), round(min(dr[i], dr[j]))) for i, j, g, sp, nd, ov in pr]
    exact = [r for r in rows if r[0] < 0.015]; near = sorted([r for r in rows if r[0] >= 0.015], key=lambda r: r[0] / max(r[1], 1e-6))
    kinds = collections.Counter((r[3].split('#')[0][:12], r[5].split('#')[0][:12]) for r in rows)
    return dict(exact=len(exact), near=len(near), within_30m_of_road=sum(1 for r in rows if r[7] < 30), worst=exact[:top] + near[:top], by_section=kinds.most_common(top), pairs=[(p[0], p[1]) for p in pr])
