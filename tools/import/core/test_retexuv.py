"""Frozen numeric/structure hashes against the original NumPy UV functions."""
import ctypes,hashlib,importlib.abc,json,struct,sys
from pathlib import Path
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
import retexuv

def packed(x):
    if x is None:return b'N'
    if isinstance(x,(list,tuple)):
        return b'L'+struct.pack('<I',len(x))+b''.join(packed(v) for v in x)
    assert type(x) is float
    return b'D'+struct.pack('<d',x)

def main(module=retexuv):
    cases=json.loads(Path(__file__).with_name('retex_uv_golden.json').read_text())['cases']
    for i,c in enumerate(cases):
        before=packed(c['q']);v=getattr(module,c['fn'])(c['q'],**c['args'])
        actual=hashlib.sha256(packed(v)).hexdigest()
        assert actual==c['expected'],(i,c['fn'],c['q'],c['args'],actual,c['expected'])
        assert packed(c['q'])==before
    for fn in ('plane_uv','box_uv','subdivide'):
        for x in (0.,-1.,float('nan'),float('inf')):
            try:getattr(module,fn)([(0.,0.,0.)]*4,x)
            except ValueError:pass
            else:raise AssertionError((fn,'accepted invalid scale'))
    for fn in ('plane_uv','box_uv','tree_uv'):
        try:getattr(module,fn)([(0.,0.,float('nan'))]*4)
        except ValueError:pass
        else:raise AssertionError((fn,'accepted invalid coordinates'))
    assert 'numpy' not in sys.modules
    print('PASS',len(cases),'UV cases; input preserved, finite guards, NumPy blocked')

if __name__=='__main__':main()
