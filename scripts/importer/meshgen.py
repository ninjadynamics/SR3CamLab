"""Authoring a static scenery mesh + material by cloning (format 0x20C7: pos xyzw, normal, tangent, uv0 u16x2, uv1 u16x2).
Template = a one-LOD, one-group world-space mesh such as Stadium4's 79d17eed and its material 7e9488ff.
See ../../07_glue_and_other_files.md (mesh section)."""
import struct
import numpy as np
import sbfw

VTX = np.dtype([('p', '<f4', 4), ('n', '<f4', 3), ('t', '<f4', 3), ('uv0', '<u2', 2), ('uv1', '<u2', 2)])
assert VTX.itemsize == 48

def parse_mesh(c):
    d = c.data; h = struct.unpack_from('<18I', d, 0)
    m = dict(stride=h[0], fmt=h[2], nv=h[5], ni=h[7], ng=h[8], pg=h[11], pv=h[12], pi=h[13], hdr=h)
    m['groups'] = [struct.unpack_from('<5I', d, m['pg'] + 20 * k) for k in range(m['ng'])]
    if m['stride'] == 48: m['verts'] = np.frombuffer(d, VTX, m['nv'], m['pv'])
    m['idx'] = np.frombuffer(d, '<u2', m['ni'], m['pi'])
    e = m['pi'] + 2 * m['ni']; m['rest'] = e + (-e % 4)
    m['tail'] = max(c.fix)                                           # {->model, 2, 0, 0, min xyz, max xyz, centre xyz, ...}
    return m

def winding_sign(c):
    """+1 if the strip triangles at even positions are counter-clockwise seen from the normal side"""
    m = parse_mesh(c); V = m['verts']; I = m['idx']; s = 0
    for k in range(len(I) - 2):
        a, b, cc = int(I[k]), int(I[k + 1]), int(I[k + 2])
        if len({a, b, cc}) < 3: continue
        n = np.cross(V['p'][b][:3] - V['p'][a][:3], V['p'][cc][:3] - V['p'][a][:3])
        if k & 1: n = -n
        s += 1 if float(n @ (V['n'][a] + V['n'][b] + V['n'][cc])) > 0 else -1
    return 1 if s >= 0 else -1, s

def quads_to_strip(nquads, ccw):
    """quad k uses vertices 4k..4k+3 laid out (a, b, c, d) around the quad counter-clockwise seen from the front.
    Strip a,b,d,c gives triangles (a,b,d) and (b,d,c)->(b,c,d flipped by parity): both front-facing when ccw is wanted."""
    out = []
    for k in range(nquads):
        a, b, c, d = 4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3
        q = [a, b, d, c] if ccw else [b, a, c, d]
        if out: out += [out[-1], q[0]]
        out += q
    return out

def clone_mesh(tpl, new_id, verts, strip, material_id, name=None):
    """tpl: template chunk (1 LOD, 1 group, stride 48). verts: np.array(VTX). Returns a new Ch."""
    m = parse_mesh(tpl); d = tpl.data
    assert m['ng'] == 1 and m['stride'] == 48 and m['pg'] == 0x48 and m['pv'] == 0x5c and m['hdr'][11] % 0x48 == 0
    nv = len(verts); ni = len(strip); assert nv < 65536 and ni < 65536, 'u16 limits: %d verts %d indices' % (nv, ni)
    g = list(m['groups'][0]); g[1] = nv; g[2] = 0; g[3] = (g[3] & 0xffff0000) | ni; g[4] = material_id
    vb = verts.tobytes(); ib = np.array(strip, '<u2').tobytes(); ib += b'\0' * (-len(ib) % 4)
    pv = 0x5c; pi = pv + len(vb); rest_new = pi + len(ib); rest_old = m['rest']; delta = rest_new - rest_old
    h = list(m['hdr']); h[5] = nv; h[7] = ni; h[11] = 0x48; h[12] = pv; h[13] = pi
    rest = bytearray(d[rest_old:])
    fix = [0x2c, 0x30, 0x34]
    for o in tpl.fix:
        if o < rest_old: continue
        v = struct.unpack_from('<I', rest, o - rest_old)[0]
        if v >= rest_old: struct.pack_into('<I', rest, o - rest_old, v + delta)
        fix.append(o + delta)
    t = m['tail'] - rest_old
    P = verts['p'][:, :3]; mn = P.min(0); mx = P.max(0); ce = (mn + mx) / 2
    struct.pack_into('<9f', rest, t + 0x10, *mn, *mx, *ce)
    if name is not None:                                              # overwrite the two name strings in place (same length or shorter)
        for o in tpl.fix:
            if o < rest_old: continue
            v = struct.unpack_from('<I', d, o)[0]
            if v >= rest_old and 0x20 <= d[v] < 0x7f and d[v:v + 4].isalnum() or (v >= rest_old and d[v:v + 4] == b'sta_'):
                e = d.index(b'\0', v); L = e - v; nb = name.encode()[:L]
                rest[v - rest_old:v - rest_old + L] = nb + b'\0' * (L - len(nb))
    data = struct.pack('<18I', *h) + struct.pack('<5I', *g) + vb + ib + bytes(rest)
    ref = [0x58] + [o + delta for o in tpl.ref if o >= rest_old]
    return sbfw.Ch(1, new_id, data, sorted(fix), ref)

