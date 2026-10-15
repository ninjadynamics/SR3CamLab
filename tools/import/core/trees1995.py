"""Trees, lamps and other cut-out boards stand ON the ground.
The 1995 course hides the feet of its roadside boards behind walls; with real ground filled in beside the road a board
whose foot is above that ground reads as a floating tree or a tree without the lower part of its trunk (user, 2026-10-07:
"either we have trees with missing trunks or floating trees, lower those trees"). So a tree is LOWERED as a whole - the
ground is not heaped up under it and the trunk is not stretched.

    faces2, info = lower_boards(faces, ground)       faces: importer face list (material, section, [xyz], [uv]); cut-out
                                                     boards are the '_t' materials; ground: every lying surface of the build
"""
import collections
import numpy as np
import fill1995 as F

TREE_CLASSES = ('crown', 'trunk', 'bare', 'tree', 'lamp')               # not tree_wall (forest backdrop), house_stone (the tower's cut-out top went down with "the trees"), ivy, fence, grass

def lower_boards(faces, ground, sink=0.10, gap=0.12, reach=25.0, up=0.6, classes=TREE_CLASSES, origin=None):
    """Which boards make ONE tree - from how the 1995 trees are built (seen in the data, 2026-10-07): a tree is a set of upright
    BLADES that all start on one vertical AXIS and run outwards (three directions); a blade is a strip of boards in one plane
    (trunk, a composed joint, crown inner part, crown outer part), each board listed once per side. So:
      - boards that share a plan corner and lie in the same plane direction form a blade strip;
      - a plan corner where boards of two or more DIFFERENT directions meet is an axis;
      - a tree = every blade strip that touches the same axis. Boards that cross each other (flat X-shaped trees, lamp posts)
        or stand alone on the same footprint are one tree too.
    The whole tree goes down by ONE amount: the largest gap between the ground and the foot of one of its lowest boards
    (those within 0.3 m of the tree's lowest foot). A board whose foot is in the ground already counts 0. Nothing is raised.
    (Earlier versions grouped by centre distance, by touching corners in 3D and by "hangs on": each broke trees in game.)"""
    import retex
    if origin is None:
        import overlay_bake as OB
        origin = OB.ORIGIN
    lab = {k: v[0] for k, v in retex.labels().items()}; cls = lambda m: lab.get(origin.get(m, m))
    ix = F.Index(ground); B = []
    for k, (mat, sec, P, UV) in enumerate(faces):
        if not str(mat).endswith('_t') or cls(mat) not in classes: continue
        Q = np.asarray(P, float); n = np.cross(Q[1] - Q[0], Q[2] - Q[0]); ln = np.linalg.norm(n)
        if ln < 1e-9 or abs(n[1]) / ln > 0.5: continue
        pts = sorted({(round(float(q[0]) / 0.05), round(float(q[2]) / 0.05)) for q in Q})
        a_, b_ = np.array(pts[0], float) * 0.05, np.array(pts[-1], float) * 0.05
        ang = int(round(np.degrees(np.arctan2(n[2], n[0])) % 180.0 / 10.0)) % 18              # plane direction, 10 degree steps
        B.append(dict(k=k, c=Q[:, [0, 2]].mean(0), foot=float(Q[:, 1].min()), top=float(Q[:, 1].max()), pts=pts, seg=(a_, b_), ang=ang))
    lower_boards.moved = {}
    if not B: return faces, dict(boards=0, trees=0)
    nb = len(B); par = list(range(nb))
    def find(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    def near_ang(a, b): return min((a - b) % 18, (b - a) % 18) <= 1
    at = collections.defaultdict(list)
    for i, b in enumerate(B):
        for pt in b['pts']:
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1): at[(pt[0] + dx, pt[1] + dz)].append(i)
    axis = {}
    for pt, ii in at.items():
        ii = sorted(set(ii)); dirs = []
        for i in ii:
            if not any(near_ang(B[i]['ang'], d_) for d_ in dirs): dirs.append(B[i]['ang'])
        if len(dirs) >= 2:                                                # blades of different directions meet here: an axis - all of them are one tree
            for i in ii[1:]: par[find(i)] = find(ii[0])
        else:                                                              # same plane: one blade strip (or the two sides of one board)
            for i in ii[1:]:
                if B[i]['foot'] <= B[ii[0]]['top'] + 0.5 and B[ii[0]]['foot'] <= B[i]['top'] + 0.5: par[find(i)] = find(ii[0])
    # crossing boards (X-shaped trees, lamp posts) and boards on the same footprint
    cell = collections.defaultdict(list)
    for i, b in enumerate(B): cell[(int(b['c'][0] // 4), int(b['c'][1] // 4))].append(i)
    def cross(s1, s2):
        (a, b), (c, d) = s1, s2; r = b - a; q = d - c; den = r[0] * q[1] - r[1] * q[0]
        if abs(den) < 1e-9: return False
        t = ((c[0] - a[0]) * q[1] - (c[1] - a[1]) * q[0]) / den; u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
        return 0.15 < t < 0.85 and 0.15 < u < 0.85
    for i, b in enumerate(B):
        cx, cz = int(b['c'][0] // 4), int(b['c'][1] // 4)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for j in cell.get((cx + dx, cz + dz), ()):
                    if j <= i or find(i) == find(j): continue
                    if B[j]['foot'] > b['top'] + 0.5 or b['foot'] > B[j]['top'] + 0.5: continue
                    if np.hypot(*(b['c'] - B[j]['c'])) < 0.25 or cross(b['seg'], B[j]['seg']): par[find(i)] = find(j)
    trees = collections.defaultdict(list)
    for i in range(nb): trees[find(i)].append(i)
    def gap_of(b):
        hs = [h for h, _ in ix.heights(float(b['c'][0]), float(b['c'][1]), True)]
        if any(b['foot'] + up < h < b['top'] - 0.3 for h in hs): return 0.0
        below = [h for h in hs if b['foot'] - reach <= h <= b['foot'] + up]
        return (b['foot'] - max(below)) if below else None
    out = list(faces); hist = collections.Counter(); none = 0; sizes = []
    for t_, mm in trees.items():
        lowest = min(B[i]['foot'] for i in mm); gs = [g for g in (gap_of(B[i]) for i in mm if B[i]['foot'] <= lowest + 0.3) if g is not None]; sizes.append(len(mm))
        if not gs: none += 1; continue
        g = max(gs)
        hist['on the ground already' if g <= gap else 'lowered up to 0.5 m' if g <= 0.5 else 'lowered 0.5 .. 2 m' if g <= 2 else 'lowered 2 .. 5 m' if g <= 5 else 'lowered more than 5 m'] += 1
        if g <= gap: continue
        d = g + sink; ks = [B[i]['k'] for i in mm]
        for k in ks:
            mat, sec, P, UV = out[k]; out[k] = (mat, sec, [(x, y - d, z) for x, y, z in P], UV); lower_boards.moved[k] = ks
    return out, dict(boards=nb, trees=len(trees), boards_per_tree_median=int(np.median(sizes)), biggest_tree=int(max(sizes)), no_ground_under_the_tree=none, **dict(hist))
