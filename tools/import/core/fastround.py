"""fastround.py - the two loops over triangles of round1995.py (_order_limits, _gap_over) in C (fastgeo.c: fg_tri_points).
The same corners are tested against the same triangles with the same formulas; the results are minima / maxima, so the order does not matter
and the numbers are the original's to the last bit.

    import fastround; fastround.install(round1995)        # once; the originals stay as round1995._old__order_limits / _old__gap_over
SR3_FASTGEO=0: install() does nothing. SR3_FASTGEO_CHECK=1: both run, differences are counted (fastgeo.REPORT)."""
import numpy as np
import fastgeo
from fastgeo import _p

def _run(mode, X0, X1, use, S, keep, cell, out1, out2):
    L = fastgeo.lib(); P = fastgeo.ctypes.c_void_p; L.fg_tri_points.argtypes = [fastgeo.ctypes.c_int, P, P, fastgeo.ctypes.c_longlong, P, P, fastgeo.ctypes.c_longlong, fastgeo.ctypes.c_double, fastgeo.ctypes.c_double, P, P]; L.fg_tri_points.restype = fastgeo.ctypes.c_int
    X1 = np.ascontiguousarray(X1, np.float64); S = np.ascontiguousarray(S, np.float64).reshape(-1, 9); X0 = None if X0 is None else np.ascontiguousarray(X0, np.float64)
    if X1.ndim != 2 or X1.shape[1] != 3 or (X0 is not None and X0.shape != X1.shape): return -3
    u = None if use is None else np.ascontiguousarray(use, np.uint8)
    return L.fg_tri_points(mode, None if X0 is None else _p(X0), _p(X1), len(X1), None if u is None else _p(u), _p(S), len(S), float(keep), float(cell), _p(out1), None if out2 is None else _p(out2))

def install(R):
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
    R._old__order_limits = old_ol; R._old__gap_over = old_go; R._order_limits = _order_limits; R._gap_over = _gap_over; R._fastround = True
    return True
