"""SEGA Rally Championship course 1 (Mountain) -> SR3, Desert4 slot. Steps 14-19 (14/15 are REBUILT with the fixes).
    python build_classic.py [name prefix]
Coordinates: classic OBJ = (x, y, -gameZ) (right-handed). SR3 is left-handed Y-up like the Model 2 game, so
SR3 = (x + ox, y, -z_obj + oz): the game's own coordinates, re-centred. (Steps 14/15 of the second batch used the OBJ
coordinates directly and were therefore MIRRORED.)"""
import os, sys, re, json, struct, math, collections
import numpy as np
from common import *
import sbfw, trackdeform as TDm, scene11, meshgen, bsp
import build_testtrack as BT, build_more as BM
from build_testtrack import log, LOG

CL = os.path.join(os.path.dirname(WORK), 'classic', 'obj')
# ZS: sign applied to the classic exports' z (they are x, y, -gameZ). First in-game run (2026-10-07): with ZS = -1 (the
# game's own coordinates) the course appeared MIRRORED in SEGA Rally 3 (board text reversed), so SR3 = the OBJ axes: ZS = +1.
ZS = -1.0     # settled in game 2026-10-07: with +1 the board text and the whole layout were mirrored (castle on the wrong side); the earlier 'mirrored' report was the signed-uv bug
CSV = os.path.join(CL, 'src_course1_centreline.csv'); COL = os.path.join(CL, 'src_course1_collision.obj')
HI = os.path.join(WORK, 'classic_tex', 'course1', 'src_course1_hi.obj')      # classic_export.py: correct texture pointers
XFORM = os.path.join(TMP, 'classic_xform.json')
# Desert4 road layers used (10_surfaces.md): Terrain_Safari_Tarmac base/top, Terrain_Safari_Gravel base/top
TARMAC = (0xe56e4a5c, 0x0558e395); GRAVEL = (0x9cbfa41a, 0x6ec69183)
# classic collision attribute bits 16-19 -> SR3 surface. 1 = the asphalt with tyre marks (782 polys, on the racing line),
# 0 = road polys in the town part (229), 8 = 11 special polys (start/finish area): all tarmac. 6 = 336 polys 7-12 m from
# the centre line under the rough stony tile x0512_y0256: gravel shoulder.
SURF_OF_CODE = {0: 'tarmac', 1: 'tarmac', 8: 'tarmac', 6: 'gravel'}
SURF_DEFAULT = 'gravel'                                               # course setting surface_default. Mountain: 'tarmac' - the course is asphalt end to end with soil only beside the road in the forest (the 1995 code 6); with 'gravel' 63 000 of 112 000 cells were Desert's loose gravel and the car slid (user, 2026-10-09)

# ---------------------------------------------------------------- road
class AttrField(BM.HeightField):
    def at2(self, x, z, yref):
        """(height, attribute) of the drivable polygon under (x, z) nearest in height to yref"""
        best = None
        for i in self.b.get((int(math.floor(x / self.cell)), int(math.floor(z / self.cell))), ()):
            a, b, c = self.t[i]
            d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-9: continue
            u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d; v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d; w = 1 - u - v
            if u < -1e-4 or v < -1e-4 or w < -1e-4: continue
            y = u * a[1] + v * b[1] + w * c[1]
            if best is None or abs(y - yref) < abs(best[0] - yref): best = (y, self.attr[i])
        return best

HALF_WIDTH = 7; START = (10, 1)                                       # per course: course.use()
def flip_v(uv):
    """In the game (ZS = +1 world) the 1995 textures came out upside-down (in-game run 2026-10-07): v is flipped per face.
    Textures wrap, so 1 - v and 2 - v are the same picture; the one that keeps the face inside the mesh format's 0..2 is used."""
    return uv        # WRONG GUESS, kept only as a note: once the signed-uv bug was fixed, every texture was upside-down WITH this flip (in-game run); v needs no flip
    if ZS < 0: return uv
    top = 1.0 if max(v for u, v in uv) <= 1.0 and min(v for u, v in uv) >= 0.0 else 2.0
    return [(u, top - v) for u, v in uv]

def import_road(half_width=None):
    """centre line -> slices (SR3 coordinates), per-vertex heights and per-cell surface from the collision mesh"""
    half_width = half_width or (MAX_HALF_WIDTH if VARIABLE else HALF_WIDTH)
    C = np.loadtxt(CSV, delimiter=',', comments='#'); C[:, 2] *= ZS                       # see ZS
    tris = [(a, t * np.array([1, 1, ZS])) for a, t in BM.load_obj_tris(COL)]            # all polys, bit 23 included
    road = AttrField([t for t in tris if not (t[0] >> 23) & 1]); allf = AttrField(tris)
    P = BM.resample_closed(C); n = len(P)
    D = np.roll(P, -1, 0) - np.roll(P, 1, 0); D[:, 1] = 0; D /= np.linalg.norm(D, axis=1)[:, None]
    lat = BT.lateral(D)
    def smooth(a, w):
        k = np.ones(2 * w + 1) / (2 * w + 1); return np.convolve(np.concatenate([a[-w:], a, a[:w]]), k, 'valid')
    yc = P[:, 1].copy()
    for i in range(n):
        h = road.at2(P[i, 0], P[i, 2], P[i, 1])
        if h: yc[i] = h[0]
    yc = smooth(yc, 3)
    B = 2 * half_width + 1; Y = np.zeros((n, B)); code = np.full((n, B), -1); src = collections.Counter()
    for i in range(n):
        for k in range(B):
            c = k - half_width; q = P[i] + lat[i] * c
            h = road.at2(q[0], q[2], yc[i])
            if h and abs(h[0] - yc[i]) < 0.35 * abs(c) + 0.6: Y[i, k] = h[0]; code[i, k] = (h[1] >> 16) & 15; src['road poly'] += 1
            else:
                h = allf.at2(q[0], q[2], yc[i])
                if h and abs(h[0] - yc[i]) < 0.5 * abs(c) + 0.6: Y[i, k] = h[0]; code[i, k] = 100; src['off-road poly'] += 1
                else: Y[i, k] = np.nan; src['none'] += 1
        row = Y[i]; bad = np.isnan(row)
        if bad.all(): row[:] = yc[i]
        elif bad.any(): row[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), row[~bad])
    for k in range(B): Y[:, k] = smooth(Y[:, k], 2)                                       # along-track smoothing of every column
    ox = -(P[:, 0].min() + P[:, 0].max()) / 2; oz = -(P[:, 2].min() + P[:, 2].max()) / 2
    json.dump(dict(ox=ox, oz=oz, note='SR3 = (x_obj + ox, y, -z_obj + oz)'), open(XFORM, 'w'))
    wl = wr = None
    if VARIABLE:
        wl, wr = classic_edges(road, P, lat, yc, half_width)
    V = np.zeros((n, B, 3))
    for k in range(B): V[:, k] = P + lat * (k - half_width)
    V[:, :, 1] = Y + (ROAD_UNDER if ROAD_VERBATIM else 0.03); V[:, :, 0] += ox; V[:, :, 2] += oz      # (verbatim road: the SR3 road is not seen and lies 2 cm UNDER the 1995 polygons, so that nothing of it can cover them)                # 3 cm above the classic polygons left at the road edges
    # drivable extent each side (cells that have a road polygon), for the report
    ext = [(int((code[i, :half_width] >= 0).sum()), int((code[i, half_width + 1:] >= 0).sum())) for i in range(n)]
    step = np.linalg.norm(np.roll(V[:, half_width], -1, 0) - V[:, half_width], axis=1)
    grade = np.abs(np.roll(yc, -1) - yc) / np.maximum(step, 1e-6)
    turn = np.arccos(np.clip((D * np.roll(D, -1, 0)).sum(1), -1, 1))
    cross = np.abs(Y[:, -1] - Y[:, 0]) / (2 * half_width)
    log('       road: %d slices, step %.3f..%.3f m, heights from %s' % (n, step.min(), step.max(), dict(src)))
    log('       elevation %.1f..%.1f, max grade %.1f%% at slice %d, tightest bend radius %.1f m at slice %d, max cross-fall %.1f%%' %
        (yc.min(), yc.max(), 100 * grade.max(), int(grade.argmax()) + 1, 1 / max(turn.max(), 1e-9), int(turn.argmax()) + 1, 100 * cross.max()))
    log('       collision surface codes under the cells: %s' % dict(collections.Counter(code.ravel().tolist())))
    log('       drivable polys found per side (cells): left median %d min %d, right median %d min %d of %d' %
        (np.median([e[0] for e in ext]), min(e[0] for e in ext), np.median([e[1] for e in ext]), min(e[1] for e in ext), half_width))
    rd = dict(V=V, D=D, lat=lat, code=code, hw=half_width, ox=ox, oz=oz, grade=grade, turn=turn, n=n)
    if wl is not None:
        rd['wl'] = wl; rd['wr'] = wr
        log('       variable width from the 1995 drivable polygons (no bank flag): left %.1f..%.1f m (median %.1f), right %.1f..%.1f m (median %.1f), total %.1f..%.1f m' %
            (wl.min(), wl.max(), np.median(wl), wr.min(), wr.max(), np.median(wr), (wl + wr).min(), (wl + wr).max()))
    return rd

VARIABLE = False; MAX_HALF_WIDTH = 16; MIN_HALF_WIDTH = 3.5
def classic_edges(road, P, lat, yc, cap):
    """per slice: how far the 1995 DRIVABLE ground (collision polygons without the bank flag, bit 23) reaches to the left
    and to the right of the centre line, walking outwards in 25 cm steps until the ground ends or steps by more than 30 cm.
    Then: minimum over the neighbouring slices, at least MIN_HALF_WIDTH, at most cap, and no more than 0.5 m change per
    slice (TrackDeform edges move at most one column per slice in SEGA's own tracks)."""
    n = len(P); W = np.zeros((2, n))
    for i in range(n):
        for s_, sg in enumerate((-1.0, 1.0)):
            y = yc[i]; w = 0.0
            for st in range(1, int(cap / 0.25) + 1):
                c = st * 0.25; q = P[i] + lat[i] * (sg * c); h = road.at2(q[0], q[2], y)
                if not h or abs(h[0] - y) > 0.30: break
                y = h[0]; w = c
            W[s_, i] = w
    out = []
    for w in W:
        w = np.minimum(np.minimum(np.roll(w, 1), w), np.roll(w, -1)); w = np.clip(w, MIN_HALF_WIDTH, cap)
        for it in range(3):
            for i in range(n): w[i] = min(w[i], w[i - 1] + 0.5)
            for i in range(n - 1, -1, -1): w[i] = min(w[i], w[(i + 1) % n] + 0.5)
        out.append(np.round(w, 2))
    return out[0], out[1]

class Near:
    """nearest2d with the bucket grid built once (many small queries against the same centre line)"""
    def __init__(self, P, cell=8.0):
        self.P = np.asarray(P, float); self.cell = cell; self.b = collections.defaultdict(list)
        for i, (x, z) in enumerate(np.floor(self.P / cell).astype(int)): self.b[(x, z)].append(i)
    def __call__(self, Q):
        Q = np.asarray(Q, float); idx = np.zeros(len(Q), int); P = self.P; cell = self.cell
        for j, q in enumerate(Q):
            cx, cz = int(np.floor(q[0] / cell)), int(np.floor(q[1] / cell)); r = 1
            while True:
                cand = [i for dx in range(-r, r + 1) for dz in range(-r, r + 1) for i in self.b.get((cx + dx, cz + dz), ())]
                if cand:
                    d = np.hypot(P[cand, 0] - q[0], P[cand, 1] - q[1]); k = int(np.argmin(d))
                    if d[k] <= r * cell or r > 64: idx[j] = cand[k]; break
                r += 1
                if r > 200: break
        return idx

def road_side(rd):
    """-> function(points) -> (nearest slice index, signed lateral position, left limit (negative), right limit) per point"""
    cen = rd['V'][:, rd['hw']]; lat = rd['lat']; n = len(cen)
    wl = rd.get('wl', np.full(n, float(rd['hw']))); wr = rd.get('wr', np.full(n, float(rd['hw'])))
    near = Near(cen[:, [0, 2]])
    def f(pts):
        pts = np.asarray(pts, float); idx = near(pts[:, [0, 2]])
        c = ((pts[:, [0, 2]] - cen[idx][:, [0, 2]]) * lat[idx][:, [0, 2]]).sum(1)
        return idx, c, -wl[idx], wr[idx]
    return f

