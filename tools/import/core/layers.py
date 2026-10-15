"""Coplanar layers of a Model 2 course. The 1995 hardware has no Z-buffer: polygons are sorted and painted in priority
order, so the data freely lays polygons exactly on top of others (road paint, tyre marks, kerb stripes, shadows,
windows and signs on walls, ivy on rock). With a Z-buffer (SEGA Rally 3, Blender) such pairs flicker.
    layer_of(faces, mode) -> list of layer numbers (0 = bottom) and the number of layered faces
faces = [(material, section, corners, uv)]. Two faces are "stacked" when they overlap by more than a sliver
  mode 'plane': in the same plane (normals within 3 degrees, 1.5 cm apart at most), overlap measured in that plane
  mode 'plan' : seen from above, whatever their height (for faces that are all draped on the SR3 road)
Order inside a stack (the original per-polygon sort mode bits were not decoded - GUESS, chosen so that the result looks
like the game): a cut-out (_t) tile lies over an opaque one; otherwise the smaller polygon lies over the larger one;
ties: the later polygon of the list. A face's layer = 1 + the highest layer among the faces under it."""
import collections
import numpy as np

def _shrunk(Q, f=0.04):
    c = Q.mean(0); return c + (Q - c) * (1 - f)

def _overlap(A, B):
    """convex polygons in 2D (already shrunk): separating axis test"""
    for P, Q in ((A, B), (B, A)):
        E = np.roll(P, -1, 0) - P; N = np.stack([-E[:, 1], E[:, 0]], 1)
        a = P @ N.T; b = Q @ N.T
        if ((a.max(0) < b.min(0)) | (b.max(0) < a.min(0))).any(): return False
    return True

def _area(P):
    P = np.asarray(P, float); return 0.5 * sum(np.linalg.norm(np.cross(P[k] - P[0], P[k + 1] - P[0])) for k in range(1, len(P) - 1))

def pairs_of(faces, mode='plane', cell=6.0, tol=0.015):
    """-> (set of index pairs of stacked faces, area per face, cut-out flag per face)"""
    n = len(faces); P3 = [np.array(f[2], float) for f in faces]; area = np.array([_area(p) for p in P3]); cut = np.array([str(f[0]).endswith('_t') for f in faces])
    nrm = np.zeros((n, 3)); ok = np.zeros(n, bool)
    for i, p in enumerate(P3):
        v = np.cross(p[1] - p[0], p[2] - p[0]); l = np.linalg.norm(v)
        if l > 1e-9 and area[i] > 1e-4: nrm[i] = v / l; ok[i] = True
    grid = collections.defaultdict(list)
    for i, p in enumerate(P3):
        if not ok[i]: continue
        lo = np.floor(p[:, [0, 2]].min(0) / cell).astype(int); hi = np.floor(p[:, [0, 2]].max(0) / cell).astype(int)
        if (hi - lo).max() > 40: continue                              # huge backdrop faces: not layered
        for x in range(lo[0], hi[0] + 1):
            for z in range(lo[1], hi[1] + 1): grid[(x, z)].append(i)
    pairs = set()
    for lst in grid.values():
        if len(lst) < 2: continue
        for a_ in range(len(lst)):
            i = lst[a_]
            for b_ in range(a_ + 1, len(lst)):
                j = lst[b_]
                if (i, j) in pairs: continue
                pi, pj = P3[i], P3[j]
                if (pi.min(0) > pj.max(0) + 0.02).any() or (pj.min(0) > pi.max(0) + 0.02).any(): continue
                if mode == 'plane':
                    if abs(nrm[i] @ nrm[j]) < 0.9986: continue                        # 3 degrees
                    if np.abs((pj - pi[0]) @ nrm[i]).max() > tol or np.abs((pi - pj[0]) @ nrm[j]).max() > tol: continue
                    u = pi[1] - pi[0]; u /= np.linalg.norm(u); w = np.cross(nrm[i], u); A = np.stack([(pi - pi[0]) @ u, (pi - pi[0]) @ w], 1); B = np.stack([(pj - pi[0]) @ u, (pj - pi[0]) @ w], 1)
                else: A = pi[:, [0, 2]]; B = pj[:, [0, 2]]
                if _overlap(_shrunk(A), _shrunk(B)): pairs.add((i, j))
    return pairs, area, cut

def layer_of(faces, mode='plane', cell=6.0):
    pairs, area, cut = pairs_of(faces, mode, cell); n = len(faces)
    nb = collections.defaultdict(list)
    for i, j in pairs: nb[i].append(j); nb[j].append(i)
    order = sorted(nb, key=lambda i: (cut[i], -area[i], i)); layer = np.zeros(n, int); seen = set()
    for i in order:
        under = [layer[j] for j in nb[i] if j in seen]; layer[i] = 1 + max(under) if under else 0; seen.add(i)
    return layer, int((layer > 0).sum()), len(nb)
