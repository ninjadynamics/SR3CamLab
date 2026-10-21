"""User-run test helper: installs only the staged candidate into its matching Rally process.
Does not launch a game, inject input or capture the desktop. Closing Rally ends the test.
The normal launcher uses this helper for SRC handling. All addresses come from the validated build.
"""
import argparse,csv,ctypes,ctypes.wintypes as W,hashlib,json,math,pathlib,struct,sys,time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sr3_recorder as R
K=R.k32;NT=ctypes.WinDLL('ntdll')
K.CloseHandle.argtypes=[W.HANDLE]
K.GetExitCodeProcess.argtypes=[W.HANDLE,ctypes.POINTER(W.DWORD)]
K.VirtualAllocEx.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_size_t,W.DWORD,W.DWORD];K.VirtualAllocEx.restype=ctypes.c_void_p
K.VirtualProtectEx.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_size_t,W.DWORD,ctypes.POINTER(W.DWORD)]
K.WriteProcessMemory.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
K.FlushInstructionCache.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_size_t]
K.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
NT.NtSuspendProcess.argtypes=[W.HANDLE];NT.NtSuspendProcess.restype=ctypes.c_long
NT.NtResumeProcess.argtypes=[W.HANDLE];NT.NtResumeProcess.restype=ctypes.c_long
SITE,STOCK=0x678878,0x45C820

AI_REASONS=('applied','replay','disabled','race_state','vehicle_class','local_src_proof',
            'ai_ownership','engine_gears','power_range','velocity_range','orientation_reverse','reserved')
AI_FIELDS=('role','controller_vt','car_vt','links_valid','vehicle_vt','engine_vt','gears_vt',
           'last_reason','applied','peak','base','limited_peak','gear_factor','kmh','native_engine_torque','native_drive_torque')

