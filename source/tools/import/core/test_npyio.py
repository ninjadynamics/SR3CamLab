"""Checks npyio.py against numpy (needs numpy, as a development test):   python test_npyio.py
- save() writes the same bytes as np.save, for every dtype and shape the stack's files use (0-d to 4-d, empty, void keys)
- load() / mmap / loadz() read np.save's, np.savez's and np.savez_compressed's files to the same dtype, shape and bytes
- numpy reads what save() / savez() write, to the same arrays"""
import os, sys, tempfile, io
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import npyio
rng = np.random.default_rng(1995); ok = bad = 0
def check(what, cond):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print('FAILED', what)
cases = [rng.random((5, 4, 3)), rng.random(7).astype(np.float32), rng.integers(0, 255, (3, 64, 64, 7), dtype=np.uint8), rng.integers(-9, 9, 11).astype(np.int32),
         rng.integers(-9, 9, (2, 3)).astype(np.int64), rng.random(13) > 0.5, np.zeros((0, 3)), np.array(3.5), np.zeros(1, np.int16),
         np.ascontiguousarray(rng.integers(-5000, 5000, (6, 12)).astype(np.int32)).view(np.dtype((np.void, 48))).ravel(), rng.random((300, 300))]
d = tempfile.mkdtemp()
for k, a in enumerate(cases):
    p1, p2 = os.path.join(d, 'np%d.npy' % k), os.path.join(d, 'ours%d.npy' % k)
    np.save(p1, a); r = npyio.load(p1); check('load %d dtype %s' % (k, a.dtype), r.dtype == a.dtype.str and r.shape == a.shape and bytes(r.buf[:r.nbytes]) == a.tobytes())
    m = npyio.load(p1, mmap=True); check('mmap %d' % k, bytes(m.buf[:m.nbytes]) == a.tobytes())
    npyio.save(p2, r); check('save %d: the same bytes as np.save' % k, open(p1, 'rb').read() == open(p2, 'rb').read())
    b = np.load(p2); check('numpy reads ours %d' % k, b.dtype == a.dtype and b.shape == a.shape and b.tobytes() == a.tobytes())
z1, z2, z3 = (os.path.join(d, n) for n in ('np.npz', 'npc.npz', 'ours.npz'))
named = {'P': cases[0], 'K': cases[9], 'U': cases[5]}
np.savez(z1, **named); np.savez_compressed(z2, **named)
for z in (z1, z2):
    r = npyio.loadz(z); check('loadz %s' % os.path.basename(z), all(r[n].dtype == a.dtype.str and r[n].shape == a.shape and bytes(r[n].buf[:r[n].nbytes]) == a.tobytes() for n, a in named.items()))
npyio.savez(z3, **npyio.loadz(z1)); r = np.load(z3); check('numpy reads our npz', all(r[n].dtype == a.dtype and r[n].tobytes() == a.tobytes() for n, a in named.items()))
npyio.savez(z3 + '2', **npyio.loadz(z1)); check('savez: the same bytes twice', open(z3, 'rb').read() == open(z3 + '2', 'rb').read())
v = npyio.load(os.path.join(d, 'np0.npy')).view(); check('view: the numbers', list(v[:5]) == list(cases[0].ravel()[:5]))
print('NPYIO CHECKS: %d passed, %d failed' % (ok, bad)); sys.exit(1 if bad else 0)
