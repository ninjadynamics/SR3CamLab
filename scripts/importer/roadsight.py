"""WHICH SIDE OF A POLYGON DOES THE PLAYER SEE?  (user, 2026-10-08: "can we flip all the polys the right way with a script?" - "proper")

lightside.py asks which side of a polygon is open to the sky. That is not the question: a polygon is lit, and drawn, for the side that is
LOOKED AT, and in a racing game the eyes are on the road. So: viewpoints all along the road (every few metres, left and right of the
middle, at car and chase-camera height), and from each of them rays to the polygons within sight (rays.c - tens of millions of rays, a
couple of seconds). The side a polygon is reached on is its seen side:
    reached on its winding side only   -> stays, and counts as SURE (plain material key)
    reached on the other side only     -> turned round (corner order reversed), SURE
    reached on both sides              -> drawn two-sided and lit as its brighter side (material key '|4', as lightside does)
    never reached from the road        -> left as lightside decided
Only opaque polygons are judged and only they block the view (cut-outs are mostly holes).  A drone camera off the road can still find a
polygon turned away: 'right' here means right from where the cars are."""
import time
import numpy as np

STEP = 4; SIDE = (-3.5, 3.5); HEIGHT = (1.1, 3.2); REACH = 170.0; MIN_HITS = 2; RATIO = 8.0

def orient(lists, rd, log=print):
    """lists = (faces, sky, extra) -> the same three lists, judged together
    (fastlm.c casts the rays, one polygon after the other on every core: 2 s where the arrays of _old_orient below took 20; 2026-10-08.
    _old_orient stays as the reference: SR3_FASTGEO=0 / SR3_FASTLM=0 selects it, SR3_FASTGEO_CHECK=1 runs both and counts differences.)"""
    import fastlm, fastgeo
    if not fastlm.ON: return _old_orient(lists, rd, log)
    t0 = time.time(); allf = [fc for L in lists for fc in L]; n = len(allf)
    def judged(fc):
        m = str(fc[0]); return not m.split('|')[0].endswith('_t') and str(fc[1]) != 'sea' and not str(fc[1]).startswith('gate_') and len(fc[2]) in (3, 4) and ('|' not in m or m.endswith('|4'))
    opaque = np.array([not str(fc[0]).split('|')[0].endswith('_t') and len(fc[2]) in (3, 4) for fc in allf], bool); J = np.array([judged(fc) for fc in allf], bool)
    try: X, off, lens = fastgeo.pack(allf)                             # the corners of all polygons in one array (the loop of _old_orient, per polygon)
    except (ValueError, TypeError): log('       (roadsight.py: a polygon whose corners are not x, y, z - the numpy code runs instead of fastlm.c)'); return _old_orient(lists, rd, log)
    Q = np.zeros((n, 4, 3)); tri = opaque & (lens == 3); op = np.nonzero(opaque)[0]
    for k in range(3): Q[op, k] = X[off[op] + k]
    q4 = np.nonzero(opaque & (lens == 4))[0]; Q[q4, 3] = X[off[q4] + 3]
    Q[tri, 3] = Q[tri, 2]; T = np.concatenate([Q[opaque][:, [0, 1, 3]], Q[opaque & ~tri][:, [1, 2, 3]]]); sc = fastlm.Scene(T)
    V = np.asarray(rd['V'], float); hw = rd['hw']; C = V[::STEP, hw]; nx = np.roll(C, -1, axis=0) - np.roll(C, 1, axis=0); nx[:, 1] = 0; nx /= np.maximum(np.linalg.norm(nx, axis=1), 1e-9)[:, None]; sd = np.stack([nx[:, 2], np.zeros(len(nx)), -nx[:, 0]], 1)
    E = np.concatenate([C + sd * s + np.array([0.0, h, 0.0]) for s in SIDE for h in HEIGHT]); per = len(SIDE) * len(HEIGHT)
    idx = np.nonzero(J)[0]; Pj = Q[idx]; nrm = np.cross(Pj, np.roll(Pj, -1, axis=1)).sum(1); ln = np.linalg.norm(nrm, axis=1); nrm /= np.maximum(ln, 1e-12)[:, None]
    S1 = (Pj[:, 0] + Pj[:, 1] + Pj[:, 3]) / 3.0; S2 = np.where(tri[idx][:, None], S1, (Pj[:, 1] + Pj[:, 2] + Pj[:, 3]) / 3.0); cen = Pj.mean(1)
    front, back, nrays = fastlm.roadsight(sc, cen, S1, S2, nrm, C, E, per, REACH)
    res = _decide(lists, allf, idx, front, back, len(E), nrays, t0, log)
    if fastlm.CHECK: old = _old_orient(lists, rd, lambda s: None); fastlm.note('roadsight.orient', old == res, sum(1 for a, b in zip([fc for L in old for fc in L], [fc for L in res for fc in L]) if a != b)); return old
    return res

