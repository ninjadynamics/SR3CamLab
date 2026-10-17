"""Packed mesh parser/clone/winding against frozen legacy results, NumPy blocked."""
import ctypes,importlib.abc,json,os,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE)); os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy': raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
import meshbuf as M, sbfw
from npyio import Arr
def chunk(e): return sbfw.Ch(1,e['id'],bytes.fromhex(e['data']),e['fix'],e['ref'])
def reject(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('Expected ValueError')
fixture=json.loads((HERE/'mesh_io_golden.json').read_text()); tpl=chunk(fixture['template'])
for c in fixture['cases']:
    for mode in ('owned','readonly','unaligned'):
        vb=bytes.fromhex(c['verts']); ib=struct.pack('<%dH'%len(c['idx']),*c['idx'])
        def buf(b): return bytearray(b) if mode=='owned' else memoryview(b) if mode=='readonly' else memoryview(bytearray(b'x'+b))[1:]
        v=Arr('|V48',(len(vb)//48,),buf(vb)); idx=Arr('<u2',(len(c['idx']),),buf(ib))
        out=M.clone_mesh(tpl,0x20202020,v,idx,0x30303030,c['rename']); e=c['expected']
        assert (out.id,out.data.hex(),out.fix,out.ref)==(e['id'],e['data'],e['fix'],e['ref']),(c['name'],mode,'clone')
        p=M.parse_mesh(out)
        assert bytes(p['verts'].buf)==vb and bytes(p['idx'].buf)==ib
        assert p['verts'].buf.readonly and p['idx'].buf.readonly
        assert list(M.winding_sign(out))==c['winding'],(c['name'],mode,'winding')
        assert bytes(v.buf)==vb and bytes(idx.buf)==ib
v=Arr('|V48',(1,)); idx=Arr('<u2',(1,))
reject(lambda:M.clone_mesh(tpl,1,Arr('|V48',(0,)),idx,2))
reject(lambda:M.clone_mesh(tpl,1,v,Arr('<u2',(0,)),2))
reject(lambda:M.clone_mesh(tpl,1,Arr('<f4',(1,)),idx,2))
reject(lambda:M.clone_mesh(tpl,1,v,Arr('<i2',(1,)),2))
for cut in (0,71,100,len(tpl.data)-155):
    bad=tpl.copy(); bad.data=bad.data[:cut]; reject(lambda:M.parse_mesh(bad))
bad=tpl.copy(); raw=bytearray(bad.data); struct.pack_into('<I',raw,48,0xffffffff); bad.data=bytes(raw); reject(lambda:M.parse_mesh(bad))
bad=tpl.copy(); p=M.parse_mesh(bad); raw=bytearray(bad.data); struct.pack_into('<H',raw,p['pi'],65000); bad.data=bytes(raw); reject(lambda:M.winding_sign(bad))
assert 'numpy' not in sys.modules and 'meshgen' not in sys.modules
print('PASS',len(fixture['cases']),'clone/parser/winding cases, storage variants, malformed ranges; NumPy blocked')
