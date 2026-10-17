"""Frozen backdrop lid geometry, chain order and triangulation; NumPy blocked."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import fillisland
data=json.loads((HERE/'fill_island_golden.json').read_text())
for mode in ('owned','readonly','unaligned'):
    tiles={}
    for name,t in data['tiles'].items():
        raw=bytes.fromhex(t['hex']);storage=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
        tiles[name]=Arr('|b1',tuple(t['shape']),storage)
    for name,c in data['cases'].items():
        before=json.dumps(c['faces']);out=fillisland.island_cap(c['faces'],tiles.get,**c['kwargs'])
        assert json.dumps(out)==json.dumps(c['expected']),(name,mode,'output',out,c['expected'])
        assert before==json.dumps(c['faces']),(name,'mutation')
for name,c in data['chains'].items():assert json.dumps(fillisland.chains(c['edges']))==json.dumps(c['expected']),('chain',name)
for name,c in data['ears'].items():assert json.dumps(fillisland.ears(c['points']))==json.dumps(c['expected']),('ears',name)
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'island scenes x three storage modes;',len(data['chains']),'chains;',len(data['ears']),'triangulations; NumPy blocked')
