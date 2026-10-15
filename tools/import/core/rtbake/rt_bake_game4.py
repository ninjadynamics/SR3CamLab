"""RT bake for the GAME, fourth version (2026-10-13, after the owner's second drive).   python rt_bake_game4.py <path> <faces.pkl> [fast|slow] [<out path>]
<path> = what an importer build collected (lm_collect); faces.pkl = the same build's GAPFILL_DUMP. Run from the importer folder (lightmap1995, retex);
needs rays.c, fastlm_rays.c, rtg2_rays.c, rtg4.c beside this file (rtg4.c is made by mk_rtg4.py).
What changed against rt_bake_game3.py, and which complaint it answers:
  bright rock beside its own shadow   every polygon was lit on both faces and kept the brighter: a wall turned away from the sun showed the sun on its
                  hidden back. The importer now says which side the ROAD sees (seenside.py): a polygon it sees is lit on its winding side only (one
                  seen from both sides comes twice, once per side) ; only polygons the road never sees still keep the brighter face.
  light under the rock   a texel on a polygon's edge lay in the plane of the wall standing there, and behind it where the wall leans over the road.
                  The point a texel is lit from is kept 4 cm inside its polygon ; feelers along the surface move a point that stands BEHIND a
                  road-seen wall in front of it (rtg4.c: lm4_light). Wall feet that hang up to 60 cm over the ground get a skirt in the ray scene
                  only (the game's geometry is not touched).
  pixelated shadows   6 texels a metre within 20 m of the road (it was 3) and no cap of 64 texels a side ; every texel asks the sun from 19 points
                  spread over its own square instead of one, so a slanted shadow edge is a ramp, not steps. Polygons the road never sees take at
                  most 2 texels a metre. The polygons of a material lie together on the pages (one material copy per page it reaches, not per page).
  RTG_NEAR / RTG_REACH / RTG_FAR / RTG_UNSEEN / RTG_MAXC   texels a metre near the road / up to how far / far away / for never-seen polygons / cap a side
  BAKE_STEP=k BAKE_OFF=j    light only every k-th batch (number j of each k): for timing
-> <out>.raw.npy (per texel: sun seen, sky seen, colour coming back x 4 (3), facing, the importer's own brightness rule), <out>.pack.npz"""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..')))      # tools/import/core
import sys, pickle, math, time, collections, os, ctypes, subprocess, hashlib
import numpy as np
sys.path.insert(0, os.getcwd())
import lightmap1995 as LM, retex
PATH, DUMP = sys.argv[1], sys.argv[2]; FAST = (sys.argv[3] if len(sys.argv) > 3 else 'slow') == 'fast'; t0 = time.time()
OUT = sys.argv[4] if len(sys.argv) > 4 else PATH; STEP = int(os.environ.get('BAKE_STEP', '1')); OFF = int(os.environ.get('BAKE_OFF', '0')); MODE = int(os.environ.get('RTG2_MODE', '1')); TM_ = collections.Counter()
NEAR = float(os.environ.get('RTG_NEAR', '6')); REACH = float(os.environ.get('RTG_REACH', '20')); FAR = float(os.environ.get('RTG_FAR', '0.75')); UNSEEN = float(os.environ.get('RTG_UNSEEN', '2')); MAXC = int(os.environ.get('RTG_MAXC', '256'))
INSET = 0.04; LIFT = 0.02; SKIRT_MAX = 0.60; FILL = float(os.environ.get('RTG_FILL', '0.88'))
# ---------------------------------------------------------------- the C side
HERE = os.path.dirname(os.path.abspath(__file__)); __import__('sys').path.insert(0, os.path.dirname(HERE)); from cbuild import GCC, MARCH, runtime as _runtime; SRCS = [os.path.join(HERE, f) for f in ('rays.c', 'fastlm_rays.c', 'rtg2_rays.c', 'rtg4.c')]
def _lib():
    h = hashlib.md5()
    for f in SRCS: h.update(open(f, 'rb').read())
    dll = os.path.join(HERE, 'rtg4.%s.dll' % h.hexdigest()[:8])          # one file per version of the sources: a running bake keeps its own
    if not os.path.exists(dll):
        tmp = dll + '.%d.tmp' % os.getpid(); oa = dll + '.%d.a.o' % os.getpid(); ob = dll + '.%d.b.o' % os.getpid()
        try:
            for cmd in ([GCC, '-O3', MARCH, '-fopenmp', '-c', '-o', oa, SRCS[2]],                             # rays.c with the flags rays.py gives it
                        [GCC, '-O3', MARCH, '-ffp-contract=off', '-fopenmp', '-c', '-o', ob, SRCS[3]],        # numpy's arithmetic: no fused multiply-add
                        [GCC, '-shared', '-fopenmp', '-o', tmp, oa, ob]):
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
                if r.returncode != 0: raise RuntimeError('rtg4 does not compile: ' + r.stderr[-1500:])
            try: os.replace(tmp, dll)
            except OSError: os.remove(tmp)                                # (another bake got there first and has it loaded)
        finally:
            for f in (oa, ob):
                if os.path.exists(f): os.remove(f)
    _runtime(); L = ctypes.CDLL(dll); Pv = ctypes.c_void_p; LL = ctypes.c_longlong; Dd = ctypes.c_double; Ii = ctypes.c_int
    L.rt_build.restype = Pv; L.rt_build.argtypes = [Pv, Ii]; L.rt_masks.argtypes = [Pv] * 3 + [Ii] + [Pv] * 4; L.rx_open.restype = Pv; L.rx_open.argtypes = [Pv, Ii]; L.rx_depth2.argtypes = [Pv]
    L.rx_cast.argtypes = [Pv, Ii, Pv, Pv, LL, Dd, Pv, Pv, Pv]; L.lm2_smooth.argtypes = [Pv, Ii, LL, Pv, Pv, Pv, Pv, Pv]
    L.lm4_light.argtypes = [Pv, Ii, LL, Pv, Pv, Pv, Pv, Pv, Pv, Pv, Pv, Dd, Pv, Pv, Ii, Pv, Pv, Pv, Pv, Pv, Pv, Pv, Pv, Ii, Pv, Pv, Ii, Dd, Dd, Pv, Pv, Pv, Pv, Pv]
    return L
