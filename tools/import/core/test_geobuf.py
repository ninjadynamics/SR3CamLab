"""Golden geometry/ABI checks with NumPy blocked: python -I test_geobuf.py.

geobuf_golden.json was captured through the original fastgeo ndarray API.
Full real-course comparisons and warm timings are separate development evidence.
"""
import importlib.abc
import json
import os
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault('OMP_NUM_THREADS', '4')


class NoNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'numpy': raise RuntimeError('NumPy import blocked: ' + fullname)


assert 'numpy' not in sys.modules
sys.meta_path.insert(0, NoNumpy())
import geobuf
from npyio import Arr, array


def raw(a): return bytes(memoryview(a.buf).cast('B')[:a.nbytes])


def rejects(fn, exc=ValueError):
    try: fn()
    except exc: return
    raise AssertionError('Expected ' + exc.__name__)


assert geobuf.prep([], col=None).X.shape == (0, 3)
assert geobuf._lib is None              # empty geometry needs no compiler/DLL
cases = json.loads((HERE / 'geobuf_golden.json').read_text())['cases']
for name, case in cases.items():
    polygons = [[tuple(struct.unpack('<d', bytes.fromhex(v))[0] for v in p) for p in poly] for poly in case['polygons']]
    faces = [('tile', 'section', p, []) for p in polygons]
    packed = geobuf.pack(faces)
    before = [raw(a) for a in packed]
    for g in (geobuf.prep(faces), geobuf.prep(polygons, col=None), geobuf.prep(packed=packed)):
        for key, expected in case['expected'].items():
            a = getattr(g, key)
            assert a.dtype == expected['dtype'] and list(a.shape) == expected['shape'], (name, key, 'type/shape')
            assert raw(a).hex() == expected['hex'], (name, key, 'bytes')
        assert g.n == len(polygons)
    assert [raw(a) for a in packed] == before, (name, 'input changed')
    # Read-only bytes/views must be accepted without modifying the input descriptor.
    readonly = tuple(Arr(a.dtype, a.shape, memoryview(raw(a))) for a in packed)
    geobuf.prep(packed=readonly)
    assert all(a.buf.readonly for a in readonly)

points = [[(0., 0., 0.), (1., 0., 0.), (0., 1., 0.)]]
X, off, lens = geobuf.pack(points, col=None)
rejects(lambda: geobuf.prep())
rejects(lambda: geobuf.pack([[(1., 2.), (3., 4., 5., 6.)]], col=None))
rejects(lambda: geobuf.prep([], packed=(X, off, lens)))
rejects(lambda: geobuf.prep(packed=(X, off)))
rejects(lambda: geobuf.prep(packed=(Arr('<f4', (3, 3)), off, lens)))
rejects(lambda: geobuf.prep(packed=(Arr('<f8', (9,)), off, lens)))
rejects(lambda: geobuf.prep(packed=(X, array('<i8', (2,), [1, 3]), lens)))
rejects(lambda: geobuf.prep(packed=(X, array('<i8', (2,), [0, 4]), lens)))
rejects(lambda: geobuf.prep(packed=(X, off, array('<i8', (1,), [-1]))))
rejects(lambda: geobuf.prep(packed=(X, off, array('<i8', (1,), [1 << 31]))))
short = Arr('<f8', (3, 3)); short.buf = bytearray(3)
rejects(lambda: geobuf.prep(packed=(short, off, lens)))
strided = Arr('<f8', (3, 3)); strided.buf = memoryview(bytearray(144))[::2]
rejects(lambda: geobuf.prep(packed=(strided, off, lens)))
negative = Arr('<f8', (3, 3)); negative.shape = (-3, 3)
rejects(lambda: geobuf.prep(packed=(negative, off, lens)))
unaligned = Arr('<f8', X.shape, memoryview(bytearray(b'x' + raw(X)))[1:])
assert raw(geobuf.prep(packed=(unaligned, off, lens)).nr) == raw(geobuf.prep(packed=(X, off, lens)).nr)


class BadFloat:
    def __float__(self): raise RuntimeError('conversion failed')


class ChangingPolygon:
    def __len__(self): return 3
    def __iter__(self): return iter(points[0][:2])


rejects(lambda: geobuf.pack([ChangingPolygon()], col=None))
rejects(lambda: geobuf.pack([[(BadFloat(), 0., 0.)]], col=None), RuntimeError)
rejects(lambda: geobuf.pack([[(10 ** 400, 0., 0.)]], col=None), OverflowError)
bad = (1., 2.)
good = points[0][0]
before = (sys.getrefcount(bad), sys.getrefcount(good))
for _ in range(100):
    rejects(lambda: geobuf.pack([[bad]], col=None))
    geobuf.pack([[good]], col=None)
assert before == (sys.getrefcount(bad), sys.getrefcount(good)), 'C packing leaked references'
assert 'numpy' not in sys.modules
print('PASS: %d golden cases, packed-buffer bounds, ownership, empty arrays and C exception/reference handling; NumPy blocked' % len(cases))
