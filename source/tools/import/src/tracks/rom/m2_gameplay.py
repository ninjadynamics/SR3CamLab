"""SEGA Rally Championship: gameplay.json + top-down plot per course, from the tables documented in ../src/gameplay.md.
All positions in the axes of the OBJ exports: (x, y, -gameZ).
    python m2_gameplay.py     -> <classic>/courses/src/course<N>_<name>/gameplay.json + gameplay_plot.png (needs src_all.py and m2_collision.py first)
Without numpy since 2026-10-15 (kb 31): the tables are read with struct, the lengths summed as numpy summed them (the lap pairwise, the
distances one after the other); the files are byte for byte the numpy version's."""
import struct, json, glob, os, math, sys, itertools
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'core')); import common   # tools/import/settings.json
from PIL import Image, ImageDraw
import m2_game as G, m2_surface as S
PROG = open(G.PROG, 'rb').read(); MAIN = open(G.MAIN, 'rb').read()
def pwsum(v):
    """np.sum of a 1-D float64 array: numpy's pairwise sum (rtbake/rt_bake_game5.py pwsum)"""
    n = len(v)
    if n < 8:
        s = 0.0
        for x in v: s += x
        return s
    if n <= 128:
        r = list(v[:8]); e = n - n % 8
        for i in range(8, e, 8):
            for j in range(8): r[j] += v[i + j]
        s = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
        for x in v[e:]: s += x
        return s
    h = n // 2; h -= h % 8
    return pwsum(v[:h]) + pwsum(v[h:])
GAME_ID = {2: 0, 4: 1, 1: 2, 3: 3}                       # my course number (collision block order) -> the game's course id
NAME = {1: 'mountain', 2: 'desert', 3: 'lakeside', 4: 'forest'}
AIREC = {0: 0x8012f0, 1: 0x804bc0, 2: 0x8025e0, 3: 0x8038d0}
ICON = {0: 'easy left', 1: 'easy right', 15: 'medium left', 16: 'medium right', 19: 'left (tight)', 20: 'right (tight)', 21: 'right', 10: 'hard left', 11: 'hard right',
        8: 'hairpin left', 9: 'hairpin right', 6: 'long hairpin right', 7: 'straight-on call (crest / caution?)', 4: 'slight left?', 26: 'slight left?'}
SURF = {0: 'tarmac', 1: 'tarmac (second kind: Mountain plain asphalt)', 2: 'gravel / light dirt', 3: 'brown dirt / mud', 4: 'water crossing (splash)', 6: 'verge: grass or rough ground beside the road',
        8: 'tarmac under cover (Mountain)', 9: 'tunnel floor (Forest)'}
