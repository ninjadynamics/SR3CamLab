"""Full listing of the SR2 program with resolved addresses -> ../work/sr2.lst ; xrefs -> ../work/xref.pkl
usage: python -I mklist.py [end_hex]"""
import struct, sys, pickle, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppc import dis, Tracker
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
B = _TMP + r"/"
C = open(B + "sr_classic/out/m3/crom.bin", "rb").read()
END = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0xA0000
SDA = {}
if len(sys.argv) > 2:
    for kv in sys.argv[2].split(','):
        r, v = kv.split('='); SDA[int(r)] = int(v, 16)
os.makedirs(B + "sr2_gameplay/work", exist_ok=True)

def cstr(a):
    if a >= len(C) or a < 0x1000: return None
    e = C.find(b'\0', a, a + 80)
    if e < 0 or e - a < 4: return None
    s = C[a:e]
    if all(32 <= ch < 127 or ch in (10, 13) for ch in s): return s.decode('ascii').replace('\n', '\\n')
    return None

T = Tracker(SDA); xr = collections.defaultdict(list); calls = collections.defaultdict(list); out = []
funcstart = 0; funcs = []
for pc in range(0, END, 4):
    w = struct.unpack_from('>I', C, pc)[0]
    m, o, I, res = T.step(pc, w)
    cm = ''
    if 'mem' in res:
        cm = '; [%08X] %s' % (res['mem'], res['rw']); xr[res['mem']].append((pc, res['rw'], m))
    elif 'const' in res:
        s = cstr(res['const']); cm = '; =%08X' % res['const'] + (' "%s"' % s if s else ''); xr[res['const']].append((pc, 'c', m))
    elif 'tbl' in res:
        cm = '; tbl %08X %s' % (res['tbl'], res['rw']); xr[res['tbl']].append((pc, 'x' + res['rw'], m))
    if I.get('kind') == 'bl': calls[I['target']].append(pc)
    out.append('%06X: %08X  %-8s %s %s' % (pc, w, m, o, cm))
    if I.get('kind') == 'blr':
        out.append(''); T.reset()
open(B + "sr2_gameplay/work/sr2.lst", "w").write('\n'.join(out))
pickle.dump((dict(xr), dict(calls)), open(B + "sr2_gameplay/work/xref.pkl", "wb"))
print(len(out), 'lines', len(xr), 'addresses', len(calls), 'call targets')
