"""The REAL 1995 checkpoint / finish gates of SEGA Rally Championship, placed on a course.

Found 2026-10-08 with the user's emulator texture dump: the "CHECK POINT" letters are tile s0 x1792 y0064 256x64; the ROM
polygons that use it are objects 789 / 790, and their neighbours in the object table are the whole gate set:
    783 / 784  post, 0.6 m wide, 6 m tall           785 / 786  post, 1.0 m          787 / 788  post with a SEGA RALLY CHAMPIONSHIP sign
    789  CHECK POINT banner 10 m (blue panel + yellow letters, y 4.6 .. 5.8)       790  the same, 20 m, with sponsor panels
    791  FINISH! banner 10 m (grey panel + red letters)                             792  the same, 20 m
Placement: the trackside table of the course (program ROM, see crowd.py / 15_spectators.md), records
{angle, x, y, z (game axes), section, kind, model, flag}: kind 16 (one per gate) and kind 17. Reading used here (LIKELY, from
the distances: at every gate one kind-17 record lies 10 m from the kind-16 record, across the road):
    a gate = two posts, at the kind-16 position and at the kind-17 position 9 .. 11 m from it; the 10 m banner hangs between them.
    kind-16 model 0 = CHECK POINT, model 1 = FINISH (the start / finish line).
The code that maps a record's model number to an object was not read; post style per gate is a choice (course JSON).

    python gates1995.py 1          -> classic/courses/src/<course dir>/src_course1_gates.obj + its tiles in textures/
    faces = gates1995.faces(cfg, rd)    importer face list (reads that OBJ)
Wired into the importer 2026-10-08 (import_classic, course JSON "gates": "1995" = default; "gantries" = the old stand-ins).
Without numpy since 2026-10-15 (kb 31): a point is a tuple; the lengths, crossings and placements are numpy's operations in its order
(n2 / n3 below; the y part of every product kept, so a -0.0 comes out where numpy's did). The files are byte for byte the numpy version's."""
import os, sys, struct, json, math
from common import *

