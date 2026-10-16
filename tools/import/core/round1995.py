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
Everything is done on arrays (the first version walked Python lists: fine for R2, minutes and gigabytes for R16).
round_outward (the default) without numpy since 2026-10-16 (kb 31): its arrays in round1995.c and fastround's buffer kernels, every step in
its numpy code's order (_old_round_outward, the reference); round_natural ('shrink') and the old helpers import numpy when called."""
import sys, math, array, ctypes

NATURAL = ('rock', 'grass', 'dirt', 'sand', 'gravel')
CAP = 2.5; FADE = 0.5; KEEP_GAP = 0.05; FLAT = 0.02; APRON = 0.75; STAND = 2.5; FOLD = 0.2

def _subdivide(P, U):
    """(n, k, 3) corners and (n, k, 2) texture coordinates of triangles (k = 3) or quads (k = 4) -> four times as many"""
    import numpy as np
    k = P.shape[1]; m = (P + np.roll(P, -1, axis=1)) / 2; mu = (U + np.roll(U, -1, axis=1)) / 2
    if k == 3:
        parts = [(P[:, 0], m[:, 0], m[:, 2]), (m[:, 0], P[:, 1], m[:, 1]), (m[:, 2], m[:, 1], P[:, 2]), (m[:, 0], m[:, 1], m[:, 2])]
        uv = [(U[:, 0], mu[:, 0], mu[:, 2]), (mu[:, 0], U[:, 1], mu[:, 1]), (mu[:, 2], mu[:, 1], U[:, 2]), (mu[:, 0], mu[:, 1], mu[:, 2])]
    else:
        c = P.mean(1); cu = U.mean(1)
        parts = [(P[:, j], m[:, j], c, m[:, (j - 1) % 4]) for j in range(4)]; uv = [(U[:, j], mu[:, j], cu, mu[:, (j - 1) % 4]) for j in range(4)]
    return np.stack([np.stack(q, 1) for q in parts], 1).reshape(-1, k, 3), np.stack([np.stack(q, 1) for q in uv], 1).reshape(-1, k, 2)

def _pack(P, weld):
    import numpy as np
    q = np.round(np.asarray(P, np.float64) / weld).astype(np.int64) + (1 << 20)
    return (q[..., 0] << 42) | (q[..., 1] << 21) | q[..., 2]

def _order_limits(X0, X1, movable, S, keep=KEEP_GAP, cell=4.0):
    """lowest and highest y every corner may take so that it stays on its side of the lying triangles S (m, 3, 3).
    X0 = where the corners were, X1 = where they are now."""
    import numpy as np
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
    import numpy as np
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
    import numpy as np
    _numpy_fast()
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
        hk = np.concatenate(pk_); PATCH['ab'] = np.concatenate(pa_); PATCH['id'] = np.concatenate(pi_).astype(np.int64); PATCH['corner'] = hk; PATCH['row'] = {b_.tobytes(): r_ for r_, b_ in enumerate(canon_keys(hk))}
    out = [fc for i, fc in enumerate(faces) if not isnat[i]] + out_nat
    stat.update(polygons_after=len(out_nat), corners=tot['corners'], corners_moved=tot['free'], kept_because_shared_with_other_things=tot['kept_shared'], kept_on_borders=tot['kept_border'],
                mean_move_m=round(tot['moved'] / max(tot['free'], 1), 3), largest_move_m=round(tot['most'], 2), held_back_by_reach=tot['held_by_reach'], held_to_their_side_of_road_and_fills=tot['held_by_order'], kept_on_the_road_apron=tot.get('apron', 0), kept_where_people_stand=tot.get('stands', 0), put_back_because_folded=tot.get('unfolded', 0), polygons_left_whole_because_flat=tot.get('flat', 0), largest_gap_at_their_edges_m=tot.get('seam', 0.0), schedule=sched)
    log('       ROUNDED natural surfaces (experiment, level %d): %s' % (level, stat))
    return out, stat

# ---------------------------------------------------------------- 'outward' (course setting round_mode, the default since 2026-10-14)
# Owner, 2026-10-14, after R4's notches, tips and clefts: "I want shit to get rounded outwards (or remain straight) unless something is clearly
# concave in low-poly". The rule set above SHRINKS the surface (smoothing pulls every corner towards its neighbours' middle) and needs eight rules to
# keep the shrinking from tearing it; a check of the R4 of that day found 2 605 edges in 538 places bent inward where the 1995 shape was flat or bent
# outward (587 by more than 45 degrees). This one never moves a 1995 corner:
#   O1. Every 1995 corner stays where it is. Each polygon becomes a curved patch through its own corners (a triangle: the cubic "PN" triangle; a
#       four-corner polygon: the patch blended from its four edge curves) and the pieces it is cut into lie on that patch. An edge curve leaves each
#       corner along the plane at right angles to that corner's normal, the normal being the mean of the polygons round the corner that join it
#       smoothly: on a curved shape the patch lies OUTSIDE the facets (it bulges), on a flat stretch it is the facet, and only where the 1995 shape is
#       hollow does it go in.
#   O2. SHARP EDGES STAY: two polygons that meet at more than `crease` degrees, or the wrong way round to each other, or an edge that is an edge of
#       something not rounded (a wall, the verge), or an open border: that edge stays straight and its corners take the normal of their own side
#       only. A flat top at a cliff stays flat (rounded outwards over the rim it would rise in a lip, a hollow behind it).
#   O3. NO NEW HOLLOW: every edge the game draws (the pieces' edges and the diagonal of each four-corner piece) is compared with the same edge
#       uncurved; one that bends inward by more than `tol` degrees more than it did has the curving of its four corners halved, again and again
#       (16 times), then taken away, until no such edge is left.
#   O4. Kept from the rules above: 2. ORDER (a corner stays on its side of the road, the verge and every lying surface that is not rounded),
#       4. FLAT STAYS COARSE, 5. THE APRON and 6. WHERE PEOPLE STAND (no curving there; O3 fades it in), 7. NOTHING TURNS OVER. Nothing ever moves
#       inward on a flat or curved-out shape, so no gap can open where pieces meet without sharing corners: 1. REACH and 8. PINNING are not needed.
# Each corner moves at most `cap` metres. round_mode 'shrink' builds the rule set above (the R4 of 2026-10-13 / the pinned one of 2026-10-14).
CREASE = 45.0; TOL = 2.0; OUT_CAP = 1.5

