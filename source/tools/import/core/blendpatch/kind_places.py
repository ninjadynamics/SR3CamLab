"""patch_kinds.py's faces, NEW ones only, as places per group of classes (faces whose middles are within `link` m chain together)
    python kind_places.py <kinds.json> [link=8] [min=200]"""
import json, sys, collections
import numpy as np
F = json.load(open(sys.argv[1])); kv = dict(x.split('=', 1) for x in sys.argv[2:] if '=' in x); link = float(kv.get('link', 8)); amin = float(kv.get('min', 200))
def group(f):
    c = f['cls']
    if c in ('rock', 'dark:rock') : return 'rock ' + ('wall' if f['up'] == 'upright' else 'ground')
    if c in ('grass', 'dirt', 'dark:grass', 'dark:dirt', 'sand', 'gravel'): return 'soft ground ' + ('wall' if f['up'] == 'upright' else 'ground')
    if c == 'baked' or c.startswith('other:bake_') or c.startswith('house') or c in ('arcade', 'church', 'plaster_wall', 'brick_wall', 'window', 'door'): return 'facade'
    if c == 'roof': return 'roof'
    if c == 'cobbles': return 'pavement'
    if c in ('crown', 'tree', 'trunk', 'bare'): return 'tree'
    return 'other'
G = collections.defaultdict(list)
for f in F:
    if f['kind'] == 'NEW': G[group(f)].append(f)
for g, fs in sorted(G.items(), key=lambda x: -sum(f['area'] for f in x[1])):
    C = np.array([f['c'] for f in fs]); A = np.array([f['area'] for f in fs]); par = np.arange(len(fs))
    def find(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    k = np.floor(C / link).astype(np.int64); cell = collections.defaultdict(list)
    for i, kk in enumerate(map(tuple, k)): cell[kk].append(i)
    for i, kk in enumerate(map(tuple, k)):
        for d in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1), (1, -1, 0), (1, 0, -1), (0, 1, -1), (1, -1, -1), (1, 1, -1), (1, -1, 1)):
            for j in cell.get((kk[0] + d[0], kk[1] + d[1], kk[2] + d[2]), ()): par[find(i)] = find(j)
        for j in cell[kk]: par[find(i)] = find(j)
    P = collections.defaultdict(list)
    for i in range(len(fs)): P[find(i)].append(i)
    pl = sorted(P.values(), key=lambda ii: -A[ii].sum())
    print('%-18s %6.0f m2 in %d places; the largest:' % (g, A.sum(), len(pl)))
    for ii in pl[:8]:
        if A[ii].sum() < amin: break
        lo = C[ii].min(0); hi = C[ii].max(0); print('     %7.0f m2  %5d faces  centre (%.0f, %.0f, %.0f)  x %.0f..%.0f  y %.0f..%.0f  z %.0f..%.0f' % (A[ii].sum(), len(ii), *C[ii].mean(0), lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
