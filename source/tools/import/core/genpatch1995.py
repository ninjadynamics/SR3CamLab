"""WHAT MOUNTAIN'S HAND PATCHES 1 AND 2 DID, AS RULES, FOR ANY 1995 COURSE  ->  a course patch file (coursepatch.py's format).
Full text: docs/kb/26_generalised_patches.md. Nothing here names a course, a tile or a place: what a polygon IS comes from the
importer's own labels (retex.labels(), grouped into ROLES below) and from geometry.

    1  python import_classic.py <game> <course> classic --norender --name step99_gen_x (+ the RAW settings) --set patch_rules=true
           -> work/tmp/genpatch/<game>.<name>.snapshot.pkl  (the faces at the patch stage as plain data + the forest floor, which needs the importer)
              and, when shapely and scipy can be imported there, the patch itself
    2  uv run --with "shapely>=2.1" --with numpy --with scipy python genpatch1995.py <snapshot.pkl> [out.json] [key=value ...]
           -> work/tmp/genpatch/<game>.<name>.rules.json   (+ .report.txt, .views.json)
    3  python import_classic.py ... --set 'patch_files=["<that file>"]'      a build with the patch (it is NOT put in courses/: "patch": true would add it to the hand patches)
    4  ... python genpatch1995.py audit <snapshot.pkl> <patch 1.json> [<patch 2.json> ...]      rule A on patch files made elsewhere (hand patches)

RULES (each is a function below; thresholds in CFG with their reasons in the document)
  H  holes       small closed holes in the solid ground / kerb beside the road are closed over their own corners           (patch 1)
  F  forest      soil from the road's verge to the forest wall (roadfill1995.generate, run in the importer)                (patch 2)
  S  sea         the sea sheet is left whole ("settings": {"sea": {"clip": false}}) when the course has one                 (patch 2)
  P  pavement    a town's paved floor is taken out and laid again as a few big triangles: old extent + the buildings' plan
                 closed up + 1 m + the strip to the road; corners on the road are the road's own; no points inside          (patch 2)
  W  facades     every building front = one flat four-cornered face with one picture composed from the faces it replaces;
                 a new facade at each step of height or change of building; neighbours share corners; feet on the floor    (patch 2)
  R  roofs       every roof = its flat sides, each cut over its outline corners only, welded to facade tops and neighbours  (patch 2)
  D  walls down  a building wall that stays as it is and whose foot hangs above the floor is carried straight down to it    (patch 2)
  A  audit       what the result may not contain: faces without area, slivers, faces lying on one another, folded faces
OPT-IN (the owner's hand edits as far as they go by rule; document section 10; off unless asked for: only=...C G B, forest=..., forest_foot=true)
  C  kerb caps   the open end of a kerb or low wall gets its end face                                                         (patch 1)
  G  gaps        a small hole seen from straight above beside the road is closed with ground                                  (patch 1)
  B  flanks      a building front gets a wall running back under its roof's side eave, wearing the front's picture            (patch 2)
  F  variants    forest=bridges: the band is laid along a 'bridge' too ; forest_foot: corners standing on a kerb top go down to its foot
OPT-IN, patch 3 (the v11 scene, accepted 2026-10-15; document section 12): only=...K T
  K  cliffs down a natural upright face whose foot is an open edge hanging in the air is carried straight down to the sea / the ground
  T  tops        a level rim with its own faces hanging down from it and nothing on top (a stack, a mesa) is capped: grass where trees or grass are"""
import os, sys, json, pickle, math, collections, fnmatch
import numpy as np

ROLES = dict(building=('house*', 'church', 'arcade', 'plaster_wall', 'brick_wall', 'window', 'door'),     # label classes -> what the rules take them for (course setting "patch_roles" replaces single entries)
             roof=('roof',), paving=('cobbles',), board=('sign', 'fence', 'lamp'), forest=('tree_wall',))
CFG = dict(
    forest='default',         # F: 'default' = as approved ; opt-in: 'bridges' = the band is laid along a 'bridge' too ; 'gaps' = bands wider than they are long are kept (the floor between two houses of a forest village) ; 'bridges+gaps'
    towns='paved',            # 'paved': P W R D only for groups of buildings that stand on a paved floor (what the owner approved on Mountain) ; 'all': W R D for every building
    town_link=20.0,           # m: buildings closer than twice this are one town
    close=3.0, margin=1.0,    # P: the buildings' plan is closed up over gaps of 2 x close, and grown by margin ("larger than the building's footprint")
    road_strip=2.5,           # P: a strip narrower than 2 x this between town and road belongs to the pavement (a facade 1.1 m from the road left a 10 cm slit)
    simp=0.15,                # P: outline simplified by this much (m)
    floor_min_width=2.0,      # P: a lying paving face narrower than this is a kerb top, not floor
    floor_min_area=25.0,      # P: a town is paved when it has this much floor (m2)
    level=0.3,                # P: an existing corner more than this above/below the road beside it is a wall top or a bank, not floor
    thru=0.03, near=0.15,     # W: faces within thru of the seed's plane and touching (corners within near) are one wall plane
    join=0.30, ang=14.0, dev=0.25, topdev=0.20,   # W: stretches joined end to end: ends this close, turning less than ang degrees, staying within dev of the straight line, top line within topdev
    under=0.02, maxgap=2.0,   # W D: a foot is carried down to 2 cm under the floor, if the floor is within maxgap below it
    post_reach=1.5, post_width=0.6,   # W: a wall end with a post (an upright face narrower than post_width, from the floor up to the wall's foot) within post_reach stands on posts and is not carried down
    board_absorb=0.10,        # W: a board lying this close to a wall and wholly within it becomes part of the wall's picture (two faces a few cm apart flicker from across the course)
    board_gap=0.30,           # W: a board (sign, fence) standing this close in front of a wall carried down is reported (the importer's gate will list the pair)
    facade_megapixels=12.0,   # W: the composed pictures of one town together (Mountain's town: 8.5)
    roof_simp=0.05, roof_join=0.08, snap_f=0.6, snap_r=0.35,   # R: outline simplification; corners of one roof / of neighbouring roofs / a facade corner under a roof corner brought to one point
    hole_max=2.5, hole_reach=20.0, hole_corners=8,             # H: a hole is closed when its smaller extent is under hole_max, it lies within hole_reach of the centre line and has at most hole_corners corners
    gap_min=0.3, gap_area=20.0, gap_reach=20.0, gap_rise=2.0,  # G (opt-in): a hole seen from above of this size, wholly within gap_reach of the centre line, its rim within gap_rise in height
    foot_min=0.3, foot_max=1.5, forest_foot=False,             # F (opt-in): a kerb is an upright face this tall ; forest_foot = set forest-floor corners standing on a kerb top down to its foot
    flank_min=3.0, flank_expose=0.0,                                          # B (opt-in): a roof eave running back from a front for at least this far gets a flank under it
    cliff_road=12.0, cliff_deck=2.0, cliff_clear=6.0, cliff_run=6.0,           # K: not the sides of the road deck / verge (within cliff_road of the centre line, top less than cliff_deck above it), not onto the road or within cliff_clear of it, runs of foot edges of at least cliff_run m
    cliff_min=0.5, cliff_drop=0.3, cliff_max=80.0, cliff_skip=0.05,            # K (opt-in, patch 3): a rock face's open foot edge at least cliff_min long, hanging more than cliff_drop (up to cliff_max) above the sea or the ground, is carried down to it
    top_min=20.0, top_area=16000.0, top_rise=3.0, top_slope=0.08, top_wall=1.0,   # T (opt-in, patch 3): a hole seen from above of this size whose rim is level (top_rise + top_slope x its width) and whose own faces hang down from it (by top_wall) is a top: capped
    sliver=0.02, onface=0.03)                                  # A: thinner than 2 cm ; lying within 3 cm of another face's plane

def _match(c, pats): return any(fnmatch.fnmatchcase(c or '', p) for p in pats)
def _newell(P):
    n = np.zeros(3)
    for i in range(len(P)): n += np.cross(P[i], P[(i + 1) % len(P)])
    return n
def _area3(P): return 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
def _geoms(g, kind='Polygon', mina=1e-6):
    return [x for x in (g.geoms if hasattr(g, 'geoms') else [g]) if x.geom_type == kind and (kind != 'Polygon' or x.area > mina)]
r3 = lambda p: (round(float(p[0]), 3), round(float(p[1]), 3), round(float(p[2]), 3))
r2 = lambda p: (round(float(p[0]), 3), round(float(p[-1]), 3))

class Scene:
    """the faces of the snapshot in the DECODED scene's coordinates (x, y up, z = -(SR3 z - oz)): the coordinates of a patch file"""
    def __init__(s, S, cfg, log):
        s.S = S; s.cfg = cfg; s.log = log; ox, oz = S['ox'], S['oz']; s.roles = {**ROLES, **(S['cfg'].get('patch_roles') or {})}
        base = lambda m: str(m).split('|')[0]; road = set(S['road_tiles']); rooft = tuple(S['cfg'].get('roof_tiles') or S['cfg'].get('round_exclude') or ())
        s.P = []; s.UV = []; s.mat = []; s.cls = []; s.n = []; s.area = []; s.cut = []; s.road = []; s.role = []
        for m, sec, P, UV in S['faces']:
            Q = np.array([(p[0] - ox, p[1], -(p[2] - oz)) for p in P], float); n = _newell(Q); a = 0.5 * float(np.linalg.norm(n)); n = n / (2 * a) if a > 1e-9 else np.array([0.0, 1.0, 0.0])
            c = S['cls'].get(m) or ''; cut = bool((S['tiles'].get(m) or {}).get('cut')) or base(m).endswith('_t') or str(S['orig'].get(m, '')).endswith('_t')
            role = ''
            if not cut:
                if _match(c, s.roles['roof']) or any(str(S['orig'].get(m, m)).startswith(r) for r in rooft): role = 'roof'
                elif _match(c, s.roles['building']): role = 'building' if abs(n[1]) < 0.3 else 'roof'      # a building's tile lying flat or sloping is its roof (courses without a roof class)
                elif _match(c, s.roles['paving']): role = 'paving'
            if _match(c, s.roles['board']): role = 'board'
            s.P.append(Q); s.UV.append(np.array(UV, float)); s.mat.append(base(m)); s.cls.append(c); s.n.append(n); s.area.append(a); s.cut.append(cut); s.road.append(base(m) in road); s.role.append(role)
        s.N = len(s.P); s.n = np.array(s.n); s.area = np.array(s.area); s.cen = np.array([(p[0] - ox, p[1], -(p[2] - oz)) for p in S['cen']], float); s.ctr = np.array([p.mean(0) for p in s.P])
        s.rm = set(); s.add = []; s.bake = []; s.notes = []; s.views = []; s.moved = {}      # (polygon, its triangle) taken out ; (tile, 3 corners, 3 uv, rule) put in ; facade recipes
        s.tsize = lambda m: ((S['tiles'].get(m) or S['tiles'].get(next((k for k in S['tiles'] if k.split('|')[0] == m), ''), None) or {}).get('size') or (64, 64))
        s.tmean = lambda m: np.array(((S['tiles'].get(m) or S['tiles'].get(next((k for k in S['tiles'] if k.split('|')[0] == m), ''), None) or {}).get('mean') or (128, 128, 128)), float) / 255.0
        from scipy.spatial import cKDTree
        s.roadc = np.array([p for k in range(s.N) if s.road[k] and abs(s.n[k][1]) > 0.7 for p in s.P[k]] or [[0, 0, 0]], float); s.roadkd = cKDTree(s.roadc[:, [0, 2]]); s.cenkd = cKDTree(s.cen[:, [0, 2]])
    def tris(s, k): return [(0, 1, 2)] if len(s.P[k]) == 3 else [(0, 1, 2), (0, 2, 3)]
    def road_y(s, x, z):
        d, i = s.roadkd.query([x, z], k=2); w = 1.0 / np.maximum(d, 1e-6); return float((s.roadc[i, 1] * w).sum() / w.sum())      # level with the road beside it (its two nearest corners)
    def note(s, rule, text): s.notes.append((rule, text)); s.log('       genpatch %s: %s' % (rule, text))
    def put(s, tile, P, UV, rule): s.add.append((tile, [tuple(map(float, p)) for p in P], [tuple(map(float, u)) for u in UV], rule))
    def view(s, name, at, h=30.0, back=35.0):
        i = int(s.cenkd.query([at[0], at[2]])[1]); c = s.cen[i]; d = c - np.asarray(at, float); d[1] = 0; L = float(np.linalg.norm(d)); d = d / L if L > 1e-6 else np.array([1.0, 0, 0])
        s.views.append(dict(name=name, eye=[float(at[0] + d[0] * back), float(at[1] + h), float(at[2] + d[2] * back)], target=[float(x) for x in at]))

class Floor:
    """heights of lying triangles under a point (a grid in plan)"""
    def __init__(s, tris, cell=4.0):
        s.T = [np.asarray(t, float) for t in tris]; s.cell = cell; s.g = collections.defaultdict(list)
        for i, t in enumerate(s.T):
            lo = np.floor(t[:, [0, 2]].min(0) / cell).astype(int); hi = np.floor(t[:, [0, 2]].max(0) / cell).astype(int)
            for x in range(lo[0], hi[0] + 1):
                for z in range(lo[1], hi[1] + 1): s.g[(x, z)].append(i)
    def at(s, x, y, z, drop, up=0.5):
        """the highest surface between y + up and y - drop under (x, z), or None"""
        best = None
        for i in s.g.get((int(math.floor(x / s.cell)), int(math.floor(z / s.cell))), ()):
            a, b, c = s.T[i]; d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-12: continue
            l0 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d; l1 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d; l2 = 1 - l0 - l1
            if min(l0, l1, l2) < -1e-6: continue
            h = l0 * a[1] + l1 * b[1] + l2 * c[1]
            if y - drop <= h <= y + up and (best is None or h > best): best = h
        return best

# ------------------------------------------------------------------------------------------------------------ towns
def towns(sc):
    """groups of buildings, each with its plan closed up; a town is PAVED when it stands on enough lying paving wider than a kerb top"""
    from shapely.geometry import Polygon, LineString
    from shapely.ops import unary_union
    C = sc.cfg; G = []
    for k in range(sc.N):
        if sc.role[k] not in ('building', 'roof') or sc.area[k] < 1e-6: continue
        q = [r2(p) for p in sc.P[k]]; g = Polygon(q)
        G.append(g if (g.is_valid and g.area > 1e-5) else LineString(q + [q[0]]).buffer(0.05))
    if not G: return []
    build = unary_union(G); closed = build.buffer(C['close'] + C['margin'], join_style=2).buffer(-C['close'], join_style=2); out = []
    def width(k):                                                       # the narrow side of a lying face
        g = Polygon([r2(p) for p in sc.P[k]])
        if not g.is_valid or g.area < 1e-6: return 0.0
        r = list(g.minimum_rotated_rectangle.exterior.coords); return min(math.dist(r[0], r[1]), math.dist(r[1], r[2]))
    pav = [k for k in range(sc.N) if sc.role[k] == 'paving' and not sc.road[k] and abs(sc.n[k][1]) > 0.9]
    wide = {k: width(k) >= C['floor_min_width'] for k in pav}
    for blob in _geoms(closed.buffer(C['town_link'])):
        cl = closed.intersection(blob); near = cl.buffer(5.0); tiles = collections.Counter()
        for k in pav:
            if wide[k] and near.intersects(Polygon([r2(p) for p in sc.P[k]]).buffer(0)): tiles[sc.mat[k]] += sc.area[k]
        floor = [t for t, a in tiles.most_common() if a >= C['floor_min_area']]
        out.append(dict(closed=cl, build=build.intersection(blob), scope=cl.buffer(40.0), floor_tiles=floor, paved=bool(floor), area=cl.area))
    out.sort(key=lambda t: -t['area'])
    sc.note('towns', '%d groups of buildings (plan %s m2) ; paved: %s' % (len(out), [round(t['area']) for t in out], [(round(t['closed'].centroid.x), round(t['closed'].centroid.y), [x[-22:] for x in t['floor_tiles']]) for t in out if t['paved']]))
    return out

