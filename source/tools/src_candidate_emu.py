"""Offline integration tests for the test-only SRC bridge. No live process access."""
import json,math,sys
from pathlib import Path
workspace=Path(__file__).resolve().parents[2]
candidate=workspace/'content/handling/src-candidate.json'
if not candidate.exists(): candidate=workspace/'SR3-investigation/steering-response/src-candidate.json'
meta=json.loads(candidate.read_text())
# Reuse the existing in-memory SR3 fixture, without executing its legacy tests.
fixture=(Path(__file__).parent/'srcport_emu.py').read_text().split('npass = nfail = 0')[0]
fixture=fixture.replace("blob, ENTRY, DATA, RELOCS, CLS = B.build(A.game)","blob, ENTRY, DATA, RELOCS, CLS = bytes.fromhex(meta['code']),meta['entry'],meta['data'],meta['relocs'],meta['surfaces']")
fixture=fixture.replace('u.mem_map(CAVE, B.ALLOC)','u.mem_map(CAVE, meta["alloc"])')
exec(compile(fixture,'srcport_emu_fixture','exec'),globals())

def setup(**kwargs):
    u=machine();c=Car(u,**kwargs)
    wu(u,0x728598,5);wu(u,0x7ECE10,0x27);wu(u,0x9EB390,0)
    for i in range(4):
        wf(u,OBJ+0x9000+0x100*i+0x50,1.0)
        wf(u,OBJ+0x6000+0x100*i+0x5C,0.,1.,0.,0.)
    return u,c

def inputs(c,stick,throttle=1,brake=0):
    c.stick(stick);c.u.mem_write(DRV+0x1C86,bytes([round(throttle*255),round(brake*255)]))

def telemetry(u):
    lp=ru(u,CAVE+DATA+0xD8); ptr=ru(u,CAVE+DATA+0x1E0)
    return rf(u,ptr+((lp-1)%256)*160,40)

def simulate(hz=60,turn=False):
    u,c=setup();V=[0,0,0];W=[0,0,0];out=[]
    for i in range(hz*10):
        inputs(c,.20 if turn and 3*hz<=i<5*hz else 0)
        c.set(V,W);V,W=c.step(1/hz);c.psi+=W[1]/hz
        assert all(math.isfinite(x) for x in V+W)
        out.append((i/hz,math.hypot(V[0],V[2])*3.6,W[1],telemetry(u)))
    return out

checks=[]
def check(name,ok):
    checks.append(bool(ok));print(('PASS ' if ok else 'FAIL ')+name,flush=True)

runs={hz:simulate(hz) for hz in (30,60,120)}
for hz,r in runs.items():
    t100=next((t for t,s,w,o in r if s>=100),None)
    gears=sorted(set(int(o[28]) for _,_,_,o in r if o[28]))
    print(hz,'Hz: 0-100',t100,'end km/h',r[-1][1],'gears',gears,flush=True)
    check(str(hz)+' Hz launches, shifts and stays within original speed cap',t100 is not None and .5<t100<5 and 180<r[-1][1]<241 and gears==[1,2,3,4])
check('30/60/120 Hz straight-line final speeds agree within 1 km/h',max(r[-1][1] for r in runs.values())-min(r[-1][1] for r in runs.values())<1)
r=simulate(turn=True);pre=max(abs(w) for t,s,w,o in r if 4.8<t<5)
# The previous no-suspension gate treated slip recovery in the opposite direction
# as continued steering. Check wheel centering separately from body settling.
release=[(t,s,w,o) for t,s,w,o in r if 5<=t<6]
check('Right input turns right and steering returns below 1% within two SRC ticks',
      pre>.1 and sum(w for t,s,w,o in r if 4<t<5)>0 and max(abs(o[3]) for t,s,w,o in release if t>=5.05)<.001995)
check('Release ends the original turn within 0.3 s; opposite-slip recovery settles within 0.6 s',
      max(w for t,s,w,o in release if 5.3<t<5.5)<pre*.25 and max(abs(w) for t,s,w,o in release if 5.6<t<5.8)<pre*.25)
for desc,kwargs,modify in [
 ('Non-SRC tyre',dict(surface=RALLY),None),('AI',dict(player=False),None),
 ('Airborne',dict(contact=(0,0,0,0)),None),('Outside race',{},lambda u:wu(u,0x7ECE10,0)),
 ('Disabled',{},lambda u:setp(u,mode=0)),
 ('Impact recovery',{},lambda u:(wu(u,VEH+0x38,OBJ+0xD000),wu(u,OBJ+0xD024,1))),
 ('Reverse',{},lambda u:(wu(u,VEH+0x18,OBJ+0xD000),wu(u,OBJ+0xD008,0)))]:
    u,c=setup(**kwargs)
    if modify:modify(u)
    inputs(c,.5);c.set((1,2,30),(.1,.2,.3));before=rf(u,BODY+0x170,6);c.step(1/60)
    check(desc+' leaves native motion intact',rf(u,BODY+0x170,6)==before)
