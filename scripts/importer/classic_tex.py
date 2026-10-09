"""SEGA Rally Championship course 1 (Mountain): OBJ + MTL (classic_export.py) and the texture tiles from the main data ROM.
    python classic_tex.py     -> ../classic_tex/course1/{src_course1_hi.obj, .mtl, textures/*.png, sheets/*.png}
Tiles are luminance (4-bit texel x 17) unless ../tmp/m2/palram.bin etc. exist (see 12_classic_textures.md).
Translucent materials (name ends _t): texel 15 is a hole -> alpha 0."""
import os, re, sys, json, numpy as np
from PIL import Image
import m2tex, classic_export
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = classic_export.OUT
PAGEFILE = os.path.join(OUT, 'pages.json')
CANDIDATES = list(range(0x200000, 0x800000, 0x80000))

BLOCK = None
def all_pages():
    d = m2tex.main_data(); return {o: m2tex.decode_words(d[o:o + 0x80000].view('<u2')) for o in CANDIDATES}

def fit_pages(mats, pages):
    """for every (sheet, half) used: the ROM page on which the tile rectangles line up best.
    score = mean over rectangles of (texel step across the rectangle's left/top border) - (step just inside)"""
    rects = {}
    for name, m in mats.items():
        if m: rects.setdefault((m['sheet'], m['x'] // 1024), set()).add((m['x'] % 1024, m['y'], m['w'], m['h']))
    res = {}
    for key, rs in sorted(rects.items()):
        sc = []
        for off, img in pages.items():
            im = img.astype(int); tot = 0.0; n = 0
            for x, y, w, h in rs:
                if x + w > 1024 or y + h > 1024: continue
                if x > 0: tot += np.abs(im[y:y + h, x] - im[y:y + h, x - 1]).mean() - np.abs(im[y:y + h, x + 1] - im[y:y + h, x]).mean(); n += 1
                if y > 0: tot += np.abs(im[y, x:x + w] - im[y - 1, x:x + w]).mean() - np.abs(im[y + 1, x:x + w] - im[y, x:x + w]).mean(); n += 1
                tot += 1.0 * (im[y:y + h, x:x + w].std() > 0.5) - 1.0 * (im[y:y + h, x:x + w].max() == 0); n += 1
            sc.append((tot / max(n, 1), off))
        sc.sort(reverse=True); res[key] = sc
    return rects, res

def load_pages(choice=None):
    pg = all_pages()
    if choice is None: choice = {tuple(int(v) for v in k.split(',')): o for k, o in json.load(open(PAGEFILE)).items()}
    return {k: pg[o] for k, o in choice.items()}

def tile(pages, m):
    pg = pages.get((m['sheet'], m['x'] // 1024))
    if pg is None: return None
    nx = pages.get((m['sheet'], m['x'] // 1024 + 1))
    if nx is not None and m['x'] % 1024 + m['w'] > 1024: pg = np.hstack([pg, nx])      # tile straddling the two halves of the sheet
    x = m['x'] % 1024; t = pg[m['y']:m['y'] + m['h'], x:x + m['w']]
    return t if t.shape == (m['h'], m['w']) else None

_COL = {}
def tile_rgb(t, m):
    """coloured texel block (m2colour: palette from the program ROM, luma ramp from the executed fill routine)"""
    import m2colour
    if not _COL: _COL['pal'] = m2colour.palette(); _COL['lr'] = m2colour.lumaram()
    lb = m.get('luma', 0); lr = _COL['lr']
    if not lr[(lb << 7):(lb << 7) + 128].any(): lb = 0               # base not filled by the boot routine: plain ramp
    return m2colour.colour_tile(t, m['cb'], lb, _COL['pal'], lr)

def to_image(t, alpha, m=None):
    rgb = tile_rgb(t, m) if m is not None else np.dstack([(t * 17).astype(np.uint8)] * 3)
    if not alpha: return Image.fromarray(rgb, 'RGB')
    a = np.where(t == 15, 0, 255).astype(np.uint8); rgb = np.where((t == 15)[:, :, None], 0, rgb).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, a]), 'RGBA')

def usable(pages, tiles):
    """tiles whose texels cannot be read (no ROM page fitted for that sheet half) count as untextured"""
    for n, m in list(tiles.items()):
        if m and tile(pages, m) is None: tiles[n] = None
    return tiles

def materials():
    """{name: info} of the exported course"""
    jp = os.path.join(OUT, 'materials.json')
    if os.path.exists(jp): return json.load(open(jp))
    out = {}
    for ln in open(os.path.join(OUT, 'src_course%s_hi.mtl' % classic_export.COURSE)):
        m = re.match(r'newmtl (tex_s(\d)_x(\d+)_y(\d+)_(\d+)x(\d+)_c([0-9A-F]+)(_mx)?(_my)?(_t)?)\s*$', ln)
        if m:
            out[m.group(1)] = dict(sheet=int(m.group(2)), x=int(m.group(3)), y=int(m.group(4)), w=int(m.group(5)), h=int(m.group(6)), cb=int(m.group(7), 16),
                                   mx=bool(m.group(8)), my=bool(m.group(9)), alpha=bool(m.group(10)))
        else:
            m = re.match(r'newmtl (col_[0-9A-F]+)', ln)
            if m: out[m.group(1)] = None
    return out

def main(choice=None):
    mats = classic_export.export(); pg = all_pages()
    rects, res = fit_pages(mats, pg)
    auto = {}
    for key, sc in res.items():
        print('sheet %d half %d: %d rectangles, best pages %s' % (key[0], key[1], len(rects[key]), [('%07x' % o, round(s, 2)) for s, o in sc[:3]]))
        auto[key] = sc[0][1]
    if choice is None and BLOCK is not None: choice = {k: BLOCK + 0x80000 * k[1] for k in res}     # course JSON: one contiguous 1 MB block per course
    if choice: auto.update(choice)
    json.dump({'%d,%d' % k: o for k, o in auto.items()}, open(PAGEFILE, 'w'))
    pages = {k: pg[o] for k, o in auto.items()}
    os.makedirs(os.path.join(OUT, 'textures'), exist_ok=True); os.makedirs(os.path.join(OUT, 'sheets'), exist_ok=True)
    for fn in os.listdir(os.path.join(OUT, 'textures')): os.remove(os.path.join(OUT, 'textures', fn))
    for (s, hf), img in pages.items():
        im = Image.fromarray((img * 17).astype(np.uint8)).convert('RGB')
        from PIL import ImageDraw
        dr = ImageDraw.Draw(im)
        for x, y, w, h in rects[(s, hf)]: dr.rectangle([x, y, x + w - 1, y + h - 1], outline=(255, 0, 0))
        im.save(os.path.join(OUT, 'sheets', 'sheet%d_half%d_rom%07x_rects.png' % (s, hf, auto[(s, hf)])))
        Image.fromarray((img * 17).astype(np.uint8)).save(os.path.join(OUT, 'sheets', 'sheet%d_half%d_rom%07x.png' % (s, hf, auto[(s, hf)])))
    n = 0; miss = 0
    for name, m in mats.items():
        if not m: continue
        t = tile(pages, m)
        if t is None: miss += 1; continue
        to_image(t, m['alpha'], m).save(os.path.join(OUT, 'textures', name + '.png')); n += 1
    print('%d tiles written, %d missing' % (n, miss))
    return mats, pages

if __name__ == '__main__':
    main()
