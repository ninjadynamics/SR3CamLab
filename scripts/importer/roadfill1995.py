"""ROADSIDE FILL as a generated course patch (Mountain's patch 2; owner, 2026-10-09: "patch 1 fixes bad authoring, patch 2 fixes
bad design decisions"): the level ground the 1995 course never had beside its road.
    python import_classic.py src 1 classic --norender --name <step> --set patch=[1] --set patch_gen=2 (+ the build's settings)
writes courses/<game>.<track>.patch.2.json in the format of the hand patches (coursepatch.py) and stops; a build with "patch": true
then applies it after patch 1. The file is the thing that ships: a build does not run this generator.

WHAT WAS TRIED AND THROWN AWAY (2026-10-09)
  1  a grid of 2 m cells laid 5 cm under the holes between the road's edge and the first solid upright scenery: 62 triangles on the
     whole course. That scenery stands on the road's edge nearly everywhere (median 0.24 m); what is missing lies behind it.
  2  cuts across the road every 2 m, each cut closing its own gaps and neighbouring cuts joined into quads; fill started from the TOP
     of rock: upright sheets of rock in front of the houses, shards sticking out sideways (neighbouring cuts did not agree), the forest
     gap missed (tree boards did not count), the hairpins a heap of fanned strips, 19 "bridges". Owner: "huge fuck up".
  3  the same cuts, every gap between two pieces of cover closed by a band of triangles between the corners of its two sides: the
     forest came out right, but in the village every house cut the bands apart (a roof is cover), so the ground showed only as slabs
     between the houses; and the forest floor came out in stripes (the verge's tile is painted black along its outer edge).
RULES (owner, 2026-10-09: "patch 2 always marches from the road, it's an horizontallity patch" ; "generate some proper geometry,
connected triangles, fans, make things sensibly authored" ; "it should look (both in-game AND wireframe) human hand authored")
  R1  cuts across the road every STEP m FIND the missing ground; the mesh is not made of them. In a cut the course is three things:
      GROUND (lying polygons level with the road: within LEVEL of its height), things that STAND (upright polygons: walls, rock, the
      forest wall - class tree_wall; lone trees, lamps and signs are not looked at), and the rest (roofs, rock far above or below).
  R2  the MARCH: from the edge of the ground the road lies on, outwards. Whatever stands within REACH = 20 m is passed and the march
      goes on from it; it ends at the next GROUND (and starts again behind that ground), or when nothing more is found within reach:
      then it ends at the last thing found. Nothing found at all: left open (the cliff side is patch 3). It also ends CAP m from the
      road, at another piece of the road, on the inside of a bend at the middle of the bend, and where the ground itself climbs or
      drops out of level.
  R3  what is laid is ONE BAND of ground from the edge the march started on to where it ended, UNDER everything that stands in between
      (a house stands on it; nobody models the ground round a house's foot). Its two sides are lines of the 1995 geometry's OWN CORNERS:
      the corners of the ground's edge, the corners of the foot of the wall it ends at.
  R4  the band is a ladder: rungs across it at every corner of either side and at most CELL apart, rails along it CELL apart; where
      one side is short and the other long the rungs fan out. Triangles as large as the 1995 polygons around (their median: a quad of
      about 4 m), and never more than one repeat of the tile, so the importer does not have to cut them.
  R5  level ground only: uprights are always joined at their FOOT, never at their top.
  R7  BRIDGES are not filled; their coordinates go to the log (patch 3). A bridge = at least 20 m of road with, on BOTH sides, no verge
      (the ground ends within 2.5 m of the road's edge), nothing within 3 m beyond it, and nothing at the edge but a low built wall
      (no rock, nothing higher than 3.5 m). (Trees stand beside Mountain's bridge: 'no trees beside it' as a further test lost the bridge.) The first tries called 19 and then 1 wrong stretch a bridge: 'nothing within 20 m' is true
      of much of the course, and Mountain's real bridge HAS its forest wall 19 m out and a 2 m parapet at its edge.
  R9  the CLIFF SIDE is not patch 2 (owner: "the cliffside and plateaus will be part of patch 3"): a band more than 3 m wide that would
      end at rock (a rock wall away from the road, the rock ground of another leg of a hairpin) is not laid; it goes to the log.
      Put the other way round, as the generator has it: a band wider than 3 m is laid only along the forest stretch and only where it
      ends at the forest wall, has houses standing on it (the village), or ends on the forest's own soil (the inside of a hairpin in
      the forest). Everywhere else only the cracks along the feet of walls and houses are closed.
  R8  a band that lies where a larger band lies already (the same hole found from the other leg of a hairpin) is left out whole; a
      triangle in the plane of an existing face is left out. Both are counted in the log.
  (R10 and R11 were built, shown and DROPPED the same day - "floor beneath the trees is a mess (and watch out for beneath buildings as
   well). drop those rules, we'll figure it out in patch 3 (hand authored ...) let the trees and buildings float". needs() is kept, unused.)
  R10 NO FLOATING TREES (owner, 2026-10-09): a tree needs ground under it. Not a square under each tree ("otherwise we end up with
      floating ground"): ONE shoulder from the roadside ground out to TREE_M beyond the trees, sloping so that it meets each tree's
      foot, and running on along the road from tree to tree where they stand less than TREE_LINK apart on the same side.
  R11 NO FLOATING BUILDINGS: one band per row of buildings, from the pavement's edge, UNDER them, to BUILD_M beyond their back walls
      and BUILD_M past their end walls ("larger / bigger / wider than the building's footprint").
      Both rules go before R9: outside the forest the band ends beyond the trees / the building, not at whatever stands further off.
  R12 the two sides of a band follow STEPS of what they run along (a verge that begins or ends, a nearer wall that begins): the
      corner of the step is put in, the band does not cut it. Corners are ordered by the cut planes they lie between (on the inside
      of a bend metres along the tangent put them out of order: spikes), and a band runs on over a break of up to BRIDGE cuts.
  R13 the SEA is not this module's geometry, but the patch carries the setting that leaves it whole ("settings": {"sea": {"clip":
      false}}): the importer cut the sheet out under land, and counted the game's own road as land, which is not drawn any more.
TEXTURES (approved 2026-10-09)
  T1  the tile of the ground the band starts on (else the ground it ends on, else the nearest lying 1995 ground on that side), at the
      tile's usual density, u along the road and v across the band
  T3  along the forest stretch (slices with forest-wall boards) never grass or paving: the brown cracked soil (the rock-class tile most
      of the forest's roadside ground is made of). Where houses stand on the band (the village in the forest) it is that tile as it is;
      (that exception went on 2026-10-09: a band that ends at the forest wall is dark, whatever stands on it)
      everywhere else in the forest it is the dark copy, from the trees' ground to the upright vegetation (owner, 2026-10-09: "the new
      terrain should carry that very dark shadow"; the version before darkened only bands that ended exactly on a forest-wall board).
      Between the soil verge and the forest wall it is the DARK copy of that tile (<tile>_dk, 0.32 of its brightness: the forest floor
      of the fill before this one, which the owner had accepted): the verge's own tile is painted black along its outer edge
  T5  never: tiles labelled dirt, sand or gravel, cut-out tiles, road tiles
  T6  only the evenly lit rows of a tile are used (the soil tile's top 48 rows are a painted shadow: repeated, it made stripes); the
      picture runs back and forth over those rows instead of jumping
  T7  flat lighting"""
import os, json, collections
import numpy as np

STEP = 1.0; REACH = 20.0; CAP = 60.0; MIN_GAP = 0.05; LEVEL = (2.0, 0.2); SLOPE = (0.5, 0.35); TILT = 0.05;      # (was 0.80, then 0.50: triangles left out as 'too steep' were the little risers where a band steps from a verge's end to the kerb - holes beside the road at every village entrance)
TILT_NOTE = None; CELL = (2.0, 6.0); DARK = 0.32; RISE = 1.5; GENTLE = 0.6
NO_TILE = ('dirt', 'sand', 'gravel', 'asphalt')
# PATCH 2 AS OF 2026-10-10 (owner: "let's redo patch 2 from the script ... we're gonna break patch 2 into several ones, one patch per problem.
# PATCH 2: connect the forest sides of the road to the upright vegetation with the matching dark texture ... an accordion of triangles, no
# weird shapes, just a seesaw"): ONLY the bands that end at the forest wall, all of them dark, ONE row of triangles from the verge's edge to
# the wall's foot (A0 B0 A1 B1 ...). Town cracks, the bright strip before house fronts, the sea setting: other patches, not in this file.
FOREST_ONLY = True
TREE_M = 2.0; BUILD_M = 2.0; TREE_LINK = 45.0; TREE_PAD = 5.0; BRIDGE = 8; BEHIND = 0.5
def _n(P):
    P = np.asarray(P, float); n = np.cross(P[1] - P[0], P[2] - P[0]); l = np.linalg.norm(n); return n / l if l > 1e-12 else np.array([0.0, 1.0, 0.0])
def _intri(q, T):
    """point q (x, z) strictly inside the triangle T (3 x 2)"""
    s = 0
    for k in range(3):
        a = T[k]; b = T[(k + 1) % 3]; c = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
        if abs(c) < 1e-9: return False
        s += 1 if c > 0 else -1
    return abs(s) == 3

