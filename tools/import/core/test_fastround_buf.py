"""Frozen legacy rounding results, with NumPy blocked: python -I test_fastround_buf.py."""
import ctypes, importlib.abc, json, os
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault('OMP_NUM_THREADS', '4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)

class NoNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'numpy': raise RuntimeError('NumPy import blocked: ' + fullname)

sys.meta_path.insert(0, NoNumpy())
import fastround as F
from npyio import Arr, array
import geobuf

def raw(a): return bytes(memoryview(a.buf).cast('B')[:a.nbytes])
def decode(a): return Arr(a['dtype'], a['shape'], bytearray.fromhex(a['hex']))
def reject(fn, exc=ValueError):
    try: fn()
    except exc: return
    raise AssertionError('Expected ' + exc.__name__)

cases = json.loads((HERE/'fastround_golden.json').read_text())['cases']
for name, case in cases.items():
    inputs = {k:decode(a) for k,a in case['inputs'].items()}
    original = {k:raw(a) for k,a in inputs.items()}
    for storage in ('owned', 'readonly', 'unaligned'):
        d = {k:Arr(a.dtype,a.shape, memoryview(original[k]) if storage == 'readonly' else
            memoryview(bytearray(b'x'+original[k]))[1:] if storage == 'unaligned' else a.buf) for k,a in inputs.items()}
        lo, hi = F.order_limits_buf(d['X0'],d['X'],d['movable'],d['S'])
        c, ok, pos = F.bend_components_buf(d['X'],d['TA'],d['TB'])
        ang, good = F.bends_buf(d['X'],d['TA'],d['TB'])
        got = dict(lo=lo,hi=hi,gap=F.gap_over_buf(d['X'],d['S']),cosine=c,valid=ok,positive=pos,angles=ang,good=good)
        for k,a in got.items():
            want = case['expected'][k]
            assert (a.dtype,list(a.shape),raw(a).hex()) == (want['dtype'],want['shape'],want['hex']), (name,storage,k)
        assert {k:raw(a) for k,a in d.items()} == original, (name,'input modified')
    if name == 'empty': assert geobuf._lib is None, 'empty input loaded native code'

X = array('<f8',(2,3),[0,0,0, 1,1,1]); S = Arr('<f8',(1,3,3))
empty = Arr('<i8',(0,3)); mask = array('|b1',(2,),[True,False])
for cell in (0,-1,float('nan'),float('inf'),1e-320): reject(lambda: F.gap_over_buf(X,S,cell))
reject(lambda: F.order_limits_buf(X,X,mask,S,keep=-1))
reject(lambda: F.order_limits_buf(None,X,mask,S))
reject(lambda: F.order_limits_buf(X,X,Arr('|b1',(1,)),S))
reject(lambda: F.order_limits_buf(X,X,Arr('<i8',(2,)),S))
reject(lambda: F.order_limits_buf(Arr('<f8',(1,3)),X,mask,S))
for bad in (Arr('<f4',(2,3)),Arr('<f8',(6,)),Arr('<f8',(2,2))): reject(lambda: F.gap_over_buf(bad,S))
short = Arr('<f8',(2,3)); short.buf = bytearray(3)
reject(lambda: F.gap_over_buf(short,S))
stride = Arr('<f8',(2,3)); stride.buf = memoryview(bytearray(96))[::2]
reject(lambda: F.gap_over_buf(stride,S))
negative = Arr('<f8',(2,3)); negative.shape = (-2,3)
reject(lambda: F.gap_over_buf(negative,S))
for value in (float('nan'),float('inf'),1e100):
    reject(lambda: F.gap_over_buf(array('<f8',(1,3),[value,0,0]),S))
reject(lambda: F.gap_over_buf(X,array('<f8',(1,3,3),[float('inf')]*9)))
huge = array('<f8',(2,3),[0,0,0,200000000,0,200000000])
reject(lambda: F.gap_over_buf(huge,S))       # native grid size refusal, before allocation
for indices in ([0,1,-1],[0,1,2]):
    a = array('<i8',(1,3),indices)
    reject(lambda: F.bends_buf(X,a,a))
reject(lambda: F.bends_buf(X,empty,Arr('<i8',(1,3))))
reject(lambda: F.bends_buf(X,Arr('<i4',(1,3)),Arr('<i4',(1,3))))
assert not any(k.split('.')[0] in ('numpy','fastgeo','round1995') for k in sys.modules)
print('PASS: %d golden rounding cases; shape/storage/index/grid checks; input ownership; NumPy blocked' % len(cases))
