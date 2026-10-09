"""A BUILD (decoded back by preview_obj.py) against a Blender scene dump (bl_dump.py), face by face: is it the same set of faces?
    python check_build.py <decoded.obj> <texmap.json of that build> <scene dump .pkl> <texmap.json of the build the scene was decoded from> [<patch.json>]
A face = its tile and its three corners. For every face found on both sides the side it faces and its texture coordinates (per corner,
whole repeats aside) are compared. With the patch file, differences are told apart: faces of the patch / original faces."""
import sys, json, pickle, collections, itertools
import numpy as np

def load_pkl(p):
    D = pickle.load(open(p, 'rb')); d = next(o for o in D['objects'] if o['name'].startswith('1995 course'))
    for k, v in list(d.items()):
        if isinstance(v, tuple) and len(v) == 4 and v[0] == 'nd': d[k] = np.frombuffer(v[3], v[1]).reshape(v[2])
    return d
def tiles(p): M = json.load(open(p)); return {'tex_%08x' % int(k): v['tile'] for k, v in M['scenery'].items()}
def from_obj(path, tile):
    V = []; VT = []; out = []; cur = None; road = False
    for ln in open(path):
        if ln.startswith('v '): V.append(tuple(map(float, ln.split()[1:4])))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('usemtl'): cur = ln.split()[1]; road = cur.split('_a')[0] not in tile
        elif ln.startswith('f ') and not road:
            ix = [tuple(int(a) - 1 for a in t.split('/')) for t in ln.split()[1:]]
            if len(ix) == 3: out.append((tile[cur.split('_a')[0]], np.array([V[a] for a, b in ix]), np.array([VT[b] for a, b in ix])))
    return out
def from_dump(d, tile):
    out = []; co = d['co_local'].astype(np.float64); uv = np.asarray(d['uv'], np.float64)
    for k in range(len(d['loop_total'])):
        s, n = int(d['loop_start'][k]), int(d['loop_total'][k]); vi = d['loop_vert'][s:s + n]; name = d['mats'][int(d['mat_index'][k])].split('_a')[0].split('.')[0]
        if n == 3 and name in tile: out.append((tile[name], co[vi], uv[s:s + n]))
    return out
key = lambda t, P: (t, tuple(sorted(tuple(np.round(p, 3) + 0.0) for p in P)))
nrm = lambda P: np.cross(P[1] - P[0], P[2] - P[0])

def main(obj, tm_new, pkl, tm_ctl, patch=None):
    A = from_obj(obj, tiles(tm_new)); B = from_dump(load_pkl(pkl), tiles(tm_ctl))
    ka = collections.defaultdict(list); kb = collections.defaultdict(list)
    for f in A: ka[key(f[0], f[1])].append(f)
    for f in B: kb[key(f[0], f[1])].append(f)
    onlya = [f for k, v in ka.items() for f in v[len(kb.get(k, [])):]]; onlyb = [f for k, v in kb.items() for f in v[len(ka.get(k, [])):]]
    for f in list(onlya):                                             # a corner that rounds to the other side of a millimetre: matched by distance (2 mm)
        for g in onlyb:
            if g[0] == f[0] and all(np.linalg.norm(g[1] - p, axis=1).min() < 0.002 for p in f[1]) and all(np.linalg.norm(f[1] - p, axis=1).min() < 0.002 for p in g[1]):
                ka[('near', id(f))] = [f]; kb[('near', id(f))] = [g]; onlya = [x for x in onlya if x is not f]; onlyb = [x for x in onlyb if x is not g]; break
    pk = []
    if patch: pk = [np.array(f_['p'], float) for f_ in json.load(open(patch))['add']]
    is_patch = lambda P: any(all(np.linalg.norm(Q - p, axis=1).min() < 0.002 for p in P) for Q in pk)
    same = flip = uvbad = 0; uvbad_patch = 0; uvmax = 0.0
    for k, va in ka.items():
        for f, g in zip(va, kb.get(k, [])):
            same += 1; na, nb = nrm(f[1]), nrm(g[1])
            if float(na @ nb) < 0: flip += 1
            d = 9.0                                                   # corners paired by place; a face with two corners at one place has more than one pairing: the best counts
            for pm in itertools.permutations(range(3)):
                if any(np.linalg.norm(g[1][pm[i]] - f[1][i]) > 0.002 for i in range(3)): continue
                e = f[2] - g[2][list(pm)]; e = e - e[0]; d = min(d, float(np.abs(e - np.round(e)).max()))
            uvmax = max(uvmax, d if d < 0.01 else 0.0)
            if d > 0.002:
                uvbad += 1; ip = is_patch(f[1]); uvbad_patch += int(ip)
                if not ip: print('      original face with other texture coordinates: %s at %s, off by %.4f of a tile ; build %s ; scene %s' % (f[0], np.round(f[1].mean(0), 2).tolist(), d, np.round(f[2], 4).tolist(), np.round(g[2], 4).tolist()))
    print('build: %d faces ; scene: %d faces ; the same face (tile and corners) on both sides: %d' % (len(A), len(B), same))
    print('   only in the build: %d (%d of them faces of the patch) ; only in the scene: %d (%d of the patch)' % (len(onlya), sum(is_patch(f[1]) for f in onlya), len(onlyb), sum(is_patch(f[1]) for f in onlyb)))
    print('   of the %d: facing the other way: %d ; texture coordinates different: %d (%d of them faces of the patch, %d original faces) ; largest difference among the rest: %.5f of a tile' % (same, flip, uvbad, uvbad_patch, uvbad - uvbad_patch, uvmax))
    if patch: print('   faces of the patch found in the build: %d of %d' % (sum(1 for f in A if is_patch(f[1])), len(pk)))
    for f in (onlya + onlyb)[:6]: print('      e.g. %s at %s' % (f[0], np.round(f[1].mean(0), 2).tolist()))

if __name__ == '__main__': main(*sys.argv[1:6])
