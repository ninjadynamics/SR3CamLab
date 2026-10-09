"""Second look at the diff: which added faces are reshaped copies of removed ones, which are new; corner checks; where on the lap."""
import sys, pickle, collections
import numpy as np
import blend_diff as BD                                                 # (runs the first pass again; argv is the same)
A, B = BD.A, BD.B; oa = A['objects'][0]; ob = next(x for x in B['objects'] if x['name'] == oa['name'])
q = lambda P: [tuple(p) for p in np.round(np.asarray(P) * 1000).astype(np.int64).tolist()]
fa = BD.faces(oa); fb = BD.faces(ob); ca = collections.Counter(k for k, _ in fa); cb = collections.Counter(k for k, _ in fb)
added = [i for k, i in fb if k not in ca]; removed = [i for k, i in fa if k not in cb]
def poly(o, k): s, n = int(o['loop_start'][k]), int(o['loop_total'][k]); return o['co'][o['loop_vert'][s:s + n]]
def mat(o, k): return o['mats'][o['mat_index'][k]]
# the same polygon by loop content: Blender keeps face order when vertices are only moved, so compare index for index too
same_index = [k for k in removed if k < len(ob['loop_total']) and int(ob['loop_total'][k]) == int(oa['loop_total'][k]) and mat(oa, k) == mat(ob, k)]
moved = []
for k in same_index:
    Pa, Pb = poly(oa, k), poly(ob, k); d = np.linalg.norm(Pa - Pb, axis=1)
    if (d < 1e-3).sum() >= 1 or d.max() < 60: moved.append((k, float(d.max()), int((d > 1e-3).sum())))
mv = {k for k, _, _ in moved}
print('removed faces: %d ; of them still there under the same number with corners moved: %d (largest move %.2f m, median %.2f m)' % (len(removed), len(moved), max([m[1] for m in moved] or [0]), float(np.median([m[1] for m in moved] or [0]))))
truly_removed = [k for k in removed if k not in mv]; print('removed outright (deleted or replaced):', len(truly_removed), collections.Counter(int(oa['loop_total'][k]) for k in truly_removed))
new = [k for k in added if k not in mv]; print('added faces that are NOT a moved original: %d ; by corners %s' % (len(new), dict(collections.Counter(int(ob['loop_total'][k]) for k in new))))
print('moved originals by corners:', dict(collections.Counter(int(ob['loop_total'][k]) for k in mv)))
# were the deleted ones replaced by triangles covering the same corners? (a quad the user triangulated)
pa_set = set(q(oa['co'])); tri_of_removed = 0
rem_keys = [frozenset(q(poly(oa, k))) for k in truly_removed]
for k in new:
    kk = frozenset(q(poly(ob, k)))
    if any(kk < r for r in rem_keys): tri_of_removed += 1
print('new faces whose corners are all corners of ONE deleted face (= that face cut up):', tri_of_removed)
# corners
allv = oa['co']; cell = 2.0; grid = collections.defaultdict(list)
for i, p in enumerate(allv): grid[tuple(np.floor(p / cell).astype(int))].append(i)
def nearest(p):
    c = np.floor(p / cell).astype(int); best = 1e9
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                ii = grid.get((c[0] + dx, c[1] + dy, c[2] + dz))
                if ii: best = min(best, float(np.linalg.norm(allv[ii] - p, axis=1).min()))
    return best
newc = {}
for k in new + list(mv):
    for p in poly(ob, k):
        t = tuple(np.round(p * 1000).astype(np.int64))
        if t not in pa_set: newc[t] = p
d = np.array([nearest(p) for p in newc.values()]) if newc else np.zeros(0)
print('corner places that are not base vertices: %d ; nearest base vertex: within 1 cm %d, 1..10 cm %d, 10 cm..1 m %d, farther %d' % (len(d), (d < 0.01).sum(), ((d >= 0.01) & (d < 0.1)).sum(), ((d >= 0.1) & (d < 1)).sum(), (d >= 1).sum()))
# flatness of the quads, and the bigger polygons
def warp(P):
    n = np.cross(P[1] - P[0], P[3] - P[0]); l = np.linalg.norm(n); return abs(float((P[2] - P[0]) @ n)) / l if l > 1e-9 else 0.0
quads = [k for k in new if int(ob['loop_total'][k]) == 4]; w = np.array([warp(poly(ob, k)) for k in quads]) if quads else np.zeros(0)
print('new quads: %d ; twisted by more than 1 cm: %d, more than 10 cm: %d, largest %.2f m' % (len(quads), (w > 0.01).sum(), (w > 0.1).sum(), w.max() if len(w) else 0))
big = [k for k in new if int(ob['loop_total'][k]) > 4]
for k in big: P = poly(ob, k); print('   face with %d corners, material %s, at Blender %s' % (len(P), mat(ob, k), np.round(P.mean(0), 1).tolist()))
# where on the lap (Blender world = OBJ (x, -z, y))
C = np.loadtxt('F:/Jogos/SEGA Rally 3/SR3 track format/classic/courses/src/course1_mountain/src_course1_centreline.csv', delimiter=',', comments='#'); Cb = np.stack([C[:, 0], -C[:, 2], C[:, 1]], 1); n = len(Cb)
def lap(P): c = P.mean(0); dd = np.linalg.norm(Cb[:, :2] - c[:2], axis=1); j = int(dd.argmin()); return j, float(dd[j]), float(c[2] - Cb[j, 2])
info = [(lap(poly(ob, k)), k) for k in new]
h = collections.Counter((i[0] * 100 // n) // 5 * 5 for i, _ in info); print('new faces by 5%% of the lap:', sorted(h.items()))
dist = np.array([i[1] for i, _ in info]); print('their distance from the centre line: median %.1f m, largest %.1f m ; farther than 30 m: %d' % (np.median(dist), dist.max(), (dist > 30).sum()))
ar = np.array([0.5 * np.linalg.norm(sum(np.cross(poly(ob, k)[i], poly(ob, k)[(i + 1) % len(poly(ob, k))]) for i in range(len(poly(ob, k))))) for k in new]); print('new faces: total %.0f m2 ; larger than 50 m2: %d ; smaller than 0.01 m2: %d' % (ar.sum(), (ar > 50).sum(), (ar < 0.01).sum()))
uvz = [k for k in new if ob['uv'] is not None and abs(float(np.sum(ob['uv'][int(ob['loop_start'][k]):int(ob['loop_start'][k]) + int(ob['loop_total'][k]), 0] * np.roll(ob['uv'][int(ob['loop_start'][k]):int(ob['loop_start'][k]) + int(ob['loop_total'][k]), 1], -1) - np.roll(ob['uv'][int(ob['loop_start'][k]):int(ob['loop_start'][k]) + int(ob['loop_total'][k]), 0], -1) * ob['uv'][int(ob['loop_start'][k]):int(ob['loop_start'][k]) + int(ob['loop_total'][k]), 1]))) < 1e-9]
print('new faces with no texture mapping (all corners on one uv point or line): %d of %d' % (len(uvz), len(new)))
print('materials of the new faces:', collections.Counter(mat(ob, k) for k in new).most_common(12))
pickle.dump(dict(new=new, moved=moved, truly_removed=truly_removed, uvz=uvz, big=big), open('blenddiff/classes.pkl', 'wb'))
