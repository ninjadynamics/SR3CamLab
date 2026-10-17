"""SEGA Rally Championship course 1 (Mountain): OBJ + MTL (classic_export.py) and the texture tiles from the main data ROM.
    python classic_tex.py     -> ../classic_tex/course1/{src_course1_hi.obj, .mtl, textures/*.png, sheets/*.png}
Tiles are luminance (4-bit texel x 17) unless ../tmp/m2/palram.bin etc. exist (see 12_classic_textures.md).
Translucent materials (name ends _t): texel 15 is a hole -> alpha 0.
Without numpy since 2026-10-15 (kb 31) for the export (main, fit_pages, page_bytes, tile_bytes, to_image): a page or a tile is bytes, one
texel a byte, row after row; colours come from bytes.translate tables. load_pages, tile, tile_rgb and usable still hand the importer's
build (which computes with numpy) numpy arrays, importing numpy only then."""
import os, re, sys, json, math
from PIL import Image
import m2tex, classic_export
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = classic_export.OUT
PAGEFILE = os.path.join(OUT, 'pages.json')
CANDIDATES = list(range(0x200000, 0x800000, 0x80000))
SIDE = 1024                                                           # a page: 1024 x 1024 texels
X17 = bytes(min(v * 17, 255) for v in range(256))                     # texel -> grey (t * 17)
SQ = bytes(min(v * v, 255) for v in range(256))                       # texel -> its square (texels are 0..15)

BLOCK = None
def page_bytes():
    """{ROM offset: the page there, 1024 x 1024 texel bytes} for every candidate offset"""
    d = m2tex.main_data(); return {o: m2tex.decode(d[o:o + 0x80000]) for o in CANDIDATES}

def all_pages():
    """{ROM offset: (1024, 1024) uint8 numpy array}: page_bytes() for the callers that compute with numpy"""
    import numpy as np
    return {o: np.frombuffer(bytearray(b), np.uint8).reshape(SIDE, SIDE) for o, b in page_bytes().items()}

def _std_gt_half(pg, x, y, w, h):
    """im[y:y + h, x:x + w].std() > 0.5 of a page's texels. The variance of whole numbers is the exact (n S2 - S1^2) / n^2; numpy's float
    value can only fall on the other side of 0.25 when the exact one IS 0.25 (any other is at least 1 / 4n^2 away, numpy's rounding a
    million times smaller), so only then is numpy's own arithmetic redone: (x - mean)^2 summed pairwise over the block, / n, sqrt."""
    s1 = s2 = 0; n = w * h
    for r in range(y, y + h):
        seg = pg[r * SIDE + x:r * SIDE + x + w]; s1 += sum(seg); s2 += sum(seg.translate(SQ))
    k = 4 * (n * s2 - s1 * s1)
    if k != n * n: return k > n * n
    mean = s1 / n; sq = [(v - mean) * (v - mean) for r in range(y, y + h) for v in pg[r * SIDE + x:r * SIDE + x + w]]
    return math.sqrt((0.0 + _pw(sq)) / n) > 0.5

def _pw(v):
    """numpy's pairwise sum (rtbake/rt_bake_game5.py pwsum)"""
    n = len(v)
    if n < 8:
        s = 0.0
        for t in v: s += t
        return s
    if n <= 128:
        r = list(v[:8]); e = n - n % 8
        for i in range(8, e, 8):
            for j in range(8): r[j] += v[i + j]
        s = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
        for t in v[e:]: s += t
        return s
    h = n // 2; h -= h % 8
    return _pw(v[:h]) + _pw(v[h:])

