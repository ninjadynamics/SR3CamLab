"""What is in a built track's scenery file, in numbers, for several builds side by side.   python sbf_stats.py <step> [<step> ...]   (from the importer folder)"""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..', '..')))      # tools/import/core
import sys, os, struct, collections
import numpy as np
from common import *
import sbfw, meshgen
rows = collections.OrderedDict()
def put(k, v): rows.setdefault(k, []).append(v)
for step in sys.argv[1:]:
    tf = track_files(os.path.join(OUT, step, 'Desert4')); f = sbfw.read_sbf(tf['master_gfx_xdata']); ch = list(f.chunks)
    put('file bytes', os.path.getsize(tf['master_gfx_xdata'])); put('chunks', len(ch)); kinds = collections.Counter(c.kind for c in ch)
    for k in (1, 2, 3, 4, 5, 6): put('chunks of kind %d' % k, kinds.get(k, 0))
    put('bytes in all chunks', sum(len(c.data) for c in ch)); put('largest chunk bytes', max(len(c.data) for c in ch))
    mesh = [c for c in ch if c.kind == 1 and (c.id >> 16) == 0xc1a7]; nv = []; ni = []
    for c in mesh:
        m = meshgen.parse_mesh(c); nv.append(m['nv']); ni.append(m['ni'])
    put('our meshes', len(mesh)); put('  vertices', sum(nv)); put('  indices', sum(ni)); put('  most vertices in one', max(nv) if nv else 0); put('  most indices in one', max(ni) if ni else 0)
    mats = [c for c in ch if c.kind == 2 and len(c.data) == 1848]; put('uber materials (1848 bytes)', len(mats)); put('other kind-2 chunks', kinds.get(2, 0) - len(mats))
    pre = collections.Counter('%04x' % (c.id >> 16) for c in ch if (c.id >> 24) == 0xc1); put('our chunks by id prefix', ' '.join('%s:%d' % kv for kv in sorted(pre.items())))
    tex = [c for c in ch if c.kind == 4]; dims = collections.Counter(); tb = 0
    for c in tex:
        try:
            w, h = struct.unpack_from('<2I', c.data, 48 + 12)[::-1] if c.data[48:52] == b'DDS ' else (0, 0); fmt = c.data[48 + 84:48 + 88]
        except Exception: w = h = 0; fmt = b'?'
        dims[(w, h, fmt.decode('latin1', 'replace'))] += 1; tb += len(c.data)
    put('textures', len(tex)); put('  texture bytes', tb); put('  largest sizes', ' '.join('%dx%d %s:%d' % (k[0], k[1], k[2], v) for k, v in sorted(dims.items(), key=lambda kv: -kv[0][0] * kv[0][1])[:5]))
    sw = collections.Counter()
    for c in mats:
        d = c.data; sw[tuple(struct.unpack_from('<I', d, o)[0] for o in (0x4d4, 0x4e4, 0x50c, 0x51c, 0x52c, 0x540, 0x594, 0x5b4, 0x620))] += 1
    put('material switch sets (ATEST ABLEND DSIDE SCAST SSRECV SDRECV LMAP SPECM REFL : count)', ' | '.join('%s:%d' % (''.join(str(min(x, 9)) for x in k), v) for k, v in sw.most_common(8)))
    for name in ('game_objects_gfx_data', 'gameobj_gfx_dis_data', 'master_xdata', 'pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata'):
        if name in tf: put('%s bytes' % name, os.path.getsize(tf[name]))
print('%-88s' % '', ' | '.join('%-22s' % s.replace('step99_mountain_', '').replace('_desert4', '') for s in sys.argv[1:]))
for k, v in rows.items(): print('%-88s' % k, ' | '.join('%-22s' % str(x) for x in v))
