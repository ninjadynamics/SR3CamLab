"""Native ring-search wrappers: frozen results, ownership, bounds and lifetime."""
import array,ctypes,gc,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
from buildnear import Near
data=json.loads((HERE/'build_near_golden.json').read_text())
def pack(rows,mode='owned'):
    raw=array.array('d',[v for r in rows for v in r]).tobytes()
    storage=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
    return Arr('<f8',(len(rows),2),storage)
for mode in ('owned','readonly','unaligned'):
    for name,c in data.items():
        p=pack(c['points'],mode);q=pack(c['queries'],mode);before=bytes(q.buf)
        with Near(p,c['cell']) as near:
            del p;gc.collect();out=near(q)
            assert out.dtype=='<i4' and out.shape==(len(c['queries']),) and bytes(out.buf).hex()==c['bytes'],(name,mode)
            assert bytes(q.buf)==before
        near.close()
        try:near(q)
        except ValueError:pass
        else:raise AssertionError('closed index accepted')
p=pack([[0.,0.],[10.,0.]]);near=Near(p);p.view()[0]=100.;del p;gc.collect()
assert list(near(pack([[0.,0.]])).view())==[0],'source mutation changed snapshot'
near.close()
for p,cell in [(pack([[0,0]]),0.),(pack([[float('nan'),0.]]),8.),(pack([[1e300,0.]]),8.),(pack([[0,0],[1000000,1000000]]),1.),(Arr('<f4',(1,2)),8.)]:
    try:Near(p,cell)
    except ValueError:pass
    else:raise AssertionError('invalid grid accepted')
with Near(pack([[0,0]])) as near:
    try:near(pack([[float('inf'),0.]]))
    except ValueError:pass
    else:raise AssertionError('invalid query accepted')
assert 'numpy' not in sys.modules
print('PASS',len(data),'Near scenes x three storage modes; snapshot/lifetime/bounds; NumPy blocked')
