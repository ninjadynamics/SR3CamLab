"""EXPERIMENT (user, 2026-10-07): "Z1R2: Z1 with all natural surfaces rounded by a factor of 2".
Course JSON "round": 2 switches it on; the default build is untouched.

    faces2, info = round_natural(faces, level=1, origin=None)

What is rounded: non-cut-out polygons of the 1995 course whose tile is natural ground (classes rock, grass, dirt, sand,
gravel), and the cliffs / lids of the hand fill. NOT rounded: buildings, walls, roofs, cobbles, asphalt, the road, trees
and every cut-out, the gantries, the sea, and the generated hillside (it is a smoothed 4 m grid already).
Tiles named in `exclude` (course JSON "round_exclude") are never rounded whatever their class says: the village's roof
tile is labelled 'dirt', and build Z15R8 melted every roof of the village into a saddle (user, 2026-10-08).

How (one level = "factor 2"): every polygon is cut into four (edge midpoints; quads also get their centre), corners that
coincide are welded, then passes of smoothing move each free corner half-way to the mean of its neighbours.
A corner stays where it is when
  - a polygon that is NOT rounded uses it (house foot, wall, road edge, tree foot ...), or
  - it lies on an open border of the rounded surface (an edge that belongs to one polygon only): borders are where the
    surface meets things by overlapping them (fills, the hillside) rather than by sharing corners.
Texture coordinates are interpolated, so tiles stay where they were.

Three limits keep a strong rounding (R8 and up) from tearing the scene (build Z15R8, user 2026-10-08: "spiky rocks, saddle
roofs and all sorts of weird things"):
  1. REACH: a corner moves at most `cap` metres, and at most `fade` x its distance (along the surface) from the nearest
     corner that stays. Without it the ground sank metres away from under a kept corner and left it as a spike, and the
     polygons from a kept corner to a far-moved one became stretched slabs beside the road.
  2. ORDER: a corner that was below the road (or any other lying surface that is not rounded: verge, cobbles, hillside,
     fills) stays below it, one that was above stays above, and one that lay ON it does not rise. Without it rounded
     ground came up through the tarmac and through the verge.
  3. Above level 3 the smoothing is done on the level-3 mesh (with the reach of the asked level) and every further level
     only cuts it finer and takes the facets off (8 passes): thousands of passes over millions of corners gave nothing more.
  4. FLAT STAYS COARSE: a polygon whose pieces all end up within `FLAT` of where they started (measured across the polygon) is
     written as the ONE polygon it was, and the corners on its outline go back exactly to where they started, so the finely
     cut neighbours meet its straight edges without a gap (user, 2026-10-08: "the inner, featureless poly-fill of the island
     can stay low-poly, right?"). A flat patch cut into 1024 pieces looks the same as the one piece.
  5. THE ROAD'S APRON STAYS: a corner that stands within `APRON` (up or down) of the road strip - the ground the tarmac lies on and
     the feet of the rock and walls beside it - does not move at all, and the reach (1.) fades the rounding in from there.
     Rounded ground shrinks and sinks: looking straight down beside the road, build BASE had dropped more than 0.3 m in 5 000
     places, which opened holes along the tarmac where it meets rock (user, 2026-10-08). Sealing wall feet again closed 3.
  6. WHERE PEOPLE STAND, THE GROUND STAYS: a corner within `STAND` of a spectator's feet (`keep_at`, the 1995 crowd table) does not move, and the
     reach (1.) fades the rounding in from there. A small standing shape has no kept corner of its own and the smoothing shrinks it towards its
     middle: the box-shaped ledge and the thin pillar at lap 1047 - 1075 became a mound and a stump, and 17 spectators hung up to 7 m in the air
     with sky under them (R2 and R4 with baked light, compared against R1 on 2026-10-13).
  7. NOTHING TURNS OVER: a piece whose drawn triangle ends up turned more than about 78 degrees from the flat polygon it was cut from is folded,
     not rounded (R4: 1 728 pieces, a black line along the rim of that ledge and under a boulder at lap 1866 - their backs). Its corners go
     back to where the stage began, again and again until no piece is folded.
  8. A CORNER THAT STAYS IS PINNED FIRST (pin=True, course setting round_pin, default on; with round_fade 0.25): the corners 7. puts back and the
     outlines of the polygons 4. keeps whole are pinned and the stage's smoothing is run again from its start, so 1.'s reach fades the surface into
     them. Put back AFTER the smoothing they stood out of the sunken ground as horns, and a lid kept whole overhung its shrunken walls (R4, owner's
     screenshots 2026-10-14). round_pin false + round_fade 0.5 builds the R4 of 2026-10-13 again.
Everything is done on arrays (the first version walked Python lists: fine for R2, minutes and gigabytes for R16)."""
import numpy as np

