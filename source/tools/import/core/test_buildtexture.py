"""Frozen DXT5 header/mip bytes and checked storage, NumPy blocked."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import buildtexture as B,sbfw
data=json.loads((HERE/'build_texture_golden.json').read_text());tpl=sbfw.Ch(4,123,bytes.fromhex(data['header']),[2],[3])
for mode in ('owned','readonly','unaligned'):
    def make(dtype,shape,raw):
        buf=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
        return Arr(dtype,shape,buf)
    for name,c in data['cases'].items():
        rgb=make('|u1',c['shape'],bytes.fromhex(c['rgb']));mask=make('|b1',c['shape'][:2],bytes.fromhex(c['mask']))
        out=B.make_texture_dxt5(tpl,456,rgb,mask)
        assert out.data.hex()==c['data'],(name,mode)
        assert (out.kind,out.id,out.fix,out.ref)==(4,456,[],[])
        assert bytes(rgb.buf).hex()==c['rgb'] and bytes(mask.buf).hex()==c['mask']
        if name.endswith('-opaque'):assert B.make_texture_dxt5(tpl,456,rgb,None).data==out.data
        calls=[]
        def adjust(a):calls.append(a.shape);return Arr('|u1',a.shape,bytes(a.buf))
        assert B.make_texture_dxt5(tpl,456,rgb,mask,adjust).data==out.data and calls==[tuple(c['shape'])]
assert tpl.data.hex()==data['header'] and tpl.fix==[2] and tpl.ref==[3]
valid=Arr('|u1',(4,4,3));mask=Arr('|b1',(4,4))
for image,hole in ((Arr('|u1',(0,4,3)),None),(Arr('|u1',(6,8,3)),None),(Arr('<f4',(4,4,3)),None),(valid,Arr('|b1',(3,4))),(valid,Arr('|u1',(4,4)))):
    try:B.make_texture_dxt5(tpl,456,image,hole)
    except ValueError:pass
    else:raise AssertionError('accepted invalid input')
try:B.make_texture_dxt5(tpl,456,valid,mask,lambda a:Arr('|u1',(8,4,3)))
except ValueError:pass
else:raise AssertionError('accepted shape-changing callback')
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'DXT5 cases x three storage modes; headers/mips/masks/callback/validation; NumPy blocked')
