"""fastround.py - the two loops over triangles of round1995.py (_order_limits, _gap_over) in C (fastgeo.c: fg_tri_points), and the
arithmetic of its _bends (fg_bends; arccos and degrees stay with numpy).
The same corners are tested against the same triangles with the same formulas; the results are minima / maxima, so the order does not matter
and the numbers are the original's to the last bit.

    import fastround; fastround.install(round1995)        # once; the originals stay as round1995._old__order_limits / _old__gap_over
SR3_FASTGEO=0: install() does nothing. SR3_FASTGEO_CHECK=1: both run, differences are counted (fastgeo.REPORT).

Additive NumPy-free APIs: order_limits_buf, gap_over_buf, bend_components_buf,
bends_buf. They accept checked npyio.Arr inputs and return owned Arr outputs.
The explicit buffer APIs always use native kernels, independent of the legacy
installer's SR3_FASTGEO switches. Importing fastround itself no longer loads NumPy.
"""
# The legacy installer alone imports NumPy. The additive *_buf functions below
# use npyio.Arr and can be imported/called in a NumPy-free process.
import ctypes
import math
import sys
from npyio import Arr

_buffer_lib = None


def _buf_lib():
    global _buffer_lib
    if _buffer_lib is None:
        from geobuf import _native
        L = _native(); P = ctypes.c_void_p; I = ctypes.c_longlong
        L.fg_round_grid_ok.argtypes = [P,I,P,I,ctypes.c_double]; L.fg_round_grid_ok.restype = ctypes.c_int
        L.fg_round_indices_ok.argtypes = [P,P,I,I]; L.fg_round_indices_ok.restype = ctypes.c_int
        L.fg_round_init.argtypes = []; L.fg_round_init.restype = ctypes.c_int
        if not L.fg_round_init(): raise RuntimeError('fastround: UCRT acos unavailable')
        L.fg_round_angles.argtypes = [P,P,I]; L.fg_round_angles.restype = ctypes.c_int
        _buffer_lib = L
    return _buffer_lib


def _buffer(a, dtype, tail, name):
    """Validate storage before passing borrowed buffers to the native kernel."""
    if sys.byteorder != 'little': raise RuntimeError('fastround requires a little-endian host')
    if not isinstance(a, Arr) or a.dtype != dtype or len(a.shape) != 1 + len(tail) or a.shape[1:] != tail:
        raise ValueError('fastround: %s must be %s (n,%s) Arr' % (name, dtype, tail))
    if any(not isinstance(d, int) or d < 0 for d in a.shape): raise ValueError('fastround: invalid ' + name + ' shape')
    if a.size > sys.maxsize // a.itemsize: raise ValueError('fastround: oversized ' + name)
    v = memoryview(a.buf)
    if not v.c_contiguous: raise ValueError('fastround: noncontiguous ' + name)
    v = v.cast('B')
    if v.nbytes < a.nbytes: raise ValueError('fastround: truncated ' + name)
    v = v[:a.nbytes]
    b = Arr(dtype, a.shape, bytearray(v) if v.readonly else v)
    if b.nbytes and b.ptr() % a.itemsize: b = Arr(dtype, a.shape, bytearray(v))
    return b


def _grid_domain(X, S, cell):
    # fg_tri_points floors x/z into signed grid cells. Reject nonfinite or huge
    # quotients before C integer casts; the span bound also prevents overflow in
    # its NX*NZ allocation calculation. This domain comfortably covers SR3.
    if not math.isfinite(cell) or cell <= 0: raise ValueError('fastround: cell must be finite and positive')
    if X.size or S.size:
        if not _buf_lib().fg_round_grid_ok(X.ptr(), X.shape[0], S.ptr(), S.shape[0], cell):
            raise ValueError('fastround: x/z outside safe grid domain')


