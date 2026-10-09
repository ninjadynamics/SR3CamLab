"""step24: the classic course with NO 1995 tile left - every surface gets SR3 art (see allsr3.py, ../../13_retexture.md).
    python build_allsr3.py
Mapping per classic tile comes from ../retex/tile_labels.csv (column class):
    rock / grass / dirt / asphalt / cobbles / stone_wall / plaster / roof / gravel : tileable SR3 texture, box UV in metres
    house_plaster / house_stone / house_brick / church / arcade : wall cut into bays x storeys, one composed SR3 bay per cell
    sign : SR3 sponsor boards            tree_wall : SR3 tree row
    crown / tree / bare / ivy / trunk / lamp / fence : SR3 cut-out laid out like the classic tile, classic UVs kept"""
import os, sys, struct, collections
import numpy as np
from common import *
import sbfw, meshgen, retex, classic_tex, allsr3 as A3
import build_testtrack as BT, build_more as BM, build_classic as BC
log = BT.log; LOG = BT.LOG
METRE = ('rock', 'grass', 'dirt', 'asphalt', 'cobbles', 'stone_wall', 'plaster', 'roof', 'gravel', 'sand', 'water', 'wood', 'brick_wall')
FACADE = ('house_plaster', 'house_stone', 'house_brick', 'church', 'arcade', 'house_front')
CUT = ('crown', 'tree', 'bare', 'ivy', 'trunk', 'lamp', 'fence', 'foliage', 'bush')
REPEAT = {'rock': 7.0, 'grass': 4.0, 'dirt': 4.0, 'roof': 2.2, 'flat': 3.0}

def quad(P):
    P = [np.array(p, float) for p in P]
    return P if len(P) == 4 else P + [P[2]]

def wall_frame(P):
    """corners rotated (winding kept) so that q0 -> q1 is the bottom edge; None if the face is not an upright wall quad"""
    if len(P) != 4: return None
    q = np.array(P, float); n = np.cross(q[1] - q[0], q[2] - q[0]); ln = np.linalg.norm(n)
    if ln < 1e-9 or abs(n[1] / ln) > 0.35: return None
    k = int(np.argmin([q[i][1] + q[(i + 1) % 4][1] for i in range(4)])); q = np.roll(q, -k, 0)
    def vert(a, b):
        d = b - a; l = np.linalg.norm(d); return l > 1e-6 and abs(d[1]) / l > 0.85
    if not (vert(q[0], q[3]) and vert(q[1], q[2])): return None
    W = (np.linalg.norm((q[1] - q[0])[[0, 2]]) + np.linalg.norm((q[2] - q[3])[[0, 2]])) / 2; H = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    return q, W, H

def cells(q, nb, nf):
    """bilinear nb x nf grid of a wall quad -> [(i, j, corners in the quad's own order)] ; j = 0 is the bottom row"""
    def pt(a, b): return (q[0] * (1 - a) + q[1] * a) * (1 - b) + (q[3] * (1 - a) + q[2] * a) * b
    return [(i, j, [pt(i / nb, j / nf), pt((i + 1) / nb, j / nf), pt((i + 1) / nb, (j + 1) / nf), pt(i / nb, (j + 1) / nf)]) for i in range(nb) for j in range(nf)]
CELL_UV = [(1.0, 1.0), (0.0, 1.0), (0.0, 0.0), (1.0, 0.0)]            # the classic faces run clockwise seen from the front: bottom edge goes right -> left ; v runs down
SCALE = 2.0                                                           # the 1995 town is built about twice life size (lamp posts 8 m, three-storey houses 25 m)

def buildings(faces, lab):
    """union of facade faces that share a corner -> building number per face index"""
    par = {}
    def find(x):
        while par.setdefault(x, x) != x: par[x] = par[par[x]]; x = par[x]
        return x
    key = lambda p: (round(p[0] * 2), round(p[1] * 2), round(p[2] * 2)); out = {}
    for i, fc in enumerate(faces):
        if lab.get(fc[0], ('',))[0] in FACADE:
            ks = [find(key(p)) for p in fc[2]]
            for k in ks[1:]: par[find(k)] = find(ks[0])
    for i, fc in enumerate(faces):
        if lab.get(fc[0], ('',))[0] in FACADE: out[i] = find(key(fc[2][0]))
    return out

