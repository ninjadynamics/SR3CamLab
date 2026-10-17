"""Frozen road strip/proxy cases with NumPy blocked."""
import importlib.abc,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import fillroad
cases=json.loads((HERE/'fill_road_golden.json').read_text())['cases']
for name,c in cases.items():
    for mode in ('owned','readonly','unaligned'):
        rd={'hw':c['hw']}
        for k,a in c['inputs'].items():
            b=bytes.fromhex(a['hex']);buf=bytearray(b) if mode=='owned' else memoryview(b) if mode=='readonly' else memoryview(bytearray(b'x'+b))[1:]
            rd[k]=Arr(a['dtype'],a['shape'],buf)
        before={k:bytes(v.buf) for k,v in rd.items() if k!='hw'}
        limits=fillroad.strip(rd);assert [v.tolist() for v in limits]==c['limits'],(name,mode,'limits')
        out=fillroad.road_faces(rd);assert json.dumps(out)==json.dumps(c['faces']),(name,mode,'faces')
        cached=fillroad.road_faces(rd);assert cached==out and cached is not out
        if out:assert cached[0] is out[0]
        assert before=={k:bytes(v.buf) for k,v in rd.items() if k!='hw'}
def reject(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Expected ValueError')
rd=dict(V=Arr('<f8',(2,3,3)),code=Arr('<i4',(2,3)),hw=1)
a=fillroad.road_faces(rd);assert len(a)==4
rd['code'].view()[1]=-1;b=fillroad.road_faces(rd);assert b==[]
rd['code'].view()[1]=0;rd['V'].view()[0]=42.;b=fillroad.road_faces(rd);assert b[0][2][0][0]==42.
rd['wr']=Arr('<f8',(2,));b=fillroad.road_faces(rd);assert len(b)==2
reject(lambda:fillroad.road_faces(dict(rd,hw=2)))
reject(lambda:fillroad.road_faces(dict(rd,code=Arr('<i4',(1,3)))))
reject(lambda:fillroad.strip(dict(rd,wl=Arr('<f8',(1,)))))
bad=Arr('<f8',(2,));bad.view()[0]=float('nan');reject(lambda:fillroad.strip(dict(rd,wl=bad)))
bad=Arr('<f8',(2,3,3));bad.buf=bytearray(1);reject(lambda:fillroad.strip(dict(rd,V=bad)))
assert fillroad.road_faces(None)==[]
assert 'numpy' not in sys.modules
print('PASS',len(cases),'road scenes, three storage modes, cache invalidation and bounds; NumPy blocked')