# ------------------------------------------------------------------------------------------------------------ P pavement
def pavement(sc, T):
    """rule P for one paved town -> the new floor's triangles (for the feet of the walls)"""
    import shapely
    from shapely.geometry import Polygon, Point
    from shapely.ops import unary_union
    C = sc.cfg; scope = T['scope']; inb = lambda k: scope.contains(Point(r2(sc.ctr[k])))
    def poly(k):
        g = Polygon([r2(p) for p in sc.P[k]]); return g if g.is_valid and g.area > 1e-5 else None
    old = [k for k in range(sc.N) if sc.mat[k] in T['floor_tiles'] and sc.role[k] == 'paving' and abs(sc.n[k][1]) > 0.7 and inb(k)]
    big = scope.buffer(40.0); inbig = lambda k: big.contains(Point(r2(sc.ctr[k]))); oldset = set(old)
    roadk = [k for k in range(sc.N) if sc.road[k] and abs(sc.n[k][1]) > 0.7 and inbig(k)]
    gk_ = [k for k in range(sc.N) if k not in oldset and not sc.road[k] and not sc.cut[k] and sc.role[k] in ('', 'paving') and abs(sc.n[k][1]) > 0.9 and inbig(k) and abs(sc.ctr[k][1] - sc.road_y(sc.ctr[k][0], sc.ctr[k][2])) < 3.0]
    extra = [np.array(P) for t, P, UV, r in sc.add if r in ('F', 'H') and abs(np.cross(np.array(P[1]) - P[0], np.array(P[2]) - P[0])[1]) > 0.9 * 2 * _area3(np.array(P)) and big.contains(Point(r2(np.mean(P, 0))))]      # ground laid by the rules before this one (the forest floor) is ground already there: the pavement stops at it
    road = unary_union([g for g in map(poly, roadk) if g]); other = unary_union([g for g in map(poly, gk_) if g] + [Polygon([r2(p) for p in P]).buffer(0) for P in extra]); ground = unary_union([road, other])
    oldu = unary_union([g for g in map(poly, old) if g]); oldu = unary_union([Polygon(g.exterior) for g in _geoms(oldu) if g.area > 1.0])
    closed = T['closed']
    town = unary_union([g for g in _geoms(closed) if g.distance(oldu) < 1.0] + [oldu.buffer(0.3, join_style=2)]); town = unary_union([Polygon(g.exterior) for g in _geoms(town)]).simplify(0.8)
    s_ = C['road_strip']; J = unary_union([town, road]).buffer(s_, join_style=2).buffer(-s_, join_style=2); bridge = J.intersection(town.buffer(4.0)); a0 = town.difference(road).area      # the strip between the buildings and the road
    town = unary_union([town, bridge]); town = unary_union([Polygon(g.exterior) for g in _geoms(town)]).simplify(C['simp']); strip = town.difference(road).area - a0
    region = town.difference(ground); parts = [g for g in _geoms(region) if g.area > 0.2]
    H = {}; RH = {}
    for P in extra:
        for p in P: H[r2(p)] = float(p[1])
    for k in gk_ + roadk:                                               # the road last: where a road corner and another stand at one place in plan, the pavement joins the ROAD's
        for p in sc.P[k]: H[r2(p)] = float(p[1])
    for k in roadk:
        for p in sc.P[k]: RH[r2(p)] = float(p[1])
    gk = np.array(list(H)); gbound = ground.boundary; gin = ground.buffer(-0.01)
    def fix_ring(coords):
        """a corner lying on the border of the ground already there must BE one of its corners: of the four nearest, the one that keeps the piece valid, off the ground, and largest"""
        pts = [(round(x, 3), round(z, 3)) for x, z in coords]; ns = 0
        for i, p in enumerate(pts):
            if p in H or gbound.distance(Point(p)) > 0.02: continue
            best = None
            for j in np.argsort(((gk - p) ** 2).sum(1))[:4]:
                c = tuple(gk[j]); t = pts[:i] + [c] + pts[i + 1:]; t = [q for k, q in enumerate(t) if q != t[k - 1]]
                if len(t) < 3: continue
                g = Polygon(t)
                if not g.is_valid: continue
                if g.intersection(gin).area < 0.01 and (best is None or g.area > best[0]): best = (g.area, c)
            if best is None: best = (0, tuple(gk[np.argmin(((gk - p) ** 2).sum(1))]))
            pts[i] = best[1]; ns += 1
        return [q for k, q in enumerate(pts) if q != pts[k - 1]], ns
    tris = []; nsnap = 0
    for g in parts:
        ext, n1 = fix_ring(list(g.exterior.coords)[:-1]); holes = []
        for h in g.interiors:
            hh, n2 = fix_ring(list(h.coords)[:-1]); n1 += n2
            if len(hh) > 2: holes.append(hh)
        if len(ext) < 3: continue
        nsnap += n1; s = Polygon(ext, holes); s = s if s.is_valid else s.buffer(0)
        for q in _geoms(s, mina=0.05):
            for t in shapely.constrained_delaunay_triangles(q).geoms:
                if t.area > 1e-4: tris.append([(round(x, 3), round(z, 3)) for x, z in list(t.exterior.coords)[:3]])
    n0 = len(tris); tris = [t for t in tris if Polygon(t).intersection(gin).area <= 0.005]      # no triangle may lie on the ground already there
    V = {p for t in tris for p in t}; oldc = {p for p in V if p in H}
    high = {p for p in oldc if p not in RH and abs(H[p] - sc.road_y(*p)) > C['level']}; oldc -= high      # a corner of a wall top or a bank is not floor: the pavement gets a corner of its own there, level with the road
    Y = {p: (H[p] if p in oldc else sc.road_y(*p)) for p in V}
    # the picture: the old floor's own lie (its largest face's mapping, carried on in plan), else the tile's usual density
    tile = T['floor_tiles'][0]; cand = [k for k in old if sc.mat[k] == tile and sc.area[k] > 0.5]; M = None
    for k in sorted(cand, key=lambda k: -sc.area[k]):
        A = np.c_[sc.P[k][:3][:, [0, 2]], np.ones(3)]
        if abs(np.linalg.det(A)) > 1e-6: M = np.linalg.solve(A, sc.UV[k][:3]); break
    if M is None: M = np.array([[0.2, 0.0], [0.0, 0.2], [0.0, 0.0]])
    up = sum(1 for k in old if sc.n[k][1] > 0) * 2 >= len(old) if old else sum(1 for k in roadk if sc.n[k][1] > 0) * 2 >= len(roadk)
    out = []
    for t in tris:
        P = np.array([[p[0], Y[p], p[1]] for p in t])
        if (np.cross(P[1] - P[0], P[2] - P[0])[1] > 0) != up: P = P[::-1]
        sc.put(tile, P, np.c_[P[:, [0, 2]], np.ones(3)] @ M, 'P'); out.append(P)
    for k in old:
        for ti in range(len(sc.tris(k))): sc.rm.add((k, ti))
    allt = unary_union([Polygon(t) for t in tris]) if tris else Polygon(); ar = [Polygon(t).area for t in tris] or [0]
    sc.note('P', 'town at (%.0f, %.0f): floor tile %s ; old floor %d polygons (%.0f m2) out ; new floor %d triangles, %.0f m2 (smallest %.2f, largest %.0f) on %d existing corners (%d the road\'s own) + %d new on the outline, 0 inside ; strip to the road added %.1f m2 ; border points moved onto an existing corner %d ; triangles dropped for lying on ground %d ; wall tops / banks not used as floor %d ; building plan left uncovered %.1f m2 ; old floor left uncovered %.1f m2' % (
        closed.centroid.x, closed.centroid.y, tile[-22:], len(old), sum(sc.area[k] for k in old), len(tris), allt.area, min(ar), max(ar), len(oldc), sum(1 for p in oldc if p in RH), len(V) - len(oldc), strip, nsnap, n0 - len(tris), len(high),
        T['build'].intersection(town).difference(allt).difference(ground.buffer(0.05)).area, oldu.difference(allt).difference(ground.buffer(0.05)).area))
    c = closed.centroid; sc.view('pavement_%d' % len(sc.views), (c.x, sc.road_y(c.x, c.y), c.y), 120.0, 60.0)
    return out

# ------------------------------------------------------------------------------------------------------------ W facades
def wall_planes(sc, T):
    """the upright building faces of a town as triangles, grouped into wall planes (a plane grows from its largest face)"""
    from shapely.geometry import Point
    from scipy.spatial import cKDTree
    C = sc.cfg; tri = []
    for k in range(sc.N):
        if sc.cut[k] or abs(sc.n[k][1]) >= 0.3 or sc.area[k] < 1e-7: continue
        if not (sc.role[k] in ('building', 'roof') or sc.cls[k] == '' or sc.role[k] == 'board'): continue
        if not T['scope'].contains(Point(r2(sc.ctr[k]))): continue
        for ti, ix in enumerate(sc.tris(k)):
            P = sc.P[k][list(ix)]; n = np.cross(P[1] - P[0], P[2] - P[0]); a = 0.5 * float(np.linalg.norm(n))
            if a < 1e-7 or abs(n[1]) / (2 * a) >= 0.3 or (k, ti) in sc.rm: continue
            tri.append(dict(k=k, ti=ti, P=P, UV=sc.UV[k][list(ix)], n=n / (2 * a), a=a, m=sc.mat[k], c=sc.cls[k] if sc.role[k] not in ('roof', 'board') else sc.role[k]))
    if not tri: return []
    pts = np.array([p for t in tri for p in t['P']]); own = np.repeat(np.arange(len(tri)), 3); kd = cKDTree(pts); nb = collections.defaultdict(set)
    for a, b in kd.query_pairs(C['near']):
        if own[a] != own[b]: nb[own[a]].add(own[b]); nb[own[b]].add(own[a])
    G = {}; done = set()
    for seed in sorted(range(len(tri)), key=lambda i: -tri[i]['a']):
        if seed in done: continue
        n = tri[seed]['n']; p0 = tri[seed]['P'][0]; ok = lambda g: abs(tri[g]['n'] @ n) > 0.999 and np.abs((tri[g]['P'] - p0) @ n).max() < C['thru']
        grp = [seed]; done.add(seed); q = [seed]
        while q:
            f = q.pop()
            for g in nb[f]:
                if g not in done and ok(g): done.add(g); grp.append(g); q.append(g)
        G[seed] = grp
    def frame(seed):
        n = tri[seed]['n'].copy(); n[1] = 0; n /= np.linalg.norm(n); return tri[seed]['P'][0].copy(), n, np.cross([0.0, 1.0, 0.0], n)
    # small pieces standing a few centimetres proud of a big wall (shutters, banners, door panels) belong to that wall
    seeds = sorted(G, key=lambda f: -sum(tri[x]['a'] for x in G[f])); AR = {f: sum(tri[x]['a'] for x in G[f]) for f in G}
    for small in list(seeds):
        if small not in G: continue
        gs = G[small]; a_s = sum(tri[x]['a'] for x in gs); tiny = a_s <= 15 and len(gs) <= 8; ps = np.array([p for x in gs for p in tri[x]['P']])
        for big in seeds:
            if big is small or big not in G: continue
            gb = G[big]; a_b = sum(tri[x]['a'] for x in gb)
            if a_b < 50 or a_b <= a_s or abs(tri[small]['n'] @ tri[big]['n']) < 0.99: continue
            sb = set(gb); touch = any(y in sb for x in gs for y in nb[x]); board = all(tri[x]['c'] == 'board' for x in gs)
            if tri[big]['c'] in ('board', 'roof'): continue
            if not board and not tiny and not (touch and abs(tri[small]['n'] @ tri[big]['n']) > 0.999 and a_s <= 200 and a_s < 0.4 * a_b): continue
            p0, n, u = frame(big)
            if np.abs((ps - p0) @ n).max() > (C['board_absorb'] if board else 0.08): continue
            if board: touch = False                                     # a board (sign) flat on a wall is part of that wall only when it lies wholly within it; a row of boards running on past the wall is not
            pb = np.array([p for x in gb for p in tri[x]['P']]); ub = (pb - p0) @ u; us = (ps - p0) @ u
            if touch or (us.min() >= ub.min() - 0.1 and us.max() <= ub.max() + 0.1 and ps[:, 1].min() >= pb[:, 1].min() - 0.1 and ps[:, 1].max() <= pb[:, 1].max() + 0.1):
                G[big] = gb + gs; del G[small]; break
    # corners of each plane and what else hangs on them
    oth = collections.defaultdict(set)
    for k in range(sc.N):
        if sc.cut[k]: continue
        for p in sc.P[k]: oth[r3(p)].add(k)
    out = []
    for g in G.values():
        big = max(g, key=lambda f: tri[f]['a']); o0, n, u = frame(big); ks = {tri[f]['k'] for f in g}
        xy = lambda p: [float((p - o0) @ u), float(p[1] - o0[1])]
        F = [dict(t=tri[f], m=tri[f]['m'], c=tri[f]['c'], p=[xy(p) for p in tri[f]['P']], uv=tri[f]['UV'].tolist()) for f in g]; V = {}
        for f in g:
            for p in tri[f]['P']: V[r3(p)] = p
        A = [dict(i=key, P=p, p=xy(p), w=float((p - o0) @ n), cls=sorted({('roof' if sc.role[k] == 'roof' else ('wall' if sc.role[k] == 'building' else (sc.cls[k] or '-'))) for k in oth[key] if k not in ks})) for key, p in V.items()]
        out.append(dict(o=o0, n=n, u=u, nface=tri[big]['n'], faces=F, verts=A))
    return out

