"""Execute actual cabinet-info handler code offline; never launches Rally.exe.

Usage: python test_boot_presentation_flow.py --exe path/to/Rally.exe
Requires pefile and unicorn. Native shared update/network/D3D/text callees are
stubbed; their ordered calls and render visibility are checked. The real handler,
prologue, epilogue, IP-info local copies and calibration branches execute in x86.
The installed payload is read directly from boot_presentation.h.
"""
import argparse
import hashlib
import itertools
import json
import re
import struct
from pathlib import Path
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP

BASE, ENTRY, BODY = 0x400000, 0x649E50, 0x649E64
SCRATCH, STATE, STOP = 0x20000000, 0x20008000, 0x200F0000
DEVICE, VTABLE, CLEAR, NETWORK = 0x20009000, 0x2000A000, 0x2000B000, 0x2000C000

def u32(x):
    return struct.pack('<I', x)

def payload_from_header(name):
    text = Path(__file__).with_name('boot_presentation.h').read_text(encoding='utf-8')
    match = re.search(r'unsigned char '+name+r'\[\d+\]\s*=\s*\{(.*?)\};',text,re.S)
    assert match, name
    return bytes(int(x,16) for x in re.findall(r'0x([0-9A-Fa-f]{2})\b',match.group(1)))

def simulate(image, frames, machine_type, calibration, network, alignment, flags, entry=ENTRY, calibration_status=0x15, calibration_enabled=1):
    m = Uc(UC_ARCH_X86, UC_MODE_32)
    m.mem_map(BASE, (len(image) + 4095) & ~4095)
    m.mem_write(BASE, image)
    m.mem_map(SCRATCH, 0x100000)
    sp = SCRATCH + 0x11000 + alignment
    saved = {UC_X86_REG_EDI:0x12345678, UC_X86_REG_ESI:0x23456789,
             UC_X86_REG_EBX:0x3456789A, UC_X86_REG_EBP:0x456789AB}
    for reg,value in saved.items(): m.reg_write(reg,value)
    m.mem_write(sp, struct.pack('<II', STOP, STATE))
    m.mem_write(STATE + 8, u32(frames))
    m.mem_write(0x9EB888, u32(machine_type))
    m.mem_write(0x9EB8B4, u32(calibration))
    m.mem_write(0x8123BC, u32(flags))
    m.mem_write(0x9EB598, u32(777))
    m.mem_write(0x9EB8CC,u32(calibration_enabled))
    m.mem_write(0x9C4398,u32(999));m.mem_write(0x9C439C,u32(999))
    m.mem_write(0xAE314C,u32(7))
    m.mem_write(0x7ED10C, u32(DEVICE))
    m.mem_write(DEVICE, u32(VTABLE))
    m.mem_write(VTABLE+0xAC, u32(CLEAR))
    m.reg_write(UC_X86_REG_ESP, sp)
    calls, global_writes, constructors, destructors = [], [], [], []
    def ret(mu, extra=0, eax=0):
        stack=mu.reg_read(UC_X86_REG_ESP)
        target=struct.unpack('<I',mu.mem_read(stack,4))[0]
        mu.reg_write(UC_X86_REG_EAX,eax)
        mu.reg_write(UC_X86_REG_ESP,stack+4+extra)
        mu.reg_write(UC_X86_REG_EIP,target)
    def hook(mu,address,size,_):
        if address==0x646CC0:
            calls.append('shared_update'); ret(mu)
        elif address==0x404070:
            calls.append('network_getter'); ret(mu,eax=NETWORK if network else 0)
        elif address==0x62DED0:
            calls.append('cabinet_calibration_poll');ret(mu,eax=calibration_status)
        elif address==0x546910:
            calls.append('display_getter');ret(mu,eax=SCRATCH+0xE000)
        elif address==0x5822D0:
            calls.append('display_lookup');ret(mu)
        elif address==0x591540:
            calls.append('begin_scene'); ret(mu)
        elif address==0x590C50:
            calls.append('render_target'); ret(mu,eax=mu.reg_read(UC_X86_REG_EAX))
        elif address==CLEAR:
            color=struct.unpack('<I',mu.mem_read(mu.reg_read(UC_X86_REG_ESP)+20,4))[0]
            assert color==0xFF011AB2, hex(color)
            calls.append('blue_clear'); ret(mu,extra=28)
        elif address==0x58B8F0:
            calls.append('format_display_string'); ret(mu,eax=SCRATCH+0xD000)
        elif address==0x639E40:
            calls.append('draw_text')
            count=struct.unpack('<I',mu.mem_read(0x9EB598,4))[0]
            mu.mem_write(0x9EB598,u32(count+1)); ret(mu)
        elif address==0x404120:
            calls.append('flush_text'); ret(mu,extra=4)
        elif address==0x591C00:
            calls.append('end_scene_present'); ret(mu)
        elif address==0x47A450:
            # Empty IP-info vector frees: real copy/destructor control flow runs.
            arg=struct.unpack('<I',mu.mem_read(mu.reg_read(UC_X86_REG_ESP)+4,4))[0]
            assert arg==0, 'Unexpected allocation in empty-IP fixture'
            ret(mu)
        elif address==0x47A4E0:
            constructors.append(mu.reg_read(UC_X86_REG_ECX))
        elif address==0x47A4F0:
            destructors.append(mu.reg_read(UC_X86_REG_ECX))
    def on_write(mu,access,address,size,value,_):
        if not SCRATCH<=address<SCRATCH+0x100000:
            global_writes.append((address,size,value))
    m.hook_add(UC_HOOK_CODE, hook)
    m.hook_add(UC_HOOK_MEM_WRITE, on_write)
    m.emu_start(entry, STOP, count=10000)
    assert m.reg_read(UC_X86_REG_EIP)==STOP,'Native handler did not return'
    assert all(m.reg_read(reg)==value for reg,value in saved.items()),'Callee-saved registers changed'
    assert m.reg_read(UC_X86_REG_ESP)==sp+4,'Stack not restored'
    assert calls.count('shared_update')==1
    if entry==ENTRY:assert calls.count('network_getter')==1
    return dict(state=m.reg_read(UC_X86_REG_EAX),calls=calls,global_writes=global_writes,
                constructors=constructors,destructors=destructors,
                render_flags=struct.unpack('<I',m.mem_read(0x8123BC,4))[0],
                calibration_result=struct.unpack('<II',m.mem_read(0x9C4398,8)),
                calibration_display_frames=struct.unpack('<I',m.mem_read(0xAE314C,4))[0])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--exe',type=Path,required=True)
    ap.add_argument('--report',type=Path)
    args=ap.parse_args()
    file=args.exe.read_bytes(); p=pefile.PE(data=file)
    assert p.OPTIONAL_HEADER.ImageBase==BASE
    original=p.get_memory_mapped_image()
    guard=payload_from_header('boot_info_original'); fast=payload_from_header('boot_info_fast')
    assert len(guard)==76 and len(fast)==56
    assert original[ENTRY-BASE:ENTRY-BASE+len(guard)]==guard,'Unsupported handler bytes'
    table=struct.unpack('<14I',original[0x70CAA8-BASE:0x70CAA8-BASE+56])
    assert table[4]==0x64D900 and table[9]==ENTRY
    assert original[0x64D956-BASE:0x64D95B-BASE]==bytes.fromhex('e80593f7ff')
    assert original[0x64D9E8-BASE:0x64D9ED-BASE]==bytes.fromhex('b809000000')
    assert original[0x64A3F5-BASE:0x64A410-BASE]==bytes.fromhex('833d88b89e000068f0a447006a036a047535833db4b89e00007416')
    patched=bytearray(original); patched[BODY-BASE:BODY-BASE+len(fast)]=fast
    changed=[i+BASE for i,(a,b) in enumerate(zip(original,patched)) if a!=b]
    assert changed and all(BODY<=address<BODY+56 for address in changed)
    unchanged=[(0x64D5E0,0x64D900),(0x64D900,0x64D9F2),(0x5C6C60,0x5C7000),
               (0x621600,0x621900),(0x70CAA8,0x70CAE0),(0x646CC0,0x646D3A),
               (0x404070,0x404110),(0x48A4A0,0x48A55D),(ENTRY,BODY)]
    for lo,hi in unchanged:
        assert patched[lo-BASE:hi-BASE]==original[lo-BASE:hi-BASE]
    cases=[]
    for machine,calibration,network,alignment,flags,frames in itertools.product((0,1),(0,1),(0,1),(0,4),(0,0x180),(0,120,121)):
        before=simulate(original,frames,machine,calibration,network,alignment,flags)
        after=simulate(bytes(patched),frames,machine,calibration,network,alignment,flags)
        target=10 if machine==0 and calibration else 13
        assert before['state']==(9 if frames<=120 else target)
        assert after['state']==target
        assert before['calls'].count('blue_clear')==1 and before['calls'].count('end_scene_present')==1
        assert len(before['constructors'])==3 and before['destructors']==before['constructors'][::-1]
        assert after['calls']==['shared_update','network_getter'],after['calls']
        assert after['global_writes']==[(0x9EB598,4,0)],after['global_writes']
        assert not after['constructors'] and not after['destructors']
        assert after['render_flags']==flags
        cases.append(dict(machine_type=machine,calibration=calibration,network_object=network,
                          stack_alignment=alignment,render_flags=flags,frames=frames,
                          original_state=before['state'],fast_state=after['state']))
    # Upgrade from a live hold-only patch is also safe: that tail is unreachable.
    legacy=bytearray(patched); legacy[0x64A3F3-BASE:0x64A3F5-BASE]=b'\x90\x90'
    upgrade=simulate(bytes(legacy),0,1,0,1,4,0x180)
    assert upgrade['state']==13 and upgrade['calls']==['shared_update','network_getter']
    calpatched=bytearray(patched)
    for address,expected,replacement,skip in [
        (0x63EE60,'boot_cal_draw_original','boot_cal_draw_fast',0),
        (0x64AB40,'boot_cal_done_original','boot_cal_done_fast',5)]:
        guard2=payload_from_header(expected);fast2=payload_from_header(replacement)
        assert original[address-BASE:address-BASE+len(guard2)]==guard2
        calpatched[address-BASE+skip:address-BASE+skip+len(fast2)]=fast2
    calibration_cases=0
    for enabled,status,frames,alignment in itertools.product((0,1),(0,19,20,21,22),(0,1,120,121),(0,4)):
        before=simulate(original,frames,0,1,1,alignment,0,entry=0x64AB60,calibration_status=status,calibration_enabled=enabled)
        after=simulate(bytes(calpatched),frames,0,1,1,alignment,0,entry=0x64AB60,calibration_status=status,calibration_enabled=enabled)
        assert before['state']==after['state']
        assert before['calibration_result']==after['calibration_result']
        assert before['calibration_display_frames']==after['calibration_display_frames']==8
        assert before['calls'].count('blue_clear')==before['calls'].count('end_scene_present')==1
        assert after['calls']==['shared_update']+(['cabinet_calibration_poll'] if enabled else [])
        assert after['render_flags']==0
        calibration_cases+=1
    for frames,alignment,flags in itertools.product((0,1,120,121),(0,4),(0,0x180)):
        before=simulate(original,frames,0,1,1,alignment,flags,entry=0x64AB40)
        after=simulate(bytes(calpatched),frames,0,1,1,alignment,flags,entry=0x64AB40)
        assert before['state']==(11 if frames<=120 else 13) and after['state']==13
        assert after['calls']==['shared_update'] and after['render_flags']==flags
        assert after['calibration_result']==before['calibration_result']==(999,999)
        assert before['calls'].count('blue_clear')==before['calls'].count('end_scene_present')==1
        calibration_cases+=1
    # Every genuine calibration branch and the actual poll call remain untouched.
    assert calpatched[0x64AB60-BASE:0x64ABD6-BASE]==original[0x64AB60-BASE:0x64ABD6-BASE]
    print(f'PASS: {calibration_cases*2} actual-x86 calibration executions; all poll/results preserved, zero blue rendering or post-completion dwell.')
    report=dict(executable=str(args.exe.resolve()),sha256=hashlib.sha256(file).hexdigest(),
                offline_only=True,game_launched=False,calibration_executions=calibration_cases*2,calibration_poll_and_result_preserved=True,patch_va=hex(BODY),patch_bytes=len(fast),
                changed_bytes=len(changed),executions=len(cases)*2+1,
                no_blue_clear_or_text_or_present=True,shared_update_and_network_getter_preserved=True,
                stack_and_callee_saved_registers_preserved=True,display_temporaries_not_constructed=True,
                initialization_ranges_unchanged=[[hex(lo),hex(hi)] for lo,hi in unchanged],cases=cases)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS: %d actual-x86 handler executions; zero blue clear/text/present, native update/network calls and calibration routing preserved.'%(len(cases)*2+1))

if __name__=='__main__':
    main()
