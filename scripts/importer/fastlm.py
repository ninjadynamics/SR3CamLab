"""fastlm.py - the two ray-heavy loops of the importer in C (fastlm.c + fastlm_rays.c, compiled with gcc on first use like fastgeo.py):

    bake(LM, path, mode, strength, shade, log)      lightmap1995.bake: texel positions, sun / sky / bounce rays, the pages (was 85 s, numpy)
    roadsight(sc, cen, S1, S2, nrm, C, E, per, reach)      roadsight.orient: the rays from the road to every polygon (was 20 s)
    Scene(tris), .masks(...), .cast(...)            rays.Scene on this DLL (fastlm_rays.c includes rays.c: the same tree, the same cast_one)

Nothing here decides anything new; the old code stays in lightmap1995._old_bake and roadsight._old_orient and is the reference.

    SR3_FASTGEO=0 or SR3_FASTLM=0     the callers use their old Python code (and sbfw.py keeps no unpacked files)
    SR3_FASTLM_ORDERED=0              every ray goes through rays.c's own walk (cast_one); the C loops stay (bake 12 s instead of 7; no assumption at all)
    SR3_FASTLM_TREE=0                 the quick walks keep rays.c's own splits (four boxes to a node either way)
    SR3_FASTGEO_CHECK=1 or SR3_FASTLM_CHECK=1      old and new both run, the OLD result is used, differences are counted (fastgeo.REPORT)

What 'the same' rests on is written at the top of fastlm.c (numpy's formulas, and the one BLAS product that numpy does not pin down)
and of fastlm_rays.c (why another tree over the same leaves reaches the same leaves, and the one assumption the nearest-hit walks make).
selftest(path) compares the walks with rays.dll on the rays of a real bake, bit for bit.
Measured 2026-10-08, Mountain: pages / table / all nine built files the bytes of the old code; bake 85 s -> 7 s, roadsight 21 s -> 2 s."""
import os, sys, ctypes, subprocess, hashlib, glob, math, time, pickle, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); GCC = r'C:\mingw64\bin\gcc.exe'
SRCS = [os.path.join(HERE, f) for f in ('rays.c', 'fastlm_rays.c', 'fastlm.c')]
ON = os.environ.get('SR3_FASTGEO', '1') != '0' and os.environ.get('SR3_FASTLM', '1') != '0'
ORDERED = os.environ.get('SR3_FASTLM_ORDERED', '1') != '0'
TREE = os.environ.get('SR3_FASTLM_TREE', '1') != '0'                     # the quick walks' tree over the leaves of rays.c's is split by surface area (fastlm_rays.c, point 1); 0: rays.c's own splits, four to a node
CHECK = os.environ.get('SR3_FASTGEO_CHECK', '0') == '1' or os.environ.get('SR3_FASTLM_CHECK', '0') == '1'
MAX_DEPTH = 90                                                          # rays.c's stack holds 96 nodes: a deeper tree loses triangles there, and only the same walk loses the same ones

def note(name, same, detail=None):
    import fastgeo
    if not fastgeo.CHECK and CHECK and not getattr(note, 'reg', False):  # (SR3_FASTLM_CHECK alone: fastgeo's report is not printed, so print it)
        import atexit; note.reg = True; atexit.register(lambda: print('fastlm check: %s' % {k: v for k, v in sorted(fastgeo.REPORT.items())}, *['\n   fastlm difference: %s %s' % (e[0], str(e[1])[:600]) for e in fastgeo.EXAMPLES]))
    fastgeo.note(name, same, detail)

