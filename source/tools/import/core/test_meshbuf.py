"""Frozen safe vertex bytes with NumPy blocked."""
import ctypes, importlib.abc, json, os, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE)); os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy': raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import meshbuf
cases=json.loads((HERE/'meshbuf_golden.json').read_text())['cases']
for name,c in cases.items():
    for mode in ('owned','readonly','unaligned'):
        raw=bytes.fromhex(c['input'])
        storage=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
        q=Arr('<f8',c['shape'],storage)
        out=meshbuf.make_verts_safe(q)
        assert (out.dtype,out.shape)==('|V48',(4*c['shape'][0],)),name
        assert bytes(out.buf).hex()==c['expected'],(name,mode)
        assert bytes(q.buf)==raw,(name,'input modified')
def reject(q):
    try: meshbuf.make_verts_safe(q)
    except ValueError: return
    raise AssertionError('Expected ValueError')
for q in (Arr('<f4',(1,4,3)),Arr('<f8',(1,3,3)),Arr('<f8',(1,4,2))): reject(q)
q=Arr('<f8',(1,4,3)); q.buf=bytearray(8); reject(q)
q=Arr('<f8',(1,4,3)); q.buf=memoryview(bytearray(192))[::2]; reject(q)
q=Arr('<f8',(1,4,3)); q.shape=(-1,4,3); reject(q)
assert 'numpy' not in sys.modules and 'meshgen' not in sys.modules
print('PASS',len(cases),'safe vertex cases, storage variants, bounds and NumPy blocked')