def facades(sc, T, floor):
    """rule W for one town: wall planes -> stretches between the steps of their outline -> facades (ends joined, corners shared) -> two triangles + a picture recipe each"""
    from shapely.geometry import Polygon, box, LineString
    from shapely.ops import unary_union
    C = sc.cfg; D = wall_planes(sc, T); SIMP, MINA = 0.05, 0.02; JOIN, ANG, DEV, TOPDEV = C['join'], C['ang'], C['dev'], C['topdev']
    if not D: return []
    S = []; kept = collections.Counter(); dens = {}; ncuts = 0
    for gi, G in enumerate(D):
        cls = collections.Counter(f['c'] for f in G['faces']).most_common(1)[0][0]
        if not _match(cls, sc.roles['building']): kept['not a building wall'] += 1; continue
        polys = []; dd = []
        for f in G['faces']:
            p = Polygon(f['p']); polys.append(p if p.is_valid else p.buffer(0))
            P = np.array(f['p']); U = np.array(f['uv']) * np.array(sc.tsize(f['m'])); A = np.c_[P[1] - P[0], P[2] - P[0]]
            if abs(np.linalg.det(A)) > 1e-6: Jm = np.c_[U[1] - U[0], U[2] - U[0]] @ np.linalg.inv(A); dd.append((np.linalg.norm(Jm[:, 0]), np.linalg.norm(Jm[:, 1])))
        dens[gi] = (float(np.percentile([d[0] for d in dd], 90)), float(np.percentile([d[1] for d in dd], 90))) if dd else (8.0, 8.0)      # texels a metre
        U0 = unary_union(polys).buffer(0.004, join_style=2).buffer(-0.004, join_style=2)
        U1 = unary_union([Polygon(g.exterior) for g in _geoms(U0)]).simplify(SIMP)             # openings inside the wall do not count
        if U1.is_empty: kept['no area'] += 1; continue
        xs = sorted({round(x, 3) for g in _geoms(U1) for x, y in g.exterior.coords}); keep = []
        for x in xs:
            if not keep or x - keep[-1] > 0.08: keep.append(x)
        if keep[-1] != xs[-1]: keep[-1] = xs[-1]
        # seams between two buildings standing in one plane: an upright line no face crosses, with no tile in common to its left and right, where the colour changes or a roof ends
        roofed = any('roof' in v['cls'] for v in G['verts'])
        FX = [(min(p[0] for p in f['p']), max(p[0] for p in f['p']), f['m'], abs(Polygon(f['p']).area)) for f in G['faces']]; cuts = []
        for x in sorted({round(v, 2) for f in FX for v in f[:2]}):
            if x - keep[0] < 3 or keep[-1] - x < 3 or (cuts and x - cuts[-1] < 3) or any(f[0] < x - 0.03 and f[1] > x + 0.03 for f in FX): continue
            tl = collections.Counter(); tr = collections.Counter()
            for f in FX:
                if x - 8 < (f[0] + f[1]) / 2 < x: tl[f[2]] += f[3]
                elif x < (f[0] + f[1]) / 2 < x + 8: tr[f[2]] += f[3]
            if not (tl and tr) or sum(min(tl[k], tr[k]) for k in tl) / min(sum(tl.values()), sum(tr.values())) >= 0.15: continue
            cl_ = sum(sc.tmean(k) * w for k, w in tl.items()) / sum(tl.values()); cr_ = sum(sc.tmean(k) * w for k, w in tr.items()) / sum(tr.values())
            if roofed or float(np.abs(cl_ - cr_).max()) > 0.06: cuts.append(x)      # (the scene the rule was made on had the roofs cut into small pieces by the build, so "a roof corner stands at the line" was true wherever a roof stood on the wall: that is what is asked here)
        ncuts += len(cuts); keep = sorted(set([k for k in keep if all(abs(k - c) > 0.08 for c in cuts)] + cuts)); bld = lambda x: sum(1 for c in cuts if c < x)
        xs = keep; b = U1.bounds; quads = []
        def spans(x):
            g = U1.intersection(LineString([(x, b[1] - 2), (x, b[3] + 2)])); o_ = []
            for l in (g.geoms if hasattr(g, 'geoms') else [g]):
                if l.geom_type == 'LineString' and l.length > 0.02: ys = [c[1] for c in l.coords]; o_.append((min(ys), max(ys)))
            return o_
        for a0, a1 in zip(xs, xs[1:]):
            w_ = a1 - a0; xl, xr = a0 + 0.2 * w_, a0 + 0.8 * w_; SL, SR = spans(xl), spans(xr)
            for m0, m1 in spans((a0 + a1) / 2):
                L = [s_ for s_ in SL if min(s_[1], m1) - max(s_[0], m0) > 0.5 * (m1 - m0)]; R_ = [s_ for s_ in SR if min(s_[1], m1) - max(s_[0], m0) > 0.5 * (m1 - m0)]
                if len(L) != 1 or len(R_) != 1: L, R_ = [(m0, m1)], [(m0, m1)]
                ex = lambda yl_, yr_, x: yl_ + (yr_ - yl_) * (x - xl) / (xr - xl)
                if (m1 - m0) * w_ < MINA: continue
                quads.append([(a0, ex(L[0][0], R_[0][0], a0)), (a1, ex(L[0][0], R_[0][0], a1)), (a1, ex(L[0][1], R_[0][1], a1)), (a0, ex(L[0][1], R_[0][1], a0))])
        merged = True
        while merged:
            merged = False
            for i, a in enumerate(quads):
                for j, bq in enumerate(quads):
                    if i == j or bld((a[0][0] + a[1][0]) / 2) != bld((bq[0][0] + bq[1][0]) / 2): continue
                    if abs(a[1][0] - bq[0][0]) > 1e-6 or abs(a[1][1] - bq[0][1]) > 0.08 or abs(a[2][1] - bq[3][1]) > 0.08: continue
                    Mq = Polygon([a[0], bq[1], bq[2], a[3]]); strip = box(a[0][0], min(a[0][1], a[1][1], bq[1][1]) - 0.3, bq[1][0], max(a[3][1], a[2][1], bq[2][1]) + 0.3)
                    if Mq.is_valid and Mq.symmetric_difference(U1.intersection(strip)).area < 0.04 * (bq[1][0] - a[0][0]): quads[i] = [a[0], bq[1], bq[2], a[3]]; quads.pop(j); merged = True; break
                if merged: break
        cover = unary_union([Polygon(q).buffer(0) for q in quads]) if quads else Polygon()
        if not quads or U1.difference(cover).area > 0.05 + 0.002 * U1.area: kept['outline is not a few straight-sided pieces'] += 1; continue
        o, u = G['o'], G['u']; pl = lambda x: (float(o[0] + u[0] * x), float(o[2] + u[2] * x))
        for q in quads: S.append(dict(pts=[(pl(q[0][0]), o[1] + q[0][1], o[1] + q[3][1]), (pl(q[1][0]), o[1] + q[1][1], o[1] + q[2][1])], atoms={gi}, bld=(gi, bld((q[0][0] + q[1][0]) / 2))))
    nplanes = len(D); nstretch = len(S); P2 = lambda p: np.array(p, float)
    # a narrow strip of wall with small pieces stacked under or over it in the same span (a door under it) is one strip from foot to top
    changed = True
    while changed:
        changed = False
        for i, a_ in enumerate(S):
            A, B = P2(a_['pts'][0][0]), P2(a_['pts'][-1][0]); L = np.linalg.norm(B - A)
            if L > 4.0 or L < 0.2: continue
            d = (B - A) / L; nrm = np.array([-d[1], d[0]]); ab, at = min(p[1] for p in a_['pts']), max(p[2] for p in a_['pts'])
            for j, b_ in enumerate(S):
                if j == i: continue
                Cc, E = P2(b_['pts'][0][0]), P2(b_['pts'][-1][0]); bb, bt = min(p[1] for p in b_['pts']), max(p[2] for p in b_['pts'])
                if not all(-0.3 < (p - A) @ d < L + 0.3 and abs((p - A) @ nrm) < 0.4 for p in (Cc, E)): continue
                if min(at, bt) - max(ab, bb) > 0.3 or max(ab, bb) - min(at, bt) > 0.4: continue
                a_['pts'] = [(p[0], min(p[1], bb), max(p[2], bt)) for p in a_['pts']]; a_['atoms'] = a_['atoms'] | b_['atoms']; S.pop(j); changed = True; break
            if changed: break
    tiles = {}
    for gi, G in enumerate(D):
        c = collections.Counter()
        for f in G['faces']: c[f['m']] += abs(Polygon(f['p']).area)
        tiles[gi] = c
    def shared(A_, B_):                                                 # how much of the smaller wall is in tiles the other wall has too: two different buildings share none
        ta = sum((tiles[g] for g in A_), collections.Counter()); tb = sum((tiles[g] for g in B_), collections.Counter())
        return sum(min(ta[k], tb[k]) for k in ta) / max(1e-6, min(sum(ta.values()), sum(tb.values())))
    def try_merge(a, b):
        best = None
        for ra in (False, True):
            for rb in (False, True):
                pa = a['pts'][::-1] if ra else a['pts']; pb = b['pts'][::-1] if rb else b['pts']
                if np.linalg.norm(P2(pa[-1][0]) - P2(pb[0][0])) > JOIN or abs(pa[-1][2] - pb[0][2]) > TOPDEV or abs(pa[-1][1] - pb[0][1]) > 0.8: continue
                da = P2(pa[-1][0]) - P2(pa[-2][0]); db = P2(pb[1][0]) - P2(pb[0][0]); ang = math.degrees(math.acos(max(-1, min(1, da @ db / (np.linalg.norm(da) * np.linalg.norm(db))))))
                if ang > ANG: continue
                if a.get('bld') != b.get('bld') and (a['atoms'] == b['atoms'] or shared(a['atoms'], b['atoms']) < 0.05): continue      # another building: its own facade
                Jp = (tuple((P2(pa[-1][0]) + P2(pb[0][0])) / 2), min(pa[-1][1], pb[0][1]), (pa[-1][2] + pb[0][2]) / 2); pts = pa[:-1] + [Jp] + pb[1:]
                A, B = P2(pts[0][0]), P2(pts[-1][0]); ab = B - A; L = np.linalg.norm(ab); dev = 0.0; tdev = 0.0
                if L < 1e-6: continue
                for p, yb, yt in pts[1:-1]:
                    t = (P2(p) - A) @ ab / (L * L)
                    if not 0 < t < 1: dev = 9; break
                    dev = max(dev, abs(float(ab[0] * (P2(p) - A)[1] - ab[1] * (P2(p) - A)[0])) / L); tdev = max(tdev, abs(yt - (pts[0][2] + t * (pts[-1][2] - pts[0][2]))))
                if dev > DEV or tdev > TOPDEV: continue
                if best is None or dev < best[0]: best = (dev, dict(pts=pts, atoms=a['atoms'] | b['atoms'], bld=a.get('bld')))
        return best
    ctr = lambda s: (P2(s['pts'][0][0]) + P2(s['pts'][-1][0])) / 2; rad = lambda s: np.linalg.norm(P2(s['pts'][0][0]) - P2(s['pts'][-1][0])) / 2
    while True:
        cand = None
        for i in range(len(S)):
            for j in range(i + 1, len(S)):
                if np.linalg.norm(ctr(S[i]) - ctr(S[j])) > rad(S[i]) + rad(S[j]) + 1.0: continue
                m = try_merge(S[i], S[j])
                if m and (cand is None or m[0] < cand[0]): cand = (m[0], i, j, m[1])
        if cand is None: break
        _, i, j, m = cand; S[i] = m; S.pop(j)
    def span_of(s):
        A, B = P2(s['pts'][0][0]), P2(s['pts'][-1][0]); return A, B, np.linalg.norm(B - A), min(p[1] for p in s['pts']), max(p[2] for p in s['pts'])
    i = 0                                                               # a small piece standing within the span of a bigger facade (a shutter column a little proud of it) is part of that facade
    while i < len(S):
        A, B, L, yb, yt = span_of(S[i]); host = None
        for j, h in enumerate(S):
            if j == i: continue
            HA, HB, HL, hb, ht = span_of(h)
            if HL < 1e-6 or HL * (ht - hb) < 3 * L * (yt - yb): continue
            d = (HB - HA) / HL; nrm = np.array([-d[1], d[0]])
            if all(-0.3 < (p - HA) @ d < HL + 0.3 and abs((p - HA) @ nrm) < 0.4 for p in (A, B)) and yb > hb - 0.5 and yt < ht + 0.3: host = j; break
        if host is None: i += 1; continue
        S[host]['atoms'] = S[host]['atoms'] | S[i]['atoms']; S.pop(i)
    # ends brought together, corners shared ; corners that roofs and other things hang on stay where they are
    AV = {}
    for G in D:
        for v in G['verts']:
            if any(c != 'wall' for c in v['cls']): AV[v['i']] = v['P']
    AVk = list(AV); AX = np.array([[AV[k][0], AV[k][2]] for k in AVk]) if AV else np.zeros((0, 2)); AY = np.array([AV[k][1] for k in AVk]) if AV else np.zeros(0)
    ends = [(fi, k, P2(s['pts'][0 if k == 0 else -1][0])) for fi, s in enumerate(S) for k in (0, 1)]; par = list(range(len(ends)))
    def find(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            if np.linalg.norm(ends[i][2] - ends[j][2]) < JOIN: par[find(i)] = find(j)
    CL = collections.defaultdict(list)
    for i in range(len(ends)): CL[find(i)].append(i)
    corner = {}; nshared = nreuse = ndown = nprop = 0; boards = []
    posts = np.array([(sc.ctr[k][0], sc.ctr[k][2], sc.P[k][:, 1].min(), sc.P[k][:, 1].max()) for k in range(sc.N) if sc.role[k] != 'board' and not _match(sc.cls[k], sc.roles['forest']) and abs(sc.n[k][1]) < 0.3 and np.hypot(np.ptp(sc.P[k][:, 0]), np.ptp(sc.P[k][:, 2])) < C['post_width'] and np.ptp(sc.P[k][:, 1]) >= 1.0] or np.zeros((0, 4)))
    for ci, mem in CL.items():
        c = np.mean([ends[i][2] for i in mem], 0); hs = []
        for i in mem:
            fi, k, _ = ends[i]; p = S[fi]['pts'][0 if k == 0 else -1]; hs.append((p[1], fi, k, 'b')); hs.append((p[2], fi, k, 't'))
        mb = min(h[0] for h in hs if h[3] == 'b')
        fl = floor.at(float(c[0]), mb, float(c[1]), C['maxgap']) if floor is not None else None      # NO FLOATING WALLS: the foot goes down to 2 cm under the floor when the floor is within reach under it
        if fl is not None and mb - fl > 0.005 and len(posts) and (((posts[:, 0] - c[0]) ** 2 + (posts[:, 1] - c[1]) ** 2 < C['post_reach'] ** 2) & (posts[:, 2] < fl + 0.3) & (posts[:, 3] > mb - 0.3)).any(): mb2 = mb; nprop += 1      # it stands on posts (narrow upright faces from the floor up to its foot): a veranda, not a floating wall
        elif fl is not None and mb - fl > 0.005: mb2 = fl - C['under']; ndown += 1
        else: mb2 = mb
        hs = [(mb2 if (h[3] == 'b' and h[0] - mb < 0.8) else h[0], h[1], h[2], h[3]) for h in hs]; hs.sort(); groups = [[hs[0]]]
        for h in hs[1:]:
            if h[0] - groups[-1][-1][0] < 0.15: groups[-1].append(h)
            else: groups.append([h])
        for gix, g in enumerate(groups):
            y = float(np.mean([h[0] for h in g])) if g[0][3] != 'b' or any(h[3] == 't' for h in g) else float(min(h[0] for h in g)); pos = [float(c[0]), y, float(c[1])]
            if len(AVk) and not (g[0][3] == 'b' and mb2 != mb and abs(y - mb2) < 1e-9):
                d = np.linalg.norm(AX - c, axis=1) + 2 * np.abs(AY - y); j = int(np.argmin(d))
                if np.linalg.norm(AX[j] - c) < 0.35 and abs(AY[j] - y) < 0.15: pos = [float(x) for x in AV[AVk[j]]]; nreuse += 1
            key = (ci, gix); nshared += len({h[1] for h in g}) > 1
            for h in g: corner[(h[1], h[2], h[3])] = dict(key=key, pos=pos)
    pw = lambda x: min(2048, 1 << max(4, math.ceil(math.log2(max(2 * x, 1)) - 0.05))); out = []
    for fi, s in enumerate(S):
        c = [corner[(fi, 0, 'b')], corner[(fi, 1, 'b')], corner[(fi, 1, 't')], corner[(fi, 0, 't')]]; A = P2([c[0]['pos'][0], c[0]['pos'][2]]); B = P2([c[1]['pos'][0], c[1]['pos'][2]]); W = float(np.linalg.norm(B - A))
        if W < 0.05 or len({x['key'] for x in c}) < 4: kept['closed up'] += 1; continue
        y0 = min(x['pos'][1] for x in c); y1 = max(x['pos'][1] for x in c); du = max(dens[g][0] for g in s['atoms']); dv = max(dens[g][1] for g in s['atoms'])
        out.append(dict(atoms=sorted(s['atoms']), corners=c, A=A, d=(B - A) / W, W=W, y0=y0, y1=y1, size=[pw(W * du), pw((y1 - y0) * dv)]))
    def untouched(F):                                                   # every corner of the facade is a corner of the wall as it was
        O = np.array([p for g in F['atoms'] for f in D[g]['faces'] for p in f['t']['P']]); return all(np.linalg.norm(O - np.array(c['pos']), axis=1).min() < 0.002 for c in F['corners'])
    plain = [F for F in out if sum(len(D[g]['faces']) for g in F['atoms']) <= 2 and len({f['m'] for g in F['atoms'] for f in D[g]['faces']}) == 1 and untouched(F)]      # a wall that IS one flat face with one picture already stays as it is (rule D carries its foot down)
    out = [F for F in out if not any(F is p for p in plain)]; kept['one flat face already'] += len(plain)
    tot = sum(F['size'][0] * F['size'][1] for F in out); nhalf = 0     # the pictures of a town may not weigh more than the budget: the largest is halved until they fit
    while tot > C['facade_megapixels'] * 1e6 and out:
        F = max(out, key=lambda F: F['size'][0] * F['size'][1]); i = 0 if F['size'][0] >= F['size'][1] else 1
        if F['size'][i] <= 16: break
        tot -= F['size'][0] * F['size'][1] // 2; F['size'][i] //= 2; nhalf += 1
    if nhalf: sc.note('W', 'facade pictures halved %d times to stay within %.0f megapixels a town' % (nhalf, C['facade_megapixels']))
    # a corner standing part-way along the edge of a neighbouring facade (their heights differ) is put exactly on that edge
    CP = {}
    for F in out:
        for c in F['corners']: CP.setdefault(c['key'], c)
    fixed = {r3(p) for p in AV.values()}; tsnap = 0
    for _ in range(3):
        for F in out:
            cs = F['corners']
            for i in range(4):
                A_, B_ = np.array(CP[cs[i]['key']]['pos']), np.array(CP[cs[(i + 1) % 4]['key']]['pos']); ab = B_ - A_; L2 = float(ab @ ab)
                if L2 < 1e-8: continue
                for key, c in CP.items():
                    if key in (x['key'] for x in cs) or r3(c['pos']) in fixed: continue
                    v = np.array(c['pos']); t = float((v - A_) @ ab) / L2
                    if 0.002 < t < 0.998:
                        on = A_ + t * ab; dd = float(np.linalg.norm(v - on))
                        if 1e-5 < dd < 0.08: c['pos'] = [float(x) for x in on]; tsnap += 1
    # the faces: two triangles and the recipe of their picture ; the old faces of the wall planes used go out
    used = sorted({g for F in out for g in F['atoms']}); nold = 0
    for gi in used:
        for f in D[gi]['faces']: sc.rm.add((f['t']['k'], f['t']['ti'])); nold += 1
    made = 0; fverts = []; npx = 0
    for F in out:
        cs = [CP[c['key']]['pos'] for c in F['corners']]; A = F['A']; d = F['d']; W = F['W']; y0, y1 = F['y0'], F['y1']; name = 'facade_%03d' % len(sc.bake); src = []
        for gi in F['atoms']:
            G = D[gi]; og, ug = G['o'], G['u']
            for f in G['faces']:
                Pq = np.array([[((np.array([og[0] + ug[0] * p[0], og[2] + ug[2] * p[0]]) - A) @ d) / W, (og[1] + p[1] - y0) / (y1 - y0)] for p in f['p']])
                e1 = Pq[1] - Pq[0]; e2 = Pq[2] - Pq[0]; ar = abs(float(e1[0] * e2[1] - e1[1] * e2[0])) * W * (y1 - y0)
                src.append((ar, dict(tile=f['m'], p=[[round(float(x), 5) for x in q] for q in Pq], uv=[[round(float(x), 5) for x in q] for q in f['uv']])))
        src.sort(key=lambda x: -x[0]); sc.bake.append(dict(name=name, size=F['size'], sources=[x[1] for x in src])); npx += F['size'][0] * F['size'][1]
        uvq = [(float((np.array([c[0], c[2]]) - A) @ d) / W, (c[1] - y0) / (y1 - y0)) for c in cs]; nref = D[max(F['atoms'], key=lambda g: len(D[g]['faces']))]['nface']
        for ix in ((0, 1, 2), (0, 2, 3)):
            t = [np.array(cs[i]) for i in ix]; n = np.cross(t[1] - t[0], t[2] - t[0])
            if np.linalg.norm(n) < 1e-7: continue
            if n @ nref < 0: ix = (ix[0], ix[2], ix[1])
            sc.put(name, [cs[i] for i in ix], [uvq[i] for i in ix], 'W'); made += 1
        fverts += cs; F['cs'] = cs
        # corners of roofs (and other things) that hung on the old wall between its ends are brought onto the flat facade
        nrm = np.array([-d[1], d[0]])
        for gi in F['atoms']:
            for v in D[gi]['verts']:
                if not v['cls']: continue
                p = np.array([v['P'][0], v['P'][2]]); s_ = float((p - A) @ d); off = float((p - A) @ nrm)
                if 0.3 < s_ < W - 0.3 and 1e-4 < abs(off) < 0.5: q = p - off * nrm; sc.moved[v['i']] = (float(q[0]), float(v['P'][1]), float(q[1]))
        # a board standing just in front of where the wall was carried down (1995 left the wall out behind it)
        for k in range(sc.N):
            if sc.role[k] != 'board' or abs(sc.n[k][1]) > 0.3 or sc.cut[k] or all((k, ti) in sc.rm for ti in range(len(sc.tris(k)))): continue
            q = sc.ctr[k]; s_ = float((q[[0, 2]] - A) @ d); off = float((q[[0, 2]] - A) @ nrm)
            if 0 < s_ < W and abs(off) < C['board_gap'] and y0 - 0.2 < q[1] < y1 and abs(float(sc.n[k][[0, 2]] @ nrm)) > 0.95: boards.append((round(abs(off), 2), [round(float(x), 1) for x in q]))
    sc.note('W', 'town at (%.0f, %.0f): wall planes %d -> stretches %d -> facades %d (seams between buildings in one plane %d) ; left as they are %s ; old triangles out %d, new %d ; corner points %d, shared %d, kept where a roof or other thing hangs %d, put on a neighbour\'s edge %d ; feet carried down to the floor %d (left on their posts: %d) ; pictures %.1f megapixels' % (
        T['closed'].centroid.x, T['closed'].centroid.y, nplanes, nstretch, len(out), ncuts, dict(kept), nold, made, len(CP), nshared, nreuse, tsnap, ndown, nprop, npx / 1e6))
    if boards: bs = sorted({tuple(b[1]) for b in boards}); sc.note('W', 'BOARDS standing within %.2f m in front of a facade (%d faces; where the 1995 wall was left out behind a board, the wall now carried down stands just behind it and the importer\'s z-fight gate may list the pair - accepted by the owner on Mountain): first %s' % (C['board_gap'], len(bs), bs[:6]))
    T['unused_planes'] = [D[g] for g in range(len(D)) if g not in used]
    T['facades'] = [dict(cs=[np.array(c, float) for c in F['cs']], name=sc.bake[len(sc.bake) - len(out) + i]['name'], A=F['A'], d=F['d'], W=F['W']) for i, F in enumerate(out)]
    return fverts

# ------------------------------------------------------------------------------------------------------------ R roofs
def roofs(sc, T, fverts):
    """rule R for one town: every roof piece -> its flat sides -> each side's outline cut into triangles over its corners only"""
    import shapely
    from shapely.geometry import Polygon, Point
    from shapely.ops import unary_union
    from scipy.spatial import cKDTree
    C = sc.cfg; SIMP, JOIN, SNAP_F, SNAP_R, UVT = C['roof_simp'], C['roof_join'], C['snap_f'], C['snap_r'], 0.02
    mv = lambda p: np.array(sc.moved.get(r3(p), p), float); F = []
    for k in range(sc.N):
        if sc.role[k] != 'roof' or sc.cut[k] or not T['scope'].contains(Point(r2(sc.ctr[k]))): continue
        for ti, ix in enumerate(sc.tris(k)):
            if (k, ti) in sc.rm: continue
            P = np.array([mv(p) for p in sc.P[k][list(ix)]]); n = np.cross(P[1] - P[0], P[2] - P[0]); a = 0.5 * float(np.linalg.norm(n))
            if a < 1e-7: sc.rm.add((k, ti)); continue                   # a roof triangle without area goes with its roof
            F.append(dict(k=k, ti=ti, P=P, UV=sc.UV[k][list(ix)], n=n / (2 * a), a=a, m=sc.mat[k], v=[r3(p) for p in P]))
    if not F: return
    vmap = collections.defaultdict(list)
    for i, f in enumerate(F):
        for v in f['v']: vmap[v].append(i)
    piece = [-1] * len(F); npieces = 0
    for i in range(len(F)):
        if piece[i] >= 0: continue
        st = [i]; piece[i] = npieces
        while st:
            g = st.pop()
            for v in F[g]['v']:
                for h in vmap[v]:
                    if piece[h] < 0: piece[h] = npieces; st.append(h)
        npieces += 1
    sides = []; stat = collections.Counter(); left = set(range(len(F)))
    while left:
        s = max(left, key=lambda i: F[i]['a']); n = F[s]['n']; o = F[s]['P'][0]; d0 = float(o @ n); grp = {s}; st = [s]; left.discard(s)
        while st:
            g = st.pop()
            for v in F[g]['v']:
                for h in vmap[v]:
                    if h in left and F[h]['n'] @ n > 0.999 and np.abs(F[h]['P'] @ n - d0).max() < 0.05: left.discard(h); grp.add(h); st.append(h)
        grp = sorted(grp); u = np.cross([0.0, 1.0, 0.0], n); u = u / np.linalg.norm(u) if np.linalg.norm(u) > 1e-6 else np.array([1.0, 0, 0]); w = np.cross(n, u)
        to2 = lambda p: (float((np.asarray(p) - o) @ u), float((np.asarray(p) - o) @ w))
        polys = [Polygon([to2(p) for p in F[i]['P']]) for i in grp]; U = unary_union([p if p.is_valid else p.buffer(0) for p in polys]).buffer(0.01, join_style=2).buffer(-0.01, join_style=2).simplify(SIMP)
        big = max(grp, key=lambda i: F[i]['a']); A = np.c_[np.array([to2(p) for p in F[big]['P']]), np.ones(3)]; M = None
        if abs(np.linalg.det(A)) > 1e-9: M = np.linalg.solve(A, F[big]['UV'])
        agree = M is not None and all(np.abs(np.r_[to2(p), 1.0] @ M - q).max() < UVT for i in grp for p, q in zip(F[i]['P'], F[i]['UV']))
        if not agree:                                                   # the faces carry the tile each in its own way: one even mapping at their usual texel size, rows of tiles along the eave
            Js = []
            for i in grp:
                Q = np.array([to2(p) for p in F[i]['P']]); Uq = F[i]['UV']; A2 = np.c_[Q[1] - Q[0], Q[2] - Q[0]]
                if abs(np.linalg.det(A2)) > 1e-6: Js.append(np.abs(np.c_[Uq[1] - Uq[0], Uq[2] - Uq[0]] @ np.linalg.inv(A2)))
            if Js:
                Jm = np.median(np.array(Js), axis=0)
                M = np.array([[Jm[0, 0], 0.0], [0.0, Jm[1, 1]], [0.0, 0.0]]) if Jm[0, 0] + Jm[1, 1] >= Jm[0, 1] + Jm[1, 0] else np.array([[0.0, Jm[1, 0]], [Jm[0, 1], 0.0], [0.0, 0.0]])
        mats = collections.Counter()
        for i in grp: mats[F[i]['m']] += F[i]['a']
        for g in _geoms(U, mina=1e-4):
            sides.append(dict(piece=piece[s], n=n, o=o, u=u, w=w, poly=g, M=M, mat=mats.most_common(1)[0][0], faces=grp)); stat['one mapping' if agree else 'mapping differs from face to face'] += 1
    # corners: one point where sides, facades and neighbouring roofs meet
    pts = []
    for si, s in enumerate(sides):
        for ring in [s['poly'].exterior] + list(s['poly'].interiors):
            for x, y in list(ring.coords)[:-1]: pts.append((si, (round(x, 4), round(y, 4)), s['o'] + s['u'] * x + s['w'] * y))
    X = np.array([p[2] for p in pts]); par = list(range(len(pts)))
    def find(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    for a, b in cKDTree(X).query_pairs(SNAP_R):
        same = sides[pts[a][0]]['piece'] == sides[pts[b][0]]['piece']
        if np.linalg.norm(X[a] - X[b]) < (JOIN if same else SNAP_R) and pts[a][0] != pts[b][0]: par[find(a)] = find(b)
    CL = collections.defaultdict(list)
    for i in range(len(pts)): CL[find(i)].append(i)
    FAC = np.array(fverts, float) if len(fverts) else np.zeros((0, 3)); kf = cKDTree(FAC) if len(FAC) else None; corner = {}; nfac = 0; nroof = 0; dfac = [0.0]
    for ci, mem in CL.items():
        c = X[mem].mean(0); pos = c
        if kf is not None:                                              # the facade corner under it: close in plan, and not above or below the roof corner by more than a step
            cand = [k for k in kf.query_ball_point(c, SNAP_F + 0.3) if np.hypot(FAC[k][0] - c[0], FAC[k][2] - c[2]) < SNAP_F and abs(FAC[k][1] - c[1]) < 0.35]
            if cand: k = min(cand, key=lambda k: np.linalg.norm(FAC[k] - c)); pos = FAC[k]; nfac += 1; dfac.append(float(np.linalg.norm(FAC[k] - c)))
        nroof += len({sides[pts[i][0]]['piece'] for i in mem}) > 1
        for i in mem: corner[(pts[i][0], pts[i][1])] = dict(key=ci, pos=[float(x) for x in pos])
    allc = {}
    for c in corner.values(): allc.setdefault(c['key'], c)
    CK = list(allc); CPp = np.array([allc[k]['pos'] for k in CK]); kc = cKDTree(CPp); ntri = 0; fail = []; failed = set(); new = []
    for si, s in enumerate(sides):
        o, u, w, n = s['o'], s['u'], s['w'], s['n']; to2 = lambda p: (float((np.asarray(p) - o) @ u), float((np.asarray(p) - o) @ w))
        def ring(r):
            ks = [corner[(si, (round(x, 4), round(y, 4)))]['key'] for x, y in list(r.coords)[:-1]]; ks = [k for i, k in enumerate(ks) if k != ks[i - 1]]; o_ = []
            for i, k in enumerate(ks):
                o_.append(k); a, b = np.array(allc[k]['pos']), np.array(allc[ks[(i + 1) % len(ks)]]['pos']); ab = b - a; L = np.linalg.norm(ab)
                if L < 1e-6: continue
                on = []
                for j in kc.query_ball_point((a + b) / 2, L / 2 + 0.05):   # corners of other sides that stand on this edge become corners of it: no corner on another face's edge
                    kk = CK[j]
                    if kk in ks: continue
                    t = (CPp[j] - a) @ ab / (L * L)
                    if 0.01 < t < 0.99 and np.linalg.norm(CPp[j] - (a + t * ab)) < 0.04: on.append((t, kk))
                o_ += [kk for t, kk in sorted(on)]
            return o_
        ext = ring(s['poly'].exterior); holes = [ring(h) for h in s['poly'].interiors]; Tt = []
        if len(set(ext)) >= 3:
            p2 = {k: to2(allc[k]['pos']) for k in set(ext) | {k for h in holes for k in h}}
            try:
                pg = Polygon([p2[k] for k in ext], [[p2[k] for k in h] for h in holes if len(set(h)) > 2]); pg = pg if pg.is_valid else pg.buffer(0); key2 = {(round(v[0], 4), round(v[1], 4)): k for k, v in p2.items()}
                for g in _geoms(pg, mina=1e-4):
                    for t in shapely.constrained_delaunay_triangles(g).geoms:
                        kk = [key2.get((round(x, 4), round(y, 4))) for x, y in list(t.exterior.coords)[:3]]
                        if None in kk or len(set(kk)) < 3 or t.area < 1e-5: continue
                        Tt.append(kk)
            except Exception: Tt = []
            if not Tt: fail.append((s['piece'], round(s['poly'].area, 1))); failed.add(s['piece']); continue
        else: stat['side closed up'] += 1; continue
        for kk in Tt:
            a, b, c = [np.array(allc[k]['pos']) for k in kk]
            if np.cross(b - a, c - a) @ n < 0: kk = [kk[0], kk[2], kk[1]]
            uv = [((np.r_[to2(allc[k]['pos']), 1.0] @ s['M']).tolist() if s['M'] is not None else [0.0, 0.0]) for k in kk]; new.append((s['piece'], s['mat'], [allc[k]['pos'] for k in kk], uv))
    nold = 0; oldn = collections.Counter(piece); newn = collections.Counter(pc for pc, m, P, uv in new); same = 0
    was = collections.defaultdict(set)
    for i, f in enumerate(F):
        for p in sc.P[f['k']][list(sc.tris(f['k'])[f['ti']])]: was[piece[i]].add((round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2)))
    for pc in range(npieces):                                           # a roof that would come out with as many triangles on the very same corners stays as it is
        if pc in failed: continue
        now = {(round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2)) for q, m, P, uv in new if q == pc for p in P}
        if newn[pc] >= oldn[pc] and now <= was[pc]: failed.add(pc); same += 1
    for i, f in enumerate(F):
        if piece[i] not in failed: sc.rm.add((f['k'], f['ti'])); nold += 1
    for pc, m, P, uv in new:
        if pc not in failed and _area3(np.array(P)) > 1e-6: sc.put(m, P, uv, 'R'); ntri += 1
    sc.note('R', 'town at (%.0f, %.0f): roof pieces %d, triangles %d -> flat sides %d %s -> triangles %d ; corner points %d ; on a facade corner %d (moved %.2f m at most) ; shared between two roofs %d ; pieces left as they are: %d that would not change, and (a side could not be laid out) %s' % (
        T['closed'].centroid.x, T['closed'].centroid.y, npieces, nold, len(sides), dict(stat), ntri, len(CL), nfac, max(dfac), nroof, same, fail))

