"""rt_bake_game2_fast.py = rt_bake_game2.py with its rays cast from C loops (rtg2.c, rtg2_rays.c; compiled with gcc on first use into rtg2.<hash>.dll
beside this file; needs rays.c, fastlm_rays.c, rtg2_rays.c, rtg2.c there). The same decisions and the same formulas: see the top of rtg2.c.
Measured 2026-10-13, 16 threads, slow: 79 s against about 590 s, raw.npy / pack.npz / side.npz the bytes of rt_bake_game2.py (compare.py).
    python rt_bake_game2_fast.py <path> <faces.pkl> [fast|slow] [<out path>]        (run from the importer folder: lightmap1995, retex)
    RTG2_MODE=1 (default) nearest hits through the quick walks of fastlm_rays.c (the answers of cast_one) ; 0 every ray through cast_one of rays.c ;
                2 = 1 + "is anything hit 0.11 m out or farther?" asked first for the sun rays (measured: the same bytes, no faster - left off)
    BAKE_STEP=k BAKE_OFF=j    light only every k-th batch of 250,000 texels (number j of each k): for timing and comparing
----- the text of rt_bake_game2.py:
RT bake for the GAME, second version (after the owner's first drive, 2026-10-13).   python rt_bake_game2.py <path> <faces.pkl> [fast|slow]
<path> = what an importer build collected (lm_collect); faces.pkl = the same build's GAPFILL_DUMP (names and classes of what stands where).
What changed against rt_bake_game.py, and which complaint it answers:
  ghost shadows   the importer's own SR3 road mesh (hidden in game, 224,000 triangles a few cm over / under the 1995 road) was in the ray scene:
                  taken out. A ray that starts 2 cm off a face and at once meets a layer lying nearly parallel to that face (within 10 cm) goes
                  on through it: coplanar leftovers no longer shadow, while a wall standing ON the face still does.
  dark polygons   which side of a polygon is lit is decided here, not taken from the build: the side the ROAD sees (eyes every 4 m, 1.1 and 3.2 m up,
                  400 m reach), else the side open to the sky WITH the sea blocking, else the build's; seen from both -> the better side.
  dark sea        the sea sheet takes no baked light at all (white = as the game draws it).
  trees / lamps   their boards are not in the ray scene. Each tree is a trunk cylinder + a canopy ball that lets 25% of the rays through,
                  each lamp post a thin cylinder: they cast shadows, and take no baked light themselves (the importer flat-lights them).
  fast | slow     fast = 7 sun rays, 16 sky rays (about a fifth of the time): for trying things. slow = 19 / 96: what goes into the game.
-> <path>.raw.npy, <path>.pack.npz, <path>.side.npz"""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..')))      # tools/import/core
import sys, pickle, math, time, collections, os, ctypes, subprocess, hashlib
import numpy as np
sys.path.insert(0, os.getcwd())
import lightmap1995 as LM, retex
PATH, DUMP = sys.argv[1], sys.argv[2]; FAST = (sys.argv[3] if len(sys.argv) > 3 else 'slow') == 'fast'; t0 = time.time()
OUT = sys.argv[4] if len(sys.argv) > 4 else PATH; STEP = int(os.environ.get('BAKE_STEP', '1')); OFF = int(os.environ.get('BAKE_OFF', '0')); MODE = int(os.environ.get('RTG2_MODE', '1')); TM_ = collections.Counter()
# ---------------------------------------------------------------- the C side
HERE = os.path.dirname(os.path.abspath(__file__)); __import__('sys').path.insert(0, os.path.dirname(HERE)); from cbuild import GCC, MARCH, runtime as _runtime; SRCS = [os.path.join(HERE, f) for f in ('rays.c', 'fastlm_rays.c', 'rtg2_rays.c', 'rtg2.c')]
def _lib():
    h = hashlib.md5()
    for f in SRCS: h.update(open(f, 'rb').read())
    dll = os.path.join(HERE, 'rtg2.%s.dll' % h.hexdigest()[:8])          # one file per version of the sources: a running bake keeps its own
    if not os.path.exists(dll):
        tmp = dll + '.%d.tmp' % os.getpid(); oa = dll + '.%d.a.o' % os.getpid(); ob = dll + '.%d.b.o' % os.getpid()
        try:
            for cmd in ([GCC, '-O3', MARCH, '-fopenmp', '-c', '-o', oa, SRCS[2]],                             # rays.c with the flags rays.py gives it
                        [GCC, '-O3', MARCH, '-ffp-contract=off', '-fopenmp', '-c', '-o', ob, SRCS[3]],        # numpy's arithmetic: no fused multiply-add
                        [GCC, '-shared', '-fopenmp', '-o', tmp, oa, ob]):
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
                if r.returncode != 0: raise RuntimeError('rtg2 does not compile: ' + r.stderr[-1500:])
            try: os.replace(tmp, dll)
            except OSError: os.remove(tmp)                                # (another bake got there first and has it loaded)
        finally:
            for f in (oa, ob):
                if os.path.exists(f): os.remove(f)
    _runtime(); L = ctypes.CDLL(dll); Pv = ctypes.c_void_p; LL = ctypes.c_longlong; Dd = ctypes.c_double; Ii = ctypes.c_int
    L.rt_build.restype = Pv; L.rt_build.argtypes = [Pv, Ii]; L.rt_masks.argtypes = [Pv] * 3 + [Ii] + [Pv] * 4; L.rx_open.restype = Pv; L.rx_open.argtypes = [Pv, Ii]; L.rx_depth2.argtypes = [Pv]
    L.rx_cast.argtypes = [Pv, Ii, Pv, Pv, LL, Dd, Pv, Pv, Pv]
    L.lm2_light.argtypes = [Pv, Ii, LL, Pv, Pv, Pv, Pv, Pv, Ii, Pv, Pv, Pv, Pv, Pv, Pv, Pv, Ii, Pv, Ii, Dd, Pv, Pv, Pv, Pv]; L.lm2_smooth.argtypes = [Pv, Ii, LL, Pv, Pv, Pv, Pv, Pv]
    return L
