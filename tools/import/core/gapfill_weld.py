"""Seams welded shut (user: "I asked for the seams to be welded shut"): the openings between ground and the foot of what
stands on it - roadside walls, house fronts, cliffs, kerbs, barrier boards - and between the SR3 road strip and its sides.

    weld(faces, ground, rd, h_at, tile_for, stat) -> filler faces      (called by gapfill_gen.terrain)
    python gapfill_weld.py <dump.pkl> [title]                          seam scan of a face-list dump (GAPFILL_DUMP)

A FOOT is the lowest edge of an opaque upright polygon within 40 m of the road that does not stand on another upright
polygon. Along every foot, every 2 m at most:
  * ground (1995 lying polygons, the SR3 road strip, the verge, the shelves) within 1.5 m sideways and 1 m of height: a
    filler strip from the ground's edge to the foot line, sloping when the two differ in height, in the ground's own tile.
    No crack can stay: on the wall side the strip ends 2 cm BEHIND the foot line at the foot's height, on the ground side it
    runs 20 cm under the ground's edge, a few cm lower (so ruts in the deformable road cannot open it) and always tilted more
    than 3 degrees against the ground it tucks under, which keeps the pair out of the z-fight gate.
  * no ground near: the wall goes on downwards as a skirt into the hillside (rock tile of the place).
Seam scan: for the same feet, sampled every 0.5 m, the distance to the nearest lying surface (plan distance and height
together); a foot that another upright polygon continues below, that stands in the water or that is in the ground counts as closed (0). Histogram printed."""
import os, sys, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fill1995 as F
import overlay_bake as OB

def _closest(p, H, Y):
    """point p (x, z) against the convex plan polygon H (k x 2) with heights Y -> (plan distance, nearest point x, z, height there, inward unit vector there)"""
    k = len(H); best = (1e9, 0.0, 0.0, 0.0); ins = True; ar = sum(H[i, 0] * H[(i + 1) % k, 1] - H[(i + 1) % k, 0] * H[i, 1] for i in range(k))
    for i in range(k):
        a, b = H[i], H[(i + 1) % k]; e = b - a; L2 = max(float(e @ e), 1e-12); t = min(max(float((p - a) @ e) / L2, 0.0), 1.0); q = a + t * e; d = float(np.hypot(*(p - q)))
        if d < best[0]: best = (d, q[0], q[1], Y[i] + t * (Y[(i + 1) % k] - Y[i]))
        cr = e[0] * (p[1] - a[1]) - e[1] * (p[0] - a[0]); ins &= (cr >= 0) if ar > 0 else (cr <= 0)
    c = H.mean(0)
    if ins:
        A = np.c_[H, np.ones(k)]; pc = np.linalg.lstsq(A, Y, rcond=None)[0]; return 0.0, float(p[0]), float(p[1]), float(pc[0] * p[0] + pc[1] * p[1] + pc[2]), c
    return best[0], best[1], best[2], best[3], c

def _closest_fast(px, pz, rec):
    """_closest on plain numbers, for Lying.near (2.5 million calls a build, 35 microseconds each through numpy = 90 s; profile 2026-10-08).
    rec = (corners [(x, z)], heights [y], area sign, plane (a, b, c) of the heights, centre)"""
    H, Y, pos, pl, c = rec[:5]; k = len(H); bd = 1e9; bx = bz = by = 0.0; ins = True; a = H[-1]; ya = Y[-1]
    for i in range(k):
        b = H[i]; yb = Y[i]; ex = b[0] - a[0]; ez = b[1] - a[1]; L2 = ex * ex + ez * ez
        if L2 < 1e-12: L2 = 1e-12
        t = ((px - a[0]) * ex + (pz - a[1]) * ez) / L2; t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t); qx = a[0] + t * ex; qz = a[1] + t * ez; d = ((px - qx) ** 2 + (pz - qz) ** 2) ** 0.5
        if d < bd: bd = d; bx = qx; bz = qz; by = ya + t * (yb - ya)
        cr = ex * (pz - a[1]) - ez * (px - a[0])
        if (cr < 0) if pos else (cr > 0): ins = False
        a = b; ya = yb
    if ins: return 0.0, px, pz, pl[0] * px + pl[1] * pz + pl[2], c
    return bd, bx, bz, by, c

