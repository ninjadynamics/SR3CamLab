"""Geometry the 1995 game never needed but SEGA Rally 3's higher cameras show to be missing (classic-sources.md, last
section). Everything works on the importer's face list: (material, section, [corner xyz, SR3 coords], [uv per corner]).

  extra = fill1995.extend_trunks(faces + sky)      tree boards hanging in the air get their trunk continued downwards
  extra = fill1995.island_cap(sky)                 lid on the open ring(s) of backdrop tree walls (castle island)
  extra = fill1995.props(cfg, rd)                  CHECK POINT banners (src_course<N>_props.obj)
  extra = fill1995.ground_skirts(faces + sky, rd)  the 1995 collision ground beside the road that was never drawn (verge)
  python fill1995.py 1                             self-test on Mountain: counts + two pictures in ../previews
None of the functions changes its input; each returns NEW faces only. No new face is coplanar with an old or new one
(checked by `coplanar_report`, run by the self-test)."""
import os, sys, re, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
WORK = os.path.dirname(HERE)
TEXDIRS = []                                                          # folders searched for <material>.png (set by _texdirs)
INFO = {}                                                             # what the last call of each function did

# ---------------------------------------------------------------- helpers
def _texdirs():
    if TEXDIRS: return TEXDIRS
    try:
        import build_classic as BC
        if BC.EXTRA_TEX: TEXDIRS.append(BC.EXTRA_TEX)
        if getattr(BC, 'BAKE_DIR', None): TEXDIRS.append(BC.BAKE_DIR)          # composed tiles of overlay_bake.py
        TEXDIRS.append(os.path.join(os.path.dirname(BC.HI), 'textures'))
    except Exception: pass
    return TEXDIRS
_ALPHA = {}
def tile_alpha(mat):
    """bool array rows x columns, True = opaque texel; None when the tile picture is not found"""
    if mat not in _ALPHA:
        _ALPHA[mat] = None
        for d in _texdirs():
            p = os.path.join(d, mat + '.png')
            if os.path.exists(p):
                from PIL import Image
                _ALPHA[mat] = np.array(Image.open(p).convert('RGBA'))[:, :, 3] > 127; break
    return _ALPHA[mat]
_RGB = {}
def tile_rgb(mat):
    """rows x columns x 4 (RGBA, uint8) of the tile picture; None when it is not found"""
    if mat not in _RGB:
        _RGB[mat] = None
        for d in _texdirs():
            p = os.path.join(d, mat + '.png')
            if os.path.exists(p):
                from PIL import Image
                _RGB[mat] = np.array(Image.open(p).convert('RGBA')); break
    return _RGB[mat]
def _leaf_row(mat, v, u0, u1):
    """True when the opaque texels of tile row v between u0 and u1 are leaf green (a crown, not a stem)"""
    im = tile_rgb(mat)
    if im is None: return False
    th, tw = im.shape[:2]; row = int(np.floor((1.0 - v) * th)) % th; m = max(int(round(abs(u1 - u0) * tw)), 2)
    px = im[row, np.floor(np.linspace(u0, u1, m, endpoint=False) * tw).astype(int) % tw].astype(float); px = px[px[:, 3] > 127]
    return bool(len(px)) and float(px[:, 1].mean()) > 1.08 * float(px[:, 0].mean())
def tile_size(mat):
    m = re.search(r'_(\d+)x(\d+)_', mat); return (int(m.group(1)), int(m.group(2))) if m else (64, 64)
def _normal(P):
    Q = P.tolist() if isinstance(P, np.ndarray) else [(float(p[0]), float(p[1]), float(p[2])) for p in P]; x = y = z = 0.0; a = Q[-1]      # (plain arithmetic, see overlay_bake._newell)
    for b in Q: x += a[1] * b[2] - a[2] * b[1]; y += a[2] * b[0] - a[0] * b[2]; z += a[0] * b[1] - a[1] * b[0]; a = b
    l = (x * x + y * y + z * z) ** 0.5; n = np.array((x, y, z)); return n / l if l > 1e-12 else n

class Index:
    """lying faces (triangles, looked up by x/z) and upright faces (plan segments) of a face list, in a grid.
    (fastgeo.IndexC holds the grid and answers heights / uprights; _OldIndex below is the Python original it was ported from: 4 s to build
    for a whole course, ten times a build, and 170 microseconds a look-up; profile 2026-10-08)"""
    def __init__(self, faces, cell=8.0):
        import fastgeo
        self.cell = cell; self.faces = faces; self._c = None; self._o = None
        if fastgeo.ON:
            try: self._c = fastgeo.IndexC(faces, cell)
            except ValueError: self._c = None
        if self._c is None or fastgeo.CHECK: self._o = _OldIndex(faces, cell)
        if self._c is None: self.heights = self._o.heights; self.uprights = self._o.uprights
        elif not fastgeo.CHECK: self.heights = self._c.heights; self.uprights = self._c.uprights
    def heights(self, x, z, opaque_only=False):                         # (only reached with SR3_FASTGEO_CHECK=1: both answers, compared)
        import fastgeo
        a = self._o.heights(x, z, opaque_only); b = self._c.heights(x, z, opaque_only); fastgeo.note('fill1995.Index.heights', a == b, (x, z, a[:4], b[:4])); return b
    def uprights(self, x, z, r=0.5):
        import fastgeo
        a = self._o.uprights(x, z, r); b = self._c.uprights(x, z, r); fastgeo.note('fill1995.Index.uprights', a == b, (x, z, r, a[:4], b[:4])); return b
class _OldIndex:
    """the Python original of Index (fallback and reference)"""
    def __init__(self, faces, cell=8.0):
        self.cell = cell; self.tri = collections.defaultdict(list); self.seg = collections.defaultdict(list); self.faces = faces
        for fi, fc in enumerate(faces):
            P = np.asarray(fc[2], float); n = _normal(P); cut = fc[0].endswith('_t')
            if abs(n[1]) < 0.3:
                h = P[:, [0, 2]]; d = np.linalg.norm(h[:, None] - h[None], axis=2); i, j = np.unravel_index(np.argmax(d), d.shape)
                rec = (h[i], h[j], P[:, 1].min(), P[:, 1].max(), fi, cut)
                for key in self._cells(np.minimum(h[i], h[j]) - 0.6, np.maximum(h[i], h[j]) + 0.6): self.seg[key].append(rec)
            else:
                for k in range(1, len(P) - 1):
                    T = P[[0, k, k + 1]]
                    for key in self._cells(T[:, [0, 2]].min(0), T[:, [0, 2]].max(0)): self.tri[key].append((T, fi, cut))
    def _cells(self, lo, hi):
        c = self.cell
        return [(i, j) for i in range(int(np.floor(lo[0] / c)), int(np.floor(hi[0] / c)) + 1) for j in range(int(np.floor(lo[1] / c)), int(np.floor(hi[1] / c)) + 1)]
    def heights(self, x, z, opaque_only=False):
        """y of every lying face over / under (x, z) -> [(y, face index)]"""
        out = []
        for T, fi, cut in self.tri.get((int(np.floor(x / self.cell)), int(np.floor(z / self.cell))), ()):
            if cut and opaque_only: continue
            a, b, c = T; d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-9: continue
            u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d; v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
            if u < -1e-6 or v < -1e-6 or u + v > 1 + 1e-6: continue
            out.append((u * a[1] + v * b[1] + (1 - u - v) * c[1], fi))
        return out
    def uprights(self, x, z, r=0.5):
        """upright faces whose plan segment passes within r of (x, z) -> [(ymin, ymax, face index, cut-out)]"""
        out = []; p = np.array([x, z])
        for a, b, y0, y1, fi, cut in self.seg.get((int(np.floor(x / self.cell)), int(np.floor(z / self.cell))), ()):
            e = b - a; t = np.clip(((p - a) @ e) / max(e @ e, 1e-12), 0, 1)
            if np.linalg.norm(a + e * t - p) <= r: out.append((y0, y1, fi, cut))
        return out