NATURAL = ('rock', 'grass', 'dirt', 'sand', 'gravel')
CAP = 2.5; FADE = 0.5; KEEP_GAP = 0.05; FLAT = 0.02; APRON = 0.75; STAND = 2.5; FOLD = 0.2

def _subdivide(P, U):
    """(n, k, 3) corners and (n, k, 2) texture coordinates of triangles (k = 3) or quads (k = 4) -> four times as many"""
    k = P.shape[1]; m = (P + np.roll(P, -1, axis=1)) / 2; mu = (U + np.roll(U, -1, axis=1)) / 2
    if k == 3:
        parts = [(P[:, 0], m[:, 0], m[:, 2]), (m[:, 0], P[:, 1], m[:, 1]), (m[:, 2], m[:, 1], P[:, 2]), (m[:, 0], m[:, 1], m[:, 2])]
        uv = [(U[:, 0], mu[:, 0], mu[:, 2]), (mu[:, 0], U[:, 1], mu[:, 1]), (mu[:, 2], mu[:, 1], U[:, 2]), (mu[:, 0], mu[:, 1], mu[:, 2])]
    else:
        c = P.mean(1); cu = U.mean(1)
        parts = [(P[:, j], m[:, j], c, m[:, (j - 1) % 4]) for j in range(4)]; uv = [(U[:, j], mu[:, j], cu, mu[:, (j - 1) % 4]) for j in range(4)]
    return np.stack([np.stack(q, 1) for q in parts], 1).reshape(-1, k, 3), np.stack([np.stack(q, 1) for q in uv], 1).reshape(-1, k, 2)

def _pack(P, weld):
    q = np.round(np.asarray(P, np.float64) / weld).astype(np.int64) + (1 << 20)
    return (q[..., 0] << 42) | (q[..., 1] << 21) | q[..., 2]

def _order_limits(X0, X1, movable, S, keep=KEEP_GAP, cell=4.0):
    """lowest and highest y every corner may take so that it stays on its side of the lying triangles S (m, 3, 3).
    X0 = where the corners were, X1 = where they are now."""
    lo = np.full(len(X1), -np.inf); hi = np.full(len(X1), np.inf)
    idx = np.nonzero(movable)[0]
    if not len(idx) or not len(S): return lo, hi
    cx = np.floor(X1[idx, 0] / cell).astype(np.int64); cz = np.floor(X1[idx, 2] / cell).astype(np.int64); BIG = 1 << 22
    ck = (cx + (BIG >> 1)) * BIG + (cz + (BIG >> 1)); o = np.argsort(ck, kind='stable'); ck = ck[o]; idx = idx[o]
    n = np.cross(S[:, 1] - S[:, 0], S[:, 2] - S[:, 0]); ok = np.abs(n[:, 1]) > 1e-9; S = S[ok]; n = n[ok]
    bx0 = np.floor(S[:, :, 0].min(1) / cell).astype(np.int64); bx1 = np.floor(S[:, :, 0].max(1) / cell).astype(np.int64)
    bz0 = np.floor(S[:, :, 2].min(1) / cell).astype(np.int64); bz1 = np.floor(S[:, :, 2].max(1) / cell).astype(np.int64)
    for t in range(len(S)):
        got = []
        for x in range(bx0[t], bx1[t] + 1):
            a = np.searchsorted(ck, (x + (BIG >> 1)) * BIG + (bz0[t] + (BIG >> 1)), 'left'); b = np.searchsorted(ck, (x + (BIG >> 1)) * BIG + (bz1[t] + (BIG >> 1)), 'right')
            if b > a: got.append(idx[a:b])
        if not got: continue
        v = np.concatenate(got); A, B, C = S[t]; p = X1[v]
        d = (B[2] - C[2]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[2] - C[2])
        w0 = ((B[2] - C[2]) * (p[:, 0] - C[0]) + (C[0] - B[0]) * (p[:, 2] - C[2])) / d; w1 = ((C[2] - A[2]) * (p[:, 0] - C[0]) + (A[0] - C[0]) * (p[:, 2] - C[2])) / d
        ins = (w0 >= -1e-6) & (w1 >= -1e-6) & (w0 + w1 <= 1 + 1e-6)
        if not ins.any(): continue
        v = v[ins]; plane = lambda q: A[1] - (n[t, 0] * (q[:, 0] - A[0]) + n[t, 2] * (q[:, 2] - A[2])) / n[t, 1]
        g0 = X0[v, 1] - plane(X0[v]); yp = plane(X1[v]); near = np.abs(g0) < 6.0          # (surfaces far above or below are no business of this corner)
        on = np.abs(g0) < keep; up = (g0 >= keep) & near; dn = (g0 <= -keep) & near
        np.maximum.at(lo, v[up], yp[up] + keep); np.minimum.at(hi, v[dn], yp[dn] - keep); np.minimum.at(hi, v[on], yp[on] + g0[on])
    return lo, hi

