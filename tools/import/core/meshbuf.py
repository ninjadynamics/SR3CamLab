"""Additive packed mesh operations; meshgen's ndarray API remains unchanged.

Vertices are owned '|V48' (4*n,) Arrs containing meshgen.VTX's exact layout:
position f4[4], normal f4[3], tangent f4[3], uv0 u2[2], uv1 u2[2].
This module imports no NumPy and does not install or replace legacy functions.
"""
import ctypes
import sys

from npyio import Arr
from fastround import _buffer


def make_verts_safe(Q):
    """Checked '<f8' (n,4,3) corners -> owned '|V48' (4*n,) records.

    Corner 2 defines the normal, including triangle quads with repeated corners.
    Norms <= 1e-9 (or NaN) use the legacy normal/tangent fallback. Input storage
    is borrowed, never modified; read-only and unaligned buffers are accepted.
    """
    Q = _buffer(Q, '<f8', (4,3), 'quad corners')
    n = Q.shape[0]
    if n > sys.maxsize // 192: raise ValueError('meshbuf: vertex output too large')
    out = Arr('|V48', (4*n,))
    # NumPy's cross/norm/repeat plus structured-field assignment, performed in
    # one C pass to preserve the record bytes without intermediate arrays.
    if n:
        from geobuf import _native
        L = _native()
        L.fg_mesh_verts_safe.argtypes = [ctypes.c_void_p, ctypes.c_longlong, ctypes.c_void_p]
        L.fg_mesh_verts_safe.restype = None
        L.fg_mesh_verts_safe(Q.ptr(), n, out.ptr())
    return out
