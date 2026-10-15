"""How much sea can be seen from the road? A plan with a 'sea visible' mask, from a face-list dump (GAPFILL_DUMP).
    python gapfill_seamask.py <dump.pkl> <out.png> [title]
From an eye 1.5 m above the road centre line every 30 m, rays go out in 48 directions at three downward pitches (3, 10, 25
degrees) for up to 240 m. A ray ends on land when it passes under a lying polygon, on the SEA when it reaches the sea level
first. Upright faces (walls, houses, boards) are ignored, so the count is an upper bound. Red dots = sea seen INSIDE the lap
(the road loop), orange = sea seen outside it (the true coast and beyond). Printed: rays, sea inside, sea outside."""
import os, sys, pickle
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fill1995 as F

def inside(poly, x, z):
    n = len(poly); c = False; j = n - 1
    for i in range(n):
        if (poly[i, 1] > z) != (poly[j, 1] > z) and x < (poly[j, 0] - poly[i, 0]) * (z - poly[i, 1]) / (poly[j, 1] - poly[i, 1]) + poly[i, 0]: c = not c
        j = i
    return c

def main(dump, out, title=''):
    from PIL import Image, ImageDraw
    d = pickle.load(open(dump, 'rb')); rd = d['rd']; land = [f for f in d['faces'] + d['sky'] + d['extra'] if f[1] != 'sea'] + F.road_faces(rd)
    sea = min([f[2][0][1] for f in d['sky'] if f[1] == 'sea'] or [-0.5]); ix = F.Index(land); cen = np.asarray(rd['V'][:, rd['hw']], float); loop = cen[::10][:, [0, 2]]
    size = 1500; sc = size / 1500.0; px = lambda x, z: (size / 2 + x * sc, size / 2 - z * sc); im = Image.new('RGB', (size, size), (60, 95, 170)); dr = ImageDraw.Draw(im)
    for mat, sec, P, UV in land:
        if not str(mat).endswith('_t') and abs(F._normal(np.asarray(P, float))[1]) > 0.3: dr.polygon([px(q[0], q[2]) for q in P], fill=(150, 150, 140) if str(sec).startswith('hf_') else (200, 200, 200))
    for mat, sec, P, UV in F.road_faces(rd): dr.polygon([px(q[0], q[2]) for q in P], fill=(80, 80, 90))
    rays = 0; n_in = 0; n_out = 0
    for i in range(0, len(cen), 30):
        e = cen[i] + (0, 1.5, 0)
        for a in np.arange(48) * (2 * np.pi / 48):
            for pitch in (3.0, 10.0, 25.0):
                dx, dz = np.cos(a), np.sin(a); dy = -np.tan(np.radians(pitch)); rays += 1; py = e[1]
                for t in np.arange(3.0, 240.0, 3.0):
                    x, z, y = e[0] + dx * t, e[2] + dz * t, e[1] + dy * t
                    hs = [h for h, k in ix.heights(x, z, True)]
                    if any(y - 0.2 <= h <= py + 3.0 for h in hs): break
                    if y <= sea:
                        if not any(h > sea for h in hs):
                            ins = inside(loop, x, z); n_in += ins; n_out += (not ins); q = px(x, z); dr.ellipse([q[0] - 2, q[1] - 2, q[0] + 2, q[1] + 2], fill=(255, 40, 40) if ins else (255, 170, 40))
                        break
                    py = y
    dr.text((10, 10), '%s  rays %d, sea seen inside the lap %d (red), outside %d (orange)' % (title, rays, n_in, n_out), fill=(255, 255, 255)); im.save(out)
    print('%s: rays %d, sea inside the lap %d, outside %d' % (title, rays, n_in, n_out))

if __name__ == '__main__':
    main(*sys.argv[1:4])
