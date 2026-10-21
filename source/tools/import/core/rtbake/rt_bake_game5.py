"""RT bake for the GAME, fifth version = the fourth + ROUNDED polygons (2026-10-13).   python rt_bake_game5.py <path> <faces.pkl> [fast|slow] [<out path>]
The pieces a rounded polygon is cut into (course setting round; 16 of them at R4) lie in ONE light-map rectangle, their polygon's: the collected file
says which rectangle a polygon lies in (R) and where its corners are in it (AB). A rectangle's texels are lit on the pieces as they are in space
(rtg5.c: lm5_light); a rectangle with one polygon is lit exactly as the fourth version lit it. With a rectangle per piece R4 had 406,610 light-map
polygons and 1.7 million vertices (no corner shared); with shared rectangles 82,144 rectangles, and corners are shared again.
Without numpy since 2026-10-15 (kb 31): the files through npyio.py / scenefile.py / nfpickle.py, the loops over triangles, edges, rectangles and
texels in rtg5prep.c (C, every core), the rest in plain Python. Every number is the one numpy gave (the three files are the numpy version's, member
for member); each step quotes the numpy line it replaced and says why it is done this way.
----- the text of rt_bake_game4.py:
RT bake for the GAME, fourth version (2026-10-13, after the owner's second drive).   python rt_bake_game4.py <path> <faces.pkl> [fast|slow] [<out path>]
<path> = what an importer build collected (lm_collect); faces.pkl = the same build's GAPFILL_DUMP. Needs rays.c, fastlm_rays.c, rtg2_rays.c, rtg5.c,
rtg5prep.c beside this file (cbuild.py builds them).
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
import sys, math, time, collections, os, ctypes, json, csv, random, bisect, itertools
from array import array
import npyio, scenefile, nfpickle, common
PATH, DUMP = sys.argv[1], sys.argv[2]; FAST = (sys.argv[3] if len(sys.argv) > 3 else 'slow') == 'fast'; t0 = time.time()
OUT = sys.argv[4] if len(sys.argv) > 4 else PATH; STEP = int(os.environ.get('BAKE_STEP', '1')); OFF = int(os.environ.get('BAKE_OFF', '0')); MODE = int(os.environ.get('RTG2_MODE', '1')); TM_ = collections.Counter()
NEAR = float(os.environ.get('RTG_NEAR', '6')); REACH = float(os.environ.get('RTG_REACH', '20')); FAR = float(os.environ.get('RTG_FAR', '0.75')); UNSEEN = float(os.environ.get('RTG_UNSEEN', '2')); MAXC = int(os.environ.get('RTG_MAXC', '256'))
INSET = 0.04; LIFT = 0.02; SKIRT_MAX = 0.60; FILL = float(os.environ.get('RTG_FILL', '0.88'))
CANOPY_STYLE = os.environ.get('RTG_CANOPY', 'legacy')
if CANOPY_STYLE not in ('legacy', 'perforated'): raise ValueError('Unknown RTG_CANOPY: ' + CANOPY_STYLE)
from rtbake.canopy_shadow import perforation_mask, project_uv
PAGE = 2048                                                            # lightmap1995.PAGE (that module still imports numpy)
# ---------------------------------------------------------------- the C side
HERE = os.path.dirname(os.path.abspath(__file__)); import cbuild as _cb
def _lib():
    dll = _cb.dll('rtg5')                                  # built on first use (cbuild.py: sources, flags, compiler)
    _cb.runtime(); L = ctypes.CDLL(dll); Pv = ctypes.c_void_p; LL = ctypes.c_longlong; Dd = ctypes.c_double; Ii = ctypes.c_int
    L.rt_build.restype = Pv; L.rt_build.argtypes = [Pv, Ii]; L.rt_masks.argtypes = [Pv] * 3 + [Ii] + [Pv] * 4; L.rx_open.restype = Pv; L.rx_open.argtypes = [Pv, Ii]; L.rx_depth2.argtypes = [Pv]
    L.rx_cast.argtypes = [Pv, Ii, Pv, Pv, LL, Dd, Pv, Pv, Pv]; L.lm2_smooth.argtypes = [Pv, Ii, LL, Pv, Pv, Pv, Pv, Pv]
    L.lm5_cars.restype = LL; L.lm5_cars.argtypes = [Pv, LL, Pv, Pv, Ii, Dd, Dd, Pv, Ii, Pv, Ii, Dd, Pv, Pv, Pv]
    L.lm5_light.argtypes = [Pv, Ii, LL] + [Pv] * 14 + [Dd, Pv, Pv, Ii] + [Pv] * 8 + [Ii, Pv, Pv, Ii, Dd, Dd] + [Pv] * 6
    for f, res, args in (('rp_tris', LL, [LL] + [Pv] * 11), ('rp_keep', LL, [LL] + [Pv] * 11), ('rp_edges', LL, [LL, Pv, Pv, Pv, Pv, LL, Pv, Pv, Pv, Pv]),
                         ('rp_normals', None, [LL, Pv, Pv]), ('rp_dot3', None, [LL, Pv, Pv, Pv]), ('rp_grid', None, [Ii, Pv, Pv, Pv]), ('rp_carpage', LL, [Ii, Pv, Pv, Pv, Pv]),
                         ('rp_rects', None, [LL, Pv, Pv, Pv, LL, Pv, Pv, Pv, Pv, LL] + [Pv] * 15), ('rp_cells', None, [LL, Pv, Pv, Pv, LL] + [Pv] * 6),
                         ('rp_texels', LL, [LL, Pv, Pv, Pv, LL, Pv, Pv, Pv, Pv]), ('rp_angles', None, [LL, Pv, Ii, Pv, Pv]), ('rp_facing', None, [LL, Pv, Pv, Pv, Pv]),
                         ('rp_pick', LL, [LL] + [Pv] * 11), ('rp_merge', None, [LL] + [Pv] * 9), ('rp_store', None, [LL] + [Pv] * 13 + [Ii, Pv]), ('rp_perpoly', None, [LL] + [Pv] * 13)):
        getattr(L, f).restype = res; getattr(L, f).argtypes = args
    return L
LIB = _lib()
# Arrays for C are array.array (the numpy version's np.ascontiguousarray(a, dtype) and a.ctypes.data_as): numpy could do all of this, but the
# toolchain zip no longer carries it for this process; the loops numpy ran on whole arrays are rtg5prep.c's.
_SZ = {'d': 8, 'i': 4, 'q': 8, 'B': 1}; assert array('i').itemsize == 4 and array('q').itemsize == 8
def new(tc, n, fill=None):
    """n zeros (np.zeros) or n times fill (np.full) for C"""
    return array(tc, bytes(_SZ[tc] * n)) if fill is None else array(tc, [fill]) * n
def ad(a):
    """the address C is given"""
    return a.buffer_info()[0] if isinstance(a, array) else a.ptr()
def conv(a, tc):
    """a file's array as C type tc: the array itself when it is one already, else converted (np.asarray(a, dtype))"""
    want = {'d': '<f8', 'i': '<i4', 'q': '<i8'}[tc]
    return a if a.dtype == want else npyio.Arr(want, a.shape, memoryview(array(tc, a.view())).cast('B'))
