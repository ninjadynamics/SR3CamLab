"""structural self-check of object files written by crowd.py against SEGA's donor files.
    python check_crowd.py <track folder> [donor track]"""
import os, sys, struct, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sbfw, crowd
from common import TRACKS, track_files

def main(folder, donor='Desert4'):
    tf = track_files(folder); F = {k: sbfw.read_sbf(p) for k, p in tf.items() if k != 'proc'}; bad = []
    def chk(ok, text):
        print('  %s %s' % ('ok  ' if ok else 'FAIL', text))
        if not ok: bad.append(text)
    print('files:', {k: len(f.chunks) for k, f in F.items()}, '| grass cache', 'proc' in tf)
    chk(all(k in F for k in ('master_gfx_xdata', 'master_xdata', crowd.GO, crowd.DIS, 'pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata')) and 'proc' in tf, 'all six sbf files and the grass cache are present')
    allids = {c.id for f in F.values() for c in f.chunks}; dg, dd = crowd.donor_files(donor)
    for key, don in ((crowd.GO, dg), (crowd.DIS, dd)):
        f = F[key]; pr = sbfw.validate(f, key, extern_ids=allids, quiet=True); orig = sbfw.validate(don, key, quiet=True)
        seen = {q.split(' -> ')[0] for q in orig}; new = [p for p in pr if p.split(' -> ')[0] not in seen]
        chk(not new, "%s: container checks (alignment, pointers inside the data, chunk ids resolve): %d problems, %d of them not in SEGA's own file %s" % (key, len(pr), len(new), new[:3]))
        chk(f.compressed == don.compressed and f.tail == don.tail, "%s: stored %s, %d zero bytes at the end, like SEGA's" % (key, 'compressed' if f.compressed else 'raw', f.tail))
        a = {c.id: c for c in f.chunks[:-1]}; b = {c.id: c for c in don.chunks[:-1]}
        same = sum(1 for i, c in a.items() if i in b and (c.kind, c.data, c.fix, c.ref, c.z) == (b[i].kind, b[i].data, b[i].fix, b[i].ref, b[i].z))
        chk(same == len(a) and [c.id for c in f.chunks[:-1]] == [c.id for c in don.chunks[:-1] if c.id in a], "%s: %d other chunks, all byte-identical to SEGA's and in SEGA's order (%d of the donor's left out)" % (key, len(a), len(b) - len(a)))
        chk(f.chunks[-1].id == don.chunks[-1].id and f.chunks[-1].kind == 5, '%s: root is the last chunk, kind 5, id %08x as in the slot' % (key, f.chunks[-1].id))
    g = F[crowd.GO].chunks[-1]; po = crowd.parse_objects(g); do = crowd.parse_objects(dg.chunks[-1])
    chk(len(po['objects']) == len(do['objects']) or (set(g.fix) == po['fix'] and set(g.ref) == po['ref']), 'game_objects root (S1: SEGA own lists, compared below): %d pointer fix-ups and %d chunk refs = exactly the cells the layout model names' % (len(g.fix), len(g.ref)))
    chk(all(struct.unpack_from('<I', g.data, o)[0] < len(g.data) for o in g.fix), 'game_objects root: every pointer lands inside the %d bytes' % len(g.data))
    safe = len(po['objects']) == len(do['objects'])
    gb = F[crowd.GO].byid(); bound = [gb[s] for s in po['shapes']]
    chk(po['shapes'] == do['shapes'] and all(r in gb and gb[r].kind == 2 for c in bound for r in c.refs()), "material binding table (root +10): the same %d chunks as SEGA's, every material they name is in the file" % len(po['shapes']))
    if safe:
        a = bytearray(g.data); b = bytearray(dg.chunks[-1].data); prec = struct.unpack_from('<I', b, 8)[0]
        for i, o in enumerate(do['objects']):
            if o['cls'] == crowd.DUMB: a[prec + 0x54 * i + 0x10:prec + 0x54 * i + 0x50] = b[prec + 0x54 * i + 0x10:prec + 0x54 * i + 0x50]
        chk(a == b and g.fix == dg.chunks[-1].fix and g.ref == dg.chunks[-1].ref, "S1: game_objects root byte-identical to SEGA's outside the 64 matrix bytes of the spectator records; same fix-up and ref lists")
        chk(F[crowd.DIS].chunks[-1].data == dd.chunks[-1].data, "S1: dis root byte-identical to SEGA's")
    else: chk(po['version'] == 3 and not po['desc'], 'version 3, particle descriptor list empty (as in the empty list that ran in game)')
    objs = po['objects']; cl = collections.Counter(o['cls'] for o in objs); print('     classes:', dict(cl))
    known = {o['cls'] for o in do['objects']}; chk(set(cl) <= known, "every class name exists in SEGA's %s file" % donor)
    chk(len({o['id'] for o in objs}) == len(objs), 'object ids unique (%x..%x)' % (min(o['id'] for o in objs), max(o['id'] for o in objs)))
    sig = lambda o: (o['cls'], o['m'], o['par'], o['group'], o['one'])
    dm = [sig(o) for o in do['objects'] if o['cls'] in crowd.MASTERS]
    chk([sig(o) for o in objs if o['cls'] in crowd.MASTERS] == dm, "%d animator objects: class, group, matrix, parameters identical to SEGA's" % len(dm))
    dpar = collections.Counter(tuple(n for n, v in o['par']) for o in do['objects'] if o['cls'] == crowd.DUMB)
    sp = [o for o in objs if o['cls'] == crowd.DUMB]
    chk(all(tuple(n for n, v in o['par']) in dpar and o['group'] == 'Skinned_Objects' and o['one'] == 1 for o in sp), "%d spectators: group, flag word and parameter names as SEGA's %s" % (len(sp), list(dpar)[0]))
    M = np.array([o['m'] for o in sp]).reshape(-1, 4, 4); R = M[:, :3, :3]
    chk(np.allclose(R @ R.transpose(0, 2, 1), np.eye(3), atol=1e-5) and np.allclose(np.linalg.det(R), 1, atol=1e-5) and np.allclose(M[:, :, 3], [0, 0, 0, 1]) and np.allclose(R[:, 1], [0, 1, 0]), "spectator matrices: rotation about Y only, determinant +1, last column 0 0 0 1 (SEGA's form)")
    P = M[:, 3, :3]; far = np.abs(P[:, [0, 2]]).max(1) >= 750; print('     spectator records parked outside the scenery square (beside the animators):', int(far.sum())); P = P[~far]; chk(safe or not far.any(), 'spectator positions inside the +-750 m scenery square (x %.0f..%.0f, y %.0f..%.0f, z %.0f..%.0f)' % (P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(), P[:, 2].min(), P[:, 2].max()))
    chk(len(sp) <= 992, '%d spectators <= 992 (the most SEGA uses, Tropical4; %s has %d)' % (len(sp), donor, sum(1 for o in do['objects'] if o['cls'] == crowd.DUMB)))
    d = F[crowd.DIS].chunks[-1]; pd = crowd.parse_dis(d); dd_ = crowd.parse_dis(dd.chunks[-1]); by = F[crowd.DIS].byid()
    chk(set(d.fix) == pd['fix'] and set(d.ref) == pd['ref'], 'dis root: %d pointer fix-ups and %d chunk refs = exactly the cells the layout model names' % (len(d.fix), len(d.ref)))
    key = lambda e: (e['cls'], e['a'], e['b'], e['type'], tuple(e['res']), tuple(e['names']), e['tail']); dk = [key(e) for e in dd_['entries']]
    pos = [dk.index(key(e)) if key(e) in dk else -1 for e in pd['entries']]
    chk(-1 not in pos and pos == sorted(pos), "dis root: %d entries, each identical to one of SEGA's %d except for its object list, same order" % (len(pd['entries']), len(dk)))
    cover = collections.Counter(); okcls = True
    for e in pd['entries']:
        cs = {objs[i]['cls'] for i in e['idx']}; okcls &= len(cs) == 1 and max(e['idx']) < len(objs) and len(set(e['idx'])) == len(e['idx'])
        for i in e['idx']: cover[i] += 1
        okcls &= all(r in by and by[r].kind == 5 and by[r].refs()[0] in by and by[by[r].refs()[0]].kind == 7 for r in e['res'])
    chk(okcls, 'dis root: every object index is valid, one class per entry, every resource id -> 8-byte chunk -> Granny chunk in the file')
    dcover = collections.Counter()
    for e in dd_['entries']:
        for i in e['idx']: dcover[do['objects'][i]['cls']] += 1
    per = {c: dcover[c] // sum(1 for o in do['objects'] if o['cls'] == c) for c in cl}
    chk(all(cover[i] == per[o['cls']] for i, o in enumerate(objs)), "every object is listed by as many model sets as in SEGA's file %s" % per)
    print('RESULT:', 'no structural difference found' if not bad else '%d FAILED' % len(bad))
    return bad

if __name__ == '__main__':
    main(*sys.argv[1:3])
