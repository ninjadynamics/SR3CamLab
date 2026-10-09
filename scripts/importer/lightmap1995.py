"""REAL LIGHT MAPS for a classic course (user, 2026-10-08: "go for it").

What the game does with a light map was measured with build LM-TEST (four squares: white, grey, black, red): the picture MULTIPLIES the
finished colour of the polygon - black gives black, red gives red - and every imported material already has the switch on (with a white
picture and one texel for all vertices). So light can be baked per TEXEL, in colour, instead of per vertex:

    1. course setting "lm_collect": <file>    the build notes every lit polygon as the meshes are written, and the scene (bake1995.save_scene)
    2. python lightmap1995.py <file> [shadows|rt] [strength]     every polygon gets a rectangle of texels on a page (its own grid, corner to
                                              corner, so two polygons that share an edge are lit alike along it); rays.c lights the texels
    3. course setting "lm_table": <file>      the build gives the vertices their place on the page (uv1) and the materials their page

A texel holds what the polygon rule's brightness must be multiplied by: 1 in the open, less where the sun is hidden ('shadows'), and with
'rt' less again where little sky is seen, plus the COLOUR of the light that comes back from what stands near (red brick gives a warm shade).
A light map cannot brighten (white = 1), so bounce only shows where something else took light away."""
import os, sys, pickle, time, math
import numpy as np

PAGE = 2048; MAXC = 64

def key(P4):
    """one key per polygon: its four corners to the millimetre"""
    return np.ascontiguousarray(np.round(np.asarray(P4, np.float64).reshape(-1, 12) * 1000.0).astype(np.int32)).view(np.dtype((np.void, 48))).ravel()

def save_collect(path, chunks, log=print):
    if not chunks: return
    P = np.concatenate([c[0] for c in chunks]); N = np.concatenate([c[1] for c in chunks]); I = np.concatenate([c[2] for c in chunks]); F = np.concatenate([c[3] for c in chunks]); U = np.concatenate([c[4] for c in chunks])
    keep = ~F; K = key(P[keep]); _, first = np.unique(K, return_index=True); first.sort()
    np.savez(path + '.lm.npz', P=P[keep][first], N=N[keep][first], I=I[keep][first], U=U[keep][first]); log('       light maps: %d polygons to light (%d written by the meshes, %d of them flat-lit) -> %s.lm.npz' % (len(first), len(P), int(F.sum()), path))

def pack(P, centre, near=3.0, far=0.75, reach=60.0):
    """-> page, x0, y0, nu, nv per polygon (texel grid nu x nv; the rectangle it takes is rounded up to whole 4 x 4 compression blocks)"""
    e = lambda a, b: np.linalg.norm(P[:, a] - P[:, b], axis=1); lu = np.maximum(e(1, 0), e(2, 3)); lv = np.maximum(e(3, 0), e(2, 1))
    c = P.mean(1)[:, [0, 2]]; cen = np.asarray(centre, float)[::4]; d = np.empty(len(P))
    for s in range(0, len(P), 4000): d[s:s + 4000] = np.sqrt(((c[s:s + 4000, None] - cen[None]) ** 2).sum(2).min(1))
    dens = np.where(d < reach, near, np.where(d < 3 * reach, near * reach / np.maximum(d, 1e-6), far)); dens = np.maximum(dens, far)
    nu = np.clip(np.ceil(lu * dens).astype(int) + 1, 2, MAXC); nv = np.clip(np.ceil(lv * dens).astype(int) + 1, 2, MAXC); w = (nu + 3) // 4 * 4; h = (nv + 3) // 4 * 4
    order = np.lexsort((-w, -h)); page = np.zeros(len(P), np.int32); x0 = np.zeros(len(P), np.int32); y0 = np.zeros(len(P), np.int32); pg = 1; cx = cy = 0; rowh = 0
    for i in order:                                                    # shelves: tallest first
        if cx + w[i] > PAGE: cx = 0; cy += rowh; rowh = 0
        if cy + h[i] > PAGE: pg += 1; cx = cy = 0; rowh = 0
        page[i] = pg; x0[i] = cx; y0[i] = cy; cx += w[i]; rowh = max(rowh, h[i])
    return page, x0, y0, nu, nv

