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
at from: the farthest road point, at most MAX_VIEW, and no further than where the overlap is still PIXELS wide on screen.

Without numpy since 2026-10-16 (kb 31): resolve, find_pairs and gate work on plain floats in numpy's own orders (the *_f twins
below; least squares through nplapack.c, the polygons' normals / areas / centres through geobuf, the pair search through the
same fastgeo.c functions as before), and give the same faces, tiles and pairs as the numpy code (checked on a whole build). The
numpy functions other modules call (_newell, _basis, _to2, _to3, _recipe, ...) keep their numpy results and import numpy when
called; _recipe paints numpy pictures, as build_classic.tile_pixels hands them over."""
import collections, hashlib, math, os, sys
import npexact

EPS_AREA = 2e-3                                                        # m2: smaller pieces are slivers, not drawn
K_DEPTH = 1.0e-6                                                       # needed gap = K d^2 (24-bit depth, near plane about 0.1 m: 0.6e-6; x 1.7)
MAX_VIEW = 600.0
PIXELS = 6.0; FOCAL = 935.0                                            # 1080 lines, 60 degrees: size on screen = FOCAL x metres / distance
COPLANAR = 0.05                                                        # faces whose corners stay within 5 cm of each other's plane are treated as one plane
INFO = {}
ORIGIN = {}                                                            # composed tile -> the tile under it (what kind of surface it is)

def _newell(P):
    # (plain arithmetic: np.cross / np.linalg.norm on three numbers cost 100 microseconds a polygon, 1.2 million times a build = 140 s; profile 2026-10-08)
    import numpy as np
    Q = P.tolist() if isinstance(P, np.ndarray) else [(float(p[0]), float(p[1]), float(p[2])) for p in P]; x = y = z = 0.0; a = Q[-1]
    for b in Q: x += a[1] * b[2] - a[2] * b[1]; y += a[2] * b[0] - a[0] * b[2]; z += a[0] * b[1] - a[1] * b[0]; a = b
    l = (x * x + y * y + z * z) ** 0.5; n = np.array((x, y, z)); return (n / l if l > 1e-12 else n), 0.5 * l
def _basis(P):
    import numpy as np
    P = np.asarray(P, float); n, _ = _newell(P); D_ = np.roll(P, -1, axis=0) - P; k = int(np.argmax((D_ * D_).sum(1)))
    u = P[(k + 1) % len(P)] - P[k]; u -= n * (u @ n); u /= max(np.linalg.norm(u), 1e-12); return P.mean(0), u, np.cross(n, u), n
def _to2(P, B):
    import numpy as np
    o, u, w, n = B; d = np.asarray(P, float) - o; return np.stack([d @ u, d @ w], 1)
def _to3(Q, B):
    o, u, w, n = B; return o + Q[:, :1] * u + Q[:, 1:2] * w
def _area(Q):
    import numpy as np
    x, y = Q[:, 0], Q[:, 1]; return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
def _ccw(Q): return Q if _area(Q) >= 0 else Q[::-1]
def _affine(Q, UV):
    """least-squares uv = [x y 1] M over the corners -> (M 3x2, largest residual)"""
    import numpy as np
    A = np.c_[Q, np.ones(len(Q))]; M = np.linalg.lstsq(A, np.asarray(UV, float), rcond=None)[0]; return M, float(np.abs(A @ M - UV).max())
def _clip(Q, a, b, inside=True):
    """convex polygon Q cut by the line a -> b: the part on its left (inside) or on its right"""
    if len(Q) < 3: return Q[:0]
    import numpy as np
    e = b - a; s = (Q[:, 0] - a[0]) * e[1] - (Q[:, 1] - a[1]) * e[0]; s = -s if inside else s      # >= 0 = kept
    out = []
    for i in range(len(Q)):
        j = (i + 1) % len(Q)
        if s[i] >= 0: out.append(Q[i])
        if (s[i] > 0 and s[j] < 0) or (s[i] < 0 and s[j] > 0): t = s[i] / (s[i] - s[j]); out.append(Q[i] + (Q[j] - Q[i]) * t)
    return np.array(out) if len(out) >= 3 else Q[:0]
def _tidy(Q, tol=1e-4):
    if len(Q) < 3: return Q[:0]
    import numpy as np
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
ON_SURFACE = False                                                    # course setting resolve_on_surface (build_classic / import_classic): cut pieces are laid on the DRAWN surface of the face they come from
def _on_surface(Q, B, P):
    """plan points Q (basis B) -> 3-D points. Plainly: in the plane B (the face's best plane). With ON_SURFACE: on the face as the
    game draws it - a quad as the triangles (0, 1, 3) + (1, 3, 2) (meshgen.quads_to_strip) - so that the pieces of a TWISTED face
    still meet its neighbours along its edges (Daytona's banking: pieces put in the best plane left cracks of a few cm the sky
    showed through)."""
    import numpy as np
    X = _to3(Q, B); P = np.asarray(P, float)
    if not ON_SURFACE or len(P) not in (3, 4): return X
    P2 = _to2(P, B); tris = [(0, 1, 2)] if len(P) == 3 else [(0, 1, 3), (1, 3, 2)]; out = X.copy()
    for k, q in enumerate(np.asarray(Q, float)):
        best = None
        for t in tris:
            a, b, c = P2[t[0]], P2[t[1]], P2[t[2]]; d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-12: continue
            l1 = ((b[1] - c[1]) * (q[0] - c[0]) + (c[0] - b[0]) * (q[1] - c[1])) / d; l2 = ((c[1] - a[1]) * (q[0] - c[0]) + (a[0] - c[0]) * (q[1] - c[1])) / d; l3 = 1.0 - l1 - l2
            if best is None or min(l1, l2, l3) > best[0]: best = (min(l1, l2, l3), l1, l2, l3, t)
        if best is not None: _, l1, l2, l3, t = best; out[k] = l1 * P[t[0]] + l2 * P[t[1]] + l3 * P[t[2]]
    return out
def _emit(mat, sec, Q, B, M, out, P=None):
    """convex plan polygon -> faces of 3 or 4 corners in the plane B (on the face P's drawn surface with ON_SURFACE) with uv from the affine M"""
    import numpy as np
    k = 1
    while k < len(Q) - 1:
        idx = [0, k, k + 1] + ([k + 2] if k + 2 < len(Q) else []); q = Q[idx]
        if abs(_area(q)) > EPS_AREA: out.append((mat, sec, [tuple(map(float, p)) for p in (_to3(q, B) if P is None else _on_surface(q, B, P))], [tuple(map(float, t)) for t in np.c_[q, np.ones(len(q))] @ M]))
        k += 2
def _key(P): return frozenset((round(p[0], 2), round(p[1], 2), round(p[2], 2)) for p in P)

# ---------------------------------------------------------------- the same on plain floats (resolve, find_pairs, gate)
# Each line keeps numpy's order of the operation it replaces (kb 31, checked bit for bit with signed zeros on random data):
#   arr.sum(1) of a (k, 3) array: (p0 + p1) + p2     arr.mean(0): the rows added one after another from 0, / k
#   d @ u, (k, 3) @ (3,):  0 + ((p0 + p2) + p1)      [q 1] @ M, (k, 3) @ (3, 2): 0 + ((p0 + p1) + p2)
#   u @ n, two 3-vectors: npexact.ddot (the second one's place in memory: a fresh array is aligned, row i of an (n, 3) array is 8
#   bytes off for odd i); np.linalg.norm(u) = sqrt(ddot(u, u)); np.sum of a 1-D array = npexact.pwsum; np.round(x, d) = rint(x 10^d) / 10^d
# Points are tuples, polygons lists of them; an empty polygon is [] (numpy: Q[:0]).
def _rint(x):
    r = float(round(x)); return math.copysign(r, x) if r == 0.0 else r                 # np.rint: half to even, the zero keeps its sign
def _npround(x, d=0):
    if not d: return _rint(x)
    f = 10.0 ** d; return _rint(x * f) / f                                           # np.round(x, d): rint(x * 10.0 ** d) / 10.0 ** d (not Python's round)
def _sign(x): return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)                       # np.sign
def _rows3(P): return [(float(p[0]), float(p[1]), float(p[2])) for p in P]
def _mean0(P):
    k = len(P); x = y = z = 0.0
    for p in P: x += p[0]; y += p[1]; z += p[2]
    return (x / k, y / k, z / k)
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _newell_f(P):
    """_newell: (unit normal, or the raw sum when shorter than 1e-12, as a tuple; area)"""
    Q = _rows3(P); x = y = z = 0.0; a = Q[-1]
    for b in Q: x += a[1] * b[2] - a[2] * b[1]; y += a[2] * b[0] - a[0] * b[2]; z += a[0] * b[1] - a[1] * b[0]; a = b
    l = (x * x + y * y + z * z) ** 0.5; return ((x / l, y / l, z / l) if l > 1e-12 else (x, y, z)), 0.5 * l
def _basis_f(P):
    P = _rows3(P); k = len(P); n, _ = _newell_f(P); kb = 0; best = None
    for i in range(k):                                                  # np.argmax((D_ * D_).sum(1)): the first longest edge
        a = P[i]; b = P[(i + 1) % k]; d0 = b[0] - a[0]; d1 = b[1] - a[1]; d2 = b[2] - a[2]; s = (d0 * d0 + d1 * d1) + d2 * d2
        if best is None or s > best: best = s; kb = i
    a = P[kb]; b = P[(kb + 1) % k]; u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
    t = npexact.ddot(u, n, 0); u = [u[0] - n[0] * t, u[1] - n[1] * t, u[2] - n[2] * t]           # u -= n * (u @ n)
    l = max(math.sqrt(npexact.ddot(u, u, 0)), 1e-12); u = (u[0] / l, u[1] / l, u[2] / l)          # u /= max(np.linalg.norm(u), 1e-12)
    return _mean0(P), u, _cross(n, u), n
def _to2_f(P, B):
    o, u, w, n = B; out = []
    for p in P:
        d0 = p[0] - o[0]; d1 = p[1] - o[1]; d2 = p[2] - o[2]
        out.append((0.0 + ((d0 * u[0] + d2 * u[2]) + d1 * u[1]), 0.0 + ((d0 * w[0] + d2 * w[2]) + d1 * w[1])))
    return out
def _to3_f(Q, B):
    o, u, w, n = B; return [((o[0] + q[0] * u[0]) + q[1] * w[0], (o[1] + q[0] * u[1]) + q[1] * w[1], (o[2] + q[0] * u[2]) + q[1] * w[2]) for q in Q]
def _area_f(Q):
    k = len(Q); return 0.5 * npexact.pwsum([Q[i][0] * Q[(i + 1) % k][1] - Q[(i + 1) % k][0] * Q[i][1] for i in range(k)])
def _ccw_f(Q): return Q if _area_f(Q) >= 0 else Q[::-1]
def _mul3(q, M):                                                       # [q0 q1 1] @ M (3 x 2 rows)
    return (0.0 + ((q[0] * M[0][0] + q[1] * M[1][0]) + 1.0 * M[2][0]), 0.0 + ((q[0] * M[0][1] + q[1] * M[1][1]) + 1.0 * M[2][1]))
def _lstsq(A, B):
    """np.linalg.lstsq(A, B, rcond=None)[0] (and the singular values): nplapack, numpy's own beyond what nplapack.c models"""
    import nplapack
    if nplapack.fits(len(A), len(A[0]), len(B[0])): return nplapack.lstsq(A, B)
    import numpy as np
    X, _, _, S = np.linalg.lstsq(np.array(A, float), np.array(B, float), rcond=None); return X.tolist(), S.tolist()
def _affine_f(Q, UV):
    A = [(q[0], q[1], 1.0) for q in Q]; UV = [(float(t[0]), float(t[1])) for t in UV]; M, _ = _lstsq(A, UV); r = 0.0
    for q, t in zip(Q, UV):
        m = _mul3(q, M); r = max(r, abs(m[0] - t[0]), abs(m[1] - t[1]))
    return M, r
def _clip_f(Q, a, b, inside=True):
    if len(Q) < 3: return []
    e0 = b[0] - a[0]; e1 = b[1] - a[1]; s = [(q[0] - a[0]) * e1 - (q[1] - a[1]) * e0 for q in Q]
    if inside: s = [-v for v in s]
    out = []; k = len(Q)
    for i in range(k):
        j = (i + 1) % k
        if s[i] >= 0: out.append(Q[i])
        if (s[i] > 0 and s[j] < 0) or (s[i] < 0 and s[j] > 0): t = s[i] / (s[i] - s[j]); out.append((Q[i][0] + (Q[j][0] - Q[i][0]) * t, Q[i][1] + (Q[j][1] - Q[i][1]) * t))
    return out if len(out) >= 3 else []
def _tidy_f(Q, tol=1e-4):
    if len(Q) < 3: return []
    keep = [Q[0]]
    for q in Q[1:]:
        if max(abs(q[0] - keep[-1][0]), abs(q[1] - keep[-1][1])) > tol: keep.append(q)
    if len(keep) > 1 and max(abs(keep[0][0] - keep[-1][0]), abs(keep[0][1] - keep[-1][1])) <= tol: keep.pop()
    return keep if len(keep) >= 3 else []
def _inter_f(A, B):
    c = A
    for k in range(len(B)):
        c = _tidy_f(_clip_f(c, B[k], B[(k + 1) % len(B)], True))
        if not c: break
    return c
def _cut_f(A, B):
    pieces = []; rem = A
    for i in range(len(B)):
        a, b = B[i], B[(i + 1) % len(B)]; o = _tidy_f(_clip_f(rem, a, b, False))
        if o and _area_f(o) > EPS_AREA: pieces.append(o)
        rem = _tidy_f(_clip_f(rem, a, b, True))
        if not rem: break
    return pieces, (rem if rem and _area_f(rem) > EPS_AREA else [])
def _on_surface_f(Q, B, P):
    X = _to3_f(Q, B)
    if not ON_SURFACE or len(P) not in (3, 4): return X
    P = _rows3(P); P2 = _to2_f(P, B); tris = [(0, 1, 2)] if len(P) == 3 else [(0, 1, 3), (1, 3, 2)]; out = list(X)
    for k, q in enumerate(Q):
        best = None
        for t in tris:
            a, b, c = P2[t[0]], P2[t[1]], P2[t[2]]; d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-12: continue
            l1 = ((b[1] - c[1]) * (q[0] - c[0]) + (c[0] - b[0]) * (q[1] - c[1])) / d; l2 = ((c[1] - a[1]) * (q[0] - c[0]) + (a[0] - c[0]) * (q[1] - c[1])) / d; l3 = 1.0 - l1 - l2
            if best is None or min(l1, l2, l3) > best[0]: best = (min(l1, l2, l3), l1, l2, l3, t)
        if best is not None:
            _, l1, l2, l3, t = best; pa, pb, pc = P[t[0]], P[t[1]], P[t[2]]; out[k] = tuple((l1 * pa[c] + l2 * pb[c]) + l3 * pc[c] for c in range(3))
    return out
def _emit_f(mat, sec, Q, B, M, out, P=None):
    k = 1
    while k < len(Q) - 1:
        q = [Q[0], Q[k], Q[k + 1]] + ([Q[k + 2]] if k + 2 < len(Q) else [])
        if abs(_area_f(q)) > EPS_AREA: out.append((mat, sec, list(_to3_f(q, B) if P is None else _on_surface_f(q, B, P)), [_mul3(t, M) for t in q]))
        k += 2

def _recipe(lo, up, T, pix, rect=None):
    """composed picture of tile `lo` with tile `up` painted over; T (3x2): upper uv = [u v 1] T of the lower uv.
    rect None: tile-sized, repeating. rect (u0, v0, u1, v1): that uv rectangle of the lower mapping, not repeating."""
    import numpy as np
    T = np.asarray(T, float).reshape(3, 2); rl, hl = pix(lo); ru, hu = pix(up); H, W = rl.shape[:2]; h2, w2 = ru.shape[:2]
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
        pl_, pu_ = self.px(ml), self.px(mu); uvl = [(float(t[0]), float(t[1])) for t in uvl]; uvu = [(float(t[0]), float(t[1])) for t in uvu]
        if pl_ is None or pu_ is None: self.stat['left alone: a tile has no picture'] += 1; return None
        A = [(t[0], t[1], 1.0) for t in uvl]; T, S = _lstsq(A, uvu)
        if sum(1 for v in S if v > 1e-6) < 3: self.stat['left alone: lower face has no uv area'] += 1; return None      # np.linalg.matrix_rank(A, tol=1e-6) < 3 (dgelsd's singular values: kb 31)
        if max(max(abs(m[0] - t[0]), abs(m[1] - t[1])) for m, t in zip((_mul3(q, T) for q in uvl), uvu)) > 0.03: self.stat['left alone: the two mappings are not affine to each other'] += 1; return None
        L = T[:2]; Lr = [[_rint(L[0][0]), _rint(L[0][1])], [_rint(L[1][0]), _rint(L[1][1])]]
        if pl_[0].shape == pu_[0].shape and max(abs(L[r][c] - Lr[r][c]) for r in (0, 1) for c in (0, 1)) < 0.01 and abs(abs(Lr[0][0] * Lr[1][1] - Lr[0][1] * Lr[1][0]) - 1) < 1e-6:      # (np.linalg.det of whole numbers)
            Tk = Lr[0] + Lr[1] + [_npround(T[2][0] % 1.0, 3) % 1.0, _npround(T[2][1] % 1.0, 3) % 1.0]; key = (ml, mu, tuple(Tk), None); rect = None; f = lambda uv: [(float(t[0]), float(t[1])) for t in uv]
        else:
            H, W = pl_[0].shape[:2]; lo_ = [min(t[c] for t in uvl) for c in (0, 1)]; hi_ = [max(t[c] for t in uvl) for c in (0, 1)]; WH = (float(W), float(H))
            sh = [float(math.floor(lo_[c] + 1e-6)) for c in (0, 1)]; a0 = [_rint((lo_[c] - sh[c]) * WH[c]) / WH[c] for c in (0, 1)]; sz = [max(_rint((hi_[c] - lo_[c]) * WH[c]), 2.0) / WH[c] for c in (0, 1)]
            t2 = [T[2][c] + (0.0 + (sh[0] * T[0][c] + sh[1] * T[1][c])) for c in (0, 1)]      # Tk[2] + sh @ T[:2]: recipe in uv relative to the whole-tile shift
            Tk = [_npround(v, 3) for v in T[0] + T[1]] + [_npround(v, 3) % 1.0 for v in t2]
            rect = (a0[0], a0[1], a0[0] + sz[0], a0[1] + sz[1]); key = (ml, mu, tuple(Tk), tuple(_npround(v, 4) for v in rect)); org = (sh[0] + a0[0], sh[1] + a0[1])
            f = lambda uv, org=org, sz=sz: [((float(t[0]) - org[0]) / sz[0], (float(t[1]) - org[1]) / sz[1]) for t in uv]
        if key not in self.names:
            rgb, hole = _recipe(ml, mu, key[2], self.px, rect)
            nm = 'bake_' + hashlib.md5(repr(key).encode()).hexdigest()[:8] + ('_t' if hole is not None else ''); self.names[key] = nm; RECIPES[nm] = key; self.save(nm, rgb, hole); ORIGIN[nm] = ORIGIN.get(ml, ml)
            self.stat['composed tiles: repeating' if rect is None else 'composed tiles: one region'] += 1
        return self.names[key], f

# ---------------------------------------------------------------- which faces can fight
def _prep(faces):
    import numpy as np
    n = len(faces); P3 = [np.asarray(f[2], float) for f in faces]; nr = np.zeros((n, 3)); ar = np.zeros(n)
    for i, p in enumerate(P3): nr[i], ar[i] = _newell(p)
    cen = np.array([p.mean(0) for p in P3]) if n else np.zeros((0, 3)); return P3, nr, ar, cen
FG_ON = os.environ.get('SR3_FASTGEO', '1') != '0'; FG_CHECK = os.environ.get('SR3_FASTGEO_CHECK', '0') == '1'      # (fastgeo.ON / CHECK, read without importing numpy)
class _Rows:
    """row i of an (n, 3) float64 buffer as a tuple, read when asked (resolve reads the few faces in pairs, not 300,000 rows)"""
    __slots__ = ('v',)
    def __init__(self, a): self.v = a.view()
    def __getitem__(self, i): return tuple(self.v[3 * i:3 * i + 3])
class _Geo:
    """normals, areas, centres and boxes of all polygons as plain rows, with geobuf's buffers for fastgeo.c"""
    def __init__(self, faces):
        if FG_ON:
            import geobuf
            g = geobuf.prep(faces); self.g = g; self.n = g.n; self.nr = _Rows(g.nr); self.ar = g.ar.view(); self.cen = _Rows(g.cen)
        else:
            self.g = None; self.n = len(faces); rows = [_newell_f(f[2]) for f in faces]
            self.nr = [r[0] for r in rows]; self.ar = [r[1] for r in rows]; self.cen = [_mean0(_rows3(f[2])) for f in faces]
def _prep_fast(faces):
    """_prep's normals, areas and centres for all polygons at once: a _Geo, or None for no faces"""
    if not len(faces): return None
    G = _Geo(faces)
    if FG_CHECK:
        import fastgeo; P3, nr, ar, cen = _prep(faces); fastgeo.note('overlay_bake._prep', nr.tolist() == [list(r) for r in G.nr] and cen.tolist() == [list(r) for r in G.cen] and ar.tolist() == G.ar, None)
    return G
def _same_pairs(a, b, tol=1e-9):
    return len(a) == len(b) and all(p[:2] == q[:2] and all(abs(x - y) <= tol * max(1.0, abs(x), abs(y)) for x, y in zip(p[2:], q[2:])) for p, q in zip(a, b))
def _road(road_xz):
    """the road points as (x, z) tuples (numpy's (n, 2) array, or any rows)"""
    R = road_xz.tolist() if hasattr(road_xz, 'tolist') else road_xz; return [(float(r[0]), float(r[1])) for r in R]
_FG = None
def _fglib():
    """fastgeo.c's pair search, bound here without numpy (fastgeo.py imports it)"""
    global _FG
    if _FG is None:
        import ctypes, cbuild
        cbuild.runtime(); L = ctypes.CDLL(cbuild.dll('fastgeo')); P = ctypes.c_void_p; LL = ctypes.c_longlong; D = ctypes.c_double
        L.fg_init.restype = ctypes.c_int; L.fg_init()
        L.fg_far.argtypes = [P, LL, P, LL, D, P]; L.fg_far.restype = None
        L.fg_pairs.argtypes = [P, P, LL, P, P, P, P, P, P, P, P, P, P, D, D, D, D, D, D]; L.fg_pairs.restype = LL
        L.fg_pairs_get.argtypes = [P, P]; L.fg_pairs_get.restype = None
        _FG = L
    return _FG
def _find_pairs_buf(faces, road, single, active, skip_sections, floor, margin, G):
    """fastgeo.find_pairs on geobuf's buffers and array.array: the same fg_far / fg_pairs calls on the same numbers; None = fastgeo.c cannot"""
    import array
    n = len(faces)
    if not n: return []
    L = _fglib(); G = G if G is not None and G.g is not None else _Geo(faces); g = G.g; ad = lambda a: a.buffer_info()[0]
    rd = array.array('d', [v for r in road[::8] for v in r]); far = array.array('d', bytes(8 * n))
    if not len(rd): return None
    L.fg_far(g.cen.ptr(), n, ad(rd), len(rd) // 2, float(MAX_VIEW), ad(far)); need0 = array.array('d', [K_DEPTH * (f * f) for f in far])      # K_DEPTH * far ** 2
    secs = [f[1] for f in faces]; kinds = set(secs)                    # (a few thousand section names: each tested once)
    sg = array.array('B', bytes(map({s: 1 if str(s).endswith('~s') else 0 for s in kinds}.__getitem__, secs)))
    if single:
        for i, f in enumerate(faces):
            if id(f) in single: sg[i] = 1
    skip = {s: s in skip_sections for s in kinds}; e = EPS_AREA
    ing = array.array('B', bytes(1 if (a > e and not skip[s]) else 0 for a, s in zip(G.ar, secs)))
    act = None
    if active is not None:
        act = array.array('B', bytes(n))
        for i in active: act[i] = 1
    r = L.fg_pairs(g.X.ptr(), g.off.ptr(), n, g.nr.ptr(), g.ar.ptr(), g.cen.ptr(), g.lo.ptr(), g.hi.ptr(), ad(need0), ad(far), ad(sg), None if act is None else ad(act), ad(ing),
                   8.0, float(margin), float(floor), float(K_DEPTH), float(FOCAL), float(PIXELS))
    if r == -1: raise MemoryError('fastgeo.find_pairs')
    if r < 0: return None
    ij = array.array('q', bytes(16 * max(r, 1))); v = array.array('d', bytes(32 * max(r, 1))); L.fg_pairs_get(ad(ij), ad(v))
    return [(ij[2 * k], ij[2 * k + 1], v[4 * k], v[4 * k + 1], v[4 * k + 2], v[4 * k + 3]) for k in range(r)]
def find_pairs(faces, road_xz, single=(), active=None, skip_sections=('sea',), floor=0.015, margin=1.0, _G=None):
    """-> [(i, j, gap, spread, need, overlap m2)]: gap = smallest distance of a corner of one face from the other's plane,
    spread = largest; need = K d^2 (see the module text). A pair is listed when gap < max(need, 1.5 cm).
    (fastgeo.c does the work: the same grid, tests and order as _old_find_pairs below, on every core; 2026-10-08)"""
    out = _find_pairs_buf(faces, _road(road_xz), single, active, skip_sections, floor, margin, _G) if FG_ON else None
    if out is None: return _old_find_pairs(faces, road_xz, single, active, skip_sections, floor, margin)
    if FG_CHECK: import fastgeo; old = _old_find_pairs(faces, road_xz, single, active, skip_sections, floor, margin); fastgeo.note('overlay_bake.find_pairs', _same_pairs(old, out), (len(old), len(out), sorted(set(p[:2] for p in old) ^ set(p[:2] for p in out))[:8]))
    return out
def _old_find_pairs(faces, road_xz, single=(), active=None, skip_sections=('sea',), floor=0.015, margin=1.0):      # (the Python original of find_pairs: fallback and reference)
    import numpy as np
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
    faces = list(faces); bk = _Baker(pixels, save); stat = bk.stat; road = _road(road_xz)
    # ---- 1. polygons on the same corners (flat or warped, no geometry needed)
    by = collections.defaultdict(list)
    def _side(fc):                                                     # a single-sided cut-out only meets faces on ITS side: front and back of a tree blade share their corners but are two boards
        if not str(fc[1]).endswith('~s'): return 0
        P = _rows3(fc[2]); n_ = _cross([P[1][c] - P[0][c] for c in range(3)], [P[2][c] - P[0][c] for c in range(3)])
        k_ = max(range(3), key=lambda c: (abs(n_[c]), -c)); return 1 if n_[k_] > 0 else -1      # np.argmax(np.abs(n_)): the first largest
    for i, fc in enumerate(faces): by[(_key(fc[2]), _side(fc))].append(i)
    gone = set(); repl = {}
    r2 = lambda P: [tuple(_npround(float(v), 2) for v in p) for p in P]      # tuple(np.round(p, 2)) of every corner
    for k in sorted(by, key=lambda k: by[k][0]):
        ii = by[k]
        if len(ii) < 2: continue
        P0 = r2(faces[ii[0]][2])
        if len(set(P0)) < 3: continue
        op = [i for i in ii if not str(faces[i][0]).endswith('_t')]; ct = [i for i in ii if str(faces[i][0]).endswith('_t')]
        for i in op[:-1]: gone.add(i); stat['same corners: opaque polygon under another opaque one dropped'] += 1      # the later one is the upper (layers.py)
        base = op[-1] if op else ct[0]; cur = faces[base]
        for j in ([c for c in ct if c != base]):
            a = dict(zip(r2(cur[2]), cur[3])); b = dict(zip(r2(faces[j][2]), faces[j][3])); ks = list(a)
            if cur[0] == faces[j][0] and all(all(abs(float(x) - float(y)) <= 1e-3 + 1e-5 * abs(float(y)) for x, y in zip(a[q], b[q])) for q in ks): gone.add(j); continue      # np.allclose(atol=1e-3)
            r = bk.compose(cur[0], faces[j][0], [a[q] for q in ks], [b[q] for q in ks])
            if r is None: continue
            nm, f = r; cur = (nm, cur[1], cur[2], f(cur[3])); gone.add(j); stat['same corners: cut-out baked into the polygon under it'] += 1
        repl[base] = cur
    faces = [repl.get(i, fc) for i, fc in enumerate(faces) if i not in gone]
    # ---- 2. overlapping polygons in one plane, and parallel ones too close
    active = None
    for rnd in range(rounds):
        G_ = _prep_fast(faces); pairs = find_pairs(faces, road, active=active, _G=G_)
        if not pairs: break
        nr, ar, cen = G_.nr, G_.ar, G_.cen; cut = [str(f[0]).endswith('_t') for f in faces]
        rank = {i: k for k, i in enumerate(sorted({i for p in pairs for i in p[:2]}, key=lambda i: (cut[i], -ar[i], i)))}      # layers.py's order: later = upper
        busy = set(); new = []; gone = set(); later = set()
        for i, j, gap, spread, need, ov in sorted(pairs, key=lambda p: (min(rank[p[0]], rank[p[1]]), max(rank[p[0]], rank[p[1]]))):
            if i in busy or j in busy: later.update((i, j)); continue
            busy.update((i, j))
            if spread < COPLANAR: lo, up = (i, j) if rank[i] < rank[j] else (j, i); apart = False
            else:                                                       # parallel, apart: the front one is on the side of the nearest road point (lying faces: the higher one)
                c = tuple((cen[i][q] + cen[j][q]) / 2 for q in range(3)); rb = None
                for rr in road:                                         # road_xz[np.argmin(((road_xz - c[[0, 2]]) ** 2).sum(1))]
                    d0 = rr[0] - c[0]; d1 = rr[1] - c[2]; dd = d0 * d0 + d1 * d1
                    if rb is None or dd < rb[0]: rb = (dd, rr)
                r = rb[1]; to = (r[0] - c[0], 0.0, r[1] - c[2]); n = nr[i]
                side = (0.0, 1.0, 0.0) if abs(n[1]) > 0.5 else to; sn = npexact.ddot(side, n, i & 1)      # (n = row i of the (faces, 3) normals: 8 bytes off 16 for odd i)
                fi = npexact.ddot([cen[i][q] - cen[j][q] for q in range(3)], n, i & 1) * _sign(sn if abs(sn) > 1e-9 else 1.0) > 0; up, lo = (i, j) if fi else (j, i); apart = True
            ml, sl, Pl, Ul = faces[lo]; mu, su, Pu, Uu = faces[up]; Bl = _basis_f(Pl); Bu = _basis_f(Pu)
            def push(reason):
                """the cut-out (else the upper) face is moved off the other one until the gap is safe"""
                k_, o_ = (up, lo) if (cut[up] or not cut[lo]) else (lo, up); n_ = nr[o_]; s_ = _sign(npexact.ddot([cen[k_][q] - cen[o_][q] for q in range(3)], n_, o_ & 1)) or 1.0
                d_ = (need * 1.15 + 0.01) - gap; mat_, sec_, P_, U_ = faces[k_]; gone.add(k_); sd = s_ * d_
                new.append((mat_, sec_, [tuple(float(p[q]) + sd * n_[q] for q in range(3)) for p in P_], U_)); stat['moved apart (%s)' % reason] += 1
            Ml, rl_ = _affine_f(_to2_f(Pl, Bl), Ul); Mu, ru_ = _affine_f(_to2_f(Pu, Bu), Uu)
            if rl_ > 0.06 or ru_ > 0.06: push('uv not affine on a quad'); continue
            Ql = _ccw_f(_to2_f(Pl, Bl)); pieces, inter = _cut_f(Ql, _ccw_f(_to2_f(Pu, Bl)))
            if not inter: continue
            if not cut[up]:                                             # opaque on top / in front: the lower face loses what is covered
                gone.add(lo)
                for q in pieces: _emit_f(ml, sl, q, Bl, Ml, new, Pl if ON_SURFACE else None)
                stat['face behind cut back (opaque face %s)' % ('in front, apart' if apart else 'on it')] += 1; continue
            if apart: push('cut-out in front of a face'); continue
            i3 = _to3_f(inter, Bl); uvl = [_mul3(q, Ml) for q in inter]; uvu = [_mul3(q, Mu) for q in _to2_f(i3, Bu)]
            r = bk.compose(ml, mu, uvl, uvu)
            if r is None: push('no composed tile'); continue
            nm, f = r; gone.update((lo, up))
            for q in pieces: _emit_f(ml, sl, q, Bl, Ml, new, Pl if ON_SURFACE else None)
            k = 1; q3 = _on_surface_f(inter, Bl, Pl) if ON_SURFACE else i3; uvn = f(uvl)
            while k < len(inter) - 1:
                idx = [0, k, k + 1] + ([k + 2] if k + 2 < len(inter) else [])
                if abs(_area_f([inter[t] for t in idx])) > EPS_AREA: new.append((nm, sl, [q3[t] for t in idx], [uvn[t] for t in idx]))
                k += 2
            pu2, _ = _cut_f(_ccw_f(_to2_f(Pu, Bu)), _ccw_f(_to2_f(i3, Bu)))
            for q in pu2: _emit_f(mu, su, q, Bu, Mu, new, Pu if ON_SURFACE else None)
            stat['shared region baked (cut-out on top)'] += 1
        if not gone: break
        keep = [k for k in range(len(faces)) if k not in gone]; pos = {k: q for q, k in enumerate(keep)}; faces = [faces[k] for k in keep]
        active = set(range(len(faces), len(faces) + len(new))) | {pos[k] for k in later if k in pos}; faces += new; stat['rounds'] = rnd + 1
    stat['pairs left'] = len(find_pairs(faces, road)); INFO.clear(); INFO.update(stat)
    log('       coplanar / near-coplanar polygons resolved without lift: %s' % dict(sorted(stat.items())))
    return faces

# ---------------------------------------------------------------- the gate
def gate(faces, road_xz, pairs_single=(), top=10, skip=None):
    """-> dict(exact, near, within_30m_of_road, worst, by_section, pairs): what can still z-fight (find_pairs).
    exact = gap below 1.5 cm, near = gap below the needed one. pairs_single: id() of faces drawn single-sided."""
    road = _road(road_xz); pr = find_pairs(faces, road, pairs_single)
    if skip is not None: pr = [p for p in pr if not skip(p[0], p[1])]
    cen = {i: _mean0(_rows3(faces[i][2])) for p in pr for i in p[:2]}
    dr = {i: math.sqrt(min((r[0] - c[0]) * (r[0] - c[0]) + (r[1] - c[2]) * (r[1] - c[2]) for r in road)) for i, c in cen.items()}
    rows = [(round(g, 3), round(nd, 3), faces[i][0][-16:], faces[i][1], faces[j][0][-16:], faces[j][1], tuple(_npround(v) for v in cen[i]), round(min(dr[i], dr[j]))) for i, j, g, sp, nd, ov in pr]
    exact = [r for r in rows if r[0] < 0.015]; near = sorted([r for r in rows if r[0] >= 0.015], key=lambda r: r[0] / max(r[1], 1e-6))
    kinds = collections.Counter((r[3].split('#')[0][:12], r[5].split('#')[0][:12]) for r in rows)
    return dict(exact=len(exact), near=len(near), within_30m_of_road=sum(1 for r in rows if r[7] < 30), worst=exact[:top] + near[:top], by_section=kinds.most_common(top), pairs=[(p[0], p[1]) for p in pr])