LIB = _lib(); _d = lambda a: np.ascontiguousarray(a, np.float64); _p = lambda a: a.ctypes.data_as(ctypes.c_void_p)
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
D = np.load(PATH + '.lm.npz'); P = D['P'].astype(float); N = D['N'].astype(float); N /= np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]; I = D['I'].astype(float); U2 = D['U'].astype(bool)
S = pickle.load(open(PATH + '.scene', 'rb')); SUN = np.asarray(S['sun'], float); SUN /= np.linalg.norm(SUN); PAGE = LM.PAGE
G = pickle.load(open(DUMP, 'rb')); rd = G['rd']; origin = G.get('origin', {}); lab = {k: v[0] for k, v in retex.labels().items()}
names = []; seen = {}
for mat, sec, Pf, Uf in ((fc[0], fc[1], fc[2], fc[3]) for fc in G['faces'] + G['sky'] + G['extra']):
    if str(sec) == 'sea' or len(Pf) < 3: continue
    m0 = str(mat).split('|')[0]
    if m0 not in seen: seen[m0] = len(names); names.append(m0)
alb0 = np.asarray(S['albedo_rgb'], float); holes0 = list(S['holes'])
# WHAT THE RAYS CAN HIT: the polygons as the game draws them. A four-corner polygon is two triangles along corners 0 - 2 (the built meshes are strips
# [1, 0, 2, 3]); the scene file of the build (bake1995.save_scene) cuts along 1 - 3. On a twisted polygon the two differ by up to metres, so half the
# texels of such a wall lay BEHIND their own occluder: the black panels and half-panels on the cliffs (2026-10-13). The triangles are made here.
T_ = []; TU_ = []; TM_0 = []
for fc in G['faces'] + G['sky'] + G['extra']:
    if str(fc[1]) == 'sea' or len(fc[2]) < 3: continue
    A_ = np.asarray(fc[2], float); B_ = np.asarray(fc[3], float); m_ = seen[str(fc[0]).split('|')[0]]
    for i0, i1, i2 in (((0, 1, 2), (0, 2, 3)) if len(A_) >= 4 else ((0, 1, 2),)): T_.append((A_[i0], A_[i1], A_[i2])); TU_.append((B_[i0], B_[i1], B_[i2])); TM_0.append(m_)
