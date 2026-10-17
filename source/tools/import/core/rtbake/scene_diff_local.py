"""An edited scene against the build it stands on, face by face -> the patch file.
    python scene_diff.py <base decoded.obj> <its texmap.json> <edited scene dump .pkl (bl_dump.py)> <texmap.json of the build that scene was decoded from> <out.json> <number> <needs,...> [key=value settings ...]
A face = its tile and its three corners (the scene's faces of more than three corners as Blender cuts them). What the scene has and the base
has not is ADDED; what the base has and the scene has not is either MOVED (a face of the same tile with the very same texture coordinates
is in the scene with other corners: Blender keeps a face's mapping when its corners are dragged) or REMOVED.
Sea faces are left out on both sides when a "sea" setting is given: the sheet is the importer's own and the setting says how it is made."""
import sys, json, os, collections, itertools
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'blendpatch'))
from check_build import load_pkl, tiles
from patch_to_json import export_sha1, f32

def from_obj(path, tile):
    V = []; VT = []; out = []; cur = None; road = False
    for ln in open(path):
        if ln.startswith('v '): V.append(tuple(map(float, ln.split()[1:4])))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('usemtl'): cur = ln.split()[1]; road = cur.split('_a')[0] not in tile
        elif ln.startswith('f ') and not road:
            ix = [tuple(int(a) - 1 for a in t.split('/')) for t in ln.split()[1:]]; assert len(ix) == 3
            out.append((tile[cur.split('_a')[0]], np.array([V[a] for a, b in ix], np.float32), np.array([VT[b] for a, b in ix], np.float32)))
    return out
def from_dump(d, tile):
    out = []; co = d['co_local']; uv = np.asarray(d['uv'], np.float32); lv = d['loop_vert']; ng = 0
    for t in range(len(d['tri_poly'])):
        k = int(d['tri_poly'][t]); name = d['mats'][int(d['mat_index'][k])].split('_a')[0].split('.')[0]
        if name.startswith('facade_'): tile[name] = name                 # a facade picture composed for this scene (facade_recipes.py): a tile of its own, by its own name
        if name not in tile: continue
        L = d['tri_loops'][t]; ng += int(d['loop_total'][k]) > 3; out.append((tile[name], co[lv[L]].astype(np.float32), uv[L]))
    return out, ng
key = lambda f: (f[0], tuple(sorted(tuple(np.round(p.astype(float), 3) + 0.0) for p in f[1])))
def area(P):                                                             # 0.5 |(P1 - P0) x (P2 - P0)|, to the bit what np.cross / np.linalg.norm on the three corners gave (the cross product term by term, the length as sqrt(x.dot(x)))
    a = P[0]; b = P[1]; c = P[2]; ax = float(a[0]); ay = float(a[1]); az = float(a[2]); ux = float(b[0]) - ax; uy = float(b[1]) - ay; uz = float(b[2]) - az; vx = float(c[0]) - ax; vy = float(c[1]) - ay; vz = float(c[2]) - az
    n = np.array((uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)); return 0.5 * __import__('math').sqrt(float(n.dot(n)))
def keys(F):
    """key(f) of every face of a list, the rounding done for all at once"""
    if not F: return []
    R = np.round(np.array([f[1] for f in F], np.float64), 3) + 0.0; return [(f[0], tuple(sorted(map(tuple, r)))) for f, r in zip(F, R.tolist())]
pts = lambda a: [[f32(x) for x in p] for p in a]