def _bends(X, TA, TB):
    """signed bend (degrees, + = inward: a hollow seen from the side the triangles face) of every edge shared by two drawn triangles.
    TA / TB (m, 3): the two triangles' corners as (u, v, w) with u -> v the shared edge in TA's order and w the third corner"""
    import numpy as np
    a = X[TA[:, 0]]; b = X[TA[:, 1]]; n1 = np.cross(b - a, X[TA[:, 2]] - a); n2 = np.cross(X[TB[:, 1]] - X[TB[:, 0]], X[TB[:, 2]] - X[TB[:, 0]])
    l1 = np.linalg.norm(n1, axis=1); l2 = np.linalg.norm(n2, axis=1); ok = (l1 > 1e-12) & (l2 > 1e-12)
    ang = np.degrees(np.arccos(np.clip((n1 * n2).sum(1) / np.maximum(l1 * l2, 1e-30), -1.0, 1.0)))
    return np.where(((X[TB[:, 2]] - a) * n1).sum(1) > 0, ang, -ang), ok

def _old_round_outward(faces, level=1, origin=None, weld=0.02, log=print, exclude=(), road=None, keep_at=None, crease=CREASE, tol=TOL, cap=OUT_CAP):
    """(the numpy original of round_outward: the reference)"""
    import retex, time
    import numpy as np
    _numpy_fast()
    t0 = time.time()
    if origin is None:
        import overlay_bake as OB
        origin = OB.ORIGIN
    lab = {k: v[0] for k, v in retex.labels().items()}; tile = lambda m: origin.get(str(m).split('|')[0], str(m).split('|')[0]); exclude = tuple(exclude)
    def natural(fc):
        mat, sec = str(fc[0]), str(fc[1])
        if mat.split('|')[0].endswith('_t') or sec == 'sea' or sec.startswith(('hf_terrain', 'hf_weld', 'hf_seal', 'hf_roof', 'verge', 'gantry', 'eave', 'gable')): return False
        if exclude and (tile(mat).startswith(exclude) or mat.startswith(exclude)): return False
        return lab.get(tile(mat)) in NATURAL and len(fc[2]) in (3, 4)
    isnat = np.array([natural(fc) for fc in faces], bool); nat = np.nonzero(isnat)[0]; stat = dict(mode='outward', polygons=int(len(nat)))
    if not len(nat): return list(faces), stat
    hard = set()                                                       # (O2) the edges of everything not rounded
    for i, fc in enumerate(faces):
        if isnat[i] or len(fc[2]) < 2: continue
        kk = _pack(np.asarray(fc[2], float)[:, :3], weld).tolist()
        for a in range(len(kk)): b = kk[(a + 1) % len(kk)]; hard.add((min(kk[a], b), max(kk[a], b)))
    S = []                                                             # (2.) the lying surfaces the rounded ground keeps its side of, as in round_natural
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
    grp = {}; orig = {}; coarse = {}
    for k in (3, 4):
        ids = [i for i in nat if len(faces[i][2]) == k]
        if ids: grp[k] = [np.array([faces[i][2] for i in ids], float), np.array([faces[i][3] for i in ids], float), np.array(ids, np.int64)]; orig[k] = grp[k][0].copy()
    ks = list(grp)
    # ---- the 1995 polygons: corners, normals, which edges are smooth (O2), the normal of every corner on each side (O1)
    VK = {k: _pack(grp[k][0], weld) for k in ks}; uk, inv = np.unique(np.concatenate([VK[k].ravel() for k in ks]), return_inverse=True); nvc = len(uk)
    VI = {}; off = 0
    for k in ks: VI[k] = inv[off:off + VK[k].size].reshape(-1, k); off += VK[k].size
    FB = {}; FN = []; base = 0
    for k in ks:
        P = grp[k][0]; FN.append(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]) if k == 3 else np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 1])); FB[k] = base; base += len(P)
    FN = np.concatenate(FN); nf = base; FL = np.linalg.norm(FN, axis=1); FU = FN / np.maximum(FL, 1e-12)[:, None]
    EA, EB, EF, EC, EK = [], [], [], [], []
    for k in ks:
        n = len(VI[k])
        for c in range(k): EA.append(VI[k][:, c]); EB.append(VI[k][:, (c + 1) % k]); EF.append(FB[k] + np.arange(n)); EC.append(np.full(n, c)); EK.append(np.full(n, k))
    EA, EB, EF, EC, EK = (np.concatenate(x) for x in (EA, EB, EF, EC, EK)); ok_ = EA != EB
    lo_, hi_ = np.minimum(EA, EB), np.maximum(EA, EB); ek = np.where(ok_, lo_ * np.int64(nvc) + hi_, -1 - np.arange(len(EA)))
    o = np.argsort(ek, kind='stable'); eks = ek[o]; ue, st, cnt = np.unique(eks, return_index=True, return_counts=True)
    sel = (cnt == 2) & (ue >= 0); i1 = o[st[sel]]; i2 = o[st[sel] + 1]
    smooth_e = (EA[i1] == EB[i2]) & (FL[EF[i1]] > 1e-12) & (FL[EF[i2]] > 1e-12) & ((FU[EF[i1]] * FU[EF[i2]]).sum(1) >= np.cos(np.radians(crease)))
    hk = [(int(uk[lo_[i]]), int(uk[hi_[i]])) in hard for i in i1.tolist()]; smooth_e &= ~np.array(hk, bool)
    smooth = np.zeros(len(EA), bool); smooth[i1[smooth_e]] = True; smooth[i2[smooth_e]] = True
    tot = dict(edges=int(len(ue)), smooth_edges=int(smooth_e.sum()), sharp_or_open_edges=int(len(ue) - smooth_e.sum()))
    node = lambda f, c: f * 4 + c                                      # a corner of a polygon; joined across every smooth edge into the fan round that 1995 corner
    s1, s2 = i1[smooth_e], i2[smooth_e]
    pa = np.concatenate([node(EF[s1], EC[s1]), node(EF[s1], (EC[s1] + 1) % EK[s1])]); pb = np.concatenate([node(EF[s2], (EC[s2] + 1) % EK[s2]), node(EF[s2], EC[s2])])
    lab_ = np.arange(nf * 4)
    for _ in range(100000):
        m_ = np.minimum(lab_[pa], lab_[pb]); new = lab_.copy(); np.minimum.at(new, pa, m_); np.minimum.at(new, pb, m_); new = new[new]; new = new[new]
        if np.array_equal(new, lab_): break
        lab_ = new
    fanN = np.zeros((nf * 4, 3)); np.add.at(fanN, lab_, np.repeat(FN, 4, axis=0)); CN = fanN[lab_]; CN /= np.maximum(np.linalg.norm(CN, axis=1), 1e-12)[:, None]
    # ---- the edge curves: the two inner control points' offsets from the straight edge (zero on a sharp or open edge)
    D1 = np.zeros((nf, 4, 3)); D2 = np.zeros((nf, 4, 3))
    for k in ks:
        P = grp[k][0]; f0 = FB[k]; n = len(P)
        for c in range(k):
            a = P[:, c]; b = P[:, (c + 1) % k]; na = CN[node(f0 + np.arange(n), c)]; nb = CN[node(f0 + np.arange(n), (c + 1) % k)]
            D1[f0:f0 + n, c] = -((b - a) * na).sum(1)[:, None] * na / 3.0; D2[f0:f0 + n, c] = -((a - b) * nb).sum(1)[:, None] * nb / 3.0
    sm_fc = np.zeros((nf, 4), bool); sm_fc[EF, EC] = smooth; D1[~sm_fc] = 0.0; D2[~sm_fc] = 0.0
    # (O3) how hollow the 1995 shape is round each polygon: the largest inward bend of a smooth edge of any polygon sharing a corner with it. Rounding
    # spreads such an edge's bend over the pieces beside it (a fillet); only bends beyond it, or any bend where the 1995 shape is flat or curved out, are new
    cen = np.concatenate([grp[k][0].mean(1) for k in ks]); f1, f2 = EF[s1], EF[s2]
    cv = np.where(((cen[f2] - cen[f1]) * FU[f1]).sum(1) > 0, np.degrees(np.arccos(np.clip((FU[f1] * FU[f2]).sum(1), -1.0, 1.0))), 0.0)
    cav = np.zeros(nf); np.maximum.at(cav, f1, cv); np.maximum.at(cav, f2, cv)
    vmax = np.zeros(nvc)
    for k in ks: np.maximum.at(vmax, VI[k].ravel(), np.repeat(cav[FB[k]:FB[k] + len(VI[k])], k))
    cav2 = np.zeros(nf)
    for k in ks: cav2[FB[k]:FB[k] + len(VI[k])] = vmax[VI[k]].max(1)
    # ---- cut every polygon as round_natural does; each piece corner goes onto its polygon's patch
    AB = {k: np.repeat(np.array([[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)][:k] if k == 4 else [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]], float), len(grp[k][2]), axis=0) for k in ks}
    PF = {k: FB[k] + np.arange(len(grp[k][2])) for k in ks}
    for k in ks:
        for _ in range(level): grp[k][0], grp[k][1] = _subdivide(grp[k][0], grp[k][1]); grp[k][2] = np.repeat(grp[k][2], 4); PF[k] = np.repeat(PF[k], 4); orig[k] = _subdivide(orig[k], np.zeros(orig[k].shape[:2] + (2,)))[0]; AB[k] = _subdivide(np.zeros(AB[k].shape[:2] + (3,)), AB[k])[1]
    E_ = lambda f, c, s: 3.0 * ((1 - s) ** 2 * s)[..., None] * D1[f, c] + 3.0 * ((1 - s) * s * s)[..., None] * D2[f, c]
    DD = {}
    for k in ks:
        f = PF[k][:, None] * np.ones((1, k), np.int64); A = AB[k]
        if k == 4:
            u, v = A[..., 0], A[..., 1]
            DD[k] = (1 - v)[..., None] * E_(f, 0, u) + v[..., None] * E_(f, 2, 1 - u) + (1 - u)[..., None] * E_(f, 3, 1 - v) + u[..., None] * E_(f, 1, v)
        else:
            w, u, v = 1 - A[..., 0], A[..., 0] - A[..., 1], A[..., 1]
            d210, d120, d021, d012, d102, d201 = D1[f, 0], D2[f, 0], D1[f, 1], D2[f, 1], D1[f, 2], D2[f, 2]; d111 = 1.5 * (d210 + d120 + d021 + d012 + d102 + d201) / 6.0
            q = lambda s: s[..., None]
            DD[k] = 3 * q(w * w * u) * d210 + 3 * q(w * u * u) * d120 + 3 * q(u * u * v) * d021 + 3 * q(u * v * v) * d012 + 3 * q(v * v * w) * d102 + 3 * q(v * w * w) * d201 + 6 * q(w * u * v) * d111
    # ---- the pieces' corners welded; what may move and how far
    allp = np.concatenate([grp[k][0].reshape(-1, 3) for k in ks]); alld = np.concatenate([DD[k].reshape(-1, 3) for k in ks]); keys, winv = np.unique(_pack(allp, weld), return_inverse=True); winv = winv.reshape(-1); nv = len(keys)
    cntw = np.bincount(winv, minlength=nv).astype(float); start = np.stack([np.bincount(winv, weights=allp[:, c], minlength=nv) for c in range(3)], 1) / cntw[:, None]
    D = np.stack([np.bincount(winv, weights=alld[:, c], minlength=nv) for c in range(3)], 1) / cntw[:, None]
    off = 0
    for k in ks: grp[k].append(winv[off:off + grp[k][0].shape[0] * k].reshape(-1, k)); off += grp[k][0].shape[0] * k
    dl = np.linalg.norm(D, axis=1); D *= np.minimum(1.0, cap / np.maximum(dl, 1e-12))[:, None]; tot['capped'] = int((dl > cap).sum())
    keep = _gap_over(start, SR) < APRON; tot['apron'] = int((keep & (dl > 1e-6)).sum())          # (5.)
    if keep_at is not None and len(keep_at):                           # (6.)
        K_ = np.asarray(keep_at, float)[:, :3]; xo_ = np.argsort(start[:, 0], kind='stable'); xs_ = start[xo_, 0]; stand_ = np.zeros(nv, bool)
        for (kx, ky, kz), a_, b_ in zip(K_.tolist(), np.searchsorted(xs_, K_[:, 0] - STAND).tolist(), np.searchsorted(xs_, K_[:, 0] + STAND).tolist()):
            c_ = xo_[a_:b_]; stand_[c_[((start[c_, 0] - kx) ** 2 + (start[c_, 2] - kz) ** 2 < STAND * STAND) & (np.abs(start[c_, 1] - ky) < 3.0)]] = True
        tot['stands'] = int((stand_ & (dl > 1e-6)).sum()); keep |= stand_
    D[keep] = 0.0
    X = start + D; lo, hi = _order_limits(start, X, np.linalg.norm(D, axis=1) > 1e-9, S); bad = lo > hi; y = np.clip(X[:, 1], lo, np.maximum(hi, lo))
    tot['held_by_order'] = int((np.abs(y - X[:, 1]) > 1e-6).sum() + bad.sum()); D[:, 1] = y - start[:, 1]; D[bad] = 0.0
    # ---- (O3) no new hollow, (7.) nothing turns over: the triangles the game draws, their shared edges
    T = []; TO = []; TP = []
    for k in ks:
        vi = grp[k][3]
        for tr in (((0, 1, 2),) if k == 3 else ((0, 1, 2), (0, 2, 3))): T.append(vi[:, list(tr)]); TO.append(orig[k][:, list(tr)]); TP.append(PF[k])
    T = np.concatenate(T); TO = np.concatenate(TO); TP = np.concatenate(TP); good = (T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2]); T = T[good]; TO = TO[good]; TP = TP[good]
    U_ = np.concatenate([T[:, 0], T[:, 1], T[:, 2]]); V_ = np.concatenate([T[:, 1], T[:, 2], T[:, 0]]); W_ = np.concatenate([T[:, 2], T[:, 0], T[:, 1]])
    ek2 = np.minimum(U_, V_) * np.int64(nv) + np.maximum(U_, V_); o = np.argsort(ek2, kind='stable'); eks = ek2[o]; ue2, st2, cnt2 = np.unique(eks, return_index=True, return_counts=True)
    j1 = o[st2[cnt2 == 2]]; j2 = o[st2[cnt2 == 2] + 1]; cons = U_[j1] == V_[j2]; j1, j2 = j1[cons], j2[cons]
    TA = np.stack([U_[j1], V_[j1], W_[j1]], 1); TB = np.stack([U_[j2], V_[j2], W_[j2]], 1); TP3 = np.concatenate([TP, TP, TP])
    b0, ok0 = _bends(start, TA, TB); b0 = np.maximum(np.maximum(b0, 0.0), np.maximum(cav2[TP3[j1]], cav2[TP3[j2]]))
    n0 = np.cross(TO[:, 1] - TO[:, 0], TO[:, 2] - TO[:, 0]); l0 = np.linalg.norm(n0, axis=1)
    scale = np.ones(nv); rounds = 0; cut = 0
    if __import__('os').environ.get('ROUND_DIAG'): np.savez(__import__('os').environ['ROUND_DIAG'], start=start, D=D, keep=keep, TA=TA, TB=TB, b0=b0, ok0=ok0)
    for rnd in range(40):
        X = start + D * scale[:, None]
        b1, ok1 = _bends(X, TA, TB); hol = ok0 & ok1 & (b1 > b0 + tol)
        P1 = X[T]; n1 = np.cross(P1[:, 1] - P1[:, 0], P1[:, 2] - P1[:, 0]); l1 = np.linalg.norm(n1, axis=1); fold = (l0 > 1e-9) & ((n0 * n1).sum(1) < FOLD * l0 * l1)
        if rnd == 0: tot['new_hollows_before_O3'] = int(hol.sum()); tot['turned_over_before_O3'] = int(fold.sum())
        mark = np.zeros(nv, bool); mark[TA[hol].ravel()] = True; mark[TB[hol, 2]] = True; mark[T[fold].ravel()] = True; mark &= scale > 0
        if not mark.any(): break
        rounds += 1; cut += int(mark.sum()); scale[mark] = scale[mark] * 0.5 if rnd < 16 else 0.0
    X = start + D * scale[:, None]; b1, ok1 = _bends(X, TA, TB)
    tot.update(O3_rounds=rounds, O3_corners_cut=cut, new_hollows_left=int((ok0 & ok1 & (b1 > b0 + tol)).sum()), corners_curved=int((np.linalg.norm(X - start, axis=1) > 0.005).sum()), corners=int(nv))
    nrm_ = lambda O: np.cross(O[:, 1] - O[:, 0], O[:, 2] - O[:, 0])
    dv = X - start; tot['largest_move_m'] = round(float(np.linalg.norm(dv, axis=1).max()), 2); tot['mean_move_m'] = round(float(np.linalg.norm(dv, axis=1)[np.linalg.norm(dv, axis=1) > 0.005].mean()) if (np.linalg.norm(dv, axis=1) > 0.005).any() else 0.0, 3)
    # ---- (4.) flat stays coarse: a polygon whose pieces all stay within FLAT of where they were is written whole, its outline corners exactly back
    nper = 4 ** level; back = np.zeros(nv, bool); flat = {}
    for rnd in range(4):
        Xn = np.where(back[:, None], start, X)
        for k in ks:
            vi = grp[k][3]; O = orig[k]; nn_ = nrm_(O); nn_ /= np.maximum(np.linalg.norm(nn_, axis=1), 1e-12)[:, None]
            flat[k] = np.abs(((Xn[vi] - O) * nn_[:, None, :]).sum(2)).max(1).reshape(-1, nper).max(1) < FLAT
        nb_ = np.zeros(nv, bool)
        for k in ks: nb_[grp[k][3][np.repeat(flat[k], nper)]] = True
        if np.array_equal(nb_, back): break
        back = nb_
    X = np.where(back[:, None], start, X); coarse = flat; tot['flat'] = int(sum(int(f.sum()) for f in flat.values()))
    for k in ks: vi = grp[k].pop(); grp[k][0] = X[vi]
    if __import__('os').environ.get('ROUND_DBG'):                     # the pieces before and after, in the form rdbg's hollow.py / ana.py read
        __import__('pickle').dump(dict(level=level, groups={k: dict(orig=orig[k], final=grp[k][0], flat=np.repeat(flat[k], nper), ids=grp[k][2]) for k in ks}), open(__import__('os').environ['ROUND_DBG'], 'wb'))
    stat.update(tot); stat['seconds'] = round(time.time() - t0, 1)
    return _emit(faces, isnat, grp, orig, AB, coarse, level, stat, log, 'ROUNDED OUTWARDS (rules O1-O4, level %d)' % level)