# ------------------------------------------------------------------------------------------------------------ D walls down
def walls_down(sc, T, floor):
    """rule D: the foot edges of building walls that were NOT made into facades, hanging above the floor, carried straight down"""
    C = sc.cfg; n = 0; gaps = []
    for G in T.get('unused_planes', []):
        if not _match(collections.Counter(f['c'] for f in G['faces']).most_common(1)[0][0], sc.roles['building']): continue
        ylow = collections.defaultdict(lambda: 1e9)
        for f in G['faces']:
            for p in f['t']['P']: k = (round(float(p[0]), 2), round(float(p[2]), 2)); ylow[k] = min(ylow[k], float(p[1]))
        for f in G['faces']:
            t = f['t']; P = t['P']; lo = float(P[:, 1].min())
            for i in range(3):
                a, b = P[i], P[(i + 1) % 3]; L = float(np.linalg.norm(a - b))
                if L < 1e-3 or abs(a[1] - b[1]) > 0.3 * L or max(a[1], b[1]) > lo + 0.02: continue
                if any(ylow[(round(float(q[0]), 2), round(float(q[2]), 2))] < q[1] - 0.02 for q in (a, b)): continue      # another face of the wall stands under this edge
                fa, fb = floor.at(a[0], a[1], a[2], C['maxgap']), floor.at(b[0], b[1], b[2], C['maxgap'])
                if fa is None or fb is None or max(a[1] - fa, b[1] - fb) < 0.005: continue
                qa = np.array([a[0], min(a[1], fa - C['under']), a[2]]); qb = np.array([b[0], min(b[1], fb - C['under']), b[2]]); gaps.append(max(a[1] - fa, b[1] - fb))
                d = b - a; d[1] = 0; Ld = max(float(np.linalg.norm(d)), 1e-6); d /= Ld; s_ = lambda p: float((p - a) @ d)
                Pm = np.array([[s_(p), p[1], 1.0] for p in P]); M = np.linalg.lstsq(Pm, t['UV'], rcond=None)[0]
                for tri in ((a, b, qb), (a, qb, qa)):
                    tri = [np.asarray(x, float) for x in tri]; nn = np.cross(tri[1] - tri[0], tri[2] - tri[0])
                    if np.linalg.norm(nn) < 1e-7: continue
                    if nn @ t['n'] < 0: tri = tri[::-1]
                    uv = []                                             # below the foot the wall's own lowest 15 cm is used (stretched over a taller gap): no window or door of the wall above lands in the base
                    for c in tri:
                        tt = min(max(s_(c) / Ld, 0.0), 1.0); yf = a[1] + (b[1] - a[1]) * tt; uv.append(np.array([s_(c), yf + min(abs(yf - c[1]), 0.15), 1.0]) @ M)
                    sc.put(t['m'], tri, uv, 'D'); n += 1
    if n: sc.note('D', 'town at (%.0f, %.0f): %d foot edges of walls that stay as they are carried down to the floor (%d triangles ; gap median %.2f, largest %.2f m)' % (T['closed'].centroid.x, T['closed'].centroid.y, len(gaps), n, float(np.median(gaps)), max(gaps)))

