"""Packed geometry without NumPy; additive to fastgeo's existing ndarray API.

pack(faces, col=2) -> X ('<f8', corners x 3), off ('<i8', polygons + 1), lens ('<i8', polygons).
prep(faces=None, col=2, packed=None) -> Geo with X/off/lens/n and nr/ar/cen/lo/hi.
Numeric results are npyio.Arr, in little-endian C order. Inputs are borrowed;
pack and the computed prep fields own their buffers. prep's X/off/lens retain
their input storage (read-only or unaligned buffers are copied for the C call).
No existing fastgeo callers or return types change merely by importing this module.
"""
import ctypes
import sys

import cbuild
from npyio import Arr

_lib = None
_MAX_CORNERS = (1 << 31) - 1       # fg_prep's per-polygon loop count is a C int


def _native():
    global _lib
    if _lib is None:
        if sys.implementation.name != 'cpython': raise RuntimeError('geobuf requires CPython for native sequence packing')
        cbuild.runtime()
        path = cbuild.dll('fastgeo')
        lib = ctypes.CDLL(path)
        lib.fg_init.argtypes = []; lib.fg_init.restype = ctypes.c_int
        lib.fg_init()             # same UCRT pow implementation as fastgeo.lib()
        lib.fg_prep.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_longlong] + [ctypes.c_void_p] * 5
        lib.fg_prep.restype = None
        py = ctypes.PyDLL(path)    # Python sequence access must retain the GIL
        py.fg_py_bind.argtypes = [ctypes.c_void_p]; py.fg_py_bind.restype = ctypes.c_int
        if not py.fg_py_bind(ctypes.pythonapi._handle): raise RuntimeError('geobuf: CPython packing API unavailable')
        py.fg_py_lengths.argtypes = [ctypes.py_object, ctypes.c_longlong, ctypes.c_void_p, ctypes.c_void_p]
        py.fg_py_lengths.restype = ctypes.c_longlong
        py.fg_py_pack.argtypes = [ctypes.py_object, ctypes.c_longlong, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_longlong]
        py.fg_py_pack.restype = ctypes.c_int
        lib.packing = py
        _lib = lib
    return _lib


def pack(faces, col=2):
    """Pack sequences of xyz corners, retaining order and float64 bits.

    col=None accepts the polygons directly. Empty/degenerate polygons are kept.
    Every corner must have exactly three coordinates; malformed records fail
    before native code is called.
    """
    if sys.byteorder != 'little': raise RuntimeError('geobuf requires a little-endian host')
    polygons = list(faces) if col is None else [f[col] for f in faces]
    n = len(polygons); off = Arr('<i8', (n + 1,)); lens = Arr('<i8', (n,))
    if not n: return Arr('<f8', (0, 3)), off, lens
    lib = _native().packing
    corners = lib.fg_py_lengths(polygons, n, off.ptr(), lens.ptr())
    if corners < 0 or corners > sys.maxsize // 24: raise ValueError('geobuf.pack: invalid corner count')
    # This can actually be done with numpy the following way: np.fromiter(..., np.float64).reshape(-1, 3);
    # it's done this way because the C copy packs and checks the same doubles without NumPy or per-corner Python loops.
    xyz = Arr('<f8', (corners, 3))
    if lib.fg_py_pack(polygons, n, off.ptr(), lens.ptr(), xyz.ptr(), corners): raise ValueError('geobuf.pack: invalid polygons')
    return xyz, off, lens


def _checked(a, dtype, rank, name):
    if not isinstance(a, Arr) or a.dtype != dtype or len(a.shape) != rank:
        raise ValueError('geobuf.prep: %s must be a rank-%d %s Arr' % (name, rank, dtype))
    count = 1
    for d in a.shape:
        if not isinstance(d, int) or d < 0: raise ValueError('geobuf.prep: invalid %s shape' % name)
        count *= d
    if count > sys.maxsize // 8: raise ValueError('geobuf.prep: %s exceeds addressable storage' % name)
    m = memoryview(a.buf)
    if not m.c_contiguous: raise ValueError('geobuf.prep: %s must be contiguous' % name)
    m = m.cast('B')
    if m.nbytes < count * 8: raise ValueError('geobuf.prep: truncated %s buffer' % name)
    m = m[:count * 8]
    b = Arr(dtype, a.shape, bytearray(m) if m.readonly else m)
    if b.nbytes and b.ptr() % 8: b = Arr(dtype, a.shape, bytearray(m))
    return b


class Geo:
    __slots__ = ('X', 'off', 'lens', 'n', 'nr', 'ar', 'cen', 'lo', 'hi')


def prep(faces=None, col=2, packed=None):
    """Same fg_prep arithmetic as fastgeo.prep, with checked packed buffers.

    With packed=(X,off,lens), faces may be None; otherwise its count must match.
    No input values are changed. The five computed fields have owned storage.
    """
    if sys.byteorder != 'little': raise RuntimeError('geobuf requires a little-endian host')
    if packed is None:
        if faces is None: raise ValueError('geobuf.prep: faces or packed buffers required')
        X, off, lens = pack(faces, col)
    else:
        if len(packed) != 3: raise ValueError('geobuf.prep: packed must contain X, off and lens')
        X = _checked(packed[0], '<f8', 2, 'X')
        off = _checked(packed[1], '<i8', 1, 'off')
        lens = _checked(packed[2], '<i8', 1, 'lens')
        n = lens.shape[0]
        if X.shape[1] != 3 or off.shape != (n + 1,): raise ValueError('geobuf.prep: incompatible packed shapes')
        if faces is not None and len(faces) != n: raise ValueError('geobuf.prep: face count differs from packed buffers')
        ov, lv = off.view(), lens.view()
        if ov[0] != 0 or ov[-1] != X.shape[0]: raise ValueError('geobuf.prep: invalid offset endpoints')
        for i, k in enumerate(lv):
            if k < 0 or k > _MAX_CORNERS or ov[i + 1] - ov[i] != k:
                raise ValueError('geobuf.prep: invalid polygon offset/length')
    g = Geo(); g.X, g.off, g.lens = X, off, lens; g.n = lens.shape[0]
    g.nr = Arr('<f8', (g.n, 3)); g.ar = Arr('<f8', (g.n,))
    g.cen = Arr('<f8', (g.n, 3)); g.lo = Arr('<f8', (g.n, 3)); g.hi = Arr('<f8', (g.n, 3))
    if g.n:
        _native().fg_prep(X.ptr(), off.ptr(), g.n, g.nr.ptr(), g.ar.ptr(), g.cen.ptr(), g.lo.ptr(), g.hi.ptr())
    return g