_lib = None
def lib():
    global _lib
    if _lib is None:
        h = hashlib.md5()
        for s in SRCS: h.update(open(s, 'rb').read())
        DLL = os.path.join(HERE, 'fastlm.%s.dll' % h.hexdigest()[:8])   # one file per version of the three sources (as fastgeo.py: a running build keeps its own)
        if not os.path.exists(DLL):
            tmp = DLL + '.%d.tmp' % os.getpid(); td = tempfile.mkdtemp(prefix='fastlm_'); oa = os.path.join(td, 'a.o'); ob = os.path.join(td, 'b.o')
            try:
                for cmd in ([GCC, '-O3', '-march=native', '-fopenmp', '-c', '-o', oa, SRCS[1]],                              # rays.c with the flags rays.py gives it
                            [GCC, '-O3', '-march=native', '-ffp-contract=off', '-fopenmp', '-c', '-o', ob, SRCS[2]],         # numpy's arithmetic: no fused multiply-add
                            [GCC, '-shared', '-fopenmp', '-o', tmp, oa, ob]):
                    r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
                    if r.returncode != 0: raise RuntimeError('fastlm does not compile: ' + r.stderr[-1500:])
                try: os.replace(tmp, DLL)
                except OSError: os.remove(tmp)                            # (another build got there first and has it loaded)
            finally:
                for f in (oa, ob):
                    try: os.remove(f)
                    except OSError: pass
                try: os.rmdir(td)
                except OSError: pass
            for old in glob.glob(os.path.join(HERE, 'fastlm.*.dll')):    # versions nobody has loaded any more
                if old != DLL:
                    try: os.remove(old)
                    except OSError: pass
        os.add_dll_directory(os.path.dirname(GCC)); L = ctypes.CDLL(DLL); P = ctypes.c_void_p; LL = ctypes.c_longlong; D = ctypes.c_double; I = ctypes.c_int
        L.rt_build.restype = P; L.rt_build.argtypes = [P, I]; L.rt_free.argtypes = [P]; L.rt_masks.argtypes = [P, P, P, I, P, P, P, P]; L.rt_cast.argtypes = [P, P, P, LL, D, P, P]
        L.rx_depth.argtypes = [P]; L.rx_depth.restype = I; L.rx_depth2.argtypes = [P]; L.rx_depth2.restype = I; L.rx_nodes.argtypes = [P]; L.rx_nodes.restype = I; L.rx_cast.argtypes = [P, I, P, P, LL, D, P, P, P]; L.rx_cast.restype = None
        L.rx_open.argtypes = [P, I]; L.rx_open.restype = P; L.rx_close.argtypes = [P]; L.rx_close.restype = None
        L.lm_init.restype = I; L.lm_threads.restype = I
        if not L.lm_init(): raise RuntimeError('fastlm: sin / cos / fmod of ucrtbase.dll not found (numpy uses them; without them the fans would turn by other angles in the last bit)')
        L.lm_bake.argtypes = [P, I, P, P, P, P, P, P, P, P, P, P, LL, P, P, P, I, P, P, I, P, I, I, D, D, P, I, P]; L.lm_bake.restype = LL
        L.lm_light.argtypes = [P, I, P, P, P, LL, P, P, P, I, P, P, I, P, I, P, P, P, P]; L.lm_light.restype = LL
        L.lm_roadsight.argtypes = [P, I, P, P, P, P, LL, P, LL, P, I, D, P, P, P]; L.lm_roadsight.restype = LL
        _lib = L
    return _lib

def _d(a): return np.ascontiguousarray(a, np.float64)
def _p(a): return a.ctypes.data_as(ctypes.c_void_p)

class Scene:
    """rays.Scene, on this DLL. .depth = the deepest leaf of the tree ; .ordered = the quicker walks may be used"""
    def __init__(self, tris):
        self.x = None; self.tris = _d(tris).reshape(-1, 9); self.h = lib().rt_build(_p(self.tris), len(self.tris)); self.keep = []
        self.x = lib().rx_open(self.h, 1 if TREE else 0)                 # .h: the scene of rays.c (rt_ functions) ; .x: that scene + the tree of the quick walks (rx_ / lm_ functions)
        if not self.x: raise MemoryError('fastlm.Scene')
        self.depth = int(lib().rx_depth(self.x)); self.depth2 = int(lib().rx_depth2(self.x)); self.ordered = bool(ORDERED and self.depth < MAX_DEPTH and self.depth2 < 100)      # (the quick walks' own stack: 512 boxes, three waiting at every level)
    def __del__(self):
        try:
            if self.x: lib().rx_close(self.x); self.x = None
            if self.h: lib().rt_free(self.h); self.h = None
        except Exception: pass
    def masks(self, tri_mat, tri_uv, holes):
        tm = np.ascontiguousarray(tri_mat, np.int32); tu = _d(tri_uv).reshape(-1, 6); n = len(holes); w = np.zeros(n, np.int32); h = np.zeros(n, np.int32); off = np.full(n, -1, np.int64); parts = []; pos = 0
        for m, hm in enumerate(holes):
            if hm is None: continue
            hm = np.ascontiguousarray(hm, np.uint8); h[m], w[m] = hm.shape; off[m] = pos; parts.append(hm.ravel()); pos += hm.size
        bits = np.concatenate(parts) if parts else np.zeros(1, np.uint8); self.keep = [tm, tu, w, h, off, bits]
        lib().rt_masks(self.h, _p(tm), _p(tu), n, _p(w), _p(h), _p(off), _p(bits))
    def cast(self, org, dir, tmax=600.0, how=0, limits=None):
        """how 0: cast_one (= rays.Scene.cast) ; 1: rx_near ; 2: rx_nearer with a limit per ray (hit 0 = something nearer than the limit, -1 = nothing) ; 3: rx_any (hit 0 / -1).  -> hit, t, rays handed back to cast_one"""
        o = _d(org).reshape(-1, 3); d = _d(dir).reshape(-1, 3); n = len(o); hit = np.empty(n, np.int32); t = np.empty(n, np.float64) if limits is None else _d(limits).copy(); fell = ctypes.c_longlong(0)
        lib().rx_cast(self.x, how, _p(o), _p(d), n, float(tmax), _p(hit), _p(t), ctypes.byref(fell)); return hit, t, fell.value

