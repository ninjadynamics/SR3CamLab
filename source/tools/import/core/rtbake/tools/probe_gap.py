"""What a view's pixel looks at in the collected polygons of two builds.   python probe_gap.py <views.json> <view name> <px> <py> <faces.pkl A> <faces.pkl B>"""
import sys, json, pickle, math
import numpy as np
V = next(v for v in json.load(open(sys.argv[1])) if v['name'] == sys.argv[2]); px, py = float(sys.argv[3]), float(sys.argv[4]); W = float(V.get('px', 960)); H = W * 600 / 960
import os
FZ = -1.0 if os.environ.get('FLIPZ') else 1.0; E = np.array(V['eye'], float) * [1, 1, FZ]; T = np.array(V['target'], float) * [1, 1, FZ]; f = T - E; f /= np.linalg.norm(f); r = np.cross(f, [0.0, 1.0, 0.0]) * FZ; r /= np.linalg.norm(r); u = np.cross(r, f)
th = 18.0 / float(V['lens']); d = f + r * ((px + 0.5) / W * 2 - 1) * th + u * (1 - (py + 0.5) / H * 2) * th * H / W; d /= np.linalg.norm(d)
def tris(G):
    out = []; who = []
    for k, fc in enumerate(G['faces'] + G['sky'] + G['extra']):
        P = np.asarray(fc[2], float)
        if len(P) < 3 or str(fc[1]) == 'sea': continue
        for a, b, c in (((0, 1, 2), (0, 2, 3)) if len(P) >= 4 else ((0, 1, 2),)): out.append((P[a], P[b], P[c])); who.append(k)
    return np.array(out), np.array(who)
def hits(Tr, o, d):
    e1 = Tr[:, 1] - Tr[:, 0]; e2 = Tr[:, 2] - Tr[:, 0]; p = np.cross(d, e2); det = (e1 * p).sum(1); ok = np.abs(det) > 1e-12; inv = 1.0 / np.where(ok, det, 1.0); tv = o - Tr[:, 0]
    b1 = (tv * p).sum(1) * inv; q = np.cross(tv, e1); b2 = (q @ d) * inv; t = (e2 * q).sum(1) * inv; m = ok & (b1 >= -1e-9) & (b2 >= -1e-9) & (b1 + b2 <= 1 + 1e-9) & (t > 1e-6); return np.nonzero(m)[0], t
res = []
for path in sys.argv[5:7]:
    G = pickle.load(open(path, 'rb')); Tr, who = tris(G); F = G['faces'] + G['sky'] + G['extra']; idx, t = hits(Tr, E, d); o = idx[np.argsort(t[idx])][:6]
    side = lambda i: 'FRONT' if float(np.cross(Tr[i, 1] - Tr[i, 0], Tr[i, 2] - Tr[i, 0]) @ (E - Tr[i, 0])) > 0 else 'back'
    print(path.split('/')[-2], ': the ray meets', [(round(float(t[i]), 2), str(F[who[i]][0])[-34:], str(F[who[i]][1]), side(i)) for i in o]); res.append((G, Tr, who, F, o, t))
(G, Tr, who, F, o, t) = res[0]; opaque = [i for i in o if not str(F[who[i]][0]).split('|')[0].endswith('_t')]
if opaque:
    i = opaque[0]; X = E + d * t[i]; fc = F[who[i]]; print('first solid polygon in A at', X.round(2).tolist(), 'tile', fc[0], 'section', fc[1], 'corners', np.asarray(fc[2]).round(2).tolist())
    (G2, Tr2, who2, F2, o2, t2) = res[1]; c = Tr2.mean(1); near = np.nonzero(np.linalg.norm(c - X, axis=1) < 4.0)[0]; n = np.cross(Tr2[near, 1] - Tr2[near, 0], Tr2[near, 2] - Tr2[near, 0]); n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    dist = np.abs(((X - Tr2[near, 0]) * n).sum(1)); same = [k for k in range(len(near)) if str(F2[who2[near[k]]][0]) == str(fc[0]) and str(F2[who2[near[k]]][1]) == str(fc[1])]
    print('B: %d triangles within 4 m of that point, %d of the same tile and section ; nearest plane distances of those: %s' % (len(near), len(same), np.sort(dist[same])[:8].round(2).tolist()))
    # every corner of the A polygon: how far is the nearest corner of B's polygons of the same tile and section
    PB = np.array([p for g in F2 if str(g[0]) == str(fc[0]) and str(g[1]) == str(fc[1]) for p in g[2]], float)
    if len(PB): print('corners of the A polygon -> nearest corner of the same tile and section in B (m):', [round(float(np.linalg.norm(PB - p, axis=1).min()), 2) for p in np.asarray(fc[2], float)])