LIB = _lib(); _d = lambda a: np.ascontiguousarray(a, np.float64); _p = lambda a: a.ctypes.data_as(ctypes.c_void_p); _i = lambda a, t: np.ascontiguousarray(a, t)
class Scene:
    """rays.Scene on this DLL: the tree of rays.c, and over its leaves the four-to-a-node tree of fastlm_rays.c for the quick walks"""
    def __init__(self, tris):
        self.tris = _d(tris).reshape(-1, 9); self.h = LIB.rt_build(_p(self.tris), len(self.tris)); self.x = None
    def masks(self, tri_mat, tri_uv, holes):
        tm = np.ascontiguousarray(tri_mat, np.int32); tu = _d(tri_uv).reshape(-1, 6); n = len(holes); w = np.zeros(n, np.int32); h = np.zeros(n, np.int32); off = np.full(n, -1, np.int64); parts = []; pos = 0
        for m, hm in enumerate(holes):
            if hm is None: continue
            hm = np.ascontiguousarray(hm, np.uint8); h[m], w[m] = hm.shape; off[m] = pos; parts.append(hm.ravel()); pos += hm.size
        bits = np.concatenate(parts) if parts else np.zeros(1, np.uint8); self.keep = [tm, tu, w, h, off, bits]
        LIB.rt_masks(self.h, _p(tm), _p(tu), n, _p(w), _p(h), _p(off), _p(bits)); self.x = LIB.rx_open(self.h, 1); self.depth = LIB.rx_depth2(self.x)
    def cast(self, org, dir, tmax=600.0):
        o = _d(org).reshape(-1, 3); d = _d(dir).reshape(-1, 3); n = len(o); hit = np.empty(n, np.int32); t = np.empty(n, np.float64); fell = ctypes.c_longlong(0)
        LIB.rx_cast(self.x, 1 if MODE else 0, _p(o), _p(d), n, float(tmax), _p(hit), _p(t), ctypes.byref(fell)); return hit, t
D = np.load(PATH + '.lm.npz'); P = D['P'].astype(float); I = D['I'].astype(float); U2 = D['U'].astype(bool); GRP = D['G'].astype(np.int64) if 'G' in D.files else np.zeros(len(P), np.int64)
import scenefile; S = scenefile.load(PATH + '.scene', numpy=True); SUN = np.asarray(S['sun'], float); SUN /= np.linalg.norm(SUN); PAGE = LM.PAGE
G = pickle.load(open(DUMP, 'rb')); rd = G['rd']; origin = G.get('origin', {}); lab = {k: v[0] for k, v in retex.labels().items()}
names = []; seen = {}
for mat, sec, Pf, Uf in ((fc[0], fc[1], fc[2], fc[3]) for fc in G['faces'] + G['sky'] + G['extra']):
    if str(sec) == 'sea' or len(Pf) < 3: continue
    m0 = str(mat).split('|')[0]
    if m0 not in seen: seen[m0] = len(names); names.append(m0)
alb0 = np.asarray(S['albedo_rgb'], float); holes0 = list(S['holes'])
# WHAT THE RAYS CAN HIT: the polygons as the game draws them (a four-corner polygon is two triangles along corners 0 - 2). ONE = the road sees this
# polygon on its winding side only (seenside.py left its key bare): something standing behind it is hidden.
T_ = []; TU_ = []; TM_0 = []; ONE_ = []; FEDGE = []
for fi, fc in enumerate(G['faces'] + G['sky'] + G['extra']):
    if str(fc[1]) == 'sea' or len(fc[2]) < 3: continue
    A_ = np.asarray(fc[2], float); B_ = np.asarray(fc[3], float); key_ = str(fc[0]); m_ = seen[key_.split('|')[0]]; one_ = ('|' not in key_) and not key_.endswith('_t')
    for i0, i1, i2 in (((0, 1, 2), (0, 2, 3)) if len(A_) >= 4 else ((0, 1, 2),)): T_.append((A_[i0], A_[i1], A_[i2])); TU_.append((B_[i0], B_[i1], B_[i2])); TM_0.append(m_); ONE_.append(one_)
    FEDGE.append((A_, m_, key_.split('|')[0].endswith('_t')))
