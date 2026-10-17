"""Frozen normals/table order and ground-callback data with NumPy blocked."""
import array,ctypes,hashlib,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
from buildnormals import oriented_normals,smooth_normals
def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest()
def storage(raw,mode):return bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
cases=json.loads((HERE/'build_normals_golden.json').read_text())
for name,c in cases.items():
    for mode in ('owned','readonly','unaligned'):
        raw=array.array('d',[x for p in c['road'] for x in p]).tobytes();road=Arr('<f8',(len(c['road']),2),storage(raw,mode));calls=[]
        def ground(x,z,base):
            idx=len(calls);calls.append([x.shape[0],hashlib.sha256(bytes(x.buf)+bytes(z.buf)+bytes(base.buf)).hexdigest()])
            raw=array.array('d',[c['heights'][idx%len(c['heights'])]]*x.shape[0]).tobytes();return Arr('<f8',x.shape,storage(raw,mode))
        callback=ground if c['heights'] is not None else None
        n=oriented_normals(c['polygons'],road,callback)
        assert bytes(n.buf).hex()==c['normals'] and calls==c['normal_calls'],('normals',name,mode)
        calls.clear();sm=smooth_normals([('tile',0,p,[]) for p in c['polygons']],road,callback)
        assert len(sm)==c['keys'] and digest([[list(k),list(v)] for k,v in sm.items()])==c['smooth'] and calls==c['smooth_calls'],('smooth',name,mode)
        assert bytes(road.buf)==raw
for polygons,road in (([[]],Arr('<f8',(1,2))),([[(float('nan'),0.,0.)]],Arr('<f8',(1,2))),([[(0.,0.,0.)]],Arr('<f8',(0,2)))):
    try:oriented_normals(polygons,road)
    except ValueError:pass
    else:raise AssertionError('invalid input accepted')
try:oriented_normals(cases['wall']['polygons'],Arr('<f8',(1,2)),lambda *args:Arr('<f8',(0,)))
except ValueError:pass
else:raise AssertionError('ground length mismatch accepted')
assert 'numpy' not in sys.modules
print('PASS',len(cases),'normal-table scenes x three storage modes; exact normals/keys/callbacks; NumPy blocked')
