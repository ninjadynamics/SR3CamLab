"""A Daytona USA (1994, Model 2) car as a SEGA Rally 3 car: staging folder with the car files, the ArcadeDatabase record,
the car's name in the text table, a manifest and install / uninstall scripts. Nothing is written to the game.

    python daytona_car.py <staging folder> [--livery hornet0] [--length 5.0 | --scale k] [--handling bowler] [--name Hornet]
           [--folder Hornet] [--light 255] [--density 0] [--id 10] [--sound ID_CAR_BOWLER]
      --livery   hornet0 (red / blue #41, rows 1460 + 1462), hornet1 (yellow / red, 1461 + 1463), hornetlink (1835 + 1793),
                 opp<k> (opponent livery k = 0..44, LOD0 row 4k), link<k> (linked-play Hornet k = 1..8, row 1803 + 4(k-1))
      --length   body length in metres (default 5.0; Daytona's own model is 4.93 m, its units are metres): the scale
                 follows; body, wheels, wheel data (hubs, radius, width), shells, shadows and lamps scale with it
      --scale    a scale factor instead (1.0 = Daytona's own size)
      --handling bowler | st205: whose handling file (bespoke_data) is used; its wheel chunk gets the Daytona wheels
      --light    Model 2 polygon luminance the colours are baked with (0..255; 174 = fully lit by the game's own car light)

Templates: the chassis, wheels, texture packs, mud / snow shells and bonnet are ST205's files (the smallest node set; test 1
ran them as "Hornet"); every id only ST205 / the handling donor uses gets a fresh id (car_clone.py).
What is built (docs/kb/daytona_usa_rom_data.md section 11; carmodel.py for the file layout):
  chassis  bodyshell, bodyshellx02, bodyshellx03 = the Daytona body (flat-shaded, one face per Model 2 polygon), its own
           1024 x 1024 atlas in place of ST205's livery texture: every polygon gets its own cell, the coplanar overlays
           (numbers, logos: Model 2 has no depth buffer) are painted into the cell of the polygon under them; translucent
           polygons (window nets) go into a second atlas with alpha and a copy of ST205's glass material; the glass nodes
           get empty meshes; rear lamps laid on the body's own rear panel (fit_rear_lamps); front lights and exhaust are
           ST205's meshes moved onto the Daytona body; suspension nodes at the Daytona hubs; shadows scaled to the
           Daytona size; tail record bounding box recomputed. Bodies without a cockpit (opponents, linked-play cars) get
           a dark inner skin, so their window openings and wheel arches do not show through the car.
  wheels   (<name>gravelmodel_data) the Daytona wheels 805 / 806 (tyre + 8-spoke rim) and 793 / 794 for the far LODs,
           with their own atlas; the blur discs = the rim, turned into a radial blur.
  handling (<name>gravel_data) the donor's bespoke_data with the wheel chunk (hub, centre, radius, width per wheel) set
           to the Daytona wheels.
  dirt     texture packs dust / mud / snow: the livery-dirt texture redrawn for the new atlas from ST205's (each texel
           takes ST205's dirt at the matching place of the car).
  mud/snow the shell over the body built from the Daytona body, attributes taken from ST205's shell at the matching place.
  bonnet   the Daytona bonnet seen from the bonnet camera, placed the way ST205's bonnet model sits relative to its body.
"""
import os, sys, json, struct, zlib, hashlib, argparse, math
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "daytona", "tracks", "rom"))
import sbfw, carmodel, arcadedb, langtable, texdxt, car_clone

GAME = car_clone.GAME
CARS = car_clone.CARS
ORIG_DB = os.path.join(GAME, "Main_release", "tracks", "_SR3Extras", "original", "arcadedatabase_xdata.sbf")

LIVERIES = {"hornet0": (1460, 1462), "hornet1": (1461, 1463), "hornetlink": (1835, 1793), "car99": (1836, None)}
DAY_WHEEL = dict(r=0.36, w=0.401, x_out=0.875, zf=1.412, zr=-1.395)
WHEEL_ROWS = {"l": (805, 793), "r": (806, 794)}


# ----------------------------------------------------------------------------------------------------- Daytona source
def day_faces(row):
    from daytona_objs import object_table
    from daytona_export import faces_of
    out = []
    for f in faces_of(row, object_table()):
        P = np.array(f["verts"], np.float64)
        n = -np.array(f["nrm"], np.float64); n /= max(np.linalg.norm(n), 1e-12)        # stored normal points inwards
        out.append(dict(P=P, uv=np.array(f["uv"], np.float64), mat=f["mat"], n=n, attr=f["attr"]))
    return out


class Tiles:
    """the Model 2 texture of a polygon (RGBA float, 0..1) baked at a fixed polygon luminance"""
    def __init__(self, light, hd=None):
        import daytona_tex as T
        self.T = T; self.light = light; self.cache = {}
        self.hd = os.path.abspath(hd) if hd else None; self.used_hd = {}
        T.poly_luma = lambda param, L=light: float(L)

    def tile(self, m):
        if not m["textured"]:
            return None
        k = (m["sheet"], m["x"], m["y"], m["w"], m["h"], m["cbase"], m["lbase"], m["translucent"], m["mx"], m["my"], m["param"], m["checker"])
        if k not in self.cache:
            img = self.T.tile_rgba(0, m["sheet"], m["x"], m["y"], m["w"], m["h"], m["cbase"], m["lbase"], m["param"],
                                   m["translucent"], m["mx"], m["my"])
            if self.hd:
                from daytona_export import mat_name
                from PIL import Image
                path = os.path.join(self.hd, mat_name(m) + ".png")
                if os.path.isfile(path):
                    with Image.open(path) as im: replacement = np.array(im.convert("RGBA"))
                    h, w = img.shape[:2]; hh, ww = replacement.shape[:2]
                    if ww < w or hh < h or ww % w or hh % h or ww // w != hh // h:
                        raise ValueError("HD tile must be a uniform integer upscale: " + path)
                    img = replacement
                    self.used_hd[os.path.basename(path)] = dict(width=ww, height=hh, scale=ww // w,
                                                               sha256=sha(open(path, "rb").read()))
            self.cache[k] = img.astype(np.float32) / 255.0
        return self.cache[k]

    def sample(self, m, uv):
        tile = self.tile(m)
        if tile is None: return np.tile(self.solid(m), (len(uv), 1))
        # Exported PNGs include mirrored halves; model UVs remain in original texels.
        w = m["w"] * (2 if m["mx"] else 1); h = m["h"] * (2 if m["my"] else 1)
        return sample(tile, uv[:, 0] * (tile.shape[1] / w), uv[:, 1] * (tile.shape[0] / h))

    def solid(self, m):
        return np.array(self.T.solid_rgb(m["cbase"], m["param"]) + [255.0], np.float32) / 255.0


def sample(tile, u, v):
    """bilinear, wrapping; u = column, v = row in texels"""
    H, W = tile.shape[:2]
    x = u - 0.5; y = v - 0.5
    x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64); fx = (x - x0)[..., None]; fy = (y - y0)[..., None]
    a = tile[y0 % H, x0 % W]; b = tile[y0 % H, (x0 + 1) % W]; c = tile[(y0 + 1) % H, x0 % W]; d = tile[(y0 + 1) % H, (x0 + 1) % W]
    # premultiplied, so transparent texels do not bleed their colour
    def pm(t): return np.concatenate([t[..., :3] * t[..., 3:4], t[..., 3:4]], -1)
    r = (pm(a) * (1 - fx) + pm(b) * fx) * (1 - fy) + (pm(c) * (1 - fx) + pm(d) * fx) * fy
    al = r[..., 3:4]
    return np.concatenate([np.where(al > 1e-6, r[..., :3] / np.maximum(al, 1e-6), 0), al], -1)


def overlay_layers(faces):
    """layer per face: 0 = lies on nothing; k = lies in the plane of a face of a lower layer that it overlaps (as the
    exporter's lift_levels), and ties between two equal faces broken by order"""
    from daytona_export import lift_levels, _clip_area
    polys = [f["P"] for f in faces]; normals = [f["n"] for f in faces]
    lv = lift_levels(polys, normals)
    n = len(faces)
    for i in range(n):
        for j in range(i + 1, n):
            if lv[i] != lv[j]: continue
            if faces[i]["n"] @ faces[j]["n"] < 0.9995: continue
            if abs((faces[j]["P"].mean(0) - faces[i]["P"].mean(0)) @ faces[i]["n"]) > 0.02: continue
            nrm = faces[i]["n"]; u = np.cross(nrm, [0, 1.0, 0] if abs(nrm[1]) < 0.9 else [1.0, 0, 0]); u /= np.linalg.norm(u); v = np.cross(nrm, u)
            A = np.stack([faces[i]["P"] @ u, faces[i]["P"] @ v], 1); B = np.stack([faces[j]["P"] @ u, faces[j]["P"] @ v], 1)
            if _clip_area(A, B) > 1e-4: lv[j] = lv[i] + 1
    return lv


# ----------------------------------------------------------------------------------------------------- atlas baking
def _corners(n):
    return np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float) if n == 4 else np.array([[0, 0], [1, 0], [0, 1]], float)


def param_points(Q, s, t):
    """point of polygon Q (3 or 4 rows) at cell coordinates (s, t); quads split v0 v1 v2 / v0 v2 v3 like the mesh"""
    s = s[..., None]; t = t[..., None]
    if len(Q) == 4:
        A = Q[0] * (1 - s) + Q[1] * (s - t) + Q[2] * t
        B = Q[0] * (1 - t) + Q[2] * s + Q[3] * (t - s)
        return np.where(s >= t, A, B)
    return Q[0] * (1 - s - t) + Q[1] * s + Q[2] * t


