"""Whole-lap checks of a face-list dump (GAPFILL_DUMP):  python gapfill_audit.py <dump.pkl> [title]
  stems     : tree / lamp / trunk boards whose lowest edge is more than 5 cm above the surface under it
  fill tiles: every tile the hand fill uses, its label class and count; 'not natural' = not rock / grass / cobbles / asphalt
  boulders  : rock groups of the fill ; thin: fill faces thinner than 1 : 8 (seam fillers apart)
  seams     : gapfill_weld.scan"""
import os, sys, pickle, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fill1995 as F, overlay_bake as OB, gapfill_weld as GW

def main(dump, title=''):
    import retex, course
    course.use('src', '1'); lab = {k: v[0] for k, v in retex.labels().items()}
    d = pickle.load(open(dump, 'rb')); rd = d['rd']; faces = [f for f in d['faces'] + d['sky'] + d['extra'] if f[1] != 'sea']; allf = faces + F.road_faces(rd)
    F.TEXDIRS[:] = [os.path.join(os.path.dirname(os.path.dirname(HERE)), 'classic', 'courses', 'src', 'course1_mountain', 'textures'), os.path.join(os.path.dirname(HERE), 'tmp', 'bake_src_mountain')]; F._ALPHA.clear()
    hang = [fi for fi, a, b in F.hanging_boards(allf, 0.05) if lab.get(allf[fi][0]) in ('trunk', 'bare', 'lamp', 'tree')]
    fill = [f for f in faces if str(f[1]).startswith('hf_')]; tiles = collections.Counter(f[0] for f in fill)
    tiles = collections.Counter(f[0] for f in fill if not str(f[1]).startswith('hf_roof'))     # (roofs put on house walls carry the roof tile)
    bad = {m: c for m, c in tiles.items() if lab.get(m) not in ('rock', 'grass', 'cobbles', 'asphalt')}
    def thin(fc):
        P = np.asarray(fc[2], float); nn, ar = OB._newell(P); e = max(np.linalg.norm(P[k] - P[(k + 1) % len(P)]) for k in range(len(P))); return ar / max(e * e, 1e-9) < 0.0625 and e > 3.0
    print('%s: stem boards more than 5 cm above the surface under them: %d' % (title, len(hang)))
    print('%s: fill faces %d ; tiles: %s' % (title, len(fill), ', '.join('%s %s %d' % (m[-4:], lab.get(m), c) for m, c in tiles.most_common())))
    print('%s: fill faces with a tile that is not natural ground: %d %s ; boulders: %d ; thin fill faces: %d' % (title, sum(bad.values()), {m[-12:]: c for m, c in bad.items()}, len({f[1] for f in fill if str(f[1]).startswith('hf_rocks')}), sum(1 for f in fill if not str(f[1]).startswith('hf_weld') and thin(f))))
    import build_classic as BC
    deg = [f for f in faces if BC.world_area(f[2]) > 0.25 and len(f[3]) == len(f[2]) and BC.uv_area(f[3]) < 1e-7 * BC.world_area(f[2])]
    print('%s: polygons (> 0.25 m2) whose uv lie on a line: %d %s' % (title, len(deg), collections.Counter(f[1].split('#')[0][:10] for f in deg).most_common(6)))
    GW.scan(d['faces'] + d['sky'] + d['extra'], rd, title)

if __name__ == '__main__':
    main(*sys.argv[1:3])
