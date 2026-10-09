"""Which side of every opaque polygon is seen? Answered by ray casting, not by rules.

The 1995 polygons do not say which of their sides shows (the importer draws them two-sided), but lighting by the sun needs the
normal of the side that is LOOKED AT. From the middle of every polygon a fan of 32 rays leaves each side (bl_sides.py, Blender's
BVH tree, headless); a ray that hits nothing within 600 m has escaped to the open:
    open on one side only   -> that is the seen side: the polygon is wound that way (one copy, drawn two-sided as before)
    open on both sides      -> a sheet seen from both (the 1995 cliff curtains, free-standing walls): material key + '|3',
                               add_scenery writes it once per side, each copy single-sided with its own normal
    open on neither         -> enclosed: left as it is
"Open" = at least OPEN of the 32 rays escape. Earlier attempts and why they went: 'faces the road' (wrong for rock seen from its far
side), 'the lower ground is the open side' (the hand fill lies lower inside every house), writing EVERY polygon twice (right, but
twice the scenery; user, 2026-10-08: "brute-forcish and dumb ... fix things properly").

    faces, info = lightside.orient(faces)        # importer faces (material, section, corners, uv); cut-outs and the sea pass through"""
import os, subprocess, tempfile
import numpy as np
BLENDER = r'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
OPEN = 3 / 32.0; FREE_MIN = 1.0; FREE_RATIO = 2.5; SURE_RATIO = 4.0      # 'sure' = the open side has at least 4 times the escaping rays of the other (it used to demand NONE on the other side: one stray ray of 32 made the ground floor of the church 'not sure', and it was lit as its brighter side while the same wall above it was in shade; user, 2026-10-08)

def _scores(V, F, ACT):
    """what bl_sides.py computed through Blender (the same fans, the same numbers), cast by rays.c on every core: for every active polygon
    the share of 32 rays that escape from its winding side and from the other, and the mean free path (capped at 100 m) of the two fans.
    Blender took 150 .. 200 s for the 440 000 polygons of a build with baked light; this takes about two."""
    import rays, math
    V = np.asarray(V, np.float64); F = np.asarray(F, np.int64); Q = V[F]; tri = F[:, 2] == F[:, 3]
    T = np.concatenate([Q[:, [0, 1, 3]], Q[~tri][:, [1, 2, 3]]]); sc = rays.Scene(T); K = 32; CAP = 100.0; H = []      # a four-corner polygon is two triangles along corners 1 - 3: that is how the game draws it (meshgen.quads_to_strip) and how Blender split it; along 0 - 2, 8 500 of 49 000 warped polygons scored differently
    for k in range(K):
        u = (k + 0.5) / K; r = math.sqrt(u) * 0.985; a = k * 2.399963229728653; H.append((r * math.cos(a), r * math.sin(a), math.sqrt(max(1.0 - r * r, 0.0))))
    H = np.array(H); out = np.zeros((len(F), 4), np.float32); act = np.nonzero(ACT)[0]
    for s0 in range(0, len(act), 40000):
        ii = act[s0:s0 + 40000]; P = Q[ii]; n = np.cross(P, np.roll(P, -1, axis=1)).sum(1); ln = np.linalg.norm(n, axis=1); ok = ln > 1e-9
        n = n / np.maximum(ln, 1e-12)[:, None]; t3 = tri[ii]; c = np.where(t3[:, None], P[:, :3].sum(1) / 3.0, P.sum(1) / 4.0)
        ax = np.where((np.abs(n[:, 1]) < 0.9)[:, None], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]); t = np.cross(n, ax); t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]; b = np.cross(n, t)
        for s, sg in enumerate((1.0, -1.0)):
            d = t[:, None, :] * H[None, :, 0, None] + b[:, None, :] * H[None, :, 1, None] + n[:, None, :] * (sg * H[None, :, 2, None]); o = np.repeat(c + sg * n * 0.06, K, axis=0)
            hit, dist = sc.cast(o, d.reshape(-1, 3), 600.0); hit = hit.reshape(-1, K); dist = dist.reshape(-1, K)
            out[ii, s] = np.where(ok, (hit < 0).mean(1), 0.0); out[ii, 2 + s] = np.where(ok, np.where(hit < 0, CAP, np.minimum(dist, CAP)).mean(1), 0.0)
    return out

def orient(faces, log=print, tag=''):
    """(fastside.orient makes the decisions of _old_orient below on whole arrays: 5 s where the loops took 20 .. 50; profile 2026-10-08.
    _old_orient stays as the reference and the fallback, and holds the comments that say why each rule is there.)"""
    import sys, fastgeo
    if fastgeo.ON:
        import fastside
        r = fastside.orient(faces, log, tag, sys.modules[__name__])
        if r is not None:
            if fastgeo.CHECK: sc_ = orient.scores; o = _old_orient(faces, lambda s: None, tag); fastgeo.note('lightside.orient', o[1] == r[1] and o[0] == r[0], (o[1], r[1], sum(1 for a, b in zip(o[0], r[0]) if a != b))); orient.scores = sc_
            return r
    return _old_orient(faces, log, tag)
