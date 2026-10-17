"""SEGA Rally 2 gameplay data -> ../course<N>/gameplay.json, sr2_course<N>_collision.obj (+ .mtl)
N = course table index 0..4 (= course id - 2).  Axes of every position written: x, y, -gameZ (as the OBJ exports)."""
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2course import *
from geom import *
from m3 import road_blocks, course_line

MAIN_STAGE = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}             # course table index -> stage used by the championship / course select
ALT_STAGES = {2: [0], 3: [6, 7]}
STAGE_NAME = [cstr(u32(0xF27B8 + 4 * i)).strip() for i in range(8)]
ARCADE = {0: 'FOREST (unused in the arcade game: not in the championship, not selectable, no pace notes)', 1: 'MOUNTAIN', 2: 'DESERT', 3: 'RIVIERA', 4: 'SNOWY (internal name SWEDISH)'}
MENU = [u32(0xF1F20 + 4 * i) for i in range(4)]         # course select cursor -> stage
CHAMP = [u32(0xED740 + 4 * i) for i in range(4)]        # championship round -> stage (via round table: round r has stage = first word)
GTYPE = {0: 'championship (game type 0)', 1: 'championship, long setting (game type 1)', 2: 'practice (game type 2)', 3: 'practice, long setting (game type 3)'}
COND = {-1: 'always', 1: 'first lap only', 2: 'every lap except the last', 3: 'praise point (crowd cheer + "excellent/outstanding/great" by score)', 4: 'crowd cheer point', 5: 'last lap only: goal crowd cheer'}
SURF_COL = {0: (0.35, 0.35, 0.38), 1: (0.5, 0.5, 0.55), 2: (0.76, 0.62, 0.38), 3: (0.62, 0.5, 0.3), 4: (0.2, 0.45, 0.9), 5: (0.3, 0.6, 0.95), 6: (0.5, 0.33, 0.18), 7: (0.4, 0.26, 0.14),
            8: (0.2, 0.2, 0.2), 9: (0.28, 0.28, 0.28), 10: (0.93, 0.93, 0.97), 11: (0.8, 0.84, 0.92), 12: (0.55, 0.75, 0.85), 13: (0.45, 0.65, 0.8)}

def O3(p): return [round(float(p[0]), 3), round(float(p[1]), 3), round(-float(p[2]), 3)]

def time_tables(stage_no):
    out = {}
    for t in range(4):
        a = 0xE8348 + 16 * t; nd, ns, K, p = u32(a), u32(a + 4), u32(a + 8), u32(a + 12)
        laps = u32(0xE8388 + 32 * t + 4 * stage_no); rows = {}
        for d in range(nd):
            v = [s32(p + 4 * ((d * ns + stage_no) * K + i)) for i in range(K)]
            rows['difficulty_%d' % d] = v
        out[GTYPE[t]] = dict(laps=laps, entries_per_stage=K, table_addr='0x%X' % p, frames=rows)
    return out

def time_summary(tt, ncp):
    """seconds for the default-looking middle difficulty of game type 0"""
    out = {}
    for name, T in tt.items():
        for d, v in T['frames'].items():
            vals = []
            for x in v:
                if x < 0: break
                vals.append(round(x / 60.0, 2))
            out.setdefault(name, {})[d] = dict(initial_s=vals[0] if vals else None, added_at_each_checkpoint_passage_s=vals[1:])
    return out

