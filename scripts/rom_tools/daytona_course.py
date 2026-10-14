"""Daytona USA: per-course gameplay tables found so far (own findings; docs/kb/daytona_usa_rom_data.md).

Course directory: main data 0x600020 + 0x20 * course id (program 0x4770 holds the four addresses), 8 pointers.
  word 4 -> table of 8 {pointer, count} pairs = eight driving lines of the computer cars.
  A driving-line record is 28 bytes: x, y, z (float, game axes, metres), a float (0.6 .. 1.42), and six 16-bit
  values (not decoded).

    python daytona_course.py beginner      -> <COURSES>/<course>/daytona_<course>_line<N>.csv , _centreline.csv, views.json
views.json = camera positions for daytona_render.py: an overview, a plan, views along driving line 0 and one view per
landmark texture (found by the tile name in the exported OBJ).
"""
import os, sys, json, struct
import numpy as np
from daytona_paths import COURSES, OUT

DIRECTORY = 0x600020
COURSE_ID = {"beginner": 0, "expert": 1, "advanced": 2}
# tile name prefix -> (view name, distance in metres from the textured polygons, along their visible side)
LANDMARKS = {
    "beginner": [("tex_s0_x0256_y0000_128x256", "sonic_rock", 55), ("tex_s0_x1088_y0000_64x256", "slot_machine_sign", 45),
                 ("tex_s1_x0832_y0384_64x64", "start_gantry", 60), ("tex_s0_x0256_y0512_64x256", "pit_boards", 40)],
    "advanced": [("tex_s0_x0768_y0256_256x256", "fossil_sign", 30), ("tex_s0_x0896_y0768_128x256", "dinosaur_skeleton", 35),
                 ("tex_s0_x0768_y0128_256x128", "caution_dinosaur", 30), ("tex_s0_x0512_y0896_256x128", "sega_wall", 30)],
    "expert": [((-1028.0, 100.0, 868.0), "jeffry_statue", 75), ("tex_s0_x0256_y0000_128x256", "am2_shutter", 30),
               ("tex_s0_x0768_y0128_256x128", "bridge", 70)],
}
_d = None


def data():
    global _d
    if _d is None: _d = open(os.path.join(OUT, "main_data.bin"), "rb").read()
    return _d


def directory(cid):
    return struct.unpack_from("<8I", data(), DIRECTORY + 0x20 * cid)


def lines(cid):
    """-> list of 8 arrays [n, 4] (x, y, z, value)"""
    d = data(); t = directory(cid)[4] - 0x02000000
    out = []
    for i in range(8):
        p, n = struct.unpack_from("<II", d, t + 8 * i)
        a = np.frombuffer(d, "<f4", n * 7, p - 0x02000000).reshape(n, 7)[:, :4]
        out.append(a.astype(np.float64))
    return out


def centreline(cid):
    """mean of the eight driving lines, point by point (they have the same count and run side by side)"""
    L = lines(cid)
    return np.mean([l[:, :3] for l in L], axis=0)


def landmark_views(course):
    """one view per landmark tile: stand on the visible side of its polygons and look at them"""
    path = os.path.join(COURSES, course, "daytona_%s.obj" % course)
    if not os.path.exists(path): return []
    V = []; faces = {}; cur = None
    want = LANDMARKS.get(course, [])
    for line in open(path):
        if line.startswith("v "): V.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("usemtl "):
            cur = None
            for pre, name, dist in want:
                if isinstance(pre, str) and line.split()[1].startswith(pre): cur = name
        elif line.startswith("f ") and cur:
            faces.setdefault(cur, []).append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
    V = np.array(V) * np.array([1.0, 1.0, -1.0])          # back to game axes
    out = []
    for pre, name, dist in want:
        if not isinstance(pre, str):
            # a point: look at it from the side of the nearest driving-line point
            c = np.array(pre, np.float64); L = lines(COURSE_ID[course])[0][:, :3]
            d = L[np.argmin(np.linalg.norm(L[:, [0, 2]] - c[[0, 2]], axis=1))] - c; d[1] = 0; d /= np.linalg.norm(d)
            pos = c + d * dist; pos[1] = c[1] + 0.1 * dist
            out.append(dict(name="landmark_" + name, pos=[float(v) for v in pos], target=[float(v) for v in c], lens=28))
            continue
        fs = faces.get(name)
        if not fs: continue
        c0 = V[fs[0]].mean(0)
        near = [f for f in fs if np.linalg.norm(V[f].mean(0) - c0) < 60]
        c = np.mean([V[f].mean(0) for f in near], axis=0)
        n = np.zeros(3)
        for f in near:
            P = V[f]; g = np.cross(P[1] - P[0], P[2] - P[0]); n += -g       # OBJ faces are counter-clockwise in OBJ axes = clockwise in game axes
        n[1] = 0
        if np.linalg.norm(n) < 1e-6: n = np.array([1.0, 0, 0])
        n /= np.linalg.norm(n)
        pts = np.concatenate([V[f] for f in near])
        dist = max(dist, 1.6 * float((pts.max(0) - pts.min(0)).max()))
        pos = c + n * dist; pos[1] = c[1] + 0.12 * dist + 2
        out.append(dict(name="landmark_" + name, pos=[float(v) for v in pos], target=[float(v) for v in c], lens=28))
    return out


def views(course, n=8):
    """camera positions in game axes"""
    cid = COURSE_ID[course]
    L = lines(cid)[0][:, :3]
    out = []
    mn = L.min(0); mx = L.max(0); c = (mn + mx) / 2; size = max(mx[0] - mn[0], mx[2] - mn[2])
    out.append(dict(name="overview", pos=[c[0] - size * 0.3, mx[1] + size * 0.95, c[2] - size * 1.0], target=[c[0], c[1], c[2]], lens=28))
    out.append(dict(name="plan", pos=[c[0], mx[1] + 3000, c[2]], target=[c[0], 0, c[2]], ortho=size * 1.35, w=1400, h=1400))
    m = len(L)
    for k in range(n):
        i = (k * m) // n + 2
        a = L[(i - 2) % m]; b = L[(i + 8) % m]
        out.append(dict(name="road_%02d_wp%03d" % (k + 1, i), pos=[a[0], a[1] + 2.0, a[2]], target=[b[0], b[1] + 1.5, b[2]], lens=20))
    return out + landmark_views(course)


if __name__ == "__main__":
    course = sys.argv[1]
    cid = COURSE_ID[course]
    folder = os.path.join(COURSES, course)
    os.makedirs(folder, exist_ok=True)
    for i, l in enumerate(lines(cid)):
        np.savetxt(os.path.join(folder, "daytona_%s_line%d.csv" % (course, i)), l, fmt="%.4f", delimiter=",", header="x,y,z (game axes, metres),value")
    cl = centreline(cid)
    np.savetxt(os.path.join(folder, "daytona_%s_centreline.csv" % course), cl, fmt="%.4f", delimiter=",", header="x,y,z (game axes) mean of the 8 driving lines")
    seg = np.linalg.norm(np.diff(np.vstack([cl, cl[:1]]), axis=0), axis=1)
    print("%s: %d points, lap %.1f m (closed), y %.1f .. %.1f" % (course, len(cl), seg.sum(), cl[:, 1].min(), cl[:, 1].max()))
    v = views(course, int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    json.dump(v, open(os.path.join(folder, "views.json"), "w"), indent=1)
    print("   views:", ", ".join(x["name"] for x in v))