def _decide(lists, allf, idx, front, back, nview, nrays, t0, log):
    """the rule of _old_orient on the counts front / back (the same lines)"""
    F = front >= MIN_HITS; B = back >= MIN_HITS; onlyf = F & (~B | (front >= RATIO * back)); onlyb = B & (~F | (back >= RATIO * front)); both = F & B & ~onlyf & ~onlyb
    out = list(allf); st = dict(judged=int(len(idx)), seen_on_winding_side=int(onlyf.sum()), turned_round=int(onlyb.sum()), seen_from_both_sides=int(both.sum()), never_seen_from_the_road=int((~F & ~B).sum()))
    was_unsure = np.array([str(allf[i][0]).endswith('|4') for i in idx], bool); st['were_unsure_now_sure'] = int((was_unsure & (onlyf | onlyb)).sum()); st['were_sure_now_turned'] = int((~was_unsure & onlyb).sum())
    for k, i in enumerate(idx):
        mat, sec, P, UV = allf[i]; base = str(mat).split('|')[0]
        if onlyf[k]: out[i] = (base, sec, P, UV)
        elif onlyb[k]: out[i] = (base, sec, list(P)[::-1], list(UV)[::-1])
        elif both[k]: out[i] = (base + '|4', sec, P, UV)
    log('       which side the PLAYER sees (roadsight.py: %d viewpoints on the road, %.1f million rays, %.1f s): %s' % (nview, nrays / 1e6, time.time() - t0, st))
    res = []; a = 0
    for L in lists: res.append(out[a:a + len(L)]); a += len(L)
    return res

