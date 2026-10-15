"""Repair built steps whose road has ONE overlay page (page count bug of the exe, see build_testtrack.two_pages and
04_trackdeform_road.md "Overlay page count"): the TrackDeform chunk is re-written with the page listed twice and the
second half of the batch records on page 1. Nothing else in the folder changes (height blob, cells, scenery, art).
    python patch_pages.py            -> list the steps that need it
    python patch_pages.py fix [step ...]   (default: all that need it, except other sessions' *_sr2_* steps)"""
import os, sys, struct
from common import *
import sbfw, trackdeform as TDm, build_testtrack as BT, reforder

def main(argv):
    fix = argv[:1] == ['fix']; only = set(argv[1:])
    for s in sorted(os.listdir(OUT)):
        for slot in ('Desert4', 'Stadium4'):
            d = os.path.join(OUT, s, slot)
            if not os.path.isdir(d) or (only and s not in only) or 'one_page_only' in s: continue      # step5b is the control: it must keep one page
            tf = track_files(d)
            if 'master_gfx_xdata' not in tf: continue
            p = tf['master_gfx_xdata']; f = sbfw.read_sbf(p); by = f.byid(); r = f.chunks[-1]; td = by[r.u32(0xc)]; t = TDm.parse_td(td)
            if max(x[10] for x in t.rec11) != 0: continue
            if not fix: print('%-50s one overlay page: the game will crash at 0x5D2D3F' % s); continue
            if '_sr2_' in s and not only: print('%-50s skipped (other session); run: python patch_pages.py fix %s' % (s, s)); continue
            m = TDm.td_to_model(t); assert BT.two_pages(m); blob = by[td.u32(0x18)]
            data, fx, ref = TDm.build_td(m, blob.id, len(blob.data)); BT.replace(f, td.id, data, fx, ref)
            for c in f.chunks: c.gap = None
            reforder.topo(f); b = sbfw.write_sbf(f, compress=True, layout='auto', level=6); g = sbfw.read_sbf(b)
            t2 = TDm.parse_td(g.byid()[td.id]); assert len(t2.pages) == 2 and max(x[10] for x in t2.rec11) == 1 and all((a['pos'] == b_['pos']).all() for a, b_ in zip(t.verts[1:t.n + 1], t2.verts[1:t.n + 1]))
            open(p, 'wb').write(b); print('%-50s fixed: 2 pages, batch records %d on page 0 / %d on page 1' % (s, sum(1 for x in t2.rec11 if x[10] == 0), sum(1 for x in t2.rec11 if x[10] == 1)))

if __name__ == '__main__':
    main(sys.argv[1:])
