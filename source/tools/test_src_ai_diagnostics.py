"""Exercise the actual compiled AI counters and the recorder decoder, offline."""
from pathlib import Path
import json
import struct
import sys
import pefile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/tools'),str(ROOT/'source/tools/handling')]
import src_ai_pace_emu as E
from candidate_host import decode_ai_diagnostics

image=pefile.PE(str(ROOT/'game/Rally/Rally.exe')).get_memory_mapped_image()
linked=E.build()
f=E.Fixture(image,linked)
ptr=E.CAVE+f.syms['_src_ai_pace_diagnostics']
read=lambda:decode_ai_diagnostics(bytes(f.u.mem_read(ptr,588)))
assert read()['calls']==0
assert f.begin()
f.end()
d=read()
assert d['calls']==d['reasons']['applied']==1
assert d['cars'][1]['role']==2 and d['cars'][1]['links_valid']==1
assert d['cars'][1]['applied']==1 and d['cars'][1]['limited_peak']==870
assert d['cars'][1]['base']==2175 and abs(d['cars'][1]['kmh']-108)<.001
assert not f.begin(replay=1)
assert read()['reasons']['replay']==1
E.wu(f.u,f.ai['engine'],0x678094)
assert not f.begin()
d=read()
assert d['reasons']['engine_gears']==1 and d['cars'][1]['last_reason']==7
E.wu(f.u,f.ai['engine'],0x6780A4)
E.wf(f.u,f.ai['engine']+0x3C,float('nan'))
assert not f.begin()
d=read()
assert d['reasons']['power_range']==1 and d['cars'][1]['peak'] is None
json.dumps(d,allow_nan=False)
legacy=bytearray(f.u.mem_read(ptr,444));struct.pack_into('<I',legacy,4,1)
assert decode_ai_diagnostics(bytes(legacy))['cars'][1]['applied']==1
for raw in (b'',bytes(444),bytes(588),struct.pack('<2I',0x50414953,2)+bytes(436)):
    try:decode_ai_diagnostics(raw)
    except ValueError:pass
    else:raise AssertionError('Invalid record accepted')
print('PASS: compiled counters, per-car values, rejected guards, replay, strict JSON and invalid-block validation; no game launched.')
