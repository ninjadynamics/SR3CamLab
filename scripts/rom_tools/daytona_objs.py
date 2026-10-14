"""Daytona USA (original Model 2, set `daytona`): object table and polygon-ROM strip decoder.

Object table (own finding, verified by the counts): main data ROM offset 0x83FBB4 (CPU address 0x0283FBB4),
3190 records of 5 words:
    { oba, tpa, tha, obc, 0 }
    oba  object address for the geometry engine: 0x800000 | word index in the polygon ROM (0x01000000 = polygon RAM)
    tpa  texture point address: 16-bit word index into the "texture" ROM (bit 23 set = texture RAM)
    tha  texture header address: 16-bit word index into the "texture" ROM
    obc  polygon count (0 = "until the end word", MAME geo_object_data)

Polygon data (MAME model2_v.cpp geo_parse_np_ns + model2_3d_process_polygon): a strip.
    P0, P1 (3 floats each), then per link 10 words: attribute, normal (3 floats), P0(n), P1(n).
    attribute bit 0 quad, bit 1 triangle (both 0 = end), bits 8-9 link type (0 = connector, not drawn),
    bits 10-11 z-sort mode, bits 12-16 signed texture-header step, bit 17 double sided,
    bits 18-22 texture-parameter (light) index, bits 27-31 LOD coefficient index.
"""
import os
import numpy as np
from daytona_paths import OUT

OBJTAB = 0x83FBB4
OBJTAB_END = 0x84F4EC

_c = {}


def region(name, dtype):
    k = (name, dtype)
    if k not in _c:
        _c[k] = np.fromfile(os.path.join(OUT, name + ".bin"), dtype=dtype)
    return _c[k]


def object_table():
    main = region("main_data", "<u4")
    t = main[OBJTAB // 4:OBJTAB_END // 4].reshape(-1, 5)
    return [tuple(int(x) for x in r[:4]) for r in t]


def decode_object(oba, obc=0, maxp=100000):
    """-> (polys, end word index). polys = list of (verts [3 or 4 xyz tuples], attr, normal, drawn)
    Vertex order as the rasterizer sees it: v0 = P1(n-1), v1 = P0(n-1), v2 = P0(n), v3 = P1(n)."""
    poly = region("polygons", "<u4"); pf = poly.view("<f4")
    a = oba & 0x3FFFFF
    p0 = tuple(float(v) for v in pf[a:a + 3]); p1 = tuple(float(v) for v in pf[a + 3:a + 6])
    a += 6
    out = []
    lim = min(obc if obc else 0xFFFFF, maxp)
    while len(out) < lim:
        attr = int(poly[a])
        if (attr & 3) == 0:
            break
        nrm = tuple(float(v) for v in pf[a + 1:a + 4])
        q0 = tuple(float(v) for v in pf[a + 4:a + 7])
        if attr & 1:
            q1 = tuple(float(v) for v in pf[a + 7:a + 10])
            out.append(([p1, p0, q0, q1], attr, nrm))
        else:
            q1 = q0
            out.append(([p1, p0, q0], attr, nrm))
        lt = (attr >> 8) & 3
        if lt in (0, 2): p0, p1 = q0, q1
        elif lt == 1: p1 = q0
        else: p0 = q1
        a += 10
    return out, a


if __name__ == "__main__":
    tab = object_table()
    print("objects", len(tab))
    for k, (oba, tpa, tha, obc) in enumerate(tab):
        if oba & 0x800000 == 0:
            print("%4d oba=%06X tpa=%06X tha=%06X obc=%4d  (polygon RAM)" % (k, oba, tpa, tha, obc)); continue
        polys, end = decode_object(oba, obc)
        if not polys:
            print("%4d oba=%06X tpa=%06X tha=%06X obc=%4d empty" % (k, oba, tpa, tha, obc)); continue
        v = np.array([p for vs, a, n in polys for p in vs])
        mn = v.min(0); mx = v.max(0)
        print("%4d oba=%06X tpa=%06X tha=%06X obc=%4d dec=%4d min(%9.1f %9.1f %9.1f) max(%9.1f %9.1f %9.1f)" % (
            k, oba, tpa, tha, obc, len(polys), mn[0], mn[1], mn[2], mx[0], mx[1], mx[2]))
