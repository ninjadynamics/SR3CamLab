"""Per-surface retexture of the classic Mountain course with SR3 textures.
Labels: ../retex/tile_labels.csv (written once from the table below; EDIT THE CSV to correct - it is read back on every build).
Classes that are replaced by an SR3 texture get new UVs in metres (box mapping, REPEAT_M metres per repeat, faces cut to
pieces of at most 2 repeats because the SR3 vertex format holds uv 0..2). Picture tiles (house fronts, signs, cut-outs)
keep the classic texture and UVs."""
import os, csv, json, math
from retexuv import subdivide, tree_uv, plane_uv, box_uv
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

SR3_TREES = ('Alpine4', 0x484f0734)                                   # 1024x256 DXT5 cut-out row of pines (Alpine4 tree walls)
