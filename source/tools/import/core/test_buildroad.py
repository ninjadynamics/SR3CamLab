"""Frozen bilinear road heights with NumPy blocked."""
import array,ctypes,gc,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
from buildroad import RoadHeight
cases=json.loads((HERE/'build_road_golden.json').read_text())
def storage(raw,mode):return bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
def road(c,mode):return {k:Arr(v['dtype'],tuple(v['shape']),storage(bytes.fromhex(v['hex']),mode)) if isinstance(v,dict) else v for k,v in c['rd'].items()}
def points(c,mode):return Arr('<f8',(len(c['points']),3),storage(array.array('d',[v for p in c['points'] for v in p]).tobytes(),mode))
for mode in ('owned','readonly','unaligned'):
    for name,c in cases.items():
        rd=road(c,mode);p=points(c,mode);before=bytes(p.buf)
        with RoadHeight(rd) as h:
            del rd;gc.collect();out=h(p)
            assert out.dtype=='<f8' and out.shape==(len(c['points']),) and bytes(out.buf).hex()==c['expected'],(name,mode)
            assert bytes(p.buf)==before
        h.close()
        try:h(p)
        except ValueError:pass
        else:raise AssertionError('closed road accepted')
c=cases['centers'];rd=road(c,'owned');p=points(c,'owned')
with RoadHeight(rd) as h:
    rd['V'].view()[1]=123.;rd['D'].view()[0]=44.;rd['lat'].view()[0]=99.;del rd;gc.collect()
    assert bytes(h(p).buf).hex()==c['expected'],'source mutation changed snapshot'
for kind in ('half_width','directions','nonfinite'):
    rd=road(c,'owned')
    if kind=='half_width':rd['hw']=0
    elif kind=='directions':rd['D']=Arr('<f8',(1,3))
    else:rd['V'].view()[0]=float('nan')
    try:RoadHeight(rd)
    except ValueError:pass
    else:raise AssertionError(('invalid accepted',kind))
assert 'numpy' not in sys.modules
print('PASS',len(cases),'road interpolation scenes x three storage modes; exact bytes/snapshot/lifetime/bounds; NumPy blocked')
