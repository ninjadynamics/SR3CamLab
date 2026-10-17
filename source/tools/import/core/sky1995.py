"""The 1995 sky inside the slot's own sky dome: only the PIXELS of the dome's two textures are replaced.
    apply(f, cfg, rd)   f = master_gfx SbfFile being built, rd = imported road (ox, oz), cfg = course JSON
SR3 dome (master_gfx root +0x10, mesh format 0x2041, stride 20: f32 x, y, z, f32 1.0, u16 u, u16 v with 32768 = 1.0;
two groups = two materials of shader f398b7a8, each with one 2048 x 1024 DXT5 texture at material +0x1BC; a closed shell
of radius 2.2 .. 2.8 km around the origin, identical vertices in Canyon / Lakeside / Desert / Stadium).
Method: every texel of both textures is mapped through the dome's own triangles and UVs to a direction from the dome
centre; that direction is ray-cast from the course centre against the 1995 far backdrop polygons (sky dome, ground
plane, distant hills: classic/courses/<game>/<course>/src_course<N>_sky.obj, faces that do not fit the +-740 m scenery
square) and takes the colour of the 1995 tile texel it hits. The alpha bytes of the original DXT5 blocks are kept.
Nothing but pixel data changes (same ids, sizes, mip count), so the mesh, materials and shader stay SEGA's.
Since 2026-10-15 (kb 31) sky1995's own numpy operations are gone: the SBF bytes are read with struct, the per-texel work is fastlm.c's
(sky_dirs, sky_tile, sky_fill: their comments quote the numpy lines), the pictures are bytes. Only the build's vivid() and dxt1_rgb(),
called as before, still take a numpy array (a bridge until build_classic is numpy-free); cast() (sky_mode 'ray') still uses numpy."""
import os, struct, math, ctypes
from array import array
from PIL import Image
from common import *

_REC = struct.Struct('<3ffHH')                                         # a dome vertex: f32 x, y, z, f32 1.0, u16 u, v
_F = struct.Struct('<f'); f32 = lambda x: _F.unpack(_F.pack(x))[0]

def dome(f):
    """-> V (vertex records [x, y, z, w, u, v], the floats as float32 values), [(triangles [(a, b, c)], texture chunk)] per group"""
    by = f.byid(); r = f.chunks[-1]; c = by[r.u32(0x10)]; h = struct.unpack_from('<18I', c.data, 0)
    assert h[0] == 20 and h[2] == 0x2041, 'sky dome format %x stride %d' % (h[2], h[0])
    V = [list(_REC.unpack_from(c.data, h[12] + 20 * i)) for i in range(h[5])]; I = struct.unpack_from('<%dH' % h[7], c.data, h[13]); out = []
    for k in range(h[8]):
        g = struct.unpack_from('<5I', c.data, h[11] + 20 * k); idx = I[g[2]:g[2] + (g[3] & 0xffff)]; tris = []
        for j in range(len(idx) - 2):
            a, b, d = idx[j], idx[j + 1], idx[j + 2]
            if len({a, b, d}) == 3: tris.append((a, b, d))
        mat = by[g[4]]; out.append((tris, by[mat.u32(0x1bc)]))
    return V, out

def directions(V, tris, W, H):
    """-> D (H x W x 3 unit directions from the dome centre, row after row, as an array of doubles), M (H x W bytes: covered) - fastlm.c sky_dirs"""
    import fastlm
    P = array('d', [q for v in V for q in v[:3]]); UV = array('d', [q for v in V for q in (v[4] / 32768.0 * W, v[5] / 32768.0 * H)]); T = array('q', [i for t in tris for i in t])
    D = array('d', bytes(24 * W * H)); M = array('B', bytes(W * H)); fastlm.lib().sky_dirs(P.buffer_info()[0], UV.buffer_info()[0], len(tris), T.buffer_info()[0], W, H, D.buffer_info()[0], M.buffer_info()[0])
    return D, M

