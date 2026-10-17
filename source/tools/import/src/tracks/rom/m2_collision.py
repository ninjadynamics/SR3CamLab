"""srallyc copro_data (mpr-17754/17755): per-course collision/height polygons.
Layout found by inspection of the user's ROM (not documented anywhere I found):
  block: u32 N (cells), pad to 0x40, then N cells.
  cell : K polygon records of 16 floats (4 xyz corners + 4 floats; for flat 'P' records the 4 floats are an
         unnormalised plane a,b,c,d with a*x+b*y+c*z+d=0), followed by ONE info record of 16 u32:
         K attribute words (low bits = vertex count 3/4, bit 23 = flag seen on off-road quads), rest 0x77777777.
Exports each course as OBJ grouped by attribute word and a centre-line CSV.
    python m2_collision.py    -> <classic>/obj/src_course<N>_collision.obj + src_course<N>_centreline.csv (N = block order: 1 Mountain 2 Desert 3 Lake Side 4 Forest)
Without numpy since 2026-10-15 (kb 31): the ROM's float32 numbers are read as they are; the means, lengths and plane tests that numpy did
in float32 are done here in float32 too (f32: each step computed in double and rounded to float32, which gives float32's own result for
+ - * / and sqrt, a double having more than twice its bits), in numpy's order. The files are byte for byte the numpy version's."""
import sys, os, math, struct
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'core')); import common   # tools/import/settings.json
O = os.path.join(common.TMP, 'm2') + '/'                          # region images (m2_build.py)
OUT = os.path.join(common.CLASSIC, 'obj') + '/'; os.makedirs(OUT, exist_ok=True)
raw = open(O + "copro_data.bin", "rb").read(0x100000)
c = memoryview(raw).cast("I")                                     # np.fromfile(..., '<u4')[:0x100000 // 4]
f = memoryview(raw).cast("f")                                     # c.view('<f4')
_F = struct.Struct('<f'); f32 = lambda x: _F.unpack(_F.pack(x))[0]
def pw32(v):
    """np.add.reduce of float32 numbers: numpy's pairwise sum (see rtbake/rt_bake_game5.py pwsum) with every addition in float32"""
    n = len(v)
    if n < 8:
        s = 0.0
        for x in v: s = f32(s + x)
        return s
    if n <= 128:
        r = list(v[:8]); e = n - n % 8
        for i in range(8, e, 8):
            for j in range(8): r[j] = f32(r[j] + v[i + j])
        s = f32(f32(f32(r[0] + r[1]) + f32(r[2] + r[3])) + f32(f32(r[4] + r[5]) + f32(r[6] + r[7])))
        for x in v[e:]: s = f32(s + x)
        return s
    h = n // 2; h -= h % 8
    return f32(pw32(v[:h]) + pw32(v[h:]))
def seq32(v):
    """the sum numpy makes down the columns of a C-ordered float32 array (mean(0)): one row after the other, from 0, in float32"""
    s = 0.0
    for x in v: s = f32(s + x)
    return s
def dot32(a, b):
    """a 3-vector product in float32 the way OpenBLAS's small kernels add it: (p0 + p2) + p1 (kb 31; it only decides a count printed)"""
    return f32(f32(f32(a[0] * b[0]) + f32(a[2] * b[2])) + f32(a[1] * b[1]))
def median(v):
    """np.median of float32 numbers: the middle one, or the float32 mean of the middle two"""
    v = sorted(v); n = len(v); return v[n // 2] if n % 2 else f32(f32(v[n // 2 - 1] + v[n // 2]) / 2)

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
            recs.append(f[pos:pos + 16].tolist()); pos += 16
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
            P = [rec[3 * i:3 * i + 3] for i in range(4)][:nv]           # rec[:12].reshape(4, 3)[:nv]
            groups.setdefault(a, []).append(P)
            nrm = rec[12:15]; d = rec[15]
            planes_n += 1
            ln = f32(math.sqrt(dot32(nrm, nrm)))                        # np.linalg.norm(nrm), float32
            if ln > 1e-6 and max(f32(abs(f32(dot32(p, nrm) + d)) / ln) for p in P) < 0.05: planes_ok += 1      # (np.abs(P @ nrm + d) / ln).max() < 0.05
            if not (a & 0x800000): roadpts += P
        if roadpts: cl.append([f32(seq32([p[k] for p in roadpts]) / len(roadpts)) for k in range(3)])     # np.concatenate(roadpts).mean(0), float32
    fo = open(OUT + "src_course%s_collision.obj" % name, "w")
    fo.write("# srallyc copro_data collision polygons, block @%06X, %d cells. Y up, Z = -gameZ. Groups = attribute word\n" % (off, n))
    vi = 1; nq = 0
    allp = []
    for a, plist in sorted(groups.items()):
        fo.write("o attr_%08X\n" % a)
        for P in plist:
            for p in P: fo.write("v %.4f %.4f %.4f\n" % (p[0], p[1], -p[2]))
            fo.write("f " + " ".join(str(vi + i) for i in range(len(P) - 1, -1, -1)) + "\n"); vi += len(P); nq += 1
            allp += P
    fo.close()
    for p in cl: p[2] = -p[2]                                          # cl[:, 2] *= -1
    with open(OUT + "src_course%s_centreline.csv" % name, "w") as fc:   # np.savetxt(..., fmt="%.4f", delimiter=",", header=...): text mode, as savetxt
        fc.write("# x,y,z mean of collision polys without bit 23 per cell (Z negated like OBJ)\n")
        for p in cl: fc.write("%.4f,%.4f,%.4f\n" % tuple(p))
    seg = [f32(math.sqrt(f32(f32(f32(f32(b[0] - a[0]) * f32(b[0] - a[0])) + f32(f32(b[1] - a[1]) * f32(b[1] - a[1]))) + f32(f32(b[2] - a[2]) * f32(b[2] - a[2]))))) for a, b in zip(cl, cl[1:])]      # np.linalg.norm(np.diff(cl, axis=0), axis=1)
    gap = [f32(cl[0][k] - cl[-1][k]) for k in range(3)]
    print("course %s block @%06X..%06X cells=%d parsed_ok=%s polys=%d plane-eq holds for %d/%d | bbox x[%.0f..%.0f] y[%.0f..%.0f] z[%.0f..%.0f] | centre-line %d pts length %.0f m closing gap %.0f step median %.1f max %.1f" % (
        name, off, pos * 4, n, ok, nq, planes_ok, planes_n, min(p[0] for p in allp), max(p[0] for p in allp), min(p[1] for p in allp), max(p[1] for p in allp), min(p[2] for p in allp), max(p[2] for p in allp),
        len(cl), pw32(seg), f32(math.sqrt(dot32(gap, gap))), median(seg), max(seg)))
    print("    attribute words:", ", ".join("%08X x%d" % kv for kv in attrc.most_common(12)))
    # after the cells: index table, N x {count, offset of polys, offset of attrs, 0} relative to block start
    idx = [c[pos + 4 * k:pos + 4 * k + 4] for k in range(n)]
    idx_ok = all(int(idx[k][0]) == len(cells[k][0]) for k in range(n)) and int(idx[0][1]) == 0x40
    print("    index table @%06X matches parsed cells: %s" % (pos * 4, idx_ok))
    off = pos * 4 + n * 16
    off = (off + 0x3F) & ~0x3F
    ci += 1
    if not ok: break