T = np.array(T_, float); TU = np.array(TU_, float); TM = np.array(TM_0, np.int64); ONE0 = np.array(ONE_, bool); nscene_ = int((np.asarray(S['mat']) != len(alb0) - 1).sum())
assert len(T) == nscene_, 'the dump (%d triangles) is not the scene the build saved (%d)' % (len(T), nscene_)
assert len(names) == len(alb0) - 1, 'materials of the scene (%d) and of the dump (%d) differ' % (len(alb0) - 1, len(names))
cls = [lab.get(origin.get(n, n), '') for n in names] + ['sr3road']; TREE = ('crown', 'trunk', 'bare', 'tree'); tcls = np.array(cls, object)[TM]
is_tree = np.isin(tcls, TREE); is_lamp = tcls == 'lamp'
print('scene %d triangles, cut as the game draws them: tree boards %d and lamp boards %d (replaced by solids), kept %d ; seen by the road on one side only %d' % (len(T), is_tree.sum(), is_lamp.sum(), (~is_tree & ~is_lamp).sum(), int(ONE0.sum())), flush=True)
# ---------------------------------------------------------------- trees and lamps as solids
def clusters(idx):
    par = {}
    def find(x):
        while par.setdefault(x, x) != x: par[x] = par[par[x]]; x = par[x]
        return x
    K = np.round(T[idx] * 20).astype(np.int64)                         # 5 cm
    for t in range(len(idx)):
        ks = [tuple(K[t, c]) for c in range(3)]
        for k in ks[1:]: par[find(k)] = find(ks[0])
    out = collections.defaultdict(list)
    for t, i in enumerate(idx): out[find(tuple(K[t, 0]))].append(i)
    return list(out.values())
def cylinder(x, z, y0, y1, r, n=8):
    out = []
    for k in range(n):
        a0 = 2 * math.pi * k / n; a1 = 2 * math.pi * (k + 1) / n; p = lambda a, y: (x + r * math.cos(a), y, z + r * math.sin(a))
        out += [(p(a0, y0), p(a1, y0), p(a1, y1)), (p(a0, y0), p(a1, y1), p(a0, y1))]
    return out
def ball(centre, rh, rv):
    t = (1 + 5 ** 0.5) / 2; V = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    V = [np.array(v, float) / np.linalg.norm(v) for v in V]; tris = [(V[a], V[b], V[c]) for a, b, c in F]; out = []
    for a, b, c in tris:                                               # one subdivision: 80 faces
        ab, bc, ca = [(x + y) / np.linalg.norm(x + y) for x, y in ((a, b), (b, c), (c, a))]; out += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
    sc_ = np.array([rh, rv, rh]); return [tuple(np.array(centre, float) + v * sc_ for v in tr) for tr in out]
solid = []; canopy = []; ntree = nlamp = 0; TREES = []
for cl in clusters(np.where(is_tree)[0]):
    V = T[cl].reshape(-1, 3); c = tcls[cl]; tr = T[np.array(cl)[c == 'trunk']].reshape(-1, 3); cr = T[np.array(cl)[c != 'trunk']].reshape(-1, 3)
    ax = (tr if len(tr) else V)[:, [0, 2]].mean(0); y0 = V[:, 1].min(); y1 = V[:, 1].max()
    if y1 - y0 < 1.0: continue
    if len(cr):
        cy0 = cr[:, 1].min() if len(tr) else y0 + 0.45 * (y1 - y0); rh = max(0.6, 0.8 * float(np.percentile(np.hypot(cr[:, 0] - ax[0], cr[:, 2] - ax[1]), 90))); cc = (ax[0], (cy0 + y1) / 2, ax[1])
        canopy += ball(cc, rh, max(0.6, (y1 - cy0) / 2)); solid += cylinder(ax[0], ax[1], y0, cc[1], 0.22); TREES.append((cc[0], cc[1], cc[2], rh, max(0.6, (y1 - cy0) / 2), y0))
    else: solid += cylinder(ax[0], ax[1], y0, y1, 0.22)
    ntree += 1
for cl in clusters(np.where(is_lamp)[0]):
    V = T[cl].reshape(-1, 3); solid += cylinder(V[:, 0].mean(), V[:, 2].mean(), V[:, 1].min(), V[:, 1].max(), 0.18, 8); nlamp += 1
print('solids for the rays: %d trees (%d canopy faces, 25%% of rays pass), %d lamp posts' % (ntree, len(canopy), nlamp), flush=True)
keep = ~is_tree & ~is_lamp; lo = T[keep].reshape(-1, 3).min(0); hi = T[keep].reshape(-1, 3).max(0); ysea = -0.6
SEA = [((lo[0] - 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, hi[2] + 4000)), ((lo[0] - 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, hi[2] + 4000), (lo[0] - 4000, ysea, hi[2] + 4000))]
nm = len(alb0); M_SOLID, M_CAN, M_SEA = nm, nm + 1, nm + 2; rng = np.random.RandomState(7)
alb = np.concatenate([np.clip(alb0 * 8.0, 0.0, 0.85), [[0.25, 0.2, 0.15], [0.12, 0.3, 0.08], [0.03, 0.12, 0.35]]]); holes = holes0 + [None, rng.rand(64, 64) < 0.25, None]
# ---------------------------------------------------------------- skirts under wall feet that hang over the ground (ray scene only)
# A standing opaque polygon whose lower edge belongs to no other polygon and has ground up to SKIRT_MAX under both its ends lets the sun through
# under it: a lit line along the foot of the wall, in the wall's shadow. The gap is closed for the rays; nothing is added to the game.
base = Scene(np.concatenate([T[keep], np.array(SEA, float)])); base.masks(np.concatenate([TM[keep], [M_SEA, M_SEA]]).astype(np.int32), np.concatenate([TU[keep], np.zeros((2, 3, 2))]), holes)
ecount = collections.Counter(); eown = {}
rk = lambda p: (int(round(p[0] * 200)), int(round(p[1] * 200)), int(round(p[2] * 200)))
for A_, m_, cut_ in FEDGE:
    if cut_ or cls[m_] in TREE or cls[m_] == 'lamp': continue
    k_ = len(A_) if (len(A_) == 3 or tuple(A_[2]) != tuple(A_[3])) else 3; ks_ = [rk(A_[i]) for i in range(k_)]
    for i in range(k_):
        a, b = ks_[i], ks_[(i + 1) % k_]
        if a == b: continue
        e = (a, b) if a < b else (b, a); ecount[e] += 1; eown[e] = (A_[i], A_[(i + 1) % k_], A_[:k_], m_)
