"""The light of a sample of texels with one build of the ray code: seconds, rays, and a hash of every number it gives.
    python bench_rays.py <dump.pkl (rt_bake_game5.py with RTG_DUMP)> <folder with rays.c fastlm_rays.c rtg2_rays.c rtg5.c> [mode] [save.npz]
    BENCH_FLAGS_A / BENCH_FLAGS_B   extra compiler flags for the ray file / for rtg5.c ; BENCH_MAX = how many of the sample's batches"""
import sys, os, pickle, time, ctypes, subprocess, hashlib, math
import numpy as np
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))); import nfpickle      # tools/import/core
D = nfpickle.load(sys.argv[1], numpy=True); SRC = os.path.abspath(sys.argv[2]); MODE = int(sys.argv[3]) if len(sys.argv) > 3 else 1; SAVE = sys.argv[4] if len(sys.argv) > 4 else None
GCC = r'C:\mingw64\bin\gcc.exe'; FA = os.environ.get('BENCH_FLAGS_A', '').split(); FB = os.environ.get('BENCH_FLAGS_B', '').split()
srcs = [os.path.join(SRC, f) for f in ('rays.c', 'fastlm_rays.c', 'rtg2_rays.c', 'rtg5.c')]; h = hashlib.md5(' '.join(FA + ['|'] + FB).encode())
for f in srcs: h.update(open(f, 'rb').read())
dll = os.path.join(SRC, 'bench.%s.dll' % h.hexdigest()[:8])
if not os.path.exists(dll):
    oa = dll + '.a.o'; ob = dll + '.b.o'
    for cmd in ([GCC, '-O3', '-march=native', '-fopenmp'] + FA + ['-c', '-o', oa, srcs[2]], [GCC, '-O3', '-march=native', '-ffp-contract=off', '-fopenmp'] + FB + ['-c', '-o', ob, srcs[3]], [GCC, '-shared', '-fopenmp', '-o', dll, oa, ob]):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=SRC)
        if r.returncode != 0: raise SystemExit('does not compile: ' + r.stderr[-3000:])
    os.remove(oa); os.remove(ob)
os.add_dll_directory(os.path.dirname(GCC)); L = ctypes.CDLL(dll); Pv = ctypes.c_void_p; LL = ctypes.c_longlong; Dd = ctypes.c_double; Ii = ctypes.c_int
L.rt_build.restype = Pv; L.rt_build.argtypes = [Pv, Ii]; L.rt_masks.argtypes = [Pv] * 3 + [Ii] + [Pv] * 4; L.rx_open.restype = Pv; L.rx_open.argtypes = [Pv, Ii]
L.lm5_light.argtypes = [Pv, Ii, LL] + [Pv] * 14 + [Dd, Pv, Pv, Ii] + [Pv] * 8 + [Ii, Pv, Pv, Ii, Dd, Dd] + [Pv] * 6
_d = lambda a: np.ascontiguousarray(a, np.float64); _p = lambda a: a.ctypes.data_as(ctypes.c_void_p); _i = lambda a, t: np.ascontiguousarray(a, t)
t0 = time.perf_counter(); TA = _d(D['TA']).reshape(-1, 9); hs = L.rt_build(_p(TA), len(TA)); holes = D['holes']
tm = np.ascontiguousarray(D['TMA'], np.int32); tu = _d(D['UVA']).reshape(-1, 6); n = len(holes); w = np.zeros(n, np.int32); hh = np.zeros(n, np.int32); off = np.full(n, -1, np.int64); parts = []; pos = 0
for m, hm in enumerate(holes):
    if hm is None: continue
    hm = np.ascontiguousarray(hm, np.uint8); hh[m], w[m] = hm.shape; off[m] = pos; parts.append(hm.ravel()); pos += hm.size
bits = np.concatenate(parts) if parts else np.zeros(1, np.uint8); L.rt_masks(hs, _p(tm), _p(tu), n, _p(w), _p(hh), _p(off), _p(bits)); X = L.rx_open(hs, 1); tb = time.perf_counter() - t0
TURNS = D['TURNS']; KS = D['KS']; STATS = np.zeros(5, np.int64); U2 = D['U2']
def light(ri, iu, iv, k0, side):
    m = len(ri); ri = _i(ri, np.int32); iu = _i(iu, np.int32); iv = _i(iv, np.int32); CA = np.empty((m, TURNS)); SA = np.empty((m, TURNS)); st_ = np.zeros(5, np.int64)
    for turn in range(TURNS):
        ang = ((k0 + turn / TURNS) * 0.618034) % 1.0 * 2 * math.pi; CA[:, turn] = np.cos(ang); SA[:, turn] = np.sin(ang)
    V = np.empty(m); sky = np.empty(m); back = np.empty((m, 3)); NO = np.empty((m, 3)); PO = np.empty(m, np.int32)
    L.lm5_light(X, MODE, m, _p(ri), _p(iu), _p(iv), _p(D['RNU']), _p(D['RNV']), _p(D['RTRI']), _p(D['RM']), _p(D['RPN']), _p(D['ROFF']), _p(D['RFIRST']), _p(D['CELL']), _p(D['PQ']), _p(D['PAB']), _p(D['PT']), float(side), _p(CA), _p(SA), TURNS,
                _p(D['TN']), _p(D['TNS']), _p(D['TND']), _p(tm), _p(D['TONE']), _p(D['ALB']), _p(D['SUN']), _p(D['SD']), len(D['SD']), _p(D['FOOT']), _p(D['HEMI']), KS, D['LIFT'], 1.0, _p(V), _p(sky), _p(back), _p(NO), _p(PO), _p(st_))
    STATS[:] += st_; return V, sky, back, NO, PO
hx = hashlib.sha1(); out = []; tl = 0.0; ntx = 0
for ri, iu, iv, k0 in D['sample'][int(os.environ.get('BENCH_SKIP', '0')):][:int(os.environ.get('BENCH_MAX', '999'))]:
    q0 = time.perf_counter(); R1 = light(ri, iu, iv, k0, 1.0); u = U2[R1[4]]; R2 = light(ri[u], iu[u], iv[u], k0[u], -1.0) if u.any() else (); tl += time.perf_counter() - q0; ntx += len(ri) + int(u.sum())
    for a in R1 + tuple(R2): hx.update(np.ascontiguousarray(a).tobytes())
    if SAVE: out.append(R1 + tuple(R2))
print('%-28s mode %d : scene %.1f s ; %.2f million texel sides, %.0f million rays, %.2f s (%.1f million rays a second) ; fell %d quick %d ; %s' % (os.path.basename(SRC.rstrip('/\\')) + ' ' + ' '.join(FA), MODE, tb, ntx / 1e6, STATS[0] / 1e6, tl, STATS[0] / 1e6 / tl, STATS[1], STATS[2], hx.hexdigest()[:16]), flush=True)
if SAVE: pickle.dump(out, open(SAVE, 'wb'), protocol=4)
if hasattr(L, 'rx_counts'):
    c = np.zeros(8, np.int64); L.rx_counts(_p(c)); r = max(int(STATS[0]), 1)
    print('   per ray: %.1f four-box nodes looked at (%.1f boxes), %.2f leaves, %.2f triangles tested, %.3f hole look-ups ; walks: nearest %.2f, any %.2f, reference %.4f' % (c[1] / r, c[0] / r, c[2] / r, c[3] / r, c[4] / r, c[5] / r, c[6] / r, c[7] / r))
