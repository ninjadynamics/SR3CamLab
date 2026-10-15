"""Frozen grid geometry and callback grouping; no NumPy imports allowed."""
import array,ctypes,hashlib,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
from buildpieces import pieces,drape,split_faces
def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest()
cases=json.loads((HERE/'build_pieces_golden.json').read_text())
for mode in ('owned','readonly','unaligned'):
    for name,c in cases.items():
        calls=[]
        def height(p):
            assert p.dtype=='<f8' and p.shape[1:]==(3,)
            calls.append([p.shape[0],hashlib.sha256(p.buf).hexdigest()]);v=p.view()
            raw=array.array('d',[(v[i]*.25+v[i+2]*.125)+v[i+1]*.0625 for i in range(0,len(v),3)]).tobytes()
            buf=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
            return Arr('<f8',(p.shape[0],),buf)
        before=digest(c['faces'])
        out=drape(c['faces'],height,c['lift'],c['maxlen']) if c['drape'] else split_faces(c['faces'],c['maxlen'])
        assert len(out)==c['count'] and digest(out)==c['expected'],(name,mode)
        assert calls==c['calls'],('callbacks',name,mode)
        assert digest(c['faces'])==before
for bad in ([('a',0,[],[])],[('a',0,[(0,0,0)]*3,[(0,0)]*2)],[('a',0,[(0,0)]*3,[(0,0)]*3)]):
    assert pieces(bad,1.) is None
fc=cases['quad']['faces']
for maxlen in (0.,-1.,float('nan'),float('inf'),1e-300):
    try:pieces(fc,maxlen)
    except ValueError:pass
    else:raise AssertionError('bad maxlen accepted')
for wrong in (Arr('<f8',(1,)),Arr('<f4',(20,)),Arr('<f8',(20,1))):
    try:drape(fc,lambda p:wrong,.03)
    except ValueError:pass
    else:raise AssertionError('bad heights accepted')
for value in (float('inf'),float('nan'),1e60):
    bad=json.loads(json.dumps(fc));bad[0][2][0][0]=value
    try:pieces(bad,1.)
    except ValueError:pass
    else:raise AssertionError('bad coordinate accepted')
try:drape(fc,lambda p:(_ for _ in ()).throw(RuntimeError('callback failed')),.03)
except RuntimeError as exc:assert str(exc)=='callback failed'
else:raise AssertionError('callback failure swallowed')
assert 'numpy' not in sys.modules
print('PASS',len(cases),'split/drape scenes x three callback storage modes; exact geometry/order; NumPy blocked')