def arr(dtype, shape, a):
    """an npyio.Arr over a C array (for the files)"""
    return npyio.Arr(dtype, shape, memoryview(a).cast('B') if isinstance(a, array) else a)
_ucrt = ctypes.CDLL('ucrtbase'); _ucrt.hypot.restype = ctypes.c_double; _ucrt.hypot.argtypes = [ctypes.c_double] * 2
hypot = _ucrt.hypot                                                    # np.hypot is the C runtime's hypot (Python's math.hypot differs in the last bit)
# numpy's arithmetic, the steps this script took from it (kb 31, measured on numpy 1.24.3):
def nrm(v):
    """np.linalg.norm(v) of a fresh 3-vector = sqrt(v.dot(v)); OpenBLAS's dot of two 3-vectors adds (p0 + p2) + p1 when the vector is 16-byte
    aligned, as every fresh array is (kb 31: the order follows where the operand sits in memory)"""
    return math.sqrt((v[0] * v[0] + v[2] * v[2]) + v[1] * v[1])
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])        # np.cross: each product rounded on its own
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def pwsum(v):
    """np.add.reduce of a 1-D float64 array: numpy's pairwise sum (below 8 one after the other; up to 128 eight running sums added as
    ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7)), then the rest one by one; above, the two halves cut at a multiple of 8)"""
    n = len(v)
    if n < 8:
        s = 0.0
        for x in v: s += x
        return s
    if n <= 128:
        r = list(v[:8]); e = n - n % 8
        for i in range(8, e, 8):
            for j in range(8): r[j] += v[i + j]
        s = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
        for x in v[e:]: s += x
        return s
    h = n // 2; h -= h % 8
    return pwsum(v[:h]) + pwsum(v[h:])
def mean(v): return (0.0 + pwsum(v)) / len(v)                          # np.mean along one axis: the sum added to 0, divided by the count
def pct90(v):
    """np.percentile(v, 90), numpy 1.24's 'linear': the (n - 1) x 0.9-th of the sorted values, between its neighbours as numpy's _lerp does it
    (a + (b - a) x g below g = 0.5, b - (b - a) x (1 - g) from there)"""
    v = sorted(v); n = len(v); vi = (n - 1) * 0.9; lo_ = math.floor(vi); hi_ = min(lo_ + 1, n - 1); g = vi - lo_; a, b = v[lo_], v[hi_]; d = b - a
    return b - d * (1 - g) if g >= 0.5 else a + d * g
def mt19937(seed):
    """np.random.RandomState(seed)'s state for Python's random (both are MT19937 and make a float of 53 bits from two draws the same way):
    numpy seeds by init_genrand, Python by init_by_array, so the state is set here"""
    mt = [seed & 0xffffffff]
    for i in range(1, 624): mt.append((1812433253 * (mt[-1] ^ (mt[-1] >> 30)) + i) & 0xffffffff)
    return (3, tuple(mt + [624]), None)
def masks(holes):
    """Scene.masks' layout (rays.c rt_masks): per material its see-through mask's width, height and place in one run of bits (-1 = none)"""
    n = len(holes); w = new('i', n); h = new('i', n); off = new('q', n, -1); bits = bytearray()
    for m, hm in enumerate(holes):
        if hm is None: continue
        h[m], w[m], b = hm; off[m] = len(bits); bits += b
    return w, h, off, array('B', bytes(bits) if bits else bytes(1))
class Scene:
    """rays.Scene on this DLL: the tree of rays.c, and over its leaves the four-to-a-node tree of fastlm_rays.c for the quick walks"""
    def __init__(self, tris, n):
        self.tris = tris; self.h = LIB.rt_build(ad(tris), n); self.x = None
    def masks(self, tm, tu, holes):
        w, h, off, bits = masks(holes); self.keep = [tm, tu, w, h, off, bits]
        LIB.rt_masks(self.h, ad(tm), ad(tu), len(holes), ad(w), ad(h), ad(off), ad(bits)); self.x = LIB.rx_open(self.h, 1); self.depth = LIB.rx_depth2(self.x)
    def cast(self, org, dirs, n, tmax=600.0):
        hit = new('i', n); t = new('d', n); fell = ctypes.c_longlong(0)
        LIB.rx_cast(self.x, 1 if MODE else 0, ad(org), ad(dirs), n, float(tmax), ad(hit), ad(t), ctypes.byref(fell)); return hit, t
D = npyio.loadz(PATH + '.lm.npz'); P = conv(D['P'], 'd'); NPOL = P.shape[0]; I = conv(D['I'], 'd'); U2 = D['U']; U2l = U2.view().tolist()      # (.astype(float), .astype(bool))
GRP = conv(D['G'], 'i') if 'G' in D else arr('<i4', (NPOL,), new('i', NPOL))
S = scenefile.load(PATH + '.scene'); SUN = conv(S['sun'], 'd').view().tolist(); n_ = nrm(SUN); SUN = [s_ / n_ for s_ in SUN]      # SUN /= np.linalg.norm(SUN)
G = nfpickle.load(DUMP); rd = G['rd']; origin = G.get('origin', {})
CSVP = os.path.join(common.WORK, 'retex', 'tile_labels.csv')          # retex.labels()'s file (retex imports numpy); the bake only reads its classes
lab = {r_['tile']: r_['class'] for r_ in csv.DictReader(open(CSVP))} if os.path.exists(CSVP) else {}
FS = [fc for fc in G['faces'] + G['sky'] + G['extra'] if not (str(fc[1]) == 'sea' or len(fc[2]) < 3)]      # the faces the rays can hit, in their order
KEYS = [str(fc[0]) for fc in FS]; BASE = [k_.split('|')[0] for k_ in KEYS]
names = []; seen = {}
for m0 in BASE:
    if m0 not in seen: seen[m0] = len(names); names.append(m0)
