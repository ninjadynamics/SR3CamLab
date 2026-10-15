"""Legacy overlap counts and material samples with NumPy blocked."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
import fillcheck
data=json.loads((HERE/'fill_check_golden.json').read_text())
for name,c in data['cases'].items():
    before=json.dumps(c);out=fillcheck.coplanar_report(c['old'],c['new'],c['tol'])
    assert json.dumps(out)==json.dumps(c['expected']),(name,out,c['expected'])
    assert before==json.dumps(c),(name,'mutation')
for name,c in data['overlaps'].items():assert fillcheck.overlap2d(c['a'],c['b'],c['shrink'])==c['expected'],name
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'coplanar scenes;',len(data['overlaps']),'overlap cases; NumPy blocked')
