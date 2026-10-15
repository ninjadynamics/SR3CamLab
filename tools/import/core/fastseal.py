"""fastseal.py - for seal1995.py: which corners may lie on the inside of which edge, found in C on every core (fastseal.c, compiled with gcc on first
use, like fastdxt.py). Only a filter: seal1995 measures what is left with its own lines.

    SR3_FASTSEAL=0   seal1995 walks every edge itself, as it did

    cnt, off, cand = candidates(U, E, xo, i0s, i1s, tol)     cand[off[e]:off[e] + cnt[e]] = the corners to measure for edge e, in the order of xo"""
import os, ctypes, subprocess, hashlib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.join(HERE, 'fastseal.c'); import cbuild as _cb; from cbuild import runtime as _runtime; ON = os.environ.get('SR3_FASTSEAL', '1') != '0'
_lib = None
def lib():
    global _lib
    if _lib is None:
        dll = _cb.dll('fastseal')                                  # built on first use (cbuild.py: sources, flags, compiler)
        _runtime(); L = ctypes.CDLL(dll); P = ctypes.c_void_p; LL = ctypes.c_longlong; D = ctypes.c_double
        L.seal_count.argtypes = [P, P, LL, P, P, P, D, P]; L.seal_fill.argtypes = [P, P, LL, P, P, P, D, P, P, P]; L.seal_count.restype = None; L.seal_fill.restype = None; _lib = L
    return _lib
def candidates(U, E, xo, i0s, i1s, tol):
    p = lambda a: a.ctypes.data_as(ctypes.c_void_p); U = np.ascontiguousarray(U, np.float64); E = np.ascontiguousarray(E, np.int64); xo = np.ascontiguousarray(xo, np.int64)
    i0 = np.ascontiguousarray(i0s, np.int64); i1 = np.ascontiguousarray(i1s, np.int64); ne = len(E); cnt = np.zeros(ne, np.int64); L = lib()
    L.seal_count(p(U), p(E), ne, p(xo), p(i0), p(i1), float(tol), p(cnt)); off = np.zeros(ne + 1, np.int64); np.cumsum(cnt, out=off[1:]); cand = np.zeros(max(int(off[-1]), 1), np.int64)
    L.seal_fill(p(U), p(E), ne, p(xo), p(i0), p(i1), float(tol), p(cnt), p(off), p(cand)); return cnt, off, cand