def smooth_axes(faces, lab):
    """projection axis per rock face from a normal smoothed over the faces that share its corners (two passes):
    1 = from above (x, z), 0 = along x (u = z), 2 = along z (u = x). Neighbouring faces of one rock surface then share
    an axis, so the texture no longer turns from triangle to triangle."""
    idx = [i for i, fc in enumerate(faces) if lab.get(fc[0], ('',))[0] == 'rock' and len(fc[2]) >= 3]; key = lambda p: (round(p[0] * 4), round(p[1] * 4), round(p[2] * 4))
    N = {}
    for i in idx:
        P = np.array(faces[i][2]); n = np.cross(P[1] - P[0], P[2] - P[0])
        if len(P) == 4: n = n + np.cross(P[2] - P[0], P[3] - P[0])
        N[i] = n                                                       # length = area weight
    for _ in range(3):
        acc = collections.defaultdict(lambda: np.zeros(3))
        for i in idx:
            for p in faces[i][2]: acc[key(p)] += N[i]
        for i in idx:
            s = sum(acc[key(p)] for p in faces[i][2]); l = np.linalg.norm(s); a = np.linalg.norm(N[i])
            if l > 1e-9: N[i] = s / l * a
    out = {}
    for i in idx:
        n = N[i] / max(np.linalg.norm(N[i]), 1e-9); out[i] = 1 if abs(n[1]) > 0.85 else (0 if abs(n[0]) > abs(n[2]) else 2)
    return out

def axis_uv(q, ax, repeat):
    q = np.array(q, float); uv = q[:, [0, 2]] if ax == 1 else (np.stack([q[:, 2], -q[:, 1]], 1) if ax == 0 else np.stack([q[:, 0], -q[:, 1]], 1))
    uv = uv / repeat; uv -= np.floor(uv.min(0) + 1e-6); return np.clip(uv, 0, 1.999)

def class_colour(faces, lab, tiles, pages, cls):
    """area-weighted mean colour of the classic tiles of one class (target for the rock tint)"""
    import course
    st = course.tile_stats(faces); tot = np.zeros(3); w = 0.0
    for name, s in st.items():
        m = tiles.get(name)
        if m and lab.get(name, ('',))[0] == cls:
            t = classic_tex.tile(pages, m)
            if t is not None: tot += classic_tex.tile_rgb(t, m).reshape(-1, 3).mean(0) * s['area']; w += s['area']
    return tot / w if w else np.array([150.0, 130.0, 105.0])