def _emit(faces, isnat, grp, orig, AB, coarse, level, stat, log, what):
    """the pieces as polygons, the light-map table PATCH and the stretch figures (as at the end of round_natural)"""
    import numpy as np
    sr_ = []
    for k in grp:
        O = orig[k]; Pk = grp[k][0]
        for a in range(k):
            l0 = np.linalg.norm(O[:, (a + 1) % k] - O[:, a], axis=1); l1 = np.linalg.norm(Pk[:, (a + 1) % k] - Pk[:, a], axis=1); ok_ = l0 > 1e-6; sr_.append(np.where(ok_, l1 / np.maximum(l0, 1e-9), 1.0)[ok_])
    if sr_:
        sr_ = np.concatenate(sr_); pct = lambda m_: round(100.0 * float(m_.mean()), 1)
        stat['texture_stretch'] = dict(edges=int(len(sr_)), percent_within_10=pct(np.abs(sr_ - 1) <= 0.10), percent_longer_by_25=pct(sr_ > 1.25), largest=round(float(sr_.max()), 2), smallest=round(float(sr_.min()), 2))
    out_nat = []; pk_ = []; pa_ = []; pi_ = []
    for k in grp:
        P, U, ids = grp[k][:3]; A = AB[k]
        if k in coarse and coarse[k].any():
            m = np.repeat(coarse[k], 4 ** level); out_nat += [faces[i] for i in ids[m][::4 ** level].tolist()]; P, U, ids = P[~m], U[~m], ids[~m]; A = A[~m]
        r = np.round(P, 3); distinct = np.ones(len(P), np.int64)
        for a in range(1, k): distinct += ~np.any([(r[:, a] == r[:, b]).all(1) for b in range(a)], axis=0)
        good = distinct >= 3; Pl = P[good].tolist(); Ul = U[good].tolist(); il = ids[good].tolist(); Pg = P[good]; Ag = A[good]
        if k == 3: Pg = np.concatenate([Pg, Pg[:, 2:3]], 1); Ag = np.concatenate([Ag, Ag[:, 2:3]], 1)
        pk_.append(corner_keys(Pg)); pa_.append(Ag); pi_.append(ids[good])
        out_nat += [(faces[i][0], faces[i][1], [tuple(q) for q in p], [tuple(q) for q in u]) for i, p, u in zip(il, Pl, Ul)]
    PATCH.clear()
    if pk_:
        hk = np.concatenate(pk_); PATCH['ab'] = np.concatenate(pa_); PATCH['id'] = np.concatenate(pi_).astype(np.int64); PATCH['corner'] = hk; PATCH['row'] = {b_.tobytes(): r_ for r_, b_ in enumerate(canon_keys(hk))}
    out = [fc for i, fc in enumerate(faces) if not isnat[i]] + out_nat; stat['polygons_after'] = len(out_nat)
    log('       %s: %s' % (what, stat))
    return out, stat