T = np.array(T_, float); TU = np.array(TU_, float); TM = np.array(TM_0, np.int64); nscene_ = int((np.asarray(S['mat']) != len(alb0) - 1).sum())
assert len(T) == nscene_, 'the dump (%d triangles) is not the scene the build saved (%d)' % (len(T), nscene_)
assert len(names) == len(alb0) - 1, 'materials of the scene (%d) and of the dump (%d) differ' % (len(alb0) - 1, len(names))
cls = [lab.get(origin.get(n, n), '') for n in names] + ['sr3road']; TREE = ('crown', 'trunk', 'bare', 'tree'); tcls = np.array(cls, object)[TM]
is_road = np.zeros(len(TM), bool); is_tree = np.isin(tcls, TREE); is_lamp = tcls == 'lamp'            # (the importer's own SR3 road mesh is not among these triangles at all)
print('scene %d triangles, cut as the game draws them: tree boards %d and lamp boards %d (replaced by solids), kept %d' % (len(T), is_tree.sum(), is_lamp.sum(), (~is_tree & ~is_lamp).sum()), flush=True)
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
def ball(centre, rh, rv):                                                # (the centre was called c and the loop below overwrote it: every canopy of the first builds sat at the origin - trees cast no shadow)
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
keep = ~is_road & ~is_tree & ~is_lamp; lo = T[keep].reshape(-1, 3).min(0); hi = T[keep].reshape(-1, 3).max(0); ysea = -0.6
SEA = [((lo[0] - 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, hi[2] + 4000)), ((lo[0] - 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, hi[2] + 4000), (lo[0] - 4000, ysea, hi[2] + 4000))]
nm = len(alb0); M_SOLID, M_CAN, M_SEA = nm, nm + 1, nm + 2; rng = np.random.RandomState(7)
TA = np.concatenate([T[keep], np.array(solid, float).reshape(-1, 3, 3), np.array(canopy, float).reshape(-1, 3, 3), np.array(SEA, float)])
TMA = np.concatenate([TM[keep], np.full(len(solid), M_SOLID), np.full(len(canopy), M_CAN), np.full(2, M_SEA)]).astype(np.int32)
UVA = np.concatenate([TU[keep], np.zeros((len(solid), 3, 2)), rng.rand(len(canopy), 3, 2), np.zeros((2, 3, 2))])
alb = np.concatenate([np.clip(alb0 * 8.0, 0.0, 0.85), [[0.25, 0.2, 0.15], [0.12, 0.3, 0.08], [0.03, 0.12, 0.35]]]); holes = holes0 + [None, rng.rand(64, 64) < 0.25, None]
TN = np.cross(TA[:, 1] - TA[:, 0], TA[:, 2] - TA[:, 0]); TN /= np.maximum(np.linalg.norm(TN, axis=1), 1e-12)[:, None]
sc = Scene(TA); sc.masks(TMA, UVA, holes); LIFT = 0.02
if sc.depth > 150 and MODE: print('the quick walks\' tree is %d deep (their stack is sized for 150): every ray goes through cast_one' % sc.depth, flush=True); MODE = 0
print('rays: mode %d, tree for the quick walks %d deep ; scene ready after %.0f s' % (MODE, sc.depth, time.time() - t0), flush=True)
def cast(o, d, nsrc, tmax=1e9):
    """nearest hit, going on through layers that lie nearly parallel to the face the ray left and within 10 cm of it"""
    hit, t = sc.cast(o, d, tmax)
    for rnd in range(3):
        k = np.nonzero((hit >= 0) & (t < 0.10))[0]
        if not len(k): break
        k = k[np.abs((TN[hit[k]] * nsrc[k]).sum(1)) > 0.9]
        if not len(k): break
        o2 = o[k] + d[k] * (t[k] + 0.003)[:, None]; h2, t2 = sc.cast(o2, d[k], tmax); hit[k] = h2; t[k] = np.where(h2 >= 0, t[k] + 0.003 + t2, t2)
    return hit, t
