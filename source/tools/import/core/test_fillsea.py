"""Legacy frozen sea results and input preservation, NumPy blocked."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
import fillsea
cases=json.loads((HERE/'fill_sea_golden.json').read_text())
for name,c in cases.items():
    before=json.dumps(c);out=fillsea.sea_clip(c['sea'],c['land'],**c['kwargs'])
    assert json.dumps(out)==json.dumps(c['expected']),(name,'output')
    assert json.dumps(c)==before,(name,'mutation')
c=cases['no_land'];out=fillsea.sea_clip(c['sea'],c['land'],**c['kwargs'])
assert out[0][0][2] is c['sea'][0][2] and out[0][0][3] is c['sea'][0][3]
for name,value in [('step',0.),('sub',float('nan')),('cell',-1.),('step',100.)]:
    kw=dict(c['kwargs']);kw[name]=value
    try:fillsea.sea_clip(c['sea'],[],**kw)
    except ValueError:pass
    else:raise AssertionError(('invalid accepted',name,value))
assert 'numpy' not in sys.modules
print('PASS',len(cases),'frozen sea scenes; geometry/area/input preservation; NumPy blocked')