def _light(sc, S, P, N, K0, rgb_alb):
    """V (n), A (n), B (n, 3) for points P with facing N (as bake1995.run_native, the bounce in colour)"""
    T = S['tris'].astype(float); TM = S['mat']; SUN = np.asarray(S['sun'], float); SUN = SUN / np.linalg.norm(SUN)
    if not hasattr(_light, 'TN') or _light.key != id(S):
        TN = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); TN /= np.maximum(np.linalg.norm(TN, axis=1), 1e-12)[:, None]; _light.TN = TN; _light.key = id(S)
    TN = _light.TN
    def frame(n):
        ax = np.where((np.abs(n[:, 1]) < 0.9)[:, None], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]); t = np.cross(n, ax); t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]; return t, np.cross(n, t)
    st, sb = frame(SUN[None]); R = math.radians(1.6); SD = [SUN] + [SUN + math.tan(R) * (math.cos(a) * st[0] + math.sin(a) * sb[0]) for a in np.arange(6) * math.pi / 3]; SD = np.array([d / np.linalg.norm(d) for d in SD])
    KS = 16; HEMI = np.array([(math.sqrt((i + 0.5) / KS) * math.cos(i * 2.399963), math.sqrt((i + 0.5) / KS) * math.sin(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / KS))) for i in range(KS)])
    o = P + N * 0.03; V = np.zeros(len(P)); fr = (N @ SUN) > 0.02
    if fr.any():
        oo = np.repeat(o[fr], len(SD), axis=0); dd = np.tile(SD, (int(fr.sum()), 1)); hit, _ = sc.cast(oo + dd * 0.12, dd, 1e9); V[fr] = (hit.reshape(-1, len(SD)) < 0).mean(1)
    t, b = frame(N); ang = (K0 * 0.618034) % 1.0 * 2 * math.pi; ca, sa = np.cos(ang)[:, None], np.sin(ang)[:, None]
    hx = HEMI[None, :, 0] * ca - HEMI[None, :, 1] * sa; hy = HEMI[None, :, 0] * sa + HEMI[None, :, 1] * ca
    d = (t[:, None, :] * hx[..., None] + b[:, None, :] * hy[..., None] + N[:, None, :] * HEMI[None, :, 2, None]).reshape(-1, 3); oo = np.repeat(o, KS, axis=0) + d * 0.12
    hit, dist = sc.cast(oo, d, 1e9); sky = (hit.reshape(-1, KS) < 0).mean(1); back = np.zeros((len(hit), 3)); h = np.nonzero(hit >= 0)[0]
    if len(h):
        hn = TN[hit[h]]; hn = np.where(((hn * d[h]).sum(1) < 0)[:, None], hn, -hn); loc = oo[h] + d[h] * dist[h][:, None]; lit = np.full(len(h), 0.3); can = (hn @ SUN) > 0.05
        if can.any():
            o2 = loc[can] + hn[can] * 0.03; d2 = np.tile(SUN, (int(can.sum()), 1)); h2, _ = sc.cast(o2 + d2 * 0.12, d2, 1e9); cc = np.nonzero(can)[0][h2 < 0]; lit[cc] = 0.3 + 0.7 * (hn[cc] @ SUN) / max(SUN[1], 0.3)
        back[h] = rgb_alb[TM[hit[h]]] * np.minimum(lit, 1.0)[:, None]
    return V, sky, back.reshape(-1, KS, 3).mean(1)

def bake(path, mode='rt', strength=1.0, shade=0.33, log=print):
    """(fastlm.c lights the texels, one polygon after the other on every core: 7 s where the arrays of _old_bake below took 85; 2026-10-08.
    _old_bake stays as the reference: SR3_FASTGEO=0 / SR3_FASTLM=0 selects it; SR3_FASTGEO_CHECK=1 runs both, counts the texels that
    differ and leaves the OLD pages in the files.)"""
    import fastlm
    new = fastlm.bake(sys.modules[__name__], path, mode, strength, shade, (lambda s: None) if fastlm.CHECK else log) if fastlm.ON else None
    if new is None or fastlm.CHECK:
        if new is None and fastlm.ON: log('(lightmap1995.py: fastlm.c cannot take these polygons - the numpy code runs instead)')
        _old_bake(path, mode, strength, shade, log)
        if new is not None: old = np.load(path + '.lm.pages.npy'); same = old.shape == new[1:].shape and np.array_equal(old, new[1:]); fastlm.note('lightmap1995.bake', same, 'texel values that differ: %s' % (int((old != new[1:]).sum()) if old.shape == new[1:].shape else 'other pages'))