cand = []
for e, cnt in ecount.items():
    if cnt != 1: continue
    p0, p1, poly, m_ = eown[e]; n_ = np.cross(poly[1] - poly[0], poly[2] - poly[0]); ln_ = np.linalg.norm(n_)
    if ln_ < 1e-9 or abs(n_[1] / ln_) > 0.6 or np.linalg.norm(p1 - p0) < 0.05: continue
    if max(p0[1], p1[1]) > poly[:, 1].mean() - 1e-6: continue          # not the lower edge
    cand.append((p0, p1, m_))
skirt = []; skm = []; sklen = 0.0; gaps = []
if cand:
    O = np.array([q for p0, p1, m_ in cand for q in (p0, p1, (p0 + p1) / 2)], float) - [0.0, 0.01, 0.0]; h_, t_ = base.cast(O, np.tile([0.0, -1.0, 0.0], (len(O), 1)), SKIRT_MAX + 0.5); t_ = np.where(h_ >= 0, t_ + 0.01, 1e9).reshape(-1, 3)
    for (p0, p1, m_), g in zip(cand, t_):
        if not (g.max() <= SKIRT_MAX and g.max() >= 0.03): continue
        q0 = p0 - [0.0, g[0] + 0.05, 0.0]; q1 = p1 - [0.0, g[1] + 0.05, 0.0]; skirt += [(p0, p1, q1), (p0, q1, q0)]; skm += [m_, m_]; sklen += float(np.linalg.norm(p1 - p0)); gaps.append(float(g.max()))
print('skirts for the rays under hanging wall feet: %d free lower edges of standing polygons looked at, %d have ground or sea within %.2f m under them (%.0f m of wall ; gap under 0.2 m: %d, 0.2 - 0.5 m: %d, over 0.5 m: %d)'
      % (len(cand), len(gaps), SKIRT_MAX, sklen, sum(1 for g_ in gaps if g_ < 0.2), sum(1 for g_ in gaps if 0.2 <= g_ < 0.5), sum(1 for g_ in gaps if g_ >= 0.5)), flush=True)
del base
# ---------------------------------------------------------------- buildings drawn with cut-out pictures are closed for the rays
# The village church tower is three walls and three roof faces: the fourth wall and roof face were never modelled (not seen from the road). Its walls
# now have an inside of their own (lm_cutouts, written once per side); open as modelled, the sun would fall into it through the missing side. Where
# a side of the walls' box has no wall a blocker stands, and a lid lies on the walls: the inside gets what comes through the openings of its own
# pictures and nothing else. Ray scene only.
CUTP = PATH + '.cutouts.json'; nclose = 0; nbuild = 0
if os.path.exists(CUTP):
    import json
    tiles_ = set(json.load(open(CUTP))); B_ = [A_[:3] if (len(A_) == 4 and tuple(A_[2]) == tuple(A_[3])) else A_ for A_, m_, cut_ in FEDGE if names[m_] in tiles_]; par_ = {}
    def find_(x):
        while par_.setdefault(x, x) != x: par_[x] = par_[par_[x]]; x = par_[x]
        return x
    for A_ in B_:
        ks_ = [rk(p_) for p_ in A_]
        for k_ in ks_[1:]: par_[find_(k_)] = find_(ks_[0])
    grp_ = collections.defaultdict(list)
    for A_ in B_: grp_[find_(rk(A_[0]))].append(A_)
    for g_ in grp_.values():
        walls_ = []
        for A_ in g_:
            n_ = np.cross(A_[1] - A_[0], A_[2] - A_[0]); l_ = np.linalg.norm(n_)
            if l_ > 1e-9 and abs(n_[1] / l_) < 0.3: walls_.append((A_, n_ / l_))
        if len(walls_) < 2 or any(max(abs(n_[0]), abs(n_[2])) < 0.996 for A_, n_ in walls_): continue      # (only buildings whose walls stand along x and z)
        W_ = np.concatenate([A_ for A_, n_ in walls_]); x0_, y0_, z0_ = W_.min(0); x1_, y1_, z1_ = W_.max(0); nbuild += 1
        has_ = lambda ax, val: any(float(np.abs(A_[:, ax] - val).max()) < 0.3 for A_, n_ in walls_)
        quads_ = [[(x0_, y1_, z0_), (x1_, y1_, z0_), (x1_, y1_, z1_), (x0_, y1_, z1_)]]                       # the lid
        if not has_(0, x0_): quads_.append([(x0_, y0_, z0_), (x0_, y0_, z1_), (x0_, y1_, z1_), (x0_, y1_, z0_)])
        if not has_(0, x1_): quads_.append([(x1_, y0_, z0_), (x1_, y0_, z1_), (x1_, y1_, z1_), (x1_, y1_, z0_)])
        if not has_(2, z0_): quads_.append([(x0_, y0_, z0_), (x1_, y0_, z0_), (x1_, y1_, z0_), (x0_, y1_, z0_)])
        if not has_(2, z1_): quads_.append([(x0_, y0_, z1_), (x1_, y0_, z1_), (x1_, y1_, z1_), (x0_, y1_, z1_)])
        for q_ in quads_: q_ = np.array(q_, float); skirt += [(q_[0], q_[1], q_[2]), (q_[0], q_[2], q_[3])]; skm += [M_SOLID, M_SOLID]; nclose += 1
    print('buildings of cut-out pictures closed for the rays: %d (%d blockers: a lid each, and a wall where a side has none)' % (nbuild, nclose), flush=True)
