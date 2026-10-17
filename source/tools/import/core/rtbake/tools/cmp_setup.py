"""Two dumps of what the bake hands to the light (rt_bake_game5.py with RTG_DUMP): is everything the same?   python cmp_setup.py <a.pkl> <b.pkl>"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))); import nfpickle      # tools/import/core (the dumps since 2026-10-15; older plain pickles load too)
A = nfpickle.load(sys.argv[1], numpy=True); B = nfpickle.load(sys.argv[2], numpy=True); bad = []
def same(x, y):
    if isinstance(x, (list, tuple)): return isinstance(y, (list, tuple)) and len(x) == len(y) and all(same(a, b) for a, b in zip(x, y))
    if x is None or y is None: return x is None and y is None
    x = np.asarray(x); y = np.asarray(y); return x.shape == y.shape and x.dtype == y.dtype and bool(np.array_equal(x, y, equal_nan=True) if x.dtype.kind == 'f' else np.array_equal(x, y))
for k in sorted(set(A) | set(B)):
    if k not in A or k not in B: bad.append(k + ' (missing on one side)'); continue
    if not same(A[k], B[k]): bad.append(k)
print('%d things compared (%s ...) ; different: %s' % (len(set(A) | set(B)), ', '.join(sorted(A)[:8]), bad or 'none'))
