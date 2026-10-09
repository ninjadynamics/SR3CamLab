"""Export SEGA Rally Championship (Model 2, srallyc) courses to OBJ straight from ROM.
Each course = 60 world-space section objects (hi detail) + 60 low-detail twins, found via the object table
in main_data @0x864B48. Output: metres(?) Y up, right-handed (game Z negated)."""
import sys, os, numpy as np
sys.path.insert(0, ".")
from m2_objs import object_table, decode_object, O
S = os.path.dirname(os.path.dirname(O.rstrip("/")))
OUT = S + "/obj/"
tex16 = np.fromfile(O + "textures.bin", dtype="<u2")
# (name, hi-detail object range, low-detail object range, background objects)
# Numbered in the order of the collision blocks in copro_data (= order of the per-course tables; presumably the
# game's course order). Matching of visual object ranges to collision blocks was verified by proximity.
COURSES = [("1", (1259, 1318), (1319, 1378), (1257, 1258)),
           ("2", (937, 996), (1000, 1059), (997, 998, 999)),
           ("3", (1379, 1438), (1441, 1500), (1439, 1440)),
           ("4", (1135, 1194), (1197, 1256), (1195, 1196))]

def export(name, rng, tag):
    tab = object_table()
    base = "src_course%s_%s" % (name, tag)
    fo = open(OUT + base + ".obj", "w"); fm = open(OUT + base + ".mtl", "w")
    fo.write("# SEGA Rally Championship (srallyc) course %s %s detail, objects %d..%d. Y up, Z = -gameZ\nmtllib %s.mtl\n" % (name, tag, rng[0], rng[1], base))
    nv = nvt = 0; nq = nt = 0; mats = {}
    mn = np.full(3, 1e9); mx = np.full(3, -1e9)
    up = 0; tot = 0
    for k in range(rng[0], rng[1] + 1):
        oba, obc, tpa, tha = tab[k]
        polys, _ = decode_object(oba, obc)
        fo.write("o sec_%04d\n" % k)
        vmap = {}; vl = []; tl = []; fl = []; curm = None
        tp = tpa; th = tha
        for vs, attr, nrm in polys:
            n = len(vs)
            uv = [(int(tex16[tp + 2 * i + 1]), int(tex16[tp + 2 * i])) for i in range(n)]   # (u, v); stored v,u
            tp += 2 * n
            h = [int(x) for x in tex16[th:th + 4]]
            tho = (attr >> 12) & 0x1F
            if tho & 0x10: tho -= 32
            th += tho * 4
            if ((attr >> 8) & 3) == 0: continue      # link type 0 = strip connector, never drawn
            textured = (h[0] >> 14) & 1
            tw = 32 << (h[0] & 7); thh = 32 << ((h[0] >> 3) & 7)
            tx = 32 * (h[2] & 0x3F); ty = 32 * ((h[2] >> 6) & 0x1F); sheet = (h[2] >> 12) & 1
            cb = (h[3] >> 6) & 0x3FF
            m = ("tex_s%d_x%04d_y%04d_%dx%d_c%03X" % (sheet, tx, ty, tw, thh, cb)) if textured else ("col_%03X" % cb)
            if m not in mats:
                mats[m] = 1
                fm.write("newmtl %s\nKd 0.8 0.8 0.8\n" % m)
                if textured: fm.write("map_Kd textures/%s.png\n" % m)
            if m != curm: fl.append("usemtl %s" % m); curm = m
            P = np.array([(x, y, -z) for (x, y, z) in vs])
            idx = []
            for i in range(n):
                key = tuple(np.round(P[i], 4))
                vi = vmap.get(key)
                if vi is None:
                    vi = nv + len(vl) + 1; vmap[key] = vi; vl.append("v %.4f %.4f %.4f" % tuple(P[i]))
                tl.append("vt %.5f %.5f" % (uv[i][0] / 8.0 / tw, 1.0 - uv[i][1] / 8.0 / thh))
                idx.append((vi, nvt + len(tl)))
            g = np.cross(P[1] - P[0], P[2] - P[0])
            hn = -np.array([nrm[0], nrm[1], -nrm[2]])   # stored normal points away from the viewer; negate for outward
            if np.dot(g, hn) < 0: idx = idx[::-1]
            if hn[1] > 0.5: up += 1
            tot += 1
            fl.append("f " + " ".join("%d/%d" % t for t in idx))
            if n == 4: nq += 1
            else: nt += 1
            mn = np.minimum(mn, P.min(0)); mx = np.maximum(mx, P.max(0))
        fo.write("\n".join(vl + tl + fl) + "\n")
        nv += len(vl); nvt += len(tl)
    fo.close(); fm.close()
    print("course %s %-4s -> %s.obj: objects=%d verts=%d faces=%d (quads=%d tris=%d) materials=%d  bbox x[%.0f..%.0f] y[%.0f..%.0f] z[%.0f..%.0f] size %.0f x %.0f x %.0f ; faces with normal.y>0.5: %d%%" % (
        name, tag, base, rng[1] - rng[0] + 1, nv, nq + nt, nq, nt, len(mats), mn[0], mx[0], mn[1], mx[1], mn[2], mx[2], mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2], 100 * up // max(tot, 1)))

if __name__ == "__main__":
    for name, hi, lo, bg in COURSES:
        export(name, hi, "hi"); export(name, lo, "low")
