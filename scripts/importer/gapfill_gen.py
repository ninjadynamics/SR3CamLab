"""Gap fill for an imported 1995 course: natural banks where the 1995 data has no polygon.

    python gapfill_gen.py [game] [course]        -> classic/courses/<game>/<course dir>/src_course<N>_handfill.obj + .mtl
                                                    + work/previews/gapfill_<name>_plan.png

The 1995 course is a ribbon: road, a low wall or a strip of rock, then nothing (its low camera never saw past the wall).
SR3's camera does. This writes the missing ground ONCE into a source file that fill1995.handfill merges on every build; the
build never regenerates it, so the file can be edited by hand afterwards. Re-running this script overwrites it.

User's rule: sober, natural, minimal. Slopes and banks only, nothing man-made, tiles of the neighbourhood, a few rocks
where one slope would be a long repeating surface.

Method, per road slice and side (every STEP m, plus the exact slice where a stretch begins and ends):
  1. walk outwards from the road edge over the ground that hangs together with the road (1995 polygons, the SR3 road
     strip); its outer end is where the fill starts, at the foot of the wall standing there if there is one.
     No fill when that end is closed (a rock face or house rising more than 2.5 m) or when the ground ends well above the road
     (a bank that hides what is behind it).
  2. look further out for what the fill can end on: other ground (first lying polygon, also fill made earlier: every gap is
     filled once), a rock face at that height, else the sea (1 m under the sheet).
  3. profile: a shelf as wide as the trees and lamps standing there need (their feet are at road height), then a slope,
     slightly hollow, to the end point; about 34 degrees to the sea, whatever it takes to reach other ground. On the inside
     of bends the reach stays inside the bend's radius.
Neighbouring profiles are joined row by row into ONE surface per stretch (shared corners, no separate ramps).
Since the island pass the profiles only make the shelf and a short skirt; the slopes are ONE hillside under the whole course
(terrain(): a height grid falling away at 38 degrees from every piece of ground of the ribbon, held under every lying polygon,
valley floor inside the lap instead of sea, cliffs under rock that floated, boulders). See terrain().
Tiles: the nearest grass / soil tile of the course for shelves and gentle ground, the nearest rock tile for slopes; one tile
per face, at most 1.2 repeats, mirrored and shifted from face to face so that no pattern runs along a bank.
Rocks: small boulders (six faces) in groups on long slopes into the sea, near the water line.
Nothing is random: every choice comes from a hash of the slice number. Faces that would lie parallel on or close over
another face (overlay_bake.find_pairs) are taken out again, and the count is printed."""
import os, sys, collections, hashlib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fill1995 as F
import overlay_bake as OB

STEP = 6                                                               # m between profiles
REACH = 90.0                                                           # how far a bank may run
SLOPE = np.tan(np.radians(34.0)); HIGH = np.tan(np.radians(50.0)); STEEP = np.tan(np.radians(62.0))
LEDGE = 22.0; SCARP = 3.5                                             # a road higher than LEDGE m above the sea gets a shelf and a rock scarp SCARP m deep (the 1995 course is a ribbon with rock skirts up there), not a slope down to the water
SPAN = 2.0                                                             # a stretch never reaches further out than this times its length along the road
REP = 8.0                                                              # metres per tile repeat
ROW = 9.0                                                              # longest face down a slope
INFO = {}

def _h(*a): return int(hashlib.md5(repr(a).encode()).hexdigest()[:8], 16) / 2.0 ** 32

class Ground:
    """what is there: the importer's faces + the road strip, and the fill made so far"""
    def __init__(self, faces): self.ix = F.Index(faces); self.new = []; self.nx = None
    def add(self, faces): self.new += faces; self.nx = F.Index(self.new)
    def heights(self, x, z):
        out = [y for y, k in self.ix.heights(x, z, True)]
        if self.nx is not None: out += [y for y, k in self.nx.heights(x, z, True)]
        return out
    def uprights(self, x, z, r=0.45):
        out = [(a, b) for a, b, k, cut in self.ix.uprights(x, z, r) if not cut]
        if self.nx is not None: out += [(a, b) for a, b, k, cut in self.nx.uprights(x, z, r) if not cut]
        return out