alb0 = conv(S['albedo_rgb'], 'd').view().tolist(); NM0 = S['albedo_rgb'].shape[0]
hh_, hw_, ho_, hb_ = S['holes_h'].view(), S['holes_w'].view(), S['holes_off'].view(), S['holes_bits'].buf
holes0 = [None if ho_[m] < 0 else (hh_[m], hw_[m], bytes(hb_[ho_[m]:ho_[m] + hh_[m] * hw_[m]])) for m in range(len(ho_))]      # (height, width, bits)
# WHAT THE RAYS CAN HIT: the polygons as the game draws them (a four-corner polygon is two triangles along corners 0 - 2). ONE = the road sees this
# polygon on its winding side only (seenside.py left its key bare): something standing behind it is hidden.
# All corners and all uv in two arrays; a face's triangles are rows of them (the same triangles in the same order as the loop over the faces gave).
NC = [len(fc[2]) for fc in FS]; FST = list(itertools.accumulate(NC, initial=0))[:-1]; NCOR = sum(NC)
CO = array('d', itertools.chain.from_iterable(itertools.chain.from_iterable(fc[2] for fc in FS))); UO = array('d', itertools.chain.from_iterable(itertools.chain.from_iterable(fc[3] for fc in FS)))
assert len(CO) == 3 * NCOR, 'a corner of another number of coordinates than 3'
assert len(UO) == 2 * NCOR, 'a face with another number of uv than corners'
FM = array('i', [seen[b_] for b_ in BASE]); FONE = array('B', [('|' not in k_) and not k_.endswith('_t') for k_ in KEYS]); FCUT = [b_.endswith('_t') for b_ in BASE]
NTRI = len(FS) + sum(1 for c_ in NC if c_ >= 4); FSTa = array('q', FST); NCa = array('q', NC)
T = new('d', 9 * NTRI); TU = new('d', 6 * NTRI); TM = new('i', NTRI); ONE0 = new('B', NTRI); TF = new('i', NTRI)
LIB.rp_tris(len(FS), ad(FSTa), ad(NCa), ad(FM), ad(FONE), ad(CO), ad(UO), ad(T), ad(TU), ad(TM), ad(ONE0), ad(TF))      # T = CO[TI]; TU = UO[TI]; TM = np.repeat(FM, nt_) ...
mat_ = S['mat'].view(); nscene_ = len(mat_) - mat_.tolist().count(NM0 - 1)
face_ = lambda i: [(CO[3 * k], CO[3 * k + 1], CO[3 * k + 2]) for k in range(FST[i], FST[i] + NC[i])]
assert NTRI == nscene_, 'the dump (%d triangles) is not the scene the build saved (%d)' % (NTRI, nscene_)
assert len(names) == NM0 - 1, 'materials of the scene (%d) and of the dump (%d) differ' % (NM0 - 1, len(names))
cls = [lab.get(origin.get(n, n), '') for n in names] + ['sr3road']; TREE = ('crown', 'trunk', 'bare', 'tree'); TMl = TM.tolist(); tcls = [cls[m_] for m_ in TMl]
is_tree = [c_ in TREE for c_ in tcls]; is_lamp = [c_ == 'lamp' for c_ in tcls]; ntb_ = sum(is_tree); nlb_ = sum(is_lamp)
print('scene %d triangles, cut as the game draws them: tree boards %d and lamp boards %d (replaced by solids), kept %d ; seen by the road on one side only %d' % (NTRI, ntb_, nlb_, NTRI - ntb_ - nlb_, sum(ONE0)), flush=True)
# ---------------------------------------------------------------- trees and lamps as solids
corner = lambda i, c: (T[9 * i + 3 * c], T[9 * i + 3 * c + 1], T[9 * i + 3 * c + 2])      # corner c of triangle i
def clusters(idx):
    par = {}
    def find(x):
        while par.setdefault(x, x) != x: par[x] = par[par[x]]; x = par[x]
        return x
    K = [[tuple(round(v_ * 20) for v_ in corner(i, c)) for c in range(3)] for i in idx]      # 5 cm (np.round(T[idx] * 20): half to even, as round())
    for t in range(len(idx)):
        ks = K[t]
        for k in ks[1:]: par[find(k)] = find(ks[0])
    out = collections.defaultdict(list)
    for t, i in enumerate(idx): out[find(K[t][0])].append(i)
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
    V = [tuple(float(c_) / nrm(v) for c_ in v) for v in V]; tris = [(V[a], V[b], V[c]) for a, b, c in F]; out = []
    for a, b, c in tris:                                               # one subdivision: 80 faces
        ab, bc, ca = [tuple(s_ / nrm(s) for s_ in s) for s in (tuple(x_ + y_ for x_, y_ in zip(x, y)) for x, y in ((a, b), (b, c), (c, a)))]; out += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
    sc_ = (rh, rv, rh); return [tuple(tuple(centre[k] + v[k] * sc_[k] for k in range(3)) for v in tr) for tr in out]      # centre + v * sc_
solid = []; canopy = []; canopy_uv = []; ntree = nlamp = 0; TREES = []
for cl in clusters([i for i in range(NTRI) if is_tree[i]]):
    V = [corner(i, c) for i in cl for c in range(3)]; tr = [corner(i, c) for i in cl if tcls[i] == 'trunk' for c in range(3)]; cr = [corner(i, c) for i in cl if tcls[i] != 'trunk' for c in range(3)]
    src_ = tr if tr else V; ax = (mean([p[0] for p in src_]), mean([p[2] for p in src_])); y0 = min(p[1] for p in V); y1 = max(p[1] for p in V)      # (tr or V)[:, [0, 2]].mean(0)
    if y1 - y0 < 1.0: continue
    if cr:
        cy0 = min(p[1] for p in cr) if tr else y0 + 0.45 * (y1 - y0); rh = max(0.6, 0.8 * pct90([hypot(p[0] - ax[0], p[2] - ax[1]) for p in cr])); cc = (ax[0], (cy0 + y1) / 2, ax[1])
        if rh > 50.0:
            raise ValueError('Tree canopy radius %.1f m: check the authored course material labels before baking' % rh)
        crown = ball(cc, rh, max(0.6, (y1 - cy0) / 2)); canopy += crown
        if CANOPY_STYLE == 'perforated': canopy_uv += project_uv(crown, cc, SUN)
        solid += cylinder(ax[0], ax[1], y0, cc[1], 0.22); TREES.append((cc[0], cc[1], cc[2], rh, max(0.6, (y1 - cy0) / 2), y0))
    else: solid += cylinder(ax[0], ax[1], y0, y1, 0.22)
    ntree += 1
for cl in clusters([i for i in range(NTRI) if is_lamp[i]]):
    V = [corner(i, c) for i in cl for c in range(3)]; solid += cylinder(mean([p[0] for p in V]), mean([p[2] for p in V]), min(p[1] for p in V), max(p[1] for p in V), 0.18, 8); nlamp += 1