def _old_bake(path, mode='rt', strength=1.0, shade=0.33, log=print):   # (the numpy original of bake: fallback and reference)
    import rays
    t0 = time.time(); D = np.load(path + '.lm.npz'); P = D['P'].astype(float); N = D['N'].astype(float); I = D['I'].astype(float); U = D['U'].astype(bool); S = pickle.load(open(path + '.scene', 'rb'))
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]; SUN = np.asarray(S['sun'], float); SUN = SUN / np.linalg.norm(SUN)
    page, x0, y0, nu, nv = pack(P, S['centre']); npg = int(page.max()); sc = rays.Scene(S['tris'].astype(float)); sc.masks(S['mat'], S['uv'], S['holes']); alb = np.asarray(S['albedo_rgb'], float)
    pages = np.full((npg + 1, PAGE, PAGE, 3), 255, np.uint8); ntex = 0; order = np.argsort(page, kind='stable')
    for s in range(0, len(order), 20000):
        ii = order[s:s + 20000]; cnt = nu[ii] * nv[ii]; tot = int(cnt.sum()); f = np.repeat(np.arange(len(ii)), cnt); st = np.repeat(np.cumsum(cnt) - cnt, cnt); loc = np.arange(tot) - st
        iu = loc % nu[ii][f]; iv = loc // nu[ii][f]; a = (iu / (nu[ii][f] - 1))[:, None]; b = (iv / (nv[ii][f] - 1))[:, None]; Q = P[ii][f]
        # where the texel is: ON the polygon as the game draws it - two triangles along corners 1 - 3 (meshgen.quads_to_strip). The first build put it on the smooth
        # patch between them; 37% of the four-corner polygons are twisted by more than 5 cm, so half of such a polygon's texels lay under its own
        # surface and were lit as if in its shadow (LIGHTMAP-RT, user 2026-10-08: "quite a few polys lit the wrong way, dark where they should be light")
        lowr = (a + b)[:, 0] <= 1.0; pt = np.where(lowr[:, None], Q[:, 0] + a * (Q[:, 1] - Q[:, 0]) + b * (Q[:, 3] - Q[:, 0]), Q[:, 2] + (1 - a) * (Q[:, 3] - Q[:, 2]) + (1 - b) * (Q[:, 1] - Q[:, 2]))
        n1 = np.cross(Q[:, 1] - Q[:, 0], Q[:, 3] - Q[:, 0]); n2 = np.cross(Q[:, 2] - Q[:, 1], Q[:, 3] - Q[:, 1]); l1 = np.linalg.norm(n1, axis=1); l2 = np.linalg.norm(n2, axis=1)
        n2 = np.where((l2 > 1e-9)[:, None], n2, n1); l2 = np.where(l2 > 1e-9, l2, l1); tn = np.where(lowr[:, None], n1 / np.maximum(l1, 1e-12)[:, None], n2 / np.maximum(l2, 1e-12)[:, None])
        Ir = I[ii][f]; ir = ((1 - a) * (1 - b))[:, 0] * Ir[:, 0] + (a * (1 - b))[:, 0] * Ir[:, 1] + (a * b)[:, 0] * Ir[:, 2] + ((1 - a) * b)[:, 0] * Ir[:, 3]
        n = N[ii][f]; tn = np.where(((tn * n).sum(1) < 0)[:, None], -tn, tn); n = np.where((np.linalg.norm(tn, axis=1) > 0.5)[:, None], tn, n)      # the texel's facing: its own triangle's, on the side the polygon is seen from
        k0 = (np.arange(tot) + ntex).astype(float); V, A, B = _light(sc, S, pt, n, k0, alb); u = U[ii][f]
        if u.any():
            V2, A2, B2 = _light(sc, S, pt[u], -n[u], k0[u], alb); bet = (V2 + A2) > (V[u] + A[u]); Vu, Au, Bu = V[u], A[u], B[u]; Vu[bet] = V2[bet]; Au[bet] = A2[bet]; Bu[bet] = B2[bet]; V[u] = Vu; A[u] = Au; B[u] = Bu
        away = ((n @ SUN) <= 0.02) & ~u; ir = np.maximum(ir, 1e-3); Dd = np.where(away | (ir <= shade), ir, shade + (ir - shade) * V)
        if mode == 'rt': col = Dd[:, None] + strength * ((Dd * (0.45 + 0.55 * A))[:, None] + 0.6 * B - Dd[:, None])
        else: col = np.repeat(Dd[:, None], 3, axis=1)
        val = np.clip(col / ir[:, None], 0.0, 1.0); px = np.round(val * 255).astype(np.uint8)
        pages[page[ii][f], y0[ii][f] + iv, x0[ii][f] + iu] = px; ntex += tot
        # the rest of the polygon's rectangle (it is rounded up to whole 4 x 4 blocks) repeats its edge: a block then holds one polygon's values only
        for j, i in enumerate(ii):
            w4 = (nu[i] + 3) // 4 * 4; h4 = (nv[i] + 3) // 4 * 4
            if w4 != nu[i] or h4 != nv[i]:
                blk = pages[page[i], y0[i]:y0[i] + nv[i], x0[i]:x0[i] + nu[i]]
                pages[page[i], y0[i]:y0[i] + h4, x0[i]:x0[i] + w4] = np.pad(blk, ((0, h4 - nv[i]), (0, w4 - nu[i]), (0, 0)), mode='edge')
    np.save(path + '.lm.pages.npy', pages[1:]); np.savez(path + '.lm.table.npz', K=key(P), page=page, x0=x0, y0=y0, nu=nu, nv=nv)
    m = pages[1:].reshape(-1, 3); log('light maps (%s): %d polygons, %.1f million texels on %d pages of %d x %d, lit in %.1f s ; mean value %.2f ; texels darker than half: %.0f%%' % (mode, len(P), ntex / 1e6, npg, PAGE, PAGE, time.time() - t0, float(m.mean()) / 255, 100.0 * (m.max(1) < 128).mean()))