def _old_orient(lists, rd, log=print):                                # (the numpy original of orient: fallback and reference)
    """lists = (faces, sky, extra) -> the same three lists, judged together"""
    import rays
    t0 = time.time(); allf = [fc for L in lists for fc in L]; n = len(allf)
    def judged(fc):
        m = str(fc[0]); return not m.split('|')[0].endswith('_t') and str(fc[1]) != 'sea' and not str(fc[1]).startswith('gate_') and len(fc[2]) in (3, 4) and ('|' not in m or m.endswith('|4'))
    opaque = np.array([not str(fc[0]).split('|')[0].endswith('_t') and len(fc[2]) in (3, 4) for fc in allf], bool); J = np.array([judged(fc) for fc in allf], bool)
    Q = np.zeros((n, 4, 3)); tri = np.zeros(n, bool)
    for i, fc in enumerate(allf):
        if opaque[i]: P = fc[2]; Q[i, :len(P)] = P; tri[i] = len(P) == 3
    Q[tri, 3] = Q[tri, 2]; T = np.concatenate([Q[opaque][:, [0, 1, 3]], Q[opaque & ~tri][:, [1, 2, 3]]]); sc = rays.Scene(T)
    # viewpoints
    V = np.asarray(rd['V'], float); hw = rd['hw']; C = V[::STEP, hw]; nx = np.roll(C, -1, axis=0) - np.roll(C, 1, axis=0); nx[:, 1] = 0; nx /= np.maximum(np.linalg.norm(nx, axis=1), 1e-9)[:, None]; sd = np.stack([nx[:, 2], np.zeros(len(nx)), -nx[:, 0]], 1)
    E = np.concatenate([C + sd * s + np.array([0.0, h, 0.0]) for s in SIDE for h in HEIGHT]); nrow = len(C); per = len(SIDE) * len(HEIGHT)
    idx = np.nonzero(J)[0]; Pj = Q[idx]; nrm = np.cross(Pj, np.roll(Pj, -1, axis=1)).sum(1); ln = np.linalg.norm(nrm, axis=1); nrm /= np.maximum(ln, 1e-12)[:, None]
    S1 = (Pj[:, 0] + Pj[:, 1] + Pj[:, 3]) / 3.0; S2 = np.where(tri[idx][:, None], S1, (Pj[:, 1] + Pj[:, 2] + Pj[:, 3]) / 3.0); cen = Pj.mean(1)
    front = np.zeros(len(idx), np.int32); back = np.zeros(len(idx), np.int32); nrays = 0
    for s in range(0, len(idx), 1500):
        c = cen[s:s + 1500]; d = np.sqrt(((c[:, None, [0, 2]] - C[None, :, [0, 2]]) ** 2).sum(2)); pi, ri = np.nonzero(d < REACH)
        if not len(pi): continue
        pi = np.repeat(pi, per); ri = (ri[:, None] + nrow * np.arange(per)[None]).ravel()
        for smp in (S1, S2):
            q = smp[s:s + 1500][pi]; e = E[ri]; v = q - e; L = np.linalg.norm(v, axis=1); dr = v / np.maximum(L, 1e-9)[:, None]; cs = -(dr * nrm[s:s + 1500][pi]).sum(1); use = (np.abs(cs) > 0.05) & (L > 0.5)
            hit = np.full(len(q), 0, np.int32)
            for a in range(0, len(q), 3000000):
                u = np.nonzero(use[a:a + 3000000])[0] + a
                if len(u): hh, tt = sc.cast(e[u], dr[u], 1e9); hit[u] = (tt >= L[u] - 0.08).astype(np.int32); nrays += len(u)
            np.add.at(front, s + pi[(hit == 1) & (cs > 0)], 1); np.add.at(back, s + pi[(hit == 1) & (cs < 0)], 1)
    F = front >= MIN_HITS; B = back >= MIN_HITS; onlyf = F & (~B | (front >= RATIO * back)); onlyb = B & (~F | (back >= RATIO * front)); both = F & B & ~onlyf & ~onlyb
    out = list(allf); st = dict(judged=int(len(idx)), seen_on_winding_side=int(onlyf.sum()), turned_round=int(onlyb.sum()), seen_from_both_sides=int(both.sum()), never_seen_from_the_road=int((~F & ~B).sum()))
    was_unsure = np.array([str(allf[i][0]).endswith('|4') for i in idx], bool); st['were_unsure_now_sure'] = int((was_unsure & (onlyf | onlyb)).sum()); st['were_sure_now_turned'] = int((~was_unsure & onlyb).sum())
    for k, i in enumerate(idx):
        mat, sec, P, UV = allf[i]; base = str(mat).split('|')[0]
        if onlyf[k]: out[i] = (base, sec, P, UV)
        elif onlyb[k]: out[i] = (base, sec, list(P)[::-1], list(UV)[::-1])
        elif both[k]: out[i] = (base + '|4', sec, P, UV)
    log('       which side the PLAYER sees (roadsight.py: %d viewpoints on the road, %.1f million rays, %.1f s): %s' % (len(E), nrays / 1e6, time.time() - t0, st))
    res = []; a = 0
    for L in lists: res.append(out[a:a + len(L)]); a += len(L)
    return res
