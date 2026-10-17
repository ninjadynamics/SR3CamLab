"""SEGA Rally Championship (Model 2A) course -> OBJ + MTL straight from the ROM extracts in ../tmp/m2, with the CORRECT
texture pointers. (The exporter in classic/scripts paired every object with the UV list and header list of the NEXT
table row: the 16-byte table entries are {UV address, header address} of object k-1 followed by {polygon address, count}
... i.e. object k = (oba_k, obc_k, tpa_{k-1}, tha_{k-1}). Proof: the UV list of row k-1 is exactly 8 words per quad +
6 per triangle of object k long, for every object checked.)
    python classic_export.py        -> ../classic_tex/course1/src_course1_hi.obj, .mtl
Geometry and texture rules: MAME model2_v.cpp (geo_parse_np_ns, model2_3d_process_polygon). Axes of the OBJ: (x, y, -gameZ).
Without numpy since 2026-10-15 (kb 31): the region images are memoryviews, a corner a tuple of floats; the few products numpy made are
written out in its order (r4, cross, dot below). The files are byte for byte the numpy version's."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import TMP, WORK; M2 = os.path.join(TMP, 'm2')
OUT = os.path.join(WORK, 'classic_tex', 'course1')
OBJTAB = 0x864B48
COURSES = {'1': (1259, 1318)}                                         # set per course by course.use() from the course JSON
COURSE = '1'

def load():
    """(main, poly, polyf, tex16): the region images as memoryviews of u32, u32, float32 (the same bytes), u16
    (the numpy version: np.fromfile(..., '<u4'), poly.view('<f4'), np.fromfile(..., '<u2'))"""
    rd = lambda f: open(os.path.join(M2, f), 'rb').read(); pb = rd('polygons.bin')
    return memoryview(rd('main_data.bin')).cast('I'), memoryview(pb).cast('I'), memoryview(pb).cast('f'), memoryview(rd('textures.bin')).cast('H')

def r4(x):
    """np.round(x, 4) of a float: rint(x * 10000.0) / 10000.0, as numpy does it (Python's round(x, 4) rounds the decimal value instead)"""
    return round(x * 10000.0) / 10000.0
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])      # np.cross, each product rounded
def dot(a, b): return (a[0] * b[0] + a[2] * b[2]) + a[1] * b[1]     # np.dot of two fresh 3-vectors: OpenBLAS's (p0 + p2) + p1 (kb 31)
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def table(main, n=1508):
    i = OBJTAB // 4; return [[int(x) for x in main[i + 4 * k:i + 4 * k + 4]] for k in range(n)]

def decode(k, tab, poly, polyf, tex16):
    """polygons of object k: list of dict(verts [3|4 xyz, game axes], uv [(u, v) in texels], hdr[4], attr, normal)"""
    oba, obc = tab[k][0], tab[k][1]; tp, th = tab[k - 1][2], tab[k - 1][3]
    a = oba & 0x7FFFFF; p0 = tuple(polyf[a:a + 3]); p1 = tuple(polyf[a + 3:a + 6]); a += 6; out = []
    for n in range(obc):
        attr = int(poly[a])
        if (attr & 3) == 0: break
        quad = attr & 1; nrm = tuple(polyf[a + 1:a + 4]); q0 = tuple(polyf[a + 4:a + 7])
        q1 = tuple(polyf[a + 7:a + 10]) if quad else q0
        nv = 4 if quad else 3
        uv = [(int(tex16[tp + 2 * i + 1]) / 8.0, int(tex16[tp + 2 * i]) / 8.0) for i in range(nv)]    # stored v, u ; 13.3 fixed point
        tp += 2 * nv
        h = [int(x) for x in tex16[th:th + 4]]
        tho = (attr >> 12) & 0x1F
        if tho & 0x10: tho -= 32
        th += tho * 4
        lt = (attr >> 8) & 3
        if lt != 0:                                                    # link type 0 is never drawn (MAME check_culling)
            out.append(dict(verts=[p1, p0, q0, q1][:nv], uv=uv, hdr=h, attr=attr, normal=nrm))
        if lt in (0, 2): p0, p1 = q0, q1
        elif lt == 1: p1 = q0
        else: p0 = q1
        a += 10
    return out

