"""Pickles a process without numpy can read (the stack's dumps: faces.pkl, patched.pkl): while pickling, every numpy
array is written as an npyio.Arr (dtype, shape, raw bytes) and every numpy scalar as a Python number (the same bits).

    dump(obj, path)                 what pickle.dump(obj, open(path, 'wb')) did, minus numpy
    load(path)                      npyio.Arr for the arrays    (readers without numpy)
    load(path, numpy=True)          numpy arrays, as before     (readers that still use numpy)

Why not pickle.dump as it was: a pickle that holds numpy objects can only be loaded where numpy is installed, and the
toolchain no longer carries numpy for every process (kb 31). A numpy float64 and a Python float are the same IEEE
double, so the values a reader computes with do not change.
How, without walking the data (a dump holds 335,000 faces): the pickler's reducer_override is called only for objects
that are not plain Python ones, i.e. exactly the numpy objects; the unpickler's find_class turns npyio._arr (the Arr
rebuilder) into a numpy array builder when numpy=True. Old dumps (numpy objects inside) still load with numpy=True."""
import io, pickle, sys
import npyio

class _Pickler(pickle.Pickler):
    def reducer_override(self, o):
        np = sys.modules.get('numpy')
        if np is not None:
            if isinstance(o, np.ndarray):
                if o.dtype.hasobject: return (list, (o.tolist(),))
                a = np.ascontiguousarray(o); return (npyio._arr, (a.dtype.str, a.shape, bytearray(a.tobytes())))
            if isinstance(o, np.generic): v = o.item(); return (type(v), (v,))
        return NotImplemented

def _numpy_arr(dtype, shape, data):
    import numpy as np
    return np.frombuffer(data, dtype, len(data) // npyio.itemsize(dtype) if npyio.itemsize(dtype) else 0).reshape(shape)

class _NumpyUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module == 'npyio' and name == '_arr': return _numpy_arr
        return super().find_class(module, name)

def dump(obj, path):
    with open(path, 'wb') as f: _Pickler(f, protocol=4).dump(obj)

def load(path, numpy=False):
    with open(path, 'rb') as f: return _NumpyUnpickler(f).load() if numpy else pickle.load(f)