# ---------------------------------------------------------------- the pieces of a rounded polygon share its light-map rectangle
PATCH = {}                                                           # filled by round_natural: 'row' piece (its corners, sorted) -> row ; 'corner' (n, 4) the corners' numbers in the order they were written ; 'ab' (n, 4, 2) where they lie in the square of the polygon the piece was cut from ; 'id' (n) that polygon
def canon_keys(K4):
    """(n, 4) corner numbers -> one key a polygon whatever order its corners run in: sorted, a corner written twice (a triangle) counted once and the
    fourth place filled with the largest number. (Sorted as they were, a triangle turned round for its other side, corners 0 2 1 1, did not match the
    piece it is, 0 1 2 2: every other-side triangle piece missed its polygon's rectangle and was lit alone; owner's shot SR3_20261015_003943.)"""
    import numpy as np
    s = np.sort(np.asarray(K4, np.int64), axis=1); d = np.zeros(s.shape, bool); d[:, 1:] = s[:, 1:] == s[:, :-1]
    return np.sort(np.where(d, np.iinfo(np.int64).max, s), axis=1)
def corner_keys(P4):
    """(n, 4, 3) corners -> (n, 4) one number per corner: its place to the millimetre, taken from the float32 the mesh writer stores"""
    import numpy as np
    q = np.round(np.asarray(P4, np.float32).astype(np.float64) * 1000.0).astype(np.int64) + (1 << 20); return (q[..., 0] << 42) | (q[..., 1] << 21) | q[..., 2]
