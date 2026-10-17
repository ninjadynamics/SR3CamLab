"""fastdxt.py - build_classic.dxt1_rgb in C on every core (fastdxt.c, compiled with gcc on first use, like fastgeo.py).

    SR3_FASTDXT=0         the numpy code is used (to time or compare a build without this module)
    SR3_FASTDXT_CHECK=1   both run and the bytes are compared; differences are counted and printed when the build ends

    blocks = dxt1_rgb(img, hole, old)      img (h, w, 3) uint8, hole (h, w) bool or None, old = the numpy function (fallback / reference)
    blocks = dxt1_bytes(rgb, h, w, hole)   the same without numpy: rgb h * w * 3 bytes, hole h * w bytes (0 / 1) or None
Since 2026-10-15 (kb 31) no numpy here: a numpy picture is read through the buffer protocol (np.ascontiguousarray(img, np.uint8) was the
same bytes); a picture of another type or shape still goes to `old`."""
import os, ctypes, subprocess, hashlib, atexit
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.join(HERE, 'fastdxt.c'); import cbuild as _cb; from cbuild import runtime as _runtime
ON = os.environ.get('SR3_FASTDXT', '1') != '0'; CHECK = os.environ.get('SR3_FASTDXT_CHECK', '0') == '1'; STAT = dict(calls=0, different=0, texels=0)
_lib = None
def lib():
    global _lib
    if _lib is None:
        dll = _cb.dll('fastdxt')                                  # built on first use (cbuild.py: sources, flags, compiler)
        _runtime(); L = ctypes.CDLL(dll); L.dxt1_rgb.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
        L.dxt1_mips.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]; L.dxt1_mips.restype = ctypes.c_int; _lib = L
    return _lib
def dxt1_bytes(rgb, h, w, hole=None):
    """h x w RGB bytes (h, w multiples of 4) -> DXT1 blocks (bytes); hole: h * w bytes, 1 = transparent texel"""
    a = ctypes.create_string_buffer(bytes(rgb), len(rgb)); m = None if hole is None else ctypes.create_string_buffer(bytes(hole), len(hole)); out = ctypes.create_string_buffer((h // 4) * (w // 4) * 8)
    lib().dxt1_rgb(a, h, w, m, out); return out.raw
def dxt1_mips(rgb, h, w, hole=None):
    """build_classic.make_texture's levels: rgb h x w x 3 bytes after vivid (h, w powers of two), hole h * w bytes for the top level or
    None -> (all levels' DXT1 blocks, number of levels, the top level's length) ; see fastdxt.c"""
    H, W, tot = h, w, 0
    while True:
        tot += (max(4, H) // 4) * (max(4, W) // 4) * 8
        if H == 1 and W == 1: break
        H = max(1, H // 2); W = max(1, W // 2)
    a = ctypes.create_string_buffer(bytes(rgb), len(rgb)); m = None if hole is None else ctypes.create_string_buffer(bytes(hole), len(hole)); out = ctypes.create_string_buffer(tot); first = ctypes.c_int(0)
    n = lib().dxt1_mips(a, h, w, m, out, ctypes.byref(first)); STAT['calls'] += 1; STAT['texels'] += h * w
    return out.raw, n, first.value
def dxt1_rgb(img, hole, old):
    if not ON: return old(img, hole)
    mv = memoryview(img)
    if mv.format.lstrip('<=@') != 'B':                                # (not uint8: a numpy array of another type, so numpy is there - converted as before)
        import numpy as np
        mv = memoryview(np.ascontiguousarray(img, np.uint8))
    h, w = (tuple(mv.shape) + (0, 0))[:2]
    if mv.ndim != 3 or mv.shape[2] != 3 or h % 4 or w % 4: return old(img, hole)
    hm = None if hole is None else memoryview(hole)
    if hm is not None and tuple(hm.shape) != (h, w): return old(img, hole)
    if hm is not None and hm.itemsize != 1:
        import numpy as np
        hm = memoryview(np.ascontiguousarray(hole, np.uint8))
    res = dxt1_bytes(mv.tobytes(), h, w, None if hm is None else hm.tobytes()); STAT['calls'] += 1; STAT['texels'] += h * w      # (np.ascontiguousarray(hole, np.uint8): the same bytes)
    if CHECK and res != old(img, hole): STAT['different'] += 1
    return res
def _report():
    if CHECK and STAT['calls']: print('fastdxt check: %d pictures compressed (%.1f million texels), %d different from the numpy code' % (STAT['calls'], STAT['texels'] / 1e6, STAT['different']))
atexit.register(_report)