# ---------------------------------------------------------------- lightmap1995
def sun_fans(SUN):
    """the directions of lightmap1995._light (the same expressions): 7 round the sun, 16 over the half space"""
    def frame(n):
        ax = np.where((np.abs(n[:, 1]) < 0.9)[:, None], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]); t = np.cross(n, ax); t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]; return t, np.cross(n, t)
    st, sb = frame(SUN[None]); R = math.radians(1.6); SD = [SUN] + [SUN + math.tan(R) * (math.cos(a) * st[0] + math.sin(a) * sb[0]) for a in np.arange(6) * math.pi / 3]; SD = np.array([d / np.linalg.norm(d) for d in SD])
    KS = 16; HEMI = np.array([(math.sqrt((i + 0.5) / KS) * math.cos(i * 2.399963), math.sqrt((i + 0.5) / KS) * math.sin(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / KS))) for i in range(KS)])
    return _d(SD), _d(HEMI)

class Lights:
    """what the texels are lit with: the scene's tree, its triangle normals and colours, the sun (all as lightmap1995._light makes them)"""
    def __init__(self, S):
        T = S['tris'].astype(float); self.sc = Scene(T); self.sc.masks(S['mat'], S['uv'], S['holes'])
        TN = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); TN /= np.maximum(np.linalg.norm(TN, axis=1), 1e-12)[:, None]; self.TN = _d(TN); self.TM = np.ascontiguousarray(S['mat'], np.int32)
        self.alb = _d(np.asarray(S['albedo_rgb'], float)).reshape(-1, 3); SUN = np.asarray(S['sun'], float); self.SUN = _d(SUN / np.linalg.norm(SUN)); self.SD, self.HEMI = sun_fans(self.SUN)
        self.exact_dot = bool((self.SUN == 0).any())                     # (n, 3) @ sun: numpy's own order of adding is only certain when one component is 0 (fastlm.c)
        if len(self.TM) and (int(self.TM.min()) < 0 or int(self.TM.max()) >= len(self.alb)): raise ValueError('fastlm: a triangle with a material the scene does not have')
    def args(self): return [_p(self.TN), _p(self.TM), _p(self.alb), len(self.alb), _p(self.SUN), _p(self.SD), len(self.SD), _p(self.HEMI), len(self.HEMI)]
    def light(self, P, N, K0):
        """lightmap1995._light(sc, S, P, N, K0, alb) -> V, A, B"""
        P = _d(P).reshape(-1, 3); N = _d(N).reshape(-1, 3); K0 = _d(K0); n = len(P); V = np.zeros(n); A = np.zeros(n); B = np.zeros((n, 3)); fell = ctypes.c_longlong(0)
        self.nray = lib().lm_light(self.sc.x, 1 if self.sc.ordered else 0, _p(P), _p(N), _p(K0), n, *self.args(), _p(V), _p(A), _p(B), ctypes.byref(fell)); self.fell = fell.value
        return V, A, B

