"""Texture pages (atlases) for a classic course: many small pictures in one texture (course setting "atlas": true).

Why: Rally.exe keeps every texture it loads in ONE table of 1024 slots for the whole game (0x585D10 takes a free slot,
records of 0x2C bytes at 0x87AEA8, use counts at 0x874EA8; 0x5861B0 shares a slot between textures with the same MD5).
Track, cars, HUD, sky and the rest share it, and with every slot taken the game stops on the int3 at 0x585D5C. Daytona USA's
first build had 797 distinct textures (774 + 25 in the pobj file; its 587 composed tiles of the overlap resolver among them)
and stopped while loading; SEGA's tracks have 403 .. 550, Mountain RT 530.

What goes on a page: every picture of the course's own material groups (the gates' unlit, relief, own-shader and checker
materials keep a texture of their own). A polygon whose picture repeats across it is cut where the repeats meet (integer
uv lines, as uv_split cuts for the 0..2 limit of the mesh format), so every piece lies within ONE repeat and can point at the
picture's place on the page; one-colour pictures need no cut. Nothing is resampled: a picture is copied texel for texel at a
place that is a multiple of 16 texels, so the 4 x 4 compression blocks and the first five mip levels are the picture's own;
around it a border of 16 texels continues it the way the sampler did - wrapped (the next repeat), or its edge texels on an
axis the old texture clamped (cut-outs that never repeat on that axis) - so filtering across a repeat seam reads the same
texels as before and never a neighbour down to mip level 4. Pages are 1024 x 1024, one set per kind of material (opaque one-
or two-sided, cut-out one- or two-sided).
    build(groups, BC, tpl_tex, tpl_tex5, tpl_mat, log) -> ({group key: (material id, faces with page uv)}, new chunks)"""
import numpy as np
import meshgen

PAGE = 1024; G = 16

def _fits_one(UV):
    u = np.array(UV, float); u[:, 1] = 1.0 - u[:, 1]; lo = u.min(0); return bool(((lo - np.floor(lo + 1e-6)) + np.ptp(u, axis=0) <= 1.00002).all())

def cut_unit(fc):
    """one polygon -> pieces of 3 or 4 corners, each within one repeat of its picture on both axes (u, 1 - v): the polygon is cut
    along the integer uv lines that cross it; corners and uv of a cut are interpolated along the edge they lie on"""
    m_, s_, P_, UV_ = fc; P = np.asarray(P_, float); U = np.asarray(UV_, float).copy(); U[:, 1] = 1.0 - U[:, 1]
    polys = [(P, U)]
    for ax in (0, 1):
        lo, hi = float(U[:, ax].min()), float(U[:, ax].max())
        for c in range(int(np.floor(lo + 1e-6)) + 1, int(np.ceil(hi - 1e-6))):
            nxt = []
            for Pp, Up in polys:
                if not (Up[:, ax].min() < c - 1e-7 and Up[:, ax].max() > c + 1e-7): nxt.append((Pp, Up)); continue
                for keep in (-1.0, 1.0):
                    sd = (Up[:, ax] - c) * keep; oP = []; oU = []; n = len(Up)
                    for i in range(n):
                        j = (i + 1) % n
                        if sd[i] >= 0: oP.append(Pp[i]); oU.append(Up[i])
                        if (sd[i] > 0 and sd[j] < 0) or (sd[i] < 0 and sd[j] > 0):
                            t = sd[i] / (sd[i] - sd[j]); oP.append(Pp[i] + (Pp[j] - Pp[i]) * t); u_ = Up[i] + (Up[j] - Up[i]) * t; u_[ax] = c; oU.append(u_)
                    if len(oP) >= 3: nxt.append((np.array(oP), np.array(oU)))
            polys = nxt
    out = []
    for Pp, Up in polys:
        k = 1
        while k < len(Pp) - 1:
            idx = [0, k, k + 1] + ([k + 2] if k + 2 < len(Pp) else []); A3 = Pp[idx]; Q = Up[idx]
            ar = 0.5 * float(np.linalg.norm(np.cross(A3[1] - A3[0], A3[2] - A3[0]))) + (0.5 * float(np.linalg.norm(np.cross(A3[2] - A3[0], A3[3] - A3[0]))) if len(idx) == 4 else 0.0)
            if ar > 1e-6: out.append((m_, s_, [tuple(map(float, p)) for p in A3], [(float(u[0]), 1.0 - float(u[1])) for u in Q]))
            k += 2
    return out

