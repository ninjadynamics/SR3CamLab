"""Headless Blender: the rays of bake1995.py (Blender is used for its BVH only).
    blender.exe -b --factory-startup --python bl_bake.py -- <points file without .npz> <first> <last>
For every vertex (place P, facing N): V = share of the sun's disc it sees, A = share of the sky it sees (cosine weighted over the half
space of N), B = light coming back from what the sky rays hit (albedo of the hit x 1 if the sun reaches the hit, 0.3 if not).
A ray that meets a see-through texel of a cut-out (tree, fence, lamp) goes on. Vertices marked U (seen from both sides) take the
better of their two sides."""
import sys, pickle, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
argv = sys.argv[sys.argv.index('--') + 1:]; PATH, A0, A1 = argv[0], int(argv[1]), int(argv[2])
S = pickle.load(open(PATH + '.scene', 'rb')); D = np.load(PATH + '.npz'); P = D['P'][A0:A1].astype(float); N = D['N'][A0:A1].astype(float); U = D['U'][A0:A1]
T = S['tris'].astype(float); TU = S['uv'].astype(float); TM = S['mat']; ALB = S['albedo']; HOLES = S['holes']; SUN = np.asarray(S['sun'], float); SUN /= np.linalg.norm(SUN)
bvh = BVHTree.FromPolygons([tuple(v) for v in T.reshape(-1, 3)], [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(T))], all_triangles=True)
TN = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); TN /= np.maximum(np.linalg.norm(TN, axis=1), 1e-12)[:, None]
HAS = np.array([h is not None for h in HOLES], bool)

def cast(o, d, skip=0.12):
    """-> index of the first solid triangle met, or -1. The first `skip` metres do not count (the vertex's own polygon and the layers lying on it)."""
    o = Vector(o) + Vector(d) * skip
    for _ in range(12):
        loc, nrm, idx, dist = bvh.ray_cast(o, d)
        if idx is None: return -1, None
        m = TM[idx]
        if not HAS[m]: return idx, loc
        a, b, c = T[idx]; v0 = b - a; v1 = c - a; v2 = np.array(loc) - a; d00 = v0 @ v0; d01 = v0 @ v1; d11 = v1 @ v1; d20 = v2 @ v0; d21 = v2 @ v1; den = d00 * d11 - d01 * d01
        if abs(den) < 1e-12: return idx, loc
        w1 = (d11 * d20 - d01 * d21) / den; w2 = (d00 * d21 - d01 * d20) / den; uv = TU[idx][0] * (1 - w1 - w2) + TU[idx][1] * w1 + TU[idx][2] * w2
        h = HOLES[m]; x = int((uv[0] % 1.0) * h.shape[1]) % h.shape[1]; y = int(((1.0 - uv[1]) % 1.0) * h.shape[0]) % h.shape[0]
        if not h[y, x]: return idx, loc
        o = loc + Vector(d) * 0.02
    return -1, None

def frame(n):
    a = np.array([0.0, 1.0, 0.0]) if abs(n[1]) < 0.9 else np.array([1.0, 0.0, 0.0]); t = np.cross(n, a); t /= np.linalg.norm(t); return t, np.cross(n, t)
st, sb = frame(SUN); R = math.radians(1.6)
SUNDIRS = [SUN] + [SUN + math.tan(R) * (math.cos(a) * st + math.sin(a) * sb) for a in np.arange(6) * math.pi / 3]; SUNDIRS = [d / np.linalg.norm(d) for d in SUNDIRS]
KS = 16; HEMI = []
for i in range(KS):                                                  # cosine-weighted directions about +z (fixed set, turned by a per-vertex angle)
    r = math.sqrt((i + 0.5) / KS); ph = i * 2.399963; HEMI.append((r * math.cos(ph), r * math.sin(ph), math.sqrt(max(0.0, 1 - r * r))))
HEMI = np.array(HEMI)

def light(p, n, k):
    o = p + n * 0.03
    if n @ SUN <= 0.02: V = 0.0
    else: V = sum(1.0 for d in SUNDIRS if cast(o, Vector(d))[0] < 0) / len(SUNDIRS)
    t, b = frame(n); ang = (k * 0.618034) % 1.0 * 2 * math.pi; ca, sa = math.cos(ang), math.sin(ang); sky = 0.0; back = 0.0
    for hx, hy, hz in HEMI:
        d = (hx * ca - hy * sa) * t + (hx * sa + hy * ca) * b + hz * n; idx, loc = cast(o, Vector(d))
        if idx < 0: sky += 1.0; continue
        hn = TN[idx] if TN[idx] @ d < 0 else -TN[idx]; lit = 0.3
        if hn @ SUN > 0.05 and cast(np.array(loc) + hn * 0.03, Vector(SUN))[0] < 0: lit = 0.3 + 0.7 * float(hn @ SUN) / max(SUN[1], 0.3)
        back += float(ALB[TM[idx]]) * min(lit, 1.0)
    return V, sky / KS, back / KS

out = np.zeros((len(P), 3), np.float32)
for k in range(len(P)):
    n = N[k] / max(np.linalg.norm(N[k]), 1e-12); r = light(P[k], n, A0 + k)
    if U[k]:
        r2 = light(P[k], -n, A0 + k)
        if r2[0] + r2[1] > r[0] + r[1]: r = r2
    out[k] = r
    if k % 20000 == 0: print('bl_bake', A0 + k, flush=True)
np.save('%s.part_%d_%d.npy' % (PATH, A0, A1), out); print('bl_bake done', A0, A1)