def _tri_buf(X0, X, movable, S, keep, cell):
    from geobuf import _native
    X = _buffer(X, '<f8', (3,), 'X'); S = _buffer(S, '<f8', (3,3), 'S')
    mode = int(X0 is not None); n = X.shape[0]
    if mode:
        X0 = _buffer(X0, '<f8', (3,), 'X0')
        dtype = movable.dtype if isinstance(movable, Arr) else ''
        if dtype not in ('|b1', '|u1'): raise ValueError('fastround: movable must be a boolean/byte Arr')
        movable = _buffer(movable, dtype, (), 'movable')
        if X0.shape != X.shape or movable.shape != (n,): raise ValueError('fastround: mismatched corner counts')
    keep, cell = float(keep), float(cell)
    if not math.isfinite(keep) or keep < 0: raise ValueError('fastround: keep must be finite and nonnegative')
    _grid_domain(X, S, cell)
    # This can actually be done with numpy the following way: np.full(n, +/-np.inf);
    # it's done this way because repeated IEEE bytes initialize owned Arr storage without NumPy.
    import struct
    out = Arr('<f8', (n,), bytearray(struct.pack('<d', -math.inf if mode else math.inf) * n))
    hi = Arr('<f8', (n,), bytearray(struct.pack('<d', math.inf) * n)) if mode else None
    if n and S.shape[0] and (not mode or any(movable.view())):
        L = _native(); P = ctypes.c_void_p
        L.fg_tri_points.argtypes = [ctypes.c_int,P,P,ctypes.c_longlong,P,P,ctypes.c_longlong,ctypes.c_double,ctypes.c_double,P,P]
        L.fg_tri_points.restype = ctypes.c_int
        status = L.fg_tri_points(mode, X0.ptr() if mode else None, X.ptr(), n,
            movable.ptr() if mode else None, S.ptr(), S.shape[0], keep, cell, out.ptr(), hi.ptr() if mode else None)
        if status == -1: raise MemoryError('fastround: native grid allocation failed')
        if status: raise ValueError('fastround: native grid too large or invalid (status %d)' % status)
    return (out, hi) if mode else out


def order_limits_buf(X0, X1, movable, S, keep=0.05, cell=4.0):
    """Owned lo/hi '<f8' (n,) Arrs; inputs are borrowed, never changed.

    X0/X1: '<f8' (n,3), movable: '|b1' or '|u1' (n,), S: '<f8' (m,3,3).
    Empty/no-active/no-surface inputs return infinities. Invalid grid domains or
    excessive grids raise ValueError; no NumPy fallback is imported.
    """
    if X0 is None: raise ValueError('fastround: X0 is required for order limits')
    return _tri_buf(X0, X1, movable, S, keep, cell)


def gap_over_buf(X, S, cell=4.0):
    """Owned '<f8' (n,) distances; same checked geometry contract as order_limits_buf."""
    return _tri_buf(None, X, None, S, 0.0, cell)


def bend_components_buf(X, TA, TB):
    """Owned cosine '<f8', valid/positive '|u1' (m,) Arrs, before acos/degrees.

    X is '<f8' (n,3); TA/TB are '<i8' (m,3). All indices are range-checked.
    The unchanged fg_bends kernel defines degenerate/nonfinite arithmetic.
    """
    from geobuf import _native
    X = _buffer(X, '<f8', (3,), 'X')
    A = _buffer(TA, '<i8', (3,), 'TA'); B = _buffer(TB, '<i8', (3,), 'TB')
    if A.shape != B.shape: raise ValueError('fastround: triangle counts differ')
    if A.size and not _buf_lib().fg_round_indices_ok(A.ptr(), B.ptr(), A.size, X.shape[0]):
        raise ValueError('fastround: vertex index out of range')
    m = A.shape[0]; c = Arr('<f8',(m,)); ok = Arr('|u1',(m,)); pos = Arr('|u1',(m,))
    if m:
        L = _native(); P = ctypes.c_void_p
        L.fg_bends.argtypes = [P,P,P,ctypes.c_longlong,P,P,P]; L.fg_bends.restype = None
        L.fg_bends(X.ptr(), A.ptr(), B.ptr(), m, c.ptr(), ok.ptr(), pos.ptr())
    return c, ok, pos


def bends_buf(X, TA, TB):
    """Owned signed degrees '<f8' and valid '|b1' (m,) Arrs, same values as _bends.

    Native acos/degrees use the CPython/UCRT math path, checked against the
    Windows NumPy 1.24 baseline. Full-caller migration still requires regression.
    """
    c, ok, pos = bend_components_buf(X, TA, TB)
    # This can actually be done with numpy the following way: np.where(pos, np.degrees(np.arccos(c)), -np.degrees(np.arccos(c)));
    # it's done this way because native UCRT math preserves the baseline bits without Python loops or importing NumPy.
    if c.size and _buf_lib().fg_round_angles(c.ptr(), pos.ptr(), c.size):
        raise RuntimeError('fastround: native angle conversion unavailable')
    return c, Arr('|b1', ok.shape, ok.buf)

