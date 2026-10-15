"""A scene patch (scene_diff) -> the same patch without the trees that only MOVED, plus the list of their corner shifts for the importer's
board_moves setting (the original polygons are moved whole there).   python tree_moves.py <patch in> <patch out> <board_moves out>
A tree = removed cut-out triangles joined by shared corners. It counts as moved when ONE shift (under 6 m) puts every one of its triangles
exactly on an added triangle of the same tile."""
import sys, json, collections
import numpy as np
J = json.load(open(sys.argv[1])); rem = J['remove']; add = J['add']; cut = lambda t: t.endswith('_t')
R = [i for i, r in enumerate(rem) if cut(r['tile'])]; A = [i for i, a in enumerate(add) if cut(a['tile'])]; kc = lambda p: tuple(np.round(p, 2)); par = {}
def find(x):
    while par.setdefault(x, x) != x: par[x] = par[par[x]]; x = par[x]
    return x
for i in R:
    ks = [kc(p) for p in rem[i]['p']]
    for k in ks[1:]: par[find(k)] = find(ks[0])
trees = collections.defaultdict(list)
for i in R: trees[find(kc(rem[i]['p'][0]))].append(i)
akey = lambda tile, P: (tile, frozenset(kc(p) for p in P)); AI = collections.defaultdict(list); acorn = collections.defaultdict(list)
for j in A:
    AI[akey(add[j]['tile'], add[j]['p'])].append(j)
    for p in add[j]['p']: acorn[add[j]['tile']].append(p)
AP = {t: np.array(v) for t, v in acorn.items()}; cm = {}; uR = set(); uA = set(); ok = bad = mixed = 0; shifts = []
solidc = {kc(p) for r in rem if not cut(r['tile']) for p in r['p']}             # corners of removed faces that are no cut-outs
for root, tris in trees.items():
    if any(kc(p) in solidc for i in tris for p in rem[i]['p']): mixed += 1; continue      # a tree that shares corners with solid faces the patch also takes out (a composed trunk piece): moving only its boards left the solid piece behind, lying in a board (13 pairs, 2026-10-13)
    i0 = tris[0]; p0 = np.array(rem[i0]['p'][0]); pts = AP.get(rem[i0]['tile']); best = None
    if pts is None: bad += 1; continue
    cand = pts[np.linalg.norm(pts - p0, axis=1) < 6.0] - p0; cand = np.unique(np.round(cand, 3), axis=0)
    for t in cand:
        if all(any(j not in uA for j in AI.get(akey(rem[i]['tile'], np.array(rem[i]['p']) + t), ())) for i in tris):
            if best is None or np.linalg.norm(t) < np.linalg.norm(best): best = t
    if best is None: bad += 1; continue
    ok += 1; shifts.append(float(np.linalg.norm(best))); uR.update(tris)
    for i in tris:
        js = [j for j in AI[akey(rem[i]['tile'], np.array(rem[i]['p']) + best)] if j not in uA]
        if js: uA.add(js[0])
        for p in rem[i]['p']: cm[tuple(np.round(p, 3))] = [float(x) for x in best]
J['remove'] = [r for i, r in enumerate(rem) if i not in uR]; J['add'] = [a for i, a in enumerate(add) if i not in uA]; J['move'] = []
json.dump(J, open(sys.argv[2], 'w')); json.dump([list(k) + v for k, v in cm.items()], open(sys.argv[3], 'w'))
print('tree_moves: %d tree groups among the removed boards ; %d moved whole (shift median %.2f m, largest %.2f) ; %d not matched and %d joined to solid pieces (those stay cut out and added) ; patch now: %d to remove, %d to add' % (len(trees), ok, np.median(shifts) if shifts else 0, max(shifts) if shifts else 0, bad, mixed, len(J['remove']), len(J['add'])))
