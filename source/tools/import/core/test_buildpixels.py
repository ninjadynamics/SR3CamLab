"""Frozen texture-source precedence, ROM colors, resizing and caches, NumPy blocked."""
import ctypes,importlib.abc,json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0]=='numpy':raise RuntimeError('NumPy blocked')
sys.meta_path.insert(0,Block())
from npyio import Arr
import buildpixels as B,m2colour as MC
data=json.loads((HERE/'build_pixels_golden.json').read_text())
def pack(out):return None if out is None else dict(shape=list(out[0].shape),rgb=bytes(out[0].buf).hex(),hole=None if out[1] is None else bytes(out[1].buf).hex())
with tempfile.TemporaryDirectory(prefix='sr3-pixels-check-') as tmp:
    base=Path(tmp)/'textures';hd=Path(str(base)+'_hd');base.mkdir();hd.mkdir()
    for name,c in data['cases'].items():
        for folder,key in ((base,'base'),(hd,'hd')):
            path=folder/(c['name']+'.png')
            if path.exists():path.unlink()
            if c[key]:path.write_bytes(bytes.fromhex(c[key]))
        tiles=B.Tiles(base);out=tiles.tile_pixels(c['name']+c['query_suffix']);assert pack(out)==c['expected'],name
        assert pack(tiles.hd_used.get(c['name']))==c['hd_cached'],name
        if c['hd_cached'] is not None:assert tiles.tile_pixels(c['name']) is out
        elif out is not None:assert tiles.tile_pixels(c['name']) is not out
    # Negative caching remains until explicitly cleared; all files can close/unlink.
    tiles=B.Tiles(base);assert tiles.hd_tile('new') is None
    payload=bytes.fromhex(data['cases']['hd_only']['hd']);p=hd/'new.png';p.write_bytes(payload)
    assert tiles.hd_tile('new') is None;tiles.hd_used.clear();value=tiles.hd_tile('new');assert value is not None
    p.unlink();assert tiles.hd_tile('new') is value
    pair=(Arr('|u1',(1,1,3),bytearray([3,4,5])),None);calls=[]
    tiles=B.Tiles(base,baked={'new':pair},rom=lambda n:calls.append(n) or pair)
    assert tiles.tile_pixels('new|suffix') is pair and not calls and not tiles.hd_used
    assert tiles.tile_pixels('rom') is pair and calls==['rom']
    (base/'rom.png').write_bytes(payload);assert tiles.tile_pixels('rom') is pair
    tiles.rom=lambda n:None;assert pack(tiles.tile_pixels('rom'))!=pack(pair)
    assert tiles.tile_pixels('not_present') is None
rom=data['rom'];MC._XLB['t']=bytes.fromhex(rom['xlat'])
pages={(1,0):bytes((i*7+i//1024)%16 for i in range(1024*1024)),(1,1):bytes((i*11+3)%16 for i in range(1024*1024))}
before=json.dumps(rom['materials']);provider=B.RomTiles(pages,rom['materials'],bytes.fromhex(rom['palette']),bytes.fromhex(rom['luma']))
for name,expected in rom['expected'].items():assert pack(provider(name))==expected,name
assert json.dumps(rom['materials'])==before and provider('absent') is None
assert 'numpy' not in sys.modules
print('PASS 35 PNG/HD and six ROM cases; source precedence/cache identity/reset/negative cache/file closure; NumPy blocked')
