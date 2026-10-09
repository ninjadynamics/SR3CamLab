"""All-SR3 retexture: every classic tile is replaced by SR3 art (artistic licence, see ../../13_retexture.md).
SR3 buildings are 3D models skinned from 512x512 atlases of pieces (walls, windows, doors), so there are no ready-made
facade pictures. This module COMPOSES facade bays, cut-outs and paint from SR3 texels:
    facade style  = seamless wall fill (an atlas patch, mirror-tiled) + an SR3 window / door piece pasted into one bay
    cut-outs      = SR3 cut-out pieces placed in the same layout as the classic tile (classic UVs stay valid)
Sources are the PNGs written by sr3_art.py from the user's own track files (../retex/art/<Track>/<id>.png).
    python allsr3.py      -> ../retex/allsr3_proof_*.png (every composed texture, to be LOOKED at)"""
import os, json, zlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from common import *
ART = os.path.join(WORK, 'retex', 'art'); SIZE = 512
_A = {}
def A(trk, tid):
    k = (trk, tid)
    if k not in _A:
        p = os.path.join(ART, trk, tid + '.png')
        if not os.path.exists(p):
            import sr3_art; sr3_art.main(trk)
        _A[k] = np.array(Image.open(p).convert('RGBA'))
    return _A[k]
def crop(spec):
    trk, tid, r = spec; a = A(trk, tid)
    return a if r is None else a[r[1]:r[3], r[0]:r[2]]
