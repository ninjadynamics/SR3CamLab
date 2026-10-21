"""Offline x86 tests for SRC AI power pacing; no live process/game access.

Compile src_ai_pace.h with the real srcport helpers, run it in Unicorn, verify
role/profile guards and exact restoration. The native-path fixture executes
Rally.exe's actual CVehicle fresh/replay branch, engine torque calculation and
force-cache save/restore. World constraints/integration, throttle and normalized
engine-curve lookup are stubbed, so this proves the adapter boundary, not race
balance or full native suspension behavior.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX
import build_srcport as B

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
EXPECTED_EXE='8eb7bdf01b8dc30ba40a43ac3d4065b9035cc59d58dd01b3c03113a1403171b5'
CAVE,OBJ,STACK,RET=0x10000000,0x20000000,0x30000000,0x3FFFF000
REC0,STRIDE=0x9DBAC8,0x1F18
CHECKS=[]


def check(label,ok):
    CHECKS.append(bool(ok))
    print(('PASS ' if ok else 'FAIL ')+label,flush=True)
    if not ok:raise AssertionError(label)


def wu(u,a,*v):u.mem_write(a,struct.pack('<%dI'%len(v),*v))
def wf(u,a,*v):u.mem_write(a,struct.pack('<%df'%len(v),*v))
def ru(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def rf(u,a):return struct.unpack('<f',u.mem_read(a,4))[0]


def build():
    src='#include "srcport.c"\n#include "src_ai_pace.h"\nSrcAiPaceSnapshot pace_snapshot;\n'
    src+='void pace_begin(void *v,u32 replay){pace_snapshot=src_ai_pace_begin(v,replay);}\n'
    src+='void pace_end(void){src_ai_pace_end(&pace_snapshot);}\n'
    src+='void pace_govern(void *v,float dt,const float *before){src_ai_pace_govern(v,dt,before); }\n'
    with tempfile.TemporaryDirectory(prefix='sr3-ai-pace-') as td:
        c=Path(td)/'test.c';o=Path(td)/'test.o';c.write_text(src)
        subprocess.run([shutil.which('clang') or r'C:\mingw64\bin\clang.exe',*B.FLAGS,
                        '-I',str(HERE),str(c),'-o',str(o)],check=True)
        return B.link(o.read_bytes())


class Fixture:
    def __init__(self,img,linked,local_role=1,ai_role=2,local_index=0):
        self.u=u=Uc(UC_ARCH_X86,UC_MODE_32)
        u.mem_map(0x400000,0x750000);u.mem_write(0x400000,img)
        blob,self.syms,relocs,_=linked
        u.mem_map(CAVE,(len(blob)+0xFFF)&~0xFFF)
        blob=bytearray(blob)
        for r in relocs:struct.pack_into('<I',blob,r,(struct.unpack_from('<I',blob,r)[0]+CAVE)&0xFFFFFFFF)
        u.mem_write(CAVE,bytes(blob));u.mem_map(OBJ,0x50000)
        u.mem_map(STACK-0x10000,0x10000);u.mem_map(RET,0x1000);u.mem_write(RET,b'\xf4')
        self.data=CAVE+self.syms['_g'];self.snap=CAVE+self.syms['_pace_snapshot']
        wu(u,self.data+8,2);wu(u,self.data+0x48,3)
        u.mem_write(self.data+0x50,bytes([0x80,0,0xFF]))
        wu(u,0x728598,5);wu(u,0x7ECE10,0x27);wu(u,0x9EB390,0)
        self.local=self.car(OBJ,local_index,local_role,True)
        self.ai=self.car(OBJ+0x20000,1,ai_role,False)

    def car(self,base,index,role,road):
        u=self.u;rec=REC0+index*STRIDE
        d=dict(veh=base,body=base+0x1000,car=base+0x2000,wrapper=base+0xB000,
               controller=base+0xB100,engine=base+0xC000,gears=base+0xC100,
               wheels=base+0xD000,clutch=base+0xF000,diff=base+0xF100,
               input=base+0xF200,ratios=base+0xF300,rec=rec)
        wu(u,rec+4,d['car']);wu(u,rec+0x300,d['controller']);wu(u,rec+0x2E0,1)
        cvt=0x6ED488 if role==1 else (0x6ED158 if role==2 else 0x6ED49C)
        wu(u,d['controller'],cvt,rec);wu(u,d['controller']+0x10,role)
        wu(u,d['car'],0x6ED0C8);wu(u,d['car']+0x7E4,rec)
        wu(u,d['car']+0x858,d['wrapper']);wf(u,d['car']+0x8700,2175.)
        wu(u,d['wrapper']+4,d['veh']);wu(u,d['veh'],0x678864)
        wu(u,d['veh']+8,d['body']);wu(u,d['veh']+0x10,d['engine'])
        wu(u,d['veh']+0x18,d['gears'],d['clutch']);wu(u,d['veh']+0x24,d['diff'],d['input'],d['wheels'],4)
        wu(u,d['engine'],0x6780A4);wu(u,d['engine']+0x30,d['veh'])
        wf(u,d['engine']+8,1.);wf(u,d['engine']+0x18,300.)
        wf(u,d['engine']+0x3C,2849.25,8800*math.pi/30)
        wu(u,d['gears'],0x677FDC,d['veh'],2,2);wu(u,d['gears']+0x18,d['ratios'])
        wf(u,d['gears']+0x20,1.);wf(u,d['gears']+0x28,.85)
        wf(u,d['ratios'],1.,0.,2.855,1.465,1.276,1.154)
        wf(u,d['body']+0xA4,1.,0.,0.,0.,1.,0.,0.,0.,1.)
        wf(u,d['body']+0x104,0.,0.,1.);wf(u,d['body']+0x170,0.,0.,30.)
        for i in range(4):
            w=base+0xD100+i*0x100;t=base+0xD500+i*0x100;wh=base+0xE000+i*0x200
            wu(u,d['wheels']+4*i,w);wu(u,w+0x10,wh,t);wu(u,t+0x1C,0 if road else 1)
        return d

    def call(self,entry,args=(),this=0):
        u=self.u;sp=STACK-0x100
        wu(u,sp,RET,*args);u.reg_write(UC_X86_REG_ESP,sp);u.reg_write(UC_X86_REG_ECX,this)
        u.emu_start(entry,RET,count=1000000)
        # C harness is cdecl; native thiscall callees pop their arguments.
        return u.reg_read(UC_X86_REG_ESP)-sp

    def begin(self,replay=0,target=None):
        target=self.ai if target is None else target
        assert self.call(CAVE+self.syms['_pace_begin'],(target['veh'],replay))==4
        return bool(ru(self.u,self.snap))

    def end(self):assert self.call(CAVE+self.syms['_pace_end'])==4
    def image(self):return bytes(self.u.mem_read(OBJ,0x50000))

    def native_fixture(self):
        u=self.u
        # Keep native45C820 branch,44F5F0->44D570->450D80,45C480/45C580.
        # Deterministic one-substep world; isolate power/caching from contact.
        stubs={0x45C6B0:bytes.fromhex('b801000000c3'),
               0x44D480:bytes.fromhex('c20800'),0x44D4B0:bytes.fromhex('c20800'),
               0x467D90:bytes.fromhex('c20800'),0x4679B0:bytes.fromhex('c21000'),
               0x45A7E0:bytes.fromhex('c20400'),
               0x45E4B0:bytes.fromhex('d9e8c3'), # throttle=1
               0x45B190:bytes.fromhex('d9e8c20400'), # curve(normalizedRPM)=1
               0x45F8E0:bytes.fromhex('d9eec3'), # clutch feedback=0
               0x44F608:bytes.fromhex('5f5e5d5bc20800')}
        for a,b in stubs.items():u.mem_write(a,b)
        wf(u,0x707438,1.)
        self.native_calls=[]
        self.native_values=[]
        def trace(uc,a,n,user):
            if a in (0x45C820,0x44F5F0,0x450D80,0x45C480,0x45C580):self.native_calls.append(a)
            if a==0x44D5C2:self.native_values.append(rf(u,self.ai['gears']+0x28))
        u.hook_add(UC_HOOK_CODE,trace)

    def native_step(self,replay):
        wu(self.u,self.ai['veh']+0x48,replay)
        self.native_calls.clear();self.native_values.clear()
        assert self.call(0x45C820,(struct.unpack('<I',struct.pack('<f',1/60))[0],),self.ai['veh'])==8



def integration_tests(make,path):
    """Full compiled candidate -> actual native engine/cache -> candidate return.

    The fixture contains both a local hardware driver and a native AI driver,
    including their common car vtable, controller roles/backrefs, wrappers and
    four tyres. The local car is airborne here: the main candidate suite covers
    player planar handling; this suite verifies its engine is never AI-paced.
    """
    meta=json.loads(path.read_text());raw=bytes.fromhex(meta['code'])
    check('Integrated candidate blob hash matches metadata',hashlib.sha256(raw).hexdigest()==meta['sha256'])
    check('Integrated candidate exact Rally.exe version matches',meta['game_sha256']==EXPECTED_EXE)
    check('Integrated candidate contains current AI helper',
          meta['source_sha256']['src_ai_pace.h']==hashlib.sha256((HERE/'src_ai_pace.h').read_bytes()).hexdigest())
    base=0x11000000

    def install(f,mode=2):
        b=bytearray(raw);f.u.mem_map(base,meta['alloc'])
        for off in meta['relocs']:
            struct.pack_into('<I',b,off,(struct.unpack_from('<I',b,off)[0]+base)&0xFFFFFFFF)
        f.u.mem_write(base,bytes(b));data=base+meta['data']
        wu(f.u,data+8,mode);wu(f.u,data+0x48,3)
        f.u.mem_write(data+0x50,bytes([0x80,0,0xFF]));f.native_fixture()
        return data

    def step(f,target,replay=0):
        wu(f.u,target['veh']+0x48,replay)
        f.native_calls.clear();f.native_values.clear();seen=[]
        def trace(u,a,n,user):
            if a==0x450D80:seen.append(('peak',rf(u,target['engine']+0x3C)))
            if a==0x44D5C2:seen.append(('gear',rf(u,target['gears']+0x28)))
        hook=f.u.hook_add(UC_HOOK_CODE,trace)
        try:
            check('Integrated wrapper returns with native calling convention',
                  f.call(base+meta['entry'],(struct.unpack('<I',struct.pack('<f',1/60))[0],),target['veh'])==8)
        finally:f.u.hook_del(hook)
        return seen

    def inputs(f,d):
        return bytes(f.u.mem_read(d['engine']+0x3C,4))+bytes(f.u.mem_read(d['gears']+0x28,4))

    for roles in ((1,2),(3,4)):
        for kmh in (100,200,210):
            f=make(local_role=roles[0],ai_role=roles[1]);install(f)
            wf(f.u,f.ai['body']+0x178,kmh/3.6)
            f.u.mem_write(f.ai['car']+0x1C84,bytes([12,60,255,44,7,21,33]))
            original=inputs(f,f.ai);vel=bytes(f.u.mem_read(f.ai['body']+0x170,24))
            controls=bytes(f.u.mem_read(f.ai['car']+0x1C84,7))
            seen=step(f,f.ai);t=max(0,min(1,(kmh-195)/10));peak=870*(1-t*t*(3-2*t))
            check(f'Full candidate corrects AI peak and preserves gearing before native force calc roles{roles} at {kmh}',
                  len(seen)==2 and seen[0][0]=='peak' and abs(seen[0][1]-peak)<.02 and seen[1][0]=='gear' and abs(seen[1][1]-.85)<1e-6)
            check('Full candidate restores exact original native inputs after fresh call',inputs(f,f.ai)==original)
            check('Full candidate leaves AI controls and body velocities untouched',
                  bytes(f.u.mem_read(f.ai['car']+0x1C84,7))==controls and bytes(f.u.mem_read(f.ai['body']+0x170,24))==vel)
            corrected=rf(f.u,f.ai['engine']+0x1C)
            for j in range(2):
                wf(f.u,f.ai['engine']+0x1C,123456.)
                seen=step(f,f.ai,1)
                check(f'Full candidate cached replay {j+1} retains corrected torque without re-scaling',
                      not seen and 0x45C580 in f.native_calls and 0x450D80 not in f.native_calls and
                      abs(rf(f.u,f.ai['engine']+0x1C)-corrected)<.001 and inputs(f,f.ai)==original)

    guards=[('disabled',0,None),('observe',1,None),
            ('SR3 local tyre profile',2,lambda f:[wu(f.u,OBJ+0xD500+i*0x100+0x1C,1) for i in range(4)]),
            ('paused',2,lambda f:wu(f.u,0x9EB390,1)),
            ('outside race',2,lambda f:wu(f.u,0x7ECE10,0x26)),
            ('remote AI',2,lambda f:(wu(f.u,f.ai['controller'],0x6ED49C),wu(f.u,f.ai['controller']+0x10,6)))]
    for name,mode,change in guards:
        f=make();install(f,mode)
        if change:change(f)
        original=inputs(f,f.ai);seen=step(f,f.ai)
        check('Full candidate preserves unmodified native engine/gearing for '+name,
              len(seen)==2 and seen[0]==('peak',2849.25) and abs(seen[1][1]-.85)<1e-6 and inputs(f,f.ai)==original)
    for role in (1,3):
        f=make(local_role=role);install(f);original=inputs(f,f.local);seen=step(f,f.local)
        check(f'Full candidate never AI-paces local human role{role}',
              len(seen)==2 and seen[0]==('peak',2849.25) and abs(seen[1][1]-.85)<1e-6 and inputs(f,f.local)==original)
    print('Integrated candidate:',path,'SHA256',meta['sha256'])


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--game',type=Path,default=ROOT/'game/Rally')
    ap.add_argument('--candidate',type=Path,help='Also exercise a hash-verified compiled full candidate wrapper')
    args=ap.parse_args()
    exe=(args.game/'Rally.exe').read_bytes()
    if hashlib.sha256(exe).hexdigest()!=EXPECTED_EXE:raise SystemExit('Rally.exe version mismatch; native tests refused')
    img=pefile.PE(data=exe).get_memory_mapped_image();linked=build()
    make=lambda **k:Fixture(img,linked,**k)
    for local,ai in [(1,2),(3,4)]:
        f=make(local_role=local,ai_role=ai);before=f.image()
        check(f'Controller roles {local}/{ai}: SRC opponent recognized',f.begin())
        check(f'Controller roles {local}/{ai}: remove file and positive catch-up boost',
              abs(rf(f.u,f.ai['engine']+0x3C)-870)<.001 and abs(rf(f.u,f.ai['gears']+0x28)-.85)<1e-6)
        f.end();check(f'Controller roles {local}/{ai}: byte-exact restoration',f.image()==before)
    f=make(local_index=2);check('Local-human proof works independently of record0',f.begin());f.end()
    for value in (0,1,3):
        f=make();wu(f.u,f.local['rec']+0x2E0,value);wu(f.u,f.ai['rec']+0x2E0,value)
        check(f'Unproven record+2E0 is not mistaken for a flavor flag ({value})',f.begin());f.end()
    f=make();before=f.image();check('Same car vtable does not classify player as AI',not f.begin(target=f.local));f.end();check('Player entirely unchanged',f.image()==before)
    for speed in (0,100,194.9,195,197.5,200,202.5,205,240):
        f=make();wf(f.u,f.ai['body']+0x178,speed/3.6);before=f.image()
        t=max(0,min(1,(speed-195)/10));expect=870*(1-t*t*(3-2*t))
        check(f'Smooth power taper at {speed:g} km/h',f.begin() and abs(rf(f.u,f.ai['engine']+0x3C)-expect)<.015)
        f.end();check(f'Taper restoration at {speed:g} km/h',f.image()==before)
    f=make();wf(f.u,f.ai['engine']+0x3C,2000);wf(f.u,f.ai['gears']+0x28,1.15)
    before=f.image();f.begin()
    check('Negative AI power/gearing pacing retained',rf(f.u,f.ai['engine']+0x3C)==800 and abs(rf(f.u,f.ai['gears']+0x28)-1.15)<1e-6)
    f.end();check('Negative pacing restored exactly',f.image()==before)
    f=make();wf(f.u,f.ai['engine']+0x3C,20000.);before=f.image();f.begin()
    check('Large positive catch-up boost is removed rather than silently skipped',rf(f.u,f.ai['engine']+0x3C)==870.)
    f.end();check('Large boost is restored byte-exact after native calculation',f.image()==before)
    guards=[
      ('disabled',lambda f:wu(f.u,f.data+8,0)),('observe',lambda f:wu(f.u,f.data+8,1)),
      ('non-race mode',lambda f:wu(f.u,0x728598,1)),('outside active race',lambda f:wu(f.u,0x7ECE10,0x26)),
      ('paused',lambda f:wu(f.u,0x9EB390,1)),
      ('local unknown tyre',lambda f:wu(f.u,OBJ+0xD500+0x1C,2)),
      ('one local non-road tyre',lambda f:wu(f.u,OBJ+0xD600+0x1C,1)),
      ('missing local wheel',lambda f:wu(f.u,f.local['wheels']+8,0)),
      ('local controller backref',lambda f:wu(f.u,f.local['controller']+4,f.ai['rec'])),
      ('AI controller backref',lambda f:wu(f.u,f.ai['controller']+4,f.local['rec'])),
      ('AI car backref',lambda f:wu(f.u,f.ai['car']+0x7E4,f.local['rec'])),
      ('unknown controller vtable',lambda f:wu(f.u,f.ai['controller'],0x6ED488)),
      ('unknown car vtable',lambda f:wu(f.u,f.ai['car'],0x6ED0CC)),
      ('simple vehicle',lambda f:wu(f.u,f.ai['veh'],0x678A10)),
      ('unknown engine vtable',lambda f:wu(f.u,f.ai['engine'],0x678094)),
      ('engine owner mismatch',lambda f:wu(f.u,f.ai['engine']+0x30,f.local['veh'])),
      ('unknown gearbox vtable',lambda f:wu(f.u,f.ai['gears'],0x6779A4)),
      ('gearbox owner mismatch',lambda f:wu(f.u,f.ai['gears']+4,f.local['veh'])),
      ('reverse gear',lambda f:wu(f.u,f.ai['gears']+8,0)),('neutral gear',lambda f:wu(f.u,f.ai['gears']+8,1)),
      ('backwards travel',lambda f:wf(f.u,f.ai['body']+0x178,-1.)),
      ('NaN peak',lambda f:wf(f.u,f.ai['engine']+0x3C,float('nan'))),
      ('implausible peak',lambda f:wf(f.u,f.ai['engine']+0x3C,100001.)),
      ('NaN gear factor',lambda f:wf(f.u,f.ai['gears']+0x28,float('nan'))),
      ('NaN velocity',lambda f:wf(f.u,f.ai['body']+0x170,float('nan'))),
      ('missing forward basis',lambda f:wf(f.u,f.ai['body']+0x104,0.,0.,0.)),
      ('unrecognized file torque',lambda f:wf(f.u,f.ai['car']+0x8700,0.)),
    ]
    for label,change in guards:
        f=make();change(f);before=f.image();active=f.begin();f.end()
        check(label+' is untouched',not active and f.image()==before)
    for role in (0,1,3,5,6,7,8):
        f=make(ai_role=role);before=f.image();active=f.begin();f.end()
        check(f'Non-local-AI controller role {role} is untouched',not active and f.image()==before)
    for local in (2,4,5,6,7):
        f=make(local_role=local);before=f.image();active=f.begin();f.end()
        check(f'Role {local} cannot prove a local SRC human',not active and f.image()==before)
    f=make();before=f.image();check('Replay never rescales engine or force cache',not f.begin(replay=1));f.end();check('Replay begins/ends byte-identically',f.image()==before)
    f=make();writes=[]
    h=f.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,access,a,n,v,data:writes.append((a,n)) if OBJ<=a<OBJ+0x50000 else None)
    f.begin();f.end();f.u.hook_del(h)
    check('Engine adapter writes only the combustion peak field',all(n==4 and a==f.ai['engine']+0x3C for a,n in writes) and len(writes)==2)
    for kmh in (100,200,210):
        stock=make();stock.native_fixture();wf(stock.u,stock.ai['body']+0x178,kmh/3.6);stock.native_step(0)
        raw=rf(stock.u,stock.ai['engine']+0x1C)
        f=make();f.native_fixture();wf(f.u,f.ai['body']+0x178,kmh/3.6)
        original=bytes(f.u.mem_read(f.ai['engine']+0x3C,4))+bytes(f.u.mem_read(f.ai['gears']+0x28,4))
        before_velocity=bytes(f.u.mem_read(f.ai['body']+0x170,24))
        f.begin();effective=rf(f.u,f.ai['engine']+0x3C);f.native_step(0);f.end()
        corrected=rf(f.u,f.ai['engine']+0x1C)
        check(f'Actual native fresh engine path uses corrected peak ({kmh} km/h)',
              all(a in f.native_calls for a in (0x45C820,0x44F5F0,0x450D80,0x45C480)) and
              abs(corrected-raw*(effective/2849.25))<.001 and len(f.native_values)==1 and abs(f.native_values[0]-.85)<1e-6)
        check(f'Native power call restores raw engine/gearing fields ({kmh} km/h)',
              original==bytes(f.u.mem_read(f.ai['engine']+0x3C,4))+bytes(f.u.mem_read(f.ai['gears']+0x28,4)))
        for j in range(3):
            wf(f.u,f.ai['engine']+0x1C,123456.)
            assert not f.begin(replay=1);f.native_step(1);f.end()
            check(f'Actual cached-force replay {j+1} retains corrected torque ({kmh} km/h)',
                  0x45C580 in f.native_calls and 0x450D80 not in f.native_calls and
                  abs(rf(f.u,f.ai['engine']+0x1C)-corrected)<.001 and not f.native_values)
        check(f'Fixture velocities remain byte-exact ({kmh} km/h)',bytes(f.u.mem_read(f.ai['body']+0x170,24))==before_velocity)
    if args.candidate:integration_tests(make,args.candidate)
    print(f'SRC AI PACE: {sum(CHECKS)} passed, {len(CHECKS)-sum(CHECKS)} failed; no game launched.')


if __name__=='__main__':main()