class Cover:
    """does a new face lie on a face that is there (nearly parallel, within tol of its plane, overlapping)?"""
    def __init__(s, sc, cell=6.0):
        s.T = []; s.cell = cell; s.g = collections.defaultdict(list)
        for k in range(sc.N):
            if sc.cut[k] or sc.area[k] < 1e-4: continue
            for ti, ix in enumerate(sc.tris(k)):
                if (k, ti) in sc.rm: continue
                P = sc.P[k][list(ix)]; n = np.cross(P[1] - P[0], P[2] - P[0]); l = float(np.linalg.norm(n))
                if l < 1e-6: continue
                lo = np.floor(P[:, [0, 2]].min(0) / cell).astype(int); hi = np.floor(P[:, [0, 2]].max(0) / cell).astype(int)
                if (hi - lo).max() > 30: continue
                s.T.append((P, n / l))
                for x in range(lo[0], hi[0] + 1):
                    for z in range(lo[1], hi[1] + 1): s.g[(x, z)].append(len(s.T) - 1)
    def on(s, P, tol=0.03):
        from shapely.geometry import Polygon
        P = np.asarray(P, float); n = _newell(P); n /= max(np.linalg.norm(n), 1e-12); lo = np.floor(P[:, [0, 2]].min(0) / s.cell).astype(int); hi = np.floor(P[:, [0, 2]].max(0) / s.cell).astype(int); cand = set()
        for x in range(lo[0], hi[0] + 1):
            for z in range(lo[1], hi[1] + 1): cand.update(s.g.get((x, z), ()))
        u = P[1] - P[0]; u /= max(np.linalg.norm(u), 1e-12); w = np.cross(n, u); g1 = Polygon([((p - P[0]) @ u, (p - P[0]) @ w) for p in P]).buffer(0); ov = 0.0
        for j in cand:
            Q, m = s.T[j]
            if abs(m @ n) < 0.9994 or np.abs((Q - P[0]) @ n).max() > tol: continue
            ov += g1.intersection(Polygon([((p - P[0]) @ u, (p - P[0]) @ w) for p in Q]).buffer(0)).area
        return ov > 0.02 and ov > 0.05 * g1.area

# ------------------------------------------------------------------------------------------------------------ H holes
def holes(sc):
    """rule H: closed rings of open edges in the solid ground, kerbs and low walls beside the road, small enough to be a slip of authoring, closed over their own corners"""
    C = sc.cfg; edges = collections.defaultdict(list); pos = {}
    solid = [k for k in range(sc.N) if not sc.cut[k] and sc.role[k] in ('', 'paving') and sc.area[k] > 1e-6 and sc.cenkd.query(sc.ctr[k][[0, 2]])[0] < C['hole_reach'] + 15.0]
    key = lambda p: (round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2))
    for k in solid:
        P = sc.P[k]; ks = [key(p) for p in P]
        for i in range(len(P)):
            a, b = ks[i], ks[(i + 1) % len(P)]
            if a == b: continue
            edges[frozenset((a, b))].append((k, a, b)); pos[a] = P[i]; pos[b] = P[(i + 1) % len(P)]
    openE = {e: v[0] for e, v in edges.items() if len(v) == 1}; nxt = collections.defaultdict(list)
    for e, (k, a, b) in openE.items(): nxt[b].append((a, k))             # walked against the face's own order: the ring then turns the way a face filling it must
    used = set(); rings = []; cover = Cover(sc); ncov = 0
    for e, (k, a, b) in openE.items():
        if e in used: continue
        ring = [b]; ks = [k]; cur = b; ok = True; used.add(e)
        while True:
            c = [(v, kk) for v, kk in nxt[cur] if frozenset((cur, v)) not in used or v == ring[0]]
            if len(nxt[cur]) != 1 or len(ring) > C['hole_corners']: ok = False; break
            v, kk = nxt[cur][0]; used.add(frozenset((cur, v)))
            if v == ring[0]: ks.append(kk); break
            ring.append(v); ks.append(kk); cur = v
        if ok and 3 <= len(ring) <= C['hole_corners']: rings.append((ring, ks))
    n = 0; places = []
    for ring, ks in rings:
        P = np.array([pos[v] for v in ring]); c = P.mean(0)
        if sc.cenkd.query(c[[0, 2]])[0] > C['hole_reach']: continue
        nrm = _newell(P); a = 0.5 * float(np.linalg.norm(nrm))
        if a < 0.02: continue
        nrm /= 2 * a
        if np.abs((P - c) @ nrm).max() > 0.35: continue                 # not flat: the mouth of something, not a hole in a surface
        u = P[1] - P[0]; u /= np.linalg.norm(u); w = np.cross(nrm, u); q = np.c_[(P - c) @ u, (P - c) @ w]; ext = sorted(np.ptp(q, axis=0))
        ang = [0.5 * np.arctan2(2 * np.cov(q.T)[0, 1], np.cov(q.T)[0, 0] - np.cov(q.T)[1, 1])]; rot = np.array([[np.cos(ang[0]), np.sin(ang[0])], [-np.sin(ang[0]), np.cos(ang[0])]]); ext = sorted(np.ptp(q @ rot.T, axis=0))
        if ext[0] > C['hole_max']: continue
        kb = max(set(ks), key=lambda k: (100.0 if sc.n[k] @ nrm > 0.7 else 0.0) + sum(np.linalg.norm(pos[ring[i]] - pos[ring[(i + 1) % len(ring)]]) for i in range(len(ring)) if ks[(i + 1) % len(ring)] == k))      # the tile of the neighbour that lies in the hole's own plane, with the longest shared border
        if sc.n[kb] @ nrm < 0.7: continue                               # no neighbour faces the way the hole does: an opening between things - or the ring is the outline of a face standing alone (it then turns the other way)
        if cover.on(P): ncov += 1; continue                             # something lies there already (a board, a wall of another kind)
        idx = list(range(len(ring))); tris = []                         # ears (the ring is small and nearly flat)
        while len(idx) > 3:
            best = None
            for j in range(len(idx)):
                i0, i1, i2 = idx[j - 1], idx[j], idx[(j + 1) % len(idx)]; cr = float(np.cross(P[i1] - P[i0], P[i2] - P[i1]) @ nrm)
                if cr <= 1e-9: continue
                T3 = P[[i0, i1, i2]]
                if any(_in_tri3(P[m], T3, nrm) for m in idx if m not in (i0, i1, i2)): continue
                if best is None or cr > best[0]: best = (cr, j)
            if best is None: tris = []; break
            j = best[1]; tris.append((idx[j - 1], idx[j], idx[(j + 1) % len(idx)])); idx.pop(j)
        else: tris.append(tuple(idx))
        if not tris or any(cover.on(P[list(t)]) for t in tris): continue
        for t in tris:
            if _area3(P[list(t)]) > 1e-5: sc.put(sc.mat[kb], P[list(t)], [sc.UV[kb][0]] * 3, 'H'); n += 1      # drawn without a mapping: the importer carries the neighbour's tile on across the shared edge (coursepatch.continue_uv)
        places.append((round(a, 1), len(ring), sc.cls[kb], [round(float(x), 1) for x in c]))
    # NOTCHES: three open edges in a row that make a U (two jambs and what joins them), flat, the mouth no wider than a hole may be: the missing end of a kerb, a slot in a low wall
    cornerf = collections.defaultdict(set)
    for k in solid:
        for p in sc.P[k]: cornerf[key(p)].add(k)
    nn = 0; notch = []; taken = set()
    for v0 in list(nxt):
        for v1, k1 in nxt[v0]:
            for v2, k2 in nxt.get(v1, ()):
                for v3, k3 in nxt.get(v2, ()):
                    if len({v0, v1, v2, v3}) < 4 or frozenset((v0, v1, v2, v3)) in taken: continue
                    P = np.array([pos[v] for v in (v0, v1, v2, v3)]); c = P.mean(0)
                    if sc.cenkd.query(c[[0, 2]])[0] > C['hole_reach']: continue
                    e1, e2, e3, e4 = P[1] - P[0], P[2] - P[1], P[3] - P[2], P[0] - P[3]; L = [float(np.linalg.norm(e)) for e in (e1, e2, e3, e4)]
                    if min(L) < 0.1 or L[3] > C['hole_max'] or L[1] > C['hole_max'] or max(L[0], L[2]) > 2 * C['hole_max']: continue
                    if (e1 @ e3) / (L[0] * L[2]) > -0.9 or abs(L[0] - L[2]) > 0.25 * max(L[0], L[2]): continue      # the two jambs: parallel, the same length
                    nrm = _newell(P); a = 0.5 * float(np.linalg.norm(nrm))
                    if a < 0.05: continue
                    nrm /= 2 * a
                    if np.abs((P - c) @ nrm).max() > 0.05: continue
                    if any(len({v0, v1, v2, v3} & {key(p) for p in sc.P[k]}) >= 3 for k in cornerf[v0] | cornerf[v2]): continue      # a face already stands on these corners
                    if frozenset((v3, v0)) in openE: continue           # four open edges: a ring, handled above
                    if not (len(cornerf[v0] - {k1}) and len(cornerf[v3] - {k3})): continue      # the mouth's two corners must be held by something else too (the ground the kerb stands on)
                    if cover.on(P) or cover.on(P[[0, 1, 2]]) or cover.on(P[[0, 2, 3]]): ncov += 1; continue
                    taken.add(frozenset((v0, v1, v2, v3)))
                    for t in ((0, 1, 2), (0, 2, 3)): sc.put(sc.mat[k2], P[list(t)], [sc.UV[k2][0]] * 3, 'H'); nn += 1
                    notch.append((round(a, 1), 4, sc.cls[k2], [round(float(x), 1) for x in c]))
    sc.note('H', 'notches (three open edges making a U no wider than %.1f m) closed: %d (%d triangles ; %d rings and notches left alone because a face lies there already ; %.1f m2): %s' % (C['hole_max'], len(notch), nn, ncov, sum(p[0] for p in notch), sorted(notch, reverse=True)[:60]))
    for i, p in enumerate(sorted(notch, reverse=True)[:6]): sc.view('notch_%d' % i, p[3], 10.0, 14.0)
    sc.note('H', 'open edges %d among %d solid polygons near the road ; closed rings of at most %d corners %d ; holes closed %d (%d triangles, %.1f m2): %s' % (len(openE), len(solid), C['hole_corners'], len(rings), len(places), n, sum(p[0] for p in places), sorted(places, reverse=True)[:40]))
    for i, p in enumerate(sorted(places, reverse=True)[:6]): sc.view('hole_%d' % i, p[3], 10.0, 14.0)

def _in_tri3(p, T, n):
    for i in range(3):
        if float(np.cross(T[(i + 1) % 3] - T[i], p - T[i]) @ n) < 1e-9: return False
    return True

# ------------------------------------------------------------------------------------------------------------ the owner's hand edits, as far as they go by rule (all OPT-IN: letters C G B in "only", CFG forest / forest_foot)
def _open_edges(sc, reach):
    """the solid polygons near the road, their corners (1 cm) and the edges only one of them uses: nxt[b] = [(a, polygon)] for an edge the polygon runs a -> b (walked b -> a, the way a face filling the opening must run)"""
    key = lambda p: (round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2)); edges = collections.defaultdict(list); pos = {}; cf = collections.defaultdict(set)
    solid = [k for k in range(sc.N) if not sc.cut[k] and sc.role[k] in ('', 'paving') and sc.area[k] > 1e-6 and sc.cenkd.query(sc.ctr[k][[0, 2]])[0] < reach + 15.0]
    for k in solid:
        P = sc.P[k]; ks = [key(p) for p in P]
        for i in range(len(P)):
            a, b = ks[i], ks[(i + 1) % len(P)]; cf[a].add(k)
            if a != b: edges[frozenset((a, b))].append((k, a, b)); pos[a] = P[i]; pos[b] = P[(i + 1) % len(P)]
    nxt = collections.defaultdict(list)
    for e, v in edges.items():
        if len(v) == 1: nxt[v[0][2]].append((v[0][1], v[0][0]))
    return nxt, pos, cf, key

