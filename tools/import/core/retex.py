"""Per-surface retexture of the classic Mountain course with SR3 textures.
Labels: ../retex/tile_labels.csv (written once from the table below; EDIT THE CSV to correct - it is read back on every build).
Classes that are replaced by an SR3 texture get new UVs in metres (box mapping, REPEAT_M metres per repeat, faces cut to
pieces of at most 2 repeats because the SR3 vertex format holds uv 0..2). Picture tiles (house fronts, signs, cut-outs)
keep the classic texture and UVs."""
import os, csv, json, math
import numpy as np
from common import *
RT = os.path.join(WORK, 'retex'); CSVP = os.path.join(RT, 'tile_labels.csv')
REPEAT_M = 3.0
# class -> (SR3 track, diffuse texture id) for the tiled classes; None = picture class. Per-course overrides: course.use().
SR3_FOR_CLASS = {'rock': ('Canyon4', 0x53850d6a), 'asphalt': ('Alpine4', 0x02b4772a), 'cobbles': ('Alpine4', 0xfc24c933),
                 'stone_wall': ('Alpine4', 0x24a1910c), 'gravel': ('Alpine4', 0x66f0ba6f), 'plaster': ('Alpine4', 0xee2e5509),
                 'roof': ('Alpine4', 0x65f21786), 'grass': ('Lakeside4', 0xd8dcd068), 'dirt': ('Canyon4', 0x1ec88958), 'sand': ('Desert4', 0xca48d483),
                 'water': ('Lakeside4', 0x1f15ac68), 'wood': ('Lakeside4', 0x0fdd1c75), 'brick_wall': ('Lakeside4', 0x9ad7a350)}
AUTO = {}                                                             # tile -> class guessed by course.auto_labels(), used when a new CSV is written

def labels():
    """{tile name: (class, track or '', texture id or None)}"""
    if not os.path.exists(CSVP):
        names = json.load(open(os.path.join(RT, 'classic_tiles_index.json')))
        with open(CSVP, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['index', 'tile', 'class', 'sr3_track', 'sr3_texture_id', 'note'])
            for i, n in enumerate(names):
                c = AUTO.get(n, 'unlabelled'); s = SR3_FOR_CLASS.get(c)
                w.writerow([i, n, c, s[0] if s else '', ('%08x' % s[1]) if s else '', 'auto label - check against the contact sheet'])
    out = {}
    for r in csv.DictReader(open(CSVP)):
        c = r['class']; t = (r['sr3_track'], int(r['sr3_texture_id'], 16)) if r['sr3_texture_id'] else SR3_FOR_CLASS.get(c)
        out[r['tile']] = (c, t[0], t[1]) if t else (c, '', None)
    return out

REPEAT_BY_CLASS = {'rock': 7.0, 'grass': 4.0, 'dirt': 4.0}                                       # larger repeat on the big rock faces

def subdivide(P, maxlen):
    """quad (4 corners; triangles come as quads with a repeated corner) -> list of quads no longer than maxlen per edge"""
    P = np.array(P, float); lu = max(np.linalg.norm(P[1] - P[0]), np.linalg.norm(P[2] - P[3])); lv = max(np.linalg.norm(P[3] - P[0]), np.linalg.norm(P[2] - P[1]))
    n = max(1, int(math.ceil(lu / maxlen))); m = max(1, int(math.ceil(lv / maxlen)))
    if n * m > 400: s = math.sqrt(400.0 / (n * m)); n = max(1, int(n * s)); m = max(1, int(m * s))
    def pt(a, b): return (P[0] * (1 - a) + P[1] * a) * (1 - b) + (P[3] * (1 - a) + P[2] * a) * b
    return [[pt(i / n, j / m), pt((i + 1) / n, j / m), pt((i + 1) / n, (j + 1) / m), pt(i / n, (j + 1) / m)] for i in range(n) for j in range(m)]

SR3_TREES = ('Alpine4', 0x484f0734)                                   # 1024x256 DXT5 cut-out row of pines (Alpine4 tree walls)
def tree_uv(P, min_h=2.5, aspect=4.0, vtop=0.13, vbot=0.895):
    """upright classic foliage board -> (quad, uv in repeats) showing a window of an SR3 tree row with the same
    width/height ratio, trunks at the lower edge; None if the face is not an upright board at least min_h tall.
    aspect = texture width / height, vtop..vbot = the rows of the texture that hold the trees"""
    q = np.array(P if len(P) == 4 else list(P) + [P[2]], float); n = np.cross(q[1] - q[0], q[2] - q[0]); ln = np.linalg.norm(n)
    if ln < 1e-9 or abs(n[1] / ln) > 0.35: return None
    y0, y1 = q[:, 1].min(), q[:, 1].max(); H = y1 - y0
    if H < min_h: return None
    hdir = np.array([-n[2], 0.0, n[0]]); hdir /= np.linalg.norm(hdir); s = q @ hdir; s -= s.min(); W = max(s.max(), 1e-6)
    span = min(1.9, W / H * (vbot - vtop) / aspect); u0 = (abs(q[0, 0] * 0.137 + q[0, 2] * 0.291) % 1.0) * (1.99 - span)
    uv = np.stack([u0 + s / W * span, vbot - (q[:, 1] - y0) / H * (vbot - vtop)], 1)
    return [tuple(p) for p in q], [tuple(u) for u in uv]

def plane_uv(q, repeat=REPEAT_M):
    """uv in repeats without stretch on sloping faces: u along the horizontal direction of the face, v down its slope
    (world-anchored, so coplanar neighbours continue each other); shifted into 0..2"""
    q = np.array(q, float); n = np.cross(q[1] - q[0], q[2] - q[0]); ln = np.linalg.norm(n)
    if ln < 1e-9: return box_uv(q, repeat)
    n = n / ln
    if abs(n[1]) > 0.92: uv = q[:, [0, 2]]
    else:
        h = np.array([n[2], 0.0, -n[0]]); h /= np.linalg.norm(h)
        if abs(h[0]) > abs(h[2]): h = h if h[0] > 0 else -h            # same sense on both sides of a ridge
        else: h = h if h[2] > 0 else -h
        t = np.cross(n, h); t = t if t[1] > 0 else -t; uv = np.stack([q @ h, -(q @ t)], 1)
    uv = uv / repeat; uv -= np.floor(uv.min(0) + 1e-6)
    return np.clip(uv, 0, 1.999)

def box_uv(q, repeat=REPEAT_M):
    """uv in repeats for one quad: project on the plane most perpendicular to its normal; shifted into 0..2"""
    q = np.array(q, float); n = np.cross(q[1] - q[0], q[2] - q[0]); a = int(np.argmax(np.abs(n))) if np.linalg.norm(n) > 1e-9 else 1
    if a == 1: uv = q[:, [0, 2]]                                      # ground / roof: x, z
    elif a == 0: uv = np.stack([q[:, 2], -q[:, 1]], 1)                # wall facing x: z across, height down
    else: uv = np.stack([q[:, 0], -q[:, 1]], 1)
    uv = uv / repeat; uv -= np.floor(uv.min(0) + 1e-6)
    return np.clip(uv, 0, 1.999)