DIRS = {1: 'course1_mountain', 2: 'course2_desert', 3: 'course3_lakeside', 4: 'course4_forest'}
TABLES = {1: [0x4AD00]}
BANNER = {0: 789, 1: 791}; POSTS = {'thin': (783, 784), 'wide': (785, 786), 'sign': (787, 788)}
PAGES = (0x200000, 0x280000)
n2 = lambda a, b: math.sqrt((a[0] - b[0]) * (a[0] - b[0]) + (a[2] - b[2]) * (a[2] - b[2]))      # np.linalg.norm((a - b)[[0, 2]])
n3 = lambda v: math.sqrt((v[0] * v[0] + v[2] * v[2]) + v[1] * v[1])                            # np.linalg.norm(v) of a fresh 3-vector: OpenBLAS's (p0 + p2) + p1 (kb 31)
sub = lambda a, b: (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def records(course):
    d = open(os.path.join(WORK, 'tmp', 'm2', 'maincpu.bin'), 'rb').read(); out = []
    for o in TABLES[course]:
        while True:
            a, x, y, z, sec, kind, model, flag = struct.unpack_from('<4f4I', d, o)
            if sec == 99999: break
            out.append(dict(angle=a, pos=(x, y, z), sec=sec, kind=kind, model=model, flag=flag)); o += 32
    return out

def gates(course):
    R = records(course); out = []
    for r in R:
        if r['kind'] != 16: continue
        near = [q for q in R if q['kind'] == 17 and 8.0 <= n2(q['pos'], r['pos']) <= 12.0]
        if r['model'] == 1:                                              # the start / finish line: its two posts are the kind-17 records of model 2 beside it
            two = sorted([q for q in R if q['kind'] == 17 and q['model'] == 2 and n2(q['pos'], r['pos']) < 20.0], key=lambda q: n3(sub(q['pos'], r['pos'])))[:2]
            if len(two) == 2:                                            # the FINISH gate is the 20 m one (object 792): of the two records the one FARTHER from the kind-16 record is the middle of the
                c, o = two[1]['pos'], two[0]['pos']; d = (c[0] - o[0], 0.0, c[2] - o[2]); l = n3(d); d = tuple(v / l for v in d)      # road, the other a post 10 m from it. (First reading, gate between the two records = a post in the middle of the road: user, 2026-10-08.)
                out.append(dict(a=tuple(c[i] - 10.0 * d[i] for i in range(3)), b=tuple(c[i] + 10.0 * d[i] for i in range(3)), model=1, sec=r['sec'], flag=r['flag'], wide=True)); continue
        if near: out.append(dict(a=r['pos'], b=min(near, key=lambda q: abs(n2(q['pos'], r['pos']) - 10.0))['pos'], model=r['model'], sec=r['sec'], flag=r['flag']))
    return out

def build(course=1, posts='thin', finish_posts='sign'):
    import classic_export as ce, classic_tex as ct
    main, poly, polyf, tex16 = ce.load(); tab = ce.table(main); pg = ct.page_bytes(); sheet = ct.sheet_bytes(pg[PAGES[0]], pg[PAGES[1]])      # np.hstack
    base = os.path.join(CLASSIC, 'courses', 'src', DIRS[course]); os.makedirs(os.path.join(base, 'textures'), exist_ok=True)
    C = [tuple(float(v) for v in ln.split(',')) for ln in open(os.path.join(base, 'src_course%d_centreline.csv' % course)) if ln.strip() and not ln.startswith('#')]; n = len(C)      # np.loadtxt
    V = []; VT = []; F = []; mats = {}; info = []
    def put(k, origin, right, fwd, name):
        """object k (local game axes x right, y up, z forward) at `origin` (OBJ axes), x along `right`, z along `fwd` (OBJ axes):
        q = origin + right * x + up * y + fwd * z, numpy's order (up = (0, 1, 0), its zeros multiplied too)"""
        up = (0.0, 1.0, 0.0)
        for p in ce.decode(k, tab, poly, polyf, tex16):
            nm, m = ce.material(p['hdr']); mats[nm] = m; tw, th = (m['w'], m['h']) if m else (1, 1); idx = []
            for (x, y, z), (u, v) in zip(p['verts'], p['uv']):
                q = tuple(((origin[i] + right[i] * x) + up[i] * y) + fwd[i] * z for i in range(3)); V.append(q); VT.append((u / tw, 1.0 - v / th)); idx.append(len(V))
            F.append((nm, name, idx))
    for g in gates(course):
        a = (g['a'][0], g['a'][1], -g['a'][2]); b = (g['b'][0], g['b'][1], -g['b'][2]); mid = tuple((a[i] + b[i]) / 2 for i in range(3))          # OBJ axes: z = -game z
        dm = [n2(c_, mid) for c_ in C]; k = dm.index(min(dm))           # np.argmin(np.linalg.norm(C[:, [0, 2]] - mid[[0, 2]], axis=1)): the first of equals
        f = sub(C[(k + 1) % n], C[(k - 1) % n]); f = (f[0], 0.0, f[2]); l = n3(f); f = tuple(v / l for v in f)
        r = sub(b, a); r = (r[0], 0.0, r[2]); w = n3(r); r = tuple(v / w for v in r)
        if f[2] * r[0] - f[0] * r[2] > 0: a, b, r = b, a, tuple(-v for v in r)      # np.cross(f, r)[1] > 0: r = the driver's right (OBJ axes are right-handed, y up: right = forward x up, so (forward x right).y < 0)
        y0 = float(min(a[1], b[1])); kind = 'finish' if g['model'] == 1 else 'check'; pl, pr = POSTS[finish_posts if kind == 'finish' else posts]
        name = 'gate_%s_%d' % (kind, g['sec'])
        put(pl, a, r, f, name); put(pr, b, r, f, name)
        ext = [q for k_ in (pl, pr) for p_ in ce.decode(k_, tab, poly, polyf, tex16) for q in p_['verts']]; pw = max(abs(q[0]) for q in ext); pd = max(abs(q[2]) for q in ext)      # the posts' half width and half depth
        bo = tuple((mid[0], y0, mid[2])[i] - f[i] * (pd + 0.05) for i in range(3)); bw = w + 2.0 * pw          # the banner hangs IN FRONT of the posts (the side the cars come from) and reaches their outer edges; it used to be fitted BETWEEN them, in their plane (user, 2026-10-08, from the Model 2 picture: "render the banner quad in front of the posts, not between them")
        sb = bw / (20.0 if g.get('wide') else 10.0); put(792 if g.get('wide') else BANNER[g['model']], bo, tuple(v * sb for v in r), f, name)          # the 10 m banner, stretched to the posts' real distance
        if g.get('wide'):                                              # the same gate as the 1995 game shows it before the final lap: the 20 m CHECK POINT banner (object 790) on the same posts
            nm2 = 'gate_finishcp_%d' % g['sec']; put(pl, a, r, f, nm2); put(pr, b, r, f, nm2); put(790, bo, tuple(v * (bw / 20.0) for v in r), f, nm2)
        info.append(dict(gate=name, section=g['sec'], centre=[round(float(x), 2) for x in mid], width=round(w, 2), centre_line_cell=k, off_centre_line=round(n2(C[k], mid), 2)))
    for nm, m in mats.items():
        if m: ct.to_image(ct.tile_bytes(sheet, 2048, m, clip=True), m['alpha'], m).save(os.path.join(base, 'textures', nm + '.png'))      # sheet[y:y + h, x:x + w]
    out = os.path.join(base, 'src_course%d_gates.obj' % course)
    with open(out, 'w') as fo:
        fo.write('# SEGA Rally Championship: checkpoint / finish gates of the course (gates1995.py), ROM objects placed by the trackside table. Y up, Z = -gameZ\n')
        fo.write('mtllib src_course%d_gates.mtl\n' % course); [fo.write('v %.4f %.4f %.4f\n' % v) for v in V]; [fo.write('vt %.5f %.5f\n' % t) for t in VT]; cur = None; sec = None
        for nm, name, idx in F:
            if name != sec: fo.write('o %s\n' % name); sec = name; cur = None
            if nm != cur: fo.write('usemtl %s\n' % nm); cur = nm
            fo.write('f ' + ' '.join('%d/%d' % (i, i) for i in idx) + '\n')
    with open(out[:-4] + '.mtl', 'w') as fm:
        for nm, m in mats.items():
            fm.write('newmtl %s\nKd 0.8 0.8 0.8\n' % nm)
            if m: fm.write('map_Kd textures/%s.png\n' % nm + ('map_d textures/%s.png\n' % nm if m['alpha'] else ''))
    return out, info, mats

def faces(cfg, rd):
    import build_classic as BC
    p = os.path.join(CLASSIC, 'courses', cfg['game'], cfg.get('gameplay', ''), 'src_course%s_gates.obj' % cfg['course'])
    if not os.path.exists(p): return []
    V = []; VT = []; out = []; mat = None; sec = 'gate'; zs = BC.ZS
    for ln in open(p):
        if ln.startswith('v '): x, y, z = map(float, ln.split()[1:4]); V.append((x + rd['ox'], y, zs * z + rd['oz']))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('o '): sec = ln.split()[1]
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]; out.append((mat, sec, [V[a] for a, b in ix][::int(zs)], [VT[b] for a, b in ix][::int(zs)]))
    return out