def bary_inside(P, Q, n):
    """for points P (N, 3) in the plane of polygon Q: (inside mask, weights (N, len(Q))) using Q's two triangles"""
    u = np.cross(n, [0, 1.0, 0] if abs(n[1]) < 0.9 else [1.0, 0, 0]); u /= np.linalg.norm(u); v = np.cross(n, u)
    p = np.stack([P @ u, P @ v], -1); q = np.stack([Q @ u, Q @ v], -1)
    tris = [(0, 1, 2), (0, 2, 3)] if len(Q) == 4 else [(0, 1, 2)]
    inside = np.zeros(len(P), bool); W = np.zeros((len(P), len(Q)))
    for a, b, c in tris:
        m = np.array([[q[b, 0] - q[a, 0], q[c, 0] - q[a, 0]], [q[b, 1] - q[a, 1], q[c, 1] - q[a, 1]]])
        if abs(np.linalg.det(m)) < 1e-12: continue
        l = np.linalg.solve(m, (p - q[a]).T).T
        w1, w2 = l[:, 0], l[:, 1]; w0 = 1 - w1 - w2
        ok = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4) & ~inside
        W[ok, a] = w0[ok]; W[ok, b] = w1[ok]; W[ok, c] = w2[ok]; inside |= ok
    return inside, W


class Atlas:
    def __init__(self, size, pad=2):
        self.size = size; self.pad = pad; self.cells = []

    def pack(self, dims):
        """dims: list of (w, h) inner sizes (multiples of 4) -> positions (x, y) of the inner areas, or None"""
        p = self.pad; order = sorted(range(len(dims)), key=lambda i: -(dims[i][1]))
        pos = [None] * len(dims); x = y = 0; shelf = 0
        for i in order:
            w, h = dims[i]; W = w + 2 * p; H = h + 2 * p
            W += -W % 4; H += -H % 4
            if x + W > self.size: x = 0; y += shelf; shelf = 0
            if y + H > self.size: return None
            pos[i] = (x + p, y + p); x += W; shelf = max(shelf, H)
        return pos


