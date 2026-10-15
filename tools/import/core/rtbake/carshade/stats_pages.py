"""joint statistics of the R and G channels of a SEGA track's road pages, on the road and off it.   python stats_pages.py <track>"""
import sys, os, struct, collections, numpy as np
from common import *
import sbfw, trackdeform as TDm, build_testtrack as BT, preview_obj as PO
trk = sys.argv[1]; tf = track_files(os.path.join(TRACKS, trk)); f = sbfw.read_sbf(tf['master_gfx_xdata']); by = f.byid(); r = BT.gfx_root(f); t = TDm.parse_td(by[r.u32(0xc)])
allpos = np.concatenate([v['pos'][:, :3] for v in t.verts if len(v)]).astype(np.float64); on = collections.Counter(); off = collections.Counter(); bch = collections.Counter(); edge = collections.Counter()
for k, (ta, tb, u0, v0, su, sv) in enumerate(t.pages):
    d = by[ta].data; h, w = struct.unpack_from('<II', d, 48 + 8); img = PO.dxt_colour(d[48 + 124:48 + 124 + 8 * (w // 4) * (h // 4)], w // 4, h // 4)[:h, :w, :3]
    u = allpos[:, 0] * su + u0; v = allpos[:, 2] * sv + v0; m = (u >= 0) & (u < 1) & (v >= 0) & (v < 1); mask = np.zeros((h, w), bool); mask[(v[m] * h).astype(int), (u[m] * w).astype(int)] = True
    # the road = within 4 texels of a road vertex (vertices are a metre apart, a texel about 10 cm): grow the mask
    g = mask.copy()
    for s in range(6): g[1:] |= g[:-1]; g[:-1] |= g[1:]; g[:, 1:] |= g[:, :-1]; g[:, :-1] |= g[:, 1:]
    R = (img[..., 0] // 32).astype(int); G = (img[..., 1] // 32).astype(int); bch.update((img[..., 2] // 32).ravel()[::5].tolist())
    on.update(zip(R[g][::3].tolist(), G[g][::3].tolist())); far = ~g
    for s in range(40): far[1:] &= far[:-1]; far[:-1] &= far[1:]; far[:, 1:] &= far[:, :-1]; far[:, :-1] &= far[:, 1:]
    off.update(zip(R[far][::9].tolist(), G[far][::9].tolist()))
def table(c, name):
    tot = sum(c.values()); print(name, 'texels sampled', tot); print('      G:   ' + ' '.join('%5d' % (g * 32) for g in range(8)))
    for r_ in range(8): print('  R %3d: ' % (r_ * 32) + ' '.join('%5.1f' % (100.0 * c.get((r_, g), 0) / max(tot, 1)) for g in range(8)))
table(on, trk + ' ON the road (percent of texels by R and G)'); table(off, trk + ' well OFF the road'); print('blue channel (thirty-seconds):', sorted(bch.items()))