def road_model(rd, src_td, page):
    """TrackDeform model: constant width, cell surfaces tarmac/gravel with blended corner weights (Stadium's scheme:
    id table [tarmacBase, tarmacTop, gravelTop, gravelBase], batch list [3,0,2,1], weights nibble1+3 tarmac, 0+2 gravel)"""
    V = rd['V']; code = rd['code']; n, B, _ = V.shape; A = B - 1
    tar = np.zeros((n, A), bool)
    for i in range(n):
        for k in range(A):
            c = [code[i, k], code[i, k + 1]]
            names = [SURF_OF_CODE.get(int(x), SURF_DEFAULT) for x in c]      # (cells with no 1995 surface code: SURF_DEFAULT)
            tar[i, k] = 'tarmac' in names and not (names[0] != 'tarmac' and names[1] != 'tarmac')
            tar[i, k] = names[0] == 'tarmac' or names[1] == 'tarmac'
    hashes = [TARMAC[0], TARMAC[1], GRAVEL[1], GRAVEL[0]]
    # corner tarmac fraction = mean of the cells around the corner (slice i..i-1, column k..k-1)
    f = np.zeros((n, B))
    for k in range(B):
        cols = [c for c in (k - 1, k) if 0 <= c < A]
        f[:, k] = np.mean([tar[:, c] for c in cols] + [np.roll(tar[:, c], 1) for c in cols], axis=0)
    def word(fr):
        t = int(round(8 * fr)); g = 8 - t; return (g) | (t << 4) | (g << 8) | (t << 12)
    b14 = collections.Counter(bytes(v['b14']) for i in range(1, src_td.n + 1, 7) for v in src_td.verts[i][:-1]).most_common(1)[0][0]
    sl = [None]
    if 'wl' in rd:
        # variable width, SEGA's layout (04_trackdeform_road.md): interior vertices on whole-metre columns, the first / last
        # vertex on the road edge; a slice's records span min(off, previous off) .. max(right column, previous right column),
        # the surplus ones collapsed on the edge; +6E = off - previous off.
        hw = rd['hw']; cl = -rd['wl']; cr = rd['wr']; off = np.floor(cl + 1e-6).astype(int); rc = np.ceil(cr - 1e-6).astype(int)
        cen = V[:, hw]; lat = rd['lat']; rec = [bytes([3, 0, 2, 1, 0xff, 0xff, 0xff, 4, 0, 2, 0])] * ((n + 3) // 4 + 1); na = collections.Counter()
        for i in range(n):
            p = (i - 1) % n; j = (i + 1) % n; c0 = min(off[i], off[p]); c1 = max(rc[i], rc[p]); cols = np.arange(c0, c1 + 1); Bi = len(cols)
            assert abs(off[i] - off[p]) <= 1 and abs(rc[i] - rc[p]) <= 1
            x = np.clip(cols.astype(float), cl[i], cr[i]); g = x + hw; k0 = np.clip(np.floor(g).astype(int), 0, B - 2); fr = g - k0
            v = np.zeros(Bi, TDm.VDT); pos = cen[i][None, :] + lat[i][None, :] * x[:, None]; pos[:, 1] = V[i, k0, 1] * (1 - fr) + V[i, k0 + 1, 1] * fr
            v['pos'] = pos; v['w10'] = 0xffffffff
            kk = np.clip(cols + hw, 0, B - 1)                               # grid column of every record
            for r_ in range(Bi):
                kc = int(min(kk[r_], A - 1)); kn = int(min(kk[r_] + 1, B - 1))
                if tar[i, kc]: v[r_]['surf'] = (0, 1, 0, 0); v[r_]['w1c'] = hashes[1]
                else: v[r_]['surf'] = (3, 2, 0, 0); v[r_]['w1c'] = hashes[2]
                v[r_]['w20'] = word(f[i, kk[r_]]); v[r_]['w24'] = word(f[j, kk[r_]]); v[r_]['w28'] = word(f[i, kn]); v[r_]['w2c'] = word(f[j, kn])
                if r_ < Bi - 1: v[r_]['b14'] = np.frombuffer(b14, np.uint8)
            d6e = int(off[i] - off[p]); Ai = int(rc[i] - off[i]); na[Ai] += 1
            sl.append(dict(A=Ai, off=int(off[i]), b6e=d6e, b6f=1 if d6e > 0 else 0, B=Bi, water=-99999.0, verts=v))
        log('       surface cells: tarmac %d, gravel %d ; quads across (A) %d..%d, column offset %d..%d' % (int(tar.sum()), int((~tar).sum()), min(na), max(na), off.min(), off.max()))
        return dict(slices=sl, rec11=rec, texids=list(hashes), hashes=list(hashes), pages=[page], w10=2)
    for i in range(n):
        v = np.zeros(B, TDm.VDT); v['pos'] = V[i]; v['w10'] = 0xffffffff
        j = (i + 1) % n
        for k in range(A):
            if tar[i, k]: v[k]['surf'] = (0, 1, 0, 0); v[k]['w1c'] = hashes[1]
            else: v[k]['surf'] = (3, 2, 0, 0); v[k]['w1c'] = hashes[2]
            v[k]['w20'] = word(f[i, k]); v[k]['w24'] = word(f[j, k]); v[k]['w28'] = word(f[i, k + 1]); v[k]['w2c'] = word(f[j, k + 1])
            v[k]['b14'] = np.frombuffer(b14, np.uint8)
        v[A]['surf'] = v[A - 1]['surf']; v[A]['w1c'] = v[A - 1]['w1c']
        for fld in ('w20', 'w24', 'w28', 'w2c'): v[A][fld] = word(f[i, A])
        sl.append(dict(A=A, off=-rd['hw'], b6e=0, b6f=0, B=B, water=-99999.0, verts=v))
    rec = [bytes([3, 0, 2, 1, 0xff, 0xff, 0xff, 4, 0, 2, 0])] * ((n + 3) // 4 + 1)
    log('       surface cells: tarmac %d, gravel %d' % (int(tar.sum()), int((~tar).sum())))
    return dict(slices=sl, rec11=rec, texids=list(hashes), hashes=list(hashes), pages=[page], w10=2)

def build_road_track(des, rd, with_spline=True):
    trk = des.copy(); f = trk.files['master_gfx_xdata']; fx = trk.files['master_xdata']
    by = f.byid(); r = BT.gfx_root(f); t = TDm.parse_td(by[r.u32(0xc)])
    cen = rd['V'][:, rd['hw']]
    small = [c for c in f.kinds(4) if len(c.data) == 868 and c.data[48 + 80:48 + 84] == b'DXT1']
    pg_a, pg_b = t.pages[0][0], t.pages[0][1]
    if small:
        a = sbfw.Ch(4, 0xa07e0001, BT.tex_fill(small[0], (0, 255, 0)), [], []); b = sbfw.Ch(4, 0xa07e0002, BT.tex_fill(small[0], (128, 128, 128)), [], [])
        f.chunks.insert(0, a); f.chunks.insert(1, b); pg_a, pg_b = a.id, b.id
    model = road_model(rd, t, BT.page_for(cen, texa=pg_a, texb=pg_b))
    BT.set_td(f, model)
    lv = BM.leaves_for(cen)
    BT.set_scene(f, lv, []); BT.drop_boundary(f)
    BT.set_aimap(fx, BT.aimap_cells(BT.td_rows(model)))
    BT.set_route(fx, START[0], START[1], BT.LAKESIDE_GRID)
    if with_spline: BT.add_spline(fx, cen)
    return trk, model, lv

# ---------------------------------------------------------------- scenery
TEX_OF = {}                                                           # add_scenery: classic tile name -> ids of the texture chunks made for it
BAKED = {}                                                            # composed tiles of overlay_bake.py: name -> (rgb, hole or None)
BAKE_DIR = None                                                       # folder that receives them as PNG (previews, fill1995.tile_alpha)
OVERLAY_MODE = 'lift'                                                 # 'bake' (import_classic, course JSON "overlays"): coplanar stacks are resolved in the plane, nothing is lifted
FAR_MODE = 'near'                                                     # 'view': far_scale from the FARTHEST road point (a rock beside one part of the road is watched from across the course)
def save_baked(name, rgb, hole):
    BAKED[name] = (np.ascontiguousarray(rgb), hole)
    if BAKE_DIR:
        from PIL import Image as _I
        os.makedirs(BAKE_DIR, exist_ok=True); a = np.where(hole, 0, 255).astype(np.uint8) if hole is not None else np.full(rgb.shape[:2], 255, np.uint8)
        _I.fromarray(np.dstack([rgb, a]), 'RGBA').save(os.path.join(BAKE_DIR, name + '.png'))
_TILES = {}
HD_USED = {}
TEXMAP = {}; TEXMAP_FINISH = {}                                       # texture id -> how it was made (texfast.py rewrites single textures of a built track from this)
def hd_tile(name):
    """RE-AUTHORED TILES (user, 2026-10-08: upscaled / repainted in Photoshop). A PNG <course>/textures_hd/<tile>.png replaces the 1995 tile of
    that name, at whatever size it has, when it DIFFERS from the export in <course>/textures (so the folder may hold untouched copies).
    Transparent texels (alpha < 128) are the cut-out's holes. -> (rgb, hole or None), or None."""
    if not EXTRA_TEX: return None
    if name in HD_USED: return HD_USED[name]
    from PIL import Image as _I
    p = os.path.join(EXTRA_TEX + '_hd', name + '.png'); o = os.path.join(EXTRA_TEX, name + '.png'); out = None
    if os.path.exists(p):
        im = _I.open(p).convert('RGBA'); same = False
        if os.path.exists(o):
            io = _I.open(o).convert('RGBA'); same = io.size == im.size and np.array_equal(np.asarray(io), np.asarray(im))
        if not same:
            w, h = im.size; w2 = int(2 ** np.clip(np.round(np.log2(w)), 2, 11)); h2 = int(2 ** np.clip(np.round(np.log2(h)), 2, 11))      # sides are powers of two (compression blocks, mip chain)
            if (w2, h2) != (w, h): im = im.resize((w2, h2), _I.LANCZOS)
            a = np.array(im); hole = a[:, :, 3] < 128; out = (np.ascontiguousarray(a[:, :, :3]), hole if hole.any() else None)
    HD_USED[name] = out; return out

def tile_pixels(name):
    """-> (rgb, hole or None) of a material's picture as add_scenery draws it (ROM tile, backdrop PNG, composed tile), or None"""
    name = str(name).split('|')[0]
    if name in BAKED: return BAKED[name]
    hd_ = hd_tile(name)
    if hd_ is not None: return hd_
    import classic_tex
    if not _TILES: _TILES['pages'] = classic_tex.load_pages(); _TILES['tiles'] = classic_tex.usable(_TILES['pages'], classic_tex.materials())
    m = _TILES['tiles'].get(name)
    if m:
        t = classic_tex.tile(_TILES['pages'], m); return classic_tex.tile_rgb(t, m), ((t == 15) if m['alpha'] else None)
    if EXTRA_TEX and os.path.exists(os.path.join(EXTRA_TEX, name + '.png')):
        from PIL import Image as _I
        im = np.array(_I.open(os.path.join(EXTRA_TEX, name + '.png')).convert('RGBA')); h = im[:, :, 3] < 128
        return np.ascontiguousarray(im[:, :, :3]), (h if (name.endswith('_t') and h.any()) else None)
    return None
EXTRA_TEX = None                                                      # folder of PNG tiles for materials that are not in the course's own tile set
DROPPED = []                                                          # classic faces inside the road strip (last load_visual)
UV_FIXED = []; UV_FLAT = []
def uv_area(U):
    U = np.asarray(U, float); return 0.5 * abs(float(np.sum(U[:, 0] * np.roll(U[:, 1], -1) - np.roll(U[:, 0], -1) * U[:, 1])))
def world_area(P):
    P = np.asarray(P, float); n = np.zeros(3)
    for i in range(len(P)): n += np.cross(P[i], P[(i + 1) % len(P)])
    return 0.5 * float(np.linalg.norm(n))
def normalise_uv(faces, factor=8.0):
    """1995 polygons whose tile repeats absurdly often (Mountain: two tree-line boards with u 1..27 over 9 and 14 m = the wall
    of green streaks in the forest, and the road polygon beside them with 28 repeats over 5 m = the bands across the road;
    all in object 1291) get the usual density of their tile: per tile the median of repeats per metre is taken over all its
    faces, and a face more than `factor` times denser on an axis is scaled back to that median about its lowest uv."""
    dens = collections.defaultdict(list); rec = []
    for fc in faces:
        P = np.asarray(fc[2], float); U = np.asarray(fc[3], float); size = float(np.linalg.norm(P.max(0) - P.min(0)))
        if size < 0.5 or len(U) != len(P): rec.append(None); continue
        d = np.ptp(U, axis=0) / size; rec.append(d); dens[fc[0]].append(d)
    med = {m: np.median(np.array(v), axis=0) for m, v in dens.items() if len(v) >= 5}; out = []; UV_FIXED[:] = []; UV_FLAT[:] = []
    for fc, d in zip(faces, rec):
        m = med.get(fc[0])
        if d is None or m is None: out.append(fc); continue
        U = np.asarray(fc[3], float).copy(); ch = False; Pw = np.asarray(fc[2], float)
        if uv_area(U) < 1e-4 * max(float(np.mean(m)), 1e-3) ** 2 * world_area(Pw) and world_area(Pw) > 0.25:      # the uv of a real polygon lie on a line (a smear of one texel row): mapped flat in its plane at the tile's usual density
            nrm = np.zeros(3)
            for i_ in range(len(Pw)): nrm += np.cross(Pw[i_], Pw[(i_ + 1) % len(Pw)])
            nrm /= max(np.linalg.norm(nrm), 1e-9); up = np.array([0.0, 1.0, 0.0]) if abs(nrm[1]) < 0.9 else np.array([0.0, 0.0, 1.0]); e1 = np.cross(up, nrm); e1 /= np.linalg.norm(e1); e2 = np.cross(nrm, e1); dn = float(np.mean(m)) * 1.4
            U = np.stack([U[:, 0].min() + ((Pw - Pw[0]) @ e1 - ((Pw - Pw[0]) @ e1).min()) * dn, U[:, 1].min() + ((Pw - Pw[0]) @ e2 - ((Pw - Pw[0]) @ e2).min()) * dn], 1); ch = True; UV_FLAT.append(fc[0])
        for ax in (0, 1):
            if m[ax] > 1e-6 and d[ax] > factor * m[ax] and np.ptp(U[:, ax]) > 2.0: lo = U[:, ax].min(); U[:, ax] = lo + (U[:, ax] - lo) * (m[ax] / d[ax]); ch = True
        if ch: UV_FIXED.append((fc[0], fc[1], tuple(np.round(np.mean(fc[2], axis=0), 1)))); out.append((fc[0], fc[1], fc[2], [tuple(map(float, u)) for u in U]))
        else: out.append(fc)
    if UV_FIXED: log('       1995 uv repeats far beyond the usual for the tile / uv on a line: %d polygons given the usual density of their tile (%d of them had their uv on a line): %s' % (len(UV_FIXED), len(UV_FLAT), UV_FIXED[:6]))
    return out

def load_visual(rd, extra=None):
    """classic hi model -> list of (material, section, [corner positions in SR3 coords], [uv]) with faces inside the road
    strip removed (they are replaced by the SR3 road)."""
    ox, oz = rd['ox'], rd['oz']; V = []; VT = []; faces = []; mat = None; sec = None
    global ROADPTS; ROADPTS = np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]]
    for ln in open(HI):
        if ln.startswith('v '): x, y, z = map(float, ln.split()[1:4]); V.append((x + ox, y, ZS * z + oz))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('o '): sec = ln.split()[1]
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]
            faces.append((mat, sec, [V[a] for a, b in ix][::int(ZS)], flip_v([VT[b] for a, b in ix][::int(ZS)])))    # a mirror (ZS = -1) flips winding
    if extra:                                                         # backdrop objects (import_classic.backdrop): 29 of Mountain's are second copies of course polygons, corner for corner
        def _key(P): return frozenset((round(p[0], 2), round(p[1], 2), round(p[2], 2)) for p in P)
        have = {_key(fc[2]) for fc in faces}; kept = [fc for fc in extra if _key(fc[2]) not in have]
        log('       backdrop joins the course before the overlap handling: %d faces, %d dropped (same corners as a course polygon)' % (len(extra), len(extra) - len(kept)))
        faces = faces + kept
    if OVERLAY_MODE == 'bake': faces = normalise_uv(faces)
    pairs, faces = split_pairs(faces)
    if OVERLAY_MODE == 'bake':
        import overlay_bake
        seen_ = set(); one = []                                       # a cut-out board listed once per side (same tile, same corners): one copy, the SR3 cut-out material is two-sided
        for fc in faces:
            k_ = (fc[0], frozenset((round(p[0], 2), round(p[1], 2), round(p[2], 2)) for p in fc[2]))
            if str(fc[0]).endswith('_t') and k_ in seen_ and not str(fc[1]).endswith(SINGLE): continue
            seen_.add(k_); one.append(fc)
        log('       1995 double polygons: %d second sides of cut-out boards dropped' % (len(faces) - len(one)))
        faces = overlay_bake.resolve(one, tile_pixels, save_baked, ROADPTS, log)
    else: faces = dedupe_overlays(faces)
    PAIRS.clear(); PAIRS.update(id(fc) for fc in pairs)
    if ROAD_VERBATIM:                                                 # the 1995 road stays where it is, joined to its walls and rock (see ROAD_VERBATIM)
        cut_ = split_at_road(rd, faces) if 'wl' in rd else list(faces); road_ = list(DROPPED); DROPPED.clear()      # (split_at_road only tells WHICH polygons are road and cuts them to 1 m; nothing is moved)
        ROAD_TILES.clear(); ROAD_TILES.update(str(fc[0]).split('|')[0] for fc in road_)
        log('       verbatim road: %d tiles are road surface ; %s' % (len(ROAD_TILES), ('cut in place into %d pieces of at most 1 m' % len(road_)) if ROAD_CUT else 'left as the 1995 polygons'))
        return (cut_ + road_ + pairs) if ROAD_CUT else (faces + pairs)
    if 'wl' in rd: return split_at_road(rd, faces if OVERLAY_MODE == 'bake' else stack_layers(faces)) + pairs      # bake: overlay_bake.resolve left no stack
    cen = rd['V'][:, rd['hw']]; hw = rd['hw']
    allv = np.array([p for fc in faces for p in fc[2]]); idx, dist = nearest2d(cen[:, [0, 2]], allv[:, [0, 2]], cell=8.0)
    keep = []; k = 0; dropped = 0; lowered = 0; DROPPED.clear()
    for fc in faces:
        m = len(fc[2]); ii = idx[k:k + m]; dd = dist[k:k + m]; k += m
        P = np.array(fc[2]); c = P.mean(0); nrm = np.cross(P[1] - P[0], P[2] - P[0]); ln = np.linalg.norm(nrm)
        jc = int(np.argmin(np.hypot(cen[ii, 0] - c[0], cen[ii, 2] - c[2]))); dc = float(np.hypot(cen[ii[jc], 0] - c[0], cen[ii[jc], 2] - c[2]))
        flat = ln > 0 and abs(nrm[1] / ln) > 0.8
        lying = ln > 0 and abs(nrm[1] / ln) > 0.5                      # upright faces (rock foot, kerb sides) stay: dropping them left holes
        inside = (lying and all(dd[j] < hw - 0.3 and abs(fc[2][j][1] - cen[ii[j], 1]) < 1.2 for j in range(m))) or (flat and dc < hw - 1.0 and abs(c[1] - cen[ii[jc], 1]) < 1.0 and max(dd) < hw + 6)
        if inside: dropped += 1; DROPPED.append(fc)
        else: keep.append(fc)
    # the replaced faces are cut to 2 m pieces; corners under the SR3 road go 20 cm down, corners beyond its edge stay, so
    # the classic verge still meets the rock foot / kerb (lowering whole faces left a 20 cm slit there, deleting them a gap)
    pieces = split_faces(DROPPED, 2.0)
    if pieces:
        pv = np.array([p for fc in pieces for p in fc[2]]); _, pd = nearest2d(cen[:, [0, 2]], pv[:, [0, 2]], cell=8.0); k = 0
        ph = pv[:, 1] - road_height(rd)(pv)                             # height of every corner above the SR3 road surface
        for mat_, sec_, P, UV in pieces:
            under = (pd[k:k + 4] < hw - 0.4) & (ph[k:k + 4] < 0.12); k += 4     # corner covered by the SR3 road (banks rising inside the strip are not)
            if under.all(): continue
            keep.append((mat_, sec_, [(p[0], p[1] - (0.20 if under[j] else 0.0), p[2]) for j, p in enumerate(P)], UV)); lowered += 1
    log('       classic visual model: %d faces, %d inside the road strip replaced by the SR3 road (%d verge pieces kept beside it), %d kept, %d materials' % (len(faces), dropped, lowered, len(keep), len({f[0] for f in keep})))
    return keep

