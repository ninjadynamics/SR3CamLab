"""Frozen material selection and verge/slope geometry, NumPy blocked."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import fillskirts
data=json.loads((HERE/'fill_skirts_golden.json').read_text())
for mode in ('owned','readonly','unaligned'):
    def storage(raw):return bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
    tiles={name:Arr('|b1',tuple(t['shape']),storage(bytes.fromhex(t['hex']))) for name,t in data['tiles'].items()}
    for name,c in data['cases'].items():
        rd={k:Arr(v['dtype'],tuple(v['shape']),storage(bytes.fromhex(v['hex']))) if isinstance(v,dict) else v for k,v in c['rd'].items()}
        before=json.dumps(c['faces']);buffers={k:bytes(v.buf) for k,v in rd.items() if isinstance(v,Arr)}
        out=fillskirts.ground_skirts(c['faces'],rd,tiles.get,labels=c['labels'],**c['kwargs'])
        assert json.dumps(out)==json.dumps(c['expected']),(name,mode,'geometry/counts',out[1:],c['expected'][1:])
        assert before==json.dumps(c['faces']) and all(bytes(rd[k].buf)==v for k,v in buffers.items()),(name,'mutation')
for name,c in data['selectors'].items():assert fillskirts.label_tile(c['faces'],c['labels'])==c['expected'],name
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'skirt scenes x three storage modes;',len(data['selectors']),'material selectors; NumPy blocked')
