"""Frozen mesh UV intermediate and packed bytes with NumPy blocked."""
import array,ctypes,hashlib,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
from buildmesh import mesh_uv,pack_uv
def digest(a):return hashlib.sha256(a.buf).hexdigest()
def storage(raw,mode):return bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
data=json.loads((HERE/'build_mesh_golden.json').read_text())
for name,c in data['cases'].items():
    before=json.dumps(c['faces'])
    for mode,expected in c['expected'].items():
        q,u,clamp=mesh_uv(c['faces'],mode)
        assert q.shape==(len(c['faces']),4,3) and u.shape==(len(c['faces']),4,2)
        for st in ('owned','readonly','unaligned'):
            p=pack_uv(Arr('<f8',u.shape,storage(bytes(u.buf),st)))
            assert p.dtype=='<u2' and p.shape==(len(c['faces'])*4,2)
            actual=dict(quads=digest(q),uv=digest(u),packed=digest(p),clamp=clamp)
            assert actual==expected,(name,mode,st,actual,expected)
    assert json.dumps(c['faces'])==before
v=data['packing']['values'];raw=array.array('d',v).tobytes()
for st in ('owned','readonly','unaligned'):
    assert bytes(pack_uv(Arr('<f8',(len(v)//8,4,2),storage(raw,st))).buf).hex()==data['packing']['expected']
for bad in ([('a',0,[],[])],[('a',0,[(0,0,0)]*3,[(0,0)]*2)]):assert mesh_uv(bad,'tile') is None
for value in (float('nan'),float('inf')):
    a=Arr('<f8',(1,4,2));a.view()[0]=value
    try:pack_uv(a)
    except ValueError:pass
    else:raise AssertionError('nonfinite UV accepted')
for a in (Arr('<f4',(1,4,2)),Arr('<f8',(4,2))):
    try:pack_uv(a)
    except ValueError:pass
    else:raise AssertionError('invalid UV layout accepted')
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'mesh scenes x three modes/storage; exact intermediate/packed bytes; NumPy blocked')