def rs(img, w, h): return np.array(Image.fromarray(img).resize((w, h), Image.LANCZOS))
def seamless(patch, size=SIZE):
    """2 x 2 mirrored copies: wraps without a seam in both directions"""
    p = rs(patch[:, :, :3], size // 2, size // 2); top = np.hstack([p, p[:, ::-1]]); return np.vstack([top, top[::-1]])
def tinted(rgb, col, k=1.0):
    c = 1.0 + (np.array(col, np.float32) - 1.0) * k; g = rgb.astype(np.float32); m = g.mean()
    return np.clip(g * c[None, None, :], 0, 255).astype(np.uint8)
def paste(base, piece, box, bottom=False, frame=0):
    """piece (RGBA) fitted inside box (fractions x0, y0, x1, y1 of base) keeping its aspect; centred, or standing on the box bottom"""
    H, W = base.shape[:2]; bx0, by0, bx1, by1 = [int(round(v * s)) for v, s in zip(box, (W, H, W, H))]
    ph, pw = piece.shape[:2]; sc = min((bx1 - bx0) / pw, (by1 - by0) / ph); w, h = max(2, int(pw * sc)), max(2, int(ph * sc))
    p = rs(piece, w, h); x = bx0 + (bx1 - bx0 - w) // 2; y = (by1 - h) if bottom else by0 + (by1 - by0 - h) // 2
    out = base.copy(); a = (p[:, :, 3:4].astype(np.float32) / 255.0) if p.shape[2] == 4 else 1.0
    if frame:                                                          # soft shadow line around the opening
        out[max(0, y - frame):y + h + frame, max(0, x - frame):x + w + frame] = (out[max(0, y - frame):y + h + frame, max(0, x - frame):x + w + frame] * 0.55).astype(np.uint8)
    out[y:y + h, x:x + w] = (p[:, :, :3] * a + out[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)
    return out

L, AL, CA = 'Lakeside4', 'Alpine4', 'Canyon4'
# wall fill, upper-floor window, ground-floor window, door ; bay width / storey height in metres
STYLES = {
    'plaster_white': dict(fill=(L, '05d9d287', (6, 6, 318, 218)), win=(L, 'dc5e6f91', (258, 8, 510, 462)), gwin=(L, 'dc5e6f91', (0, 372, 220, 512)), door=(L, 'dc5e6f91', (0, 0, 245, 330)), bay=3.0, floor=3.1, tint=True),
    'plaster_beige': dict(fill=(AL, '6fdfabb4', (6, 268, 250, 506)), win=(AL, '6fdfabb4', (258, 0, 370, 160)), gwin=(AL, 'a33fab8f', (362, 130, 512, 245)), door=(AL, 'a33fab8f', (440, 335, 512, 505)), bay=3.0, floor=3.0, tint=True),
    'plaster_rough': dict(fill=(AL, 'a33fab8f', (6, 166, 350, 320)), win=(L, '05d9d287', (410, 126, 490, 222)), gwin=(L, '05d9d287', (372, 228, 482, 300)), door=(L, 'a1c60215', (75, 365, 130, 482)), bay=2.8, floor=3.0, tint=True),
    'stone_rubble': dict(fill=(L, 'efadc649', (0, 278, 255, 510)), win=(L, '972c2b1c', (395, 62, 512, 182)), gwin=(L, 'efadc649', (335, 0, 512, 180)), door=(L, 'a1c60215', (75, 365, 130, 482)), bay=3.2, floor=3.0),
    'stone_block': dict(fill=(L, 'a057c011', (0, 408, 384, 510)), win=(L, 'a057c011', (24, 4, 116, 122)), gwin=(L, 'a057c011', (24, 4, 116, 122)), door=(L, '9885b7b5', (190, 0, 262, 218)), bay=3.2, floor=3.2),
    'brick': dict(fill=(L, '9ad7a350', None), win=(L, 'a1c60215', (305, 160, 380, 232)), gwin=(L, 'a1c60215', (220, 160, 290, 235)), door=(L, 'a1c60215', (160, 165, 215, 255)), bay=3.0, floor=3.0, plainfill=True),
    'church': dict(fill=(L, '9885b7b5', (0, 278, 255, 458)), win=(L, '9885b7b5', (95, 0, 186, 222)), gwin=(L, '9885b7b5', (0, 0, 92, 222)), door=(L, '9885b7b5', (190, 0, 262, 218)), bay=4.0, floor=5.0, tall=True),
    'arcade': dict(fill=(L, 'a057c011', (0, 408, 384, 510)), win=(L, 'a057c011', (24, 4, 116, 122)), gwin=(L, '9885b7b5', (190, 0, 262, 218)), door=(L, '9885b7b5', (190, 0, 262, 218)), bay=3.5, floor=4.0, tall=True),
}
CLASS_STYLES = {'house_plaster': ['plaster_white', 'plaster_beige', 'plaster_rough'], 'house_stone': ['stone_rubble', 'stone_block', 'plaster_rough'], 'house_brick': ['brick', 'plaster_beige', 'brick'],
                'church': ['church'], 'arcade': ['arcade'], 'house_front': ['plaster_white', 'plaster_beige', 'stone_rubble']}
PASTEL = {'cream': (1.0, 0.96, 0.86), 'pink': (1.0, 0.80, 0.78), 'yellow': (1.0, 0.92, 0.66), 'blue': (0.82, 0.89, 1.0), 'plain': (1.0, 1.0, 1.0), 'ochre': (0.96, 0.78, 0.56)}
def pastel_for(rgb, h):
    r, g, b = [float(v) for v in rgb]; mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 40: return ('plain', 'cream', 'cream', 'blue')[h % 4]
    if r >= g and r >= b: return 'yellow' if g > 0.8 * r else ('ochre' if g > 0.55 * r else 'pink')
    return 'blue' if b >= g else 'cream'

_T = {}
def facade_tex(style, kind, tint='plain'):
    """kind: 'up' (upper-floor bay), 'gw' (ground-floor bay with a window), 'gd' (ground-floor bay with a door), 'pl' (plain wall)"""
    k = (style, kind, tint)
    if k in _T: return _T[k]
    s = STYLES[style]; f = crop(s['fill'])
    fill = rs(f[:, :, :3], SIZE, SIZE) if s.get('plainfill') else seamless(f)
    if s.get('tint'): fill = tinted(fill, PASTEL[tint])
    tall = s.get('tall')
    if kind == 'up': img = paste(fill, crop(s['win']), (0.20, 0.12 if tall else 0.16, 0.80, 0.86 if tall else 0.84), frame=3)
    elif kind == 'gw': img = paste(fill, crop(s['gwin']), (0.20, 0.25 if not tall else 0.2, 0.80, 0.78 if not tall else 1.0), bottom=bool(tall and style == 'arcade'), frame=3)
    elif kind == 'gd': img = paste(fill, crop(s['door']), (0.25, 0.40 if not tall else 0.35, 0.75, 1.0), bottom=True, frame=3)
    else: img = fill
    _T[k] = img; return img

# ---- cut-outs laid out like the classic tile (classic UVs are kept) -> (rgb, hole)
def _rgba(spec, w, h, box=(0, 0, 1, 1), bottom=True):
    base = np.zeros((h, w, 4), np.uint8); p = crop(spec); ph, pw = p.shape[:2]
    bx0, by0, bx1, by1 = [int(round(v * s)) for v, s in zip(box, (w, h, w, h))]; sc = min((bx1 - bx0) / pw, (by1 - by0) / ph)
    ww, hh = max(2, int(pw * sc)), max(2, int(ph * sc)); q = rs(p, ww, hh); x = bx0 + (bx1 - bx0 - ww) // 2; y = (by1 - hh) if bottom else by0 + (by1 - by0 - hh) // 2
    base[y:y + hh, x:x + ww] = q; return base
def _split(img):
    hole = img[:, :, 3] < 128; rgb = img[:, :, :3].copy()
    if hole.any() and (~hole).any(): rgb[hole] = rgb[~hole].mean(0).astype(np.uint8)       # no dark fringe from the transparent texels
    return rgb, hole
def _stretch(spec, w, h): return rs(crop(spec), w, h)
def masked(mask, fillspec, w, h, shade=None):
    """SR3 texels (seamless fill) shown through a mask (True = opaque) resized smoothly to w x h"""
    m = np.array(Image.fromarray((mask * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))) > 110
    f = seamless(crop(fillspec), max(w, h))[:h, :w]
    if shade is not None: f = np.clip(f.astype(np.float32) * shade[:, :, None], 0, 255).astype(np.uint8)
    return f, ~m

def cutout(cls, tile_shape=None, classic_mask=None):
    h0, w0 = tile_shape if tile_shape else (256, 256); w = 512 if w0 >= h0 else 256; h = max(64, int(round(w * h0 / w0 / 4.0)) * 4); h = min(h, 1024)
    if cls == 'crown' or cls == 'foliage': return _split(_stretch(PIECES['crown'], w, h))      # the dense SR3 leaf mass reads best as a round crown
    if cls == 'tree': return _split(_stretch(PIECES['tree'], w, h))
    if cls == 'ivy': return _split(_stretch(PIECES['ivy'], w, h))
    if cls == 'bush': return _split(_stretch(PIECES['bush'], w, h))
    if cls == 'fence':                                                 # the classic 'fence' is a guard rail: its silhouette in SR3 galvanised metal
        return masked(classic_mask, (AL, 'a24a68e9', (4, 4, 196, 150)), w, h, np.full((h, w), 0.42, np.float32))      # dark galvanised rail, not a white fence
    if cls in ('trunk', 'bare'):                                                 # bark behind a drawn trunk: column, forking near the top
        yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w], float)[:, None, None]; half = 0.10 + 0.05 * yy
        m = (np.abs(xx - 0.5) < half) & (yy > 0.38)
        for sgn in (-1, 1):
            cx = 0.5 + sgn * (0.38 - yy) * 0.75; m |= (np.abs(xx - cx) < 0.07) & (yy <= 0.40)
        return masked(m, PIECES['bark'], w, h)
    if cls in ('lamp', 'mask'):                                        # classic silhouette, SR3 metal texels, lit from the left
        shade = np.tile(np.linspace(0.55, 0.25, w)[None, :], (h, 1)).astype(np.float32)           # dark painted metal
        return masked(classic_mask, (L, 'dc5e6f91', (262, 474, 508, 510)), w, h, shade)
    if cls == 'paint': return masked(classic_mask, (L, '54c156ac', (30, 20, 44, 230)), 512, 512)
    raise KeyError(cls)

