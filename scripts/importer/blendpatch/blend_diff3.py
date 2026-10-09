import sys, pickle, collections, numpy as np
import blend_diff as BD
A, B = BD.A, BD.B; oa = A['objects'][0]; ob = next(x for x in B['objects'] if x['name'] == oa['name']); K = pickle.load(open('blenddiff/classes.pkl', 'rb'))
def poly(o, k): s, n = int(o['loop_start'][k]), int(o['loop_total'][k]); return o['co'][o['loop_vert'][s:s + n]]
def mat(o, k): return o['mats'][o['mat_index'][k]]
def area(P): return 0.5 * float(np.linalg.norm(sum(np.cross(P[i], P[(i + 1) % len(P)]) for i in range(len(P)))))
C = np.loadtxt('F:/Jogos/SEGA Rally 3/SR3 track format/classic/courses/src/course1_mountain/src_course1_centreline.csv', delimiter=',', comments='#'); Cb = np.stack([C[:, 0], -C[:, 2], C[:, 1]], 1); n = len(Cb)
def lap(c): dd = np.linalg.norm(Cb[:, :2] - c[:2], axis=1); j = int(dd.argmin()); return 100.0 * j / n, float(dd[j]), float(c[2] - Cb[j, 2])
# --- the moved originals
mk = [k for k, _, _ in K['moved']]; D = np.concatenate([poly(ob, k) - poly(oa, k) for k in mk]); D = D[np.linalg.norm(D, axis=1) > 1e-3]
cen = np.mean([poly(oa, k).mean(0) for k in mk], axis=0); ext = np.ptp(np.concatenate([poly(oa, k) for k in mk]), axis=0)
print('MOVED ORIGINALS: %d triangles, material %s ; all in one place: centre %s, extent %s m ; at %.0f%% of the lap, %.0f m from the centre line' % (len(mk), collections.Counter(mat(oa, k) for k in mk).most_common(2), cen.round(1).tolist(), ext.round(1).tolist(), *lap(cen)[:2]))
print('   their corners moved by (x, y, z in Blender, z up): distinct vectors', [tuple(v) for v in np.unique(D.round(2), axis=0).tolist()][:6], '; corners moved %d of %d' % (len(D), 3 * len(mk)))
# --- new faces: degenerate ones
new = K['new']; ar = {k: area(poly(ob, k)) for k in new}; deg = [k for k in new if ar[k] < 0.01]; good = [k for k in new if ar[k] >= 0.01]
print('NEW FACES: %d ; with (almost) no area: %d ; real: %d' % (len(new), len(deg), len(good)))
kinds = collections.Counter()
for k in deg:
    P = poly(ob, k); u = len({tuple(p) for p in np.round(P, 3).tolist()}); e = np.linalg.norm(P - np.roll(P, -1, axis=0), axis=1); kinds[(len(P), 'distinct corners %d' % u, 'longest edge %.1f m' % e.max() if e.max() > 0.05 else 'a point')] += 1
print('   the no-area ones:', dict(kinds))
dl = collections.Counter(int(lap(poly(ob, k).mean(0))[0]) for k in deg); print('   where (percent of the lap: count):', sorted(dl.items()))
# --- clusters of real new faces (sharing a corner)
key = lambda p: tuple(np.round(p * 1000).astype(np.int64)); par = {k: k for k in good}
def find(x):
    while par[x] != x: par[x] = par[par[x]]; x = par[x]
    return x
cor = collections.defaultdict(list)
for k in good:
    for p in poly(ob, k): cor[key(p)].append(k)
for l in cor.values():
    for x in l[1:]: par[find(x)] = find(l[0])
cl = collections.defaultdict(list)
for k in good: cl[find(k)].append(k)
print('REAL NEW FACES in %d patches:' % len(cl))
pa_set = {key(p) for p in oa['co']}; rows = []
for ks in cl.values():
    P = np.concatenate([poly(ob, k) for k in ks]); c = P.mean(0); pc, dist, dh = lap(c); size = np.ptp(P, axis=0); a = sum(ar[k] for k in ks)
    corners = {key(p) for p in P}; free = len([1 for t in corners if t not in pa_set])
    uvz = sum(k in set(K['uvz']) for k in ks); rows.append((pc, len(ks), a, float(np.linalg.norm(size)), dist, dh, len(corners) - free, len(corners), uvz, collections.Counter(mat(ob, k) for k in ks).most_common(1)[0][0], collections.Counter(int(ob['loop_total'][k]) for k in ks)))
for r in sorted(rows): print('   %4.1f%% of lap  %2d faces  %6.1f m2  span %5.1f m  %5.1f m from centre line  %+5.1f m against the road  corners on base vertices %2d/%2d  unmapped %2d  %s  %s' % (r[:9] + (r[9],) + (dict(r[10]),)))
pickle.dump(dict(good=good, deg=deg, moved=mk), open('blenddiff/final.pkl', 'wb'))
