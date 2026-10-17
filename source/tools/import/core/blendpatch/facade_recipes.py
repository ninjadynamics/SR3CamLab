"""The facade pictures of an edited scene as RECIPES for the patch file (facadebake.py composes them again at import time).
    python facade_recipes.py <wall planes .json> <facade design .json> <texmap.json of the build the scene was decoded from> <out.json>
wall planes: the faces each facade replaced, in the plane of their wall (scratch v10b_in.json); design: where each facade stands and how
big its picture is (scratch v11_design.json). Out: [{"name": "facade_NNN", "size", "sources": [{"tile", "p", "uv"}]}], bigger triangles first."""
import sys, json, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_build import tiles

def main(planes, design, texmap, out):
    D = json.load(open(planes)); F = json.load(open(design))['facades']; tile = tiles(texmap); res = []; r5 = lambda a: [[round(float(x), 5) for x in q] for q in a]
    for fi, f in enumerate(F):
        A = np.array(f['A']); d = np.array(f['d']); W = f['W']; y0, y1 = f['y0'], f['y1']; src = []
        for gi in f['atoms']:
            G = D['groups'][gi]; og, ug = np.array(G['o']), np.array(G['u'])
            for t in G['faces']:
                P = np.array([[((np.array([og[0] + ug[0] * p[0], og[2] + ug[2] * p[0]]) - A) @ d) / W, (og[1] + p[1] - y0) / (y1 - y0)] for p in t['p']])
                ar = abs(float(np.cross(P[1] - P[0], P[2] - P[0]))) * W * (y1 - y0)                # in square metres, as the scene's own bake sorted them
                src.append((ar, dict(tile=tile[t['m'].split('_a')[0].split('.')[0]], p=r5(P), uv=r5(t['uv']))))
        src.sort(key=lambda x: -x[0]); res.append(dict(name='facade_%03d' % fi, size=f['size'], sources=[s for a, s in src]))
    json.dump(res, open(out, 'w')); print('facade recipes: %d pictures, %d source triangles, %.1f megapixels -> %s' % (len(res), sum(len(r['sources']) for r in res), sum(r['size'][0] * r['size'][1] for r in res) / 1e6, out))

if __name__ == '__main__': main(*sys.argv[1:])
