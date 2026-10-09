"""Contact sheets for the retexture work: (1) the classic course-1 tiles, (2) candidate SR3 diffuse textures.
    python retex_survey.py   -> ../retex/classic_tiles_contact.png, ../retex/sr3_candidates_<Track>.png, ../retex/sr3_tex/<id>.png"""
import os, sys, struct, collections, json
import numpy as np
from PIL import Image, ImageDraw
from common import *
import sbfw, preview_obj, classic_tex
RT = os.path.join(WORK, 'retex'); os.makedirs(os.path.join(RT, 'sr3_tex'), exist_ok=True)

def classic_contact():
    mats = classic_tex.materials(); names = sorted(n for n, m in mats.items() if m); cols = 13; cell = 100
    W = Image.new('RGB', (cols * cell, ((len(names) + cols - 1) // cols) * (cell + 12)), (30, 30, 60)); dr = ImageDraw.Draw(W)
    for i, n in enumerate(names):
        im = Image.open(os.path.join(classic_tex.OUT, 'textures', n + '.png')).convert('RGBA'); bg = Image.new('RGBA', im.size, (200, 0, 200, 255)); bg.alpha_composite(im)
        x, y = (i % cols) * cell, (i // cols) * (cell + 12); W.paste(bg.convert('RGB').resize((cell - 2, cell - 2)), (x, y)); dr.text((x + 1, y + cell - 2), '%d' % i, fill=(255, 255, 0))
    W.save(os.path.join(RT, 'classic_tiles_contact.png')); json.dump(names, open(os.path.join(RT, 'classic_tiles_index.json'), 'w'))
    return names

def sr3_candidates(track, top=48):
    """diffuse textures (material +0x1BC) ranked by the number of scenery vertices that use the material"""
    f = sbfw.read_sbf(track_files(os.path.join(TRACKS, track))['master_gfx_xdata']); by = f.byid(); use = collections.Counter()
    for c in f.kinds(1):
        h = struct.unpack_from('<18I', c.data, 0)
        if h[11] != 0x48: continue
        for k in range(h[8]):
            g = struct.unpack_from('<5I', c.data, 0x48 + 20 * k); m = by.get(g[4])
            if m is not None and len(m.data) > 0x1c0 and 0x1bc in m.ref:
                t = m.u32(0x1bc)
                if t in by and by[t].kind == 4: use[t] += g[1]
    ids = [t for t, n in use.most_common(top)]; cols = 8; cell = 160
    W = Image.new('RGB', (cols * cell, ((len(ids) + cols - 1) // cols) * (cell + 12)), (30, 30, 60)); dr = ImageDraw.Draw(W)
    for i, t in enumerate(ids):
        p = os.path.join(RT, 'sr3_tex', '%s_%08x.png' % (track, t)); preview_obj.texture_png(by[t], p)
        im = Image.open(p).convert('RGB').resize((cell - 2, cell - 2)); x, y = (i % cols) * cell, (i // cols) * (cell + 12)
        W.paste(im, (x, y)); dr.text((x + 1, y + cell - 2), '%d %08x' % (i, t), fill=(255, 255, 0))
    W.save(os.path.join(RT, 'sr3_candidates_%s.png' % track)); json.dump(['%08x' % t for t in ids], open(os.path.join(RT, 'sr3_candidates_%s.json' % track), 'w'))
    print(track, len(ids), 'candidates')

if __name__ == '__main__':
    print(len(classic_contact()), 'classic tiles')
    for t in sys.argv[1:] or ['Alpine4']: sr3_candidates(t)
