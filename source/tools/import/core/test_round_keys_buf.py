"""Frozen NumPy subdivision/keys, without importing NumPy: python -I test_round_keys_buf.py."""
import ctypes, importlib.abc, json, os, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE)); os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy': raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
import fastround as F
from npyio import Arr
def raw(a): return bytes(memoryview(a.buf).cast('B')[:a.nbytes])
def reject(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('Expected ValueError')
cases=json.loads((HERE/'round_keys_golden.json').read_text())['cases']
for name,case in cases.items():
    for mode in ('owned','readonly','unaligned'):
        d={}
        for k,v in case['inputs'].items():
            b=bytes.fromhex(v['hex'])
            buf=bytearray(b) if mode=='owned' else memoryview(b) if mode=='readonly' else memoryview(bytearray(b'x'+b))[1:]
            d[k]=Arr(v['dtype'],v['shape'],buf)
        before={k:raw(a) for k,a in d.items()}
        op=case['op']
        if op=='subdivide': got=F.subdivide_buf(d['P'],d['U'])
        elif op=='pack': got=(F.pack_keys_buf(d['P'],case['weld']),)
        elif op=='corner': got=(F.corner_keys_buf(d['P']),)
        else: got=(F.canon_keys_buf(d['K']),)
        for a,e in zip(got,case['expected']):
            assert (a.dtype,list(a.shape),raw(a).hex())==(e['dtype'],e['shape'],e['hex']),(name,mode)
        assert before=={k:raw(a) for k,a in d.items()},(name,'input modified')
P=Arr('<f8',(1,4,3)); U=Arr('<f8',(1,4,2))
reject(lambda:F.subdivide_buf(P,Arr('<f8',(2,4,2))))
reject(lambda:F.subdivide_buf(Arr('<f8',(1,5,3)),U))
reject(lambda:F.subdivide_buf(Arr('<f4',(1,4,3)),U))
reject(lambda:F.corner_keys_buf(Arr('<f8',(1,3,3))))
reject(lambda:F.corner_keys_buf(Arr('<i8',(1,4,3))))
reject(lambda:F.canon_keys_buf(Arr('<i8',(1,3))))
reject(lambda:F.canon_keys_buf(Arr('<f8',(1,4))))
reject(lambda:F.pack_keys_buf(Arr('<f8',(1,4,2)),.02))
for weld in (0,-1,float('nan'),float('inf')): reject(lambda:F.pack_keys_buf(P,weld))
for fn in (lambda a:F.subdivide_buf(a,U),lambda a:F.pack_keys_buf(a,.02),F.corner_keys_buf):
    a=Arr('<f8',(1,4,3)); a.buf=bytearray(8); reject(lambda:fn(a))
    a=Arr('<f8',(1,4,3)); a.buf=memoryview(bytearray(192))[::2]; reject(lambda:fn(a))
    a=Arr('<f8',(1,4,3)); a.shape=(-1,4,3); reject(lambda:fn(a))
assert not any(k.split('.')[0] in ('numpy','round1995','fastgeo') for k in sys.modules)
print('PASS:',len(cases),'golden cases, readonly/unaligned storage, input bounds and NumPy blocked')