def _strip(rd):
    """first and last grid column of the SR3 road per slice"""
    n = len(rd['V']); hw = rd['hw']; wl = rd.get('wl', np.full(n, float(hw))); wr = rd.get('wr', np.full(n, float(hw)))
    return np.clip(hw + np.floor(-wl + 1e-6).astype(int), 0, 2 * hw), np.clip(hw + np.ceil(wr - 1e-6).astype(int), 0, 2 * hw)
_ROADF = []                                                           # road_faces: [signature of the road, its faces]
def road_faces(rd):
    """the strip SEGA Rally 3 draws as road (rd['V'], 1 m columns, from floor(-wl) to ceil(wr) like build_classic) as lying
    faces 'road_proxy': the ground the visual face list no longer holds once load_visual has cut the road out. Used for
    look-ups and previews only, never returned as scenery."""
    if rd is None: return []
    V = rd['V']; code = rd['code']; n, B = code.shape; out = []; c0, c1 = _strip(rd)
    # (asked for eleven times a build with the same road, 0.25 s each: the list is made once per road and handed out as a fresh list of the
    #  same faces. The signature is the CONTENT of the road's arrays, so a road that was changed in any way is made anew.)
    import fastgeo
    sig = (np.asarray(V).tobytes(), np.asarray(code).tobytes(), c0.tobytes(), c1.tobytes()) if fastgeo.ON else None
    if sig is not None and _ROADF and _ROADF[0] == sig: return list(_ROADF[1])
    for i in range(n):
        j = (i + 1) % n
        for c in range(max(c0[i], c0[j]), min(c1[i], c1[j])):
            if min(code[i, c], code[i, c + 1], code[j, c], code[j, c + 1]) < 0: continue
            out.append(('road_proxy', 'road', [tuple(V[i, c]), tuple(V[i, c + 1]), tuple(V[j, c + 1]), tuple(V[j, c])], [(0, 0), (1, 0), (1, 1), (0, 1)]))
    if sig is not None: _ROADF[:] = [sig, list(out)]
    return out

def _stem_runs(al, row, u0, u1):
    tw = al.shape[1]; m = max(int(round(abs(u1 - u0) * tw)), 2); cols = np.floor(np.linspace(u0, u1, m, endpoint=False) * tw).astype(int) % tw
    r = al[row, cols]; return float(r.mean()), int((r[1:] & ~r[:-1]).sum() + int(r[0]))

def hanging_boards(faces, gap=1.0, ix=None, sunk=1.5):
    """upright cut-out boards whose tile shows something (a trunk, a post) on the board's lowest edge and that have
    nothing under that edge within `gap` m: no lying face (one up to `sunk` m ABOVE the edge counts: the foot is in the
    ground), no upright face reaching lower.
    -> [(face index, i, j)]: corners i -> j are the lowest edge, in the face's own winding order"""
    ix = ix or Index(faces); out = []; tiles = collections.Counter()
    for fi, (mat, sec, P, UV) in enumerate(faces):
        if not mat.endswith('_t') or len(P) != 4: continue
        P = np.asarray(P, float); n = _normal(P)
        if abs(n[1]) > 0.3: continue
        al = tile_alpha(mat)
        if al is None: continue
        e = min(range(4), key=lambda i: P[i, 1] + P[(i + 1) % 4, 1]); i, j = e, (e + 1) % 4
        if abs(P[i, 1] - P[j, 1]) > 0.5 * np.linalg.norm(P[i] - P[j]) + 0.05: continue          # the low edge must be a bottom, not a side
        th, tw = al.shape; uv = np.asarray(UV, float); up = uv[(j + 1) % 4] - uv[j]              # uv step from the low edge into the board
        if abs(up[1]) < 1e-6: continue                                                            # tile rows must run across the board
        v_in = uv[i, 1] + np.sign(up[1]) * 1.0 / th; row = int(np.floor((1.0 - v_in) * th)) % th
        frac, runs = _stem_runs(al, row, uv[i, 0], uv[j, 0])
        if frac == 0 or frac > 0.5 or runs > 2: continue                                          # nothing to continue / a sheet (ivy, fence panel, hedge), not one or two stems
        base = min(P[i, 1], P[j, 1]); held = False
        for t in (0.25, 0.5, 0.75):
            q = P[i] + (P[j] - P[i]) * t
            if any(base - gap <= y <= q[1] + sunk for y, k in ix.heights(q[0], q[2]) if k != fi): held = True; break
            if any(y0 < base - 0.05 and y1 > base - gap for y0, y1, k, cut in ix.uprights(q[0], q[2]) if k != fi): held = True; break
        if not held: out.append((fi, i, j)); tiles[mat] += 1
    INFO['hanging_tiles'] = dict(tiles)
    return out