ns_ = len(skirt)
TA = np.concatenate([T[keep], np.array(solid, float).reshape(-1, 3, 3), np.array(canopy, float).reshape(-1, 3, 3), np.array(SEA, float), np.array(skirt, float).reshape(-1, 3, 3)])
TMA = np.concatenate([TM[keep], np.full(len(solid), M_SOLID), np.full(len(canopy), M_CAN), np.full(2, M_SEA), np.array(skm, np.int64)]).astype(np.int32)
UVA = np.concatenate([TU[keep], np.zeros((len(solid), 3, 2)), rng.rand(len(canopy), 3, 2), np.zeros((2, 3, 2)), np.zeros((ns_, 3, 2))])
TONE = np.concatenate([ONE0[keep], np.zeros(len(solid) + len(canopy) + 2 + ns_, bool)]).astype(np.uint8)
TN = np.cross(TA[:, 1] - TA[:, 0], TA[:, 2] - TA[:, 0]); TN /= np.maximum(np.linalg.norm(TN, axis=1), 1e-12)[:, None]
sc = Scene(TA); sc.masks(TMA, UVA, holes)
if sc.depth > 150 and MODE: print('the quick walks\' tree is %d deep (their stack is sized for 150): every ray goes through cast_one' % sc.depth, flush=True); MODE = 0
print('rays: mode %d, tree for the quick walks %d deep ; scene ready after %.0f s' % (MODE, sc.depth, time.time() - t0), flush=True)
sh = np.array([SUN[0], 0.0, SUN[2]]); lh = np.linalg.norm(sh); design = (sh / lh * 0.7071 + np.array([0.0, 0.7071, 0.0])) if lh > 1e-6 else np.array([0.0, 1.0, 0.0])
def frame(n):
    ax = np.where((np.abs(n[:, 1]) < 0.9)[:, None], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]); t = np.cross(n, ax); t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]; return t, np.cross(n, t)
