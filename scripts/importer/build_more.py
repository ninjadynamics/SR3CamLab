"""Second batch of ladder steps (10+): walls, authored meshes, imported classic course. Existing steps are not renumbered.
    python build_more.py [name prefix]
Appends to ..\\out\\build_log.txt (section "build_more")."""
import os, sys, struct, math, collections
import numpy as np
from common import *
import sbfw, grid as G, trackdeform as TDm, scene11, bsp, bsp_build, meshgen
import build_testtrack as BT
from build_testtrack import log, LOG

# ---------------------------------------------------------------- walls
def boundary_surfaces(f):
    """(id table, wall index, floor index) taken from the slot's own boundary chunk"""
    r = BT.gfx_root(f); b = bsp.parse_bsp(f.byid()[r.u32(0x34)])
    wall = collections.Counter(); floor = collections.Counter()
    for pl, sf, pa, pb in b.leaves:
        for q, s in zip(pl, sf): (wall if abs(q[1]) < 0.5 else floor)[int(s)] += 1
    return b.surf, wall.most_common(1)[0][0], floor.most_common(1)[0][0]

def set_boundary(f, data, fix, cid=0xb0d1e001):
    r = BT.gfx_root(f); by = f.byid(); old = r.u32(0x34)
    if old and old in by:
        BT.replace(f, old, data, fix, [])
    else:
        f.chunks.insert(len(f.chunks) - 1, sbfw.Ch(5, cid, data, fix, []))
        d = bytearray(r.data); struct.pack_into('<I', d, 8, 0x34); struct.pack_into('<I', d, 0x34, cid); r.data = bytes(d)
        r.fix = sorted(set(r.fix) | {8}); r.ref = sorted(set(r.ref) | {0x34})

def corridor_lines(rows, every=4, inset=0.5, with_heights=False):
    """left/right wall polylines from road rows (vertex positions per slice): `inset` metres inside the road edges"""
    L = []; R = []; ys = []; H = []
    for pos, off, A in rows[::every]:
        a, b = pos[0], pos[-1]; d = (b - a); d = d / np.linalg.norm(d)
        p = a + d * inset; q = b - d * inset
        L.append((p[0], p[2])); R.append((q[0], q[2])); ys += [a[1], b[1]]; H.append((float(pos[:, 1].min()), float(pos[:, 1].max())))
    if with_heights: return L, R, min(ys), max(ys), H
    return L, R, min(ys), max(ys)