def _same_near(a, b):
    if a is None or b is None: return a is None and b is None
    return all(abs(x - y) <= 1e-9 for x, y in zip(a[:5], b[:5])) and a[5] == b[5] and np.array_equal(a[6], b[6])
class Lying:
    """lying opaque faces in a 4 m grid.
    (fastgeo.LyingC holds them and answers near(); _OldLying below is the Python original it was ported from: 8 s to build for a whole
    course - a least-squares plane per polygon - and 80 microseconds a look-up; profile 2026-10-08)"""
    def __init__(self, faces, skip=()):
        import fastgeo
        self._c = None; self._o = None
        if fastgeo.ON:
            try: self._c = fastgeo.LyingC(faces, skip)
            except ValueError: self._c = None
        if self._c is None or fastgeo.CHECK: self._o = _OldLying(faces, skip)
        if self._c is None: self.near = self._o.near
        elif not fastgeo.CHECK: self.near = self._c.near
    def near(self, p3, reach=1.5, dy=1.0):                              # (only reached with SR3_FASTGEO_CHECK=1: both answers, compared)
        import fastgeo
        a = self._o.near(p3, reach, dy); b = self._c.near(p3, reach, dy); fastgeo.note('gapfill_weld.Lying.near', _same_near(a, b), (tuple(p3), a, b)); fastgeo.note('gapfill_weld.Lying.near to the last bit', a is None or a[:5] == b[:5]); return b
