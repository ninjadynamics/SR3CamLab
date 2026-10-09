"""The 1995 sky inside the slot's own sky dome: only the PIXELS of the dome's two textures are replaced.
    apply(f, cfg, rd)   f = master_gfx SbfFile being built, rd = imported road (ox, oz), cfg = course JSON
SR3 dome (master_gfx root +0x10, mesh format 0x2041, stride 20: f32 x, y, z, f32 1.0, u16 u, u16 v with 32768 = 1.0;
two groups = two materials of shader f398b7a8, each with one 2048 x 1024 DXT5 texture at material +0x1BC; a closed shell
of radius 2.2 .. 2.8 km around the origin, identical vertices in Canyon / Lakeside / Desert / Stadium).
Method: every texel of both textures is mapped through the dome's own triangles and UVs to a direction from the dome
centre; that direction is ray-cast from the course centre against the 1995 far backdrop polygons (sky dome, ground
plane, distant hills: classic/courses/<game>/<course>/src_course<N>_sky.obj, faces that do not fit the +-740 m scenery
square) and takes the colour of the 1995 tile texel it hits. The alpha bytes of the original DXT5 blocks are kept.
Nothing but pixel data changes (same ids, sizes, mip count), so the mesh, materials and shader stay SEGA's."""
import os, struct
import numpy as np
from PIL import Image
from common import *

def dome(f):
    by = f.byid(); r = f.chunks[-1]; c = by[r.u32(0x10)]; h = struct.unpack_from('<18I', c.data, 0)
    assert h[0] == 20 and h[2] == 0x2041, 'sky dome format %x stride %d' % (h[2], h[0])
    V = np.frombuffer(c.data, np.dtype([('p', '<f4', 3), ('w', '<f4'), ('uv', '<u2', 2)]), h[5], h[12]); I = np.frombuffer(c.data, '<u2', h[7], h[13]); out = []
    for k in range(h[8]):
        g = struct.unpack_from('<5I', c.data, h[11] + 20 * k); idx = I[g[2]:g[2] + (g[3] & 0xffff)].astype(int); tris = []
        for j in range(len(idx) - 2):
            a, b, d = idx[j], idx[j + 1], idx[j + 2]
            if len({a, b, d}) == 3: tris.append((a, b, d))
        mat = by[g[4]]; out.append((np.array(tris), by[mat.u32(0x1bc)]))
    return V, out

def directions(V, tris, W, H):
    """-> (H, W, 3) unit directions from the dome centre for every texel covered by the group's triangles, mask"""
    D = np.zeros((H, W, 3)); M = np.zeros((H, W), bool); P = V['p'].astype(float); UV = V['uv'].astype(float) / 32768.0 * np.array([W, H])
    for a, b, c in tris:
        u = UV[[a, b, c]]; x0, y0 = np.floor(u.min(0) - 1).astype(int); x1, y1 = np.ceil(u.max(0) + 1).astype(int)
        x0 = max(x0, 0); y0 = max(y0, 0); x1 = min(x1, W - 1); y1 = min(y1, H - 1)
        if x1 < x0 or y1 < y0: continue
        X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        den = (u[1, 1] - u[2, 1]) * (u[0, 0] - u[2, 0]) + (u[2, 0] - u[1, 0]) * (u[0, 1] - u[2, 1])
        if abs(den) < 1e-9: continue
        w0 = ((u[1, 1] - u[2, 1]) * (X - u[2, 0]) + (u[2, 0] - u[1, 0]) * (Y - u[2, 1])) / den
        w1 = ((u[2, 1] - u[0, 1]) * (X - u[2, 0]) + (u[0, 0] - u[2, 0]) * (Y - u[2, 1])) / den; w2 = 1 - w0 - w1
        ins = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        p = w0[..., None] * P[a] + w1[..., None] * P[b] + w2[..., None] * P[c]
        sub = D[y0:y1 + 1, x0:x1 + 1]; sub[ins] = p[ins]; M[y0:y1 + 1, x0:x1 + 1] |= ins
    n = np.linalg.norm(D, axis=2); D[M] /= n[M][:, None]
    return D, M

