"""seenside.py - which side of a polygon does the road see?  (course setting "seen_sides": true; baked light only)

Why (Mountain RT, 2026-10-13): the game draws an opaque 1995 polygon from both sides and a light map holds ONE light for it. The bake lit both
faces and kept the brighter, so a rock wall turned away from the sun showed the sun that falls on its hidden back: a bright wall with its own
shadow lying at its foot, dark panels where something stands behind it (owner: "that bright piece of rock next to the shadowed faces looks
suspicious as hell"). Counted near the road: 2 168 standing polygons, 19 600 m2, against 26 900 m2 honestly sunlit.

The light a polygon shows must be the light on the side that is LOOKED AT, and the eyes are on the road (roadsight.py asked the same question
for the vertex-lit builds). Viewpoints every 3 m along the road, left / middle / right, at car and chase-camera height; six points on every
opaque polygon; a point counts for the side the viewpoint stands on when nothing is in the way:
    seen on its winding side only   -> stays as it is                       the bake lights that side
    seen on the other side only     -> wound the other way (see rewind)      the bake lights that side
    seen on both sides              -> material key + '|3': add_scenery writes it once per side, single-sided, each copy with its own light map
    never seen from the road        -> material key + '|4': drawn two-sided, the bake keeps the brighter of its two faces (what every polygon got before)
Nothing here moves a corner. A four-corner polygon is drawn as two triangles along corners 0 - 2; roadsight.py and lightside.py reversed the
corner list, which cuts a twisted polygon along its other diagonal - another surface (37% of Mountain's are twisted). rewind() keeps the diagonal.

    faces, sky, extra = seenside.orient((faces, sky, extra), rd, skip=BC.PAIRS, log=log)"""
import time, os, hashlib
import numpy as np

STEP = 3; SIDE = (-3.5, 0.0, 3.5); HEIGHT = (1.1, 3.2); REACH = 220.0; MIN_HITS = 2; RATIO = 8.0
# OPEN SIDES (course setting seen_open, default on since 2026-10-14; owner: "fix the faces"): the road is not the only place a side is looked at from - a
# free camera sees the backs of cliff cards and the far sides of rock walls, and a polygon never seen from the road showed the brighter of its two faces'
# light (the sunlit far side, with the shadows of the fence posts on it, in a shaded wall). A side is OPEN when at least OPEN_MIN of the rays it sends
# over its half space (24 directions from each of the six points the road test uses) reach the sky; a side buried in rock or turned to the ground under
# a terrain sheet is not. Then: both sides open -> written once per side ('|3'); only the side the road does not see open -> wound round when the road
# sees neither ... i.e. every side that can be seen from anywhere open carries its own light.
OPEN_MIN = 0.06
_HEMI = np.array([(np.sqrt((i + 0.5) / 24) * np.cos(i * 2.399963), np.sqrt((i + 0.5) / 24) * np.sin(i * 2.399963), np.sqrt(max(0.0, 1 - (i + 0.5) / 24))) for i in range(24)])

def _open_sides(sc, pts, nrm, lift=0.05):
    """share of each polygon's rays that reach the sky, for its winding side and for its other side (pts: points on the polygons, nrm: unit normals)"""
    ax = np.where((np.abs(nrm[:, 1]) < 0.9)[:, None], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]); t = np.cross(nrm, ax); t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]; b = np.cross(nrm, t)
    res = []
    for sgn in (1.0, -1.0):
        n_ = nrm * sgn; esc = np.zeros(len(nrm)); m = 0
        for P in pts:
            o = np.ascontiguousarray(P + n_ * lift)
            for h in _HEMI:
                d = h[0] * t + h[1] * b + h[2] * n_; hit, _, _ = sc.cast(o, np.ascontiguousarray(d), 4000.0, how=3); esc += (hit < 0) & (d[:, 1] > 0.02); m += 1
        res.append(esc / m)
    return res[0], res[1]

def rewind(P, UV):
    """the other winding of the SAME surface: corners 0 and 2 (the diagonal the game cuts along) stay, 1 and 3 change places"""
    P = list(P); UV = list(UV)
    if len(P) >= 4 and tuple(P[2]) != tuple(P[3]): return [P[0], P[3], P[2], P[1]], [UV[0], UV[3], UV[2], UV[1]]
    return [P[0], P[2], P[1]], [UV[0], UV[2], UV[1]]

