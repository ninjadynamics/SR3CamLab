"""Headless Blender: from which side is every polygon open to the world?
    blender.exe -b --factory-startup --python bl_sides.py -- <faces.npz> <out.npy>
faces.npz: V (n x 3 corners, y up), F (m x 4 corner indices, a triangle repeats its last corner), ACT (m bool: polygons to test; the
rest only block rays). out.npy: m x 4 = share of the rays that ESCAPE (hit nothing within 600 m) from the winding side and from the other side, then the MEAN FREE PATH in metres (each ray capped at 100) of the same two fans; the
fan = 32 fixed directions over each side's hemisphere. Deterministic."""
import sys, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
argv = sys.argv[sys.argv.index('--') + 1:]; d = np.load(argv[0]); V = d['V'].astype(float); F = d['F']; ACT = d['ACT']
polys = [tuple(int(i) for i in (f[:3] if f[2] == f[3] else f)) for f in F]
tree = BVHTree.FromPolygons([tuple(v) for v in V], polys, all_triangles=False, epsilon=0.0)
# 32 directions on the upper hemisphere of a local frame (z = the side's normal): a sunflower pattern, more of them near the normal
CAP = 100.0
K = 32; H = []
for k in range(K):
    u = (k + 0.5) / K; r = math.sqrt(u) * 0.985; a = k * 2.399963229728653; H.append((r * math.cos(a), r * math.sin(a), math.sqrt(max(1.0 - r * r, 0.0))))
out = np.zeros((len(F), 4), np.float32)
for i, f in enumerate(F):
    if not ACT[i]: continue
    P = V[list(dict.fromkeys(int(x) for x in f))]
    if len(P) < 3: continue
    n = np.zeros(3)
    for k in range(len(P)): a, b = P[k], P[(k + 1) % len(P)]; n += np.cross(a, b)
    ln = np.linalg.norm(n)
    if ln < 1e-9: continue
    n /= ln; c = P.mean(0); t = np.cross(n, [0.0, 1.0, 0.0] if abs(n[1]) < 0.9 else [1.0, 0.0, 0.0]); t /= np.linalg.norm(t); b = np.cross(n, t)
    for s, sg in enumerate((1.0, -1.0)):
        o = Vector(tuple(c + sg * n * 0.06)); free = 0.0; esc = 0
        for hx, hy, hz in H:
            dv = t * hx + b * hy + n * (sg * hz); hit = tree.ray_cast(o, Vector(tuple(dv)), 600.0)
            free += CAP if hit[0] is None else min(hit[3], CAP)
            if hit[0] is None: esc += 1
        out[i, s] = esc / K; out[i, 2 + s] = free / K                 # share of the rays that escape ; mean free path of the fan in metres (an escaped ray counts CAP)
np.save(argv[1], out)
print('bl_sides: %d polygons tested of %d' % (int(ACT.sum()), len(F)))
