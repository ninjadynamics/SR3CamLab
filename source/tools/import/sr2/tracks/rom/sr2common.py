import struct, os, csv
import numpy as np
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
B = _TMP + r"/"
W = B + "sr2_gameplay/work/"
OUT = B + "sr2_gameplay/"
C = open(B + "sr_classic/out/m3/crom.bin", "rb").read()
def u32(a): return struct.unpack_from('>I', C, a)[0]
def s32(a): return struct.unpack_from('>i', C, a)[0]
def u16(a): return struct.unpack_from('>H', C, a)[0]
def s16(a): return struct.unpack_from('>h', C, a)[0]
def f32(a): return struct.unpack_from('>f', C, a)[0]
def cstr(a):
    e = C.find(b'\0', a); return C[a:e].decode('latin1')
# sound request names: pointer table at 0xE3168, index = request number passed to func 0x1788
REQ = []
a = 0xE3168
while True:
    p = u32(a)
    if not (0x8D000 <= p < 0x200000): break
    REQ.append(cstr(p)); a += 4
SPOKEN = {}
try:
    for r in csv.reader(open(_DATA + r"/classic/audio/sr2_requests.csv")):
        SPOKEN[r[0]] = r[1]
except Exception as e: pass
