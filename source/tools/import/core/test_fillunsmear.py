"""Frozen stretch-correction outputs with NumPy blocked."""
import ctypes,hashlib,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from fillunsmear import unsmear
def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest()
cases=json.loads((HERE/'fill_unsmear_golden.json').read_text())
for name,c in cases.items():
    before=digest(c['faces']);out,n=unsmear(c['faces'],c['labels'],skip={id(c['faces'][i]) for i in c['skip']},**c['opts'])
    assert n==c['count'] and digest(out)==c['expected'],(name,n,c['count'],out)
    assert [a is b for a,b in zip(c['faces'],out)]==c['same']
    assert all(a[2] is b[2] for a,b in zip(c['faces'],out)) and digest(c['faces'])==before
large=['rock',0,[(0.,0.,0.),(10.,0.,0.),(10.,0.,10.),(0.,0.,10.)]+[(0.,0.,0.)]*5,[(0.,0.)]*9]
try:unsmear([large],{'rock':'rock'})
except ValueError as exc:assert 'solver domain' in str(exc)
else:raise AssertionError('unsupported solver domain accepted')
assert 'numpy' not in sys.modules
print('PASS',len(cases),'unsmear scenes; exact geometry/count/identity; NumPy blocked')