def far_faces(cfg, rd):
    """1995 backdrop triangles that are NOT inside the scenery square -> (tri positions n x 3 x 3 in OBJ axes, uv n x 3 x 2, tile index), tiles"""
    base = os.path.join(CLASSIC, 'courses', cfg['game'], cfg.get('gameplay', '')); p = os.path.join(base, 'src_course%s_sky.obj' % cfg['course'])
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
                if os.path.exists(tp): im = Image.open(tp).convert('RGBA'); tiles.append((im.size[0], im.size[1], im.tobytes()))      # (width, height, RGBA bytes)
            if names[mat] < 0: continue
            for k in range(1, len(ix) - 1):
                T.append([P[0], P[k], P[k + 1]]); U.append([VT[ix[0][1]], VT[ix[k][1]], VT[ix[k + 1][1]]]); K.append(names[mat])
    return T, U, K, tiles

def cast(dirs, org, T, U, K, tiles, chunk=4096):
    """colour of the first opaque 1995 texel along each ray (dirs n x 3 in OBJ axes); rays that hit nothing -> nan (sky_mode 'ray': numpy)"""
    import numpy as np
    T = np.array(T, float); U = np.array(U, float); K = np.array(K); tiles = [np.frombuffer(b, np.uint8).reshape(h, w, 4) for w, h, b in tiles]; dirs = np.asarray(dirs, float).reshape(-1, 3); org = np.asarray(org, float)
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

def _pw(v):
    """numpy's pairwise sum (rtbake/rt_bake_game5.py pwsum)"""
    n = len(v)
    if n < 8:
        t = 0.0
        for x in v: t += x
        return t
    if n <= 128:
        r = list(v[:8]); e = n - n % 8
        for i in range(8, e, 8):
            for j in range(8): r[j] += v[i + j]
        t = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
        for x in v[e:]: t += x
        return t
    h = n // 2; h -= h % 8
    return _pw(v[:h]) + _pw(v[h:])

def _ymean(tris):
    """T[K == k][:, :, 1].mean(): the corners' heights, a triangle's three after one another, the triangles added one after the other"""
    s = 0.0
    for t in tris: s += ((0.0 + t[0][1]) + t[1][1]) + t[2][1]
    return s / (3 * len(tris))

