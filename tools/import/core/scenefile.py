"""The ray scene a build collects for the light bake (<path>.scene; bake1995.save_scene writes it): what the rays can hit.

Format: an .npz (npyio.py reads and writes it without numpy) with
    tris f4 (n,3,3)   uv f4 (n,3,2)   mat i4 (n,)   albedo f4 (m,)   albedo_rgb f4 (m,3)   sun f8 (3,)   centre f8 (c,2)
    holes_h i4 (m,)   holes_w i4 (m,)   holes_off i8 (m,)   holes_bits b1 (total,)
holes_*: each material's see-through mask (height x width bools) at holes_off in holes_bits; -1 = none. That is the
layout the C ray code takes (rays.c rt_masks), so a reader without numpy hands the arrays straight to it.
Until 2026-10-15 the file was a pickle of numpy arrays (unreadable without numpy); load() still reads those.

    load(path)               {name: npyio.Arr}                       for readers without numpy
    load(path, numpy=True)   the dict as it always was: numpy arrays, 'holes' a list of 2-D bool arrays or None
    save(path, D)            D as bake1995 builds it (numpy arrays, holes list)"""
import pickle
import npyio

ARRAYS = ('tris', 'uv', 'mat', 'albedo', 'albedo_rgb', 'sun', 'centre')

def save(path, D):
    import numpy as np                                    # the writer still builds its scene with numpy (bake1995.py)
    def arr(a): a = np.ascontiguousarray(a); return npyio.Arr(a.dtype.str, a.shape, memoryview(a).cast('B'))
    out = {k: arr(D[k]) for k in ARRAYS}; holes = D['holes']; m = len(holes)
    h = np.zeros(m, np.int32); w = np.zeros(m, np.int32); off = np.full(m, -1, np.int64); parts = []; pos = 0
    for i, hm in enumerate(holes):
        if hm is None: continue
        hm = np.ascontiguousarray(hm, bool); h[i], w[i] = hm.shape; off[i] = pos; parts.append(hm.ravel()); pos += hm.size
    bits = np.concatenate(parts) if parts else np.zeros(0, bool)
    out.update(holes_h=arr(h), holes_w=arr(w), holes_off=arr(off), holes_bits=arr(bits))
    npyio.savez(path, **out)

def load(path, numpy=False):
    with open(path, 'rb') as f: magic = f.read(2)
    if magic != b'PK':                                    # the old pickle
        S = pickle.load(open(path, 'rb'))
        if numpy: return S
        raise ValueError('%s is a scene of the old kind (a pickle of numpy arrays): collect again' % path)
    A = npyio.loadz(path)
    if not numpy: return A
    import numpy as np
    S = {k: np.frombuffer(A[k].buf, A[k].dtype, A[k].size).reshape(A[k].shape) for k in ARRAYS}
    h, w, off = (A[k].view() for k in ('holes_h', 'holes_w', 'holes_off')); bits = np.frombuffer(A['holes_bits'].buf, bool, A['holes_bits'].size)
    S['holes'] = [None if off[i] < 0 else bits[off[i]:off[i] + h[i] * w[i]].reshape(h[i], w[i]) for i in range(len(off))]
    return S
