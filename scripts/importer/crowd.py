"""SR3's own animated spectators on an imported course. See ../../15_spectators.md.

  spots = crowd.classic_spots('1', cen=centre_line_sr3, ox=.., oz=..)   # the 1995 crowd table -> [(x, y, z, heading)]
  crowd.apply(trk, spots)                                               # importer: replaces the two object files of a BT.Track
  python crowd.py <built track folder> <new output folder> [course] [--safe]   # standalone: copies the folder, writes the two files
      --safe = S1: SEGA's files with only the spectator matrices rewritten (build_safe); default = S2 (build)

What is written
  *_game_objects_gfx_data.sbf : the donor's file (default: SEGA's Desert4) with a NEW root chunk: only the donor's hidden
      "animator" spectators (the animated masters) + one (A)Dumb_Temp_Spectator per spot. No particles, animals, bollards,
      start banner, birds, cameramen, sounds. The material binding table (root +10) and all other chunks are kept as they are.
  *_gameobj_gfx_dis_data.sbf  : the donor's file with a NEW root chunk: only the model/animation sets whose objects still
      exist, with their object index lists rewritten. Granny chunks are kept.
Heading: radians, direction the spectator LOOKS at, f = (sin h, 0, cos h) in SR3 x/z."""
import os, sys, struct, shutil, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sbfw
from common import TRACKS, WORK, track_files

GO, DIS = 'game_objects_gfx_data', 'gameobj_gfx_dis_data'
REC = 0x54; ENT = 0x2C
DUMB = '(A)Dumb_Temp_Spectator'
MASTERS = ('(A)Temp_Spec_Anim', '(A)Temp_Active_Spec_Anim', '(A)Temp_Female_Spec_Anim', '(A)Temp_Airhorn_Spec_Anim', '(A)Temp_Camera_Spec_Anim')
M2 = os.path.join(WORK, 'tmp', 'm2')
# 1995 program ROM (maincpu.bin): per-course tables of trackside objects, 32-byte records, ended by section 99999.
# course 1 VERIFIED against the centre line (median 9 m); the others matched the same way, not used yet.
SRC_TABLES = {'1': (0x4AD00,), '3': (0x4F4C0,), '2': (0x50F00, 0x53120), '4': (0x54000, 0x55EA0)}
SRC_DIRS = {'1': 'course1_mountain', '2': 'course2_desert', '3': 'course3_lakeside', '4': 'course4_forest'}

def cstr(d, o): return d[o:d.index(b'\0', o)].decode('latin1')

# ---------------------------------------------------------------- parsers (also the self-check's model of the layout)
def parse_entries(d, pdesc):
    """descriptor {u32 1, u32 n, ptr entries}; entry 0x2C = {ptr class, u32, u32, ptr type, u32 nobj, ptr object indices,
    u32 nres, ptr res ids (chunk refs), ptr res name pointers, u32, u32}. -> (entries, pointer offsets, ref offsets)"""
    one, n, pe = struct.unpack_from('<3I', d, pdesc); fix = {pdesc + 8}; ref = set(); out = []
    for i in range(n):
        o = pe + ENT * i; w = struct.unpack_from('<11I', d, o)
        fix |= {o, o + 0xC, o + 0x14, o + 0x1C, o + 0x20}
        idx = list(struct.unpack_from('<%dI' % w[4], d, w[5])); ids = list(struct.unpack_from('<%dI' % w[6], d, w[7]))
        npt = struct.unpack_from('<%dI' % w[6], d, w[8])
        ref |= {w[7] + 4 * k for k in range(w[6])}; fix |= {w[8] + 4 * k for k in range(w[6])}
        out.append(dict(cls=cstr(d, w[0]), a=w[1], b=w[2], type=cstr(d, w[3]), idx=idx, res=ids, names=[cstr(d, p) for p in npt], tail=(w[9], w[10])))
    return out, fix, ref