def pack(LM, P, centre, near=3.0, far=0.75, reach=60.0):
    """lightmap1995.pack: the same numbers (the distance from the road on every core, the shelves on plain Python numbers)"""
    import fastgeo
    PAGE, MAXC = LM.PAGE, LM.MAXC
    e = lambda a, b: np.linalg.norm(P[:, a] - P[:, b], axis=1); lu = np.maximum(e(1, 0), e(2, 3)); lv = np.maximum(e(3, 0), e(2, 1))
    c = P.mean(1)[:, [0, 2]]; cen = np.asarray(centre, float)[::4]; d = np.sqrt(fastgeo.mindist2(c, cen))
    dens = np.where(d < reach, near, np.where(d < 3 * reach, near * reach / np.maximum(d, 1e-6), far)); dens = np.maximum(dens, far)
    nu = np.clip(np.ceil(lu * dens).astype(int) + 1, 2, MAXC); nv = np.clip(np.ceil(lv * dens).astype(int) + 1, 2, MAXC); w = (nu + 3) // 4 * 4; h = (nv + 3) // 4 * 4
    order = np.lexsort((-w, -h)); n = len(P); pl = [0] * n; xl = [0] * n; yl = [0] * n; pg = 1; cx = cy = 0; rowh = 0; wl = w.tolist(); hl = h.tolist()
    for i in order.tolist():                                            # shelves: tallest first
        wi = wl[i]; hi = hl[i]
        if cx + wi > PAGE: cx = 0; cy += rowh; rowh = 0
        if cy + hi > PAGE: pg += 1; cx = cy = 0; rowh = 0
        pl[i] = pg; xl[i] = cx; yl[i] = cy; cx += wi
        if hi > rowh: rowh = hi
    return np.array(pl, np.int32).reshape(n), np.array(xl, np.int32).reshape(n), np.array(yl, np.int32).reshape(n), nu, nv

def bake(LM, path, mode='rt', strength=1.0, shade=0.33, log=print):
    """lightmap1995.bake (LM = that module): the same two files.  None = this code cannot take the input (the caller runs the old code)"""
    t0 = time.time(); D = np.load(path + '.lm.npz'); P = D['P'].astype(float); N = D['N'].astype(float); I = D['I'].astype(float); U = D['U'].astype(bool); S = pickle.load(open(path + '.scene', 'rb'))
    if not len(P) or P.shape[1:] != (4, 3) or I.shape != (len(P), 4): return None
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]
    page, x0, y0, nu, nv = pack(LM, P, S['centre']); npg = int(page.max()); PAGE = LM.PAGE
    if CHECK:
        o = LM.pack(P, S['centre']); note('lightmap1995.pack', all(np.array_equal(a, b) and a.dtype == b.dtype for a, b in zip(o, (page, x0, y0, nu, nv))))
    Lg = Lights(S); pages = np.full((npg + 1, PAGE, PAGE, 3), 255, np.uint8); order = np.argsort(page, kind='stable'); cnt = (nu * nv).astype(np.int64)
    k0 = np.zeros(len(P), np.int64); k0[order] = np.cumsum(cnt[order]) - cnt[order]; ntex = int(cnt.sum())      # texels are numbered in the order the old loop lights them: page by page
    Pc = _d(P).reshape(-1, 12); Nc = _d(N); Ic = _d(I); Uc = np.ascontiguousarray(U, np.uint8); a32 = lambda a: np.ascontiguousarray(a, np.int32); pg_, x0_, y0_, nu_, nv_ = a32(page), a32(x0), a32(y0), a32(nu), a32(nv); fell = ctypes.c_longlong(0)
    nray = lib().lm_bake(Lg.sc.x, 1 if Lg.sc.ordered else 0, _p(Pc), _p(Nc), _p(Ic), _p(Uc), _p(pg_), _p(x0_), _p(y0_), _p(nu_), _p(nv_), _p(k0), len(P), *Lg.args(),
                         1 if mode == 'rt' else 0, float(strength), float(shade), _p(pages), PAGE, ctypes.byref(fell))
    np.save(path + '.lm.pages.npy', pages[1:]); np.savez(path + '.lm.table.npz', K=LM.key(P), page=page, x0=x0, y0=y0, nu=nu, nv=nv)
    m = pages[1:].reshape(-1, 3); log('light maps (%s): %d polygons, %.1f million texels on %d pages of %d x %d, lit in %.1f s ; mean value %.2f ; texels darker than half: %.0f%%' % (mode, len(P), ntex / 1e6, npg, PAGE, PAGE, time.time() - t0, float(m.mean()) / 255, 100.0 * (m.max(1) < 128).mean()))
    log('       (fastlm.c: %.0f million rays on %d threads ; tree %d levels deep, %s ; %s)' % (nray / 1e6, lib().lm_threads(), Lg.sc.depth,
        'quick walks (%s), %d rays handed back to the plain walk' % ('own tree over its leaves, %d levels' % Lg.sc.depth2 if TREE else 'same tree', fell.value) if Lg.sc.ordered else "rays.c's own walk",
        'sun with a zero component: numpy to the last bit' if Lg.exact_dot else 'NOTE the sun has three non-zero components: its products with a normal can differ from numpy (BLAS) in the last bit'))
    return pages