def main(obj, tm_a, pkl, tm_b, out, number, needs, *sets):
    settings = {}; bake = None
    for s in sets:
        k, v = s.split('=', 1)
        if k == 'bake': bake = json.load(open(v))                        # the recipes of the scene's facade pictures (facade_recipes.py)
        else: settings[k] = json.loads(v)
    ta = tiles(tm_a); tb = tiles(tm_b); A = from_obj(obj, ta); B, ng = from_dump(load_pkl(pkl), tb)
    ka = collections.defaultdict(list); kb = collections.defaultdict(list)
    for f, k_ in zip(A, keys(A)): ka[k_].append(f)
    for f, k_ in zip(B, keys(B)): kb[k_].append(f)
    def same_map(f, g):                                                 # the same picture on the same corners (whole repeats aside), seen from the same side
        P, Q = f[1].astype(float), g[1].astype(float); perm = [int(np.argmin(np.linalg.norm(Q - p, axis=1))) for p in P]
        if len(set(perm)) < 3: return True
        if float(np.cross(P[1] - P[0], P[2] - P[0]) @ np.cross(Q[perm[1]] - Q[perm[0]], Q[perm[2]] - Q[perm[0]])) < 0: return False
        d = f[2].astype(float) - g[2].astype(float)[perm]; d = d - np.round(d[0]); return float(np.abs(d).max()) < 0.004
    onlya = []; onlyb = []; same = remap = 0
    for k in sorted(set(ka) | set(kb)):                                  # (sorted: the walk over a set of names went in another order every run, and with it the order of the faces in the patch file and of everything built from it)
        x, y = list(ka.get(k, [])), list(kb.get(k, []))
        keepx = []                                                      # faces on the same corners pair up when they also show the same picture; a face re-mapped in the scene is removed and added
        for f in x:
            j = next((j for j, g in enumerate(y) if same_map(f, g)), None)
            if j is None: keepx.append(f)
            else: y.pop(j); same += 1
        remap += min(len(keepx), len(y)); onlya += keepx; onlyb += y
    print('faces on the same corners but with another mapping or facing (removed and added again): %d' % remap)
    # a corner that rounds to the other side of a millimetre: matched by distance (2 mm)
    gb = collections.defaultdict(list)
    for j, g in enumerate(onlyb): gb[(g[0], tuple(np.floor(g[1].astype(float).mean(0) / 2.0).astype(int)))].append(j)
    usedb = set(); keepa = []
    for f in onlya:
        c = np.floor(f[1].astype(float).mean(0) / 2.0).astype(int); hit = None
        for d in itertools.product((-1, 0, 1), repeat=3):
            for j in gb.get((f[0], tuple(c + d)), ()):
                g = onlyb[j]
                if j not in usedb and all(np.linalg.norm(g[1].astype(float) - p, axis=1).min() < 0.002 for p in f[1].astype(float)) and all(np.linalg.norm(f[1].astype(float) - p, axis=1).min() < 0.002 for p in g[1].astype(float)) and same_map(f, g): hit = j; break
            if hit is not None: break
        if hit is None: keepa.append(f)
        else: usedb.add(hit); same += 1
    onlya = keepa; onlyb = [g for j, g in enumerate(onlyb) if j not in usedb]
    print('base %d faces ; scene %d faces (%d of them cut from faces of more than three corners) ; the same on both sides %d ; only in the base %d ; only in the scene %d' % (len(A), len(B), ng, same, len(onlya), len(onlyb)))
    print('   only in the base, by tile:', dict(collections.Counter(f[0][-26:] for f in onlya).most_common(12)))
    print('   only in the scene, by tile:', dict(collections.Counter(f[0][-26:] for f in onlyb).most_common(12)))
    if 'sea' in settings:                                             # the sea sheet is the importer's own (made after the patches): the setting says how, its faces are not listed
        ns = (sum('sea' in f[0] for f in onlya), sum('sea' in f[0] for f in onlyb)); onlya = [f for f in onlya if 'sea' not in f[0]]; onlyb = [f for f in onlyb if 'sea' not in f[0]]
        print('   sea faces left to the setting %s: %d only in the base, %d only in the scene' % (settings['sea'], ns[0], ns[1]))
    M = json.load(open(tm_b)); comp = [f for f in onlyb if f[0] in M.get('recipes', {})]; print('   LOCAL BUILD ONLY: the scene adds %d faces of %d composed tiles (allowed here; such a patch cannot ship)' % (len(comp), len({f[0] for f in comp})))
    deg = [f for f in onlyb if area(f[1]) < 1e-9]; onlyb = [f for f in onlyb if area(f[1]) >= 1e-9]
    head = dict(format='sr3lab course patch', version=2 if onlya else 1, course=dict(game='src', course='1', name='mountain'), base=dict(course_export_sha1=export_sha1(), needs=[int(x) for x in needs.split(',') if x]),
                made_by='scene_diff.py: an edited Blender scene against the build it stands on', settings=settings,
                space='the build decoded back (preview_obj.py): x, y up, z = -gameZ of the 1995 course, metres; uv as Blender has them (v up)')
    if not settings: head.pop('settings')
    add = [dict(tile=f[0], p=pts(f[1]), uv=[[f32(x) for x in q] for q in f[2]]) for f in onlyb]; rem = [dict(tile=f[0], p=pts(f[1])) for f in onlya]
    used = sorted({f[0] for f in onlyb if f[0].startswith('facade_')}); bk = []
    if used:
        by = {e['name']: e for e in (bake or [])}; miss = [n for n in used if n not in by]; assert not miss, 'the scene shows facade pictures with no recipe: %s' % miss
        bk = [by[n] for n in used]; head['version'] = 3
        print('   facade pictures in the scene: %d (%d faces) ; their recipes: %d source triangles' % (len(used), sum(f[0].startswith('facade_') for f in onlyb), sum(len(e['sources']) for e in bk)))
    NL = chr(10)
    with open(out, 'w', newline=NL) as fo:                                # one face a line: a change shows as changed lines
        fo.write('{' + NL + ''.join(' %s: %s,%s' % (json.dumps(k), json.dumps(v), NL) for k, v in head.items()))
        fo.write(' "remove": [' + NL + (',' + NL).join('  ' + json.dumps(a) for a in rem) + NL + ' ],' + NL)
        if bk: fo.write(' "bake": [' + NL + (',' + NL).join('  ' + json.dumps(e, separators=(',', ':')) for e in bk) + NL + ' ],' + NL)
        fo.write(' "add": [' + NL + (',' + NL).join('  ' + json.dumps(a) for a in add) + NL + ' ],' + NL + ' "move": []' + NL + '}' + NL)
    print('patch %s: %d faces to remove, %d to add (%.0f m2; %d with no area left out) ; %d bytes -> %s' % (number, len(rem), len(add), sum(area(f[1]) for f in onlyb), len(deg), os.path.getsize(out), out))
    return A, B, onlya, onlyb, settings

if __name__ == '__main__': R = main(*sys.argv[1:])
