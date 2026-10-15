"""fastdxt.py - build_classic.dxt1_rgb in C on every core (fastdxt.c, compiled with gcc on first use, like fastgeo.py).

    SR3_FASTDXT=0         the numpy code is used (to time or compare a build without this module)
    SR3_FASTDXT_CHECK=1   both run and the bytes are compared; differences are counted and printed when the build ends

    blocks = dxt1_rgb(img, hole, old)      img (h, w, 3) uint8, hole (h, w) bool or None, old = the numpy function (fallback / reference)"""
import os, ctypes, subprocess, hashlib, atexit
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.join(HERE, 'fastdxt.c'); GCC = r'C:\mingw64\bin\gcc.exe'
ON = os.environ.get('SR3_FASTDXT', '1') != '0'; CHECK = os.environ.get('SR3_FASTDXT_CHECK', '0') == '1'; STAT = dict(calls=0, different=0, texels=0)
_lib = None
def lib():
    global _lib
    if _lib is None:
        dll = os.path.join(HERE, 'fastdxt.%s.dll' % hashlib.md5(open(SRC, 'rb').read()).hexdigest()[:8])      # one file per version of the source
        if not os.path.exists(dll):
            tmp = dll + '.%d.tmp' % os.getpid(); r = subprocess.run([GCC, '-O3', '-march=native', '-fopenmp', '-shared', '-o', tmp, SRC], capture_output=True, text=True, cwd=HERE)
            if r.returncode != 0: raise RuntimeError('fastdxt does not compile: ' + r.stderr[-1500:])
            try: os.replace(tmp, dll)
            except OSError: os.remove(tmp)
        os.add_dll_directory(os.path.dirname(GCC)); L = ctypes.CDLL(dll); L.dxt1_rgb.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]; _lib = L
    return _lib
def dxt1_rgb(img, hole, old):
    if not ON: return old(img, hole)
    a = np.ascontiguousarray(img, np.uint8); h, w = a.shape[:2]
    if a.ndim != 3 or a.shape[2] != 3 or h % 4 or w % 4 or (hole is not None and np.shape(hole) != (h, w)): return old(img, hole)
    m = None if hole is None else np.ascontiguousarray(hole, np.uint8); out = np.empty((h // 4) * (w // 4) * 8, np.uint8)
    lib().dxt1_rgb(a.ctypes.data_as(ctypes.c_void_p), h, w, None if m is None else m.ctypes.data_as(ctypes.c_void_p), out.ctypes.data_as(ctypes.c_void_p)); res = out.tobytes(); STAT['calls'] += 1; STAT['texels'] += h * w
    if CHECK and res != old(img, hole): STAT['different'] += 1
    return res
def _report():
    if CHECK and STAT['calls']: print('fastdxt check: %d pictures compressed (%.1f million texels), %d different from the numpy code' % (STAT['calls'], STAT['texels'] / 1e6, STAT['different']))
atexit.register(_report)
