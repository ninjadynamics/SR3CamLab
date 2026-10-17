"""Full packed vertex bytes for geometry and explicit lighting policies."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
import buildfaces,buildsmooth
data=json.loads((HERE/'build_faces_golden.json').read_text())
for name,c in data['cases'].items():
    before=json.dumps(c['faces'])
    for key,expected in c['expected'].items():
        index,mode=key.split('-');v,n,clamp=buildfaces.faces_to_mesh(c['faces'],mode,**data['policies'][int(index)])
        assert (n,clamp)==(expected['quads'],expected['clamp']),(name,key,'metadata')
        if bytes(v.buf).hex()!=expected['data']:
            old=bytes.fromhex(expected['data']);bad=[i for i,(a,b) in enumerate(zip(v.buf,old)) if a!=b]
            raise AssertionError((name,key,'bytes',bad[:16]))
    smooth=buildsmooth.Smooth({tuple(k):v for k,v in c['smooth_table']})
    v,_,_=buildfaces.faces_to_mesh(c['faces'],'tile',smooth=smooth,**data['policies'][2])
    assert bytes(v.buf).hex()==c['smooth_expected'],(name,'smooth')
    assert json.dumps(c['faces'])==before,name
v,n,c=buildfaces.faces_to_mesh([],'tile');assert v.nbytes==n==c==0
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'scenes x five lighting policies x three UV modes; packed bytes exact, NumPy blocked')
