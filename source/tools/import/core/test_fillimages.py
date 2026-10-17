"""Exact legacy decoding with NumPy blocked, including ownership/lifetime."""
import ctypes,importlib.abc,json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from fillimages import load_rgba,load_alpha
cases=json.loads((HERE/'fill_images_golden.json').read_text())
with tempfile.TemporaryDirectory(prefix='sr3-fill-images-') as tmp:
    for name,c in cases.items():
        path=Path(tmp)/(name+'.png');path.write_bytes(bytes.fromhex(c['png']))
        rgba=load_rgba(path);alpha=load_alpha(path)
        assert rgba.shape==tuple(c['shape']) and alpha.shape==tuple(c['shape'][:2])
        assert rgba.dtype=='|u1' and alpha.dtype=='|b1'
        assert bytes(rgba.buf).hex()==c['rgba'] and bytes(alpha.buf).hex()==c['alpha'],name
        second=load_rgba(path);rgba.view()[0]^=255;assert bytes(second.buf).hex()==c['rgba']
        path.unlink();assert bytes(alpha.buf).hex()==c['alpha']
    try:load_rgba(Path(tmp)/'missing.png')
    except FileNotFoundError:pass
    else:raise AssertionError('missing input accepted')
assert 'numpy' not in sys.modules
print('PASS',len(cases),'image modes; exact RGBA/threshold alpha and owned buffers; NumPy blocked')
