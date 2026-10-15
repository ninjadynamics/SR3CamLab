"""Export the Daytona USA (set `daytona`, original Model 2) courses from the ROM region images:
one OBJ + MTL + PNG tiles per course, a materials.json, and a top-down plan picture.

    python daytona_build.py                      # once: region images from the unpacked chips
    python daytona_export.py beginner            # or advanced / expert / all

Output: <COURSES>/<course>/daytona_<course>.obj (+ .mtl, textures/, materials.json, placed_objects.json, plan.png)
        and daytona_<course>_lifted.obj, the same polygons with coplanar overlays moved 1.5 cm per layer, for viewing.
Axes of the OBJ: metres, Y up, Z = -(game Z) (the game is left-handed; this is the convention of the SEGA Rally
Championship exports). One `o` per 128 m cell of the course grid, then the placed objects.

How a course is stored: docs/kb/daytona_usa_rom_data.md.
"""
import os, sys, json
import numpy as np
from daytona_paths import COURSES
from daytona_objs import object_table, decode_object, region
import daytona_tex as T

# course id (RAM 0x501460) -> name, first object of its 16 x 16 cell grid (pointer tables at main data 0x84FCCC + 0x400 * id)
COURSE = {"beginner": (0, 2678), "expert": (1, 2422), "advanced": (2, 2166)}
CELL = 128.0
LIFT = 0.015        # metres per layer in the *_lifted.obj (overlays that lie exactly in the plane of another polygon)


def faces_of(k, tab=None):
    """decode object-table row k -> list of dict(verts (game axes), uv (texels u, v), mat key, attr, normal)"""
    tab = tab or object_table()
    tex = region("textures", "<u2")
    oba, tpa, tha, obc = tab[k]
    polys, _ = decode_object(oba, obc)
    out = []
    tp = tpa; th = tha
    for vs, attr, nrm in polys:
        n = len(vs)
        uv = [(int(tex[tp + 2 * i + 1]) / 8.0, int(tex[tp + 2 * i]) / 8.0) for i in range(n)]     # stored v, u ; 13.3 fixed
        tp += 2 * n
        h = [int(x) for x in tex[th:th + 4]]
        tho = (attr >> 12) & 0x1F
        if tho & 0x10: tho -= 32
        th += tho * 4
        if ((attr >> 8) & 3) == 0: continue                 # link type 0: strip connector, never drawn
        rend = (h[0] >> 13) & 3                             # bit 1 textured, bit 0 translucent
        mat = dict(textured=bool(rend & 2), translucent=bool(rend & 1), checker=(h[0] >> 15) & 1,
                   w=32 << (h[0] & 7), h=32 << ((h[0] >> 3) & 7), mx=(h[0] >> 8) & 1, my=(h[0] >> 9) & 1,
                   x=32 * (h[2] & 0x3F), y=32 * ((h[2] >> 6) & 0x1F), sheet=(h[2] >> 12) & 1,
                   cbase=(h[3] >> 6) & 0x3FF, lbase=h[1] & 0xFF, param=(attr >> 18) & 0x1F,
                   micro=(h[0] >> 12) & 1, hdr=h)
        out.append(dict(verts=vs, uv=uv, mat=mat, attr=attr, nrm=nrm, obj=k))
    return out


def mat_name(m):
    if not m["textured"]:
        return "col_c%03X_p%d%s%s" % (m["cbase"], m["param"], "_ck" if m["checker"] else "", "_t" if m["translucent"] else "")
    s = "tex_s%d_x%04d_y%04d_%dx%d_c%03X" % (m["sheet"], m["x"], m["y"], m["w"], m["h"], m["cbase"])
    if m["lbase"]: s += "_l%d" % m["lbase"]
    s += "_p%d" % m["param"]
    if m["mx"]: s += "_mx"
    if m["my"]: s += "_my"
    if m["checker"]: s += "_ck"
    if m["translucent"]: s += "_t"
    return s