class Course:
    """the polygons the scan works on, and the road"""
    def __init__(self, faces, rd, BC, roofs=()):
        import retex, overlay_bake as OB
        self.faces = faces; V = np.asarray(rd['V'], float); self.hw = hw = int(rd['hw']); self.cen = cen = V[:, hw]; lat = np.asarray(rd['lat'], float); n = len(cen)
        self.base = base = lambda m: str(m).split('|')[0]; lab = {k: v[0] for k, v in retex.labels().items()}; self.orig = orig = lambda m: OB.ORIGIN.get(base(m), base(m)); self.cls = cls = lambda m: lab.get(orig(m))
        sel = []; cl = []
        for k, fc in enumerate(faces):
            if len(fc[2]) < 3: continue
            c = cls(fc[0]); cut = base(fc[0]).endswith('_t') or str(orig(fc[0])).endswith('_t')
            if (cut and c != 'tree_wall') or c in ('sign', 'lamp'): continue
            sel.append(k); cl.append(c or '')
        self.sel = np.array(sel); FP = np.zeros((len(sel), 4, 3))
        for i, k in enumerate(sel):
            P = np.asarray(faces[k][2], float)[:4]; FP[i, :len(P)] = P
            if len(P) == 3: FP[i, 3] = P[2]
        self.FP = FP; nn = np.cross(FP[:, 1] - FP[:, 0], FP[:, 2] - FP[:, 0]); n2 = np.cross(FP[:, 2] - FP[:, 0], FP[:, 3] - FP[:, 0]); bad = np.linalg.norm(nn, axis=1) < 1e-9; nn[bad] = n2[bad]
        nn /= np.maximum(np.linalg.norm(nn, axis=1), 1e-12)[:, None]; cl = np.array(cl); self.cl = cl
        self.tw = cl == 'tree_wall'; self.up = (np.abs(nn[:, 1]) < 0.5) | self.tw
        self.roof = ~self.up & ((cl == 'roof') | np.char.startswith(cl, 'house') | (cl == 'church') | (cl == 'arcade') | np.array([any(str(orig(faces[k][0])).startswith(r) for r in roofs) for k in sel], bool))
        self.road = np.array([base(faces[k][0]) in BC.ROAD_TILES or orig(faces[k][0]) in BC.ROAD_TILES for k in sel])
        self.vmap = collections.defaultdict(list)                       # corner -> the lying polygons that have it
        for k in np.flatnonzero(~self.up & ~self.roof):
            for i in range(4): self.vmap[(round(float(FP[k][i][0]), 2), round(float(FP[k][i][1]), 2), round(float(FP[k][i][2]), 2))].append((int(k), i))
        seg = np.linalg.norm(np.roll(cen, -1, 0)[:, [0, 2]] - cen[:, [0, 2]], axis=1); sl = [0]; acc = 0.0      # slices STEP apart
        for i in range(1, n):
            acc += seg[i - 1]
            if acc >= STEP - 1e-6: sl.append(i); acc = 0.0
        self.sl = sl = np.array(sl); self.m = m = len(sl); self.C = C = cen[sl].copy(); L = lat[sl].copy(); L[:, 1] = 0.0; L /= np.linalg.norm(L, axis=1)[:, None]; self.L = L
        F = np.roll(C, -1, 0) - np.roll(C, 1, 0); F[:, 1] = 0.0; F -= (F * L).sum(1)[:, None] * L; F /= np.linalg.norm(F, axis=1)[:, None]; self.T = F      # forwards, square to the cut
        d = np.linalg.norm((np.roll(C, -1, 0) - C)[:, [0, 2]], axis=1); self.sig = np.concatenate([[0.0], np.cumsum(d)[:-1]]); self.lap = float(d.sum())    # metres along the road
        w = max(2, int(round(16.0 / STEP))); self.inner = np.zeros(m, int); self.R = np.full(m, 1e9)
        for a in range(m):
            p0, p1, p2 = C[(a - w) % m, [0, 2]], C[a, [0, 2]], C[(a + w) % m, [0, 2]]; t1 = p1 - p0; t2 = p2 - p1; l1 = np.linalg.norm(t1); l2 = np.linalg.norm(t2)
            if l1 < 1e-6 or l2 < 1e-6: continue
            ang = np.arctan2(t1[0] * t2[1] - t1[1] * t2[0], t1 @ t2)
            if abs(ang) > 1e-4: self.R[a] = 0.5 * (l1 + l2) / abs(ang); self.inner[a] = 1 if float((t2 / l2 - t1 / l1) @ L[a, [0, 2]]) > 0 else -1

def needs(co, faces, log=print):
    """R10 / R11 -> (E, H, K) per slice and side: how far from the centre line ground MUST reach because something stands there, the
    height of its foot, and what it is (1 = trees, 2 = buildings; 0 = nothing)"""
    m = co.m; C, L, sig = co.C, co.L, co.sig; E = np.full((m, 2), np.nan); H = np.full((m, 2), np.nan); K = np.zeros((m, 2), int)
    def place(p, ylo, yhi):                                            # -> (slice, side, metres from the centre line): the nearest slice at about that height
        d2 = (C[:, 0] - p[0]) ** 2 + (C[:, 2] - p[2]) ** 2 + np.where((C[:, 1] < ylo - 12.0) | (C[:, 1] > yhi + 12.0), 1e9, 0.0); a = int(np.argmin(d2))
        if d2[a] > 45.0 ** 2: return None
        dl = float((np.asarray(p, float) - C[a]) @ L[a]); return a, (0 if dl < 0 else 1), abs(dl)
    def put(a, sd, e, h, k):
        if not np.isfinite(E[a, sd]) or e > E[a, sd]: E[a, sd] = e; H[a, sd] = h; K[a, sd] = k
    trees = []                                                         # boards of lone trees gathered round their stems: [x, z, foot]
    for fc in faces:
        mat, P = fc[0], fc[2]
        if not co.base(mat).endswith('_t') or co.cls(mat) not in ('crown', 'trunk', 'bare', 'tree'): continue
        Q = np.asarray(P, float); c = Q[:, [0, 2]].mean(0); f = float(Q[:, 1].min())
        for t in trees:
            if (t[0] - c[0]) ** 2 + (t[1] - c[1]) ** 2 < 2.5 ** 2: t[2] = min(t[2], f); break
        else: trees.append([float(c[0]), float(c[1]), f])
    side = ([], []); pad = int(round(TREE_PAD / STEP))
    for x, z, f in trees:
        pl = place((x, f, z), f, f + 6.0)
        if pl: side[pl[1]].append((pl[0], pl[2], f))
    for sd in (0, 1):
        row = sorted(side[sd])
        for a, d, f in row:
            for b in range(a - pad - 3, a + pad + 4): put(b % m, sd, d + TREE_M - 4.0 * max(abs(b - a) - 2, 0) / (pad + 1), f, 1)      # full width at the tree, narrowing towards the two ends
        for (a1, d1, f1), (a2, d2, f2) in zip(row, row[1:]):          # trees that follow each other along the road: one shoulder
            if a2 > a1 and sig[a2] - sig[a1] <= TREE_LINK and abs(d2 - d1) <= 10.0:
                for b in range(a1, a2 + 1): t = (b - a1) / (a2 - a1); put(b, sd, d1 + (d2 - d1) * t + TREE_M, f1 + (f2 - f1) * t, 1)
    def smooth(sd, kind, w):                                           # the outer edge does not step from slice to slice
        ok = K[:, sd] == kind; v = E[:, sd].copy(); out_ = v.copy()
        for a in np.flatnonzero(ok):
            j = [(a + q) % m for q in range(-w, w + 1)]; j = [x for x in j if ok[x]]; out_[a] = float(np.mean(v[j]))
        E[:, sd] = out_
    for sd in (0, 1): smooth(sd, 1, 3)
    EB = np.full((m, 2), np.nan); nb = 0
    for k in np.flatnonzero(co.up & ~co.tw & (np.char.startswith(co.cl, 'house') | (co.cl == 'church') | (co.cl == 'arcade'))):
        P = co.FP[k]; o = np.argsort(P[:, 1]); f0 = P[o[0]]; f1 = next((P[i] for i in o[1:] if np.hypot(P[i][0] - f0[0], P[i][2] - f0[2]) > 0.2), None)
        if f1 is None: continue
        ylo, yhi = float(P[:, 1].min()), float(P[:, 1].max()); p0 = place(f0, ylo, yhi); p1 = place(f1, ylo, yhi)
        if p0 is None or p1 is None or p0[1] != p1[1] or abs(p1[0] - p0[0]) > 60: continue
        (a0, sd, d0), (a1, _, d1) = sorted([p0, p1]); nb += 1
        for b in range(a0, a1 + 1): e = d0 + (d1 - d0) * (b - a0) / max(a1 - a0, 1) + BUILD_M; EB[b, sd] = e if not np.isfinite(EB[b, sd]) else max(EB[b, sd], e)
    padb = int(round(BUILD_M / STEP)); wide = int(round(6.0 / STEP))
    for sd in (0, 1):
        for a in range(m):
            w = EB[[(a + j) % m for j in range(-padb, padb + 1)], sd]
            if np.isfinite(w).any(): put(a, sd, float(np.nanmax(EB[[(a + j) % m for j in range(-wide, wide + 1)], sd])), np.nan, 2)      # one strip under a row of houses: as deep as the deepest within 6 m
        smooth(sd, 2, 4)
    log('       roadside fill: %d lone trees, %d building walls ; slice sides where ground is owed: %d to trees, %d to buildings' % (len(trees), nb, int((K == 1).sum()), int((K == 2).sum())))
    return E, H, K

