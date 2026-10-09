"""Model 2 srallyc: object table in main_data (@0x864B48, 16-byte entries {oba, obc, tpa, tha})
and polygon ROM strip decoder (format per MAME model2_v.cpp geo_parse_np_ns / model2_3d_process_polygon)."""
import numpy as np
O = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic/out/m2/"
main = np.fromfile(O + "main_data.bin", dtype="<u4")
poly = np.fromfile(O + "polygons.bin", dtype="<u4")
polyf = poly.view("<f4")
texrom = np.fromfile(O + "textures.bin", dtype="<u4")
OBJTAB = 0x864B48

def object_table(off=OBJTAB):
    out = []
    i = off // 4
    while True:
        oba, obc, tpa, tha = [int(x) for x in main[i:i + 4]]
        if not (0x00800000 <= oba < 0x00A00000) or obc > 0x10000: break
        out.append((oba, obc, tpa, tha)); i += 4
    return out

def decode_object(oba, obc, maxp=100000):
    """returns list of polys: (verts list of 3-tuples (3 or 4), attr, normal). Strip: P0,P1 then per link attr,normal,P2,P3."""
    a = oba & 0x7FFFFF
    p0 = tuple(float(v) for v in polyf[a:a + 3]); p1 = tuple(float(v) for v in polyf[a + 3:a + 6])
    a += 6
    out = []
    n = 0
    while n < min(obc if obc else 0xFFFFF, maxp):
        attr = int(poly[a])
        if (attr & 3) == 0: break
        nrm = tuple(float(v) for v in polyf[a + 1:a + 4])
        q0 = tuple(float(v) for v in polyf[a + 4:a + 7])
        if attr & 1:
            q1 = tuple(float(v) for v in polyf[a + 7:a + 10])
            out.append(([p1, p0, q0, q1], attr, nrm))   # MAME: v0=P1(n-1), v1=P0(n-1), v2=P0(n), v3=P1(n)
        else:
            q1 = q0   # triangle: P1(n) := P0(n)  (MAME copies P0(n) into the P1(n) slot)
            out.append(([p1, p0, q0], attr, nrm))
        lt = (attr >> 8) & 3          # link type, MAME model2_3d_process_polygon 'update linking'
        if lt in (0, 2): p0, p1 = q0, q1
        elif lt == 1: p1 = q0
        else: p0 = q1
        a += 10; n += 1
    return out, a

if __name__ == "__main__":
    tab = object_table()
    print("objects", len(tab), "oba range %06X..%06X" % (min(t[0] for t in tab) & 0x7FFFFF, max(t[0] for t in tab) & 0x7FFFFF), "total polys", sum(t[1] for t in tab))
    big = 0
    rows = []
    for k, (oba, obc, tpa, tha) in enumerate(tab):
        polys, end = decode_object(oba, obc)
        if not polys: rows.append((k, oba, obc, 0, None, None)); continue
        v = np.array([p for vs, a, n in polys for p in vs])
        rows.append((k, oba, obc, len(polys), v.min(0), v.max(0)))
    for r in rows[:40] + rows[300:330] + rows[-20:]:
        k, oba, obc, n, a, b = r
        if a is None: print(k, hex(oba), obc, "empty"); continue
        print("%4d oba=%06X obc=%4d dec=%4d  min(%8.1f %8.1f %8.1f) max(%8.1f %8.1f %8.1f)" % (k, oba & 0x7FFFFF, obc, n, a[0], a[1], a[2], b[0], b[1], b[2]))
    ext = np.array([np.abs(np.concatenate([r[4], r[5]])).max() for r in rows if r[4] is not None])
    print("objects with |coord|>100:", int((ext > 100).sum()), " >500:", int((ext > 500).sum()), "mismatch count:", sum(1 for r in rows if r[2] != r[3]))
