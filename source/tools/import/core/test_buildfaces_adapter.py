"""Current-state buffer adapter, legacy array contract and dispatch guards."""
import ctypes,json,os
from pathlib import Path
os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
import numpy as np
import build_classic as BC,buildfaces,fastgeo
from npyio import Arr

data=json.loads(Path(__file__).with_name('build_faces_golden.json').read_text())
def configure(p):
    BC.BUMP={};BC.BAKE_COLLECT=BC.BAKE_TABLE=BC.LM_COLLECT=BC.LM_TABLE=None;BC.SMOOTH_N={}
    BC.LIGHT_K=p['light_k'];BC.LIGHT_ENV=p.get('light_env',(.64,1.08,(0.,.94,-.34)))
    BC.LM_TEST=p.get('lm_test',False);BC.FLAT_LIT=set(p.get('flat_lit',()));BC.LM_CUTOUTS=set(p.get('lm_cutouts',()))

for name,c in data['cases'].items():
    for key,e in c['expected'].items():
        index,mode=key.split('-');p=data['policies'][int(index)];configure(p)
        for api in (BC.faces_to_mesh_buf,BC.faces_to_mesh):
            BC.KEEP_T='stale';v,n,cl=api(c['faces'],mode,p['up_normals'])
            raw=bytes(v.buf) if isinstance(v,Arr) else v.tobytes()
            assert raw.hex()==e['data'] and (n,cl)==(e['quads'],e['clamp']),(name,key,api.__name__)
            assert BC.KEEP_T is None
            if isinstance(v,Arr):assert v.dtype=='|V48' and v.shape==(n*4,) and isinstance(v.buf,bytearray)
            else:assert v.dtype==BC.meshgen.VTX and v.flags.owndata and v.flags.writeable
    configure(data['policies'][2]);BC.SMOOTH_N={tuple(k):np.array(v) for k,v in c['smooth_table']}
    v,_,_=BC.faces_to_mesh_buf(c['faces'],'tile',True)
    assert bytes(v.buf).hex()==c['smooth_expected'],(name,'smooth')
print('PASS both public APIs: 58 scenes x five policies x three UV modes, buffer smoothing',flush=True)

original=BC._faces_to_mesh_numpy;fast=buildfaces.faces_to_mesh;calls=[]
source=np.zeros(4,dtype=BC.meshgen.VTX);source['p'][0]=[1,2,3,1]
def reference(*args):
    calls.append(args);BC.KEEP_T='reference tangent';BC.LM_LAST='reference pages'
    return source,1,7
def forbidden(*args,**kw):raise AssertionError('fast path used for legacy policy')
BC._faces_to_mesh_numpy=reference;buildfaces.faces_to_mesh=forbidden
try:
    for guard in ('BAKE_COLLECT','BAKE_TABLE','LM_COLLECT','LM_TABLE','BUMP','ON','CHECK','axis'):
        configure(data['policies'][2]);old_on,old_check=fastgeo.ON,fastgeo.CHECK
        if guard=='ON':fastgeo.ON=False
        elif guard=='CHECK':fastgeo.CHECK=True
        elif guard=='axis':BC.LIGHT_ENV=(.5,1.,(1.,0.,0.))
        else:setattr(BC,guard,{'x':1} if guard=='BUMP' else [])
        try:
            v,n,cl=BC.faces_to_mesh_buf([],'tile',True)
            assert isinstance(v,Arr) and v.dtype=='|V48' and v.shape==(4,)
            assert bytes(v.buf)==source.tobytes() and (n,cl)==(1,7)
            assert BC.KEEP_T=='reference tangent' and BC.LM_LAST=='reference pages'
            v.buf[0]^=1;assert bytes(v.buf)!=source.tobytes()
            a,_,_=BC.faces_to_mesh([],'tile',True);assert a is source
        finally:fastgeo.ON,fastgeo.CHECK=old_on,old_check
    assert len(calls)==16
finally:BC._faces_to_mesh_numpy=original;buildfaces.faces_to_mesh=fast
configure(data['policies'][0]);v,n,cl=BC.faces_to_mesh_buf([],'tile')
assert v.shape==(0,) and v.nbytes==n==cl==0
print('PASS eight shared fallback guards, preserved side effects, owned writable buffer, empty mesh')