u,c=setup();inputs(c,.3);setp(u,mode=1);c.set((1,2,30),(.1,.2,.3));before=rf(u,BODY+0x170,6);c.step(1/57.5)
check('Observe mode computes telemetry without changing motion',rf(u,BODY+0x170,6)==before and ru(u,CAVE+DATA+0xD4)==1)
u,c=setup();inputs(c,.3);c.set((1,2,30),(.1,.2,.3));V,W=c.step(1/57.5)
check('Vertical/pitch/roll remain native',V[1]==2 and abs(W[0]-.1)<1e-6 and abs(W[2]-.3)<1e-6)
# Replay recorded input, velocity, surface and contact samples with a synthetic
# level road plane: older captures did not record contact planes. This is a
# stress test of integration bounds, NOT a replay of actual suspension dynamics.
import csv
trace=workspace/'work/research/steering-response/run-20261016-113518/steering.csv'
if not trace.exists(): trace=workspace/'SR3-investigation/steering-response/run-20261016-113518/steering.csv'
u,c=setup();tested=applied=0;max_yaw=0.0
for row in csv.DictReader(trace.open()):
    if row['sample_coherent']!='1':continue
    U=tuple(float(row['body_up_'+k]) for k in 'xyz');X=tuple(float(row['body_right_'+k]) for k in 'xyz');Z=tuple(float(row['body_forward_'+k]) for k in 'xyz')
    wf(u,BODY+0xA4,*(X+U+Z));wf(u,BODY+0xEC,*(U+X+Z))
    V=tuple(float(row['body_velocity_'+k]) for k in 'xyz');W=tuple(float(row['body_angular_velocity_'+k]) for k in 'xyz')
    wf(u,BODY+0x170,*V);wf(u,BODY+0x17C,*W)
    wu(u,VEH+0x38,OBJ+0xD000);wu(u,OBJ+0xD024,int(row['hit']))
    for i,name in enumerate(('fl','fr','rl','rr')):
        wu(u,OBJ+0x6000+0x100*i+0x58,int(row[name+'_contact']))
        wf(u,OBJ+0x6000+0x100*i+0x8C,float(row[name+'_susp_8c']))
        wu(u,OBJ+0x9000+0x100*i+0x1C,int(row[name+'_surface_index']))
        wf(u,OBJ+0x9000+0x100*i+0x50,float(row[name+'_tyre_50']))
    inputs(c,float(row['raw_stick']),float(row['throttle']),float(row['brake']))
    before=ru(u,CAVE+DATA+0xD4);vv,ww=c.step(1/60);tested+=1
    assert all(math.isfinite(v) for v in vv+ww)
    if ru(u,CAVE+DATA+0xD4)>before:
        applied+=1
        t=telemetry(u);yaw=abs(ww[1]);max_yaw=max(max_yaw,yaw)
        # SRC clamps BEFORE slip-change damping: |w| <= .1*.93 + .07*pi.
        # A zero-tick adapter step instead preserves the incoming native yaw.
        limit=(.1*.93+.07*math.pi)*57.5 if t[30] else abs(W[1])
        assert yaw<=limit+1e-4, (tested,yaw,limit,t)
        assert abs(vv[1]-V[1])<.0001
check('Recorded states on synthetic flat planes: finite, native world-vertical motion preserved',tested>6000 and applied>4000)
print('Synthetic-plane stress samples:',tested,'candidate-applied:',applied,'maximum yaw rad/s:',max_yaw)

# Native prediction/replay protocol: the first call's body is restored by
# 0x44A7F0, and two collision passes ask for that same step again. SRC state
# must advance once, even if replay inputs change during collision resolution.
a,ca=setup();b,cb=setup();V=(0.,0.,25.);W=(0.,0.,0.);same=True
for frame in range(180):
    steer=.5 if frame<90 else 0.
    for car in (ca,cb):inputs(car,steer)
    for u,car in ((a,ca),(b,cb)):
        wu(u,VEH+0x48,0);car.set(V,W)
    va,wa=ca.step(.016); vb,wb=cb.step(.016)
    same &= max(abs(x-y) for x,y in zip(va+wa,vb+wb))<1e-6
    for repeat in range(2):
        wu(b,VEH+0x48,1);cb.set(V,W);vr,wr=cb.step(.016)
        same &= max(abs(x-y) for x,y in zip(va+wa,vr+wr))<1e-6
        same &= telemetry(b)[32]==1
    V,W=va,wa;ca.psi+=wa[1]*.016;cb.psi=ca.psi