def make_verts(quads, uv_tile=None):
    """quads: list of 4 corner positions (a,b,c,d counter-clockwise seen from the visible side). uv0 0..1 per quad."""
    v = np.zeros(4 * len(quads), VTX); uv = [(0, 0), (32767, 0), (32767, 32767), (0, 32767)]
    for k, q in enumerate(quads):
        q = np.array(q, float); n = np.cross(q[1] - q[0], q[3] - q[0]); n /= np.linalg.norm(n)
        t = q[1] - q[0]; t /= np.linalg.norm(t)
        for j in range(4):
            r = v[4 * k + j]; r['p'][:3] = q[j]; r['p'][3] = 1.0; r['n'] = n; r['t'] = t; r['uv0'] = uv[j]; r['uv1'] = (16384, 16384)
    return v

def make_verts_safe(quads):
    """like make_verts but tolerates triangles given as quads with a repeated corner and degenerate faces.
    (On arrays: the first version set every field of every vertex in a Python loop, a million and more times a build.)"""
    v = np.zeros(4 * len(quads), VTX)
    if not len(quads): return v
    Q = np.asarray(quads, np.float64).reshape(-1, 4, 3); n = np.cross(Q[:, 1] - Q[:, 0], Q[:, 2] - Q[:, 0]); ln = np.linalg.norm(n, axis=1)
    n = np.where((ln > 1e-9)[:, None], n / np.maximum(ln, 1e-300)[:, None], [0.0, 1.0, 0.0]); t = Q[:, 1] - Q[:, 0]; lt = np.linalg.norm(t, axis=1)
    t = np.where((lt > 1e-9)[:, None], t / np.maximum(lt, 1e-300)[:, None], [1.0, 0.0, 0.0])
    v['p'][:, :3] = Q.reshape(-1, 3); v['p'][:, 3] = 1.0; v['n'] = np.repeat(n, 4, axis=0); v['t'] = np.repeat(t, 4, axis=0)
    v['uv0'] = np.tile(np.array([(0, 0), (32767, 0), (32767, 32767), (0, 32767)], np.uint16), (len(Q), 1)); v['uv1'] = 16384
    return v

def ground_quads(x0, z0, x1, z1, y, cell):
    out = []; nx = int(round((x1 - x0) / cell)); nz = int(round((z1 - z0) / cell))
    for i in range(nx):
        for j in range(nz):
            xa, xb = x0 + i * cell, x0 + (i + 1) * cell; za, zb = z0 + j * cell, z0 + (j + 1) * cell
            out.append([(xa, y, za), (xa, y, zb), (xb, y, zb), (xb, y, za)])        # normal +y
    return out

def box_quads(cx, cy, cz, sx, sy, sz):
    x0, x1, y0, y1, z0, z1 = cx - sx / 2, cx + sx / 2, cy, cy + sy, cz - sz / 2, cz + sz / 2
    return [[(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)],          # top (+y)
            [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],          # +z
            [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)],          # -z
            [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)],          # +x
            [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)]]          # -x

ATEST_CELL, DSIDE_CELL, ABLEND_CELL = 0x4d4, 0x50c, 0x4e4      # value cells of gbUberATEST / gbUberDSIDE in the 1848-byte materials of shader f398b7a8
def clone_material(tpl, new_id, diffuse_id, diffuse_off=0x1bc, cutout=False, blend=False, two_sided=False):
    """cutout=True: alpha test + two-sided, the two switches every alpha-textured Alpine4 material has set"""
    d = bytearray(tpl.data); assert diffuse_off in tpl.ref
    struct.pack_into('<I', d, diffuse_off, diffuse_id)
    if cutout:
        assert len(d) == 1848; struct.pack_into('<I', d, ATEST_CELL, 1); struct.pack_into('<I', d, DSIDE_CELL, 1)
    if two_sided: assert len(d) == 1848; struct.pack_into('<I', d, DSIDE_CELL, 1)
    if blend:                                                          # alpha blend, one-sided: what Alpine4's own road paint materials have set (61b54d97)
        assert len(d) == 1848; struct.pack_into('<I', d, ABLEND_CELL, 1)
    return sbfw.Ch(2, new_id, bytes(d), tpl.fix, tpl.ref)

if __name__ == '__main__':
    import os
    from common import *
    f = sbfw.read_sbf(track_files(os.path.join(TRACKS, 'Stadium4'))['master_gfx_xdata']); by = f.byid()
    for cid in (0x79d17eed, 0x736c9d72, 0x7ae9c4e7):
        c = by[cid]; print('%08x winding sign, score' % cid, winding_sign(c), 'verts', parse_mesh(c)['nv'])
    tpl = by[0x79d17eed]; m = parse_mesh(tpl)
    # identity clone: same verts/strip -> must reproduce the template bytes
    c2 = clone_mesh(tpl, tpl.id, m['verts'].copy(), m['idx'].tolist(), m['groups'][0][4])
    print('identity clone identical', c2.data == tpl.data, sorted(c2.fix) == sorted(tpl.fix), c2.ref == tpl.ref)
    q = ground_quads(0, 0, 40, 40, 0, 20) + box_quads(5, 0, 5, 2, 2, 2); v = make_verts(q)
    c3 = clone_mesh(tpl, 0x12345678, v, quads_to_strip(len(q), winding_sign(tpl)[0] > 0), m['groups'][0][4], 'authored_ground')
    print('authored', c3, 'winding', winding_sign(c3), 'problems', len(sbfw.validate(type('F', (sbfw.SbfFile,), {})() if False else _mk(c3), quiet=True)) if False else '')
