"""blend_diff.py <base.pkl> <edited.pkl> <out.pkl>: what the edited Blender file has that the base has not (faces by the places of their corners)."""
import sys, pickle, collections
import numpy as np
def load(p):
    D = pickle.load(open(p, 'rb'))
    for d in D['objects']:
        for k, v in list(d.items()):
            if isinstance(v, tuple) and len(v) == 4 and v[0] == 'nd': d[k] = np.frombuffer(v[3], v[1]).reshape(v[2])
    return D
A = load(sys.argv[1]); B = load(sys.argv[2])
def faces(o):
    q = np.round(o['co'] * 1000.0).astype(np.int64); out = []
    for k in range(len(o['loop_total'])):
        s, n = int(o['loop_start'][k]), int(o['loop_total'][k]); vi = o['loop_vert'][s:s + n]
        out.append((frozenset(map(tuple, q[vi].tolist())), k))
    return out
rep = {}; patch = []
for oa in A['objects']:
    ob = next((x for x in B['objects'] if x['name'] == oa['name']), None)
    if ob is None: print('object gone from the edited file:', oa['name']); continue
    fa = faces(oa); fb = faces(ob); ca = collections.Counter(k for k, _ in fa); cb = collections.Counter(k for k, _ in fb)
    added = [i for k, i in fb if k not in ca]; removed = [i for k, i in fa if k not in cb]
    dup = sum(max(0, cb[k] - ca[k]) for k in cb if k in ca)
    pa = set(map(tuple, np.round(oa['co'] * 1000).astype(np.int64).tolist())); pb = set(map(tuple, np.round(ob['co'] * 1000).astype(np.int64).tolist()))
    print('%-42s base %6d faces / %6d vertices ; edited %6d / %6d ; faces added %d, removed %d, existing faces doubled %d ; vertex places new %d, gone %d ; modifiers %s' %
          (oa['name'][:42], len(fa), len(oa['co']), len(fb), len(ob['co']), len(added), len(removed), dup, len(pb - pa), len(pa - pb), ob['modifiers']))
    if added or removed:
        n = ob['loop_total'][added]; print('   added faces by number of corners:', dict(collections.Counter(n.tolist())))
        for k in added:
            s, m = int(ob['loop_start'][k]), int(ob['loop_total'][k]); vi = ob['loop_vert'][s:s + m]; P = ob['co'][vi]
            new_corners = sum(1 for p in np.round(P * 1000).astype(np.int64).tolist() if tuple(p) not in pa)
            patch.append(dict(obj=oa['name'], P=P, uv=(ob['uv'][s:s + m] if ob['uv'] is not None else None), mat=ob['mats'][ob['mat_index'][k]] if ob['mats'] else None, new_corners=new_corners, index=k))
        rep[oa['name']] = dict(removed=[(oa['co'][oa['loop_vert'][int(oa['loop_start'][k]):int(oa['loop_start'][k]) + int(oa['loop_total'][k])]], oa['mats'][oa['mat_index'][k]]) for k in removed])
for ob in B['objects']:
    if not any(x['name'] == ob['name'] for x in A['objects']): print('NEW object in the edited file: %s, %d faces' % (ob['name'], len(ob['loop_total'])))
pickle.dump(dict(patch=patch, rep=rep), open(sys.argv[3], 'wb'))
if patch:
    def area(P):
        n = np.zeros(3)
        for i in range(len(P)): n += np.cross(P[i], P[(i + 1) % len(P)])
        return 0.5 * np.linalg.norm(n)
    ar = np.array([area(p['P']) for p in patch]); ed = np.array([max(np.linalg.norm(p['P'] - np.roll(p['P'], -1, axis=0), axis=1)) for p in patch])
    print('added faces: area total %.1f m2, median %.2f, largest %.1f ; longest edge median %.2f m, largest %.1f m' % (ar.sum(), np.median(ar), ar.max(), np.median(ed), ed.max()))
    print('corners of added faces that sit on an existing vertex: %d of %d' % (sum(len(p['P']) - p['new_corners'] for p in patch), sum(len(p['P']) for p in patch)))
    print('materials of added faces:', collections.Counter(p['mat'] for p in patch).most_common(12))
    print('added faces with a uv layer: %d ; with zero uv area: %d' % (sum(p['uv'] is not None for p in patch), sum(1 for p in patch if p['uv'] is not None and abs(float(np.sum(p['uv'][:, 0] * np.roll(p['uv'][:, 1], -1) - np.roll(p['uv'][:, 0], -1) * p['uv'][:, 1]))) < 1e-9)))