print('solids for the rays: %d trees (%d canopy faces, %s mask), %d lamp posts' % (ntree, len(canopy), CANOPY_STYLE, nlamp), flush=True)
keep = array('B', [not (a_ or b_) for a_, b_ in zip(is_tree, is_lamp)]); NK = sum(keep); Tk = new('d', 9 * NK); TUk = new('d', 6 * NK); TMk = new('i', NK); ONEk = new('B', NK); lo = new('d', 3); hi = new('d', 3)
LIB.rp_keep(NTRI, ad(keep), ad(T), ad(TU), ad(TM), ad(ONE0), ad(Tk), ad(TUk), ad(TMk), ad(ONEk), ad(lo), ad(hi)); lo = lo.tolist(); hi = hi.tolist(); ysea = -0.6      # T[keep] ... ; T[keep].reshape(-1, 3).min(0)
SEA = [((lo[0] - 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, hi[2] + 4000)), ((lo[0] - 4000, ysea, lo[2] - 4000), (hi[0] + 4000, ysea, hi[2] + 4000), (lo[0] - 4000, ysea, hi[2] + 4000))]
nm = NM0; M_SOLID, M_CAN, M_SEA = nm, nm + 1, nm + 2; rng = random.Random(); rng.setstate(mt19937(7))      # np.random.RandomState(7)
alb = [min(max(a_ * 8.0, 0.0), 0.85) for a_ in alb0] + [0.25, 0.2, 0.15, 0.12, 0.3, 0.08, 0.03, 0.12, 0.35]      # np.clip(alb0 * 8.0, 0.0, 0.85) + three rows
legacy_mask = (64, 64, bytes(int(rng.random() < 0.25) for _ in range(64 * 64)))
canopy_mask = perforation_mask() if CANOPY_STYLE == 'perforated' else legacy_mask
print('canopy holes: %.1f%% open, %s; sun-aligned through openings %s' % (100*sum(canopy_mask[2])/len(canopy_mask[2]), CANOPY_STYLE, CANOPY_STYLE == 'perforated'), flush=True)
holes = holes0 + [None, canopy_mask, None]      # rng.rand(64, 64) < 0.25
flat = lambda tris: [c_ for tr_ in tris for p_ in tr_ for c_ in p_]
# ---------------------------------------------------------------- skirts under wall feet that hang over the ground (ray scene only)
# A standing opaque polygon whose lower edge belongs to no other polygon and has ground up to SKIRT_MAX under both its ends lets the sun through
# under it: a lit line along the foot of the wall, in the wall's shadow. The gap is closed for the rays; nothing is added to the game.
base = Scene(Tk + array('d', flat(SEA)), NK + 2); base.masks(TMk + array('i', [M_SEA, M_SEA]), TUk + new('d', 12), holes)
rk = lambda p: (int(round(p[0] * 200)), int(round(p[1] * 200)), int(round(p[2] * 200)))
# The edges that belong to ONE polygon, in the order a walk over the faces first meets them (rtg5prep.c: rp_edges, the lexsort over 1.2 million
# edges numpy did: a corner's place to 5 mm is one whole number, an edge the pair of its ends' numbers, the lower first).
cm_ = [c_ in TREE or c_ == 'lamp' for c_ in cls]; assert max(NC) <= 4, 'a face of more than four corners'
fi_ = array('q', [i for i in range(len(FS)) if not FCUT[i] and not cm_[FM[i]]]); ia_, ib_, ef_, ek_ = (new('q', 4 * len(fi_)) for _ in range(4))
ne_ = LIB.rp_edges(len(fi_), ad(fi_), ad(FSTa), ad(NCa), ad(CO), NCOR, ad(ia_), ad(ib_), ad(ef_), ad(ek_)); assert ne_ >= 0, 'a corner outside the range of the edge keys'
cand = []; pt_ = lambda k: (CO[3 * k], CO[3 * k + 1], CO[3 * k + 2])
for j_ in range(ne_):
    p0 = pt_(ia_[j_]); p1 = pt_(ib_[j_]); f_ = ef_[j_]; poly = [pt_(k) for k in range(FST[f_], FST[f_] + ek_[j_])]; m_ = FM[f_]; n_ = cross(sub(poly[1], poly[0]), sub(poly[2], poly[0])); ln_ = nrm(n_)
    if ln_ < 1e-9 or abs(n_[1] / ln_) > 0.6 or nrm(sub(p1, p0)) < 0.05: continue
    if max(p0[1], p1[1]) > mean([q_[1] for q_ in poly]) - 1e-6: continue      # not the lower edge
    cand.append((p0, p1, m_))
skirt = []; skm = []; sklen = 0.0; gaps = []
if cand:
    O = array('d', [c_ for p0, p1, m_ in cand for q_ in (p0, p1, tuple((a_ + b_) / 2 for a_, b_ in zip(p0, p1))) for c_ in (q_[0] - 0.0, q_[1] - 0.01, q_[2] - 0.0)])      # (p0, p1, (p0 + p1) / 2) - [0, 0.01, 0]
    h_, t_ = base.cast(O, array('d', [0.0, -1.0, 0.0]) * (3 * len(cand)), 3 * len(cand), SKIRT_MAX + 0.5); t_ = [t_[k] + 0.01 if h_[k] >= 0 else 1e9 for k in range(3 * len(cand))]
    for k_, (p0, p1, m_) in enumerate(cand):
        g = t_[3 * k_:3 * k_ + 3]
        if not (max(g) <= SKIRT_MAX and max(g) >= 0.03): continue
        q0 = (p0[0] - 0.0, p0[1] - (g[0] + 0.05), p0[2] - 0.0); q1 = (p1[0] - 0.0, p1[1] - (g[1] + 0.05), p1[2] - 0.0); skirt += [(p0, p1, q1), (p0, q1, q0)]; skm += [m_, m_]; sklen += nrm(sub(p1, p0)); gaps.append(max(g))
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
    tiles_ = set(json.load(open(CUTP))); B_ = [A_[:3] if (len(A_) == 4 and tuple(A_[2]) == tuple(A_[3])) else A_ for A_ in (face_(i_) for i_ in range(len(FS)) if BASE[i_] in tiles_)]; par_ = {}
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
            n_ = cross(sub(A_[1], A_[0]), sub(A_[2], A_[0])); l_ = nrm(n_)
            if l_ > 1e-9 and abs(n_[1] / l_) < 0.3: walls_.append((A_, tuple(c_ / l_ for c_ in n_)))
        if len(walls_) < 2 or any(max(abs(n_[0]), abs(n_[2])) < 0.996 for A_, n_ in walls_): continue      # (only buildings whose walls stand along x and z)
        W_ = [p_ for A_, n_ in walls_ for p_ in A_]; x0_, y0_, z0_ = (min(p_[k] for p_ in W_) for k in range(3)); x1_, y1_, z1_ = (max(p_[k] for p_ in W_) for k in range(3)); nbuild += 1
        has_ = lambda ax, val: any(max(abs(p_[ax] - val) for p_ in A_) < 0.3 for A_, n_ in walls_)
        quads_ = [[(x0_, y1_, z0_), (x1_, y1_, z0_), (x1_, y1_, z1_), (x0_, y1_, z1_)]]                       # the lid
        if not has_(0, x0_): quads_.append([(x0_, y0_, z0_), (x0_, y0_, z1_), (x0_, y1_, z1_), (x0_, y1_, z0_)])
        if not has_(0, x1_): quads_.append([(x1_, y0_, z0_), (x1_, y0_, z1_), (x1_, y1_, z1_), (x1_, y1_, z0_)])
        if not has_(2, z0_): quads_.append([(x0_, y0_, z0_), (x1_, y0_, z0_), (x1_, y1_, z0_), (x0_, y1_, z0_)])
        if not has_(2, z1_): quads_.append([(x0_, y0_, z1_), (x1_, y0_, z1_), (x1_, y1_, z1_), (x0_, y1_, z1_)])
        for q_ in quads_: skirt += [(q_[0], q_[1], q_[2]), (q_[0], q_[2], q_[3])]; skm += [M_SOLID, M_SOLID]; nclose += 1
    print('buildings of cut-out pictures closed for the rays: %d (%d blockers: a lid each, and a wall where a side has none)' % (nbuild, nclose), flush=True)
