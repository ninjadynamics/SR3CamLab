"""rays.py - the importer's ray caster (rays.c, compiled with gcc on first use): triangles in a BVH, rays on every core.

    S = rays.Scene(tris)                      tris (m, 3, 3)
    S.masks(tri_mat, tri_uv, holes)           optional: holes[material] = bool picture (True = see-through) or None
    hit, t = S.cast(org, dir, tmax)           n rays
    hit, t = S.fan(P, N, fan, turn=None, lift=0.03, skip=0.12, tmax=600.0)      k directions from every point, in its own frame (z = N)
"""
import os, ctypes, subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.join(HERE, 'rays.c'); DLL = os.path.join(HERE, 'rays.dll'); GCC = r'C:\mingw64\bin\gcc.exe'
_lib = None
def lib():
    global _lib
    if _lib is None:
        # One file per version of the source (as fastgeo.py). It used to be rays.dll, rebuilt when older than rays.c: but Windows will not replace a
        # DLL that a running build has loaded, and the build that had asked for the new source then loaded the OLD rays.dll without a word
        # (shown 2026-10-08 with two processes). rays.dll itself is left alone: builds started before this change still hold it.
        import hashlib
        dll = os.path.join(HERE, 'rays.%s.dll' % hashlib.md5(open(SRC, 'rb').read()).hexdigest()[:8])
        if not os.path.exists(dll):
            tmp = dll + '.%d.tmp' % os.getpid(); r = subprocess.run([GCC, '-O3', '-march=native', '-fopenmp', '-shared', '-o', tmp, SRC], capture_output=True, text=True)
            if r.returncode != 0: raise RuntimeError('rays.c does not compile: ' + r.stderr[-800:])
            try: os.replace(tmp, dll)
            except OSError: os.remove(tmp)                                # (another build got there first and has it loaded)
        os.add_dll_directory(os.path.dirname(GCC)); L = ctypes.CDLL(dll); P = ctypes.c_void_p; LL = ctypes.c_longlong; D = ctypes.c_double; I = ctypes.c_int
        L.rt_build.restype = P; L.rt_build.argtypes = [P, I]; L.rt_free.argtypes = [P]; L.rt_masks.argtypes = [P, P, P, I, P, P, P, P]
        L.rt_cast.argtypes = [P, P, P, LL, D, P, P]; L.rt_fan.argtypes = [P, P, P, LL, P, I, P, D, D, D, P, P]; L.rt_threads.restype = I
        _lib = L
    return _lib

def _d(a): return np.ascontiguousarray(a, np.float64)
def _p(a): return a.ctypes.data_as(ctypes.c_void_p)

class Scene:
    def __init__(self, tris):
        self.tris = _d(tris).reshape(-1, 9); self.h = lib().rt_build(_p(self.tris), len(self.tris)); self.keep = []
    def __del__(self):
        try:
            if self.h: lib().rt_free(self.h); self.h = None
        except Exception: pass
    def masks(self, tri_mat, tri_uv, holes):
        tm = np.ascontiguousarray(tri_mat, np.int32); tu = _d(tri_uv).reshape(-1, 6); n = len(holes); w = np.zeros(n, np.int32); h = np.zeros(n, np.int32); off = np.full(n, -1, np.int64); parts = []; pos = 0
        for m, hm in enumerate(holes):
            if hm is None: continue
            hm = np.ascontiguousarray(hm, np.uint8); h[m], w[m] = hm.shape; off[m] = pos; parts.append(hm.ravel()); pos += hm.size
        bits = np.concatenate(parts) if parts else np.zeros(1, np.uint8); self.keep = [tm, tu, w, h, off, bits]
        lib().rt_masks(self.h, _p(tm), _p(tu), n, _p(w), _p(h), _p(off), _p(bits))
    def cast(self, org, dir, tmax=600.0):
        o = _d(org).reshape(-1, 3); d = _d(dir).reshape(-1, 3); n = len(o); hit = np.empty(n, np.int32); t = np.empty(n, np.float64)
        lib().rt_cast(self.h, _p(o), _p(d), n, float(tmax), _p(hit), _p(t)); return hit, t
    def fan(self, P, N, fan, turn=None, lift=0.03, skip=0.12, tmax=600.0):
        p = _d(P).reshape(-1, 3); n = _d(N).reshape(-1, 3); f = _d(fan).reshape(-1, 3); k = len(f); hit = np.empty(len(p) * k, np.int32); t = np.empty(len(p) * k, np.float64)
        tr = None if turn is None else _d(turn)
        lib().rt_fan(self.h, _p(p), _p(n), len(p), _p(f), k, None if tr is None else _p(tr), float(lift), float(skip), float(tmax), _p(hit), _p(t))
        return hit.reshape(-1, k), t.reshape(-1, k)
