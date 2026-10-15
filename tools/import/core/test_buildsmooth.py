"""Frozen smoothing results and safe buffer ownership, NumPy blocked."""
import array,ctypes,gc,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from buildsmooth import Smooth
from npyio import Arr
cases=json.loads((HERE/'build_smooth_golden.json').read_text())
def arr(rows,dtype,mode):
    raw=array.array('f' if dtype=='<f4' else 'd',[x for row in rows for x in row]).tobytes()
    buf=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
    return Arr(dtype,(len(rows),len(rows[0]) if rows else 3),buf)
for name,c in cases.items():
    for mode in ('owned','readonly','unaligned'):
        table={tuple(k):list(v) for k,v in c['table']};s=Smooth(table)
        for v in table.values():v[:]=[42.]*3
        del table;gc.collect()
        for stride in (3,4):
            p=arr([row+([1.] if stride==4 else []) for row in c['positions']],'<f4',mode);n=arr(c['normals'],'<f8',mode)
            before=(bytes(n.buf),bytes(p.buf));out=s.apply(n,p)
            assert out.dtype=='<f8' and out.shape==n.shape and bytes(out.buf).hex()==c['expected'],(name,mode,stride)
            assert (bytes(n.buf),bytes(p.buf))==before
s=Smooth({(0,0,0):(1,0,0)})
for n,p in ((Arr('<f4',(1,3)),Arr('<f4',(1,3))),(Arr('<f8',(1,3)),Arr('<f8',(1,3))),(Arr('<f8',(1,3)),Arr('<f4',(2,3)))):
    try:s.apply(n,p)
    except ValueError:pass
    else:raise AssertionError('invalid buffer accepted')
for table in ({(float('nan'),0,0):(1,0,0)},{(0,0,0):(float('inf'),0,0)},{(0,0):(1,0,0)}):
    try:Smooth(table)
    except ValueError:pass
    else:raise AssertionError('invalid table accepted')
assert 'numpy' not in sys.modules
print('PASS',len(cases),'smooth scenes x three storage modes / two strides; exact bytes/snapshots; NumPy blocked')