def _gap_over(X, S, cell=4.0):
    """how far (up or down) every corner is from the lying triangles S it stands over; inf where it stands over none"""
    gap = np.full(len(X), np.inf)
    if not len(S): return gap
    cx = np.floor(X[:, 0] / cell).astype(np.int64); cz = np.floor(X[:, 2] / cell).astype(np.int64); BIG = 1 << 22
    ck = (cx + (BIG >> 1)) * BIG + (cz + (BIG >> 1)); idx = np.argsort(ck, kind='stable'); ck = ck[idx]
    n = np.cross(S[:, 1] - S[:, 0], S[:, 2] - S[:, 0]); ok = np.abs(n[:, 1]) > 1e-9; S = S[ok]; n = n[ok]
    bx0 = np.floor(S[:, :, 0].min(1) / cell).astype(np.int64); bx1 = np.floor(S[:, :, 0].max(1) / cell).astype(np.int64)
    bz0 = np.floor(S[:, :, 2].min(1) / cell).astype(np.int64); bz1 = np.floor(S[:, :, 2].max(1) / cell).astype(np.int64)
    for t in range(len(S)):
        got = []
        for x in range(bx0[t], bx1[t] + 1):
            a = np.searchsorted(ck, (x + (BIG >> 1)) * BIG + (bz0[t] + (BIG >> 1)), 'left'); b = np.searchsorted(ck, (x + (BIG >> 1)) * BIG + (bz1[t] + (BIG >> 1)), 'right')
            if b > a: got.append(idx[a:b])
        if not got: continue
        v = np.concatenate(got); A, B, C = S[t]; p = X[v]
        d = (B[2] - C[2]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[2] - C[2])
        w0 = ((B[2] - C[2]) * (p[:, 0] - C[0]) + (C[0] - B[0]) * (p[:, 2] - C[2])) / d; w1 = ((C[2] - A[2]) * (p[:, 0] - C[0]) + (A[0] - C[0]) * (p[:, 2] - C[2])) / d
        ins = (w0 >= -1e-6) & (w1 >= -1e-6) & (w0 + w1 <= 1 + 1e-6)
        if not ins.any(): continue
        v = v[ins]; g = np.abs(X[v, 1] - (A[1] - (n[t, 0] * (X[v, 0] - A[0]) + n[t, 2] * (X[v, 2] - A[2])) / n[t, 1])); np.minimum.at(gap, v, g)
    return gap