def bake(faces, layers, tiles, size, density, alpha_target=False, render_scale=1):
    """faces: the faces drawn (layer 0 ones of this atlas); returns (rgba image float, per-face corner uv list, density)"""
    if render_scale not in (1, 2, 4): raise ValueError("render_scale must be 1, 2 or 4")
    base = [i for i in range(len(faces)) if layers[i] == 0 and faces[i]["sel"]]
    over = [i for i in range(len(faces)) if layers[i] > 0]
    def dims(dens):
        out = []
        for i in base:
            Q = faces[i]["P"]
            if len(Q) == 4: lu = max(np.linalg.norm(Q[1] - Q[0]), np.linalg.norm(Q[2] - Q[3])); lv = max(np.linalg.norm(Q[3] - Q[0]), np.linalg.norm(Q[2] - Q[1]))
            else: lu = np.linalg.norm(Q[1] - Q[0]); lv = np.linalg.norm(Q[2] - Q[0])
            w = max(4, int(math.ceil(lu * dens / 4)) * 4); h = max(4, int(math.ceil(lv * dens / 4)) * 4)
            out.append((min(w, size // 2), min(h, size // 2)))
        return out
    at = Atlas(size)
    if density <= 0:
        area = sum(np.linalg.norm(np.cross(faces[i]["P"][1] - faces[i]["P"][0], faces[i]["P"][-1] - faces[i]["P"][0])) for i in base)
        density = min(256.0, math.sqrt(0.55 * size * size / max(area, 1e-6)))
    while True:
        dm = dims(density); pos = at.pack(dm)
        if pos is not None: break
        density *= 0.92
    image_size = size * render_scale
    img = np.zeros((image_size, image_size, 4), np.float32)
    uvs = {}
    for k, i in enumerate(base):
        f = faces[i]; Q = f["P"]; (w, h) = (v * render_scale for v in dm[k]); (x0, y0) = (v * render_scale for v in pos[k]); p = at.pad * render_scale
        xs = np.arange(-p, w + p) + 0.5; ys = np.arange(-p, h + p) + 0.5
        S, Tt = np.meshgrid(np.clip(xs / w, 0, 1), np.clip(ys / h, 0, 1))
        if len(Q) == 3:                        # keep padding texels on the triangle
            tot = np.maximum(S + Tt, 1e-9); over_ = tot > 1; S = np.where(over_, S / tot, S); Tt = np.where(over_, Tt / tot, Tt)
        P3 = param_points(Q, S, Tt).reshape(-1, 3)
        UV = param_points(f["uv"], S, Tt).reshape(-1, 2)
        col = tiles.sample(f["mat"], UV)
        if not alpha_target: col[:, 3] = 1.0 if not f["mat"]["translucent"] else col[:, 3]
        cand = [j for j in over if faces[j]["n"] @ f["n"] > 0.999 and abs((faces[j]["P"].mean(0) - Q.mean(0)) @ f["n"]) < 0.02
                and (faces[j]["P"].min(0) <= P3.max(0) + 1e-3).all() and (faces[j]["P"].max(0) >= P3.min(0) - 1e-3).all()]
        for j in sorted(cand, key=lambda j: layers[j]):
            o = faces[j]
            ins, Wt = bary_inside(P3, o["P"], f["n"])
            if not ins.any(): continue
            ouv = Wt[ins] @ o["uv"]
            oc = tiles.sample(o["mat"], ouv)
            a = oc[:, 3:4]
            col[ins, :3] = col[ins, :3] * (1 - a) + oc[:, :3] * a
            col[ins, 3] = np.maximum(col[ins, 3], oc[:, 3])
        img[y0 - p:y0 + h + p, x0 - p:x0 + w + p] = col.reshape(h + 2 * p, w + 2 * p, 4)
        cuv = _corners(len(Q)) * np.array([w, h]) + np.array([x0, y0])
        uvs[i] = cuv / image_size
    return img, uvs, density


# ----------------------------------------------------------------------------------------------------- SR3 meshes
VERT44 = np.dtype([("p", "<f4", 4), ("n", "<f4", 3), ("t", "<f4", 3), ("uv", "<u2", 2)])


def tri_order(a, b, c, P, n):
    """SEGA's winding: a strip triangle at an even position has cross(b - a, c - a) . n < 0 (5194 of 5197 on ST205's body)"""
    return (a, b, c) if np.cross(P[b] - P[a], P[c] - P[a]) @ n < 0 else (a, c, b)


def strip_of(tris):
    s = []
    for a, b, c in tris:
        if s: s += [s[-1]] + [a] * (2 if len(s) % 2 == 0 else 3) + [b, c]
        else: s = [a, b, c]
    return s


def build_mesh(groups, template_hdr):
    """groups: list of (material id, faces [(P (k,3) sr3 coords, n, uv (k,2) 0..1)]) -> carmodel.Mesh (format 0x2047)"""
    V = []; idx = []; gl = []
    for mat, fl in groups:
        v0 = len(V); i0 = len(idx); tris = []
        for P, n, uv in fl:
            base = len(V)
            t = P[1] - P[0]; t = t - n * (t @ n); t /= max(np.linalg.norm(t), 1e-12)
            for k in range(len(P)): V.append((P[k], n, t, uv[k]))
            loc = {k: base + k for k in range(len(P))}
            Pw = {base + k: P[k] for k in range(len(P))}
            for (a, b, c) in ([(0, 1, 2), (0, 2, 3)] if len(P) == 4 else [(0, 1, 2)]):
                A, B, C = loc[a], loc[b], loc[c]
                tris.append(tri_order(A, B, C, Pw, n))
        st = strip_of(tris) if tris else []
        if not st:                            # empty group: one degenerate triangle on its first vertex
            if len(V) == v0: V.append((np.zeros(3), np.array([0, 1.0, 0]), np.array([1.0, 0, 0]), np.zeros(2)))
            st = [v0, v0, v0]
        idx += st
        gl.append([v0, len(V) - v0, i0, (1 << 16) | len(st), mat])
    a = np.zeros(len(V), VERT44)
    for k, (P, n, t, uv) in enumerate(V):
        a[k]["p"] = (P[0], P[1], P[2], 1.0); a[k]["n"] = n; a[k]["t"] = t
        a[k]["uv"] = np.clip(np.round(np.asarray(uv) * 32767), 0, 32767)      # SHORT2N (signed): 32768 would be -1.0
    hdr = list(template_hdr); hdr[5] = len(V); hdr[7] = len(idx); hdr[8] = len(gl)
    ib = struct.pack("<%dH" % len(idx), *idx)
    return carmodel.Mesh(hdr, gl, a.tobytes(), ib, b"\0" * (-len(ib) % 4))


def empty_mesh(m):
    """the same mesh header and groups (materials kept), one degenerate triangle per group"""
    return build_mesh([(g[4], []) for g in m.groups], m.hdr) if m.fmt == 0x2047 else _empty_any(m)


def _empty_any(m):
    st = m.stride; v = bytes(st)
    gl = [[0, 1, 0, (1 << 16) | 3, g[4]] for g in m.groups]
    hdr = list(m.hdr); hdr[5] = 1; hdr[7] = 3 * len(gl)
    for k, g in enumerate(gl): g[2] = 3 * k
    ib = struct.pack("<%dH" % (3 * len(gl)), *([0] * 3 * len(gl)))
    return carmodel.Mesh(hdr, gl, v, ib, b"\0" * (-len(ib) % 4))


def mesh_points(m):
    return np.frombuffer(m.vdata, np.uint8).reshape(-1, m.stride)[:, :12].copy().view("<f4").reshape(-1, 3).astype(np.float64)


def moved_mesh(m, fn):
    """mesh with every position (and normal / tangent for 0x2047 / 0x2057) passed through fn(points) (positions only move)"""
    a = np.frombuffer(m.vdata, np.uint8).reshape(-1, m.stride).copy()
    P = a[:, :12].copy().view("<f4").reshape(-1, 3).astype(np.float64)
    a[:, :12] = fn(P).astype("<f4").view(np.uint8).reshape(-1, 12)
    return carmodel.Mesh(m.hdr, m.groups, a.tobytes(), m.idx, m.pad)


# ----------------------------------------------------------------------------------------------------- the build
def sha(b): return hashlib.sha256(b).hexdigest().upper()


def material_with_texture(mat_chunk, old_tex, new_tex, new_id):
    d = bytearray(mat_chunk.data)
    for o in mat_chunk.ref:
        if struct.unpack_from("<I", d, o)[0] == old_tex: struct.pack_into("<I", d, o, new_tex)
    return sbfw.Ch(mat_chunk.kind, new_id, bytes(d), mat_chunk.fix, mat_chunk.ref, mat_chunk.z, None)


def first_texture(f, mat_id):
    ids = f.byid(); c = ids[mat_id]
    for r in c.refs():
        if r in ids and ids[r].kind == 4: return r
    return None


CHANGED = set()          # ids of chunks whose content this build changes: they always get fresh ids


def replace_texture(f, tex_id, rgba):
    CHANGED.add(tex_id)
    for i, c in enumerate(f.chunks):
        if c.id == tex_id:
            f.chunks[i] = sbfw.Ch(c.kind, c.id, texdxt.texture_data(c.data, rgba), c.fix, c.ref, c.z, c.gap)
            return
    raise KeyError("%08x" % tex_id)


def write_realigned(f, path):
    """keep SEGA's padding where the alignment still holds after edits, else the alignment rules (01_container.md)"""
    pos = f.first; out = []
    for c in f.chunks:
        hl = 24 + 4 * len(c.fix) + 4 * len(c.ref)
        want = sbfw.ALIGN16.get(c.kind)
        def ok(g):
            dat = pos + g + hl
            return (dat % 16 == want) if want is not None and c.kind != 7 else (dat % 4 == 0 if c.kind != 7 else (dat % 16) in (0, 4, 8, 12))
        g = c.gap if c.gap is not None and ok(c.gap) else next(g for g in range(0, 64) if ok(g))
        out.append(sbfw.Ch(c.kind, c.id, c.data, c.fix, c.ref, c.z, g))
        pos += g + hl + len(c.data)
    f2 = sbfw.SbfFile(); f2.chunks = out; f2.first = f.first; f2.tail = f.tail; f2.hdr = f.hdr; f2.raw = f.raw; f2.compressed = f.compressed
    return carmodel.write_file(f2, path, keep_layout=True)


def liveries():
    """every livery this script can build: key, body row, frame row, what it is (daytona_usa_rom_data.md section 11)"""
    out = [dict(key="hornet0", body=1460, frames=1462, label="Hornet #41 red / blue (player car, default)"),
           dict(key="hornet1", body=1461, frames=1463, label="Hornet #41 yellow / red (player car, other transmission)"),
           dict(key="hornetlink", body=1835, frames=1793, label="Hornet red, no number (linked play)")]
    out += [dict(key="opp%d" % k, body=4 * k, frames=None, label="opponent livery %d" % k) for k in range(45)]
    out += [dict(key="link%d" % k, body=1803 + 4 * (k - 1), frames=None, label="linked-play Hornet #%d" % k) for k in range(1, 9)]
    out += [dict(key="car99", body=1836, frames=None, label="#99 livery (in the ROM, use unknown)")]
    return out


def main():
    if "--list-liveries" in sys.argv:
        print(json.dumps(liveries(), indent=1)); return
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--livery", default="hornet0"); ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--length", type=float, default=5.0)       # target body length in metres (the scale follows)
    ap.add_argument("--handling", default="bowler"); ap.add_argument("--name", default="Hornet")
    ap.add_argument("--folder", default="Hornet"); ap.add_argument("--langid", default=None)
    ap.add_argument("--light", type=float, default=174.0); ap.add_argument("--density", type=float, default=0.0)
    ap.add_argument("--id", type=int, default=10); ap.add_argument("--sound", default="ID_CAR_BOWLER")
    a = ap.parse_args()
    folder = a.folder; low = folder.lower()
    langid = a.langid or "LANG_ID_" + "".join(ch for ch in folder.upper() if ch.isalnum())
    report = dict(args=vars(a))

    # ---------------- Daytona model
    if a.livery in LIVERIES: body_row, frame_row = LIVERIES[a.livery]
    elif a.livery.startswith("opp"): body_row, frame_row = 4 * int(a.livery[3:]), None
    elif a.livery.startswith("link"): body_row, frame_row = 1803 + 4 * (int(a.livery[4:]) - 1), None
    else: raise SystemExit("unknown livery " + a.livery)
    faces = day_faces(body_row) + (day_faces(frame_row) if frame_row is not None else [])
    day_len = float(np.ptp(np.concatenate([f["P"] for f in faces])[:, 2]))
    s = a.scale if a.scale else a.length / day_len          # Daytona units are metres (wheelbase 2.807 vs NASCAR 110 in)
    report["daytona_length"] = day_len; report["scale"] = s
    layers = overlay_layers(faces)
    tiles = Tiles(a.light)

    # ---------------- donors
    st = {k: sbfw.read_sbf(p) for k, p in car_clone.car_files("st205") if os.path.exists(p)}
    hd = sbfw.read_sbf(os.path.join(CARS, a.handling.lower() + "bespoke_data.sbf"))
    hwheel = [c for c in hd.chunks if c.kind == 5 and len(c.data) == 180 and c.u32(0) == 2][0]
    hub_y = struct.unpack_from("<f", hwheel.data, 8)[0]
    G = hub_y - s * DAY_WHEEL["r"]                       # ground in SR3 car space; the hubs keep the donor's height
    def to_sr3(P): return P * s + np.array([0.0, G, 0.0])
    report["ground_y"] = G; report["hub_y"] = hub_y

    # ---------------- chassis: atlas for the opaque body, one for the translucent faces
    for f in faces: f["sel"] = not f["mat"]["translucent"]
    body_img, body_uv, dens = bake(faces, layers, tiles, 1024, a.density)
    for f in faces: f["sel"] = bool(f["mat"]["translucent"])
    glass_img, glass_uv, gdens = bake(faces, layers, tiles, 512, dens, alpha_target=True)
    report.update(body_faces=len(body_uv), glass_faces=len(glass_uv), overlays=int((layers > 0).sum()), density=round(dens, 1))
    body_rgba = np.clip(body_img * 255, 0, 255); body_rgba[..., 3] = 255
    glass_rgba = np.clip(glass_img * 255, 0, 255)

    ch = st["chassismodel"]; cm_i = [i for i, c in enumerate(ch.chunks) if c.kind == 1][0]
    model = carmodel.read_model(ch.chunks[cm_i])
    byname = {n.name: n for n in model.nodes}
    def mesh_of(name): return model.meshes[byname[name].mesh]
    livery_mat = mesh_of("bodyshell").groups[1][4]            # 5bbffc35: the livery material (1024 DXT1)
    glass_mat_old = mesh_of("screen_f").groups[0][4]          # 4bf687c6: glass
    livery_tex = first_texture(ch, livery_mat); glass_tex_old = first_texture(ch, glass_mat_old)
    replace_texture(ch, livery_tex, body_rgba)
    taken = set()
    for f in list(st.values()) + [hd]:
        for c in f.chunks: taken.add(c.id); taken.update(c.refs())
    new_glass_tex = carmodel.fresh_id(low + ":glasstex", glass_tex_old, taken)
    new_glass_mat = carmodel.fresh_id(low + ":glassmat", glass_mat_old, taken)
    gt = ch.byid()[glass_tex_old]
    gtex = sbfw.Ch(4, new_glass_tex, texdxt.texture_data(gt.data, glass_rgba), [], [], 0, None)
    gmat = material_with_texture(ch.byid()[glass_mat_old], glass_tex_old, new_glass_tex, new_glass_mat)
    # new chunks go right before the mesh chunk (references point backwards only)
    ch.chunks[cm_i:cm_i] = [gtex, gmat]; cm_i += 2

    def sr3_faces(uvmap):
        out = []
        for i, uv in uvmap.items():
            f = faces[i]; out.append((to_sr3(f["P"]), f["n"], uv))
        return out
    body_faces = sr3_faces(body_uv)
    if frame_row is None:
        # the opponent and linked-play bodies are hollow shells (Daytona only shows them from outside): seen through
        # their window openings and wheel arches the car would be empty; a dark inner skin closes them
        inner = inner_skin(body_faces, body_img, body_uv)
        body_faces += inner; report["inner_skin_faces"] = len(inner)
    body_mesh = build_mesh([(livery_mat, body_faces), (new_glass_mat, sr3_faces(glass_uv))], mesh_of("bodyshell").hdr)
    for nm in ("bodyshell", "bodyshellx02", "bodyshellx03"):
        model.meshes[byname[nm].mesh] = body_mesh
    # Daytona body measurements (SR3 space) for placing ST205's small parts
    allP = np.concatenate([to_sr3(f["P"]) for f in faces]); bmin = allP.min(0); bmax = allP.max(0)
    def rear_z(y0, y1, xw): sel = (allP[:, 1] >= y0) & (allP[:, 1] <= y1) & (np.abs(allP[:, 0]) <= xw); return allP[sel, 2].min() if sel.any() else bmin[2]
    def front_z(y0, y1, xw): sel = (allP[:, 1] >= y0) & (allP[:, 1] <= y1) & (np.abs(allP[:, 0]) <= xw); return allP[sel, 2].max() if sel.any() else bmax[2]
    st_orig = carmodel.read_model([c for c in sbfw.read_sbf(os.path.join(CARS, "st205chassismodel_data.sbf")).chunks if c.kind == 1][0])
    st_body = mesh_points(st_orig.meshes[0])
    st_ground = -0.199 + 0.015                            # ST205: tyre bottom (floor shadow 1.5 cm below it)
    hornet_tyre_bottom = G
    dy = hornet_tyre_bottom - st_ground                   # height shift ST205 -> Daytona for parts set by height above ground
    # glass nodes: empty
    for nm in ("screen_f", "screen_b", "sideglass_bl", "sideglass_br", "screen_fx02", "screen_bx02", "sideglass_blx02", "sideglass_brx02"):
        if nm in byname and byname[nm].mesh is not None: model.meshes[byname[nm].mesh] = empty_mesh(model.meshes[byname[nm].mesh])
    # rear lamps: ST205's lamp triangles (material, UVs, lit / unlit) laid flush on the Hornet's own rear face
    report["rear_lamps"] = fit_rear_lamps(model, byname, faces, to_sr3, dy)
    # front light glow and exhaust: node translations moved
    for nm in ("runlitg_fl", "runlitg_flx02"):
        if nm in byname and byname[nm].mesh is not None:
            n = byname[nm]; t = np.array(n.translation()); m0 = model.meshes[n.mesh]; P0 = mesh_points(m0)
            y = t[1] + dy
            zf = front_z(y - 0.1, y + 0.1, 0.8)
            near = allP[(np.abs(allP[:, 1] - y) < 0.12) & (allP[:, 2] > zf - 0.25)]
            half = np.abs(near[:, 0]).max() if len(near) else 0.8
            xs = P0[:, 0] + t[0]; k = min(1.0, 0.85 * half / max(np.abs(xs).max(), 1e-6))     # both lamps inside the nose
            model.meshes[n.mesh] = moved_mesh(m0, lambda P, k=k, t0=t[0]: np.stack([(P[:, 0] + t0) * k - t0 * k, P[:, 1], P[:, 2]], 1))
            n.set_translation(t[0] * k, y, zf - 0.12)
    for nm in ("exhaust", "exhaustx02"):
        if nm in byname:
            n = byname[nm]; t = np.array(n.translation())
            n.set_translation(t[0] * s, t[1] + dy, bmin[2] + 0.23 * s)
    if "driver" in byname:
        t = byname["driver"].translation(); byname["driver"].set_translation(-0.35 * s, t[1] + dy, -0.25 * s)
    # suspension at the Daytona hubs (inner face of the tyre), wheel dummies at the tyre centre
    hubs = {}
    for ax, z in (("f", DAY_WHEEL["zf"]), ("b", DAY_WHEEL["zr"])):
        for side, sx in (("l", -1), ("r", 1)):
            hubs[ax + side] = np.array([sx * s * (DAY_WHEEL["x_out"] - DAY_WHEEL["w"]), hub_y, s * z])
    for k, h in hubs.items():
        n = byname["suspension_" + k]; n.set_translation(*h)
        sx = -1 if k[1] == "l" else 1
        byname["wheel_%s_dummy" % k].set_translation(sx * s * DAY_WHEEL["w"] / 2, 0, 0)
    # shadows
    fs_ = byname["floor_shadow"]; fsm = model.meshes[fs_.mesh]; P0 = mesh_points(fsm)
    st_len = st_body[:, 2].max() - st_body[:, 2].min(); st_wid = st_body[:, 0].max() - st_body[:, 0].min()
    kz = (bmax[2] - bmin[2]) / st_len; kx = (bmax[0] - bmin[0]) / st_wid
    zc = (st_body[:, 2].max() + st_body[:, 2].min()) / 2; hc = (bmax[2] + bmin[2]) / 2
    model.meshes[fs_.mesh] = moved_mesh(fsm, lambda P: np.stack([P[:, 0] * kx, np.full(len(P), G - 0.015), (P[:, 2] - zc) * kz + hc], 1))
    for k, h in hubs.items():
        n = byname["wheel_shadow_" + k]
        st_t = np.array(n.translation())
        sx = -1 if k[1] == "l" else 1
        # ST205: node 0.124 m inboard of its tyre centre (hub 0.624, tyre centre 0.748); the same offset here
        centre_x = sx * s * (DAY_WHEEL["x_out"] - DAY_WHEEL["w"] / 2)
        n.set_translation(centre_x - sx * 0.124, G - 0.028, h[2])
    # tail record bounding box (lod1 + shadows, world space)
    W = _world(model)
    pts = []
    for i, n in enumerate(model.nodes):
        if n.mesh is None or "x02" in n.name or "x03" in n.name: continue
        P = mesh_points(model.meshes[n.mesh]); pts.append((np.c_[P, np.ones(len(P))] @ W[i])[:, :3])
    pts = np.concatenate(pts); mn = pts.min(0); mx = pts.max(0)
    tw = bytearray(model.tail_words); struct.pack_into("<3f", tw, 12, *mn); struct.pack_into("<3f", tw, 24, *mx)
    struct.pack_into("<3f", tw, 40, *((mn + mx) / 2)); model.tail_words = bytes(tw)
    d, fx, rf = model.serialize(); CHANGED.add(ch.chunks[cm_i].id)
    ch.chunks[cm_i] = sbfw.Ch(1, ch.chunks[cm_i].id, d, fx, rf, ch.chunks[cm_i].z, ch.chunks[cm_i].gap)
    report["body_bbox"] = [bmin.round(3).tolist(), bmax.round(3).tolist()]

    # ---------------- wheels
    wf = st["bespokemodel"]; wm_i = [i for i, c in enumerate(wf.chunks) if c.kind == 1][0]
    wmodel = carmodel.read_model(wf.chunks[wm_i]); wby = {n.name: n for n in wmodel.nodes}
    wfaces = {}
    for side, (hi, lo) in WHEEL_ROWS.items():
        wfaces[side] = (day_faces(hi), day_faces(lo))
    # wheel atlas: every face of the four wheel models, one cell each (no overlays on wheels)
    allw = []
    for side in ("l", "r"):
        for part in wfaces[side]: allw += part
    for f in allw: f["sel"] = True
    wl = np.zeros(len(allw), int)
    w_img, w_uv, _ = bake(allw, wl, tiles, 512, 0)
    w_rgba = np.clip(w_img * 255, 0, 255); w_rgba[..., 3] = 255
    tyre_mat = wmodel.meshes[wby["wheel_bl"].mesh].groups[0][4]
    blur_mat = wmodel.meshes[wby["wheel_blur_bl"].mesh].groups[0][4]
    tyre_tex = first_texture(wf, tyre_mat); blur_tex = first_texture(wf, blur_mat)
    replace_texture(wf, tyre_tex, w_rgba)
    # blur: the rim faces (textured faces near the outer face) with a radially averaged copy of the wheel atlas
    rim_tile = None
    for f in wfaces["l"][0]:
        if f["mat"]["textured"]: rim_tile = f; break
    blur_rgba = radial_blur_atlas(w_rgba, allw, w_uv, wfaces)
    replace_texture(wf, blur_tex, blur_rgba)
    # ST205's tyre / blur normal maps (DXT5, x in alpha, y in green: 82bf532e, edcc1584) follow ST205's UVs: made flat
    ids_ = wf.byid(); flat_done = []
    for mid in (tyre_mat, blur_mat):
        for r in ids_[mid].refs():
            c = ids_.get(r)
            if c is None or c.kind != 4 or r in (tyre_tex, blur_tex) or r in flat_done: continue
            w_, h_, fc_ = texdxt.texture_info(c.data)
            if fc_ != "DXT5" or w_ < 64: continue
            im = texdxt.decode_texture(c.data).reshape(-1, 4).astype(float)
            if im[:, 0].mean() < 8 and im[:, 2].mean() < 8 and abs(im[:, 1].mean() - 128) < 16 and abs(im[:, 3].mean() - 128) < 16:
                flat = np.zeros((h_, w_, 4), np.float32); flat[..., 1] = 128; flat[..., 3] = 128
                replace_texture(wf, r, flat); flat_done.append(r)
    report["flat_normal_maps"] = ["%08x" % r for r in flat_done]
    off = 0; idx_of = {}
    for side in ("l", "r"):
        for part in (0, 1):
            for j in range(len(wfaces[side][part])): idx_of[(side, part, j)] = off + j
            off += len(wfaces[side][part])
    def wheel_faces(side, part, only=None):
        out = []
        for j, f in enumerate(wfaces[side][part]):
            if only is not None and not only(f): continue
            out.append((f["P"] * s, f["n"], w_uv[idx_of[(side, part, j)]]))
        return out
    def is_rim(f):           # faces of the outer disc: normal along -x / +x and textured
        return f["mat"]["textured"] and abs(f["n"][0]) > 0.95
    for k in ("fl", "fr", "bl", "br"):
        side = k[1]
        n = wby["wheel_" + k]; m0 = wmodel.meshes[n.mesh]
        wmodel.meshes[n.mesh] = build_mesh([(m0.groups[0][4], wheel_faces(side, 0))] + [(g[4], []) for g in m0.groups[1:]], m0.hdr)
        for nm in ("wheel_spoke_" + k,):
            ms = wmodel.meshes[wby[nm].mesh]; wmodel.meshes[wby[nm].mesh] = build_mesh([(g[4], []) for g in ms.groups], ms.hdr)
        mb = wmodel.meshes[wby["wheel_blur_" + k].mesh]
        sx = -1 if side == "l" else 1
        blur = [(P + np.array([sx * 0.003, 0, 0]), nn, uv) for P, nn, uv in wheel_faces(side, 0, is_rim)]
        wmodel.meshes[wby["wheel_blur_" + k].mesh] = build_mesh([(mb.groups[0][4], blur)] + [(g[4], []) for g in mb.groups[1:]], mb.hdr)
        for lodn in ("wheel_%sx02" % k, "wheel_%sx03" % k):
            if lodn in wby:
                ml = wmodel.meshes[wby[lodn].mesh]
                wmodel.meshes[wby[lodn].mesh] = build_mesh([(ml.groups[0][4], wheel_faces(side, 1))] + [(g[4], []) for g in ml.groups[1:]], ml.hdr)
    d, fx, rf = wmodel.serialize(); CHANGED.add(wf.chunks[wm_i].id)
    wf.chunks[wm_i] = sbfw.Ch(1, wf.chunks[wm_i].id, d, fx, rf, wf.chunks[wm_i].z, wf.chunks[wm_i].gap)

    # ---------------- handling: the donor's, wheel chunk set to the Daytona wheels
    dw = bytearray(hwheel.data)
    order = [("fl", -1, DAY_WHEEL["zf"]), ("fr", 1, DAY_WHEEL["zf"]), ("bl", -1, DAY_WHEEL["zr"]), ("br", 1, DAY_WHEEL["zr"])]
    for k, (nm, sx, z) in enumerate(order):
        o = 4 + 44 * k
        hx = sx * s * (DAY_WHEEL["x_out"] - DAY_WHEEL["w"]); cx = sx * s * (DAY_WHEEL["x_out"] - DAY_WHEEL["w"] / 2)
        struct.pack_into("<11f", dw, o, hx, hub_y, s * z, cx, hub_y, s * z, cx, hub_y, s * z, s * DAY_WHEEL["r"], s * DAY_WHEEL["w"])
    old_r = struct.unpack_from("<f", hwheel.data, 4 + 36)[0]
    for i, c in enumerate(hd.chunks):
        if c is hwheel: CHANGED.add(c.id); hd.chunks[i] = sbfw.Ch(c.kind, c.id, bytes(dw), c.fix, c.ref, c.z, c.gap)
    same_r = []                                           # other places that hold the donor's wheel radius bit for bit
    rb = struct.pack("<f", old_r)
    for c in hd.chunks:
        if c.id == hwheel.id: continue
        o = c.data.find(rb)
        while o >= 0:
            if o % 4 == 0: same_r.append(("%08x" % c.id, o))
            o = c.data.find(rb, o + 1)
    report["handling"] = dict(donor=a.handling, wheel_chunk="%08x" % hwheel.id, donor_radius=old_r, new_radius=s * DAY_WHEEL["r"],
                              other_copies_of_the_radius=same_r)

    # ---------------- dirt maps (texture packs) and mud / snow shells by transfer from ST205
    st_bm = st_orig.meshes[0]
    stA = np.frombuffer(st_bm.vdata, np.uint8).reshape(-1, st_bm.stride)
    stP = stA[:, :12].copy().view("<f4").reshape(-1, 3).astype(np.float64)
    stUV = stA[:, 40:44].copy().view("<u2").reshape(-1, 2) / 32768.0
    # ST205 vertices of the livery group only (its UVs address the livery / dirt texture)
    g = st_bm.groups[1]; lv_sel = np.zeros(len(stP), bool); lv_sel[g[0]:g[0] + g[1]] = True
    stPl = stP[lv_sel]; stUVl = stUV[lv_sel]
    def to_st(P):       # Daytona (SR3 space) -> ST205 body space, box to box
        return (P - (bmin + bmax) / 2) / (bmax - bmin) * (stP.max(0) - stP.min(0)) + (stP.max(0) + stP.min(0)) / 2
    grid = Nearest(stPl)
    # one triangle of ST205's livery group per vertex (for the local UV mapping of the dirt transfer)
    idx_st = np.frombuffer(st_bm.idx, "<u2").astype(np.int64)
    s_ = idx_st[g[2]:g[2] + (g[3] & 0xFFFF)]
    tri_of = {}
    for k in range(len(s_) - 2):
        a_, b_, c_ = s_[k], s_[k + 1], s_[k + 2]
        if a_ == b_ or b_ == c_ or a_ == c_: continue
        for v_ in (a_, b_, c_): tri_of.setdefault(int(v_), (int(a_), int(b_), int(c_)))
    lv_index = np.nonzero(lv_sel)[0]
    dens_ = []
    for (a_, b_, c_) in set(tri_of.values()):
        for u_, w_ in ((a_, b_), (b_, c_), (c_, a_)):
            dp = np.linalg.norm(stP[u_] - stP[w_]); du = np.linalg.norm(stUV[u_] - stUV[w_])
            if dp > 1e-3: dens_.append(du / dp)
    st_local = dict(P=stP, UV=stUV, tri_of=tri_of, index=lv_index, uvpm=float(np.median(dens_)), window=0.1)
    report["dirt_uv_per_metre"] = st_local["uvpm"]
    livery_dirt_ph = None
    for r in ch.byid()[livery_mat].refs():
        if r not in ch.byid(): livery_dirt_ph = r; break             # the placeholder the texture pack maps
    for kind in ("texturepackdust", "texturepackmud", "texturepacksnow"):
        tp = st[kind]; table = tp.chunks[-1]
        tex_id = None
        n_ = table.u32(4)
        for j in range(n_):
            if table.u32(8 + 8 * j + 4) == livery_dirt_ph: tex_id = table.u32(8 + 8 * j)
        src = texdxt.decode_texture(tp.byid()[tex_id].data).astype(np.float32)
        dirt = transfer_dirt(faces, body_uv, to_sr3, to_st, grid, st_local, src, 1024)
        replace_texture(tp, tex_id, dirt)
    for kind in ("mudmodel", "snowmodel"):
        mf = st[kind]; mi = [i for i, c in enumerate(mf.chunks) if c.kind == 1][0]
        mmodel = carmodel.read_model(mf.chunks[mi])
        replace_texture(mf, first_texture(mf, mmodel.meshes[0].groups[0][4]), body_rgba)   # its copy of the livery texture
        mmodel.meshes[0] = mud_shell(mmodel.meshes[0], faces, body_uv, to_sr3, to_st)
        d, fx, rf = mmodel.serialize(); CHANGED.add(mf.chunks[mi].id)
        mf.chunks[mi] = sbfw.Ch(1, mf.chunks[mi].id, d, fx, rf, mf.chunks[mi].z, mf.chunks[mi].gap)

    # ---------------- bonnet
    bf = st["bonnet"]; bi = [i for i, c in enumerate(bf.chunks) if c.kind == 1][0]
    bmodel = carmodel.read_model(bf.chunks[bi]); bm = bmodel.meshes[0]
    bonnet_mat = bm.groups[0][4]; bonnet_tex = first_texture(bf, bonnet_mat)
    replace_texture(bf, bonnet_tex, body_rgba)
    # ST205's bonnet model is not its body hood moved (best translation leaves 14 cm mean distance): it is a hood drawn
    # for the bonnet camera (x 0.91, z 1.9 times the hood). The Daytona hood top is mapped box to box onto that model.
    Bb = mesh_points(bm); bb0, bb1 = Bb.min(0), Bb.max(0)
    hood = []
    zc_ws = hood_cut(faces, to_sr3)
    for i, uv in body_uv.items():
        f = faces[i]; P = to_sr3(f["P"])
        if P[:, 2].mean() > zc_ws and f["n"][1] > 0.5: hood.append((P, f["n"], uv))
    hp = np.concatenate([h[0] for h in hood]); h0, h1 = hp.min(0), hp.max(0)
    k = (bb1 - bb0) / np.maximum(h1 - h0, 1e-6)
    def to_bonnet(P): return (P - h0) * k + bb0
    hood = [(to_bonnet(P), n_, uv) for P, n_, uv in hood]
    hood = [(P, _face_normal(P, n_), uv) for P, n_, uv in hood]
    T_b = k
    bmodel.meshes[0] = build_mesh([(bonnet_mat, hood)] + [(g[4], []) for g in bm.groups[1:]], bm.hdr)
    d, fx, rf = bmodel.serialize(); CHANGED.add(bf.chunks[bi].id)
    bf.chunks[bi] = sbfw.Ch(1, bf.chunks[bi].id, d, fx, rf, bf.chunks[bi].z, bf.chunks[bi].gap)
    report["bonnet"] = dict(scale=np.round(T_b, 3).tolist(), box=[bb0.round(3).tolist(), bb1.round(3).tolist()], faces=len(hood))

    # ---------------- fresh ids over the whole set, write
    files = {"chassismodel": ch, "bespokemodel": wf, "bespoke": hd, "mudmodel": st["mudmodel"], "snowmodel": st["snowmodel"],
             "bonnet": bf, "texturepackdust": st["texturepackdust"], "texturepackmud": st["texturepackmud"], "texturepacksnow": st["texturepacksnow"]}
    mapping = fresh_map(files, low, a.handling.lower())
    manifest = dict(car=folder, livery=a.livery, scale=s, handling=a.handling, files=[], replace=[], id_map=len(mapping))
    for kind, f in files.items():
        carmodel.remap(f, mapping)
        rel = "Main_release/cars/" + car_clone.target_name(kind, folder)
        b = write_realigned(f, os.path.join(a.out, rel))
        probs = sbfw.validate(sbfw.read_sbf(os.path.join(a.out, rel)), rel, quiet=True, extern_ids=set(mapping.values()) | all_ids_of(files))
        manifest["files"].append(dict(path=rel.replace("/", "\\"), sha256=sha(b), size=len(b), problems=len(probs)))
        print("  %-48s %8d bytes, validate problems %d" % (rel, len(b), len(probs)))

    # ---------------- ArcadeDatabase (from SEGA's original) and the car's name
    srcb = open(ORIG_DB, "rb").read()
    db = sbfw.read_sbf(ORIG_DB)
    cars = arcadedb.read_cars(db.byid()[arcadedb.CARS_ID])
    nums = [c for c in cars if c.folder.lower() == a.handling.lower()][0].nums
    arcadedb.add_car(db, arcadedb.Car(a.id, langid, folder, a.sound, 0, 0, nums))
    dbb = arcadedb.write_db(db); rel = "ArcadeDatabase/arcadedatabase_xdata.sbf"
    os.makedirs(os.path.join(a.out, "ArcadeDatabase"), exist_ok=True); open(os.path.join(a.out, rel), "wb").write(dbb)
    manifest["replace"].append(dict(path=rel.replace("/", "\\"), source_sha256=sha(srcb), sha256=sha(dbb), size=len(dbb),
                                    backup="arcadedatabase_xdata.before_%s.sbf" % low, fallback="arcadedatabase_xdata.sbf"))
    sysp = langtable.GAME_SYSTEM
    sf = sbfw.read_sbf(sysp); ti = langtable.find_chunk(sf)
    if langid in langtable.LangTable.parse(sf.chunks[ti].data).ids:     # an earlier build is installed: start from SEGA's file
        sysp = os.path.join(os.path.dirname(ORIG_DB), "system_data.before_%s.sbf" % low)
        if not os.path.exists(sysp): raise SystemExit("the game's system_data.sbf already has %s and no original copy was found" % langid)
        sf = sbfw.read_sbf(sysp); ti = langtable.find_chunk(sf)
        assert langid not in langtable.LangTable.parse(sf.chunks[ti].data).ids
    sysb = open(sysp, "rb").read(); tc = sf.chunks[ti]
    t = langtable.LangTable.parse(tc.data); t.add(langid, a.name)
    sf.chunks[ti] = sbfw.Ch(tc.kind, tc.id, t.build(), tc.fix, tc.ref, tc.z, tc.gap)
    rel = "system/system_data.sbf"
    sb = write_realigned(sf, os.path.join(a.out, rel))
    back = langtable.LangTable.parse(sbfw.read_sbf(os.path.join(a.out, rel)).chunks[ti].data)
    assert back.get(langid)["LANG_ENGLISH"] == a.name
    manifest["replace"].append(dict(path=rel.replace("/", "\\"), source_sha256=sha(sysb), sha256=sha(sb), size=len(sb),
                                    backup="system_data.before_%s.sbf" % low))
    manifest["record"] = dict(id=a.id, name=langid, text=a.name, folder=folder, sound=a.sound, nums=nums)
    manifest["report"] = json.loads(json.dumps(report, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w"), indent=1)
    for s_, d_ in (("car_install.ps1", "install.ps1"), ("car_uninstall.ps1", "uninstall.ps1")):
        open(os.path.join(a.out, d_), "wb").write(open(os.path.join(HERE, s_), "rb").read())
    for img, nm in ((body_rgba, "atlas_body.png"), (glass_rgba, "atlas_glass.png"), (w_rgba, "atlas_wheels.png")):
        from PIL import Image
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(a.out, nm))
    print(json.dumps(manifest["report"], indent=1)[:1500])


def _strip_tris(m, g):
    """triangles of one group as drawn (odd strip positions reversed), degenerate ones left out"""
    idx = np.frombuffer(m.idx, "<u2").astype(int); s = idx[g[2]:g[2] + (g[3] & 0xFFFF)]; out = []
    for k in range(len(s) - 2):
        a, b, c = s[k], s[k + 1], s[k + 2]
        if a == b or b == c or a == c: continue
        out.append((a, b, c) if k % 2 == 0 else (b, a, c))
    return out


def _plane_z(face, P):
    """z of the plane of a body face (SR3 space, points P (N, 3) give x, y)"""
    n = face["n"]; c = face["Q"].mean(0)
    return c[2] - (n[0] * (P[:, 0] - c[0]) + n[1] * (P[:, 1] - c[1])) / n[2]


INNER_INSET = 0.01      # the inner skin of a hollow body sits this far inside the outer surface (m)


def inner_skin(body_faces, img, uvmap):
    """a hollow body's inside: every opaque face again, INNER_INSET inwards, facing in, in one dark colour (the centre of
    the darkest large polygon of the body's own atlas, e.g. the windscreen)"""
    H, W = img.shape[:2]; best = None
    for uv in uvmap.values():
        x0, y0 = np.floor(uv.min(0) * [W, H]).astype(int); x1, y1 = np.ceil(uv.max(0) * [W, H]).astype(int)
        if x1 - x0 < 12 or y1 - y0 < 12: continue
        reg = img[y0 + 3:y1 - 3, x0 + 3:x1 - 3, :3]
        key = float(reg.mean() + reg.std())
        if best is None or key < best[0]: best = (key, (uv.min(0) + uv.max(0)) / 2)
    duv = best[1]
    return [(P[::-1] - n * INNER_INSET, -n, np.tile(duv, (len(P), 1))) for P, n, uv in body_faces]


class RearCaster:
    """rays cast from behind (along +z) onto a body: the first surface each ray meets, with its outward normal.
    tris (T, 3, 3), normals (T, 3) unit, outward."""
    def __init__(self, tris, normals):
        a = tris[:, 0]; e1 = tris[:, 1] - a; e2 = tris[:, 2] - a
        den = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]; ok = np.abs(den) > 1e-12
        self.a, self.e1, self.e2, self.n, self.den = a[ok], e1[ok], e2[ok], normals[ok], den[ok]

    def first_hit(self, X, Y):
        """-> z, normal, hit mask for rays at (X, Y)"""
        X = np.asarray(X, float).ravel(); Y = np.asarray(Y, float).ravel()
        z = np.full(len(X), np.inf); nn = np.zeros((len(X), 3))
        for k in range(0, len(X), 512):
            dx = X[k:k + 512, None] - self.a[None, :, 0]; dy = Y[k:k + 512, None] - self.a[None, :, 1]
            l1 = (dx * self.e2[None, :, 1] - dy * self.e2[None, :, 0]) / self.den
            l2 = (self.e1[None, :, 0] * dy - self.e1[None, :, 1] * dx) / self.den
            inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l1 + l2 <= 1 + 1e-6)
            zz = np.where(inside, self.a[None, :, 2] + l1 * self.e1[None, :, 2] + l2 * self.e2[None, :, 2], np.inf)
            j = zz.argmin(1)
            z[k:k + 512] = zz[np.arange(len(j)), j]; nn[k:k + 512] = self.n[j]
        return z, nn, np.isfinite(z)

    def walk(self, x0, y0, ux, uy, step=0.002, length=3.0):
        """walk from (x0, y0) along (ux, uy) over the flat rear panel, seen from behind: stops where the surface has
        turned more than CORNER_TURN from straight back or steps in depth (another surface) -> distance walked"""
        t = np.arange(0.0, length, step)
        z, n, hit = self.first_hit(x0 + ux * t, y0 + uy * t)
        good = hit & (n[:, 2] <= -math.cos(CORNER_TURN))
        with np.errstate(invalid="ignore"): good[1:] &= np.abs(np.diff(z)) <= step * math.tan(CORNER_TURN) + 0.001
        if not good[0]: return None
        return t[(np.argmin(good) if not good.all() else len(t)) - 1]


CORNER_TURN = math.radians(15)   # the flat rear panel ends where the surface turns further than this from straight back
LAMP_LIFT = 0.002                # lamps sit this far in front of the body (m)
# corner lamps: laid into the corner of the rear panel, in units of the panel's height h there: the lamp zone reaches
# ZONE_IN h in from the corner line, the lamps keep ZONE_OUT h clear of it; tail / brake (runlit) above reverse (revlit)
ZONE_IN, ZONE_OUT = 0.55, 0.06
LAMP_ROWS = {"runlit": (0.45, 0.88), "revlit": (0.12, 0.40)}


def _rot_to(a, b):
    """rotation matrix turning unit vector a onto unit vector b (the shortest way)"""
    v = np.cross(a, b); c = float(a @ b)
    if c < -0.999999: return np.diag([1.0, -1.0, -1.0])
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)