BOARDS = [(AL, '55644df5'), (AL, 'cd719948'), (AL, 'efff912e'), (AL, 'd07234f4'), (AL, '4939c3df'), (AL, 'aeec9c24')]   # SEGA, WRC, Pirelli, easynet, Karcher, Abu Dhabi
FLAT = (L, 0x1c24d989)                                                # grey roughcast for the untextured classic polygons
TREE_ROW = (L, 0x0fcf0f84)
ROCKS = [(CA, 0x53850d6a), (CA, 0x89f2eea0), (CA, 0xc24eb36a)]         # Canyon4 sandstone faces (user's art direction): one per classic rock tile, by hash
ROAD_TARMAC = (L, 0x7f8b9a62, 0x6025fa42)                             # Lakeside_Tarmac base + top: the only blue-grey asphalt in SR3 (road_match.py)
ROAD_DIRT = (L, 0x029be493, 0xed8aec61)                               # Lakeside_Dirt base + top: nearest to the classic sandy verge / loose section

TREE_ROW_UV = dict(aspect=2.0, vtop=0.19, vbot=0.975)
# single pieces, replaceable per course (course JSON: art.pieces, same keys; rect = [x0, y0, x1, y1] or null for the whole texture)
PIECES = dict(windows=[(L, 'dc5e6f91', (258, 8, 510, 462)), (AL, 'a33fab8f', (362, 130, 512, 245)), (L, '972c2b1c', (395, 62, 512, 182)), (AL, '6fdfabb4', (258, 0, 370, 160))],
              doors=[(L, 'dc5e6f91', (0, 0, 245, 330)), (AL, 'a33fab8f', (440, 335, 512, 505)), (L, 'a1c60215', (75, 365, 130, 482))],
              crown=(L, 'a057c011', (312, 2, 490, 250)), tree=(L, '6ebafe84', (258, 300, 512, 474)), bush=(CA, '782406a2', None), ivy=(L, 'a057c011', (312, 2, 490, 250)),
              wallfill=(L, '05d9d287', (6, 6, 318, 218)), bark=(AL, '2fde3ae7', None))