# ---------------------------------------------------------------- roadsight
def roadsight(sc, cen, S1, S2, nrm, C, E, per, reach):
    """roadsight.orient's loop: -> front, back (samples reached on the winding side / the other side per judged polygon), rays cast.  sc = fastlm.Scene"""
    cen = _d(cen); S1 = _d(S1); S2 = _d(S2); nrm = _d(nrm); C = _d(C); E = _d(E); n = len(cen); front = np.zeros(n, np.int32); back = np.zeros(n, np.int32)
    if len(E) != len(C) * per: raise ValueError('fastlm.roadsight: viewpoints')
    fell = ctypes.c_longlong(0)
    nray = lib().lm_roadsight(sc.x, 1 if sc.ordered else 0, _p(cen), _p(S1), _p(S2), _p(nrm), n, _p(C), len(C), _p(E), int(per), float(reach), _p(front), _p(back), ctypes.byref(fell)) if n else 0
    roadsight.fell = fell.value; return front, back, int(nray)

# ---------------------------------------------------------------- the walks against rays.dll
def selftest(path, nmax=40000000, log=print):
    """the rays of a real bake (<path>.lm.npz + .scene: sky fans from the polygons' corners) through rays.dll and through this DLL's three walks, bit for bit"""
    import rays
    D = np.load(path + '.lm.npz'); S = pickle.load(open(path + '.scene', 'rb')); T = S['tris'].astype(float); a = rays.Scene(T); a.masks(S['mat'], S['uv'], S['holes']); Lg = Lights(S); b = Lg.sc
    P = D['P'].astype(float).reshape(-1, 3); N = np.repeat(D['N'].astype(float), 4, axis=0); N /= np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]; k = max(1, nmax // 16); sel = np.linspace(0, len(P) - 1, min(k, len(P))).astype(int); P = P[sel]; N = N[sel]
    def frame(n):
        ax = np.where((np.abs(n[:, 1]) < 0.9)[:, None], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]); t = np.cross(n, ax); t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]; return t, np.cross(n, t)
    t, bb = frame(N); H = Lg.HEMI; d = (t[:, None, :] * H[None, :, 0, None] + bb[:, None, :] * H[None, :, 1, None] + N[:, None, :] * H[None, :, 2, None]).reshape(-1, 3); o = np.repeat(P + N * 0.03, len(H), axis=0) + d * 0.12
    t0 = time.time(); h0, t_0 = a.cast(o, d, 1e9); ta = time.time() - t0; t0 = time.time(); h1, t_1, _ = b.cast(o, d, 1e9, 0); tb = time.time() - t0; t0 = time.time(); h2, t_2, fell = b.cast(o, d, 1e9, 1); tc = time.time() - t0
    t0 = time.time(); h3, _, _ = b.cast(o, d, 1e9, 3); td = time.time() - t0; k3 = np.arange(len(o)) % 5
    lim = np.where(h0 >= 0, t_0, 50.0) * np.choose(k3, [1.0, 0.999999, 1.000001, 1.0 - 1e-9, 1.0 + 1e-9]); h4, _, fell2 = b.cast(o, d, 1e9, 2, lim); want = np.where((h0 >= 0) & (t_0 < lim), 0, -1)      # limits on, just before and just behind the hit
    r = dict(rays=len(o), tree_depth=b.depth, hit_some=int((h0 >= 0).sum()), cast_one_other_hit=int((h1 != h0).sum()), cast_one_other_t=int((t_1 != t_0).sum()), near_other_hit=int((h2 != h0).sum()), near_other_t=int((t_2 != t_0).sum()), near_handed_back=int(fell),
             any_other=int(((h3 >= 0) != (h0 >= 0)).sum()), nearer_other=int((h4 != want).sum()), nearer_handed_back=int(fell2), seconds=dict(rays_dll=round(ta, 2), cast_one=round(tb, 2), near=round(tc, 2), any=round(td, 2)))
    log('fastlm.selftest: %s' % r); return r

if __name__ == '__main__':
    selftest(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40000000)
