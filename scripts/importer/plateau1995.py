"""Hand model for SRC Mountain: the far PLATEAU completed.

The 1995 course draws the big ivy-covered rock of sections 1280 .. 1282 as a curved SCREEN of cliff faces (about 100 m
long, y 54 .. 125): no back, no top. It is seen from most of the lap and from every free / intro camera, so its hollow
back and a sliver of its edge show (user, 2026-10-07: "it's a plateau that can be seen from anywhere in track. The least you
could do is complete its shape in a natural way (make it round) and apply the same texturing").

    python plateau1995.py        -> classic/courses/src/course1_mountain/src_course1_handmodel.obj

The model: the screen stays as it is and becomes the front of a mesa. A back wall is swept round behind it through
hand-placed control points (uneven outline, wider at the foot, leaning in towards the top), meeting the screen's own corners
at both ends; a low dome closes the top. Texture: the screen's own tile at the screen's own scale (measured on its faces:
0.023 repeats per metre along, 0.0195 per metre up), running on round the back. The tile is named by reference
('@near:x,y,z' = "the material of the course polygon nearest this point"), so the file never names a composed tile.
Deterministic; no SEGA data in the file (positions of the new faces and the 36 screen corners they meet)."""
import os, hashlib
import numpy as np
from common import *

OUT = os.path.join(os.path.dirname(WORK), 'classic', 'courses', 'src', 'course1_mountain', 'src_course1_handmodel.obj')
HI = os.path.join(os.path.dirname(WORK), 'classic', 'courses', 'src', 'course1_mountain', 'src_course1_hi.obj')
CTRL = [(-189, -170), (-181, -152), (-192, -131), (-219, -117), (-250, -106), (-281, -115), (-306, -137), (-322, -168), (-333, -203),
        (-329, -241), (-316, -272), (-296, -297), (-270, -314), (-242, -318), (-216, -301)]            # foot of the back wall, from the screen's E end round to its S end (OBJ x, z)
G = np.array([-262.0, -212.0]); DU = 0.023; DV = 0.0195; REF = (-212.1, 125.4, -172.3)

def _h(*a): return int(hashlib.md5(repr(a).encode()).hexdigest()[:8], 16) / 2.0 ** 32

def screen_rings():
    V = []; F = []; mat = None
    for l in open(HI):
        if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
        elif l.startswith('usemtl'): mat = l.split()[1]
        elif l.startswith('f ') and not str(mat).endswith('_t'): F.append([int(t.split('/')[0]) - 1 for t in l.split()[1:]])
    V = np.array(V); pts = []
    for ix in F:
        P = V[ix]
        if np.hypot(P[:, 0].mean() + 225, P[:, 2].mean() + 180) < 120 and P[:, 1].max() > 88: pts += [tuple(np.round(p, 2)) for p in P]
    pts = np.array(sorted(set(pts)))
    def ring(y):
        q = pts[np.abs(pts[:, 1] - y) < 0.7][:, [0, 2]]; start = q[np.argmin(q[:, 1])]; out = [start]; rest = [tuple(x) for x in q if tuple(x) != tuple(start)]
        while rest:
            j = min(range(len(rest)), key=lambda k: np.hypot(rest[k][0] - out[-1][0], rest[k][1] - out[-1][1])); out.append(np.array(rest.pop(j)))
        return np.array(out)                                            # from the S end to the E end
    return ring(97.9), ring(112.5), ring(125.4)

def catmull(C, n=5):
    C = np.asarray(C, float); out = []
    for i in range(len(C) - 1):
        a, b, c, d = C[max(i - 1, 0)], C[i], C[i + 1], C[min(i + 2, len(C) - 1)]
        for k in range(n):
            t = k / n; out.append(0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t ** 3))
    out.append(C[-1]); return np.array(out)

ROUGH = True                                                           # user, 2026-10-07: "I prefer the rougher one, tbh. Looks more natural." (the smooth version is build_smooth)
GENTLE = 0.45                                                          # user, 2026-10-08: "the rough is too rough and created some very weird geometry ... something in between with gentle roughness":
                                                                       # the jitter of the rough version scaled down, the rim heights averaged with their neighbours (no single tooth on the skyline)
CTRL_ROUGH = [(-189, -170), (-183, -150), (-198, -128), (-228, -114), (-262, -110), (-292, -122), (-314, -146), (-327, -180), (-331, -215),
              (-325, -250), (-309, -281), (-286, -303), (-259, -315), (-233, -313), (-216, -301)]