def export(k):
    sno = MAIN_STAGE[k]; S = sections(sno); st = S['stage']; n = S['n']
    entry, cen, ex, dist, L = centreline(S); q = S['quads']
    R = road_blocks(k); CL = course_line(k)
    out_dir = OUT + 'course%d/' % k; os.makedirs(out_dir, exist_ok=True)
    def ypos(sec, x, z):
        g = ground(S, sec, x, z) or ground(S, (sec - 1) % n, x, z) or ground(S, (sec + 1) % n, x, z) or ground(S, sec, x, z, walls=True)
        return g
    # per-section info
    secs = []; surf_tot = {}
    for i in range(n):
        area = {}
        for p in S['lists'][i]:
            a = attr(S, p); T = tri(S, p); c = T.mean(axis=0)
            # only polygons whose centre lies inside this section's quad (lists overlap neighbours)
            if not inside(q[i], c[0], c[2]): continue
            ar = 0.5 * abs((T[1, 0] - T[0, 0]) * (T[2, 2] - T[0, 2]) - (T[2, 0] - T[0, 0]) * (T[1, 2] - T[0, 2]))
            key = 'WALL' if a & 0x8000 else SURF[a & 0xF]; area[key] = area.get(key, 0) + ar
        for kk, v in area.items(): surf_tot[kk] = surf_tot.get(kk, 0) + v
        rc = road_centre(S, i); g = ypos(i, rc[0], rc[2]) if rc is not None else None
        em = entry[i]; ge = ypos(i, em[0], em[1])
        drv = {kk: v for kk, v in area.items() if kk != 'WALL'}
        secs.append(dict(index=i, distance_m=round(float(dist[i]), 1),
                         entry_left=[round(float(q[i, 0, 0]), 2), round(-float(q[i, 0, 1]), 2)], entry_right=[round(float(q[i, 3, 0]), 2), round(-float(q[i, 3, 1]), 2)],
                         centre=O3((R[i, 0], R[i, 1], R[i, 2])), road_centre=O3(rc) if rc is not None else None,
                         surface_main=max(drv, key=drv.get) if drv else None, surface_area_m2={kk: round(v, 1) for kk, v in sorted(area.items())}))
    def secpos(i):
        s = secs[i % n]; return s['road_centre'] or s['centre']
    # start (round record = 0xE8714 + 124*round; championship round = stage, practice round = stage + 6)
    import math
    def slots(rnd):
        out = []
        for slot in range(5):
            a = 0xE8714 + 124 * rnd + 12 + 20 * slot; h = s16(a + 12); ang = h * math.pi / 32768.0
            out.append(dict(slot=slot, position=O3((f32(a), f32(a + 4), f32(a + 8))), heading_s16=h, heading=[round(-math.sin(ang), 4) + 0.0, 0.0, round(-math.cos(ang), 4) + 0.0], section_hint=s32(a + 16)))
        return out
    grid = slots(sno); sp = (f32(0xE8714 + 124 * sno + 12), f32(0xE8714 + 124 * sno + 16), f32(0xE8714 + 124 * sno + 20))
    ssec = [i for i in range(n) if inside(q[i], sp[0], sp[2])]
    g0 = None
    for i in ssec + [0, n - 1]:
        g0 = g0 or ground(S, i, sp[0], sp[2])
    start = dict(position=grid[0]['position'], ground_y=round(g0[0], 3) if g0 else None, ground_surface=SURF[g0[1]] if g0 else None, heading=grid[0]['heading'], heading_s16=grid[0]['heading_s16'],
                 section=ssec[-1] if ssec else None, distance_m=secs[ssec[-1]]['distance_m'] if ssec else None,
                 heading_note='s16 angle: 0 = game +Z (OBJ -Z), 0xC000 (-16384) = game +X (matches the course direction at the Riviera start: VERIFIED by geometry). The car is dropped from 1 m above the ground.',
                 source='round table 0xE8714 (124 bytes per round; rounds 0-5 = stages 0-5): slot 0 at +12 = position, s16 heading at +24, s32 at +28 (181 on Riviera = starting section, 0 elsewhere). VERIFIED in code 0x31F80 (player car init)',
                 slots_championship_round=grid, slots_practice_round=slots(sno + 6),
                 slots_note='slot 0 = single player. Slots 1-4 are taken by linked cabinets (code 0x31FEC: slot = link id): side by side, about -2, +2, -6, +6 m (practice rounds -1.5, +1.5, -5, +5).',
                 lap_line=dict(section=0, left=secs[0]['entry_left'], right=secs[0]['entry_right'], note='lap / finish line = entry edge of section 0 (the section counter wraps 255 -> 0 there); game z of its middle = %.2f' % entry[0][1]),
                 race_direction='increasing section index (= road block index)')
    # checkpoints
    cpa = 0xE5828 + 20 * sno; ncp = u32(cpa); cps = [s32(cpa + 4 + 4 * i) for i in range(ncp)]
    spa = 0xE5708 + 36 * sno; nsp = u32(spa); sps = [s32(spa + 4 + 4 * i) for i in range(nsp)]
    tt = time_tables(sno)
    def cp_entry(sec, idx, total):
        s = secs[sec % n]; last = (sec % n) == 0
        return dict(index=idx, section=sec, is_lap_line=last, distance_m=round(L, 1) if last else s['distance_m'], position=secpos(sec), gate_left=s['entry_left'], gate_right=s['entry_right'])
    checkpoints = [cp_entry(c, i, ncp) for i, c in enumerate(cps)]
    splits = [dict(index=i, section=c, distance_m=round(L, 1) if c % n == 0 else secs[c % n]['distance_m'], position=secpos(c)) for i, c in enumerate(sps)]
    # pace notes
    notes = []; events = []
    for N in pace_notes(sno):
        s = secs[N['section']]
        base = dict(section=N['section'], distance_m=s['distance_m'], position=secpos(N['section']), condition=COND.get(N['cond'], str(N['cond'])), condition_code=N['cond'], rom_addr='0x%X' % N['addr'])
        if N['req'] < 0:
            events.append(base); continue
        dreq = s32(0xF160C + 8 * N['dist']) if N['dist'] >= 0 else -1; delay = s32(0xF160C + 8 * N['dist'] + 4) if N['dist'] >= 0 else 0
        dname = REQ[dreq] if dreq >= 0 else None; name = REQ[N['req']]
        dm = int(dname[3:]) if dname else None
        tgt = None
        if dm is not None:
            dd = (s['distance_m'] + dm) % L; tgt = int(np.searchsorted(dist, dd, side='right') - 1)
        base.update(distance_call_request=dreq, distance_call=dname, distance_call_text=SPOKEN.get(dname, None) if dname else None, delay_frames_before_note=delay,
                    request=N['req'], vo_name=name, text=SPOKEN.get(name), spoken=((SPOKEN.get(dname, '') + ', ') if dname else '') + (SPOKEN.get(name) or ''),
                    icon1=N['icon1'], icon2=N['icon2'], announced_distance_m=dm, target_section=tgt, target_position=secpos(tgt) if tgt is not None else None)
        notes.append(base)
    # zones (car reflection environment per section range)
    zones = []; za = 0x12D8C8 + 640 * (st['course_id'] - 1); prev = 0
    for i in range(32):
        e = s32(za + 20 * i)
        if e == 0: break
        zones.append(dict(sections=[prev, min(e, n) - 1], body_env_tex='0x%08X' % u32(za + 20 * i + 4), window_env_tex='0x%08X' % u32(za + 20 * i + 8), f1=round(f32(za + 20 * i + 12), 3), f2=round(f32(za + 20 * i + 16), 3))); prev = e
    # rival (computer car) line: pointer table 0x1353DC[stage] -> banked nodes {x, y, z, heading rad}, count 0xEE100[stage]
    rp = u32(0x1353DC + 4 * sno); rn = u32(0xEE100 + 4 * sno); bk = S['bank']
    RN = bk.words(rp, rn * 4, '>f4').reshape(rn, 4).astype(float)
    rseg = np.linalg.norm(np.diff(RN[:, :3], axis=0), axis=1); rd = np.concatenate([[0], np.cumsum(rseg)])
    rivals = []
    for i in range(16):
        ra = 0xEE140 + 256 * sno + 16 * i
        if u32(ra) == 0: break
        rivals.append(dict(index=i, speed_value=round(f32(ra), 2), f1=round(f32(ra + 4), 3), f2=round(f32(ra + 8), 3), start_node=s32(ra + 12)))
    rival_line = dict(note='line followed by the computer cars (code 0x325AC / 0x3298C). Nodes about 10 m apart starting just ahead of the start position; y is about 0.5-0.65 m above the road (car origin height), heading_rad = -atan2(dx, dz) in game axes (0 = +Z, -pi/2 = +X). Looks like a recorded drive. Not closed: the last node is short of / past the first by a few metres.',
                      pointer='0x%08X (bank %d)' % (rp, st['bank']), node_count=rn, length_m=round(float(rd[-1]), 1), cars_in_round=u32(0xE8714 + 124 * sno + 112),
                      rival_table='0x%X (16 bytes per car: float speed value, 2 floats, s32 start node)' % (0xEE140 + 256 * sno), rivals=rivals,
                      nodes=[dict(index=i, position=O3(RN[i, :3]), heading_rad=round(float(RN[i, 3]), 4), distance_m=round(float(rd[i]), 1)) for i in range(rn)])
    if k == 0: rival_line['note'] = 'WARNING: for FOREST the table points at a byte-identical copy of the MOUNTAIN line (342 nodes, 3410 m; this course is 4253 m): placeholder data, it does not follow this course. ' + rival_line['note']
    if k == 3: rival_line['note'] += ' On Riviera the line (1638 m + 20 m gap) is shorter than lap_length_m (1905 m): the section centres swing through the wide paddock sections 120-128, so lap_length_m overestimates there.'
    alt = {}
    for a in ALT_STAGES.get(k, []):
        ca = 0xE5828 + 20 * a; sa = 0xE5708 + 36 * a; As = stage(a)
        alt['stage_%d_%s' % (a, STAGE_NAME[a])] = dict(checkpoint_sections=[s32(ca + 4 + 4 * i) for i in range(u32(ca))], split_sections=[s32(sa + 4 + 4 * i) for i in range(u32(sa))],
            section_table='0x%08X (bank %d)' % (As['sect'], As['bank']), same_collision_as_main=As['sect'] == st['sect'], pace_note_table='0x%X' % As['notes'], time_tables=time_summary(time_tables(a), 0),
            used_by='round table entries with stage = %d: rounds %s' % (a, [r for r in range(20) if u32(0xE8714 + 124 * r) == a]))
    J = dict(game='SEGA Rally 2 (arcade, Model 3 Step 2.0, srally2)', course_table_index=k, course_id=st['course_id'], stage=sno, internal_name=STAGE_NAME[sno], course=ARCADE[k],
             axes='x, y, -gameZ (same as the OBJ exports); plan positions are [x, -gameZ]', units='metres; times in frames (1/60 s) unless a key ends in _s',
             course_select=dict(menu_cursor_to_stage=MENU, menu_position=MENU.index(sno) if sno in MENU else None, championship_order_stages=CHAMP, championship_position=CHAMP.index(sno) if sno in CHAMP else None,
                                note='stage -> course id: stage table 0xE8408 + 96*stage, word +4; course table index = course id - 2. VERIFIED in code (0x46AEC menu table 0xF1F20, 0x2C8A4 round sequence 0xED740, 0x2BB08 round table 0xE8714, 0x14AF4/0x14D5C block tables)'),
             lap_length_m=round(L, 1), sections=dict(count=n, note='section i = road block i (block position = centre of the section quad: VERIFIED, 256 of 256 identical). The player\'s current section is the unit of progress for laps, checkpoints, split points and pace notes.'),
             start=start, laps={GTYPE[t]: u32(0xE8388 + 32 * t + 4 * sno) for t in range(4)},
             checkpoints=dict(note='time-extension points: SE_CHECK1 + VO_CHECKPOINT ("checkpoint") and time added (code 0x3E130). The last entry (section 256 = 0 of the next lap) is the lap line; on the last lap it is the finish.',
                              table='0x%X' % cpa, list=checkpoints, times_s=time_summary(tt, ncp), times_raw=tt,
                              times_note='entry 0 = time given at the start of the stage, entry k = time added at the k-th checkpoint passage (counting on through the laps); -1 = nothing. The remaining time runs down 1 per frame, warning beep each second under 300 (= 5 s): units are 1/60 s (VERIFIED code 0x3EE6C). Difficulty index 0..4 = RAM 0x22CF18 (operator setting; which index is the factory default was not traced).'),
             split_points=dict(note='sector timing points (time stored and compared with the record: code 0x3DFDC); no time is added', table='0x%X' % spa, list=splits),
             pace_notes=dict(note='co-driver calls. Trigger: the player enters `section` (code 0x3E68C compares RAM 0x22CFB8 with the next note). Sequence: distance call (VO_xx) -> wait delay_frames_before_note -> the note. icon1/icon2 = arrow/hazard icon numbers shown on screen. target_* = where the announced distance lands along the course (derived).',
                             table='0x%X' % st['notes'], record='24 bytes: s32 section, s32 condition, s32 distance-call index (table 0xF160C {request, delay}), s32 icon1, s32 icon2, s32 VO request', list=notes),
             crowd_and_praise_points=dict(note='entries of the pace-note table that speak no note (request = -1)', list=events),
             surfaces=dict(note='collision polygon attribute (304-byte polygon record, word +296): low 4 bits = surface type, bit 15 = wall / blocked zone, bits 16+ = polygon number. Names from the ROAD STATUS tuning menu (0xF4FD4...), index = position in the grip table.',
                           type_names=SURF, area_m2={kk: round(v) for kk, v in sorted(surf_tot.items())}, per_section=[dict(section=s['index'], main=s['surface_main'], area_m2=s['surface_area_m2']) for s in secs],
                           collision_obj='sr2_course%d_collision.obj' % k),
             section_list=[{kk: s[kk] for kk in ('index', 'distance_m', 'entry_left', 'entry_right', 'centre', 'road_centre')} for s in secs],
             debug_course_line=dict(note='table 0xE2BFC + 8*course id {count-1, pointer}: path followed by the auto-run "car" of the built-in course-object editor (code 0x5D230 / 0x5C538). Not used by the race code (only reference).',
                                    addr='0x%X' % u32(LINE_TAB_ADDR + 8 * k + 4), points=[O3(p) for p in CL]),
             rival_line=rival_line,
             environment=dict(fog_colour_rgb='0x%06X' % st['colour'], fog_or_far_distance=st['fog'], light_dir_game=[round(x, 4) for x in st['light']], sky_dome_model_index=st['w2'], sky_dome_vrom_addr='0x%06X' % u32(0xA4BA8 + 16 * st['w2']), sky_obj='sr2_course%d_sky.obj' % k, start_banner_model_index=st['w3'], goal_banner_model_index=st['w4'], banners_obj='sr2_course%d_banners.obj' % k, model_table='0xA4BA8 (16 bytes per entry, word 0 = VROM address in words)', bank=st['bank'],
                              stage_record='0x%X' % st['addr'], car_reflection_zones=zones),
             alternate_stages=alt)
    json.dump(J, open(out_dir + 'gameplay.json', 'w'), indent=1)
    # collision OBJ
    fo = open(out_dir + 'sr2_course%d_collision.obj' % k, 'w'); fm = open(out_dir + 'sr2_course%d_collision.mtl' % k, 'w')
    fo.write('# SEGA Rally 2 course table index %d: collision / surface polygons from banked CROM (bank %d, polygon array 0x%08X). x, y, -gameZ. One group per surface type.\nmtllib sr2_course%d_collision.mtl\n' % (k, st['bank'], S['pB'], k))
    Pf = S['Pf']; Pu = S['Pu']; npoly = len(Pf)
    for i in range(npoly):
        T = Pf[i, 4:13].reshape(3, 3)
        for v in T: fo.write('v %.4f %.4f %.4f\n' % (v[0], v[1], -v[2]))
    groups = {}
    for i in range(npoly):
        a = int(Pu[i, 74]) & 0xFFFF; key = 'WALL' if a & 0x8000 else SURF[a & 0xF]; groups.setdefault(key, []).append(i)
    for key, L_ in sorted(groups.items()):
        col = (0.9, 0.3, 0.3) if key == 'WALL' else SURF_COL[SURF.index(key)]
        fm.write('newmtl %s\nKd %.3f %.3f %.3f\n' % ((key,) + col)); fo.write('g %s\nusemtl %s\n' % (key, key))
        for i in L_:
            T = Pf[i, 4:13].reshape(3, 3).astype(float); nrm = np.cross(T[1] - T[0], T[2] - T[0])
            idx = (3 * i + 1, 3 * i + 2, 3 * i + 3) if nrm[1] < 0 else (3 * i + 1, 3 * i + 3, 3 * i + 2)   # z negated flips winding; keep normals up
            fo.write('f %d %d %d\n' % idx)
    fo.close(); fm.close()
    print('course %d (%s, stage %d): lap %.0f m, %d checkpoints %s, %d splits, %d pace notes, %d events, %d collision polys, surfaces %s' % (k, STAGE_NAME[sno], sno, L, ncp, cps, nsp, len(notes), len(events), npoly, {kk: round(v) for kk, v in surf_tot.items()}))
    return J

def inside(quad, x, z):
    s = 0
    for i in range(4):
        x0, z0 = quad[i]; x1, z1 = quad[(i + 1) % 4]; c = (x1 - x0) * (z - z0) - (z1 - z0) * (x - x0)
        if abs(c) < 1e-9: continue
        if s == 0: s = 1 if c > 0 else -1
        elif (c > 0) != (s > 0): return False
    return True

LINE_TAB_ADDR = 0xE2C0C
if __name__ == '__main__':
    for k in ([int(a) for a in sys.argv[1:]] or range(5)): export(k)
