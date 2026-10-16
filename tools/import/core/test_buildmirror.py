"""Frozen mirroring geometry, UVs, logs and no-op identities with NumPy blocked."""
import ctypes,hashlib,importlib.abc,json,sys
from pathlib import Path
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from buildmirror import mirror_screen

def digest(v):return hashlib.sha256(json.dumps(v,separators=(',',':')).encode()).hexdigest()
def check(faces,sky,tiles,expected,fn=mirror_screen):
    before=digest((faces,sky));logs=[];a,b=fn(faces,sky,set(tiles),logs.append)
    actual=dict(hash=digest((a,b)),logs=logs,identity=[a is faces,b is sky],counts=[len(a),len(b)])
    assert actual==expected,(actual,expected)
    assert digest((faces,sky))==before,'source mutated'
    for src,out in ((faces,a),(sky,b)):
        identities={id(v) for v in out}
        for fc in src:
            if str(fc[0]).split('|')[0] not in tiles or len(fc[2])!=4:assert id(fc) in identities
    return actual
def main(fn=mirror_screen):
    cases=json.loads(Path(__file__).with_name('mirror_golden.json').read_text())['cases']
    for c in cases:check(c['faces'],c['sky'],c['tiles'],c['expected'],fn)
    print('PASS',len(cases),'mirror scenes: geometry/UV/logs, no-op identity, input preservation')
if __name__=='__main__':
    main();assert 'numpy' not in sys.modules
