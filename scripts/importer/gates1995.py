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
Wired into the importer 2026-10-08 (import_classic, course JSON "gates": "1995" = default; "gantries" = the old stand-ins)."""
import os, sys, struct, json
import numpy as np
from common import *

DIRS = {1: 'course1_mountain', 2: 'course2_desert', 3: 'course3_lakeside', 4: 'course4_forest'}
TABLES = {1: [0x4AD00]}
BANNER = {0: 789, 1: 791}; POSTS = {'thin': (783, 784), 'wide': (785, 786), 'sign': (787, 788)}
PAGES = (0x200000, 0x280000)

def records(course):
    d = open(os.path.join(WORK, 'tmp', 'm2', 'maincpu.bin'), 'rb').read(); out = []
    for o in TABLES[course]:
        while True:
            a, x, y, z, sec, kind, model, flag = struct.unpack_from('<4f4I', d, o)
            if sec == 99999: break
            out.append(dict(angle=a, pos=np.array([x, y, z]), sec=sec, kind=kind, model=model, flag=flag)); o += 32
    return out

def gates(course):
    R = records(course); out = []
    for r in R:
        if r['kind'] != 16: continue
        near = [q for q in R if q['kind'] == 17 and 8.0 <= np.linalg.norm((q['pos'] - r['pos'])[[0, 2]]) <= 12.0]
        if r['model'] == 1:                                              # the start / finish line: its two posts are the kind-17 records of model 2 beside it
            two = sorted([q for q in R if q['kind'] == 17 and q['model'] == 2 and np.linalg.norm((q['pos'] - r['pos'])[[0, 2]]) < 20.0], key=lambda q: np.linalg.norm(q['pos'] - r['pos']))[:2]
            if len(two) == 2:                                            # the FINISH gate is the 20 m one (object 792): of the two records the one FARTHER from the kind-16 record is the middle of the
                c, o = two[1]['pos'], two[0]['pos']; d = c - o; d[1] = 0.0; d = d / np.linalg.norm(d)      # road, the other a post 10 m from it. (First reading, gate between the two records = a post in the middle of the road: user, 2026-10-08.)
                out.append(dict(a=c - 10.0 * d, b=c + 10.0 * d, model=1, sec=r['sec'], flag=r['flag'], wide=True)); continue
        if near: out.append(dict(a=r['pos'], b=min(near, key=lambda q: abs(np.linalg.norm((q['pos'] - r['pos'])[[0, 2]]) - 10.0))['pos'], model=r['model'], sec=r['sec'], flag=r['flag']))
    return out

def build(course=1, posts='thin', finish_posts='sign'):
    import classic_export as ce, classic_tex as ct
    main, poly, polyf, tex16 = ce.load(); tab = ce.table(main); pg = ct.all_pages(); sheet = np.hstack([pg[PAGES[0]], pg[PAGES[1]]])
    base = os.path.join(os.path.dirname(WORK), 'classic', 'courses', 'src', DIRS[course]); os.makedirs(os.path.join(base, 'textures'), exist_ok=True)
    C = np.loadtxt(os.path.join(base, 'src_course%d_centreline.csv' % course), delimiter=',', comments='#'); n = len(C)
    V = []; VT = []; F = []; mats = {}; info = []
    def put(k, origin, right, fwd, name):
        """object k (local game axes x right, y up, z forward) at `origin` (OBJ axes), x along `right`, z along `fwd` (OBJ axes)"""
        up = np.array([0.0, 1.0, 0.0])
        for p in ce.decode(k, tab, poly, polyf, tex16):
            nm, m = ce.material(p['hdr']); mats[nm] = m; tw, th = (m['w'], m['h']) if m else (1, 1); idx = []
            for (x, y, z), (u, v) in zip(p['verts'], p['uv']):
                q = origin + right * x + up * y + fwd * z; V.append(tuple(q)); VT.append((u / tw, 1.0 - v / th)); idx.append(len(V))
            F.append((nm, name, idx))
    for g in gates(course):
        a = np.array([g['a'][0], g['a'][1], -g['a'][2]]); b = np.array([g['b'][0], g['b'][1], -g['b'][2]]); mid = (a + b) / 2          # OBJ axes: z = -game z
        k = int(np.argmin(np.linalg.norm(C[:, [0, 2]] - mid[[0, 2]], axis=1))); f = C[(k + 1) % n] - C[(k - 1) % n]; f[1] = 0.0; f /= np.linalg.norm(f)
        r = b - a; r[1] = 0.0; w = float(np.linalg.norm(r)); r /= w
        if np.cross(f, r)[1] > 0: a, b, r = b, a, -r                      # r = the driver's right (OBJ axes are right-handed, y up: right = forward x up, so (forward x right).y < 0)
        y0 = float(min(a[1], b[1])); kind = 'finish' if g['model'] == 1 else 'check'; pl, pr = POSTS[finish_posts if kind == 'finish' else posts]
        name = 'gate_%s_%d' % (kind, g['sec'])
        put(pl, np.array([a[0], a[1], a[2]]), r, f, name); put(pr, np.array([b[0], b[1], b[2]]), r, f, name)
        ext = np.array([q for k_ in (pl, pr) for p_ in ce.decode(k_, tab, poly, polyf, tex16) for q in p_['verts']], float); pw = float(np.abs(ext[:, 0]).max()); pd = float(np.abs(ext[:, 2]).max())      # the posts' half width and half depth
        bo = np.array([mid[0], y0, mid[2]]) - f * (pd + 0.05); bw = w + 2.0 * pw          # the banner hangs IN FRONT of the posts (the side the cars come from) and reaches their outer edges; it used to be fitted BETWEEN them, in their plane (user, 2026-10-08, from the Model 2 picture: "render the banner quad in front of the posts, not between them")
        put(792 if g.get('wide') else BANNER[g['model']], bo, r * (bw / (20.0 if g.get('wide') else 10.0)), f, name)          # the 10 m banner, stretched to the posts' real distance
        if g.get('wide'):                                              # the same gate as the 1995 game shows it before the final lap: the 20 m CHECK POINT banner (object 790) on the same posts
            n2 = 'gate_finishcp_%d' % g['sec']; put(pl, np.array([a[0], a[1], a[2]]), r, f, n2); put(pr, np.array([b[0], b[1], b[2]]), r, f, n2); put(790, bo, r * (bw / 20.0), f, n2)
        info.append(dict(gate=name, section=g['sec'], centre=[round(float(x), 2) for x in mid], width=round(w, 2), centre_line_cell=k, off_centre_line=round(float(np.linalg.norm(C[k][[0, 2]] - mid[[0, 2]])), 2)))
    for nm, m in mats.items():
        if m: ct.to_image(sheet[m['y']:m['y'] + m['h'], m['x']:m['x'] + m['w']], m['alpha'], m).save(os.path.join(base, 'textures', nm + '.png'))
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
    p = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'src_course%s_gates.obj' % cfg['course'])
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
