"""Forest-verge fixtures, including selection boundaries, without NumPy."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import fillverge
cases=json.loads((HERE/'fill_verge_golden.json').read_text())
for mode in ('owned','readonly','unaligned'):
    def storage(raw):return bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
    for name,c in cases.items():
        rd={k:Arr(v['dtype'],tuple(v['shape']),storage(bytes.fromhex(v['hex']))) if isinstance(v,dict) else v for k,v in c['rd'].items()};before=json.dumps(c);logs=[]
        out=fillverge.retile_verge(c['verge'],c['faces'],rd,c['labels'],origin=c['origin'],log=logs.append,reach=c['reach'])
        assert json.dumps(out)==json.dumps(c['expected']) and logs==c['logs'],(name,mode,'selection/log')
        assert (out is c['verge'])==c['same'],(name,'outer identity')
        assert all(a[2] is b[2] and a[3] is b[3] for a,b in zip(out,c['verge'])),(name,'corner/uv identity')
        assert before==json.dumps(c),(name,'mutation')
assert 'numpy' not in sys.modules
print('PASS',len(cases),'verge scenes x three storage modes; materials/logs/identity; NumPy blocked')