def kerb_caps(sc):
    """rule C (the owner's patch 1, ten places): the open END of a kerb or low wall gets its cap. A kerb is an upright face towards the road and a flat top that share their long
    edge; where it ends, the upright's end edge and the top's end edge are both open and meet at the top corner. The cap is the rectangle those two edges span
    (its fourth corner is new: straight under the top's far corner, at the upright's foot)."""
    C = sc.cfg; nxt, pos, cf, key = _open_edges(sc, C['hole_reach']); cover = Cover(sc); made = []; madep = []; seen = set()
    have = [np.array(P) for t, P, uv, r in sc.add if r == 'H']; ends = collections.defaultdict(list)
    for u in nxt:
        for v, k in nxt[u]: ends[u].append((v, k)); ends[v].append((u, k))
    for b0 in list(nxt):
        for a0, k1 in nxt[b0]:                                         # the upright's end edge
            e = pos[a0] - pos[b0]; L1 = float(np.linalg.norm(e))
            if abs(sc.n[k1][1]) > 0.3 or not 0.2 <= L1 <= C['hole_max'] or abs(e[1]) < 0.95 * L1: continue
            top, foot = (a0, b0) if pos[a0][1] > pos[b0][1] else (b0, a0)
            for c0, k2 in ends[top]:                                    # open edges that start or end at the top corner
                if c0 in (top, foot) or k2 == k1 or abs(sc.n[k2][1]) < 0.9: continue
                t = pos[c0] - pos[top]; L2 = float(np.linalg.norm(t))
                if not 0.2 <= L2 <= C['hole_max'] or abs(t[1]) > 0.1 * L2 or abs(float(t @ e)) > 0.2 * L1 * L2: continue
                if len({key(p) for p in sc.P[k1]} & {key(p) for p in sc.P[k2]}) < 2: continue      # not the two faces of one kerb
                A, B, Cc = pos[foot], pos[top], pos[c0]; Dd = A + (Cc - B); n = np.cross(Cc - B, A - B); n /= np.linalg.norm(n)
                side = [float((p - B) @ n) for k in (k1, k2) for p in sc.P[k]]
                if min(side) < -0.05 and max(side) > 0.05: continue    # the kerb runs on to both sides of this plane: a kink, not an end
                kk = frozenset((foot, top, c0))
                if kk in seen or any(len({foot, top, c0} & {key(p) for p in sc.P[k]}) >= 3 for k in cf[top]): continue
                if sc.cenkd.query(((A + Cc) / 2)[[0, 2]])[0] > C['hole_reach']: continue
                quad = [B, A, Dd, Cc] if (a0, b0) == (top, foot) else [A, B, Cc, Dd]      # the open edge is walked against its face
                T1, T2 = np.array([quad[0], quad[1], quad[2]]), np.array([quad[0], quad[2], quad[3]])
                if cover.on(np.array(quad)) or cover.on(T1) or cover.on(T2): continue
                if any(np.abs((H - B) @ n).max() < 0.05 and np.linalg.norm(H.mean(0) - (A + Cc) / 2) < max(L1, L2) for H in have): continue      # rule H closed this one as a notch
                mid = (A + Cc) / 2
                if any(np.linalg.norm(np.array(m[2]) - mid) < 0.3 for m in madep): continue      # the same end, found from the kerb's other upright
                madep.append((0, 0, mid)); seen.add(kk); sc.put(sc.mat[k1], T1, [sc.UV[k1][0]] * 3, 'C'); sc.put(sc.mat[k1], T2, [sc.UV[k1][0]] * 3, 'C')
                made.append((round(L1 * L2, 1), sc.cls[k1], [round(float(x), 1) for x in (A + Cc) / 2]))
    sc.note('C', 'kerb and low-wall ends capped: %d (%d triangles, %.1f m2): %s' % (len(made), 2 * len(made), sum(m[0] for m in made), sorted(made, key=lambda m: m[2])))
    for i, m in enumerate(made[:8]): sc.view('cap_%d' % i, m[2], 4.0, 7.0)

def plan_holes(sc):
    """rule G (the owner's patch 1, the ground pieces; and holes inside the forest floor): seen from straight above, a small hole in everything that is there beside the road -
    the sea shows through it - is closed with ground, over the corners that surround it."""
    import shapely
    from shapely.geometry import Polygon, LineString
    from shapely.ops import unary_union
    from scipy.spatial import cKDTree
    C = sc.cfg; G = []; corners = []
    def take(P, k):
        P = np.asarray(P, float)
        if sc.cenkd.query(P.mean(0)[[0, 2]])[0] > C['gap_reach'] + 40.0: return
        q = [r2(p) for p in P]; g = Polygon(q); G.append(g.buffer(0.02) if (g.is_valid and g.area > 1e-4) else LineString(q + [q[0]]).buffer(0.02))
        n = _newell(P); ly = abs(n[1]) > 0.7 * np.linalg.norm(n) > 0
        for p in P: corners.append((p[0], p[2], p[1], ly, k))
    for k in range(sc.N):
        if not sc.cut[k] and sc.area[k] > 1e-6 and not all((k, ti) in sc.rm for ti in range(len(sc.tris(k)))): take(sc.P[k], k)
    for i, (t, P, uv, r) in enumerate(sc.add): take(P, -1 - i)
    U = unary_union(G); CA = np.array(corners, float); kc = cKDTree(CA[:, :2]); made = []; rej = collections.Counter(); up = -1.0 if sum(sc.n[k][1] for k in range(sc.N) if sc.road[k]) < 0 else 1.0
    for g in _geoms(U):
        for ring in g.interiors:
            h = Polygon(ring)
            if not C['gap_min'] <= h.area <= C['gap_area']: continue
            if max(sc.cenkd.query([x, z])[0] for x, z in ring.coords) > C['gap_reach']: continue
            hs = h.buffer(0.021, join_style=2).simplify(0.05); pts = list(hs.exterior.coords)[:-1] if hs.geom_type == 'Polygon' else []
            if len(pts) < 3: rej['outline closes up'] += 1; continue
            cand = [[j for j in kc.query_ball_point(p, 0.3)] for p in pts]
            if sum(1 for c in cand if c) < 3: rej['fewer than 3 corners round it'] += 1; continue
            base = [min(CA[c, 2]) for c in cand if c and any(CA[j, 3] for j in c)] or [min(CA[c, 2]) for c in cand if c]; h0 = float(np.median(base)); V = []
            rej['no ground corner round it'] += 0
            for p, c in zip(pts, cand):
                if c: j = min(c, key=lambda j: (abs(CA[j, 2] - h0) > 0.3, float(np.hypot(CA[j, 0] - p[0], CA[j, 1] - p[1])), abs(CA[j, 2] - h0))); V.append((round(CA[j, 0], 3), round(CA[j, 2], 3), round(CA[j, 1], 3), int(CA[j, 4])))
            V = [v for i, v in enumerate(V) if v[:3] != V[i - 1][:3]]
            if len(V) < 3 or np.ptp([v[1] for v in V]) > C['gap_rise']: rej['its rim is not level (or closes up)'] += 1; continue
            pg = Polygon([(v[0], v[2]) for v in V]); pg = pg if pg.is_valid else pg.buffer(0); Y = {(v[0], v[2]): v[1] for v in V}; tris = []
            for q in _geoms(pg, mina=0.05):
                for t in shapely.constrained_delaunay_triangles(q).geoms:
                    kk = [(round(x, 3), round(z, 3)) for x, z in list(t.exterior.coords)[:3]]
                    if all(k_ in Y for k_ in kk) and t.area > 1e-3: tris.append(np.array([[k_[0], Y[k_], k_[1]] for k_ in kk]))
            if not tris: rej['could not be cut'] += 1; continue
            ks = [v[3] for v in V]; gk = [k for k in ks if k >= 0 and abs(sc.n[k][1]) > 0.7 and not sc.road[k] and sc.role[k] in ('', 'paving')]; ak = [k for k in ks if k < 0]
            if not gk: gk = [k for k in ks if k >= 0 and abs(sc.n[k][1]) > 0.7 and sc.role[k] in ('', 'paving')]      # (a verge can be a road tile)
            if gk: kb = max(set(gk), key=lambda k: gk.count(k) * 1000 + sc.area[k]); tile = sc.mat[kb]; uv0 = sc.UV[kb][0]
            elif ak: tile = sc.add[-1 - ak[0]][0]; uv0 = sc.add[-1 - ak[0]][2][0]
            else: rej['no ground round it'] += 1; continue              # nothing but walls round it: not a hole in ground
            for P in tris:
                if (np.cross(P[1] - P[0], P[2] - P[0])[1] > 0) != (up > 0): P = P[::-1]
                sc.put(tile, P, [uv0] * 3, 'G')
            c = h.centroid; made.append((round(h.area, 1), len(tris), [round(c.x, 1), round(h0, 1), round(c.y, 1)]))
    sc.note('G', 'holes seen from above (%.1f .. %.0f m2, within %.0f m of the centre line) closed: %d (%d triangles, %.1f m2): %s ; left: %s' % (C['gap_min'], C['gap_area'], C['gap_reach'], len(made), sum(m[1] for m in made), sum(m[0] for m in made), sorted(made, reverse=True), dict(rej)))
    for i, m in enumerate(sorted(made, reverse=True)[:8]): sc.view('gap_%d' % i, m[2], 14.0, 12.0)

# ------------------------------------------------------------------------------------------------------------ patch 3 (the v11 scene, accepted 2026-10-15), as far as it goes by rule (OPT-IN: letters K T in "only")
NATURAL_CLS = ('rock', 'grass', 'dirt', 'sand', 'gravel')
TREE_CLS = ('crown', 'tree', 'trunk', 'bare', 'tree_wall')

def cliffs_down(sc):
    """rule K (patch 3: "cliff it down", the sea cliffs and stacks of the v11 scene): a natural face standing upright whose FOOT is an open edge hanging in the air -
    the 1995 cliffs stop above the sea and show the sea under them from any camera off the road - is carried straight down to what is under it: the ground, or
    the sea where the course has one. Its picture runs on downwards (the face's own mapping, continued)."""
    C = sc.cfg; key = lambda p: (round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2)); use = collections.Counter()
    solid = [k for k in range(sc.N) if not sc.cut[k] and sc.area[k] > 1e-6]
    for k in solid:
        ks = [key(p) for p in sc.P[k]]
        for i in range(len(ks)):
            if ks[i] != ks[(i + 1) % len(ks)]: use[frozenset((ks[i], ks[(i + 1) % len(ks)]))] += 1
    lying = [sc.P[k][list(ix)] for k in solid if abs(sc.n[k][1]) > 0.5 for ix in sc.tris(k)]
    floor = Floor(lying, cell=6.0); sea = (sc.S['cfg'].get('sea') or {}).get('level'); cover = Cover(sc); made = []; rej = collections.Counter(); up = 0
    roadfloor = Floor([sc.P[k][list(ix)] for k in solid if sc.road[k] and abs(sc.n[k][1]) > 0.5 for ix in sc.tris(k)], cell=6.0)
    cand = []
    for k in solid:
        if sc.cls[k] not in NATURAL_CLS or abs(sc.n[k][1]) > 0.5 or sc.role[k] not in ('',): continue
        P = sc.P[k]; lo = float(P[:, 1].min()); hi = float(P[:, 1].max()); ks = [key(p) for p in P]
        dc, ic = sc.cenkd.query(sc.ctr[k][[0, 2]])
        if dc < C['cliff_road'] and hi < sc.cen[ic][1] + C['cliff_deck']: rej['a side of the road deck or verge (a bridge, a kerb)'] += 1; continue      # (the owner left the bay's bridge open)
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]; L = float(np.linalg.norm(b - a))
            if L < C['cliff_min'] or use[frozenset((ks[i], ks[(i + 1) % len(P)]))] != 1: continue
            if abs(a[1] - b[1]) > 0.3 * L or max(a[1], b[1]) > lo + 0.3: continue      # not a level edge at the face's foot
            ga = floor.at(a[0], a[1] - C['cliff_skip'], a[2], C['cliff_max'], up=0.0); gb = floor.at(b[0], b[1] - C['cliff_skip'], b[2], C['cliff_max'], up=0.0)
            if sea is not None:
                ga = max(ga if ga is not None else -1e9, sea - 0.3); gb = max(gb if gb is not None else -1e9, sea - 0.3)
            if ga is None or gb is None: rej['nothing under it'] += 1; continue
            da, db = a[1] - ga, b[1] - gb
            if max(da, db) < C['cliff_drop']: rej['stands on something'] += 1; continue
            if min(da, db) > C['cliff_max']: rej['too far down'] += 1; continue
            if min(sc.cenkd.query(a[[0, 2]])[0], sc.cenkd.query(b[[0, 2]])[0]) < C['cliff_clear'] or roadfloor.at(a[0], a[1] - C['cliff_skip'], a[2], C['cliff_max'], up=0.0) is not None or roadfloor.at(b[0], b[1] - C['cliff_skip'], b[2], C['cliff_max'], up=0.0) is not None: rej['it would stand on or by the road'] += 1; continue
            qa = np.array([a[0], ga - 0.02, a[2]]); qb = np.array([b[0], gb - 0.02, b[2]])
            d = b - a; d[1] = 0; Ld = max(float(np.linalg.norm(d)), 1e-6); d /= Ld; s_ = lambda p: float((p - a) @ d)
            M = np.linalg.lstsq(np.array([[s_(p), p[1], 1.0] for p in P]), sc.UV[k], rcond=None)[0]      # the face's own mapping as a function of (along the edge, height)
            quad = [a, b, qb, qa]
            if cover.on(np.array(quad)): rej['lies on a face that is there'] += 1; continue
            cand.append((k, a, b, qa, qb, M, d, L, max(da, db), ks[i], ks[(i + 1) % len(P)]))
    par = {}                                                           # runs of foot edges joined end to end: a run shorter than cliff_run (or than a quarter of its drop) is a fin, not a cliff
    def find(x):
        while par.setdefault(x, x) != x: par[x] = par[par[x]]; x = par[x]
        return x
    for c in cand: par[find(c[9])] = find(c[10])
    run = collections.defaultdict(lambda: [0.0, 0.0])
    for c in cand: r = run[find(c[9])]; r[0] += c[7]; r[1] = max(r[1], c[8])
    for k, a, b, qa, qb, M, d, L, dmax, ka, kb in cand:
        r = run[find(ka)]
        if r[0] < max(C['cliff_run'], 0.25 * r[1]): rej['a fin (its run of foot edges too short for its drop)'] += 1; continue
        s_ = lambda p: float((p - a) @ d)
        for tri in ((a, b, qb), (a, qb, qa)):
            tri = [np.asarray(x, float) for x in tri]; nn = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            if np.linalg.norm(nn) < 1e-7: continue
            if nn @ sc.n[k] < 0: tri = tri[::-1]
            sc.put(sc.mat[k], tri, [np.array([s_(c), c[1], 1.0]) @ M for c in tri], 'K'); up += 1
        made.append((round(L * (a[1] - qa[1] + b[1] - qb[1]) / 2, 1), [round(float(x), 1) for x in (a + b) / 2], round(float(dmax), 1)))
    sc.note('K', 'foot edges of natural upright faces carried down to %s: %d (%d triangles, %.0f m2, drop median %.1f m, largest %.1f m) ; left: %s' % (
        'the sea (%.1f) or the ground' % sea if sea is not None else 'the ground', len(made), up, sum(m[0] for m in made), float(np.median([m[2] for m in made])) if made else 0, max([m[2] for m in made] or [0]), dict(rej)))
    for i, m in enumerate(sorted(made, reverse=True)[:6]): sc.view('cliff_%d' % i, m[1], 25.0, 60.0)