def far_faces(cfg, rd):
    """1995 backdrop triangles that are NOT inside the scenery square -> (tri positions n x 3 x 3 in OBJ axes, uv n x 3 x 2, tile index), tiles"""
    base = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', '')); p = os.path.join(base, 'src_course%s_sky.obj' % cfg['course'])
    V = []; VT = []; T = []; U = []; K = []; tiles = []; names = {}; mat = None
    for ln in open(p):
        if ln.startswith('v '): V.append(tuple(map(float, ln.split()[1:4])))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]; P = [V[a] for a, b in ix]
            if all(abs(q[0] + rd['ox']) < 740 and abs(-q[2] + rd['oz']) < 740 and -200 < q[1] < 400 for q in P): continue
            if mat not in names:
                tp = os.path.join(base, 'textures', mat + '.png'); names[mat] = len(tiles) if os.path.exists(tp) else -1
                if os.path.exists(tp): tiles.append(np.array(Image.open(tp).convert('RGBA')))
            if names[mat] < 0: continue
            for k in range(1, len(ix) - 1):
                T.append([P[0], P[k], P[k + 1]]); U.append([VT[ix[0][1]], VT[ix[k][1]], VT[ix[k + 1][1]]]); K.append(names[mat])
    return np.array(T, float), np.array(U, float), np.array(K), tiles

def cast(dirs, org, T, U, K, tiles, chunk=4096):
    """colour of the first opaque 1995 texel along each ray (dirs n x 3 in OBJ axes); rays that hit nothing -> nan"""
    out = np.full((len(dirs), 3), np.nan); e1 = T[:, 1] - T[:, 0]; e2 = T[:, 2] - T[:, 0]; s = org[None, :] - T[:, 0]
    for c0 in range(0, len(dirs), chunk):
        d = dirs[c0:c0 + chunk]                                         # m x 3
        pv = np.cross(d[:, None, :], e2[None, :, :]); det = (pv * e1[None]).sum(2); ok = np.abs(det) > 1e-12; inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        u = (pv * s[None]).sum(2) * inv; qv = np.cross(s, e1); v = (d[:, None, :] * qv[None]).sum(2) * inv; t = (e2 * qv).sum(1)[None, :] * inv
        hit = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (t > 1.0); t = np.where(hit, t, np.inf)
        order = np.argsort(t, axis=1)[:, :5]
        for r in range(len(d)):
            for j in order[r]:
                if not np.isfinite(t[r, j]): break
                uu, vv = u[r, j], v[r, j]; tex = (1 - uu - vv) * U[j, 0] + uu * U[j, 1] + vv * U[j, 2]; img = tiles[K[j]]; h, w = img.shape[:2]
                px = img[int(np.floor((1.0 - tex[1]) * h)) % h, int(np.floor(tex[0] * w)) % w]
                if px[3] >= 128: out[c0 + r] = px[:3]; break
    return out

def fill(img, mask):
    """texels without a value take the nearest valid one along the row, then along the column"""
    img = img.copy(); m = mask.copy()
    for axis in (1, 0):
        A = np.moveaxis(img, axis, 0); Mk = np.moveaxis(m, axis, 0); n = A.shape[0]; idx = np.where(Mk, np.arange(n).reshape((n,) + (1,) * (Mk.ndim - 1)), -1)
        fw = np.maximum.accumulate(idx, axis=0); idb = np.where(Mk, np.arange(n).reshape((n,) + (1,) * (Mk.ndim - 1)), 10 ** 9); bw = np.minimum.accumulate(idb[::-1], axis=0)[::-1]
        use_f = (fw >= 0) & ((bw >= 10 ** 9) | (np.arange(n).reshape((n,) + (1,) * (Mk.ndim - 1)) - fw <= bw - np.arange(n).reshape((n,) + (1,) * (Mk.ndim - 1))))
        src = np.where(use_f, fw, np.where(bw < 10 ** 9, bw, 0)); got = (fw >= 0) | (bw < 10 ** 9)
        cols = np.indices(Mk.shape)[1:]; A2 = A[(src,) + tuple(cols)]; A[~Mk & got] = A2[~Mk & got]; Mk |= got
    return img