def parse_objects(c):
    """game_objects root chunk -> dict(version, objects, desc, shapes, fix, ref); fix / ref = the pointer and chunk-id
    offsets this layout model predicts (compared with the chunk's real lists by selfcheck)"""
    d = c.data; ver, n, prec, pdesc, ptab = struct.unpack_from('<5I', d, 0); fix = {8, 0xC, 0x10}; objs = []; real = set(c.fix)
    for i in range(n):
        o = prec + REC * i; pg, pc, one, npar, oid = struct.unpack_from('<IIHHI', d, o); pp = struct.unpack_from('<I', d, o + 0x50)[0]
        fix |= {o, o + 4, o + 0x50}; par = []
        for k in range(npar):
            a, b = struct.unpack_from('<II', d, pp + 8 * k); fix |= {pp + 8 * k, pp + 8 * k + 4}
            if b in real: fix.add(b); par.append((cstr(d, a), cstr(d, struct.unpack_from('<I', d, b)[0])))     # text parameter: the value cell is a pointer
            elif cstr(d, a).startswith('Assets') and d[b:b + 3] == b'M:/': par.append((cstr(d, a), ('inline', cstr(d, b))))     # a path written where the value is (Start_Finish_Line; not a pointer cell)
            else: par.append((cstr(d, a), d[b:b + 4]))
        objs.append(dict(group=cstr(d, pg), cls=cstr(d, pc), one=one, id=oid, m=struct.unpack_from('<16f', d, o + 0x10), par=tuple(par)))
    desc, f2, ref = parse_entries(d, pdesc); fix |= f2
    nt = struct.unpack_from('<I', d, ptab)[0]; ref |= {ptab + 4 + 4 * k for k in range(nt)}
    return dict(version=ver, objects=objs, desc=desc, shapes=list(struct.unpack_from('<%dI' % nt, d, ptab + 4)), fix=fix, ref=ref)

def parse_dis(c):
    ent, fix, ref = parse_entries(c.data, 0); return dict(entries=ent, fix=fix, ref=ref)

# ---------------------------------------------------------------- writers
class _Buf:
    def __init__(self): self.b = bytearray(); self.fix = []; self.ref = []; self.late = []; self.strs = {}
    def pos(self): return len(self.b)
    def u32(self, *v): self.b += struct.pack('<%dI' % len(v), *v)
    def ptr(self, target=0):                      # target: int offset now, or a key resolved by link()
        self.fix.append(len(self.b))
        if isinstance(target, int): self.u32(target)
        else: self.late.append((len(self.b), target)); self.u32(0)
    def cid(self, v): self.ref.append(len(self.b)); self.u32(v)
    def pad(self, n=4): self.b += b'\0' * (-len(self.b) % n)
    def string(self, s):
        if s not in self.strs: self.strs[s] = len(self.b); self.b += s.encode('latin1') + b'\0'; self.pad()
        return self.strs[s]
    def link(self, where):
        for o, key in self.late: struct.pack_into('<I', self.b, o, where[key])
        self.late = []

def _write_entries(B, ents, tag):
    """entry table at the current position; returns nothing, pointers resolved through B.link"""
    where = {}
    for i, e in enumerate(ents):
        B.ptr(('s', e['cls'])); B.u32(e['a'], e['b']); B.ptr(('s', e['type'])); B.u32(len(e['idx'])); B.ptr((tag, i, 'idx'))
        B.u32(len(e['res'])); B.ptr((tag, i, 'res')); B.ptr((tag, i, 'names')); B.u32(*e['tail'])
    for i, e in enumerate(ents):
        where[(tag, i, 'idx')] = B.pos(); B.u32(*e['idx']) if e['idx'] else None
        where[(tag, i, 'res')] = B.pos()
        for r in e['res']: B.cid(r)
        where[(tag, i, 'names')] = B.pos()
        for s in e['names']: B.ptr(('s', s))
    return where

def _strings(B, where):
    for o, key in B.late:
        if key[0] == 's': where[key] = B.string(key[1])