def add_scenery_all(f, sta_gfx, faces, lv, rd):
    BM.import_closure(f, sta_gfx, [BM.TPL_MAT]); sby = sta_gfx.byid(); tpl_mesh = sby[BM.TPL_MESH]; tpl_tex = sby[BM.TPL_TEX]; tpl_mat = f.get(BM.TPL_MAT)
    tpl_tex5 = next(c for c in sta_gfx.kinds(4) if c.data[48 + 80:48 + 84] == b'DXT5' and struct.unpack_from('<I', c.data, 40)[0] == 1)
    ccw = meshgen.winding_sign(tpl_mesh)[0] > 0
    lab = retex.labels(); pages = classic_tex.load_pages(); tiles = classic_tex.usable(pages, classic_tex.materials()); pal = None
    import m2colour; pal = m2colour.palette()
    out = collections.defaultdict(list); spec = {}; stat = collections.Counter()
    def put(key, sp, P, UV): spec[key] = sp; out[key].append((key, None, [tuple(p) for p in P], [tuple(u) for u in UV]))
    def metre(cls, trk, tid, P):
        rpt = REPEAT.get(cls, retex.REPEAT_M)
        for q in retex.subdivide(P, 2 * rpt - 0.5): put(('tex', trk, tid), ('chunk', trk, tid, 'given'), q, retex.plane_uv(q, rpt))
        stat[cls] += 1
    rock_axis = smooth_axes(faces, lab); rock_rgb = class_colour(faces, lab, tiles, pages, 'rock')
    bld = buildings(faces, lab); flat = A3.FLAT; grass = next(((v[1], v[2]) for v in lab.values() if v[0] == 'grass' and v[2]), ('Lakeside4', 0xd8dcd068))
    bcount = collections.Counter()
    for fi, (name, sec, P, UV) in enumerate(faces):
        cls, trk, tid = lab.get(name, ('flat', '', None)); m = tiles.get(name); P4 = quad(P)
        if m is None: cls = 'flat'
        if cls == 'rock':
            rk = A3.ROCKS[A3.hsh(name) % len(A3.ROCKS)]; ax = rock_axis.get(fi, 1)
            for q in retex.subdivide(P4, 2 * REPEAT['rock'] - 0.5): put(('rock', rk[0], rk[1]), ('rockimg', 'given'), q, axis_uv(q, ax, REPEAT['rock']))
            stat['rock'] += 1
        elif cls in METRE and tid is not None: metre(cls, trk, tid, P4)
        elif cls == 'plaster_wall':                                 # plain painted wall tile: sloping faces are roofs, the rest tinted SR3 plaster
            q0 = np.array(P4); nn = np.cross(q0[1] - q0[0], q0[2] - q0[0]); ny = abs(nn[1]) / max(np.linalg.norm(nn), 1e-9)
            if 0.25 < ny < 0.92: rf = retex.SR3_FOR_CLASS['roof']; metre('roof', rf[0], rf[1], P4)
            else:
                tint = A3.pastel_for(pal[m['cb']], A3.hsh(name))
                for q in retex.subdivide(P4, 11.5): put(('wall', tint), ('wallimg', 'given'), q, retex.box_uv(q, 6.0))
                stat['painted walls'] += 1
        elif cls in ('window', 'door'): put(('open', cls, name), ('openimg', 'tile', cls, name), P, UV); stat['windows and doors'] += 1
        elif cls in FACADE:
            wf = wall_frame(P4); b = bld.get(fi, 0); styles = A3.CLASS_STYLES[cls]; st = styles[A3.hsh(b, name) % len(styles)]; S = A3.STYLES[st]
            tint = A3.pastel_for(pal[m['cb']], A3.hsh(b)) if S.get('tint') else 'plain'
            if wf is None or wf[2] < 3.5 or wf[1] < 3.0:               # gables, slivers, sloping pieces: plain wall in metres
                for q in retex.subdivide(P4, 5.5 * SCALE): put(('fac', st, 'pl', tint), ('img', 'given'), q, retex.box_uv(q, 3.0 * SCALE))
                stat['wall pieces without openings'] += 1; continue
            q, W, H = wf; nf = max(1, int(round(H / (SCALE * S['floor']))))
            if H / nf > 7.5: nf += 1                                  # no storey taller than 7.5 m (windows were blown up on 8..9 m walls)
            ch = H / nf; nb = max(1, int(round(W / max(SCALE * S['bay'], 0.85 * ch))))
            if W / nb > 1.5 * ch: nb = int(np.ceil(W / (1.5 * ch)))
            door = A3.hsh(b, fi) % nb if A3.hsh(fi) % 3 != 0 else -1
            for i, j, c in cells(q, nb, nf):
                kind = 'up' if j > 0 else ('gd' if i == door else 'gw')
                put(('fac', st, kind, tint), ('img', 'given'), c, CELL_UV)
            stat['facade walls'] += 1; bcount[st] += 1
        elif cls == 'sign':
            wf = wall_frame(P4)
            if wf is None: metre('flat', flat[0], flat[1], P4); continue
            q, W, H = wf; n = max(1, int(round(W / (2.6 * H)))); hv = min(0.5, H / (W / n))            # logo files are 2 : 1 ; show a centred band
            v0, v1 = 0.5 + hv, 0.5 - hv
            for i, j, c in cells(q, n, 1):
                bd = A3.BOARDS[(A3.hsh(round(q[0][0]), round(q[0][2])) + i) % len(A3.BOARDS)]
                put(('tex', bd[0], int(bd[1], 16)), ('chunk', bd[0], int(bd[1], 16), 'given'), c, [(1.0, v0), (0.0, v0), (0.0, v1), (1.0, v1)])
            stat['sponsor boards'] += n
        elif cls == 'tree_wall':
            r = retex.tree_uv(P, min_h=2.5, **A3.TREE_ROW_UV)
            if r is None: metre('grass', grass[0], grass[1], P4)
            else: put(('cut', 'tree_row'), ('chunk', A3.TREE_ROW[0], A3.TREE_ROW[1], 'given', True), r[0], r[1]); stat['tree row boards'] += 1
        elif cls in CUT:
            key = ('cut', cls, name if cls in ('lamp', 'fence') else (m['w'], m['h']))
            put(key, ('cutimg', 'tile', cls, name), P, UV); stat['cut-out boards: ' + cls] += 1
        else: metre('flat', flat[0], flat[1], P4)
    # road decals: paved strips in SR3 cobbles, paint = SR3 line texels behind the classic paint mask
    hf = BC.road_height(rd); by_tile = collections.defaultdict(list)
    for fc in BC.DROPPED: by_tile[fc[0]].append(fc)
    cob = next(((v[1], v[2]) for v in lab.values() if v[0] == 'cobbles' and v[2]), None)
    for name, fl in sorted(by_tile.items()):
        m = tiles.get(name); cls = lab.get(name, ('',))[0]
        if not m: continue
        if cls == 'asphalt':
            t = classic_tex.tile(pages, m); l = m2colour.lumaram()[(m.get('luma', 0) << 7) + (t.astype(np.int32) << 3)]; mark = l >= 58
            if not 0.003 < mark.mean() < 0.5: continue
            for fc in BC.drape(fl, hf, 0.03): put(('paint', name), ('paintimg', 'tile', mark), fc[2], fc[3])
            stat['road paint faces'] += len(fl)
        elif cls in ('cobbles', 'pavement') and cob:
            for fc in BC.drape(fl, hf, 0.025): put(('tex', cob[0], cob[1]), ('chunk', cob[0], cob[1], 'given'), fc[2], retex.box_uv(np.array(fc[2]), 3.0))
            stat['paved strip faces'] += len(fl)
    # chunks
    new = []; ids = []; nv = 0; src = {}; ntex = collections.Counter(); k = 0
    for key in sorted(out, key=repr):
        sp = spec[key]; fl = out[key]; mid = 0xc1b10000 + k; tid = 0xc1b00000 + k; k += 1; cut = False
        if sp[0] == 'chunk':
            trk, cid = sp[1], sp[2]; cut = len(sp) > 4
            if trk not in src: src[trk] = sbfw.read_sbf(track_files(os.path.join(TRACKS, trk))['master_gfx_xdata']).byid()
            if cid not in {c.id for c in f.chunks} and cid not in {c.id for c in new}:
                tx = src[trk][cid].copy(); tx.gap = None; new.append(tx)
            new.append(meshgen.clone_material(tpl_mat, mid, cid, cutout=cut)); ntex['SR3 texture chunks copied'] += 1
        else:
            if sp[0] == 'img': rgb = A3.facade_tex(key[1], key[2], key[3]); hole = None
            elif sp[0] == 'wallimg': rgb = A3.wall_tex(key[1]); hole = None
            elif sp[0] == 'openimg':
                m = tiles[sp[3]]; t = classic_tex.tile(pages, m); rgb, hole = A3.opening_tex(sp[2], sp[3], (m['h'], m['w']), (t != 15) if m['alpha'] else None)
            elif sp[0] == 'rockimg': rgb = A3.tinted_texture(key[1], key[2], rock_rgb, A3.ROCK_TINT); hole = None
            elif sp[0] == 'cutimg':
                m = tiles[sp[3]]; t = classic_tex.tile(pages, m); rgb, hole = A3.cutout(sp[2], (m['h'], m['w']), (t != 15) if sp[2] in ('lamp', 'fence') else None)
            else: rgb, hole = A3.cutout('paint', None, sp[2])
            if hole is not None: new += [BC.make_texture_dxt5(tpl_tex5, tid, rgb, hole), meshgen.clone_material(tpl_mat, mid, tid, cutout=sp[0] != 'paintimg', blend=sp[0] == 'paintimg')]; ntex['composed cut-out textures'] += 1
            else: new += [BC.make_texture(tpl_tex, tid, rgb, None), meshgen.clone_material(tpl_mat, mid, tid)]; ntex['composed facade textures'] += 1
        for part in range(0, len(fl), 10000):
            v, nq, cl = BC.faces_to_mesh(fl[part:part + 10000], 'tile' if sp[0] in ('cutimg', 'paintimg', 'openimg') else 'given'); nv += len(v)
            msh = meshgen.clone_mesh(tpl_mesh, 0xc1b70000 + len(ids), v, meshgen.quads_to_strip(nq, ccw), mid, 'allsr3_%d' % len(ids)); new.append(msh); ids.append(msh.id)
    f.chunks[len(f.chunks) - 1:len(f.chunks) - 1] = new
    allp = np.array([p for fl in out.values() for fc in fl[::3] for p in fc[2]]); BT.set_scene(f, lv | BM.leaves_for(allp[::5], pad=0), ids)
    log('       all-SR3 scenery: %d meshes, %d vertices, %d materials %s' % (len(ids), nv, k, dict(ntex)))
    log('       faces by treatment: %s' % dict(stat)); log('       facade walls per style: %s' % dict(bcount))