def _old_orient(faces, log=print, tag=''):
    here = os.path.dirname(os.path.abspath(__file__)); tmp = os.path.join(os.path.dirname(here), 'tmp'); os.makedirs(tmp, exist_ok=True)
    fin = os.path.join(tmp, 'sides_in_%s.npz' % (tag or os.getpid())); fout = os.path.join(tmp, 'sides_out_%s.npy' % (tag or os.getpid()))
    V = []; F = []; ACT = []
    for mat, sec, P, UV in faces:
        m0 = str(mat).split('|')[0]; cut = m0.endswith('_t'); k = len(V); n = min(len(P), 4)
        V += [tuple(map(float, p)) for p in P[:n]]; F.append([k, k + 1, k + 2, k + 3 if n == 4 else k + 2])
        ACT.append((not cut) and sec != 'sea' and not str(sec).startswith('gate_'))          # cut-outs are tested by nobody and block nobody's view (they are mostly holes) ...
    F = np.array(F, np.int32); ACT = np.array(ACT, bool); V = np.array(V, np.float64)
    blockers = np.array([not str(fc[0]).split('|')[0].endswith('_t') for fc in faces], bool)
    keep = np.nonzero(blockers)[0]                                                              # ... so only opaque polygons go into the tree
    k0 = len(V); lo = float(V[:, 1].min()) - 5.0; V = np.vstack([V, [(-5000.0, lo, -5000.0), (5000.0, lo, -5000.0), (5000.0, lo, 5000.0), (-5000.0, lo, 5000.0)]])      # a floor under everything: nothing escapes DOWNWARDS (the sea sheet is cut away under the land)
    orient.scores = None; res_ = _scores(V, np.vstack([F[keep], [[k0, k0 + 1, k0 + 2, k0 + 3]]]), np.r_[ACT[keep], False])[:-1]      # (rays.c; it used to go through Blender: bl_sides.py)
    sc = np.zeros((len(faces), 4), np.float32); sc[keep] = res_; orient.scores = sc
    nfol = [0]
    # Decision per polygon, from two numbers per side: the share of its 32 rays that ESCAPE to the open, and their mean free path.
    #   escape on one side only (at least OPEN of the rays)  -> that side is seen
    #   escape on both sides                                 -> seen from both: written once per side
    #   hardly any escape on either side (under an overhang, in a narrow gap):
    #       the side with MORE escaping rays; none at all -> the side with the clearly longer free path (FREE_MIN m and FREE_RATIO times the other)
    #       neither -> ENCLOSED (a polygon lying against another): it takes the side of the polygons it shares an edge with
    # The escape share comes first because the scenery is thin shells: under the hillside and inside every house and rock there is a large
    # EMPTY space, so the free path alone calls half the track "seen from both sides" (tried). The free path only settles what the sky cannot.
    # (First version: escape share alone; a polygon that reached the sky with 2 rays of 32 counted as enclosed and kept its 1995 winding,
    #  which may look into the rock: a dark rectangle in a sunlit cliff, user shot 103206, 2026-10-08.)
    def wn_(P):
        A = np.asarray(P, float); B = np.roll(A, -1, axis=0); return ((A[:, [1, 2, 0]] - B[:, [1, 2, 0]]) * (A[:, [2, 0, 1]] + B[:, [2, 0, 1]])).sum(0)
    sure = set(); state = {}; n1 = n2 = nb = n0 = 0; how = {'sky': 0, 'lying, looks up': 0, 'few rays': 0, 'free path': 0}
    for k, fc in enumerate(faces):
        if not ACT[k]: continue
        ea, eb, fa, fb = (float(x) for x in sc[k]); A_, B_ = ea >= OPEN, eb >= OPEN
        if A_ and B_: state[k] = 'both'; how['sky'] += 1
        elif A_ or B_: state[k] = 'keep' if A_ else 'turn'; how['sky'] += 1; sure.add(k) if max(ea, eb) >= 2 * OPEN and max(ea, eb) >= SURE_RATIO * min(ea, eb) else None
        elif abs(wn_(fc[2])[1]) > 0.5 * float(np.linalg.norm(wn_(fc[2]))): state[k] = 'keep' if wn_(fc[2])[1] > 0 else 'turn'; how['lying, looks up'] += 1; sure.add(k)      # ground with no sky above it (the hillside under the 1995 ground): up, whatever lies below
        elif ea != eb: state[k] = 'keep' if ea > eb else 'turn'; how['few rays'] += 1
        elif max(fa, fb) >= FREE_MIN and max(fa, fb) >= FREE_RATIO * min(fa, fb): state[k] = 'keep' if fa > fb else 'turn'; how['free path'] += 1
        else: state[k] = 'enclosed'
    # enclosed polygons: the winding that agrees with their decided neighbours (two polygons that share an edge are wound alike when they run
    # along it in opposite directions); several rounds, so it spreads through a patch of enclosed polygons
    key = lambda p: (round(p[0], 2), round(p[1], 2), round(p[2], 2))
    def corners(k, turned): P = [key(p) for p in faces[k][2]]; return P[::-1] if turned else P
    for rnd in range(6):
        edges = {}
        for k, st in state.items():
            if st in ('keep', 'turn'):
                P = corners(k, st == 'turn')
                for q in range(len(P)): edges[(P[q], P[(q + 1) % len(P)])] = True
        ch = 0
        for k, st in list(state.items()):
            if st != 'enclosed': continue
            P = corners(k, False); same = opp = 0
            for q in range(len(P)):
                e = (P[q], P[(q + 1) % len(P)])
                if e in edges: same += 1                              # a neighbour runs the SAME way along the shared edge: this polygon is wound against it
                if (e[1], e[0]) in edges: opp += 1
            if same or opp: state[k] = 'turn' if same > opp else 'keep'; ch += 1; nfol[0] += 1
        if not ch: break
    # WALLS IN ONE PLANE AGREE. Polygons that lie in the same plane and touch (share a corner) are one wall: the side the SURE ones among
    # them are seen from (by area) is given to all of them, and all of them count as sure. (user, 2026-10-08: "I don't get why the church +
    # tower is unevenly lit when all those faces are coplanar")
    def plane_of(k):
        A = np.asarray(faces[k][2], float); n = wn_(A); ln = float(np.linalg.norm(n))
        if ln < 1e-9: return None
        n = n / ln; sgn = 1.0 if (n[np.argmax(np.abs(n))] > 0) else -1.0; n = n * sgn            # one normal per plane, whichever way the polygon is wound
        return (round(float(n[0]), 1), round(float(n[1]), 1), round(float(n[2]), 1), round(float(A.mean(0) @ n) / 0.25)), sgn, ln / 2.0
    groups = {}; pinfo = {}
    for k in state:
        pl = plane_of(k)
        if pl: pinfo[k] = pl; groups.setdefault(pl[0], []).append(k)
    nagree = 0
    for pk, ks in groups.items():
        if len(ks) < 2: continue
        par = {k: k for k in ks}
        def find(x):
            while par[x] != x: par[x] = par[par[x]]; x = par[x]
            return x
        cor = {}
        for k in ks:
            for p in faces[k][2]: cor.setdefault(key(p), []).append(k)
        for lst in cor.values():
            for q in lst[1:]: par[find(q)] = find(lst[0])
        walls = {}
        for k in ks: walls.setdefault(find(k), []).append(k)
        for wk in walls.values():
            if len(wk) < 2: continue
            vote = 0.0                                                # > 0: the wall is seen from the side of the plane's normal
            for k in wk:
                if k in sure and state[k] in ('keep', 'turn'):
                    side = pinfo[k][1] * (1.0 if state[k] == 'keep' else -1.0); vote += side * pinfo[k][2]
            if vote == 0.0: continue
            for k in wk:
                want = 'keep' if (pinfo[k][1] > 0) == (vote > 0) else 'turn'
                if state[k] != want or k not in sure: nagree += 1
                state[k] = want; sure.add(k)
    out = []
    for k, fc in enumerate(faces):
        st = state.get(k)
        if st is None: out.append(fc); continue
        mat, sec, P, UV = fc
        k4 = str(mat).split('|')[0] + '|4'                              # '|4' = which side is seen is NOT certain: add_scenery draws it two-sided, faces_to_mesh lights it as the brighter of its sides
        if st == 'both': out.append((k4, sec, P, UV)); nb += 1
        elif st == 'turn': out.append((mat if k in sure else k4, sec, list(P)[::-1], list(UV)[::-1])); n2 += 1
        elif st == 'keep': out.append((mat if k in sure else k4, sec, P, UV)); n1 += 1
        else: out.append((k4, sec, list(P)[::-1], list(UV)[::-1]) if wn_(P)[1] < 0 else (k4, sec, P, UV)); n0 += 1
    info = dict(tested=int(ACT.sum()), seen_from_winding_side=n1, turned_round=n2, seen_from_both_sides=nb, enclosed_left=n0, enclosed_set_by_their_neighbours=nfol[0], decided_by=how, set_by_the_wall_they_belong_to=nagree, sure=len(sure), not_sure_lit_as_their_brighter_side=int(ACT.sum()) - len(sure))
    log('       which side is seen (ray casting, 32 rays a side): %s' % info)
    return out, info
