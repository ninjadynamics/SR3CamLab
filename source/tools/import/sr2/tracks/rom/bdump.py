"""python -I bdump.py BANK ADDR(FFxxxxxx or offset) NWORDS [PERLINE] [fmt]  : dump banked CROM words"""
import sys, struct
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
B = _TMP + r"/"
f = open(B + "sr_classic/out/m3/banked_crom.bin", "rb")
bank = int(sys.argv[1]); a = int(sys.argv[2], 16) & 0x7FFFFF; n = int(sys.argv[3], 0); per = int(sys.argv[4]) if len(sys.argv) > 4 else 8; fmt = sys.argv[5] if len(sys.argv) > 5 else 'a'
f.seek(bank * 0x800000 + a); D = f.read(4 * n)
def one(w):
    fl = struct.unpack('>f', struct.pack('>I', w))[0]
    if fmt == 'x': return '%08X' % w
    if fmt == 'f': return '%.3f' % fl
    if w == 0x80000000: return '-0'
    if w and (1e-4 < abs(fl) < 1e6): return '%.3f' % fl
    if w < 0x10000: return '%d' % w
    if w >= 0xFFFF0000: return '%d' % (w - (1 << 32))
    return '%08X' % w
for i in range(0, n, per):
    ws = struct.unpack_from('>%dI' % min(per, n - i), D, 4 * i)
    print('%06X: ' % (a + 4 * i) + ' '.join(one(w) for w in ws))
