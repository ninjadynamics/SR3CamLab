"""Frozen UV subdivision geometry, ordering and depth limit, NumPy blocked."""
import ctypes,hashlib,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from builduv import uv_split
def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest()
cases=json.loads((HERE/'build_uv_golden.json').read_text())
for name,c in cases.items():
    before=digest(c['faces']);out,n=uv_split(c['faces'],c['maxspan'])
    assert n==c['split'] and len(out)==c['count'] and digest(out)==c['expected'],name
    assert digest(c['faces'])==before
fc=cases['fit']['faces'][0];out,n=uv_split([fc]);assert out[0][2] is fc[2] and out[0][3] is fc[3]
for span in (0.,-1.,float('inf'),float('nan')):
    try:uv_split([fc],span)
    except ValueError:pass
    else:raise AssertionError('invalid span accepted')
for bad in ([('x',0,[],[])],[('x',0,[(0,0,0)]*3,[(0,0)]*2)],[('x',0,[(0,0,0)]*3,[(float('inf'),0)]*3)],[('x',0,[(0,0,0)]*3,[(0,0),(100000,0),(0,100000)])]):
    try:uv_split(bad)
    except ValueError:pass
    else:raise AssertionError('invalid/unbounded polygon accepted')
assert 'numpy' not in sys.modules
print('PASS',len(cases),'UV subdivision scenes; exact geometry/order/depth; NumPy blocked')