def build_objects_root(objs, desc=(), shapes=()):
    """objs: dicts like parse_objects gives. -> (data, fix, ref). Same field layout as SEGA's root, own block order."""
    B = _Buf(); B.u32(3, len(objs)); B.ptr('rec'); B.ptr('desc'); B.ptr('tab'); where = {}
    where['desc'] = B.pos(); B.u32(1, len(desc)); B.ptr('ent')
    where['ent'] = B.pos(); where.update(_write_entries(B, list(desc), 'd'))
    where['rec'] = B.pos(); sets = {}
    for ob in objs:
        B.ptr(('s', ob['group'])); B.ptr(('s', ob['cls'])); B.b += struct.pack('<HHI', ob.get('one', 1), len(ob['par']), ob['id'])
        B.b += struct.pack('<16f', *ob['m']); B.ptr(('p', sets.setdefault(ob['par'], len(sets))))
    for par, k in sets.items():
        where[('p', k)] = B.pos()
        for j in range(len(par)): B.ptr(('s', par[j][0])); B.ptr(('v', k, j))
        if not par: B.u32(0, 0)
    for par, k in sets.items():
        for j, (nm, val) in enumerate(par):
            where[('v', k, j)] = B.pos()
            if isinstance(val, str): B.ptr(('s', val))                 # text parameter: the value cell is a pointer
            elif isinstance(val, tuple) and val[0] == 'inline': B.b += val[1].encode('latin1') + bytes(1); B.pad(4)
            else: B.b += bytes(val)[:4].ljust(4, b'\0')
    _strings(B, where); B.pad(4)
    where['tab'] = B.pos(); B.u32(len(shapes))
    for s in shapes: B.cid(s)
    B.pad(16); B.link(where)
    return bytes(B.b), sorted(B.fix), sorted(B.ref)

def build_dis_root(ents):
    B = _Buf(); B.u32(1, len(ents)); B.ptr('ent'); where = {'ent': B.pos()}; where.update(_write_entries(B, ents, 'e'))
    _strings(B, where); B.pad(16); B.link(where)
    return bytes(B.b), sorted(B.fix), sorted(B.ref)

# ---------------------------------------------------------------- the object files
def matrix(x, y, z, heading):
    """rows as SEGA stores them: (c, 0, s, 0) (0, 1, 0, 0) (-s, 0, c, 0) (x, y, z, 1). The model looks along local -Z
    (15_spectators.md), so -row2 = (sin h, 0, cos h)."""
    c, s = -np.cos(heading), np.sin(heading)
    return (c, 0.0, s, 0.0, 0.0, 1.0, 0.0, 0.0, -s, 0.0, c, 0.0, float(x), float(y), float(z), 1.0)

def donor_files(donor='Desert4'):
    p = track_files(donor if os.path.isdir(donor) else os.path.join(TRACKS, donor))
    return sbfw.read_sbf(p[GO]), sbfw.read_sbf(p[DIS])