def _lamp_samples(XY, tris, k=4):
    """points spread evenly over a lamp's triangles (barycentric grid), with their area weights"""
    pts = []; w = []
    for a, b, c in tris:
        A, B, C = XY[a], XY[b], XY[c]; area = abs(np.cross(B - A, C - A)) / 2
        g = [(i / k, j / k) for i in range(k + 1) for j in range(k + 1 - i)]
        for u, v in g: pts.append(A + u * (B - A) + v * (C - A)); w.append(area / len(g))
    return np.array(pts), np.array(w)


def _place_lamp(H, XY, tris):
    """a lamp laid out flat as seen from behind (XY) set on the body: turned as a whole to the surface where it lands
    (its own orientation: the plane of the body under it), then moved straight back until no part of it is inside the
    body and its nearest point is LAMP_LIFT in front -> positions, normal, rotation, largest gap"""
    S, w = _lamp_samples(XY, tris)
    z, n, hit = H.first_hit(S[:, 0], S[:, 1])
    if not hit.all(): raise SystemExit("rear lamp off the body at %s" % np.round(S[~hit][0], 3))
    # the plane that fits the body under the lamp best (weighted least squares z = a x + b y + c): on a flat face its own
    # plane, on a curved or creased surface the plane closest to all of it
    M = np.c_[S, np.ones(len(S))] * np.sqrt(w)[:, None]
    (pa, pb, _), *_ = np.linalg.lstsq(M, z * np.sqrt(w), rcond=None)
    nb = np.array([pa, pb, -1.0]); nb /= np.linalg.norm(nb)
    R = _rot_to(np.array([0.0, 0.0, -1.0]), nb)
    c = XY.mean(0); cz = H.first_hit([c[0]], [c[1]])[0][0]
    place = lambda Q: np.array([c[0], c[1], cz]) + np.c_[Q - c, np.zeros(len(Q))] @ R.T
    P = place(XY); Sp = place(S)
    zb, _, hb = H.first_hit(Sp[:, 0], Sp[:, 1])
    e = np.where(hb, zb - Sp[:, 2], np.inf)                           # how far each lamp point is in front of the body
    shift = e.min() - LAMP_LIFT
    P[:, 2] += shift
    return P, nb, R, float((e - shift)[np.isfinite(e)].max())