def tops(sc):
    """rule T (patch 3: "make the top of the mesa look like every other seastack (with grass)", "fill all the mesa/plateau tops you can find"): seen from straight
    above, a hole whose rim is level and whose own faces hang DOWN from the rim (walls of a stack, a mesa, a rock) is a top left open - from above the walls'
    insides and the sea show - and is capped over the rim's own corners. Grass where trees stand on it or grass lies beside it, else the rim's own tile."""
    import shapely
    from shapely.geometry import Polygon, LineString, Point
    from shapely.ops import unary_union
    from scipy.spatial import cKDTree
    C = sc.cfg; G = []; corners = []
    for k in range(sc.N):
        if sc.cut[k] or sc.area[k] < 1e-6 or all((k, ti) in sc.rm for ti in range(len(sc.tris(k)))): continue
        P = sc.P[k]; q = [r2(p) for p in P]; g = Polygon(q); G.append(g.buffer(0.02) if (g.is_valid and g.area > 1e-4) else LineString(q + [q[0]]).buffer(0.02))
        for p in P: corners.append((p[0], p[2], p[1], k))
    for i, (t, P, uv, r) in enumerate(sc.add):
        q = [r2(p) for p in P]; g = Polygon(q); G.append(g.buffer(0.02) if (g.is_valid and g.area > 1e-4) else LineString(q + [q[0]]).buffer(0.02))
    U = unary_union(G); CA = np.array(corners, float); kc = cKDTree(CA[:, :2]); made = []; rej = collections.Counter()
    trees = np.array([sc.ctr[k] for k in range(sc.N) if sc.cut[k] and sc.cls[k] in TREE_CLS] or [[1e9, 0, 1e9]], float); tk = cKDTree(trees[:, [0, 2]])
    grass = [k for k in range(sc.N) if not sc.cut[k] and sc.cls[k] == 'grass' and abs(sc.n[k][1]) > 0.7]; gkd = cKDTree(np.array([sc.ctr[k][[0, 2]] for k in grass] or [[1e9, 1e9]]))
    up = -1.0 if sum(sc.n[k][1] for k in range(sc.N) if sc.road[k]) < 0 else 1.0      # which way "up" winds in these coordinates (as rule G)
    for g in _geoms(U):
        for ring in g.interiors:
            h = Polygon(ring)
            if not C['top_min'] <= h.area <= C['top_area']: continue
            hs = h.buffer(0.021, join_style=2).simplify(0.10); pts = list(hs.exterior.coords)[:-1] if hs.geom_type == 'Polygon' else []
            if len(pts) < 3: rej['outline closes up'] += 1; continue
            cand = [kc.query_ball_point(p, 0.3) for p in pts]
            V = []
            for p, c in zip(pts, cand):
                if c: j = max(c, key=lambda j: CA[j, 2]); V.append((round(CA[j, 0], 3), round(CA[j, 2], 3), round(CA[j, 1], 3), int(CA[j, 3])))      # the rim: the highest corner there
            V = [v for i, v in enumerate(V) if v[:3] != V[i - 1][:3]]
            if len(V) < 3: rej['fewer than 3 corners round it'] += 1; continue
            ys = np.array([v[1] for v in V]); width = math.sqrt(h.area)
            if np.ptp(ys) > C['top_rise'] + C['top_slope'] * width: rej['its rim is not level'] += 1; continue
            down = [float(np.mean([v[1] - float(sc.P[v[3]][:, 1].min()) for v in V]))]      # how far the rim's own faces reach below it
            if down[0] < C['top_wall']: rej['nothing hangs down from its rim (not a top)'] += 1; continue
            pg = Polygon([(v[0], v[2]) for v in V]); pg = pg if pg.is_valid else pg.buffer(0); Y = {(v[0], v[2]): v[1] for v in V}; tris = []
            for q in _geoms(pg, mina=0.05):
                for t in shapely.constrained_delaunay_triangles(q).geoms:
                    kk = [(round(x, 3), round(z, 3)) for x, z in list(t.exterior.coords)[:3]]
                    if all(k_ in Y for k_ in kk) and t.area > 1e-3: tris.append(np.array([[k_[0], Y[k_], k_[1]] for k_ in kk]))
            if not tris: rej['could not be cut'] += 1; continue
            c = h.centroid; ntree = len(tk.query_ball_point([c.x, c.y], width / 2 + 3.0))
            if grass:                                                   # (the owner: the tops grass "like every other seastack": the course's own grass, its tile nearest by)
                gi = [i for i in gkd.query_ball_point([c.x, c.y], width / 2 + 150.0) if i < len(grass)] or [int(gkd.query([c.x, c.y], k=1)[1])]
                kb = grass[max(gi, key=lambda i: sc.area[grass[i]])]; tile = sc.mat[kb]; uv0 = sc.UV[kb][0]; what = 'grass'
            else:
                kr = collections.Counter(v[3] for v in V).most_common(1)[0][0]; tile = sc.mat[kr]; uv0 = sc.UV[kr][0]; what = sc.cls[kr] or 'rim'
            for P in tris:
                if (np.cross(P[1] - P[0], P[2] - P[0])[1] > 0) != (up > 0): P = P[::-1]
                sc.put(tile, P, [uv0] * 3, 'T')
            made.append((round(h.area), len(tris), [round(c.x, 1), round(float(np.median(ys)), 1), round(c.y, 1)], what, ntree, round(down[0], 1)))
    sc.note('T', 'tops seen from above (%.0f .. %.0f m2, rim level, its faces hanging down) capped: %d (%d triangles, %.0f m2): %s ; left: %s' % (C['top_min'], C['top_area'], len(made), sum(m[1] for m in made), sum(m[0] for m in made), sorted(made, reverse=True), dict(rej)))
    for i, m in enumerate(sorted(made, reverse=True)[:8]): sc.view('top_%d' % i, m[2], 40.0, 70.0)

def forest_foot(sc):
    """rule F's opt-in correction (the owner's hand edit in the forest villages): a corner of the forest floor that stands on the TOP of a kerb goes down to the kerb's foot,
    straight under it ("uprights are met at their foot, never at their top")."""
    C = sc.cfg; tops = {}
    for k in range(sc.N):
        if sc.cut[k] or sc.role[k] not in ('', 'paving') or abs(sc.n[k][1]) > 0.3: continue
        P = sc.P[k]
        for p in P:
            # A sloping kerb has a different top/foot height at each end.
            # Measure the local vertical pair, not the whole face's height or
            # only its highest corner. Original scenery remains untouched.
            under = [q for q in P if np.hypot(q[0] - p[0], q[2] - p[2]) < 0.05 and C['foot_min'] < p[1] - q[1] <= C['foot_max']]
            if under: kk = (round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2)); tops[kk] = min(tops.get(kk, 1e9), float(min(q[1] for q in under)))
    use = collections.defaultdict(list)
    for i, (t, P, uv, r) in enumerate(sc.add):
        if r == 'F':
            for j, p in enumerate(P): use[(round(p[0], 2), round(p[1], 2), round(p[2], 2))].append((i, j))
    n = 0; where = []; changes = []
    for kk, L in use.items():
        if kk not in tops: continue
        ok = False                                                      # only where the floor itself lies lower: a triangle here has both its other corners under this one
        for i, j in L:
            P = sc.add[i][1]; o = [P[m][1] for m in range(3) if m != j]
            if max(o) < kk[1] - 0.2: ok = True
        if not ok: continue
        changes.append((kk, L))
        n += 1; where.append([kk[0], tops[kk], kk[2]])
    # Decide on the original fill. Lowering one corner must not make its
    # neighbour eligible merely because triangles were visited in that order.
    for kk, L in changes:
        for i, j in L: t, P, uv, r = sc.add[i]; P = list(P); P[j] = (P[j][0], tops[kk], P[j][2]); sc.add[i] = (t, P, uv, r)
    sc.note('F', 'corners of the forest floor standing on a kerb top, set down to its foot: %d %s' % (n, [[round(x, 1) for x in w] for w in where[:40]]))

def flanks(sc, T, floor):
    """rule B (the owner's hand edit, 13 walls on 8 buildings): a building front with a roof that runs back from it gets its FLANK: a wall from the front's end corner back along the
    roof's side eave, as tall as the front, wearing the front's picture. Not where a wall already stands under that eave."""
    from shapely.geometry import Point
    C = sc.cfg; edges = []
    for k in range(sc.N):
        if sc.role[k] != 'roof' or sc.cut[k] or not T['scope'].contains(Point(r2(sc.ctr[k]))): continue
        P = [np.array(sc.moved.get(r3(p), p), float) for p in sc.P[k]]
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]; L = float(np.hypot(b[0] - a[0], b[2] - a[2]))
            if L >= C['flank_min'] and abs(a[1] - b[1]) < 0.5: edges.append((a, b)); edges.append((b, a))
    walls = [np.array(P) for t, P, uv, r in sc.add if r in ('W', 'D')]
    for k in range(sc.N):
        if sc.role[k] == 'building' and not sc.cut[k]:
            for ti, ix in enumerate(sc.tris(k)):
                if (k, ti) not in sc.rm: walls.append(sc.P[k][list(ix)])
    WB = np.array([np.r_[w.min(0), w.max(0)] for w in walls]) if walls else np.zeros((0, 6))
    def walled(p):                                                      # an upright building face stands at this place (0.5 m off at most), covering this height
        m = (WB[:, 0] - 0.5 <= p[0]) & (p[0] <= WB[:, 3] + 0.5) & (WB[:, 2] - 0.5 <= p[2]) & (p[2] <= WB[:, 5] + 0.5) & (WB[:, 1] <= p[1]) & (p[1] <= WB[:, 4])
        for i in np.flatnonzero(m):
            w = walls[i]; n = np.cross(w[1] - w[0], w[2] - w[0]); l = np.linalg.norm(n)
            if l > 1e-9 and abs(float((p - w[0]) @ n)) / l < 0.5: return True
        return False
    made = []; cands = []; FA = T.get('facades', [])
    tops = [(c[[0, 2]], float(c[1]), i) for i, F in enumerate(FA) for c in (F['cs'][2], F['cs'][3])]
    for fi, F in enumerate(FA):
        b0, b1, t1, t0 = F['cs']; d3 = np.array([F['d'][0], 0.0, F['d'][1]])
        for foot, top, other in ((b0, t0, t1), (b1, t1, t0)):
            best = None
            for a, b in edges:
                if np.hypot(a[0] - top[0], a[2] - top[2]) > C['snap_f'] or abs(a[1] - top[1]) > 0.6: continue
                v = b - a; v[1] = 0; L = float(np.linalg.norm(v))
                if abs(float(v @ d3)) / L > 0.64: continue             # it runs along the front, not back from it (under 50 degrees)
                if best is None or L > best[0]: best = (L, b)
            if best is None: continue
            L, bk = best; topB = np.array([bk[0], top[1], bk[2]]); fl = floor.at(bk[0], foot[1] + 0.5, bk[2], C['maxgap'] + 1.0); footB = np.array([bk[0], (fl - C['under']) if fl is not None else foot[1], bk[2]])
            if sum(walled(top + (topB - top) * s_ + np.array([0, -2.0, 0])) for s_ in (0.3, 0.5, 0.7)) >= 2: continue      # a wall stands under this eave already
            nb = [y for xz, y, j in tops if j != fi and np.hypot(xz[0] - top[0], xz[1] - top[2]) < C['snap_f']]      # how far this front stands above the fronts that end at the same corner
            inward = (other - top); inward[1] = 0
            cands.append(dict(quad=[footB, foot, top, topB], name=F['name'], inward=inward, L=L, expo=float(top[1] - max(nb)) if nb else float(top[1] - foot[1]), alone=not nb))
    cands.sort(key=lambda c: -float(c['quad'][2][1])); keep = []
    for c in cands:                                                     # two buildings side by side give the same flank: the taller one's stays
        mid = lambda q: (q['quad'][1] + q['quad'][3])[[0, 2]] / 2; dr = lambda q: (q['quad'][3] - q['quad'][2])[[0, 2]] / max(np.linalg.norm((q['quad'][3] - q['quad'][2])[[0, 2]]), 1e-9)
        if any(np.linalg.norm(mid(k) - mid(c)) < 1.5 and abs(float(dr(k) @ dr(c))) > 0.95 for k in keep): continue
        keep.append(c)
    for c in keep:
        if c['expo'] < C['flank_expose']: continue
        quad = c['quad']; uvq = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]      # the whole picture, its end at the front corner (as the owner laid it)
        for ix in ((0, 1, 2), (0, 2, 3)):
            P = [quad[i] for i in ix]; n = np.cross(P[1] - P[0], P[2] - P[0])
            if n @ c['inward'] > 0: ix = (ix[0], ix[2], ix[1])          # it faces away from the building
            sc.put(c['name'], [quad[i] for i in ix], [uvq[i] for i in ix], 'B')
        made.append((round(c['L'], 1), [round(float(x), 1) for x in (quad[1] + quad[3]) / 2], round(c['expo'], 1)))
    sc.flank_cands = getattr(sc, 'flank_cands', []) + keep
    sc.note('B', 'town at (%.0f, %.0f): free eaves running back from a front %d ; flanks made (the front stands at least %.1f m above its neighbour at that corner) %d, %.0f m of wall (length, middle, metres above the neighbour): %s' % (T['closed'].centroid.x, T['closed'].centroid.y, len(keep), C['flank_expose'], len(made), sum(m[0] for m in made), sorted(made, key=lambda m: m[1])))

# ------------------------------------------------------------------------------------------------------------ A audit
def audit(sc):
    """what the patch may not contain, counted on the faces it adds (against each other and against what stays)"""
    C = sc.cfg; A = [(t, np.array(P), r) for t, P, uv, r in sc.add]; zero = thin = 0; bad = []
    for t, P, r in A:
        a = _area3(P); L = max(np.linalg.norm(P[i] - P[(i + 1) % 3]) for i in range(3))
        if a < 1e-7: zero += 1
        elif 2 * a / L < C['sliver']: thin += 1; bad.append(('thinner than %.0f cm' % (100 * C['sliver']), r, [round(float(x), 1) for x in P.mean(0)]))
    # faces lying on one another: nearly parallel, within onface of each other's plane, overlapping in that plane
    stay = []
    for k in range(sc.N):
        if sc.cut[k]: continue
        for ti, ix in enumerate(sc.tris(k)):
            if (k, ti) not in sc.rm and _area3(sc.P[k][list(ix)]) > 1e-4: stay.append(sc.P[k][list(ix)])
    allT = [P for t, P, r in A if _area3(P) > 1e-6] + stay; na = sum(1 for t, P, r in A if _area3(P) > 1e-6); rules = [r for t, P, r in A if _area3(P) > 1e-6]
    grid = collections.defaultdict(list); cell = 6.0
    for i, P in enumerate(allT):
        lo = np.floor(P[:, [0, 2]].min(0) / cell).astype(int); hi = np.floor(P[:, [0, 2]].max(0) / cell).astype(int)
        if (hi - lo).max() > 30: continue
        for x in range(lo[0], hi[0] + 1):
            for z in range(lo[1], hi[1] + 1): grid[(x, z)].append(i)
    Nn = [np.cross(P[1] - P[0], P[2] - P[0]) for P in allT]; Nn = [n / max(np.linalg.norm(n), 1e-12) for n in Nn]; seen = set(); lying = []
    from shapely.geometry import Polygon
    for i in range(na):
        P = allT[i]; n = Nn[i]; lo = np.floor(P[:, [0, 2]].min(0) / cell).astype(int); hi = np.floor(P[:, [0, 2]].max(0) / cell).astype(int); cand = set()
        for x in range(lo[0], hi[0] + 1):
            for z in range(lo[1], hi[1] + 1): cand.update(grid[(x, z)])
        u = P[1] - P[0]; u /= max(np.linalg.norm(u), 1e-12); w = np.cross(n, u); g1 = None
        for j in cand:
            if j == i or (j < na and j < i) or (i, j) in seen: continue
            Q = allT[j]
            if abs(Nn[j] @ n) < 0.9994 or np.abs((Q - P[0]) @ n).max() > C['onface'] or (Q.min(0) > P.max(0) + 0.01).any() or (P.min(0) > Q.max(0) + 0.01).any(): continue
            if g1 is None: g1 = Polygon([((p - P[0]) @ u, (p - P[0]) @ w) for p in P]).buffer(0)
            g2 = Polygon([((p - P[0]) @ u, (p - P[0]) @ w) for p in Q]).buffer(0); ov = g1.intersection(g2).area
            if ov > 0.02 and ov > 0.02 * min(g1.area, g2.area): seen.add((i, j)); lying.append((round(ov, 2), rules[i], rules[j] if j < na else '1995', [round(float(x), 1) for x in P.mean(0)]))
    by = collections.Counter((a[1], a[2]) for a in lying)
    sc.note('A', 'faces added %d ; without area %d ; thinner than %.0f cm %d ; added faces lying on another face (within %.0f cm of its plane, overlapping): %d %s' % (len(A), zero, 100 * C['sliver'], thin, 100 * C['onface'], len(lying), dict(by)))
    if lying: sc.note('A', 'lying on another face, largest first (overlap m2, rule, other, where): %s' % sorted(lying, reverse=True)[:25])
    if bad: sc.note('A', 'thin faces: %s' % bad[:25])
    sc.audit = dict(zero=zero, thin=thin, lying=len(lying))
    for i, a in enumerate(sorted(lying, reverse=True)[:4]): sc.view('lying_%d' % i, a[3], 12.0, 16.0)