def build():
    """the rough plateau: corners of the upper rings jittered, a rim of random heights (a broken skyline), a plain fan on top"""
    if not ROUGH: return build_smooth()
    f_base, f_mid, f_top = screen_rings(); back = catmull(CTRL_ROUGH, 4); n = len(back); rings = []
    for y, f, jit in [(40.0, 1.0, 0.0), (97.9, 1.0, 0.0), (112.5, 0.985, 2.0), (125.4, 0.93, 3.0)]:
        jit *= GENTLE; R = G + (back - G) * f; R = R + np.array([[(_h('jx', i, y) - 0.5) * jit, (_h('jz', i, y) - 0.5) * jit] for i in range(n)])
        fr = {97.9: f_base, 112.5: f_mid, 125.4: f_top}.get(y, f_base); R[0] = fr[-1]; R[-1] = fr[0]; yy = np.full(n, y)
        if y > 120:
            raw = np.array([(_h('ty', i) - 0.5) * 5.0 * GENTLE for i in range(n)]); raw[0] = raw[-1] = 0.0
            yy = y + np.array([0.25 * raw[max(i - 1, 0)] + 0.5 * raw[i] + 0.25 * raw[min(i + 1, n - 1)] for i in range(n)]); yy[0] = yy[-1] = y
        rings.append(np.c_[R[:, 0], yy, R[:, 1]])
    V = []; VT = []; F = []
    def add(p, uv): V.append(tuple(map(float, p))); VT.append(tuple(map(float, uv))); return len(V)
    vof = lambda y: DV * (y - 97.9) + 0.70; per = np.r_[0, np.cumsum(np.linalg.norm(np.diff(back, axis=0), axis=1))]
    for a in range(len(rings) - 1):
        lo, hi = rings[a], rings[a + 1]
        for i in range(n - 1):
            q = [lo[i], lo[i + 1], hi[i + 1], hi[i]]; uv = [(per[i] * DU, vof(lo[i][1])), (per[i + 1] * DU, vof(lo[i + 1][1])), (per[i + 1] * DU, vof(hi[i + 1][1])), (per[i] * DU, vof(hi[i][1]))]
            F.append([add(q[k], uv[k]) for k in range(4)])
    loop = np.vstack([rings[-1], np.c_[f_top[:, 0], np.full(len(f_top), 125.4), f_top[:, 1]][1:-1]])
    # the top. The rim is not seen whole from any one point (the screen's inner corner), so no fan: a band 12 m in from the rim,
    # a little higher, and the middle triangulated by ear clipping (a fan from the mesa's middle folded triangles over each other).
    import fill1995 as FL
    L2 = loop[:, [0, 2]]; m = len(loop); area = sum(L2[k][0] * L2[(k + 1) % m][1] - L2[(k + 1) % m][0] * L2[k][1] for k in range(m)); sgn = 1.0 if area > 0 else -1.0
    # every inner corner must lie INSIDE the outline and clear of it: at the outline's sharp corners (where the back wall meets the
    # screen) a fixed 12 m step landed outside, and the band stood out over the cliff as a slab (user, 2026-10-08, shots 001339 / 001417).
    def inside(q):
        c = False
        for k in range(m):
            a, b = L2[k], L2[(k + 1) % m]
            if (a[1] > q[1]) != (b[1] > q[1]) and q[0] < a[0] + (q[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]): c = not c
        return c
    def clear(q):
        d = 1e9
        for k in range(m):
            a, b = L2[k], L2[(k + 1) % m]; e = b - a; t = min(max(float((q - a) @ e) / max(float(e @ e), 1e-9), 0.0), 1.0); d = min(d, float(np.linalg.norm(q - a - t * e)))
        return d
    inner = []; cen2 = L2.mean(0)
    for k in range(m):
        t = L2[(k + 1) % m] - L2[k - 1]; t = t / max(np.linalg.norm(t), 1e-9); nrm = sgn * np.array([-t[1], t[0]]); q = None
        for step in (12.0, 9.0, 6.0, 4.0, 2.5):
            for dr in (nrm, (cen2 - L2[k]) / max(np.linalg.norm(cen2 - L2[k]), 1e-9)):
                c = L2[k] + step * dr
                if inside(c) and clear(c) > 0.7 * step: q = c; lift = step / 12.0; break
            if q is not None: break
        if q is None: q = L2[k].copy(); lift = 0.0                   # no room: the band has no width here
        inner.append((q[0], loop[k][1] + lift * (1.2 + 1.5 * GENTLE * (_h('cap', k) - 0.5)), q[1]))
    inner = np.array(inner)
    def a2(p, q, r): return (q[0] - p[0]) * (r[2] - p[2]) - (q[2] - p[2]) * (r[0] - p[0])      # signed area in plan
    for it in range(m):                                               # a band triangle turned over = its inner corner is on the wrong side of the rim there: that corner goes back onto the rim
        bad = set()
        for k in range(m):
            k1 = (k + 1) % m
            if a2(loop[k], loop[k1], inner[k1]) * sgn < -1e-6: bad.add(k1)
            if a2(loop[k], inner[k1], inner[k]) * sgn < -1e-6: bad.update((k, k1))
        bad = {k for k in bad if np.linalg.norm(inner[k] - loop[k]) > 1e-9}
        if not bad: break
        for k in bad: inner[k] = loop[k]
    tuv = lambda x: (x[0] * DU, x[2] * DU)
    for k in range(m):                                                 # the band, as two triangles per step (its quads are not flat); steps with no width are skipped
        q = [loop[k], loop[(k + 1) % m], inner[(k + 1) % m], inner[k]]
        for tri in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
            if np.linalg.norm(np.cross(tri[1] - tri[0], tri[2] - tri[0])) > 0.05: F.append([add(x, tuv(x)) for x in tri])
    for a, b, c in FL._ears([tuple(x) for x in inner[:, [0, 2]]]): F.append([add(inner[a], tuv(inner[a])), add(inner[b], tuv(inner[b])), add(inner[c], tuv(inner[c]))])
    return V, VT, F

