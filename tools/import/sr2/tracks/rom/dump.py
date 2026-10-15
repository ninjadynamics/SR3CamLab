"""python -I dump.py ADDR NWORDS [PERLINE] [fmt]  : dump CROM words as hex + float/str hints. fmt: x (hex only) f (floats) a (auto)"""
import sys, struct
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
B = _TMP + r"/"
C = open(B + "sr_classic/out/m3/crom.bin", "rb").read()
a = int(sys.argv[1], 16); n = int(sys.argv[2], 0); per = int(sys.argv[3]) if len(sys.argv) > 3 else 8; fmt = sys.argv[4] if len(sys.argv) > 4 else 'a'
def cs(p):
    if not (0x8D000 <= p < 0x200000): return None
    e = C.find(b'\0', p, p + 60)
    s = C[p:e]
    if len(s) >= 3 and all(32 <= c < 127 for c in s): return s.decode()
def one(w):
    f = struct.unpack('>f', struct.pack('>I', w))[0]
    if fmt == 'x': return '%08X' % w
    if fmt == 'f': return '%10.3f' % f
    s = cs(w)
    if s: return '"%s"' % s
    if w and (1e-3 < abs(f) < 1e6) and (w >> 24) not in (0,): return '%.3f' % f
    if w < 0x10000: return '%d' % w
    if w >= 0xFFFF0000: return '%d' % (w - (1 << 32))
    return '%08X' % w
for i in range(0, n, per):
    ws = struct.unpack_from('>%dI' % min(per, n - i), C, a + 4 * i)
    print('%06X: ' % (a + 4 * i) + ' '.join(one(w) for w in ws))
