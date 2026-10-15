"""Which texture lies under each collision attribute type: nearest visual face (hi OBJ) to each collision polygon centre.
load_coll is numpy-free (2026-10-15, kb 31: m2_gameplay uses it); the survey below (python m2_surface.py) still computes with numpy."""
import collections, glob, os, pickle, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'core')); import common   # tools/import/settings.json
class cKDTree:
    def __init__(self, C): self.C = C
    def query(self, p):
        import numpy as np
        d = np.abs(self.C - p).sum(1); i = int(d.argmin()); return float(np.linalg.norm(self.C[i] - p)), i
from PIL import Image, ImageDraw
def load_visual(p):
    import numpy as np
    V = []; C = []; M = []; cur = None
    for ln in open(p):
        if ln.startswith('v '): V.append([float(x) for x in ln.split()[1:4]])
        elif ln.startswith('usemtl'): cur = ln.split()[1]
        elif ln.startswith('f '):
            idx = [int(t.split('/')[0]) - 1 for t in ln.split()[1:]]; C.append(np.mean([V[i] for i in idx], 0)); M.append(cur)
    return np.array(C), M
def load_coll(p):
    """[(attribute word, [[x, y, z] per corner])] of a collision OBJ"""
    V = []; out = []; cur = None
    for ln in open(p):
        if ln.startswith('o attr_'): cur = int(ln[7:15], 16)
        elif ln.startswith('v '): V.append([float(x) for x in ln.split()[1:]])
        elif ln.startswith('f '): out.append((cur, [V[int(x) - 1] for x in ln.split()[1:]]))
    return out
if __name__ == '__main__':
    import numpy as np
    res = {}; sheet = Image.new('RGB', (4 * 3 * 132 + 60, 9 * 132 + 20), (30, 30, 30)); dr = ImageDraw.Draw(sheet)
    for ci, (n, nm) in enumerate(((1, 'mountain'), (2, 'desert'), (3, 'lakeside'), (4, 'forest'))):
        d = glob.glob(os.path.join(common.CLASSIC, 'courses', 'src', 'course%d_*' % n))[0]; C, M = load_visual(os.path.join(d, 'src_course%d_hi.obj' % n)); tree = cKDTree(C)
        by = collections.defaultdict(collections.Counter)
        for attr, Pp in load_coll(os.path.join(common.CLASSIC, 'obj', 'src_course%d_collision.obj' % n)):
            if attr & 0x800000: continue
            dist, i = tree.query(np.array(Pp).mean(0))
            if dist < 6: by[(attr >> 16) & 15][M[i]] += 1
        res[nm] = {t: c.most_common(4) for t, c in by.items()}
        for t in sorted(by):
            top = by[t].most_common(3); tot = sum(by[t].values()); print('%-9s type %d (%4d polys): %s' % (nm, t, tot, ', '.join('%s %d%%' % (m, 100 * k // tot) for m, k in top)))
            for j, (m, k) in enumerate(top):
                p = os.path.join(d, 'textures', m + '.png')
                if os.path.exists(p): sheet.paste(Image.open(p).convert('RGB').resize((128, 128)), (60 + (ci * 3 + j) * 132, 20 + [0, 1, 2, 3, 4, 6, 8, 9].index(t) * 132 + 2))
        dr.text((60 + ci * 3 * 132, 4), nm, fill=(255, 255, 255))
    for r, t in enumerate([0, 1, 2, 3, 4, 6, 8, 9]): dr.text((4, 20 + r * 132 + 60), 'type %d' % t, fill=(255, 255, 255))
    sheet.save(os.path.join(common.CLASSIC, 'courses', 'src', 'surface_types_contact.png')); pickle.dump(res, open(os.path.join(common.TMP, 'm2', 'surface_tiles.pkl'), 'wb'))