def round_natural(faces, level=1, origin=None, passes=2, lam=0.5, weld=0.02, log=print, exclude=(), road=None, cap=CAP, fade=FADE, slide=True, keep_at=None, pin=False):
    # pin=True (course setting round_pin, on by default since 2026-10-14; rule 8 below): a corner that has to stay where it started (a folded piece,
    # rule 7; the outline of a polygon put back whole, rule 4) is PINNED and the stage's smoothing is done again from its start with it pinned, so the
    # reach (1.) fades the surface into it. Without it such a corner was put back AFTER its neighbours had sunk and stood out of the ground: the
    # "horns" and lips on R4's rims and tops (owner's screenshots, 2026-10-14; measured: 2 395 corners left standing more than 0.25 m above a
    # neighbour, 204 more than 1 m; with pin and fade 0.25: 1 078 and 34).
    # slide=False (course setting round_slide): a corner moves only along the normal of the surface it sits in. The smoothing pulls a corner towards the
    # middle of its neighbours, which is partly ALONG the surface: the shape hardly changes by that part, but the picture is fixed to the corners and
    # is stretched on one side and squeezed on the other (owner, 2026-10-13: "watch out for texture warping").
    import retex
    if origin is None:
        import overlay_bake as OB
        origin = OB.ORIGIN
    lab = {k: v[0] for k, v in retex.labels().items()}; tile = lambda m: origin.get(str(m).split('|')[0], str(m).split('|')[0]); exclude = tuple(exclude)
    def natural(fc):
        mat, sec = str(fc[0]), str(fc[1])
        if mat.split('|')[0].endswith('_t') or sec == 'sea' or sec.startswith(('hf_terrain', 'hf_weld', 'hf_seal', 'hf_roof', 'verge', 'gantry', 'eave', 'gable')): return False
        if exclude and (tile(mat).startswith(exclude) or mat.startswith(exclude)): return False
        return lab.get(tile(mat)) in NATURAL and len(fc[2]) in (3, 4)
    isnat = np.array([natural(fc) for fc in faces], bool); nat = np.nonzero(isnat)[0]; stat = dict(polygons=int(len(nat)))
    if not len(nat): return list(faces), stat
    fixed = np.unique(_pack(np.array([p for i, fc in enumerate(faces) if not isnat[i] for p in fc[2]], float), weld))
    # the lying surfaces the rounded ground must keep its side of: everything that is not rounded and not a cut-out, plus the road
    S = []
    for i, fc in enumerate(faces):
        if isnat[i] or str(fc[0]).split('|')[0].endswith('_t') or str(fc[1]) == 'sea': continue
        P = np.asarray(fc[2], float)
        for a in range(1, len(P) - 1): S.append((P[0], P[a], P[a + 1]))
    S = np.array(S, float).reshape(-1, 3, 3); nS = np.cross(S[:, 1] - S[:, 0], S[:, 2] - S[:, 0]); ln = np.linalg.norm(nS, axis=1)
    S = S[(ln > 1e-9) & (np.abs(nS[:, 1]) > 0.5 * np.maximum(ln, 1e-12))]
    SR = np.zeros((0, 3, 3))
    if road is not None:
        R = np.asarray(road, float); R2 = np.roll(R, -1, axis=0); a, b, c, d = R[:, :-1], R[:, 1:], R2[:, 1:], R2[:, :-1]
        SR = np.concatenate([np.stack([a, b, c], 2).reshape(-1, 3, 3), np.stack([a, c, d], 2).reshape(-1, 3, 3)]); S = np.concatenate([S, SR])
    # the polygons as arrays, triangles and quads apart
    grp = {}; orig = {}; coarse = {}
    for k in (3, 4):
        ids = [i for i in nat if len(faces[i][2]) == k]
        if ids: grp[k] = [np.array([faces[i][2] for i in ids], float), np.array([faces[i][3] for i in ids], float), np.array(ids, np.int64)]; orig[k] = grp[k][0].copy()      # orig: the same cuts of the polygons as they were
    sched = [(level, passes)] if level <= 3 else [(3, int(64 * 2 ** (level - 2)))] + [(1, 8)] * (level - 3)
    AB = {k: np.repeat(np.array([[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)][:k] if k == 4 else [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]], float), len(grp[k][2]), axis=0) for k in grp}      # where a piece's corners lie in the square of the polygon it was cut from (light maps: PATCH)
    tot = dict(moved=0.0, most=0.0, free=0, held_by_reach=0, held_by_order=0, kept_shared=0, kept_border=0); worst = []
    for stage, (lv, ps) in enumerate(sched):
        for k in grp:
            for _ in range(lv): grp[k][0], grp[k][1] = _subdivide(grp[k][0], grp[k][1]); grp[k][2] = np.repeat(grp[k][2], 4); orig[k] = _subdivide(orig[k], np.zeros(orig[k].shape[:2] + (2,)))[0]; AB[k] = _subdivide(np.zeros(AB[k].shape[:2] + (3,)), AB[k])[1]
        allp = np.concatenate([grp[k][0].reshape(-1, 3) for k in grp]); keys, inv = np.unique(_pack(allp, weld), return_inverse=True); inv = inv.reshape(-1); nv = len(keys)
        cnt = np.bincount(inv, minlength=nv).astype(float); X = np.stack([np.bincount(inv, weights=allp[:, c], minlength=nv) for c in range(3)], 1) / cnt[:, None]
        E = []; off = 0
        for k in grp:
            vi = inv[off:off + grp[k][0].shape[0] * k].reshape(-1, k); off += vi.size; grp[k].append(vi)
            for a in range(k): E.append(np.stack([vi[:, a], vi[:, (a + 1) % k]], 1))
        E = np.concatenate(E); E = E[E[:, 0] != E[:, 1]]; E = np.sort(E, 1); ue, ec = np.unique(E[:, 0] * np.int64(nv) + E[:, 1], return_counts=True); ea = ue // nv; eb = ue % nv
        deg = np.bincount(ea, minlength=nv) + np.bincount(eb, minlength=nv); border = np.zeros(nv, bool); border[ea[ec == 1]] = True; border[eb[ec == 1]] = True
        shared = np.isin(keys, fixed); free = ~shared & ~border & (deg >= 3); start = X.copy()
        apron_ = _gap_over(X, SR) < APRON; tot['apron'] = int((free & apron_).sum()); free &= ~apron_          # (5.)
        if keep_at is not None and len(keep_at):                   # (6.) corners sorted by x, a slab of them looked at per spectator
            K_ = np.asarray(keep_at, float)[:, :3]; xo_ = np.argsort(X[:, 0], kind='stable'); xs_ = X[xo_, 0]; stand_ = np.zeros(nv, bool)
            for (kx, ky, kz), a_, b_ in zip(K_.tolist(), np.searchsorted(xs_, K_[:, 0] - STAND).tolist(), np.searchsorted(xs_, K_[:, 0] + STAND).tolist()):
                c_ = xo_[a_:b_]; stand_[c_[((X[c_, 0] - kx) ** 2 + (X[c_, 2] - kz) ** 2 < STAND * STAND) & (np.abs(X[c_, 1] - ky) < 3.0)]] = True
            tot['stands'] = int((free & stand_).sum()); free &= ~stand_
        # reach: the distance along the surface from the nearest corner that stays
        el = np.linalg.norm(X[ea] - X[eb], axis=1); dist = np.where(free, np.inf, 0.0)
        for _ in range(400):
            d2 = dist.copy(); np.minimum.at(d2, ea, dist[eb] + el); np.minimum.at(d2, eb, dist[ea] + el)
            ch = d2 < dist - 1e-9; dist = d2
            if not ch.any() or d2[ch].min() > cap / fade: break          # (farther than that the reach is `cap` anyway)
        reach = np.minimum(cap, fade * dist) if stage == 0 else np.full(nv, 0.25)
        def held(X):
            d = X - start; n = np.linalg.norm(d, axis=1); s = np.where(n > reach, reach / np.maximum(n, 1e-12), 1.0); return start + d * s[:, None], int((s < 1.0).sum())
        w = 1.0 / np.maximum(deg, 1)
        if not slide:                                              # the surface's normal at every corner: the polygons round it, larger ones counting more
            cn = np.zeros((nv, 3))
            for k in grp:
                vi = grp[k][3]; Pk = start[vi]; pn_ = np.cross(Pk[:, 1] - Pk[:, 0], Pk[:, 2] - Pk[:, 0]) + (np.cross(Pk[:, 2] - Pk[:, 0], Pk[:, 3] - Pk[:, 0]) if k == 4 else 0.0)
                for a in range(k): np.add.at(cn, vi[:, a], pn_)
            cl = np.linalg.norm(cn, axis=1); okn = cl > 1e-9; cn = np.where(okn[:, None], cn / np.maximum(cl, 1e-12)[:, None], 0.0)
            def along(X):
                d = X - start; return np.where(okn[:, None], start + (d * cn).sum(1)[:, None] * cn, X)
        for it in range(ps):
            M = np.stack([np.bincount(ea, weights=X[eb, c], minlength=nv) + np.bincount(eb, weights=X[ea, c], minlength=nv) for c in range(3)], 1) * w[:, None]
            X = np.where(free[:, None], X + lam * (M - X), X)
            if not slide and (it % 4 == 3 or it == ps - 1): X = along(X)
            if it % 8 == 7: X, _ = held(X)
        X, nreach = held(X)
        lo, hi = _order_limits(start, X, free, S); bad = lo > hi; y = np.clip(X[:, 1], lo, np.maximum(hi, lo))
        nord = int((np.abs(y - X[:, 1]) > 1e-6).sum() + bad.sum()); X[:, 1] = y; X[bad] = start[bad]          # (a corner squeezed between two surfaces stays where it was)
        for rnd in range(40):                                      # (7.) the two triangles the game draws of a four-corner piece: corners 0 1 2 and 0 2 3
            fold_ = np.zeros(nv, bool)
            for k in grp:
                vi = grp[k][3]; O = orig[k]; Pk = X[vi]
                for a_, b_, c_ in (((0, 1, 2),) if k == 3 else ((0, 1, 2), (0, 2, 3))):
                    n0 = np.cross(O[:, b_] - O[:, a_], O[:, c_] - O[:, a_]); n1 = np.cross(Pk[:, b_] - Pk[:, a_], Pk[:, c_] - Pk[:, a_]); l0 = np.linalg.norm(n0, axis=1); l1 = np.linalg.norm(n1, axis=1)
                    fold_[vi[(l0 > 1e-9) & ((n0 * n1).sum(1) < FOLD * l0 * l1)].ravel()] = True
            fold_ &= np.abs(X - start).max(1) > 0
            if not fold_.any(): break
            X[fold_] = start[fold_]; tot['unfolded'] = tot.get('unfolded', 0) + int(fold_.sum())
        if pin:                                                    # (8.) the corners that have to stay are pinned and the smoothing is done again around them
            el_ = np.linalg.norm(start[ea] - start[eb], axis=1)
            def run_(pinned):
                fr = free & ~pinned; dist = np.where(fr, np.inf, 0.0)
                for _ in range(400):
                    d2 = dist.copy(); np.minimum.at(d2, ea, dist[eb] + el_); np.minimum.at(d2, eb, dist[ea] + el_)
                    ch = d2 < dist - 1e-9; dist = d2
                    if not ch.any() or d2[ch].min() > cap / fade: break
                rch = np.where(fr, np.minimum(cap, fade * dist) if stage == 0 else 0.25, 0.0)
                def held_(X):
                    d = X - start; n = np.linalg.norm(d, axis=1); s = np.where(n > rch, rch / np.maximum(n, 1e-12), 1.0); return start + d * s[:, None], int((s < 1.0).sum())
                X = start.copy()
                for it in range(ps):
                    M = np.stack([np.bincount(ea, weights=X[eb, c], minlength=nv) + np.bincount(eb, weights=X[ea, c], minlength=nv) for c in range(3)], 1) * w[:, None]
                    X = np.where(fr[:, None], X + lam * (M - X), X)
                    if not slide and (it % 4 == 3 or it == ps - 1): X = along(X)
                    if it % 8 == 7: X, _ = held_(X)
                X, nr_ = held_(X)
                lo, hi = _order_limits(start, X, fr, S); bad = lo > hi; y = np.clip(X[:, 1], lo, np.maximum(hi, lo))
                no_ = int((np.abs(y - X[:, 1]) > 1e-6).sum() + bad.sum()); X[:, 1] = y; X[bad] = start[bad]
                return X, nr_, no_
            def folds_(X):
                f_ = np.zeros(nv, bool)
                for k in grp:
                    vi = grp[k][3]; O = orig[k]; Pk = X[vi]
                    for a_, b_, c_ in (((0, 1, 2),) if k == 3 else ((0, 1, 2), (0, 2, 3))):
                        n0 = np.cross(O[:, b_] - O[:, a_], O[:, c_] - O[:, a_]); n1 = np.cross(Pk[:, b_] - Pk[:, a_], Pk[:, c_] - Pk[:, a_]); l0 = np.linalg.norm(n0, axis=1); l1 = np.linalg.norm(n1, axis=1)
                        f_[vi[(l0 > 1e-9) & ((n0 * n1).sum(1) < FOLD * l0 * l1)].ravel()] = True
                return f_ & (np.abs(X - start).max(1) > 0)
            def settle_(pinned):
                for rnd in range(12):
                    X, nr_, no_ = run_(pinned); f_ = folds_(X)
                    if not f_.any(): return X, nr_, no_, pinned
                    pinned = pinned | f_
                X[f_] = start[f_]; return X, nr_, no_, pinned | f_
            X, nreach, nord, pinned_ = settle_(np.zeros(nv, bool)); tot['unfolded'] = int(pinned_.sum())
        mv = np.linalg.norm(X - start, axis=1) * free; tot['moved'] += float(mv.sum()); tot['most'] = max(tot['most'], float(mv.max())); tot['free'] = int(free.sum()); tot['held_by_reach'] += nreach; tot['held_by_order'] += nord
        tot['kept_shared'] = int(shared.sum()); tot['kept_border'] = int((border & ~shared).sum()); tot['corners'] = int(nv)
        if stage == 0: worst = [(tuple(np.round(start[q], 1)), tuple(np.round(X[q], 1)), round(float(mv[q]), 1)) for q in np.argsort(-mv)[:8]]
        if stage == len(sched) - 1:                                # flat stays coarse (4.)
            nper = 4 ** level; back = np.zeros(nv, bool); tgt = X.copy(); flat = {}
            for k in grp:
                vi = grp[k][3]; O = orig[k]; nrm = np.cross(O[:, 1] - O[:, 0], O[:, 2] - O[:, 0]); nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
                dev = np.abs(((X[vi] - O) * nrm[:, None, :]).sum(2)).max(1); flat[k] = dev.reshape(-1, nper).max(1) < FLAT
            for rnd in range(3):                                      # a corner that goes back may un-flatten nobody, but a polygon beside a bent one must be looked at again with the corners where they will be
                back[:] = False
                for k in grp: m = np.repeat(flat[k], nper); back[grp[k][3][m]] = True; tgt[grp[k][3][m]] = orig[k][m]
                Xn = np.where(back[:, None], tgt, X)
                for k in grp:
                    vi = grp[k][3]; O = orig[k]; nrm = np.cross(O[:, 1] - O[:, 0], O[:, 2] - O[:, 0]); nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
                    flat[k] = np.abs(((Xn[vi] - O) * nrm[:, None, :]).sum(2)).max(1).reshape(-1, nper).max(1) < FLAT
            back[:] = False
            for k in grp: m = np.repeat(flat[k], nper); back[grp[k][3][m]] = True; tgt[grp[k][3][m]] = orig[k][m]
            if pin: X, _, _, pinned_ = settle_(pinned_ | back); tot['lid_pinned'] = int(back.sum())      # (8.) the outlines of the polygons put back whole pinned too: the walls under a lid fade into it
            X = np.where(back[:, None], tgt, X); coarse = flat; tot['flat'] = int(sum(int(f.sum()) for f in flat.values())); tot['flat_pieces'] = tot['flat'] * nper
            tot['seam'] = max([float(np.abs(X[grp[k][3]][np.repeat(flat[k], nper)] - orig[k][np.repeat(flat[k], nper)]).max()) for k in grp if flat[k].any()] or [0.0])      # how far the finely cut neighbours' corners are from the whole polygons' edges: must be 0
        if __import__('os').environ.get('ROUND_DBG') and stage == len(sched) - 1: __import__('pickle').dump({k: X[grp[k][3]] for k in grp}, open(__import__('os').environ['ROUND_DBG'], 'wb'))
        for k in grp: vi = grp[k].pop(); grp[k][0] = X[vi]
    round_natural.worst = worst
    # how much the pictures are stretched: every edge of every piece, its length now over its length before (the picture's coordinates did not move)
    sr_ = []; sc_ = []
    for k in grp:
        O = orig[k]; Pk = grp[k][0]; mx = np.ones(len(Pk))
        for a in range(k):
            l0 = np.linalg.norm(O[:, (a + 1) % k] - O[:, a], axis=1); l1 = np.linalg.norm(Pk[:, (a + 1) % k] - Pk[:, a], axis=1); ok_ = l0 > 1e-6; r_ = np.where(ok_, l1 / np.maximum(l0, 1e-9), 1.0); sr_.append(r_[ok_]); mx = np.maximum(mx, np.maximum(r_, 1.0 / np.maximum(r_, 1e-6)))
        sc_.append((mx, Pk.mean(1)))
    if sr_:
        sr_ = np.concatenate(sr_); mxa = np.concatenate([m_ for m_, c_ in sc_]); cea = np.concatenate([c_ for m_, c_ in sc_]); pct = lambda m_: round(100.0 * float(m_.mean()), 1)
        stat['texture_stretch'] = dict(edges=int(len(sr_)), percent_within_10=pct(np.abs(sr_ - 1) <= 0.10), percent_longer_by_25=pct(sr_ > 1.25), percent_longer_by_50=pct(sr_ > 1.5), percent_twice_as_long=pct(sr_ > 2.0), percent_shorter_than_080=pct(sr_ < 0.8), percent_shorter_than_half=pct(sr_ < 0.5),
                                       pieces_with_an_edge_changed_by_half=int((mxa > 1.5).sum()), pieces_with_an_edge_doubled_or_halved=int((mxa > 2.0).sum()), largest=round(float(sr_.max()), 2), smallest=round(float(sr_.min()), 2))
        round_natural.stretched = [(cea[q].round(2).tolist(), round(float(mxa[q]), 2)) for q in np.argsort(-mxa)[:400]]
        if __import__('os').environ.get('ROUND_STRETCH'): __import__('json').dump(dict(stat=stat['texture_stretch'], worst=round_natural.stretched), open(__import__('os').environ['ROUND_STRETCH'], 'w'))
    out_nat = []; pk_ = []; pa_ = []; pi_ = []
    for k in grp:
        P, U, ids = grp[k]; A = AB[k]
        if k in coarse and coarse[k].any():                         # the flat ones: as they came
            m = np.repeat(coarse[k], 4 ** level); out_nat += [faces[i] for i in ids[m][::4 ** level].tolist()]; P, U, ids = P[~m], U[~m], ids[~m]; A = A[~m]
        r = np.round(P, 3); distinct = np.ones(len(P), np.int64)
        for a in range(1, k): distinct += ~np.any([(r[:, a] == r[:, b]).all(1) for b in range(a)], axis=0)
        good = distinct >= 3; Pl = P[good].tolist(); Ul = U[good].tolist(); il = ids[good].tolist()
        Pg = P[good]; Ag = A[good]
        if k == 3: Pg = np.concatenate([Pg, Pg[:, 2:3]], 1); Ag = np.concatenate([Ag, Ag[:, 2:3]], 1)      # (the mesh writer has a triangle as four corners, the last one twice)
        pk_.append(corner_keys(Pg)); pa_.append(Ag); pi_.append(ids[good])
        out_nat += [(faces[i][0], faces[i][1], [tuple(q) for q in p], [tuple(q) for q in u]) for i, p, u in zip(il, Pl, Ul)]
    if pk_:
        hk = np.concatenate(pk_); PATCH['ab'] = np.concatenate(pa_); PATCH['id'] = np.concatenate(pi_).astype(np.int64); PATCH['corner'] = hk; PATCH['row'] = {b_.tobytes(): r_ for r_, b_ in enumerate(np.sort(hk, axis=1))}
    out = [fc for i, fc in enumerate(faces) if not isnat[i]] + out_nat
    stat.update(polygons_after=len(out_nat), corners=tot['corners'], corners_moved=tot['free'], kept_because_shared_with_other_things=tot['kept_shared'], kept_on_borders=tot['kept_border'],
                mean_move_m=round(tot['moved'] / max(tot['free'], 1), 3), largest_move_m=round(tot['most'], 2), held_back_by_reach=tot['held_by_reach'], held_to_their_side_of_road_and_fills=tot['held_by_order'], kept_on_the_road_apron=tot.get('apron', 0), kept_where_people_stand=tot.get('stands', 0), put_back_because_folded=tot.get('unfolded', 0), polygons_left_whole_because_flat=tot.get('flat', 0), largest_gap_at_their_edges_m=tot.get('seam', 0.0), schedule=sched)
    log('       ROUNDED natural surfaces (experiment, level %d): %s' % (level, stat))
    return out, stat

