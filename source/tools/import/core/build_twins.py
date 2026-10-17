"""Desert4 twins of the isolating ladder steps 0-6, 10, 11 (folders <step>_desert4\\Desert4).
    python build_twins.py [name prefix]"""
import os, sys, math
import numpy as np
from common import *
import sbfw, trackdeform as TDm, scene11, meshgen
import build_testtrack as BT, build_more as BM
from build_testtrack import log, LOG

def main(only='', slot='Desert4', suffix='_desert4'):
    def want(n): return n.startswith(only)
    LOG.append('---- build_twins %s ----' % slot)
    src = BT.Track(slot); sta = BT.Track('Stadium4'); sta_gfx = sta.files['master_gfx_xdata']
    def td_of(t):
        f = t.files['master_gfx_xdata']; return TDm.parse_td(f.byid()[BT.gfx_root(f).u32(0xc)])

    n = 'step0_rewrite_identical' + suffix
    if want(n):
        same = [sbfw.write_raw(f.chunks, f.first, f.tail, f.hdr, 'keep') == f.raw for f in src.files.values()]
        BT.write_track(n, src, layout='keep', note='| decompressed bytes identical to the original: %s' % all(same))
    n = 'step1_writer_layout' + suffix
    if want(n): BT.write_track(n, src.copy(), layout='auto')
    n = 'step2_authored_aimap' + suffix
    if want(n):
        t = src.copy(); BT.set_aimap(t.files['master_xdata'], BT.aimap_cells(BT.td_rows(TDm.td_to_model(td_of(t)))))
        BT.write_track(n, t); BT.check_authored(n, t)
    n = 'step3_no_boundary' + suffix
    if want(n):
        t = src.copy(); BT.drop_boundary(t.files['master_gfx_xdata']); BT.write_track(n, t)
    n = 'step4_authored_scene' + suffix
    if want(n):
        t = src.copy(); f = t.files['master_gfx_xdata']
        s = scene11.parse11(f.byid()[BT.gfx_root(f).u32(4)]); lv = {(nd.gx - 1, nd.gz - 1) for nd in s.nodes if nd.leafp}
        BT.set_scene(f, lv, []); d = BT.gc(f, t); BT.write_track(n, t, note='| %d unreferenced chunks dropped' % d); BT.check_authored(n, t)
    n = 'step5_authored_road_surface' + suffix
    if want(n):
        t = src.copy(); f = t.files['master_gfx_xdata']; td = td_of(t); m = TDm.td_to_model(td); pat = BT.uniform_pattern(td)
        allp = np.concatenate([s['verts']['pos'] for s in m['slices'][1:]])
        for s in m['slices'][1:]:
            v = s['verts']; v['surf'] = np.frombuffer(pat['surf'], np.uint8); v['w1c'] = pat['w1c']
            for fld in ('w20', 'w24', 'w28', 'w2c'): v[fld] = pat['w']
        m['rec11'] = [pat['rec'] + bytes([0])] * len(m['rec11'])
        m['pages'] = [BT.page_for(allp, texa=td.pages[0][0], texb=td.pages[0][1])]
        BT.set_td(f, m); d = BT.gc(f, t); BT.write_track(n, t, note='| pattern surf %s weights %x' % (pat['surf'].hex(), pat['w'])); BT.check_authored(n, t)
    n = 'step6_added_spline' + suffix
    if want(n):
        t = src.copy(); td = td_of(t)
        cen = np.array([td.verts[i]['pos'][-td.off[i]] for i in range(1, td.n + 1)], float)
        BT.add_spline(t.files['master_xdata'], cen); BT.write_track(n, t, note='| the original spline + pace notes are REPLACED'); BT.check_authored(n, t)
    n = 'step10_authored_walls' + suffix
    if want(n):
        t = src.copy(); f = t.files['master_gfx_xdata']; surf, wi, fi = BM.boundary_surfaces(f)
        log(n); BM.add_walls(f, BT.td_rows(TDm.td_to_model(td_of(t))), surf, wi, fi, every=3, terrain=True) if 'terrain' in BM.add_walls.__code__.co_varnames else BM.add_walls(f, BT.td_rows(TDm.td_to_model(td_of(t))), surf, wi, fi, every=3)
        BT.write_track(n, t)
    n = 'step11_scene_ground_box' + suffix
    if want(n):
        t = src.copy(); f = t.files['master_gfx_xdata']; td = td_of(t)
        s = scene11.parse11(f.byid()[BT.gfx_root(f).u32(4)]); lv = {(nd.gx - 1, nd.gz - 1) for nd in s.nodes if nd.leafp}
        allp = np.concatenate([td.verts[i]['pos'] for i in range(1, td.n + 1)])
        x0, z0 = np.floor((allp[:, [0, 2]].min(0) - 60) / 20) * 20; x1, z1 = np.ceil((allp[:, [0, 2]].max(0) + 60) / 20) * 20
        ymin = float(allp[:, 1].min()) - 2.5
        root = t.files['master_xdata'].chunks[-1]; start = root.u32(0x2c) or 1
        i = max(1, min(td.n, start)); v = td.verts[i]['pos']; d = v[1] - v[0]; d /= np.linalg.norm(d)
        c = v[0] - d * 4.0                                              # 4 m outside the first road vertex of the start slice
        log(n)
        sets = [('authored_ground', meshgen.ground_quads(float(x0), float(z0), float(x1), float(z1), ymin, 20.0)),
                ('authored_box', meshgen.box_quads(float(c[0]), float(v[0][1]) + 0.5, float(c[2]), 2.0, 2.0, 2.0))]
        BM.add_meshes(f, sta_gfx, sets, lv | BM.leaves_for([(x, 0, z) for x in np.arange(x0, x1 + 1, 20) for z in np.arange(z0, z1 + 1, 20)], pad=0))
        d2 = BT.gc(f, t); BT.write_track(n, t, note='| ground at y=%.1f, box beside start slice %d at (%.0f, %.0f, %.0f)' % (ymin, i, c[0], v[0][1] + 0.5, c[2])); BT.check_authored(n, t)
    open(os.path.join(OUT, 'build_log.txt'), 'a').write('\n'.join(LOG[LOG.index('---- build_twins %s ----' % slot):]) + '\n')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '')