SCOL = {0: (120, 130, 140), 1: (90, 100, 115), 2: (215, 195, 140), 3: (150, 95, 60), 4: (60, 120, 230), 6: (90, 160, 70), 8: (60, 60, 90), 9: (230, 200, 90)}
def fl(o, n): return struct.unpack_from('<%df' % n, PROG, o)
def u32(o, n): return struct.unpack_from('<%dI' % n, PROG, o)
def obj(p): return [round(float(p[0]), 3), round(float(p[1]), 3), round(-float(p[2]), 3)]
for c in (1, 2, 3, 4):
    gid = GAME_ID[c]; gate, quad, dirs = G.sections(c); n = len(gate)
    ai = [struct.unpack_from('<3f', MAIN, AIREC[gid] + 16 * i) for i in range(n)]; flag = [MAIN[AIREC[gid] + 16 * i + 12] for i in range(n)]      # 16-byte records: x y z (f32), flag
    seg = [math.sqrt(((b[0] - a[0]) * (b[0] - a[0]) + (b[1] - a[1]) * (b[1] - a[1])) + (b[2] - a[2]) * (b[2] - a[2])) for a, b in zip(ai, ai[1:] + ai[:1])]      # np.linalg.norm(np.diff(np.vstack([ai, ai[:1]]), axis=0), axis=1)
    dist = [0.0] + list(itertools.accumulate(seg))[:-1]; lap = pwsum(seg)      # np.concatenate([[0], np.cumsum(seg)[:-1]]), seg.sum()
    g_ = fl(0x3db20 + 48 * gid, 12); grid = [g_[3 * k:3 * k + 3] for k in range(4)]; rot = fl(0x3dc70 + 12 * gid, 3)
    splits = [s for s in u32(0x1e790 + 32 * gid, 8) if s < n]; events = [s for s in u32(0x46010 + 16 * gid, 4) if s < n]
    notes = G.notes(gid); hd = dirs[0]
    out = dict(game='SEGA Rally Championship (Model 2A)', course=NAME[c], export_course_number=c, game_course_id=gid, axes='x, y, -gameZ (same as the OBJ exports); angles: heading vector in these axes',
        lap_length_m=round(lap, 1), direction=dict(note='sections are numbered in driving order; the game counts progress in sections (0..299)', start_heading=[round(float(hd[0]), 4), 0.0, round(-float(hd[1]), 4)]),
        start=dict(grid=[obj(p) for p in grid], rotation_xyz_radians_game=[round(float(r), 4) for r in rot], note='four grid slots from the program table; which slot is the player is not known'),
        checkpoints=[dict(section=s, position=obj(ai[s]), distance_m=round(float(dist[s]), 1)) for s in splits],
        checkpoints_note='sections at which the game stores the running time and shows it for 3 s (split points). Time awarded is not stored in this table',
        event_sections=[dict(section=s, position=obj(ai[s])) for s in events],
        surfaces=dict(legend={str(k): v for k, v in SURF.items()}, note='collision polygon attribute bits 16-19; bit 23 = side polygon (bank / wall beside the road). See src_course%d_collision.obj groups' % c),
        pace_notes=[dict(section=s, distance_m=round(float(dist[s]), 1), position=obj(ai[s]), voice=a, icon=b, call=ICON.get(b, 'unknown')) for s, a, b in notes],
        ai_line=[dict(section=i, position=obj(ai[i]), distance_m=round(float(dist[i]), 1), speed_zone=int(flag[i] >> 4), variant=int(flag[i] & 15)) for i in range(n)],
        sections=[dict(left_right=[obj(gate[i][0]), obj(gate[i][1])], heading=[round(float(dirs[i][0]), 4), round(-float(dirs[i][1]), 4)]) for i in range(n)])
    d = glob.glob(os.path.join(common.CLASSIC, 'courses', 'src', 'course%d_*' % c))[0]; json.dump(out, open(os.path.join(d, 'gameplay.json'), 'w'), indent=1)
    # plot (north = +gameZ up, i.e. the true plan; x right)
    coll = S.load_coll(os.path.join(common.CLASSIC, 'obj', 'src_course%d_collision.obj' % c)); allp = [q for a, p in coll for q in p]      # np.vstack(...).min(0) / .max(0)
    mn = [min(q[k] for q in allp) for k in range(3)]; mx = [max(q[k] for q in allp) for k in range(3)]
    W = 1600; sc = (W - 120) / max(mx[0] - mn[0], mx[2] - mn[2]); H = int((mx[2] - mn[2]) * sc) + 160
    def XY(p): return (60 + (p[0] - mn[0]) * sc, 60 + (p[2] - mn[2]) * sc)             # OBJ z = -gameZ grows downwards on the page -> gameZ up
    im = Image.new('RGB', (W, H), (245, 245, 240)); dr = ImageDraw.Draw(im)
    for a, p in coll:
        if a & 0x800000: continue
        dr.polygon([XY(q) for q in p], fill=SCOL.get((a >> 16) & 15, (255, 0, 255)))
    aio = [obj(p) for p in ai]; dr.line([XY(p) for p in aio] + [XY(aio[0])], fill=(40, 40, 40), width=1)
    for s in splits: x, y = XY(aio[s]); dr.rectangle([x - 7, y - 7, x + 7, y + 7], outline=(200, 0, 0), width=3); dr.text((x + 10, y - 16), 'CP s%d' % s, fill=(200, 0, 0))
    for s, a, b in notes: x, y = XY(aio[s]); dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(0, 0, 0)); dr.text((x + 6, y + 2), '%d: %s' % (s, ICON.get(b, '?').split(' (')[0]), fill=(0, 0, 0))
    for p in grid: x, y = XY(obj(p)); dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(255, 0, 255))
    x, y = XY(aio[0]); x2, y2 = XY(aio[4]); dr.line([x, y, x2, y2], fill=(255, 0, 255), width=4); dr.text((x + 8, y + 8), 'START (grid magenta, arrow = direction)', fill=(160, 0, 160))
    for k, (t, nm) in enumerate(SURF.items()): dr.rectangle([10, H - 20 - 14 * (len(SURF) - k), 22, H - 10 - 14 * (len(SURF) - k)], fill=SCOL[t]); dr.text((28, H - 22 - 14 * (len(SURF) - k)), '%d %s' % (t, nm), fill=(0, 0, 0))
    dr.text((10, 10), 'SEGA Rally Championship - %s (game course id %d): surfaces, start, split points (CP), pace notes. Plan view, game +Z up.' % (NAME[c], gid), fill=(0, 0, 0))
    im.save(os.path.join(d, 'gameplay_plot.png'))
    print(NAME[c], 'id', gid, 'lap %.0f m' % lap, 'grid0', obj(grid[0]), 'splits', splits, 'events', events, 'notes', len(notes), 'speed zones', sorted(set(int(x) >> 4 for x in flag)))
