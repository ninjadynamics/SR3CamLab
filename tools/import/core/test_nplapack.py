"""nplapack against np.linalg.lstsq (a development test: needs numpy). Random and 1995-like (1/8 grid, 1/16 uv) systems of every
shape nplapack.c models, one at a time and as one threaded batch (the OpenMP workers' x87 precision is set by nplapack.c itself).
    python test_nplapack.py [systems per shape]"""
import sys, struct, array
import numpy as np
import nplapack

def main(count):
    rng = np.random.default_rng(29); bad = 0; total = 0
    for m, n, nrhs in ((4, 3, 2), (3, 3, 2), (4, 3, 1), (5, 3, 2), (6, 3, 2), (8, 3, 2), (2, 2, 1), (3, 2, 2), (8, 4, 3), (1, 1, 1), (8, 8, 8)):
        for kind in ('random', 'grid'):
            if kind == 'random':
                A = rng.normal(size=(count, m, n)) * np.exp(rng.normal(size=(count, m, n))); B = rng.normal(size=(count, m, nrhs))
                A[rng.random(size=A.shape) < 0.05] = 0.0
            else:
                A = rng.integers(-40, 40, size=(count, m, n)) / 8.0; A[:, :, -1] = 1.0; B = A[:, :, :1] * 0.25 + rng.integers(-8, 8, size=(count, m, nrhs)) / 16.0
            want = [np.linalg.lstsq(A[k], B[k], rcond=None)[0] for k in range(count)]
            X, info = nplapack.lstsq_batch(array.array('d', A.ravel().tolist()), array.array('d', B.ravel().tolist()), count, m, n, nrhs)
            got = np.frombuffer(X, float).reshape(count, n, nrhs); total += count
            nb = sum(want[k].tobytes() != got[k].tobytes() for k in range(count)); bad += nb
            one = sum(np.array(nplapack.lstsq(A[k].tolist(), B[k].tolist())[0]).tobytes() != want[k].tobytes() for k in range(0, count, 7))
            bad += one
            print('%2d x %d, %d right-hand sides, %-6s: batch %s, one by one %s' % (m, n, nrhs, kind, 'same' if not nb else '%d DIFFERENT' % nb, 'same' if not one else '%d DIFFERENT' % one))
    print('PASS: %d systems, the same bits as np.linalg.lstsq' % total if not bad else 'FAIL: %d systems differ' % bad)
    return 1 if bad else 0

if __name__ == '__main__': sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 5000))