def add_walls(f, rows, surf, wall_i, floor_i, every=4, terrain=False):
    """terrain=True: floor/ceiling follow the road height cell by cell (2 m below the lowest, 10 m above the highest road
    point of the stretch a cell overlaps) instead of one floor and ceiling for the whole track."""
    L, R, ymin, ymax, H = corridor_lines(rows, every, with_heights=True)
    y0, y1 = ymin - 2.0, ymax + 10.0
    hts = None; xfall = 0.0
    if terrain:
        lo = np.array([h[0] for h in H]); hi = np.array([h[1] for h in H])
        hts = (lo + hi) / 2.0; xfall = float((hi - lo).max())           # cross-fall of a slice widens the margins
    data, fix, tree, polys, stats, inc = bsp_build.build_corridor(L, R, y0=y0, y1=y1, surf_wall=wall_i, surf_floor=floor_i, surf_ids=surf,
                                                                  heights=hts, below=2.0 + xfall / 2, above=10.0 + xfall / 2)
    set_boundary(f, data, fix)
    # self checks: (1) random points agree with the geometry, (2) every road centre point 1 m above the road is free
    allp = np.array(L + R); bbox = (allp[:, 0].min() - 20, allp[:, 1].min() - 20, allp[:, 0].max() + 20, allp[:, 1].max() + 20)
    chk = bsp_build.check_corridor(tree, inc, bbox, y0, y1, n=6000) if not terrain else 'n/a (stepped floor/ceiling)'
    free = 0; tot = 0; under = 0; over = 0; span = (ymax - ymin) if not terrain else 0.0
    for pos, off, A in rows[::3]:
        e = pos[-1] - pos[0]; e = e / np.linalg.norm(e)
        for c in (pos[len(pos) // 2], pos[0] + e * 2.0, pos[-1] - e * 2.0):   # centre and 2 m inside both edges, 1 m above the road
            lf = bsp_build.classify_tree(tree, (c[0], c[1] + 1.0, c[2])); tot += 1; free += lf[0] == 'leaf'
            under += bsp_build.classify_tree(tree, (c[0], c[1] - 12.0 - span, c[2]))[0] == 'solid'
            over += bsp_build.classify_tree(tree, (c[0], c[1] + 24.0 + span, c[2]))[0] == 'solid'
    if terrain:
        gaps = [(b - a) for cell, a, b in inc.cells]; log('       terrain-following: %d free cells, tunnel height %.1f..%.1f m' % (len(gaps), min(gaps), max(gaps)))
    log('       points 12 m below the road solid %d/%d, 24 m above solid %d/%d' % (under, tot, over, tot))
    b = bsp.parse_bsp(sbfw.Ch(5, 1, data, fix, []))
    log('       walls: %d wall segments, floor %.1f ceiling %.1f, nodes kd %d planes %d solid %d leaves %d polys %d, depth max/mean %s' %
        (2 * len(L), y0, y1, b.nkd, b.npl, b.n3, b.nleaf, b.npoly, '%d/%.1f' % bsp_build.depth_stats(tree)[:2]))
    log('       walls check: random points %s ; road points (centre + both sides) free %d/%d' % (chk, free, tot))

# ---------------------------------------------------------------- authored meshes
TPL_MESH, TPL_MAT, TPL_TEX = 0x79d17eed, 0x7e9488ff, 0x4fd0d213
def import_closure(dst, src, ids):
    """copy chunks (and everything they reference) from another parsed file, skipping ids already present"""
    have = {c.id for c in dst.chunks}; sby = src.byid(); st = list(ids); add = []
    while st:
        i = st.pop()
        if i in have or i not in sby: continue
        have.add(i); c = sby[i].copy(); c.gap = None; add.append(c); st += c.refs()
    order = {c.id: k for k, c in enumerate(src.chunks)}
    add.sort(key=lambda c: order[c.id])
    dst.chunks[0:0] = add
    return len(add)

def add_meshes(f, sta_gfx, quad_sets, leaves):
    """quad_sets: list of (name, quads). One authored mesh per set, one shared authored material + diffuse texture.
    Meshes are world-space and hang on the ROOT node of a freshly built scenery tree."""
    n = import_closure(f, sta_gfx, [TPL_MAT])                         # shader + the borrowed secondary textures of the material
    sby = sta_gfx.byid(); tex = sby[TPL_TEX].copy(); tex.id = 0xa07e0003; tex.gap = None
    tex.data = BT.tex_fill(tex, (70, 120, 60), checker=((50, 90, 45), 64))
    mat = meshgen.clone_material(f.get(TPL_MAT), 0xa07e0010, tex.id)
    ccw = meshgen.winding_sign(sby[TPL_MESH])[0] > 0
    ids = []; new = [tex, mat]
    for k, (name, quads) in enumerate(quad_sets):
        v = meshgen.make_verts(quads)
        m = meshgen.clone_mesh(sby[TPL_MESH], 0xa07e0020 + k, v, meshgen.quads_to_strip(len(quads), ccw), mat.id, name)
        ws = meshgen.winding_sign(m); new.append(m); ids.append(m.id)
        log('       mesh %s: %d quads, %d verts, winding score %d (template sign %d), bbox %s .. %s' %
            (name, len(quads), len(v), ws[1], -1 if not ccw else 1, v['p'][:, :3].min(0).round(1).tolist(), v['p'][:, :3].max(0).round(1).tolist()))
    f.chunks[len(f.chunks) - 1:len(f.chunks) - 1] = new
    BT.set_scene(f, leaves, ids)
    return ids

def leaves_for(points, pad=30):
    lv = set()
    for p in points:
        for dx in (-pad, 0, pad):
            for dz in (-pad, 0, pad):
                lv.add((int((p[0] + dx + 750) // 46.875), int((p[2] + dz + 750) // 46.875)))
    return {(x, z) for x, z in lv if 0 <= x < 32 and 0 <= z < 32}

def loop_scenery(info):
    """ground plane 0.3 m under a flat road + a 2 m box 4 m outside the left edge 30 m after the start line"""
    P = info['P']; lat = info['lat']; hw = info['half_width']
    x0 = math.floor((P[:, 0].min() - 60) / 20) * 20; x1 = math.ceil((P[:, 0].max() + 60) / 20) * 20
    z0 = math.floor((P[:, 2].min() - 60) / 20) * 20; z1 = math.ceil((P[:, 2].max() + 60) / 20) * 20
    y = float(P[:, 1].min()) - 0.3
    ground = meshgen.ground_quads(x0, z0, x1, z1, y, 20.0)
    i = 130 % len(P); c = P[i] + lat[i] * (hw + 4.0)
    box = meshgen.box_quads(c[0], P[i][1], c[2], 2.0, 2.0, 2.0)
    pts = [(x, 0, z) for x in np.arange(x0, x1 + 1, 20) for z in np.arange(z0, z1 + 1, 20)]
    return [('authored_ground', ground), ('authored_box', box)], leaves_for(pts, pad=0) | info['leaves']

# ---------------------------------------------------------------- classic course importer (prototype)
def load_obj_tris(path):
    """returns list of (attr, tri[3,3]) for the drivable polygons (attribute without bit 23)"""
    V = []; out = []; attr = 0
    for ln in open(path):
        if ln.startswith('o attr_'): attr = int(ln.split('_')[1], 16)
        elif ln.startswith('v '): V.append(tuple(map(float, ln.split()[1:4])))
        elif ln.startswith('f '):
            ix = [int(t.split('/')[0]) - 1 for t in ln.split()[1:]]
            for k in range(1, len(ix) - 1): out.append((attr, np.array([V[ix[0]], V[ix[k]], V[ix[k + 1]]])))
    return out

class HeightField:
    def __init__(self, tris, cell=8.0):
        self.t = np.array([t for a, t in tris]); self.attr = [a for a, t in tris]; self.cell = cell; self.b = collections.defaultdict(list)
        for i, t in enumerate(self.t):
            x0, z0 = np.floor(t[:, [0, 2]].min(0) / cell).astype(int); x1, z1 = np.floor(t[:, [0, 2]].max(0) / cell).astype(int)
            for x in range(x0, x1 + 1):
                for z in range(z0, z1 + 1): self.b[(x, z)].append(i)
    def at(self, x, z, yref=None):
        best = None
        for i in self.b.get((int(math.floor(x / self.cell)), int(math.floor(z / self.cell))), ()):
            a, b, c = self.t[i]
            d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-9: continue
            u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d; v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d; w = 1 - u - v
            if u < -1e-4 or v < -1e-4 or w < -1e-4: continue
            y = u * a[1] + v * b[1] + w * c[1]
            if best is None or (yref is not None and abs(y - yref) < abs(best - yref)) or (yref is None and y > best): best = y
        return best

def resample_closed(C, smooth=2):
    """closed Catmull-Rom through C, resampled to an integer number of points ~1 m apart (exactly L/n apart)."""
    n = len(C); pts = []
    for i in range(n):
        p0, p1, p2, p3 = C[(i - 1) % n], C[i], C[(i + 1) % n], C[(i + 2) % n]
        for t in np.linspace(0, 1, 24, endpoint=False):
            pts.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    pts = np.array(pts)
    for it in range(4):                                               # arc-length resampling (iterated so the chords converge to equal length)
        closed = np.vstack([pts, pts[:1]]); seg = np.linalg.norm(np.diff(closed, axis=0), axis=1); s = np.concatenate([[0], np.cumsum(seg)])
        L = s[-1]; m = int(round(L)) if it == 0 else m
        tt = np.arange(m) * (L / m)
        pts = np.stack([np.interp(tt, s, closed[:, k]) for k in range(3)], 1)
    return pts

def import_classic(csv, obj, half_width=None, centre_to=(0.0, 0.0), log=print):
    C = np.loadtxt(csv, delimiter=',', comments='#')
    tris = [t for t in load_obj_tris(obj) if not (t[0] >> 23) & 1]
    hf = HeightField(tris)
    P = resample_closed(C); n = len(P)
    D = np.roll(P, -1, 0) - np.roll(P, 1, 0); D[:, 1] = 0; D /= np.linalg.norm(D, axis=1)[:, None]
    lat0 = BT.lateral(D)
    # width + height profile from the collision mesh
    ext_l = np.zeros(n); ext_r = np.zeros(n); yc = P[:, 1].copy(); slope = np.zeros(n); miss = 0
    for i in range(n):
        y = hf.at(P[i, 0], P[i, 2], P[i, 1])
        if y is None: miss += 1
        else: yc[i] = y
        prof = {}
        for sgn in (1, -1):
            k = 0
            while k < 20:
                q = P[i] + lat0[i] * sgn * (k + 1); h = hf.at(q[0], q[2], yc[i])
                if h is None or abs(h - yc[i]) > 0.45 * (k + 1) + 0.5: break
                prof[sgn * (k + 1)] = h; k += 1
            if sgn > 0: ext_l[i] = k
            else: ext_r[i] = k
        ks = [k for k in prof if abs(k) <= 5]
        if len(ks) >= 4: slope[i] = np.polyfit(ks, [prof[k] for k in ks], 1)[0]
    def smooth(a, w):
        k = np.ones(2 * w + 1) / (2 * w + 1); return np.convolve(np.concatenate([a[-w:], a, a[:w]]), k, 'valid')
    yc = smooth(yc, 3); slope = smooth(slope, 5)
    P2 = P.copy(); P2[:, 1] = yc
    lat = lat0.copy(); lat[:, 1] = slope; lat /= np.linalg.norm(lat, axis=1)[:, None]
    wmin = np.minimum(ext_l, ext_r)
    if half_width is None: half_width = int(max(4, min(10, np.percentile(wmin, 20))))
    # centre the course on the requested point
    mid = (P2[:, [0, 2]].min(0) + P2[:, [0, 2]].max(0)) / 2; P2[:, 0] += centre_to[0] - mid[0]; P2[:, 2] += centre_to[1] - mid[1]
    step = np.linalg.norm(np.roll(P2, -1, 0) - P2, axis=1); grade = np.abs(np.roll(yc, -1) - yc) / np.maximum(step, 1e-6)
    turn = np.degrees(np.arccos(np.clip((D * np.roll(D, -1, 0)).sum(1), -1, 1)))
    rmin = 1.0 / max(np.radians(turn.max()), 1e-9)
    log('       classic course: %d source points -> %d slices, step %.3f..%.3f m, centre heights taken from the mesh on %d/%d slices' % (len(C), n, step.min(), step.max(), n - miss, n))
    log('       drivable half width found: left med %.0f (min %.0f), right med %.0f (min %.0f) -> constant half width %d used' % (np.median(ext_l), ext_l.min(), np.median(ext_r), ext_r.min(), half_width))
    log('       elevation %.1f..%.1f m, max grade %.1f%%, max bank %.1f deg, min radius %.1f m (inner edge needs radius > half width %d)' %
        (yc.min(), yc.max(), 100 * grade.max(), np.degrees(np.arctan(np.abs(slope).max())), rmin, half_width))
    x = P2[:, 0]; z = P2[:, 2]
    log('       extent x %.0f..%.0f z %.0f..%.0f (scenery tree limit +-750)' % (x.min(), x.max(), z.min(), z.max()))
    return dict(P=P2, D=D, lat=lat, start=10), half_width, dict(ext_l=ext_l, ext_r=ext_r, grade=grade, slope=slope, rmin=rmin)

def self_cross(P, min_sep=40, dist=14.0):
    """slices far apart along the lap but closer than `dist` in plan (bridges / crossings / parallel sections)"""
    idx, d = [], []
    n = len(P); XZ = P[:, [0, 2]]; hits = 0
    for i in range(0, n, 5):
        dd = np.linalg.norm(XZ - XZ[i], axis=1); j = np.arange(n); far = np.minimum(np.abs(j - i), n - np.abs(j - i)) > min_sep
        if (dd[far] < dist).any(): hits += 1
    return hits

# ---------------------------------------------------------------- steps
def main(only=''):
    def want(n): return n.startswith(only)
    LOG.append('---- build_more ----')
    sta = BT.Track('Stadium4'); sta_gfx = sta.files['master_gfx_xdata']
    des = BT.Track('Desert4') if os.path.isdir(os.path.join(TRACKS, 'Desert4')) else None

    n = 'step10_stadium_authored_walls'
    if want(n):
        t = sta.copy(); f = t.files['master_gfx_xdata']; td = TDm.parse_td(f.byid()[BT.gfx_root(f).u32(0xc)])
        surf, wi, fi = boundary_surfaces(f)
        log(n); add_walls(f, BT.td_rows(TDm.td_to_model(td)), surf, wi, fi, every=3); BT.write_track(n, t)
    n = 'step11_stadium_scene_ground_box'
    if want(n):
        t = sta.copy(); f = t.files['master_gfx_xdata']
        s = scene11.parse11(f.byid()[BT.gfx_root(f).u32(4)]); lv = {(nd.gx - 1, nd.gz - 1) for nd in s.nodes if nd.leafp}
        log(n)
        ground = meshgen.ground_quads(-200, -200, 200, 200, -2.5, 20.0)                # below Stadium's lowest road point
        box = meshgen.box_quads(0.0, 0.5, 120.0, 2.0, 2.0, 2.0)                        # on the infield side of the start straight
        add_meshes(f, sta_gfx, [('authored_ground', ground), ('authored_box', box)], lv)
        d = BT.gc(f, t); BT.write_track(n, t, note='| %d unreferenced chunks dropped' % d); BT.check_authored(n, t)
    for slot, src, centre, suffix in (('Stadium4', sta, (0.0, 0.0, 450.0), ''), ('Desert4', des, (0.0, 0.0, 600.0), '_desert4')):
        if src is None: continue
        n = 'step12_flat_loop_walls' + suffix
        if want(n):
            surf, wi, fi = boundary_surfaces(src.files['master_gfx_xdata'])
            info = {}; t, d, pat = BT.authored_loop(src, centre, True, info=info); f = t.files['master_gfx_xdata']
            log(n); add_walls(f, BT.td_rows(info['model']), surf, wi, fi); BT.write_track(n, t); BT.check_authored(n, t)
        n = 'step13_flat_loop_walls_ground_box' + suffix
        if want(n):
            surf, wi, fi = boundary_surfaces(src.files['master_gfx_xdata'])
            info = {}; t, d, pat = BT.authored_loop(src, centre, True, info=info); f = t.files['master_gfx_xdata']
            log(n); add_walls(f, BT.td_rows(info['model']), surf, wi, fi)
            sets, lv = loop_scenery(info); add_meshes(f, sta_gfx, sets, lv)
            BT.write_track(n, t); BT.check_authored(n, t)
    if des is not None:
        csv = os.path.join(os.path.dirname(WORK), 'classic', 'obj', 'src_course1_centreline.csv'); obj = csv.replace('centreline.csv', 'collision.obj')
        for n, walls in (('step14_classic_course1_desert4', False), ('step15_classic_course1_walls_desert4', True)):
            if not want(n) or not os.path.exists(csv): continue
            log(n)
            road, hw, st = import_classic(csv, obj, log=log)
            log('       plan-view near-crossings (slices > 40 m apart along the lap but < 14 m apart): %d sample points' % self_cross(road['P']))
            info = {}; t, d, pat = BT.authored_loop(des, None, True, half_width=hw, road=road, info=info); f = t.files['master_gfx_xdata']
            if walls:
                surf, wi, fi = boundary_surfaces(des.files['master_gfx_xdata']); add_walls(f, BT.td_rows(info['model']), surf, wi, fi, terrain=True)
            BT.write_track(n, t); BT.check_authored(n, t)
    open(os.path.join(OUT, 'build_log.txt'), 'a').write('\n'.join(LOG[LOG.index('---- build_more ----'):]) + '\n')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '')