def orient(lists, rd, skip=(), also=(), single='~s', log=print, keep=None, read=None, open_=False):
    # keep = a file to write what was found to (the collecting build) ; read = that file, to take over instead of casting the rays again (the final
    # build: the two must agree polygon by polygon, and at R4 the rays are 28 s). Taken over only when the judged polygons are the very same.
    """also = cut-out tiles that take baked light (course setting lm_cutouts: a building drawn with cut-out pictures). They are not judged: each
    is written once per side, both copies single-sided (section mark `single`, as the tree boards' front / back pairs), so its outside and its
    inside each have their own light. They stand in the way of the viewpoints like walls."""
    import fastlm
    t0 = time.time(); allf = [fc for L in lists for fc in L]; n = len(allf); skip = set(skip); also = set(also)
    cutj = lambda fc: str(fc[0]) in also and len(fc[2]) in (3, 4)
    opq = lambda fc: not str(fc[0]).split('|')[0].endswith('_t') and len(fc[2]) in (3, 4)
    def judged(fc): return opq(fc) and str(fc[1]) != 'sea' and not str(fc[1]).startswith('gate_') and '|' not in str(fc[0]) and id(fc) not in skip
    opaque = np.array([(opq(fc) or cutj(fc)) and str(fc[1]) != 'sea' for fc in allf], bool); J = np.array([judged(fc) for fc in allf], bool); Q = np.zeros((n, 4, 3))      # (a listed cut-out stands in the way like a wall: without that the tower's walls were seen from inside, through the tower)
    for i in np.nonzero(opaque | J)[0]:
        P = allf[i][2]; Q[i, :len(P)] = np.asarray(P, float)[:, :3]
        if len(P) == 3: Q[i, 3] = Q[i, 2]
    tri = np.linalg.norm(Q[:, 2] - Q[:, 3], axis=1) < 1e-9
    T = np.concatenate([Q[opaque][:, [0, 1, 2]], Q[opaque & ~tri][:, [0, 2, 3]]])                                        # what stands in the way: the triangles the game draws
    V = np.asarray(rd['V'], float); hw = rd['hw']; C = V[::STEP, hw]; nx = np.roll(C, -1, axis=0) - np.roll(C, 1, axis=0); nx[:, 1] = 0; nx /= np.maximum(np.linalg.norm(nx, axis=1), 1e-9)[:, None]; sd = np.stack([nx[:, 2], np.zeros(len(nx)), -nx[:, 0]], 1)
    E = np.concatenate([C + sd * s + np.array([0.0, h, 0.0]) for s in SIDE for h in HEIGHT]); per = len(SIDE) * len(HEIGHT)
    idx = np.nonzero(J)[0]; Pj = Q[idx]; tj = tri[idx][:, None]
    nrm = np.cross(Pj[:, 1] - Pj[:, 0], Pj[:, 2] - Pj[:, 0]) + np.cross(Pj[:, 2] - Pj[:, 0], Pj[:, 3] - Pj[:, 0]); nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
    mix = lambda a, b, c, w: w * Pj[:, a] + (1 - w) / 2 * (Pj[:, b] + Pj[:, c]); cen = (Pj[:, 0] + Pj[:, 2]) / 2
    pairs = [(mix(1, 0, 2, 1 / 3), np.where(tj, mix(0, 1, 2, 1 / 3), mix(3, 0, 2, 1 / 3))),                           # the middles of the two drawn triangles
             (mix(1, 0, 2, 0.6), np.where(tj, mix(0, 1, 2, 0.6), mix(3, 0, 2, 0.6))),                               # towards corners 1 and 3
             (mix(0, 1, 2, 0.6), np.where(tj, mix(2, 0, 1, 0.6), mix(2, 0, 3, 0.6)))]                               # towards corners 0 and 2
    front = np.zeros(len(idx), np.int64); back = np.zeros(len(idx), np.int64); nrays = 0; took = ''
    fp = hashlib.sha1(np.ascontiguousarray(Pj).tobytes() + np.ascontiguousarray(T).tobytes() + np.ascontiguousarray(E).tobytes()).hexdigest()      # the judged polygons, what stands in the way, the viewpoints
    if read and os.path.exists(read):
        Z = np.load(read)
        if str(Z['fp']) == fp and len(Z['front']) == len(idx): front = Z['front'].astype(np.int64); back = Z['back'].astype(np.int64); nrays = int(Z['nrays']); took = ' ; taken over from the collecting build'
        else: log('       which side the road sees: the polygons of this build are NOT the ones the collecting build judged (%s): judged again - its light-map table may not fit' % read)
    if not took:
        sc = fastlm.Scene(T)
        for S1, S2 in pairs:
            f_, b_, r_ = fastlm.roadsight(sc, cen, np.ascontiguousarray(S1), np.ascontiguousarray(S2), nrm, C, E, per, REACH); front += f_; back += b_; nrays += r_
        if keep: np.savez(keep, fp=fp, front=front, back=back, nrays=nrays)
    F = front >= MIN_HITS; B = back >= MIN_HITS; onlyf = F & (~B | (front >= RATIO * back)); onlyb = B & (~F | (back >= RATIO * front)); both = F & B & ~onlyf & ~onlyb; none = ~F & ~B
    if open_:                                                          # (open sides, owner 2026-10-14) a side the road does not see but that faces open air gets its own light too
        fo_, bo_ = None, None
        if read and os.path.exists(read):
            Z = np.load(read)
            if 'fopen' in Z.files and str(Z['fp']) == fp and len(Z['fopen']) == len(idx): fo_, bo_ = Z['fopen'], Z['bopen']
        if fo_ is None:
            fo_, bo_ = _open_sides(fastlm.Scene(T) if took else sc, [p for pr in pairs for p in pr], nrm)
            if keep: Z = dict(np.load(keep)); Z.update(fopen=fo_, bopen=bo_); np.savez(keep, **Z)
        fo = fo_ >= OPEN_MIN; bo = bo_ >= OPEN_MIN; rest = ~onlyf & ~onlyb & ~both
        both2 = both | (onlyf & bo) | (onlyb & fo) | (rest & fo & bo); onlyf2 = (onlyf & ~bo) | (rest & fo & ~bo); onlyb2 = (onlyb & ~fo) | (rest & bo & ~fo)
        log('       open sides (seenside.py, %d rays a side, open = at least %.0f%% of them reach the sky): front open %d, back open %d ; written once per side %d -> %d ; lit on their winding side %d -> %d ; wound round %d -> %d ; neither side open %d'
            % (len(pairs) * 2 * len(_HEMI), 100 * OPEN_MIN, int(fo.sum()), int(bo.sum()), int(both.sum()), int(both2.sum()), int(onlyf.sum()), int(onlyf2.sum()), int(onlyb.sum()), int(onlyb2.sum()), int((rest & ~fo & ~bo).sum())))
        both, onlyf, onlyb = both2, onlyf2, onlyb2
    out = list(allf); area = 0.5 * (np.linalg.norm(np.cross(Pj[:, 1] - Pj[:, 0], Pj[:, 2] - Pj[:, 0]), axis=1) + np.linalg.norm(np.cross(Pj[:, 2] - Pj[:, 0], Pj[:, 3] - Pj[:, 0]), axis=1))
    for k, i in enumerate(idx.tolist()):
        mat, sec, P, UV = allf[i][:4]
        if onlyb[k]: P2, U2 = rewind(P, UV); out[i] = (mat, sec, P2, U2) + tuple(allf[i][4:])
        elif both[k]: out[i] = (str(mat) + '|3', sec, P, UV) + tuple(allf[i][4:])
        elif not onlyf[k]: out[i] = (str(mat) + '|4', sec, P, UV) + tuple(allf[i][4:])
    log('       which side the road sees (seenside.py: %d viewpoints, %.1f million rays, %.1f s%s): %d polygons judged ;winding side %d (%.0f m2) ; other side, wound round %d (%.0f m2) ; both sides, written once per side %d (%.0f m2) ; never seen, brighter face kept %d (%.0f m2)'
        % (len(E), nrays / 1e6, time.time() - t0, took, len(idx), int(onlyf.sum()), area[onlyf].sum(), int(onlyb.sum()), area[onlyb].sum(), int(both.sum()), area[both].sum(), int(none.sum() + (~onlyf & ~onlyb & ~both & ~none).sum()), area[~onlyf & ~onlyb & ~both].sum()))
    more = []
    for i, fc in enumerate(allf):
        if cutj(fc) and '|' not in str(fc[0]) and str(fc[1]) != 'sea' and not str(fc[1]).startswith('gate_') and not str(fc[1]).endswith(single):
            mat, sec, P, UV = fc[:4]; P2, U2 = rewind(P, UV); out[i] = (mat, str(sec) + single, P, UV) + tuple(fc[4:]); more.append((mat, str(sec) + single, P2, U2) + tuple(fc[4:]))
    if more: log('       cut-out polygons that take baked light (lm_cutouts): %d written once per side, single-sided' % len(more))
    res = []; a = 0
    for L in lists: res.append(out[a:a + len(L)]); a += len(L)
    res[-1] = list(res[-1]) + more
    return res
