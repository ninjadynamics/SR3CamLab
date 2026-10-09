"""FACADE RELIEF TEST (user, 2026-10-08: "can we use bump maps or normal maps to make the building facades look 3d?").

Every imported material has the normal-map switch on, with a flat map. SEGA's own normal maps (probed in Tropical4: 136 of them) are plain
tangent-space pictures, x in red, y in green, z in blue, flat = (127, 127, 255), DXT1 or DXT5 with a solid alpha.
Course setting "bump_tiles": {tile: strength} gives those tiles a normal map made from their own picture - DARKER PAINT = FURTHER BACK,
which is right for windows, joints and door openings and wrong for anything dark for another reason - and their polygons true normals and
a tangent along the picture's u, so the game's sun lights the relief."""
import numpy as np

def height(rgb, blur=1.2):
    g = np.asarray(rgb, np.float64); g = g if g.ndim == 2 else g[..., :3] @ np.array([0.30, 0.59, 0.11]); g = g / 255.0
    r = int(np.ceil(blur * 3)); k = np.exp(-0.5 * (np.arange(-r, r + 1) / blur) ** 2); k /= k.sum()
    for ax in (0, 1):                                                  # the tile repeats: blur with wrap-around
        g = sum(w * np.roll(g, s, axis=ax) for w, s in zip(k, range(-r, r + 1)))
    return g

def normal_map(rgb, strength=4.0, flip_green=False, scale=2):
    """-> uint8 (h, w, 3) tangent-space normal map of the tile, `scale` times its size (smoother slopes than the 1995 texels give)"""
    from PIL import Image
    im = np.asarray(Image.fromarray(np.ascontiguousarray(np.asarray(rgb)[..., :3].astype(np.uint8))).resize((rgb.shape[1] * scale, rgb.shape[0] * scale), Image.BICUBIC)) if scale > 1 else rgb
    h = height(im, 1.2 * scale); dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * scale; dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * scale      # per original texel
    n = np.stack([-dx * strength * 8.0, (dy if flip_green else -dy) * strength * 8.0, np.ones_like(h)], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return np.clip(np.round(n * 127.5 + 127.5), 0, 255).astype(np.uint8)

def tangents(P4, UV4):
    """(n, 4, 3) corners and (n, 4, 2) texture coordinates (u right, v DOWN the picture) -> unit tangent along +u per polygon"""
    P = np.asarray(P4, np.float64); U = np.asarray(UV4, np.float64); e1 = P[:, 1] - P[:, 0]; e2 = P[:, 3] - P[:, 0]; a1 = U[:, 1] - U[:, 0]; a2 = U[:, 3] - U[:, 0]
    det = a1[:, 0] * a2[:, 1] - a2[:, 0] * a1[:, 1]; ok = np.abs(det) > 1e-12; t = (e1 * a2[:, 1:2] - e2 * a1[:, 1:2]) / np.where(ok, det, 1.0)[:, None]
    ln = np.linalg.norm(t, axis=1); t = np.where((ok & (ln > 1e-12))[:, None], t / np.maximum(ln, 1e-12)[:, None], e1 / np.maximum(np.linalg.norm(e1, axis=1), 1e-12)[:, None]); return t