class _OldLying:
    """the Python original of Lying (fallback and reference)"""
    def __init__(self, faces, skip=()):
        self.g = collections.defaultdict(list); self.P = []; self.R = []
        for fc in faces:
            if str(fc[0]).endswith('_t') or str(fc[1]).startswith(skip): continue
            P = np.asarray(fc[2], float); n, ar = OB._newell(P)
            if abs(n[1]) < 0.3 or ar < 0.01: continue
            k = len(self.P); H_ = P[:, [0, 2]]; Y_ = P[:, 1]; kk = len(H_); ar_ = sum(H_[i, 0] * H_[(i + 1) % kk, 1] - H_[(i + 1) % kk, 0] * H_[i, 1] for i in range(kk))
            pl_ = np.linalg.lstsq(np.c_[H_, np.ones(kk)], Y_, rcond=None)[0]; mn_ = H_.min(0); mx_ = H_.max(0)
            self.P.append((H_.copy(), Y_.copy(), fc[0])); self.R.append(([tuple(q) for q in H_.tolist()], Y_.tolist(), ar_ > 0, (float(pl_[0]), float(pl_[1]), float(pl_[2])), H_.mean(0), float(mn_[0]), float(mn_[1]), float(mx_[0]), float(mx_[1]), float(Y_.min()), float(Y_.max())))
            lo = np.floor((mn_ - 1.6) / 4).astype(int); hi = np.floor((mx_ + 1.6) / 4).astype(int)
            for x in range(lo[0], hi[0] + 1):
                for z in range(lo[1], hi[1] + 1): self.g[(x, z)].append(k)
    def near(self, p3, reach=1.5, dy=1.0):
        """-> (3D gap, plan distance, x, z, y, material, centre of that polygon) of the nearest lying face, or None"""
        best = None; px = float(p3[0]); py = float(p3[1]); pz = float(p3[2]); R = self.R
        for k in self.g.get((int(px // 4), int(pz // 4)), ()):
            r = R[k]
            if px < r[5] - reach or px > r[7] + reach or pz < r[6] - reach or pz > r[8] + reach: continue          # (too far in plan to be within reach: no need to measure)
            d, x, z, y, c = _closest_fast(px, pz, r); mat = self.P[k][2]
            if d > reach or abs(y - py) > dy: continue
            g = (d * d + (y - py) ** 2) ** 0.5
            if best is None or g < best[0]: best = (g, d, x, z, y, mat, c)
        return best

def feet(faces, cen, ix, limit=40.0):
    """-> [(face index, A, B)]: lowest edge of every opaque upright face near the road that no upright face continues below
    (the tests of _old_feet on whole arrays; only the look-up of what stands under a foot is left to a loop)"""
    import fastgeo
    if not fastgeo.ON or not len(faces): return _old_feet(faces, cen, ix, limit)
    n = len(faces); G = fastgeo.prep(faces); cxz = np.ascontiguousarray(np.asarray(cen, float)[:, [0, 2]]); rows = []
    skip = np.fromiter((str(f[0]).endswith('_t') or str(f[1]).startswith(('hf_', 'obj_', 'verge', 'road', 'sea')) for f in faces), bool, n)
    ok = ~skip & ~((np.abs(G.nr[:, 1]) >= 0.3) | (G.ar < 0.05) | (G.lens < 3))
    for k, ii in fastgeo.by_len(G.lens):
        ii = ii[ok[ii]]
        if not len(ii): continue
        P = G.X[G.off[ii][:, None] + np.arange(k)[None, :]]; o = np.argsort(P[:, :, 1], axis=1, kind='stable'); r = np.arange(len(ii)); A = P[r, o[:, 0]]; B = P[r, o[:, 1]]
        h = np.hypot(A[:, 0] - B[:, 0], A[:, 2] - B[:, 2]); m = (A + B) / 2
        keep = ~((h < 0.3) | (np.abs(A[:, 1] - B[:, 1]) > 0.6 * h + 0.05)); keep[keep] = ~(fastgeo.mindist2(m[keep][:, [0, 2]], cxz) > limit * limit)
        rows += [(fi, A[q], B[q], m[q]) for q, fi in zip(np.nonzero(keep)[0].tolist(), ii[keep].tolist())]
    rows.sort(key=lambda t: t[0]); out = []
    for fi, A, B, m in rows:
        if any(y0 < m[1] - 0.05 and y1 > m[1] - 0.5 for y0, y1, k, cut in ix.uprights(m[0], m[2], 0.25) if k != fi and not cut): continue
        out.append((fi, A, B))
    if fastgeo.CHECK: old = _old_feet(faces, cen, ix, limit); fastgeo.note('gapfill_weld.feet', len(old) == len(out) and all(a[0] == b[0] and np.array_equal(a[1], b[1]) and np.array_equal(a[2], b[2]) for a, b in zip(old, out)), (len(old), len(out)))
    return out
def _old_feet(faces, cen, ix, limit=40.0):                             # (the Python original of feet: fallback and reference)
    out = []; cxz = cen[:, [0, 2]]
    for fi, (mat, sec, P, UV) in enumerate(faces):
        if str(mat).endswith('_t') or str(sec).startswith(('hf_', 'obj_', 'verge', 'road', 'sea')): continue
        P = np.asarray(P, float); n, ar = OB._newell(P)
        if abs(n[1]) >= 0.3 or ar < 0.05 or len(P) < 3: continue
        o = np.argsort(P[:, 1]); A, B = P[o[0]], P[o[1]]
        if np.hypot(A[0] - B[0], A[2] - B[2]) < 0.3 or abs(A[1] - B[1]) > 0.6 * np.hypot(A[0] - B[0], A[2] - B[2]) + 0.05: continue
        m = (A + B) / 2
        if ((cxz - m[[0, 2]]) ** 2).sum(1).min() > limit * limit: continue
        if any(y0 < m[1] - 0.05 and y1 > m[1] - 0.5 for y0, y1, k, cut in ix.uprights(m[0], m[2], 0.25) if k != fi and not cut): continue
        out.append((fi, A, B))
    return out

ALT = {}                                                               # id(filler face) -> [steeper filler, skirt under the wall]: what gapfill_gen falls back to when a filler would lie in the plane of what it joins
CARRY_MAX = 1.2                                                        # metres a wall may be carried down to close a seam
def weld(faces, ground, rd, h_at, tile_for, stat, sea=-0.5):
    """faces: importer faces (course + backdrop); ground: every lying thing that is not the hillside (faces + road strip +
    verge); h_at(x, z) = height of the hillside; tile_for(xz, classes) -> tile. -> filler faces.
    A filler starts EXACTLY on the foot line (the wall's own foot corners and points on the straight edge between them) and
    ends 20 cm under the ground's edge, always falling from the wall end (at least 8 %), so it is never parallel to flat
    ground. ALT holds a steeper version and a skirt (the wall carried 0.6 m further down) for the cases where even that
    lies in the plane of a polygon it joins: a seam is never left open because of the z-fight gate."""
    cen = np.asarray(rd['V'][:, rd['hw']], float); ix = F.Index(list(faces) + list(ground[len(faces):])); G = Lying(ground); out = []; ALT.clear()
    import retex
    lab = {k: v[0] for k, v in retex.labels().items()}
    natural = lambda m: lab.get(OB.ORIGIN.get(m, m)) in ('rock', 'grass', 'cobbles', 'asphalt')        # a filler never takes a roof, wall or wood tile (or the road proxy): then the nearest ground tile
    r3 = lambda v: tuple(round(float(x), 3) for x in v)
    def skirt(p0, p1, mat, su):
        ys = []
        for p in (p0, p1):
            below = [y for y, q in ix.heights(p[0], p[2], True) if y < p[1] - 0.02 and y > p[1] - 6.0]; ys.append(min((max(below) if below else max(h_at(p[0], p[2]), sea - 1.2)) - 0.3, p[1] - 0.05))
        return (mat, sec, [r3(p0), r3(p1), r3((p1[0], ys[1], p1[2])), r3((p0[0], ys[0], p0[2]))], [(0.0, 0.0), (su, 0.0), (su, (p1[1] - ys[1]) / 8.0), (0.0, (p0[1] - ys[0]) / 8.0)])
    for fi, A, B in feet(faces, cen, ix):
        ln = float(np.hypot(B[0] - A[0], B[2] - A[2])); nseg = max(1, int(np.ceil(ln / 2.0))); pts = [A + (B - A) * (k / nseg) for k in range(nseg + 1)]; hits = [G.near(p) for p in pts]
        sec = 'hf_weld_%03d_%03d' % (int((A[0] + 800) // 64), int((A[2] + 800) // 64)); su = ln / nseg / 8.0
        for k in range(nseg):
            p0, p1, h0, h1 = pts[k], pts[k + 1], hits[k], hits[k + 1]; hm = G.near((p0 + p1) / 2)
            if h0 is not None and h1 is not None and hm is not None and max(h0[0], h1[0], hm[0]) <= 0.015: continue
            rock = tile_for(((p0 + p1) / 2)[[0, 2]], ('rock', 'grass'))
            if h0 is not None and h1 is not None:
                vers = []; mat = None
                for extra in (0.0, 0.25):
                    quad = []
                    for p, h in ((p0, h0), (p1, h1)):
                        g, d, x, z, y, m_, c = h; inw = np.array([c[0] - x, 0.0, c[1] - z]); li = np.linalg.norm(inw); inw = inw / li if li > 1e-6 else np.zeros(3)
                        t = np.array([x, 0.0, z]) + inw * 0.2; run = float(np.hypot(t[0] - p[0], t[2] - p[2])); t[1] = min(y, p[1]) - max(0.04, 0.08 * run) - extra
                        quad.append(t); mat = mat or (OB.ORIGIN.get(m_, m_) if natural(m_) else None)
                    Q = np.array([p0, p1, quad[1], quad[0]]); nn, ar = OB._newell(Q); w = float(np.linalg.norm(Q[3] - Q[0])); u0 = (k * ln / nseg) / 8.0 % 1.0; uv = [(u0, 0.0), (u0 + su, 0.0), (u0 + su, w / 8.0), (u0, w / 8.0)]
                    vers.append((Q, uv, ar))
                mat = mat or tile_for(((p0 + p1) / 2)[[0, 2]], ('asphalt', 'cobbles', 'grass', 'rock')) or rock
                if mat is None: continue
                sk_ = skirt(p0, p1, mat, su); fs = [(mat, sec, [r3(x) for x in Q], uv) for Q, uv, ar in vers if ar >= 0.002] + ([sk_] if max(sk_[2][0][1] - sk_[2][3][1], sk_[2][1][1] - sk_[2][2][1]) <= CARRY_MAX else [])
                if not fs: continue
                out.append(fs[0]); ALT[id(fs[0])] = fs[1:]; stat['seams welded: filler strips'] += 1
            else:                                                       # nothing to stand on within reach: the wall goes down into the ground under it / the hillside
                if rock is None: continue
                f_ = skirt(p0, p1, rock, su)
                if max(f_[2][0][1] - f_[2][3][1], f_[2][1][1] - f_[2][2][1]) < 0.06: continue
                if max(f_[2][0][1] - f_[2][3][1], f_[2][1][1] - f_[2][2][1]) > CARRY_MAX: continue          # the 'foot' is the lower edge of an overhang or of a rock face that starts above the road: carried down it stood as an upright slab of rock at the roadside (user, twice). Not a seam.
                out.append(f_); stat['seams welded: wall carried down into the hillside'] += 1
    return out

def seal(faces, rd, sink=0.4, log=print):
    """Last pass over the FINISHED face list: every wall foot the seam scan still finds open (no ground within 2 cm, nothing
    upright continuing below) gets its wall carried straight down to the surface under it (the texture simply continues).
    -> extra faces. The user asked for zero open seams ("WHY? still open"); this closes what the fillers could not."""
    sea = min([f[2][0][1] for f in faces if f[1] == 'sea'] or [-0.5]); cen = np.asarray(rd['V'][:, rd['hw']], float); allf = [f for f in faces if f[1] != 'sea']
    ix = F.Index(allf + F.road_faces(rd)); G = Lying(allf + F.road_faces(rd)); out = []; n_open = 0
    for fi, A, B in feet(allf, cen, ix):
        ln = float(np.hypot(B[0] - A[0], B[2] - A[2])); n = max(1, int(np.ceil(ln / 0.5))); bad = False
        for k in range(n + 1):
            p = A + (B - A) * (k / n); h = G.near(p, reach=1.5, dy=3.0); g = h[0] if h is not None else 9.0
            if p[1] <= sea + 0.6: g = 0.0
            elif any(y >= p[1] - 0.02 for y, q in ix.heights(p[0], p[2], True)): g = min(g, 0.0)
            if g > 0.02 and any(y0 < p[1] - 0.05 and y1 > p[1] - 0.03 for y0, y1, q, cut in ix.uprights(p[0], p[2], 0.05) if q != fi and not cut): g = 0.0
            if g > 0.02: bad = True; n_open += 1
        if not bad: continue
        mat, sec, P, UV = allf[fi]; P = np.asarray(P, float); UV = np.asarray(UV, float)
        ia = int(np.argmin(np.linalg.norm(P - A, axis=1))); ib = int(np.argmin(np.linalg.norm(P - B, axis=1))); ic = int(np.argmax(P[:, 1]))
        if ia == ib or P[ic, 1] - max(P[ia, 1], P[ib, 1]) < 0.05: continue
        def floor_(q):
            hs = [y for y, _ in ix.heights(float(q[0]), float(q[2]), True) if y < q[1] - 0.02]; return (max(hs) if hs else max(q[1] - 3.0, sea - 1.0)) - sink
        ya, yb = min(floor_(P[ia]), P[ia, 1] - 0.05), min(floor_(P[ib]), P[ib, 1] - 0.05)
        if max(P[ia, 1] - ya, P[ib, 1] - yb) > CARRY_MAX: continue
        grad = (UV[ic] - (UV[ia] + UV[ib]) / 2) / (P[ic, 1] - (P[ia, 1] + P[ib, 1]) / 2)             # uv per metre of height on this wall: the picture runs on downwards
        q = [tuple(P[ia]), tuple(P[ib]), (float(P[ib, 0]), float(yb), float(P[ib, 2])), (float(P[ia, 0]), float(ya), float(P[ia, 2]))]
        u = [tuple(UV[ia]), tuple(UV[ib]), tuple(UV[ib] - grad * (P[ib, 1] - yb)), tuple(UV[ia] - grad * (P[ia, 1] - ya))]
        out.append((mat, 'hf_seal_%s' % str(sec)[-4:], [tuple(map(float, x)) for x in q], [tuple(map(float, x)) for x in u]))
    log('       seal: %d open wall-foot samples -> %d walls carried down to the surface under them' % (n_open, len(out)))
    return out

def scan(faces, rd, title=''):
    """seam scan of a full face list (importer faces + extra, the road strip is added) -> histogram dict"""
    sea = min([f[2][0][1] for f in faces if f[1] == 'sea'] or [-0.5]); cen = np.asarray(rd['V'][:, rd['hw']], float); allf = [f for f in faces if f[1] != 'sea']; ix = F.Index(allf + F.road_faces(rd)); G = Lying(allf + F.road_faces(rd)); bins = collections.Counter(); worst = []
    for fi, A, B in feet(allf, cen, ix):
        ln = float(np.hypot(B[0] - A[0], B[2] - A[2])); n = max(1, int(np.ceil(ln / 0.5)))
        for k in range(n + 1):
            p = A + (B - A) * (k / n); h = G.near(p, reach=1.5, dy=3.0); g = h[0] if h is not None else 9.0
            if p[1] <= sea + 0.6: g = 0.0                                                          # the foot stands in the water
            elif any(y >= p[1] - 0.02 for y, q in ix.heights(p[0], p[2], True)): g = min(g, 0.0)         # ground at or above the foot: it is in the ground
            if g > 0.02 and any(y0 < p[1] - 0.05 and y1 > p[1] - 0.03 for y0, y1, q, cut in ix.uprights(p[0], p[2], 0.05) if q != fi and not cut): g = 0.0      # an upright face continues below
            bins['<= 2 cm' if g <= 0.02 else '2-5 cm' if g <= 0.05 else '5-20 cm' if g <= 0.2 else '20 cm-1 m' if g <= 1.0 else '> 1 m'] += 1
            if g > 0.02: worst.append((round(g, 2), tuple(np.round(p, 1).tolist()), allf[fi][1]))
    tot = sum(bins.values()); order = ['<= 2 cm', '2-5 cm', '5-20 cm', '20 cm-1 m', '> 1 m']
    print('seam scan %s: %d samples on wall feet within 40 m of the road: %s ; open (> 2 cm): %d = %.1f%%' % (title, tot, {k: bins[k] for k in order}, tot - bins['<= 2 cm'], 100.0 * (tot - bins['<= 2 cm']) / max(tot, 1)))
    worst.sort(reverse=True); print('   widest:', worst[:8]); return dict(bins), worst

if __name__ == '__main__':
    import pickle
    d = pickle.load(open(sys.argv[1], 'rb')); scan(d['faces'] + d['sky'] + d['extra'], d['rd'], sys.argv[2] if len(sys.argv) > 2 else '')
