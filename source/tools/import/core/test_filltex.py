"""Original leaf/stem results with NumPy blocked, including UV wrap and ties."""
import importlib.abc,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import filltex
cases=json.loads((HERE/'fill_texture_golden.json').read_text())['cases'];count=0
for name,c in cases.items():
    h,w,_=c['shape'];raw=bytes.fromhex(c['rgba']);alpha=bytes(a>127 for a in raw[3::4])
    for mode in ('owned','readonly','unaligned'):
        def storage(b):return bytearray(b) if mode=='owned' else memoryview(b) if mode=='readonly' else memoryview(bytearray(b'x'+b))[1:]
        rgba=Arr('|u1',(h,w,4),storage(raw));al=Arr('|b1',(h,w),storage(alpha))
        for row,v,u0,u1,frac,runs,leaf in c['queries']:
            assert filltex.stem_runs(al,row,u0,u1)==(frac,runs),(name,mode,row,u0,u1)
            assert filltex.leaf_row(rgba,v,u0,u1)==leaf,(name,mode,'leaf',v,u0,u1)
            count+=1
        assert bytes(rgba.buf)==raw and bytes(al.buf)==alpha
def reject(fn):
    try:fn()
    except (ValueError,OverflowError):return
    raise AssertionError('Expected invalid-input failure')
reject(lambda:filltex.stem_runs(Arr('|b1',(0,3)),0,0.,1.))
reject(lambda:filltex.leaf_row(Arr('|u1',(1,3,3)),0.,0.,1.))
reject(lambda:filltex.stem_runs(al,h,0.,1.))
reject(lambda:filltex.stem_runs(al,0,float('nan'),1.))
bad=Arr('|u1',(1,1,4));bad.buf=bytearray(1);reject(lambda:filltex.leaf_row(bad,0.,0.,1.))
assert 'numpy' not in sys.modules
print('PASS',len(cases),'images,',count,'row samples across three storage modes; NumPy blocked')