def fit_rear_lamps(model, byname, faces, to_sr3, dy):
    """ST205's rear lamps (runlit_bl: two corner tail / brake lamps + the centre high-mount; revlit_bl: two reverse
    lamps) on the Hornet, found from the Hornet's own body; the lamps keep their lens triangles, material, UVs and
    lit / unlit behaviour:
      - rear panel: from the height of ST205's corner lamps above the ground, walk over the Hornet's rear (seen from
        behind) out to each side to the corner line, where the panel turns away from the rear, and up and down to its
        top and bottom; the corner lamps go into that corner (ZONE_IN / ZONE_OUT / LAMP_ROWS, in panel heights);
      - centre high-mount: on the middle line, centred on its rearmost point above the panel (the deck lid's edge);
      - every lamp is then turned to the surface where it lands and laid on it (_place_lamp), so each corner lamp takes
        its own orientation, whatever the shape of the corner; mirror-symmetric because the body is."""
    T = []; N = []
    for f in faces:
        if f["mat"]["translucent"]: continue
        Q = to_sr3(f["P"])
        for a, b, c in ([(0, 1, 2), (0, 2, 3)] if len(Q) == 4 else [(0, 1, 2)]): T.append(Q[[a, b, c]]); N.append(f["n"])
    H = RearCaster(np.array(T), np.array(N))

    def pieces_of(nm):
        m0 = model.meshes[byname[nm].mesh]
        A = np.frombuffer(m0.vdata, np.uint8).reshape(-1, m0.stride)
        P = A[:, :12].copy().view("<f4").reshape(-1, 3).astype(np.float64)
        Nv = A[:, 16:28].copy().view("<f4").reshape(-1, 3).astype(np.float64)
        out = []
        for gi, g in enumerate(m0.groups):
            tris = [t for t in _strip_tris(m0, g) if Nv[list(t)].mean(0)[2] < -0.5]            # the lens: faces the rear
            parent = {}
            def root(v):
                while parent.setdefault(v, v) != v: v = parent[v]
                return v
            for t in tris:
                for v in t[1:]: parent[root(v)] = root(t[0])
            pcs = {}
            for t in tris: pcs.setdefault(root(t[0]), []).append(t)
            lamps = {}
            for pc in pcs.values():                                    # the pieces touching the middle line: one lamp
                vs = sorted(set(v for t in pc for v in t)); x = P[vs, 0]
                key = "centre" if x.min() <= 1e-3 and x.max() >= -1e-3 else ("right" if x.mean() > 0 else "left")
                lamps.setdefault(key, []).extend(pc)
            out.append((gi, lamps))
        return m0, P, out

    # the rear panel's corner, per side, at the height ST205's corner lamps have above the ground
    m0, P0, gl0 = pieces_of("runlit_bl")
    seed = np.concatenate([P0[sorted(set(v for t in tl for v in t)), 1] for _, lamps in gl0
                           for k, tl in lamps.items() if k != "centre"]).mean() + dy
    zone = {}; out = {}
    # the middle line above the rear panel: its rearmost point (the deck lid's edge, a lip or spoiler) carries the high-mount
    top = seed + (H.walk(0.0, seed, 0.0, 1.0) or 0.0)
    ys = np.arange(top, H.a[:, 1].max() + 0.002, 0.002); zl, _, hl = H.first_hit(np.zeros(len(ys)), ys)
    y_lip = ys[np.argmin(np.where(hl, zl, np.inf))]
    out["centre_lip_y"] = round(float(y_lip), 3)
    for side, key in ((1.0, "right"), (-1.0, "left")):
        xc = H.walk(0.0, seed, side, 0.0)
        if xc is None: raise SystemExit("no flat rear panel on the middle line at height %.3f" % seed)
        up = H.walk(0.0, seed, 0.0, 1.0); dn = H.walk(0.0, seed, 0.0, -1.0); h = up + dn
        xm = side * (xc - ZONE_IN * h / 2)                             # the panel's top and bottom at the lamp zone
        up = H.walk(xm, seed, 0.0, 1.0); dn = H.walk(xm, seed, 0.0, -1.0)
        if up is None or dn is None: raise SystemExit("rear panel corner not flat at x %.3f" % xm)
        y0 = seed - dn; h = up + dn
        zone[key] = dict(corner=xc, x=(xc - ZONE_IN * h, xc - ZONE_OUT * h), y0=y0, h=h)
        out["panel_" + key] = dict(corner_x=round(side * xc, 3), y=[round(y0, 3), round(y0 + h, 3)])

    for nm in ("runlit_bl", "revlit_bl", "runlit_blx02", "revlit_blx02"):
        if nm not in byname or byname[nm].mesh is None: continue
        m0, P, groups = pieces_of(nm)
        A = np.frombuffer(m0.vdata, np.uint8).reshape(-1, m0.stride).copy()
        Nn = A[:, 16:28].copy().view("<f4").reshape(-1, 3).astype(np.float64)
        Bn = A[:, 28:40].copy().view("<f4").reshape(-1, 3).astype(np.float64)
        newP = P.copy(); keep_all = []
        row = LAMP_ROWS["runlit" if nm.startswith("runlit") else "revlit"]
        for gi, lamps in groups:
            keep = []
            for key, tl in lamps.items():
                vs = sorted(set(v for t in tl for v in t)); Q = P[vs]
                if key == "centre":
                    XY = np.c_[Q[:, 0], Q[:, 1] - (Q[:, 1].min() + Q[:, 1].max()) / 2 + y_lip]
                    loc_ = {v: i for i, v in enumerate(vs)}
                    S_, _ = _lamp_samples(XY, [(loc_[a], loc_[b], loc_[c]) for a, b, c in tl])
                    for _k in range(100):                              # never past the top of the body: slide it down
                        if H.first_hit(S_[:, 0], S_[:, 1] - 0.002 * _k)[2].all(): break
                    XY[:, 1] -= 0.002 * _k
                else:
                    zn = zone[key]; side = 1.0 if key == "right" else -1.0
                    lo, hi = Q.min(0), Q.max(0)
                    fx = (side * Q[:, 0] - side * (lo[0] if side > 0 else hi[0])) / max(hi[0] - lo[0], 1e-9)   # 0 inner .. 1 outer
                    fy = (Q[:, 1] - lo[1]) / max(hi[1] - lo[1], 1e-9)
                    X = side * (zn["x"][0] + fx * (zn["x"][1] - zn["x"][0]))
                    Y = zn["y0"] + zn["h"] * (row[0] + fy * (row[1] - row[0]))
                    XY = np.c_[X, Y]
                loc = {v: i for i, v in enumerate(vs)}
                Pl, nb, R, gap = _place_lamp(H, XY, [(loc[a], loc[b], loc[c]) for a, b, c in tl])
                newP[vs] = Pl; Nn[vs] = nb
                Bf = Bn[vs] * np.array([1.0, 1.0, 0.0]); Bf /= np.maximum(np.linalg.norm(Bf, axis=1, keepdims=True), 1e-9)
                Bn[vs] = Bf @ R.T
                keep += tl
                out["%s_%s" % (nm, key)] = dict(min=np.round(Pl.min(0), 3).tolist(), max=np.round(Pl.max(0), 3).tolist(),
                                                 normal=np.round(nb, 3).tolist(), largest_gap=round(gap, 4))
            keep_all.append((m0.groups[gi], keep))
        A[:, :12] = newP.astype("<f4").view(np.uint8).reshape(-1, 12)
        A[:, 16:28] = Nn.astype("<f4").view(np.uint8).reshape(-1, 12)
        A[:, 28:40] = Bn.astype("<f4").view(np.uint8).reshape(-1, 12)
        idx = []; gl = []
        for g, keep in keep_all:
            Pw = {v: newP[v] for t in keep for v in t}
            st = strip_of([tri_order(a_, b_, c_, Pw, Nn[a_]) for a_, b_, c_ in keep]) or [g[0], g[0], g[0]]
            gl.append([g[0], g[1], len(idx), (g[3] & 0xFFFF0000) | len(st), g[4]]); idx += st
        hdr = list(m0.hdr); hdr[7] = len(idx)
        ib = struct.pack("<%dH" % len(idx), *idx)
        model.meshes[byname[nm].mesh] = carmodel.Mesh(hdr, gl, A.tobytes(), ib, b"\0" * (-len(ib) % 4))
    return out