def build_smooth():
    f_base, f_mid, f_top = screen_rings(); back = catmull(CTRL); n = len(back); s = np.linspace(0.0, 1.0, n)
    ease = np.sin(np.pi * s) ** 0.5                                     # 0 at the two ends (where the back meets the screen), 1 round the back
    wob = 1.0 + ease * (0.035 * np.sin(2 * np.pi * (3 * s + 0.2)) + 0.025 * np.sin(2 * np.pi * (7 * s + 0.6)))       # uneven outline
    lean = 1.0 + 0.5 * np.sin(2 * np.pi * (2 * s + 0.1))                                                          # the lean changes round the back
    rim = 125.4 + ease * (2.2 * np.sin(2 * np.pi * (1.5 * s + 0.3)) + 1.2 * np.sin(2 * np.pi * (4 * s + 0.7)))     # a smooth, gently rolling rim (random heights stood as teeth on the skyline)
    levels = [(38.0, 1.07, 0.5), (70.0, 1.03, 0.3), (97.9, 1.0, 0.0), (112.5, 0.975, -0.6), (None, 0.93, -1.3)]
    ends = {97.9: f_base, 112.5: f_mid, None: f_top}; rings = []
    for y, f, lk in levels:
        ff = 1.0 + (f - 1.0) * (0.6 + 0.4 * lean) * ease if y not in (97.9,) else np.ones(n)
        R = G + (back - G) * (wob * ff)[:, None]; fr = ends.get(y, f_base)
        R[0] = fr[-1] if y in ends else R[0]; R[-1] = fr[0] if y in ends else R[-1]
        if y not in ends:                                               # below the screen's own foot (it starts at y 54): straight under its ends
            R[0] = f_base[-1]; R[-1] = f_base[0]
        yy = np.full(n, 125.4 if y is None else y) if y is not None else rim.copy()
        rings.append(np.c_[R[:, 0], yy, R[:, 1]])
    V = []; VT = []; F = []
    def add(p, uv): V.append(tuple(map(float, p))); VT.append(tuple(map(float, uv))); return len(V)
    vof = lambda y: DV * (y - 97.9) + 0.70; per = np.r_[0, np.cumsum(np.linalg.norm(np.diff(rings[2][:, [0, 2]], axis=0), axis=1))]
    for a in range(len(rings) - 1):
        lo, hi = rings[a], rings[a + 1]
        for i in range(n - 1):
            q = [lo[i], lo[i + 1], hi[i + 1], hi[i]]; uv = [(per[i] * DU, vof(lo[i][1])), (per[i + 1] * DU, vof(lo[i + 1][1])), (per[i + 1] * DU, vof(hi[i + 1][1])), (per[i] * DU, vof(hi[i][1]))]
            F.append([add(q[k], uv[k]) for k in range(4)])
    # the top: two rings in from the rim and a centre, a low uneven dome
    loop = np.vstack([rings[-1], np.c_[f_top[:, 0], np.full(len(f_top), 125.4), f_top[:, 1]][1:-1]]); m = len(loop); c3 = np.array([G[0], 0.0, G[1]])
    def inner(f, lift):
        R = c3 + (loop - c3) * f; R[:, 1] = loop[:, 1] + lift + np.array([1.2 * np.sin(2 * np.pi * (3 * k / m + f)) for k in range(m)]); return R
    caps = [loop, inner(0.72, 2.0), inner(0.38, 3.4)]; tuv = lambda p: (p[0] * DU, p[2] * DU)
    for a in range(2):
        lo, hi = caps[a], caps[a + 1]
        for i in range(m):
            q = [lo[i], lo[(i + 1) % m], hi[(i + 1) % m], hi[i]]; F.append([add(x, tuv(x)) for x in q])
    top = np.array([G[0], 125.4 + 4.2, G[1]])
    for i in range(m):
        q = [caps[2][i], caps[2][(i + 1) % m], top]; F.append([add(x, tuv(x)) for x in q])
    return V, VT, F

def main():
    V, VT, F = build()
    with open(OUT, 'w') as f:
        f.write('# SRC Mountain: the plateau of sections 1280 .. 1282 completed (plateau1995.py). OBJ axes of the course export.\n')
        f.write('o hm_plateau\n'); [f.write('v %.3f %.3f %.3f\n' % p) for p in V]; [f.write('vt %.4f %.4f\n' % t) for t in VT]
        f.write('usemtl @near:%.1f,%.1f,%.1f\n' % REF); [f.write('f ' + ' '.join('%d/%d' % (k, k) for k in fc) + '\n') for fc in F]
    print('written %s: %d faces, %d vertices, sha1 %s' % (OUT, len(F), len(V), hashlib.sha1(open(OUT, 'rb').read()).hexdigest()[:12]))

if __name__ == '__main__': main()
