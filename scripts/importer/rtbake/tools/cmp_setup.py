"""Two dumps of what the bake hands to the light (rt_bake_game5.py with RTG_DUMP): is everything the same?   python cmp_setup.py <a.pkl> <b.pkl>"""
import sys, pickle
import numpy as np
A = pickle.load(open(sys.argv[1], 'rb')); B = pickle.load(open(sys.argv[2], 'rb')); bad = []
def same(x, y):
    if isinstance(x, (list, tuple)): return isinstance(y, (list, tuple)) and len(x) == len(y) and all(same(a, b) for a, b in zip(x, y))
    if x is None or y is None: return x is None and y is None
    x = np.asarray(x); y = np.asarray(y); return x.shape == y.shape and x.dtype == y.dtype and bool(np.array_equal(x, y, equal_nan=True) if x.dtype.kind == 'f' else np.array_equal(x, y))
for k in sorted(set(A) | set(B)):
    if k not in A or k not in B: bad.append(k + ' (missing on one side)'); continue
    if not same(A[k], B[k]): bad.append(k)
print('%d things compared (%s ...) ; different: %s' % (len(set(A) | set(B)), ', '.join(sorted(A)[:8]), bad or 'none'))
