"""fastside.py - lightside.orient on whole arrays (the decisions of lightside._old_orient, rule for rule; that function is the reference
and the text that says WHY each rule is there).

    out, info = fastside.orient(faces, log, tag, lightside)        None = this code cannot take the input (lightside falls back)

What the loops of the original became:
  corners -> one array (fastgeo.pack); the corner keys round(x, 2) -> whole numbers per corner (fastgeo.round_keys), each key a vertex number
  the decision per polygon -> comparisons on arrays, in the order of the original's if / elif chain
  enclosed polygons taking the winding of their neighbours -> directed edges as numbers (from * count + to), looked up in a sorted array
  walls in one plane -> polygons that share a vertex within one plane key are one group (fastgeo.components), the vote a sum per group
The original's np.linalg.norm / @ on three numbers go through BLAS, whose last bit depends on where in memory the numbers lie (measured: 30 %
of the dot products of two 3-vectors change in the last bit with the alignment); for freshly made arrays, which is what the original hands
it, the order is (x*x + z*z) + y*y, and that order is used here (fastbuild.norm3)."""
import os
import numpy as np
import fastgeo

NONE, KEEP, TURN, BOTH, ENC = 0, 1, 2, 3, 4

def _isin(q, E):
    if not len(E) or not len(q): return np.zeros(len(q), bool)
    i = np.searchsorted(E, q); i[i >= len(E)] = len(E) - 1; return E[i] == q

