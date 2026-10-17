"""Replay captured SRC internals through compiled production C equations.

python tools/src_kernel_replay.py desert/steer.csv mountain/steer.csv --report result.json
Requires clang and Unicorn. Runs only an emulated CPU; never opens a game process.
Inputs are archived original-game telemetry, NOT srcmodel.py predictions.
Force and yaw residuals are reported in full, including boundary/air/wall cases.
Passing regression gates does not certify the SR3 state adapter or full handling.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP
import build_srcport as B

WRAPPER = r"""
#include "srcport.c"
/*ENGINE_TABLE*/
/* Input fields are named in Python's FIELDS below. */
void replay(const float *a, float *o) {
    unsigned int age = (unsigned int)a[41];
    o[15] = (float)src_auto_gear((int)a[40], &age, a[34], a[39], a[30]);
    float feedback = src_engine_feedback(a[34],a[35],a[36],a[37],a[38]);
    o[14] = src_engine_rpm(a[34],a[3],a[27],a[28],feedback);
    o[13] = src_load_transfer(a[24],a[25],a[32],a[33],0.4f,1.0f);
    o[12] = src_drive_force(a[3], a[26], a[27], a[30], (int)a[31], a[28], a[2], engine_table);
    o[0] = src_steering(a[0], a[1], 1.0f);
    float spin = a[29] ? src_wheelspin(a[3], a[26], a[27], a[28]) : a[9];
    o[11] = spin;
    float fm = a[2] * 1000.0f * (1.0f + 0.3f * a[3]);
    float ff = fm * a[4] * (1.0f + a[6]);
    float fr = fm * a[5] * (1.0f - a[6]);
    if (a[24] + a[25] == 0.0f) ff = fr = 0.0f;
    float drive = a[24]*a[25] == 0.0f ? 0.0f : a[7];
    for (int legacy = 0; legacy < 2; legacy++) {
        float fxf = a[8] * drive, fxr = drive - fxf;
        float wsp = legacy ? 0.0f : spin;
        float fyf = src_tyre(a[10], a[11], ff, 2.0f*PI/3.0f, &fxf, 1.2f, wsp);
        float fyr = src_tyre(a[12], a[13], fr, PI, &fxr, 0.4f, wsp);
        if (fxf < 0.0f) { fxr += fxf; fxf = 0.0f; }
        int j = 1 + legacy * 4;
        o[j] = fyf; o[j+1] = fxf; o[j+2] = fyr; o[j+3] = fxr;
    }
    /* Separately replay torque from recorded forces to isolate each stage. */
    float xf = a[19]*fcos(a[14]) - a[20]*fsin(a[14]);
    float fyr = a[21] - xf;
    float fxr = a[22] - (a[19]*fsin(a[14]) + a[20]*fcos(a[14]));
    o[9] = 1.25f*(fyr-xf) + 0.66f*a[15]*fxr - 0.635f*a[16]*a[20];
    o[10] = src_yaw(a[17], a[18], a[23], 0.07f, 0.07f, 1.0f);
}
"""
FIELDS = ('counts','previous_sm','gsc','spd','gripf','gripr','lt','drv','share',
          'wsp','sf','vf','sr','vr','st74','r13','r14','previous_w','Ty_acc',
          'Fyf','Fxf','Fytot','Fxtot','dbeta','front_compression','rear_compression','rpm','effective_ratio','forward_speed','reconstruct_spin','throttle','brake_byte','previous_lt','lag_up','previous_rpm','previous_ratio','previous_throttle','previous_drive','previous_axle_force','previous_spin','previous_gear','gear_age')
BASE, ARG, STACK, RET = 0x10000000, 0x20000000, 0x30000000, 0x40000000

class Kernel:
    def __init__(self,rom):
        raw=rom.read_bytes()
        curve=struct.unpack_from("<104f",raw,0x5d8f20-0x59f000)
        table="static const float engine_table[104] = {"+",".join(float(x).hex()+"f" for x in curve)+"};"
        clang = shutil.which('clang') or r'C:\mingw64\bin\clang.exe'
        with tempfile.TemporaryDirectory(prefix='src-kernel-') as tmp:
            source, obj = Path(tmp)/'replay.c', Path(tmp)/'replay.o'
            source.write_text(WRAPPER.replace("/*ENGINE_TABLE*/",table))
            subprocess.run([clang]+B.FLAGS+['-I',B.HERE,str(source),'-o',str(obj)], check=True)
            blob, symbols, relocs, _ = B.link(obj.read_bytes())
        blob = bytearray(blob)
        for site in relocs:
            struct.pack_into('<I',blob,site,struct.unpack_from('<I',blob,site)[0]+BASE)
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        self.u.mem_map(BASE,(len(blob)+4095)//4096*4096)
        self.u.mem_write(BASE,bytes(blob))
        self.u.mem_map(ARG,0x1000)
        self.u.mem_map(STACK-0x10000,0x10000)
        self.u.mem_map(RET,0x1000)
        self.entry = BASE+symbols['_replay']
    def __call__(self, fields):
        u=self.u; esp=STACK-0x100
        u.mem_write(ARG,struct.pack('<42f',*(fields[k] for k in FIELDS)))
        u.mem_write(esp,struct.pack('<III',RET,ARG,ARG+0x100))
        u.reg_write(UC_X86_REG_ESP,esp)
        u.emu_start(self.entry,RET,count=100000)
        if u.reg_read(UC_X86_REG_EIP)!=RET or u.reg_read(UC_X86_REG_ESP)!=esp+4:
            raise RuntimeError('compiled kernel failed to return cleanly')
        result=struct.unpack('<16f',u.mem_read(ARG+0x100,64))
        if not all(map(math.isfinite,result)): raise ValueError('nonfinite kernel output')
        return result

def summary(items):
    items=sorted(items,key=lambda x:x['error'])
    if not items: raise ValueError('empty capture metric')
    return dict(n=len(items),median=items[len(items)//2]['error'],
                p95=items[int(len(items)*.95)]['error'],max=items[-1]['error'],
                above_1e_5=sum(x['error']>1e-5 for x in items),worst=items[-5:])

def replay(kernel,path,reconstruct=False):
    with path.open(newline='') as f: rows=list(csv.DictReader(f))
    metrics={n:[] for n in ('auto_gear','engine_rpm','load_transfer','drive','steering','front_fy','front_fx','rear_fy','rear_fx',
                            'tyre_torque','yaw','zero_spin_front_fy','zero_spin_rear_fy')}
    used=0; skipped=0; spin_frames=0; age=0; prevprev=None
    for prev,row in zip(rows,rows[1:]):
        prior_age=age
        age=0 if row['gear']!=prev['gear'] else min(age+1,31)
        pprev=prevprev;prevprev=prev
        # A fresh, single player-physics capture; no fabricated missing values.
        if float(row['r'])<1 or not row['Ty'] or int(row['ntap'],16)>>24!=1:
            skipped+=1; continue
        r={k:float(row[k]) for k in FIELDS if k in row}
        # Standard-car ratios from maincpu.bin RAM 0x5D9254 / 0x5D9264.
        gears=(1.0,3.5,2.0,1.649999976158142,1.399999976158142)
        gear=int(row['gear'])
        if not 0<=gear<len(gears): raise ValueError('unsupported SRC gear')
        heading=float(prev['yaw'])+r['st74']
        forward=-float(prev['vx'])*math.sin(heading)+float(prev['vz'])*math.cos(heading)
        r.update(previous_lt=float(prev['lt']),lag_up=.05 if int(row['sidx']) in (2,3,10,11,12,13,14,15) else .10,throttle=max(0,min(143,int(row["acc"])-48))/143,brake_byte=int(row["brk"]),effective_ratio=3.0*gears[gear] if gear else 0.0,
                 forward_speed=forward,reconstruct_spin=float(reconstruct),
                 counts=float(row['steer'])-128, previous_sm=float(prev['sm']),
                 previous_w=float(prev['w48']),
                 front_compression=float(row['c0'])+float(row['c1']),
                 rear_compression=float(row['c2'])+float(row['c3']),share=.23 if int(row['sidx']) in (6,7) else .25)
        pd=float(prev['st74'])
        r.update(previous_rpm=float(prev['rpm']),previous_ratio=3.0*gears[int(prev['gear'])],
                 previous_throttle=max(0,min(143,int(prev['acc'])-48))/143,
                 previous_drive=float(prev['drv']),
                 previous_axle_force=float(prev['Fxtot'])-float(prev['Fyf'])*math.sin(pd)+float(prev['Fxf'])*(1-math.cos(pd)))
        prpm=float(prev['rpm']); pspeed=float(prev['spd']); pratio=r['previous_ratio']
        # The archives' frame-end wsp can be reset after the engine saves its
        # own previous wheelspin. Reconstruct that stage from previous RPM/speed.
        psign=1.0
        if pprev:
            ph=float(pprev['yaw'])+float(prev['st74'])
            psign=-float(pprev['vx'])*math.sin(ph)+float(pprev['vz'])*math.cos(ph)
        pspin=min(1,abs((prpm-pspeed*3600/1.8849555921538759*pratio)/prpm)) if prpm>1000 and psign>0 else 0
        r.update(previous_spin=pspin,previous_gear=int(prev['gear']),gear_age=prior_age)
        o=kernel(r); used+=1; spin_frames+=r['wsp']>0
        d=r['st74']; xf=r['Fyf']*math.cos(d)-r['Fxf']*math.sin(d)
        rear_y=r['Fytot']-xf
        rear_x=r['Fxtot']-(r['Fyf']*math.sin(d)+r['Fxf']*math.cos(d))
        pairs={'load_transfer':(o[13],r['lt']),'drive':(o[12],r['drv']),'steering':(o[0],float(row['sm'])), 'front_fy':(o[1],r['Fyf']),
               'front_fx':(o[2],r['Fxf']), 'rear_fy':(o[3],rear_y),'rear_fx':(o[4],rear_x),
               'tyre_torque':(o[9],float(row['Ty'])),
               'zero_spin_front_fy':(o[5],r['Fyf']), 'zero_spin_rear_fy':(o[7],rear_y)}
        if gear and int(prev['gear']):
            pairs['engine_rpm']=(o[14],r['rpm'])
            pairs['auto_gear']=(o[15],gear)
        # The yaw check omits the documented low-speed road-alignment branch.
        if r['spd']>.0463: pairs['yaw']=(o[10],float(row['w48']))
        for name,(pred,actual) in pairs.items():
            metrics[name].append(dict(error=abs(pred-actual),race_s=float(row['r']),
                                     predicted=pred,actual=actual,wsp=r['wsp'],used_wsp=o[11]))
    stats={k:summary(v) for k,v in metrics.items()}
    gates=dict(auto_gear=stats["auto_gear"]["max"]==0,engine_rpm_max=stats["engine_rpm"]["max"]<0.01,load_transfer_max=stats["load_transfer"]["max"]<1e-5,drive_max=stats["drive"]["max"]<5e-4,drive_p95=stats["drive"]["p95"]<3e-5,steering=stats['steering']['max']<2e-6,
               tyre_torque=stats['tyre_torque']['max']<1e-5,
               tyre_force_p95=all(stats[k]['p95']<1e-5 for k in ('front_fy','front_fx','rear_fy','rear_fx')),
               yaw_p95=stats['yaw']['p95']<1e-7)
    if reconstruct:
        gates["all_tyre_force_frames"]=all(stats[k]["max"]<1e-5 for k in ("front_fy","front_fx","rear_fy","rear_fx"))
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                used=used,skipped=skipped,nonzero_wheelspin_frames=spin_frames,metrics=stats,gates=gates)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom',type=Path,default=Path(r'F:\Jogos\SEGA Rally 3\SR3 track format\work\tmp\m2\maincpu.bin'))
    ap.add_argument('--reconstruct-wheelspin',action='store_true',help='Standard cars only; effective clutch/shift state is absent from these archives.')
    ap.add_argument('captures',type=Path,nargs='+'); ap.add_argument('--report',type=Path)
    args=ap.parse_args(); kernel=Kernel(args.rom)
    results=[replay(kernel,p,args.reconstruct_wheelspin) for p in args.captures]
    report=dict(engine_table_rom_sha256=hashlib.sha256(args.rom.read_bytes()).hexdigest(),reconstructed_wheelspin=args.reconstruct_wheelspin,scope='Compiled SRC force/steering/yaw stages only; SR3 adapter NOT validated.',
                caveat='All residuals retained. Percentile gates do not resolve force-boundary or later collision/air writes.',
                captures=results)
    for r in results:
        print(r['path'], 'frames',r['used'],'nonzero wheelspin',r['nonzero_wheelspin_frames'])
        for name,s in r['metrics'].items():
            print('  %-20s n=%4d p95=%.3g max=%.3g residuals>1e-5=%d' % (name,s['n'],s['p95'],s['max'],s['above_1e_5']))
        print('  regression gates:',r['gates'])
    if args.report: args.report.write_text(json.dumps(report,indent=2)+'\n')
    if not all(all(r['gates'].values()) for r in results): raise SystemExit(1)

if __name__=='__main__': main()