def _pack(items):
    """items [(key, w, h)] -> {key: (page, x, y)}, pages; shelf packing, slots of (w + 2G, h + 2G) on a 16-texel grid"""
    out = {}; pages = 0; x = y = shelf = 0
    for key, w, h in sorted(items, key=lambda t: (-t[2], -t[1], str(t[0]))):
        sw = -(-(w + 2 * G) // 16) * 16; sh = -(-(h + 2 * G) // 16) * 16
        if pages == 0: pages = 1
        if x + sw > PAGE: x = 0; y += shelf; shelf = 0
        if y + sh > PAGE: pages += 1; x = y = shelf = 0
        out[key] = (pages - 1, x + G, y + G); x += sw; shelf = max(shelf, sh)
    return out, pages

def build(groups, BC, tpl_tex, tpl_tex5, tpl_mat, log):
    import overlay_bake as OB
    cand = {}; why = {'no picture': 0, 'special material': 0, 'too large': 0}
    for gi, (key, fl) in enumerate(groups):
        k = str(key); both = k.endswith(('|2', '|4')); one_ = k.endswith('|1'); three_ = k.endswith('|3'); name = k.split('|')[0]
        if three_ or (BC.UNLIT_TPL is not None and name in BC.UNLIT) or BC.bump_of(name) > 0 or name.endswith('_ck') or (BC.OWN_SHADER and name in BC.OWN_SHADER) or (BC.ROAD_RECIPE and name in BC.ROAD_TILES):
            why['special material'] += 1; continue
        px = BC.tile_pixels(name)
        if px is None: why['no picture'] += 1; continue
        rgb, hole = px; rgb = np.asarray(rgb)
        if rgb.ndim == 2: rgb = np.dstack([rgb] * 3)
        rgb = np.ascontiguousarray(rgb[:, :, :3]).astype(np.uint8); h, w = rgb.shape[:2]
        if w + 2 * G > PAGE or h + 2 * G > PAGE: why['too large'] += 1; continue
        flat = hole is None and bool((rgb == rgb[0, 0]).all())
        ncut_ = 0 if flat else sum(1 for fc in fl if not _fits_one(fc[3])); why['polygons cut into one repeat'] = why.get('polygons cut into one repeat', 0) + ncut_
        sp = list(fl) if flat else [q for fc in fl for q in (cut_unit(fc) if not _fits_one(fc[3]) else [fc])]
        clamp = [False, False]
        if hole is not None:                                        # the old texture clamped an axis along which the cut-out never repeats (add_scenery)
            spn = np.array([(np.array(fc[3], float) - np.floor(np.array(fc[3], float).min(0) + 1e-6)).max(0) for fc in fl]).max(0) if fl else np.array([9.0, 9.0]); clamp = [bool(spn[0] <= 1.00002), bool(spn[1] <= 1.00002)]
        if hole is not None and hole.shape == rgb.shape[:2] and (~hole).any(): rgb = rgb.copy(); rgb[hole] = rgb[~hole].mean(0).astype(np.uint8)      # (as add_scenery does: no dark fringe)
        cand[key] = dict(gi=gi, name=name, rgb=rgb, hole=hole, w=w, h=h, flat=flat, faces=sp, kind=(hole is not None, one_, both), pad=('edge' if clamp[1] else 'wrap', 'edge' if clamp[0] else 'wrap'))
    by_kind = {}
    for key, c in cand.items(): by_kind.setdefault(c['kind'], []).append(key)
    new = []; out = {}; npages = 0; texmap = {}
    for kind in sorted(by_kind):
        keys = sorted(by_kind[kind], key=str); place, n = _pack([(k, cand[k]['w'], cand[k]['h']) for k in keys])
        for p in range(n):
            pid = 0xc1a5f000 + npages; mid = 0xc1a6f000 + npages; npages += 1
            img = np.zeros((PAGE, PAGE, 3), np.uint8); hol = np.zeros((PAGE, PAGE), bool) if kind[0] else None; tiles = []
            for k in keys:
                pg, x0, y0 = place[k]
                if pg != p: continue
                c = cand[k]; w, h = c['w'], c['h']
                pv, pu = c['pad']; pad2 = lambda a_: np.pad(np.pad(a_, ((G, G),) + ((0, 0),) * (a_.ndim - 1), mode=pv), ((0, 0), (G, G)) + ((0, 0),) * (a_.ndim - 2), mode=pu)      # rows (v) then columns (u), each the way its axis was sampled
                img[y0 - G:y0 + h + G, x0 - G:x0 + w + G] = pad2(c['rgb'])
                if hol is not None:
                    hh = c['hole'] if c['hole'] is not None else np.zeros((h, w), bool); hol[y0 - G:y0 + h + G, x0 - G:x0 + w + G] = pad2(hh)
                fl2 = []
                for m_, s_, P_, UV_ in c['faces']:
                    u = np.array(UV_, float); u[:, 1] = 1.0 - u[:, 1]
                    loc = np.full_like(u, 0.5) if c['flat'] else np.clip(u - np.floor(u.min(0) + 1e-6), 0.0, 1.0)
                    fl2.append((m_, s_, P_, [((x0 + a * w) / PAGE, (y0 + b * h) / PAGE) for a, b in loc]))
                out[k] = (mid, fl2); BC.TEX_OF.setdefault(c['name'], []).append(pid); tiles.append(dict(tile=c['name'], key=str(k), x=x0, y=y0, w=w, h=h, pad=list(c['pad'])))
            if kind[0]:
                tex = BC.make_texture_dxt5(tpl_tex5, pid, img, hol); mat = meshgen.clone_material(tpl_mat, mid, pid, cutout=True)
                if kind[1]:
                    d_ = bytearray(mat.data); import struct; struct.pack_into('<I', d_, meshgen.DSIDE_CELL, 0); mat.data = bytes(d_)
            else:
                tex = BC.make_texture(tpl_tex, pid, img, None); mat = meshgen.clone_material(tpl_mat, mid, pid, two_sided=kind[2])
            new += [tex, mat]
            BC.TEXMAP[pid] = dict(atlas=tiles, cut=bool(kind[0]), page=PAGE, border=G, vivid=list(BC.VIVID) if BC.VIVID else None,
                                  gain=None if BC.SCENE_GAIN is None else [float(q) for q in np.asarray(BC.SCENE_GAIN, float).ravel()])
    log('       texture pages (atlas): %d pictures of %d material groups on %d pages of %d x %d (border %d texels), %d polygons on them ; %s' % (
        len(cand), len(groups), npages, PAGE, PAGE, G, sum(len(v[1]) for v in out.values()), why))
    return out, new