ns_ = len(skirt)
NTA = NK + len(solid) + len(canopy) + 2 + ns_      # TA = np.concatenate([T[keep], solid, canopy, SEA, skirt]) and its materials, uv (canopy: rng.rand), ONE flags
TA = Tk + array('d', flat(solid) + flat(canopy) + flat(SEA) + flat(skirt)); TMA = TMk + array('i', [M_SOLID] * len(solid) + [M_CAN] * len(canopy) + [M_SEA] * 2 + skm)
UVA = TUk + new('d', 6 * len(solid)) + array('d', canopy_uv if CANOPY_STYLE == 'perforated' else [rng.random() for _ in range(6 * len(canopy))]) + new('d', 6 * (2 + ns_)); TONE = ONEk + new('B', len(solid) + len(canopy) + 2 + ns_)
TN = new('d', 3 * NTA); LIB.rp_normals(NTA, ad(TA), ad(TN))       # np.cross(TA[:, 1] - TA[:, 0], TA[:, 2] - TA[:, 0]), normalized
sc = Scene(TA, NTA); sc.masks(TMA, UVA, holes)
if sc.depth > 150 and MODE: print('the quick walks\' tree is %d deep (their stack is sized for 150): every ray goes through cast_one' % sc.depth, flush=True); MODE = 0
print('rays: mode %d, tree for the quick walks %d deep ; scene ready after %.0f s' % (MODE, sc.depth, time.time() - t0), flush=True)
sh = (SUN[0], 0.0, SUN[2]); lh = nrm(sh); design = tuple(sh[k] / lh * 0.7071 + (0.0, 0.7071, 0.0)[k] for k in range(3)) if lh > 1e-6 else (0.0, 1.0, 0.0)
def frame(n):
    """frame(SUN[None]) of one direction: t = np.cross(n, ax), / np.maximum(np.linalg.norm(t, axis=1), 1e-12) ((x*x + y*y) + z*z), and np.cross(n, t)"""
    ax = (0.0, 1.0, 0.0) if abs(n[1]) < 0.9 else (1.0, 0.0, 0.0); t = cross(n, ax); l = math.sqrt((t[0] * t[0] + t[1] * t[1]) + t[2] * t[2]); l = l if (l != l or l > 1e-12) else 1e-12
    t = tuple(c_ / l for c_ in t); return t, cross(n, t)
# ---------------------------------------------------------------- the cars' pages
# The game lights a car by ambient x (1 - red) + sun x green of the road page's first picture, laid over the car from above (pixel shader with the
# sampler TexStaticShadow; SEGA's own pages: green 255 / red 0 in the open, green 0 in shadow, red up to 255 where the sky is shut out - tunnels).
# For every page the importer listed (course setting car_shade_dump): a picture of CAR_RES x CAR_RES; a texel within CAR_REACH of the road's middle
# asks the sun (7 rays over its disc) and the sky (24 rays) from CAR_UP above the road there; the rest is open sun. The outermost texels stay
# open sun: a car that is given a page it does not stand on reads that, which is what every car read before.
CAR_RES = int(os.environ.get('RTG_CAR_RES', '512')); CAR_REACH = 14.0; CAR_UP = 0.6; CARP = PATH + '.carpages.json'
if os.path.exists(CARP):
    tq = time.time(); pgs = [tuple(float(v_) for v_ in pg_) for pg_ in json.load(open(CARP))['pages']]; V_ = conv(rd['V'], 'd'); nv_, nk_ = V_.shape[0], V_.shape[1]; Vv_ = V_.view(); hw = rd['hw']
    cen3 = [tuple(Vv_[(r_ * nk_ + hw) * 3:(r_ * nk_ + hw) * 3 + 3]) for r_ in range(nv_)]      # rd['V'][:, rd['hw']]: the road's middle
    imgs = bytearray(bytes((0, 255, 0))) * (len(pgs) * CAR_RES * CAR_RES)      # np.zeros((len(pgs), CAR_RES, CAR_RES, 3), np.uint8); imgs[..., 1] = 255
    stc, sbc = frame(SUN); SDC = [SUN] + [[SUN[k] + math.tan(math.radians(1.5)) * (math.cos(a_) * stc[k] + math.sin(a_) * sbc[k]) for k in range(3)] for a_ in (j * math.pi / 3 for j in range(6))]; SDC = [[c_ / nrm(d_) for c_ in d_] for d_ in SDC]
    KC = 24; HC = [(math.sqrt((i + 0.5) / KC) * math.cos(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / KC)), math.sqrt((i + 0.5) / KC) * math.sin(i * 2.399963)) for i in range(KC)]      # about straight up, more rays near the top
    nlit = 0; nsh = 0; ntx = 0; SDCc = array('d', flat([SDC])); HCc = array('d', flat([HC])); XZ = new('d', 2 * CAR_RES * CAR_RES); G64 = new('d', CAR_RES * CAR_RES); R64 = new('d', CAR_RES * CAR_RES); ASK = new('B', CAR_RES * CAR_RES)
    IMG = ad(array('B')) if not imgs else ctypes.addressof((ctypes.c_char * len(imgs)).from_buffer(imgs))
    for k, (u0, v0, su, sv) in enumerate(pgs):
        uu = [(j + 0.5) / CAR_RES for j in range(CAR_RES)]; X = array('d', [(u_ - u0) / su for u_ in uu]); Z = array('d', [(u_ - v0) / sv for u_ in uu])      # row = v (z), column = u (x)
        xa_, xb_, za_, zb_ = min(X) - 20, max(X) + 20, min(Z) - 20, max(Z) + 20; sel = [c_ for c_ in cen3 if c_[0] > xa_ and c_[0] < xb_ and c_[2] > za_ and c_[2] < zb_]
        if not sel: continue
        LIB.rp_grid(CAR_RES, ad(X), ad(Z), ad(XZ)); C3 = array('d', flat([sel]))      # one C loop over the page's texels on every core (rtg5.c: lm5_cars)
        nask = int(LIB.lm5_cars(sc.x, CAR_RES * CAR_RES, ad(XZ), ad(C3), len(sel), CAR_REACH, CAR_UP, ad(SDCc), len(SDC), ad(HCc), KC, 0.05, ad(G64), ad(R64), ad(ASK)))
        if not nask: continue
        nshd = int(LIB.rp_carpage(CAR_RES, ad(G64), ad(R64), ad(ASK), IMG + k * CAR_RES * CAR_RES * 3)); ntx += nask; nsh += nshd      # blur, edges, bytes (rtg5prep.c)
    npyio.savez_compressed(OUT + '.carshade.npz', pages=arr('|u1', (len(pgs), CAR_RES, CAR_RES, 3), imgs), map=arr('<f8', (len(pgs), 4) if pgs else (0,), array('d', flat([pgs]))))
    print('cars: %d road pages of %d x %d ; %.1f million texels within %.0f m of the road asked, %.0f%% of them in shadow ; %.0f s -> %s.carshade.npz' % (len(pgs), CAR_RES, CAR_RES, ntx / 1e6, CAR_REACH, 100.0 * nsh / max(ntx, 1), time.time() - tq, OUT), flush=True)
    if os.environ.get('RTG_CARS_ONLY'): raise SystemExit(0)
