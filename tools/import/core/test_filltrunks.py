"""Frozen trunk outputs, all scalar counts and removed-board indices; no NumPy."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import filltrunks
data=json.loads((HERE/'fill_trunks_golden.json').read_text());count=0
for mode in ('owned','readonly','unaligned'):
    rgba={};alpha={}
    def storage(b):return bytearray(b) if mode=='owned' else memoryview(b) if mode=='readonly' else memoryview(bytearray(b'x'+b))[1:]
    for name,c in data['tiles'].items():
        h,w,_=c['shape'];raw=bytes.fromhex(c['hex']);rgba[name]=Arr('|u1',(h,w,4),storage(raw));alpha[name]=Arr('|b1',(h,w),storage(bytes(a>127 for a in raw[3::4])))
    for name,c in data['cases'].items():
        before=json.dumps(c['faces']);out,info,removed=filltrunks.extend_trunks(c['faces'],alpha.get,rgba.get,labels=data['labels'],**c['kwargs'])
        assert json.dumps(out)==json.dumps(c['expected']),(name,mode,'geometry')
        assert info==c['info'],(name,mode,info,c['info'])
        assert removed==c['ungrounded'],(name,mode,'ungrounded')
        assert before==json.dumps(c['faces']);count+=1
try:filltrunks.extend_trunks([],alpha.get,rgba.get,classes=['stem'])
except ValueError:pass
else:raise AssertionError('missing labels accepted')
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'trunk scenes x three image storage modes; geometry/info/removals/input preservation; NumPy blocked')