def _world(model):
    def M(n):
        r = struct.unpack("<16f", n.matrix); m = np.array(r, float).reshape(4, 4); return m
    out = {}
    for i, n in enumerate(model.nodes):
        m = M(n); p = n.parent
        while p is not None:
            m = m @ M(model.nodes[p]); p = model.nodes[p].parent
        out[i] = m
    return out


def all_ids_of(files):
    s = set()
    for f in files.values():
        for c in f.chunks: s.add(c.id)
        s.update(carmodel.placeholders(f))
    return s


def fresh_map(files, tag, handling):
    """fresh ids for every id that only the donors (ST205, the handling donor) use; ids other cars share stay"""
    owner = {}
    for car in car_clone.TEN:
        for kind, p in car_clone.car_files(car):
            if not os.path.exists(p): continue
            f = sbfw.read_sbf(p)
            for c in f.chunks:
                owner.setdefault(c.id, set()).add(car)
                for r in c.refs(): owner.setdefault(r, set()).add(car)
            for ph in carmodel.placeholders(f): owner.setdefault(ph, set()).add(car)
    taken = set(owner) | all_ids_of(files)
    donors = {"st205", handling}
    return {i: carmodel.fresh_id(tag, i, taken) for i in sorted(all_ids_of(files))
            if (i in owner and owner[i] <= donors) or i in CHANGED}