def patch_lookup(P4, back=None):
    """(n, 4, 3) corners as the mesh writer has them -> (id per polygon, -1 = not a piece of a rounded polygon ; (n, 4, 2) the corners' places in that
    polygon's square, the unit square where it is none). back[n] = this polygon is the other-side copy of one written once per side: it never
    shares the front's rectangle (its light is another light), only the other-side copies of the same polygon's pieces share one (the polygon's number +
    BACK_RECT); it is known by its corners running the other way round."""
    import numpy as np                                                # (build_classic hands numpy corners and takes numpy arrays back; PATCH holds buffers)
    n = len(P4); ids = np.full(n, -1, np.int64); ab = np.tile(np.array([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]), (n, 1, 1))
    if not n or 'row' not in PATCH: return ids, ab
    hq = corner_keys(P4); hs = canon_keys(hq); get = PATCH['row'].get; rows = np.array([get(b_.tobytes(), -1) for b_ in hs], np.int64); m = np.nonzero(rows >= 0)[0]
    if not len(m): return ids, ab
    pcorner = np.frombuffer(PATCH['corner'], np.int64).reshape(-1, 4); pab = np.frombuffer(PATCH['ab'], np.float64).reshape(-1, 4, 2); pid = np.frombuffer(PATCH['id'], np.int64)
    st = pcorner[rows[m]]; sa = pab[rows[m]]; got = np.zeros((len(m), 4, 2))
    for c in range(4): j = (st == hq[m][:, c:c + 1]).argmax(1); got[:, c] = sa[np.arange(len(m)), j]
    area = 0.5 * sum(got[:, c, 0] * got[:, (c + 1) % 4, 1] - got[:, (c + 1) % 4, 0] * got[:, c, 1] for c in range(4))      # the corners as cut run one way round the square, a polygon turned round the other
    bk = np.zeros(len(m), bool) if back is None else (np.asarray(back, bool)[m] & (area < 0))
    # the other-side copies of a polygon's pieces share a rectangle of THEIR OWN (the polygon's number + BACK_RECT): alone, each piece of a side seen only
    # from a free camera was lit in a rectangle of 2 x 2 texels, and the light broke into blotches along the pieces (owner's shot SR3_20261015_003943)
    ids[m] = pid[rows[m]] + np.where(bk, BACK_RECT, 0); ab[m] = got; return ids, ab
