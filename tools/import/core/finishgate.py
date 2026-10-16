"""The 1995 finish gate as SR3's own lap-aware start / finish banner.

1995 (user, Model 2, 2026-10-08): no gate at the start of the race; after one lap the gate at the line is a 20 m CHECK POINT
gate with its posts outside the road; on the final lap the same gate reads FINISH.

SR3 has an object that does this: class Start_Finish_Line (CSR_StartFinishObject), one per track, model type 'StartFinishObj'
= ONE mesh chunk with three LODs. The object forces the LOD itself (object +1B8, read at 0x632BE5 as the LOD to draw), so the
three "LODs" are three states (0x61CAF0, called every frame from the object's update 0x61FD30):
    LOD 0  from the start                                   SEGA: START banner in front
    LOD 1  race running and the car more than 300 m away     SEGA: CHECKPOINT
    LOD 2  final lap ([0x9DD614] == laps - 1), car within 300 m   SEGA: FINISH
VERIFIED in code; the in-game result of THIS replacement is not confirmed yet.

    finishgate.install(go_file, states, centre, tpl5)
states = three face lists (importer faces, SR3 coordinates): [nothing, CHECK POINT gate, FINISH gate]; centre = where the
object stands (crowd.build(finish_at=centre) writes the object record). The mesh chunk keeps its id and its tail (node names,
LOD table); vertices are format 0x20C3 (36 bytes: position xyzw, normal, uv0, uv1), relative to the centre. Materials are
clones of the banner's own (blend, two-sided, shadow casting, light map) with the 1995 tiles as textures.
Without numpy since 2026-10-16 (kb 31): build_classic's buffer twins (tile_pixels_buf, vivid_buf, make_texture_dxt5_buf, faces_to_mesh_buf)
and builduv.uv_split; numpy's float32 steps emulated (a product or difference of float32 numbers in double, rounded to float32: the same
bits); _old_install is the numpy original."""
import struct
import sbfw, meshgen

MESH = 0x4ec27d47; MAT = 0x93757b78; TEX0 = 0xc1b00000
V36S = struct.Struct('<4f3f2H2H'); V48S = struct.Struct('<4f3f12x2H4x')   # the banner's vertex (36 bytes: position xyzw, normal, uv0, uv1); meshgen.VTX's fields but the tangent and uv1
_F = struct.Struct('<f')
def _f32(x): return _F.unpack(_F.pack(x))[0]
def _upscale(b, H, W, ch, S):
    """np.repeat(np.repeat(a, S, 0), S, 1) of an H x W x ch byte picture"""
    out = bytearray()
    for y in range(H):
        row = b''.join(b[(y * W + x) * ch:(y * W + x + 1) * ch] * S for x in range(W)); out += row * S
    return bytes(out)