def _clip_area(A, B):
    """area of the intersection of two convex polygons (N x 2 arrays)"""
    def ccw(P):
        x = P[:, 0]; y = P[:, 1]
        return P if (x * np.roll(y, -1) - np.roll(x, -1) * y).sum() >= 0 else P[::-1]
    out = [tuple(v) for v in ccw(A)]; B = ccw(B)
    for i in range(len(B)):
        px, py = B[i]; qx, qy = B[(i + 1) % len(B)]
        ex, ey = qx - px, qy - py
        inp = out; out = []
        if not inp: return 0.0
        for j in range(len(inp)):
            cx, cy = inp[j]; dx, dy = inp[(j + 1) % len(inp)]
            sc = ex * (cy - py) - ey * (cx - px); sd = ex * (dy - py) - ey * (dx - px)
            if sc >= 0: out.append((cx, cy))
            if (sc > 0 > sd) or (sc < 0 < sd):
                t = sc / (sc - sd); out.append((cx + t * (dx - cx), cy + t * (dy - cy)))
    if len(out) < 3: return 0.0
    o = np.array(out); x = o[:, 0]; y = o[:, 1]
    return 0.5 * abs((x * np.roll(y, -1) - np.roll(x, -1) * y).sum())


def lift_levels(polys, normals):
    """polys: list of N x 3 arrays, normals: unit outward normals. -> layer number per polygon: 0 = lies on nothing,
    k = lies in the plane of a larger polygon of layer k - 1 that faces the same way and that it overlaps."""
    n = len(polys)
    lvl = np.zeros(n, int)
    if n < 2: return lvl
    Nn = np.array(normals); C = np.array([p.mean(0) for p in polys])
    lo = np.array([p.min(0) for p in polys]); hi = np.array([p.max(0) for p in polys])
    area = np.array([0.5 * np.linalg.norm(np.cross(p[1] - p[0], p[2] - p[0]) + (np.cross(p[2] - p[0], p[3] - p[0]) if len(p) == 4 else 0)) for p in polys])
    ok = area > 1e-6
    cand = {}
    for i in range(n):
        if not ok[i]: continue
        m = ok & (Nn @ Nn[i] > 0.9995) & (np.abs((C - C[i]) @ Nn[i]) < 0.02)
        m &= (lo <= hi[i] - 1e-3).all(1) & (hi >= lo[i] + 1e-3).all(1)
        m[i] = False
        js = np.nonzero(m)[0]
        if len(js): cand[i] = js
    if not cand: return lvl
    order = sorted(cand, key=lambda i: (-area[i], i))
    rank = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: (-area[i], i)))}
    for i in order:
        nrm = Nn[i]
        u = np.cross(nrm, [0.0, 1.0, 0.0] if abs(nrm[1]) < 0.9 else [1.0, 0.0, 0.0]); u /= np.linalg.norm(u); v = np.cross(nrm, u)
        A = np.stack([polys[i] @ u, polys[i] @ v], 1)
        best = 0
        for j in cand[i]:
            if rank[j] > rank[i]: continue                  # only larger (or earlier, when equal) polygons can be underneath
            Bp = np.stack([polys[j] @ u, polys[j] @ v], 1)
            if _clip_area(A, Bp) > max(0.02 * area[i], 1e-4): best = max(best, lvl[j] + 1)
        lvl[i] = min(best, 6)
    return lvl


class _Obj:
    def __init__(self, path, header):
        self.f = open(path, "w"); self.f.write(header); self.nv = self.nvt = 0

    def write(self, name, items):
        """items: list of (material, points N x 3 (OBJ axes), uv N x 2 or None, reversed)"""
        vmap = {}; vl = []; tl = []; fl = []; cur = None
        for mname, Q, uv, rev in items:
            if mname != cur: fl.append("usemtl " + mname); cur = mname
            idx = []
            for i in range(len(Q)):
                key = (round(Q[i][0], 4), round(Q[i][1], 4), round(Q[i][2], 4))
                vi = vmap.get(key)
                if vi is None:
                    vi = self.nv + len(vl) + 1; vmap[key] = vi; vl.append("v %.4f %.4f %.4f" % key)
                if uv is not None:
                    tl.append("vt %.5f %.5f" % (uv[i][0], uv[i][1]))
                    idx.append("%d/%d" % (vi, self.nvt + len(tl)))
                else:
                    idx.append("%d" % vi)
            fl.append("f " + " ".join(idx[::-1] if rev else idx))
        self.f.write("o %s\n" % name + "\n".join(vl + tl + fl) + "\n")
        self.nv += len(vl); self.nvt += len(tl)