BACK_RECT = 1 << 40

def _numpy_fast():
    """compiled versions of the slow numpy functions above for the numpy code (fastround.install: checked to give the same bytes; SR3_FASTGEO=0 off)"""
    import fastround
    fastround.install(sys.modules[__name__])

# ---------------------------------------------------------------- round_outward without numpy
_L = None
def _lib():
    global _L
    if _L is None:
        import cbuild
        cbuild.runtime(); L = ctypes.CDLL(cbuild.dll('round1995')); P = ctypes.c_void_p; LL = ctypes.c_longlong; D = ctypes.c_double; I = ctypes.c_int
        for nm, a, r in (('ro_hard', [LL, P, P, D, P], LL), ('ro_lying', [LL, P, P, LL, LL, P, P], LL), ('ro_faces', [LL, P, P, D, P, LL, D, P, P, P, P], I),
                         ('ro_dd', [LL, I, P, P, P, P, P], None), ('ro_weld', [LL, P, P, D, P, P, P], LL), ('ro_cap', [LL, P, D, P], LL), ('ro_argsort_x', [LL, P, P], None),
                         ('ro_keep', [LL, P, P, P, P, P], None), ('ro_order', [LL, P, P, P, P, P], LL), ('ro_tris', [I, P, P, P, P, P, LL, P, P, P, P, P, P, P, P], LL),
                         ('ro_b0', [LL, P, P, P, P, P, P, P, P], I), ('ro_o3', [LL, P, P, P, LL, P, P, LL, P, P, P, P, D, D, P, P], I),
                         ('ro_flat', [LL, P, P, I, P, P, P, P, LL, D, P, P], LL), ('ro_moves', [LL, P, P, P], None), ('ro_gather', [LL, P, P, P], None),
                         ('ro_stretch', [LL, I, P, P, P], LL), ('ro_good', [LL, I, P, P, P], None), ('ro_patch', [LL, I, P, P, P, P, P], LL)):
            f = getattr(L, nm); f.argtypes = a; f.restype = r
        _L = L
    return _L
def _ad(a):
    """the address of a buffer for the C: array.array, npyio.Arr, bytearray"""
    if a is None: return None
    if isinstance(a, array.array): return a.buffer_info()[0]
    if hasattr(a, 'ptr'): return a.ptr()
    return ctypes.addressof((ctypes.c_char * max(len(a), 1)).from_buffer(a)) if len(a) else None
def _arr(dtype, shape, a):
    """an npyio.Arr on a buffer (an array.array as its bytes: Arr counts bytes)"""
    from npyio import Arr
    return Arr(dtype, shape, memoryview(a).cast('B') if isinstance(a, array.array) else a)
def _f8(a):
    """float64 numbers of an array (numpy's, an Arr, or rows) as array('d')"""
    out = array.array('d')
    if hasattr(a, 'view') and hasattr(a, 'ptr'): out.frombytes(memoryview(a.buf)[:a.nbytes])
    elif hasattr(a, 'shape'): out.frombytes(memoryview(a).tobytes())
    else: out.extend(float(v) for r in a for v in (r if hasattr(r, '__len__') else [r]))
    return out