# ---------------------------------------------------------------- smeared tiles
def unsmear(faces, origin=None, skip=(), ratio=10.0, min_area=10.0, classes=('rock', 'grass', 'dirt', 'sand', 'gravel')):
    """-> (faces, n). 1995 polygons of natural ground whose tile is stretched more than `ratio` times further one way than the other
    (the end caps of the cliff curtains of sections 1284 / 1285: 6 texels across 12 m, 256 texels up 30 m - a face of horizontal
    streaks, user 2026-10-08, shot 001437) get the density of their GOOD direction both ways. The picture keeps its place at the
    polygon's middle and its direction; polygons stacked on one another keep meeting (same width = same new uv on shared corners).
    skip: ids of faces to leave alone (front / back pairs are found by id)."""
    import retex, overlay_bake as OB
    origin = OB.ORIGIN if origin is None else origin; lab = {k: v[0] for k, v in retex.labels().items()}; out = []; n = 0
    for fc in faces:
        mat, sec, P, UV = fc; m0 = str(mat).split('|')[0]
        if id(fc) in skip or m0.endswith('_t') or len(P) < 3 or lab.get(origin.get(m0, m0)) not in classes: out.append(fc); continue
        Pn = np.asarray(P, float); U = np.asarray(UV, float); nrm, ar = OB._newell(Pn)
        if ar < min_area: out.append(fc); continue
        B = OB._basis(Pn); Q = OB._to2(Pn, B); M = np.linalg.lstsq(np.c_[Q, np.ones(len(Q))], U, rcond=None)[0][:2].T
        tw, th = tile_size(m0); a, sv, bt = np.linalg.svd(M * np.array([[tw], [th]]))                  # texels per metre
        if sv[1] > 1e-9 and sv[0] / sv[1] <= ratio: out.append(fc); continue
        M2 = (a @ np.diag([sv[0], sv[0]]) @ bt) / np.array([[tw], [th]]); U2 = U.mean(0) + (Q - Q.mean(0)) @ M2.T
        out.append((mat, sec, P, [tuple(map(float, u)) for u in U2])); n += 1
    INFO['unsmear'] = n
    return out, n

# ---------------------------------------------------------------- 1. trunks
UNGROUNDED = []                                                        # extend_trunks: indices (into its face list) of stem boards with no ground within reach
def extend_trunks(faces, depth=8.0, gap=1.0, floor=None, rd=None, max_depth=40.0, limit=None, classes=None):
    """-> extra faces: one quad under every hanging board (see hanging_boards): down to 0.3 m under the first lying face
    below its foot when there is one within max_depth (rd given: the road grid counts as ground too), else `depth` m
    straight down; never below `floor` if given; same cut-out material, mapped on the tile rows 0.5 .. 1.5 texels inside the board's lowest edge:
    the stem simply continues. uv stay inside the uv range of the board they continue. Boards that share their lowest
    edge get ONE quad; a quad that would lie in the plane of an existing upright face below it is shortened or dropped."""
    allf = list(faces) + road_faces(rd); ix = Index(allf); out = []; seen = set(); cut_short = 0; ends = collections.Counter(); lab = None; UNGROUNDED[:] = []
    if classes:                                                        # limit / classes (import_classic): only tiles of these label classes are continued (a canopy or tree-line board continued downwards is a wall of streaks), and never further than `limit` m: the hillside of the hand fill is the ground
        import retex
        lab = {k: v[0] for k, v in retex.labels().items()}
    for fi, i, j in hanging_boards(allf, gap, ix):
        mat, sec, P, UV = faces[fi]; P = np.asarray(P, float); uv = np.asarray(UV, float); tw, th = tile_size(mat)
        key = tuple(sorted((tuple(np.round(P[i], 2)), tuple(np.round(P[j], 2)))))
        if key in seen: continue
        seen.add(key); d = depth; n = _normal(P); mid = (P[i] + P[j]) / 2; base = min(P[i, 1], P[j, 1])
        under = [y for y, k in ix.heights(mid[0], mid[2]) if base - max_depth < y < base]; end = 'air'
        if under: d = base - max(under) + 0.3; end = 'ground'
        if floor is not None and base - d <= floor: d = base - floor; end = 'floor'
        for y0, y1, k, cut in ix.uprights(mid[0], mid[2], 0.05):                                  # upright face in (nearly) the same plane further down
            if k == fi or y1 > base - 0.01: continue
            if abs(_normal(np.asarray(faces[k][2], float)) @ n) > 0.999: d = min(d, base - y1 - 0.05); cut_short += 1
        if d < 0.3: continue
        if lab is not None and lab.get(mat) not in classes: ends['not a stem: left alone'] += 1; continue
        if _leaf_row(mat, uv[i, 1] + np.sign((uv[(j + 1) % 4] - uv[j])[1]) * 1.0 / th, uv[i, 0], uv[j, 0]): ends['leaves on the lowest edge (a crown, no stem): left alone'] += 1; continue      # user, 2026-10-08: "wtf are those green posts, almost every tree has one" = crown boards continued to the ground in leaf green
        if limit is not None and (d > limit or end != 'ground'): ends['no ground within reach: board to be removed'] += 1; UNGROUNDED.append(fi); continue
        ends[end] += 1
        s = np.sign((uv[(j + 1) % 4] - uv[j])[1]); va = uv[i, 1] + s * 1.5 / th; vb = uv[i, 1] + s * 0.5 / th; dn = np.array([0.0, d, 0.0])
        out.append((mat, sec, [tuple(P[j]), tuple(P[i]), tuple(P[i] - dn), tuple(P[j] - dn)], [(uv[j, 0], va), (uv[i, 0], va), (uv[i, 0], vb), (uv[j, 0], vb)]))
    INFO['trunks'] = dict(added=len(out), shortened=cut_short, foot=dict(ends), tiles=INFO.get('hanging_tiles'))
    return out

# ---------------------------------------------------------------- 2. island
def _chains(edges, tol=0.05):
    """join edges (a, b) that share end points into polylines"""
    key = lambda p: tuple(np.round(np.asarray(p) / tol).astype(int)); adj = collections.defaultdict(list)
    for a, b in edges: adj[key(a)].append((key(b), b)); adj[key(b)].append((key(a), a))
    pos = {};
    for a, b in edges: pos[key(a)] = a; pos[key(b)] = b
    left = set(adj); out = []
    while left:
        ends = [k for k in left if len(adj[k]) == 1]; k = ends[0] if ends else next(iter(left)); ch = [k]; left.discard(k)
        while True:
            nx = [q for q, _ in adj[ch[-1]] if q in left]
            if not nx: break
            ch.append(nx[0]); left.discard(nx[0])
        closed = len(ch) > 2 and any(q == ch[0] for q, _ in adj[ch[-1]]); out.append(([np.asarray(pos[k], float) for k in ch], closed))
    return out
def _ears(Q):
    """ear clipping of a simple plan polygon (n x 2) -> index triples"""
    idx = list(range(len(Q))); tri = []
    area = sum(Q[i][0] * Q[(i + 1) % len(Q)][1] - Q[(i + 1) % len(Q)][0] * Q[i][1] for i in range(len(Q)))
    if area < 0: idx.reverse()
    cr = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]); guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1; n = len(idx)
        for k in range(n):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % n]
            if cr(Q[a], Q[b], Q[c]) <= 1e-9: continue
            if any(cr(Q[a], Q[b], Q[p]) > 0 and cr(Q[b], Q[c], Q[p]) > 0 and cr(Q[c], Q[a], Q[p]) > 0 for p in idx if p not in (a, b, c)): continue
            tri.append((a, b, c)); idx.pop(k); break
        else: break
    if len(idx) == 3: tri.append(tuple(idx))
    return tri
