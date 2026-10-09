"""Static checks of a built classic step that an in-game test depends on.   python check_classic.py <game> <course> [variant]
Reads the BUILT files back (road from the TrackDeform chunk, scenery meshes, start values) and compares with the classic data."""
import os, sys, struct, json
import numpy as np
import course
from common import *
import sbfw, trackdeform as TDm, scene11, meshgen

def main(game, crs, variant='classic'):
    cfg = course.use(game, crs); import build_classic as BC, build_more as BM
    name = 'step%02d_%s_%s_desert4' % (cfg['steps'][variant], cfg['name'], variant); tf = track_files(os.path.join(OUT, name, 'Desert4')); ok = True
    def say(c, t):
        nonlocal ok; ok &= bool(c); print('   %s %s' % ('ok  ' if c else 'WARN', t))
    print(name); f = sbfw.read_sbf(tf['master_gfx_xdata']); by = f.byid(); r = f.chunks[-1]; td = TDm.parse_td(by[r.u32(0xc)]); n = td.n
    cen, lat, lo, hi = TDm.road_frame(td); xf = json.load(open(BC.XFORM)); wid = hi - lo
    def lateral(pts):
        idx, d = nearest2d(cen[:, [0, 2]], pts[:, [0, 2]], cell=8.0); return idx, ((pts[:, [0, 2]] - cen[idx][:, [0, 2]]) * lat[idx][:, [0, 2]]).sum(1)
    print('   road width %.1f..%.1f m (median %.1f); left edge %.1f..%.1f, right edge %.1f..%.1f' % (wid.min(), wid.max(), np.median(wid), lo.min(), lo.max(), hi.min(), hi.max()))
    # 1 road against the classic collision
    tris = [(a, t * np.array([1, 1, BC.ZS]) + np.array([xf['ox'], 0, xf['oz']])) for a, t in BM.load_obj_tris(BC.COL)]
    road = [(a, t) for a, t in tris if not (a >> 23) & 1 and ((a >> 16) & 15) != 6]; pts = np.array([t.mean(0) for a, t in road]); idx, c = lateral(pts); ins = (c >= lo[idx]) & (c <= hi[idx])
    dy = np.abs(pts[:, 1] - cen[idx, 1]); w = np.array([0.5 * np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0])) for a, t in road])
    say((w[ins].sum() / w.sum()) > 0.97, 'classic drivable polygons (no bank flag, not verge): %.0f%% of their area lies inside the SR3 road; %.0f%% is beyond its edges' % (100 * w[ins].sum() / w.sum(), 100 * w[~ins].sum() / w.sum()))
    near = ins & (np.abs(c) < 3.0)
    say(np.percentile(dy[near], 95) < 0.6, 'height of the SR3 road centre against those polygons within 3 m of the centre line: median %.2f m, 95%% %.2f m' % (np.median(dy[near]), np.percentile(dy[near], 95)))
    # 2 scenery intruding on the road
    s = scene11.parse11(by[r.u32(4)]); bad = 0; tot = 0; worst = []
    for mid in s.nodes[0].meshes:
        m = meshgen.parse_mesh(by[mid]); P = m['verts']['p'][:, :3][np.asarray(m['idx'], np.int64)[(6 * np.arange((len(m['idx']) + 2) // 6))[:, None] + np.arange(4)]].astype(float); cq = P.mean(1); tot += len(cq)
        i2, c2 = lateral(cq); h = cq[:, 1] - cen[i2, 1]; up = np.ptp(P[:, :, 1], axis=1) > 0.5
        k = (c2 > lo[i2] + 1.5) & (c2 < hi[i2] - 1.5) & (h > 0.15) & (h < 3.0) & up; bad += int(k.sum()); worst += [int(x) for x in i2[k][:5]]
    say(bad < 30, 'upright scenery quads standing inside the road (seen, not collided with): more than 1.5 m from the edge, 0.15..3 m above the centre: %d of %d%s' % (bad, tot, (' near slices %s' % sorted(set(worst))[:12]) if bad else ''))
    # 2b z-fighting: drawn quads that lie in the same plane (3 degrees, closer than 8 mm) and overlap; decal height above the SR3 road
    import layers, build_classic as BC2
    quads = []; dec = []
    for mid in s.nodes[0].meshes:
        m = meshgen.parse_mesh(by[mid]); P = m['verts']['p'][:, :3][np.asarray(m['idx'], np.int64)[(6 * np.arange((len(m['idx']) + 2) // 6))[:, None] + np.arange(4)]].astype(float); isdec = b'road_decal' in by[mid].data[m['rest']:]
        for q in P: quads.append(('m%08x' % mid, '', [tuple(x) for x in q], None))
        if isdec: dec.append(P)
    pr, _, _ = layers.pairs_of(quads, 'plane', cell=2.0, tol=0.008)
    say(len(pr) == 0, 'z-fighting check: %d pairs of drawn scenery quads are coplanar (closer than 8 mm) and overlap, of %d quads%s' % (len(pr), len(quads), (' e.g. near %s' % [tuple(round(v) for v in quads[i][2][0]) for i, j in list(pr)[:4]]) if pr else ''))
    if dec:
        D = np.concatenate(dec).reshape(-1, 3); i3, c3 = lateral(D); on = (c3 > lo[i3] + 0.3) & (c3 < hi[i3] - 0.3)
        col = {}
        def road_y(pts, idx, c):                                           # bilinear height of the SR3 road under a point
            out = np.full(len(pts), np.nan)
            for q in range(len(pts)):
                i = idx[q]; d = pts[q, [0, 2]] - cen[i, [0, 2]]; fwd = np.array([-lat[i, 2], lat[i, 0]]); a = float(d @ fwd)
                j = (i + (1 if a >= 0 else -1)) % n; fa = min(abs(a), 1.0); ys = []
                for sl_ in (i, j):
                    if sl_ not in col: v = td.verts[sl_ + 1]['pos'].astype(float); col[sl_] = (((v - cen[sl_]) @ lat[sl_]), v[:, 1])
                    xs, yy = col[sl_]; ys.append(float(np.interp(c[q], xs, yy)))
                out[q] = ys[0] * (1 - fa) + ys[1] * fa
            return out
        sel = np.flatnonzero(on)[::7]; gap = D[sel, 1] - road_y(D[sel], i3[sel], c3[sel])
        say(np.percentile(gap, 1) > 0.015, 'road decals above the SR3 road surface (every 7th decal corner on the road, %d points): min %.3f m, 1%% %.3f m, median %.3f m, max %.3f m' % (len(sel), gap.min(), np.percentile(gap, 1), np.median(gap), gap.max()))
    # 3 start, grid, splits, notes
    x = sbfw.read_sbf(tf['master_xdata']); xr = x.chunks[-1]; start, direction = struct.unpack_from('<ii', xr.data, 0x2c); grid = struct.unpack_from('<16i', xr.data, 0x34)
    say(direction == 1 and 0 <= start < n, 'start slice %d of %d, direction %+d' % (start, n, direction))
    cols = [grid[2 * k + 1] for k in range(8)]; sl = [(start - grid[2 * k]) % n for k in range(8)]
    say(all(lo[sl[k] - 1] + 1 <= cols[k] <= hi[sl[k] - 1] - 1 for k in range(8)) and all(0 < grid[2 * k] < 60 for k in range(8)), 'grid: slices %s columns %s (all at least 1 m inside the road edges, behind the start slice)' % (sl, cols))
    gp = os.path.join(os.path.dirname(WORK), 'classic', 'courses', game, cfg.get('gameplay', ''), 'gameplay.json')
    if os.path.exists(gp):
        g = json.load(open(gp)); hd = g['direction']['start_heading']; t = cen[(start + 5) % n] - cen[start]; t = t[[0, 2]] / np.linalg.norm(t[[0, 2]])
        cs = float(t @ np.array([hd[0], -hd[-1]]))                                # JSON axes (x, y, -gameZ); SR3 z = game z
        say(cs > 0.8, 'driving direction at the start (%.2f, %.2f) against the classic start heading %s: cos %.2f' % (t[0], t[1], hd, cs))
        gpos = np.array([[p[0] + xf['ox'], p[1], BC.ZS * p[2] + xf['oz']] for p in g['start']['grid']]); me = np.array([cen[sl[k] - 1] + lat[sl[k] - 1] * cols[k] for k in range(8)])
        dm = [float(np.hypot(me[:, 0] - q[0], me[:, 2] - q[2]).min()) for q in gpos]; say(max(dm) < 4, 'distance from each classic grid car to the nearest SR3 grid position: %s m' % [round(v, 1) for v in dm])
    import pacenotes as PN
    PN.TRACKS = OUT; P, M, _ = PN.read(os.path.join(name, 'Desert4')); sp = [m['start'] for m in M if (m['a'], m['b']) == (0, 5)]; nt = [m['start'] for m in M if m['props']]
    say(sp == sorted(sp) and all(0 <= v < 1 for v in sp), '%d sector splits in order at lap fractions %s' % (len(sp), [round(v, 3) for v in sp]))
    say(nt == sorted(nt), '%d pace notes, in order' % len(nt))
    say(r.u32(0x34) != 0 and r.u32(8) != 0, 'boundary BSP present (corridor 0.5 m inside both SR3 road edges)')
    print('RESULT', 'no warnings' if ok else 'see WARN lines'); return ok

if __name__ == '__main__':
    main(*sys.argv[1:4])
