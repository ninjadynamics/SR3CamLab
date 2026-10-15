"""seal1995 on the meshes of a built step (nothing is written): gaps counted before and after.   python seal_test.py <step>"""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..')))      # tools/import/core
import sys, os, time, struct, collections, numpy as np
from common import *
import sbfw, meshgen, seal1995
step = sys.argv[1]; tf = track_files(os.path.join(OUT, step, 'Desert4')); f = sbfw.read_sbf(tf['master_gfx_xdata']); ch = list(f.chunks)
def tris(chunks):
    mats = {c.id: c for c in chunks if c.kind == 2}; out = []
    for c in chunks:
        if c.kind != 1 or (c.id >> 16) != 0xc1a7: continue
        m = meshgen.parse_mesh(c); mt = mats.get(m['groups'][0][4])
        if mt is not None and len(mt.data) == 1848 and (struct.unpack_from('<I', mt.data, 0x4d4)[0] or struct.unpack_from('<I', mt.data, 0x4e4)[0]): continue
        I = np.asarray(m['idx']).astype(np.int64); p = m['verts']['p'][:, :3]; a, b, c2 = I[:-2], I[1:-1], I[2:]; ok = (a != b) & (b != c2) & (a != c2); out.append(np.stack([p[a[ok]], p[b[ok]], p[c2[ok]]], 1))
    return np.concatenate(out)
LEFT = []
def count(P, tag):
    V = (P.reshape(-1, 3) + np.float32(0)).astype(np.float32); raw = np.ascontiguousarray(V).view(np.dtype((np.void, 12))).ravel(); uq, first, inv = np.unique(raw, return_index=True, return_inverse=True); U = V[first].astype(np.float64); inv = inv.ravel()
    lab = seal1995._clusters(U, 0.001); near = len(U) - len(np.unique(lab)); tri = inv.reshape(-1, 3); tri = tri[(tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])]      # (triangles that are drawn: three different places)
    E = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]); E.sort(axis=1); E = np.unique(E, axis=0); used = np.unique(tri); xo = used[np.argsort(U[used, 0], kind='stable')]; xs = U[xo, 0]; TOL = 0.001; nj = 0
    i0s = np.searchsorted(xs, np.minimum(U[E[:, 0], 0], U[E[:, 1], 0]) - TOL); i1s = np.searchsorted(xs, np.maximum(U[E[:, 0], 0], U[E[:, 1], 0]) + TOL)
    for (a, b), i0, i1 in zip(E.tolist(), i0s.tolist(), i1s.tolist()):
        if i1 - i0 <= 2: continue
        c = xo[i0:i1]; A = U[a]; ab = U[b] - A; L2 = float(ab @ ab)
        if L2 < 4e-6: continue
        Q = U[c] - A; t = (Q @ ab) / L2; e = TOL / np.sqrt(L2); m = (t > e) & (t < 1 - e)
        if m.any():
            k = int((np.linalg.norm(Q[m] - t[m, None] * ab, axis=1) < TOL).sum()); nj += k
            if k and len(LEFT) < 12 and tag.startswith('after'): LEFT.append((U[a].round(4).tolist(), U[b].round(4).tolist(), U[c[m][np.linalg.norm(Q[m] - t[m, None] * ab, axis=1) < TOL][0]].round(4).tolist()))
    area = 0.5 * np.linalg.norm(np.cross(P[:, 1].astype(np.float64) - P[:, 0], P[:, 2].astype(np.float64) - P[:, 0]), axis=1).sum()
    print('%s: opaque triangles %d, area %.3f m2 ; places that have a different place within 1 mm: %d ; corners on the inside of an edge: %d' % (tag, len(P), area, near, nj), flush=True)
count(tris(ch), "before")
for k in range(2):
    r = seal1995.seal(ch); count(tris(ch), "after pass %d" % (k + 1))
    if not r[1]: break

for l in LEFT: print(l)
