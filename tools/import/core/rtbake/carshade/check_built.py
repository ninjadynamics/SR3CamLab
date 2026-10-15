"""The cars' pages of a BUILT step read back from its file and compared with what the bake made.   python check_built.py <step> <carshade.npz>"""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..', '..')))      # tools/import/core
import sys, os, struct, numpy as np
from common import *
import sbfw, trackdeform as TDm, build_testtrack as BT, preview_obj as PO
step, ref = sys.argv[1], sys.argv[2]; tf = track_files(os.path.join(OUT, step, 'Desert4')); f = sbfw.read_sbf(tf['master_gfx_xdata']); by = f.byid(); r = BT.gfx_root(f); t = TDm.parse_td(by[r.u32(0xc)])
D = np.load(ref) if os.path.exists(ref) else None; ids = [p[0] for p in t.pages]; print(step, 'slices', t.n, 'pages', len(t.pages), '; different first pictures', len(set(ids)), '; second pictures', sorted({'%08x' % p[1] for p in t.pages}))
recp = [r_[10] for r_ in t.rec11]; print('batch records', len(recp), 'page indices used', min(recp), '..', max(recp), '; every page used:', set(recp) == set(range(len(t.pages))))
worst = 0.0; missing = 0
for k, (ta, tb, u0, v0, su, sv) in enumerate(t.pages):
    if ta not in by or tb not in by: missing += 1; continue
    d = by[ta].data; w0, h0 = struct.unpack_from('<II', d, 8); h, w, top = struct.unpack_from('<III', d, 48 + 8); mips = struct.unpack_from('<I', d, 48 + 24)[0]; four = d[48 + 80:48 + 84]
    img = PO.dxt_colour(d[48 + 124:48 + 124 + 8 * (w // 4) * (h // 4)], w // 4, h // 4)[:h, :w, :3].astype(int)
    if k == 0: print('page 0 picture: %d x %d, %s, %d levels, %d bytes ; kind %d ; a SEGA page picture for comparison is 1024 x 1024 DXT1, 11 levels, 699236 bytes' % (w, h, four.decode(), mips, len(d), by[ta].kind))
    if D is not None:
        assert np.allclose(D['map'][k], (u0, v0, su, sv), rtol=1e-5, atol=1e-5); e = np.abs(img - D['pages'][k].astype(int)); worst = max(worst, float(e.mean()))
        if k in (0, 9): print('  page %d: mean difference to the bake %.1f of 255 (block compression) ; shadow share built %.3f, bake %.3f ; border all open sun: %s' % (k, e.mean(), (img[..., 1] < 128).mean(), (D['pages'][k][..., 1] < 128).mean(), bool((img[0, :, 1] > 240).all() and (img[:, 0, 1] > 240).all() and (img[0, :, 0] < 16).all())))
print('pictures missing from the file:', missing, '; worst mean difference over all pages %.1f' % worst)
