"""Export SEGA Rally 2 (Model 3) courses to OBJ straight from ROM.
Sources of truth: block tables in fixed CROM (see m3_tables.py), polygon format per Supermodel New3D.
Output coordinates: metres, Y up, right-handed (game Z negated).
usage: m3_export.py [course index 0-4 | all] [lod]
"""
import sys, os, numpy as np
sys.path.insert(0, ".")
from m3_scene import decode_model, O
from m3_tables import descriptors, records, GROUPS
S = os.path.dirname(os.path.dirname(O.rstrip("/")))
OUT = S + "/obj/"
os.makedirs(OUT, exist_ok=True)
vrom = np.fromfile(O + "vrom_le.bin", dtype="<u4")

def s24(v):
    v >>= 8
    return v - 0x1000000 if v & 0x800000 else v

def export(ci, lod=0):
    name = "sr2_course%d_lod%d" % (ci, lod)
    fo = open(OUT + name + ".obj", "w")
    fm = open(OUT + name + ".mtl", "w")
    fo.write("# SEGA Rally 2 (srally2) course table index %d, LOD %d. Units metres, Y up, Z = -gameZ\nmtllib %s.mtl\n" % (ci, lod, name))
    mats = {}
    nv = 0; nvt = 0; nf = 0; ntri = 0; nquad = 0; bad = 0
    allmin = np.full(3, 1e9); allmax = np.full(3, -1e9)
    stats = {}
    centre_line = []
    for g, label in (("B", "road"), ("A", "scenery")):
        n, kind, ptr = descriptors(GROUPS[g])[ci]
        recs = records(ptr, n)
        gf = 0; gmin = np.full(3, 1e9); gmax = np.full(3, -1e9); nblocks = 0
        for ri, (xyz, w, lods) in enumerate(recs):
            if g == "B": centre_line.append(xyz)
            cand = [lods[lod]] + lods
            addr = next((a for a, _ in cand if a != 0xFFFFFFFF), None)
            if addr is None: continue
            polys, ok = decode_model(vrom, addr)
            if not ok: bad += 1
            if not polys: continue
            nblocks += 1
            fo.write("o %s_%04d_%06X\n" % (label, ri, addr))
            vmap = {}; tmap = {}
            vlines = []; tlines = []; flines = []
            curm = None
            for vs, h in polys:
                tex = bool(h[6] & 0x400)
                tw = 32 << (((h[3] >> 3) & 7) if ((h[3] >> 3) & 7) < 6 else 0)
                th = 32 << ((h[3] & 7) if (h[3] & 7) < 6 else 0)
                tx = (32 * (((h[4] & 0x1F) << 1) | ((h[5] >> 7) & 1))) & 2047
                ty = (32 * (h[5] & 0x1F)) & 2047
                page = (h[4] >> 6) & 1
                fmt = (h[6] >> 7) & 7
                uvs = 1.0 if (h[1] & 0x40) else 0.125
                if tex:
                    m = "tex_p%d_x%04d_y%04d_%dx%d_f%d" % (page, tx, ty, tw, th, fmt)
                    col = (0.8, 0.8, 0.8)
                else:
                    if h[1] & 2:
                        col = ((h[4] >> 24) / 255.0, ((h[4] >> 16) & 255) / 255.0, ((h[4] >> 8) & 255) / 255.0)
                        m = "col_%06X" % (h[4] >> 8)
                    else:
                        col = (0.5, 0.5, 0.5); m = "pal_%03X" % ((h[4] >> 8) & 0xFFF)
                if m not in mats:
                    mats[m] = col
                    fm.write("newmtl %s\nKd %.3f %.3f %.3f\n" % ((m,) + col))
                    if tex: fm.write("map_Kd textures/%s.png\n" % m)
                if m != curm:
                    flines.append("usemtl %s" % m); curm = m
                idx = []
                P = []
                for (x, y, z, u, v) in vs:
                    wx, wy, wz = x + xyz[0], y + xyz[1], -(z + xyz[2])
                    P.append((wx, wy, wz))
                    key = (round(wx, 4), round(wy, 4), round(wz, 4))
                    vi = vmap.get(key)
                    if vi is None:
                        vi = nv + len(vlines) + 1; vmap[key] = vi
                        vlines.append("v %.4f %.4f %.4f" % (wx, wy, wz))
                    tk = (u * uvs / tw, 1.0 - v * uvs / th)
                    ti = tmap.get(tk)
                    if ti is None:
                        ti = nvt + len(tlines) + 1; tmap[tk] = ti
                        tlines.append("vt %.5f %.5f" % tk)
                    idx.append((vi, ti))
                # orient using header face normal (2.22 fixed), in exported space (z negated)
                P = np.array(P)
                nrm = np.cross(P[1] - P[0], P[2] - P[0])
                hn = np.array([s24(h[1]), s24(h[2]), -s24(h[3])], dtype=float)
                if np.dot(nrm, hn) < 0: idx = idx[::-1]
                flines.append("f " + " ".join("%d/%d" % t for t in idx))
                if len(idx) == 4: nquad += 1
                else: ntri += 1
                gmin = np.minimum(gmin, P.min(0)); gmax = np.maximum(gmax, P.max(0))
            fo.write("\n".join(vlines) + "\n" + "\n".join(tlines) + "\n" + "\n".join(flines) + "\n")
            nv += len(vlines); nvt += len(tlines); gf += len(polys)
        stats[label] = (nblocks, gf, gmin, gmax)
        allmin = np.minimum(allmin, gmin); allmax = np.maximum(allmax, gmax)
    fo.close(); fm.close()
    cl = np.array(centre_line); cl[:, 2] *= -1
    np.savetxt(OUT + "sr2_course%d_centreline.csv" % ci, cl, fmt="%.4f", delimiter=",", header="x,y,z (road block centres, metres, Z negated like the OBJ)")
    seg = np.linalg.norm(np.diff(cl, axis=0), axis=1)
    print("course %d lod %d -> %s.obj : verts=%d faces=%d (quads=%d tris=%d) materials=%d undecodable=%d" % (ci, lod, name, nv, nquad + ntri, nquad, ntri, len(mats), bad))
    for k, (nb, gf, a, b) in stats.items():
        print("   %-8s blocks=%4d faces=%6d bbox x[%.0f..%.0f] y[%.0f..%.0f] z[%.0f..%.0f]  size %.0f x %.0f x %.0f m" % (k, nb, gf, a[0], b[0], a[1], b[1], a[2], b[2], b[0] - a[0], b[1] - a[1], b[2] - a[2]))
    print("   road centre-line: %d pts, length %.0f m, first->last gap %.0f m, step median %.1f max %.1f" % (len(cl), seg.sum(), np.linalg.norm(cl[0] - cl[-1]), np.median(seg), seg.max()))

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    lod = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    for ci in (range(5) if which == "all" else [int(which)]):
        export(ci, lod)
