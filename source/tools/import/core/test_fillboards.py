"""Frozen hanging-board decisions, NumPy blocked."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import fillboards,fillbuf
data=json.loads((HERE/'fill_boards_golden.json').read_text());count=0
for mode in ('owned','readonly','unaligned'):
    tiles={}
    for name,t in data['tiles'].items():
        raw=bytes.fromhex(t['hex']);buf=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
        tiles[name]=Arr('|b1',t['shape'],buf)
    for name,c in data['cases'].items():
        before=json.dumps(c['faces']);out,stats=fillboards.hanging_boards(c['faces'],tiles.get,gap=c['gap'],sunk=c['sunk'])
        assert json.loads(json.dumps(out))==c['expected'],(name,mode)
        assert stats==c['tiles'],(name,mode,'counts')
        assert json.dumps(c['faces'])==before
        with fillbuf.Index(c['faces']) as ix:
            assert fillboards.hanging_boards(c['faces'],tiles.get,gap=c['gap'],sunk=c['sunk'],ix=ix)==(out,stats)
            assert ix.h is not None
        count+=1
# Deliberately fail in the tile callback and verify the internally-owned grid
# is closed; an external grid must remain usable after the same exception.
original=fillboards.fillbuf.Index;made=[]
def tracked(faces):
    ix=original(faces);made.append(ix);return ix
def fail(mat):raise LookupError('fixture')
faces=data['cases']['hanging']['faces'];fillboards.fillbuf.Index=tracked
try:
    try:fillboards.hanging_boards(faces,fail)
    except LookupError:pass
    else:raise AssertionError('expected callback error')
    assert made and made[-1].h is None
finally:fillboards.fillbuf.Index=original
with original(faces) as ix:
    try:fillboards.hanging_boards(faces,fail,ix=ix)
    except LookupError:pass
    else:raise AssertionError('expected callback error')
    assert ix.h is not None
assert 'numpy' not in sys.modules
print('PASS',len(data['cases']),'board scenes x three storage modes, borrowed/owned index and exception cleanup; NumPy blocked')
