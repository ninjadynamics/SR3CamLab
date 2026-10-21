"""Offline compiled AI pace regression: real SetVelocity, synthetic native drive.

The live trace disproved engine-peak reduction as a sufficient pace control.
Inject excessive output after the native engine/cache fixture, independently of
combustion power. Verify the production wrapper bounds it on fresh and replay
passes, preserves collision losses and never changes the local human. This is
not a full native-world simulation or evidence of owner race acceptance.
"""
import argparse
import hashlib
import math
from pathlib import Path
import json
import struct
import pefile
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
import src_ai_pace_emu as E


def bits(f):return struct.unpack('<I',struct.pack('<f',f))[0]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game',type=Path,default=E.ROOT/'game/Rally')
    ap.add_argument('--candidate',type=Path,required=True)
    a=ap.parse_args()
    exe=(a.game/'Rally.exe').read_bytes()
    assert hashlib.sha256(exe).hexdigest()==E.EXPECTED_EXE
    img=pefile.PE(data=exe).get_memory_mapped_image();linked=E.build()
    count=0
    def check(name,ok):
        nonlocal count
        assert ok,name
        count+=1

    def make(**kwargs):
        f=E.Fixture(img,linked,**kwargs)
        for d in (f.ai,f.local):
            E.wf(f.u,d['body']+8,1300)
            for i in range(4):
                su=d['veh']+0x11000+i*0x100
                E.wu(f.u,E.ru(f.u,d['wheels']+i*4)+0xC,su)
                E.wu(f.u,su+0x58,1);E.wf(f.u,su+0x5C,0,1,0,0)
        return f

    def govern(f,before,native,dt=1/60,replay=0,target=None):
        d=target or f.ai;u=f.u;vbuf=E.OBJ+0x4F000
        E.wf(u,vbuf,*before);E.wf(u,d['body']+0x170,*native)
        E.wu(u,d['veh']+0x48,replay);E.wu(u,d['veh']+0x4C,1)
        E.wf(u,d['veh']+0x50,dt)
        f.call(E.CAVE+f.syms['_pace_govern'],(d['veh'],bits(dt),vbuf))
        return tuple(E.rf(u,d['body']+0x170+4*i) for i in range(3))

    for roles in ((1,2),(3,4)):
        f=make(local_role=roles[0],ai_role=roles[1])
        for speed in (0,10,40,80,100,140,180,195,200,210,246):
            for hz in (30,60,120):
                before=(2.,3.,speed/3.6);native=(2.,3.,speed/3.6+40/hz)
                fresh=govern(f,before,native,1/hz)
                for replay in (1,1):
                    check('Fresh/replay output is identical',govern(f,before,native,1/hz,replay)==fresh)
                check('Sideways and vertical velocity preserved',fresh[:2]==native[:2])
                check('Excess propulsion actually removed',fresh[2]<native[2]-.01)
                check('Native momentum remains consistent',
                      max(abs(E.rf(f.u,f.ai['body']+0x158+4*i)-1300*fresh[i]) for i in range(3))<.01)
                if speed>=200:check('Flat overspeed cannot accelerate',fresh[2]<=before[2]+1e-5)
        for before,native in (((2,3,30),(2,3,20)),((2,3,30),(-5,7,0)),((2,3,30),(2,3,-1))):
            check('Braking/contact/reverse losses retained',govern(f,before,native)==native)
        angular=bytes.fromhex('0000803f0000004000004040')
        f.u.mem_write(f.ai['body']+0x17C,angular)
        govern(f,(0,0,50),(0,0,60))
        check('All angular velocity remains native',bytes(f.u.mem_read(f.ai['body']+0x17C,12))==angular)

    guards=[('disabled',lambda f:E.wu(f.u,f.data+8,0)),
            ('observe',lambda f:E.wu(f.u,f.data+8,1)),
            ('outside race',lambda f:E.wu(f.u,0x7ECE10,0)),
            ('paused',lambda f:E.wu(f.u,0x9EB390,1)),
            ('native SR3',lambda f:E.wu(f.u,E.OBJ+0xD500+0x1C,1)),
            ('remote',lambda f:E.wu(f.u,f.ai['controller']+0x10,6)),
            ('broken owner',lambda f:E.wu(f.u,f.ai['controller']+4,0)),
            ('wrong vehicle',lambda f:E.wu(f.u,f.ai['veh'],0x678A10)),
            ('wrong gears owner',lambda f:E.wu(f.u,f.ai['gears']+4,0)),
            ('reverse',lambda f:E.wu(f.u,f.ai['gears']+8,0)),
            ('neutral',lambda f:E.wu(f.u,f.ai['gears']+8,1)),
            ('invalid mass',lambda f:E.wf(f.u,f.ai['body']+8,float('nan'))),
            ('invalid basis',lambda f:E.wf(f.u,f.ai['body']+0x104,0,0,0)),
            ('airborne',lambda f:[E.wu(f.u,f.ai['veh']+0x11000+i*0x100+0x58,0) for i in range(4)]),
            ('one wheel only',lambda f:[E.wu(f.u,f.ai['veh']+0x11000+i*0x100+0x58,0) for i in range(1,4)]),
            ('wall contact plane',lambda f:E.wf(f.u,f.ai['veh']+0x11000+0x5C,1,0,0,0))]
    for name,change in guards:
        f=make();change(f)
        check(name+' motion untouched',govern(f,(2,3,50),(2,3,60))==(2,3,60))
    for role in (1,3):
        f=make(local_role=role)
        check('Local player never pace-limited',govern(f,(2,3,50),(2,3,60),target=f.local)==(2,3,60))
    f=make()
    for dt in (0,-.01,.101,float('nan')):
        check('Invalid dt ignored',govern(f,(2,3,50),(2,3,60),dt)==(2,3,60))
    check('Backwards travel untouched',govern(f,(2,3,-1),(2,3,1))==(2,3,1))
    writes=[]
    h=f.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,t,p,n,v,x:writes.append((p,n)) if E.OBJ<=p<E.OBJ+0x4F000 else None)
    E.wf(f.u,E.OBJ+0x4F000,2,3,50);E.wf(f.u,f.ai['body']+0x170,2,3,60)
    writes.clear()
    f.call(E.CAVE+f.syms['_pace_govern'],(f.ai['veh'],bits(1/60),E.OBJ+0x4F000))
    f.u.hook_del(h)
    allowed={f.ai['body']+o for o in (0x158,0x15C,0x160,0x170,0x174,0x178)}
    check('Only native linear velocity/momentum fields changed',len(writes)==6 and all(n==4 and p in allowed for p,n in writes))

    for sign in (-1,1):
        f=make()
        for i in range(4):E.wf(f.u,f.ai['veh']+0x11000+i*0x100+0x5C,0,1/math.sqrt(1.04),sign*.2/math.sqrt(1.04),0)
        out=govern(f,(0,0,200/3.6),(0,0,60))
        check('Ground slope influences allowance with correct sign',(out[2]-200/3.6)*sign>0)

    # Integrated production wrapper, actual native engine and cache, with an
    # independent excessive drive contribution injected at native-step return.
    meta=json.loads(a.candidate.read_text());raw=bytes.fromhex(meta['code'])
    assert hashlib.sha256(raw).hexdigest()==meta['sha256']
    base=0x11000000
    def combined():
        f=make(local_role=3,ai_role=4);b=bytearray(raw)
        f.u.mem_map(base,meta['alloc'])
        for off in meta['relocs']:struct.pack_into('<I',b,off,(struct.unpack_from('<I',b,off)[0]+base)&0xFFFFFFFF)
        f.u.mem_write(base,bytes(b));f.native_fixture()
        data=base+meta['data'];E.wu(f.u,data+8,2);E.wu(f.u,data+0x48,3)
        f.u.mem_write(data+0x50,bytes([0x80,0,0xFF]))
        return f
    def step(f,before,dt,replay=0):
        E.wf(f.u,f.ai['body']+0x170,0,0,before)
        E.wu(f.u,f.ai['veh']+0x48,replay)
        def force(u,pc,n,data):
            if pc==0x45CA24:E.wf(u,f.ai['body']+0x170,0,0,before+40*dt)
        hook=f.u.hook_add(UC_HOOK_CODE,force)
        try:f.call(base+meta['entry'],(bits(dt),),f.ai['veh'])
        finally:f.u.hook_del(hook)
        return E.rf(f.u,f.ai['body']+0x178)

    outcomes=[]
    for hz in (30,60,120):
        f=combined();v=0;t100=None
        for frame in range(hz*12):
            v1=step(f,v,1/hz)
            if frame%11==0:
                for retry in range(2):check('Integrated replay reproduces bounded output',abs(step(f,v,1/hz,1)-v1)<1e-5)
            v=v1
            if t100 is None and v*3.6>=100:t100=(frame+1)/hz
        check('Integrated overpowered AI settles at 200 km/h',199.8<v*3.6<=200.001)
        check('AI launch below accepted player capability',1.6<t100<2.4)
        diag=base+meta['ai_diagnostics']+444+24
        check('Output limiter diagnostics prove real application',E.ru(f.u,diag+4)>hz*10)
        outcomes.append({'hz':hz,'zero_to_100_s':t100,'final_kmh':v*3.6})
    check('Frame-rate-independent envelope',max(x['final_kmh'] for x in outcomes)-min(x['final_kmh'] for x in outcomes)<.1)
    print(json.dumps({'checks_passed':count,'synthetic_overpowered_ai':outcomes,
                      'game_launched':False,'live_balance_acceptance':'pending'},indent=2))


if __name__=='__main__':main()
