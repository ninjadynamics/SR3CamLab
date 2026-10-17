"""Frozen IndexC results, ordinary Python numbers, no NumPy."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
import fillbuf
cases=json.loads((HERE/'fill_index_golden.json').read_text())['cases']
for name,c in cases.items():
    before=json.dumps(c['faces'])
    with fillbuf.Index(c['faces'],c['cell']) as ix:
        result=[[ix.heights(x,z,op),ix.uprights(x,z,r)] for x,z,op,r in c['queries']]
        assert json.dumps(result)==json.dumps(c['expected']),name
        if name.startswith('grow'):assert ix.cap>512
    assert json.dumps(c['faces'])==before
    assert ix.h is None;ix.close()
def reject(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Expected ValueError')
faces=cases['floor']['faces']
for cell in (0,-1,float('nan'),float('inf'),1e-300):reject(lambda:fillbuf.Index(faces,cell))
reject(lambda:fillbuf.Index([('s','p',[],[])]))
for v in (float('nan'),float('inf'),1e100):reject(lambda:fillbuf.Index([('s','p',[(v,0,0)],[])]))
with fillbuf.Index(faces) as ix:
    assert ix.heights(1e300,1e300)==[]
    reject(lambda:ix.heights(float('nan'),0))
    reject(lambda:ix.uprights(0,0,-1))
    reject(lambda:ix.uprights(0,0,float('inf')))
reject(lambda:ix.heights(0,0));reject(lambda:ix.uprights(0,0))
assert 'numpy' not in sys.modules
print('PASS',len(cases),'index scenes; capacity growth, finite bounds and close checks; NumPy blocked')