class Writer:
    def __init__(self, course_id, folder, base, header):
        from PIL import Image
        self.Image = Image
        self.cid = course_id; self.folder = folder; self.base = base
        os.makedirs(os.path.join(folder, "textures"), exist_ok=True)
        self.obj = _Obj(os.path.join(folder, base + ".obj"), header + "mtllib %s.mtl\n" % base)
        self.lifted = _Obj(os.path.join(folder, base + "_lifted.obj"), header + "# FOR VIEWING: polygons that lie exactly in the plane of a larger "
                           "one are moved %.3f m per layer towards their visible side (the 1995 hardware has no depth buffer)\nmtllib %s.mtl\n" % (LIFT, base))
        self.fm = open(os.path.join(folder, base + ".mtl"), "w")
        self.mats = {}; self.count = dict(objects=0, quads=0, tris=0, lifted=0)
        self.mn = np.full(3, 1e9); self.mx = np.full(3, -1e9)
        self.plan = []                      # (xz polygon, max y, rgb, opacity) for the top-down picture

    def material(self, m):
        name = mat_name(m)
        if name in self.mats: return name
        info = {k: m[k] for k in ("textured", "translucent", "checker", "w", "h", "mx", "my", "x", "y", "sheet", "cbase", "lbase", "param", "micro")}
        info["header"] = ["%04X" % x for x in m["hdr"]]
        if m["textured"]:
            img = T.tile_rgba(self.cid, m["sheet"], m["x"], m["y"], m["w"], m["h"], m["cbase"], m["lbase"], m["param"],
                              m["translucent"], m["mx"], m["my"])
            self.Image.fromarray(img, "RGBA").save(os.path.join(self.folder, "textures", name + ".png"))
            a = img[:, :, 3] > 0
            rgb = img[:, :, :3][a].mean(0) / 255.0 if a.any() else np.array([0.5, 0.5, 0.5])
            info["cover"] = float(a.mean())
            self.fm.write("newmtl %s\nKd 1 1 1\nKs 0 0 0\nmap_Kd textures/%s.png\n" % (name, name))
            if m["translucent"]: self.fm.write("map_d textures/%s.png\n" % name)
        else:
            rgb = np.array(T.solid_rgb(m["cbase"], m["param"])) / 255.0
            self.fm.write("newmtl %s\nKd %.4f %.4f %.4f\nKs 0 0 0\n" % (name, rgb[0], rgb[1], rgb[2]))
        if m["checker"]: self.fm.write("d 0.5\n")
        self.fm.write("\n")
        info["rgb"] = [round(float(x), 4) for x in rgb]
        info["faces"] = 0
        self.mats[name] = info
        return name

    def add(self, name, faces, xform=None):
        """faces from faces_of(); xform = function(points Nx3 game axes) -> Nx3 game axes (placed objects).
        Polygons with the double-sided bit (attribute bit 17) go to a second object named <name>_2s: the OBJ face
        itself has one side, the hardware draws those from both."""
        if not faces: return
        self.count["objects"] += 1
        items = []; polys = []; normals = []
        for f in faces:
            m = f["mat"]; mname = self.material(m)
            P = np.array(f["verts"], np.float64)
            N = np.array(f["nrm"], np.float64)
            if xform is not None:
                P2 = xform(P); N = (xform(P + N) - P2).mean(0); P = P2
            Q = P * np.array([1.0, 1.0, -1.0])
            uv = None
            if m["textured"]:
                W = m["w"] * (2 if m["mx"] else 1); H = m["h"] * (2 if m["my"] else 1)
                uv = np.array(f["uv"])
                uv = uv - np.floor(uv.min(0) / np.array([W, H])) * np.array([W, H])     # same picture, small numbers
                uv = np.stack([uv[:, 0] / W, 1.0 - uv[:, 1] / H], 1)
            # the stored normal points away from the viewer on the visible side (MAME: front when normal . point >= 0)
            g = np.cross(Q[1] - Q[0], Q[2] - Q[0])
            if len(Q) == 4 and np.linalg.norm(g) < 1e-9: g = np.cross(Q[2] - Q[0], Q[3] - Q[0])
            out_n = -np.array([N[0], N[1], -N[2]])
            rev = bool(np.dot(g, out_n) < 0)
            gl = np.linalg.norm(g)
            normals.append((-g if rev else g) / gl if gl > 1e-12 else np.array([0.0, 1.0, 0.0]))
            polys.append(Q); items.append((mname, Q, uv, rev))
            self.count["quads" if len(Q) == 4 else "tris"] += 1
            self.mn = np.minimum(self.mn, P.min(0)); self.mx = np.maximum(self.mx, P.max(0))
            info = self.mats[mname]; info["faces"] += 1
            if not (m["textured"] and info.get("cover", 1) < 0.02):
                self.plan.append((P[:, [0, 2]], float(P[:, 1].max()), info["rgb"], info.get("cover", 1.0) if m["translucent"] else 1.0))
        lv = lift_levels(polys, normals)                        # over the whole object, both groups together
        self.count["lifted"] += int((lv > 0).sum())
        two = [bool((f["attr"] >> 17) & 1) for f in faces]
        self.count["double_sided"] = self.count.get("double_sided", 0) + sum(two)
        lifted = [(mn_, Q + normals[i] * (LIFT * lv[i]), uv, rev) for i, (mn_, Q, uv, rev) in enumerate(items)]
        for suffix, keep in (("", False), ("_2s", True)):
            sel = [i for i in range(len(items)) if two[i] == keep]
            if not sel: continue
            self.obj.write(name + suffix, [items[i] for i in sel])
            self.lifted.write(name + suffix, [lifted[i] for i in sel])

    def close(self):
        self.obj.f.close(); self.lifted.f.close(); self.fm.close()
        json.dump(self.mats, open(os.path.join(self.folder, "materials.json"), "w"), indent=1)

    def plan_png(self, path, title, extra=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import PolyCollection
        order = sorted(range(len(self.plan)), key=lambda i: self.plan[i][1])
        polys = [self.plan[i][0] for i in order]
        cols = [tuple(self.plan[i][2]) + (max(0.25, min(1.0, self.plan[i][3])),) for i in order]
        sx = self.mx[0] - self.mn[0]; sz = self.mx[2] - self.mn[2]
        k = 14.0 / max(sx, sz)
        fig, ax = plt.subplots(figsize=(max(6, sx * k + 1), max(6, sz * k + 1)), dpi=130)
        ax.set_facecolor((0.07, 0.07, 0.09))
        ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors="none", antialiaseds=False))
        if extra: extra(ax)
        ax.set_xlim(self.mn[0] - 20, self.mx[0] + 20); ax.set_ylim(self.mn[2] - 20, self.mx[2] + 20)
        ax.set_aspect("equal"); ax.set_xlabel("game x (m)"); ax.set_ylabel("game z (m)")
        ax.set_title(title, fontsize=9)
        fig.savefig(path, bbox_inches="tight"); plt.close(fig)