sh = np.array([SUN[0], 0.0, SUN[2]]); lh = np.linalg.norm(sh); design = (sh / lh * 0.7071 + np.array([0.0, 0.7071, 0.0])) if lh > 1e-6 else np.array([0.0, 1.0, 0.0])
def frame(n):
    ax = np.where((np.abs(n[:, 1]) < 0.9)[:, None], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]); t = np.cross(n, ax); t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]; return t, np.cross(n, t)
# ---------------------------------------------------------------- no side is chosen (owner, 2026-10-13: "there's a light source, there's an angle and there's geometry. just shine a light on it")
# Every texel is lit from BOTH faces of its polygon and keeps the brighter result: the face turned to the sun takes the sun if nothing is in the
# way, the face that sees sky takes the sky. A closed body is dark inside, so its outside wins; ground is never lit from underneath. The version
# before this guessed one "seen side" per polygon (from the road, then from the sky): 952 pieces of ground were lit from below and neighbours
# on one surface disagreed - the dark wedges and panels of the first two game builds.
C = P.mean(1); sea_poly = (P[:, :, 1].max(1) < -0.3) & (P[:, :, 1].min(1) > -0.7); U2 = np.ones(len(P), bool)
print('lit side: none chosen, both faces of every polygon are lit and the brighter kept ; sea polygons (no baked light) %d ; %.0f s' % (int(sea_poly.sum()), time.time() - t0), flush=True)
# ---------------------------------------------------------------- the light
SUN_DEG = 3.0; KS = 16 if FAST else 32; TURNS = 1 if FAST else 3
st, sb = frame(SUN[None]); rad = math.radians(SUN_DEG / 2); SD = [SUN]
for ring, cnt in (((1.0, 6),) if FAST else ((0.5, 6), (1.0, 12))):
    for k in range(cnt):
        a = 2 * math.pi * (k + 0.5 * (ring < 1)) / cnt; d = SUN + math.tan(rad * ring) * (math.cos(a) * st[0] + math.sin(a) * sb[0]); SD.append(d / np.linalg.norm(d))
SD = np.array(SD); HEMI = np.array([(math.sqrt((i + 0.5) / KS) * math.cos(i * 2.399963), math.sqrt((i + 0.5) / KS) * math.sin(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / KS))) for i in range(KS)])
TNS = _d(TN @ SUN); TND = _d(TN @ design); TNc = _d(TN); ALBc = _d(alb); SDc = _d(SD); HEMIc = _d(HEMI); SUNc = _d(SUN); STATS = np.zeros(3, np.int64)
def light(pt, n, k0):
    """sun_seen + light of rt_bake_game2.py, the rays in C (rtg2.c: lm2_light)"""
    pt = _d(pt); n = _d(n); m = len(pt); f = np.ascontiguousarray((n @ SUN) > 0.02, np.uint8); CA = np.empty((m, TURNS)); SA = np.empty((m, TURNS)); st_ = np.zeros(3, np.int64)
    for turn in range(TURNS):
        ang = ((k0 + turn / TURNS) * 0.618034) % 1.0 * 2 * math.pi; CA[:, turn] = np.cos(ang); SA[:, turn] = np.sin(ang)
    V = np.empty(m); sky = np.empty(m); back = np.empty((m, 3))
    LIB.lm2_light(sc.x, MODE, m, _p(pt), _p(n), _p(f), _p(CA), _p(SA), TURNS, _p(TNc), _p(TNS), _p(TND), _p(TMA), _p(ALBc), _p(SUNc), _p(SDc), len(SDc), _p(HEMIc), KS, LIFT, _p(V), _p(sky), _p(back), _p(st_))
    STATS[:] += st_; return V, sky, back
