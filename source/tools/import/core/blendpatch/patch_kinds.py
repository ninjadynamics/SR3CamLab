"""Patch 3's stage of the v11 scene, sorted into kinds (kb 26, section 12). An added face is
    RECUT      when a removed triangle of the same tile lies in its plane under its middle (the same surface cut into other triangles:
               the owner's v7 "revamp the whole map via script ... mid-sized triangles ... the shapes CANNOT CHANGE", welding);
    MOVED      when such a triangle of the same tile is near (< 1.5 m) but not in its plane (a surface reshaped);
    NEW        otherwise - geometry that was not there,
and every face gets a CLASS from its tile (label class; 'baked:' = a picture composed from tiles, rule W's facades; 'dark:' = a tile's dark copy).
    python patch_kinds.py <patch.json> [stage] [out=<kinds.json>]"""
import json, sys, os, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import retex

def tri_list(J, key):
    T = []; tiles = []
    for f in J.get(key, []):
        P = np.asarray(f['p'], float)
        for a in range(1, len(P) - 1): T.append((P[0], P[a], P[a + 1])); tiles.append(f.get('tile', '?'))
    return np.array(T, float).reshape(-1, 3, 3), tiles

def main():
    a = [x for x in sys.argv[1:] if '=' not in x]; kv = dict(x.split('=', 1) for x in sys.argv[1:] if '=' in x)
    J = json.load(open(a[0]))
    if 'stages' in J: J = J['stages'][int(a[1]) - 1 if len(a) > 1 else 0]
    lab = {k: v[0] for k, v in retex.labels().items()}; bake = {b['name']: b for b in J.get('bake', [])}
    def cls(t):
        t0 = t.split('|')[0]
        if t0 in lab: return lab[t0]
        if t0.endswith('_dk') and t0[:-3] in lab: return 'dark:' + lab[t0[:-3]]
        if t0 in bake: return 'baked'
        return 'other:' + t0[:24]
    R, rt = tri_list(J, 'remove'); rtile = np.array(rt, object)
    n = np.cross(R[:, 1] - R[:, 0], R[:, 2] - R[:, 0]); ln = np.linalg.norm(n, axis=1); n = n / np.maximum(ln, 1e-12)[:, None]; rc = R.mean(1)
    cell = 4.0; ck = np.floor(rc[:, [0, 2]] / cell).astype(np.int64); key = ck[:, 0] * 100003 + ck[:, 1]; o = np.argsort(key); ks = key[o]
    out = []; kinds = collections.Counter(); karea = collections.Counter(); cc = collections.defaultdict(float)
    for f in J.get('add', []):
        P = np.asarray(f['p'], float); c = P.mean(0); nf = np.zeros(3)
        for q in range(1, len(P) - 1): nf += np.cross(P[q] - P[0], P[q + 1] - P[0])
        ar = 0.5 * float(np.linalg.norm(nf)); nf = nf / max(2 * ar, 1e-12); t = f.get('tile', '?')
        g = np.floor(c[[0, 2]] / cell).astype(np.int64); cand = []
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                kk = (g[0] + dx) * 100003 + (g[1] + dz); lo, hi = np.searchsorted(ks, [kk, kk + 1]); cand.append(o[lo:hi])
        cand = np.concatenate(cand) if cand else np.zeros(0, np.int64)
        kind = 'NEW'
        if len(cand):
            same = cand[rtile[cand] == t]
            if len(same):
                d = np.abs(((c - R[same, 0]) * n[same]).sum(1)); close = np.linalg.norm(rc[same] - c, axis=1)
                if ((d < 0.03) & (np.abs((n[same] * nf).sum(1)) > 0.995) & (close < 12)).any(): kind = 'RECUT'
                elif (close < 1.5).any(): kind = 'MOVED'
        k2 = cls(t); up = 'upright' if abs(nf[1]) < 0.3 else ('sloping' if abs(nf[1]) < 0.8 else 'lying')
        kinds[(kind, k2, up)] += 1; karea[(kind, k2, up)] += ar; cc[kind] += ar
        out.append(dict(kind=kind, cls=k2, up=up, area=round(ar, 2), c=[round(float(x), 1) for x in c]))
    tot = sum(cc.values())
    print('added %.0f m2: %s' % (tot, ', '.join('%s %.0f m2 (%.0f %%)' % (k, v, 100 * v / tot) for k, v in sorted(cc.items(), key=lambda x: -x[1]))))
    for (kd, k2, up), v in sorted(karea.items(), key=lambda x: -x[1])[:40]: print('  %-6s %-22s %-8s %6d faces %8.0f m2' % (kd, k2, up, kinds[(kd, k2, up)], v))
    if kv.get('out'): json.dump(out, open(kv['out'], 'w'))

if __name__ == '__main__': main()
