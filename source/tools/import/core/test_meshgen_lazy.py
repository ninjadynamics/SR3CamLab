"""Import/material operations stay NumPy-free; legacy mesh bytes stay unchanged."""
import ctypes,importlib.abc,json,os,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
block=Block();sys.meta_path.insert(0,block)
import meshgen as M,sbfw
assert 'VTX' not in vars(M) and 'VTX' in dir(M)
assert getattr(M,'missing_attribute',None) is None
assert M.quads_to_strip(2,True)==[0,1,3,2,2,4,4,5,7,6]
assert M.quads_to_strip(1,False)==[1,0,2,3]
assert M.ground_quads(0,0,4,4,2,4)==[[(0,2,0),(0,2,4),(4,2,4),(4,2,0)]]
assert len(M.box_quads(0,0,0,2,2,2))==5
tpl=sbfw.Ch(2,1,bytes(1848),[],[0x1bc])
for cutout in (False,True):
    for blend in (False,True):
        for two_sided in (False,True):
            out=M.clone_material(tpl,2,3,cutout=cutout,blend=blend,two_sided=two_sided)
            expected=bytearray(tpl.data);struct.pack_into('<I',expected,0x1bc,3)
            if cutout:struct.pack_into('<I',expected,0x4d4,1)
            if cutout or two_sided:struct.pack_into('<I',expected,0x50c,1)
            if blend:struct.pack_into('<I',expected,0x4e4,1)
            assert out.data==expected and out.id==2 and out.fix==tpl.fix and out.ref==tpl.ref
assert tpl.data==bytes(1848) and 'numpy' not in sys.modules
try:M.VTX
except RuntimeError:pass
else:raise AssertionError('dtype unexpectedly did not need NumPy')
assert 'VTX' not in vars(M)  # Failed optional import must not poison the cache.
sys.meta_path.remove(block)
import numpy as np
# First dtype user may be any legacy entry point, not just external M.VTX.
q=[[(0,0,0),(1,0,0),(1,0,1),(0,0,1)]]
v=M.make_verts(q);dtype=M.VTX
assert v.dtype is dtype and dtype.itemsize==48
from meshgen import VTX
assert VTX is dtype and M.VTX is dtype
assert dtype.names==('p','n','t','uv0','uv1')
cases=json.loads((HERE/'meshbuf_golden.json').read_text())['cases']
with np.errstate(all='ignore'):
    for name,c in cases.items():
        Q=np.frombuffer(bytes.fromhex(c['input']),'<f8').reshape(c['shape'])
        del M.VTX
        out=M.make_verts_safe(Q)
        assert out.tobytes().hex()==c['expected'],name
fixture=json.loads((HERE/'mesh_io_golden.json').read_text())
def chunk(e):return sbfw.Ch(1,e['id'],bytes.fromhex(e['data']),e['fix'],e['ref'])
tpl=chunk(fixture['template'])
for c in fixture['cases']:
    v=np.frombuffer(bytes.fromhex(c['verts']),M.VTX)
    del M.VTX
    with np.errstate(all='ignore'):
        out=M.clone_mesh(tpl,0x20202020,v,c['idx'],0x30303030,c['rename'])
        m=M.parse_mesh(out);w=M.winding_sign(out)
    e=c['expected']
    assert (out.id,out.data.hex(),out.fix,out.ref)==(e['id'],e['data'],e['fix'],e['ref']),c['name']
    assert not m['verts'].flags.writeable and not m['idx'].flags.writeable
    assert m['verts'].tobytes()==v.tobytes() and m['idx'].tolist()==c['idx']
    assert list(w)==c['winding'],c['name']
print('PASS NumPy-blocked import/material/topology, lazy dtype/retry/cache,',len(cases),'vertex and',len(fixture['cases']),'mesh I/O goldens')
