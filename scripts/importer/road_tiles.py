"""Which classic tiles lie on the road strip (the faces build_classic drops)?  -> ../retex/road_tiles_contact.png
    python road_tiles.py"""
import os, sys, json, collections
import numpy as np
from PIL import Image, ImageDraw
from common import *
import build_classic as BC, classic_tex, retex

def split(rd):
    """(kept, dropped) faces exactly as load_visual decides"""
    keep = BC.load_visual(rd); ids = {id(f) for f in keep}
    return keep

def dropped_faces(rd):
    ox, oz = rd['ox'], rd['oz']; V = []; VT = []; faces = []; mat = None; sec = None
    for ln in open(BC.HI):
        if ln.startswith('v '): x, y, z = map(float, ln.split()[1:4]); V.append((x + ox, y, -z + oz))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('o '): sec = ln.split()[1]
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]
            faces.append((mat, sec, [V[a] for a, b in ix][::-1], [VT[b] for a, b in ix][::-1]))
    keep = BC.load_visual(rd); kk = collections.Counter((f[0], tuple(f[2][0])) for f in keep); out = []
    for f in faces:
        k = (f[0], tuple(f[2][0]))
        if kk[k] > 0: kk[k] -= 1
        else: out.append(f)
    return out

def main():
    rd = BC.import_road(); dr = dropped_faces(rd); cnt = collections.Counter(f[0] for f in dr)
    area = collections.Counter()
    for f in dr:
        P = np.array(f[2]); a = 0.5 * np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0]))
        if len(P) == 4: a += 0.5 * np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[0]))
        area[f[0]] += a
    pages = classic_tex.load_pages(); tiles = classic_tex.materials(); lab = retex.labels()
    names = [n for n, _ in area.most_common()]; cell = 150; cols = 8; rows = (len(names) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * (cell + 26)), (40, 40, 40)); dr_ = ImageDraw.Draw(sheet)
    idx = json.load(open(os.path.join(retex.RT, 'classic_tiles_index.json')))
    for i, n in enumerate(names):
        x, y = (i % cols) * cell, (i // cols) * (cell + 26)
        if tiles.get(n):
            t = classic_tex.tile(pages, tiles[n]); im = Image.fromarray(classic_tex.tile_rgb(t, tiles[n])).resize((cell - 6, cell - 6), Image.NEAREST); sheet.paste(im, (x + 3, y + 3))
        dr_.text((x + 3, y + cell - 2), '%s %s' % (idx.index(n) if n in idx else '?', lab.get(n, ('?',))[0]), fill=(255, 255, 0))
        dr_.text((x + 3, y + cell + 10), '%d f %.0f m2' % (cnt[n], area[n]), fill=(200, 200, 200))
        print('%4s %-40s %-12s faces %5d area %7.0f m2' % (idx.index(n) if n in idx else '?', n, lab.get(n, ('?',))[0], cnt[n], area[n]))
    p = os.path.join(retex.RT, 'road_tiles_contact.png'); sheet.save(p); print(p)

if __name__ == '__main__':
    main()
