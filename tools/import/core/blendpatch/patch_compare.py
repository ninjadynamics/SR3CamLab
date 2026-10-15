"""Two course patch files side by side, tile by tile: how close is a generated patch (genpatch1995.py) to a reference one?
    uv run --with "shapely>=2.1" --with numpy python patch_compare.py <reference.json> <other.json>
Per group of tiles (the composed facade pictures as one group, every other tile by its name without the palette code): faces and
area added on both sides, and for lying faces the ground they cover in plan: common, only in the reference, only in the other,
with the middles of the largest differences (decoded-scene x, z). Facades are paired by their middle (1.5 m) and width (1 m)."""
import sys, json, collections
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

def group(t): return 'facade pictures' if t.startswith('facade_') else t.split('_c')[0] + ('_dk' if t.endswith('_dk') else '')
area = lambda P: 0.5 * float(np.linalg.norm(np.cross(np.array(P[1]) - P[0], np.array(P[2]) - P[0])))
def main(a, b):
    A, B = json.load(open(a)), json.load(open(b)); G = collections.defaultdict(lambda: [[], []])
    for i, J in enumerate((A, B)):
        for f in J['add']: G[group(f['tile'])][i].append(np.array(f['p'], float))
    print('triangles to remove: %d / %d (not comparable when one file lists a build\'s pieces and the other whole polygons) ; pictures: %d / %d ; settings: %s / %s' % (len(A.get('remove', [])), len(B.get('remove', [])), len(A.get('bake', [])), len(B.get('bake', [])), A.get('settings'), B.get('settings')))
    for g, (x, y) in sorted(G.items(), key=lambda kv: -sum(area(p) for p in kv[1][0] + kv[1][1])):
        line = '%-34s faces %5d / %5d   area %8.0f / %8.0f m2' % (g[-34:], len(x), len(y), sum(map(area, x)), sum(map(area, y)))
        lying = lambda L: [p for p in L if abs(np.cross(p[1] - p[0], p[2] - p[0])[1]) > 0.5 * 2 * area(p) > 0]
        if g != 'facade pictures' and (lying(x) or lying(y)):
            ux, uy = (unary_union([Polygon(p[:, [0, 2]]).buffer(0) for p in lying(L)]) if lying(L) else Polygon() for L in (x, y)); d1, d2 = ux.difference(uy), uy.difference(ux)
            big = lambda d: [(round(q.area), round(q.centroid.x), round(q.centroid.y)) for q in sorted([q for q in (d.geoms if hasattr(d, 'geoms') else [d]) if q.area > 5], key=lambda q: -q.area)[:5]]
            line += '   in plan: common %.0f, only reference %.0f %s, only other %.0f %s' % (ux.intersection(uy).area, d1.area, big(d1), d2.area, big(d2))
        print(line)
    def fac(J):
        F = collections.defaultdict(list)
        for f in J['add']:
            if f['tile'].startswith('facade_'): F[f['tile']].append(np.array(f['p'], float))
        return [dict(c=np.concatenate(T).mean(0), w=float(np.hypot(np.ptp(np.concatenate(T)[:, 0]), np.ptp(np.concatenate(T)[:, 2]))), lo=float(np.concatenate(T)[:, 1].min()), n=len(T)) for T in F.values()]
    FA, FB = fac(A), fac(B)
    if FA and FB:
        hit = [(f, min(FB, key=lambda q: np.linalg.norm(q['c'] - f['c']))) for f in FA]; hit = [(f, q) for f, q in hit if np.linalg.norm(q['c'] - f['c']) < 1.5 and abs(q['w'] - f['w']) < 1.0]
        print('facades: %d / %d ; the same facade on both sides (middle within 1.5 m, width within 1 m): %d ; their feet differ by at most %.2f m ; triangles a facade: %s / %s' % (len(FA), len(FB), len(hit), max([abs(f['lo'] - q['lo']) for f, q in hit] or [0]), dict(collections.Counter(f['n'] for f in FA)), dict(collections.Counter(f['n'] for f in FB))))
if __name__ == '__main__': main(*sys.argv[1:3])