def apply(f, cfg, rd, log=print, preview=None):
    import build_classic as BC
    # The dome is drawn about 110 m above a camera at Mountain's sea-level stretch (in game: the sea / sky line stood 2.3 degrees
    # over the road's vanishing point; Desert4's root +0x24 is 128.0, LIKELY the dome's height). Below its equator the dome has
    # almost no texture rows, so painting cannot move the horizon: the MESH is lowered (course JSON sky_drop, metres). Idempotent:
    # SEGA's widest ring is at y = 435.87, the current drop is read back from it.
    drop = float(cfg.get('sky_drop', 0.0)); by_ = f.byid(); c_ = by_[f.chunks[-1].u32(0x10)]; h_ = struct.unpack_from('<18I', c_.data, 0)
    dt_ = np.dtype([('p', '<f4', 3), ('w', '<f4'), ('uv', '<u2', 2)]); Vm = np.frombuffer(c_.data, dt_, h_[5], h_[12]).copy()
    rr = np.hypot(Vm['p'][:, 0], Vm['p'][:, 2]); now_ = 435.8731689453125 - float(Vm['p'][np.argmax(rr), 1]); shift_ = drop - now_
    if abs(shift_) > 0.01:
        Vm['p'][:, 1] -= shift_; d_ = bytearray(c_.data); d_[h_[12]:h_[12] + Vm.nbytes] = Vm.tobytes(); c_.data = bytes(d_); c_.gap = None
        log('       sky dome lowered by %.1f m in total (this run: %.1f)' % (drop, shift_))
    undo_ = np.array([0.0, drop, 0.0])
    V, groups = dome(f); V = V.copy(); V['p'] = V['p'] + undo_.astype(np.float32)   # directions are taken from SEGA's own shape, not the lowered one
    T, U, K, tiles = far_faces(cfg, rd)
    if not len(T): log('       1995 sky: no far backdrop faces with a readable tile; the slot keeps its own sky'); return False
    cen = rd['V'][:, rd['hw']]; org = np.array([-rd['ox'], float(cen[:, 1].mean()) + 2.0, rd['oz']]); res = []
    for gi, (tris, tex) in enumerate(groups):
        d = tex.data; w, h = struct.unpack_from('<II', d, 8); assert d[48 + 80:48 + 84] == b'DXT5' and len(d) == 48 + 124 + w * h, 'sky texture layout'
        W, H = w // 4, h // 4; D, M = directions(V, tris, W, H); dirs = D[M] * np.array([1, 1, -1.0])
        if cfg.get('sky_mode', 'tile') == 'tile':
            # The 1995 sky is ONE 256 x 256 picture: clear blue at the top, clouds, soft haze along its bottom edge (= the horizon).
            # Ray-casting the 1995 dome from the course smeared it near the horizon (user, three runs). The picture is now laid on
            # SR3's dome directly: its bottom row on the horizon, its top row at `sky_top` degrees, `sky_repeat` times around.
            ksky = max(set(K.tolist()), key=lambda k: T[K == k][:, :, 1].mean()); im_ = tiles[ksky][..., :3].astype(float); th, tw = im_.shape[:2]
            # Measured on the 1995 dome (objects 1257 / 1258): a wall of radius 100 km from the horizon up to 53.8 km = 28.3 degrees
            # carries the picture once in height (v linear in HEIGHT, so in tan(elevation)) and once per 60 degrees of azimuth
            # (6 times around, u = (90 deg - azimuth) / 60 deg, azimuth = atan2(z, x) in OBJ axes); above the wall the cone uses the top row.
            rep = float(cfg.get('sky_repeat', 6)); top = np.radians(float(cfg.get('sky_top', 28.28)))
            el = np.arcsin(np.clip(dirs[:, 1], -1, 1)); az = np.arctan2(dirs[:, 2], dirs[:, 0])
            fx = (((np.pi / 2 - az) / (2 * np.pi) * rep) % 1.0) * tw; fy = (1.0 - np.clip(np.tan(np.clip(el, 0.0, 1.5)) / np.tan(top), 0.0, 1.0)) * (th - 1)
            x0 = np.floor(fx).astype(int) % tw; x1 = (x0 + 1) % tw; y0 = np.clip(np.floor(fy).astype(int), 0, th - 1); y1 = np.clip(y0 + 1, 0, th - 1); ax = (fx - np.floor(fx))[:, None]; ay = (fy - np.floor(fy))[:, None]
            col = (im_[y0, x0] * (1 - ax) + im_[y0, x1] * ax) * (1 - ay) + (im_[y1, x0] * (1 - ax) + im_[y1, x1] * ax) * ay
            # above the picture: ONE colour. Its top row is not perfectly even (a few texels of 102 133 217 in a row of 109 138 219); repeated
            # upwards to the zenith they stood as faint vertical lines, one per copy of the picture (user: 'vertical lines repeating at every seam').
            flat_ = np.median(im_[0], axis=0); k_ = np.clip((el - 0.97 * top) / (0.03 * top), 0.0, 1.0)[:, None]; col = col * (1 - k_) + flat_ * k_
        else:
            col = cast(dirs, org, T, U, K, tiles)
        img = np.zeros((H, W, 3)); good = np.zeros((H, W), bool); ok = ~np.isnan(col[:, 0]); yy, xx = np.nonzero(M); img[yy[ok], xx[ok]] = col[ok]; good[yy[ok], xx[ok]] = True
        if not good.any(): log('       1995 sky: no ray hit the backdrop; the slot keeps its own sky'); return False
        img = fill(img, good); big = np.array(Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((w, h), Image.BILINEAR))
        BC.VIVID = tuple(BC.VIVID_CFG) if BC.VIVID_CFG else None; big = BC.vivid(big); BC.VIVID = None   # same brightening as the course's tiles
        # Below the horizon. The dome squeezes everything from the horizon down to the nadir into the texture's last rows, so a
        # per-texel "sea colour" came out as coarse blocks that differ from column to column: a pale wall with dark vertical
        # bars between the sea sheet's far edge and the clouds (user's 4K screenshot, 2026-10-07; reported four times as
        # smear / border / bars / "sky too high"). Now ONE row index for the whole texture, on a DXT block boundary: every row
        # from there down is the colour the sea sheet has on screen (course JSON sea.screen_colour, measured from a screenshot).
        sc_ = (cfg.get('sea') or {}).get('screen_colour')
        if sc_ is not None:
            E = np.full((H, W), np.nan); E[yy, xx] = dirs[:, 1]; below = E < 0.0
            rows_ = [int(np.argmax(below[:, x])) for x in range(W) if below[:, x].any()]
            if rows_:
                hr = (min(rows_) * (h // H)) // 4 * 4; big[hr:, :] = np.array(sc_, np.uint8)
                log('       sky: rows %d..%d of %d (horizon and below) = sea screen colour %s' % (hr, h - 1, h, sc_))
        blocks = np.frombuffer(d, np.uint8, w * h, 48 + 124).reshape(-1, 16).copy(); half = len(blocks) // 2; hb = h // 2
        for part in range(2):                                          # two halves: keeps the encoder's temporary arrays small
            rows = big[part * hb:(part + 1) * hb]; blocks[part * half:(part + 1) * half, 8:] = np.frombuffer(BC.dxt1_rgb(np.ascontiguousarray(rows)), np.uint8).reshape(-1, 8)
        tex.data = d[:48 + 124] + blocks.tobytes(); tex.gap = None
        res.append((int(M.sum()), int(ok.sum()), big.reshape(-1, 3).mean(0).round().tolist()))
        if preview: Image.fromarray(big).resize((w // 4, h // 4)).save(preview % gi)
    log('       1995 sky: %d far backdrop triangles of %d tiles ray-cast from the course centre into the slot\'s two sky dome textures (2048 x 1024 DXT5, pixels only): texels mapped / hit / mean colour per texture %s' % (len(T), len(tiles), res))
    return True
