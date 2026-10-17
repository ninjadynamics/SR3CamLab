"""The sun / shadow pages of a SEGA track's road: colours used, and each page as a picture with the road's vertices marked.
    python dump_pages.py <track folder name> <out dir>"""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..', '..')))      # tools/import/core
import sys, os, struct, collections, numpy as np
from PIL import Image
from common import *
import sbfw, trackdeform as TDm, build_testtrack as BT, preview_obj as PO
trk, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
tf = track_files(os.path.join(TRACKS, trk)); f = sbfw.read_sbf(tf['master_gfx_xdata']); by = f.byid(); r = BT.gfx_root(f); t = TDm.parse_td(by[r.u32(0xc)])
print(trk, 'slices', t.n, 'pages', len(t.pages)); cols = collections.Counter(); sizes = collections.Counter()
def tex(tid):
    d = by[tid].data; h, w, mips = struct.unpack_from('<III', d, 48 + 8)[0], struct.unpack_from('<I', d, 48 + 12)[0], struct.unpack_from('<I', d, 48 + 24)[0]; four = d[48 + 80:48 + 84]; base = 48 + 124
    assert four == b'DXT1', four; img = PO.dxt_colour(d[base:base + 8 * (w // 4) * (h // 4)], w // 4, h // 4); return img[:h, :w, :3], (w, h, mips, len(d))
allpos = np.concatenate([v['pos'][:, :3] for v in t.verts if len(v)]).astype(np.float64)
for k, (ta, tb, u0, v0, su, sv) in enumerate(t.pages):
    img, info = tex(ta); sizes[info] += 1; imb, infob = tex(tb) if tb in by else (None, None)
    flat = img.reshape(-1, 3); q = (flat // 16).astype(np.int32); cols.update(map(tuple, q[::7].tolist()))
    u = allpos[:, 0] * su + u0; v = allpos[:, 2] * sv + v0; m = (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1); pic = img.copy(); H, W = pic.shape[:2]
    px = np.clip((u[m] * W).astype(int), 0, W - 1); py = np.clip((v[m] * H).astype(int), 0, H - 1)
    if k < 40:
        im2 = Image.fromarray(pic).resize((512, 512 * H // W), Image.BILINEAR); a = np.asarray(im2).copy(); a[np.clip(py * a.shape[0] // H, 0, a.shape[0] - 1), np.clip(px * a.shape[1] // W, 0, a.shape[1] - 1)] = (0, 0, 255); Image.fromarray(a).save(os.path.join(out, 'page_%02d.png' % k))
    if k < 6: print('page', k, 'texA %08x' % ta, info, 'texB %08x' % tb, infob, 'span %.0f x %.0f m' % (1 / su, 1 / sv), 'road vertices inside', int(m.sum()), 'mean colour', flat.mean(0).round(0), 'texB mean', None if imb is None else imb.reshape(-1, 3).mean(0).round(0))
print('texture sizes (w, h, mips, bytes):', dict(sizes)); print('colours (R, G, B in sixteenths), most common:', cols.most_common(14))