check('Prediction plus two identical replays equals one step over 180 frames',same)
# An altered collision retry must not poison the next frame's drivetrain state.
u,c=setup();inputs(c,.3);c.set((0,0,30),(0,0,0));wu(u,VEH+0x48,1)
before=rf(u,BODY+0x170,6);c.step(.016)
check('Installing midway through a replay waits for a fresh prediction',rf(u,BODY+0x170,6)==before and ru(u,CAVE+DATA+0xD4)==0)
a,ca=setup();b,cb=setup()
for car in (ca,cb):inputs(car,.4);car.set((0,0,30),(0,0,0));car.step(.016)
wu(b,VEH+0x48,1);cb.set((3,2,20),(.1,.3,.2));cb.step(.016)
wu(b,VEH+0x48,0)
for car in (ca,cb):car.set((0,0,30),(0,0,0))
va,wa=ca.step(.016);vb,wb=cb.step(.016)
check('Collision retry does not advance committed SRC state',max(abs(x-y) for x,y in zip(va+wa,vb+wb))<1e-6)

# A native front/rear load imbalance must not alter the SRC sprung-body model.
a,ca=setup();b,cb=setup();V=(0.,0.,40.);W=(0.,0.,0.);same=True;peak=0
for i in range(4):wf(b,OBJ+0x9000+0x100*i+0x50,.65 if i<2 else 1.35)
for frame in range(180):
    for car in (ca,cb):inputs(car,.95 if frame>=60 else 0);car.set(V,W)
    va,wa=ca.step(1/60);vb,wb=cb.step(1/60)
    same &= max(abs(x-y) for x,y in zip(va+wa,vb+wb))<1e-6
    peak=max(peak,wa[1]);V,W=va,wa;ca.psi+=wa[1]/60;cb.psi=ca.psi
check('Native front/rear support-load bias cannot cap SRC steering',same and peak>0.5)
print('Full-turn peak yaw rad/s:',peak)
# At rest, four SRC springs must support exactly the original mass/weight.
u,c=setup();inputs(c,0,throttle=0)
for frame in range(300):c.set((0,0,0),(0,0,0));c.step(1/57.5)
t=telemetry(u)
check('SRC springs settle at 1/12 m depth, with zero vertical drift',max(abs(x-1/12) for x in t[22:26])<1e-5 and abs(t[11])<1e-6)
# Invalid contact geometry must leave the native solver in charge.
for label,plane in [('zero',(0,0,0,0)),('wall',(1,0,0,0)),('NaN',(0,float('nan'),0,0))]:
    u,c=setup();wf(u,OBJ+0x6000+0x5C,*plane);inputs(c,.5);c.set((1,2,30),(.1,.2,.3));before=rf(u,BODY+0x170,6);c.step(1/57.5)
    check('Invalid '+label+' contact plane falls back to native motion',rf(u,BODY+0x170,6)==before and ru(u,CAVE+DATA+0xdc)==5)
# Ground slope/elevation changes, dropped contacts, throttle and braking stress.
u,c=setup();V=(0.,0.,25.);W=(0.,0.,0.);px=pz=0.;errors=set();finite=True
for frame in range(900):
    nx=.05*math.sin(frame/120);nz=.04*math.sin(frame/180);ny=math.sqrt(1-nx*nx-nz*nz)
    ground=.05*math.sin(frame/60)
    for i in range(4):
        wf(u,OBJ+0x6000+0x100*i+0x5C,nx,ny,nz,-nx*px-nz*pz-ny*ground)
        wu(u,OBJ+0x6000+0x100*i+0x58,int(not(i==0 and 300<=frame<330)))
    wf(u,BODY+0x88,px,.32+ground,pz)
    inputs(c,.4*math.sin(frame/90),throttle=0 if 500<=frame<530 else 1,brake=1 if 500<=frame<530 else 0)
    c.set(V,W);V,W=c.step(1/60);c.psi+=W[1]/60;px+=V[0]/60;pz+=V[2]/60
    finite &= all(math.isfinite(v) for v in V+W);errors.add(ru(u,CAVE+DATA+0xdc))
check('Changing slopes, a missing wheel contact and braking stay finite without state reset',finite and errors=={0})

print(sum(checks),'passed;',len(checks)-sum(checks),'failed')
if not all(checks):raise SystemExit(1)