# ---------------------------------------------------------------- the cars' pages
# The game lights a car by ambient x (1 - red) + sun x green of the road page's first picture, laid over the car from above (pixel shader with the
# sampler TexStaticShadow; SEGA's own pages: green 255 / red 0 in the open, green 0 in shadow, red up to 255 where the sky is shut out - tunnels).
# For every page the importer listed (course setting car_shade_dump): a picture of CAR_RES x CAR_RES; a texel within CAR_REACH of the road's middle
# asks the sun (7 rays over its disc) and the sky (24 rays) from CAR_UP above the road there; the rest is open sun. The outermost texels stay
# open sun: a car that is given a page it does not stand on reads that, which is what every car read before.
CAR_RES = int(os.environ.get('RTG_CAR_RES', '512')); CAR_REACH = 14.0; CAR_UP = 0.6; CARP = PATH + '.carpages.json'
if os.path.exists(CARP):
    import json
    tq = time.time(); pgs = np.array(json.load(open(CARP))['pages'], float); cen3 = np.asarray(rd['V'][:, rd['hw']], float); imgs = np.zeros((len(pgs), CAR_RES, CAR_RES, 3), np.uint8); imgs[..., 1] = 255
    stc, sbc = frame(SUN[None]); SDC = [SUN] + [SUN + math.tan(math.radians(1.5)) * (math.cos(a_) * stc[0] + math.sin(a_) * sbc[0]) for a_ in np.arange(6) * math.pi / 3]; SDC = [d_ / np.linalg.norm(d_) for d_ in SDC]
    KC = 24; HC = np.array([(math.sqrt((i + 0.5) / KC) * math.cos(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / KC)), math.sqrt((i + 0.5) / KC) * math.sin(i * 2.399963)) for i in range(KC)])      # about straight up, more rays near the top
    nlit = 0; nsh = 0; ntx = 0
    for k, (u0, v0, su, sv) in enumerate(pgs):
        uu = (np.arange(CAR_RES) + 0.5) / CAR_RES; X = (uu - u0) / su; Z = (uu - v0) / sv; gx, gz = np.meshgrid(X, Z)                 # row = v (z), column = u (x)
        sel = np.nonzero((cen3[:, 0] > X.min() - 20) & (cen3[:, 0] < X.max() + 20) & (cen3[:, 2] > Z.min() - 20) & (cen3[:, 2] < Z.max() + 20))[0]
        if not len(sel): continue
        pts = np.c_[gx.ravel(), gz.ravel()]; dmin = np.full(len(pts), 1e9); near = np.zeros(len(pts), np.int64); C2 = cen3[sel][:, [0, 2]]
        for s0 in range(0, len(pts), 8000):
            d2 = ((pts[s0:s0 + 8000, None] - C2[None]) ** 2).sum(2); near[s0:s0 + 8000] = d2.argmin(1); dmin[s0:s0 + 8000] = np.sqrt(d2.min(1))
        m = np.nonzero(dmin < CAR_REACH)[0]
        if not len(m): continue
        P3 = np.c_[pts[m, 0], cen3[sel][near[m], 1] + CAR_UP, pts[m, 1]]; opn = np.zeros(len(m)); skyv = np.zeros(len(m))
        for d_ in SDC: h_, t_ = sc.cast(P3 + d_ * 0.05, np.tile(d_, (len(m), 1)), 1e9); opn += h_ < 0
        for d_ in HC: h_, t_ = sc.cast(P3 + d_ * 0.05, np.tile(d_, (len(m), 1)), 1e9); skyv += h_ < 0
        Gm = np.ones(CAR_RES * CAR_RES, np.float32); Rm = np.zeros(CAR_RES * CAR_RES, np.float32); Gm[m] = opn / len(SDC); Rm[m] = 1.0 - skyv / KC
        def blur(a_):
            a_ = a_.reshape(CAR_RES, CAR_RES); q_ = np.pad(a_, 1, mode='edge'); return sum(q_[1 + dy:1 + dy + CAR_RES, 1 + dx:1 + dx + CAR_RES] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
        Gi = blur(Gm); Ri = blur(Rm); Gi[:4] = 1; Gi[-4:] = 1; Gi[:, :4] = 1; Gi[:, -4:] = 1; Ri[:4] = 0; Ri[-4:] = 0; Ri[:, :4] = 0; Ri[:, -4:] = 0      # (four texels = one whole compression block, so the edge is exactly open sun)
        imgs[k, ..., 0] = np.round(np.clip(Ri, 0, 1) * 255); imgs[k, ..., 1] = np.round(np.clip(Gi, 0, 1) * 255); ntx += len(m); nsh += int((opn < 0.5 * len(SDC)).sum())
    np.savez_compressed(OUT + '.carshade.npz', pages=imgs, map=pgs)
    print('cars: %d road pages of %d x %d ; %.1f million texels within %.0f m of the road asked, %.0f%% of them in shadow ; %.0f s -> %s.carshade.npz' % (len(pgs), CAR_RES, CAR_RES, ntx / 1e6, CAR_REACH, 100.0 * nsh / max(ntx, 1), time.time() - tq, OUT), flush=True)
    if os.environ.get('RTG_CARS_ONLY'): raise SystemExit(0)
else: print('cars: no page list beside the collected polygons (%s): the cars keep open sun everywhere' % CARP, flush=True)
# ---------------------------------------------------------------- which face is lit
# U (the importer's 'unsure' flag, material key '|4') = the road never sees this polygon: both faces are lit and the brighter kept, as rt_bake_game3
# did for every polygon. All others are lit on their WINDING side: seenside.py wound them towards the road (a polygon seen from both sides is in
# the list twice, once per winding, each copy drawn single-sided with its own texels).
sea_poly = (P[:, :, 1].max(1) < -0.3) & (P[:, :, 1].min(1) > -0.7)
print('lit side: %d polygons on their winding side (the side the road sees), %d never seen from the road: both faces lit, the brighter kept ; sea polygons (no baked light) %d' % (int((~U2).sum()), int(U2.sum()), int(sea_poly.sum())), flush=True)
# ---------------------------------------------------------------- the pages
def pack(P, centre, grp, unsure):
    """-> page, x0, y0, nu, nv per polygon. Texels a metre: NEAR within REACH of the road (the nearest of a polygon's corners and middle counts),
    thinning with distance to FAR ; polygons the road never sees at most UNSEEN. Shelves, the polygons of one material together, tallest first."""
    e = lambda a, b: np.linalg.norm(P[:, a] - P[:, b], axis=1); lu = np.maximum(e(1, 0), e(2, 3)); lv = np.maximum(e(3, 0), e(2, 1)); cen = np.asarray(centre, float)[::2]; d = np.full(len(P), 1e9)
    for X in [P.mean(1)] + [P[:, k] for k in range(4)]:
        for s in range(0, len(P), 4000): d[s:s + 4000] = np.minimum(d[s:s + 4000], np.sqrt(((X[s:s + 4000, None][:, :, [0, 2]] - cen[None]) ** 2).sum(2).min(1)))
    dens = np.where(d < REACH, NEAR, np.maximum(NEAR * REACH / np.maximum(d, 1e-6), FAR)); dens = np.where(unsure, np.minimum(dens, UNSEEN), dens)
    nu = np.clip(np.ceil(lu * dens).astype(int) + 1, 2, MAXC); nv = np.clip(np.ceil(lv * dens).astype(int) + 1, 2, MAXC); w = (nu + 3) // 4 * 4; h = (nv + 3) // 4 * 4
    area = (w * h).astype(np.int64); cap = int(PAGE * PAGE * FILL); garea = np.bincount(grp, weights=area).astype(np.int64); bins = []; left = []      # bins: polygons per page ; left: room in it
    for g in np.argsort(-garea, kind='stable'):
        if not garea[g]: continue
        ii = np.nonzero(grp == g)[0]; ii = ii[np.lexsort((-w[ii], -h[ii]))]
        if garea[g] <= cap:
            k = next((k for k in range(len(bins)) if left[k] >= garea[g]), None)                     # first page with room for the whole material
            if k is None: bins.append([]); left.append(cap); k = len(bins) - 1
            bins[k] += ii.tolist(); left[k] -= int(garea[g]); continue
        k = None                                                                                      # larger than a page: over as many as it needs
        for i in ii.tolist():
            if k is None or left[k] < area[i]: bins.append([]); left.append(cap); k = len(bins) - 1
            bins[k].append(i); left[k] -= int(area[i])
    page = np.zeros(len(P), np.int32); x0 = np.zeros(len(P), np.int32); y0 = np.zeros(len(P), np.int32); over = []; npage = 0
    def shelf(idx, pg):
        idx = np.array(idx, np.int64); idx = idx[np.lexsort((-w[idx], -h[idx]))]; cx = cy = 0; rowh = 0; out = []
        for i in idx.tolist():
            if cx + w[i] > PAGE: cx = 0; cy += rowh; rowh = 0
            if cy + h[i] > PAGE: out.append(i); continue
            page[i] = pg; x0[i] = cx; y0[i] = cy; cx += w[i]; rowh = max(rowh, h[i])
        return out
    for bn in bins:
        if not bn: continue
        npage += 1; over += shelf(bn, npage)
    while over: npage += 1; over = shelf(over, npage)                                                 # what did not fit its page (few): pages of their own
    return page, x0, y0, nu, nv, d
page, x0, y0, nu, nv, droad = pack(P, S['centre'], GRP, U2); npg = int(page.max()); ntot = int((nu * nv).sum())
combos = len(set(zip(GRP.tolist(), page.tolist()))); assert page.min() >= 1; fill_ = float((((nu + 3) // 4 * 4) * ((nv + 3) // 4 * 4)).sum()) / (npg * PAGE * PAGE)
print('texels %.1f million on %d pages, %.0f%% of them used (%s) ; %.0f texels a metre within %.0f m of the road ; material x page combinations %d (materials %d)' % (ntot / 1e6, npg, 100 * fill_, 'FAST' if FAST else 'slow', NEAR, REACH, combos, len(np.unique(GRP))), flush=True)
if os.environ.get('RTG_PACK_ONLY'): raise SystemExit(0)
# ---------------------------------------------------------------- the light
SUN_DEG = 3.0; KS = 16 if FAST else 32; TURNS = 1 if FAST else 3
st, sb = frame(SUN[None]); rad = math.radians(SUN_DEG / 2); SD = [SUN]
for ring, cnt in (((1.0, 6),) if FAST else ((0.5, 6), (1.0, 12))):
    for k in range(cnt):
        a = 2 * math.pi * (k + 0.5 * (ring < 1)) / cnt; d = SUN + math.tan(rad * ring) * (math.cos(a) * st[0] + math.sin(a) * sb[0]); SD.append(d / np.linalg.norm(d))
SD = np.array(SD); HEMI = np.array([(math.sqrt((i + 0.5) / KS) * math.cos(i * 2.399963), math.sqrt((i + 0.5) / KS) * math.sin(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / KS))) for i in range(KS)])
FOOT = np.array([(0.0, 0.0)] + [((0.5 + j * 0.7548776662466927) % 1.0 - 0.5, (0.5 + j * 0.5698402909980532) % 1.0 - 0.5) for j in range(1, len(SD))])      # where in the texel's square each sun ray starts (an even spread)
TNS = _d(TN @ SUN); TND = _d(TN @ design); TNc = _d(TN); ALBc = _d(alb); SDc = _d(SD); HEMIc = _d(HEMI); SUNc = _d(SUN); FOOTc = _d(FOOT); STATS = np.zeros(5, np.int64)
tri_p = np.linalg.norm(P[:, 2] - P[:, 3], axis=1) < 1e-9; PQ = _d(P.reshape(-1, 12)); PNU = _i(nu, np.int32); PNV = _i(nv, np.int32); PTRI = _i(tri_p, np.uint8)
e_ = lambda a, b: np.linalg.norm(P[:, a] - P[:, b], axis=1); PM = _d(np.stack([np.minimum(INSET / np.maximum(np.maximum(e_(1, 0), e_(2, 3)), 1e-6), 0.2), np.minimum(INSET / np.maximum(np.maximum(e_(3, 0), e_(2, 1)), 1e-6), 0.2)], 1))
def light(pi, iu, iv, k0, side):
    """lm4_light (rtg4.c): -> sun seen, sky seen, colour coming back, the normal at the point used"""
    m = len(pi); pi = _i(pi, np.int32); iu = _i(iu, np.int32); iv = _i(iv, np.int32); CA = np.empty((m, TURNS)); SA = np.empty((m, TURNS)); st_ = np.zeros(5, np.int64)
    for turn in range(TURNS):
        ang = ((k0 + turn / TURNS) * 0.618034) % 1.0 * 2 * math.pi; CA[:, turn] = np.cos(ang); SA[:, turn] = np.sin(ang)
    V = np.empty(m); sky = np.empty(m); back = np.empty((m, 3)); NO = np.empty((m, 3))
    LIB.lm4_light(sc.x, MODE, m, _p(pi), _p(iu), _p(iv), _p(PQ), _p(PNU), _p(PNV), _p(PTRI), _p(PM), float(side), _p(CA), _p(SA), TURNS, _p(TNc), _p(TNS), _p(TND), _p(TMA), _p(TONE), _p(ALBc),
                  _p(SUNc), _p(SDc), len(SDc), _p(FOOTc), _p(HEMIc), KS, LIFT, 1.0, _p(V), _p(sky), _p(back), _p(NO), _p(st_))
    STATS[:] += st_; return V, sky, back, NO
def facing(n):
    ns = n @ SUN; face = np.clip((ns - 0.02) / 0.13, 0.0, 1.0); face = face * face * (3 - 2 * face); return np.clip((n @ design + 0.2) / 0.907, 0.0, 1.0) * face
RAW = np.zeros((npg + 1, PAGE, PAGE, 7), np.uint8); RAW[..., 0] = 255; RAW[..., 1] = 255; RAW[..., 5] = 255; RAW[..., 6] = 255; ntex = 0; order = np.argsort(page, kind='stable'); t1 = time.time()
csum = np.cumsum((nu * nv)[order]); cuts = [0]
while cuts[-1] < len(order): cuts.append(max(int(np.searchsorted(csum, csum[cuts[-1]] - (nu * nv)[order[cuts[-1]]] + 250000, side='right')), cuts[-1] + 1))
TM_.clear(); nlit = 0
for bi in range(len(cuts) - 1):
    if bi % STEP != OFF: ntex += int((nu * nv)[order[cuts[bi]:cuts[bi + 1]]].sum()); continue
    q0 = time.perf_counter(); ii = order[cuts[bi]:cuts[bi + 1]]; cnt = nu[ii] * nv[ii]; tot_ = int(cnt.sum()); f = np.repeat(np.arange(len(ii)), cnt); stt = np.repeat(np.cumsum(cnt) - cnt, cnt); loc = np.arange(tot_) - stt
    iu = loc % nu[ii][f]; iv = loc // nu[ii][f]; a = iu / (nu[ii][f] - 1); b = iv / (nv[ii][f] - 1); pi = ii[f]
    Ir = I[ii][f]; ir = (1 - a) * (1 - b) * Ir[:, 0] + a * (1 - b) * Ir[:, 1] + a * b * Ir[:, 2] + (1 - a) * b * Ir[:, 3]
    k0 = (np.arange(tot_) + ntex).astype(float); TM_['texel maths'] += time.perf_counter() - q0; q0 = time.perf_counter(); V, A, B, NO = light(pi, iu, iv, k0, 1.0); TM_['light, winding side'] += time.perf_counter() - q0; TM_['texels'] += tot_; Fc = facing(NO); u = U2[ii][f]
    if u.any():
        q0 = time.perf_counter(); V2, A2, B2, NO2 = light(pi[u], iu[u], iv[u], k0[u], -1.0); TM_['light, other side'] += time.perf_counter() - q0; TM_['texels other side'] += int(u.sum()); F2 = facing(NO2)
        bet = (0.66 * V2 * F2 + 0.22 * A2 + B2.mean(1)) > (0.66 * V[u] * Fc[u] + 0.22 * A[u] + B[u].mean(1))
        for arr, alt in ((V, V2), (A, A2), (Fc, F2)): tmp = arr[u]; tmp[bet] = alt[bet]; arr[u] = tmp
        tmp = B[u]; tmp[bet] = B2[bet]; B[u] = tmp
    q0 = time.perf_counter(); sp = sea_poly[ii][f]; V[sp] = 1.0; A[sp] = 1.0; B[sp] = 0.0; Fc[sp] = 1.0
    RAW[page[ii][f], y0[ii][f] + iv, x0[ii][f] + iu] = np.round(np.clip(np.c_[V, A, B * 4.0, Fc, ir], 0, 1) * 255).astype(np.uint8); ntex += tot_; nlit += tot_; TM_['store'] += time.perf_counter() - q0
    if bi % 20 == 0: print('  %d%% (%.1f of %.1f million texels), %.0f s' % (100 * ntex // ntot, ntex / 1e6, ntot / 1e6, time.time() - t1), flush=True)
t2 = time.time(); RAW = np.ascontiguousarray(RAW); pg_, x0_, y0_, nu_, nv_ = _i(page, np.int32), _i(x0, np.int32), _i(y0, np.int32), _i(nu, np.int64), _i(nv, np.int64)
LIB.lm2_smooth(_p(RAW), PAGE, len(P), _p(pg_), _p(x0_), _p(y0_), _p(nu_), _p(nv_))             # the 3 x 3 smoothing of sky and colour in every polygon's rectangle and its growth to whole 4 x 4 blocks (rtg2.c)
t3 = time.time(); np.save(OUT + '.raw.npy', RAW[1:]); np.savez(OUT + '.pack.npz', page=page, x0=x0, y0=y0, nu=nu, nv=nv, droad=droad, trees=np.array(TREES, float).reshape(-1, 6))
print('RTG4 %d polygons, %.1f million texels, %d pages ; rays %.0f s, all %.0f s' % (len(P), ntex / 1e6, npg, time.time() - t1, time.time() - t0))
print('TIMES lit texels %.2f million ; batches %.1f s ; smoothing %.1f s ; save %.1f s ; %s ; rays %.0f million ; texels moved in front of a wall they stood behind %d ; texels with something crossing their square %d'
      % (nlit / 1e6, t2 - t1, t3 - t2, time.time() - t3, {k: round(v, 1) for k, v in TM_.items()}, STATS[0] / 1e6, STATS[3], STATS[4]))