def scan(co, extra=None, want_edges=True, probe=(), log=print, trace=None, need=None, infor=None):
    """R1 / R2. -> (bands to lay per slice side {(slice, side): [...]}, bridge sides (m, 2), counts). extra: more ground (n, 4, 3), e.g. the fill"""
    FP = co.FP; up = co.up; roof = co.roof; road = co.road; tw = co.tw; n0 = len(co.FP)
    if extra is not None and len(extra):
        FP = np.concatenate([FP, extra]); z = np.zeros(len(extra), bool); up = np.concatenate([up, z]); roof = np.concatenate([roof, z]); road = np.concatenate([road, z]); tw = np.concatenate([tw, z])
    C, L, T, m, hw = co.C, co.L, co.T, co.m, co.hw; far = CAP + hw + REACH + 5.0
    fc = FP.mean(1); fr = np.linalg.norm(FP - fc[:, None, :], axis=2).max(1); gaps = {}; bridge = np.zeros((m, 2), bool); stat = collections.Counter(); ar = np.arange(m)
    for a in range(m):
        near = np.flatnonzero((fc[:, 0] - C[a, 0]) ** 2 + (fc[:, 2] - C[a, 2]) ** 2 < (far + fr) ** 2); Q = FP[near] - C[a]
        s = Q @ T[a]; s = np.where(s == 0, 1e-9, s); sj = np.roll(s, -1, 1); ch = (s * sj) < 0; ok = ch.sum(1) == 2
        if not ok.any(): continue
        near = near[ok]; Q = Q[ok]; s = s[ok]; sj = sj[ok]; ch = ch[ok]; e = np.argsort(~ch, axis=1, kind='stable')[:, :2]; r = np.arange(len(near))[:, None]
        Pi = Q[r, e]; Pj = Q[r, (e + 1) % 4]; t = s[r, e] / (s[r, e] - sj[r, e]); X = Pi + t[..., None] * (Pj - Pi); d = X @ L[a]; y = X[..., 1] + C[a, 1]; cy = float(C[a, 1])
        for sd, sg in enumerate((-1.0, 1.0)):
            D = d * sg; keep = (D.max(1) > -0.5) & (D.min(1) < far)
            if not keep.any(): continue
            D = D[keep]; Y = y[keep]; E = e[keep]; F = near[keep]; o = np.argsort(D, axis=1); D = np.take_along_axis(D, o, 1); Y = np.take_along_axis(Y, o, 1); E = np.take_along_axis(E, o, 1)
            u = up[F]; g = ~u & ~roof[F]; fcol = np.argmin(Y, axis=1); rr = np.arange(len(F)); fd = D[rr, fcol]; fy = Y[rr, fcol]; fe = E[rr, fcol]; ty = Y.max(1)
            er = 0.0; kr = None                                        # the edge of the road: road polygons followed out from the centre line
            for k in np.argsort(D[:, 0]):
                if not (road[F[k]] and g[k]): continue
                if D[k, 0] <= er + 0.1:
                    if D[k, 1] > er: kr = k
                    er = max(er, D[k, 1])
                elif er > 0: break
            order = [k for k in np.argsort(D[:, 0]) if g[k]]
            def run(end, yend):
                """the ground followed outwards over its terraces: lying polygons that join on at about the same height. A bank or a step of
                more than RISE ends it. -> (where it ends, its height there, the polygon it ends with, True when it climbs or drops away)"""
                last = None
                for k in order:
                    if D[k, 0] > end + MIN_GAP: break
                    if D[k, 1] <= end: continue
                    y_at = Y[k, 0] + (Y[k, 1] - Y[k, 0]) * min(max((end - D[k, 0]) / max(D[k, 1] - D[k, 0], 1e-6), 0.0), 1.0)
                    if abs(y_at - yend) > RISE: continue                # another level (rock overhead, ground far below): not part of this ground
                    dy = Y[k, 1] - y_at
                    if abs(dy) > RISE and abs(dy) > GENTLE * (D[k, 1] - max(end, D[k, 0])): return end, yend, last, True
                    end = float(D[k, 1]); yend = float(Y[k, 1]); last = k
                return end, yend, last, False
            def edge_of(k, col, yref):                                 # the polygon edge the cut leaves the polygon through: its two corners, the one behind the cut first
                if k >= n0 or not want_edges: return None
                v0 = FP[k][col]; v1 = FP[k][(col + 1) % 4]; h = float(np.hypot(v1[0] - v0[0], v1[2] - v0[2]))
                if h < 0.05 or h > 40.0 or abs(v1[1] - v0[1]) > 0.3 * h + 0.1 or max(abs(v0[1] - yref), abs(v1[1] - yref)) > 0.3 * h + 0.5: return None      # the slanting side of an upright triangle is not a foot; a corner far above or below is not this ground
                return (v0, v1) if float((v0 - C[a]) @ T[a]) < float((v1 - C[a]) @ T[a]) else (v1, v0)
            p, yp, last, away = run(-0.5, cy)
            if last is None or p < 0.0: stat['slice sides with no ground under the centre line'] += 1; continue
            lim = min(CAP + er, 0.9 * co.R[a]) if co.inner[a] == int(sg) else CAP + er; out = []; first = True; why = ''
            nE = float(need[0][a, sd]) if need is not None else np.nan; nH = float(need[1][a, sd]) if need is not None else np.nan; nK = int(need[2][a, sd]) if need is not None else 0
            inf_ = bool(infor[a]) if infor is not None else True
            while True:
                rr_ = lambda dd: 0.5 + LEVEL[1] * np.maximum(dd - p, 0.0)   # what counts as level with where the march stands
                things = sorted([(float(D[k, 0]), 0, int(k)) for k in np.flatnonzero(g & (D[:, 0] > p + MIN_GAP) & (np.abs(Y[:, 0] - yp) <= SLOPE[0] + SLOPE[1] * (D[:, 0] - p)))] + [(float(max(fd[k], p)), 1, int(k)) for k in np.flatnonzero(u & (fd >= p - 0.3) & (fy <= yp + rr_(fd)) & (ty >= yp - rr_(fd)))]
                                + ([(nE, 2, -1)] if (np.isfinite(nE) and nE > p + 0.3) else []))      # 2 = ground is owed up to here (R10, R11)
                if first:                                              # R7: no verge, open beyond the edge, nothing at it but a low built wall
                    at_edge = u & (fd >= er - 1.0) & (fd <= p + 0.5); tall = bool((at_edge & ((ty > cy + 3.5) | (co.cl[np.minimum(F, n0 - 1)] == 'rock'))).any()); nxt = min([x[0] for x in things if x[0] > p + 0.5 and x[1] != 2] or [1e9])      # (a parapet stands at a bridge's edge, 2 m high on Mountain; rock or a house front is not a bridge)
                    bridge[a, sd] = (p - er < 2.5) and (nxt - p > 3.0) and not tall; first = False
                    if a in probe: log('       probe slice %d side %d: road edge %.2f, ground ends %.2f at %.2f, next thing %.2f, tall at the edge %s, bridge side %s ; things %s' % (co.sl[a], sd, er, p, yp - cy, nxt, tall, bridge[a, sd], [(round(x[0], 1), ('ground', 'stands', 'owed')[x[1]]) for x in things[:6]]))
                if away or abs(yp - cy) > LEVEL[0] + 0.35 * max(p - er, 0.0): why = 'the ground climbs or drops away at %.1f (%.1f from the height of the road)' % (p, yp - cy); stat['marches that end where the ground climbs or drops away'] += 1; break
                cur = p; tgt = None; ups = []
                for pos, kind, k in things:
                    if pos - cur > REACH or pos > lim: break
                    if kind == 0: tgt = k; break
                    ups.append((pos, kind, k)); cur = pos
                if inf_ and any(x[1] == 1 and tw[F[x[2]]] for x in ups):   # in the forest the band ends at the forest wall, whatever stands or is owed beyond it
                    ups = ups[:max(i_ for i_, x in enumerate(ups) if x[1] == 1 and tw[F[x[2]]]) + 1]; tgt = None
                if nK == 1 and any(x[1] == 2 for x in ups):             # trees behind something tall (a tunnel's wall, a rock face) are not the road's trees: no shoulder hung outside that wall
                    in_ = next(i_ for i_, x in enumerate(ups) if x[1] == 2)
                    if any(x[1] == 1 and ty[x[2]] > yp + 2.5 for x in ups[:in_]): ups = [x for x in ups if x[1] != 2]
                hn = any(x[1] == 2 for x in ups)
                if hn and not inf_:                                    # outside the forest the band ends beyond the trees / the building, not at whatever stands further off
                    il = max(i_ for i_, x in enumerate(ups) if x[1] == 2); ups = ups[:il + 1] + [x for x in ups[il + 1:] if x[0] - ups[il][0] <= 2.5]
                    if tgt is not None and float(D[tgt, 0]) - ups[-1][0] > 4.0: tgt = None
                if tgt is None and not ups: why = 'nothing within reach of %.1f (things: %s)' % (p, [(round(x[0], 1), x[1]) for x in things[:4]]); stat['marches that end with nothing within %.0f m (left open)' % REACH] += 1; break
                A = (p, yp, int(F[last]), int(E[last, 1])); free = False
                if tgt is not None: B = (float(D[tgt, 0]), float(Y[tgt, 0]), int(F[tgt]), int(E[tgt, 0])); eB = edge_of(B[2], B[3], B[1])
                elif ups[-1][1] == 2:                                  # a free end: TREE_M beyond the trees (sloping through the tree's foot), BUILD_M beyond the building (level)
                    free = True; yB = yp
                    if nK == 1 and np.isfinite(nH): yB = float(np.clip(yp + (nH - yp) * (nE - p) / max(nE - TREE_M - p, 1.5), yp - 1.2 * (nE - p), yp + 1.2 * (nE - p)))
                    B = (nE, yB, int(F[last]), int(E[last, 1])); eB = None
                else:
                    k = min((x[2] for x in ups if x[1] == 1 and x[0] >= ups[-1][0] - 0.3), key=lambda k: fy[k]); lvl = abs(fy[k] - yp) <= rr_(fd[k])      # R5: the lowest foot there; a wall that goes on down below is met at the band's own height
                    B = (float(max(fd[k], p)), float(fy[k]) if lvl else yp, int(F[k]), int(fe[k])); eB = edge_of(B[2], B[3], B[1]) if lvl else None
                    if eB is None: B = (B[0] + BEHIND, B[1], B[2], B[3])   # no foot edge to follow: the band ends BEHIND what stands there (chords along a curved wall left slivers in front of it)
                wdt = B[0] - A[0]; sl_ = (0.5, 1.2) if (free and nK == 1) else SLOPE; steep = abs(B[1] - A[1]) > sl_[0] + sl_[1] * max(wdt, 0.0)
                mid_ = np.clip(0.5 * (np.maximum(D[:, 0], A[0]) + np.minimum(D[:, 1], B[0])), A[0], B[0]); line_ = A[1] + (B[1] - A[1]) * (mid_ - A[0]) / max(wdt, 1e-6); top_ = np.maximum(Y[:, 0], Y[:, 1])
                if (g & (D[:, 1] > A[0] + 0.3) & (D[:, 0] < B[0] - 0.3) & (top_ < line_ - 0.5) & (top_ > line_ - 12.0)).any():      # ground under the band (the lower leg of a hairpin): the band would lie over it
                    why = 'ground lies under the band between %.1f and %.1f' % (A[0], B[0]); stat['marches that end over lower ground (a slope: patch 3)'] += 1; break
                if wdt >= MIN_GAP and not steep:
                    pA = C[a] + L[a] * (sg * A[0]); pA[1] = A[1]; pB = C[a] + L[a] * (sg * B[0]); pB[1] = B[1]; real = [x[2] for x in ups if x[1] == 1 and F[x[2]] < n0]
                    hf_ = [x[0] for x in ups if x[1] == 1 and F[x[2]] < n0 and (str(co.cl[F[x[2]]]).startswith('house') or co.cl[F[x[2]]] in ('church', 'arcade'))]
                    if FOREST_ONLY and hf_ and kr is not None:      # v6 (owner, 2026-10-11): in the village the fill is made as in the forest, but from the upright vegetation to THE BASE OF THE ROAD ITSELF: it starts on the road's own edge, at the road's height, under the kerb
                        A = (float(D[kr, 1]), float(Y[kr, 1]), int(F[kr]), int(E[kr, 1])); pA = C[a] + L[a] * (sg * A[0]); pA[1] = A[1]
                        if eB is None: pB = pB.copy(); pB[1] = A[1]
                    kw_ = [k_ for k_ in np.flatnonzero(u & (np.abs(fd - A[0]) < 0.8) & (ty >= yp - 0.4) & (fy < yp - 0.15) & (fy > yp - 6.0))]      # the wall that hangs from the kerb's edge on the houses' side
                    kerb_ = float(fy[min(kw_, key=lambda k_: abs(ty[k_] - yp))]) if kw_ else np.nan
                    out.append(dict(a=a, sd=sd, dA=A[0], dB=B[0], pA=pA, pB=pB, fA=A[2], fB=B[2], eA=edge_of(A[2], A[3], A[1]), eB=eB, wall=tgt is None, need=hn, free=free, front=(min(hf_) - A[0]) if hf_ else np.nan, yh=np.nan,
                                    forest=bool(tw[B[2]]) if (tgt is None and not free) else False, clsB=str(co.cl[B[2]]) if (B[2] < n0 and not free) else '', tileB=str(co.orig(co.faces[co.sel[B[2]]][0])) if (B[2] < n0 and not free) else '',
                                    built=(hn and nK == 2) or any(str(co.cl[F[k_]]).startswith('house') or co.cl[F[k_]] in ('church', 'arcade') for k_ in real))); stat['gap metres'] += wdt
                elif steep: why = 'a step: from %.2f at %.1f to %.2f at %.1f' % (A[1] - cy, A[0], B[1] - cy, B[0]); stat['marches that end at a step in the ground'] += 1; break
                if tgt is None: why = 'ended at what stands at %.1f (%s ; owed to %s up to %.1f ; passed %s)' % (B[0], 'free end' if free else co.cl[B[2]] if B[2] < n0 else 'fill', ('nothing', 'trees', 'buildings')[nK], nE, [str(co.cl[F[x[2]]]) if (x[1] == 1 and F[x[2]] < n0) else 'owed' for x in ups][:6]); break
                p, yp, last, away = run(float(D[tgt, 0]) - MIN_GAP, float(Y[tgt, 0]))
                if last is None: break
                ia = np.abs(ar - a); ia = np.minimum(ia, m - ia)       # another part of the road: joined, and the march ends
                if ((ia > 80.0 / STEP) & ((C[:, 0] - (C[a, 0] + L[a, 0] * sg * B[0])) ** 2 + (C[:, 2] - (C[a, 2] + L[a, 2] * sg * B[0])) ** 2 < 14.0 ** 2) & (np.abs(C[:, 1] - B[1]) < 3.0)).any(): why = 'another piece of road'; stat['marches that end at another piece of road'] += 1; break
            if trace and trace[0] <= co.sl[a] <= trace[1]: log('       trace slice %d side %d: road edge %.1f ; bands %s ; %s' % (co.sl[a], sd, er, [(round(o_['dA'], 1), round(o_['dB'], 1)) for o_ in out], why))
            if out: gaps[(a, sd)] = out
    return gaps, bridge, stat

