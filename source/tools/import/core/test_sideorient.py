"""Frozen original fastside decisions and real-score scenes; NumPy blocked.

--numpy-scalars additionally tests the original NumPy scalar tie semantics,
with NumPy allowed only for constructing those input records.
"""
import ctypes,importlib.abc,json,os,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
numpy_scalars='--numpy-scalars' in sys.argv
if numpy_scalars: import numpy as np
else:
    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split('.')[0]=='numpy': raise RuntimeError('NumPy blocked')
    sys.meta_path.insert(0,Block())
from npyio import Arr
import sideorient,lightside
cases=json.loads((HERE/'side_orient_golden.json').read_text())['cases'];count=0
plain=lambda v:json.loads(json.dumps(v))
for name,c in cases.items():
    if (c['scalar']=='numpy')!=numpy_scalars: continue
    faces=c['faces']
    if numpy_scalars:faces=[(m,s,[[np.float64(v) for v in p] for p in ps],uv) for m,s,ps,uv in faces]
    before=plain(faces)
    for mode in ('owned','readonly','unaligned'):
        scores=None
        if c['scores'] is not None:
            vals=[v for row in c['scores'] for v in row];raw=struct.pack('<%df'%len(vals),*vals)
            b=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
            scores=Arr('<f4',(len(faces),4),b)
        logs=[];out,info,sc=sideorient.orient(faces,logs.append,scores=scores)
        assert plain([out,info,logs])==c['expected'],(name,mode,info,c['expected'][1])
        assert bytes(sc.buf).hex()==c['score_hex'],(name,mode,'scores')
        assert plain(faces)==before,(name,'input mutated')
        if scores is not None:assert bytes(scores.buf)==raw
        for i,(mat,sec,p,uv) in enumerate(faces):
            if str(mat).split('|')[0].endswith('_t') or sec=='sea' or str(sec).startswith('gate_'):
                assert out[i] is faces[i],(name,'inactive record identity')
        if c['scores'] is None:
            logs=[];r=lightside.orient_buf(faces,logs.append)
            assert plain([*r,logs])==c['expected']
            assert bytes(lightside.orient_buf.scores.buf)==bytes(sc.buf)
    count+=1
def reject(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Expected ValueError')
quiet=lambda s:None
fc=[('stone','house',[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)],[(0,0),(1,0),(0,1)])]
reject(lambda:sideorient.orient([],quiet))
reject(lambda:sideorient.orient([('s','h',[(0,0,0)]*2,[])],quiet))
for v in (float('inf'),float('nan'),10485.76,-10485.76):
    reject(lambda:sideorient.orient([('s','h',[(v,0,0),(1,0,0),(0,1,0)],[])],quiet))
reject(lambda:sideorient.orient(fc,quiet,scores=Arr('<f8',(1,4))))
reject(lambda:sideorient.orient(fc,quiet,scores=Arr('<f4',(2,4))))
reject(lambda:sideorient.orient(fc,quiet,scores=Arr('<f4',(1,4),struct.pack('<4f',float('nan'),0,0,0))))
if not numpy_scalars:assert 'numpy' not in sys.modules
print('PASS',count,'orientation cases, three storage modes, UV/identity/input checks, malformed bounds;', 'NumPy scalar compatibility' if numpy_scalars else 'NumPy blocked')
