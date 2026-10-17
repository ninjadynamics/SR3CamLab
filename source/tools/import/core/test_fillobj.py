"""Frozen authored geometry and exact OBJ/MTL bytes, NumPy blocked."""
import ctypes,importlib.abc,json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
import fillobj
data=json.loads((HERE/'fill_obj_golden.json').read_text())
with tempfile.TemporaryDirectory(prefix='sr3-fillobj-') as td:
    root=Path(td)
    for name,c in data['cases'].items():
        p=root/c['filename'];p.write_text(c['text']);logs=[];before=json.dumps(c)
        out=fillobj.props(p,c['rd'],c['zs']) if c['mode']=='props' else fillobj.handfill(p,c['rd'],c['zs']) if c['mode']=='fill' else fillobj.handmodel(p,c['rd'],c['faces'],c['zs'],logs.append)
        assert json.dumps(out)==json.dumps(c['expected']) and logs==c['logs'],(name,'geometry/log')
        assert before==json.dumps(c),(name,'mutation')
    for name,c in data['writers'].items():
        p=root/'saved.obj';fillobj.write_handfill(p,c['faces'],c['rd'],c['zs'],c['texdir'])
        assert p.read_bytes().hex()==c['obj'] and p.with_suffix('.mtl').read_bytes().hex()==c['mtl'],(name,'bytes')
    missing=root/'missing.obj';rd=dict(ox=0.,oz=0.)
    assert fillobj.props(missing,rd)==[] and fillobj.handfill(missing,rd)==[] and fillobj.handmodel(missing,rd,[])==[]
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'OBJ cases;',len(data['writers']),'writer byte pairs; missing paths; NumPy blocked')
