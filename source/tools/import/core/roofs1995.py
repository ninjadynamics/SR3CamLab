"""Open gable ends of the 1995 houses get their triangle.
The 1995 town was only ever seen from the road, so pitched roofs are often two sloping quads with nothing closing the end
that faces away: from a free or replay camera the roof reads as a slab hanging in the air (user, 2026-10-07: "add the missing
wall/roof part to that building (like 1 triangle)"). Rule for every roof on the course: a SLOPING edge of a roof polygon
(eave end to ridge end) that no other polygon shares is an open end;
  - two such edges meeting at the ridge point  -> one gable triangle (eave, ridge, eave);
  - a single one (mono-pitch, half-hip)        -> a triangle down to the eave height under the ridge point.
The triangle takes the roof's own tile.   faces2 = gables(faces)  -> extra faces (importer format)"""
import collections
import numpy as np

def gables(faces, origin=None, log=print, min_rise=0.3):
    import retex
    if origin is None:
        import overlay_bake as OB
        origin = OB.ORIGIN
    lab = {k: v[0] for k, v in retex.labels().items()}; cls = lambda m: lab.get(origin.get(m, m))
    rk = lambda p: (round(float(p[0]), 1), round(float(p[1]), 1), round(float(p[2]), 1))
    edges = collections.Counter()
    for mat, sec, P, UV in faces:
        if str(mat).endswith('_t'): continue
        for i in range(len(P)): edges[frozenset((rk(P[i]), rk(P[(i + 1) % len(P)])))] += 1
    ends = collections.defaultdict(list)                                # ridge point -> [(eave point, material, section)]
    for mat, sec, P, UV in faces:
        if cls(mat) != 'roof' or str(sec).startswith('hf_'): continue
        Q = np.asarray(P, float); n = np.cross(Q[1] - Q[0], Q[2] - Q[0]); ln = np.linalg.norm(n)
        if ln < 1e-6 or abs(n[1]) / ln < 0.3: continue
        for i in range(len(Q)):
            a, b = Q[i], Q[(i + 1) % len(Q)]
            if abs(a[1] - b[1]) < min_rise or abs(a[1] - b[1]) > 8.0 or edges[frozenset((rk(a), rk(b)))] != 1: continue
            lo, hi = (a, b) if a[1] < b[1] else (b, a); ends[rk(hi)].append((lo, hi, mat, sec))
    out = []; two = one = 0
    for key, lst in ends.items():
        hi = lst[0][1]; mat = lst[0][2]; sec = 'gable_' + str(lst[0][3])[-4:]
        if len(lst) >= 2:
            lo1, lo2 = lst[0][0], max(lst[1:], key=lambda e: np.linalg.norm(e[0] - lst[0][0]))[0]
            if np.linalg.norm(lo1 - lo2) < 0.5: continue
            tri = [lo1, hi, lo2]; two += 1
        else:
            lo = lst[0][0]; foot = np.array([hi[0], lo[1], hi[2]])
            if np.linalg.norm(foot - lo) < 0.5: continue
            tri = [lo, hi, foot]; one += 1
        T = np.array(tri); w = np.linalg.norm(T[2] - T[0]); h = T[1][1] - min(T[0][1], T[2][1]); t = float(np.clip(np.dot(T[1] - T[0], T[2] - T[0]) / max(w * w, 1e-9), 0.0, 1.0))
        uv = [(0.0, 0.0), (t * min(w / 4.0, 1.9), min(h / 4.0, 1.9)), (min(w / 4.0, 1.9), 0.0)]
        out.append((mat, sec, [tuple(map(float, q)) for q in T], uv))
    log('       roofs: %d open gable ends closed (%d between two slopes, %d under a single slope)' % (len(out), two, one))
    return out