def orient(faces, log, tag, LS):
    n = len(faces)
    if not n: return None
    here = os.path.dirname(os.path.abspath(__file__)); tmp = os.path.join(os.path.dirname(here), 'tmp'); os.makedirs(tmp, exist_ok=True)
    X, off, lens = fastgeo.pack(faces); tot = len(X); G = fastgeo.prep(faces, packed=(X, off, lens))
    if int(lens.min()) < 3: return None                                 # (the original reads corners that are not there: let it)
    cut = np.fromiter((str(fc[0]).split('|')[0].endswith('_t') for fc in faces), bool, n)
    ACT = ~cut & ~np.fromiter((fc[1] == 'sea' or str(fc[1]).startswith('gate_') for fc in faces), bool, n)
    fcorner = np.repeat(np.arange(n), lens); loc = np.arange(tot) - off[:-1][fcorner]
    # ---- the fans (lightside._scores, rays.c): at most four corners a polygon, opaque polygons only, a floor under everything
    n4 = np.minimum(lens, 4); V = X[loc < 4]; vo = np.cumsum(n4) - n4; F = np.stack([vo, vo + 1, vo + 2, np.where(n4 == 4, vo + 3, vo + 2)], 1).astype(np.int32)
    keep = np.nonzero(~cut)[0]; k0 = len(V); lo = float(V[:, 1].min()) - 5.0; V = np.vstack([V, [(-5000.0, lo, -5000.0), (5000.0, lo, -5000.0), (5000.0, lo, 5000.0), (-5000.0, lo, 5000.0)]])
    LS.orient.scores = None; res_ = LS._scores(V, np.vstack([F[keep], [[k0, k0 + 1, k0 + 2, k0 + 3]]]), np.r_[ACT[keep], False])[:-1]
    sc = np.zeros((n, 4), np.float32); sc[keep] = res_; LS.orient.scores = sc
    # ---- wn_ of every polygon (all its corners, summed corner by corner as numpy sums the rows)
    wn = np.zeros((n, 3))
    for k, ii in fastgeo.by_len(lens):
        P = X[off[ii][:, None] + np.arange(k)[None, :]]; B = np.roll(P, -1, axis=1); T = (P[:, :, [1, 2, 0]] - B[:, :, [1, 2, 0]]) * (P[:, :, [2, 0, 1]] + B[:, :, [2, 0, 1]]); w = T[:, 0].copy()
        for i in range(1, k): w = w + T[:, i]
        wn[ii] = w
    ln = np.sqrt((wn[:, 0] * wn[:, 0] + wn[:, 2] * wn[:, 2]) + wn[:, 1] * wn[:, 1])      # (x, z, then y: the order numpy's norm / @ add three numbers in, see fastbuild.norm3)
    # ---- the decision per polygon
    OPEN, FREE_MIN, FREE_RATIO, SURE_RATIO = LS.OPEN, LS.FREE_MIN, LS.FREE_RATIO, LS.SURE_RATIO
    s64 = sc.astype(np.float64); ea, eb, fa, fb = s64[:, 0], s64[:, 1], s64[:, 2], s64[:, 3]; A_ = ea >= OPEN; B_ = eb >= OPEN; mx = np.maximum(ea, eb); mn = np.minimum(ea, eb); fx = np.maximum(fa, fb); fn = np.minimum(fa, fb)
    st = np.zeros(n, np.int8); sure = np.zeros(n, bool); left = ACT.copy(); how = {}
    c = left & A_ & B_; st[c] = BOTH; left &= ~c; n_sky = int(c.sum())
    c = left & (A_ | B_); st[c] = np.where(A_[c], KEEP, TURN); sure |= c & (mx >= 2 * OPEN) & (mx >= SURE_RATIO * mn); left &= ~c; how['sky'] = n_sky + int(c.sum())
    c = left & (np.abs(wn[:, 1]) > 0.5 * ln); st[c] = np.where(wn[c, 1] > 0, KEEP, TURN); sure |= c; left &= ~c; how['lying, looks up'] = int(c.sum())
    c = left & (ea != eb); st[c] = np.where(ea[c] > eb[c], KEEP, TURN); left &= ~c; how['few rays'] = int(c.sum())
    c = left & (fx >= FREE_MIN) & (fx >= FREE_RATIO * fn); st[c] = np.where(fa[c] > fb[c], KEEP, TURN); left &= ~c; how['free path'] = int(c.sum())
    st[left] = ENC
    # ---- corner keys -> vertex numbers; directed edges as numbers
    N = fastgeo.round_keys(X, lambda r, a: faces[fcorner[r]][2][loc[r]][a], 2)
    if int(np.abs(N).max()) >= (1 << 20): return None
    code = ((N[:, 0] + (1 << 20)) << 42) | ((N[:, 1] + (1 << 20)) << 21) | (N[:, 2] + (1 << 20)); uq, vid = np.unique(code, return_inverse=True); NV = len(uq)
    nxt = np.arange(tot) + 1; last = off[1:] - 1; nxt[last] = off[:-1]; va = vid; vb = vid[nxt]; fwd = va * NV + vb; bwd = vb * NV + va
    # ---- enclosed polygons: the winding that agrees with their decided neighbours (edge table of the round's start, as in the original)
    nfol = 0
    for rnd in range(6):
        stc = st[fcorner]; E = np.unique(np.concatenate([fwd[stc == KEEP], bwd[stc == TURN]])); m = stc == ENC
        if not m.any(): break
        fe = fcorner[m]; same = np.bincount(fe, weights=_isin(fwd[m], E), minlength=n); opp = np.bincount(fe, weights=_isin(bwd[m], E), minlength=n)
        upd = (st == ENC) & ((same > 0) | (opp > 0))
        if not upd.any(): break
        st[upd] = np.where(same[upd] > opp[upd], TURN, KEEP); nfol += int(upd.sum())
    # ---- walls in one plane agree
    has = (st != NONE) & ~(ln < 1e-9); ii = np.nonzero(has)[0]; nagree = 0
    if len(ii):
        nn = wn[ii] / ln[ii][:, None]; am = np.argmax(np.abs(nn), axis=1); sgn = np.where(nn[np.arange(len(ii)), am] > 0, 1.0, -1.0); nn = nn * sgn[:, None]
        cen = G.cen[ii]; dist = ((cen[:, 0] * nn[:, 0] + cen[:, 2] * nn[:, 2]) + cen[:, 1] * nn[:, 1]) / 0.25; area = ln[ii] / 2.0
        gid = {}; gl = [gid.setdefault((round(a, 1), round(b, 1), round(c_, 1), round(d)), len(gid)) for a, b, c_, d in zip(nn[:, 0].tolist(), nn[:, 1].tolist(), nn[:, 2].tolist(), dist.tolist())]
        gof = np.full(n, -1, np.int64); gof[ii] = gl; cm = has[fcorner]; nodes = np.unique(gof[fcorner[cm]] * NV + vid[cm], return_inverse=True)[1]
        pos = np.full(n, -1, np.int64); pos[ii] = np.arange(len(ii)); label = fastgeo.components(len(ii), pos[fcorner[cm]], nodes)          # per polygon of ii: the smallest member of its wall
        size = np.bincount(label, minlength=len(ii)); sti = st[ii]; sui = sure[ii]; dec = sui & ((sti == KEEP) | (sti == TURN))
        vote = np.bincount(label[dec], weights=(sgn * np.where(sti == KEEP, 1.0, -1.0) * area)[dec], minlength=len(ii))      # (added polygon by polygon in their order, as the original does)
        w = (size[label] >= 2) & (vote[label] != 0.0); want = np.where((sgn > 0) == (vote[label] > 0), KEEP, TURN).astype(np.int8)
        nagree = int((w & ((sti != want) | ~sui)).sum()); st[ii[w]] = want[w]; sure[ii[w]] = True
    # ---- the faces
    out = []; n1 = n2 = nb = n0 = 0; stl = st.tolist(); sul = sure.tolist(); dn = (wn[:, 1] < 0).tolist()
    for k, fc in enumerate(faces):
        s = stl[k]
        if not s: out.append(fc); continue
        mat, sec, P, UV = fc; k4 = str(mat).split('|')[0] + '|4'
        if s == BOTH: out.append((k4, sec, P, UV)); nb += 1
        elif s == TURN: out.append((mat if sul[k] else k4, sec, list(P)[::-1], list(UV)[::-1])); n2 += 1
        elif s == KEEP: out.append((mat if sul[k] else k4, sec, P, UV)); n1 += 1
        else: out.append((k4, sec, list(P)[::-1], list(UV)[::-1]) if dn[k] else (k4, sec, P, UV)); n0 += 1
    nact = int(ACT.sum()); nsure = int(sure.sum())
    info = dict(tested=nact, seen_from_winding_side=n1, turned_round=n2, seen_from_both_sides=nb, enclosed_left=n0, enclosed_set_by_their_neighbours=nfol, decided_by=how, set_by_the_wall_they_belong_to=nagree, sure=nsure, not_sure_lit_as_their_brighter_side=nact - nsure)
    log('       which side is seen (ray casting, 32 rays a side): %s' % info)
    return out, info