def _median(v):
    """np.median: the middle value, or the mean of the middle two ((0 + a) + b) / 2"""
    v = sorted(v); n = len(v); return v[n // 2] if n % 2 else ((0.0 + v[n // 2 - 1]) + v[n // 2]) / 2

def apply(f, cfg, rd, log=print, preview=None):
    import build_classic as BC
    # The dome is drawn about 110 m above a camera at Mountain's sea-level stretch (in game: the sea / sky line stood 2.3 degrees
    # over the road's vanishing point; Desert4's root +0x24 is 128.0, LIKELY the dome's height). Below its equator the dome has
    # almost no texture rows, so painting cannot move the horizon: the MESH is lowered (course JSON sky_drop, metres). Idempotent:
    # SEGA's widest ring is at y = 435.87, the current drop is read back from it.
    drop = float(cfg.get('sky_drop', 0.0)); by_ = f.byid(); c_ = by_[f.chunks[-1].u32(0x10)]; h_ = struct.unpack_from('<18I', c_.data, 0)
    Vm = [list(_REC.unpack_from(c_.data, h_[12] + 20 * i)) for i in range(h_[5])]
    hf_ = ctypes.CDLL('ucrtbase')._hypotf; hf_.restype = ctypes.c_float; hf_.argtypes = [ctypes.c_float] * 2      # np.hypot of float32: the C runtime's _hypotf (50,000 of 50,000 the same)
    rr = [hf_(v[0], v[2]) for v in Vm]; now_ = 435.8731689453125 - Vm[rr.index(max(rr))][1]; shift_ = drop - now_      # (np.argmax: the first of equals)
    if abs(shift_) > 0.01:
        s_ = f32(shift_); d_ = bytearray(c_.data)
        for i, v in enumerate(Vm): v[1] = f32(v[1] - s_); _REC.pack_into(d_, h_[12] + 20 * i, *v)      # Vm['p'][:, 1] -= shift_, in float32 (numpy makes the number a float32)
        c_.data = bytes(d_); c_.gap = None
        log('       sky dome lowered by %.1f m in total (this run: %.1f)' % (drop, shift_))
    V, groups = dome(f); dr_ = f32(drop)
    for v in V: v[0] = f32(v[0] + 0.0); v[1] = f32(v[1] + dr_); v[2] = f32(v[2] + 0.0)      # V['p'] + undo_.astype(np.float32): directions are taken from SEGA's own shape, not the lowered one
    T, U, K, tiles = far_faces(cfg, rd)
    if not T: log('       1995 sky: no far backdrop faces with a readable tile; the slot keeps its own sky'); return False
    import roadsight; Rv = roadsight.rows(rd['V']); cy_ = [r_[rd['hw']][1] for r_ in Rv]; org = (-rd['ox'], _pw(cy_) / len(cy_) + 2.0, rd['oz']); res = []      # cen[:, 1].mean(): pairwise
    for gi, (tris, tex) in enumerate(groups):
        d = tex.data; w, h = struct.unpack_from('<II', d, 8); assert d[48 + 80:48 + 84] == b'DXT5' and len(d) == 48 + 124 + w * h, 'sky texture layout'
        W, H = w // 4, h // 4; D, M = directions(V, tris, W, H); cov = [i for i in range(W * H) if M[i]]      # D[M] * [1, 1, -1.0], row after row
        dirs = array('d', [q for i in cov for q in (D[3 * i] * 1, D[3 * i + 1] * 1, D[3 * i + 2] * -1.0)])
        if cfg.get('sky_mode', 'tile') == 'tile':
            # The 1995 sky is ONE 256 x 256 picture: clear blue at the top, clouds, soft haze along its bottom edge (= the horizon).
            # Ray-casting the 1995 dome from the course smeared it near the horizon (user, three runs). The picture is now laid on
            # SR3's dome directly: its bottom row on the horizon, its top row at `sky_top` degrees, `sky_repeat` times around.
            ksky = max(set(K), key=lambda k: _ymean([t for t, k_ in zip(T, K) if k_ == k])); tw, th, tb_ = tiles[ksky]; im_ = array('d', [tb_[i] for i in range(len(tb_)) if i % 4 != 3])      # T[K == k][:, :, 1].mean() ; [..., :3].astype(float)
            # Measured on the 1995 dome (objects 1257 / 1258): a wall of radius 100 km from the horizon up to 53.8 km = 28.3 degrees
            # carries the picture once in height (v linear in HEIGHT, so in tan(elevation)) and once per 60 degrees of azimuth
            # (6 times around, u = (90 deg - azimuth) / 60 deg, azimuth = atan2(z, x) in OBJ axes); above the wall the cone uses the top row.
            rep = float(cfg.get('sky_repeat', 6)); top = math.radians(float(cfg.get('sky_top', 28.28)))      # (np.radians: the same x * (pi / 180))
            # above the picture: ONE colour. Its top row is not perfectly even (a few texels of 102 133 217 in a row of 109 138 219); repeated
            # upwards to the zenith they stood as faint vertical lines, one per copy of the picture (user: 'vertical lines repeating at every seam').
            flat_ = array('d', [_median([im_[3 * x + ch] for x in range(tw)]) for ch in range(3)]); col = array('d', bytes(len(dirs) * 8)); import fastlm      # np.median(im_[0], axis=0)
            assert fastlm.lib().sky_tile(len(cov), dirs.buffer_info()[0], tw, th, im_.buffer_info()[0], rep, top, flat_.buffer_info()[0], col.buffer_info()[0]), 'ucrtbase asin / tan / atan2'      # (fastlm.c quotes the numpy lines)
        else:
            col = array('d', [float(v) for v in cast(dirs, org, T, U, K, tiles).ravel()])
        img = array('d', bytes(24 * W * H)); good = array('B', bytes(W * H)); nok = 0
        for j, i in enumerate(cov):
            if col[3 * j] == col[3 * j]: img[3 * i:3 * i + 3] = col[3 * j:3 * j + 3]; good[i] = 1; nok += 1      # (not NaN: the ray hit something)
        if not nok: log('       1995 sky: no ray hit the backdrop; the slot keeps its own sky'); return False
        import fastlm; fastlm.lib().sky_fill(H, W, img.buffer_info()[0], good.buffer_info()[0])      # fill(img, good)
        sm_ = bytearray(len(img))                                       # np.clip(img, 0, 255).astype(np.uint8): bytes(int(min(max(v, 0.0), 255.0)) for v in img) in C
        if fastlm.lib().sky_bytes(len(img), img.buffer_info()[0], (fastlm.ctypes.c_char * len(sm_)).from_buffer(sm_)): raise ValueError('cannot convert float NaN to integer')
        small = bytes(sm_)
        big = Image.frombytes('RGB', (W, H), small).resize((w, h), Image.BILINEAR).tobytes()
        import numpy as np                                             # (the bridge: the build's vivid() takes a numpy array - kb 31)
        BC.VIVID = tuple(BC.VIVID_CFG) if BC.VIVID_CFG else None; big = BC.vivid(np.frombuffer(big, np.uint8).reshape(h, w, 3).copy()).tobytes(); BC.VIVID = None   # same brightening as the course's tiles
        # Below the horizon. The dome squeezes everything from the horizon down to the nadir into the texture's last rows, so a
        # per-texel "sea colour" came out as coarse blocks that differ from column to column: a pale wall with dark vertical
        # bars between the sea sheet's far edge and the clouds (user's 4K screenshot, 2026-10-07; reported four times as
        # smear / border / bars / "sky too high"). Now ONE row index for the whole texture, on a DXT block boundary: every row
        # from there down is the colour the sea sheet has on screen (course JSON sea.screen_colour, measured from a screenshot).
        sc_ = (cfg.get('sea') or {}).get('screen_colour')
        if sc_ is not None:
            below = bytearray(W * H)
            for j, i in enumerate(cov): below[i] = dirs[3 * j + 1] < 0.0
            rows_ = [next(y for y in range(H) if below[y * W + x]) for x in range(W) if any(below[y * W + x] for y in range(H))]      # np.argmax(below[:, x]): the first row below the horizon
            if rows_:
                hr = (min(rows_) * (h // H)) // 4 * 4; big = big[:3 * w * hr] + bytes(bytes(int(v) & 255 for v in sc_) * (w * (h - hr)))      # big[hr:, :] = sc_
                log('       sky: rows %d..%d of %d (horizon and below) = sea screen colour %s' % (hr, h - 1, h, sc_))
        blocks = bytearray(d[48 + 124:48 + 124 + w * h]); half = len(blocks) // 32; hb = h // 2      # 16-byte DXT5 blocks: alpha half kept, colour half new
        for part in range(2):                                          # two halves: keeps the encoder's temporary arrays small
            rows = np.frombuffer(big[3 * w * hb * part:3 * w * hb * (part + 1)], np.uint8).reshape(hb, w, 3); dx = bytes(BC.dxt1_rgb(np.ascontiguousarray(rows)))
            for j in range(half): o_ = 16 * (part * half + j) + 8; blocks[o_:o_ + 8] = dx[8 * j:8 * j + 8]
        tex.data = d[:48 + 124] + bytes(blocks); tex.gap = None
        res.append((sum(M), nok, [float(round(sum(big[ch::3]) / (w * h))) for ch in range(3)]))      # big.reshape(-1, 3).mean(0).round(): exact sums of whole numbers, / n, half to even
        if preview: Image.frombytes('RGB', (w, h), big).resize((w // 4, h // 4)).save(preview % gi)
    log('       1995 sky: %d far backdrop triangles of %d tiles ray-cast from the course centre into the slot\'s two sky dome textures (2048 x 1024 DXT5, pixels only): texels mapped / hit / mean colour per texture %s' % (len(T), len(tiles), res))
    return True
