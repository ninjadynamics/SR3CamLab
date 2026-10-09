"""srallyc copro_data (mpr-17754/17755): per-course collision/height polygons.
Layout found by inspection of the user's ROM (not documented anywhere I found):
  block: u32 N (cells), pad to 0x40, then N cells.
  cell : K polygon records of 16 floats (4 xyz corners + 4 floats; for flat 'P' records the 4 floats are an
         unnormalised plane a,b,c,d with a*x+b*y+c*z+d=0), followed by ONE info record of 16 u32:
         K attribute words (low bits = vertex count 3/4, bit 23 = flag seen on off-road quads), rest 0x77777777.
Exports each course as OBJ grouped by attribute word and a centre-line CSV."""
import sys, os, numpy as np
from collections import Counter
O = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic/out/m2/"
OUT = os.path.dirname(os.path.dirname(O.rstrip("/"))) + "/obj/"
c = np.fromfile(O + "copro_data.bin", dtype="<u4")[:0x100000 // 4]
f = c.view("<f4")

def is_info(w):
    seen77 = False
    for x in w:
        x = int(x)
        if x == 0x77777777: seen77 = True; continue
        if seen77: return False
        if (x >> 24) != 0 or (x & 0xFFFF) not in (3, 4): return False
    return True

off = 0; ci = 0
while off + 0x40 < len(c) * 4:
    n = int(c[off // 4])
    if n == 0 or n > 5000: print("stop at %06X word=%08X" % (off, n)); break
    pos = (off + 0x40) // 4
    cells = []
    ok = True
    for k in range(n):
        recs = []
        while True:
            w = c[pos:pos + 16]
            if is_info(w):
                attrs = [int(x) for x in w if int(x) != 0x77777777]
                pos += 16
                while len(attrs) < len(recs) and is_info(c[pos:pos + 16]):   # >16 polys: attribute words spill over
                    attrs += [int(x) for x in c[pos:pos + 16] if int(x) != 0x77777777]; pos += 16
                break
            recs.append(f[pos:pos + 16].copy()); pos += 16
            if len(recs) > 64: ok = False; break
        if not ok: break
        if len(attrs) != len(recs): ok = False; print("  cell %d: %d recs vs %d attrs" % (k, len(recs), len(attrs)))
        cells.append((recs, attrs))
    name = "12345678"[ci]
    attrc = Counter(a for r, a in cells for a in a)
    groups = {}
    cl = []
    planes_ok = planes_n = 0
    for recs, attrs in cells:
        roadpts = []
        for rec, a in zip(recs, attrs):
            nv = a & 0xFFFF
            P = rec[:12].reshape(4, 3)[:nv]
            groups.setdefault(a, []).append(P)
            nrm = rec[12:15]; d = rec[15]
            planes_n += 1
            ln = np.linalg.norm(nrm)
            if ln > 1e-6 and (np.abs(P @ nrm + d) / ln).max() < 0.05: planes_ok += 1
            if not (a & 0x800000): roadpts.append(P)
        if roadpts: cl.append(np.concatenate(roadpts).mean(0))
    fo = open(OUT + "src_course%s_collision.obj" % name, "w")
    fo.write("# srallyc copro_data collision polygons, block @%06X, %d cells. Y up, Z = -gameZ. Groups = attribute word\n" % (off, n))
    vi = 1; nq = 0
    allp = []
    for a, plist in sorted(groups.items()):
        fo.write("o attr_%08X\n" % a)
        for P in plist:
            for p in P: fo.write("v %.4f %.4f %.4f\n" % (p[0], p[1], -p[2]))
            fo.write("f " + " ".join(str(vi + i) for i in range(len(P) - 1, -1, -1)) + "\n"); vi += len(P); nq += 1
            allp.append(P)
    fo.close()
    allp = np.concatenate(allp)
    cl = np.array(cl); cl[:, 2] *= -1
    np.savetxt(OUT + "src_course%s_centreline.csv" % name, cl, fmt="%.4f", delimiter=",", header="x,y,z mean of collision polys without bit 23 per cell (Z negated like OBJ)")
    seg = np.linalg.norm(np.diff(cl, axis=0), axis=1)
    print("course %s block @%06X..%06X cells=%d parsed_ok=%s polys=%d plane-eq holds for %d/%d | bbox x[%.0f..%.0f] y[%.0f..%.0f] z[%.0f..%.0f] | centre-line %d pts length %.0f m closing gap %.0f step median %.1f max %.1f" % (
        name, off, pos * 4, n, ok, nq, planes_ok, planes_n, allp[:, 0].min(), allp[:, 0].max(), allp[:, 1].min(), allp[:, 1].max(), allp[:, 2].min(), allp[:, 2].max(), len(cl), seg.sum(), np.linalg.norm(cl[0] - cl[-1]), np.median(seg), seg.max()))
    print("    attribute words:", ", ".join("%08X x%d" % kv for kv in attrc.most_common(12)))
    # after the cells: index table, N x {count, offset of polys, offset of attrs, 0} relative to block start
    idx = c[pos:pos + 4 * n].reshape(n, 4)
    idx_ok = all(int(idx[k, 0]) == len(cells[k][0]) for k in range(n)) and int(idx[0, 1]) == 0x40
    print("    index table @%06X matches parsed cells: %s" % (pos * 4, idx_ok))
    off = pos * 4 + n * 16
    off = (off + 0x3F) & ~0x3F
    ci += 1
    if not ok: break
