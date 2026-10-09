"""Per-course context for the classic importer. Course data lives in ../courses/<game>_<course>.json:
    name, objects [first, last] (object table rows of the hi-detail sections), centreline / collision (files written by
    classic/scripts/m2_collision.py), half_width, surface_codes {collision code: tarmac | gravel}, start {slice, direction},
    label_overrides {tile index: class}, textures {class: [track, id hex]}, art {...} (all-SR3 choices, see allsr3.py)
use(game, course) points every module at that course's files; nothing else in the code names a course."""
import os, json, collections
import numpy as np
from common import *
CDIR = os.path.join(WORK, 'courses'); CFG = {}

def use(game, course):
    import classic_export, classic_tex, build_classic as BC, retex, preview_obj, allsr3
    cfg = json.load(open(os.path.join(CDIR, '%s_%s.json' % (game, course)))); CFG.clear(); CFG.update(cfg); CFG['game'] = game; CFG['course'] = str(course); c = str(course)
    out = os.path.join(WORK, 'classic_tex', 'course' + c)
    classic_export.OUT = out; classic_export.COURSE = c; classic_export.COURSES = {c: tuple(cfg['objects'])}
    classic_tex.BLOCK = int(cfg['texel_block'], 16) if 'texel_block' in cfg else None
    classic_tex.OUT = out; classic_tex.PAGEFILE = os.path.join(out, 'pages.json')
    cl = os.path.join(os.path.dirname(WORK), 'classic', 'obj')
    BC.CSV = os.path.join(cl, cfg.get('centreline', 'src_course%s_centreline.csv' % c)); BC.COL = os.path.join(cl, cfg.get('collision', 'src_course%s_collision.obj' % c))
    BC.HI = os.path.join(out, 'src_course%s_hi.obj' % c); BC.XFORM = os.path.join(TMP, 'classic_xform.json' if c == '1' else 'classic_xform_%s.json' % c); preview_obj.XFORM = BC.XFORM
    BC.SURF_OF_CODE = {int(k): v for k, v in cfg.get('surface_codes', {'0': 'tarmac', '1': 'tarmac', '8': 'tarmac', '6': 'gravel'}).items()}
    BC.HALF_WIDTH = int(cfg.get('half_width', 7)); BC.START = (int(cfg.get('start', {}).get('slice', 10)), int(cfg.get('start', {}).get('direction', 1)))
    retex.RT = os.path.join(WORK, 'retex') if c == '1' else os.path.join(WORK, 'retex', '%s_%s' % (game, c)); os.makedirs(retex.RT, exist_ok=True)
    retex.CSVP = os.path.join(retex.RT, 'tile_labels.csv')
    for k, v in cfg.get('textures', {}).items(): retex.SR3_FOR_CLASS[k] = (v[0], int(v[1], 16))
    allsr3.configure(cfg.get('art', {}))
    cfg['game'] = game; cfg['course'] = c
    return cfg

def tile_stats(faces):
    """per tile: area, share of lying faces, mean upright face height"""
    st = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for name, sec, P, UV in faces:
        P = np.array(P); n = np.cross(P[1] - P[0], P[2] - P[0]); a = 0.5 * np.linalg.norm(n)
        if len(P) == 4: a += 0.5 * np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[0]))
        if a < 1e-9: continue
        ny = abs(n[1]) / max(np.linalg.norm(n), 1e-9); s = st[name]; s[0] += a
        if ny > 0.7: s[1] += a
        else: s[2] += a * np.ptp(P[:, 1]); s[3] += a
    return {k: dict(area=v[0], lying=v[1] / v[0], height=v[2] / v[3] if v[3] else 0.0) for k, v in st.items()}

def auto_labels(faces):
    """first guess of a class per tile from colour, alpha and how the tile is used. Reviewed by eye afterwards
    (label_overrides in the course JSON, or the CSV itself)."""
    import classic_tex
    pages = classic_tex.load_pages(); tiles = classic_tex.materials(); st = tile_stats(faces); out = {}
    for name, m in tiles.items():
        if not m: continue
        t = classic_tex.tile(pages, m)
        if t is None: continue
        rgb = classic_tex.tile_rgb(t, m).reshape(-1, 3).astype(float)
        if m['alpha']: rgb = rgb[(t != 15).ravel()] if (t != 15).any() else rgb
        r, g, b = rgb.mean(0); sat = max(r, g, b) - min(r, g, b); s = st.get(name, dict(area=0, lying=0, height=0)); green = g > r + 6 and g > b + 6
        if m['alpha']: c = 'crown' if green else ('fence' if s['height'] < 2.5 else 'trunk')
        elif s['lying'] > 0.6: c = 'grass' if green else ('asphalt' if sat < 22 else ('sand' if r > 150 and g > 120 else 'dirt'))
        elif green: c = 'tree_wall'
        elif s['height'] > 9 and sat > 18: c = 'rock'
        else: c = 'house_plaster'
        out[name] = c
    return out
