"""Finer ladder for the ROAD (TrackDeform) on Desert4, after step5 crashed in the game at 0x5D2D3F.
Cause found by disassembly (04_trackdeform_road.md, "Overlay page count"): a road whose batch records all use overlay
page 0 gets a page count of 0. Every step is the ORIGINAL Desert4 with exactly one thing changed.
    python build_road_ladder.py
step5a_identity_desert4            parser -> model -> writer, nothing changed (TrackDeform bytes identical). Expect: Desert4.
step5b_one_page_only_desert4       ONLY the overlay pages: all batch records -> page 0, page table = 1 page (Desert's first).
                                   Expect: CRASH like step5 (0x5D2D3F). This is the control that proves the cause.
step5c_two_equal_pages_desert4     as 5b but the same page written twice, second half of the batch records -> page 1.
                                   Expect: loads; the road's painted detail (overlay) is wrong / stretched, driving normal.
step5d_blob_only_desert4           ONLY the height blob: all 0xBF (undeformed). Expect: Desert4 without pre-baked ruts.
step5e_uniform_cells_desert4       ONLY the cells: every cell = the most common uniform cell, each slice keeps its own batch
                                   record and page. Expect: loads; whole road one surface (sand on dry mud).
step5f_uniform_batch_desert4       5e + every batch record = the pattern's (pages kept per record). Expect: as 5e.
step5_authored_road_surface_desert4  REBUILT with the fix (uniform cells + batch + one page written twice + blob).
"""
import os, sys, zlib, struct
import numpy as np
from common import *
import sbfw, trackdeform as TDm
import build_testtrack as BT

def main():
    src = BT.Track('Desert4'); log = BT.log; BT.LOG.append('---- build_road_ladder ----'); mark = len(BT.LOG) - 1
    def td_of(t):
        f = t.files['master_gfx_xdata']; by = f.byid(); return TDm.parse_td(by[BT.gfx_root(f).u32(0xc)])
    def keep_blob(f, m):
        """set_td without touching the height blob"""
        r = BT.gfx_root(f); by = f.byid(); td = by[r.u32(0xc)]; blob = by[td.u32(0x18)]
        data, fix, ref = TDm.build_td(m, blob.id, len(blob.data)); BT.replace(f, td.id, data, fix, ref)
    def out(n, t, note): BT.write_track(n, t, note=note); BT.check_authored(n, t)
    orig = td_of(src); pat = BT.uniform_pattern(orig)
    # a
    t = src.copy(); f = t.files['master_gfx_xdata']; m = TDm.td_to_model(td_of(t)); keep_blob(f, m)
    same = f.byid()[BT.gfx_root(f).u32(0xc)].data == orig.c.data; out('step5a_identity_desert4', t, '| TrackDeform bytes identical to the original: %s' % same)
    # b, c
    for n, two in (('step5b_one_page_only_desert4', False), ('step5c_two_equal_pages_desert4', True)):
        t = src.copy(); f = t.files['master_gfx_xdata']; m = TDm.td_to_model(td_of(t)); k = len(m['rec11'])
        m['pages'] = [m['pages'][0]] * (2 if two else 1); m['rec11'] = [bytes(r[:10]) + bytes([1 if (two and i >= k // 2) else 0]) for i, r in enumerate(m['rec11'])]
        keep_blob(f, m); d = BT.gc(f, t); out(n, t, '| %d page(s), %d unreferenced page textures dropped' % (len(m['pages']), d))
    # d
    t = src.copy(); f = t.files['master_gfx_xdata']; m = TDm.td_to_model(td_of(t)); by = f.byid(); td = by[BT.gfx_root(f).u32(0xc)]; blob = by[td.u32(0x18)]
    z = zlib.compress(b'\xbf' * TDm.blob_size(m), 9); blob.data = z; blob.gap = None; data, fix, ref = TDm.build_td(m, blob.id, len(z)); BT.replace(f, td.id, data, fix, ref)
    out('step5d_blob_only_desert4', t, '| blob %d bytes of 0xBF' % TDm.blob_size(m))
    # e, f
    for n, batch in (('step5e_uniform_cells_desert4', False), ('step5f_uniform_batch_desert4', True)):
        t = src.copy(); f = t.files['master_gfx_xdata']; m = TDm.td_to_model(td_of(t))
        for s in m['slices'][1:]:
            v = s['verts']; v['surf'] = np.frombuffer(pat['surf'], np.uint8); v['w1c'] = pat['w1c']
            for fld in ('w20', 'w24', 'w28', 'w2c'): v[fld] = pat['w']
        if batch: m['rec11'] = [pat['rec'] + bytes([r[10]]) for r in m['rec11']]
        keep_blob(f, m); out(n, t, '| pattern surf %s weights %x%s' % (pat['surf'].hex(), pat['w'], ', batch records uniform' if batch else ''))
    # step5 rebuilt with the fix
    import build_twins
    build_twins.main('step5_authored_road_surface') if hasattr(build_twins, 'main') else None
    open(os.path.join(OUT, 'build_log.txt'), 'a').write('\n'.join(BT.LOG[mark:]) + '\n')

if __name__ == '__main__':
    main()