else: print('cars: no page list beside the collected polygons (%s): the cars keep open sun everywhere' % CARP, flush=True)
# ---------------------------------------------------------------- which face is lit
# U (the importer's 'unsure' flag, material key '|4') = the road never sees this polygon: both faces are lit and the brighter kept, as rt_bake_game3
# did for every polygon. All others are lit on their WINDING side: seenside.py wound them towards the road (a polygon seen from both sides is in
# the list twice, once per winding, each copy drawn single-sided with its own texels).
# ---------------------------------------------------------------- the rectangles
# R = the rectangle a polygon lies in, AB = where its four corners are in it (the unit square for a polygon alone in its rectangle).
Rp = conv(D['R'], 'q') if 'R' in D else arr('<i8', (NPOL,), array('q', range(NPOL))); ABp = conv(D['AB'], 'd') if 'AB' in D else arr('<f8', (NPOL, 4, 2), array('d', [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]) * NPOL)
Rl_ = Rp.view().tolist(); ru = sorted(set(Rl_)); at_ = {v_: i_ for i_, v_ in enumerate(ru)}; rinv = array('q', [at_[v_] for v_ in Rl_]); nrect = len(ru)      # np.unique(Rp, return_inverse=True)
cv_ = conv(S['centre'], 'd').view(); cen_ = array('d', [cv_[2 * k + c_] for k in range(0, S['centre'].shape[0], 2) for c_ in (0, 1)])      # S['centre'][::2]
tri_p, d_p, sea_poly, Imean = new('B', NPOL), new('d', NPOL), new('B', NPOL), new('d', NPOL)
cnt_r, first_r, lu_r, lv_r, d_r, un_r, grp_r, minext, multi, pn_r, roff = new('q', nrect), new('q', nrect), new('d', nrect), new('d', nrect), new('d', nrect), new('B', nrect), new('q', nrect), new('d', nrect), new('B', nrect), new('i', nrect), new('q', nrect + 1)
LIB.rp_rects(NPOL, ad(P), ad(ABp), ad(rinv), nrect, ad(U2), ad(GRP), ad(I), ad(cen_), len(cen_) // 2, ad(tri_p), ad(d_p), ad(sea_poly), ad(Imean),      # (rtg5prep.c quotes the numpy lines)
             ad(cnt_r), ad(first_r), ad(lu_r), ad(lv_r), ad(d_r), ad(un_r), ad(grp_r), ad(minext), ad(multi), ad(pn_r), ad(roff))