def island_cap(backdrop_faces, sink=None, inset=2.0, min_length=80.0, min_turn=150.0):
    """-> extra faces: a lid on every run (>= min_length m) of upright cut-out boards of the backdrop whose TOP edges join
    into a loop or an open arc (an arc is closed with a straight chord): the castle island's tree wall. The lid lies
    `sink` of the wall's height below its top (default: where the wall's tile rows become 90 % opaque + 8 %; the rows
    above are fringe), `inset` m inside the wall; runs that turn less than min_turn degrees in plan are tree lines, not rings;
    and uses the wall's own foliage tile restricted to its fully opaque rows (no new texture; a `col_XXX` name would
    come out as flat grey 150 in build_classic.add_scenery). Triangles; uv span below one repeat."""
    edges = []; info = {}
    for mat, sec, P, UV in backdrop_faces:
        if not mat.endswith('_t') or len(P) != 4: continue
        P = np.asarray(P, float)
        if abs(_normal(P)[1]) > 0.3 or np.ptp(P[:, 1]) < 4.0: continue
        o = np.argsort(P[:, 1]); a, b = P[o[2]], P[o[3]]
        if abs(a[1] - b[1]) < 0.5:
            uv = np.asarray(UV, float); edges.append((tuple(a), tuple(b))); info[tuple(np.round(a, 1))] = info[tuple(np.round(b, 1))] = (mat, np.ptp(P[:, 1]), uv[o[3], 1], uv[o[0], 1])
    out = []; caps = []; ix = Index(backdrop_faces)
    for ch, closed in _chains(edges):
        L = sum(np.linalg.norm(ch[k + 1] - ch[k]) for k in range(len(ch) - 1))
        if L < min_length or len(ch) < 3: continue
        H = np.array([[p[0], p[2]] for p in ch]); D = np.diff(H, axis=0); ang = np.arctan2(D[:, 1], D[:, 0]); turn = abs(np.degrees(np.sum((np.diff(ang) + np.pi) % (2 * np.pi) - np.pi)))
        if turn < min_turn and not closed: continue
        mat, hgt, vt, vb = info[tuple(np.round(ch[0], 1))]; al = tile_alpha(mat); tw, th = tile_size(mat); sk = sink
        if sk is None:
            sk = 0.35
            if al is not None:
                for t in np.linspace(0, 0.9, 46):
                    if al[int(np.floor((1.0 - (vt + (vb - vt) * t)) * th)) % th].mean() >= 0.9: sk = t + 0.08; break
        y = float(np.mean([p[1] for p in ch]) - sk * hgt); Q = np.array([[p[0], p[2]] for p in ch]); c = Q.mean(0)
        Q = Q + (c - Q) / np.maximum(np.linalg.norm(c - Q, axis=1), 1e-6)[:, None] * inset
        while any(abs(h - y) < 0.05 for q in Q[::3] for h, k in ix.heights(q[0], q[1])): y -= 0.1          # never in the plane of a lying backdrop face
        r0, r1 = 0.3 * th, 0.6 * th
        if al is not None:                                             # longest run of fully opaque rows
            full = al.mean(1) > 0.99; best = (0, 0); s = None
            for r in range(th + 1):
                if r < th and full[r]: s = r if s is None else s
                else:
                    if s is not None and r - s > best[1] - best[0]: best = (s, r)
                    s = None
            if best[1] - best[0] >= 4: r0, r1 = best[0] + 1.0, best[1] - 1.0
        lo = Q.min(0); ext = np.maximum(Q.max(0) - lo, 1.0)
        uvf = lambda q: (0.9 * (q[0] - lo[0]) / ext[0], 1.0 - (r0 + (r1 - r0) * (q[1] - lo[1]) / ext[1]) / th)
        for a, b, c_ in _ears(Q):
            T = [Q[a], Q[c_], Q[b]]                                    # ears are counter-clockwise in (x, z) = facing down; reversed = facing up
            if _normal(np.array([(q[0], y, q[1]) for q in T]))[1] < 0: T = T[::-1]
            out.append((mat, 'island_cap', [(float(q[0]), y, float(q[1])) for q in T], [uvf(q) for q in T]))
        caps.append(dict(points=len(ch), closed=closed, length=round(L), turn=round(turn), sink=round(sk, 2), y=round(y, 2), tile=mat, rows=(round(r0), round(r1)), triangles=len(_ears(Q))))
    INFO['island'] = caps
    return out

# ---------------------------------------------------------------- 3. banners
def props(cfg, rd):
    """CHECK POINT banners (classic/courses/<game>/<dir>/src_course<N>_props.obj) -> faces. The 1995 boards are front/back
    pairs in ONE plane: each face is moved 2 cm towards the side it faces (4 cm apart)."""
    import build_classic as BC
    p = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'src_course%s_props.obj' % cfg['course'])
    if not cfg.get('gameplay') or not os.path.exists(p): INFO['props'] = 0; return []
    V = []; VT = []; out = []; mat = None; sec = 'props'; zs = BC.ZS
    for ln in open(p):
        if ln.startswith('v '): x, y, z = map(float, ln.split()[1:4]); V.append((x + rd['ox'], y, zs * z + rd['oz']))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('o '): sec = ln.split()[1]
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]; P = np.array([V[a] for a, b in ix][::int(zs)])
            uv = BC.flip_v([VT[b] for a, b in ix][::int(zs)]); du = np.floor(min(u for u, v in uv)); uv = [(u - du, v) for u, v in uv]      # whole repeats off: u inside 0..1
            P = P + _normal(P) * 0.02; out.append((mat, sec, [tuple(q) for q in P], uv))
    seen = {}; keep = []
    for fc in out:                                                     # two faces in one plane looking the SAME way: keep one
        k = (tuple(sorted(tuple(np.round(q, 2)) for q in fc[2])))
        if k not in seen: seen[k] = 1; keep.append(fc)
    INFO['props'] = len(keep)
    return keep

def handfill_path(cfg):
    return os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'src_course%s_handfill.obj' % cfg['course'])
def handfill(cfg, rd):
    """Authored gap fill (gapfill_gen.py, or a hand-edited file): classic/courses/<game>/<dir>/src_course<N>_handfill.obj,
    classic OBJ coordinates like the course export, one `o` block per object (the importer's section name), `usemtl` = a
    1995 tile of the course. -> faces, corners and uv as written (no shift, nothing dropped). The ROM export never writes
    this file, so a re-export or re-import leaves it alone. Missing file -> []."""
    import build_classic as BC
    p = handfill_path(cfg)
    if not cfg.get('gameplay') or not os.path.exists(p): INFO['handfill'] = 0; return []
    V = []; VT = []; out = []; mat = None; sec = 'hf'; zs = BC.ZS
    for ln in open(p):
        if ln.startswith('v '): x, y, z = map(float, ln.split()[1:4]); V.append((x + rd['ox'], y, zs * z + rd['oz']))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('o '): sec = ln.split()[1]
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]
            out.append((mat, sec, [V[a] for a, b in ix][::int(zs)], [VT[b] for a, b in ix][::int(zs)]))
    INFO['handfill'] = len(out)
    return out
