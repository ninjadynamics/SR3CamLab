"""Read-only steering trace. No game memory writes, input injection or screenshots."""
import argparse, csv, ctypes, ctypes.wintypes as W, json, math, pathlib, struct, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sr3_recorder as R
R.k32.CloseHandle.argtypes = [W.HANDLE]
R.k32.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]

def floats(p, address, count):
    data = p.read(address, count * 4)
    return struct.unpack('<%df' % count, data) if data else None

def dot(a, b): return sum(x*y for x,y in zip(a,b))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    ap.add_argument('--seconds', type=float, default=120)
    a = ap.parse_args()
    target = pathlib.Path(a.out); target.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 600
    pid = None
    while time.monotonic() < deadline:
        pid = R.pid_of()
        if pid: break
        time.sleep(1)
    if not pid: raise SystemExit('No Rally process appeared within ten minutes.')
    p = R.Proc(pid); rows = 0; race_seconds = 0; last_time = time.monotonic(); parts = None; next_locate = 0; last_sample = None
    columns = ['host_s','elapsed_ms','input_mode','raw_stick','driver_steer','lock_factor','vehicle_steer','speed_kmh','forward_ms','side_ms','yaw_rad_s','slip_deg','wheel_fl_rad','wheel_fr_rad','wheel_rl_rad','wheel_rr_rad','force_model','hit','hit_timer','vehicle_step']
    extra_columns = ['throttle','brake','handbrake','gear','engine_rpm','sample_coherent']
    extra_columns += ['body_'+name+'_'+axis for name in ('up','right','forward','velocity','angular_velocity','position') for axis in 'xyz']
    wheel_fields = ['contact','susp_28','susp_2c','susp_8c','susp_90','susp_a8','spin_rad_s','radius','surface_index','tyre_4c','tyre_50','plane_x','plane_y','plane_z','plane_d']
    extra_columns += [name+'_'+field for name in ('fl','fr','rl','rr') for field in wheel_fields]
    extra_columns += ['time_limit_ms','checkpoint_next','checkpoint_count','checkpoint_last_lap','lap_index','game_mode']
    columns += extra_columns
    # Low-frequency checkpoint context supplements the already-read time limit.
    checkpoint_context = (None,) * 5; next_checkpoint_read = 0
    start = time.monotonic()
    try:
        with target.open('w',newline='') as out:
            writer = csv.writer(out); writer.writerow(columns)
            while time.monotonic() < deadline and race_seconds < a.seconds:
                now = time.monotonic(); delta = now-last_time; last_time = now
                code = W.DWORD()
                if not R.k32.GetExitCodeProcess(p.h,ctypes.byref(code)) or code.value != 259: break
                if now >= next_locate:
                    parts = R.locate(p); next_locate = now+0.5; out.flush()
                if not parts or not parts['veh'] or not R.racing(p): time.sleep(0.02); continue
                over, elapsed, limit = R.race_over(p,parts['rec'])
                if over: time.sleep(0.02); continue
                race_seconds += delta
                veh = parts['veh']; body = p.u32(veh+8)
                axes = floats(p,body+0xec,9); velocity = floats(p,body+0x170,6)
                control = p.read(parts['ctl']+8,24); raw = p.read(parts['drv']+0x1c84,2)
                if not axes or not velocity or not control or not raw: time.sleep(0.01); continue
                marker = (elapsed,bytes(control),bytes(raw),velocity)
                if marker == last_sample: time.sleep(0.005); continue
                last_sample = marker
                mode, brake, hb, gas, steering, lock = struct.unpack('<I5f',control)
                up, right, forward = axes[:3],axes[3:6],axes[6:9]
                v,w = velocity[:3],velocity[3:]; vf,vs = dot(v,forward),dot(v,right)
                flist=p.u32(veh+0x2c); wheel_angles=[]; wheel_data=[]
                if p.u32(veh+0x30) != 4: time.sleep(0.01); continue
                for i in range(4):
                    assembly=p.u32(flist+i*4)
                    susp,wheel,tyre=(p.u32(assembly+o) for o in (0xc,0x10,0x14))
                    sb=p.read(susp,0xc4) if susp else None
                    wb=p.read(wheel,0x194) if wheel else None
                    tb=p.read(tyre,0x54) if tyre else None
                    val=lambda block,offset,kind='f': struct.unpack_from('<'+kind,block,offset)[0] if block else None
                    wheel_angles.append(val(wb,0x190))
                    wheel_data.extend([val(sb,0x58,'I'),*[val(sb,o) for o in (0x28,0x2c,0x8c,0x90,0xa8)],val(wb,0x18),val(wb,0x44),val(tb,0x1c,'I'),val(tb,0x4c),val(tb,0x50),*[val(sb,o) for o in (0x5c,0x60,0x64,0x68)]])
                fm=p.u32(veh+0x38); vc=p.u32(veh+0x28)
                eng=parts['eng']; gears=parts['gears']
                rpm=p.f32(eng+0x18)*60/(2*math.pi) if eng else None
                gear=p.u32(gears+8)-1 if gears else None
                if now >= next_checkpoint_read:
                    checkpoint_context = tuple(p.u32(address) for address in (0x9EB388,0xB2A89C,0xB2A8A0,0x9DD610,0x728598))
                    next_checkpoint_read = now + 0.25
                coherent=int(floats(p,body+0x170,6)==velocity and p.u32(parts['rec']+0x1da0)==elapsed)
                extras=[gas,brake,hb,gear,rpm,coherent,*axes,*velocity,*(floats(p,body+0x88,3) or (None,None,None)),*wheel_data,limit,*checkpoint_context]
                writer.writerow([round(now-start,6),elapsed,mode,(raw[1]-raw[0])/255,steering,lock,p.f32(vc+8),math.sqrt(dot(v,v))*3.6,vf,vs,dot(w,up),math.degrees(math.atan2(vs,vf)),*wheel_angles,hex(p.u32(fm)),p.u32(fm+0x24),p.f32(fm+0x28),hex(p.u32(0x678878)),*extras])
                rows+=1; time.sleep(0.005)
    finally:
        R.k32.CloseHandle(p.h)
        target.with_suffix('.json').write_text(json.dumps({'pid':pid,'rows':rows,'duration_s':time.monotonic()-start,'read_only':True,'schema_version':4,'snapshot_note':'sample_coherent checks velocity and elapsed time before/after; other fields are not atomically captured'},indent=2))
    print('%d samples saved to %s' % (rows,target))

if __name__ == '__main__': main()
