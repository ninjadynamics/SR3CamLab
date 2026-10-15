"""Surface types: dumps the two lists behind exe 0x5B1820 (SurfacePairEffects\\surfacepairdata_xdata.sbf root +0x2C names,
+0x30 texture ids) and finds, per track, which road-layer texture ids select which terrain.
    python surfaces.py            -> prints tables, writes ../tmp/surfaces.json
"""
import os, sys, struct, json, collections, glob
from common import *
import sbfw

def cstr(d, o): return d[o:d.index(b'\0', o)].decode('latin1')
def load_db():
    p = os.path.join(GAME, 'SurfacePairEffects', 'surfacepairdata_xdata.sbf')
    f = sbfw.read_sbf(p); by = f.byid(); r = f.chunks[-1]
    A = by[r.u32(0x2c)]; B = by[r.u32(0x30)]
    names = []; o = 8
    for k in range(A.u32(4)):
        nxt, h, idx = struct.unpack_from('<III', A.data, o); names.append((cstr(A.data, o + 12), idx, h)); o = nxt
    ids = []; o = 8
    for k in range(B.u32(4)):
        nxt, n = struct.unpack_from('<II', B.data, o); ids.append(list(struct.unpack_from('<%dI' % n, B.data, o + 8))); o = nxt
    assert len(names) == len(ids)
    return [dict(name=n, index=i, hash=h, ids=t) for (n, i, h), t in zip(names, ids)], f

def td_tables(path):
    """(surface id table, usage count of each (surf0, surf1) pair) of a master_gfx file"""
    import trackdeform as TDm, numpy as np
    f = sbfw.read_sbf(path); by = f.byid(); r = f.chunks[-1]
    t = TDm.parse_td(by[r.u32(0xc)])
    V = np.concatenate([v[:-1] for v in t.verts[1:t.n + 1]])
    pairs = collections.Counter(zip(V['surf'][:, 0].tolist(), V['surf'][:, 1].tolist()))
    return t.hashes, pairs, {c.id for c in f.kinds(4)}

if __name__ == '__main__':
    db, f = load_db()
    id2s = {}
    for s in db:
        for i in s['ids']: id2s.setdefault(i, []).append(s['name'])
    print('%d terrain entries' % len(db))
    for s in db: print('%3d %-36s %08x  %d ids' % (s['index'], s['name'], s['hash'], len(s['ids'])))
    tracks = [(t, os.path.join(TRACKS, t)) for t in SR3]
    tracks += [('demo/' + t, os.path.join(DEMO, t)) for t in sorted(os.listdir(DEMO))] if os.path.isdir(DEMO) else []
    tracks += [('ps3/' + t, os.path.join(CONV, t)) for t in sorted(os.listdir(CONV))] if os.path.isdir(CONV) and '--fast' not in sys.argv else []
    out = dict(db=db, tracks={})
    for name, folder in tracks:
        try:
            p = track_files(folder)['master_gfx_xdata']; hashes, pairs, tex = td_tables(p)
        except Exception as e:
            print(name, 'FAILED', e); continue
        rows = []
        for (a, b), n in pairs.most_common():
            rows.append(dict(top_id='%08x' % hashes[a], top=id2s.get(hashes[a], ['?']), base_id='%08x' % hashes[b], base=id2s.get(hashes[b], ['?']), cells=n))
        out['tracks'][name] = dict(ids=['%08x' % h for h in hashes], names=[id2s.get(h, ['?']) for h in hashes], pairs=rows,
                                   missing_textures=['%08x' % h for h in hashes if h not in tex])
        print('==', name, 'layers', len(hashes), 'unknown ids', sum(1 for h in hashes if h not in id2s))
        for r in rows[:8]: print('    %6d cells  top %s %-28s base %s %s' % (r['cells'], r['top_id'], '/'.join(r['top']), r['base_id'], '/'.join(r['base'])))
    json.dump(out, open(os.path.join(TMP, 'surfaces.json'), 'w'), indent=1)
