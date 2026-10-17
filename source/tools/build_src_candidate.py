"""Build isolated test-only SRC bridge; never embeds into the normal launcher."""
import argparse,hashlib,json,struct,subprocess,tempfile,shutil
from pathlib import Path
import build_srcport as B

def build(game,rom):
    clang=shutil.which('clang') or r'C:\mingw64\bin\clang.exe'
    with tempfile.TemporaryDirectory(prefix='src-candidate-') as td:
        obj=Path(td)/'candidate.o'
        subprocess.run([clang]+B.FLAGS+[str(Path(B.HERE)/'src_candidate.c'),'-o',str(obj)],check=True)
        blob,names,relocs,image=B.link(obj.read_bytes())
    b=bytearray(blob);data=names['_g'];curve=names['_candidate_engine_curve'];raw=rom.read_bytes()
    b[curve:curve+416]=raw[0x5d8f20-0x59f000:0x5d8f20-0x59f000+416]
    assert len(b)<0x20000
    struct.pack_into('<I',b,data+4,2)
    cls=B.surface_classes(str(game));struct.pack_into('<I',b,data+B.OFF_COUNT,len(cls))
    for i,(_,kind,_) in enumerate(cls):b[data+B.OFF_CLS+i]=kind
    return dict(code=b.hex(),sha256=hashlib.sha256(b).hexdigest(),entry=names['_candidate_step'],data=data,
                curve=curve,relocs=relocs,size=len(b),alloc=0x20000,version=2,
                game_sha256=hashlib.sha256((game/'Rally.exe').read_bytes()).hexdigest(),
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(B.HERE)/n for n in ('src_candidate.c','srcport.c','src_kernel.h','src_suspension.h')]},
                caveat='Experimental planar SRC drivetrain/tyres. SRC sprung-body state from native contact planes; native vertical/collision body retained. Not full verbatim physics.',
                surfaces=cls)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--game',type=Path,required=True)
    ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    m=build(a.game,a.rom);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(m,indent=2)+'\n')
    print('Candidate',m['size'],'bytes; entry',hex(m['entry']),'data',hex(m['data']))