def _face_normal(P, n_old):
    """unit normal of a (possibly stretched) face, on the side of the old one"""
    n = np.cross(P[1] - P[0], P[-1] - P[0]); l = np.linalg.norm(n)
    if l < 1e-12: return n_old
    n /= l
    return n if n @ n_old >= 0 else -n


def nearest(P, Q, chunk=512):
    """index of the nearest row of P for every row of Q (brute force in chunks)"""
    out = np.zeros(len(Q), np.int64)
    P2 = (P ** 2).sum(1)
    for k in range(0, len(Q), chunk):
        q = Q[k:k + chunk]
        d = P2[None, :] - 2 * q @ P.T
        out[k:k + chunk] = d.argmin(1)
    return out


class Nearest:
    def __init__(self, P): self.P = P
    def query(self, Q): return nearest(self.P, Q)


def transfer_dirt(faces, body_uv, to_sr3, to_st, grid, st, src, size, pad=2):
    """dirt texture (ST205's pack texture: tangent-space normal map, mud mask in alpha) for the new atlas. Each body cell
    takes the ST205 livery vertex nearest to its centre (car boxes matched) and that vertex's triangle: the UV there plus the
    triangle's UV-per-metre map of the offset gives every texel its place in ST205's texture (no seam crossings, the
    mud keeps its scale)."""
    out = np.zeros((size, size, 4), np.float32); out[..., :3] = src[..., :3].reshape(-1, 3).mean(0); out[..., 3] = 0
    H, W = src.shape[:2]
    P, UV, tri_of, index = st["P"], st["UV"], st["tri_of"], st["index"]
    for i, uv in body_uv.items():
        f = faces[i]; Q = to_sr3(f["P"])
        x0, y0 = np.round(uv.min(0) * size).astype(int); x1, y1 = np.round(uv.max(0) * size).astype(int)
        w = max(1, x1 - x0); h = max(1, y1 - y0)
        ys, xs = np.mgrid[0:h, 0:w]
        S = (xs + 0.5) / w; T = (ys + 0.5) / h
        if len(Q) == 3:
            tot = np.maximum(S + T, 1e-9); over = tot > 1; S = np.where(over, S / tot, S); T = np.where(over, T / tot, T)
        Pt = to_st(param_points(Q, S, T).reshape(-1, 3))
        c = Pt.mean(0, keepdims=True)
        v = int(index[grid.query(c)[0]])
        # offset: our own face plane at ST205's median texel density (uv per metre), mirrored inside +-r around the
        # matched place, so the grain keeps its size and never runs off the island
        n = f["n"]; e1 = Q[1] - Q[0]; e1 -= n * (e1 @ n); e1 /= max(np.linalg.norm(e1), 1e-12); e2 = np.cross(n, e1)
        Ps = param_points(Q, S, T).reshape(-1, 3) - Q.mean(0)
        off = np.stack([Ps @ e1, Ps @ e2], 1) * st["uvpm"]
        r = st["window"]
        m = np.mod(off + r, 4 * r); off = np.abs(m - 2 * r) - r
        uvv = UV[v] + off
        px = np.clip((uvv[:, 0] * W).astype(int), 0, W - 1); py = np.clip((uvv[:, 1] * H).astype(int), 0, H - 1)
        block = np.pad(src[py, px].reshape(h, w, 4), ((pad, pad), (pad, pad), (0, 0)), mode="edge")
        ya, xa = y0 - pad, x0 - pad
        yb, xb = min(size, ya + block.shape[0]), min(size, xa + block.shape[1])
        out[max(0, ya):yb, max(0, xa):xb] = block[max(0, -ya):max(0, -ya) + yb - max(0, ya), max(0, -xa):max(0, -xa) + xb - max(0, xa)]
    return np.clip(out, 0, 255)