def audit_patch(S, paths, log=print, **over):
    """the audit on patch files that were NOT made here (hand patches, an edited scene): python genpatch1995.py audit <snapshot.pkl> <patch 1.json> [<patch 2.json> ...]
    The patches are laid on the snapshot in the order given. A triangle to remove takes out the polygon triangle its middle lies in (a build's pieces of a polygon
    count for the whole polygon: good enough for a check)."""
    cfg = dict(CFG); cfg.update(over); sc = Scene(S, cfg, log); cell = 6.0; grid = collections.defaultdict(list); T = []
    for k in range(sc.N):
        for ti, ix in enumerate(sc.tris(k)):
            P = sc.P[k][list(ix)]; n = np.cross(P[1] - P[0], P[2] - P[0]); l = float(np.linalg.norm(n))
            if l < 1e-9: continue
            T.append((k, ti, P, n / l)); lo = np.floor(P[:, [0, 2]].min(0) / cell).astype(int); hi = np.floor(P[:, [0, 2]].max(0) / cell).astype(int)
            if (hi - lo).max() > 30: continue
            for x in range(lo[0], hi[0] + 1):
                for z in range(lo[1], hi[1] + 1): grid[(x, z)].append(len(T) - 1)
    for path in paths:
        J = json.load(open(path)); nr = 0; nm = 0
        for m in J.get('move', []):                                     # corners moved: in the polygons that have all three corners of the triangle as it was
            B = np.array(m['before'], float); A = np.array(m['after'], float)
            for j in grid.get((int(math.floor(B[:, 0].mean() / cell)), int(math.floor(B[:, 2].mean() / cell))), ()):
                k = T[j][0]; d = np.linalg.norm(sc.P[k][:, None, :] - B[None], axis=2)
                if (d.min(0) < 0.002).all():
                    for c in range(3):
                        i = int(np.argmin(d[:, c]))
                        if np.linalg.norm(A[c] - B[c]) > 1e-6: sc.P[k][i] = A[c]; nm += 1
        for r in J.get('remove', []):
            c = np.mean(np.array(r['p'], float), 0)
            for j in grid.get((int(math.floor(c[0] / cell)), int(math.floor(c[2] / cell))), ()):
                k, ti, P, n = T[j]
                if sc.mat[k] != r['tile'].split('|')[0] or abs(float((c - P[0]) @ n)) > 0.01 or not (_in_tri3(c, P, n) or _in_tri3(c, P[::-1], -n)): continue
                if (k, ti) not in sc.rm: sc.rm.add((k, ti)); nr += 1
                break
        for f in J.get('add', []): sc.put(f['tile'], f['p'], f['uv'], os.path.basename(path).split('.')[-2] if os.path.basename(path).split('.')[-2].isdigit() else 'patch')
        log('       genpatch audit: %s: %d faces added ; %d triangles to remove took out %d polygon triangles of the snapshot ; corners moved %d' % (os.path.basename(path), len(J.get('add', [])), len(J.get('remove', [])), nr, nm))
    audit(sc); return sc

# ------------------------------------------------------------------------------------------------------------ the patch file
def run(S, out=None, log=print, **over):
    cfg = dict(CFG); cfg.update(S['cfg'].get('patch_rules_cfg') or {}); cfg.update(over); sc = Scene(S, cfg, log); only = cfg.get('only', 'HFSPWRDA')
    if 'H' in only: holes(sc)
    if 'F' in only:
        ox, oz = S['ox'], S['oz']
        FF = S.get('forest', []) if cfg['forest'] == 'default' else S.get('forest_variants', {}).get(cfg['forest'])
        assert FF is not None, 'the snapshot has no forest floor variant %r: make the snapshot again with this genpatch1995.py' % cfg['forest']
        for t, P, UV in FF: sc.put(t, [(p[0] - ox, p[1], -(p[2] - oz)) for p in P], UV, 'F')
        sc.note('F', 'forest floor (roadfill1995.generate, run in the importer; variant %s): %d triangles, %.0f m2%s' % (cfg['forest'], len(FF), sum(_area3(np.array(P)) for t, P, UV in FF), ' ; THE GENERATOR FAILED, see forest_error in the snapshot' if S.get('forest_error') else ''))
        Ff = [np.mean(P, 0) for t, P, UV, r in sc.add if r == 'F']
        for i in range(4):
            if Ff: q = Ff[(2 * i + 1) * len(Ff) // 8]; sc.view('forest_%d' % i, (q[0], q[1], q[2]), 22.0, 30.0)
        if cfg['forest_foot']: forest_foot(sc)
    if 'C' in only: kerb_caps(sc)
    TW = towns(sc)
    for T in TW:
        if cfg['towns'] == 'paved' and not T['paved']: continue
        new = pavement(sc, T) if (T['paved'] and 'P' in only) else []
        fl = [P for P in new]
        for k in range(sc.N):                                           # the floor a wall can stand on: the new pavement, the road, lying ground
            if sc.cut[k] or abs(sc.n[k][1]) < 0.7 or sc.role[k] in ('roof', 'building', 'board') or not T['scope'].buffer(10).intersects(__import__('shapely.geometry', fromlist=['Point']).Point(r2(sc.ctr[k]))): continue
            for ti, ix in enumerate(sc.tris(k)):
                if (k, ti) not in sc.rm: fl.append(sc.P[k][list(ix)])
        floor = Floor(fl)
        fv = facades(sc, T, floor) if 'W' in only else []
        if 'R' in only: roofs(sc, T, fv)
        if 'D' in only: walls_down(sc, T, floor)
        if 'B' in only: flanks(sc, T, floor)
        c = T['closed'].centroid; y = sc.road_y(c.x, c.y)
        for i, (dx, dz) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))): sc.views.append(dict(name='town_%d_%d' % (TW.index(T), i), eye=[c.x + 70 * dx, y + 45, c.y + 70 * dz], target=[c.x, y + 5, c.y]))
    if 'G' in only: plan_holes(sc)                                      # after the towns: a hole the pavement closes is no hole
    if 'K' in only: cliffs_down(sc)                                     # patch 3 (opt-in): cliffs carried down, then tops capped
    if 'T' in only: tops(sc)
    if 'A' in only: audit(sc)
    return write_patch(sc, out)

def write_patch(sc, out):
    S = sc.S; f5 = lambda x: round(float(x), 5); rem = []
    for k, ti in sorted(sc.rm): rem.append(dict(tile=sc.mat[k], p=[[f5(x) for x in sc.P[k][i]] for i in sc.tris(k)[ti]]))
    add = [dict(tile=t, p=[[f5(x) for x in p] for p in P], uv=[[round(float(x), 6) for x in u] for u in UV]) for t, P, UV, r in sc.add if _area3(np.array(P)) > 1e-9]
    settings = {'sea': {'clip': False}} if (S['cfg'].get('sea') and 'S' in sc.cfg.get('only', 'S')) else {}
    head = dict(format='sr3lab course patch', version=3 if sc.bake else (2 if rem else 1), course=dict(game=S['cfg']['game'], course=str(S['cfg']['course']), name=S['cfg']['name']), base=dict(course_export_sha1=S['sha1'], needs=[]), whole_polygons=True,
                made_by='genpatch1995.py: the rules of docs/kb/26_generalised_patches.md on the raw import (rules run: %s ; towns: %s)' % (sc.cfg.get('only', 'HFSPWRDA'), sc.cfg['towns']), **({'settings': settings} if settings else {}),
                space='the build decoded back (preview_obj.py): x, y up, z = -gameZ of the 1995 course, metres; uv as Blender has them (v up)')
    by = collections.Counter(r for t, P, UV, r in sc.add); sc.note('patch', 'faces to add %d %s ; triangles to remove %d ; facade pictures %d ; settings %s' % (len(add), dict(by), len(rem), len(sc.bake), settings))
    if out:
        NL = chr(10)
        with open(out, 'w', newline=NL) as fo:
            fo.write('{' + NL + ''.join(' %s: %s,%s' % (json.dumps(k), json.dumps(v), NL) for k, v in head.items()))
            fo.write(' "remove": [' + NL + (',' + NL).join('  ' + json.dumps(a) for a in rem) + NL + ' ],' + NL)
            if sc.bake: fo.write(' "bake": [' + NL + (',' + NL).join('  ' + json.dumps(e, separators=(',', ':')) for e in sc.bake) + NL + ' ],' + NL)
            fo.write(' "add": [' + NL + (',' + NL).join('  ' + json.dumps(a) for a in add) + NL + ' ],' + NL + ' "move": []' + NL + '}' + NL)
        open(out[:-5] + '.report.txt', 'w').write(''.join('%s: %s\n' % n for n in sc.notes)); json.dump(sc.views, open(out[:-5] + '.views.json', 'w'), indent=1)
        sc.log('       genpatch: %d bytes -> %s (+ .report.txt, .views.json)' % (os.path.getsize(out), out))
    return sc

# ------------------------------------------------------------------------------------------------------------ in the importer
def snapshot(faces, rd, BC, cfg, log):
    """what the rules read, as plain data (so that they run without the importer: python genpatch1995.py <snapshot.pkl>)"""
    import retex, overlay_bake as OB, coursepatch
    base = lambda m: str(m).split('|')[0]; lab = {k: v[0] for k, v in retex.labels().items()}
    mats = sorted({str(fc[0]) for fc in faces}); orig = {m: OB.ORIGIN.get(base(m), base(m)) for m in mats}; cls = {m: lab.get(orig[m]) or '' for m in mats}
    tiles = {}
    for m in mats:
        px = BC.tile_pixels(m)
        if px is None: tiles[m] = None; continue
        rgb = np.asarray(px[0]); hole = px[1]; keep = (~np.asarray(hole)) if hole is not None else np.ones(rgb.shape[:2], bool)
        tiles[m] = dict(size=(int(rgb.shape[1]), int(rgb.shape[0])), mean=[float(x) for x in (rgb[keep].reshape(-1, 3).mean(0) if keep.any() else rgb.reshape(-1, 3).mean(0))], cut=hole is not None)
    V = np.asarray(rd['V'], float)
    return dict(faces=[(str(fc[0]), str(fc[1]), [tuple(map(float, p)) for p in fc[2]], [tuple(map(float, u)) for u in fc[3]]) for fc in faces],
                ox=float(rd['ox']), oz=float(rd['oz']), cen=V[:, int(rd['hw'])].copy(), lat=np.asarray(rd['lat'], float).copy(), hw=int(rd['hw']),
                orig=orig, cls=cls, tiles=tiles, road_tiles=sorted(BC.ROAD_TILES), sha1=coursepatch.export_sha1(BC.HI),
                cfg={k: cfg.get(k) for k in ('game', 'course', 'name', 'round_exclude', 'roof_tiles', 'patch_roles', 'patch_rules_cfg', 'sea')})

def write(faces, rd, BC, cfg, log):
    """import_classic's "patch_rules" stage: the snapshot, the forest floor (it needs the importer's tiles), and the patch when shapely and scipy are there"""
    from common import WORK
    S = snapshot(faces, rd, BC, cfg, log)
    import roadfill1995
    try: ff = roadfill1995.generate(faces, rd, BC, log, roofs=tuple(cfg.get('roof_tiles', cfg.get('round_exclude', ()))))
    except Exception as e: ff = []; log('       genpatch: the forest-floor generator failed on this course: %r' % (e,)); import traceback; S['forest_error'] = traceback.format_exc()
    S['forest'] = [(str(fc[0]), [tuple(map(float, p)) for p in fc[2]], [tuple(map(float, u)) for u in fc[3]]) for fc in ff]
    S['forest_variants'] = {}                                           # rule F's opt-in variants (CFG 'forest'), made here because the generator needs the importer
    for name, fb, ks in (('bridges', True, False), ('gaps', False, True), ('bridges+gaps', True, True)):
        roadfill1995.FILL_BRIDGES, roadfill1995.KEEP_SLABS = fb, ks; roadfill1995.SLABS[:] = []
        try: fv = roadfill1995.generate(faces, rd, BC, lambda *a: None, roofs=tuple(cfg.get('roof_tiles', cfg.get('round_exclude', ()))))
        except Exception as e: fv = []; log('       genpatch: forest floor variant %s failed: %r' % (name, e))
        S['forest_variants'][name] = [(str(fc[0]), [tuple(map(float, p)) for p in fc[2]], [tuple(map(float, u)) for u in fc[3]]) for fc in fv]
    roadfill1995.FILL_BRIDGES = roadfill1995.KEEP_SLABS = False; log('       genpatch: forest floor: %d triangles ; variants %s' % (len(ff), {k: len(v) for k, v in S['forest_variants'].items()}))
    d = os.path.join(WORK, 'tmp', 'genpatch'); os.makedirs(d, exist_ok=True); p = os.path.join(d, '%s.%s.snapshot.pkl' % (cfg['game'], cfg['name']))
    pickle.dump(S, open(p, 'wb')); log('       genpatch: snapshot of %d faces -> %s' % (len(S['faces']), p))
    out = cfg['patch_rules'] if isinstance(cfg['patch_rules'], str) else os.path.join(d, '%s.%s.rules.json' % (cfg['game'], cfg['name']))
    try: import shapely, scipy
    except ImportError: log('       genpatch: shapely / scipy are not installed for this Python. Run:  uv run --with "shapely>=2.1" --with numpy --with scipy python genpatch1995.py "%s" "%s"' % (p, out)); return None
    run(S, out, log); return out

if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if '=' not in x or x.endswith('.pkl') or x.endswith('.json')]; kv = dict(x.split('=', 1) for x in sys.argv[1:] if x not in a)
    if a and a[0] == 'audit': audit_patch(pickle.load(open(a[1], 'rb')), a[2:]); sys.exit(0)
    S_ = pickle.load(open(a[0], 'rb')); out_ = a[1] if len(a) > 1 else a[0].replace('.snapshot.pkl', '.rules.json')
    def _val(v):
        try: return json.loads(v)
        except Exception: return v
    run(S_, out_, print, **{k: _val(v) for k, v in kv.items()})