if __name__ == '__main__':
    c = int(sys.argv[1]) if len(sys.argv) > 1 else 1; out, info, mats = build(c)
    print('written', out); [print('  ', i) for i in info]; print('   tiles:', sorted(mats))


def banner_in_front(faces, clearance=0.05, log=print):
    """Place the Mountain lap banner ahead of the FINAL resolved sign-post surfaces.

    Overlay resolution can push the textured post skins beyond their raw ROM box.
    Measure after resolution, move every panel/letter together, keep posts and UVs.
    This is opted into by the Mountain recipe, for the ROM sign-post gate only.
    """
    post_tiles = {'col_047', 'tex_s0_x1536_y0064_256x64_c059_t'}
    posts = [f for f in faces if str(f[0]).split('|')[0] in post_tiles]
    panels = [f for f in faces if str(f[0]).split('|')[0] not in post_tiles]
    if not posts or not panels: raise ValueError('finish banner: expected sign posts and panels')
    pp = [p for f in posts for p in f[2]]; bp = [p for f in panels for p in f[2]]
    a, b = max(((a,b) for a in bp for b in bp), key=lambda ab: (ab[1][0]-ab[0][0])**2+(ab[1][2]-ab[0][2])**2)
    dx,dz=b[0]-a[0],b[2]-a[2]; length=math.hypot(dx,dz)
    nx,nz=-dz/length,dx/length
    proj=lambda p: nx*p[0]+nz*p[2]
    # The original panel plane is already on the approach side of the post centres.
    if sum(map(proj,bp))/len(bp)<sum(map(proj,pp))/len(pp): nx,nz=-nx,-nz
    gap=min(map(proj,bp))-max(map(proj,pp)); move=max(0.0,float(clearance)-gap)
    if move>1.0: raise ValueError('finish banner unexpectedly far behind posts')
    out=[]
    for f in faces:
        if str(f[0]).split('|')[0] in post_tiles: out.append(f)
        else: out.append(tuple(f[:2])+([(p[0]+nx*move,p[1],p[2]+nz*move) for p in f[2]],)+tuple(f[3:]))
    log('       finish banner clearance: %.4f m -> %.4f m; translated %.4f m toward approach' % (gap,gap+move,move))
    return out
