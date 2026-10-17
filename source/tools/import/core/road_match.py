"""Which SR3 road layer pair looks most like the 1995 road?   python road_match.py
Compares the mean colour of the coloured classic road tiles with the TOP layer texture of every (base, top) pair used by
the six arcade tracks (terrain names from ../tmp/surfaces.json; note its keys top/base are swapped: surf[0] is the base).
Writes ../retex/road_match.png (classic tiles first, then the candidates in order of colour distance)."""
import os, json, struct
import numpy as np
from PIL import Image, ImageDraw
from common import *
import sbfw, sr3_art, classic_tex, retex
ARC = ('Alpine4', 'Canyon4', 'Desert4', 'Lakeside4', 'Stadium4', 'Tropical4')

def candidates():
    S = json.load(open(os.path.join(TMP, 'surfaces.json')))['tracks']; out = {}
    for t in ARC:
        f = None
        for r in S[t]['pairs']:
            top, base = r['base_id'], r['top_id']; nm = '/'.join(r['base'])
            if (base, top) in out or r['cells'] < 300: continue
            if f is None: f = sbfw.read_sbf(track_files(os.path.join(TRACKS, t))['master_gfx_xdata']).byid()
            c = f.get(int(top, 16))
            if c is None or c.kind != 4: continue
            p = os.path.join(WORK, 'retex', 'art', t, top + '.png'); os.makedirs(os.path.dirname(p), exist_ok=True)
            if not os.path.exists(p): sr3_art.full_png(c, p)
            im = np.array(Image.open(p).convert('RGB')); out[(base, top)] = dict(track=t, name=nm, base_name='/'.join(r['top']), cells=r['cells'], mean=im.reshape(-1, 3).mean(0), std=float(im.mean(2).std()), png=p)
    return out

def main():
    idx = json.load(open(os.path.join(retex.RT, 'classic_tiles_index.json'))); pages = classic_tex.load_pages(); tiles = classic_tex.materials()
    cl = {}
    for i in (21, 8, 107, 42):
        m = tiles[idx[i]]; rgb = classic_tex.tile_rgb(classic_tex.tile(pages, m), m); cl[i] = (rgb, rgb.reshape(-1, 3).mean(0))
        print('classic tile %3d %-38s mean colour %s contrast %.1f' % (i, idx[i], cl[i][1].round().tolist(), rgb.mean(2).std()))
    C = candidates(); ref = cl[21][1]; rows = sorted(C.items(), key=lambda kv: float(np.linalg.norm(kv[1]['mean'] - ref)))
    for (b, t), v in rows: print('%-10s base %s top %s %-34s cells %6d mean %s distance to classic asphalt %.0f, to classic dirt %.0f' % (v['track'], b, t, v['name'], v['cells'], v['mean'].round().tolist(), np.linalg.norm(v['mean'] - ref), np.linalg.norm(v['mean'] - cl[42][1])))
    cell = 200; cols = 8; items = [('classic %d' % i, Image.fromarray(cl[i][0])) for i in cl] + [('%s %s %s' % (v['track'][:4], t, v['name'].replace('Terrain_', '')[:14]), Image.open(v['png']).convert('RGB')) for (b, t), v in rows]
    W = Image.new('RGB', (cols * cell, ((len(items) + cols - 1) // cols) * (cell + 14)), (30, 30, 30)); dr = ImageDraw.Draw(W)
    for k, (nm, im) in enumerate(items):
        x, y = (k % cols) * cell, (k // cols) * (cell + 14); W.paste(im.resize((cell - 2, cell - 2)), (x, y)); dr.text((x + 2, y + cell - 1), nm, fill=(255, 255, 0))
    W.save(os.path.join(retex.RT, 'road_match.png')); print(os.path.join(retex.RT, 'road_match.png'))

if __name__ == '__main__':
    main()
