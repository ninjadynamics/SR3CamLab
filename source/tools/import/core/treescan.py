"""List meshes whose materials are alpha-tested (trees, bushes, fences) in a track's master_gfx and pobj_master files.
    python treescan.py [Track]"""
import os, sys, struct, re, collections
import numpy as np
from common import *
import sbfw, meshgen, matscan

def names(c):
    return [s.decode('latin1') for s in re.findall(rb'[A-Za-z_][A-Za-z0-9_\-\.]{5,}', c.data[-400:])]

def main(track='Alpine4'):
    tf = track_files(os.path.join(TRACKS, track)); g = sbfw.read_sbf(tf['master_gfx_xdata']); gby = g.byid()
    for key in ('master_gfx_xdata', 'pobj_master_gfx_xdata'):
        f = sbfw.read_sbf(tf[key]); by = f.byid(); rows = []; fmts = collections.Counter()
        for c in f.kinds(1):
            h = struct.unpack_from('<18I', c.data, 0); fmts[(h[0], hex(h[2]), h[8], h[11] // 0x48 if h[11] % 0x48 == 0 else -1)] += 1
            if h[11] % 0x48: continue
            try: m = meshgen.parse_mesh(c)
            except Exception: continue
            at = []
            for gr in m['groups']:
                mt = by.get(gr[4]) or gby.get(gr[4])
                at.append(None if mt is None or len(mt.data) != 1848 else (mt.u32(0x4d4), mt.u32(0x4e4), mt.u32(0x50c), mt.u32(0x1bc)))
            if not any(a and a[0] for a in at): continue
            t = m['tail']; bb = struct.unpack_from('<9f', c.data, t + 0x10)
            rows.append((c.id, h[0], h[2], m['nv'], m['ni'], len(m['groups']), h[11] // 0x48, bb, at, names(c)[:3]))
        print(key, 'meshes', len(f.kinds(1)), 'layouts (stride, fmt, groups, lods):', fmts.most_common(8))
        print('  meshes with an alpha-tested group:', len(rows))
        for r in sorted(rows, key=lambda r: r[3])[:60]:
            bb = r[7]; sz = [bb[3 + i] - bb[i] for i in range(3)]
            print('  %08x stride %d fmt %04x nv %5d ni %5d groups %d lods %d size %6.1f %6.1f %6.1f min %7.1f %7.1f %7.1f  %s %s' % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], *sz, *bb[:3], [('%d%d%d %08x' % a) if a else None for a in r[8]], r[9]))

if __name__ == '__main__':
    main(*sys.argv[1:2])
