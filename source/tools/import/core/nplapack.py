"""np.linalg.lstsq of small systems without numpy: nplapack.c, LAPACK's dgelsd as numpy 1.24.3's OpenBLAS runs it on the author's
PC, the same bits (kb 31; checked against np.linalg.lstsq on the 9,074 systems of a Desert build and on 120,000 random ones).

    X, S = lstsq(A, B)        A: m rows of n numbers, B: m rows of nrhs numbers (or m numbers) -> X: n rows of nrhs numbers (or
                              n numbers), S: A's singular values, largest first (dgelsd's, not np.linalg.svd's: they can differ
                              in the last bit, which is why matrix_rank() compares them with its tolerance only)
    matrix_rank(A, tol)       np.linalg.matrix_rank(A, tol): the singular values above tol
    X, info = lstsq_batch(A, B, count, m, n, nrhs)   flat row-major float64 buffers (array / bytes / Arr), the systems one after
                              another -> X array('d') (count x n x nrhs), info array('i') (0 = solved)
    U, S, Vh = svd(A)         np.linalg.svd(A) (full matrices): U m rows of m, S n numbers (largest first), Vh n rows of n
    U, S, Vh, info = svd_batch(A, count, m, n)       the same on a flat row-major buffer (count x m x n)
What the C models: m <= 8 rows, n <= m, nrhs <= 8; svd: m >= n and m < INT(n x 11 / 6) (dgesdd without its QR step: every square
matrix, 4 x 3, 6 x 4, ...); outside that a ValueError (numpy's own is the fallback there)."""
import array, ctypes
import cbuild

MAXM = 8; MAXRHS = 8
class LinAlgError(ValueError): pass                                  # (np.linalg.LinAlgError: "SVD did not converge in Linear Least Squares")
_L = None
def _lib():
    global _L
    if _L is None:
        cbuild.runtime(); L = ctypes.CDLL(cbuild.dll('nplapack')); P = ctypes.c_void_p; I = ctypes.c_int
        L.np_lstsq.argtypes = [I, I, I, I, P, P, P, P, P, P]; L.np_lstsq.restype = I
        L.np_svd.argtypes = [I, I, I, P, P, P, P, P]; L.np_svd.restype = I
        _L = L
    return _L
def _addr(a):
    if isinstance(a, array.array): return a.buffer_info()[0]
    if hasattr(a, 'ptr'): return a.ptr()                              # npyio.Arr
    return ctypes.addressof(ctypes.c_char.from_buffer(a))
def fits(m, n, nrhs): return 1 <= n <= m <= MAXM and 1 <= nrhs <= MAXRHS
def lstsq(A, B):
    m = len(A); n = len(A[0]) if m else 0; one = m and not hasattr(B[0], '__len__'); nrhs = 1 if one else (len(B[0]) if m else 0)
    if not fits(m, n, nrhs): raise ValueError('nplapack.lstsq: %d x %d with %d right-hand sides is outside what nplapack.c models' % (m, n, nrhs))
    a = array.array('d', [v for r in A for v in r]); b = array.array('d', B if one else [v for r in B for v in r])
    x = array.array('d', bytes(8 * n * nrhs)); s = array.array('d', bytes(8 * n)); info = array.array('i', [0])
    _lib().np_lstsq(1, m, n, nrhs, _addr(a), _addr(b), _addr(x), _addr(s), None, _addr(info))
    if info[0]: raise LinAlgError('SVD did not converge in Linear Least Squares')
    X = x.tolist(); return (X if one else [X[i * nrhs:(i + 1) * nrhs] for i in range(n)]), s.tolist()
def matrix_rank(A, tol):
    _, S = lstsq(A, [0.0] * len(A)); return sum(1 for v in S if v > tol)
def fits_svd(m, n): return 1 <= n <= m <= MAXM and m < int(n * 11.0 / 6.0)
def svd_batch(A, count, m, n):
    if not fits_svd(m, n): raise ValueError('nplapack.svd: %d x %d is outside what nplapack.c models' % (m, n))
    U = array.array('d', bytes(8 * count * m * m)); S = array.array('d', bytes(8 * count * n)); V = array.array('d', bytes(8 * count * n * n)); info = array.array('i', bytes(4 * count))
    if count: _lib().np_svd(count, m, n, _addr(A), _addr(U), _addr(S), _addr(V), _addr(info))
    return U, S, V, info
def svd(A):
    m = len(A); n = len(A[0]) if m else 0
    U, S, V, info = svd_batch(array.array('d', [v for r in A for v in r]), 1, m, n)
    if info[0]: raise LinAlgError('SVD did not converge')
    u = U.tolist(); v = V.tolist(); return [u[i * m:(i + 1) * m] for i in range(m)], S.tolist(), [v[i * n:(i + 1) * n] for i in range(n)]
def lstsq_batch(A, B, count, m, n, nrhs):
    if not fits(m, n, nrhs): raise ValueError('nplapack.lstsq_batch: %d x %d with %d right-hand sides is outside what nplapack.c models' % (m, n, nrhs))
    x = array.array('d', bytes(8 * count * n * nrhs)); info = array.array('i', bytes(4 * count))
    if count: _lib().np_lstsq(count, m, n, nrhs, _addr(A), _addr(B), _addr(x), None, None, _addr(info))
    return x, info