def export(course):
    cid, first = COURSE[course]
    folder = os.path.join(COURSES, course)
    base = "daytona_" + course
    tab = object_table()
    w = Writer(cid, folder, base, "# Daytona USA (set daytona) course %d %s, object-table rows %d..%d + placed objects. "
               "Metres, Y up, Z = -gameZ\n" % (cid, course, first, first + 255))
    cells = 0
    for i in range(256):
        f = faces_of(first + i, tab)
        if not f: continue
        cells += 1
        w.add("cell_r%02d_c%02d" % (i // 16, i % 16), f)
    ncell = dict(w.count)
    try:
        import daytona_placed as P
        extra_info = P.add_placed(w, cid, tab)
    except ImportError:
        extra_info = None
    w.close()

    def overlay(ax):
        try:
            import daytona_course as C
        except ImportError:
            return
        L = C.lines(cid)[0]
        ax.plot(L[:, 0], L[:, 2], color=(1.0, 0.9, 0.1), lw=0.6)
        ax.plot([L[0, 0]], [L[0, 2]], "o", color=(1, 0.2, 0.2), ms=4)
        d = L[3, [0, 2]] - L[0, [0, 2]]
        ax.annotate("", xy=(L[0, 0] + d[0] * 2.5, L[0, 2] + d[1] * 2.5), xytext=(L[0, 0], L[0, 2]), arrowprops=dict(arrowstyle="->", color=(1, 0.2, 0.2)))
    w.plan_png(os.path.join(folder, "plan.png"), "Daytona USA - %s (course id %d): extracted polygons, driving line 0 (yellow), its first point and direction (red)" % (course, cid), overlay)
    print("%-9s cells with polygons %d, polygons %d (quads %d, tris %d) ; with placed objects: objects %d quads %d tris %d ; materials %d (textured %d)" % (
        course, cells, ncell["quads"] + ncell["tris"], ncell["quads"], ncell["tris"], w.count["objects"], w.count["quads"], w.count["tris"],
        len(w.mats), sum(1 for m in w.mats.values() if m["textured"])))
    print("          bbox game x[%.1f %.1f] y[%.1f %.1f] z[%.1f %.1f] ; double-sided polygons (objects *_2s): %d ; overlay polygons lifted in the _lifted.obj: %d  -> %s" % (
        w.mn[0], w.mx[0], w.mn[1], w.mx[1], w.mn[2], w.mx[2], w.count.get("double_sided", 0), w.count["lifted"], folder))
    if extra_info: print("          " + extra_info)
    return w


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for c in (COURSE if which == "all" else [which]):
        export(c)