def install(g, states, centre, tpl5, log=print, unlit=None):
    import build_classic as BC, builduv
    from npyio import Arr
    by = g.byid(); mesh = by[MESH]; d = mesh.data; mat0 = by[MAT]; centre = [float(v) for v in centre]
    hdr = [struct.unpack_from('<18I', d, 0x48 * k) for k in range(3)]
    assert all(h[0] == 0x24 and h[2] == 0x20c3 for h in hdr), 'not the 3-LOD banner mesh'
    rest_old = hdr[2][13] + 2 * hdr[2][7]; rest_old += -rest_old % 4
    uv1 = struct.unpack_from('<2H', d, hdr[0][12] + 32)                # one texel of the banner's light map for every vertex (the first vertex's uv1)
    new = []; mats = {}
    def material(tile):
        if tile not in mats:
            if tile.startswith('col_'): H = W = 16; rgb = bytes([150]) * (16 * 16 * 3); hole = None          # flat-colour polygons: the grey add_scenery gives them
            else:
                px = BC.tile_pixels_buf(tile)
                if px is None: raise SystemExit('finish gate: no picture for %s' % tile)
                ra, ha = px; H, W = ra.shape[:2]; rgb = bytes(memoryview(ra.buf).cast('B')[:ra.nbytes]); hole = None if ha is None else (bytes(memoryview(ha.buf).cast('B')[:ha.nbytes]), tuple(ha.shape))
            k = len(mats); tid = TEX0 + 2 * k; mid = tid + 1; gain = BC.UNLIT_GAIN if unlit else 1.0
            if gain != 1.0: gf = _f32(gain); rgb = bytes(int(min(max(_f32(x * gf), 0.0), 255.0)) for x in rgb)      # np.clip(np.asarray(rgb, np.float32) * gain, 0, 255).astype(np.uint8)
            BC.VIVID = tuple(BC.VIVID_CFG) if BC.VIVID_CFG else None; va = BC.vivid_buf(Arr('|u1', (H, W, 3), bytearray(rgb))); BC.VIVID = None      # the colours the scenery tiles get
            rgb = bytes(memoryview(va.buf).cast('B')[:va.nbytes])
            if BC.GATE_SHARP > 1:                                      # (as add_scenery does for the other gates)
                S = BC.GATE_SHARP
                if hole is not None and hole[1] == (H, W): hole = (_upscale(hole[0], H, W, 1, S), (H * S, W * S))
                rgb = _upscale(rgb, H, W, 3, S); H, W = H * S, W * S
            ho = Arr('|b1', hole[1], bytearray(hole[0])) if hole is not None else Arr('|b1', (H, W), bytearray(H * W))
            t = BC.make_texture_dxt5_buf(tpl5, tid, Arr('|u1', (H, W, 3), bytearray(rgb)), ho)
            td = bytearray(t.data); struct.pack_into('<2I', td, 20, 1, 1); t.data = bytes(td)          # wrap both ways
            m = (unlit or mat0).copy(); m.id = mid; m.gap = None; md = bytearray(m.data); struct.pack_into('<I', md, 0x1bc, tid); m.data = bytes(md)      # unlit: SEGA's unlit material (see build_classic.UNLIT_TPL) instead of the banner's lit one, which came out dull
            BC.TEXMAP_FINISH[tid] = dict(tile=str(tile), cut=True, unlit=bool(unlit), unlit_gain=float(BC.UNLIT_GAIN), sharp=int(BC.GATE_SHARP), vivid=list(BC.VIVID_CFG) if BC.VIVID_CFG else None, gain=None)
            new.extend([t, m]); mats[tile] = mid
        return mats[tile]
    blocks = []; allp = []; cf = [_f32(c) for c in centre]
    for st in states:
        groups = []
        if st:
            bym = {}
            for fc in st: bym.setdefault(str(fc[0]).split('|')[0], []).append(fc)
            for tile, fl in bym.items():
                fl, ns = builduv.uv_split(fl); v48, nq, cl = BC.faces_to_mesh_buf(fl, 'tile', up_normals=True); vb = bytearray()
                for r in V48S.iter_unpack(bytes(memoryview(v48.buf).cast('B')[:v48.nbytes])):
                    q = (_f32(r[0] - cf[0]), _f32(r[1] - cf[1]), _f32(r[2] - cf[2]))      # v['p'][:, :3] -= centre.astype(np.float32)
                    vb += V36S.pack(q[0], q[1], q[2], r[3], r[4], r[5], r[6], r[7], r[8], uv1[0], uv1[1]); allp.append(q)
                groups.append((material(tile), bytes(vb), meshgen.quads_to_strip(nq, True)))
        else:                                                          # nothing to show: one quad of no size under the ground (a LOD needs a group)
            groups.append((None, V36S.pack(0.0, -60.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0, 0, uv1[0], uv1[1]) * 4, meshgen.quads_to_strip(1, True)))
        blocks.append(groups)
    first = next(iter(mats.values()))
    out = bytearray(0x48 * 3); fix = []; ref = []; nvx = lambda v: len(v) // 36
    for k, groups in enumerate(blocks):
        pg = len(out); nv = sum(nvx(v) for m, v, s in groups); ni = sum(len(s) for m, v, s in groups); assert nv < 65536 and ni < 65536
        v0 = i0 = 0
        for m, v, s in groups:
            ref.append(len(out) + 16); out += struct.pack('<5I', v0, nvx(v), i0, 0x10000 | len(s), m or first); v0 += nvx(v); i0 += len(s)
        pv = len(out); v0 = 0; idx = []
        for m, v, s in groups: out += v; idx += [v0 + q for q in s]; v0 += nvx(v)
        pi = len(out); out += struct.pack('<%dH' % len(idx), *idx); out += bytes(-len(out) % 4)
        h = list(hdr[k]); h[5] = nv; h[7] = ni; h[8] = len(groups); h[11] = pg; h[12] = pv; h[13] = pi
        struct.pack_into('<18I', out, 0x48 * k, *h); fix += [0x48 * k + 0x2c, 0x48 * k + 0x30, 0x48 * k + 0x34]
    rest_new = len(out); delta = rest_new - rest_old; rest = bytearray(d[rest_old:])
    for o in mesh.fix:
        if o < rest_old: continue
        p = struct.unpack_from('<I', rest, o - rest_old)[0]
        if p >= rest_old: struct.pack_into('<I', rest, o - rest_old, p + delta)
        fix.append(o + delta)
    mn = [min(q[c] for q in allp) for c in range(3)]; mx = [max(q[c] for q in allp) for c in range(3)]
    struct.pack_into('<9f', rest, len(rest) - 60, *mn, *mx, *(_f32(_f32(mn[c] + mx[c]) / 2) for c in range(3)))      # {min, max, centre} before the LOD table ((mn + mx) / 2 in float32)
    out += rest
    i = g.chunks.index(mesh); g.chunks[i] = sbfw.Ch(1, MESH, bytes(out), sorted(fix), sorted(ref))
    g.chunks[i:i] = new
    for c in g.chunks: c.gap = None
    info = dict(lods=[(sum(nvx(v) for m, v, s in gr), len(gr)) for gr in blocks], materials=len(mats), mesh_bytes=len(out), was=len(d))
    log('       finish gate as the lap-aware Start_Finish_Line object: LOD (vertices, groups) %s, %d materials, mesh %d bytes (SEGA: %d)' % (info['lods'], info['materials'], info['mesh_bytes'], info['was']))
    return info