SLABS = []; CLIFFS = []
FILL_BRIDGES = False; KEEP_SLABS = False                               # OPT-IN (genpatch1995.py, rule F's variants): lay the band along a 'bridge' too (R7 off) ; keep bands that are wider than they are long (the floor between two houses of a forest village)
def tracks_of(co, gaps, bridge_on, stat, cliff=lambda g: False):
    """R3 / R12: bands of neighbouring slices that overlap are one band; -> per band its two sides as lines of corners [(point, metres along the road)]"""
    m = co.m; C, T, L, sig = co.C, co.T, co.L, co.sig
    for key in list(gaps):
        if bridge_on[key[0]]: del gaps[key]
    nxt = {}; has_prev = set()
    for step in range(1, BRIDGE + 1):                                  # the next cut first; then over breaks (the tip of a bend, a cut that found nothing)
        for (a, sd), ga in gaps.items():
            b = (a + step) % m; gb = gaps.get((b, sd), [])
            if not gb or (step > 1 and bridge_on[[(a + q) % m for q in range(1, step)]].any()): continue
            for i, g in enumerate(ga):
                if (a, sd, i) in nxt: continue
                best = None
                for j, h in enumerate(gb):
                    if (b, sd, j) in has_prev: continue
                    ov = min(g['dB'], h['dB']) - max(g['dA'], h['dA'])
                    if ov > 0.3 * min(g['dB'] - g['dA'], h['dB'] - h['dA']) and abs(g['pA'][1] - h['pA'][1]) < 2.5 and cliff(g) == cliff(h) and (best is None or ov > best[0]): best = (ov, j)
                if best:
                    nxt[(a, sd, i)] = (b, sd, best[1]); has_prev.add((b, sd, best[1]))
                    if step > 1: stat['breaks in a band run over (up to %d cuts)' % BRIDGE] += 1
    out = []; seen = set(); every = [(a, sd, i) for (a, sd), ga in gaps.items() for i in range(len(ga))]
    key = lambda p: (round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2))
    for st in [x for x in every if x not in has_prev] + every:
        if st in seen: continue
        tr = []; cur = st; turn = 0.0; base = []
        while cur is not None and cur not in seen:
            seen.add(cur); g = gaps[(cur[0], cur[1])][cur[2]]
            if tr and g['a'] < tr[-1]['a']: turn += co.lap             # the band runs over the start line
            tr.append(g); base.append(sig[g['a']] + turn); cur = nxt.get(cur)
        sg_ = -1.0 if tr[0]['sd'] == 0 else 1.0
        def line(side):
            """A polygon edge counts from the first to the last cut that crossed it. Its corner is used when it lies between that cut and the
            next cut's plane (then the edge ends there), else the point where the cut crossed (the edge runs on beside something else).
            Where one stretch ends and the next begins at another distance from the road, the corner of that step is put in."""
            pts = []                                                   # (point, metres along the road, slice)
            lat = lambda q, a: sg_ * float((q - C[a]) @ L[a])
            def walk(c, a, d_to):
                """from a corner of the ground's edge along the END of that ground (the 1995 polygons' own edges) towards the distance d_to from
                the centre line: -> the corners passed. (A verge that ends is not cut square: a straight step beside its end left a sliver open.)"""
                got = []
                for _ in range(8):
                    dc = lat(c, a); best = None
                    if abs(dc - d_to) <= 0.5: break
                    for k, i_ in co.vmap.get(key(c), ()):
                        for n_ in (co.FP[k][(i_ + 1) % 4], co.FP[k][(i_ - 1) % 4]):
                            dn = lat(n_, a); gain = abs(dc - d_to) - abs(dn - d_to); al = abs(float((n_ - c) @ T[a]))
                            if gain > 0.2 and abs(dn - d_to) < abs(dc - d_to) and al < 0.8 * gain + 0.3 and abs(n_[1] - c[1]) < 1.0 and (best is None or al / gain < best[0]): best = (al / gain, n_)
                    if best is None: break
                    c = best[1].copy(); got.append(c)
                return got
            skip = [False]
            def add(q, x, a, first, corner=False):
                q = np.asarray(q, float).copy()
                if skip[0] and not corner and not first: return        # still on the way to the next true corner
                if corner or first: skip[0] = False
                if pts and np.linalg.norm(pts[-1][0] - q) < 0.05: return
                if pts and first:
                    both = bool(corner and pts[-1][3])                    # two true corners: no step is made up between them - but the END of the ground between them is still followed (it is not always one straight edge)
                    o, xo, ao, oc = pts[-1]; do = lat(o, ao); dq = lat(q, a)
                    if abs(dq - do) > 0.75 and x - xo < 3.0 * STEP:
                        w = walk(o, ao, dq) if (side == 'A' and oc) else []       # the old stretch ended at a corner: along the end of that ground
                        if w:
                            for n_, c_ in enumerate(w): pts.append((c_, xo + 1e-3 * (n_ + 1), ao, True))
                            if not corner: skip[0] = True; return      # (owner, 2026-10-09: "as long as it needs to connect to something": from the end of the verge the side runs to the next true corner, at that corner's height - no riser one cut further on)
                        else:
                            w = walk(q, a, do)[::-1] if (side == 'A' and corner) else []      # the new stretch begins at a corner: along the beginning of that ground
                            if w:
                                if len(pts) >= 2 and not pts[-1][3]: pts.pop()      # (the same the other way round: the cut's point just before a ground begins goes, the side comes from the last true corner)
                                for n_, c_ in enumerate(w): pts.append((c_, max(x - 1e-3 * (len(w) - n_), pts[-1][1] + 1e-4), a, True))
                            elif both: pass
                            elif (dq > do) if side == 'A' else (dq < do): X = q + L[a] * (sg_ * (do - dq)); X[1] = o[1]; pts.append((X, max(x - 1e-3, xo + 1e-3), a, False))      # the band gets narrower: the step is where the new stretch begins
                            else: X = o + L[ao] * (sg_ * (dq - do)); X[1] = q[1]; pts.append((X, xo + 1e-3, ao, False))                                                              # wider: where the old one ended
                pts.append((q, max(float(x), pts[-1][1] + 1e-3) if pts else float(x), a, corner))
            i = 0
            while i < len(tr):
                e = tr[i]['e' + side]; j = i
                if e is None:
                    while j + 1 < len(tr) and tr[j + 1]['e' + side] is None and abs(tr[j + 1]['d' + side] - tr[j]['d' + side]) < 0.75: j += 1
                    for n_, k in enumerate(list(range(i, j, 3)) + [j]): add(tr[k]['p' + side], base[k], tr[k]['a'], n_ == 0)      # no edge to follow: the cut's own points, 3 m apart
                else:
                    ke = (key(e[0]), key(e[1]))
                    while j + 1 < len(tr) and tr[j + 1]['e' + side] is not None and (key(tr[j + 1]['e' + side][0]), key(tr[j + 1]['e' + side][1])) == ke: j += 1
                    a0, a1 = tr[i]['a'], tr[j]['a']; ap, an = (a0 - 1) % m, (a1 + 1) % m
                    s0 = float((e[0] - C[a0]) @ T[a0]); sp = float((e[0] - C[ap]) @ T[ap]); s1 = float((e[1] - C[a1]) @ T[a1]); sn = float((e[1] - C[an]) @ T[an])
                    if s0 <= 0.0 and sp >= -0.02: add(e[0], base[i] - STEP * (-s0) / max(-s0 + max(sp, 0.0), 1e-6), a0, True, True)
                    else: add(tr[i]['p' + side], base[i], a0, True)
                    if s1 >= 0.0 and sn <= 0.02: add(e[1], base[j] + STEP * s1 / max(s1 + max(-sn, 0.0), 1e-6), a1, False, True)
                    else: add(tr[j]['p' + side], base[j], a1, False)
                i = j + 1
            return [(q, x) for q, x, a, c_ in pts]
        A = line('A'); B = line('B'); mid = tr[len(tr) // 2]; wmed = float(np.median([g['dB'] - g['dA'] for g in tr])); owed = sum(g['need'] for g in tr) > 0.3 * len(tr)
        if cliff(mid) and wmed > 3.0:
            stat['bands that would end at rock away from the road (the cliff side: patch 3)'] += 1; CLIFFS.append((int(co.sl[tr[0]['a']]), int(co.sl[tr[-1]['a']]), tr[0]['sd'], round(wmed, 1), tuple(np.round(mid['pA'], 1).tolist()))); continue
        if len(A) + len(B) < 3: stat['bands too small to follow'] += 1; continue
        if not owed and not KEEP_SLABS and base[-1] - base[0] < max(4.0, wmed): stat['slabs left out (wider than they are long)'] += 1; SLABS.append((int(co.sl[tr[0]['a']]), tr[0]['sd'], round(base[-1] - base[0], 1), round(wmed, 1))); continue
        ft = np.array([g['forest'] for g in tr], bool); at = np.array(base); fr_ = np.array([g['front'] for g in tr], float)
        out.append(dict(A=A, B=B, a=mid['a'], sd=mid['sd'], fA=mid['fA'], fB=mid['fB'], slices=len(tr), w=float(np.mean([g['dB'] - g['dA'] for g in tr])), wall=sum(g['wall'] for g in tr) > 0.5 * len(tr), owed=owed, trees=sum(g['free'] and not g['built'] for g in tr) > 0.3 * len(tr),
                        front=np.array([np.nanmin(fr_[np.abs(at - y) <= 8.0]) if np.isfinite(fr_[np.abs(at - y) <= 8.0]).any() else 0.0 for y in at]),
                        yh=np.array([g['yh'] for g in tr], float), at=at, hasforest=bool(ft.any()), floor=np.array([ft[np.abs(at - y) <= 3.0].any() for y in at])))
    return out

def ladder(b, cell):
    """R4: -> [(3 corners, 3 x (metres along the road, metres from the band's first side))], None for a triangle too steep to be ground.
    A plain grid (owner, 2026-10-09: "everything connected (vertices) and a wireframe that seen from above could be hanged in the Louvre"):
    a RUNG crosses the band at every corner of either side - a corner of one side that has a corner of the other within half a
    cell shares its rung with it - and wherever rungs would be more than a cell apart; rungs are straight; between them rows of quads,
    all cut the same way. (Before: rails smoothed along the band and sewn to the sides' corners in the order of the road - fans of every
    shape, and folds at the tips of bends, where triangles of the fill lay on each other and were then left out: the notches.)"""
    def clean(pts):                                                    # a side must not run back on itself (a corner put out of order at the tip of a bend)
        P = [q for q, x in pts]; S_ = [x for q, x in pts]; ch = True
        while ch and len(P) > 2:
            ch = False
            for k in range(1, len(P) - 1):
                u = (P[k] - P[k - 1])[[0, 2]]; v = (P[k + 1] - P[k])[[0, 2]]; lu = np.linalg.norm(u); lv = np.linalg.norm(v)
                if lu > 1e-6 and lv > 1e-6 and float(u @ v) / (lu * lv) < -0.5: del P[k]; del S_[k]; ch = True; break
        return np.array(P), np.array(S_)
    pa, sa = clean(b['A']); pb, sb = clean(b['B']); at = lambda P, x_, x: np.stack([np.interp(x, x_, P[:, c]) for c in range(3)], 1)
    st = [[float(x), float(x), None] for x in sa]; last = -1             # [where the rung meets side A, where it meets side B (both as metres along the road), paired]
    for x in sb:
        k = next((k for k in range(last + 1, len(st)) if abs(st[k][0] - x) < 0.5 * cell and st[k][2] is None), None)
        if k is not None and all(st[q][0] > x - 0.5 * cell for q in range(last + 1, k)): st[k][1] = float(x); st[k][2] = True; last = k
        else: st.append([float(x), float(x), True])
    st.sort(key=lambda r: 0.5 * (r[0] + r[1])); ta = np.maximum.accumulate([r[0] for r in st]); tb = np.maximum.accumulate([r[1] for r in st])
    keep = [0] + [k for k in range(1, len(st)) if (ta[k] - ta[k - 1]) + (tb[k] - tb[k - 1]) > 0.02]; ta = ta[keep]; tb = tb[keep]; TA = [ta[0]]; TB = [tb[0]]
    for k in range(1, len(ta)):                                        # more rungs where they are far apart
        n = int(np.ceil(max(ta[k] - ta[k - 1], tb[k] - tb[k - 1]) / (1.25 * cell) - 1e-6))
        for q in range(1, n): TA.append(ta[k - 1] + (ta[k] - ta[k - 1]) * q / n); TB.append(tb[k - 1] + (tb[k] - tb[k - 1]) * q / n)
        TA.append(ta[k]); TB.append(tb[k])
    TA = np.array(TA); TB = np.array(TB); PA = at(pa, sa, TA); PB = at(pb, sb, TB); wd = np.linalg.norm(PB - PA, axis=1); N = len(TA) - 1
    M = 1 if FOREST_ONLY else int(min(max(1, round(float(np.percentile(wd, 75)) / cell)), 12)); f = np.arange(M + 1) / M
    fw = np.interp(0.5 * (TA + TB), b['at'], b['front']) if (b.get('front') is not None and not FOREST_ONLY) else np.zeros(len(TA)); f0 = np.where((fw > 0.05) & (wd > fw + 1.0), (fw + 0.3) / np.maximum(wd, 1e-6), 0.0)
    has0 = bool((f0 > 0).any()); FR = (np.concatenate([np.zeros((len(TA), 1)), f0[:, None] + (1.0 - f0)[:, None] * f[None, :]], 1) if has0 else np.repeat(f[None, :], len(TA), 0)); M = FR.shape[1] - 1
    G = PA[:, None, :] + (PB - PA)[:, None, :] * FR[:, :, None]; SS = TA[:, None] + (TB - TA)[:, None] * FR; WW = wd[:, None] * FR; tris = []; riser = False
    if FOREST_ONLY and b.get('yh') is not None and np.isfinite(b['yh']).any():      # owner, 2026-10-11: "in the village the filling height should match the footprint of those houses ... see the door? put it at the bottom"
        ok_ = np.isfinite(b['yh']); st_ = 0.5 * (TA + TB); yt = np.interp(st_, b['at'][ok_], b['yh'][ok_]); nr_ = np.array([np.abs(b['at'][ok_] - x).min() for x in st_]) <= 15.0      # (between two houses the level runs straight from one foot to the next; 15 m beyond the last house it goes back up to the verge)
        A1 = PA.copy(); B1 = PB.copy(); yt = np.minimum(yt, PA[:, 1]); A1[nr_, 1] = yt[nr_]; B1[nr_, 1] = yt[nr_]; dz_ = np.abs(PA[:, 1] - A1[:, 1])
        G = np.stack([PA, A1, B1], 1); SS = np.stack([TA, TA, TB], 1); WW = np.stack([-dz_, np.zeros(len(TA)), wd], 1); M = 2; riser = True; low_ = nr_ & (dz_ > 0.05)      # row 0 -> 1: the riser from the kerb's edge down to the houses' level (nothing where there are no houses)
    def tri(x, y, z):
        T3 = np.array([G[x], G[y], G[z]]); n = np.cross(T3[1] - T3[0], T3[2] - T3[0]); l = float(np.linalg.norm(n)); par = [(float(SS[q]), float(WW[q])) for q in (x, y, z)]
        if l < 2e-3: return
        if abs(n[1]) / l < TILT and not (riser and max(x[1], y[1], z[1]) <= 1): tris.append(None); return
        tris.append((T3, par, has0 and x[1] == 0 and y[1] <= 1 and z[1] <= 1) if n[1] > 0 else (T3[::-1], par[::-1], has0 and x[1] == 0 and y[1] <= 1 and z[1] <= 1))
    for i in range(N):
        for r in range(M):
            if riser and r == 0 and low_[i] and low_[i + 1]: continue      # the kerb's own wall stands there: no second face in its plane
            tri((i, r), (i + 1, r), (i + 1, r + 1)); tri((i, r), (i + 1, r + 1), (i, r + 1))
    return tris

_LIT = {}
def lit_rows(BC, tile):
    """T6: -> (v low, v high) of the tile's evenly lit rows (as texture coordinates, v up), or None when all of it is"""
    if tile not in _LIT:
        px = BC.tile_pixels(tile); _LIT[tile] = None
        if px is not None:
            b = np.asarray(px[0], float)[:, :, :3].mean((1, 2)); H = len(b); k = max(1, H // 32); bs = np.convolve(b, np.ones(k) / k, 'same'); ok = bs >= 0.75 * np.median(bs); best = (0, 0); i = 0
            while i < H:
                if ok[i]:
                    j = i
                    while j < H and ok[j]: j += 1
                    if j - i > best[1] - best[0]: best = (i, j)
                    i = j
                else: i += 1
            if best[1] - best[0] < 0.92 * H and best[1] - best[0] >= 0.3 * H: _LIT[tile] = (1.0 - (best[1] - 2) / H, 1.0 - (best[0] + 2) / H)
    return _LIT[tile]

def dark_tile(BC, tile):
    """T3: the picture <tile>_dk beside the course's own pictures, made when it is not there (as gapfill_gen did)"""
    name = tile + '_dk'; d = os.path.dirname(BC.HI); ds = [x for x in (getattr(BC, 'EXTRA_TEX', None), os.path.join(d, 'textures')) if x]
    if not any(os.path.exists(os.path.join(x, name + '.png')) for x in ds):
        from PIL import Image
        px = BC.tile_pixels(tile)
        if px is None: return tile
        im = Image.fromarray((np.asarray(px[0], float) * DARK).clip(0, 255).astype(np.uint8))
        for x in ds: os.makedirs(x, exist_ok=True); im.save(os.path.join(x, name + '.png'))
    return name

def generate(faces, rd, BC, log, roofs=()):
    import overlay_bake as OB
    co = Course(faces, rd, BC, roofs); m = co.m; C = co.C; ox, oz = rd['ox'], rd['oz']; dec = lambda p: (round(float(p[0] - ox), 1), round(float(p[1]), 1), round(float(-(p[2] - oz)), 1))
    probe = set()
    for q in [x for x in os.environ.get('ROADFILL_PROBE', '').split(';') if x]:
        x, z = map(float, q.split(',')); probe.add(int(np.argmin((C[:, 0] - (x + ox)) ** 2 + (C[:, 2] - (-z + oz)) ** 2)))
    trace = [int(x) for x in os.environ['ROADFILL_TRACE'].split('-')] if os.environ.get('ROADFILL_TRACE') else None
    cen = co.cen; sl = co.sl
    ks = [int(np.argmin(((cen[:, [0, 2]] - np.asarray(fc[2], float)[:, [0, 2]].mean(0)) ** 2).sum(1))) for fc in faces if co.base(fc[0]).endswith('_t') and co.cls(fc[0]) == 'tree_wall']
    forest = (min(ks) - 20, max(ks) + 20) if ks else (1, 0); infor_s = (sl >= forest[0]) & (sl <= forest[1]); need = None      # R10 / R11 (needs()) are OFF: the owner dropped them after seeing them ("floor beneath the trees is a mess"): trees and buildings float until patch 3, hand authored
    gaps, bridge, stat = scan(co, probe=probe, log=log, trace=trace, need=need, infor=infor_s); before = stat['gap metres']
    bs = bridge.all(1); bridges = []; a = 0                             # R7
    while a < m:
        if bs[a]:
            b = a
            while b + 1 < m and (bs[b + 1] or (b + 2 < m and bs[b + 2])): b += 1
            if (b - a) * STEP >= 20.0: bridges.append((a, b))
            a = b + 1
        else: a += 1
    on = np.zeros(m, bool)
    for a, b in bridges:
        if FILL_BRIDGES: log('       roadside fill: BRIDGE filled like the rest (FILL_BRIDGES): slices %d..%d' % (a, b)); continue
        on[max(a - 2, 0):b + 3] = True; log('       roadside fill: BRIDGE, not filled (patch 3): %.0f m, from %s to %s (x, y, z of the decoded scene)' % (co.sig[b] - co.sig[a], dec(C[a]), dec(C[b])))
    # tiles (T1 .. T6) and the ladder of each band
    cen = co.cen; sl = co.sl; fidx = co.sel; cls_of = co.cl; lat = np.asarray(rd['lat'], float)
    def ground_tile(k):                                                # may the fill take the tile of polygon k?
        c = cls_of[k]; t0 = co.orig(faces[fidx[k]][0])
        if co.up[k] or co.roof[k] or co.road[k] or not c or c in NO_TILE or str(t0).endswith('_t'): return None
        return t0
    cand = []; dens = collections.defaultdict(list)
    for k in range(len(fidx)):
        mat, sec, P, UV = faces[fidx[k]][:4]; t0 = co.orig(mat); P = np.asarray(P, float); U = np.asarray(UV, float)
        a3 = 0.5 * np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])); au = 0.5 * abs((U[1, 0] - U[0, 0]) * (U[2, 1] - U[0, 1]) - (U[1, 1] - U[0, 1]) * (U[2, 0] - U[0, 0]))
        if a3 > 0.05 and au > 1e-9: dens[t0].append(np.sqrt(au / a3))
        if ground_tile(k) and cls_of[k] in ('grass', 'rock') and abs(_n(P)[1]) > 0.7:
            ctr = P.mean(0); i = int(np.argmin(((cen[:, [0, 2]] - ctr[[0, 2]]) ** 2).sum(1))); cand.append((ctr[0], ctr[2], 1 if float((ctr - cen[i]) @ lat[i]) > 0 else -1, t0, cls_of[k] == 'rock'))
    CX = np.array([(c[0], c[1]) for c in cand]); CS = np.array([c[2] for c in cand]); CR = np.array([c[4] for c in cand]); dn = {t: float(np.median(v)) for t, v in dens.items()}
    soil_area = collections.Counter()
    for k in range(len(fidx)):
        if cls_of[k] != 'rock' or not ground_tile(k): continue
        P = co.FP[k]; ctr = P.mean(0); i = int(np.argmin(((cen[:, [0, 2]] - ctr[[0, 2]]) ** 2).sum(1)))
        if forest[0] <= i <= forest[1] and np.hypot(*(ctr - cen[i])[[0, 2]]) < 25.0 and abs(_n(P)[1]) > 0.7: soil_area[co.orig(faces[fidx[k]][0])] += float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
    soil_tile = soil_area.most_common(1)[0][0] if soil_area else None
    house = lambda g: g['wall'] and (g['clsB'].startswith('house') or g['clsB'] in ('church', 'arcade'))      # the band ends at a building's wall (town, village): always laid ("make sure the generic rule connects the road to buildings")
    cliff = lambda g: not (g['forest'] or house(g)) and (not (forest[0] <= sl[g['a']] <= forest[1]) or not (g['built'] or g['tileB'] == soil_tile))      # R9: a wide band is laid only where it ends at the forest wall, has houses standing on it, or ends on the forest's own soil
    for key in list(gaps):
        keep_ = [g for g in gaps[key] if (g['forest'] if FOREST_ONLY else      # (owner, 2026-10-11, after four tries at the village's floor height: "just give me the version with the forest fill and make it stop at the houses. I'll fix it myself")
                  not (cliff(g) and g['dB'] - g['dA'] > 3.0))]; n_ = len(gaps[key]) - len(keep_)
        if n_: stat['cuts whose wide gap is cliff side, not roadside (patch 3)'] += n_
        if keep_: gaps[key] = keep_
        else: del gaps[key]
    bd = tracks_of(co, gaps, on, stat, (lambda g: False) if FOREST_ONLY else cliff)
    def nearest(p, sg, rock):
        d = ((CX - np.asarray(p)[[0, 2]]) ** 2).sum(1); ok = CR | (not rock); same = ok & (CS == sg) & (d < 60.0 ** 2); use = same if same.any() else ok; return cand[int(np.argmin(np.where(use, d, np.inf)))][3]
    for b in bd:
        infor = forest[0] <= sl[b['a']] <= forest[1]; sg = -1 if b['sd'] == 0 else 1; tA = ground_tile(b['fA']); tB = None if b['wall'] else ground_tile(b['fB']); p = b['A'][len(b['A']) // 2][0]
        if infor or b['hasforest']:
            t = soil_tile or nearest(p, sg, True); b['dark'] = True    # dark wherever the band ends at the forest wall, houses or not (owner: "vertical dark bottom vegetation? dark patching. always."): decided along the band (b['floor'])
        else: t = tA or tB or nearest(p, sg, False)
        b['tile'] = t; b['dens'] = min(dn.get(t, 0.2), 0.98 / CELL[0]); b['cell'] = float(np.clip(0.98 / b['dens'], *CELL)); b['tris'] = ladder(b, b['cell'])
        stat['triangles too steep for level ground (left out)'] += sum(1 for x in b['tris'] if x is None); b['tris'] = [x for x in b['tris'] if x is not None]
    bd = [b for b in bd if b['tris']]
    # R8: a band where another lies already goes as a whole (narrow bands first)
    bd.sort(key=lambda b: -len(b['tris'])); grid = collections.defaultdict(list); keep = []; left = []
    def lies_on(t):
        t2 = t[:, [0, 2]]; c2 = t2.mean(0); pts = [c2] + [q * 0.8 + c2 * 0.2 for q in t2]; r = int(np.ceil(np.abs(t2 - c2).max() / 8.0)) + 1; cx, cz = int(c2[0] // 8), int(c2[1] // 8)
        for gx in range(cx - r, cx + r + 1):
            for gz in range(cz - r, cz + r + 1):
                for o in grid.get((gx, gz), ()):
                    if abs(o[:, 1].mean() - t[:, 1].mean()) > 4.0: continue
                    o2 = o[:, [0, 2]]; oc = o2.mean(0)
                    if any(_intri(q, o2) for q in pts) or _intri(oc, t2) or any(_intri(q * 0.8 + oc * 0.2, t2) for q in o2): return True
        return False
    for b in bd:
        hit = [lies_on(t) for t, par, fr0 in b['tris']]; nh = sum(hit)
        if nh > 0.5 * len(hit):
            stat['bands left out (a larger band lies there: the same hole found twice)'] += 1; left.append(b['tris'][0][0].mean(0))
            log('       roadside fill: band left out, a larger one lies there: slice %d side %d, %d triangles, %.0f m wide, at %s' % (co.sl[b['a']], b['sd'], len(b['tris']), b['w'], dec(b['tris'][len(b['tris']) // 2][0].mean(0)))); continue
        if nh: stat['triangles left out (a larger band lies there)'] += nh; b['tris'] = [x for x, h in zip(b['tris'], hit) if not h]
        for t, par, fr0 in b['tris']: c2 = t[:, [0, 2]].mean(0); grid[(int(c2[0] // 8), int(c2[1] // 8))].append(t)
        keep.append(b)
    out = []; used = collections.Counter()
    for b in keep:
        t = b['tile']; d = b['dens']; lr = lit_rows(BC, t); name = dark_tile(BC, t) if b.get('dark') else t
        def uv(s, w):
            v = w * d
            if FOREST_ONLY: lo, h = (lr[0], lr[1] - lr[0]) if lr is not None else (0.0, 1.0); return (float(s * d), float(lo + (h if w > 1e-6 else w * d if w < 0 else 0.0)))      # the accordion: the tile's lit rows once across the band
            lo, h = (lr[0], lr[1] - lr[0]) if lr is not None else (0.0, 1.0); x = (v / h) % 2.0; v = lo + h * (x if x <= 1.0 else 2.0 - x)      # T6: back and forth over the lit rows (a row of the band never spans more than the picture)
            return (float(s * d), float(v))
        for tri, par, fr0 in b['tris']:
            nm = name if FOREST_ONLY or (not fr0 and (not b.get('dark') or b['floor'][int(np.argmin(np.abs(b['at'] - np.mean([x[0] for x in par]))))])) else t      # between the kerb and the house fronts: the tile as it is (owner's addendum: "the part that connects or faces the road may retain normal brightness")
            out.append((nm, 'roadfill', [tuple(round(float(x), 4) for x in q) for q in tri], [uv(s, w) for s, w in par])); used[nm] += 1
    if False:                                                          # (walls extruded down through the fill: tried on 2026-10-11 for a village floor at the kerb's foot, dropped with it)
        tg = collections.defaultdict(list)
        for fc in out:
            P_ = np.array(fc[2]); c_ = P_.mean(0)
            if abs(_n(P_)[1]) > 0.5: tg[(int(c_[0] // 8), int(c_[2] // 8))].append(P_)
        def floor_y(q):
            best = None
            for gx in (-1, 0, 1):
                for gz in (-1, 0, 1):
                    for P_ in tg.get((int(q[0] // 8) + gx, int(q[2] // 8) + gz), ()):
                        a_, b_, c_ = P_; d_ = (b_[2] - c_[2]) * (a_[0] - c_[0]) + (c_[0] - b_[0]) * (a_[2] - c_[2])
                        if abs(d_) < 1e-9: continue
                        u_ = ((b_[2] - c_[2]) * (q[0] - c_[0]) + (c_[0] - b_[0]) * (q[2] - c_[2])) / d_; v_ = ((c_[2] - a_[2]) * (q[0] - c_[0]) + (a_[0] - c_[0]) * (q[2] - c_[2])) / d_
                        if u_ >= -1e-6 and v_ >= -1e-6 and u_ + v_ <= 1 + 1e-6:
                            y_ = u_ * a_[1] + v_ * b_[1] + (1 - u_ - v_) * c_[1]
                            if abs(y_ - q[1]) < 6.0 and (best is None or abs(y_ - q[1]) < abs(best - q[1])): best = y_
            return best
        nx = 0; hw_ = np.flatnonzero(co.up & ~co.tw & (np.char.startswith(co.cl, 'house') | (co.cl == 'church') | (co.cl == 'arcade'))); lowest = {}; did = set()
        for k in hw_:
            for q in co.FP[k]: kk = (round(float(q[0]), 1), round(float(q[2]), 1)); lowest[kk] = min(lowest.get(kk, 1e9), float(q[1]))
        for k in hw_:
            fc = faces[co.sel[k]]; P_ = [np.asarray(q, float) for q in fc[2]]; U_ = [np.asarray(q, float) for q in fc[3]]; lo_ = min(q[1] for q in P_)
            ft = [i_ for i_, q in enumerate(P_) if q[1] < lo_ + 0.05]
            if len(ft) != 2 or np.hypot(*(P_[ft[0]] - P_[ft[1]])[[0, 2]]) < 0.2: continue
            a_, b_ = P_[ft[0]], P_[ft[1]]
            if any(q[1] > lowest[(round(float(q[0]), 1), round(float(q[2]), 1))] + 0.02 for q in (a_, b_)): continue      # another wall face goes on below this one (an upper storey): not a foot
            ek_ = frozenset((tuple(np.round(a_, 2)), tuple(np.round(b_, 2))))
            if ek_ in did: continue                                    # the back of the same wall
            did.add(ek_); fa, fb = floor_y(a_), floor_y(b_)
            if fa is None or fb is None or max(a_[1] - fa, b_[1] - fb) > 3.0: continue      # only walls that stand on the fill with both feet (the seaside town's fronts only touch the end of a band: 67 faces in the plane of its boards and doors)
            if fa is None and fb is None: continue
            fa = fb if fa is None else fa; fb = fa if fb is None else fb
            if max(a_[1] - fa, b_[1] - fb) < 0.02: continue
            a2 = np.array([a_[0], min(fa - 0.10, a_[1]), a_[2]]); b2 = np.array([b_[0], min(fb - 0.10, b_[1]), b_[2]])
            d_ = (b_ - a_); d_[1] = 0; L_ = max(np.linalg.norm(d_), 1e-6); d_ /= L_; M_ = np.array([[float((q - a_) @ d_), q[1], 1.0] for q in P_]); A_ = np.linalg.lstsq(M_, np.array(U_), rcond=None)[0]      # the wall's picture carried on downwards
            uv_ = lambda q: tuple(float(x) for x in np.array([float((q - a_) @ d_), q[1], 1.0]) @ A_); r4_ = lambda q: tuple(round(float(x), 4) for x in q)
            for T_ in ((a_, b_, b2), (a_, b2, a2)):
                if np.linalg.norm(np.cross(T_[1] - T_[0], T_[2] - T_[0])) < 2e-4: continue
                out.append((co.base(fc[0]), 'roadfill', [r4_(q) for q in T_], [uv_(q) for q in T_]))
            nx += 1
        stat['house walls extruded down through the fill'] = nx
    vk = lambda q: (round(float(q[0]), 3), round(float(q[1]), 3), round(float(q[2]), 3)); anchor = {vk(q) for P in co.FP for q in P}; partner = collections.Counter(); nlow = set()
    for pass_ in range(12):                                            # R8: nothing in the plane of an existing face (the build's own gate)
        all_ = list(faces) + out; n0 = len(faces); prs = OB.find_pairs(all_, cen[:, [0, 2]])
        if not prs: break
        if pass_ == 0:
            for q in prs: partner[str(all_[min(q[0], q[1])][1])[:10] + ' ' + str(all_[min(q[0], q[1])][0])[-14:]] += 1
        drop = set(); move = set()
        for q in prs:
            i, j = sorted((q[0] - n0, q[1] - n0))
            if j < 0: continue
            if i >= 0: drop.add(j); continue                           # two triangles of the fill: the later one goes
            free_ = [vk(c) for c in out[j][2] if vk(c) not in anchor]  # against a 1995 face (a decal on the ground): the fill's own corners go 6 cm down, in EVERY triangle that has them (a triangle lowered alone tore off its neighbours)
            if not free_ or pass_ >= 6: drop.add(j)
            else: move.update(free_)
        if move: nlow |= move; out = [(fc[0], fc[1], [((c[0], round(c[1] - 0.06, 4), c[2]) if vk(c) in move else c) for c in fc[2]], fc[3]) for fc in out]
        if drop: stat['triangles left out (in the plane of another face)'] += len(drop); left += [np.mean(out[i][2], axis=0) for i in drop]; out = [fc for i, fc in enumerate(out) if i not in drop]
    stat['corners of the fill set lower (a 1995 face lies in the plane)'] = len(nlow)
    if partner: log('       roadside fill: what lay in the plane of the fill (section, tile: pairs): %s' % dict(partner.most_common(8)))
    cs_ = 0.05; ck = lambda q: (int(q[0] // cs_), int(q[1] // cs_), int(q[2] // cs_)); H1 = collections.defaultdict(set)
    for fc in faces:
        for q in fc[2]: q = (round(float(q[0]), 4), round(float(q[1]), 4), round(float(q[2]), 4)); H1[ck(q)].add(q)
    def close(q, HH, lo=-1.0):
        best = None; c = ck(q)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for p_ in HH.get((c[0] + dx, c[1] + dy, c[2] + dz), ()):
                        d_ = ((p_[0] - q[0]) ** 2 + (p_[1] - q[1]) ** 2 + (p_[2] - q[2]) ** 2) ** 0.5
                        if lo < d_ < 0.03 and (best is None or d_ < best[0]): best = (d_, p_)
        return best
    H2 = collections.defaultdict(set); mp = {}; nwa = nwf = 0
    for fc in out:
        for q in fc[2]:
            if q in mp: continue
            b_ = close(q, H1)
            if b_: mp[q] = b_[1]; nwa += b_[0] > 1e-4; continue
            b_ = close(q, H2)
            if b_: mp[q] = b_[1]; nwf += 1
            else: mp[q] = q; H2[ck(q)].add(q)
    o2 = []; nzero = 0
    for fc in out:
        P_ = [mp[q] for q in fc[2]]
        if len(set(P_)) < 3 or 0.5 * float(np.linalg.norm(np.cross(np.subtract(P_[1], P_[0]), np.subtract(P_[2], P_[0])))) < 1e-4: nzero += 1; continue
        o2.append((fc[0], fc[1], P_, fc[3]))
    out = o2; fv = {q for fc in out for q in fc[2]}; H3 = collections.defaultdict(set)
    for q in fv: H3[ck(q)].add(q)
    miss = sum(1 for q in fv if close(q, H1, 1e-4) or close(q, H3, 1e-4))
    stat['CLEAN: corners moved onto a 1995 corner (within 3 cm)'] = nwa; stat['CLEAN: corners of the fill merged with each other'] = nwf; stat['CLEAN: triangles without a surface removed'] = nzero; stat['CLEAN: corners still 0.1 mm .. 3 cm from another corner'] = miss
    A = [0.5 * float(np.linalg.norm(np.cross(np.subtract(fc[2][1], fc[2][0]), np.subtract(fc[2][2], fc[2][0])))) for fc in out]
    g2, _, st2 = scan(co, extra=np.array([[fc[2][0], fc[2][1], fc[2][2], fc[2][2]] for fc in out], float) if out else None, want_edges=False, need=need, infor=infor_s)
    for b in sorted(keep, key=lambda b: -len(b['tris']))[:40]: log('       roadside fill: band at slice %d side %d: %d cuts, %.0f m wide, %d triangles, owed %s, trees %s, tile %s' % (sl[b['a']], b['sd'], b['slices'], b['w'], len(b['tris']), b['owed'], b['trees'], b['tile'][-10:]))
    log('       roadside fill: %d slices %.0f m apart ; bands: %d ; bridges: %d ; forest stretch slices %d..%d' % (m, STEP, len(keep), len(bridges), forest[0], forest[1]))
    log('       roadside fill: %d triangles, %.0f m2, median %.1f m2 a triangle ; missing ground found by the scan: %.0f m of cut line, after the fill: %.0f m' % (len(out), sum(A), float(np.median(A)) if A else 0.0, before, st2['gap metres']))
    log('       roadside fill: %s' % {k: v for k, v in stat.items() if k != 'gap metres'})
    log('       roadside fill: tiles %s ; cells %s' % (dict(used.most_common(10)), {b['tile'][-10:]: round(b['cell'], 1) for b in keep}))
    for c in CLIFFS[:40]: log('       roadside fill: CLIFF SIDE, not filled (patch 3): slices %d..%d side %d, %.0f m wide, at %s' % (c[0], c[1], c[2], c[3], dec(c[4])))
    if SLABS: log('       roadside fill: slabs left out (slice, side, metres along, metres wide): %s' % SLABS[:40])
    if left: log('       roadside fill: left out at (decoded scene x, y, z; first 25 of %d): %s' % (len(left), [dec(q) for q in left[:25]]))
    if os.environ.get('ROADFILL_VIEWS'):                               # places to look at (blendpatch/bl_views.py): eye and target in the decoded scene's coordinates
        vw = []
        def view(name, a, h=28.0, back=30.0, ahead=8.0): vw.append(dict(name=name, eye=list(dec(C[a] - co.T[a] * back + np.array([0, h, 0]))), target=list(dec(C[a] + co.T[a] * ahead))))
        for a, b in bridges[:6]: view('bridge_%d' % sl[a], (a + b) // 2, 60.0, 50.0)
        hp = [a for a in range(m) if co.R[a] < 70 and co.R[a] == co.R[max(a - 25, 0):a + 26].min()]
        for a in hp[:16]: view('hairpin_%d' % sl[a], a, 55.0, 25.0, 0.0)
        ow = sorted([b for b in keep if b['owed']], key=lambda b: -len(b['tris']))
        for b in [b for b in ow if b['trees']][:8]: view('trees_%d_side%d' % (sl[b['a']], b['sd']), b['a'], 20.0, 24.0)
        for b in [b for b in ow if not b['trees'] and not infor_s[b['a']]][:8]: view('town_%d_side%d' % (sl[b['a']], b['sd']), b['a'], 30.0, 30.0)
        for b in sorted(keep, key=lambda b: -len(b['tris']))[:6]: view('band_%d_side%d' % (sl[b['a']], b['sd']), b['a'], 22.0, 26.0)
        fs = [a for a in range(m) if forest[0] <= sl[a] <= forest[1]]
        for a in fs[::max(1, len(fs) // 5)][:5]: view('forest_%d' % sl[a], a)
        hs = sorted({int(np.argmin(((C[:, [0, 2]] - co.FP[k].mean(0)[[0, 2]]) ** 2).sum(1))) for k in np.flatnonzero(np.char.startswith(co.cl, 'house'))})
        for a in hs[::max(1, len(hs) // 6)][:6]: view('village_%d' % sl[a], a, 18.0, 22.0)
        json.dump(vw, open(os.environ['ROADFILL_VIEWS'], 'w'), indent=1)
    return out

def write(faces, rd, BC, cfg, number, needs, log):
    """the generated faces as courses/<game>.<track>.patch.<number>.json (the hand patches' format and coordinates)"""
    import coursepatch
    from common import WORK
    out = generate(faces, rd, BC, log, roofs=tuple(cfg.get('roof_tiles', cfg.get('round_exclude', ())))); ox, oz = rd['ox'], rd['oz']; r = lambda x: round(float(x), 4)
    add = [dict(tile=str(fc[0]), p=[[r(p[0] - ox), r(p[1]), r(-(p[2] - oz))] for p in fc[2]], uv=[[r(u[0]), r(u[1])] for u in fc[3]]) for fc in out]
    head = dict(format='sr3lab course patch', version=1, course=dict(game=cfg['game'], course=str(cfg['course']), name=cfg['name']),
                base=dict(course_export_sha1=coursepatch.export_sha1(BC.HI), needs=list(needs)), made_by='roadfill1995.py (generated: forest floor, verge to forest wall)', **({} if FOREST_ONLY else dict(settings=dict(sea=dict(clip=False)))),
                space='the build decoded back (preview_obj.py): x, y up, z = -gameZ of the 1995 course, metres; uv as Blender has them (v up)')
    path = os.path.join(WORK, 'courses', '%s.%s.patch.%d.json' % (cfg['game'], cfg['name'], number))
    with open(path, 'w', newline='\n') as fo:
        fo.write('{\n' + ''.join(' %s: %s,\n' % (json.dumps(k), json.dumps(v)) for k, v in head.items()))
        fo.write(' "add": [\n' + ',\n'.join('  ' + json.dumps(a) for a in add) + '\n ],\n "move": [\n ]\n}\n')
    log('       patch %d written: %d faces, %d bytes -> %s' % (number, len(add), os.path.getsize(path), path)); return path