def build(spots, donor='Desert4', draw_distance=95.0, shadow=True, prune=False, root_ids=None, bindings=True, drop_looks=(), finish_at=None):
    """-> (game_objects SbfFile, gameobj_dis SbfFile, info dict). spots: [(x, y, z, heading)] in SR3 coordinates.
    root_ids: (game_objects root id, dis root id) of the SLOT when the donor is another track (the file names carry the
    slot's route name; the root id is kept from the donor otherwise)."""
    g, dz = donor_files(donor); po = parse_objects(g.chunks[-1]); pd = parse_dis(dz.chunks[-1])
    old = po['objects']; masters = [dict(o) for o in old if o['cls'] in MASTERS]
    if not any(o['cls'] == DUMB for o in old): raise ValueError('donor has no %s' % DUMB)
    par = (('Draw Distance', struct.pack('<f', draw_distance)), ('Cast Shadow (Fwd)', struct.pack('<I', int(shadow))),
           ('Cast Shadow (Rvs)', struct.pack('<I', int(shadow))), ('Reflect in water', struct.pack('<I', 0)))
    objs = masters + [dict(group='Skinned_Objects', cls=DUMB, one=1, id=0, m=matrix(*s), par=par) for s in spots]
    # finish_at (x, y, z): the slot's own Start_Finish_Line object is kept and stood there (identity rotation). The game shows its
    # model's LOD 0 at the start, LOD 1 once the race is on and the car is 300 m away, LOD 2 on the final lap within 300 m
    # (0x61CAF0: the 'LOD' forced through object +1B8 is the banner's state). finishgate.py puts the 1995 gate into those LODs.
    desc = []
    if finish_at is not None:
        sf = next(dict(o) for o in old if o['cls'] == 'Start_Finish_Line')
        sf['m'] = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, float(finish_at[0]), float(finish_at[1]), float(finish_at[2]), 1.0)
        objs.append(sf); desc = [dict(e, idx=[len(objs) - 1]) for e in po['desc'] if e['cls'] == 'StartFinishObj']
    base = min(o['id'] for o in old)
    for i, o in enumerate(objs): o['id'] = base + i                    # unique, ascending, from the donor's first id
    oldcls = [o['cls'] for o in old]; bycls = collections.defaultdict(list)
    for i, o in enumerate(objs): bycls[o['cls']].append(i)
    ents = []
    for e in pd['entries']:
        # drop_looks: the game draws three of the eleven looks it picks from (the woman, the man with the camera, the man with the
        # airhorn) turned 180 degrees from the other eight - seen in game 2026-10-08 (two women and one man with their backs to the
        # road while their neighbours faced it; the Granny models and animations all face the same way, so it is the game's doing,
        # not traced). Which look a spectator gets is the game's choice at run time, so the heading cannot be corrected per person:
        # those looks are left out of the pool (user: "Every NPC must face the track").
        if e['cls'].startswith('Dumb') and any(k in e['cls'] for k in drop_looks): continue
        cl = {oldcls[k] for k in e['idx']}
        if len(cl) != 1: raise ValueError('dis entry %s mixes classes %s' % (e['cls'], cl))
        idx = bycls.get(cl.pop())
        if idx: ents.append(dict(e, idx=list(idx)))
    # root +10 is the MATERIAL BINDING table (Granny material name -> kind 2 chunk): 0x55D7B0 finds a model's materials in it by
    # name and 0x5BF4A6 switches a shader option on each of them. Emptied (first step35) = grey, T-posed, misplaced figures.
    d, fx, rf = build_objects_root(objs, desc=desc, shapes=po['shapes'] if bindings else ())
    gr = g.chunks[-1]; g.chunks[-1] = sbfw.Ch(5, (root_ids or (gr.id,))[0], d, fx, rf)
    d2, fx2, rf2 = build_dis_root(ents); dr = dz.chunks[-1]; dz.chunks[-1] = sbfw.Ch(5, (root_ids or (0, dr.id))[1], d2, fx2, rf2)
    dropped = 0
    if prune:                                                          # granny chunks no entry uses any more
        by = dz.byid(); keep = {dz.chunks[-1].id}
        for e in ents:
            for r in e['res']: keep.add(r); keep.update(by[r].refs())
        dropped = len(dz.chunks) - len(keep); dz.chunks = [c for c in dz.chunks if c.id in keep]
    for f in (g, dz):
        for c in f.chunks: c.gap = None
    info = dict(objects=len(objs), masters=len(masters), spectators=len(spots), removed=len(old) - len(masters), donor_objects=len(old),
                dis_entries=len(ents), dis_entries_donor=len(pd['entries']), dis_chunks_dropped=dropped)
    return g, dz, info

