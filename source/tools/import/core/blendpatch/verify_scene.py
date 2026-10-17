"""IS THE BUILD THE SCENE? A build decoded back (preview_obj.py) against the Blender scene it was meant to reproduce, face by face.
    python verify_scene.py <decoded.obj> <its texmap.json> <scene dump .pkl> <texmap.json of the build the scene was decoded from>
A face = its tile, its three corners (1 mm; 2 mm for a corner that rounds the other way), the side it faces and its texture coordinates
(whole repeats aside). A scene face whose tile repeats more than twice arrives CUT by the build (build_classic.uv_split: the game's
texture coordinates hold two repeats): it counts as the same when build faces of its tile lie inside it, cover its whole area and carry
its own mapping. Anything else is listed: only in the scene / only in the build."""
import sys, os, collections, itertools
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_build import load_pkl, tiles
import scene_diff as SD

area = lambda P: 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
def bary(T, q):
    a, b, c = T; n = np.cross(b - a, c - a); d = float(n @ n)
    l1 = float(np.cross(q - a, c - a) @ n) / d; l2 = float(np.cross(b - a, q - a) @ n) / d; off = abs(float((q - a) @ n)) / np.sqrt(d); return np.array([1 - l1 - l2, l1, l2]), off

def main(obj, tm_a, pkl, tm_b):
    ta = tiles(tm_a); tb = tiles(tm_b); A = SD.from_obj(obj, ta); B, ng = SD.from_dump(load_pkl(pkl), tb)
    A = [(t, p.astype(float), u.astype(float)) for t, p, u in A]; B = [(t, p.astype(float), u.astype(float)) for t, p, u in B]
    key = lambda f: (f[0], tuple(sorted(tuple(np.round(p, 3) + 0.0) for p in f[1])))
    ka = collections.defaultdict(list); kb = collections.defaultdict(list)
    for i, f in enumerate(A): ka[key(f)].append(i)
    for j, f in enumerate(B): kb[key(f)].append(j)
    pairs = []; la = []; lb = []
    for k in set(ka) | set(kb):
        x, y = list(ka.get(k, [])), list(kb.get(k, []))
        if len(x) > 1 or len(y) > 1:                                    # back-to-back faces on the same corners (tree blades): each with the one facing its way
            nrm = lambda f: np.cross(f[1][1] - f[1][0], f[1][2] - f[1][0]); y2 = []
            for i in x:
                j = next((j for j in y if j not in y2 and float(nrm(A[i]) @ nrm(B[j])) > 0), None)
                if j is not None: y2.append(j)
            y = y2 + [j for j in y if j not in y2]
            x = [i for i in x if any(float(nrm(A[i]) @ nrm(B[j])) > 0 for j in y2)] + [i for i in x if not any(float(nrm(A[i]) @ nrm(B[j])) > 0 for j in y2)]
        n = min(len(x), len(y)); pairs += list(zip(x[:n], y[:n])); la += x[n:]; lb += y[n:]
    grid = collections.defaultdict(list)                                # corners that round to the other side of a millimetre
    for j in lb: grid[(B[j][0], tuple(np.floor(B[j][1].mean(0) / 2.0).astype(int)))].append(j)
    used = set(); la2 = []
    for i in la:
        f = A[i]; c = np.floor(f[1].mean(0) / 2.0).astype(int); hit = None
        for d in itertools.product((-1, 0, 1), repeat=3):
            for j in grid.get((f[0], tuple(c + d)), ()):
                g = B[j]
                if j not in used and all(np.linalg.norm(g[1] - p, axis=1).min() < 0.002 for p in f[1]) and all(np.linalg.norm(f[1] - p, axis=1).min() < 0.002 for p in g[1]): hit = j; break
            if hit is not None: break
        if hit is None: la2.append(i)
        else: used.add(hit); pairs.append((i, hit))
    la = la2; lb = [j for j in lb if j not in used]
    # the matched faces: same side, same mapping
    flip = uvbad = 0; worst = 0.0; FL = []; UB = []
    for i, j in pairs:
        fa, fb = A[i], B[j]; perm = [int(np.argmin(np.linalg.norm(fb[1] - p, axis=1))) for p in fa[1]]
        if len(set(perm)) < 3: continue
        na = np.cross(fa[1][1] - fa[1][0], fa[1][2] - fa[1][0]); nb = np.cross(fb[1][1] - fb[1][0], fb[1][2] - fb[1][0]); flip += float(na @ nb) < 0
        d = fa[2] - fb[2][perm]; d = d - np.round(d[0]); e = float(np.abs(d).max()); worst = max(worst, e if e < 0.5 else 0.0); uvbad += e > 0.004
        if float(na @ nb) < 0: FL.append((fa[0][-22:], np.round(fa[1].mean(0), 1).tolist()))
        if e > 0.004: UB.append((fa[0][-22:], round(e, 4), np.round(fa[1].mean(0), 1).tolist(), np.round(fa[2], 3).tolist(), np.round(fb[2][perm], 3).tolist()))
    # scene faces the build shows cut into pieces
    ga = collections.defaultdict(list)
    for i in la: ga[A[i][0]].append(i)
    cut = 0; pieces = 0; uvpiece = 0; usedA = set(); still = []
    for j in lb:
        T = B[j]; ar = area(T[1]); mine = []; lo = T[1].min(0) - 0.003; hi = T[1].max(0) + 0.003
        if ar < 1e-9: still.append(j); continue
        for i in ga.get(T[0], ()):
            if i in usedA: continue
            P = A[i][1]
            if (P < lo).any() or (P > hi).any(): continue
            bs = [bary(T[1], q) for q in P]
            if all(off < 0.003 and (b > -0.002).all() for b, off in bs) and (bary(T[1], P.mean(0))[0] > 1e-7).all(): mine.append((i, [b for b, off in bs]))      # (its middle strictly inside: a sliver of the neighbouring face is not taken)
        if not mine or abs(sum(area(A[i][1]) for i, _ in mine) - ar) > 1e-3 + 2e-3 * ar: still.append(j); continue
        cut += 1; pieces += len(mine)
        for i, bs in mine:
            usedA.add(i); d = A[i][2] - np.array([b @ T[2] for b in bs]); d = d - np.round(d[0]); uvpiece += float(np.abs(d).max()) > 0.004
    la = [i for i in la if i not in usedA]; lb = still
    print('build %d faces ; scene %d faces' % (len(A), len(B)))
    print('the very same face on both sides: %d ; of them facing the other way: %d ; with another mapping: %d (largest difference among the rest %.5f)' % (len(pairs), flip, uvbad, worst))
    print('scene faces the build shows cut into pieces (tile repeats more than twice): %d, as %d pieces ; pieces with another mapping: %d' % (cut, pieces, uvpiece))
    print('   facing the other way, by tile:', dict(collections.Counter(f[0] for f in FL).most_common(8)), FL[:4])
    print('   another mapping, by tile:', dict(collections.Counter(f[0] for f in UB).most_common(8)), UB[:4])
    print('ONLY IN THE SCENE: %d %s' % (len(lb), dict(collections.Counter(B[j][0][-26:] for j in lb).most_common(8))))
    print('ONLY IN THE BUILD: %d %s' % (len(la), dict(collections.Counter(A[i][0][-26:] for i in la).most_common(8))))
    for nm, L, S in (('scene', lb, B), ('build', la, A)):
        for k in L[:12]: print('   only in the %s: %s area %.4f m2 at %s' % (nm, S[k][0][-30:], area(S[k][1]), np.round(S[k][1].mean(0), 2).tolist()))
    return A, B, la, lb

if __name__ == '__main__': main(*sys.argv[1:])
