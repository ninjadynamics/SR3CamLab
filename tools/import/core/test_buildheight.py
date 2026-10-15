"""Frozen highest/nearest surface choices, attributes, ownership and bounds."""
import array,ctypes,gc,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
from buildheight import AttrField
data=json.loads((HERE/'build_height_golden.json').read_text())
def pack(tris,mode='owned'):
    raw=array.array('d',[v for t in tris for p in t for v in p]).tobytes()
    storage=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
    return Arr('<f8',(len(tris),3,3),storage)
for mode in ('owned','readonly','unaligned'):
    for name,c in data.items():
        t=pack(c['triangles'],mode)
        with AttrField(t,c['attributes'],c['cell']) as f:
            del t;gc.collect();out=[[f.at(x,z,yref),f.at2(x,z,0. if yref is None else yref)] for x,z,yref in c['queries']]
            assert json.dumps(out)==json.dumps(c['expected']),(name,mode,out,c['expected'])
        f.close()
        try:f.at(0,0)
        except ValueError:pass
        else:raise AssertionError('closed field accepted')
c=data['flat'];t=pack(c['triangles']);attr={'source':1}
with AttrField(t,[attr]) as f:
    t.view()[1]=100.;del t;gc.collect()
    assert f.at2(1,1,0.)==(0.,attr) and f.at2(1,1,0.)[1] is attr
    assert f.at(1e300,1e300) is None
with AttrField.from_records(zip(c['attributes'],c['triangles'])) as f:assert f.at(1,1)==0.
for triangles,attributes,cell in [(pack(c['triangles']),[],8.),(pack(c['triangles']),[1],0.),(pack([[[0.,0.,0.],[1e9,0.,0.],[0.,0.,1e9]]]),[1],1.),(pack([[[float('nan'),0.,0.]]*3]),[1],8.)]:
    try:AttrField(triangles,attributes,cell)
    except ValueError:pass
    else:raise AssertionError('invalid field accepted')
with AttrField(pack(c['triangles']),[1]) as f:
    try:f.at(float('inf'),0.)
    except ValueError:pass
    else:raise AssertionError('nonfinite query accepted')
assert 'numpy' not in sys.modules
print('PASS',len(data),'height scenes x three storage modes; attributes/snapshot/lifetime/bounds; NumPy blocked')
