"""Frozen light-side scores; run with NumPy blocked."""
import ctypes,importlib.abc,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE)); os.environ.setdefault('OMP_NUM_THREADS','4')
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy': raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import sidebuf
cases=json.loads((HERE/'side_scores_golden.json').read_text())['cases']
for name,c in cases.items():
    for mode in ('owned','readonly','unaligned'):
        args={}
        for k,v in c['inputs'].items():
            raw=bytes.fromhex(v['hex']); b=bytearray(raw) if mode=='owned' else memoryview(raw) if mode=='readonly' else memoryview(bytearray(b'x'+raw))[1:]
            args[k]=Arr(v['dtype'],v['shape'],b)
        before={k:bytes(v.buf) for k,v in args.items()}
        out=sidebuf.scores(**args); e=c['expected']
        assert (out.dtype,list(out.shape),bytes(out.buf).hex())==(e['dtype'],e['shape'],e['hex']),(name,mode)
        assert before=={k:bytes(v.buf) for k,v in args.items()}
def reject(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('Expected ValueError')
V=Arr('<f8',(1,3)); F=Arr('<i8',(1,4)); A=Arr('|b1',(1,))
reject(lambda:sidebuf.scores(V,F,Arr('|b1',(2,))))
reject(lambda:sidebuf.scores(Arr('<f4',(1,3)),F,A))
reject(lambda:sidebuf.scores(V,Arr('<i8',(1,3)),A))
for index in (-1,1,2**63-1):
    F.view()[0]=index; reject(lambda:sidebuf.scores(V,F,A))
F.view()[0]=0
bad=Arr('<f8',(1,3)); bad.buf=bytearray(1); reject(lambda:sidebuf.scores(bad,F,A))
bad=Arr('<f8',(1,3)); bad.buf=memoryview(bytearray(48))[::2]; reject(lambda:sidebuf.scores(bad,F,A))
out=sidebuf.scores(Arr('<f8',(0,3)),Arr('<i8',(0,4)),Arr('|b1',(0,)))
assert out.shape==(0,4) and out.nbytes==0
assert not any(k in sys.modules for k in ('numpy','lightside','fastside','rays'))
print('PASS',len(cases),'score scenes, three storage modes, index/shape/storage checks; NumPy blocked')