def fit_pages(mats, pages):
    """for every (sheet, half) used: the ROM page on which the tile rectangles line up best (pages: page_bytes()).
    score = mean over rectangles of (texel step across the rectangle's left/top border) - (step just inside)
    The steps are whole numbers, so each mean is their exact sum / count, as numpy's float mean is; numpy did the same with arrays:
        np.abs(im[y:y + h, x] - im[y:y + h, x - 1]).mean() - np.abs(im[y:y + h, x + 1] - im[y:y + h, x]).mean() ..."""
    rects = {}
    for name, m in mats.items():
        if m: rects.setdefault((m['sheet'], m['x'] // 1024), set()).add((m['x'] % 1024, m['y'], m['w'], m['h']))
    res = {}; dif = lambda a, b: sum(map(abs, map(int.__sub__, a, b)))
    for key, rs in sorted(rects.items()):
        sc = []
        for off, pg in pages.items():
            tot = 0.0; n = 0
            col = lambda c, y, h: pg[y * SIDE + c:(y + h - 1) * SIDE + c + 1:SIDE]; row = lambda r, x, w: pg[r * SIDE + x:r * SIDE + x + w]
            for x, y, w, h in rs:
                if x + w > 1024 or y + h > 1024: continue
                if x > 0: tot += dif(col(x, y, h), col(x - 1, y, h)) / h - dif(col(x + 1, y, h), col(x, y, h)) / h; n += 1
                if y > 0: tot += dif(row(y, x, w), row(y - 1, x, w)) / w - dif(row(y + 1, x, w), row(y, x, w)) / w; n += 1
                tot += 1.0 * _std_gt_half(pg, x, y, w, h) - 1.0 * (not any(any(row(r, x, w)) for r in range(y, y + h))); n += 1      # ... .std() > 0.5, .max() == 0
            sc.append((tot / max(n, 1), off))
        sc.sort(reverse=True); res[key] = sc
    return rects, res

def load_pages(choice=None):
    pg = all_pages()
    if choice is None: choice = {tuple(int(v) for v in k.split(',')): o for k, o in json.load(open(PAGEFILE)).items()}
    return {k: pg[o] for k, o in choice.items()}

def tile(pages, m):
    """numpy pages (load_pages) -> the tile's texels, a numpy array"""
    import numpy as np
    pg = pages.get((m['sheet'], m['x'] // 1024))
    if pg is None: return None
    nx = pages.get((m['sheet'], m['x'] // 1024 + 1))
    if nx is not None and m['x'] % 1024 + m['w'] > 1024: pg = np.hstack([pg, nx])      # tile straddling the two halves of the sheet
    x = m['x'] % 1024; t = pg[m['y']:m['y'] + m['h'], x:x + m['w']]
    return t if t.shape == (m['h'], m['w']) else None

def tile_bytes(sheet, width, m, clip=False):
    """a sheet as bytes (width texels a row) -> the tile (bytes, w, h), or None when it does not lie whole on the sheet (numpy's
    sheet[y:y + h, x:x + w] would come out smaller); clip=True: that smaller piece, as numpy's slice gives it"""
    x, y, w, h = m['x'], m['y'], m['w'], m['h']; H = len(sheet) // width
    if x + w > width or y + h > H:
        if not clip: return None
        w = max(0, min(width, x + w) - x); h = max(0, min(H, y + h) - y)
    return b''.join(sheet[r * width + x:r * width + x + w] for r in range(y, y + h)), w, h

def sheet_bytes(left, right):
    """np.hstack([left, right]) of two 1024 x 1024 pages: 2048 texels a row"""
    return b''.join(left[r * SIDE:(r + 1) * SIDE] + right[r * SIDE:(r + 1) * SIDE] for r in range(SIDE))

_COL = {}
def tile_rgb(t, m):
    """coloured texel block (m2colour: palette from the program ROM, luma ramp from the executed fill routine); numpy in and out"""
    import m2colour
    if not _COL: _COL['pal'] = m2colour.palette(); _COL['lr'] = m2colour.lumaram()
    lb = m.get('luma', 0); lr = _COL['lr']
    if not lr[(lb << 7):(lb << 7) + 128].any(): lb = 0               # base not filled by the boot routine: plain ramp
    return m2colour.colour_tile(t, m['cb'], lb, _COL['pal'], lr)

_COLB = {}
def to_image(t, alpha, m=None):
    """a tile (bytes, w, h) -> its PIL image: RGB, or RGBA with texel 15 a hole (alpha 0, colour 0). The colours as tile_rgb gives them
    (m2colour.colour_tables), or grey (t * 17) without a material. numpy: Image.fromarray(np.dstack([rgb, a]), 'RGBA') ..."""
    b, w, h = t
    if m is None: tabs = [bytes(0 if alpha and v == 15 else X17[v] for v in range(256))] * 3
    else:
        import m2colour
        if not _COLB: _COLB['pal'] = m2colour.palette_bytes(); _COLB['lr'] = m2colour.lumaram_bytes()
        lb = m.get('luma', 0); lr = _COLB['lr']
        if not any(lr[(lb << 7):(lb << 7) + 128]): lb = 0           # base not filled by the boot routine: plain ramp
        tabs = m2colour.colour_tables(m['cb'], lb, _COLB['pal'], lr, alpha)
    k = 4 if alpha else 3; out = bytearray(k * w * h)
    for ch in range(3): out[ch::k] = b.translate(tabs[ch])
    if alpha: out[3::k] = b.translate(bytes(0 if v == 15 else 255 for v in range(256)))
    return Image.frombytes('RGBA' if alpha else 'RGB', (w, h), bytes(out))

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
    mats = classic_export.export(); pg = page_bytes()
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
        im = Image.frombytes('L', (SIDE, SIDE), img.translate(X17)).convert('RGB')
        from PIL import ImageDraw
        dr = ImageDraw.Draw(im)
        for x, y, w, h in rects[(s, hf)]: dr.rectangle([x, y, x + w - 1, y + h - 1], outline=(255, 0, 0))
        im.save(os.path.join(OUT, 'sheets', 'sheet%d_half%d_rom%07x_rects.png' % (s, hf, auto[(s, hf)])))
        Image.frombytes('L', (SIDE, SIDE), img.translate(X17)).save(os.path.join(OUT, 'sheets', 'sheet%d_half%d_rom%07x.png' % (s, hf, auto[(s, hf)])))
    n = 0; miss = 0
    for name, m in mats.items():
        if not m: continue
        hf = m['x'] // 1024; p0 = pages.get((m['sheet'], hf)); p1 = pages.get((m['sheet'], hf + 1))      # (tile(): the page, and the next one when the tile straddles both)
        if p0 is None: miss += 1; continue
        t = tile_bytes(sheet_bytes(p0, p1), 2048, dict(m, x=m['x'] % 1024)) if (p1 is not None and m['x'] % 1024 + m['w'] > 1024) else tile_bytes(p0, SIDE, dict(m, x=m['x'] % 1024))
        if t is None: miss += 1; continue
        to_image(t, m['alpha'], m).save(os.path.join(OUT, 'textures', name + '.png')); n += 1
    print('%d tiles written, %d missing' % (n, miss))
    return mats, pages

if __name__ == '__main__':
    main()