print('lit side: %d polygons on their winding side (the side the road sees), %d never seen from the road: both faces lit, the brighter kept ; sea polygons (no baked light) %d' % (NPOL - sum(U2l), sum(U2l), sum(sea_poly)), flush=True)
# the lattice of a rectangle that holds several polygons: pn x pn cells of the square, two numbers a cell (the piece of the half b' <= a', the piece of the other)
CELL = new('i', max(roff[-1], 2), -1); tri_r = new('B', nrect); LIB.rp_cells(NPOL, ad(ABp), ad(tri_p), ad(rinv), nrect, ad(multi), ad(pn_r), ad(roff), ad(first_r), ad(CELL), ad(tri_r))
print('rectangles %d for %d polygons ; %d rectangles hold several (%d pieces, lattice up to %d x %d) ; empty cells in their lattices %d of %d' % (nrect, NPOL, sum(multi), sum(c_ for c_, m_ in zip(cnt_r, multi) if m_), max(pn_r), max(pn_r), CELL[:roff[-1]].count(-1), roff[-1]), flush=True)
# ---------------------------------------------------------------- the pages
def pack(lu, lv, d, grp, unsure):
    """-> page, x0, y0, nu, nv per rectangle. Texels a metre: NEAR within REACH of the road, thinning with distance to FAR ; rectangles the road never
    sees at most UNSEEN. Materials are dealt out to pages by their area, each page packed as a whole, tallest first. (Plain Python on the
    rectangles' numbers: numpy's lexsort is a stable sort on (-h, -w), its argsort(kind='stable') one on -area.)"""
    n = len(lu); dens = [NEAR if d_ < REACH else max(NEAR * REACH / max(d_, 1e-6), FAR) for d_ in d]; dens = [min(e_, UNSEEN) if u_ else e_ for e_, u_ in zip(dens, unsure)]
    nu = array('i', [min(max(int(math.ceil(a_ * e_)) + 1, 2), MAXC) for a_, e_ in zip(lu, dens)]); nv = array('i', [min(max(int(math.ceil(b_ * e_)) + 1, 2), MAXC) for b_, e_ in zip(lv, dens)])
    w = [(a_ + 3) // 4 * 4 for a_ in nu]; h = [(b_ + 3) // 4 * 4 for b_ in nv]; area = [a_ * b_ for a_, b_ in zip(w, h)]; cap = int(PAGE * PAGE * FILL)
    garea = [0] * (max(grp) + 1 if n else 0); mem = collections.defaultdict(list); bins = []; left = []
    for i, g in enumerate(grp): garea[g] += area[i]; mem[g].append(i)      # np.bincount(grp, weights=area)
    for g in sorted(range(len(garea)), key=lambda g_: -garea[g_]):
        if not garea[g]: continue
        ii = sorted(mem[g], key=lambda i_: (-h[i_], -w[i_]))
        if garea[g] <= cap:
            k = next((k for k in range(len(bins)) if left[k] >= garea[g]), None)
            if k is None: bins.append([]); left.append(cap); k = len(bins) - 1
            bins[k] += ii; left[k] -= int(garea[g]); continue
        k = None
        for i in ii:
            if k is None or left[k] < area[i]: bins.append([]); left.append(cap); k = len(bins) - 1
            bins[k].append(i); left[k] -= int(area[i])
    page = new('i', n); x0 = new('i', n); y0 = new('i', n); over = []; npage = 0
    def shelf(idx, pg):
        idx = sorted(idx, key=lambda i_: (-h[i_], -w[i_])); cx = cy = 0; rowh = 0; out = []
        for i in idx:
            if cx + w[i] > PAGE: cx = 0; cy += rowh; rowh = 0
            if cy + h[i] > PAGE: out.append(i); continue
            page[i] = pg; x0[i] = cx; y0[i] = cy; cx += w[i]; rowh = max(rowh, h[i])
        return out
    for bn in bins:
        if not bn: continue
        npage += 1; over += shelf(bn, npage)
    while over: npage += 1; over = shelf(over, npage)
    return page, x0, y0, nu, nv
page, x0, y0, nu, nv = pack(lu_r.tolist(), lv_r.tolist(), d_r.tolist(), grp_r.tolist(), un_r.tolist()); npg = max(page); ntot = sum(a_ * b_ for a_, b_ in zip(nu, nv))
combos = len(set(zip(grp_r.tolist(), page.tolist()))); assert min(page) >= 1; fill_ = float(sum(((a_ + 3) // 4 * 4) * ((b_ + 3) // 4 * 4) for a_, b_ in zip(nu, nv))) / (npg * PAGE * PAGE)
print('texels %.1f million on %d pages, %.0f%% of them used (%s) ; %.0f texels a metre within %.0f m of the road ; material x page combinations %d (materials %d)' % (ntot / 1e6, npg, 100 * fill_, 'FAST' if FAST else 'slow', NEAR, REACH, combos, len(set(grp_r))), flush=True)
if os.environ.get('RTG_PACK_ONLY'): raise SystemExit(0)
# ---------------------------------------------------------------- the light
SUN_DEG = 3.0; KS = int(os.environ.get('RTG_KS', 16 if FAST else 32)); TURNS = int(os.environ.get('RTG_TURNS', 1 if FAST else 3))      # sky rays a texel = KS x TURNS (96 in the slow bake) ; RTG_KS / RTG_TURNS: to try fewer
st, sb = frame(SUN); rad = math.radians(SUN_DEG / 2); SD = [SUN]
for ring, cnt in (((1.0, 6),) if FAST else ((0.5, 6), (1.0, 12))):
    for k in range(cnt):
        a = 2 * math.pi * (k + 0.5 * (ring < 1)) / cnt; d = [SUN[i] + math.tan(rad * ring) * (math.cos(a) * st[i] + math.sin(a) * sb[i]) for i in range(3)]; SD.append([c_ / nrm(d) for c_ in d])
HEMI = [(math.sqrt((i + 0.5) / KS) * math.cos(i * 2.399963), math.sqrt((i + 0.5) / KS) * math.sin(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / KS))) for i in range(KS)]
FOOT = [(0.0, 0.0)] + [((0.5 + j * 0.7548776662466927) % 1.0 - 0.5, (0.5 + j * 0.5698402909980532) % 1.0 - 0.5) for j in range(1, len(SD))]
SUNc = array('d', SUN); DESc = array('d', design); TNS = new('d', NTA); TND = new('d', NTA); LIB.rp_dot3(NTA, ad(TN), ad(SUNc), ad(TNS)); LIB.rp_dot3(NTA, ad(TN), ad(DESc), ad(TND))      # TN @ SUN, TN @ design
ALBc = array('d', alb); SDc = array('d', flat([SD])); HEMIc = array('d', flat([HEMI])); FOOTc = array('d', flat([FOOT])); STATS = [0] * 5; RFIRST = array('i', first_r)
RM = array('d', [v_ for a_, b_ in zip(lu_r, lv_r) for v_ in (min(INSET / max(a_, 1e-6), 0.2), min(INSET / max(b_, 1e-6), 0.2))])
def light(o, ri, iu, iv, k0, m, side):
    """lm5_light (rtg5.c) on m texels: -> o[...] sun seen, sky seen, colour coming back, the normal at the point used, the polygon it lies on"""
    V, A, B, NO, PO, CA, SA = o; st_ = new('q', 5); LIB.rp_angles(m, ad(k0), TURNS, ad(CA), ad(SA))      # the fan turns (rtg5prep.c)
    LIB.lm5_light(sc.x, MODE, m, ad(ri), ad(iu), ad(iv), ad(nu), ad(nv), ad(tri_r), ad(RM), ad(pn_r), ad(roff), ad(RFIRST), ad(CELL), ad(P), ad(ABp), ad(tri_p), float(side), ad(CA), ad(SA), TURNS,
                  ad(TN), ad(TNS), ad(TND), ad(TMA), ad(TONE), ad(ALBc), ad(SUNc), ad(SDc), len(SD), ad(FOOTc), ad(HEMIc), KS, LIFT, 1.0, ad(V), ad(A), ad(B), ad(NO), ad(PO), ad(st_))
    for j in range(5): STATS[j] += st_[j]
RAW = bytearray(bytes((255, 255, 0, 0, 0, 255, 255))) * ((npg + 1) * PAGE * PAGE); RAWp = ctypes.addressof((ctypes.c_char * len(RAW)).from_buffer(RAW)); ntex = 0      # np.zeros((npg + 1, PAGE, PAGE, 7)) ; channels 0, 1, 5, 6 = 255
order = array('q', sorted(range(nrect), key=page.__getitem__)); t1 = time.time()      # np.argsort(page, kind='stable')
cnt_o = [nu[r_] * nv[r_] for r_ in order]; csum = list(itertools.accumulate(cnt_o)); cuts = [0]
while cuts[-1] < len(order): cuts.append(max(bisect.bisect_right(csum, csum[cuts[-1]] - cnt_o[cuts[-1]] + 250000), cuts[-1] + 1))      # np.searchsorted(csum, ..., side='right')
btot = lambda bi: csum[cuts[bi + 1] - 1] - csum[cuts[bi]] + cnt_o[cuts[bi]]      # the texels of batch bi
TM_.clear(); nlit = 0
if os.environ.get('RTG_DUMP'):                                        # what lm5_light is given and the texels of every k-th batch: for the ray bench (tools/bench_rays.py; nfpickle.load(numpy=True) reads it)
    kk_ = int(os.environ.get('RTG_DUMP_STEP', '20')); smp_ = []; nt_ = 0
    for bi in range(len(cuts) - 1):
        tot_ = btot(bi)
        if bi % kk_ == 0:
            s_ = (new('i', tot_), new('i', tot_), new('i', tot_), new('d', tot_)); LIB.rp_texels(cuts[bi + 1] - cuts[bi], ad(order) + 8 * cuts[bi], ad(nu), ad(nv), nt_, *(ad(x_) for x_ in s_))
            smp_.append(tuple(arr(dt_, (tot_,), x_) for dt_, x_ in zip(('<i4', '<i4', '<i4', '<f8'), s_)))
        nt_ += tot_
    hl_ = [None if hm_ is None else npyio.Arr('|b1', (hm_[0], hm_[1]), bytearray(hm_[2])) for hm_ in holes]; nr_ = (nrect,)
    nfpickle.dump(dict(TA=arr('<f8', (NTA, 3, 3), TA), TMA=arr('<i4', (NTA,), TMA), UVA=arr('<f8', (NTA, 3, 2), UVA), holes=hl_, RNU=arr('<i4', nr_, nu), RNV=arr('<i4', nr_, nv), RTRI=arr('|u1', nr_, tri_r),
                       RM=arr('<f8', (nrect, 2), RM), RPN=arr('<i4', nr_, pn_r), ROFF=arr('<i8', nr_, roff[:-1]), RFIRST=arr('<i4', nr_, RFIRST), CELL=arr('<i4', (len(CELL),), CELL), PQ=arr('<f8', (NPOL, 12), P.buf),
                       PAB=arr('<f8', (NPOL, 8), ABp.buf), PT=arr('|u1', (NPOL,), tri_p), TN=arr('<f8', (NTA, 3), TN), TNS=arr('<f8', (NTA,), TNS), TND=arr('<f8', (NTA,), TND), TONE=arr('|u1', (NTA,), TONE),
                       ALB=arr('<f8', (nm + 3, 3), ALBc), SUN=arr('<f8', (3,), SUNc), SD=arr('<f8', (len(SD), 3), SDc), FOOT=arr('<f8', (len(FOOT), 2), FOOTc), HEMI=arr('<f8', (KS, 3), HEMIc), KS=KS, LIFT=LIFT, TURNS=TURNS,
                       U2=U2, sample=smp_, page=arr('<i4', nr_, page), x0=arr('<i4', nr_, x0), y0=arr('<i4', nr_, y0), nu=arr('<i4', nr_, nu), nv=arr('<i4', nr_, nv), d_r=arr('<f8', nr_, d_r), rinv=arr('<i8', (NPOL,), rinv),
                       TREES=arr('<f8', (len(TREES), 6) if TREES else (0,), array('d', flat([TREES]))), sea_poly=arr('|b1', (NPOL,), sea_poly), Imean=arr('<f8', (NPOL,), Imean), order=arr('<i8', nr_, order),
                       cuts=arr('<i4', (len(cuts),), array('i', cuts))), os.environ['RTG_DUMP'])
    print('ray bench dump: %d batches, %.2f million texels -> %s' % (len(smp_), sum(s_[0].shape[0] for s_ in smp_) / 1e6, os.environ['RTG_DUMP'])); raise SystemExit(0)
MX = max(btot(bi) for bi in range(len(cuts) - 1)); ri, iu, iv, k0 = new('i', MX), new('i', MX), new('i', MX), new('d', MX); ri2, iu2, iv2, k02, sel = new('i', MX), new('i', MX), new('i', MX), new('d', MX), new('q', MX)
L1 = (new('d', MX), new('d', MX), new('d', 3 * MX), new('d', 3 * MX), new('i', MX), new('d', MX * TURNS), new('d', MX * TURNS)); L2 = tuple(array(a_.typecode, a_) for a_ in L1); Fc = new('d', MX); F2 = new('d', MX)
for bi in range(len(cuts) - 1):
    tot_ = btot(bi)
    if bi % STEP != OFF: ntex += tot_; continue
    q0 = time.perf_counter(); LIB.rp_texels(cuts[bi + 1] - cuts[bi], ad(order) + 8 * cuts[bi], ad(nu), ad(nv), ntex, ad(ri), ad(iu), ad(iv), ad(k0)); TM_['texel maths'] += time.perf_counter() - q0      # (rtg5prep.c quotes the numpy lines)
    q0 = time.perf_counter(); light(L1, ri, iu, iv, k0, tot_, 1.0); TM_['light, winding side'] += time.perf_counter() - q0; TM_['texels'] += tot_; LIB.rp_facing(tot_, ad(L1[3]), ad(SUNc), ad(DESc), ad(Fc))
    nu_ = LIB.rp_pick(tot_, ad(L1[4]), ad(U2), ad(ri), ad(iu), ad(iv), ad(k0), ad(sel), ad(ri2), ad(iu2), ad(iv2), ad(k02))      # u = U2[PO]
    if nu_:
        q0 = time.perf_counter(); light(L2, ri2, iu2, iv2, k02, nu_, -1.0); TM_['light, other side'] += time.perf_counter() - q0; TM_['texels other side'] += nu_; LIB.rp_facing(nu_, ad(L2[3]), ad(SUNc), ad(DESc), ad(F2))
        LIB.rp_merge(nu_, ad(sel), ad(L1[0]), ad(L1[1]), ad(L1[2]), ad(Fc), ad(L2[0]), ad(L2[1]), ad(L2[2]), ad(F2))      # the brighter side kept
    q0 = time.perf_counter(); LIB.rp_store(tot_, ad(ri), ad(iu), ad(iv), ad(L1[4]), ad(sea_poly), ad(Imean), ad(L1[0]), ad(L1[1]), ad(L1[2]), ad(Fc), ad(page), ad(x0), ad(y0), PAGE, RAWp)
    ntex += tot_; nlit += tot_; TM_['store'] += time.perf_counter() - q0
    if bi % 20 == 0: print('  %d%% (%.1f of %.1f million texels), %.0f s' % (100 * ntex // ntot, ntex / 1e6, ntot / 1e6, time.time() - t1), flush=True)
t2 = time.time(); nu64 = array('q', nu); nv64 = array('q', nv)
LIB.lm2_smooth(RAWp, PAGE, nrect, ad(page), ad(x0), ad(y0), ad(nu64), ad(nv64))             # once per RECTANGLE: the 3 x 3 smoothing of sky and colour and its growth to whole 4 x 4 blocks (rtg2.c)
t3 = time.time(); npyio.save(OUT + '.raw.npy', npyio.Arr('|u1', (npg, PAGE, PAGE, 7), memoryview(RAW)[PAGE * PAGE * 7:]))      # np.save(OUT + '.raw.npy', RAW[1:])
pp_ = tuple(new('i', NPOL) for _ in range(5)) + (new('d', NPOL),); LIB.rp_perpoly(NPOL, ad(rinv), ad(page), ad(x0), ad(y0), ad(nu), ad(nv), ad(d_r), *(ad(x_) for x_ in pp_)); np_ = (NPOL,)
npyio.savez(OUT + '.pack.npz', page=arr('<i4', np_, pp_[0]), x0=arr('<i4', np_, pp_[1]), y0=arr('<i4', np_, pp_[2]), nu=arr('<i4', np_, pp_[3]), nv=arr('<i4', np_, pp_[4]), ab=ABp, droad=arr('<f8', np_, pp_[5]),
            rect=arr('<i8', np_, rinv), trees=arr('<f8', (len(TREES), 6), array('d', flat([TREES]))))      # per POLYGON, as the importer's table wants it: its rectangle, and where its corners are in it
print('RTG5 %d polygons in %d rectangles, %.1f million texels, %d pages ; rays %.0f s, all %.0f s' % (NPOL, nrect, ntex / 1e6, npg, time.time() - t1, time.time() - t0))
print('TIMES lit texels %.2f million ; batches %.1f s ; smoothing %.1f s ; save %.1f s ; %s ; rays %.0f million ; texels moved in front of a wall they stood behind %d ; texels with something crossing their square %d'
      % (nlit / 1e6, t2 - t1, t3 - t2, time.time() - t3, {k: round(v, 1) for k, v in TM_.items()}, STATS[0] / 1e6, STATS[3], STATS[4]))