def build_safe(spots, donor='Desert4', park=None):
    """S1: SEGA's two files untouched except the MATRICES of the existing spectator records (no record, index, id, pointer
    or chunk changes; the root keeps its size). Spare records are parked in a block beside SEGA's hidden animators.
    Everything else of the donor (animals, bollards, ...) stays where SEGA put it."""
    g, dz = donor_files(donor); c = g.chunks[-1]; po = parse_objects(c); d = bytearray(c.data); prec = struct.unpack_from('<I', d, 8)[0]
    idx = [i for i, o in enumerate(po['objects']) if o['cls'] == DUMB]
    if len(spots) > len(idx): raise ValueError('%d spots, the donor has %d spectator records' % (len(spots), len(idx)))
    an = np.array([o['m'][12:15] for o in po['objects'] if o['cls'] in MASTERS]); px, py, pz = park or (an[:, 0].max() + 6.0, an[:, 1].min(), an[:, 2].mean())
    for k, i in enumerate(idx):
        if k < len(spots): m = matrix(*spots[k])
        else: j = k - len(spots); m = matrix(px + 1.5 * (j // 10), py, pz + 1.5 * (j % 10 - 4.5), 0.0)
        struct.pack_into('<16f', d, prec + REC * i + 0x10, *m)
    g.chunks[-1] = sbfw.Ch(5, c.id, bytes(d), c.fix, c.ref)
    info = dict(objects=len(po['objects']), masters=sum(1 for o in po['objects'] if o['cls'] in MASTERS), spectators=len(spots), parked=len(idx) - len(spots),
                removed=0, donor_objects=len(po['objects']), dis_entries=len(parse_dis(dz.chunks[-1])['entries']), dis_chunks_dropped=0)
    info['dis_entries_donor'] = info['dis_entries']
    return g, dz, info

def apply(trk, spots, donor='Desert4', **kw):
    """importer hook: trk = build_testtrack.Track; replaces its two object files (do NOT run BT.gc on them afterwards:
    the textures / materials of the spectators are found by id, not through the root)."""
    old = trk.files.get(GO); odis = trk.files.get(DIS)
    ids = None
    if os.path.basename(str(donor)).lower() != trk.slot.lower():
        src = donor_files(trk.slot); ids = (src[0].chunks[-1].id, src[1].chunks[-1].id)
    g, dz, info = build(spots, donor, root_ids=ids, **kw); trk.files[GO] = g; trk.files[DIS] = dz
    return info

# ---------------------------------------------------------------- 1995 crowd
def classic_table(course='1'):
    """records of the 1995 trackside-object table(s): dict(angle, pos (game x, y, z), section, kind, model, flag).
    kind 4 = one spectator sprite (22 models = objects 235..278 in pairs)."""
    b = open(os.path.join(M2, 'maincpu.bin'), 'rb').read(); out = []
    for o in SRC_TABLES[str(course)]:
        while True:
            a, x, y, z = struct.unpack_from('<4f', b, o); s, k, m, fl = struct.unpack_from('<4I', b, o + 16)
            if s == 99999 or s > 4096: break
            out.append(dict(angle=a, pos=(x, y, z), section=s, kind=k, model=m, flag=fl)); o += 32
    return out

def fit_offset(cen, course='1', zs=-1.0):
    """(ox, oz) of SR3 = (x_obj + ox, y, zs * z_obj + oz), recovered from a built track's centre line and the course csv"""
    d = os.path.join(os.path.dirname(WORK), 'classic', 'courses', 'src', SRC_DIRS[str(course)])
    C = np.loadtxt(os.path.join(d, 'src_course%s_centreline.csv' % course), delimiter=',', comments='#'); Q = np.stack([C[:, 0], zs * C[:, 2]], 1)
    S = np.asarray(cen)[:, [0, 2]]; off = (S.min(0) + S.max(0)) / 2 - (Q.min(0) + Q.max(0)) / 2
    for it in range(3):
        j = [int(np.argmin(np.hypot(S[:, 0] - q[0] - off[0], S[:, 1] - q[1] - off[1]))) for q in Q]; off = off + np.median(S[j] - (Q + off), axis=0)
    res = np.array([np.min(np.hypot(S[:, 0] - q[0] - off[0], S[:, 1] - q[1] - off[1])) for q in Q])
    return float(off[0]), float(off[1]), float(np.median(res)), float(res.max())

def classic_spots(course, cen, ox, oz, zs=-1.0, lat=None, lo=None, hi=None, margin=0.75, kinds=(4,), lift=0.09):
    """1995 spectators -> [(x, y, z, heading)] in SR3 coordinates, each looking at the nearest centre-line point.
    cen: n x 3 centre line (SR3). With lat / lo / hi (trackdeform.road_frame of the built road) a spectator standing inside
    the drivable strip is moved sideways to its edge + margin (height kept, never below the road edge there).
    lift: the 1995 sprites sit 9 cm (median) under the 1995 ground polygons; the feet are raised by that much."""
    cen = np.asarray(cen, float); out = []; moved = 0
    for r in classic_table(course):
        if r['kind'] not in kinds: continue
        gx, gy, gz = r['pos']; p = np.array([gx + ox, gy + lift, -zs * gz + oz])         # OBJ z = -game z ; SR3 z = zs * OBJ z + oz
        j = int(np.argmin(np.hypot(cen[:, 0] - p[0], cen[:, 2] - p[2])))
        if lat is not None:
            l = lat[j]; s = (p - cen[j]) @ l
            if lo[j] - margin < s < hi[j] + margin and abs(p[1] - cen[j, 1]) < 2.5:
                t = hi[j] + margin if s >= 0 else lo[j] - margin; p = p + l * (t - s); p[1] = max(p[1], cen[j, 1]); moved += 1
        to = cen[j] - p; out.append((float(p[0]), float(p[1]), float(p[2]), float(np.arctan2(to[0], to[2]))))
    classic_spots.moved = moved
    return out

# ---------------------------------------------------------------- standalone
def road_of(folder):
    import trackdeform as TDM
    f = sbfw.read_sbf(track_files(folder)['master_gfx_xdata']); by = f.byid(); t = TDM.parse_td(by[f.chunks[-1].u32(0xC)], by)
    return TDM.road_frame(t)

def write_folder(src, out, spots, donor='Desert4', slot=None, safe=False, **kw):
    """copy the built folder `src` to `out` and write the two object files there. Missing pobj files are copied from the
    slot's own track (the game needs them with the grass cache)."""
    slot = slot or os.path.basename(os.path.normpath(src)); os.makedirs(out, exist_ok=True); notes = []
    game = track_files(os.path.join(TRACKS, slot)); have = track_files(src)
    for fn in os.listdir(src): shutil.copyfile(os.path.join(src, fn), os.path.join(out, fn))
    for s in ('pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata', 'proc'):
        if s not in have and s in game: shutil.copyfile(game[s], os.path.join(out, os.path.basename(game[s]))); notes.append('%s copied from the game (missing in %s)' % (os.path.basename(game[s]), src))
    ids = None
    if os.path.basename(str(donor)).lower() != slot.lower():
        a, b = donor_files(slot); ids = (a.chunks[-1].id, b.chunks[-1].id)
    g, dz, info = build_safe(spots, donor) if safe else build(spots, donor, root_ids=ids, **kw)
    for s, f in ((GO, g), (DIS, dz)):
        name = os.path.basename(have.get(s) or game[s]); open(os.path.join(out, name), 'wb').write(sbfw.write_sbf(f, layout='auto'))
    info['notes'] = notes
    return info

def main(argv):
    safe = '--safe' in argv; argv = [a for a in argv if a != '--safe']
    src, out = argv[0], argv[1]; course = argv[2] if len(argv) > 2 else '1'
    cen, lat, lo, hi = road_of(src); ox, oz, med, worst = fit_offset(cen, course)
    spots = classic_spots(course, cen, ox, oz, lat=lat, lo=lo, hi=hi)
    info = write_folder(src, out, spots, safe=safe)
    print('offset ox %.3f oz %.3f (centre-line fit: median %.2f m, worst %.2f m)' % (ox, oz, med, worst))
    print('%d spectators (%d moved off the road strip), %d hidden animators; %d of the donor\'s %d objects removed; dis entries %d of %d' %
          (info['spectators'], classic_spots.moved, info['masters'], info['removed'], info['donor_objects'], info['dis_entries'], info['dis_entries_donor']))
    for n in info['notes']: print('NOTE', n)

if __name__ == '__main__':
    main(sys.argv[1:])