def load_table(path):
    T = np.load(path + '.lm.table.npz'); d = {k.tobytes(): i for i, k in enumerate(T['K'])}
    return dict(idx=d, page=T['page'], x0=T['x0'], y0=T['y0'], nu=T['nu'], nv=T['nv'], pages=np.load(path + '.lm.pages.npy', mmap_mode='r'), miss=[0], hit=[0])

def lookup(tab, P4):
    """-> page per polygon (0 = not on any page: the white picture), uv1 (4 per polygon, u16)"""
    K = key(P4); n = len(K); idx = np.array([tab['idx'].get(k.tobytes(), -1) for k in K], np.int64); ok = idx >= 0; j = np.maximum(idx, 0); tab['miss'][0] += int((~ok).sum()); tab['hit'][0] += int(ok.sum())
    x0 = tab['x0'][j].astype(float); y0 = tab['y0'][j].astype(float); nu = tab['nu'][j].astype(float); nv = tab['nv'][j].astype(float)
    cu = np.stack([x0 + 0.5, x0 + nu - 0.5, x0 + nu - 0.5, x0 + 0.5], 1) / PAGE; cv = np.stack([y0 + 0.5, y0 + 0.5, y0 + nv - 0.5, y0 + nv - 0.5], 1) / PAGE
    uv = np.stack([cu, cv], 2); uv = np.where(ok[:, None, None], uv, 0.5); page = np.where(ok, tab['page'][j], 0)
    return page.astype(np.int32), np.clip(np.round(uv.reshape(-1, 2) * 32768), 0, 32767).astype(np.uint16)

if __name__ == '__main__':
    bake(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'rt', float(sys.argv[3]) if len(sys.argv) > 3 else 1.0, float(sys.argv[4]) if len(sys.argv) > 4 else 0.33)
