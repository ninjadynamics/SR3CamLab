"""ONE PICTURE FOR A WHOLE FACADE, made at import time from the course's own tiles (user, 2026-10-12: "one facade, 2 triangles").

A course patch may carry "bake" entries: {"name": "facade_012", "size": [w, h], "sources": [{"tile", "p": 3 x [u, v], "uv": 3 x [u, v]}]}.
Each source is one triangle of the wall as it was: where it lies on the new picture (p, 0..1, v up) and which part of its tile it showed
(uv, as Blender has it, v up). The picture is painted texel by texel from those tiles (nearest texel, bigger triangles first so that a
window drawn over its wall wins); texels no triangle reaches take the nearest painted one. Nothing of SEGA's ships: only the recipe."""
import collections, bisect
from array import array
# Since 2026-10-15 (kb 31) the painting and the fill are fastlm.c's (fb_paint, fb_fill: their comments quote the numpy lines), the picture is
# bytes (compose_bytes). compose() hands the build its numpy array as before: save_baked keeps numpy pictures (a bridge until build_classic
# is numpy-free).

def compose_bytes(size, sources, pixels):
    """size (w, h), sources as in the patch file (in painting order), pixels(tile) -> (rgb top row first, hole) -> the picture as bytes,
    h rows of w RGB texels, top row first (what compose returns as an array)"""
    import fastlm; from lightmap1995 import _raw
    W, H = int(size[0]), int(size[1]); img = bytearray(H * W * 3); got = bytearray(H * W)      # row 0 = v 0 (bottom) while painting
    px = [(i + 0.5) / W for i in range(W)]; py = [(j + 0.5) / H for j in range(H)]; pxa = array('d', px); pya = array('d', py); memo = {}; L = fastlm.lib()      # (np.arange(W) + 0.5) / W
    ad = lambda b_: fastlm.ctypes.addressof((fastlm.ctypes.c_char * max(1, len(b_))).from_buffer(b_)) if b_ else 0
    for s in sources:
        if s['tile'] not in memo:
            px_ = pixels(s['tile'])
            if px_ is None: memo[s['tile']] = None
            else:
                dt, sh, tb = _raw(px_[0]); kind = 0 if dt == '|u1' else 1
                if kind == 1 and dt != '<f8': dt, sh, tb = _raw(px_[0], '<f8')
                memo[s['tile']] = (sh, kind, bytearray(tb))
        if memo[s['tile']] is None: continue
        sh, kind, tb = memo[s['tile']]; th, tw = sh[0], sh[1]; tc = sh[2] if len(sh) == 3 else 1
        P = [float(v) for q in s['p'] for v in q]; U = [float(v) for q in s['uv'] for v in q]
        i0, i1 = bisect.bisect_left(px, min(P[0], P[2], P[4]) - 2.0 / W), bisect.bisect_left(px, max(P[0], P[2], P[4]) + 2.0 / W)      # np.searchsorted (side left)
        j0, j1 = bisect.bisect_left(py, min(P[1], P[3], P[5]) - 2.0 / H), bisect.bisect_left(py, max(P[1], P[3], P[5]) + 2.0 / H)
        if i1 <= i0 or j1 <= j0: continue
        Pa = array('d', P); Ua = array('d', U)
        L.fb_paint(W, H, ad(img), ad(got), pxa.buffer_info()[0], pya.buffer_info()[0], i0, i1, j0, j1, Pa.buffer_info()[0], Ua.buffer_info()[0], ad(tb), th, tw, tc, kind)
    for _ in range(4):
        if all(got) or not any(got): break
        L.fb_fill(W, H, ad(img), ad(got))
    return b''.join(bytes(img[3 * W * r:3 * W * (r + 1)]) for r in range(H - 1, -1, -1))       # img[::-1]: top row first

def compose(size, sources, pixels):
    """compose_bytes as an (h, w, 3) uint8 numpy array, top row first (the build keeps its pictures as numpy arrays)"""
    import numpy as np
    return np.frombuffer(bytearray(compose_bytes(size, sources, pixels)), np.uint8).reshape(int(size[1]), int(size[0]), 3)

def apply(entries, pixels, save, origin=None, log=print):
    """the "bake" entries of a patch: every picture composed and handed to save(name, rgb, hole) (build_classic.save_baked)"""
    for e in entries:
        save(e['name'], compose(e['size'], e['sources'], pixels), None)
        if origin is not None and e['sources']: origin[e['name']] = collections.Counter(s['tile'] for s in e['sources']).most_common(1)[0][0]      # the picture counts as its main tile (labels, lighting classes)
    log('       facade pictures composed from the course tiles: %d (%.1f megapixels, %d source triangles)' % (len(entries), sum(e['size'][0] * e['size'][1] for e in entries) / 1e6, sum(len(e['sources']) for e in entries)))