_PDEF = {k: (list(v) if isinstance(v, list) else v) for k, v in PIECES.items()}
def wall_tex(tint):
    k = ('wall', tint)
    if k not in _T: _T[k] = tinted(seamless(crop(PIECES['wallfill'])), PASTEL[tint])
    return _T[k]
def opening_tex(cls, name, tile_shape, mask):
    """a classic window / door tile -> an SR3 window / door stretched over the classic opening (the box of its opaque texels)"""
    h0, w0 = tile_shape; sc = max(1, 256 // max(w0, h0)); w, h = w0 * sc, h0 * sc; ys, xs = np.nonzero(mask) if mask is not None and mask.any() else (np.array([0, h0 - 1]), np.array([0, w0 - 1]))
    x0, x1, y0, y1 = xs.min() * sc, (xs.max() + 1) * sc, ys.min() * sc, (ys.max() + 1) * sc
    lst = PIECES['doors' if cls == 'door' else 'windows']; p = crop(lst[hsh(name) % len(lst)]); q = rs(np.ascontiguousarray(p[:, :, :3]), max(2, x1 - x0), max(2, y1 - y0))
    rgb = np.zeros((h, w, 3), np.uint8); rgb[:] = q.reshape(-1, 3).mean(0).astype(np.uint8); rgb[y0:y1, x0:x1] = q; hole = np.ones((h, w), bool); hole[y0:y1, x0:x1] = False
    return rgb, (hole if hole.any() else None)
ROCK_TINT = 0.6                                                        # how far the rock textures are pulled towards the classic rock colour (0 = as in SR3)
_DEF = None
def configure(art):
    """per-course all-SR3 choices (course JSON, key art): rocks [[track, id]..], road_tarmac / road_dirt [track, base, top],
    tree_row [track, id, aspect, vtop, vbot], class_styles {class: [style..]}, rock_tint, flat [track, id]"""
    global ROCKS, ROAD_TARMAC, ROAD_DIRT, TREE_ROW, TREE_ROW_UV, ROCK_TINT, FLAT, _DEF
    if _DEF is None: _DEF = dict(ROCKS=list(ROCKS), ROAD_TARMAC=ROAD_TARMAC, ROAD_DIRT=ROAD_DIRT, TREE_ROW=TREE_ROW, TREE_ROW_UV=dict(TREE_ROW_UV), ROCK_TINT=ROCK_TINT, FLAT=FLAT, CS={k: list(v) for k, v in CLASS_STYLES.items()})
    ROCKS = list(_DEF['ROCKS']); ROAD_TARMAC = _DEF['ROAD_TARMAC']; ROAD_DIRT = _DEF['ROAD_DIRT']; TREE_ROW = _DEF['TREE_ROW']; TREE_ROW_UV = dict(_DEF['TREE_ROW_UV']); ROCK_TINT = _DEF['ROCK_TINT']; FLAT = _DEF['FLAT']
    CLASS_STYLES.clear(); CLASS_STYLES.update({k: list(v) for k, v in _DEF['CS'].items()})
    h = lambda v: int(v, 16) if isinstance(v, str) else v
    if 'rocks' in art: ROCKS = [(t, h(i)) for t, i in art['rocks']]
    if 'road_tarmac' in art: ROAD_TARMAC = (art['road_tarmac'][0], h(art['road_tarmac'][1]), h(art['road_tarmac'][2]))
    if 'road_dirt' in art: ROAD_DIRT = (art['road_dirt'][0], h(art['road_dirt'][1]), h(art['road_dirt'][2]))
    if 'tree_row' in art: t = art['tree_row']; TREE_ROW = (t[0], h(t[1])); TREE_ROW_UV = dict(aspect=t[2], vtop=t[3], vbot=t[4])
    if 'flat' in art: FLAT = (art['flat'][0], h(art['flat'][1]))
    if 'rock_tint' in art: ROCK_TINT = float(art['rock_tint'])
    for k, v in art.get('class_styles', {}).items(): CLASS_STYLES[k] = list(v)
    PIECES.clear(); PIECES.update({k: (list(v) if isinstance(v, list) else v) for k, v in _PDEF.items()}); _T.clear()
    sp = lambda v: (v[0], v[1], tuple(v[2]) if v[2] else None)
    for k, v in art.get('pieces', {}).items(): PIECES[k] = [sp(x) for x in v] if isinstance(v[0], list) else sp(v)

def tinted_texture(trk, tid, target, k):
    """SR3 texture with its mean colour pulled a fraction k towards target (RGB): keeps the SR3 detail, shifts the hue"""
    a = A(trk, '%08x' % tid)[:, :, :3].astype(np.float32); m = a.reshape(-1, 3).mean(0); gain = 1.0 + (np.array(target, np.float32) / np.maximum(m, 1.0) - 1.0) * k
    return np.clip(a * gain[None, None, :], 0, 255).astype(np.uint8)

def hsh(*a): return zlib.crc32(repr(a).encode())

if __name__ == '__main__':
    out = os.path.join(WORK, 'retex'); items = []
    for st in STYLES:
        for kd in ('up', 'gw', 'gd', 'pl'): items.append(('%s %s' % (st, kd), facade_tex(st, kd, 'pink' if st == 'plaster_white' else 'yellow' if st == 'plaster_beige' else 'plain'), None))
    m = np.zeros((128, 64), bool); m[20:, 28:36] = True; m[10:30, 16:48] = True
    for c in ('crown', 'tree', 'bare', 'ivy', 'fence', 'trunk', 'lamp', 'paint'):
        rgb, hole = cutout(c, (128, 64) if c in ('lamp', 'fence') else None, m if c in ('lamp', 'paint', 'fence') else None); items.append((c, rgb, hole))
    cols = 8; cell = 200
    for pg in range(0, len(items), 32):
        part = items[pg:pg + 32]; W = Image.new('RGB', (cols * cell, ((len(part) + cols - 1) // cols) * (cell + 14)), (40, 40, 40)); dr = ImageDraw.Draw(W)
        for i, (nm, rgb, hole) in enumerate(part):
            im = rgb.copy()
            if hole is not None: im[hole] = (200, 0, 200)
            x, y = (i % cols) * cell, (i // cols) * (cell + 14); W.paste(Image.fromarray(im).resize((cell - 2, cell - 2)), (x, y)); dr.text((x + 2, y + cell - 1), nm, fill=(255, 255, 0))
        p = os.path.join(out, 'allsr3_proof_%d.png' % (pg // 32 + 1)); W.save(p); print(p)
