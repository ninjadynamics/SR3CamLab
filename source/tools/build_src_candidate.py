"""Build the process-only SRC bridge loaded by the normal PLAY helper."""
import argparse,hashlib,json,struct,subprocess,tempfile,shutil
from pathlib import Path
import build_srcport as B

def build(game,rom=None,curve_candidate=None):
    clang=shutil.which('clang') or r'C:\mingw64\bin\clang.exe'
    with tempfile.TemporaryDirectory(prefix='src-candidate-') as td:
        obj=Path(td)/'candidate.o'
        subprocess.run([clang]+B.FLAGS+[str(Path(B.HERE)/'src_candidate.c'),'-o',str(obj)],check=True)
        blob,names,relocs,image=B.link(obj.read_bytes())
    b=bytearray(blob);data=names['_g'];curve=names['_candidate_engine_curve']
    if curve_candidate is not None:
        original=json.loads(curve_candidate.read_text());raw=bytes.fromhex(original['code'])
        if hashlib.sha256(raw).hexdigest()!=original['sha256']:raise ValueError('Reference candidate hash mismatch')
        engine_curve=raw[original['curve']:original['curve']+416]
    else:
        raw=rom.read_bytes();engine_curve=raw[0x5d8f20-0x59f000:0x5d8f20-0x59f000+416]
    if len(engine_curve)!=416:raise ValueError('Incomplete original engine curve')
    b[curve:curve+416]=engine_curve
    assert len(b)<0x20000
    struct.pack_into('<I',b,data+4,2)
    cls=B.surface_classes(str(game));struct.pack_into('<I',b,data+B.OFF_COUNT,len(cls))
    for i,(_,kind,_) in enumerate(cls):b[data+B.OFF_CLS+i]=kind
    return dict(code=b.hex(),sha256=hashlib.sha256(b).hexdigest(),entry=names['_candidate_step'],data=data,
                curve=curve,relocs=relocs,size=len(b),alloc=0x20000,version=2,
                ai_diagnostics=names['_src_ai_pace_diagnostics'],ai_diagnostics_size=588,
                game_sha256=hashlib.sha256((game/'Rally.exe').read_bytes()).hexdigest(),
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(B.HERE)/n for n in ('src_candidate.c','srcport.c','src_kernel.h','src_suspension.h','src_ai_pace.h')]},
                caveat='Experimental planar SRC drivetrain/tyres. SRC sprung-body state from native contact planes; native vertical/collision body retained. Not full verbatim physics.',
                surfaces=cls)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--game',type=Path,required=True)
    curve_source=ap.add_mutually_exclusive_group(required=True)
    curve_source.add_argument('--rom',type=Path)
    curve_source.add_argument('--curve-candidate',type=Path,help='Reuse the original engine curve from a hash-verified prior build')
    ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    m=build(a.game,a.rom,a.curve_candidate);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(m,indent=2)+'\n')
    print('Candidate',m['size'],'bytes; entry',hex(m['entry']),'data',hex(m['data']))
