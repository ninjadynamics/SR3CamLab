"""CHECK POINT gantries for the imported 1995 courses: two posts and a blue banner with yellow letters across the road at
every 1995 time checkpoint (the sections the importer already uses for SR3's checkpoint markers, classic_notes 'classic'
mode), so that the banner you drive under is the checkpoint that fires.

Why this exists: the first try used ROM object 172, which is a hand-written white "CHECK POINT" text overlay, not the
trackside banner, and stands about 65 m off the road (user, 2026-10-07: "the white checkpoint banners are fake (wrong
texture, it should be blue and yellow) and crossing them doesn't trigger checkpoint"). The real 1995 gantry is a placed
object (trackside table kinds 16 / 17) whose model was not identified, so the gantry is built here: plain geometry and a
texture drawn by this script (no SEGA data). Emulator reference: Screenshots/ref_model2 (blue banner, yellow text, posts).

    faces = checkpoints1995.gantries(cfg, rd)        importer face format (material, section, [xyz], [uv]), SR3 coordinates
"""
import os, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from common import *

BANNER = 'tex_gantry_checkpoint_512x64'; POST = 'tex_gantry_post_32x32'

def course_dir(cfg): return os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''))

def textures(cfg):
    """writes the two PNG tiles into the course's textures folder (deterministic)"""
    d = os.path.join(course_dir(cfg), 'textures'); os.makedirs(d, exist_ok=True)
    im = Image.new('RGB', (512, 64), (22, 52, 160)); dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, 511, 63], outline=(236, 236, 240), width=3)
    font = None
    for fn in ('arialbd.ttf', 'ariblk.ttf', 'arial.ttf'):
        try: font = ImageFont.truetype(os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', fn), 46); break
        except OSError: pass
    font = font or ImageFont.load_default(); text = 'CHECK POINT'
    box = dr.textbbox((0, 0), text, font=font); dr.text(((512 - (box[2] - box[0])) // 2 - box[0], (64 - (box[3] - box[1])) // 2 - box[1]), text, fill=(250, 208, 30), font=font)
    im.save(os.path.join(d, BANNER + '.png'))
    Image.new('RGB', (32, 32), (46, 52, 66)).save(os.path.join(d, POST + '.png'))

def sections(cfg):
    """1995 time-checkpoint sections of the course (same source as import_classic.classic_notes)"""
    tp = os.path.join(os.path.dirname(WORK), 'classic', 'sr2_gameplay', cfg['game'], 'src_checkpoints_times.json')
    g = json.load(open(os.path.join(course_dir(cfg), 'gameplay.json'))); name = {1: 'Mountain', 2: 'Desert', 3: 'Lakeside', 4: 'Forest'}.get(int(cfg['course']))
    t = json.load(open(tp)); key = next((k for k in t if name and k.lower().startswith(name.lower()[:4])), None)
    if key is None: return [], g
    return [x for x in t[key]['checkpoint_sections'] if x > 0], g

def box(c, ax, ay, az, hx, hy, hz, mat, sec, front_uv=None):
    """axis-aligned-in-its-own-frame box centred at c with half sizes along the unit axes ax (right), ay (up), az (forward).
    -> OBJ-space faces, counter-clockwise seen from outside; the -az face (seen by a car driving along +az) carries front_uv."""
    def P(i, j, k): return tuple(c + i * hx * ax + j * hy * ay + k * hz * az)
    uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    f = [((P(-1, -1, -1), P(1, -1, -1), P(1, 1, -1), P(-1, 1, -1)), front_uv),            # faces -az: left of the driver first
         ((P(1, -1, 1), P(-1, -1, 1), P(-1, 1, 1), P(1, 1, 1)), front_uv),                # faces +az: reads the right way from behind too
         ((P(1, -1, -1), P(1, -1, 1), P(1, 1, 1), P(1, 1, -1)), None), ((P(-1, -1, 1), P(-1, -1, -1), P(-1, 1, -1), P(-1, 1, 1)), None),
         ((P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1)), None), ((P(-1, -1, 1), P(1, -1, 1), P(1, -1, -1), P(-1, -1, -1)), None)]
    return [((mat[0] if fuv else mat[1]), sec, list(q), list(fuv or uv)) for q, fuv in f]

def gantries(cfg, rd, clear=4.7, tall=1.8, post=0.22, side=1.6):
    import build_classic as BC
    secs, g = sections(cfg)
    if not secs: return []
    textures(cfg); C = np.loadtxt(os.path.join(course_dir(cfg), 'src_course%s_centreline.csv' % cfg['course']), delimiter=',', comments='#'); n = len(C)
    up = np.array([0.0, 1.0, 0.0]); out = []; ox, oz, zs = rd['ox'], rd['oz'], BC.ZS
    Vr = None; edges = None                                           # rd['V'] columns 0 / -1 are NOT the driveable edges (they gave a 30 m wide, tilted banner): fixed 12 m gantry on the centre line, like the 13 m 1995 one
    if Vr is not None and getattr(Vr, 'ndim', 0) == 3 and len(Vr) > 10:      # the SR3 road as built (variable width): posts stand just outside ITS edges,
        Vr = np.asarray(Vr, float); cen = Vr[:, rd['hw']]                     # not at a fixed half width (a post stood in a cliff, user 2026-10-07)
        edges = lambda q: (lambda k: (Vr[k, 0], Vr[k, -1]))(int(np.argmin(np.hypot(cen[:, 0] - (q[0] + ox), cen[:, 2] - (zs * q[2] + oz)))))
    for s in secs:
        i = int(s) % n; p = C[i].astype(float); f = C[(i + 1) % n] - C[(i - 1) % n]; f[1] = 0.0; f /= np.linalg.norm(f); r = np.cross(f, up)   # OBJ axes are right-handed: right = forward x up
        hw = float(cfg.get('gantry_half_width', 6.0))
        if edges:
            a, b = [np.array([e[0] - ox, e[1], (e[2] - oz) / zs]) for e in edges(p)]          # road edges back in OBJ axes
            mid = (a + b) / 2; half = np.linalg.norm((b - a)[[0, 2]]) / 2; p = np.array([mid[0], max(a[1], b[1], p[1]), mid[2]]); hw = half + 0.45
            rr = (b - a); rr[1] = 0.0; rr /= np.linalg.norm(rr); r = rr if np.dot(rr, r) > 0 else -rr; f = np.cross(up, r)
        sec = 'gantry_%d' % s; uvb = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        for sg in (-1.0, 1.0):                                         # posts, 1 m into the ground so no foot hangs on a slope
            out += box(p + sg * hw * r + up * ((clear + tall) / 2 - 0.5), r, up, f, post, (clear + tall) / 2 + 0.5, post, (POST, POST), sec)
        out += box(p + up * (clear + tall / 2), r, up, f, hw - post - 0.02, tall / 2, 0.12, (BANNER, POST), sec, front_uv=uvb)
    return [(m, sec, [(x + ox, y, zs * z + oz) for x, y, z in P][::int(zs)], uv[::int(zs)]) for m, sec, P, uv in out]

if __name__ == '__main__':
    cfg = json.load(open(os.path.join(WORK, 'courses', 'src_1.json'))); cfg.setdefault('game', 'src'); cfg.setdefault('gameplay', 'course1_mountain'); cfg.setdefault('course', '1')
    fs = gantries(cfg, dict(ox=137.745, oz=52.842)); print(len(fs), 'faces;', sections(cfg)[0]); print(fs[20][0], [tuple(round(v, 1) for v in q) for q in fs[20][2]], fs[20][3])