def write_handfill(path, faces, rd, zs, texdir='textures'):
    """faces (SR3 coordinates) -> OBJ + MTL in classic OBJ coordinates, grouped by section then material, fixed number format"""
    by = collections.defaultdict(list)
    for fc in faces: by[fc[1]].append(fc)
    mats = []
    with open(path, 'w', newline='\n') as fo:
        fo.write('# gap fill of the imported course: natural banks where the 1995 data has no polygon (gapfill_gen.py)\n# classic OBJ coordinates; SR3 = (x + ox, y, -z + oz). Read by fill1995.handfill.\n')
        fo.write('mtllib %s\n' % os.path.basename(path).replace('.obj', '.mtl')); nv = 0
        for sec in sorted(by):
            fo.write('o %s\n' % sec); cur = None
            for mat, _, P, UV in sorted(by[sec], key=lambda f: f[0]):
                if mat != cur: fo.write('usemtl %s\n' % mat); cur = mat
                if mat not in mats: mats.append(mat)
                P = list(P)[::int(zs)]; UV = list(UV)[::int(zs)]
                for (x, y, z), (u, v) in zip(P, UV): fo.write('v %.3f %.3f %.3f\nvt %.4f %.4f\n' % (x - rd['ox'], y, (z - rd['oz']) / zs, u, v))
                fo.write('f ' + ' '.join('%d/%d' % (nv + k + 1, nv + k + 1) for k in range(len(P))) + '\n'); nv += len(P)
    with open(path.replace('.obj', '.mtl'), 'w', newline='\n') as fm:
        for mat in sorted(mats): fm.write('newmtl %s\nKd 0.8 0.8 0.8\nmap_Kd %s/%s.png\n' % (mat, texdir, mat))

_SEA_ALL = [False]                                                     # sea_clip: True = every face goes through the loop (the reference run of SR3_FASTGEO_CHECK)
def sea_clip(sea, land, level, cell, sub=10.0, step=2.5, max_h=25.0):
    """the sea sheet without the water that lies under land. sea: quads of `cell` m with uv 0..1 (import_classic); land:
    faces. A point is land when an opaque lying face up to max_h m above the sea covers it (2.5 m lattice; higher land is the
    mountain ribbon, and the water under it is seen from the side). Each quad is cut into
    `sub` m pieces; a piece is left out when it and its eight neighbours are all land; untouched quads stay whole.
    -> (faces, m2 left out)"""
    if not sea: return sea, 0
    P = np.array([q for fc in sea for q in fc[2]]); x0, z0 = P[:, 0].min(), P[:, 2].min(); nx = int(round((P[:, 0].max() - x0) / step)) + 1; nz = int(round((P[:, 2].max() - z0) / step)) + 1
    R = np.zeros((nx, nz), bool); ref_ = None
    import fastgeo
    if fastgeo.ON and len(land) and not _SEA_ALL[0]:                   # the tests of the loop below for all faces at once: only faces that pass them (a tenth: most hold no point of the 2.5 m lattice) go through the loop
        G_ = fastgeo.prep(land); a_ = np.clip(np.ceil((G_.lo[:, [0, 2]] - [x0, z0]) / step).astype(int), 0, [nx - 1, nz - 1]); b_ = np.clip(np.floor((G_.hi[:, [0, 2]] - [x0, z0]) / step).astype(int), 0, [nx - 1, nz - 1])
        go_ = ~np.fromiter((str(fc[0]).endswith('_t') for fc in land), bool, len(land)) & ~(np.abs(G_.nr[:, 1]) < 0.3) & ~(G_.hi[:, 1] <= level) & ~(G_.lo[:, 1] > level + max_h) & ~(b_ < a_).any(1)
        if fastgeo.CHECK: _SEA_ALL[0] = True; ref_ = sea_clip(sea, land, level, cell, sub, step, max_h); _SEA_ALL[0] = False
        land = [land[i] for i in np.nonzero(go_)[0].tolist()]
    for mat, sec, Q, UV in land:
        if str(mat).endswith('_t'): continue
        Q = np.asarray(Q, float); n = _normal(Q)
        if abs(n[1]) < 0.3 or Q[:, 1].max() <= level or Q[:, 1].min() > level + max_h: continue
        H = Q[:, [0, 2]]; a = np.clip(np.ceil((H.min(0) - [x0, z0]) / step).astype(int), 0, [nx - 1, nz - 1]); b = np.clip(np.floor((H.max(0) - [x0, z0]) / step).astype(int), 0, [nx - 1, nz - 1])
        if (b < a).any(): continue
        gx, gz = np.meshgrid(x0 + np.arange(a[0], b[0] + 1) * step, z0 + np.arange(a[1], b[1] + 1) * step, indexing='ij'); ins = np.ones(gx.shape, bool); sg = 0
        ar = sum(H[i, 0] * H[(i + 1) % len(H), 1] - H[(i + 1) % len(H), 0] * H[i, 1] for i in range(len(H)))
        for i in range(len(H)):
            p, q = H[i], H[(i + 1) % len(H)]; cr = (q[0] - p[0]) * (gz - p[1]) - (q[1] - p[1]) * (gx - p[0]); ins &= (cr >= -1e-6) if ar > 0 else (cr <= 1e-6)
        R[a[0]:b[0] + 1, a[1]:b[1] + 1] |= ins
    k = int(round(sub / step)); mx = (nx - 1) // k; mz = (nz - 1) // k; C = np.zeros((mx, mz), bool)
    for i in range(mx):
        for j in range(mz): C[i, j] = R[i * k:(i + 1) * k + 1, j * k:(j + 1) * k + 1].all()
    pad = np.pad(C, 1, constant_values=False); drop = np.ones_like(C)
    for di in (0, 1, 2):
        for dj in (0, 1, 2): drop &= pad[di:di + mx, dj:dj + mz]
    out = []; m = int(round(cell / sub))
    for mat, sec, Q, UV in sea:
        i0 = int(round((Q[0][0] - x0) / sub)); j0 = int(round((Q[0][2] - z0) / sub)); blk = drop[i0:i0 + m, j0:j0 + m]
        if not blk.any(): out.append((mat, sec, Q, UV)); continue
        for a in range(m):
            for b in range(m):
                if blk[a, b]: continue
                xa, xb = Q[0][0] + a * sub, Q[0][0] + (a + 1) * sub; za, zb = Q[0][2] + b * sub, Q[0][2] + (b + 1) * sub
                out.append((mat, sec, [(xa, level, za), (xb, level, za), (xb, level, zb), (xa, level, zb)], [(a / m, b / m), ((a + 1) / m, b / m), ((a + 1) / m, (b + 1) / m), (a / m, (b + 1) / m)]))
    if ref_ is not None: fastgeo.note('fill1995.sea_clip', ref_ == (out, int(drop.sum() * sub * sub)), (len(ref_[0]), len(out)))
    return out, int(drop.sum() * sub * sub)

