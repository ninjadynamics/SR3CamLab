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
polygon turned away: 'right' here means right from where the cars are.
Without numpy since 2026-10-15 (kb 31): the corners are packed by geobuf.pack, the triangles, normals and sample points made by fastlm.c
(lm_rs_prep), the viewpoints and the decision computed in plain Python, every number as numpy's code computed it; the lists that come out
are the numpy version's. _old_orient (the numpy original, the reference) still imports numpy."""
import time, math
from array import array

STEP = 4; SIDE = (-3.5, 3.5); HEIGHT = (1.1, 3.2); REACH = 170.0; MIN_HITS = 2; RATIO = 8.0

def orient(lists, rd, log=print):
    """lists = (faces, sky, extra) -> the same three lists, judged together
    (fastlm.c casts the rays, one polygon after the other on every core: 2 s where the arrays of _old_orient below took 20; 2026-10-08.
    _old_orient stays as the reference: SR3_FASTGEO=0 / SR3_FASTLM=0 selects it, SR3_FASTGEO_CHECK=1 runs both and counts differences.)"""
    import fastlm, geobuf
    if not fastlm.ON: return _old_orient(lists, rd, log)
    t0 = time.time(); allf = [fc for L in lists for fc in L]; n = len(allf)
    def judged(fc):
        m = str(fc[0]); return not m.split('|')[0].endswith('_t') and str(fc[1]) != 'sea' and not str(fc[1]).startswith('gate_') and len(fc[2]) in (3, 4) and ('|' not in m or m.endswith('|4'))
    opaque = array('B', [not str(fc[0]).split('|')[0].endswith('_t') and len(fc[2]) in (3, 4) for fc in allf]); J = array('B', [judged(fc) for fc in allf])
    try: X, off, lens = geobuf.pack(allf)                              # the corners of all polygons in one array (the loop of _old_orient, per polygon)
    except (ValueError, TypeError): log('       (roadsight.py: a polygon whose corners are not x, y, z - the numpy code runs instead of fastlm.c)'); return _old_orient(lists, rd, log)
    ntri = sum(opaque) + sum(1 for o, k in zip(opaque, lens.view()) if o and k == 4); nj = sum(J)      # T: a triangle per opaque polygon, a second per four-corner one
    T = array('d', bytes(72 * ntri)); idx = array('q', bytes(8 * nj)); cen, S1, S2, nrm = (array('d', bytes(24 * nj)) for _ in range(4))
    fastlm.lib().lm_rs_prep(n, X.ptr(), off.ptr(), lens.ptr(), *(a.buffer_info()[0] for a in (opaque, J, T, idx, cen, S1, S2, nrm)))      # (fastlm.c quotes the numpy lines)
    sc = fastlm.Scene(T, ntri)
    C, E = viewpoints(rd, STEP, SIDE, HEIGHT); per = len(SIDE) * len(HEIGHT)
    front, back, nrays = fastlm.roadsight(sc, cen, S1, S2, nrm, C, E, per, REACH)
    res = _decide(lists, allf, idx, front, back, len(E) // 3, nrays, t0, log)
    if fastlm.CHECK: old = _old_orient(lists, rd, lambda s: None); fastlm.note('roadsight.orient', old == res, sum(1 for a, b in zip([fc for L in old for fc in L], [fc for L in res for fc in L]) if a != b)); return old
    return res

def viewpoints(rd, step, side, height):
    """the viewpoints on the road: every step-th point of its middle, beside it at `side`, at `height` -> C, E (array.array of doubles;
    viewpoint k of road point r = E[r + len(C) * k]). The numpy lines (here and in seenside.py) and the same arithmetic on floats, zeros too:
        C = V[::step, hw]; nx = np.roll(C, -1, 0) - np.roll(C, 1, 0); nx[:, 1] = 0; nx /= np.maximum(np.linalg.norm(nx, axis=1), 1e-9)[:, None]
        sd = np.stack([nx[:, 2], np.zeros(len(nx)), -nx[:, 0]], 1); E = np.concatenate([C + sd * s + np.array([0.0, h, 0.0]) for s in side for h in height])"""
    V = rows(rd['V']); hw = rd['hw']; C = [tuple(V[r][hw]) for r in range(0, len(V), step)]; m = len(C); sd = []
    for r in range(m):
        a, b = C[(r + 1) % m], C[(r - 1) % m]; x, z = a[0] - b[0], a[2] - b[2]; l = math.sqrt((x * x + 0.0 * 0.0) + z * z); l = l if (l != l or l > 1e-9) else 1e-9
        sd.append((z / l, 0.0, -(x / l)))
    E = [((C[r][i] + sd[r][i] * s) + (0.0, h, 0.0)[i]) for s in side for h in height for r in range(m) for i in range(3)]
    return array('d', [v for p in C for v in p]), array('d', E)

def rows(V):
    """rd['V'] as nested lists of floats: a numpy array (any float type: np.asarray(V, float)'s values), an npyio.Arr, or lists"""
    if isinstance(V, list): return V
    if hasattr(V, 'view') and hasattr(V, 'shape') and type(V).__name__ == 'Arr':
        f = V.view().tolist(); a, b, c = V.shape; return [[f[(i * b + j) * c:(i * b + j + 1) * c] for j in range(b)] for i in range(a)]
    return memoryview(V).tolist()

def _decide(lists, allf, idx, front, back, nview, nrays, t0, log):
    """the rule of _old_orient on the counts front / back (the same rule, one polygon after the other; numpy compared front >= RATIO * back
    as floats, as Python does here)"""
    out = list(allf); c_f = c_b = c_both = c_never = c_us = c_tu = 0
    for k, i in enumerate(idx):
        f, b = front[k], back[k]; F = f >= MIN_HITS; B = b >= MIN_HITS; onlyf = F and (not B or f >= RATIO * b); onlyb = B and (not F or b >= RATIO * f); both = F and B and not onlyf and not onlyb
        mat, sec, P, UV = allf[i]; base = str(mat).split('|')[0]; unsure = str(mat).endswith('|4')
        c_f += onlyf; c_b += onlyb; c_both += both; c_never += not F and not B; c_us += unsure and (onlyf or onlyb); c_tu += (not unsure) and onlyb
        if onlyf: out[i] = (base, sec, P, UV)
        elif onlyb: out[i] = (base, sec, list(P)[::-1], list(UV)[::-1])
        elif both: out[i] = (base + '|4', sec, P, UV)
    st = dict(judged=len(idx), seen_on_winding_side=c_f, turned_round=c_b, seen_from_both_sides=c_both, never_seen_from_the_road=c_never, were_unsure_now_sure=c_us, were_sure_now_turned=c_tu)
    log('       which side the PLAYER sees (roadsight.py: %d viewpoints on the road, %.1f million rays, %.1f s): %s' % (nview, nrays / 1e6, time.time() - t0, st))
    res = []; a = 0
    for L in lists: res.append(out[a:a + len(L)]); a += len(L)
    return res

def _old_orient(lists, rd, log=print):                                # (the numpy original of orient: fallback and reference)
    """lists = (faces, sky, extra) -> the same three lists, judged together"""
    import rays, numpy as np
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