def round_outward(faces, level=1, origin=None, weld=0.02, log=print, exclude=(), road=None, keep_at=None, crease=CREASE, tol=TOL, cap=OUT_CAP):
    """faces2, info = round_outward(faces, level): rules O1 - O4 above. The same input, output and light-map table (PATCH) as round_natural.
    The steps of _old_round_outward (its numpy is quoted in round1995.c) on buffers; the same faces, figures and PATCH."""
    import retex, time, bisect, npexact
    import fastround as FR
    from npyio import Arr
    t0 = time.time()
    if origin is None:
        import overlay_bake as OB
        origin = OB.ORIGIN
    lab = {k: v[0] for k, v in retex.labels().items()}; tile = lambda m: origin.get(str(m).split('|')[0], str(m).split('|')[0]); exclude = tuple(exclude)
    def natural(fc):
        mat, sec = str(fc[0]), str(fc[1])
        if mat.split('|')[0].endswith('_t') or sec == 'sea' or sec.startswith(('hf_terrain', 'hf_weld', 'hf_seal', 'hf_roof', 'verge', 'gantry', 'eave', 'gable')): return False
        if exclude and (tile(mat).startswith(exclude) or mat.startswith(exclude)): return False
        return lab.get(tile(mat)) in NATURAL and len(fc[2]) in (3, 4)
    isnat = [natural(fc) for fc in faces]; nat = [i for i, b in enumerate(isnat) if b]; stat = dict(mode='outward', polygons=len(nat))
    if not nat: return list(faces), stat
    L = _lib(); ad = _ad; P_ = ctypes.c_void_p
    def corners(fl):
        coff = array.array('q', [0]); C = array.array('d')
        for fc in fl: C.extend(float(v) for p in fc[2] for v in tuple(p)[:3]); coff.append(coff[-1] + len(fc[2]))
        return coff, C
    oth = [fc for i, fc in enumerate(faces) if not isnat[i]]
    co, C = corners(oth); hard = array.array('q', bytes(16 * max(co[-1], 1))); nh = L.ro_hard(len(oth), ad(co), ad(C), weld, ad(hard))      # (O2) the edges of everything not rounded
    co2, C2 = corners([fc for fc in oth if not (str(fc[0]).split('|')[0].endswith('_t') or str(fc[1]) == 'sea')])                         # (2.) the lying surfaces
    if road is not None: ns_, nc_ = int(road.shape[0]), int(road.shape[1]); Rb = _f8(road)
    else: ns_ = nc_ = 0; Rb = array.array('d', [0.0])
    nS = L.ro_lying(len(co2) - 1, ad(co2), ad(C2), ns_, nc_, ad(Rb), None); S = array.array('d', bytes(72 * max(nS, 1))); L.ro_lying(len(co2) - 1, ad(co2), ad(C2), ns_, nc_, ad(Rb), ad(S))
    z = array.array('q', [0]); nSR = L.ro_lying(0, ad(z), ad(Rb), ns_, nc_, ad(Rb), None); SR = array.array('d', bytes(72 * max(nSR, 1))); L.ro_lying(0, ad(z), ad(Rb), ns_, nc_, ad(Rb), ad(SR))
    # ---- the 1995 polygons (triangles first, then quads, as round1995 groups them)
    ks = [k for k in (3, 4) if any(len(faces[i][2]) == k for i in nat)]; G = {}; FB = {}; nf = 0
    for k in ks:
        ids = [i for i in nat if len(faces[i][2]) == k]
        G[k] = dict(ids=ids, n=len(ids), P=array.array('d', [float(v) for i in ids for q in faces[i][2] for v in q]), U=array.array('d', [float(v) for i in ids for q in faces[i][3] for v in q]))
        FB[k] = nf; nf += len(ids)
    Pf = array.array('d', bytes(96 * nf)); Kf = array.array('i', bytes(4 * nf))
    for k in ks:
        P = G[k]['P']
        for j in range(G[k]['n']): f = FB[k] + j; Pf[12 * f:12 * f + 3 * k] = P[3 * k * j:3 * k * (j + 1)]; Kf[f] = k
    D1 = array.array('d', bytes(96 * nf)); D2 = array.array('d', bytes(96 * nf)); cav2 = array.array('d', bytes(8 * nf)); st = array.array('q', [0, 0, 0])
    if L.ro_faces(nf, ad(Kf), ad(Pf), weld, ad(hard), nh, math.cos(math.radians(crease)), ad(D1), ad(D2), ad(cav2), ad(st)): raise RuntimeError('round1995.c: UCRT acos unavailable')      # np.cos(np.radians(crease)): the same UCRT cos, x * (pi / 180)
    tot = dict(edges=st[0], smooth_edges=st[1], sharp_or_open_edges=st[2])
    # ---- cut every polygon as round_natural does; each piece corner goes onto its polygon's patch
    nper = 4 ** level
    for k in ks:
        g = G[k]; n = g['n']; Pa = Arr('<f8', (n, k, 3), bytearray(g['P'].tobytes())); Ua = Arr('<f8', (n, k, 2), bytearray(g['U'].tobytes()))
        ABa = Arr('<f8', (n, k, 2), bytearray(array.array('d', ([0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0] if k == 4 else [0.0, 0.0, 1.0, 0.0, 1.0, 1.0]) * n).tobytes()))
        for _ in range(level): Pa, Ua = FR.subdivide_buf(Pa, Ua); ABa = FR.subdivide_buf(Arr('<f8', ABa.shape[:2] + (3,)), ABa)[1]      # (orig: the same cuts, the same numbers as Pa)
        g.update(O=Pa, U=Ua, AB=ABa, np=n * nper); g['PF'] = array.array('q', [FB[k] + p // nper for p in range(g['np'])])
        g['DD'] = array.array('d', bytes(24 * g['np'] * k)); L.ro_dd(g['np'], k, ad(g['PF']), ad(ABa), ad(D1), ad(D2), ad(g['DD']))
    # ---- the pieces' corners welded; what may move and how far
    allp = array.array('d'); alld = array.array('d')
    for k in ks: allp.frombytes(memoryview(G[k]['O'].buf)[:G[k]['O'].nbytes]); alld.extend(G[k]['DD'])
    na = len(allp) // 3; winv = array.array('q', bytes(8 * na)); nv = L.ro_weld(na, ad(allp), ad(alld), weld, ad(winv), None, None)
    start = array.array('d', bytes(24 * nv)); D = array.array('d', bytes(24 * nv)); L.ro_weld(na, ad(allp), ad(alld), weld, ad(winv), ad(start), ad(D)); off = 0
    for k in ks: G[k]['vi'] = winv[off:off + G[k]['np'] * k]; off += G[k]['np'] * k
    dl = array.array('d', bytes(8 * nv)); tot['capped'] = L.ro_cap(nv, ad(D), cap, ad(dl))
    startA = _arr('<f8', (nv, 3), start)
    gap = FR.gap_over_buf(startA, _arr('<f8', (nSR, 3, 3), SR)).view(); keep = bytearray(1 if v < APRON else 0 for v in gap)      # (5.)
    tot['apron'] = sum(1 for k_, d_ in zip(keep, dl) if k_ and d_ > 1e-6)
    if keep_at is not None and len(keep_at):                           # (6.) corners sorted by x, a slab of them looked at per spectator
        xo = array.array('q', bytes(8 * nv)); L.ro_argsort_x(nv, ad(start), ad(xo)); xs = [start[3 * i] for i in xo]; stand = bytearray(nv); SS = STAND * STAND
        for q in keep_at:
            kx, ky, kz = float(q[0]), float(q[1]), float(q[2])
            for c in xo[bisect.bisect_left(xs, kx - STAND):bisect.bisect_left(xs, kx + STAND)]:
                dx = start[3 * c] - kx; dz = start[3 * c + 2] - kz
                if dx * dx + dz * dz < SS and abs(start[3 * c + 1] - ky) < 3.0: stand[c] = 1
        tot['stands'] = sum(1 for s_, d_ in zip(stand, dl) if s_ and d_ > 1e-6); keep = bytearray(a | b for a, b in zip(keep, stand))
    X = array.array('d', bytes(24 * nv)); mov = bytearray(nv); L.ro_keep(nv, ad(keep), ad(start), ad(D), ad(X), ad(mov))
    lo, hi = FR.order_limits_buf(startA, _arr('<f8', (nv, 3), X), _arr('|u1', (nv,), mov), _arr('<f8', (nS, 3, 3), S))
    tot['held_by_order'] = L.ro_order(nv, lo.ptr(), hi.ptr(), ad(start), ad(X), ad(D))
    # ---- (O3) no new hollow, (7.) nothing turns over: the triangles the game draws, their shared edges
    ksA = array.array('i', ks); nsA = array.array('q', [G[k]['np'] for k in ks]); vis = (P_ * len(ks))(*[ad(G[k]['vi']) for k in ks]); Os = (P_ * len(ks))(*[G[k]['O'].ptr() for k in ks]); PFs = (P_ * len(ks))(*[ad(G[k]['PF']) for k in ks])
    cn = array.array('q', [0, 0]); L.ro_tris(len(ks), ad(ksA), ad(nsA), vis, Os, PFs, nv, ad(cn), None, None, None, None, None, None, None); nt, ne = cn[0], cn[1]
    T = array.array('q', bytes(24 * max(nt, 1))); TO = array.array('d', bytes(72 * max(nt, 1))); TP = array.array('q', bytes(8 * max(nt, 1))); TA = array.array('q', bytes(24 * max(ne, 1))); TB = array.array('q', bytes(24 * max(ne, 1)))
    TPA = array.array('q', bytes(8 * max(ne, 1))); TPB = array.array('q', bytes(8 * max(ne, 1))); L.ro_tris(len(ks), ad(ksA), ad(nsA), vis, Os, PFs, nv, ad(cn), ad(T), ad(TO), ad(TP), ad(TA), ad(TB), ad(TPA), ad(TPB))
    b0 = array.array('d', bytes(8 * max(ne, 1))); ok0 = bytearray(max(ne, 1)); L.ro_b0(ne, ad(start), ad(TA), ad(TB), ad(TPA), ad(TPB), ad(cav2), ad(b0), ad(ok0))
    scale = array.array('d', [1.0]) * nv; X = array.array('d', bytes(24 * nv)); s3 = array.array('q', [0] * 5)
    L.ro_o3(nv, ad(start), ad(D), ad(scale), nt, ad(T), ad(TO), ne, ad(TA), ad(TB), ad(b0), ad(ok0), tol, FOLD, ad(X), ad(s3))
    tot['new_hollows_before_O3'] = s3[2]; tot['turned_over_before_O3'] = s3[3]
    mv = array.array('d', bytes(8 * nv)); L.ro_moves(nv, ad(X), ad(start), ad(mv)); far = [v for v in mv if v > 0.005]
    tot.update(O3_rounds=s3[0], O3_corners_cut=s3[1], new_hollows_left=s3[4], corners_curved=len(far), corners=nv)
    tot['largest_move_m'] = round(max(mv), 2); tot['mean_move_m'] = round(npexact.pwsum(far) / len(far), 3) if far else 0.0      # (np.mean: numpy's pairwise sum / n)
    # ---- (4.) flat stays coarse: a polygon whose pieces all stay within FLAT of where they were is written whole, its outline corners exactly back
    foff = array.array('q', [0]); fo = {}
    for k in ks: fo[k] = foff[-1]; foff.append(foff[-1] + G[k]['n'])
    flat = bytearray(foff[-1]); tot['flat'] = L.ro_flat(nv, ad(start), ad(X), len(ks), ad(ksA), ad(nsA), vis, Os, nper, FLAT, ad(flat), ad(foff))
    for k in ks: g = G[k]; g['X'] = array.array('d', bytes(24 * g['np'] * k)); L.ro_gather(g['np'] * k, ad(g['vi']), ad(X), ad(g['X']))
    stat.update(tot); stat['seconds'] = round(time.time() - t0, 1)
    return _emit_buf(faces, isnat, G, ks, flat, fo, level, stat, log, 'ROUNDED OUTWARDS (rules O1-O4, level %d)' % level)
def _emit_buf(faces, isnat, G, ks, flat, fo, level, stat, log, what):
    """_emit on round_outward's buffers: the pieces as polygons, the light-map table PATCH, the stretch figures"""
    import fastround as FR
    from npyio import Arr
    L = _lib(); ad = _ad; nper = 4 ** level; sr = array.array('d')
    for k in ks:
        g = G[k]; r = array.array('d', bytes(8 * g['np'] * k)); m = L.ro_stretch(g['np'], k, ad(g['O']), ad(g['X']), ad(r)); sr.extend(r[:m])
    if len(sr):
        n = len(sr); pct = lambda c: round(100.0 * (c / n), 1)            # (the mean of a boolean array: how many / n)
        stat['texture_stretch'] = dict(edges=n, percent_within_10=pct(sum(1 for v in sr if abs(v - 1) <= 0.10)), percent_longer_by_25=pct(sum(1 for v in sr if v > 1.25)), largest=round(max(sr), 2), smallest=round(min(sr), 2))
    out_nat = []; PG = array.array('d'); PA = array.array('d'); PI = array.array('q')
    for k in ks:
        g = G[k]; ids = g['ids']; skip = bytearray(g['np'])
        for f in range(g['n']):
            if flat[fo[k] + f]: out_nat.append(faces[ids[f]]); skip[f * nper:(f + 1) * nper] = b'\x01' * nper      # the flat ones: as they came
        good = bytearray(g['np']); L.ro_good(g['np'], k, ad(g['X']), ad(skip), ad(good))
        Xl = g['X'].tolist(); Ul = g['U'].tolist(); ct = list(zip(Xl[0::3], Xl[1::3], Xl[2::3])); ut = list(zip(Ul[0::2], Ul[1::2]))      # every corner's (x, y, z) / (u, v)
        sel = [q for q in range(g['np']) if good[q]]; pf = [ids[q // nper] for q in sel]
        out_nat.extend([(faces[i][0], faces[i][1], ct[k * q:k * q + k], ut[k * q:k * q + k]) for q, i in zip(sel, pf)]); PI.extend(pf)
        pg = array.array('d', bytes(96 * len(sel))); pa = array.array('d', bytes(64 * len(sel))); L.ro_patch(g['np'], k, ad(g['X']), ad(g['AB']), ad(good), ad(pg), ad(pa)); PG.extend(pg); PA.extend(pa)
    PATCH.clear()
    if len(PI):
        m = len(PI); hk = FR.corner_keys_buf(_arr('<f8', (m, 4, 3), PG)); cn = FR.canon_keys_buf(hk); cb = bytes(memoryview(cn.buf)[:cn.nbytes])
        PATCH['ab'] = PA; PATCH['id'] = PI; PATCH['corner'] = bytes(memoryview(hk.buf)[:hk.nbytes]); PATCH['row'] = {cb[32 * r:32 * r + 32]: r for r in range(m)}
    out = [fc for i, fc in enumerate(faces) if not isnat[i]] + out_nat; stat['polygons_after'] = len(out_nat)
    log('       %s: %s' % (what, stat))
    return out, stat