# ---------------------------------------------------------------- 4. skirts
def _label_tile(faces, classes=('grass', 'rock')):
    """the course's own tile of the first class in `classes` that the label table knows (retex tile_labels.csv), largest
    lying area first; None without a table"""
    try:
        import retex, csv
        lab = {r['tile']: r['class'] for r in csv.DictReader(open(os.path.join(retex.RT, 'tile_labels.csv')))}
    except Exception: return None
    area = collections.Counter()
    for mat, sec, P, UV in faces:
        P = np.asarray(P, float)
        if lab.get(mat) in classes and abs(_normal(P)[1]) > 0.5: area[mat] += np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0]))
    for c in classes:
        best = [m for m, a in area.most_common() if lab[m] == c]
        if best: return best[0]
    return None

def ground_skirts(faces, rd, sea=-0.5, slopes=False, reach=30.0, drop=14.0, tile=None, clear=10.0):
    """-> extra faces beside road slices that have hanging tree boards on that side:
    (1) VERGE: the 1995 game has collision ground beside the road that it never draws (rd['V'] / rd['code'], 1 m cells).
    Every such cell outside the SR3 road strip that no lying visual face covers (within 3 m of its height) is drawn,
    5 cm lower.  (2) only with slopes=True (OFF by default: in the self-test picture the pieces come out as separate
    ramps, some over the sea) SLOPE falling away from the outer end of that ground. Per slice and side: the 1995 collision ground is followed outwards from the centre line
    (rd['code'] >= 0, 1 m columns); the slope starts 0.3 m beyond its last column, 0.15 m lower, and ends `reach` m further
    out and `drop` m lower, but never deeper than 0.5 m under the sea level; two quads across. A slice side is SKIPPED when any lying visual face is over or
    under the slope (real geometry is there), when the ground's end is less than 1 m above the sea, or when the
    slope comes within `clear` m of another part of the course. Only runs of at least 3 slices are built.
    Tile: `tile`, else the course's grass / rock tile from the label table, else the largest lying off-road material."""
    ix = Index(faces); V = rd['V']; code = rd['code']; hw = rd['hw']; cen = V[:, hw]; lat = rd['lat']; n = len(cen); B = code.shape[1]
    allf = list(faces) + road_faces(rd); hang = hanging_boards(allf, 1.0); want = np.zeros((n, 2), bool)
    for fi, i, j in hang:
        b = (np.asarray(allf[fi][2][i]) + np.asarray(allf[fi][2][j])) / 2; k = int(np.argmin(np.hypot(cen[:, 0] - b[0], cen[:, 2] - b[2]))); s = (b - cen[k]) @ lat[k]
        if abs(s) < hw + reach: want[[(k + t) % n for t in range(-3, 4)], int(s > 0)] = True
    tile = tile or _label_tile(faces)
    if tile is None:
        area = collections.Counter()
        for mat, sec, P, UV in faces:
            P = np.asarray(P, float)
            if not (mat.endswith('_t') or mat.startswith('col_')) and abs(_normal(P)[1]) > 0.5: area[mat] += np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0]))
        tile = area.most_common(1)[0][0] if area else None
    if tile is None: INFO['skirts'] = dict(added=0); return []
    out = []; c0, c1 = _strip(rd); nverge = 0                           # (1) verge: the 1995 collision ground beside the SR3 road that no visual face covers
    for k in range(n):
        k2 = (k + 1) % n
        for sd in (0, 1):
            if not (want[k, sd] or want[k2, sd]): continue
            cols = range(max(c1[k], c1[k2]), B - 1) if sd else range(min(c0[k], c0[k2]) - 1, -1, -1)
            for c in cols:
                if min(code[k, c], code[k, c + 1], code[k2, c], code[k2, c + 1]) < 0: break
                Q = np.array([V[k, c], V[k, c + 1], V[k2, c + 1], V[k2, c]], float); m = Q.mean(0)
                if any(abs(y - m[1]) < 3.0 for y, f in ix.heights(m[0], m[2])): continue
                Q[:, 1] -= 0.05; UV = [((c % 8) / 8.0, (k % 8) / 8.0), ((c % 8 + 1) / 8.0, (k % 8) / 8.0), ((c % 8 + 1) / 8.0, (k % 8 + 1) / 8.0), ((c % 8) / 8.0, (k % 8 + 1) / 8.0)]
                P = [tuple(map(float, q)) for q in Q]
                if _normal(Q)[1] < 0: P = P[::-1]; UV = UV[::-1]
                out.append((tile, 'verge', P, UV)); nverge += 1
    ok = np.zeros((n, 2), bool); A = np.zeros((n, 2, 3)); Bp = np.zeros((n, 2, 3)); why = collections.Counter()
    for k in range(n if slopes else 0):
        for sd in (0, 1):
            if not want[k, sd]: continue
            step = 1 if sd else -1; c = hw
            while 0 <= c + step < B and code[k, c + step] >= 0: c += step
            l = lat[k] * step; e = V[k, c].astype(float)
            if e[1] - sea < 1.0: why['at sea level'] += 1; continue
            a = e + l * 0.3; a[1] = e[1] - 0.15; b = a + l * reach; b[1] = max(sea - 0.5, e[1] - drop)
            pts = [a + (b - a) * t for t in np.linspace(0.02, 1.0, 9)]
            if any(ix.heights(q[0], q[2]) for q in pts): why['geometry there'] += 1; continue
            far = np.abs((np.arange(n) - k + n // 2) % n - n // 2) > 25
            if any(np.min(np.hypot(cen[far, 0] - q[0], cen[far, 2] - q[2])) < clear for q in pts): why['other road near'] += 1; continue
            ok[k, sd] = True; A[k, sd] = a; Bp[k, sd] = b
    nrun = 0
    for sd in (0, 1):
        good = ok[:, sd].copy(); link = np.array([good[k] and good[(k + 1) % n] and (Bp[(k + 1) % n, sd] - Bp[k, sd]) @ (A[(k + 1) % n, sd] - A[k, sd]) > 0 and np.linalg.norm(A[(k + 1) % n, sd] - A[k, sd]) < 6.0 for k in range(n)])
        k = 0
        while k < n:
            if not link[k]: k += 1; continue
            e = k
            while e < n and link[e]: e += 1
            if e - k >= 2:
                nrun += 1
                for q in range(k, e):
                    q2 = (q + 1) % n; a0, b0, a1, b1 = A[q, sd], Bp[q, sd], A[q2, sd], Bp[q2, sd]; m0, m1 = (a0 + b0) / 2, (a1 + b1) / 2
                    u0 = ((q - k) % 8) / 8.0; u1 = u0 + 1 / 8.0
                    for (p, r, s_, t_), (v0, v1) in (((a0, a1, m1, m0), (0.0, 0.5)), ((m0, m1, b1, b0), (0.5, 1.0))):
                        P = [p, r, s_, t_]; UV = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
                        if _normal(np.array(P))[1] < 0: P = P[::-1]; UV = UV[::-1]
                        out.append((tile, 'skirt', [tuple(map(float, x)) for x in P], UV))
            k = e
    INFO['skirts'] = dict(added=len(out), verge_cells=nverge, slope_quads=len(out) - nverge, runs=nrun, slice_sides_ok=int(ok.sum()), wanted=int(want.sum()), skipped=dict(why), tile=tile)
    return out

# ---------------------------------------------------------------- checks
def _overlap2d(A, B, shrink=0.02):
    """convex polygons in a plane (n x 2): True when they overlap by more than `shrink` (separating axis test)"""
    for P, Q in ((A, B), (B, A)):
        for i in range(len(P)):
            e = P[(i + 1) % len(P)] - P[i]; ln = np.linalg.norm(e)
            if ln < 1e-9: continue
            ax = np.array([-e[1], e[0]]) / ln; a = P @ ax; b = Q @ ax
            if a.max() - b.min() < shrink or b.max() - a.min() < shrink: return False
    return True
def coplanar_report(old, new, tol=0.02):
    """number of pairs (a new face, any other face) that lie in ONE plane (normals parallel, within tol) and overlap by
    more than 2 cm: what would z-fight. 0 wanted."""
    allf = list(old) + list(new); recs = []
    for fc in allf:
        P = np.asarray(fc[2], float); recs.append((_normal(P), P.min(0), P.max(0), P))
    grid = collections.defaultdict(list)
    for i, (nr, lo, hi, P) in enumerate(recs):
        for a in range(int(lo[0] // 16), int(hi[0] // 16) + 1):
            for b in range(int(lo[2] // 16), int(hi[2] // 16) + 1): grid[(a, b)].append(i)
    bad = set()
    for i in range(len(old), len(allf)):
        nr, lo, hi, P = recs[i]
        if not nr.any(): continue
        ref = np.array([1.0, 0, 0]) if abs(nr[0]) < 0.9 else np.array([0, 1.0, 0]); e1 = np.cross(nr, ref); e1 /= np.linalg.norm(e1); e2 = np.cross(nr, e1)
        for a in range(int(lo[0] // 16), int(hi[0] // 16) + 1):
            for b in range(int(lo[2] // 16), int(hi[2] // 16) + 1):
                for j in grid[(a, b)]:
                    if j == i or (min(i, j), max(i, j)) in bad: continue
                    n2, lo2, hi2, P2 = recs[j]
                    if abs(nr @ n2) < 0.9995 or np.any(lo > hi2) or np.any(lo2 > hi) or np.abs((P2 - P[0]) @ nr).max() > tol: continue
                    if _overlap2d(np.stack([P @ e1, P @ e2], 1), np.stack([P2 @ e1, P2 @ e2], 1)): bad.add((min(i, j), max(i, j)))
    INFO['coplanar'] = [(allf[i][0], allf[j][0]) for i, j in list(bad)[:6]]
    return len(bad)

# ---------------------------------------------------------------- self-test
def _write_obj(path, faces, rd, zs, texdirs):
    mats = {}
    with open(path, 'w') as fo:
        fo.write('mtllib %s\n' % os.path.basename(path).replace('.obj', '.mtl')); nv = 0; cur = None
        for mat, sec, P, UV in faces:
            if mat != cur: fo.write('usemtl %s\n' % mat); cur = mat; mats[mat] = 1
            P = list(P)[::int(zs)]; UV = list(UV)[::int(zs)]
            for (x, y, z), (u, v) in zip(P, UV): fo.write('v %.4f %.4f %.4f\nvt %.5f %.5f\n' % (x - rd['ox'], y, (z - rd['oz']) / zs, u, v))
            fo.write('f ' + ' '.join('%d/%d' % (nv + k + 1, nv + k + 1) for k in range(len(P))) + '\n'); nv += len(P)
    with open(path.replace('.obj', '.mtl'), 'w') as fm:
        for mat in mats:
            fm.write('newmtl %s\nKd 0.8 0.8 0.8\n' % mat); p = [os.path.join(d, mat + '.png') for d in texdirs if os.path.exists(os.path.join(d, mat + '.png'))]
            if p:
                fm.write('map_Kd %s\n' % p[0].replace(chr(92), '/'))
                if mat.endswith('_t'): fm.write('map_d %s\n' % p[0].replace(chr(92), '/'))
            elif 'sea' in mat: fm.write('Kd 0.24 0.42 0.62\n')
            elif mat == 'road_proxy': fm.write('Kd 0.33 0.34 0.36\n')

def selftest(crs='1', game='src'):
    import course, build_classic as BC, import_classic as IC, render_all as RA
    from PIL import Image, ImageDraw
    cfg = course.use(game, crs); BC.VARIABLE = cfg.get('variable_width', True); rd = BC.import_road()
    BC.EXTRA_TEX = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'textures')
    faces = BC.load_visual(rd); sky, far = IC.backdrop(cfg, rd)
    if sky: sky = BC.stack_layers(BC.dedupe_overlays(sky))
    sea = cfg.get('sea', {}).get('level', -0.5); base = faces + sky
    cap = island_cap(sky); ban = props(cfg, rd); sk = ground_skirts(base, rd, sea=sea); tr = extend_trunks(base + sk, floor=sea - 0.5, rd=rd)
    road = road_faces(rd); hang0 = len(hanging_boards(base + road))
    print('faces: course %d, backdrop %d (far, left out: %d)' % (len(faces), len(sky), far))
    print('hanging boards (road grid counted as ground): %d ; tiles %s' % (hang0, INFO['trunks']['tiles']))
    print('extend_trunks: %s' % {k: v for k, v in INFO['trunks'].items() if k != 'tiles'}); print('ground_skirts:', INFO['skirts']); print('island_cap:', INFO['island']); print('props:', INFO['props'], 'faces')
    new = cap + ban + sk + tr; print('coplanar overlapping pairs involving a new face:', coplanar_report(base + road, new), INFO['coplanar'])
    uv = np.array([q for fc in new for q in fc[3]]); print('uv range of new faces: u %.3f..%.3f v %.3f..%.3f' % (uv[:, 0].min(), uv[:, 0].max(), uv[:, 1].min(), uv[:, 1].max()))
    tmp = os.path.join(WORK, 'tmp', 'fill1995'); os.makedirs(tmp, exist_ok=True); s_ = 1480.0
    seaq = [('sea_flat', 'sea', [(-s_, sea, -s_), (s_, sea, -s_), (s_, sea, s_), (-s_, sea, s_)][::-1], [(0, 0), (1, 0), (1, 1), (0, 1)])]
    pv = os.path.join(WORK, 'previews'); shots = []
    for tag, fl in (('before', base + road + seaq), ('after', base + road + new + seaq)):
        _write_obj(os.path.join(tmp, tag + '.obj'), fl, rd, BC.ZS, _texdirs()); RA.render(os.path.join(tmp, tag + '.obj'), 'fill1995_%s_' % tag, (40, 50))
        shots.append([Image.open(os.path.join(pv, 'fill1995_%s_road_%d.png' % (tag, k))).convert('RGB').resize((960, 540)) for k in (1, 2)])
    o = Image.new('RGB', (1920, 1104), (0, 0, 0)); d = ImageDraw.Draw(o)
    for r in range(2):
        for c in range(2): o.paste(shots[c][r], (c * 960, 24 + r * 540))
    d.text((8, 6), 'fill1995 self-test, %s: left = importer faces as they are, right = + trunks, skirts, island lid, banners (centre-line index 40 and 50)' % cfg['name'], fill=(255, 255, 255))
    o.save(os.path.join(pv, 'fill1995_%s_views.png' % cfg['name']))
    for f in os.listdir(pv):
        if f.startswith('fill1995_before_') or f.startswith('fill1995_after_'): os.remove(os.path.join(pv, f))
    W = 1800; allp = np.array([q for fc in faces for q in fc[2]]); lo = allp.min(0); hi = allp.max(0); c = (lo + hi) / 2; sc = (W - 40) / max(hi[0] - lo[0], hi[2] - lo[2], 1) * 0.8
    px = lambda q: (W / 2 + (q[0] - c[0]) * sc, W / 2 + (q[2] - c[2]) * sc); im = Image.new('RGB', (W, W), (255, 255, 255)); d = ImageDraw.Draw(im)
    for mat, sec, P, UV in road: d.polygon([px(q) for q in P], fill=(170, 170, 175))
    for mat, sec, P, UV in base:
        if not mat.endswith('_t'): d.polygon([px(q) for q in P], fill=(205, 205, 205))
    for fl, col in ((sk, (150, 200, 120)), (cap, (40, 110, 40)), (ban, (0, 0, 255))):
        for mat, sec, P, UV in fl: d.polygon([px(q) for q in P], fill=col, outline=col)
    for mat, sec, P, UV in tr: x, y = px(P[0]); d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(200, 90, 0))
    for k, (col, t) in enumerate((((205, 205, 205), 'existing opaque faces'), ((150, 200, 120), 'ground_skirts'), ((40, 110, 40), 'island_cap'), ((0, 0, 255), 'props (banners)'), ((200, 90, 0), 'extend_trunks (one dot per new quad)'))):
        d.rectangle([20, 18 + 20 * k, 34, 30 + 20 * k], fill=col); d.text((42, 17 + 20 * k), t, fill=(0, 0, 0))
    im.save(os.path.join(pv, 'fill1995_%s_plan.png' % cfg['name'])); print('pictures: previews/fill1995_%s_views.png, fill1995_%s_plan.png' % (cfg['name'], cfg['name']))

if __name__ == '__main__':
    selftest(sys.argv[1] if len(sys.argv) > 1 else '1')


def retile_verge(verge, faces, rd, origin=None, log=print, reach=60.0):
    """Verge cells (the never-drawn 1995 collision ground, all in the course's grass tile) along the FOREST stretch take the
    tile of the nearest lying 1995 rock ground instead: beside the brown cracked ground of the forest road a green patch
    stood out (user's mock-up, 2026-10-07). The forest stretch = road slices that have forest-wall boards (class tree_wall)."""
    import retex
    if origin is None:
        import overlay_bake as OB
        origin = OB.ORIGIN
    lab = {k: v[0] for k, v in retex.labels().items()}; cls = lambda m: lab.get(origin.get(m, m))
    cen = np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]]
    ks = [int(np.argmin(((cen - np.asarray(P, float)[:, [0, 2]].mean(0)) ** 2).sum(1))) for mat, sec, P, UV in faces if str(mat).endswith('_t') and cls(mat) == 'tree_wall']
    if not ks: return verge
    k0, k1 = min(ks) - 20, max(ks) + 20; C = []; M = []               # (as installed in build Z; a trimmed stretch only brought green patches back beside the brown ground near the start)
    for mat, sec, P, UV in faces:
        if str(mat).endswith('_t') or cls(mat) != 'rock' or str(sec).startswith('hf_'): continue
        Q = np.asarray(P, float); n = _normal(Q)
        if abs(n[1]) > 0.5: C.append(Q[:, [0, 2]].mean(0)); M.append(origin.get(mat, mat))
    if not C: return verge
    C = np.array(C); out = []; n_ = 0
    for mat, sec, P, UV in verge:
        c = np.asarray(P, float)[:, [0, 2]].mean(0); k = int(np.argmin(((cen - c) ** 2).sum(1)))
        if sec == 'verge' and k0 <= k <= k1:
            d = ((C - c) ** 2).sum(1); j = int(d.argmin())
            if d[j] <= reach * reach: mat = M[j]; n_ += 1
        out.append((mat, sec, P, UV))
    log('       verge: %d cells of the forest stretch (slices %d..%d) take the nearest 1995 rock ground tile' % (n_, k0, k1))
    return out


def handmodel(cfg, rd, faces, log=print):
    """Hand-made models (plateau1995.py ...): classic/courses/<game>/<dir>/src_course<N>_handmodel.obj, read like the hand fill.
    A material '@near:x,y,z' (OBJ axes) means: the material of the course polygon whose centre is nearest that point - so a
    model can continue a rock face in that face's own (possibly composed) tile without naming it."""
    import build_classic as BC
    p = handfill_path(cfg).replace('_handfill.obj', '_handmodel.obj')
    if not cfg.get('gameplay') or not os.path.exists(p): return []
    V = []; VT = []; out = []; mat = None; sec = 'hm'; zs = BC.ZS; cen = None
    for ln in open(p):
        if ln.startswith('v '): x, y, z = map(float, ln.split()[1:4]); V.append((x + rd['ox'], y, zs * z + rd['oz']))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('o '): sec = ln.split()[1]
        elif ln.startswith('usemtl'):
            mat = ln.split()[1]
            if mat.startswith('@near:'):
                x, y, z = map(float, mat[6:].split(',')); q = np.array([x + rd['ox'], y, zs * z + rd['oz']])
                if cen is None: cen = np.array([np.asarray(fc[2], float).mean(0) for fc in faces])
                ok = np.array([not str(fc[0]).endswith('_t') for fc in faces]); d = ((cen - q) ** 2).sum(1); d[~ok] = 1e18; mat = faces[int(d.argmin())][0]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]
            out.append((mat, sec, [V[a] for a, b in ix][::int(zs)], [VT[b] for a, b in ix][::int(zs)]))
    log('       hand models: %d faces (%s), tiles %s' % (len(out), os.path.basename(p), sorted({str(fc[0])[-18:] for fc in out})))
    return out
