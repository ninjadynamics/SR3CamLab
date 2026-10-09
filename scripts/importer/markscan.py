"""How are a track's painted road markings stored?  python markscan.py [Track] [texture id hex]
Lists mesh groups whose material's diffuse texture is the line texture (default 54c156ac, the white double line)."""
import os, sys, struct, collections
import numpy as np
from common import *
import sbfw, meshgen, trackdeform as TDm

def main(track='Alpine4', tex='54c156ac'):
    tex = int(tex, 16); f = sbfw.read_sbf(track_files(os.path.join(TRACKS, track))['master_gfx_xdata']); by = f.byid(); r = f.chunks[-1]
    td = TDm.parse_td(by[r.u32(0xc)]); cen = np.array([td.verts[i][len(td.verts[i]) // 2]['pos'] for i in range(1, td.n + 1)])
    mats = [c for c in f.kinds(2) if tex in c.refs()]
    print(track, 'materials referencing %08x:' % tex, [('%08x' % c.id, len(c.data), [hex(o) for o in c.ref if c.u32(o) == tex]) for c in mats])
    ids = {c.id for c in mats}; n = 0; tot = 0; dists = []; ys = []; fm = collections.Counter(); uvr = []
    for c in f.kinds(1):
        h = struct.unpack_from('<18I', c.data, 0)
        if h[11] % 0x48: continue
        for k in range(h[8]):
            g = struct.unpack_from('<5I', c.data, h[11] + 20 * k)
            if g[4] not in ids: continue
            st = h[0]; V = np.frombuffer(c.data, np.uint8, st * h[5], h[12]).reshape(-1, st); P = V[g[0]:g[0] + g[1], :12].copy().view('<f4').reshape(-1, 3)
            n += 1; tot += g[1]; fm[(st, hex(h[2]))] += 1
            idx, d = nearest2d(cen[:, [0, 2]], P[:, [0, 2]], cell=8.0); dists += d.tolist(); ys += (P[:, 1] - cen[idx, 1]).tolist()
            if n <= 3:
                print('  mesh %08x group %d: verts %d (first %d), strip %d, material %08x, stride %d fmt %04x' % (c.id, k, g[1], g[0], g[3] & 0xffff, g[4], st, h[2]))
                for j in range(min(6, g[1])):
                    row = V[g[0] + j]; print('     pos %8.2f %7.2f %8.2f  dist to centre line %.2f  dy %.3f  tail u16 %s' % (*P[j], d[j], P[j, 1] - cen[idx[j], 1], np.frombuffer(row.tobytes(), '<u2')[-4:].tolist()))
    if not n: print('  no mesh group uses it'); return
    dists = np.array(dists); ys = np.array(ys)
    print('  %d groups, %d vertices, formats %s' % (n, tot, dict(fm)))
    print('  distance from the road centre line: min %.2f median %.2f max %.2f ; height above the road vertex: median %.3f, 5..95%% %.3f..%.3f' % (dists.min(), np.median(dists), dists.max(), np.median(ys), np.percentile(ys, 5), np.percentile(ys, 95)))
    print('  histogram of distance (m):', np.histogram(dists, bins=[0, 0.5, 1, 2, 3, 4, 5, 6, 8, 12, 50])[0].tolist())

if __name__ == '__main__':
    main(*sys.argv[1:3])