PAIRS = set()                                                          # id() of the front/back pair faces of the last load_visual
SINGLE = '~s'                                                          # end of the section name of a cut-out face that is drawn single-sided (split_pairs)
def split_pairs(faces):
    """The 1995 model lists 2819 polygons twice on the same corners with OPPOSITE winding and the same tile: a front and
    a back (the hardware culls back faces, so a board or wall meant to be seen from both sides is two polygons, each with
    its own uv so text reads right from its side). These stay single-sided, each 5 mm off the shared plane on its own
    side, and are kept out of the overlap handling (which used to treat the back as a layer on the front).
    -> (pairs, the other faces)"""
    def key(P): return frozenset((round(p[0], 2), round(p[1], 2), round(p[2], 2)) for p in P)
    def normal(P):
        P = np.array(P, float); n = np.cross(P[1] - P[0], P[2] - P[0]); l = np.linalg.norm(n); return n / l if l > 1e-9 else None
    by = collections.defaultdict(list)
    for i, fc in enumerate(faces):
        if not str(fc[0]).endswith('_t'): by[key(fc[2])].append(i)
    paired = {}
    for k, ii in by.items():
        if len(ii) < 2: continue
        n0 = normal(faces[ii[0]][2])
        if n0 is None: continue
        for j in ii[1:]:
            n1 = normal(faces[j][2])
            if n1 is not None and float(np.dot(n0, n1)) < -0.9: paired[ii[0]] = n0; paired[j] = n1; break
    pairs = [(faces[i][0], faces[i][1], [tuple(np.array(p) + 0.005 * n) for p in faces[i][2]], faces[i][3]) for i, n in paired.items()]
    # CUT-OUT boards listed once per side with a DIFFERENT picture on each side: every 1995 tree is built of blades that run
    # from the tree's axis outwards, the front face showing the left half of the trunk / crown tile (u 0.5 .. 0), the back face
    # the right half (u 0.5 .. 1). Until 2026-10-07 the second face was dropped as "the same board again" and the first drawn
    # two-sided: fat trunks showed only the sliver of their left half ("floating trees"), thin trees one stem instead of
    # three, crowns one half mirrored. Both faces stay, each SINGLE-sided (section name + SINGLE: no offset is needed, the
    # hardware culls the one facing away), and both go through the overlap handling on their own side.
    byc = collections.defaultdict(list); single = set()
    for i, fc in enumerate(faces):
        if str(fc[0]).endswith('_t'): byc[(fc[0], key(fc[2]))].append(i)
    def cornermap(fc): return {(round(p[0], 2), round(p[1], 2), round(p[2], 2)): np.array(u, float) for p, u in zip(fc[2], fc[3])}
    for k, ii in byc.items():
        for a_ in range(len(ii) - 1):
            for b_ in range(a_ + 1, len(ii)):
                i, j = ii[a_], ii[b_]
                if i in single and j in single: continue
                n0, n1 = normal(faces[i][2]), normal(faces[j][2])
                if n0 is None or n1 is None or float(np.dot(n0, n1)) > -0.9: continue
                ma, mb = cornermap(faces[i]), cornermap(faces[j])
                if any(q in mb and np.abs(ma[q] - mb[q]).max() > 0.02 for q in ma): single.add(i); single.add(j)
    rest = [((fc[0], str(fc[1]) + SINGLE, fc[2], fc[3]) if i in single else fc) for i, fc in enumerate(faces) if i not in paired]
    log('       1995 cut-out boards with a different picture on each side: %d faces kept single-sided (tree blades)' % len(single))
    log('       1995 front/back pairs: %d polygons (kept single-sided, 5 mm apart); the other %d go on' % (len(pairs), len(rest)))
    return pairs, rest

def two_sided(fc):
    """Opaque 1995 polygons WITHOUT a back twin are drawn two-sided in SR3 (material switch): which side the 1995 game
    shows comes from a stored normal that is not reliable for every polygon, and a culled wall is a hole in the scenery."""
    return fc if (str(fc[0]).endswith('_t') or '|' in str(fc[0])) else (str(fc[0]) + '|2',) + tuple(fc[1:])      # (a key that already says how it is drawn, e.g. '|3' from lightside.py, is left alone)

SHADOW_CELLS = {0x4D4: 0, 0x4E4: 1, 0x4F8: 0, 0x50C: 0, 0x51C: 0, 0x52C: 1, 0x540: 1, 0x554: 1, 0x574: 1, 0x594: 0, 0x5B4: 0, 0x5D8: 0, 0x620: 0, 0x65C: 0, 0x670: 0}
def shadow_recv(mat):
    """Uber material switches as in Desert4's 3546ce1e (163 SEGA materials: alpha blend + static AND dynamic shadow receive).
    Each switch VALUE of the 1848-byte material is the u32 right BEFORE its inline name string (regex gbUber[A-Za-z]+,
    value at match.start() - 4): +4D4 ATEST, +4E4 ABLEND, +4F8 ABLENDAdd, +50C DSIDE, +51C SCAST, +52C SSRECV, +540 SDRECV,
    +554 DIFFM, +574 NORM, +594 LMAP, +5B4 SPECM, +5D8 TWOS, +620 REFL, +65C SCROLL, +670 DISCR (07_glue_and_other_files.md).
    The earlier cells (taken by position in the name list) left SDRECV at 0: the cars threw no shadow on the draped road."""
    d = bytearray(mat.data)
    for o, v in SHADOW_CELLS.items(): struct.pack_into('<I', d, o, v)
    # gf3SpecCol (the 3 floats before its name, +498): the cloned material keeps the SPEC switch with no specular MAP, so the road shone
    # with the template's flat 0.5 specular (user, 2026-10-08: "the roads are too reflective ... even the dirt is reflective there").
    # SEGA's own materials with SPEC and no SPECM carry specular colour 0; so do these (ROAD_SPEC, course JSON "road_spec").
    struct.pack_into('<3f', d, 0x498, ROAD_SPEC, ROAD_SPEC, ROAD_SPEC)
    mat.data = bytes(d); return mat
MISSING_TEX = []
ROAD_SPEC = 0.0
LIGHT_K = 0.0
UNLIT = set(); UNLIT_TPL = None; UNLIT_GAIN = 0.94                  # gates: SEGA's unlit material. 1.075 (= as bright as lit scenery) read "a little bit overbright" (user, 2026-10-08; the Model 2 gates are slightly shaded): now about 0.9 of the lit scenery
SCENE_GAIN = None; _NO_GAIN = [False]                               # per-channel gain on every classic tile except the unlit ones (see vivid)
LIGHT_FLIP = False                                                 # (mirrors the horizontal part of the normals. It was switched on after a report of shade on the sunny side; that was the far side of free-standing rock, cured by oriented_normals' 'lower side' rule. With it ON, build Z7L25 was measured inverted: sun on the left, left houses lit. OFF.)
ROAD_BLEND = True
ROAD_UP_NORMALS = False                                                # (True lit the road as flat ground: it came out nearly white; the bands it was tried against were clamped uv, see add_scenery)
ROAD_MODE = 'drape'                                                   # 'layers' (see add_scenery) or 'drape' (every 1995 road polygon as a decal)
ROAD_MAIN = []
ROAD_DECALS = True                                                     # False: no draped 1995 road at all (test: do SR3's car shadows come back?)
LAYER_STEP = 0.02
ROADPTS = None                                                         # (n, 2) road centre line x, z: set by load_visual / import_classic
def far_scale(P):
    """how much wider a gap between two stacked faces must be than next to the road. The depth buffer resolves about
    d^2 / (near x 2^24) at distance d, and the camera is always near the road: a face d metres from the road needs
    (d / 50)^2 times the roadside gap (2 cm at 50 m, 0.72 m at 300 m; capped at 60 x). User: zero z-fighting."""
    if ROADPTS is None: return 1.0
    c = np.asarray(P, float).mean(0); d2 = ((ROADPTS - c[[0, 2]]) ** 2).sum(1); d = np.sqrt(d2.max() if FAR_MODE == 'view' else d2.min())
    return float(min(60.0, max(1.0, (d / 50.0) ** 2)))
def stack_layers(faces):
    """coplanar polygons that overlap (layers.py: Model 2 paints by priority, a Z-buffer makes them flicker): every upper
    layer is moved LAYER_STEP x layer off the surface - lying faces upwards, upright faces as two copies, one on each side
    (1995 walls are drawn without culling, so the winding does not tell the visible side)."""
    import layers
    lay, nup, nst = layers.layer_of(faces, 'plane'); out = []
    for fc, L in zip(faces, lay):
        if L == 0: out.append(fc); continue
        P = np.array(fc[2], float); n = np.cross(P[1] - P[0], P[2] - P[0]); n /= np.linalg.norm(n)
        if abs(n[1]) > 0.5:
            if n[1] < 0: n = -n
            out.append((fc[0], fc[1], [tuple(q + LAYER_STEP * far_scale(P) * L * n) for q in P], fc[3]))
        else:
            for sg in (1.0, -1.0): out.append((fc[0], fc[1], [tuple(q + sg * LAYER_STEP * far_scale(P) * L * n) for q in P], fc[3]))
    log('       coplanar layers (1995 priority painting): %d polygons lie on another polygon of the same plane (%d polygons in stacks, highest layer %d): moved %.1f cm per layer off the surface' % (nup, nst, int(lay.max()) if len(lay) else 0, 100 * LAYER_STEP))
    return out

def split_at_road(rd, faces):
    """variable-width road: every LYING classic face that reaches into the SR3 road and lies at road height is cut into
    pieces of at most 1 m; pieces whose centre is on the road go to DROPPED (they come back as decals draped on the SR3
    road, classic_road), the others stay scenery. Upright faces are never touched."""
    side = road_side(rd); hf = road_height(rd); keep = []; DROPPED.clear(); ncut = 0
    allv = np.array([p for fc in faces for p in fc[2]]); idx, c, lo, hi = side(allv); dh = allv[:, 1] - hf(allv); k = 0
    cand = []
    for fc in faces:
        m = len(fc[2]); sl_ = slice(k, k + m); k += m
        P = np.array(fc[2]); nrm = np.cross(P[1] - P[0], P[2] - P[0]); ln = np.linalg.norm(nrm)
        lying = ln > 0 and abs(nrm[1] / ln) > 0.5
        if not lying or not (np.abs(dh[sl_]) < 1.2).all(): keep.append(fc); continue
        cc = c[sl_]; inside = (cc > lo[sl_]) & (cc < hi[sl_])
        if not inside.any():
            ce = P.mean(0)[None, :]; i2, c2, l2, h2 = side(ce)
            if not (l2[0] < c2[0] < h2[0]): keep.append(fc); continue
        cand.append(fc)
    import layers
    lay, nup, nst = layers.layer_of(cand, 'plan') if cand else ([], 0, 0)
    for fc, L in zip(cand, lay):
        fc = (fc[0], '%s#L%d' % (fc[1], L), fc[2], fc[3])                    # the layer travels with the pieces (classic_road lifts by it)
        pcs = split_faces([fc], 1.0); ce = np.array([np.mean(q[2], axis=0) for q in pcs]); d2 = np.abs(ce[:, 1] - hf(ce)); ncut += 1
        co = np.array([p_ for q in pcs for p_ in q[2]] ); i2, c2, l2, h2 = side(np.vstack([co, ce])); on = (c2 > l2) & (c2 < h2); nq = len(pcs)
        touch = on[:4 * nq].reshape(nq, 4).any(1) | on[4 * nq:]            # a piece that touches the road becomes a decal (no sliver of the SR3 texture at the edge)
        for q, t_, d_ in zip(pcs, touch, d2):
            (DROPPED if (t_ and d_ < 0.6) else keep).append(q)
    log('       layers on the road (seen from above): %d of the %d road faces lie on another one (highest layer %d); decal lift 3 cm + 2 cm per layer' % (nup, len(cand), int(max(lay)) if len(lay) else 0))
    log('       classic visual model: %d faces; %d lying faces reach into the road and were cut to 1 m pieces: %d pieces on the road (replaced by the SR3 road, returned as decals), %d faces and pieces kept, %d materials' %
        (len(faces), ncut, len(DROPPED), len(keep), len({f[0] for f in keep})))
    return keep

OVERLAY_LIFT = 0.04
def dedupe_overlays(faces):
    """The 1995 model draws many polygons twice on the same corners: (a) a cut-out board listed once per side (same
    tile): the second copy is dropped, the SR3 cut-out material is two-sided; (b) a cut-out OVERLAY on an opaque face
    (ivy on rock, grass fringe on a bank): the overlay is moved OVERLAY_LIFT metres off the base face along the base
    face's front normal, because two coplanar faces z-fight in SR3 (and Blender's OBJ importer silently drops one)."""
    seen = {}; out = []; ndrop = 0; nlift = 0
    def key(P): return frozenset((round(p[0], 2), round(p[1], 2), round(p[2], 2)) for p in P)
    def normal(P):
        P = np.array(P); n = np.cross(P[1] - P[0], P[2] - P[0]); l = np.linalg.norm(n); return n / l if l > 1e-9 else np.zeros(3)
    def lifted(fc, n, sg=1.0): return (fc[0], fc[1], [tuple(np.array(p) + sg * OVERLAY_LIFT * far_scale(fc[2]) * n) for p in fc[2]], fc[3])
    for fc in faces:
        k = key(fc[2]); cut = str(fc[0]).endswith('_t')
        if k in seen:
            j = seen[k]; other = out[j]; ocut = str(other[0]).endswith('_t')
            if other[0] == fc[0] and cut: ndrop += 1; continue
            # the overlay goes on BOTH sides of its base face: 1995 walls are drawn without culling, so the base winding does not say which side is seen
            if cut and not ocut: out.append(lifted(fc, normal(other[2]))); out.append(lifted(fc, normal(other[2]), -1.0)); nlift += 1; continue
            if ocut and not cut: out[j] = lifted(other, normal(fc[2])); out.append(lifted(other, normal(fc[2]), -1.0)); seen[k] = len(out); out.append(fc); nlift += 1; continue
        else: seen[k] = len(out)
        out.append(fc)
    log('       1995 double polygons: %d second sides of cut-out boards dropped, %d cut-out overlays set %.0f cm off BOTH sides of their base face' % (ndrop, nlift, 100 * OVERLAY_LIFT))
    return out

