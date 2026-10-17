"""Coplanar layers of a Model 2 course. The 1995 hardware has no Z-buffer: polygons are sorted and painted in priority
order, so the data freely lays polygons exactly on top of others (road paint, tyre marks, kerb stripes, shadows,
windows and signs on walls, ivy on rock). With a Z-buffer (SEGA Rally 3, Blender) such pairs flicker.
    layer_of(faces, mode) -> list of layer numbers (0 = bottom) and the number of layered faces
faces = [(material, section, corners, uv)]. Two faces are "stacked" when they overlap by more than a sliver
  mode 'plane': in the same plane (normals within 3 degrees, 1.5 cm apart at most), overlap measured in that plane
  mode 'plan' : seen from above, whatever their height (for faces that are all draped on the SR3 road)
Order inside a stack (the original per-polygon sort mode bits were not decoded - GUESS, chosen so that the result looks
like the game): a cut-out (_t) tile lies over an opaque one; otherwise the smaller polygon lies over the larger one;
ties: the later polygon of the list. A face's layer = 1 + the highest layer among the faces under it.
Without numpy since 2026-10-15 (kb 31): plain floats on three or four corners (numpy's small arrays cost more than the arithmetic), each
product written in the order numpy's call gave it: a fresh 3-vector's norm and a 3-row x vector product (BLAS) add (p0 + p2) + p1; the
dot of two rows of the normals' (n, 3) array follows where the second row sits in memory (16-byte aligned: (p0 + p2) + p1, 8 bytes off:
(p0 + p1) + p2); a two-term product is p0 + p1. layer_of / pairs_of give lists where they gave numpy arrays (the build only iterates them)."""
import collections, math

def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _n3(v): return math.sqrt((v[0] * v[0] + v[2] * v[2]) + v[1] * v[1])          # np.linalg.norm of a fresh 3-vector
def _mv(v, s): return 0.0 + ((v[0] * s[0] + v[2] * s[2]) + v[1] * s[1])          # one row of (k, 3) @ s (dgemv, added to y = 0)

def _shrunk(Q, f=0.04):
    """the polygon (2-D corners) shrunk towards its corner mean: c = Q.mean(0); c + (Q - c) * (1 - f)"""
    k = len(Q); c = [(0.0 + sum_seq([q[a] for q in Q])) / k for a in (0, 1)]; g = 1 - f
    return [(c[0] + (q[0] - c[0]) * g, c[1] + (q[1] - c[1]) * g) for q in Q]
def sum_seq(v):
    s = 0.0
    for x in v: s += x
    return s

def _overlap(A, B):
    """convex polygons in 2D (already shrunk): separating axis test (numpy: a = P @ N.T, the two products p0 + p1)"""
    for P, Q in ((A, B), (B, A)):
        k = len(P); N = [(-(P[(i + 1) % k][1] - P[i][1]), P[(i + 1) % k][0] - P[i][0]) for i in range(k)]
        for n_ in N:
            a = [p[0] * n_[0] + p[1] * n_[1] for p in P]; b = [q[0] * n_[0] + q[1] * n_[1] for q in Q]
            if max(a) < min(b) or max(b) < min(a): return False
    return True

def _area(P):
    """0.5 * the sum of the fan's cross products' lengths (numpy: np.linalg.norm(np.cross(P[k] - P[0], P[k + 1] - P[0])) for k ...)"""
    P = [tuple(float(v) for v in p) for p in P]; s = 0
    for k in range(1, len(P) - 1): s = s + _n3(_cross(_sub(P[k], P[0]), _sub(P[k + 1], P[0])))
    return 0.5 * s

def pairs_of(faces, mode='plane', cell=6.0, tol=0.015):
    """-> (set of index pairs of stacked faces, area per face, cut-out flag per face)"""
    n = len(faces); P3 = [[tuple(float(v) for v in q) for q in f[2]] for f in faces]; area = [_area(p) for p in P3]; cut = [str(f[0]).endswith('_t') for f in faces]
    nrm = [(0.0, 0.0, 0.0)] * n; ok = [False] * n
    for i, p in enumerate(P3):
        v = _cross(_sub(p[1], p[0]), _sub(p[2], p[0])); l = _n3(v)
        if l > 1e-9 and area[i] > 1e-4: nrm[i] = (v[0] / l, v[1] / l, v[2] / l); ok[i] = True
    grid = collections.defaultdict(list)
    for i, p in enumerate(P3):
        if not ok[i]: continue
        lo = (math.floor(min(q[0] for q in p) / cell), math.floor(min(q[2] for q in p) / cell)); hi = (math.floor(max(q[0] for q in p) / cell), math.floor(max(q[2] for q in p) / cell))
        if max(hi[0] - lo[0], hi[1] - lo[1]) > 40: continue                # huge backdrop faces: not layered
        for x in range(lo[0], hi[0] + 1):
            for z in range(lo[1], hi[1] + 1): grid[(x, z)].append(i)
    mn = [tuple(min(q[a] for q in p) for a in range(3)) for p in P3]; mx = [tuple(max(q[a] for q in p) for a in range(3)) for p in P3]
    pairs = set()
    for lst in grid.values():
        if len(lst) < 2: continue
        for a_ in range(len(lst)):
            i = lst[a_]
            for b_ in range(a_ + 1, len(lst)):
                j = lst[b_]
                if (i, j) in pairs: continue
                if any(mn[i][a] > mx[j][a] + 0.02 or mn[j][a] > mx[i][a] + 0.02 for a in range(3)): continue
                pi, pj = P3[i], P3[j]
                if mode == 'plane':
                    ni, nj = nrm[i], nrm[j]
                    d = (ni[0] * nj[0] + ni[2] * nj[2]) + ni[1] * nj[1] if j % 2 == 0 else (ni[0] * nj[0] + ni[1] * nj[1]) + ni[2] * nj[2]      # nrm[i] @ nrm[j]: row j's place in memory
                    if abs(d) < 0.9986: continue                        # 3 degrees
                    if max(abs(_mv(_sub(q, pi[0]), ni)) for q in pj) > tol or max(abs(_mv(_sub(q, pj[0]), nj)) for q in pi) > tol: continue
                    u = _sub(pi[1], pi[0]); lu = _n3(u); u = (u[0] / lu, u[1] / lu, u[2] / lu); w = _cross(ni, u)
                    A = [(_mv(_sub(q, pi[0]), u), _mv(_sub(q, pi[0]), w)) for q in pi]; B = [(_mv(_sub(q, pi[0]), u), _mv(_sub(q, pi[0]), w)) for q in pj]
                else: A = [(q[0], q[2]) for q in pi]; B = [(q[0], q[2]) for q in pj]
                if _overlap(_shrunk(A), _shrunk(B)): pairs.add((i, j))
    return pairs, area, cut

def layer_of(faces, mode='plane', cell=6.0):
    pairs, area, cut = pairs_of(faces, mode, cell); n = len(faces)
    nb = collections.defaultdict(list)
    for i, j in pairs: nb[i].append(j); nb[j].append(i)
    order = sorted(nb, key=lambda i: (cut[i], -area[i], i)); layer = [0] * n; seen = set()
    for i in order:
        under = [layer[j] for j in nb[i] if j in seen]; layer[i] = 1 + max(under) if under else 0; seen.add(i)
    return layer, sum(1 for v in layer if v > 0), len(nb)
