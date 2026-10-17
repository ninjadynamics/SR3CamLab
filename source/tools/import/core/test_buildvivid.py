"""Frozen float32 color adjustments; no NumPy import."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import buildvivid
data=json.loads((HERE/'build_vivid_golden.json').read_text());raw=bytes.fromhex(data['rgb'])
for mode in ('owned','readonly','unaligned'):
    buf=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
    rgb=Arr('|u1',data['shape'],buf)
    for name,c in data['cases'].items():
        before=json.dumps(c);out=buildvivid.vivid(rgb,c['config'],c['scene_gain'],c['no_gain'])
        assert bytes(out.buf).hex()==c['expected'],(mode,name)
        assert bytes(rgb.buf)==raw and json.dumps(c)==before
        if not c['config']:assert out is rgb
        else:assert out is not rgb and not memoryview(out.buf).readonly
empty=Arr('|u1',(0,3,3));assert buildvivid.vivid(empty,[1.,1.]).nbytes==0
for cfg,gain in (([1],None),([1,1,-1],None),([float('nan'),1],None),([1,1],[1,2]),([1,1],float('inf')),([1e30,1],None)):
    try:buildvivid.vivid(rgb,cfg,gain)
    except ValueError:pass
    else:raise AssertionError(('accepted invalid policy',cfg,gain))
assert 'numpy' not in sys.modules
print('PASS 29 policies x 1261 pixels x three storage modes; identity, ownership, validation; NumPy blocked')