def main():
    LOG.append('---- build_allsr3 ----'); n = 'step24_classic_all_sr3_desert4'
    des = BT.Track('Desert4'); sta_gfx = BT.Track('Stadium4').files['master_gfx_xdata']; surf, wi, fi = BM.boundary_surfaces(des.files['master_gfx_xdata'])
    log('importing road'); rd = BC.import_road(); log(n)
    BC.TARMAC = A3.ROAD_TARMAC[1:]; BC.GRAVEL = A3.ROAD_DIRT[1:]
    t, model, lv = BC.build_road_track(des, rd); f = t.files['master_gfx_xdata']
    lk = sbfw.read_sbf(track_files(os.path.join(TRACKS, A3.ROAD_TARMAC[0]))['master_gfx_xdata']).byid(); have = {c.id for c in f.chunks}
    for cid in A3.ROAD_TARMAC[1:] + A3.ROAD_DIRT[1:]:
        if cid not in have: c = lk[cid].copy(); c.gap = None; f.chunks.insert(0, c)
    log('       road layers: Lakeside_Tarmac %08x + %08x on the tarmac cells, Lakeside_Dirt %08x + %08x on the loose cells (4 texture chunks copied from Lakeside4)' % (A3.ROAD_TARMAC[1:] + A3.ROAD_DIRT[1:])); BM.add_walls(f, BT.td_rows(model), surf, wi, fi, terrain=True)
    faces = BC.load_visual(rd); add_scenery_all(f, sta_gfx, faces, lv, rd)
    d = BT.gc(f, t); BT.write_track(n, t, note='| %d unreferenced chunks dropped' % d); BT.check_authored(n, t)
    open(os.path.join(OUT, 'build_log.txt'), 'a').write('\n'.join(LOG[LOG.index('---- build_allsr3 ----'):]) + '\n')

if __name__ == '__main__':
    main()