def _run(mode, X0, X1, use, S, keep, cell, out1, out2):
    import numpy as np
    import fastgeo
    from fastgeo import _p
    L = fastgeo.lib(); P = fastgeo.ctypes.c_void_p; L.fg_tri_points.argtypes = [fastgeo.ctypes.c_int, P, P, fastgeo.ctypes.c_longlong, P, P, fastgeo.ctypes.c_longlong, fastgeo.ctypes.c_double, fastgeo.ctypes.c_double, P, P]; L.fg_tri_points.restype = fastgeo.ctypes.c_int
    X1 = np.ascontiguousarray(X1, np.float64); S = np.ascontiguousarray(S, np.float64).reshape(-1, 9); X0 = None if X0 is None else np.ascontiguousarray(X0, np.float64)
    if X1.ndim != 2 or X1.shape[1] != 3 or (X0 is not None and X0.shape != X1.shape): return -3
    u = None if use is None else np.ascontiguousarray(use, np.uint8)
    return L.fg_tri_points(mode, None if X0 is None else _p(X0), _p(X1), len(X1), None if u is None else _p(u), _p(S), len(S), float(keep), float(cell), _p(out1), None if out2 is None else _p(out2))

def install(R):
    import numpy as np
    import fastgeo
    from fastgeo import _p
    if not fastgeo.ON or getattr(R, '_fastround', False): return False
    old_ol, old_go = R._order_limits, R._gap_over; keep0 = old_ol.__defaults__[0]
    def _order_limits(X0, X1, movable, S, keep=keep0, cell=4.0):
        """lowest and highest y every corner may take so that it stays on its side of the lying triangles S (round1995._order_limits)"""
        lo = np.full(len(X1), -np.inf); hi = np.full(len(X1), np.inf); mv = np.asarray(movable, bool)
        if not mv.any() or not len(S): return lo, hi
        if _run(1, X0, X1, mv, S, keep, cell, lo, hi): return old_ol(X0, X1, movable, S, keep, cell)
        if fastgeo.CHECK: a = old_ol(X0, X1, movable, S, keep, cell); fastgeo.note('round1995._order_limits', np.array_equal(a[0], lo) and np.array_equal(a[1], hi), (int((a[0] != lo).sum()), int((a[1] != hi).sum())))
        return lo, hi
    def _gap_over(X, S, cell=4.0):
        """how far (up or down) every corner is from the lying triangles S it stands over; inf where it stands over none (round1995._gap_over)"""
        gap = np.full(len(X), np.inf)
        if not len(S): return gap
        if _run(0, None, X, None, S, 0.0, cell, gap, None): return old_go(X, S, cell)
        if fastgeo.CHECK: a = old_go(X, S, cell); fastgeo.note('round1995._gap_over', np.array_equal(a, gap), int((a != gap).sum()))
        return gap
    old_b = R._bends
    def _bends(X, TA, TB):
        """signed bend of every edge shared by two drawn triangles (round1995._bends): the arithmetic in C (fastgeo.c fg_bends), arccos and degrees in numpy"""
        L = fastgeo.lib(); P = fastgeo.ctypes.c_void_p
        L.fg_bends.argtypes = [P, P, P, fastgeo.ctypes.c_longlong, P, P, P]; L.fg_bends.restype = None
        Xc = np.ascontiguousarray(X, np.float64); A = np.ascontiguousarray(TA, np.int64); B = np.ascontiguousarray(TB, np.int64); m = len(A)
        c = np.empty(m); ok = np.empty(m, np.uint8); pos = np.empty(m, np.uint8)
        if m: L.fg_bends(_p(Xc), _p(A), _p(B), m, _p(c), _p(ok), _p(pos))
        ang = np.degrees(np.arccos(c)); out = (np.where(pos.astype(bool), ang, -ang), ok.astype(bool))
        if fastgeo.CHECK: o = old_b(X, TA, TB); fastgeo.note('round1995._bends', np.array_equal(o[0], out[0], equal_nan=True) and np.array_equal(o[1], out[1]), (int((o[0] != out[0]).sum()), int((o[1] != out[1]).sum())))
        return out
    R._old__order_limits = old_ol; R._old__gap_over = old_go; R._order_limits = _order_limits; R._gap_over = _gap_over; R._old__bends = old_b; R._bends = _bends; R._fastround = True
    return True
