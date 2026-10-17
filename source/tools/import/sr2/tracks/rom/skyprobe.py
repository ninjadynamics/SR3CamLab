"""Inspect the backdrop / extra models named by the stage records (model table 0xA4BA8, 16 bytes per entry)."""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
sys.path.insert(1, _TMP + r"/sr_classic/scripts")
from sr2course import *
from m3_scene import decode_model
vrom = np.fromfile(B + "sr_classic/out/m3/vrom_le.bin", dtype="<u4")
MODELTAB = 0xA4BA8
def model_addr(i): return u32(MODELTAB + 16 * i)
def texinfo(h):
    tw = 32 << (((h[3] >> 3) & 7) if ((h[3] >> 3) & 7) < 6 else 0); th = 32 << ((h[3] & 7) if (h[3] & 7) < 6 else 0)
    tx = (32 * (((h[4] & 0x1F) << 1) | ((h[5] >> 7) & 1))) & 2047; ty = (32 * (h[5] & 0x1F)) & 2047
    return ((h[4] >> 6) & 1, tx, ty, tw, th, (h[6] >> 7) & 7) if h[6] & 0x400 else None
if __name__ == '__main__':
    for s in range(8):
        st = stage(s)
        for nm in ('w3', 'w4', 'w2'):
            i = st[nm]; a = model_addr(i); polys, ok = decode_model(vrom, a)
            P = np.array([v[:3] for vs, h in polys for v in vs]) if polys else np.zeros((1, 3))
            tex = sorted({texinfo(h) for vs, h in polys if texinfo(h)})
            print('stage %d %s idx %4d addr %06X ok=%s polys %4d bbox x[%.0f %.0f] y[%.0f %.0f] z[%.0f %.0f] tex %s' % (s, nm, i, a, ok, len(polys), P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(), P[:, 2].min(), P[:, 2].max(), tex[:6]))
