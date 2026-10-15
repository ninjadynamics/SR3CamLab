"""Checks of the Daytona USA extraction that need no emulator: numbers that would be wrong if the decode were wrong.

    python daytona_check.py

1. Object table: the texture-header pointer of every record, advanced by the signed steps of its polygons, must land on
   the next record's pointer; the texture-point pointer must land on it too (records with a polygon count carry 8
   extra zero words for the end record).
2. Per course: the eight driving lines are closed loops; every point of them lies on a road-surface quad of the
   coprocessor ROM and on an upward-facing polygon of the exported course, at the same height.
3. Texture coordinates: share of textured polygons whose uv are degenerate (no area).
"""
import numpy as np
from daytona_objs import object_table, decode_object, region
from daytona_export import faces_of, COURSE
import daytona_course as DC
import daytona_collision as DCOL


def table_check():
    tab = object_table(); tex = region("textures", "<u2")
    th_ok = th_n = tp0 = tp8 = tp_n = 0
    for k in range(len(tab) - 1):
        oba, tpa, tha, obc = tab[k]
        if not (oba & 0x800000) or not (tab[k + 1][0] & 0x800000): continue
        polys, _ = decode_object(oba, obc)
        tp = tpa; th = tha
        for vs, attr, n in polys:
            tp += 2 * len(vs)
            tho = (attr >> 12) & 0x1F
            if tho & 0x10: tho -= 32
            th += tho * 4
        th_n += 1; th_ok += (th == tab[k + 1][2])
        tp_n += 1; tp0 += (tp == tab[k + 1][1]); tp8 += (tp + 8 == tab[k + 1][1])
    print("object table: %d records ; header pointer chain exact for %d of %d ; texture-point chain exact for %d, +8 words for %d, of %d" % (
        len(tab), th_ok, th_n, tp0, tp8, tp_n))


def height_under(P, polys):
    """polys: list of N x 3 (game axes). -> for each point the height of the polygon under it closest to the point's y"""
    lo = np.array([p[:, [0, 2]].min(0) for p in polys]); hi = np.array([p[:, [0, 2]].max(0) for p in polys])
    out = np.full(len(P), np.nan)
    for i, pt in enumerate(P):
        cand = np.nonzero((lo[:, 0] <= pt[0]) & (hi[:, 0] >= pt[0]) & (lo[:, 1] <= pt[2]) & (hi[:, 1] >= pt[2]))[0]
        best = None
        for j in cand:
            q = polys[j]
            # fan triangles
            for a in range(1, len(q) - 1):
                A, B, C = q[0], q[a], q[a + 1]
                v0 = B[[0, 2]] - A[[0, 2]]; v1 = C[[0, 2]] - A[[0, 2]]; v2 = pt[[0, 2]] - A[[0, 2]]
                den = v0[0] * v1[1] - v1[0] * v0[1]
                if abs(den) < 1e-9: continue
                s = (v2[0] * v1[1] - v1[0] * v2[1]) / den; t = (v0[0] * v2[1] - v2[0] * v0[1]) / den
                if s >= -1e-4 and t >= -1e-4 and s + t <= 1 + 1e-4:
                    y = A[1] + s * (B[1] - A[1]) + t * (C[1] - A[1])
                    if best is None or abs(y - pt[1]) < abs(best - pt[1]): best = y
        if best is not None: out[i] = best
    return out


def course_check(course):
    cid, first = COURSE[course]
    L = DC.lines(cid)
    tab = object_table()
    vis = []; ntex = ndeg = 0
    for i in range(256):
        for f in faces_of(first + i, tab):
            P = np.array(f["verts"])
            if f["mat"]["textured"]:
                ntex += 1
                uv = np.array(f["uv"])
                a = abs(np.cross(uv[1] - uv[0], uv[2] - uv[0])) + (abs(np.cross(uv[2] - uv[0], uv[3] - uv[0])) if len(uv) == 4 else 0)
                ndeg += a < 1e-6
            g = sum(np.cross(P[a], P[(a + 1) % len(P)]) for a in range(len(P)))      # Newell: also right when two corners coincide
            ln = np.linalg.norm(g)
            if ln > 1e-9 and abs(g[1]) / ln > 0.5: vis.append(P)          # floor-like polygons (either winding)
    Q, C, last = DCOL.quads(cid)
    col = [q for q in Q]
    print("%s (course id %d)" % (course, cid))
    print("   textured polygons %d, with degenerate uv %d (%.2f%%)" % (ntex, ndeg, 100.0 * ndeg / max(ntex, 1)))
    for li in (0, 1, 5):
        P = L[li][:, :3]
        seg = np.linalg.norm(np.diff(np.vstack([P, P[:1]]), axis=0), axis=1)
        hv = height_under(P, vis); hc = height_under(P, col)
        dv = np.abs(hv - P[:, 1]); dc = np.abs(hc - P[:, 1])
        print("   driving line %d: %d points, closed length %.1f m, largest step %.1f m ; over a coprocessor quad: %d (height within 0.25 m: %d) ; "
              "over a floor polygon of the export: %d (height within 0.25 m: %d)" % (
                  li, len(P), seg.sum(), seg.max(), int(np.isfinite(hc).sum()), int((dc < 0.25).sum()), int(np.isfinite(hv).sum()), int((dv < 0.25).sum())))


if __name__ == "__main__":
    table_check()
    for c in ("beginner", "advanced", "expert"):
        course_check(c)