def decode_ai_diagnostics(raw):
    if len(raw) not in (444,588):raise ValueError('Invalid AI diagnostics length')
    values=struct.unpack('<%dI'%(len(raw)//4),raw)
    if values[0]!=0x50414953 or (values[1],len(raw)) not in ((1,444),(2,588)):
        raise ValueError('Invalid AI diagnostics header')
    rows=[]
    for index in range(6):
        fields=values[15+16*index:31+16*index]
        row=dict(zip(AI_FIELDS,fields));row['record']=index
        for key in ('peak','base','limited_peak','gear_factor','kmh','native_engine_torque','native_drive_torque'):
            row[key]=struct.unpack('<f',struct.pack('<I',row[key]))[0]
            if not math.isfinite(row[key]):row[key]=None
        if values[1]==2:
            e=values[111+6*index:117+6*index]
            row['pace_steps'],row['pace_limited']=e[:2]
            for key,bits in zip(('pace_before_kmh','pace_native_kmh','pace_after_kmh','pace_allowance_mps2'),e[2:]):
                value=struct.unpack('<f',struct.pack('<I',bits))[0]
                row[key]=value if math.isfinite(value) else None
        rows.append(row)
    return dict(calls=values[2],reasons=dict(zip(AI_REASONS,values[3:15])),cars=rows)

class Process(R.Proc):
    def __init__(self,pid):
        self.h=K.OpenProcess(0x10|0x20|0x8|0x400|0x800,False,pid)
        if not self.h:raise ctypes.WinError(ctypes.get_last_error())
    def alive(self):
        c=W.DWORD();return bool(K.GetExitCodeProcess(self.h,ctypes.byref(c)) and c.value==259)
    def write(self,address,data):
        b=ctypes.create_string_buffer(data);got=ctypes.c_size_t()
        if not K.WriteProcessMemory(self.h,address,b,len(data),ctypes.byref(got)) or got.value!=len(data):raise ctypes.WinError(ctypes.get_last_error())
    def hook(self,expected,value):
        if NT.NtSuspendProcess(self.h)!=0:raise RuntimeError('Cannot suspend for atomic hook update')
        try:
            if self.u32(SITE)!=expected:raise RuntimeError('Vehicle hook changed; left untouched')
            old=W.DWORD()
            if not K.VirtualProtectEx(self.h,SITE,4,0x40,ctypes.byref(old)):raise ctypes.WinError(ctypes.get_last_error())
            try:self.write(SITE,struct.pack('<I',value))
            finally:
                restore=W.DWORD()
                if not K.VirtualProtectEx(self.h,SITE,4,old.value,ctypes.byref(restore)):raise ctypes.WinError(ctypes.get_last_error())
            K.FlushInstructionCache(self.h,SITE,4)
        finally:
            if NT.NtResumeProcess(self.h)!=0:raise RuntimeError('Failed to resume game after hook update')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=pathlib.Path,required=True)
    ap.add_argument('--game',type=pathlib.Path,required=True);ap.add_argument('--out',type=pathlib.Path,required=True);a=ap.parse_args()
    m=json.loads(a.candidate.read_text());raw=bytes.fromhex(m['code'])
    if hashlib.sha256(raw).hexdigest()!=m['sha256']:raise RuntimeError('Candidate hash mismatch')
    expected_exe=(a.game/'Rally.exe').resolve()
    if hashlib.sha256(expected_exe.read_bytes()).hexdigest()!=m['game_sha256']:raise RuntimeError('Different Rally executable')
    if m['size']!=len(raw) or not 0<m['size']<=m['alloc']<=0x20000:raise RuntimeError('Invalid image bounds')
    if not (0<=m['entry']<len(raw) and 0<=m['data']<len(raw)-0x1e4):raise RuntimeError('Invalid entry/data')
    if struct.unpack_from('<II',raw,m['data'])!=(0x50435253,2):raise RuntimeError('Wrong candidate version')
    ai_offset=m.get('ai_diagnostics');ai_size=m.get('ai_diagnostics_size',0)
    if ai_offset is not None:
        if ai_size not in (444,588) or not 0<=ai_offset<=len(raw)-ai_size:raise RuntimeError('Invalid AI diagnostics bounds')
        decode_ai_diagnostics(raw[ai_offset:ai_offset+ai_size])
    for site in m['relocs']:
        if not 0<=site<=len(raw)-4 or struct.unpack_from('<I',raw,site)[0]>=m['alloc']:raise RuntimeError('Invalid relocation')
    a.out.parent.mkdir(parents=True,exist_ok=True);p=None;cave=None;entry=None;deadline=time.monotonic()+600
    info=dict(candidate_sha256=m['sha256'],installed=False,rows=0,dropped=0,caveat=m['caveat'])
    try:
        while time.monotonic()<deadline:
            pid=R.pid_of()
            if pid:p=Process(pid);break
            time.sleep(.5)
        if not p:raise RuntimeError('No Rally appeared within ten minutes')
        size=W.DWORD(32768);buf=ctypes.create_unicode_buffer(size.value)
        if not K.QueryFullProcessImageNameW(p.h,0,buf,ctypes.byref(size)) or pathlib.Path(buf.value).resolve()!=expected_exe:
            raise RuntimeError('Rally process is not the standalone test target')
        info['pid']=pid
        while p.alive() and time.monotonic()<deadline:
            if R.racing(p) and R.locate(p):break
            time.sleep(.1)
        if not p.alive():raise RuntimeError('Rally closed before race')
        if not R.racing(p):raise RuntimeError('No live race within ten minutes')
        if p.u32(SITE)!=STOCK:raise RuntimeError('Unknown vehicle hook; not installing')
        cave=K.VirtualAllocEx(p.h,None,m['alloc'],0x3000,0x40)
        if not cave or cave+m['alloc']>=0x80000000:raise RuntimeError('Cannot allocate 32-bit candidate')
        blob=bytearray(raw)
        for site in m['relocs']:struct.pack_into('<I',blob,site,struct.unpack_from('<I',blob,site)[0]+cave)
        p.write(cave,bytes(blob))
        if p.read(cave,len(blob))!=bytes(blob):raise RuntimeError('Candidate memory verification failed')
        K.FlushInstructionCache(p.h,cave,len(blob));entry=cave+m['entry'];data=cave+m['data']
        p.hook(STOCK,entry);info.update(installed=True,cave=hex(cave),entry=hex(entry),data=hex(data))
        print('SRC candidate installed for this process only.',flush=True)
        a.out.with_suffix('.json').write_text(json.dumps(info,indent=2)+'\n')
        last=0;start=time.monotonic();next_ai=0
        with a.out.open('w',newline='') as f, a.out.with_suffix('.ai.jsonl').open('w') as ai_log:
            writer=csv.writer(f);writer.writerow(['host_s','sequence','dt','counts','steering','vx_frame','vz_frame','yaw_frame','beta','front_fy','rear_fy','front_fx','rear_fx','torque','load_transfer','surface','contacts','c0','c1','c2','c3','drive','src_rpm','src_gear','wheelspin','ticks','feedback','solver_replay','body_x','body_z','pending','src_pitch','src_roll','src_height','src_vertical_frame','suspension_yaw_torque','contact_reconciliations','collision_slip_rebases'])
            while p.alive():
                if p.u32(SITE)!=entry:raise RuntimeError('Candidate hook replaced during run')
                end=p.u32(data+0xD8);log=p.u32(data+0x1E0)
                if not cave<=log<=cave+m['alloc']-256*160:raise RuntimeError('Invalid log pointer')
                begin=max(last,end-256);info['dropped']+=max(0,begin-last)
                for index in range(begin,end):
                    b=p.read(log+(index%256)*160,160)
                    if not b:continue
                    t=struct.unpack('<40f',b)
                    if t[0]!=index:info['dropped']+=1;continue
                    writer.writerow([round(time.monotonic()-start,6),*t[:8],*t[13:19],*t[20:36],*t[8:13],t[36],t[37]])
                    info['rows']+=1
                last=end;f.flush();info['last_error']=p.u32(data+0xDC)
                if ai_offset is not None and time.monotonic()>=next_ai:
                    record=decode_ai_diagnostics(p.read(cave+ai_offset,ai_size))
                    record['host_s']=round(time.monotonic()-start,3)
                    ai_log.write(json.dumps(record,allow_nan=False)+'\n');ai_log.flush()
                    info['ai_pace']=record;next_ai=time.monotonic()+1
                time.sleep(.1)
    finally:
        if p:
            if entry and p.alive() and p.u32(SITE)==entry:
                # Leave code allocated: a suspended thread could already be executing it.
                p.write(cave+m['data']+8,struct.pack('<I',0))
                p.hook(entry,STOCK)
            K.CloseHandle(p.h)
        a.out.with_suffix('.json').write_text(json.dumps(info,indent=2)+'\n')
    print('Candidate recording ended:',info,flush=True)

if __name__=='__main__':main()