MUD_REACH = 0.12           # metres (ST205 space)


def mud_shell(m, faces, body_uv, to_sr3, to_st):
    """the mud / snow shell over the Daytona body, packed as the mud shader (bb24264c) reads it:
      xyzw    position on the body; w = pack scale = max(1, largest |target coordinate|)
      normal, binormal (float3 each), colour D3DCOLOR (A = morph start; SEGA: 128,128,127,255 everywhere)
      texcoord0 SHORT4N x w: u, v, target x, target y      texcoord1 SHORT4N x w: target z, target normal xyz
    The shader moves each vertex from its position towards the target by colour.a + gfMudMeshInterpExtra (the mud
    building up). Targets: the body point moved out along the face normal by the mud thickness of ST205's shell at the
    matching place (ST205: 1.6 cm mean, 8.5 cm max)."""
    st = m.stride
    A = np.frombuffer(m.vdata, np.uint8).reshape(-1, st)
    P0 = A[:, :12].copy().view("<f4").reshape(-1, 3).astype(np.float64)
    W0 = A[:, 12:16].copy().view("<f4").ravel().astype(np.float64)
    S0 = A[:, 44:60].copy().view("<i2").reshape(-1, 8).astype(np.float64) / 32767.0 * W0[:, None]
    N0 = A[:, 16:28].copy().view("<f4").reshape(-1, 3).astype(np.float64)
    thick = ((S0[:, 2:5] - P0) * N0).sum(1)                       # ST205: target - position along the normal
    def s16(x): return np.clip(np.round(np.asarray(x) * 32767.0), -32767, 32767).astype("<i2")
    per = []
    for i in body_uv:
        f = faces[i]; Q = to_sr3(f["P"]); n = f["n"]
        qs = to_st(Q); j = nearest(P0, qs)
        # SEGA's shell covers only where mud collects (rockers, bumpers, arches): a face joins when its matched place
        # (car boxes matched) lies within reach of ST205's shell
        if np.linalg.norm(P0[nearest(P0, qs.mean(0, keepdims=True))[0]] - qs.mean(0)) > MUD_REACH: continue
        t = Q[1] - Q[0]; t -= n * (t @ n); t /= max(np.linalg.norm(t), 1e-12)
        recs = []
        for k in range(len(Q)):
            tgt = Q[k] + n * max(float(thick[j[k]]), 0.004)
            w = max(1.0, float(np.abs(tgt).max()))
            rec = bytearray(A[j[k]].tobytes())                        # keeps ST205's colour
            struct.pack_into("<4f", rec, 0, Q[k][0], Q[k][1], Q[k][2], w)
            struct.pack_into("<3f", rec, 16, *n); struct.pack_into("<3f", rec, 28, *t)
            uv = body_uv[i][k]
            rec[44:52] = s16(np.array([uv[0], uv[1], tgt[0], tgt[1]]) / w).tobytes()
            rec[52:60] = s16(np.array([tgt[2], n[0], n[1], n[2]]) / w).tobytes()
            recs.append(bytes(rec))
        per.append((Q, n, recs))
    verts = []; tris = []
    for Q, n, recs in per:
        base = len(verts); verts += recs
        Pw = {base + q: Q[q] for q in range(len(Q))}
        for a, b, c in ([(0, 1, 2), (0, 2, 3)] if len(Q) == 4 else [(0, 1, 2)]):
            tris.append(tri_order(base + a, base + b, base + c, Pw, n))
    stp = strip_of(tris)
    groups = [[0, len(verts), 0, (1 << 16) | len(stp), m.groups[0][4]]]
    for g in m.groups[1:]:                       # the window-mud group: one degenerate triangle
        groups.append([0, 1, len(stp), (1 << 16) | 3, g[4]]); stp = stp + [0, 0, 0]
    hdr = list(m.hdr); hdr[5] = len(verts); hdr[7] = len(stp); hdr[8] = len(groups)
    ib = struct.pack("<%dH" % len(stp), *stp)
    return carmodel.Mesh(hdr, groups, b"".join(verts), ib, b"\0" * (-len(ib) % 4))

def bonnet_offset(st_hood, stBonnet):
    """translation that puts ST205's hood (body space) onto its bonnet model: coarse then fine grid search on the mean
    nearest distance"""
    sub = stBonnet[:: max(1, len(stBonnet) // 300)]
    hood = st_hood[:: max(1, len(st_hood) // 1500)]
    def cost(dy, dz):
        q = sub - np.array([0, dy, dz]); j = nearest(hood, q)
        return np.sqrt(((hood[j] - q) ** 2).sum(1)).mean()
    best = min(((cost(dy, dz), dy, dz) for dz in np.arange(-0.2, 1.21, 0.05) for dy in np.arange(-0.5, 0.31, 0.05)))
    _, by, bz = best
    best = min(((cost(dy, dz), dy, dz) for dz in np.arange(bz - 0.05, bz + 0.051, 0.01) for dy in np.arange(by - 0.05, by + 0.051, 0.01)))
    return np.array([0.0, best[1], best[2]])


def hood_cut(faces, to_sr3):
    """z of the windscreen base: the frontmost point of the faces that look forward and up above the waist"""
    zs = [to_sr3(f["P"])[:, 2].max() for f in faces if f["n"][1] > 0.4 and f["n"][2] > 0.3 and f["P"][:, 1].mean() > 0.9]
    return max(zs) - 0.05 if zs else 0.4


def radial_blur_atlas(w_rgba, allw, w_uv, wfaces):
    """the wheel atlas with every textured cell replaced by its own rotational average (a spinning rim)"""
    out = w_rgba.copy(); size = w_rgba.shape[0]
    for i, f in enumerate(allw):
        if not f["mat"]["textured"] or i not in w_uv: continue
        uv = w_uv[i]; x0, y0 = (uv.min(0) * size).astype(int); x1, y1 = np.ceil(uv.max(0) * size).astype(int)
        cell = out[y0:y1, x0:x1].astype(np.float32)
        if cell.size == 0: continue
        cell[..., :3] = cell[..., :3].mean((0, 1)) * 0.6 + cell[..., :3] * 0.4
        out[y0:y1, x0:x1] = cell
    return out


if __name__ == "__main__":
    main()