def _tiles(faces):
    """centres and tiles of the course's natural polygons -> nearest(xz, classes) -> tile"""
    import retex
    lab = {k: v[0] for k, v in retex.labels().items()}; pts = collections.defaultdict(list); ok = {}
    def plain(mat):
        """a tile fit for open ground: evenly lit (the tunnel rock fades to black) and not dark"""
        if mat not in ok:
            import build_classic as BC
            px = BC.tile_pixels(mat); ok[mat] = False
            if px is not None:
                g = px[0].astype(float).mean(2); h = g.shape[0]; bands = [g[k * h // 4:(k + 1) * h // 4].mean() for k in range(4)]; ok[mat] = 30 < g.mean() < 170              # (a pale sandy tile stood out as a bright band)
        return ok[mat]
    for mat, sec, P, UV in faces:
        c = lab.get(OB.ORIGIN.get(mat, mat))
        if c is None or str(sec).startswith('obj_') or str(mat).endswith('_t') or str(mat).startswith('bake_'): continue
        P = np.asarray(P, float); n, a = OB._newell(P)
        if a < 2.0 or not plain(mat) or c not in ('rock', 'grass', 'asphalt', 'cobbles'): continue      # 'dirt' / 'sand' / 'gravel' labels turned out to hold roof planks and pale wall tiles: never used
        pts[c].append((P[:, [0, 2]].mean(0), mat))
        if abs(n[1]) >= 0.5: pts[c + '/lying'].append((P[:, [0, 2]].mean(0), mat))
    arr = {c: (np.array([p for p, m in v]), [m for p, m in v]) for c, v in pts.items()}
    def nearest(xz, classes, many=1, lying=False):
        if lying: classes = tuple(c + '/lying' for c in classes)
        """the nearest tile of these classes; many > 1: also other tiles not more than 1.6 x as far (to mix)"""
        cand = {}
        for c in classes:
            if c not in arr: continue
            d = ((arr[c][0] - xz) ** 2).sum(1)
            for k in np.argsort(d)[:40]:
                m = arr[c][1][k]
                if m not in cand or d[k] < cand[m]: cand[m] = float(d[k])
        if not cand: return None
        o = sorted(cand, key=lambda m: (cand[m], m)); o = [m for m in o if cand[m] <= max(cand[o[0]] * 2.56, 400.0)][:many]
        return o[0] if many == 1 else tuple(o)
    return nearest, {c: len(v) for c, v in pts.items()}

def generate(cfg, rd, faces, log=print):
    """faces: the importer's course + backdrop faces (after load_visual). -> fill faces (SR3 coordinates)"""
    sea = (cfg.get('sea') or {}).get('level', -0.5); V = rd['V']; hw = rd['hw']; cen = np.asarray(V[:, hw], float); lat = rd['lat']; D = rd['D']; n = len(cen)
    wl = rd.get('wl', np.full(n, float(cfg.get('half_width', 7)))); wr = rd.get('wr', np.full(n, float(cfg.get('half_width', 7))))
    road = F.road_faces(rd); G = Ground(list(faces) + road); nearest, ncls = _tiles(faces)
    # signed curvature (towards +lat = positive), smoothed over 17 m: the reach on the inside of a bend
    dD = np.roll(D, -1, 0) - D; kap = (dD * lat).sum(1); kk = np.ones(17) / 17.0; kap = np.convolve(np.concatenate([kap[-8:], kap, kap[:8]]), kk, 'valid')
    # feet of the boards (trunks, lamp posts) that stand on nothing: how wide the shelf must be
    allf = list(faces) + road; hang = F.hanging_boards(allf, 1.0); need_w = collections.defaultdict(float); need_y = {}
    for fi, a, b in hang:
        P = np.asarray(allf[fi][2], float); m = (P[a] + P[b]) / 2; k = int(np.argmin((cen[:, 0] - m[0]) ** 2 + (cen[:, 2] - m[2]) ** 2)); s = float((m - cen[k]) @ lat[k])
        if abs(s) < 30:
            for t in range(-5, 6):
                q = ((k + t) % n, int(s > 0)); need_w[q] = max(need_w[q], abs(s)); need_y[q] = min(need_y.get(q, 1e9), float(min(P[a, 1], P[b, 1])))
    stat = collections.Counter()

    def profile(i, sd, cap=None):
        sg = 1.0 if sd else -1.0; c = cen[i]; l = lat[i] * sg; yr = c[1]; edge = float((wr if sd else wl)[i])
        pt = lambda s: (c[0] + l[0] * s, c[2] + l[2] * s)
        near = lambda s: [y for y in G.heights(*pt(s)) if yr - 4.0 <= y <= yr + 6.0]
        s = max(edge - 1.0, 0.0); last = None; yl = yr; ended = False
        while s <= edge + 75.0:
            g = near(s)
            if g: last = s; yl = min(g, key=lambda y: abs(y - yr))
            elif last is not None and s - last > 2.0: ended = True; break
            s += 0.5
        if last is None or not ended: return None
        a, b = last, last + 0.5
        for _ in range(4):
            m = (a + b) / 2
            if near(m): a = m
            else: b = m
        s0 = a + 0.04
        behind = yl > yr + 1.8
        if behind and need_w.get((i, sd), 0.0) <= s0: stat['closed: the ground ends on a bank above the road, nothing stands behind it'] += 1; return None
        ups = G.uprights(*pt(a + 0.1))
        if any(y1 > yr + 2.6 and y0 < yr + 1.5 for y0, y1 in ups) and not behind: stat['closed: rock face or house'] += 1; return None
        foot = [y0 for y0, y1 in ups if y1 <= yr + 2.6 and y0 > yr - 3.0]; y0 = min(foot + [yl]) - 0.02
        if behind: y0 = min(y0, need_y[(i, sd)] + 0.1); stat['profiles behind a bank (trees stand there)'] += 1          # the ground the trees behind the bank stand on
        w = float(np.clip(max(need_w.get((i, sd), 0.0) - s0 + 1.5, 1.5), 1.5, 16.0)); high = True                                                    # the slope itself is the hillside's job (terrain); LEDGE is no longer used
        reach = REACH if cap is None else cap; kin = kap[i] * sg                                 # > 0: this side is the inside of the bend
        if kin > 1e-4: reach = min(reach, max(1.0 / kin - 2.0 - s0, 0.0) + 0.0)
        if reach < 1.0: stat['skipped: inside of a tight bend'] += 1; return None
        sl = float(np.clip((y0 - sea + 1.0) / max(REACH - w - 4.0, 1.0), SLOPE, HIGH))
        if high: sl = STEEP; reach = min(reach, w + SCARP / STEEP)
        yb = lambda s: y0 - 0.04 * min(s - s0, w) - sl * max(0.0, s - s0 - w)
        s = s0 + 0.5; kind = 'air'; s1 = s0 + reach; y1 = None
        while s <= s0 + reach:
            hs = [y for y in G.heights(*pt(s)) if sea - 3.0 <= y <= y0 + 3.0]
            if hs:
                a, b = s - 0.5, s
                for _ in range(3):
                    m = (a + b) / 2
                    if [y for y in G.heights(*pt(m)) if sea - 3.0 <= y <= y0 + 3.0]: b = m
                    else: a = m
                hs = [y for y in G.heights(*pt(b)) if sea - 3.0 <= y <= y0 + 3.0]; kind = 'ground'; s1 = b - 0.04; y1 = max(hs) - 0.03; break
            if any(u0 <= yb(s) + 0.5 and u1 >= yb(s) - 0.2 for u0, u1 in G.uprights(*pt(s), 0.3)): kind = 'rock'; s1 = s + 0.3; y1 = yb(s + 0.3); break
            if yb(s) <= sea - 1.0: kind = 'sea'; s1 = s; y1 = sea - 1.0; break
            s += 0.5
        if s1 - s0 < 0.4: return None
        w = min(w, 0.6 * (s1 - s0))
        if kind == 'air':                                               # nothing to land on within reach: steeper, down to the sea if it can be reached
            y1 = max(sea - 1.0, y0 - 0.04 * w - STEEP * (s1 - s0 - w)); kind = 'sea' if y1 <= sea - 0.99 else ('scarp' if high else 'air')
        return dict(i=i, sd=sd, s0=s0, y0=y0, w=w, s1=s1, y1=y1, kind=kind, c=c, l=l)

    fill = []; runs = []; plan = []; skirts = []
    for sd in ((1, 0) if PROFILES else ()):
        base = list(range(0, n - STEP // 2, STEP)); prof = {i: profile(i, sd) for i in base}
        # stretches of consecutive profiles, grown slice by slice at both ends
        seqs = []; cur = []
        for i in base:
            if prof[i] is not None: cur.append(i)
            elif cur: seqs.append(cur); cur = []
        if cur: seqs.append(cur)
        for seq in seqs:
            for step_, end in ((-1, 0), (1, -1)):
                i = seq[end]
                for t in range(1, STEP):
                    j = (i + step_ * t) % n; p = profile(j, sd)
                    if p is None: break
                    prof[j] = p; best = j
                else: continue
                if t > 1: seq.insert(0, best) if step_ < 0 else seq.append(best)
            if len(seq) < 2: stat['skipped: a single profile'] += 1; continue
            st = [prof[i] for i in seq]
            pts_ = [np.array([p['c'][0] + p['l'][0] * p['s0'], p['c'][2] + p['l'][2] * p['s0']]) for p in st]; length = float(sum(np.linalg.norm(pts_[k + 1] - pts_[k]) for k in range(len(pts_) - 1)))
            if SPAN * length < max(p['s1'] - p['s0'] for p in st):       # a notch between rock banks, an alley between houses: an apron, not a tongue running far out
                st = [profile(i, sd, max(SPAN * length, 8.0)) for i in seq]
                if any(p is None for p in st): stat['skipped: a notch that closes'] += 1; continue
                stat['short stretches (reach held to %g x their length)' % SPAN] += 1
            ns = int(np.clip(np.ceil(max(np.hypot(p['s1'] - p['s0'] - p['w'], p['y0'] - 0.04 * p['w'] - p['y1']) for p in st) / ROW), 1, 12))
            X = np.zeros((len(st), ns + 2, 3))
            for j, p in enumerate(st):
                sv = [p['s0'], p['s0'] + p['w']]; yv = [p['y0'], p['y0'] - 0.04 * p['w']]; ln = np.hypot(p['s1'] - sv[1], yv[1] - p['y1'])
                for k in range(1, ns + 1):
                    t = k / ns; s_ = sv[1] + (p['s1'] - sv[1]) * t; y_ = yv[1] + (p['y1'] - yv[1]) * t
                    if k < ns:
                        if p['kind'] in ('sea', 'air'): y_ -= min(1.5, 0.05 * ln) * np.sin(np.pi * t)                # slightly hollow, like a scree slope
                        amp = min(0.7, 0.06 * ln); ph = 6.283 * _h('ph', sd, k)
                        s_ += amp * (0.7 * np.sin(p['i'] * 0.11 + ph) + 0.3 * np.sin(p['i'] * 0.37 + 2 * ph)); y_ += 0.4 * amp * np.sin(p['i'] * 0.19 + 3 * ph)
                    sv.append(s_); yv.append(y_)
                for k in range(ns + 2): X[j, k] = (p['c'][0] + p['l'][0] * sv[k], yv[k], p['c'][2] + p['l'][2] * sv[k])
            # no fold: every row must advance along the road from one profile to the next
            for j in range(len(st) - 1):
                d = D[st[j]['i']]; base_adv = (X[j + 1, 0] - X[j, 0]) @ d
                for k in range(1, ns + 2):
                    for _ in range(8):
                        if (X[j + 1, k] - X[j, k]) @ d >= 0.2 * base_adv: break
                        X[j + 1, k:] = X[j + 1, k - 1] + 0.7 * (X[j + 1, k:] - X[j + 1, k - 1]); X[j, k:] = X[j, k - 1] + 0.85 * (X[j, k:] - X[j, k - 1]); stat['rows pulled in (inside of a bend)'] += 1
            # tiles: nearest of the course, the same over a stretch of about 50 m
            tg = [nearest(X[j, 0, [0, 2]], ('grass', 'rock'), lying=True) for j in range(len(st))]; tr = [nearest(X[j, 0, [0, 2]], ('rock',)) for j in range(len(st))]; trm = [nearest(X[j, 0, [0, 2]], ('rock',), 3) for j in range(len(st))]
            def smooth(t):
                return [collections.Counter(x for x in t[max(0, j - 4):j + 5] if x).most_common(1)[0][0] if any(t[max(0, j - 4):j + 5]) else None for j in range(len(t))]
            tg = smooth(tg); tr = smooth(tr); name = 'hf_%s_%04d' % ('r' if sd else 'l', seq[0]); mine = []
            for j in range(len(st) - 1):
                p = st[j]; drop = p['y0'] - p['y1']; steep = drop / max(p['s1'] - p['s0'] - p['w'], 0.1)
                for k in range(ns + 1):
                    A, B, C, E = X[j, k], X[j + 1, k], X[j + 1, k + 1], X[j, k + 1]
                    rock = False                                        # shelf and skirt in the tile of the ground next to them
                    mat = (tr[j] if rock else tg[j]) or tr[j] or tg[j]
                    if rock and trm[j]: mat = trm[j][int(_h('mix', sd, p['i'], k) * len(trm[j]))]                     # two or three rock tiles of the place, face by face
                    if mat is None: continue
                    lu = (np.linalg.norm(B - A) + np.linalg.norm(C - E)) / 2; lv = (np.linalg.norm(E - A) + np.linalg.norm(C - B)) / 2
                    su = min(lu / REP, 1.2); sv_ = min(lv / REP, 1.2); ou = int(_h('u', sd, p['i'], k) * 4) / 4.0; ov = int(_h('v', sd, p['i'], k) * 4) / 4.0
                    uv = np.array([(0, 0), (su, 0), (su, sv_), (0, sv_)], float)
                    if _h('fu', sd, p['i'], k) < 0.5: uv[:, 0] = su - uv[:, 0]
                    if _h('fv', sd, p['i'], k) < 0.5: uv[:, 1] = sv_ - uv[:, 1]
                    uv += (ou, ov); Q = np.array([A, B, C, E])
                    nq, aq = OB._newell(Q); warp = np.abs((Q - Q.mean(0)) @ nq).max()
                    parts = [[0, 1, 2, 3]] if warp < 0.08 else ([[0, 1, 2], [0, 2, 3]] if np.linalg.norm(A - C) <= np.linalg.norm(B - E) else [[0, 1, 3], [1, 2, 3]])
                    for ix in parts:
                        q = Q[ix]; u = uv[ix]; nn, ar = OB._newell(q)
                        if ar < 0.05: continue
                        if nn[1] < 0: q = q[::-1]; u = u[::-1]
                        mine.append((mat, name, [tuple(map(float, x)) for x in q], [tuple(map(float, x)) for x in u]))
                        if k >= 1 and p['kind'] in ('scarp', 'air'): skirts.append(mine[-1])                 # dives into the hillside made below: not ground
            G.add(mine); fill += mine; runs.append((name, st, X, tr)); stat['stretches'] += 1; stat['profiles'] += len(st)
            for p in st: stat['ends on: ' + p['kind']] += 1
    # rocks in groups on the long slopes into the sea
    rocks = []
    for name, st, X, tr in (runs if BOULDERS else ()):
        for j in range(2, len(st) - 2):
            p = st[j]
            if p['kind'] != 'sea' or p['y0'] - p['y1'] < 7.0 or tr[j] is None: continue
            if (p['i'] // STEP) % 7 != int(_h('rk', p['sd'], p['i'] // (7 * STEP)) * 7): continue
            rows = X.shape[1]
            for g in range(2 + int(_h('n', p['i']) * 3)):
                t = 0.62 + 0.3 * _h('t', p['i'], g); a = _h('a', p['i'], g); kf = 1 + t * (rows - 2); k0 = int(np.floor(kf)); f = kf - k0
                P0 = X[j, k0] * (1 - f) + X[j, min(k0 + 1, rows - 1)] * f; P1 = X[j + 1, k0] * (1 - f) + X[j + 1, min(k0 + 1, rows - 1)] * f; ctr = P0 * (1 - a) + P1 * a
                r = 1.3 + 1.9 * _h('r', p['i'], g); h = 0.9 + 1.5 * _h('hh', p['i'], g); m = 6; ang0 = 6.283 * _h('o', p['i'], g)
                ring = [ctr + np.array([np.cos(ang0 + 6.283 * q / m) * r * (0.75 + 0.5 * _h('rr', p['i'], g, q)), -1.0 - 0.4 * r, np.sin(ang0 + 6.283 * q / m) * r * (0.75 + 0.5 * _h('rz', p['i'], g, q))]) for q in range(m)]
                apex = ctr + np.array([(_h('ax', p['i'], g) - 0.5) * 0.8 * r, h, (_h('az', p['i'], g) - 0.5) * 0.8 * r]); sec = 'hf_rocks_%s_%04d' % ('r' if p['sd'] else 'l', p['i'])
                for q in range(m):
                    T = np.array([ring[q], ring[(q + 1) % m], apex]); nn, ar = OB._newell(T)
                    if nn[1] < 0: T = T[::-1]
                    w_ = min(np.linalg.norm(T[1] - T[0]) / REP * 2.0, 1.0); hh_ = min(np.linalg.norm(apex - (ring[q] + ring[(q + 1) % m]) / 2) / REP * 2.0, 1.0); o_ = int(_h('ro', p['i'], g, q) * 4) / 4.0
                    uvq = np.array([(o_, 0.0), (o_ + w_, 0.0), (o_ + w_ / 2, hh_)]) if nn[1] >= 0 else np.array([(o_ + w_, 0.0), (o_, 0.0), (o_ + w_ / 2, hh_)])
                    rocks.append((tr[j], sec, [tuple(map(float, x)) for x in T], [tuple(map(float, x)) for x in uvq]))
                stat['rocks'] += 1
    fill += rocks
    fill += terrain(cfg, rd, faces, fill, skirts, nearest, stat, log)
    # no knife edges: a fill face (the seam fillers apart, which lie flat in the ground) thinner than 1 : 8 is left out
    def thin(fc):
        P = np.asarray(fc[2], float); nn, ar = OB._newell(P); e = max(np.linalg.norm(P[k] - P[(k + 1) % len(P)]) for k in range(len(P))); return ar / max(e * e, 1e-9) < 0.0625 and e > 3.0
    n0_ = len(fill); fill = [fc for fc in fill if str(fc[1]).startswith(('hf_weld', 'hf_roof')) or not thin(fc)]; stat['thin faces (worse than 1 : 8) left out'] = n0_ - len(fill)
    # nothing parallel on or close over another face
    import gapfill_weld as GW
    def r3f(fc):
        g = (fc[0], fc[1], [tuple(round(float(v), 3) for v in p) for p in fc[2]], [tuple(round(float(v), 4) for v in u) for u in fc[3]])
        if id(fc) in GW.ALT: GW.ALT[id(g)] = GW.ALT[id(fc)]
        return g
    fill = [r3f(fc) for fc in fill]                                    # as the OBJ will hold it: what is tested is what is built
    allf = list(faces) + fill; nb = len(faces); taken = 0
    for rnd in range(8):
        pr = OB.find_pairs(allf, cen[:, [0, 2]], active=set(range(nb, len(allf))), floor=0.06, margin=1.5)      # stricter than the build's gate
        if not pr: break
        bad = set()
        for i, j, gap, spread, need, ov in pr: bad.add(max(i, j))                                            # the fill face (of two fill faces: the later one)
        rsec = {allf[k][1] for k in bad if k >= nb and str(allf[k][1]).startswith('hf_rocks')}             # a rock goes as a whole
        for k in sorted(bad):                                         # a seam filler is not dropped: its steeper version, then a skirt under the wall, takes its place
            alt = GW.ALT.get(id(allf[k])) if k >= nb else None
            if alt: nf_ = alt[0]; GW.ALT[id(nf_)] = alt[1:]; allf[k] = nf_; bad.discard(k); stat['seam fillers replaced by their fallback (steeper / skirt)'] += 1
        keep = [k for k in range(len(allf)) if k < nb or (k not in bad and allf[k][1] not in rsec)]; taken += len(allf) - len(keep); allf = [allf[k] for k in keep]
    fill = allf[nb:]; stat['faces taken out again (parallel on / close over another face)'] = taken; stat['pairs left'] = len(OB.find_pairs(allf, cen[:, [0, 2]], active=set(range(nb, len(allf)))))
    uv = np.array([q for fc in fill for q in fc[3]]); P = np.array([q for fc in fill for q in fc[2]])
    stat['faces'] = len(fill); INFO.clear(); INFO.update(stat); INFO['tiles'] = dict(collections.Counter(fc[0][-10:] for fc in fill)); INFO['classes'] = ncls
    log('gap fill: %s' % dict(sorted(stat.items())))
    log('gap fill: tiles %s ; extent x %.0f..%.0f y %.1f..%.1f z %.0f..%.0f ; uv %.2f..%.2f' % (INFO['tiles'], P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(), P[:, 2].min(), P[:, 2].max(), uv.min(), uv.max()))
    return fill

PROFILES = False                                                       # the shelf + skirt strips beside the road made long flat triangles with straight creases and knife edges: the hillside grid alone carries the ground now
BOULDERS = False                                                       # user: big boulders 'scream this was not here before'; uneven ground suffices
BODIES = False                                                         # the automatic 'rock screens get a body' rule: OFF. Its flat back walls looked like quarry faces (user: 'No, come on'); screens are completed by hand models instead (plateau1995.py)
BODY_MIN = 12.0; BODY_DEPTH = 30.0; BODY_REP = 24.0                                     # rock screens: how far above the hillside behind them they must stand to get a body, and how deep it is
FOREST_REACH = 26.0; FOREST_UNDER = 4.0; FOREST_TOWN = 30.0; FOREST_DARK = 0.32                                # forest = this many tree boards within about 20 m; its fill tile is the local ground / rock tile at this brightness
SHOULDER = 20.0                                                        # the land stays level this far out from every piece of ground beside the road before it starts to fall: trees stand about that far out, and with a slope starting at the road edge they had to come down 3 m
CELL = 4.0                                                             # terrain grid
D0 = 0.7                                                               # the hillside stays this far under every lying polygon it passes below (parallel faces closer than 0.36 m could flicker)
SHORE_REP = 32.0; SHORE = True; SHORE_SHOULDER = 6.0; SHORE_CLIFF = np.tan(np.radians(62.0)); SHORE_NEAR = 10.0; SHORE_EASE = 1.0; SHORE_TREES = 4.0
# ^ the shore is a CLIFF (user, 2026-10-08, shots 001635 / 001646: "the terrain script added too much land ... the shore should be more
#   cliffy, instead of a gentle slope ... a lot of verticality ... we're supposed to see a lot of sea"). A second height field is built with
#   the land level only SHORE_SHOULDER m out from the roadside ground (SHORE_TREES m beyond a tree) and then falling at 62 degrees; where
#   THAT field reaches the open sea, the hillside within SHORE_NEAR m of the water takes it, easing back into the gentle hillside
#   (1 m up per metre further from the water). Inland nothing changes.
HILL = np.tan(np.radians(24.0))                                        # was 38: the land beside the road should read as uneven, mostly level ground, not as a ridge the road runs along (user, 2026-10-07)
def _poly_dist(Vx, H, Y):
    """plan distance of points Vx (m x 2) from the convex polygon H (k x 2, heights Y) and the polygon's height at the nearest point"""
    k = len(H); d = np.full(len(Vx), 1e9); y = np.zeros(len(Vx)); ins = np.ones(len(Vx), bool); ar = sum(H[i, 0] * H[(i + 1) % k, 1] - H[(i + 1) % k, 0] * H[i, 1] for i in range(k))
    for i in range(k):
        a, b = H[i], H[(i + 1) % k]; e = b - a; L2 = max(float(e @ e), 1e-12); t = np.clip(((Vx - a) @ e) / L2, 0.0, 1.0); q = a + t[:, None] * e; dd = np.hypot(Vx[:, 0] - q[:, 0], Vx[:, 1] - q[:, 1])
        m = dd < d; d[m] = dd[m]; y[m] = (Y[i] + t * (Y[(i + 1) % k] - Y[i]))[m]
        cr = e[0] * (Vx[:, 1] - a[1]) - e[1] * (Vx[:, 0] - a[0]); ins &= (cr >= 0) if ar > 0 else (cr <= 0)
    if ins.any():
        A = np.c_[H, np.ones(k)]; c = np.linalg.lstsq(A, Y, rcond=None)[0]; d[ins] = 0.0; y[ins] = (np.c_[Vx[ins], np.ones(int(ins.sum()))] @ c)
    return d, y

def terrain(cfg, rd, faces, fill, skirts, nearest, stat, log=print):
    """ONE hillside under the whole course (user: no floating skirts, no open backs from the free camera). A height grid:
        up   : from every piece of ground of the ribbon (road strip, 1995 ground near road height, the never-drawn 1995
               collision ground, the shelves made above, the foot of every board that stands on nothing, the top of rock
               walls beside the road) the ground falls away at 38 degrees; the hillside is the highest of these cones.
        down : wherever a grid cell touches a lying polygon the hillside is held D0 under it, so it never comes up through
               the road, a field, a rock face or a roof.
    Rougher with distance from the ribbon (no flat cones), cut off 1 m under the sea, cells that lie wholly under ground left
    out. Tiles: ground tile of the place where it is gentle, two or three rock tiles of the place where it is steep, one
    tile per 8 m block, mirrored block by block. Boulders in groups on the steep parts."""
    sea = (cfg.get('sea') or {}).get('level', -0.5); V = rd['V']; hw = rd['hw']; cen = np.asarray(V[:, hw], float); n = len(cen)
    import retex
    lab = {k: v[0] for k, v in retex.labels().items()}; cls = lambda m: lab.get(OB.ORIGIN.get(m, m))
    sk = {id(f) for f in skirts}; ownground = [f for f in fill if id(f) not in sk and not str(f[1]).startswith('hf_rocks')]
    verge = F.ground_skirts(list(faces) + ownground, rd, sea=sea); road = F.road_faces(rd)                # as import_classic calls it
    solid = list(faces) + road + verge + ownground; ix = F.Index(solid)
    cxz = cen[:, [0, 2]]
    def road_y(xz):
        k = int(np.argmin(((cxz - xz) ** 2).sum(1))); return float(cen[k, 1]), float(np.hypot(*(cxz[k] - xz)))
    # ---- grid
    reach = (float(cen[:, 1].max()) - sea) / HILL + 40.0 + SHOULDER; x0 = np.floor((cxz[:, 0].min() - reach) / CELL) * CELL; z0 = np.floor((cxz[:, 1].min() - reach) / CELL) * CELL
    x0 = max(x0, -736.0); z0 = max(z0, -736.0); nx = int(min((cxz[:, 0].max() + reach - x0), 736.0 - x0) // CELL) + 1; nz = int(min((cxz[:, 1].max() + reach - z0), 736.0 - z0) // CELL) + 1
    gx = x0 + np.arange(nx) * CELL; gz = z0 + np.arange(nz) * CELL; L = np.full((nx, nz), -1e9); Lc = np.full((nx, nz), -1e9); U = np.full((nx, nz), 1e9); seed = np.zeros((nx, nz), bool)
    def window(lo, hi, pad):
        a = np.clip(np.floor((np.asarray(lo) - pad - [x0, z0]) / CELL).astype(int), 0, [nx - 1, nz - 1]); b = np.clip(np.ceil((np.asarray(hi) + pad - [x0, z0]) / CELL).astype(int), 0, [nx - 1, nz - 1]); return a, b
    def raise_(H, Y, r, pad, cliff_only=False):
        a, b = window(H.min(0), H.max(0), pad); X, Z = np.meshgrid(gx[a[0]:b[0] + 1], gz[a[1]:b[1] + 1], indexing='ij'); d, y = _poly_dist(np.c_[X.ravel(), Z.ravel()], H, Y)
        vc = (y - D0 - SHORE_CLIFF * np.maximum(0.0, d - min(r, SHORE_SHOULDER))).reshape(X.shape); sub = Lc[a[0]:b[0] + 1, a[1]:b[1] + 1]; np.maximum(sub, vc, out=sub)
        if cliff_only: return
        v = (y - D0 - HILL * np.maximum(0.0, d - r)).reshape(X.shape); sub = L[a[0]:b[0] + 1, a[1]:b[1] + 1]; np.maximum(sub, v, out=sub); seed[a[0]:b[0] + 1, a[1]:b[1] + 1] |= (d.reshape(X.shape) <= r + CELL)
    # forest: where tree boards stand thick, the fill is the DARK floor that runs on under the trees (user: "the filling of the
    # forest area should have been that dark (black?) continuation that visually merges the ground with the vegetation")
    walls_ = []
    for mat, sec, P, UV in faces:
        if str(mat).endswith('_t') and cls(mat) == 'tree_wall':            # the 16 m wide wall-of-forest boards: they stand only along the forest stretch (sections 1291 .. 1317), 14 .. 35 m from the road
            c = np.asarray(P, float)[:, [0, 2]].mean(0); walls_.append((c[0], c[1], float(np.sqrt(((cxz - c) ** 2).sum(1).min()))))
    forest = np.zeros((nx, nz), bool)
    if walls_:
        # ONLY the void between the roadside ground and the foot of the forest wall (user, three times): a cell is forest floor when
        # the nearest wall board is within FOREST_REACH and the cell lies on the ROAD side of it (no further from the road than the
        # wall, plus FOREST_UNDER metres under its foot). Not the hillside behind the trees, not the rest of the stage.
        Wl = np.array(walls_); Xg, Zg = np.meshgrid(gx, gz, indexing='ij'); G2 = np.c_[Xg.ravel(), Zg.ravel()]; near_d = np.full(len(G2), 1e9); near_w = np.zeros(len(G2))
        for a_ in range(0, len(Wl), 64):
            dd = np.sqrt(((G2[:, None, :] - Wl[None, a_:a_ + 64, :2]) ** 2).sum(2)); k_ = dd.argmin(1); m_ = dd[np.arange(len(G2)), k_]; b_ = m_ < near_d; near_d[b_] = m_[b_]; near_w[b_] = Wl[a_:a_ + 64, 2][k_[b_]]
        droad = np.empty(len(G2))
        for a_ in range(0, len(G2), 4096): droad[a_:a_ + 4096] = np.sqrt(((G2[a_:a_ + 4096, None, :] - cxz[None, ::2, :]) ** 2).sum(2).min(1))
        # Where HOUSES stand nearer than the forest wall (the old town inside the forest) the ground between road and house is
        # the 1995 ground's own tile, not the dark forest floor (user's screenshot + arrow + mock-up, 2026-10-07: "you should have continued that dark grass up to
        # the house wall": the green verge beside the road ended in a black hole in front of the house).
        hs_ = []
        for mat, sec, P, UV in faces:
            c_ = cls(mat)
            if c_ and str(c_).startswith('house') and not str(mat).endswith('_t'):
                Q_ = np.asarray(P, float); n_ = np.cross(Q_[1] - Q_[0], Q_[2] - Q_[0]); l_ = np.linalg.norm(n_)
                if l_ > 1e-6 and abs(n_[1]) / l_ < 0.3: hs_.append(Q_[:, [0, 2]].mean(0))
        dh = np.full(len(G2), 1e9)
        if hs_:
            Hs = np.array(hs_); Hs = Hs[np.sqrt(((Hs[:, None, :] - Wl[None, :, :2]) ** 2).sum(2)).min(1) < 80.0]      # houses of the forest stretch only ...
            kw_ = np.array(sorted(int(np.argmin(((cxz - w_[:2]) ** 2).sum(1))) for w_ in Wl)); kh_ = np.array([int(np.argmin(((cxz - h_) ** 2).sum(1))) for h_ in Hs]) if len(Hs) else np.zeros(0, int)
            in_ = np.array([bool(((kw_ >= k_ - 150) & (kw_ < k_)).any() and ((kw_ > k_) & (kw_ <= k_ + 150)).any()) for k_ in kh_], bool) if len(Hs) else np.zeros(0, bool)
            if cfg.get('forest_village_only', False): Hs = Hs[in_]                                               # ... with forest wall before AND after them along the road: the village inside the forest, not the town at the start line where the forest ends
            for a_ in range(0, len(Hs), 64): dh = np.minimum(dh, np.sqrt(((G2[:, None, :] - Hs[None, a_:a_ + 64, :]) ** 2).sum(2)).min(1))
        town = ((dh <= FOREST_TOWN) & (dh < near_d)).reshape(nx, nz)
        forest = ((near_d <= FOREST_REACH) & (droad <= near_w + FOREST_UNDER)).reshape(nx, nz) & ~town
        stat['town cells in the forest stretch (grass)'] = int(town.sum())
    else: town = np.zeros((nx, nz), bool)
    dk = {}
    def dark(mat):
        if mat not in dk:
            import build_classic as BC, csv
            from PIL import Image
            px = BC.tile_pixels(mat); name = mat + '_dk'
            if px is None: dk[mat] = mat
            else:
                im_ = Image.fromarray((px[0].astype(float) * FOREST_DARK).clip(0, 255).astype(np.uint8))
                for d_ in (os.path.join(os.path.dirname(F.handfill_path(cfg)), 'textures'), os.path.join(os.path.dirname(BC.HI), 'textures')):   # the importer looks in the course's own textures folder (the first build wrote only the second: every forest cell came out flat grey)
                    os.makedirs(d_, exist_ok=True); im_.save(os.path.join(d_, name + '.png'))
                if name not in retex.labels():
                    rows = list(csv.reader(open(retex.CSVP)))
                    with open(retex.CSVP, 'a', newline='') as f_: csv.writer(f_).writerow([len(rows) - 1, name, cls(mat) or 'rock', '', '', 'dark forest floor made by gapfill_gen from ' + mat])
                dk[mat] = name
        return dk[mat]
    gt_ = {}
    def grass_tile(i, j):
        k_ = (i // 4, j // 4)
        if k_ not in gt_:
            g_ = nearest(np.array([gx[i], gz[j]]), ('rock',), lying=True); gt_[k_] = g_ if (isinstance(g_, str) or g_ is None) else g_[0]      # the brown cracked ground the 1995 course has beside the road there (user's mock-up, 2026-10-07): continued level up to the house wall - not grass, not the dark floor
        return gt_[k_]
    nanch = collections.Counter(); tops = []
    for fi, (mat, sec, P, UV) in enumerate(solid):
        if str(mat).endswith('_t'): continue
        P = np.asarray(P, float); nrm, ar = OB._newell(P)
        if ar < 0.05: continue
        H = P[:, [0, 2]]
        if abs(nrm[1]) >= 0.3:
            # down: every cell this polygon touches stays under it
            a = np.clip(np.floor((H.min(0) - 0.05 - [x0, z0]) / CELL).astype(int), 0, [nx - 1, nz - 1]); b = np.clip(np.floor((H.max(0) + 0.05 - [x0, z0]) / CELL).astype(int) + 1, 0, [nx - 1, nz - 1])
            Xw, Zw = np.meshgrid(gx[a[0]:b[0] + 1], gz[a[1]:b[1] + 1], indexing='ij'); pc = np.linalg.lstsq(np.c_[H, np.ones(len(H))], P[:, 1], rcond=None)[0]
            yv = np.clip(pc[0] * Xw + pc[1] * Zw + pc[2], P[:, 1].min(), P[:, 1].max()); pad_ = np.pad(yv, 1, mode='edge'); lo_ = yv.copy()      # the polygon's own height there, lowest over the neighbouring corners
            for di_ in (0, 1, 2):
                for dj_ in (0, 1, 2): np.minimum(lo_, pad_[di_:di_ + yv.shape[0], dj_:dj_ + yv.shape[1]], out=lo_)
            sub = U[a[0]:b[0] + 1, a[1]:b[1] + 1]; np.minimum(sub, lo_ - D0, out=sub)
            # up: ground of the ribbon
            own = fi >= len(faces); c = cls(mat); yr, dr = road_y(H.mean(0))
            if own or (c in ('rock', 'grass', 'dirt', 'sand', 'gravel', 'asphalt', 'cobbles') and not str(sec).startswith('obj_') and dr < 45.0 and yr - 8.0 <= P[:, 1].mean() <= yr + 5.0 and P[:, 1].max() <= yr + 7.0):
                if c == 'cobbles' and not own and P[:, 1].mean() > yr + 0.5: continue                    # the top of the roadside wall is not ground
                raise_(H, P[:, 1], SHOULDER, SHOULDER + 2 * CELL); nanch['ground polygons'] += 1
        elif cls(mat) == 'rock' and not str(sec).startswith('obj_'):
            yr, dr = road_y(H.mean(0)); top = float(P[:, 1].max())
            if dr < 30.0 and yr + 2.0 <= top <= yr + 25.0 and np.ptp(P[:, 1]) > 2.0:                       # a rock wall beside the road: the hill stands behind it up to its top
                o = np.argsort(P[:, 1])[-2:]; e = H[o]
                # only a wall that stands ON the roadside ground (a cutting) is backed by the hill. A rock that rises out of a drop beside the
                # road (the orange formation of section 1279: road on a ledge, 60 m retaining wall, the rock 12 m out in the void) has no ground
                # in front of it: backed, the hill came round its front as a dark pyramid between the road wall and the rock (user, 2026-10-07).
                mid_ = H.mean(0); kr_ = int(np.argmin(((cxz - mid_) ** 2).sum(1))); v_ = cxz[kr_] - mid_; lv_ = float(np.hypot(*v_)); q_ = mid_ + v_ / max(lv_, 1e-6) * 1.5
                if not any(yr - 4.0 <= y_ <= top + 1.0 for y_, k_ in ix.heights(float(q_[0]), float(q_[1]), True)): nanch['rock tops skipped (no ground in front)'] += 1; continue
                if np.hypot(*(e[1] - e[0])) > 0.3: tops.append((P[o[0]].copy(), P[o[1]].copy())); raise_(np.array([e[0], e[1], e[1] + 1e-3]), np.array([top, top, top]) - 0.3, 1.0, 1.0 + 2 * CELL); nanch['rock wall tops'] += 1
    # boards that stand on nothing
    for fi, (mat, sec, P, UV) in enumerate(faces):
        if str(sec).startswith('obj_'): continue
        board = str(mat).endswith('_t'); P = np.asarray(P, float); nrm, ar = OB._newell(P)
        if abs(nrm[1]) >= 0.3 or len(P) < 3 or ar < 0.05: continue
        o = np.argsort(P[:, 1]); a_, b_ = P[o[0]], P[o[1]]; base = float(min(a_[1], b_[1]))
        if abs(a_[1] - b_[1]) > 0.5 * np.hypot(a_[0] - b_[0], a_[2] - b_[2]) + 0.05: continue
        m = (a_ + b_) / 2; yr, dr = road_y(m[[0, 2]])
        if dr > 70.0 or not (yr - 12.0 <= base <= yr + 14.0): continue
        held = False
        for t in (0.25, 0.5, 0.75):
            q = a_ + (b_ - a_) * t
            if any(base - 1.0 <= y <= base + 1.5 for y, k in ix.heights(q[0], q[2], True)): held = True; break
            if any(y0 < base - 0.05 and y1 > base - 1.0 for y0, y1, k, cut in ix.uprights(q[0], q[2]) if k != fi): held = True; break
        if board and SHORE: raise_(np.array([a_[[0, 2]], b_[[0, 2]], b_[[0, 2]] + 1e-3]), np.array([base, base, base]) + D0 - 0.25, SHORE_TREES, SHORE_TREES + 2 * CELL, cliff_only=True)      # the cliff edge stays outside the trees
        if board: continue                                             # trees are LOWERED onto the ground (trees1995.lower_boards), the ground is not heaped up under each one: those cones stood as rows of pointed mounds between road and forest (user: 'eye-sore')
        if not held: r_ = 5.0 if board else 2.0; raise_(np.array([a_[[0, 2]], b_[[0, 2]], b_[[0, 2]] + 1e-3]), np.array([base, base, base]) + D0 - (0.25 if board else 0.05), r_, r_ + 2 * CELL); nanch['boards standing on nothing' if board else 'walls standing on nothing'] += 1
    # the cones spread over the grid (8 directions), and the distance from the ribbon with them
    dist = np.where(seed & (L > -1e8), 0.0, 1e9)
    for it in range(400):
        ch = False
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            st = CELL * np.hypot(dx, dz); a = (slice(max(dx, 0), nx + min(dx, 0)), slice(max(dz, 0), nz + min(dz, 0))); b = (slice(max(-dx, 0), nx + min(-dx, 0)), slice(max(-dz, 0), nz + min(-dz, 0)))
            c = L[b] - HILL * st; m = c > L[a] + 1e-6
            if m.any(): L[a] = np.where(m, c, L[a]); ch = True
            c = Lc[b] - SHORE_CLIFF * st; m = c > Lc[a] + 1e-6
            if m.any(): Lc[a] = np.where(m, c, Lc[a]); ch = True
            c = dist[b] + st; m = c < dist[a] - 1e-6
            if m.any(): dist[a] = np.where(m, c, dist[a]); ch = True
        if not ch: break
    shore = np.zeros((nx, nz), bool)
    if SHORE:
        wetc = Lc <= sea - 1.499; openc = np.zeros_like(wetc); openc[0, :] = wetc[0, :]; openc[-1, :] = wetc[-1, :]; openc[:, 0] = wetc[:, 0]; openc[:, -1] = wetc[:, -1]
        while True:
            g = openc.copy(); g[1:, :] |= openc[:-1, :]; g[:-1, :] |= openc[1:, :]; g[:, 1:] |= openc[:, :-1]; g[:, :-1] |= openc[:, 1:]; g &= wetc
            if (g == openc).all(): break
            openc = g
        ds = np.where(openc, 0.0, 1e9)
        for it in range(400):
            ch = False
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                st = CELL * np.hypot(dx, dz); a = (slice(max(dx, 0), nx + min(dx, 0)), slice(max(dz, 0), nz + min(dz, 0))); b = (slice(max(-dx, 0), nx + min(-dx, 0)), slice(max(-dz, 0), nz + min(-dz, 0)))
                c = ds[b] + st; m = c < ds[a] - 1e-6
                if m.any(): ds[a] = np.where(m, c, ds[a]); ch = True
            if not ch: break
        cut = np.maximum(Lc, sea - 1.5) + SHORE_EASE * np.maximum(0.0, ds - SHORE_NEAR); land0 = int((L > sea - 1.499).sum())
        shore = (cut < L - 0.3) & (ds < 1e8); L = np.minimum(L, cut)
        stat['shore: land cut back to a cliff (m2 of land turned to sea)'] = int((land0 - int((L > sea - 1.499).sum())) * CELL * CELL); stat['shore: cells on the cliff'] = int(shore.sum())
    # rougher away from the ribbon: two waves and a 12 m value noise, only ever downwards
    X, Z = np.meshgrid(gx, gz, indexing='ij'); ph = [6.283 * _h('tn', k) for k in range(4)]
    lat_ = lambda v: np.floor(v / 20.0).astype(int); hv = np.vectorize(lambda a, b: _h('vn', int(a), int(b)))
    ix0, iz0 = lat_(X), lat_(Z); fx = X / 20.0 - ix0; fz = Z / 20.0 - iz0; fx = fx * fx * (3 - 2 * fx); fz = fz * fz * (3 - 2 * fz)
    vn = (hv(ix0, iz0) * (1 - fx) + hv(ix0 + 1, iz0) * fx) * (1 - fz) + (hv(ix0, iz0 + 1) * (1 - fx) + hv(ix0 + 1, iz0 + 1) * fx) * fz
    n01 = 0.5 * vn + 0.25 * (1 + np.sin(X * 0.071 + Z * 0.043 + ph[0])) * 0.5 + 0.25 * (1 + np.sin(X * 0.031 - Z * 0.083 + ph[1])) * 0.5
    Hh = np.minimum(L - np.clip(0.12 * (dist - 6.0), 0.0, 2.2) * np.clip((L - sea) / 8.0, 0.25, 1.0) * n01, U); Hh = np.maximum(Hh, sea - 1.5)
    # an island: water only where it hangs together with the open sea round the course. What is under water but shut in by
    # land (the hollow inside the lap, pockets between hills) becomes a valley floor just above the sea level.
    wetv = Hh <= sea - 1.499; open_ = np.zeros_like(wetv); open_[0, :] = wetv[0, :]; open_[-1, :] = wetv[-1, :]; open_[:, 0] = wetv[:, 0]; open_[:, -1] = wetv[:, -1]
    while True:
        g = open_.copy(); g[1:, :] |= open_[:-1, :]; g[:-1, :] |= open_[1:, :]; g[:, 1:] |= open_[:, :-1]; g[:, :-1] |= open_[:, 1:]; g &= wetv
        if (g == open_).all(): break
        open_ = g
    inner = wetv & ~open_; Hh[inner] = np.minimum(sea + 0.9 + 2.2 * n01[inner], U[inner]); stat['valley floor inside the island (m2)'] = int(inner.sum() * CELL * CELL)
    free_ = (dist > 1.5 * CELL) & ~shore                                          # smooth, uneven ground: three passes of a 3 x 3 mean away from the ribbon (never up through anything it lies under)
    for it in range(3):
        Pd_ = np.pad(Hh, 1, mode='edge'); S_ = sum(Pd_[a_:a_ + nx, b_:b_ + nz] for a_ in range(3) for b_ in range(3)) / 9.0
        Hh = np.where(free_ & ~wetv, np.maximum(np.minimum(S_, U), sea - 1.5), Hh)
    lone_ = (U > 1e8) & ~wetv                                          # no pointed peaks: a corner more than 1.5 m above the mean of its eight neighbours comes down to that (ridges and broad hills stay; the cones behind short rock-wall tops stood as pyramids)
    for it in range(6):
        Pd_ = np.pad(Hh, 1, mode='edge'); nb8 = (sum(Pd_[a_:a_ + nx, b_:b_ + nz] for a_ in range(3) for b_ in range(3)) - Hh) / 8.0
        Hh = np.where(lone_ & (Hh > nb8 + 1.5), np.maximum(nb8 + 1.5, sea - 1.5), Hh)
    for it in range(200):                                              # nowhere may the hillside rise more than 65 degrees from one grid corner to the next (it only ever comes DOWN to meet that)
        ch = False
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            st = CELL * np.hypot(dx, dz); a = (slice(max(dx, 0), nx + min(dx, 0)), slice(max(dz, 0), nz + min(dz, 0))); b = (slice(max(-dx, 0), nx + min(-dx, 0)), slice(max(-dz, 0), nz + min(-dz, 0)))
            c = Hh[b] + 2.14 * st; m = c < Hh[a] - 1e-6
            if m.any(): Hh[a] = np.where(m, c, Hh[a]); ch = True
        if not ch: break
    # away from the ribbon 8 m cells do: a 2 x 2 block that touches no ground and lies more than 20 m out becomes one cell; the
    # corners in the middle of its sides take the mean of their neighbours, so the finer cells next to it still meet it
    coarse = np.zeros((nx // 2 + 1, nz // 2 + 1), bool)
    for bi in range((nx - 1) // 2):
        for bj in range((nz - 1) // 2):
            i, j = 2 * bi, 2 * bj
            if i + 2 < nx and j + 2 < nz and dist[i:i + 3, j:j + 3].min() > 20.0 and U[i:i + 3, j:j + 3].min() > 1e8 and np.ptp(Hh[i:i + 3, j:j + 3]) < 9.0: coarse[bi, bj] = True
    for bi, bj in zip(*np.nonzero(coarse)):
        i, j = 2 * bi, 2 * bj
        Hh[i + 1, j] = (Hh[i, j] + Hh[i + 2, j]) / 2; Hh[i + 1, j + 2] = (Hh[i, j + 2] + Hh[i + 2, j + 2]) / 2; Hh[i, j + 1] = (Hh[i, j] + Hh[i, j + 2]) / 2; Hh[i + 2, j + 1] = (Hh[i + 2, j] + Hh[i + 2, j + 2]) / 2
    # rock or ground tile by how steep the hillside is AROUND a cell (3 x 3 cells), so the border between the two follows the slope instead of stepping in 8 m blocks
    St = (np.maximum.reduce([Hh[:-1, :-1], Hh[1:, :-1], Hh[:-1, 1:], Hh[1:, 1:]]) - np.minimum.reduce([Hh[:-1, :-1], Hh[1:, :-1], Hh[:-1, 1:], Hh[1:, 1:]])) / CELL
    Sp = np.pad(St, 1, mode='edge'); Ssm = sum(Sp[a:a + St.shape[0], b:b + St.shape[1]] for a in range(3) for b in range(3)) / 9.0
    # cells
    out = []; tg = {}; trk = {}; wet = Hh <= sea - 1.499
    def tiles_at(bx, bz):
        if (bx, bz) not in tg:
            xz = np.array([x0 + (bx + 0.5) * 2 * CELL, z0 + (bz + 0.5) * 2 * CELL]); tg[(bx, bz)] = nearest(xz, ('grass', 'rock'), lying=True); trk[(bx, bz)] = (lambda r_: (r_,) if isinstance(r_, str) else (r_ or ()))(nearest(xz, ('rock',), 1))      # ONE rock tile, the nearest: mixing 'two or three of the place' put dark rock teeth in front of an orange formation (user, 2026-10-07)
        return tg[(bx, bz)], trk[(bx, bz)]
    vr = {}
    def vrange(mat):
        if mat not in vr:
            import build_classic as BC
            px = BC.tile_pixels(mat); vr[mat] = (0.0, 1.0)
            if px is not None:
                g = px[0].astype(float).mean(2).mean(1); h = len(g); good = g > 0.6 * np.median(g); best = (0, h); run = None; runs_ = []
                for r in range(h + 1):
                    if r < h and good[r]: run = r if run is None else run
                    elif run is not None: runs_.append((run, r)); run = None
                if runs_: best = max(runs_, key=lambda t: t[1] - t[0])
                if best[1] - best[0] >= h // 3 and best != (0, h): vr[mat] = (1.0 - (best[1] - 1.0) / h, 1.0 - (best[0] + 1.0) / h)
        return vr[mat]
    for i in range(nx - 1):
        for j in range(nz - 1):
            big = coarse[i // 2, j // 2]; st_ = 2 if big else 1
            if big and (i % 2 or j % 2): continue
            if wet[i:i + st_ + 1, j:j + st_ + 1].all(): continue
            hq = Hh[i:i + st_ + 1:st_, j:j + st_ + 1:st_]
            if hq.min() < -1e8: continue
            Q = np.array([(gx[i], hq[0, 0], gz[j]), (gx[i + st_], hq[1, 0], gz[j]), (gx[i + st_], hq[1, 1], gz[j + st_]), (gx[i], hq[0, 1], gz[j + st_])])
            pts = list(Q) + [Q.mean(0)]
            # (cells under the road and the 1995 ground are kept: they are what shows through every seam between road, verge, wall foot and rock instead of the sea)
            bx, bz = i // 2, j // 2; g_, r_ = tiles_at(bx, bz); rise = float(np.ptp(hq)); steep = rise / (CELL * st_)
            rock = Ssm[i, j] + 0.25 * (n01[i, j] - 0.5) > 0.95 or steep > 1.5 or g_ is None       # rock only where it is a rock face; a slope is uneven ground in the tile of the ground beside it
            mat = (r_[int(_h('tm', bx, bz) * len(r_))] if (rock and r_) else g_) or (r_[0] if r_ else None)
            if mat is None: continue
            if town[i, j] and steep <= 1.5: mat = grass_tile(i, j) or mat
            sh_ = bool(shore[i:i + st_ + 1, j:j + st_ + 1].any()) and rise > 6.0      # a cell of the sea cliff
            if forest[i, j] and not sh_: mat = dark(mat); stat['forest floor cells (dark tile)'] += 1
            fu = _h('tfu', bx, bz) < 0.5; fv = _h('tfv', bx, bz) < 0.5; sw = _h('tsw', bx, bz) < 0.5
            if rise > 6.0:                                              # a rock step: the tile runs up it, not stretched over it
                e1 = np.hypot(CELL, hq[1, 0] - hq[0, 0]); uv = np.array([(0.0, Q[0, 1] / 8.0), (0.5, Q[1, 1] / 8.0), (0.5, Q[2, 1] / 8.0), (0.0, Q[3, 1] / 8.0)]) if abs(hq[:, 1].mean() - hq[:, 0].mean()) >= abs(hq[1].mean() - hq[0].mean()) else np.array([(Q[0, 1] / 8.0, 0.0), (Q[1, 1] / 8.0, 0.0), (Q[2, 1] / 8.0, 0.5), (Q[3, 1] / 8.0, 0.5)])
                if sh_:                                                 # the sea cliff: ONE continuous rock picture at the scale of the 1995 cliff curtains (32 m a repeat), not half a tile restarted in every cell (it stood as terraces)
                    ax_ = 2 if abs(hq[:, 1].mean() - hq[:, 0].mean()) < abs(hq[1].mean() - hq[0].mean()) else 0; uv = np.array([(Q[k_, ax_] / SHORE_REP, Q[k_, 1] / SHORE_REP) for k_ in range(4)])
                uv = uv - np.floor(uv.min(0))
            else:
                uu = np.array([(i % 2) * 0.5, (i % 2) * 0.5 + 0.5 * st_, (i % 2) * 0.5 + 0.5 * st_, (i % 2) * 0.5]); vv = np.array([(j % 2) * 0.5, (j % 2) * 0.5, (j % 2) * 0.5 + 0.5 * st_, (j % 2) * 0.5 + 0.5 * st_])
                if fu: uu = 1.0 - uu
                if fv: vv = 1.0 - vv
                uv = np.stack([vv, uu], 1) if sw else np.stack([uu, vv], 1)
            if rise <= 6.0:                                             # only the evenly lit rows of the tile (the dark rock tile of the forest has a black band along one side: it stood as black patches on the hill)
                v0_, v1_ = vrange(mat); uv = uv.copy(); uv[:, 1] = v0_ + np.clip(uv[:, 1], 0.0, 1.0) * (v1_ - v0_)
            name = 'hf_terrain_%02d_%02d' % (i // 16, j // 16)
            nq, aq = OB._newell(Q); warp = np.abs((Q - Q.mean(0)) @ nq).max()
            parts = [[0, 1, 2, 3]]                                   # one quad per cell (the mesh draws it as two triangles)
            for ix_ in parts:
                q = Q[ix_]; u = uv[ix_]; nn, ar = OB._newell(q)
                if ar < 0.05: continue
                if nn[1] < 0: q = q[::-1]; u = u[::-1]
                out.append((mat, name, [tuple(map(float, x)) for x in q], [tuple(map(float, x)) for x in u]))
            # boulders in groups on the steep, open parts
            if BOULDERS and steep > 0.5 and dist[i, j] > 10.0 and r_ and i % 6 == int(_h('bi', i // 6, j // 6) * 6) and j % 6 == int(_h('bj', i // 6, j // 6) * 6) and _h('bp', i // 6, j // 6) < 0.3:
                for g in range(2 + int(_h('bn', i, j) * 3)):
                    ctr = Q.mean(0) + np.array([(_h('bx', i, j, g) - 0.5) * 9.0, 0.0, (_h('bz', i, j, g) - 0.5) * 9.0]); fxq = np.clip((ctr[0] - x0) / CELL, 0, nx - 1.001); fzq = np.clip((ctr[2] - z0) / CELL, 0, nz - 1.001); a0, b0 = int(fxq), int(fzq); tx, tz = fxq - a0, fzq - b0
                    ctr[1] = (Hh[a0, b0] * (1 - tx) + Hh[a0 + 1, b0] * tx) * (1 - tz) + (Hh[a0, b0 + 1] * (1 - tx) + Hh[a0 + 1, b0 + 1] * tx) * tz
                    if U[a0:a0 + 2, b0:b0 + 2].min() < 1e8: continue                                       # not beside the road or on ground
                    r = 1.4 + 2.4 * _h('br', i, j, g); h = 1.0 + 1.8 * _h('bh', i, j, g); m = 6; ang0 = 6.283 * _h('bo', i, j, g); sec = 'hf_rocks_t_%03d_%03d' % (i, j)
                    ring = [ctr + np.array([np.cos(ang0 + 6.283 * q / m) * r * (0.75 + 0.5 * _h('b1', i, j, g, q)), -1.2 - 0.5 * r, np.sin(ang0 + 6.283 * q / m) * r * (0.75 + 0.5 * _h('b2', i, j, g, q))]) for q in range(m)]
                    apex = ctr + np.array([(_h('b3', i, j, g) - 0.5) * 0.8 * r, h, (_h('b4', i, j, g) - 0.5) * 0.8 * r]); bm = r_[int(_h('b5', i, j, g) * len(r_))]
                    for q in range(m):
                        T = np.array([ring[q], ring[(q + 1) % m], apex]); nn, ar = OB._newell(T); w_ = min(np.linalg.norm(T[1] - T[0]) / 4.0, 1.0); hh_ = min(np.linalg.norm(apex - (ring[q] + ring[(q + 1) % m]) / 2) / 4.0, 1.0); o_ = int(_h('b6', i, j, g, q) * 4) / 4.0
                        uvq = np.array([(o_, 0.0), (o_ + w_, 0.0), (o_ + w_ / 2, hh_)])
                        if nn[1] < 0: T = T[::-1]; uvq = uvq[::-1]
                        out.append((bm, sec, [tuple(map(float, x)) for x in T], [tuple(map(float, x)) for x in uvq]))
                    stat['boulders on the hillside'] += 1
    # no rock floats: every free lower edge of a rock polygon with nothing under it goes down as a cliff to the hillside (or the sea)
    def h_at(x, z):
        fx_ = np.clip((x - x0) / CELL, 0, nx - 1.001); fz_ = np.clip((z - z0) / CELL, 0, nz - 1.001); a0, b0 = int(fx_), int(fz_); tx, tz = fx_ - a0, fz_ - b0
        return (Hh[a0, b0] * (1 - tx) + Hh[a0 + 1, b0] * tx) * (1 - tz) + (Hh[a0, b0 + 1] * (1 - tx) + Hh[a0 + 1, b0 + 1] * tx) * tz
    rk = lambda p: (round(p[0], 2), round(p[1], 2), round(p[2], 2)); edges = collections.Counter()
    for mat, sec, P, UV in faces:
        if str(mat).endswith('_t'): continue
        for k in range(len(P)): edges[frozenset((rk(P[k]), rk(P[(k + 1) % len(P)])))] += 1
    for fi, (mat, sec, P, UV) in enumerate(faces):
        if str(mat).endswith('_t') or cls(mat) != 'rock' or (x0 > min(p[0] for p in P) or z0 > min(p[2] for p in P)): continue
        P = np.asarray(P, float); lo_, hi_ = P[:, 1].min(), P[:, 1].max(); base_mat = OB.ORIGIN.get(mat, mat)
        for k in range(len(P)):
            A, B = P[k], P[(k + 1) % len(P)]
            if edges[frozenset((rk(A), rk(B)))] != 1 or max(A[1], B[1]) > lo_ + 0.35 * (hi_ - lo_) + 0.05: continue
            ln = float(np.hypot(B[0] - A[0], B[2] - A[2]))
            if ln < 0.5: continue
            m = (A + B) / 2
            if road_y(m[[0, 2]])[1] < 25.0: continue                    # not beside the road: a curtain hung from an overhanging rock edge there stood as a flat upright slab of rock at the roadside (user: 'what are those vertical 2d rectangular slabs')
            if any(m[1] - 1.0 <= y <= m[1] + 0.3 for y, q in ix.heights(m[0], m[2], True) if q != fi): continue
            if any(y0_ < m[1] - 0.3 and y1_ > m[1] - 1.0 for y0_, y1_, q, cut in ix.uprights(m[0], m[2], 0.3) if q != fi and not cut): continue
            ya = max(h_at(A[0], A[2]) - 1.0, sea - 1.5); yb = max(h_at(B[0], B[2]) - 1.0, sea - 1.5)
            if A[1] - ya < 0.5 and B[1] - yb < 0.5: continue
            ya = min(ya, A[1] - 0.01); yb = min(yb, B[1] - 0.01); su = min(ln / REP, 1.9); o_ = int(_h('cu', fi, k) * 4) / 4.0
            out.append((base_mat, 'hf_cliff_%03d_%03d' % (int((m[0] - x0) // 64), int((m[2] - z0) // 64)), [tuple(map(float, A)), tuple(map(float, B)), (float(B[0]), float(yb), float(B[2])), (float(A[0]), float(ya), float(A[2]))],
                        [(o_, 0.0), (o_ + su, 0.0), (o_ + su, (B[1] - yb) / REP), (o_, (A[1] - ya) / REP)])); stat['cliffs under floating rock'] += 1
    # Rock SCREENS get a body. The 1995 course has tall cliff faces away from the road that are a single curtain of polygons: no
    # top, nothing behind (the far "plateau" of sections 1280 .. 1282 is a curved wall 100 m long from y 54 to 125). From the
    # 1995 road only the front showed; from the other parts of the lap, the intro and the free cameras its open back and its
    # thinness show (user, 2026-10-07: "why not build the back side as well?"). Every free TOP edge of an upright rock polygon
    # that stands more than BODY_MIN above the hillside behind it and more than 25 m from the road gets a top running BODY_DEPTH
    # back (a little lower, uneven) and a back wall down to the hillside, in the screen's own rock tile; open ends are closed.
    top_e = []
    for fi, (mat, sec, P, UV) in enumerate(faces if BODIES else []):
        if str(mat).endswith('_t') or cls(mat) != 'rock' or (x0 > min(p[0] for p in P) or z0 > min(p[2] for p in P)): continue
        P = np.asarray(P, float); nrm, ar = OB._newell(P); lo_, hi_ = P[:, 1].min(), P[:, 1].max()
        if ar < 1.0 or abs(nrm[1]) > 0.5 or hi_ - lo_ < 4.0: continue
        for k in range(len(P)):
            A, B = P[k], P[(k + 1) % len(P)]; ln = float(np.hypot(B[0] - A[0], B[2] - A[2]))
            if ln < 1.0 or edges[frozenset((rk(A), rk(B)))] != 1 or min(A[1], B[1]) < hi_ - 0.35 * (hi_ - lo_) or abs(A[1] - B[1]) > 0.6 * ln: continue
            m = (A + B) / 2; yr, dr = road_y(m[[0, 2]])
            if dr < 25.0: continue
            e = np.array([B[0] - A[0], 0.0, B[2] - A[2]]) / ln; nb_ = np.array([-e[2], 0.0, e[0]])
            kr = int(np.argmin(((cxz - m[[0, 2]]) ** 2).sum(1))); away = np.array([m[0] - cxz[kr, 0], 0.0, m[2] - cxz[kr, 1]])
            if float(nb_ @ away) < 0: nb_ = -nb_                                      # the back is the side away from the road
            q = m + nb_ * 12.0
            if m[1] - h_at(q[0], q[2]) < BODY_MIN: continue
            top_e.append((A.copy(), B.copy(), nb_, OB.ORIGIN.get(mat, mat)))
    vn = collections.defaultdict(list)
    for A, B, nb_, mat in top_e: vn[rk(A)].append(nb_); vn[rk(B)].append(nb_)
    def back(A):
        n_ = np.sum(vn[rk(A)], axis=0); l_ = np.linalg.norm(n_); n_ = n_ / l_ if l_ > 1e-6 else vn[rk(A)][0]
        d_ = BODY_DEPTH * (0.8 + 0.4 * _h('bd', rk(A))); q = A + n_ * d_
        while d_ > 6.0 and road_y(q[[0, 2]])[1] < 22.0: d_ *= 0.7; q = A + n_ * d_           # never out over the road
        q[1] = A[1] - (1.5 + 3.0 * _h('bh', rk(A))); return q
    def low(q): return np.array([q[0], max(h_at(q[0], q[2]) - 1.0, sea - 1.5), q[2]])
    def quad_(mat, name, Q, uv):
        nn, ar = OB._newell(np.array(Q))
        if ar >= 0.2: out.append((mat, name, [tuple(map(float, x)) for x in Q], [tuple(map(float, x)) for x in uv]))
    for A, B, nb_, mat in top_e:
        A2, B2 = back(A), back(B); ln = float(np.hypot(B[0] - A[0], B[2] - A[2])); dp = float(np.linalg.norm(A2 - A)); name = 'hf_body_%03d_%03d' % (int((A[0] - x0) // 64), int((A[2] - z0) // 64)); o_ = int(_h('bu', rk(A)) * 4) / 4.0
        quad_(mat, name, [A, B, B2, A2], [(o_, 0.0), (o_ + ln / BODY_REP, 0.0), (o_ + ln / BODY_REP, dp / BODY_REP), (o_, dp / BODY_REP)]); stat['rock screens: top faces'] += 1
        A3, B3 = low(A2), low(B2)
        if max(A2[1] - A3[1], B2[1] - B3[1]) > 0.5: quad_(mat, name, [A2, B2, B3, A3], [(o_, 0.0), (o_ + ln / BODY_REP, 0.0), (o_ + ln / BODY_REP, (B2[1] - B3[1]) / BODY_REP), (o_, (A2[1] - A3[1]) / BODY_REP)]); stat['rock screens: back walls'] += 1
    for kv, lst in vn.items():                                         # an end of a screen: the side is closed too
        if len(lst) != 1: continue
        A = next(np.array(X) for X, Y, n_, m_ in ((a_, b_, n2, m2) for a_, b_, n2, m2 in top_e) if rk(X) == kv) if any(rk(a_) == kv for a_, b_, n2, m2 in top_e) else next(np.array(b_) for a_, b_, n2, m2 in top_e if rk(b_) == kv)
        mat = next(m2 for a_, b_, n2, m2 in top_e if rk(a_) == kv or rk(b_) == kv); A2 = back(A); dp = float(np.linalg.norm((A2 - A)[[0, 2]]))
        quad_(mat, 'hf_body_end', [A, A2, low(A2), low(A)], [(0.0, 0.0), (dp / BODY_REP, 0.0), (dp / BODY_REP, (A2[1] - low(A2)[1]) / BODY_REP), (0.0, (A[1] - low(A)[1]) / BODY_REP)]); stat['rock screens: ends closed'] += 1
    # ... and where the screen HAS a top (the plateau's sloping top polygons), the open rim of that top gets its back wall: every
    # free edge of a LYING rock polygon far from the road that hangs more than BODY_MIN over the hillside goes straight down to it.
    for fi, (mat, sec, P, UV) in enumerate(faces if BODIES else []):
        if str(mat).endswith('_t') or cls(mat) != 'rock' or (x0 > min(p[0] for p in P) or z0 > min(p[2] for p in P)): continue
        P = np.asarray(P, float); nrm, ar = OB._newell(P)
        if ar < 1.0 or abs(nrm[1]) <= 0.5: continue
        for k in range(len(P)):
            A, B = P[k], P[(k + 1) % len(P)]; ln = float(np.hypot(B[0] - A[0], B[2] - A[2]))
            if ln < 1.0 or edges[frozenset((rk(A), rk(B)))] != 1: continue
            m = (A + B) / 2
            if road_y(m[[0, 2]])[1] < 25.0: continue
            A3, B3 = low(A), low(B)
            if min(A[1] - A3[1], B[1] - B3[1]) < BODY_MIN: continue
            o_ = int(_h('br', rk(A)) * 4) / 4.0
            quad_(OB.ORIGIN.get(mat, mat), 'hf_body_%03d_%03d' % (int((A[0] - x0) // 64), int((A[2] - z0) // 64)), [A, B, B3, A3], [(o_, 0.0), (o_ + ln / BODY_REP, 0.0), (o_ + ln / BODY_REP, (B[1] - B3[1]) / BODY_REP), (o_, (A[1] - A3[1]) / BODY_REP)]); stat['rock screens: walls under the rim of a top'] += 1
    # the hillside welded to the rock walls it stands behind: a lid from the wall's top edge to where the hill has come up (the cells
    # that touch the road's ground are held low, which left a trench of up to 4 m behind tall walls)
    for E0, E1 in tops:
        m = (E0 + E1) / 2; k = int(np.argmin(((cxz - m[[0, 2]]) ** 2).sum(1))); e = E1 - E0; nh = np.array([-e[2], 0.0, e[0]]); l = np.linalg.norm(nh)
        if l < 1e-6: continue
        nh /= l
        if nh[0] * (m[0] - cen[k, 0]) + nh[2] * (m[2] - cen[k, 2]) < 0: nh = -nh                       # away from the road
        ends = []
        for E in (E0, E1):
            for s_ in np.arange(1.0, 10.01, 1.0):
                q = E + nh * s_; hq_ = h_at(q[0], q[2])
                if hq_ >= E[1] - 2.0: ends.append((s_, np.array([q[0], min(hq_, E[1] + 1.0) - 0.25, q[2]]))); break
        if len(ends) < 2 or max(ends[0][0], ends[1][0]) <= 1.0: continue
        mat = nearest(m[[0, 2]], ('rock',))
        if mat is None: continue
        Q = np.array([E0, E1, ends[1][1], ends[0][1]]); nn, ar = OB._newell(Q); su = min(float(np.linalg.norm(E1 - E0)) / REP, 1.9); sv_ = min(float(np.linalg.norm(Q[3] - Q[0])) / REP, 1.9); uv = np.array([(0.0, 0.0), (su, 0.0), (su, sv_), (0.0, sv_)])
        if ar < 0.05: continue
        if nn[1] < 0: Q = Q[::-1]; uv = uv[::-1]
        out.append((mat, 'hf_lid_%03d_%03d' % (int((m[0] - x0) // 64), int((m[2] - z0) // 64)), [tuple(map(float, x)) for x in Q], [tuple(map(float, x)) for x in uv])); stat['lids from rock wall tops to the hillside'] += 1
    # no building open from above: a house wall whose top has no roof within 2 m on either side (the 1995 street fronts are cards) gets a
    # roof from its top edge falling away from the road into the hillside, closed at both ends, in the roof tile of the place
    hix = F.Index(list(faces)); rtile = {}
    for fi, (mat, sec, P, UV) in enumerate(faces):
        c = cls(mat)
        if str(mat).endswith('_t') or c is None or str(sec).startswith('obj_') or not (c.startswith('house') or c in ('church', 'arcade', 'plaster_wall', 'window', 'door')): continue
        P = np.asarray(P, float); nrm, ar = OB._newell(P)
        if abs(nrm[1]) >= 0.3 or ar < 1.0: continue
        o = np.argsort(P[:, 1]); A, B = P[o[-1]], P[o[-2]]; top = float(max(A[1], B[1])); m = (A + B) / 2; yr, dr = road_y(m[[0, 2]])
        if top < yr + 4.0 or np.hypot(A[0] - B[0], A[2] - B[2]) < 1.0 or abs(A[1] - B[1]) > 0.5: continue
        if any(y0 < top + 0.3 and y1 > top + 0.5 for y0, y1, q, cut in hix.uprights(m[0], m[2], 0.3) if q != fi and not cut): continue
        nh = nrm.copy(); nh[1] = 0.0; nh /= max(np.linalg.norm(nh), 1e-9)
        if any(top - 4.0 <= y <= top + 8.0 for sg in (1.0, -1.0) for dd in (0.3, 1.0, 2.0) for y, q in hix.heights(m[0] + nh[0] * sg * dd, m[2] + nh[2] * sg * dd, True)): continue
        k = int(np.argmin(((cxz - m[[0, 2]]) ** 2).sum(1)))
        if nh[0] * (m[0] - cen[k, 0]) + nh[2] * (m[2] - cen[k, 2]) < 0: nh = -nh                       # away from the road
        if 'roof' not in rtile:
            rf = collections.Counter(f[0] for f in faces if cls(f[0]) == 'roof' and not str(f[0]).endswith('_t')); rtile['roof'] = rf.most_common(1)[0][0] if rf else None
        if rtile['roof'] is None: break
        depth = 9.0; ends = []
        for E in (A, B):
            q = E + nh * depth; ends.append(np.array([q[0], min(max(h_at(q[0], q[2]), sea) - 0.3, top - 3.0), q[2]]))
        feet_ = [np.array([E[0], max(h_at(E[0], E[2]), sea) - 0.3, E[2]]) for E in (A, B)]; rs = 'hf_roof_%03d_%03d' % (int((m[0] - x0) // 64), int((m[2] - z0) // 64)); w_ = float(np.linalg.norm(B - A)); l_ = float(np.linalg.norm(ends[0] - A))
        for Q, uvq in ((np.array([A, B, ends[1], ends[0]]), [(0.0, 0.0), (min(w_ / 4.0, 1.9), 0.0), (min(w_ / 4.0, 1.9), min(l_ / 4.0, 1.9)), (0.0, min(l_ / 4.0, 1.9))]),
                       (np.array([A, ends[0], feet_[0]]), [(0.0, 0.0), (1.0, 1.0), (0.0, 1.0)]), (np.array([B, feet_[1], ends[1]]), [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)])):
            nn, ar = OB._newell(Q)
            if ar < 0.5: continue
            out.append((rtile['roof'], rs, [tuple(map(float, x)) for x in Q], [tuple(map(float, x)) for x in uvq]))
        stat['roofs on house walls that had none'] += 1
    # seams welded shut (gapfill_weld.py)
    import gapfill_weld as GW
    out += GW.weld(list(faces), solid, rd, h_at, nearest, stat, sea)
    stat['hillside faces'] = sum(1 for f in out if f[1].startswith('hf_terrain')); stat['hillside anchors'] = dict(nanch); stat['hillside grid'] = '%d x %d cells of %g m' % (nx - 1, nz - 1, CELL)
    return out

def plan_png(path, rd, faces, fill, size=2400):
    from PIL import Image, ImageDraw
    sc = size / 1500.0; px = lambda q: (size / 2 + q[0] * sc, size / 2 - q[2] * sc); im = Image.new('RGB', (size, size), (40, 70, 150)); d = ImageDraw.Draw(im)
    lying = lambda P: abs(OB._newell(np.asarray(P, float))[0][1]) > 0.3
    for mat, sec, P, UV in F.road_faces(rd): d.polygon([px(q) for q in P], fill=(90, 90, 100))
    for mat, sec, P, UV in faces:
        if not mat.endswith('_t') and lying(P): d.polygon([px(q) for q in P], fill=(170, 170, 170))
    for mat, sec, P, UV in fill: d.polygon([px(q) for q in P], fill=(200, 150, 90) if 'rocks' in sec else (110, 190, 110), outline=(60, 110, 60))
    for mat, sec, P, UV in faces:
        if not mat.endswith('_t') and not lying(P): d.line([px(q) for q in P] + [px(P[0])], fill=(255, 255, 255))
    cen = rd['V'][:, rd['hw']]
    for i in range(0, len(cen), 100): d.text(px(cen[i]), str(i), fill=(255, 255, 0))
    im.save(path)

def main(game='src', crs='1'):
    import course, build_classic as BC, import_classic as IC, build_testtrack as BT
    cfg = course.use(game, crs); BC.VARIABLE = cfg.get('variable_width', True); rd = BC.import_road()
    BC.EXTRA_TEX = os.path.join(os.path.dirname(BC.WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'textures')
    BC.OVERLAY_MODE = 'bake'; BC.BAKED.clear(); BC.BAKE_DIR = os.path.join(BC.WORK, 'tmp', 'bake_%s_%s' % (cfg['game'], cfg['name']))
    sky, far = IC.backdrop(cfg, rd); faces = BC.load_visual(rd, extra=sky)
    fill = generate(cfg, rd, faces, BT.log); p = F.handfill_path(cfg); F.write_handfill(p, fill, rd, BC.ZS)
    plan_png(os.path.join(BC.WORK, 'previews', 'gapfill_%s_plan.png' % cfg['name']), rd, faces, fill)
    print('written: %s (%d faces)' % (p, len(fill)))

if __name__ == '__main__':
    main(*sys.argv[1:3])