def material(h):
    """name + fields from a texture header (MAME model2_3d_render)"""
    rend = (h[0] >> 13) & 3                                            # 2 textured, 3 textured translucent (texel 15 = hole)
    cb = (h[3] >> 6) & 0x3FF
    if rend < 2: return 'col_%03X' % cb, None
    tw = 32 << (h[0] & 7); th = 32 << ((h[0] >> 3) & 7); tx = 32 * (h[2] & 0x3F); ty = 32 * ((h[2] >> 6) & 0x1F); sheet = (h[2] >> 12) & 1
    mx = (h[0] >> 8) & 1; my = (h[0] >> 9) & 1
    name = 'tex_s%d_x%04d_y%04d_%dx%d_c%03X' % (sheet, tx, ty, tw, th, cb) + ('_mx' if mx else '') + ('_my' if my else '') + ('_t' if rend == 3 else '')
    return name, dict(sheet=sheet, x=tx, y=ty, w=tw, h=th, cb=cb, mx=mx, my=my, alpha=rend == 3, luma=h[1] & 0xff)

def export(course=None):
    course = course or COURSE
    main, poly, polyf, tex16 = load(); tab = table(main); lo, hi = COURSES[course]
    os.makedirs(OUT, exist_ok=True); base = 'src_course%s_hi' % course
    fo = open(os.path.join(OUT, base + '.obj'), 'w'); mats = {}
    fo.write('# SEGA Rally Championship course %s, objects %d..%d, texture pointers of table row k-1. Y up, Z = -gameZ\nmtllib %s.mtl\n' % (course, lo, hi, base))
    nv = nvt = 0; nf = 0; ndeg = 0
    for k in range(lo, hi + 1):
        fo.write('o sec_%04d\n' % k); vl = []; tl = []; fl = []; cur = None; vmap = {}
        for p in decode(k, tab, poly, polyf, tex16):
            name, info = material(p['hdr'])
            if name not in mats: mats[name] = info
            if name != cur: fl.append('usemtl ' + name); cur = name
            P = [(x, y, -z) for x, y, z in p['verts']]; idx = []
            tw, th = (info['w'], info['h']) if info else (1, 1)
            for i in range(len(P)):
                key = tuple(r4(c) for c in P[i]); vi = vmap.get(key)
                if vi is None: vi = nv + len(vl) + 1; vmap[key] = vi; vl.append('v %.4f %.4f %.4f' % tuple(P[i]))
                u, v = p['uv'][i]
                if info and info['mx']: u = u if int(u // tw) % 2 == 0 else (2 * tw * (int(u // tw) // 2 + 1) - u)   # mirror -> fold back
                if info and info['my']: v = v if int(v // th) % 2 == 0 else (2 * th * (int(v // th) // 2 + 1) - v)
                tl.append('vt %.5f %.5f' % (u / tw, 1.0 - v / th)); idx.append((vi, nvt + len(tl)))
            g = cross(sub(P[1], P[0]), sub(P[2], P[0])); hn = (-p['normal'][0], -p['normal'][1], p['normal'][2])      # -np.array([n0, n1, -n2])
            if dot(g, hn) < 0: idx = idx[::-1]
            fl.append('f ' + ' '.join('%d/%d' % t for t in idx)); nf += 1
            us = [q[0] for q in p['uv']]; vs = [q[1] for q in p['uv']]
            if info and (max(us) - min(us) < 0.5 or max(vs) - min(vs) < 0.5): ndeg += 1      # np.ptp(uu[:, 0]) < 0.5 ...
        fo.write('\n'.join(vl + tl + fl) + '\n'); nv += len(vl); nvt += len(tl)
    fo.close()
    with open(os.path.join(OUT, base + '.mtl'), 'w') as fm:
        for name, info in mats.items():
            fm.write('newmtl %s\nKd 0.8 0.8 0.8\n' % name)
            if info:
                fm.write('map_Kd textures/%s.png\n' % name)
                if info['alpha']: fm.write('map_d textures/%s.png\n' % name)
    import json
    json.dump(mats, open(os.path.join(OUT, 'materials.json'), 'w'), indent=0)
    print('course %s: %d faces, %d vertices, %d materials (%d textured, %d translucent); faces whose uv is degenerate in one axis: %d' %
          (course, nf, nv, len(mats), sum(1 for m in mats.values() if m), sum(1 for m in mats.values() if m and m['alpha']), ndeg))
    return mats

if __name__ == '__main__':
    export()