def uv_split(faces, maxspan=1.999):
    """faces whose uv span exceeds what the u16 uv (0..2 repeats) can hold are cut along their edges until every piece fits"""
    out = []; n = 0
    for mat, sec, P, UV in faces:
        u = np.array(UV, float); u[:, 1] = 1.0 - u[:, 1]; sp = np.ptp(u, axis=0); lo = u.min(0); top = (lo - np.floor(lo + 1e-6) + sp).max()
        if top <= maxspan: out.append((mat, sec, P, UV)); continue
        k = int(np.ceil(sp.max() / 0.999)); n += 1
        if len(P) == 3: P = list(P) + [P[2]]; UV = list(UV) + [UV[2]]
        Pa = np.array(P[:4], float); Ua = np.array(UV[:4], float)
        def pt(A, a, b): return (A[0] * (1 - a) + A[1] * a) * (1 - b) + (A[3] * (1 - a) + A[2] * a) * b
        for i in range(k):
            for j in range(k):
                c = [(i / k, j / k), ((i + 1) / k, j / k), ((i + 1) / k, (j + 1) / k), (i / k, (j + 1) / k)]
                out.append((mat, sec, [tuple(pt(Pa, a, b)) for a, b in c], [tuple(pt(Ua, a, b)) for a, b in c]))
    def fits(UV):
        u = np.array(UV, float); u[:, 1] = 1.0 - u[:, 1]; lo = u.min(0); return (lo - np.floor(lo + 1e-6) + np.ptp(u, axis=0)).max() <= maxspan
    done = []; todo = []
    for fc in out: (done if fits(fc[3]) else todo).append(fc)
    todo = [(m_, s_, [P_[i] for i in t_], [UV_[i] for i in t_]) for m_, s_, P_, UV_ in todo for t_ in (((0, 1, 2), (0, 2, 3)) if len(P_) >= 4 else ((0, 1, 2),))]
    for depth in range(12):
        nxt = []
        for m_, s_, P_, UV_ in todo:
            if fits(UV_): done.append((m_, s_, P_, UV_)); continue
            P3 = np.array(P_, float); U3 = np.array(UV_, float); k_ = int(np.argmax([np.abs(U3[(i + 1) % 3] - U3[i]).max() for i in range(3)])); a_, b_, c_ = k_, (k_ + 1) % 3, (k_ + 2) % 3
            pm = tuple((P3[a_] + P3[b_]) / 2); um = tuple((U3[a_] + U3[b_]) / 2)
            nxt += [(m_, s_, [P_[a_], pm, P_[c_]], [UV_[a_], um, UV_[c_]]), (m_, s_, [pm, P_[b_], P_[c_]], [um, UV_[b_], UV_[c_]])]
        todo = nxt
        if not todo: break
    return done + todo, n

GROUND_AT = None                                                       # f(x array, z array, y array) -> height of the highest lying surface at or below y + 1 (very low where there is none); set by import_classic for the lighting experiment
LIGHT_ENV = (0.64, 1.08, (0.0, 0.94, -0.34))                           # (ambient, sun, direction TOWARDS the sun) of the slot's lighting, means of the three channels: set by import_classic
GATE_SHARP = 4
ROAD_CUT = False; ROAD_RECIPE = False; ROAD_TILES = set()             # the car's shadow came out in bands on the verbatim road (RAW3, in game). Two tests: road_cut = the road polygons cut in place to 1 m ; road_recipe = their materials get SEGA's shadow-receiving recipe (shadow_recv, as the draped road had)
ROAD_UNDER = -0.02                                                     # verbatim road: where the SR3 road lies against the 1995 polygons (course setting road_under; 0 when the launcher stops the game drawing it)
ROAD_VERBATIM = False                                                  # EXPERIMENT 'RAW2' (course setting road_verbatim; user, 2026-10-09: "all 1995 polys verbatim (geometry and texture) but drivable"):
                                                                       # the 1995 road polygons are NOT cut out and re-laid on the SR3 road. They stay as scenery, corner to corner with the walls and rock they
                                                                       # were modelled against; the SR3 road carries the driving only: 2 cm under them, its layers fully transparent. Every scenery material
                                                                       # gets the two shadow-receive switches, so that the cars' shadows have something to fall on.
LM_ROAD_GREY = True                                                     # the road's light map without colour (see add_scenery, the pages)
LM_COLLECT = None; LM_TABLE = None; LM_LAST = None                    # real light maps (lightmap1995.py): the list polygons are collected in / the table they are read from / the pages of the mesh just made
OWN_SHADER = set()                                                    # tiles whose materials select a technique nothing else uses (see add_scenery), so that the launcher can replace its pixel shader for them alone
BUMP = {}; BUMP_GREEN = False; BUMP_GAIN = 1.0; BUMP_TRUE = False; KEEP_T = None          # facade relief test (bump1995.py): tile -> strength ; the vertices of the mesh just made that keep their own tangent
LM_TEST = False                                                        # EXPERIMENT (course setting 'lm_test'): what does the game do with the LIGHT MAP of the imported materials? see add_scenery
SHARE = True                                                           # corners shared between the polygons of a mesh (share_corners)
FLAT_LIT = set()                                                       # material names lit as flat ground whatever they face (signs)
SMOOTH_N = {}                                                          # corner (x, y, z rounded to cm) -> unit normal, natural ground only (import_classic fills it when LIGHT_K > 0)
def oriented_normals(quads):
    """unit normal per polygon, turned to the side that is SEEN: lying faces look up, upright ones face the nearest road point
    (the winding of 1995 polygons does not say which side shows)"""
    n = np.zeros((len(quads), 3)); c = np.zeros((len(quads), 3))
    for k, P in enumerate(quads):
        A = np.asarray(P, float); B = np.roll(A, -1, axis=0); n[k] = ((A[:, [1, 2, 0]] - B[:, [1, 2, 0]]) * (A[:, [2, 0, 1]] + B[:, [2, 0, 1]])).sum(0); c[k] = A.mean(0)
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    lying = np.abs(n[:, 1]) > 0.3; n[lying & (n[:, 1] < 0)] *= -1.0
    up_ = np.nonzero(~lying)[0]
    if GROUND_AT is not None and len(up_):
        # Which side of an upright face is SEEN: the side where someone can stand at its foot. On each side, 2 m out, the highest ground
        # that is not above the face's own lowest edge (+1 m) is looked up; the side where that ground is HIGHER is the open one.
        #   house wall: street at its foot, the hillside of the hand fill far below inside            -> the street side
        #   cliff beside the road, hill behind it at its TOP (above the foot: does not count)          -> the road side
        #   rock rising from the hillside, hollow inside                                             -> outwards
        # Earlier rules ('the lower side', then 'lower by 2 m') turned house walls and the church front inwards wherever the fill lay
        # lower inside them (builds Z8 / Z9: sunny houses dark, the church front lit in three different ways; user, 2026-10-08).
        h = n[up_][:, [0, 2]]; h /= np.maximum(np.linalg.norm(h, axis=1), 1e-9)[:, None]; base = np.array([np.asarray(quads[k], float)[:, 1].min() for k in up_])
        ya = GROUND_AT(c[up_][:, 0] + 2.0 * h[:, 0], c[up_][:, 2] + 2.0 * h[:, 1], base); yb = GROUND_AT(c[up_][:, 0] - 2.0 * h[:, 0], c[up_][:, 2] - 2.0 * h[:, 1], base)
        ha = ya > -900.0; hb = yb > -900.0
        flip = hb & (~ha | (yb > ya + 0.3)); same = (~ha & ~hb) | (ha & hb & (np.abs(ya - yb) <= 0.3)); n[up_[flip]] *= -1.0; up_ = up_[same]      # nothing either side, or level: the road side
    for a0 in range(0, len(up_), 2000):
        ix = up_[a0:a0 + 2000]; d2 = ((c[ix][:, None, [0, 2]] - ROADPTS[None, :, :]) ** 2).sum(2); to = ROADPTS[d2.argmin(1)] - c[ix][:, [0, 2]]
        flip = (n[ix, 0] * to[:, 0] + n[ix, 2] * to[:, 1]) < 0; n[ix[flip]] *= -1.0
    return n
def smooth_normals(faces):
    """-> {corner: unit normal}: the area-weighted mean of the oriented normals of the given faces round each corner"""
    quads = [fc[2] for fc in faces]; n = oriented_normals(quads); acc = {}
    for k, P in enumerate(quads):
        A = np.asarray(P, float); B = np.roll(A, -1, axis=0); ar = float(np.linalg.norm(((A[:, [1, 2, 0]] - B[:, [1, 2, 0]]) * (A[:, [2, 0, 1]] + B[:, [2, 0, 1]])).sum(0)))
        for p in np.round(A, 2):
            key = (p[0], p[1], p[2]); acc[key] = acc.get(key, 0.0) + n[k] * ar
    return {k: v / max(float(np.linalg.norm(v)), 1e-12) for k, v in acc.items()}

BAKE_COLLECT = None; BAKE_TABLE = None; BAKE_MODE = 'shadows'; BAKE_STRENGTH = 1.0; BAKE_SHADE = 0.42      # baked light (bake1995.py): the list the lit vertices are collected in / the table they are read from
def _encode_light(nv_, I_):
    """the normal that makes the game show brightness I_ (1 = flat ground in the sun) under the slot's light: ambient + sun x N.L"""
    amb_, sun_, sv_ = LIGHT_ENV; sv_ = np.asarray(sv_, float) / np.linalg.norm(sv_)
    ground_ = amb_ + sun_ * max(float(sv_[1]), 0.0); cosT = np.clip((I_ * ground_ - amb_) / max(sun_, 1e-6), -1.0, 1.0)
    e_ = nv_ - (nv_ @ sv_)[:, None] * sv_; le_ = np.linalg.norm(e_, axis=1); alt_ = np.cross(sv_, [1.0, 0.0, 0.0]); alt_ /= np.linalg.norm(alt_)
    e_ = np.where((le_ > 1e-6)[:, None], e_ / np.maximum(le_, 1e-9)[:, None], alt_)
    return (cosT[:, None] * sv_ + np.sqrt(1.0 - cosT ** 2)[:, None] * e_).astype(np.float32)

def bake_light(v, nv_, I_, flat, unsure):
    """BAKED LIGHT (bake1995.py). I_ = the brightness the polygon rule gives every vertex. Collecting: the vertices are noted for the rays.
    Reading: the rays' answer changes I_ -
      'shadows'  where something stands between the vertex and the sun it drops to BAKE_SHADE (about what the game's own moving shadows leave:
                 ambient only = 0.39), by the share of the sun's disc that is hidden. Polygons turned from the sun keep the rule's shade.
      'rt'       the same, then dimmed where little sky is seen (to 0.45 with none) and raised by the light that comes back from sunlit things.
    Cut-out boards and signs (flat) stay as they are."""
    import bake1995
    P = v['p'][:, :3]; sel = ~np.asarray(flat, bool)
    if BAKE_COLLECT is not None: BAKE_COLLECT.append((P[sel].copy(), nv_[sel].astype(np.float32), np.asarray(unsure, bool)[sel].copy()))
    if BAKE_TABLE is None or not sel.any(): return I_
    L = np.ones((len(P), 3)); L[:, 2] = 0.0; L[sel] = bake1995.lookup(BAKE_TABLE, P[sel], nv_[sel]); V, A, B = L[:, 0], L[:, 1], L[:, 2]
    sv_ = np.asarray(LIGHT_ENV[2], float); sv_ = sv_ / np.linalg.norm(sv_); away = ((nv_ @ sv_) <= 0.02) & ~np.asarray(unsure, bool)
    D = np.where(away | (I_ <= BAKE_SHADE), I_, BAKE_SHADE + (I_ - BAKE_SHADE) * V)
    if BAKE_MODE == 'rt': D = np.clip(D + BAKE_STRENGTH * (D * (0.45 + 0.55 * A) + 0.6 * B - D), 0.12, 1.04)      # BAKE_STRENGTH (course setting 'bake_strength'): 1 = as first built, 1.25 = everything the sky and the bounce do, a quarter stronger
    return np.where(sel, D, I_)

def bump_of(key):
    """relief strength of a material (course settings 'bump_tiles' / 'bump_classes'), 0 for none; a composed tile counts as the tile under it"""
    if not BUMP: return 0.0
    k = str(key).split('|')[0]
    if k in BUMP: return float(BUMP[k])
    try:
        import overlay_bake as _ob; return float(BUMP.get(_ob.ORIGIN.get(k, k), 0.0))
    except Exception: return 0.0

def relief_tangent(nf, nt, tt, sv):
    """RELIEF WITHOUT GIVING UP THE BRIGHTNESS RULE. The first test (FACADE-TEST) lit the relief walls by the game's sun on their true normal: the
    relief read well, but every panel took the brightness of its own exact angle (neighbouring panels of one wall differed) and walls turned
    from the sun went dark (user's screenshots, 2026-10-08). Here the vertex keeps the normal that gives the RULE's brightness (nf), and the
    tangent is turned so that a slope of the normal map changes the light the way it would on the true wall:
        the game shades a texel with  N = nf + dx T + dy B ,  B = nf x T ,  light = sun x N.L
        on the true wall the change would be  dx (Tt.L) + dy (Bt.L) ;  T is chosen so that  (T.L, B.L)  points the same way as  (Tt.L, Bt.L).
    (Its length cannot be matched as well - T.L^2 + B.L^2 = 1 - (nf.L)^2 whatever T is - so relief is fainter on the walls the rule makes
    brightest, by about a third; the map's strength makes up for it.)   nf, nt, tt: (n, 3) rule normal, true normal, true tangent along u."""
    L = np.asarray(sv, float) / np.linalg.norm(sv); c0 = nf @ L; s = np.sqrt(np.maximum(1.0 - c0 ** 2, 0.0)); e = nf - c0[:, None] * L; le = np.linalg.norm(e, axis=1)
    alt = np.cross(L, [1.0, 0.0, 0.0]); alt /= np.linalg.norm(alt); e = np.where((le > 1e-6)[:, None], e / np.maximum(le, 1e-12)[:, None], alt); g = np.cross(L, e); u2 = -s[:, None] * L + c0[:, None] * e
    tt = tt - (tt * nt).sum(1)[:, None] * nt; lt = np.linalg.norm(tt, axis=1); tt = np.where((lt > 1e-9)[:, None], tt / np.maximum(lt, 1e-12)[:, None], g); bt = np.cross(nt, tt)
    a = tt @ L; b = bt @ L; r = np.hypot(a, b); ok = r > 1e-4; ca = np.where(ok, b / np.maximum(r, 1e-12), 1.0); sa = np.where(ok, -a / np.maximum(r, 1e-12), 0.0)
    T = ca[:, None] * g + sa[:, None] * u2; return (T / np.maximum(np.linalg.norm(T, axis=1), 1e-12)[:, None]).astype(np.float32)

