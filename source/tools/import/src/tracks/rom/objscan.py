import sys, numpy as np
import classic_export as ce
main, poly, polyf, tex16 = ce.load(); tab = ce.table(main)
def info(k):
    try: ps = ce.decode(k, tab, poly, polyf, tex16)
    except Exception as e: return None
    if not ps: return None
    V = np.array([v for p in ps for v in p['verts']]); return len(ps), V.min(0), V.max(0)
for a, b in [tuple(int(x) for x in r.split('-')) for r in sys.argv[1:]]:
    for k in range(a, b + 1):
        r = info(k)
        if r is None: print(k, 'empty'); continue
        n, mn, mx = r; print('%d polys %4d  x %9.0f..%9.0f  y %8.0f..%8.0f  z %9.0f..%9.0f' % (k, n, mn[0], mx[0], mn[1], mx[1], mn[2], mx[2]))