# ---------------------------------------------------------------- the pieces of a rounded polygon share its light-map rectangle
PATCH = {}                                                             # filled by round_natural: 'row' piece (its corners, sorted) -> row ; 'corner' (n, 4) the corners' numbers in the order they were written ; 'ab' (n, 4, 2) where they lie in the square of the polygon the piece was cut from ; 'id' (n) that polygon
def corner_keys(P4):
    """(n, 4, 3) corners -> (n, 4) one number per corner: its place to the millimetre, taken from the float32 the mesh writer stores"""
    q = np.round(np.asarray(P4, np.float32).astype(np.float64) * 1000.0).astype(np.int64) + (1 << 20); return (q[..., 0] << 42) | (q[..., 1] << 21) | q[..., 2]
def patch_lookup(P4, back=None):
    """(n, 4, 3) corners as the mesh writer has them -> (id per polygon, -1 = not a piece of a rounded polygon ; (n, 4, 2) the corners' places in that
    polygon's square, the unit square where it is none). back[n] = this polygon is the other-side copy of one written once per side: it never
    shares (its light is another light), and it is known by its corners running the other way round."""
    n = len(P4); ids = np.full(n, -1, np.int64); ab = np.tile(np.array([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]), (n, 1, 1))
    if not n or 'row' not in PATCH: return ids, ab
    hq = corner_keys(P4); hs = np.sort(hq, axis=1); get = PATCH['row'].get; rows = np.array([get(b_.tobytes(), -1) for b_ in hs], np.int64); m = np.nonzero(rows >= 0)[0]
    if not len(m): return ids, ab
    st = PATCH['corner'][rows[m]]; sa = PATCH['ab'][rows[m]]; got = np.zeros((len(m), 4, 2))
    for c in range(4): j = (st == hq[m][:, c:c + 1]).argmax(1); got[:, c] = sa[np.arange(len(m)), j]
    area = 0.5 * sum(got[:, c, 0] * got[:, (c + 1) % 4, 1] - got[:, (c + 1) % 4, 0] * got[:, c, 1] for c in range(4))      # the corners as cut run one way round the square, a polygon turned round the other
    keep = np.ones(len(m), bool) if back is None else ~(np.asarray(back, bool)[m] & (area < 0))
    ids[m[keep]] = PATCH['id'][rows[m]][keep]; ab[m[keep]] = got[keep]; return ids, ab

# compiled / array versions of the slow functions above (fastround.py, checked to give the same bytes; SR3_FASTGEO=0 switches them off)
import sys as _sys, fastround as _fr_mod; _fr_mod.install(_sys.modules[__name__])