def eave_walls(faces, ground_index, origin=None, log=print, sea=-0.5):
    """A roof whose eave has NO wall under it (the side of a house the 1995 game never showed): the roof reads as a slab
    sticking out into the air (user's screenshot of the town, 2026-10-07). Every free, level low edge of a roof polygon
    without an upright face below it gets a wall from the eave down to the surface under it, in the tile of the nearest
    house wall (same picture density, top row at the eave).  -> extra faces"""
    import retex
    if origin is None:
        import overlay_bake as OB
        origin = OB.ORIGIN
    lab = {k: v[0] for k, v in retex.labels().items()}; cls = lambda m: lab.get(origin.get(m, m))
    rk = lambda p: (round(float(p[0]), 1), round(float(p[1]), 1), round(float(p[2]), 1))
    edges = collections.Counter(); donors = []
    for mat, sec, P, UV in faces:
        if str(mat).endswith('_t'): continue
        for i in range(len(P)): edges[frozenset((rk(P[i]), rk(P[(i + 1) % len(P)])))] += 1
        c = cls(mat)
        if c and str(c).startswith('house') and not str(sec).startswith('hf_'):
            Q = np.asarray(P, float); U = np.asarray(UV, float); n = np.cross(Q[1] - Q[0], Q[2] - Q[0]); ln = np.linalg.norm(n)
            hz = float(np.hypot(np.ptp(Q[:, 0]), np.ptp(Q[:, 2]))); vt = float(np.ptp(Q[:, 1]))
            if ln > 1e-6 and abs(n[1]) / ln < 0.2 and hz > 2.0 and vt > 2.0 and np.ptp(U[:, 0]) > 1e-3 and np.ptp(U[:, 1]) > 1e-3:
                donors.append((Q.mean(0), float(Q[:, 1].max()), mat, float(np.ptp(U[:, 0])) / hz, float(np.ptp(U[:, 1])) / vt, float(U[:, 0].min()), float(U[:, 1].max())))
    if not donors: log('       roofs: no house wall to take a tile from'); return []
    DC = np.array([d[0] for d in donors]); DT = np.array([d[1] for d in donors]); out = []; stat = collections.Counter()
    for mat, sec, P, UV in faces:
        if cls(mat) != 'roof' or str(sec).startswith('hf_'): continue
        Q = np.asarray(P, float); n = np.cross(Q[1] - Q[0], Q[2] - Q[0]); ln = np.linalg.norm(n)
        if ln < 1e-6 or abs(n[1]) / ln < 0.3: continue
        cen = Q.mean(0); lowy = float(Q[:, 1].min())
        for i in range(len(Q)):
            a, b = Q[i], Q[(i + 1) % len(Q)]; L = float(np.hypot(b[0] - a[0], b[2] - a[2]))
            if L < 1.0 or abs(a[1] - b[1]) > 0.3 or max(a[1], b[1]) > lowy + 0.3 or edges[frozenset((rk(a), rk(b)))] != 1: continue
            m = (a + b) / 2; o = np.array([m[0] - cen[0], 0.0, m[2] - cen[2]]); o /= max(np.linalg.norm(o), 1e-9)
            walled = 0
            for t in (0.25, 0.5, 0.75):
                q = a + (b - a) * t
                if any((not cut) and y1 >= q[1] - 1.0 and y0 < q[1] - 1.5 for y0, y1, k, cut in ground_index.uprights(float(q[0]), float(q[2]), 2.5)): walled += 1      # 2.5 m: an eave may overhang its facade; a new wall in front of a facade would hide its windows
            if walled >= 2: stat['eaves that have a wall'] += 1; continue
            bot = []
            for q in (a, b):
                x, z = float(q[0] + 0.4 * o[0]), float(q[2] + 0.4 * o[2]); hs = [h for h, _ in ground_index.heights(x, z, True) if h < q[1] - 0.5]
                bot.append((max(hs) if hs else sea) - 0.3)
            if max(a[1] - bot[0], b[1] - bot[1]) < 0.5: continue
            j = int(np.argmin(((DC - m) ** 2).sum(1) + 4.0 * (DT - m[1]) ** 2)); _, _, dmat, du, dv, u0, v1 = donors[j]
            quad = [tuple(map(float, a)), tuple(map(float, b)), (float(b[0]), float(bot[1]), float(b[2])), (float(a[0]), float(bot[0]), float(a[2]))]
            uv = [(u0, v1), (u0 + L * du, v1), (u0 + L * du, v1 - (b[1] - bot[1]) * dv), (u0, v1 - (a[1] - bot[0]) * dv)]
            out.append((dmat, 'eave_' + str(sec)[-4:], quad, uv)); stat['walls added under open eaves'] += 1
    log('       roofs: %s' % dict(stat))
    return out
