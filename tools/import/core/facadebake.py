"""ONE PICTURE FOR A WHOLE FACADE, made at import time from the course's own tiles (user, 2026-10-12: "one facade, 2 triangles").

A course patch may carry "bake" entries: {"name": "facade_012", "size": [w, h], "sources": [{"tile", "p": 3 x [u, v], "uv": 3 x [u, v]}]}.
Each source is one triangle of the wall as it was: where it lies on the new picture (p, 0..1, v up) and which part of its tile it showed
(uv, as Blender has it, v up). The picture is painted texel by texel from those tiles (nearest texel, bigger triangles first so that a
window drawn over its wall wins); texels no triangle reaches take the nearest painted one. Nothing of SEGA's ships: only the recipe."""
import collections
import numpy as np

def _nearest(g):
    """per texel: row of the nearest painted texel in its column, and how far"""
    idx = np.arange(g.shape[0])[:, None] * np.ones((1, g.shape[1]), int)
    up = np.maximum.accumulate(np.where(g, idx, -10 ** 6), axis=0); dn = np.minimum.accumulate(np.where(g, idx, 10 ** 6)[::-1], axis=0)[::-1]
    pick = np.where((idx - up) <= (dn - idx), up, dn); return pick, np.abs(pick - idx)

def compose(size, sources, pixels):
    """size (w, h), sources as in the patch file (in painting order), pixels(tile) -> (rgb top row first, hole) -> rgb uint8 (h, w, 3), top row first"""
    W, H = int(size[0]), int(size[1]); img = np.zeros((H, W, 3), np.uint8); got = np.zeros((H, W), bool)      # row 0 = v 0 (bottom) while painting
    px = (np.arange(W) + 0.5) / W; py = (np.arange(H) + 0.5) / H; memo = {}
    for s in sources:
        if s['tile'] not in memo: memo[s['tile']] = pixels(s['tile'])
        if memo[s['tile']] is None: continue
        T = np.asarray(memo[s['tile']][0]); th, tw = T.shape[:2]; P = np.asarray(s['p'], float); U = np.asarray(s['uv'], float)
        i0, i1 = np.searchsorted(px, P[:, 0].min() - 2.0 / W), np.searchsorted(px, P[:, 0].max() + 2.0 / W); j0, j1 = np.searchsorted(py, P[:, 1].min() - 2.0 / H), np.searchsorted(py, P[:, 1].max() + 2.0 / H)
        if i1 <= i0 or j1 <= j0: continue
        X, Y = np.meshgrid(px[i0:i1], py[j0:j1]); den = (P[1, 1] - P[2, 1]) * (P[0, 0] - P[2, 0]) + (P[2, 0] - P[1, 0]) * (P[0, 1] - P[2, 1])
        if abs(den) < 1e-12: continue
        l0 = ((P[1, 1] - P[2, 1]) * (X - P[2, 0]) + (P[2, 0] - P[1, 0]) * (Y - P[2, 1])) / den; l1 = ((P[2, 1] - P[0, 1]) * (X - P[2, 0]) + (P[0, 0] - P[2, 0]) * (Y - P[2, 1])) / den; l2 = 1 - l0 - l1
        m = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        if not m.any(): continue
        uu = l0 * U[0, 0] + l1 * U[1, 0] + l2 * U[2, 0]; vv = l0 * U[0, 1] + l1 * U[1, 1] + l2 * U[2, 1]
        tx = np.floor(uu * tw + 1e-6).astype(int) % tw; ty = (th - 1) - np.floor(vv * th + 1e-6).astype(int) % th
        sub = img[j0:j1, i0:i1]; sub[m] = T[ty[m], tx[m]][:, :3]; got[j0:j1, i0:i1] |= m
    for _ in range(4):
        if got.all() or not got.any(): break
        pv, dv = _nearest(got); ph, dh = _nearest(got.T); ph, dh = ph.T, dh.T; rows = np.arange(H)[:, None] * np.ones((1, W), int); cols = np.ones((H, 1), int) * np.arange(W)[None, :]
        usev = (dv <= dh) & (dv < 10 ** 5); useh = ~usev & (dh < 10 ** 5); miss = ~got
        a = miss & usev; img[a] = img[np.clip(pv, 0, H - 1)[a], cols[a]]; b = miss & useh; img[b] = img[rows[b], np.clip(ph, 0, W - 1)[b]]; got |= a | b
    return np.ascontiguousarray(img[::-1])

def apply(entries, pixels, save, origin=None, log=print):
    """the "bake" entries of a patch: every picture composed and handed to save(name, rgb, hole) (build_classic.save_baked)"""
    for e in entries:
        save(e['name'], compose(e['size'], e['sources'], pixels), None)
        if origin is not None and e['sources']: origin[e['name']] = collections.Counter(s['tile'] for s in e['sources']).most_common(1)[0][0]      # the picture counts as its main tile (labels, lighting classes)
    log('       facade pictures composed from the course tiles: %d (%.1f megapixels, %d source triangles)' % (len(entries), sum(e['size'][0] * e['size'][1] for e in entries) / 1e6, sum(len(e['sources']) for e in entries)))