def _old_install(g, states, centre, tpl5, log=print, unlit=None):
    """(the numpy original of install: the reference)"""
    import numpy as np
    V36 = np.dtype([('p', '<f4', 4), ('n', '<f4', 3), ('uv0', '<u2', 2), ('uv1', '<u2', 2)]); assert V36.itemsize == 36
    import build_classic as BC
    by = g.byid(); mesh = by[MESH]; d = mesh.data; mat0 = by[MAT]; centre = np.asarray(centre, float)
    hdr = [struct.unpack_from('<18I', d, 0x48 * k) for k in range(3)]
    assert all(h[0] == 0x24 and h[2] == 0x20c3 for h in hdr), 'not the 3-LOD banner mesh'
    rest_old = hdr[2][13] + 2 * hdr[2][7]; rest_old += -rest_old % 4
    uv1 = tuple(np.frombuffer(d, V36, 1, hdr[0][12])[0]['uv1'])       # one texel of the banner's light map for every vertex
    new = []; mats = {}
    def material(tile):
        if tile not in mats:
            px = (np.full((16, 16, 3), 150, np.uint8), None) if tile.startswith('col_') else BC.tile_pixels(tile)      # flat-colour polygons: the grey add_scenery gives them
            if px is None: raise SystemExit('finish gate: no picture for %s' % tile)
            rgb, hole = px; k = len(mats); tid = TEX0 + 2 * k; mid = tid + 1
            BC.VIVID = tuple(BC.VIVID_CFG) if BC.VIVID_CFG else None; rgb = BC.vivid(np.clip(np.asarray(rgb, np.float32) * (BC.UNLIT_GAIN if unlit else 1.0), 0, 255).astype(np.uint8)); BC.VIVID = None      # the colours the scenery tiles get
            if BC.GATE_SHARP > 1:                                      # (as add_scenery does for the other gates)
                hole = np.repeat(np.repeat(hole, BC.GATE_SHARP, 0), BC.GATE_SHARP, 1) if hole is not None and hole.shape == rgb.shape[:2] else hole; rgb = np.repeat(np.repeat(rgb, BC.GATE_SHARP, 0), BC.GATE_SHARP, 1)
            t = BC.make_texture_dxt5(tpl5, tid, np.ascontiguousarray(rgb), hole if hole is not None else np.zeros(rgb.shape[:2], bool))
            td = bytearray(t.data); struct.pack_into('<2I', td, 20, 1, 1); t.data = bytes(td)          # wrap both ways
            m = (unlit or mat0).copy(); m.id = mid; m.gap = None; md = bytearray(m.data); struct.pack_into('<I', md, 0x1bc, tid); m.data = bytes(md)      # unlit: SEGA's unlit material (see build_classic.UNLIT_TPL) instead of the banner's lit one, which came out dull
            BC.TEXMAP_FINISH[tid] = dict(tile=str(tile), cut=True, unlit=bool(unlit), unlit_gain=float(BC.UNLIT_GAIN), sharp=int(BC.GATE_SHARP), vivid=list(BC.VIVID_CFG) if BC.VIVID_CFG else None, gain=None)
            new.extend([t, m]); mats[tile] = mid
        return mats[tile]
    blocks = []; allp = []
    for st in states:
        groups = []
        if st:
            bym = {}
            for fc in st: bym.setdefault(str(fc[0]).split('|')[0], []).append(fc)
            for tile, fl in bym.items():
                fl, ns = BC.uv_split(fl); v48, nq, cl = BC.faces_to_mesh(fl, 'tile', up_normals=True)
                v = np.zeros(len(v48), V36); v['p'] = v48['p']; v['p'][:, :3] -= centre.astype(np.float32); v['n'] = v48['n']; v['uv0'] = v48['uv0']; v['uv1'] = uv1
                groups.append((material(tile), v, meshgen.quads_to_strip(nq, True))); allp.append(v['p'][:, :3])
        else:                                                          # nothing to show: one quad of no size under the ground (a LOD needs a group)
            v = np.zeros(4, V36); v['p'] = (0.0, -60.0, 0.0, 1.0); v['n'] = (0.0, 1.0, 0.0); v['uv1'] = uv1
            groups.append((None, v, meshgen.quads_to_strip(1, True)))
        blocks.append(groups)
    first = next(iter(mats.values()))
    out = bytearray(0x48 * 3); fix = []; ref = []
    for k, groups in enumerate(blocks):
        pg = len(out); nv = sum(len(v) for m, v, s in groups); ni = sum(len(s) for m, v, s in groups); assert nv < 65536 and ni < 65536
        v0 = i0 = 0
        for m, v, s in groups:
            ref.append(len(out) + 16); out += struct.pack('<5I', v0, len(v), i0, 0x10000 | len(s), m or first); v0 += len(v); i0 += len(s)
        pv = len(out); v0 = 0; idx = []
        for m, v, s in groups: out += v.tobytes(); idx += [v0 + q for q in s]; v0 += len(v)
        pi = len(out); out += np.array(idx, '<u2').tobytes(); out += bytes(-len(out) % 4)
        h = list(hdr[k]); h[5] = nv; h[7] = ni; h[8] = len(groups); h[11] = pg; h[12] = pv; h[13] = pi
        struct.pack_into('<18I', out, 0x48 * k, *h); fix += [0x48 * k + 0x2c, 0x48 * k + 0x30, 0x48 * k + 0x34]
    rest_new = len(out); delta = rest_new - rest_old; rest = bytearray(d[rest_old:])
    for o in mesh.fix:
        if o < rest_old: continue
        p = struct.unpack_from('<I', rest, o - rest_old)[0]
        if p >= rest_old: struct.pack_into('<I', rest, o - rest_old, p + delta)
        fix.append(o + delta)
    P = np.vstack(allp); mn = P.min(0); mx = P.max(0)
    struct.pack_into('<9f', rest, len(rest) - 60, *mn, *mx, *((mn + mx) / 2))       # {min, max, centre} before the LOD table
    out += rest
    i = g.chunks.index(mesh); g.chunks[i] = sbfw.Ch(1, MESH, bytes(out), sorted(fix), sorted(ref))
    g.chunks[i:i] = new
    for c in g.chunks: c.gap = None
    info = dict(lods=[(sum(len(v) for m, v, s in gr), len(gr)) for gr in blocks], materials=len(mats), mesh_bytes=len(out), was=len(d))
    log('       finish gate as the lap-aware Start_Finish_Line object: LOD (vertices, groups) %s, %d materials, mesh %d bytes (SEGA: %d)' % (info['lods'], info['materials'], info['mesh_bytes'], info['was']))
    return info

def check(g):
    """re-reads the banner mesh as written: every pointer inside, every group inside its LOD, every material present"""
    by = g.byid(); c = by[MESH]; d = c.data; out = []
    for k in range(3):
        h = struct.unpack_from('<18I', d, 0x48 * k); nv, ni, ng, pg, pv, pi = h[5], h[7], h[8], h[11], h[12], h[13]
        assert pg + 20 * ng == pv and pv + 36 * nv == pi and pi + 2 * ni <= len(d), 'LOD %d layout' % k
        assert not ni or max(struct.unpack_from('<%dH' % ni, d, pi)) < nv
        for q in range(ng):
            v0, n, i0, w, m = struct.unpack_from('<5I', d, pg + 20 * q); assert v0 + n <= nv and i0 + (w & 0xffff) <= ni and m in by and by[m].kind == 2, 'group %d of LOD %d' % (q, k)
            assert pg + 20 * q + 16 in c.ref
        out.append((nv, ni, ng))
    for o in c.fix: assert struct.unpack_from('<I', d, o)[0] < len(d), 'pointer at %x' % o
    return out