def facing(n):
    ns = n @ SUN; face = np.clip((ns - 0.02) / 0.13, 0.0, 1.0); face = face * face * (3 - 2 * face); return np.clip((n @ design + 0.2) / 0.907, 0.0, 1.0) * face
page, x0, y0, nu, nv = LM.pack(P, S['centre']); npg = int(page.max()); ntot = int((nu * nv).sum()); print('texels %.1f million on %d pages (%s)' % (ntot / 1e6, npg, 'FAST' if FAST else 'slow'), flush=True)
RAW = np.zeros((npg + 1, PAGE, PAGE, 7), np.uint8); RAW[..., 0] = 255; RAW[..., 1] = 255; RAW[..., 5] = 255; RAW[..., 6] = 255; ntex = 0; order = np.argsort(page, kind='stable'); t1 = time.time()
csum = np.cumsum((nu * nv)[order]); cuts = [0]
while cuts[-1] < len(order): cuts.append(max(int(np.searchsorted(csum, csum[cuts[-1]] - (nu * nv)[order[cuts[-1]]] + 250000, side='right')), cuts[-1] + 1))
TM_.clear(); nlit = 0
for bi in range(len(cuts) - 1):
    if bi % STEP != OFF: ntex += int((nu * nv)[order[cuts[bi]:cuts[bi + 1]]].sum()); continue
    q0 = time.perf_counter(); ii = order[cuts[bi]:cuts[bi + 1]]; cnt = nu[ii] * nv[ii]; tot_ = int(cnt.sum()); f = np.repeat(np.arange(len(ii)), cnt); stt = np.repeat(np.cumsum(cnt) - cnt, cnt); loc = np.arange(tot_) - stt
    iu = loc % nu[ii][f]; iv = loc // nu[ii][f]; a = (iu / (nu[ii][f] - 1))[:, None]; b = (iv / (nv[ii][f] - 1))[:, None]; Q = P[ii][f]
    # WHERE A TEXEL IS: on the two triangles the game draws. The built meshes are strips [1, 0, 2, 3] per polygon (meshgen.quads_to_strip with
    # ccw False, read back from a built file on 2026-10-13): triangles (1, 0, 2) and (0, 2, 3) - the polygon is cut along corners 0 - 2, NOT 1 - 3
    # as lightmap1995.py assumed. On a flat four-corner polygon both cuts give the same places; a THREE-corner polygon (corners 2 and 3 the same)
    # is drawn as texels b <= a only, and the old formula filled a + b <= 1: every triangle showed sheared light and half of it edge values.
    lowr = (b <= a)[:, 0]; pt = np.where(lowr[:, None], Q[:, 0] + (a - b) * (Q[:, 1] - Q[:, 0]) + b * (Q[:, 2] - Q[:, 0]), Q[:, 0] + a * (Q[:, 2] - Q[:, 0]) + (b - a) * (Q[:, 3] - Q[:, 0]))
    n1 = np.cross(Q[:, 1] - Q[:, 0], Q[:, 2] - Q[:, 0]); n2 = np.cross(Q[:, 2] - Q[:, 0], Q[:, 3] - Q[:, 0]); l1 = np.linalg.norm(n1, axis=1); l2 = np.linalg.norm(n2, axis=1)
    n2 = np.where((l2 > 1e-9)[:, None], n2, n1); l2 = np.where(l2 > 1e-9, l2, l1); tn = np.where(lowr[:, None], n1 / np.maximum(l1, 1e-12)[:, None], n2 / np.maximum(l2, 1e-12)[:, None])
    n = N[ii][f]; tn = np.where(((tn * n).sum(1) < 0)[:, None], -tn, tn); n = np.where((np.linalg.norm(tn, axis=1) > 0.5)[:, None], tn, n)
    Ir = I[ii][f]; ir = ((1 - a) * (1 - b))[:, 0] * Ir[:, 0] + (a * (1 - b))[:, 0] * Ir[:, 1] + (a * b)[:, 0] * Ir[:, 2] + ((1 - a) * b)[:, 0] * Ir[:, 3]
    k0 = (np.arange(tot_) + ntex).astype(float); TM_['texel maths'] += time.perf_counter() - q0; q0 = time.perf_counter(); V, A, B = light(pt, n, k0); TM_['light 1st side'] += time.perf_counter() - q0; TM_['texels 1st'] += tot_; Fc = facing(n); u = U2[ii][f]
    if u.any():
        q0 = time.perf_counter(); V2, A2, B2 = light(pt[u], -n[u], k0[u]); TM_['light 2nd side'] += time.perf_counter() - q0; TM_['texels 2nd'] += int(u.sum()); F2 = facing(-n[u]); bet = (0.66 * V2 * F2 + 0.22 * A2 + B2.mean(1)) > (0.66 * V[u] * Fc[u] + 0.22 * A[u] + B[u].mean(1))
        for arr, alt in ((V, V2), (A, A2), (Fc, F2)): tmp = arr[u]; tmp[bet] = alt[bet]; arr[u] = tmp
        tmp = B[u]; tmp[bet] = B2[bet]; B[u] = tmp
    q0 = time.perf_counter(); sp = sea_poly[ii][f]; V[sp] = 1.0; A[sp] = 1.0; B[sp] = 0.0; Fc[sp] = 1.0
    RAW[page[ii][f], y0[ii][f] + iv, x0[ii][f] + iu] = np.round(np.clip(np.c_[V, A, B * 4.0, Fc, ir], 0, 1) * 255).astype(np.uint8); ntex += tot_; nlit += tot_; TM_['store'] += time.perf_counter() - q0
    if bi % 10 == 0: print('  %d%% (%.1f of %.1f million texels), %.0f s' % (100 * ntex // ntot, ntex / 1e6, ntot / 1e6, time.time() - t1), flush=True)
t2 = time.time(); RAW = np.ascontiguousarray(RAW); _i = lambda a_, t_: np.ascontiguousarray(a_, t_); pg_, x0_, y0_, nu_, nv_ = _i(page, np.int32), _i(x0, np.int32), _i(y0, np.int32), _i(nu, np.int64), _i(nv, np.int64)
LIB.lm2_smooth(_p(RAW), PAGE, len(P), _p(pg_), _p(x0_), _p(y0_), _p(nu_), _p(nv_))             # the 3 x 3 smoothing of every polygon's rectangle and its growth to whole 4 x 4 blocks (rtg2.c)
t3 = time.time(); np.save(OUT + '.raw.npy', RAW[1:]); np.savez(OUT + '.pack.npz', page=page, x0=x0, y0=y0, nu=nu, nv=nv, trees=np.array(TREES, float).reshape(-1, 6))
print('RTG2 %d polygons, %.1f million texels, %d pages ; rays %.0f s, all %.0f s' % (len(P), ntex / 1e6, npg, time.time() - t1, time.time() - t0))
print('TIMES lit texels %.2f million ; batches %.1f s ; smoothing %.1f s ; save %.1f s ; %s ; rays %.0f million (%d handed to cast_one, %.0f million sun questions answered by the quick walk)'
      % (nlit / 1e6, t2 - t1, t3 - t2, time.time() - t3, {k: round(v, 1) for k, v in TM_.items()}, STATS[0] / 1e6, STATS[1], STATS[2] / 1e6))
