"""What a course patch does, place by place: its added and removed faces grouped into places (faces within `link` metres of each other),
each place with its label classes, area, height, how upright it is, and what it replaces. Written 2026-10-15 to sort Mountain's patch 3
(the generated stage and the v11 scene's stage) into kinds for the generalisation (kb 26).

    python patch_places.py <patch.json> [stage number, 1-based, for a staged file] [link=6] [top=60] [out=<places.json>]
Coordinates are the patch's own (the decoded scene's: x, y up, z = -gameZ)."""
import json, sys, os, math, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import retex

def faces_of(J, key):
    out = []
    for f in J.get(key, []):
        P = np.asarray(f['p'], float)
        if len(P) < 3: continue
        n = np.zeros(3)
        for a in range(1, len(P) - 1): n += np.cross(P[a] - P[0], P[a + 1] - P[0])
        ar = 0.5 * float(np.linalg.norm(n)); up = abs(n[1]) / max(2 * ar, 1e-12)
        out.append(dict(tile=f.get('tile', '?'), P=P, area=ar, up=up, c=P.mean(0)))
    return out

def places(F, link):
    """union of faces whose corners come within `link` of each other (grid hashing on corners)"""
    par = list(range(len(F)))
    def find(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    cell = {}
    for i, f in enumerate(F):
        for p in f['P']:
            k = (int(p[0] // link), int(p[1] // link), int(p[2] // link))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for j in cell.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                            if np.min(np.linalg.norm(F[j]['P'][:, None, :] - p[None, None, :], axis=2)) < link: par[find(i)] = find(j)
            cell.setdefault(k, []).append(i)
    G = collections.defaultdict(list)
    for i in range(len(F)): G[find(i)].append(i)
    return list(G.values())

def main():
    a = [x for x in sys.argv[1:] if '=' not in x]; kv = dict(x.split('=', 1) for x in sys.argv[1:] if '=' in x)
    J = json.load(open(a[0])); link = float(kv.get('link', 6)); top = int(kv.get('top', 60))
    if 'stages' in J: J = J['stages'][int(a[1]) - 1 if len(a) > 1 else 0]
    lab = {k: v[0] for k, v in retex.labels().items()}
    bake = {b['name']: b for b in J.get('bake', [])}
    def cls(t):
        t0 = t.split('|')[0]
        if t0 in lab: return lab[t0]
        if t0 in bake: return 'baked:' + ','.join(sorted({lab.get(s.get('tile', s) if isinstance(s, dict) else s, '?') for s in bake[t0].get('sources', [])}))[:40]
        return 'unknown'
    A = faces_of(J, 'add'); R = faces_of(J, 'remove')
    print('%s: %d faces added (%.0f m2), %d triangles removed (%.0f m2)' % (os.path.basename(a[0]), len(A), sum(f['area'] for f in A), len(R), sum(f['area'] for f in R)))
    for kind, F in (('ADDED', A), ('REMOVED', R)):
        cc = collections.Counter(); ca = collections.Counter()
        for f in F: c = cls(f['tile']); cc[c] += 1; ca[c] += f['area']
        print('%s by class: %s' % (kind, ', '.join('%s %d (%.0f m2)' % (c, cc[c], ca[c]) for c, _ in ca.most_common(14))))
    G = places(A, link); out = []
    Rc = np.array([f['c'] for f in R]) if R else np.zeros((0, 3))
    for g in G:
        fs = [A[i] for i in g]; C = np.array([f['c'] for f in fs]); P = np.concatenate([f['P'] for f in fs]); ar = sum(f['area'] for f in fs)
        cc = collections.Counter();
        for f in fs: cc[cls(f['tile'])] += f['area']
        upright = sum(f['area'] for f in fs if f['up'] < 0.3) / max(ar, 1e-9)
        lo, hi = P.min(0), P.max(0)
        rem = int(((Rc >= lo - 1) & (Rc <= hi + 1)).all(1).sum()) if len(Rc) else 0
        out.append(dict(n=len(fs), area=round(ar, 1), centre=[round(float(x), 1) for x in C.mean(0)], lo=[round(float(x), 1) for x in lo], hi=[round(float(x), 1) for x in hi],
                        upright=round(upright, 2), classes={k: round(v) for k, v in cc.most_common(4)}, removed_inside=rem))
    out.sort(key=lambda r: -r['area'])
    print('%d places (faces within %.0f m); the %d largest:' % (len(out), link, min(top, len(out))))
    for r in out[:top]:
        print('  %5.0f m2 %4d faces  at %-22s  span %-18s up %.0f %% upright  removed inside %5d  %s' % (r['area'], r['n'], tuple(r['centre']), tuple(round(h - l) for h, l in zip(r['hi'], r['lo'])), r['upright'] * 100 * 0 + r['upright'] * 100, r['removed_inside'], r['classes']))
    if kv.get('out'): json.dump(out, open(kv['out'], 'w'), indent=0)

if __name__ == '__main__': main()