def faces_to_mesh(faces, uv_mode, up_normals=False):
    """-> (verts array, nquads). uv_mode 'tile' = classic uv (shifted into 0..2 per face), 'box' = 0..1 per face"""
    quads = []; uvs = []; clamp = 0
    for mat, sec, P, UV in faces:
        if len(P) == 3: P = P + [P[2]]; UV = UV + [UV[2]]
        quads.append(P[:4]); u = np.array(UV[:4], float)
        if uv_mode == 'given': pass                                   # already in repeats, 0..2
        elif uv_mode == 'tile':
            u[:, 1] = 1.0 - u[:, 1]                                   # OBJ v up -> texture rows down
            u -= np.floor(u.min(0) + 1e-6)
            if u.max() > 1.999: clamp += 1; u = np.clip(u, 0, 1.999)
        else: u = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
        # The mesh stores uv as SIGNED 16-bit, -1..+1 (SEGA's own meshes: 95% of the values are 0..0x7FFF, the rest small
        # negatives). Written as 0..2 unsigned, every face that crossed 1.0 had some corners read as negative: the tile ran
        # backwards between them (boards mirrored / upside-down, walls smeared - first in-game runs). A face keeps its
        # corners together: an axis that reaches 1.0 is moved down by one repeat (textures wrap, the picture is the same).
        for ax in (0, 1):
            if u[:, ax].max() > 1.00002: u[:, ax] -= 1.0              # exactly 1.0 stays (stored as 0x7FFF)
        uvs.append(u)
    v = meshgen.make_verts_safe(quads)
    globals()['KEEP_T'] = None; bm_ = np.array([bump_of(fc[0]) > 0 for fc in faces], bool) if (BUMP and up_normals) else None; gn_ = v['n'].copy() if (bm_ is not None and bm_.any()) else None
    if up_normals and LIGHT_K > 0:
        # SHADING BY THE SUN (course JSON 'light_contrast' K, 0 = flat .. 1 = strongest). The importer decides how bright every polygon is, by one
        # rule, and hands the game a normal that gives exactly that brightness under the slot's sun (the game lights with ambient + sun x N.L):
        #     d = polygon's direction . a "design sun" (the real sun's compass direction, 45 degrees up)
        #     brightness = floor + (1 - floor) x clamp((d + 0.2) / 0.907)      floor = 1 - 0.6 K      (1 = as bright as flat ground)
        #   -> flat ground and walls that face the sun: 1 ; walls side-on to it: a little above the floor ; walls facing away: the floor.
        # Why not the plain physical N.L of the 1995 sun (70 degrees up): a wall facing that sun squarely gets cos 70 = a third of what the
        # ground gets, so every wall was dim and every polygon turned from the sun nearly black (build Z13L75: "these faces are way too dark
        # for something exposed to direct sunlight ... wtf are these dark patches", user 2026-10-08). The 1995 picture has lit walls as
        # bright as the ground and shaded ones at about 0.55.
        # A polygon whose seen side is NOT certain (lightside.py, material key '|4') takes the brighter of its two sides: never a dark patch
        # by mistake; the price is that a real sheet seen from its shaded side is shown lit.
        nv_ = v['n'].astype(np.float64).copy()
        if SMOOTH_N:                                                 # natural ground: the mean direction of the faces round a corner, taken on this side
            P_ = np.round(v['p'][:, :3].astype(np.float64), 2)
            for k_ in range(len(P_)):
                q_ = SMOOTH_N.get((P_[k_, 0], P_[k_, 1], P_[k_, 2]))
                if q_ is not None: nv_[k_] = q_ if float(q_ @ nv_[k_]) >= 0.0 else -q_
        amb_, sun_, sv_ = LIGHT_ENV; sv_ = np.asarray(sv_, float) / np.linalg.norm(sv_); sh_ = np.array([sv_[0], 0.0, sv_[2]]); lh_ = float(np.linalg.norm(sh_))
        sd_ = (sh_ / lh_ * 0.7071 + np.array([0.0, 0.7071, 0.0])) if lh_ > 1e-6 else np.array([0.0, 1.0, 0.0]); floor_ = 1.0 - 0.6 * LIGHT_K
        bright = lambda n_: floor_ + (1.0 - floor_) * np.clip((n_ @ sd_ + 0.2) / 0.907, 0.0, 1.0)
        I_ = bright(nv_); unsure = np.repeat(np.array([str(fc[0]).endswith('|4') for fc in faces], bool), 4); I_ = np.where(unsure, np.maximum(I_, bright(-nv_)), I_)
        flat = np.repeat(np.array([str(fc[0]).split('|')[0].endswith('_t') or str(fc[0]).split('|')[0] in FLAT_LIT for fc in faces], bool), 4); I_ = np.where(flat, 1.0, I_)      # cut-out boards and signs: as flat ground
        if BAKE_COLLECT is not None or BAKE_TABLE is not None: I_ = bake_light(v, nv_, I_, flat, unsure)
        if LM_COLLECT is not None: LM_COLLECT.append((v['p'][:, :3].reshape(-1, 4, 3).astype(np.float64), nv_.reshape(-1, 4, 3).mean(1), I_.reshape(-1, 4).astype(np.float32), np.asarray(flat, bool).reshape(-1, 4)[:, 0].copy(), np.asarray(unsure, bool).reshape(-1, 4)[:, 0].copy()))
        if LM_TABLE is not None:
            import lightmap1995; fl_ = np.asarray(flat, bool).reshape(-1, 4)[:, 0]; m0_ = LM_TABLE['miss'][0]; pg_, uv1_ = lightmap1995.lookup(LM_TABLE, v['p'][:, :3].reshape(-1, 4, 3).astype(np.float64)); LM_TABLE['miss'][0] = m0_ + int((~fl_ & (pg_ == 0)).sum()); pg_ = np.where(fl_, 0, pg_)
            v['uv1'] = np.where(np.repeat(fl_, 4)[:, None], v['uv1'], uv1_); globals()['LM_LAST'] = pg_
        ground_ = amb_ + sun_ * max(float(sv_[1]), 0.0); cosT = np.clip((I_ * ground_ - amb_) / max(sun_, 1e-6), -1.0, 1.0)      # the N.L that gives this brightness
        e_ = nv_ - (nv_ @ sv_)[:, None] * sv_; le_ = np.linalg.norm(e_, axis=1); alt_ = np.cross(sv_, [1.0, 0.0, 0.0]); alt_ /= np.linalg.norm(alt_)
        e_ = np.where((le_ > 1e-6)[:, None], e_ / np.maximum(le_, 1e-9)[:, None], alt_)
        v['n'] = (cosT[:, None] * sv_ + np.sqrt(1.0 - cosT ** 2)[:, None] * e_).astype(np.float32)
    elif up_normals: v['n'] = (0.0, 1.0, 0.0)                         # classic faces are lit like flat ground: 1995 textures carry their own shading, and crossed tree boards must not shade differently
    if LM_TEST and len(v):                                            # (see _lm_test_texture) the square of the map the polygon's middle stands in picks one of the four texels
        c_ = v['p'][:, :3].reshape(-1, 4, 3).mean(1); q_ = (np.floor(c_[:, 0] / 16.0).astype(np.int64) + 2 * np.floor(c_[:, 2] / 16.0).astype(np.int64)) % 4
        v['uv1'] = np.repeat(np.stack([np.where(q_ % 2 == 0, 8192, 24576), np.where(q_ < 2, 8192, 24576)], 1).astype(np.uint16), 4, axis=0)
    if not up_normals and uv_mode == 'tile' and LIGHT_K > 0 and (BAKE_COLLECT is not None or BAKE_TABLE is not None):      # the ROAD (its 1995 tarmac pieces keep their own normals): what the game shows now is
        amb_, sun_, sv_ = LIGHT_ENV; sv_ = np.asarray(sv_, float) / np.linalg.norm(sv_); nr_ = v['n'].astype(np.float64)                 # ambient + sun x N.L ; the baked light changes that brightness
        Ir_ = (amb_ + sun_ * np.clip(nr_ @ sv_, 0.0, 1.0)) / (amb_ + sun_ * max(float(sv_[1]), 0.0)); I2_ = bake_light(v, nr_, Ir_, np.zeros(len(v), bool), np.zeros(len(v), bool))
        if BAKE_TABLE is not None: v['n'] = _encode_light(nr_, I2_)
    if not up_normals and uv_mode == 'tile' and LIGHT_K > 0 and (LM_COLLECT is not None or LM_TABLE is not None) and len(v):      # the ROAD on the light maps too (LIGHTMAP-RT had none: "the road has no shadows", user 2026-10-08)
        amb_, sun_, sv_ = LIGHT_ENV; sv_ = np.asarray(sv_, float) / np.linalg.norm(sv_); nr_ = v['n'].astype(np.float64); Ir_ = (amb_ + sun_ * np.clip(nr_ @ sv_, 0.0, 1.0)) / (amb_ + sun_ * max(float(sv_[1]), 0.0))
        if LM_COLLECT is not None: LM_COLLECT.append((v['p'][:, :3].reshape(-1, 4, 3).astype(np.float64), nr_.reshape(-1, 4, 3).mean(1), Ir_.reshape(-1, 4).astype(np.float32), np.zeros(len(v) // 4, bool), np.zeros(len(v) // 4, bool)))
        if LM_TABLE is not None:
            import lightmap1995; pg_, uv1_ = lightmap1995.lookup(LM_TABLE, v['p'][:, :3].reshape(-1, 4, 3).astype(np.float64)); v['uv1'] = uv1_; globals()['LM_LAST'] = pg_
            if LM_ROAD_GREY: LM_TABLE.setdefault('grey', set()).update(i_ for i_ in (LM_TABLE['idx'].get(k_.tobytes(), -1) for k_ in lightmap1995.key(v['p'][:, :3].reshape(-1, 4, 3).astype(np.float64))) if i_ >= 0)      # these polygons are ROAD: remembered for the pages
    if gn_ is not None:                                               # RELIEF TEST: these polygons are lit by the game's sun on their TRUE normal (the normal map bends it), with a tangent along the picture's u
        import bump1995; m4_ = np.repeat(bm_, 4); tg_ = np.repeat(bump1995.tangents(np.asarray(quads, np.float64), np.asarray(uvs, np.float64)), 4, axis=0)
        if BUMP_TRUE or LIGHT_K <= 0: v['n'] = np.where(m4_[:, None], gn_, v['n']); v['t'] = np.where(m4_[:, None], tg_.astype(np.float32), v['t'])      # (the first test: true normal, tangent along u)
        else: v['t'] = np.where(m4_[:, None], relief_tangent(v['n'].astype(np.float64), gn_.astype(np.float64), tg_, LIGHT_ENV[2]), v['t'])               # the rule's brightness stays; see relief_tangent
        globals()['KEEP_T'] = m4_
    for k, u in enumerate(uvs): v['uv0'][4 * k:4 * k + 4] = np.clip(np.round(u * 32768), -32768, 32767).astype(np.int16).view(np.uint16)
    return v, len(quads), clamp

def dxt1_grey(img, hole=None):
    """uint8 grey image (h, w multiple of 4) -> DXT1 blocks. hole = bool mask of transparent texels: blocks containing
    holes use the 3-colour + transparent mode (c0 <= c1, index 3 = transparent)."""
    h, w = img.shape; b = img.reshape(h // 4, 4, w // 4, 4).transpose(0, 2, 1, 3).reshape(-1, 16).astype(np.int32)
    if hole is not None and hole.any():
        m = hole.reshape(h // 4, 4, w // 4, 4).transpose(0, 2, 1, 3).reshape(-1, 16)
        big = np.where(m, -1, b); lo = np.where(m, 999, b).min(1); hi = big.max(1); lo = np.where(lo == 999, 0, lo); hi = np.where(hi < 0, 0, hi)
        def c565(g): return ((g >> 3) << 11) | ((g >> 2) << 5) | (g >> 3)
        c0 = c565(lo); c1 = c565(hi)                                  # c0 <= c1 : c0, c1, mid, transparent
        pal = np.stack([lo, hi, (lo + hi) // 2], 1)
        ix = np.abs(b[:, :, None] - pal[:, None, :]).argmin(2); ix[m] = 3
        anyh = m.any(1)
        # blocks without holes are encoded in the same 3-colour mode (still valid)
        bits = (ix.astype(np.uint64) << (2 * np.arange(16, dtype=np.uint64))).sum(1).astype(np.uint32)
        out = np.zeros(len(b), np.dtype([('c0', '<u2'), ('c1', '<u2'), ('ix', '<u4')])); out['c0'] = c0; out['c1'] = c1; out['ix'] = bits
        return out.tobytes()
    lo = b.min(1); hi = b.max(1)
    def c565(g): return ((g >> 3) << 11) | ((g >> 2) << 5) | (g >> 3)
    c0 = c565(hi); c1 = c565(lo); same = c0 == c1
    # palette: c0, c1, 2/3 c0 + 1/3 c1, 1/3 c0 + 2/3 c1  (c0 > c1 mode)
    pal = np.stack([hi, lo, (2 * hi + lo) // 3, (hi + 2 * lo) // 3], 1)
    ix = np.abs(b[:, :, None] - pal[:, None, :]).argmin(2); ix[same] = 0
    bits = (ix << (2 * np.arange(16))).sum(1).astype(np.uint32)
    out = np.zeros(len(b), np.dtype([('c0', '<u2'), ('c1', '<u2'), ('ix', '<u4')])); out['c0'] = c0; out['c1'] = c1; out['ix'] = bits
    return out.tobytes()

def dxt1_rgb(img, hole=None):
    """RGB uint8 image (h, w multiple of 4, 3) -> DXT1 blocks; endpoints = brightest/darkest texel of the block.
    hole: transparent texels -> 3-colour + transparent mode."""
    h, w, _ = img.shape; b = img.reshape(h // 4, 4, w // 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3).astype(np.int32)
    lum = b.sum(2); n = len(b); ar = np.arange(n)
    m = hole.reshape(h // 4, 4, w // 4, 4).transpose(0, 2, 1, 3).reshape(-1, 16) if hole is not None else np.zeros((n, 16), bool)
    hi = b[ar, np.where(m, -1, lum).argmax(1)]; lo = b[ar, np.where(m, 99999, lum).argmin(1)]
    def c565(c): return ((c[:, 0] >> 3) << 11) | ((c[:, 1] >> 2) << 5) | (c[:, 2] >> 3)
    def un565(v): return np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31], 1)
    ch = c565(hi); cl = c565(lo); anyh = m.any(1)
    # opaque blocks: c0 > c1 (4 colours); blocks with holes: c0 <= c1 (3 colours + transparent)
    c0 = np.where(anyh, np.minimum(ch, cl), np.maximum(ch, cl)); c1 = np.where(anyh, np.maximum(ch, cl), np.minimum(ch, cl))
    same = (c0 == c1) & ~anyh
    c0 = np.where(same & (c0 < 0xffff), c0 + 1, c0); c1 = np.where(same & (c0 == 0xffff) & (c1 == 0xffff), 0xfffe, c1)
    p0 = un565(c0); p1 = un565(c1)
    p2 = np.where(anyh[:, None], (p0 + p1) // 2, (2 * p0 + p1) // 3); p3 = np.where(anyh[:, None], 0, (p0 + 2 * p1) // 3)
    pal = np.stack([p0, p1, p2, p3], 1)                                # n, 4, 3
    dist = ((b[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(3)       # n, 16, 4
    dist[:, :, 3] = np.where(anyh[:, None], 10 ** 9, dist[:, :, 3])
    ix = dist.argmin(2); ix[m] = 3
    bits = (ix.astype(np.uint64) << (2 * np.arange(16, dtype=np.uint64))).sum(1).astype(np.uint32)
    out = np.zeros(n, np.dtype([('c0', '<u2'), ('c1', '<u2'), ('ix', '<u4')])); out['c0'] = c0; out['c1'] = c1; out['ix'] = bits
    return out.tobytes()

VIVID_CFG = (0.95, 1.0, 1.7)                                                # set from the course JSON by import_classic
VIVID = None                                                           # (gain, saturation) applied to classic tiles while add_scenery builds them
def vivid(rgb):
    """The 1995 game shows its textures unlit and bright; inside SR3's lit, tone-mapped picture the same texels looked
    dull (in-game run 2026-10-07). Classic tiles are written brighter and more saturated: course JSON 'vivid': [gain, saturation]."""
    if not VIVID: return rgb
    g, sat = VIVID[:2]; x = rgb.astype(np.float32)
    if len(VIVID) > 2: x = 255.0 * (x / 255.0) ** VIVID[2]             # gamma: Model 2 emulator shots (2026-10-07) show the mid tones far darker than the decoded tiles while white stays white; 1.7 matches rock, sea and sky
    lum = x.mean(-1, keepdims=True)
    y = np.maximum((lum + (x - lum) * sat) * g, 0); top = y.max(-1, keepdims=True)
    y = y * np.where(top > 255, 255.0 / np.maximum(top, 1), 1.0)
    if SCENE_GAIN is not None and not _NO_GAIN[0]: y = y * np.asarray(SCENE_GAIN, np.float32)      # the slot's lighting changed (course JSON 'lighting_from'): the tiles are scaled so the LIT scenery looks as it did
    return np.clip(y, 0, 255).astype(np.uint8)

def make_texture_dxt5(tpl5, new_id, rgb, hole):
    """kind 4 DXT5 chunk with a 1-bit alpha channel (255 / 0), full mip chain; header cloned from a DXT5 texture"""
    rgb = vivid(rgb); h, w = rgb.shape[:2]; d = bytearray(tpl5.data[:48 + 124]); mips = []; g = rgb.astype(np.float32); a = np.where(hole, 0.0, 255.0).astype(np.float32)
    while True:
        hh, ww = g.shape[:2]; pc = np.zeros((max(4, hh), max(4, ww), 3), np.float32); pa = np.zeros((max(4, hh), max(4, ww)), np.float32); pc[:hh, :ww] = g; pa[:hh, :ww] = a
        if hh < 4: pc[hh:] = pc[hh - 1:hh]; pa[hh:] = pa[hh - 1:hh]
        if ww < 4: pc[:, ww:] = pc[:, ww - 1:ww]; pa[:, ww:] = pa[:, ww - 1:ww]
        col = np.frombuffer(dxt1_rgb(np.clip(pc, 0, 255).astype(np.uint8)), np.uint8).reshape(-1, 8)
        H, W = pa.shape; ab = (pa.reshape(H // 4, 4, W // 4, 4).transpose(0, 2, 1, 3).reshape(-1, 16) < 128)        # True = transparent
        idx = (ab.astype(np.uint64) << (3 * np.arange(16, dtype=np.uint64))).sum(1)                                # index 1 = alpha1 = 0
        blk = np.zeros((len(col), 16), np.uint8); blk[:, 0] = 255; blk[:, 1] = 0
        for k in range(6): blk[:, 2 + k] = ((idx >> np.uint64(8 * k)) & np.uint64(255)).astype(np.uint8)
        blk[:, 8:] = col; mips.append(blk.tobytes())
        if hh == 1 and ww == 1: break
        if hh > 1: g = (g[0:hh // 2 * 2:2] + g[1:hh // 2 * 2:2]) / 2; a = np.minimum(a[0:hh // 2 * 2:2], a[1:hh // 2 * 2:2])
        if ww > 1: g = (g[:, 0:ww // 2 * 2:2] + g[:, 1:ww // 2 * 2:2]) / 2; a = np.minimum(a[:, 0:ww // 2 * 2:2], a[:, 1:ww // 2 * 2:2])
    struct.pack_into('<II', d, 8, w, h)
    struct.pack_into('<III', d, 48 + 8, h, w, len(mips[0])); struct.pack_into('<I', d, 48 + 24, len(mips))
    return sbfw.Ch(4, new_id, bytes(d) + b''.join(mips), [], [])

def make_texture(tpl, new_id, grey, hole=None):
    """kind 4 chunk from a grey image, full mip chain, header cloned from a DXT1 template. hole: transparent texels
    (written as DXT1 punch-through on the top level only)."""
    if grey.ndim == 2: grey = np.dstack([grey] * 3)
    grey = vivid(grey); h, w = grey.shape[:2]; d = bytearray(tpl.data[:48 + 124]); mips = []; g = grey.astype(np.float32)
    while True:
        hh, ww = g.shape[:2]; pad = np.zeros((max(4, hh), max(4, ww), 3), np.float32); pad[:hh, :ww] = g
        if hh < 4: pad[hh:, :] = pad[hh - 1:hh, :]
        if ww < 4: pad[:, ww:] = pad[:, ww - 1:ww]
        mips.append(dxt1_rgb(np.clip(pad, 0, 255).astype(np.uint8), hole if (not mips and hole is not None and hole.shape == pad.shape[:2]) else None))
        if hh == 1 and ww == 1: break
        g = g[:max(1, hh // 2) * 2 if hh > 1 else 1, :max(1, ww // 2) * 2 if ww > 1 else 1]
        if hh > 1: g = (g[0::2] + g[1::2]) / 2
        if ww > 1: g = (g[:, 0::2] + g[:, 1::2]) / 2
    struct.pack_into('<II', d, 8, w, h)
    struct.pack_into('<III', d, 48 + 8, h, w, len(mips[0])); struct.pack_into('<I', d, 48 + 24, len(mips))
    return sbfw.Ch(4, new_id, bytes(d) + b''.join(mips), [], [])

def share_corners(v, strip, keep=None):
    """SEGA's meshes share a corner between the polygons that meet there; ours wrote four corners for every polygon, so Mountain had
    730 000 vertices against 186 000 .. 368 000 for SEGA's six tracks, and 1.8 million rounded 8 times (counted 2026-10-08).
    Vertices of one mesh that are the same in everything (place, shading normal, both texture coordinates) become one; the triangle
    strip is the same strip with the new numbers. The tangent is made a function of the normal first: it used to follow each polygon's
    first edge (so no two polygons agreed), and nothing reads it - the normal map of every imported material is flat."""
    v = v.copy(); n = v['n'].astype(np.float64); t = np.cross(n, [0.0, 0.0, 1.0]); lt = np.linalg.norm(t, axis=1); t_ = np.where((lt > 1e-3)[:, None], t / np.maximum(lt, 1e-12)[:, None], [1.0, 0.0, 0.0]).astype(np.float32)
    v['t'] = t_ if keep is None else np.where(np.asarray(keep, bool)[:, None], v['t'], t_)                # (keep: vertices whose tangent IS read - the relief test's)
    for f_ in ('p', 'n', 't'): v[f_] = v[f_] + np.float32(0.0)             # (-0.0 and 0.0 are the same number)
    raw = np.ascontiguousarray(v).view(np.dtype((np.void, v.dtype.itemsize))).ravel(); uq, first, inv = np.unique(raw, return_index=True, return_inverse=True)
    keep = np.sort(first); rank = np.empty(len(first), np.int64); rank[np.argsort(first)] = np.arange(len(first))
    return v[keep], rank[inv.ravel()][np.asarray(strip, np.int64)].tolist()

def _lm_test_texture(tpl):
    """EXPERIMENT 'lm_test'. Every imported material has the light map switch on, with a plain white picture and one texel for all vertices.
    To learn what the game does with it, the picture becomes four squares - white, half grey, black, red - and every polygon points at one of
    them by where it stands (16 m squares on the map, see faces_to_mesh). One screenshot then tells whether a light map dims everything or the
    sun only, what grey means, and whether it carries colour."""
    global VIVID
    im = np.zeros((16, 16, 3), np.uint8); im[:8, :8] = 255; im[:8, 8:] = 128; im[8:, :8] = 0; im[8:, 8:] = (255, 40, 40)
    keep = VIVID, _NO_GAIN[0]; VIVID = None; _NO_GAIN[0] = True; t = make_texture(tpl, 0xc1af0002, im, None); VIVID, _NO_GAIN[0] = keep; return t

def add_scenery(f, sta_gfx, faces, mode, lv, trees=False, rd=None):
    """mode 'checker' (step16), 'classic' (step17: one material per classic tile, luminance as DXT1), 'sr3' (step18: an
    existing Desert4 scenery material on everything)"""
    BM.import_closure(f, sta_gfx, [BM.TPL_MAT])
    sby = sta_gfx.byid(); tpl_mesh = sby[BM.TPL_MESH]; tpl_tex = sby[BM.TPL_TEX]; tpl_mat = f.get(BM.TPL_MAT)
    ccw = meshgen.winding_sign(tpl_mesh)[0] > 0; new = []; ids = []; nv = 0; clamp = 0; ncut = [0]; nsplit = [0]; nsingle = [0]; ndbl = [0]; nbefore = [0]; nafter = [0]; lm_mats = {}; bump_tex = {}; own_mats = []; road_mats = []
    tpl_tex5 = next(c for c in sta_gfx.kinds(4) if c.data[48 + 80:48 + 84] == b'DXT5' and struct.unpack_from('<I', c.data, 40)[0] == 1)   # small DXT5 header to clone
    groups = collections.defaultdict(list); treefaces = []
    global VIVID; VIVID = tuple(VIVID_CFG) if (mode == 'classic' and VIVID_CFG) else None
    if mode in ('classic', 'retex'):
        import classic_tex
        pages = classic_tex.load_pages(); tiles = classic_tex.usable(pages, classic_tex.materials())
        for fc in faces: groups[(str(fc[0]) + '|1') if (mode == 'classic' and str(fc[0]).endswith('_t') and str(fc[1]).endswith(SINGLE)) else (two_sided(fc)[0] if (mode == 'classic' and id(fc) not in PAIRS) else fc[0])].append(fc)
    if mode == 'retex':
        import retex
        lab = retex.labels(); src_files = {}; texmat = {}; nrep = collections.Counter()
    if mode not in ('classic', 'retex'):
        for fc in faces: groups[fc[1]].append(fc)
    if mode == 'checker':
        tex = tpl_tex.copy(); tex.id = 0xc1a50000; tex.gap = None; tex.data = BT.tex_fill(tex, (150, 130, 100), checker=((110, 95, 75), 64))
        mat_id = 0xc1a60000; new += [tex, meshgen.clone_material(tpl_mat, mat_id, tex.id)]
    if mode == 'sr3':
        mat_id = pick_sr3_material(f)
    for gi, (key, fl) in enumerate(sorted(groups.items())):
        uvmode = 'tile' if mode in ('classic', 'retex') else 'box'
        if mode == 'retex' and lab.get(key, ('', '', None))[2] is not None and not (trees and lab[key][0] == 'tree_wall'):
            cls, trk, tid = lab[key]
            if tid not in texmat:                                     # copy the SR3 texture chunk from the user's own track file
                if trk not in src_files: src_files[trk] = sbfw.read_sbf(track_files(os.path.join(TRACKS, trk))['master_gfx_xdata']).byid()
                tx = src_files[trk][tid].copy(); tx.gap = None
                if tid not in {c.id for c in f.chunks} and tid not in {c.id for c in new}: new.append(tx)
                texmat[tid] = 0xc1a80000 + len(texmat); new.append(meshgen.clone_material(tpl_mat, texmat[tid], tid))
            mat_id = texmat[tid]; cut = []
            for fc in fl:
                P = fc[2] if len(fc[2]) == 4 else fc[2] + [fc[2][2]]
                rpt = retex.REPEAT_BY_CLASS.get(cls, retex.REPEAT_M)
                for q in retex.subdivide(P, 2 * rpt - 0.5): cut.append((fc[0], fc[1], [tuple(p) for p in q], [tuple(u) for u in retex.box_uv(q, rpt)]))
            fl = cut; uvmode = 'given'; nrep[cls] += len(fl)
        if mode == 'retex' and trees and lab.get(key, ('',))[0] == 'tree_wall':      # upright tree boards -> SR3 tree-line texture
            rest = []
            for fc in fl:
                q = retex.tree_uv(fc[2])
                if q is None: rest.append(fc)
                else: treefaces.append((fc[0], fc[1], q[0], q[1]))
            fl = rest
            if not fl: continue
        if mode == 'retex' and lab.get(key, ('', '', None))[2] is not None and not (trees and lab[key][0] == 'tree_wall'): pass
        elif mode in ('classic', 'retex'):
            hole = None; both = str(key).endswith(('|2', '|4')); one_ = str(key).endswith('|1'); three_ = str(key).endswith('|3'); key = str(key).split('|')[0]; dbl_ = False
            if key in BAKED: grey, hole = BAKED[key]
            elif hd_tile(key) is not None: grey, hole = hd_tile(key)      # a re-authored tile (textures_hd): it was only read for the gates and the composed tiles, the course's own tiles came straight from the ROM here (user, 2026-10-08: "HD texture pick up not working")
            elif tiles.get(key):
                t = classic_tex.tile(pages, tiles[key]); grey = classic_tex.tile_rgb(t, tiles[key])
                if tiles[key]['alpha']: hole = (t == 15)
            elif EXTRA_TEX and os.path.exists(os.path.join(EXTRA_TEX, str(key) + '.png')):          # backdrop objects: tiles exported by the other session
                from PIL import Image as _I
                im = np.array(_I.open(os.path.join(EXTRA_TEX, str(key) + '.png')).convert('RGBA')); grey = np.ascontiguousarray(im[:, :, :3])
                if str(key).endswith('_t') and (im[:, :, 3] < 128).any(): hole = im[:, :, 3] < 128
            else:
                grey = np.full((16, 16, 3), 150, np.uint8)                      # flat-colour classic polygons (col_XXX)
                if not str(key).startswith('col_'): MISSING_TEX.append(str(key))   # anything else without a picture is a BUG (the grey forest floor of build W1)
            mat_id = 0xc1a60000 + gi; TEX_OF.setdefault(str(key), []).append(0xc1a50000 + gi)
            un_ = UNLIT_TPL is not None and key in UNLIT            # checkpoint / finish gates: SEGA's own UNLIT material (Desert4 47948b52: alpha test, two-sided, shadow casting, no lighting), so no light experiment and no shade dulls them (user, 2026-10-08)
            if un_: grey = np.clip(np.asarray(grey, np.float32) * UNLIT_GAIN, 0, 255).astype(np.uint8)
            _NO_GAIN[0] = bool(un_)
            if un_ and GATE_SHARP > 1:                              # the gates' pictures are small (CHECK POINT = 256 x 64 over 10 or 20 m): filtered and block-compressed at that size the letters came out soft and blotchy
                if hole is not None and hole.shape == np.asarray(grey).shape[:2]: hole = np.repeat(np.repeat(hole, GATE_SHARP, 0), GATE_SHARP, 1)      # (user, 2026-10-08: "our checkpoint resolution is lower"). Each texel written as a block of 4 x 4:
                grey = np.repeat(np.repeat(np.asarray(grey), GATE_SHARP, 0), GATE_SHARP, 1)                                                              # sharp edges, and the 4 x 4 compression blocks hold one colour each
            dbl_ = three_ and mode == 'classic' and hole is None and not un_      # seen from both sides (lightside.py, material key '|3'): written once per side, single-sided, each side with its own normal
            if not dbl_ and three_: both = True                       # (a '|3' that cannot be doubled is drawn two-sided like the rest)
            if bump_of(key) > 0 and hole is None:                    # RELIEF TEST: a normal map made from the tile's own picture; the picture itself brighter (the real sun lights an upright wall weakly)
                import bump1995; g3_ = np.asarray(grey); g3_ = g3_ if g3_.ndim == 3 else np.dstack([g3_] * 3); kp_ = VIVID, _NO_GAIN[0]; globals()['VIVID'] = None; _NO_GAIN[0] = True
                new.append(make_texture(tpl_tex, 0xc1ae0000 + gi, bump1995.normal_map(g3_, bump_of(key), BUMP_GREEN), None)); globals()['VIVID'], _NO_GAIN[0] = kp_; bump_tex[mat_id] = 0xc1ae0000 + gi
                grey = np.clip(g3_.astype(np.float32) * BUMP_GAIN, 0, 255).astype(np.uint8)
            if ROAD_RECIPE and hole is None and str(key) in ROAD_TILES: road_mats.append(mat_id)
            if OWN_SHADER and hole is None and (str(key) in OWN_SHADER or __import__('overlay_bake').ORIGIN.get(str(key), str(key)) in OWN_SHADER): own_mats.append(mat_id)
            TEXMAP[0xc1a50000 + gi] = dict(tile=str(key), cut=hole is not None, unlit=bool(un_), unlit_gain=float(UNLIT_GAIN), sharp=int(GATE_SHARP if un_ else 1), vivid=list(VIVID) if VIVID else None,
                                           gain=None if (un_ or SCENE_GAIN is None) else [float(q) for q in np.asarray(SCENE_GAIN, float).ravel()])
            if hole is not None:                                          # cut-out: DXT5 alpha + alpha-tested two-sided material
                if hole.shape == grey.shape[:2] and (~hole).any():        # see-through texels take the picture's mean colour: no dark fringe when the texture is filtered
                    grey = grey.copy(); grey[hole] = grey[~hole].mean(0).astype(np.uint8)
                tex = make_texture_dxt5(tpl_tex5, 0xc1a50000 + gi, grey, hole)
                span = np.array([(np.array(fc[3], float) - np.floor(np.array(fc[3], float).min(0) + 1e-6)).max(0) for fc in fl]).max(0) if fl else np.array([9.0, 9.0])
                if (span <= 1.00002).any():   # (limit = the one faces_to_mesh uses to move a face down by a repeat: with 1.002 here a board spanning 1.0005 was moved to negative uv on a CLAMPED axis and showed one texel row smeared over its whole height - the wall of green streaks in the forest)   # an axis along which the tile is never repeated is clamped, so filtering does not pull the opposite edge in (seams on the castle; tree lines repeat sideways only)
                    dd = bytearray(tex.data); struct.pack_into('<2I', dd, 20, 3 if span[0] <= 1.00002 else 1, 3 if span[1] <= 1.00002 else 1); tex.data = bytes(dd)
                cm_ = meshgen.clone_material(tpl_mat, mat_id, tex.id, cutout=True)
                if one_:                                                  # a tree blade's front or back: alpha test, NOT two-sided (the other face of the pair shows the other half of the picture)
                    dm_ = bytearray(cm_.data); struct.pack_into('<I', dm_, meshgen.DSIDE_CELL, 0); cm_.data = bytes(dm_); nsingle[0] += 1
                new += [tex, cm_]; ncut[0] += 1
            else:
                tex = make_texture(tpl_tex, 0xc1a50000 + gi, grey, None); new += [tex, meshgen.clone_material(tpl_mat, mat_id, tex.id, two_sided=both)]
            if un_:
                k_ = max(q_ for q_, c_ in enumerate(new) if c_.kind == 2 and c_.id == mat_id); m_ = UNLIT_TPL.copy(); m_.id = mat_id; m_.gap = None; d_ = bytearray(m_.data); struct.pack_into('<I', d_, 0x1bc, 0xc1a50000 + gi); m_.data = bytes(d_); new[k_] = m_
        _NO_GAIN[0] = False
        if uvmode == 'tile' and mode == 'classic': fl, ns = uv_split(fl); nsplit[0] += ns
        if mode == 'classic' and LIGHT_K > 0 and locals().get('dbl_'): fl = fl + [(m_, s_, list(P_)[::-1], list(U_)[::-1]) for m_, s_, P_, U_ in fl]; ndbl[0] += len(fl) // 2
        for part in range(0, len(fl), 10000):
            globals()['LM_LAST'] = None; v, nq, cl = faces_to_mesh(fl[part:part + 10000], uvmode, up_normals=(mode == 'classic')); clamp += cl
            pgs_ = LM_LAST if (LM_LAST is not None and len(LM_LAST) == nq) else np.zeros(nq, np.int32)          # LIGHT MAPS: a material shows ONE light map, so the polygons of each page become a mesh of their own, with a copy of the material that points at that page
            for pg_ in np.unique(pgs_):
                sel_ = np.nonzero(pgs_ == pg_)[0]; rows_ = None if len(sel_) == nq else (4 * sel_[:, None] + np.arange(4)).ravel(); vv = v if rows_ is None else v[rows_]; st_ = meshgen.quads_to_strip(len(sel_), ccw); mid_ = mat_id
                kt_ = None if (KEEP_T is None or len(KEEP_T) != len(v)) else (KEEP_T if rows_ is None else KEEP_T[rows_])
                if pg_ > 0:
                    if (mat_id, int(pg_)) not in lm_mats:
                        b_ = [c_ for c_ in new if c_.kind == 2 and c_.id == mat_id][-1].copy(); b_.id = 0xc1ac0000 + len(lm_mats); b_.gap = None; new.append(b_); lm_mats[(mat_id, int(pg_))] = b_.id
                    mid_ = lm_mats[(mat_id, int(pg_))]
                if SHARE and mode == 'classic': nbefore[0] += len(vv); vv, st_ = share_corners(vv, st_, kt_); nafter[0] += len(vv)
                nv += len(vv)
                m = meshgen.clone_mesh(tpl_mesh, 0xc1a70000 + len(ids), vv, st_, mid_, 'classic_%s' % str(key)[-12:])
                new.append(m); ids.append(m.id)
    if treefaces:
        trk, tid = retex.SR3_TREES
        if trk not in src_files: src_files[trk] = sbfw.read_sbf(track_files(os.path.join(TRACKS, trk))['master_gfx_xdata']).byid()
        tx = src_files[trk][tid].copy(); tx.gap = None; new += [tx, meshgen.clone_material(tpl_mat, 0xc1a90000, tid, cutout=True)]
        for part in range(0, len(treefaces), 10000):
            v, nq, cl = faces_to_mesh(treefaces[part:part + 10000], 'given'); nv += len(v)
            m = meshgen.clone_mesh(tpl_mesh, 0xc1a70000 + len(ids), v, meshgen.quads_to_strip(nq, ccw), 0xc1a90000, 'sr3_trees'); new.append(m); ids.append(m.id)
        log('       SR3 tree line texture %s %08x (alpha-tested clone) on %d upright classic foliage boards' % (trk, tid, len(treefaces)))
    if rd is not None and mode in ('classic', 'retex') and ROAD_DECALS:
        import retex as _rt
        road_list = classic_road(rd, pages, tiles) if mode == 'classic' else road_decals(rd, pages, tiles, _rt.labels())
        if mode == 'classic' and ROAD_MODE == 'layers' and road_list:
            # SR3 draws car shadows, skid marks and ruts on ITS road; a draped 1995 road hides them all (user: no shadow with the
            # SR3 road hidden). So the main 1995 asphalt tile goes INTO the SR3 tarmac layers (import_classic writes ROAD_MAIN),
            # tiles of the same asphalt are not draped, painted lines stay as see-through decals, other surfaces stay decals.
            big = max(road_list, key=lambda e: len(e[1])); main = big[2].reshape(-1, 3).astype(float); mc = main.mean(0); ROAD_MAIN[:] = [big[2]]; keep = []
            for name, pieces, rgb, hole in road_list:
                x = rgb.astype(float); lum = x.mean(-1); mark = (lum > mc.mean() + 55) & ((x.max(-1) - x.min(-1)) < 60); dist = float(np.abs(x.reshape(-1, 3).mean(0) - mc).max())
                if name == big[0]: what = 'into the SR3 layers'
                elif 0.003 < mark.mean() < 0.6: keep.append((name, pieces, rgb, ~mark if hole is None else (hole | ~mark))); what = 'painted lines kept as decal (%.1f%% of texels)' % (100 * mark.mean())
                elif dist < 40 and hole is None: what = 'same asphalt, not draped'
                else: keep.append((name, pieces, rgb, hole)); what = 'other surface, draped'
                log('       road tile %s: %d pieces, mean colour %s -> %s' % (name, len(pieces), x.reshape(-1, 3).mean(0).round().tolist(), what))
            road_list = keep
        for di, (name, pieces, rgb, hole) in enumerate(road_list):
            tid = 0xc1aa0000 + 2 * di; mid = tid + 1
            if ROAD_BLEND:                                                 # SEGA's own road paint (Alpine4 centre dashes) is decal quads 1-2 cm over the road with the alpha-BLEND switch, and does not z-fight; opaque decals 3 cm up did, in the distance
                new += [make_texture_dxt5(tpl_tex5, tid, rgb, hole if hole is not None else np.zeros(rgb.shape[:2], bool)), shadow_recv(meshgen.clone_material(tpl_mat, mid, tid, blend=True))]
            elif hole is not None: new += [make_texture_dxt5(tpl_tex5, tid, rgb, hole), meshgen.clone_material(tpl_mat, mid, tid, cutout=True)]; ncut[0] += 1
            else: new += [make_texture(tpl_tex, tid, rgb, None), meshgen.clone_material(tpl_mat, mid, tid)]
            pieces, ns_ = uv_split(pieces); nsplit[0] += ns_           # (road pieces whose tile repeats more than twice were clamped = smeared bands across the road)
            for part in range(0, len(pieces), 10000):
                globals()['LM_LAST'] = None; v, nq, cl = faces_to_mesh(pieces[part:part + 10000], 'tile', up_normals=ROAD_UP_NORMALS); clamp += cl
                pgs_ = LM_LAST if (LM_LAST is not None and len(LM_LAST) == nq) else np.zeros(nq, np.int32)
                for pg_ in np.unique(pgs_):                                # (light maps: a mesh and a copy of the material for every page, as in the scenery; the copy has the light map switch ON)
                    sel_ = np.nonzero(pgs_ == pg_)[0]; vv = v if len(sel_) == nq else v[(4 * sel_[:, None] + np.arange(4)).ravel()]; mid_ = mid
                    if pg_ > 0:
                        if (mid, int(pg_)) not in lm_mats:
                            b_ = [c_ for c_ in new if c_.kind == 2 and c_.id == mid][-1].copy(); b_.id = 0xc1ac0000 + len(lm_mats); b_.gap = None; d_ = bytearray(b_.data); struct.pack_into('<I', d_, 0x594, 1); b_.data = bytes(d_); new.append(b_); lm_mats[(mid, int(pg_))] = b_.id
                        mid_ = lm_mats[(mid, int(pg_))]
                    nv += len(vv); m = meshgen.clone_mesh(tpl_mesh, 0xc1a70000 + len(ids), vv, meshgen.quads_to_strip(len(sel_), ccw), mid_, 'road_decal'); new.append(m); ids.append(m.id)
            faces = faces + pieces[::50]                                # so the leaf list covers them
    # The cloned material is a Stadium wall's (LITE PIXL SPEC DIFFM NORM LMAP SPECM REFL) and still pointed at that wall's
    # normal map, light map, specular map and reflection: in the game they painted bright window-grid patches over the
    # 1995 textures (first in-game run of Mountain). Its shader stays (only switch combinations SEGA compiled exist), the
    # four maps become neutral: flat normal, white light, no specular, no reflection.
    VIVID = None
    if mode != 'allsr3':
        have_ids = {c.id for c in f.chunks} | {c.id for c in new}
        flat = np.zeros((8, 8, 3), np.uint8); flat[:] = (128, 128, 255)
        neutral = {0x1dc: (0xc1af0001, make_texture_dxt5(tpl_tex5, 0xc1af0001, flat, np.ones((8, 8), bool) & False)),     # normal: (0, 0, 1)
                   0x1fc: (0xc1af0002, _lm_test_texture(tpl_tex) if LM_TEST else make_texture(tpl_tex, 0xc1af0002, np.full((8, 8, 3), 255, np.uint8), None)),        # light: white
                   0x21c: (0xc1af0003, make_texture(tpl_tex, 0xc1af0003, np.zeros((8, 8, 3), np.uint8), None)),            # specular: none
                   0x27c: (0xc1af0003, None)}                                                                             # reflection: none
        used = False
        for c in new:
            if c.kind == 2 and len(c.data) == 1848 and (c.id >> 16) in (0xc1a6, 0xc1a7, 0xc1a8, 0xc1a9, 0xc1aa, 0xc1ab, 0xc1ac):
                d = bytearray(c.data)
                for off, (tid, _) in neutral.items():
                    if off in c.ref: struct.pack_into('<I', d, off, tid); used = True
                c.data = bytes(d)
        if used: new += [t for _, t in neutral.values() if t is not None and t.id not in have_ids]
        if lm_mats:                                                    # the light map pages, and the copies of the materials pointed at them
            keep_ = VIVID, _NO_GAIN[0]; globals()['VIVID'] = None; _NO_GAIN[0] = True; byid_ = {c.id: c for c in new if c.kind == 2}
            # THE ROAD'S LIGHT WITHOUT COLOUR. The light maps carry the colour of the light that comes back from what stands near, and a light map
            # multiplies what is under it: beside brick and warm plaster the white road lines came out orange (measured on a screenshot: 238 / 209 / 204
            # along a building, 227 / 221 / 224 in the open; user, 2026-10-08: "the white markings on the road aren't white, they're tinted orange").
            # The road's rectangles keep their brightness (0.30 R + 0.59 G + 0.11 B) and lose their colour; the scenery keeps both.
            pgi_ = {}
            for i_ in LM_TABLE.get('grey', ()): pgi_.setdefault(int(LM_TABLE['page'][i_]), []).append(i_)
            for pg_ in sorted({p_ for _, p_ in lm_mats}):
                im_ = np.array(LM_TABLE['pages'][pg_ - 1])
                for i_ in pgi_.get(int(pg_), ()):
                    x_ = int(LM_TABLE['x0'][i_]); y_ = int(LM_TABLE['y0'][i_]); w_ = (int(LM_TABLE['nu'][i_]) + 3) // 4 * 4; h_ = (int(LM_TABLE['nv'][i_]) + 3) // 4 * 4; r_ = im_[y_:y_ + h_, x_:x_ + w_].astype(np.float32)
                    im_[y_:y_ + h_, x_:x_ + w_] = np.clip(np.round(r_ @ np.array([0.30, 0.59, 0.11], np.float32)), 0, 255).astype(np.uint8)[..., None]
                new.append(make_texture(tpl_tex, 0xc1ad0000 + pg_, np.ascontiguousarray(im_), None))
            if pgi_: log('       light maps: the road keeps brightness only (%d road polygons made colourless)' % sum(len(q_) for q_ in pgi_.values()))
            for (m_, pg_), id_ in lm_mats.items(): d_ = bytearray(byid_[id_].data); struct.pack_into('<I', d_, 0x1fc, 0xc1ad0000 + pg_); byid_[id_].data = bytes(d_)
            globals()['VIVID'], _NO_GAIN[0] = keep_; log('       light maps: %d pages, %d materials copied for them ; polygons found on a page %d, not found %d (those keep the white picture)' % (len({p_ for _, p_ in lm_mats}), len(lm_mats), LM_TABLE['hit'][0], LM_TABLE['miss'][0]))
    if own_mats:
        # A SHADER OF THEIR OWN (24_shaders.md). The imported materials select the uber technique T_Lpse_Tdnsl (switch mask 0x3E0E), which 18 of SEGA's own
        # materials select too. With the specular-MAP switch off (+0x5B4) the mask is 0x2E0E = T_Lpse_Tdnl, which NO material of the game or of the added
        # tracks selects (18 428 materials counted): its pixel shader can be replaced at run time without touching anything else. The specular map of
        # imported materials is the black 'none' picture anyway.
        byid_ = {c.id: c for c in new if c.kind == 2}; n_ = 0
        for id_ in list(own_mats) + [i_ for (m_, p_), i_ in lm_mats.items() if m_ in set(own_mats)]:
            if id_ in byid_ and len(byid_[id_].data) == 1848: d_ = bytearray(byid_[id_].data); struct.pack_into('<I', d_, 0x5B4, 0); byid_[id_].data = bytes(d_); n_ += 1
        log('       own shader: %d materials of %d tiles select the unused technique (specular-map switch off)' % (n_, len(OWN_SHADER)))
    if bump_tex:
        byid_ = {c.id: c for c in new if c.kind == 2}; n_ = 0
        for id_, base_ in [(m_, m_) for m_ in bump_tex] + [(i_, m_) for (m_, p_), i_ in lm_mats.items() if m_ in bump_tex]:
            if id_ in byid_: d_ = bytearray(byid_[id_].data); struct.pack_into('<I', d_, 0x1dc, bump_tex[base_]); byid_[id_].data = bytes(d_); n_ += 1
        log('       relief test: %d tiles with a normal map made from their picture, on %d materials' % (len(bump_tex), n_))
    if ROAD_VERBATIM and mode == 'classic':
        n_ = 0
        for c_ in new:
            if c_.kind == 2 and len(c_.data) == 1848: d_ = bytearray(c_.data); struct.pack_into('<I', d_, 0x52C, 1); struct.pack_into('<I', d_, 0x540, 1); c_.data = bytes(d_); n_ += 1
        log('       verbatim road: %d scenery materials receive static and dynamic shadows' % n_)
        if road_mats:
            rm_ = set(road_mats); k_ = 0
            for q_, c_ in enumerate(new):
                if c_.kind == 2 and c_.id in rm_ and len(c_.data) == 1848:
                    # which part of SEGA's recipe cures the banded shadow? (TEST B = the whole recipe: cured, but alpha blend upsets the order dust is drawn in; user, 2026-10-09)
                    #   'sega' the whole recipe ; 'opaque' the recipe without alpha blend ; 'nolm' only the light map off ; 'oneside' only single-sided ; 'nospec' only specular map and reflection off
                    if ROAD_RECIPE in (True, 'sega'): new[q_] = shadow_recv(c_)
                    else:
                        d_ = bytearray(c_.data)
                        if ROAD_RECIPE == 'opaque': d_ = bytearray(shadow_recv(c_).data); struct.pack_into('<I', d_, 0x4E4, 0)
                        elif ROAD_RECIPE == 'nolm': struct.pack_into('<I', d_, 0x594, 0)
                        elif ROAD_RECIPE == 'oneside': struct.pack_into('<I', d_, 0x50C, 0)
                        elif ROAD_RECIPE == 'nospec': struct.pack_into('<I', d_, 0x5B4, 0); struct.pack_into('<I', d_, 0x620, 0)
                        c_.data = bytes(d_)
                    k_ += 1
            log('       verbatim road: %d road materials changed (road_recipe %s)' % (k_, ROAD_RECIPE))
    f.chunks[len(f.chunks) - 1:len(f.chunks) - 1] = new
    if ndbl[0]: log('       lit by the sun (light_contrast %.2f): %d opaque faces written once per side, single-sided' % (LIGHT_K, ndbl[0]))
    if nsplit[0]: log('       %d classic faces repeat their tile more than twice: cut into pieces (u16 uv holds 0..2 repeats)' % nsplit[0])
    if ncut[0]: log('       cut-out materials (alpha test + two-sided, DXT5 alpha): %d' % ncut[0])
    if mode == 'retex': log('       retextured with SR3 textures (pieces per class): %s ; %d SR3 textures copied' % (dict(nrep), len(texmat)))
    allp = np.array([p for fc in faces for p in fc[2]])
    lv2 = lv | BM.leaves_for(allp[::7], pad=0)
    BT.set_scene(f, lv2, ids)
    if nbefore[0]: log('       corners shared between polygons (share_corners): %d vertices written as %d in those meshes' % (nbefore[0], nafter[0]))
    log('       scenery (%s): %d meshes, %d vertices, largest mesh %d verts, %d faces with uv span > 2 clamped, extent x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f' %
        (mode, len(ids), nv, max(struct.unpack_from('<I', c.data, 0x14)[0] for c in new if c.kind == 1), clamp, allp[:, 0].min(), allp[:, 0].max(), allp[:, 1].min(), allp[:, 1].max(), allp[:, 2].min(), allp[:, 2].max()))

def road_height(rd):
    """-> function (x, z) -> height of the SR3 road surface (bilinear in the slice / column grid)"""
    V = rd['V']; hw = rd['hw']; cen = V[:, hw]; n = len(V); D = rd['D']; lat = rd['lat']
    near = Near(cen[:, [0, 2]])
    def at(pts):
        pts = np.asarray(pts, float); idx = near(pts[:, [0, 2]]); out = np.zeros(len(pts))
        for q, (p, i) in enumerate(zip(pts, idx)):
            d = p[[0, 2]] - cen[i, [0, 2]]; a = float(d @ D[i, [0, 2]]); c = float(d @ lat[i, [0, 2]]) + hw
            c = min(max(c, 0.0), 2 * hw - 1e-6); k = int(c); fc = c - k; j = (i + (1 if a >= 0 else -1)) % n; fa = min(abs(a), 1.0)
            y0 = V[i, k, 1] * (1 - fc) + V[i, k + 1, 1] * fc; y1 = V[j, k, 1] * (1 - fc) + V[j, k + 1, 1] * fc
            out[q] = y0 * (1 - fa) + y1 * fa
        return out
    return at

def split_faces(faces, maxlen):
    """faces cut to quads of at most maxlen per side, uv interpolated (triangles become quads with a repeated corner)"""
    out = []
    for mat, sec, P, UV in faces:
        if len(P) == 3: P = list(P) + [P[2]]; UV = list(UV) + [UV[2]]
        P = np.array(P[:4], float); U = np.array(UV[:4], float)
        lu = max(np.linalg.norm(P[1] - P[0]), np.linalg.norm(P[2] - P[3])); lv = max(np.linalg.norm(P[3] - P[0]), np.linalg.norm(P[2] - P[1]))
        n = max(1, int(np.ceil(lu / maxlen))); m = max(1, int(np.ceil(lv / maxlen)))
        if n * m > 900: sc = (900.0 / (n * m)) ** 0.5; n = max(1, int(n * sc)); m = max(1, int(m * sc))
        def pt(A, a, b): return (A[0] * (1 - a) + A[1] * a) * (1 - b) + (A[3] * (1 - a) + A[2] * a) * b
        for i in range(n):
            for j in range(m):
                c = [(i / n, j / m), ((i + 1) / n, j / m), ((i + 1) / n, (j + 1) / m), (i / n, (j + 1) / m)]
                out.append((mat, sec, [tuple(pt(P, a, b)) for a, b in c], [tuple(pt(U, a, b)) for a, b in c]))
    return out

def drape(faces, hfun, lift, maxlen=1.0):
    """cut faces to pieces of at most maxlen (uv interpolated) and lay them on the SR3 road, lift metres above it"""
    out = []
    for mat, sec, P, UV in faces:
        if len(P) == 3: P = P + [P[2]]; UV = UV + [UV[2]]
        P = np.array(P[:4], float); U = np.array(UV[:4], float)
        lu = max(np.linalg.norm(P[1] - P[0]), np.linalg.norm(P[2] - P[3])); lv = max(np.linalg.norm(P[3] - P[0]), np.linalg.norm(P[2] - P[1]))
        n = max(1, int(np.ceil(lu / maxlen))); m = max(1, int(np.ceil(lv / maxlen)))
        if n * m > 900: sc = (900.0 / (n * m)) ** 0.5; n = max(1, int(n * sc)); m = max(1, int(m * sc))
        def pt(A, a, b): return (A[0] * (1 - a) + A[1] * a) * (1 - b) + (A[3] * (1 - a) + A[2] * a) * b
        G = np.array([[pt(P, i / n, j / m) for j in range(m + 1)] for i in range(n + 1)]); T = np.array([[pt(U, i / n, j / m) for j in range(m + 1)] for i in range(n + 1)])
        G[:, :, 1] = hfun(G.reshape(-1, 3)).reshape(n + 1, m + 1) + lift
        for i in range(n):
            for j in range(m):
                out.append((mat, sec, [tuple(G[i, j]), tuple(G[i + 1, j]), tuple(G[i + 1, j + 1]), tuple(G[i, j + 1])], [tuple(T[i, j]), tuple(T[i + 1, j]), tuple(T[i + 1, j + 1]), tuple(T[i, j + 1])]))
    return out

def classic_road(rd, pages, tiles):
    """classic variant: EVERY 1995 polygon that the SR3 road replaced is laid back on the SR3 road as an opaque decal,
    3 cm above it, with its own 1995 tile and UVs (asphalt, painted lines, dirt, cobbles). The SR3 layers underneath keep
    the physics. -> [(tile name, pieces, rgb, None)]"""
    import classic_tex
    hf = road_height(rd); by = collections.defaultdict(list); out = []; n = 0
    def lay(fc): return int(str(fc[1]).rsplit('#L', 1)[1]) if '#L' in str(fc[1]) else 0
    for fc in DROPPED: by[(fc[0], lay(fc))].append(fc)
    for (name, L), fl in sorted(by.items()):
        m = tiles.get(name)
        if not m: continue
        t = classic_tex.tile(pages, m); hole = (t == 15) if m.get('alpha') else None
        out.append((name, drape(fl, hf, 0.03 + 0.02 * L, maxlen=1.002), classic_tex.tile_rgb(t, m), hole)); n += len(fl)      # (1.002, not 1.0: the pieces come from split_faces(..., 1.0) with sides of 1.0000000000000002, and at exactly 1.0 drape halved them all again - 239 000 pieces became 337 000; found 2026-10-08)
    log('       1995 road surface: %d classic road polygons of %d tiles draped on the SR3 road as decals (3 cm above it)' % (n, len(out)))
    return out

def road_decals(rd, pages, tiles, lab):
    """classic lane markings (bright texels of the asphalt tiles that have any; the tarmac itself is made transparent) and
    paved strips (tiles labelled cobbles) that lie on the road strip -> [(tile name, pieces, rgb, hole or None)]"""
    import classic_tex, m2colour
    lr = m2colour.lumaram(); hf = road_height(rd); by = collections.defaultdict(list); out = []
    for fc in DROPPED: by[fc[0]].append(fc)
    for name, fl in sorted(by.items()):
        m = tiles.get(name); cls = lab.get(name, ('',))[0]
        if not m: continue
        t = classic_tex.tile(pages, m); rgb = classic_tex.tile_rgb(t, m)
        if cls == 'asphalt':
            lb = m.get('luma', 0); l = lr[(lb << 7) + (t.astype(np.int32) << 3)].astype(np.int32)
            mark = l >= 58                                             # top of the ramp = the white paint in gradient row 13
            if not 0.003 < mark.mean() < 0.5: continue
            out.append((name, drape(fl, hf, 0.03), rgb, ~mark)); log('       road markings: tile %s, %d classic faces, %.1f%% painted texels' % (name, len(fl), 100 * mark.mean()))
        elif cls in ('cobbles', 'pavement'):
            out.append((name, drape(fl, hf, 0.025), rgb, None)); log('       paved strip on the road: tile %s, %d classic faces' % (name, len(fl)))
    return out

def pick_sr3_material(f):
    """the material used by most vertices of Desert4's own one-group format-0x20C7 scenery meshes"""
    cnt = collections.Counter()
    for c in f.kinds(1):
        h = struct.unpack_from('<18I', c.data, 0)
        if h[0] == 48 and h[2] == 0x20c7 and h[11] == 0x48:
            for k in range(h[8]):
                g = struct.unpack_from('<5I', c.data, 0x48 + 20 * k); cnt[g[4]] += g[1]
    mid = cnt.most_common(1)[0][0]
    log('       SR3 material for the scenery: %08x (used by %d vertices of Desert4 scenery)' % (mid, cnt[mid]))
    return mid

def empty_objects(trk):
    """smallest edit that removes the borrowed props: object count of the game_objects list set to 0"""
    g = trk.files['game_objects_gfx_data']; c = g.chunks[-1]; d = bytearray(c.data)
    n = struct.unpack_from('<I', d, 4)[0]; struct.pack_into('<I', d, 4, 0); c.data = bytes(d)
    return n

def minimal_objects(trk):
    """AUTHORED empty object list: the game_objects file becomes one kind 5 chunk
        +00 u32 3 (version; 0x5BF484 needs >= 3)   +04 u32 0 objects   +08 ptr object records (0x54 bytes each; none)
        +0C ptr animated-model descriptor {1, 0 entries, ptr}          +10 ptr shape table {0 entries}
    and the gameobj_dis, pobj_master, pobj_plac files and the grass cache are left out (the loaders skip missing files:
    0x6530B0 returns 0, 0x5BE010 / 0x5C5509 test for it). See ../../07_glue_and_other_files.md."""
    g = trk.files['game_objects_gfx_data']; old = g.chunks[-1]; n = old.u32(4); nch = len(g.chunks)
    d = struct.pack('<5I', 3, 0, 0x30, 0x14, 0x24) + struct.pack('<3I', 1, 0, 0x30) + struct.pack('<I', 0) + struct.pack('<3I', 0, 0, 0) + b'\0' * 16
    assert len(d) == 0x40
    g.chunks = [sbfw.Ch(5, old.id, d, [8, 0xc, 0x10, 0x1c], [])]
    for s_ in ('gameobj_gfx_dis_data', 'pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata'): trk.files.pop(s_, None)
    return n, nch

def no_cameras(trk):
    """master_xdata root: +0C (camera lists) and +14 (helicopter) set to 0, their chunks dropped. 0x5FB250 skips the lists
    when +0C is 0; the three camera managers then build their own default cameras on first use."""
    fx = trk.files['master_xdata']; r = fx.chunks[-1]; d = bytearray(r.data); gone = [o for o in (0xc, 0x14) if o in r.ref and r.u32(o)]
    for o in gone: struct.pack_into('<I', d, o, 0)
    r.data = bytes(d); r.ref = [o for o in r.ref if o not in gone]
    return len(gone), BT.gc(fx)

# ---------------------------------------------------------------- steps
def main(only=''):
    def want(n): return n.startswith(only)
    LOG.append('---- build_classic ----')
    des = BT.Track('Desert4'); sta_gfx = BT.Track('Stadium4').files['master_gfx_xdata']
    surf, wi, fi = BM.boundary_surfaces(des.files['master_gfx_xdata'])
    log('importing road'); rd = import_road(); faces = None
    def base(walls):
        t, model, lv = build_road_track(des, rd); f = t.files['master_gfx_xdata']
        if walls: BM.add_walls(f, BT.td_rows(model), surf, wi, fi, terrain=True)
        return t, f, model, lv
    plan = [('step14_classic_course1_desert4', False, None, ''), ('step15_classic_course1_walls_desert4', True, None, ''),
            ('step16_classic_scenery_checker_desert4', True, 'checker', ''), ('step17_classic_scenery_textured_desert4', True, 'classic', ''),
            ('step18_classic_scenery_sr3material_desert4', True, 'sr3', ''), ('step19_classic_no_props_desert4', True, 'classic', 'noprops'),
            ('step20_classic_retextured_sr3_desert4', True, 'retex', 'decals'),
            ('step21_classic_min_objects_desert4', True, 'retex', 'decals minobj'),
            ('step22_classic_no_cameras_desert4', True, 'retex', 'decals minobj nocam'),
            ('step23_classic_sr3_trees_desert4', True, 'retex', 'decals trees')]
    for n, walls, scen, opt in plan:
        if not want(n): continue
        log(n); t, f, model, lv = base(walls); opt = opt.split()
        if scen:
            if faces is None: faces = load_visual(rd)
            add_scenery(f, sta_gfx, faces, scen, lv, trees='trees' in opt, rd=rd if 'decals' in opt else None)
        omit = ()
        if 'noprops' in opt:
            k = empty_objects(t); omit = ('pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata', 'proc')
            log('       game_objects: object count %d -> 0 ; pobj files and grass cache omitted' % k)
        if 'minobj' in opt:
            k, nch = minimal_objects(t); omit = ('proc',)
            log('       game_objects: AUTHORED empty list (1 chunk, 64 bytes) replaces %d objects in %d chunks; gameobj_dis, pobj_master, pobj_plac and the grass cache left out' % (k, nch))
        if 'nocam' in opt:
            k, dr = no_cameras(t); log('       master_xdata: %d root references cleared (camera lists +0C, helicopter +14), %d chunks dropped' % (k, dr))
        d = BT.gc(f, t); BT.write_track(n, t, omit=omit, note='| %d unreferenced chunks dropped' % d); BT.check_authored(n, t)
    open(os.path.join(OUT, 'build_log.txt'), 'a').write('\n'.join(LOG[LOG.index('---- build_classic ----'):]) + '\n')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '')

# compiled / array versions of the slow functions above (fastbuild.py, checked to give the same bytes; SR3_FASTGEO=0 switches them off)
import sys as _sys, fastbuild as _fb_mod; _fb_mod.install(_sys.modules[__name__])
