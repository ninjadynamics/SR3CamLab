"""Classic course -> SEGA Rally 3 track folder (Desert4 slot), one command:
    python import_classic.py <game> <course> <variant> [--export] [--norender] [--nobuild]
        game    src            (SEGA Rally Championship, Model 2A; data in ../tmp/m2)
        course  1..4           (../courses/<game>_<course>.json holds everything course-specific)
        variant classic | mixed | allsr3
Stages: export (OBJ + coloured tiles from ROM) -> labels (../retex/.../tile_labels.csv: auto guess, then the JSON
label_overrides) -> road, walls, AI map, spline -> scenery -> minimal objects / no camera lists (JSON "props") ->
../out/stepNN_<name>_<variant>_desert4/Desert4 -> decode back and render nine cameras + 2560 px composites.
Nothing is ever run in the game."""
import os, sys, json, csv, struct
import numpy as np
from PIL import Image, ImageDraw
from common import *
import course, sbfw

def stage_export(cfg, force):
    import classic_tex, classic_export
    if force or not os.path.exists(os.path.join(classic_tex.OUT, 'materials.json')) or not os.path.isdir(os.path.join(classic_tex.OUT, 'textures')):
        classic_tex.main()
    return classic_tex.materials()

def stage_labels(cfg, faces):
    import retex, retex_contact
    ip = os.path.join(retex.RT, 'classic_tiles_index.json'); import classic_tex
    if not os.path.exists(ip): json.dump(sorted(n for n, m in classic_tex.materials().items() if m), open(ip, 'w'))
    if not os.path.exists(retex.CSVP): retex.AUTO.clear(); retex.AUTO.update(course.auto_labels(faces))
    lab = retex.labels(); ov = {int(k): v for k, v in cfg.get('label_overrides', {}).items()}
    if ov:
        rows = list(csv.reader(open(retex.CSVP))); ch = 0
        for r in rows[1:]:
            c = ov.get(int(r[0]))
            if c and r[2] != c: s = retex.SR3_FOR_CLASS.get(c); r[2] = c; r[3] = s[0] if s else ''; r[4] = ('%08x' % s[1]) if s else ''; r[5] = 'label from the course JSON'; ch += 1
        if ch: csv.writer(open(retex.CSVP, 'w', newline='')).writerows(rows); lab = retex.labels()
    retex_contact.main(); return lab

def mirror_screen(faces, sky, tiles, log):
    """Several upright boards that stand end to end and make ONE painted picture (Mountain: the castle = keep, round tower, wall, a folded
    screen 164 m long) shown MIRRORED AS A WHOLE, without moving anything: the screen keeps its footprint and its fold lines, and the
    picture is laid on it from the other end (what was at distance t from one end is now at t from the other, left and right swapped).
    A board whose new place runs over a fold is cut there. Why not reflect the boards themselves: the screen is an L with unequal arms on
    the edge of its island - reflected (build Z15), the long arm hung 20 m out over the sea and stood off the ground (user, 2026-10-08:
    "the castle position needs to be adjusted")."""
    B = []
    for w, L in enumerate((faces, sky)):
        for i, fc in enumerate(L):
            if str(fc[0]).split('|')[0] not in tiles or len(fc[2]) != 4: continue
            P = np.asarray(fc[2], float); U = np.asarray(fc[3], float); o = [int(q) for q in np.argsort(P[:, 1])]; b0, b1 = o[0], o[1]
            t0 = min(o[2:], key=lambda j: float(np.linalg.norm(P[j, [0, 2]] - P[b0, [0, 2]]))); t1 = [j for j in o[2:] if j != t0][0]
            B.append(dict(w=w, i=i, fc=fc, P=P, U=U, b=[b0, b1], t=[t0, t1]))
    if len(B) < 2: return faces, sky
    xz = lambda bd, e: bd['P'][bd['b'][e], [0, 2]]; near = lambda p, q: float(np.linalg.norm(p - q)) < 0.5
    ends = [(k, e) for k, bd in enumerate(B) for e in (0, 1) if not any(near(xz(bd, e), xz(o_, e2)) for k2, o_ in enumerate(B) if k2 != k for e2 in (0, 1))]
    if not ends: log('       mirror_groups: the boards make a ring, not mirrored'); return faces, sky
    k, e = ends[0]; chain = [(k, e)]; left = set(range(len(B))) - {k}
    while left:
        tip = xz(B[chain[-1][0]], 1 - chain[-1][1]); nx = [(k2, e2) for k2 in left for e2 in (0, 1) if near(tip, xz(B[k2], e2))]
        if not nx: log('       mirror_groups: %d of %d boards do not join the others, not mirrored' % (len(left), len(B))); return faces, sky
        chain.append(nx[0]); left.discard(nx[0][0])
    seg = []; t = 0.0
    for k, e in chain:                                                 # every board: where it starts and ends along the screen, and which of its corners is which
        bd = B[k]; ln = float(np.linalg.norm(xz(bd, 1 - e) - xz(bd, e))); seg.append(dict(bd=bd, s=t, e=t + ln, bs=bd['b'][e], be=bd['b'][1 - e], ts=bd['t'][e], te=bd['t'][1 - e])); t += ln
    Lt = t; new = {0: [], 1: []}
    for pk in seg:                                                     # the picture of board pk now lies on [Lt - e, Lt - s]
        for gj in seg:
            ta, tb = max(Lt - pk['e'], gj['s']), min(Lt - pk['s'], gj['e'])
            if tb - ta < 1e-4: continue
            Pj, Uk = gj['bd']['P'], pk['bd']['U']; g = lambda q: (q - gj['s']) / (gj['e'] - gj['s']); f = lambda q: (Lt - q - pk['s']) / (pk['e'] - pk['s'])
            pt = {gj['bs']: (Pj[gj['bs']] + g(ta) * (Pj[gj['be']] - Pj[gj['bs']]), Uk[pk['bs']] + f(ta) * (Uk[pk['be']] - Uk[pk['bs']])),
                  gj['be']: (Pj[gj['bs']] + g(tb) * (Pj[gj['be']] - Pj[gj['bs']]), Uk[pk['bs']] + f(tb) * (Uk[pk['be']] - Uk[pk['bs']])),
                  gj['ts']: (Pj[gj['ts']] + g(ta) * (Pj[gj['te']] - Pj[gj['ts']]), Uk[pk['ts']] + f(ta) * (Uk[pk['te']] - Uk[pk['ts']])),
                  gj['te']: (Pj[gj['ts']] + g(tb) * (Pj[gj['te']] - Pj[gj['ts']]), Uk[pk['ts']] + f(tb) * (Uk[pk['te']] - Uk[pk['ts']]))}
            new[gj['bd']['w']].append((pk['bd']['fc'][0], gj['bd']['fc'][1], [tuple(map(float, pt[q][0])) for q in range(4)], [tuple(map(float, pt[q][1])) for q in range(4)]))      # (corner order = the board's it lies on: same facing)
    gone = {(bd['w'], bd['i']) for bd in B}
    faces = [fc for i, fc in enumerate(faces) if (0, i) not in gone] + new[0]; sky = [fc for i, fc in enumerate(sky) if (1, i) not in gone] + new[1]
    log('       boards mirrored as one picture, in place (mirror_groups): %d boards, screen %.1f m, now %d polygons' % (len(B), Lt, len(new[0]) + len(new[1])))
    return faces, sky

def progress_start(cfg, name):
    """Percentage of a running build. A build of given settings takes the same time every run, so the percentage is the time
    gone over the time the last build with the same 'round' / 'light_contrast' took (work\\tmp\\build_times.json; 330 s when
    there is none), with the build's latest log line beside it. Costs one small file write a second. -> function to call at the end."""
    import threading, time
    import build_testtrack as BT
    tf = os.path.join(WORK, 'tmp', 'build_times.json'); key = 'round=%s light=%s' % (cfg.get('round', 0), cfg.get('light_contrast', 0)); pf = os.path.join(WORK, 'tmp', 'progress_%s.txt' % name)
    try: times = json.load(open(tf))
    except Exception: times = {}
    exp = float(times.get(key, times.get('_last', 60.0))); t0 = time.time(); stop = threading.Event()        # (a kind of build never made before: the time of the last build of any kind. It used to assume 330 s, from before the build was sped up: 'still showing wrong 300 sec estimates', user 2026-10-09)
    def write(pct):
        last = next((str(x).strip() for x in reversed(BT.LOG) if str(x).strip()), 'starting')
        try: open(pf + '.new', 'w').write('%d|%d|%d|%s' % (pct, time.time() - t0, exp, last[:110])); os.replace(pf + '.new', pf)      # written beside and swapped in, so a reader never finds it half written
        except Exception: pass
    def loop():
        while not stop.wait(1.0): write(min(99, int(100 * (time.time() - t0) / exp)))
    threading.Thread(target=loop, daemon=True).start()
    def done():
        stop.set(); write(100)
        try:
            times2 = json.load(open(tf)) if os.path.exists(tf) else {}
            times2[key] = round(time.time() - t0, 1); times2['_last'] = times2[key]; json.dump(times2, open(tf, 'w'), indent=1)
        except Exception: pass
    return done

def donor_light(cfg):
    """-> the 49-float lighting sets of the track named by course JSON 'lighting_from' (or None)"""
    trk = cfg.get('lighting_from')
    if not trk: return None
    g = sbfw.read_sbf(track_files(os.path.join(TRACKS, trk))['master_gfx_xdata']); by = g.byid(); c18 = by[g.chunks[-1].u32(0x18)]
    return [np.frombuffer(by[c18.u32(o)].data, '<f4').copy() for o in c18.ref]

def scene_gain(cfg, ref=1.14):
    """per-channel gain for the classic tiles under the donor's light, so flat ground is as bright as it was under the
    importer's own light (ambient 0.41 + sun 1.0 x 0.73 = 1.14): gain = 1.14 / (ambient + sun x scale x how steeply the sun stands)"""
    d = donor_light(cfg)
    if not d: return None
    if cfg.get('scene_gain'): return [float(x) for x in cfg['scene_gain']]      # measured, not computed: Tropical's light shows lit scenery 1.53 / 1.50 / 1.39 times brighter (R G B) than the importer's own (user screenshots 'Light A' / 'Light B', 2026-10-08, six surfaces); the formula below gave a green cast
    fl = d[0].copy(); fl[1:4] = cfg.get('light_dir', fl[1:4]); L = -fl[1:4] / max(float(np.linalg.norm(fl[1:4])), 1e-9)
    return [float(ref / max(fl[4 + k] + fl[7 + k] * fl[23 + k] * max(float(L[1]), 0.0), 1e-3)) for k in range(3)]

def stage_build(cfg, variant, name):
    import build_testtrack as BT, build_more as BM, build_classic as BC, build_allsr3 as BA, allsr3 as A3
    log = BT.log; BT.LOG.append('---- import_classic %s ----' % name); mark = len(BT.LOG) - 1
    des = BT.Track('Desert4'); sta_gfx = BT.Track('Stadium4').files['master_gfx_xdata']; surf, wi, fi = BM.boundary_surfaces(des.files['master_gfx_xdata'])
    BC.TARMAC, BC.GRAVEL = ((A3.ROAD_TARMAC[1:], A3.ROAD_DIRT[1:]) if variant == 'allsr3' else (SAFARI_T, SAFARI_G))
    # course JSON "road_layers": {"tarmac": [track, base id, top id]}: the SR3 road layer pair under the 1995 road. The id decides the physics
    # surface AND what the wheels throw up (10_surfaces.md): Desert4's own pair is Terrain_Safari_Tarmac = dust clouds on asphalt
    # (user, 2026-10-08: "lifts a lot of dirt into the air on asphalt, wtf!!"). Alpine4's Terrain_Tarmac is clean tarmac.
    rl_ = cfg.get('road_layers') or {} if variant != 'allsr3' else {}; copy_ = []
    for key_ in ('tarmac', 'gravel'):
        if key_ in rl_:
            ids_ = tuple(int(x, 16) for x in rl_[key_][1:3]); copy_.append((rl_[key_][0], ids_))
            if key_ == 'tarmac': BC.TARMAC = ids_
            else: BC.GRAVEL = ids_
    ROAD_T_, ROAD_G_ = tuple(BC.TARMAC), tuple(BC.GRAVEL)
    BC.ROAD_VERBATIM = variant == 'classic' and bool(cfg.get('road_verbatim', False)); BC.ROAD_UNDER = float(cfg.get('road_under', -0.02)); BC.SURF_DEFAULT = cfg.get('surface_default', 'gravel'); BC.ROAD_CUT = bool(cfg.get('road_cut', False)); BC.ROAD_RECIPE = cfg.get('road_recipe', False)
    BC.VARIABLE = variant == 'classic' and cfg.get('variable_width', True)        # mixed / allsr3 (frozen lane) keep the constant 14 m road
    log('importing road'); rd = BC.import_road(); log(name)
    cen = rd['V'][:, rd['hw']]; start, grid = classic_grid(cfg, rd); BC.START = (start, 1)
    import pacenotes as PN
    notes, splits = classic_notes(cfg, rd, PN.corners(cen)); shift = lambda fr: fr                      # lap fractions of the spline start at slice 1 like the slices
    BT.SPLINE_EXTRA.clear(); BT.SPLINE_EXTRA.update(splits=splits or [((start + k * len(cen) // 3) % len(cen)) / len(cen) for k in (1, 2)], notes=[(fr, c) for fr, c, tr, rad in notes])
    log('       left/right check (1995 call vs sign of the turn over the next 120 m; positive = the 1995 lefts turn the way SR3 left-coded markers do): %s ; 1995 notes not written or shortened: %s' % (VOTE.get(cfg['name']), NOTE_SKIP.get(cfg['name'])))
    log('       checkpoints (split + time-extension markers): %s' % CHECKPOINTS.get(cfg['name']))
    log('       start slice %d (classic grid table), grid %s ; %d pace notes: %s' % (start, grid, len(notes), [(round(fr, 3), c, tr, rad) for fr, c, tr, rad in notes][:40]))
    t, model, lv = BC.build_road_track(des, rd); f = t.files['master_gfx_xdata']; BT.set_route(t.files['master_xdata'], start, 1, grid)
    for trk_, ids_ in copy_:                                          # the layer textures of another track come with their ids (kind 4 chunks, as build_allsr3 does)
        src_ = sbfw.read_sbf(track_files(os.path.join(TRACKS, trk_))['master_gfx_xdata']).byid(); have_ = {c_.id for c_ in f.chunks}
        for cid_ in ids_:
            if cid_ not in have_: c_ = src_[cid_].copy(); c_.gap = None; f.chunks.insert(0, c_)
        log('       road layers: %08x + %08x copied from %s' % (ids_ + (trk_,)))
    aic = classic_ai_cells(cfg, rd)
    if aic: BT.set_aimap(t.files['master_xdata'], aic); log('       AI map: ' + AI_INFO[cfg['name']])
    if variant == 'allsr3':
        have = {c.id for c in f.chunks}
        for trk, ids in ((A3.ROAD_TARMAC[0], A3.ROAD_TARMAC[1:]), (A3.ROAD_DIRT[0], A3.ROAD_DIRT[1:])):
            src = sbfw.read_sbf(track_files(os.path.join(TRACKS, trk))['master_gfx_xdata']).byid()
            for cid in ids:
                if cid not in have: c = src[cid].copy(); c.gap = None; f.chunks.insert(0, c); have.add(cid)
        log('       road layers: tarmac %s %08x + %08x, loose %s %08x + %08x' % (A3.ROAD_TARMAC + A3.ROAD_DIRT))
    BM.add_walls(f, BT.td_rows(model), surf, wi, fi, terrain=True)
    bake = variant == 'classic' and cfg.get('overlays', 'bake') == 'bake'      # course JSON "overlays": "bake" (default) | "lift" (the old 2 / 4 cm offsets)
    BC.OVERLAY_MODE = 'bake' if bake else 'lift'; BC.FAR_MODE = 'view' if bake else 'near'; BC.BAKED.clear(); BC._TILES.clear(); BC.TEX_OF.clear()
    BC.BAKE_DIR = os.path.join(WORK, 'tmp', 'bake_%s_%s' % (cfg['game'], cfg['name']) + ('_' + PRIVATE[0] if PRIVATE[0] else ''))
    sky = []; far = 0
    if variant == 'classic': BC.EXTRA_TEX = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'textures'); sky, far = backdrop(cfg, rd)
    if bake:                                                           # ONE overlap pass over course + backdrop (overlay_bake.py); the backdrop faces are told apart again by their object names
        bsec = {fc[1] for fc in sky}; allf = BC.load_visual(rd, extra=sky)
        sky = [fc for fc in allf if str(fc[1]).split('#')[0] in bsec]; faces = [fc for fc in allf if str(fc[1]).split('#')[0] not in bsec]
    else: faces = BC.load_visual(rd)
    stage_labels(cfg, faces)
    if cfg.get('mirror_tiles'):                                        # painted pictures whose light comes from the wrong side for the course's sun: each polygon shows its picture mirrored left to right, in place
        mt_ = set(cfg['mirror_tiles']); nm_ = [0]                       # (Mountain: the three boards of the castle are painted lit from the LEFT, the 1995 sun stands to their RIGHT from every part of the road; user, 2026-10-08: "flip each individual component horizontally")
        def _mir(fc):
            if str(fc[0]).split('|')[0] not in mt_: return fc
            u_ = [q[0] for q in fc[3]]; nm_[0] += 1; return (fc[0], fc[1], fc[2], [(min(u_) + max(u_) - q[0], q[1]) for q in fc[3]])
        faces = [_mir(fc) for fc in faces]; sky = [_mir(fc) for fc in sky]; log('       pictures mirrored left to right (mirror_tiles): %d polygons' % nm_[0])
    for grp_ in cfg.get('mirror_groups', []): faces, sky = mirror_screen(faces, sky, set(grp_), log)
    if variant == 'classic' and cfg.get('patch'):                      # the course's hand patches (coursepatch.py): faces added and corners moved in Blender, shipped as small JSON files beside the course settings,
        import coursepatch, glob as _gl                                # named <game>.<course name>.patch.<number>.json (user, 2026-10-09) and applied in the order of their numbers. "patch": true = all of them, a number or a list of numbers = those
        pd_ = os.path.join(WORK, 'courses'); num_ = lambda p_: int(p_.split('.')[-2])
        have_ = sorted(_gl.glob(os.path.join(pd_, '%s.%s.patch.*.json' % (cfg['game'], cfg['name']))), key=num_); want_ = cfg['patch']
        if want_ is not True: want_ = [int(w_) for w_ in (want_ if isinstance(want_, list) else [want_])]; miss_ = [w_ for w_ in want_ if w_ not in [num_(p_) for p_ in have_]]; assert not miss_, 'no patch file number %s for this course in %s' % (miss_, pd_); have_ = [p_ for p_ in have_ if num_(p_) in want_]
        for p_ in have_: faces = coursepatch.apply(faces, p_, rd['ox'], rd['oz'], BC.HI, log, fill_uv=bool(cfg.get('patch_uv', True)))
    if variant == 'classic' and cfg.get('unsmear', True):
        import fill1995 as _Fu
        faces, nu_ = _Fu.unsmear(faces, skip=BC.PAIRS); sky, ns_ = _Fu.unsmear(sky, skip=BC.PAIRS); log('       smeared tiles on natural ground given an even density: %d course polygons, %d backdrop polygons' % (nu_, ns_))
    if variant == 'classic':
        log('       backdrop objects: %d faces within the +-740 m scenery square added as scenery, %d far faces (sky dome, ground plane, distant hills) left out: the slot keeps its own sky' % (len(sky), far))
        if sky and not bake: sky = BC.stack_layers(BC.dedupe_overlays(sky))
        extra = []                                                     # what the 1995 game never needed behind its walls and low camera (fill1995.py): verge ground, longer trunks, a lid on the castle island, the CHECK POINT banners
        if cfg.get('fill', True):
            import fill1995
            lvl_ = (cfg.get('sea') or {}).get('level', -0.5)
            sky = sky + fill1995.island_cap(sky)
            lift_ = cfg.get('banner_lift', 3.0)                        # the CHECK POINT banners hang 2.8 m over the road: inside SR3's chase camera (first own run). Lifted
            fill1995.TEXDIRS[:] = []; fill1995._ALPHA.clear(); fill1995._RGB.clear()
            hf_ = fill1995.handfill(cfg, rd) if cfg.get('handfill', True) else []      # classic/courses/<game>/<course>/src_course<N>_handfill.obj (gapfill_gen.py): natural banks where the 1995 data has nothing
            # ROM object 172 (fill1995.props) is NOT the trackside banner: it is a white hand-written text overlay standing 65 m off the
            # road (user: "the white checkpoint banners are fake"). Gantries built by checkpoints1995 stand at the 1995 time checkpoints.
            import checkpoints1995
            ban_ = []
            if cfg.get('gates', '1995') == '1995':                     # the REAL 1995 gates (gates1995.py: ROM objects 783 .. 792 placed by the trackside table); letters composed into their panel (no stack)
                import gates1995, overlay_bake as _OBg
                ban_ = gates1995.faces(cfg, rd); rxz_ = np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]]
                res_ = (lambda fl_: _OBg.resolve(BC.normalise_uv(fl_), BC.tile_pixels, BC.save_baked, rxz_, log) if (fl_ and bake) else fl_)
                # the gate at the line: nothing at the start, CHECK POINT after a lap, FINISH on the last lap (user, Model 2, 2026-10-08). With
                # the crowd files written, it becomes SR3's lap-aware Start_Finish_Line object (finishgate.py); else it stays scenery reading FINISH.
                lap_ = cfg.get('finish_gate', 'lap') == 'lap' and cfg.get('crowd', True) and cfg.get('props', 'minimal') != 'minimal'
                cp_ = [fc for fc in ban_ if str(fc[1]).startswith('gate_finishcp')]; fi_ = [fc for fc in ban_ if str(fc[1]).startswith('gate_finish_')]
                ban_ = [fc for fc in ban_ if not str(fc[1]).startswith('gate_finish')]
                if lap_ and cp_ and fi_:
                    pf_ = np.array([q for fc in fi_ for q in fc[2]], float); FINISH_GATE[name] = dict(states=[[], res_(cp_), res_(fi_)], centre=(float(pf_[:, 0].mean()), float(pf_[:, 1].min()), float(pf_[:, 2].mean())))
                    ban_ = res_(ban_)
                else: ban_ = res_(ban_ + fi_)
                if cfg.get('gates_unlit', True): BC.UNLIT = {str(fc[0]).split('|')[0] for fc in ban_}; BC.UNLIT_TPL = des.files['master_gfx_xdata'].byid().get(0x47948b52)
                else: BC.UNLIT = set(); BC.UNLIT_TPL = None
                log('       1995 checkpoint / finish gates: %d faces in %s' % (len(ban_), sorted({fc[1] for fc in ban_})))
            if not ban_ and cfg.get('gantries', True):                # stand-in gantries (no gate file for the course)
                ban_ = checkpoints1995.gantries(cfg, rd)
                if bake: BC.PAIRS.update(id(fc) for fc in ban_)            # front / back boards 4 cm apart: single-sided, or the two-sided copies fight in the distance
            if bake and hf_:                                           # a weld / lid / cliff of the hand fill that would lie in the plane of a polygon it joins (after the file's rounding) is left out
                import overlay_bake as _OB
                all_ = faces + sky + hf_; n0_ = len(faces) + len(sky); act_ = {n0_ + k_ for k_, fc in enumerate(hf_) if str(fc[1]).startswith(('hf_weld', 'hf_lid', 'hf_cliff', 'hf_body'))}
                bad_ = {max(p_[0], p_[1]) for p_ in _OB.find_pairs(all_, np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], active=act_)} & act_
                if bad_: hf_ = [fc for k_, fc in enumerate(hf_) if n0_ + k_ not in bad_]; log('       hand fill: %d weld faces left out (in the plane of a polygon they join)' % len(bad_))
            extra = hf_ + ban_ + (fill1995.handmodel(cfg, rd, faces, log=log) if cfg.get('handmodel', True) else [])
            if cfg.get('verge', True):                                # (the hillside lies under the verge, it does not replace it)
                vg_ = fill1995.ground_skirts(faces + sky + [fc for fc in hf_ if not str(fc[1]).startswith(('hf_terrain', 'hf_rocks', 'hf_weld', 'hf_cliff', 'hf_lid'))], rd, sea=lvl_)
                vg_ = fill1995.retile_verge(vg_, faces + sky, rd, log=log)
                if bake and vg_:                                       # a verge cell that would lie in the plane of a 1995 polygon is left out (zero z-fighting comes first)
                    import overlay_bake as _OBv
                    all_ = faces + sky + extra + vg_; n0_ = len(all_) - len(vg_)
                    bad_ = {i_ for p_ in _OBv.find_pairs(all_, np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], active=set(range(n0_, len(all_)))) for i_ in p_[:2] if i_ >= n0_}
                    if bad_: vg_ = [fc for k_, fc in enumerate(vg_) if n0_ + k_ not in bad_]; log('       verge: %d cells left out (in the plane of a polygon they meet)' % len(bad_))
                extra += vg_
            # (verge = 1995 collision ground that was never drawn; cells that 1995 polygons or the shelves cover are skipped)
            if cfg.get('lower_trees', True):                           # trees and lamps are set down on the final ground as whole trees (trees1995), before any trunk is extended
                import trees1995
                gr_ = [fc for fc in faces + sky + extra if not str(fc[0]).endswith('_t')] + fill1995.road_faces(rd)
                f0_ = faces; DUMP_EXTRA['faces_before_lowering'] = list(faces); DUMP_EXTRA['ground_for_trees'] = list(gr_); faces, ti_ = trees1995.lower_boards(faces, gr_)
                if bake and trees1995.lower_boards.moved:              # a tree whose new place lies in the plane of another face goes back where it was (zero z-fighting comes first)
                    import overlay_bake as _OB
                    for pass_ in range(3):
                        mv_ = trees1995.lower_boards.moved; all_ = faces + sky + extra
                        bad_ = {i_ for p_ in _OB.find_pairs(all_, np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], active=set(mv_)) for i_ in p_[:2] if i_ in mv_}
                        if not bad_: break
                        back_ = {k_ for i_ in bad_ for k_ in mv_[i_]}; faces = [f0_[k_] if k_ in back_ else fc for k_, fc in enumerate(faces)]
                        for k_ in back_: mv_.pop(k_, None)
                        ti_['put back (would lie in the plane of another face)'] = ti_.get('put back (would lie in the plane of another face)', 0) + len(back_)
                log('       trees set down on the ground: %s' % ti_)
            tr_ = fill1995.extend_trunks(faces + sky + extra, gap=cfg.get('trunk_gap', 0.12 if hf_ else 1.0), rd=rd, floor=lvl_ - 0.5, limit=cfg.get('trunk_limit', 8.0 if hf_ else None), classes=cfg.get('trunk_classes', ('trunk', 'bare', 'lamp', 'tree') if hf_ else None))
            if hf_ and fill1995.UNGROUNDED:                           # a stem with no ground under it (over water, in mid-air): the whole tree / post goes - every cut-out board within 1.5 m of it
                src_ = faces + sky + extra; gone_ = [np.asarray(src_[k_][2], float)[:, [0, 2]].mean(0) for k_ in fill1995.UNGROUNDED]; n0_ = len(faces)
                near_ = lambda fc: str(fc[0]).endswith('_t') and any(np.hypot(*(np.asarray(fc[2], float)[:, [0, 2]].mean(0) - g_)) < 1.5 for g_ in gone_)
                faces = [fc for fc in faces if not near_(fc)]; log('       boards with no ground within reach removed (with the rest of their tree): %d stems, %d boards in all, at %s' % (len(gone_), n0_ - len(faces), [tuple(np.round(g_, 0).tolist()) for g_ in gone_][:20]))
            if bake and tr_:                                           # an extension that would lie on / close over another face is left out
                import overlay_bake as _OB
                all_ = faces + sky + extra + tr_; n0_ = len(all_) - len(tr_); bad_ = {max(p_[0], p_[1]) for p_ in _OB.find_pairs(all_, np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], active=set(range(n0_, len(all_))), floor=0.05, margin=1.5)}
                tr_ = [fc for k_, fc in enumerate(tr_) if n0_ + k_ not in bad_]
            extra += tr_
            log('       hand fill: %d faces of %d objects ; trunks: %s' % (len(hf_), len({fc[1] for fc in hf_}), {k: v for k, v in fill1995.INFO.get('trunks', {}).items() if k != 'tiles'}))
            log('       fill1995: %d extra faces' % len(extra))
        if cfg.get('sea'):                                             # the 1995 sea is a bowl 2..100 km out and 3.6 km down: outside SR3's scenery square. A flat sheet of its tile below the whole course stands in for it (the dome below the horizon carries the same colour, sky1995)
            sc = cfg['sea']; lvl = sc['level'] if 'level' in sc else min(q[1] for fc in faces + sky for q in fc[2]) - sc.get('drop', 25.0); cell = sc.get('cell', 40.0); n = int(1480 // cell); o = -n * cell / 2
            sea = [(sc['tile'], 'sea', [(o + i * cell, lvl, o + j * cell), (o + (i + 1) * cell, lvl, o + j * cell), (o + (i + 1) * cell, lvl, o + (j + 1) * cell), (o + i * cell, lvl, o + (j + 1) * cell)], [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]) for i in range(n) for j in range(n)]
            if sc.get('clip', True):                                   # no water under land: 10 m pieces, left out where the land covers them and all their neighbours (a ring of water stays under every shore)
                import fill1995 as _F
                sea, nl_ = _F.sea_clip(sea, faces + sky + extra + _F.road_faces(rd), lvl, cell)
                log('       sea clipped: %d m2 under land left out' % nl_)
            sky = sky + sea; log('       sea: %d quads of %s at y %.1f' % (len(sea), sc['tile'], lvl))
        BC.ROAD_DECALS = cfg.get('road_decals', True); BC.ROAD_SPEC = float(cfg.get('road_spec', 0.0)); BC.LIGHT_K = float(cfg.get('light_contrast', 0.0)); BC.LM_TEST = bool(cfg.get('lm_test', False)); BC.OWN_SHADER = set(cfg.get('own_shader_tiles', ())); BC.BUMP = dict(cfg.get('bump_tiles', {})); BC.BUMP.update({t_: float(cfg.get('bump_strength', 8.0)) for t_, v_ in __import__('retex').labels().items() if v_[0] in set(cfg.get('bump_classes', ())) and t_ not in BC.BUMP}); BC.BUMP_TRUE = bool(cfg.get('bump_true', False)); BC.BUMP_GREEN = bool(cfg.get('bump_flip_green', False)); BC.BUMP_GAIN = float(cfg.get('bump_gain', 1.0)); BC.SCENE_GAIN = scene_gain(cfg); log('       lighting from %s: classic tiles scaled by %s' % (cfg.get('lighting_from'), BC.SCENE_GAIN)) if BC.SCENE_GAIN else None
        BC.ROAD_MODE = cfg.get('road_mode', 'drape'); BC.ROAD_MAIN[:] = []
        if cfg.get('gate', 'report'):                                  # "gate": "report" (default) | "fail" | false : coplanar / near-coplanar overlapping faces = what can z-fight (overlay_bake.gate)
            import overlay_bake
            g_ = overlay_bake.gate(faces + sky + extra, np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], BC.PAIRS); GATE[name] = g_
            log('       z-fight gate: %d coplanar + %d near-coplanar overlapping pairs (%d of them within 30 m of the road) ; by section %s ; worst (gap, needed, tile, section, tile, section, where): %s' % (g_['exact'], g_['near'], g_['within_30m_of_road'], g_['by_section'], g_['worst']))
            if cfg.get('gate') == 'fail' and g_['exact'] + g_['near']: raise SystemExit('z-fight gate: %d pairs, see the build log' % (g_['exact'] + g_['near']))
        if cfg.get('fill', True) and cfg.get('roofs', True):           # houses the 1995 game never showed from behind or above: gable triangles and walls under open eaves (roofs1995.py)
            import roofs1995, fill1995 as _Fr, overlay_bake as _OBr
            cur_ = faces + sky + extra; gi_ = _Fr.Index([fc for fc in cur_ if fc[1] != 'sea' and not str(fc[0]).endswith('_t')] + _Fr.road_faces(rd))
            new_ = roofs1995.gables(cur_, log=log) + roofs1995.eave_walls(cur_, gi_, log=log, sea=(cfg.get('sea') or {}).get('level', -0.5))
            if new_:
                all_ = cur_ + new_; n0_ = len(cur_)
                bad_ = set()
                for p_ in _OBr.find_pairs(all_, np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], active=set(range(n0_, len(all_)))):
                    i_, j_ = sorted(p_[:2]); bad_.add(j_ if j_ >= n0_ else i_)      # two new walls on one line (neighbours sharing an eave): the later one goes; a new one against an old face: the new one goes
                bad_ = {b_ - n0_ for b_ in bad_ if b_ >= n0_}
                extra = extra + [fc for k_, fc in enumerate(new_) if k_ not in bad_]; log('       roofs: %d faces added, %d left out (in the plane of another face)' % (len(new_) - len(bad_), len(bad_)))
        if cfg.get('fill', True) and cfg.get('seal', True):            # last: whatever wall foot is still open is carried down (gapfill_weld.seal), minus anything that would z-fight
            import gapfill_weld as _GW, overlay_bake as _OBs
            for pass_ in range(2):
                sl_ = _GW.seal(faces + sky + extra, rd, log=log)
                if not sl_: break
                all_ = faces + sky + extra + sl_; n0_ = len(all_) - len(sl_)
                bad_ = {max(p_[0], p_[1]) for p_ in _OBs.find_pairs(all_, np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], active=set(range(n0_, len(all_))))}
                extra = extra + [fc for k_, fc in enumerate(sl_) if n0_ + k_ not in bad_]
        if cfg.get('round'):                                           # EXPERIMENT 'Z1R2' (round1995.py): natural 1995 surfaces cut finer and smoothed; default off
            import round1995
            n0_, n1_ = len(faces), len(sky); lv_ = max(1, int(round(np.log2(float(cfg['round'])))))        # 'round' 2 = every edge halved once, 4 = twice. Each step is also ROUNDER (user, 2026-10-08: "I'd like each R to increment roundness as well"): the passes go 2, 16, 128, 1024 = the reach of the smoothing grows by 1.41 a step (4 x the passes would only keep R2's reach): a pass reaches one edge, and the edges are half as long each time - with 2 passes at every level the finer mesh came out LESS rounded (first Z4R4: mean move 0.13 m against 0.50 m for R2)
            all_, ri_ = round1995.round_natural(faces + sky + extra, level=lv_, passes=int(cfg.get('round_passes', 2 * 8 ** (lv_ - 1))), log=log, exclude=cfg.get('round_exclude', ()), road=np.asarray(rd['V'], float))      # (the limits that keep a strong rounding whole: round1995.py)
            faces, sky, extra = all_, [], []
            if cfg.get('seal_after_round', False) and cfg.get('fill', True) and cfg.get('seal', True):       # (OFF by default: it took 3 minutes of a 10 minute build and closed 3 places; what holds the road's edge is round1995's apron) ... and sealed again: rounded ground shrinks away from the road and sinks (looking straight down beside the road, the ground had dropped more than 0.3 m
                import gapfill_weld as _GW2, overlay_bake as _OB2     # in 5 000 places of build BASE), which opened holes along the tarmac where it meets rock and walls (user, 2026-10-08, who had asked for this after Z15R8: "a second poly-fill pass after rounding")
                for pass_ in range(2):
                    sl_ = _GW2.seal(faces, rd, log=log)
                    if not sl_: break
                    all_ = faces + sl_; n0_ = len(faces); bad_ = {max(p_[0], p_[1]) for p_ in _OB2.find_pairs(all_, np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], active=set(range(n0_, len(all_))))}
                    faces = faces + [fc for k_, fc in enumerate(sl_) if n0_ + k_ not in bad_]; log('       sealed again after the rounding (pass %d): %d pieces, %d left out (they would z-fight)' % (pass_ + 1, len(sl_) - len(bad_), len(bad_)))
        import atexit as _ae, texfast as _tf, overlay_bake as _OBt      # texmap.json beside the built files: which texture shows which tile (texfast.py, the fast lane for re-authored textures)
        _ae.register(lambda: _tf.save_map(os.path.join(WORK, 'out', name, 'Desert4'), BC, _OBt, print))
        if cfg.get('bake_refine'):                                    # baked light is per vertex: big polygons near the road are cut so that a shadow has corners to land on (bake1995.py)
            import bake1995; n0_ = len(faces); faces = bake1995.refine(faces + sky + extra, float(cfg['bake_refine']), np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]], log=log); sky, extra = [], []
        if cfg.get('bake_collect'):
            import bake1995, atexit; BC.BAKE_COLLECT = []; sd_ = cfg.get('light_dir'); bake1995.save_scene(cfg['bake_collect'], faces + sky + extra, rd, BC.tile_pixels, [-float(q) for q in sd_] if sd_ else [0.0, 0.94, -0.34], log)
            atexit.register(lambda: bake1995.save_points(cfg['bake_collect'], BC.BAKE_COLLECT, print))
        if cfg.get('lm_collect'):                                     # real light maps (lightmap1995.py): pass 1, the polygons and the scene
            import bake1995, lightmap1995, atexit; BC.LM_COLLECT = []; sd_ = cfg.get('light_dir'); bake1995.save_scene(cfg['lm_collect'], faces + sky + extra, rd, BC.tile_pixels, [-float(q) for q in sd_] if sd_ else [0.0, 0.94, -0.34], log)
            atexit.register(lambda: lightmap1995.save_collect(cfg['lm_collect'], BC.LM_COLLECT, print))
        if cfg.get('lm_bake'):                                        # ONE-PASS light maps (see the add_scenery call below): the scene for the rays is saved here, at the point the two-pass way saves it
            import bake1995; sd_ = cfg.get('light_dir'); bake1995.save_scene(cfg['lm_bake'], faces + sky + extra, rd, BC.tile_pixels, [-float(q) for q in sd_] if sd_ else [0.0, 0.94, -0.34], log)
        if cfg.get('lm_table'):                                       # pass 2: the pages
            import lightmap1995; BC.LM_TABLE = lightmap1995.load_table(cfg['lm_table'])
        if cfg.get('bake_table'):
            import bake1995, atexit; BC.BAKE_TABLE = bake1995.load_table(cfg['bake_table']); BC.BAKE_MODE = cfg.get('bake_mode', 'shadows'); BC.BAKE_SHADE = float(cfg.get('bake_shade', 0.42)); BC.BAKE_STRENGTH = float(cfg.get('bake_strength', 1.0))
            atexit.register(lambda: print('       baked light (%s): %d vertices found by place only, %d not found at all (those are lit as if in the open)' % (BC.BAKE_MODE, BC.BAKE_TABLE['miss'][0], BC.BAKE_TABLE['miss'][1])))
        if os.environ.get('GAPFILL_DUMP'):
            import pickle
            import overlay_bake as _OBd
            pickle.dump(dict(faces=faces, sky=sky, extra=extra, rd=rd, baked=dict(BC.BAKED), origin=dict(_OBd.ORIGIN), **DUMP_EXTRA, pairs=[k for k, fc in enumerate(faces + sky + extra) if id(fc) in BC.PAIRS]), open(os.environ['GAPFILL_DUMP'], 'wb'))
        if float(cfg.get('light_contrast', 0.0)) > 0:               # lighting by the sun: every opaque polygon wound towards the side it is seen from (lightside.py)
            import lightside
            n0_, n1_ = len(faces), len(sky); all_, li_ = lightside.orient(faces + sky + extra, log, tag=name); faces, sky, extra = all_[:n0_], all_[n0_:n0_ + n1_], all_[n0_ + n1_:]
            if cfg.get('roadsight', True):                              # ... then the proper question: which side is seen FROM THE ROAD (roadsight.py) - it overrules the sky test wherever the road sees the polygon
                import roadsight; faces, sky, extra = roadsight.orient((faces, sky, extra), rd, log)
        if float(cfg.get('light_contrast', 0.0)) > 0:
            dl_ = donor_light(cfg); fl_ = (dl_[min(1, len(dl_) - 1)].copy() if dl_ else np.array([0, -4, -6, 4, 0.41, 0.41, 0.41, 1, 1, 1] + [0] * 13 + [1, 1, 1], float)); fl_[1:4] = cfg.get('light_dir', fl_[1:4])
            BC.LIGHT_ENV = (float(np.mean(fl_[4:7])), float(np.mean(fl_[7:10] * fl_[23:26])), tuple(-fl_[1:4] / max(float(np.linalg.norm(fl_[1:4])), 1e-9))); log('       light for the shading rule: ambient %.2f, sun %.2f, towards the sun %s' % (BC.LIGHT_ENV[0], BC.LIGHT_ENV[1], np.round(BC.LIGHT_ENV[2], 2).tolist()))
        BC.SMOOTH_N = {}
        BC.GROUND_AT = None
        if BC.LIGHT_K > 0:
            import fill1995 as _Fg
            gi_ = _Fg.Index([fc for fc in faces + sky + extra if fc[1] != 'sea' and not str(fc[0]).split('|')[0].endswith('_t')] + _Fg.road_faces(rd))
            def _gat(X_, Z_, Y_):
                out_ = np.full(len(X_), -1e3)
                for k_ in range(len(X_)):
                    hs_ = [h_ for h_, q_ in gi_.heights(float(X_[k_]), float(Z_[k_])) if h_ <= Y_[k_] + 1.0]
                    if hs_: out_[k_] = max(hs_)
                return out_
            BC.GROUND_AT = None                                       # (not used: every polygon is written once per side, see build_classic.faces_to_mesh)
        if BC.LIGHT_K > 0:                                            # lighting experiment: smooth normals on natural ground (1995 rock / grass / dirt, the hand fill, the verge)
            import retex as _rs, overlay_bake as _OBn
            lab_ = {k_: v_[0] for k_, v_ in _rs.labels().items()}; nat_ = lambda fc: (not str(fc[0]).split('|')[0].endswith('_t')) and fc[1] != 'sea' and (str(fc[1]).startswith(('hf_', 'hm_', 'verge')) or lab_.get(_OBn.ORIGIN.get(str(fc[0]).split('|')[0], str(fc[0]).split('|')[0])) in ('rock', 'grass', 'dirt', 'sand', 'gravel'))
            BC.FLAT_LIT = {k_ for k_, v_ in lab_.items() if v_ in cfg.get('flat_lit_classes', ['sign'])} | {b_ for b_, o_ in _OBn.ORIGIN.items() if lab_.get(o_) in cfg.get('flat_lit_classes', ['sign'])}
            BC.SMOOTH_N = BC.smooth_normals([fc for fc in faces + sky + extra if nat_(fc)]); log('       lighting experiment: light_contrast %.2f, smooth normals on %d corners of natural ground' % (BC.LIGHT_K, len(BC.SMOOTH_N)))
        BC.MISSING_TEX[:] = []
        if cfg.get('lm_bake'):
            # LIGHT MAPS IN ONE BUILD (course settings lm_bake = <table file>, lm_mode, lm_strength, lm_shade). The bake needs the polygons exactly as the mesh
            # writer makes them, so the two-pass way ran the WHOLE build twice (lm_collect, then lm_table: 38 s + 42 s of an 87 s round, 2026-10-08).
            # Here the mesh writer runs once on a copy of the file that is thrown away, only to note the polygons; then the bake; then the real run.
            import copy, lightmap1995; keep_ = (list(BC.MISSING_TEX), {k_: list(v_) for k_, v_ in BC.TEX_OF.items()}, dict(BC.TEXMAP), list(BC.ROAD_MAIN), BC.SCENE_GAIN)
            BC.LM_COLLECT = []; BC.LM_TABLE = None; BC.add_scenery(copy.deepcopy(f), sta_gfx, faces + sky + extra, 'classic', lv, rd=rd)
            lightmap1995.save_collect(cfg['lm_bake'], BC.LM_COLLECT, log); BC.LM_COLLECT = None
            BC.MISSING_TEX[:] = keep_[0]; BC.TEX_OF.clear(); BC.TEX_OF.update(keep_[1]); BC.TEXMAP.clear(); BC.TEXMAP.update(keep_[2]); BC.ROAD_MAIN[:] = keep_[3]; BC.SCENE_GAIN = keep_[4]
            lightmap1995.bake(cfg['lm_bake'], cfg.get('lm_mode', 'rt'), float(cfg.get('lm_strength', 1.0)), float(cfg.get('lm_shade', 0.33)), log=log); BC.LM_TABLE = lightmap1995.load_table(cfg['lm_bake'])
        BC.add_scenery(f, sta_gfx, faces + sky + extra, 'classic', lv, rd=rd)
        BC.SCENE_GAIN = None                                          # only the lit scenery: the sky and the unlit gates keep their own colours (the gain reached the sky textures in build Z6: sky at 0.68 of its brightness)
        if BC.MISSING_TEX: raise SystemExit('BUILD STOPPED: materials without a picture (they would render flat grey): %s' % sorted(set(BC.MISSING_TEX))[:12])
        if cfg.get('sky', '1995') == '1995':                           # 1995 sky colours in the slot's own dome textures (sky1995.py); 'slot' keeps Desert4's sky
            import sky1995
            try: sky1995.apply(f, cfg, rd, log, preview=os.path.join(WORK, 'previews', 'sky1995_%s_%%d.png' % cfg['name']))
            except AssertionError as e: log('       1995 sky NOT applied (%s): the slot keeps its own sky' % e)
        r_ = f.chunks[-1]                                              # root +14: the slot's far horizon card (Desert4: Kilimanjaro, mesh format 0x2041). 0 in Stadium4, so optional
        if 0x14 in r_.ref and r_.u32(0x14):
            d_ = bytearray(r_.data); struct.pack_into('<I', d_, 0x14, 0); r_.data = bytes(d_); r_.ref = [o for o in r_.ref if o != 0x14]; log('       slot horizon card (root +14) removed')
        lg_ = cfg.get('lighting', {'ambient': [0.41, 0.41, 0.41], 'sun': [1.0, 1.0, 1.0], 'scale': [1.0, 1.0, 1.0], 'tint': [0.40, 0.40, 0.40], 'fog': [0.80, 0.80, 0.80]})      # 2026-10-08: ambient was 0.40 0.41 0.43 and the fog / sky colour Desert4's 0.55 0.82 0.92: the car's white read 211 222 255 (user); both neutral now                                      # the slot's two lighting sets (root +18 -> c7975114 -> 2 x b473b5a7, 49 floats): Desert4's are warm (sun 0.97 1 0.82, scale 1.12 1.05 1, tint 0.45 0.33 0.26) = sepia over the 1995 colours
        if lg_:
            by0 = f.byid(); c18 = by0[f.chunks[-1].u32(0x18)]
            don_ = donor_light(cfg)                                    # course JSON 'lighting_from': another track's lighting sets, float for float (the cars are lit as on that track)
            if don_: lg_ = {}
            for q_, o_ in enumerate(c18.ref):
                s_ = by0[c18.u32(o_)]; fl = np.frombuffer(s_.data, '<f4').copy()
                if don_: fl[:] = don_[min(q_, len(don_) - 1)]
                if cfg.get('light_dir'): fl[1:4] = cfg['light_dir']      # the direction the sun shines IN (both sets: the cast shadows and the shading must agree). Mountain: Desert4's own -4 -6 4 = sun ahead and to the right on the start grid, 47 degrees up, which is where the 1995 game has it (left houses lit, church front and right houses in shade, SRC.png)
                for k0, key in ((4, 'ambient'), (7, 'sun'), (23, 'scale'), (44, 'tint'), (14, 'fog')):
                    if key in lg_: fl[k0:k0 + 3] = lg_[key]
                fr_ = cfg.get('fog_range', [20000.0, 40000.0, 20000.0, 40000.0])      # floats 10..13 of each set: the 1995 game has no fog (the fogged far edge of the sea sheet stood as blue bars on the horizon)
                if fr_: fl[10:14] = fr_
                s_.data = fl.tobytes()
            log('       lighting sets overridden: %s ; fog range %s' % (lg_, cfg.get('fog_range', [20000.0, 40000.0, 20000.0, 40000.0])))
        if BC.ROAD_MAIN:                                               # the 1995 asphalt tile, tiled, replaces the COLOUR of the two SR3 tarmac layer textures (ids, alpha blocks, size and mip chain stay SEGA's)
            tile_ = BC.ROAD_MAIN[0]; rep_ = int(cfg.get('road_tile_repeat', 4)); by0 = f.byid()
            BC.VIVID = tuple(BC.VIVID_CFG) if BC.VIVID_CFG else None; tile_ = BC.vivid(tile_); BC.VIVID = None
            for i_ in ROAD_T_:
                c_ = by0[i_]; w_, h_ = struct.unpack_from('<II', c_.data, 8); assert c_.data[48 + 80:48 + 84] == b'DXT5'; hd = 48 + 124; out_ = bytearray(c_.data); o_ = hd
                big_ = Image.fromarray(np.tile(tile_, (rep_, rep_, 1))).resize((w_, h_), Image.BICUBIC); lw, lh = w_, h_
                while o_ < len(out_):
                    bw, bh = max(1, (lw + 3) // 4), max(1, (lh + 3) // 4); n_ = bw * bh * 16
                    if o_ + n_ > len(out_): break
                    lvl = np.array(big_.resize((bw * 4, bh * 4), Image.BILINEAR).convert('RGB')); B = np.frombuffer(bytes(out_[o_:o_ + n_]), np.uint8).reshape(-1, 16).copy()
                    B[:, 8:] = np.frombuffer(BC.dxt1_rgb(np.ascontiguousarray(lvl)), np.uint8).reshape(-1, 8); out_[o_:o_ + n_] = B.tobytes(); o_ += n_
                    if lw == 1 and lh == 1: break
                    lw, lh = max(1, lw // 2), max(1, lh // 2)
                c_.data = bytes(out_); c_.gap = None
            log('       SR3 tarmac layers repainted with the 1995 asphalt tile (%d x %d texels, %d repeats)' % (tile_.shape[1], tile_.shape[0], rep_))
        by_ = f.byid()                                                 # road layers keep SEGA's ids (the id decides the physics surface); their pixels are tinted towards the 1995 road colours
        for key, ids_ in (('tarmac', ROAD_T_), ('gravel', ROAD_G_)):
            k_ = (cfg.get('road_tint') or {}).get(key)
            if key == 'tarmac' and BC.ROAD_MAIN: k_ = None
            for i_ in ids_ if k_ else ():
                c_ = by_[i_]; assert c_.data[48 + 80:48 + 84] == b'DXT5'; hd = 48 + 124; B = np.frombuffer(c_.data, np.uint8, (len(c_.data) - hd) // 16 * 16, hd).reshape(-1, 16).copy(); e = B[:, 8:12].copy().view('<u2').astype(np.float32)
                rgb = np.stack([(e.astype(np.int32) >> 11) & 31, (e.astype(np.int32) >> 5) & 63, e.astype(np.int32) & 31], -1) * np.array(k_, np.float32)
                rgb = np.clip(np.round(rgb), 0, [31, 63, 31]).astype(np.uint16); B[:, 8:12] = ((rgb[..., 0] << 11) | (rgb[..., 1] << 5) | rgb[..., 2]).astype('<u2').view(np.uint8)
                c_.data = c_.data[:hd] + B.tobytes() + c_.data[hd + B.size:]; c_.gap = None
            if k_: log('       road layer %s tinted by %s' % (key, k_))
        # texture header +14: sampler set-up read by 0x58DF40 {addrU, addrV, addrW, filter (3 = min aniso / mag linear / mip linear, i.e. trilinear), f32 mip LOD bias, u16 max anisotropy}.
        # Our textures had max anisotropy 1 (SEGA's road layers: 4): the road went soft a few metres ahead. road_lod_bias -12 = mip level 0 everywhere (mipmapping off).
        an_, lb_ = int(cfg.get('road_aniso', 8)), float(cfg.get('road_lod_bias', 0.0))
        da_ = cfg.get('road_decal_alpha')                              # experiment: draped road slightly see-through, so the car shadow SR3 draws on its own road shows
        for c_ in f.chunks if da_ else ():
            if c_.kind == 4 and c_.id >> 16 == 0xc1aa and c_.data[48 + 80:48 + 84] == b'DXT5':
                hd = 48 + 124; B = np.frombuffer(c_.data, np.uint8, (len(c_.data) - hd) // 16 * 16, hd).reshape(-1, 16).copy()
                if (B[:, 0] == 255).all() and (B[:, 2:8] == 0).all(): B[:, 0] = B[:, 1] = int(255 * da_); c_.data = c_.data[:hd] + B.tobytes() + c_.data[hd + B.size:]; c_.gap = None
        for c_ in f.chunks:
            if c_.kind != 4: continue
            hi_ = c_.id >> 16; road_ = hi_ == 0xc1aa or c_.id in ROAD_T_ + ROAD_G_
            if road_ or hi_ == 0xc1a5:
                d_ = bytearray(c_.data); struct.pack_into('<H', d_, 0x28, an_ if road_ else 4)
                if road_: struct.pack_into('<f', d_, 0x24, lb_)
                c_.data = bytes(d_)
        sb_ = (cfg.get('sea') or {}).get('lod_bias')                    # the sea sheet's own texture: a mip LOD bias (2.0 = two levels softer) and no anisotropy, so the 64 px tile does not sparkle towards the horizon
        if sb_ is not None:
            ids_ = set(BC.TEX_OF.get(cfg['sea']['tile'], ())); n_ = 0
            for c_ in f.chunks:
                if c_.kind == 4 and c_.id in ids_: d_ = bytearray(c_.data); struct.pack_into('<f', d_, 0x24, float(sb_)); struct.pack_into('<H', d_, 0x28, int(cfg['sea'].get('aniso', 1))); c_.data = bytes(d_); n_ += 1
            log('       sea texture: mip LOD bias %s, max anisotropy %d on %d texture chunk(s)' % (sb_, int(cfg['sea'].get('aniso', 1)), n_))
        if cfg.get('road_alpha0'):                                     # experiment: SR3 road layers fully transparent, so only the draped 1995 road shows (no z-fight between the two)
            for i_ in ROAD_T_ + ROAD_G_:
                c_ = by_[i_]; hd = 48 + 124; B = np.frombuffer(c_.data, np.uint8, (len(c_.data) - hd) // 16 * 16, hd).reshape(-1, 16).copy(); B[:, :8] = 0
                c_.data = c_.data[:hd] + B.tobytes() + c_.data[hd + B.size:]; c_.gap = None
        r_ = f.chunks[-1]                                              # root +14: the slot's far horizon card (Desert4: Kilimanjaro, mesh format 0x2041). 0 in Stadium4, so optional
        if 0x14 in r_.ref and r_.u32(0x14):
            d_ = bytearray(r_.data); struct.pack_into('<I', d_, 0x14, 0); r_.data = bytes(d_); r_.ref = [o for o in r_.ref if o != 0x14]; log('       slot horizon card (root +14) removed')
    elif variant == 'mixed': BC.add_scenery(f, sta_gfx, faces, 'retex', lv, rd=rd)
    else: BA.add_scenery_all(f, sta_gfx, faces, lv, rd)
    omit = ()
    if cfg.get('props', 'minimal') == 'minimal':
        k, nch = BC.minimal_objects(t); omit = ('proc',); k2, dr = BC.no_cameras(t)
        log('       props: authored empty object list (was %d objects in %d chunks), no pobj files / grass cache; camera lists and helicopter removed (%d chunks): the game builds default cameras' % (k, nch, dr))
    if cfg.get('cameras') == 'default':                                # the slot's camera lists stand where Desert4's road is: without them the game builds its own (intro, post-race, replay)
        k2, dr = BC.no_cameras(t); log('       cameras: slot camera lists and helicopter removed (%d chunks): the game builds default cameras' % dr)
    if cfg.get('props') == 'noobjects':                               # the slot's animals, props and breakables go; pobj files, grass cache and cameras stay (the game needs them)
        k, nch = BC.minimal_objects(t); log('       props: authored empty object list (was %d objects in %d chunks); pobj files, grass cache and cameras kept' % (k, nch))
    if variant == 'classic' and cfg.get('crowd', True) and cfg['game'] == 'src' and cfg.get('props', 'minimal') != 'minimal':
        import crowd, trackdeform as TDM                               # the 1995 spectators as SR3's own animated crowd (15_spectators.md); course JSON "crowd": false keeps the object files as "props" left them
        if str(cfg['course']) in crowd.SRC_TABLES:
            by_ = f.byid(); cen_, lat_, lo_, hi_ = TDM.road_frame(TDM.parse_td(by_[f.chunks[-1].u32(0xC)], by_))
            spots = crowd.classic_spots(str(cfg['course']), cen_, rd['ox'], rd['oz'], zs=BC.ZS, lat=lat_, lo=lo_, hi=hi_)
            if cfg.get('crowd_snap', True) and cfg.get('fill', True):   # every spectator ON the final ground: the highest lying surface within 3 m of the 1995 height; none = no spectator
                import fill1995 as _F
                fl_ = [fc for fc in faces + sky + extra if fc[1] != 'sea'] + _F.road_faces(rd); gi_ = _F.Index(fl_); out_ = []; nd_ = nm_ = nf_ = 0
                import retex as _rt, overlay_bake as _OBc
                lab_ = {k_: v_[0] for k_, v_ in _rt.labels().items()}; wcls_ = lambda k_: lab_.get(_OBc.ORIGIN.get(fl_[k_][0], fl_[k_][0]))
                def _gy(x_, y_, z_):
                    hs_ = [h_ for h_, k_ in gi_.heights(x_, z_, True) if y_ - 3.0 <= h_ <= y_ + 3.0]; return min(hs_, key=lambda h_: abs(h_ - y_)) if hs_ else None   # the surface NEAREST the 1995 foot height: the highest one put people on top of the roadside walls
                for x_, y_, z_, hd_ in spots:
                    j_ = int(np.argmin((cen_[:, 0] - x_) ** 2 + (cen_[:, 2] - z_) ** 2)); s_ = float((np.array([x_, y_, z_]) - cen_[j_]) @ lat_[j_]); e_ = hi_[j_] if s_ >= 0 else lo_[j_]; g_ = _gy(x_, y_, z_)
                    if g_ is not None and 0.0 < abs(s_) - abs(e_) < 5.5:                    # behind a stone wall or rock right beside the road: the person is hidden, the shadow lies on the tarmac alone. Back to 5.5 m from the road edge
                        wall_ = False
                        for t_ in np.arange(abs(e_) + 0.25, abs(s_), 0.5):
                            q_ = cen_[j_] + lat_[j_] * (np.sign(s_) * t_)
                            if any((not c_) and b_ > g_ + 0.5 and a_ < g_ + 1.6 and wcls_(k_) in ('cobbles', 'rock') for a_, b_, k_, c_ in gi_.uprights(q_[0], q_[2], 0.3)): wall_ = True; break
                        if wall_: p_ = cen_[j_] + lat_[j_] * (np.sign(s_) * (abs(e_) + 5.5)); x_, z_ = float(p_[0]), float(p_[2]); g_ = _gy(x_, y_, z_); nm_ += 1
                    if g_ is None: nd_ += 1; continue
                    j2_ = int(np.argmin((cen_[:, 0] - x_) ** 2 + (cen_[:, 2] - z_) ** 2)); hd_ = float(np.arctan2(cen_[j2_, 0] - x_, cen_[j2_, 2] - z_))   # still facing the road after any move
                    nf_ += abs(g_ - y_) > 0.15; out_.append((x_, float(g_) + 0.02, z_, hd_))
                log('       crowd on the final ground: %d spectators set on the surface under them (moved more than 15 cm), %d moved back from the road (stood behind a wall or rock beside it, shadow alone on the tarmac), %d left out (no ground within 3 m)' % (nf_, nm_, nd_)); spots = out_
            fg_ = FINISH_GATE.get(name)
            ci_ = crowd.apply(t, spots, finish_at=fg_['centre'] if fg_ else None)
            if fg_:
                import finishgate
                tpl5_ = next(c_ for c_ in sta_gfx.kinds(4) if c_.data[48 + 80:48 + 84] == b'DXT5' and struct.unpack_from('<I', c_.data, 40)[0] == 1)
                finishgate.install(t.files[crowd.GO], fg_['states'], fg_['centre'], tpl5_, log, unlit=BC.UNLIT_TPL); log('       finish gate object re-read: LOD (vertices, indices, groups) %s' % finishgate.check(t.files[crowd.GO]))
            log("       crowd: %d spectators from the 1995 table (%d moved off the road strip), %d hidden animators; %d of the slot's %d objects removed" % (ci_['spectators'], crowd.classic_spots.moved, ci_['masters'], ci_['removed'], ci_['donor_objects']))
    d = BT.gc(f, t); BT.write_track(name, t, omit=omit, note='| %d unreferenced chunks dropped' % d); BT.check_authored(name, t)
    open(os.path.join(OUT, 'build_log.txt'), 'a').write('\n'.join(BT.LOG[mark:]) + '\n')

def stage_render(cfg, variant, name):
    import preview_obj, render_all as RA, build_classic as BC, classic_tex
    RA.CSV = BC.CSV; cn = cfg['name']; rom = 'blender_%s_rom_' % cn; pre = 'blender_%s_%s_' % (cn, variant)
    if not os.path.exists(os.path.join(RA.PV, rom + 'overview.png')) or '--export' in sys.argv or '--rerom' in sys.argv: RA.render(render_copy(BC.HI), rom)
    RA.render(preview_obj.main(name), pre)
    for k, v in enumerate(['road_%d' % i for i in range(1, 9)] + ['overview']):
        a = Image.open(os.path.join(RA.PV, rom + v + '.png')).convert('RGB'); b = Image.open(os.path.join(RA.PV, pre + v + '.png')).convert('RGB')
        W = Image.new('RGB', (2560, 764), (0, 0, 0)); W.paste(a, (0, 44)); W.paste(b, (1280, 44)); d = ImageDraw.Draw(W)
        d.text((16, 14), cfg.get('title', cn) + ' - original textures and colours', fill=(255, 255, 255))
        d.text((1296, 14), {'classic': 'the same course as a SEGA RALLY 3 track, 1995 textures inside SR3 files', 'mixed': 'the same course as a SEGA RALLY 3 track, surfaces from SR3, pictures from 1995',
                            'allsr3': 'the same course rebuilt as a SEGA RALLY 3 track, all textures from SR3'}[variant] + ' (%s)' % name.split('_')[0], fill=(255, 255, 255))
        W.save(os.path.join(RA.PV, 'final_%s_%s_%d_%s.png' % (cn, variant, k + 1, v)))
    print('renders:', os.path.join(RA.PV, 'final_%s_%s_*.png' % (cn, variant)))

def render_copy(hi):
    """the 1995 export rewritten for Blender: one vertex per face corner and the cut-out overlays lifted 4 cm off their base
    face (build_classic.dedupe_overlays). Blender's OBJ importer drops a face that uses the same vertices as an earlier one,
    which removed every overlay (ivy on rock, grass fringes) or its base from the '1995' pictures."""
    import build_classic as BC
    V = []; VT = []; faces = []; mat = None; sec = None; lib = ''
    for ln in open(hi):
        if ln.startswith('v '): V.append(tuple(map(float, ln.split()[1:4])))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('o '): sec = ln.split()[1]
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('mtllib'): lib = ln
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]; faces.append((mat, sec, [V[a] for a, b in ix], [VT[b] for a, b in ix]))
    faces = BC.stack_layers(BC.dedupe_overlays(faces)); out = hi[:-4] + '_render.obj'; k = 1; cur = None
    with open(out, 'w') as fo:
        fo.write('# render copy of %s (overlays lifted, unique vertices)\n%s' % (os.path.basename(hi), lib))
        for m, s_, P, UV in faces:
            if m != cur: fo.write('usemtl %s\n' % m); cur = m
            for p_, u in zip(P, UV): fo.write('v %.4f %.4f %.4f\nvt %.5f %.5f\n' % (p_[0], p_[1], p_[2], u[0], u[1]))
            fo.write('f ' + ' '.join('%d/%d' % (k + j, k + j) for j in range(len(P))) + '\n'); k += len(P)
    return out

DUMP_EXTRA = {}
VOTE = {}; NOTE_SKIP = {}; CHECKPOINTS = {}; GATE = {}
def backdrop(cfg, rd):
    """the course's sky / backdrop objects (other session's export src_course<N>_sky.obj): faces that fit inside SR3's
    scenery square are returned like load_visual's; the rest is counted"""
    p = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'src_course%s_sky.obj' % cfg['course'])
    if not cfg.get('gameplay') or not os.path.exists(p): return [], 0
    V = []; VT = []; out = []; far = 0; mat = None; sec = None
    for ln in open(p):
        if ln.startswith('v '): x, y, z = map(float, ln.split()[1:4]); V.append((x + rd['ox'], y, __import__('build_classic').ZS * z + rd['oz']))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('o '): sec = ln.split()[1]
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]; P = [V[a] for a, b in ix][::int(__import__('build_classic').ZS)]
            if all(abs(q[0]) < 740 and abs(q[2]) < 740 and -200 < q[1] < 400 for q in P): out.append((mat, sec, P, __import__('build_classic').flip_v([VT[b] for a, b in ix][::int(__import__('build_classic').ZS)])))
            else: far += 1
    return out, far

def classic_notes(cfg, rd, geo):
    """pace notes and split points of the 1995 game (other session's decode: classic/courses/src/<dir>/gameplay.json,
    axes x, y, -gameZ) -> [(lap fraction, SR3 Direction code, turn, radius)], [split fractions].
    Severity from the classic call (easy / medium -> gentle code, hard / tighter -> second, hairpin -> third); the turning
    SENSE from the imported centre line over the 80 m after the note (SR3's own sign convention, see pacenotes.py)."""
    import pacenotes as PN
    p = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'gameplay.json')
    if not cfg.get('gameplay') or not os.path.exists(p): return geo, None
    g = json.load(open(p)); cen = rd['V'][:, rd['hw']]; n = len(cen); Q = cen[:, [0, 2]]
    D = np.roll(Q, -1, 0) - Q; h = np.unwrap(np.arctan2(D[:, 1], D[:, 0]))
    def sl(pos): return int(np.argmin(np.hypot(cen[:, 0] - (pos[0] + rd['ox']), cen[:, 2] - (__import__('build_classic').ZS * pos[2] + rd['oz']))))
    raw = []
    for nt in g.get('pace_notes', []):
        call = nt.get('call') or ''
        if 'left' not in call and 'right' not in call: continue
        i = sl(nt['position']); tr = float(np.degrees(h[(i + 120) % n] - h[i])) if i + 120 < n else 0.0; raw.append((i, call, tr))
    # which SR3 code family is "left"? vote: the 1995 call against the sign of the turn over the next 120 m
    v = sum((1 if (tr > 0) == ('left' in call) else -1) for i, call, tr in raw if abs(tr) > 12); left = 1 if v >= 0 else -1; VOTE[cfg['name']] = v
    out = []; skipped = []
    lp = os.path.join(os.path.dirname(WORK), 'classic', 'sr2_gameplay', cfg['game'], 'src_pace_notes_labelled.csv'); cname = {'mountain': 'Mountain', 'desert': 'Desert', 'lakeside': 'Lake Side', 'forest': 'Forest'}.get(cfg['name'])
    if os.path.exists(lp) and g.get('ai_line'):
        # the game's own sound-test names: Easy -> gentle code, Mid -> second, K / Hairpin -> third; the side is the first Left / Right in the name
        for r_ in csv.DictReader(open(lp)):
            if r_['course'] != cname: continue
            nm = r_['name']; code, caution = PN.code_for_name(nm)           # exe table 0x70CD28: code -> SP_ speech event (pacenotes.py)
            if code is None: skipped.append(nm); continue
            if caution: skipped.append(nm + ' (caution prefix dropped)')
            i = sl(g['ai_line'][int(r_['section']) % len(g['ai_line'])]['position']); out.append((i / n, code, 0, nm + ' -> ' + PN.code_name(code)))
        NOTE_SKIP[cfg['name']] = skipped
    else:
        for i, call, tr in raw:
            c = PN.CODES[left if 'left' in call else -left]
            code = c[2] if 'hairpin' in call else (c[1] if ('hard' in call or 'tight' in call) else c[0]); out.append((i / n, code, round(tr), call))
    out.sort()
    splits = sorted(sl(c['position']) / n for c in g.get('checkpoints', []))
    # SR3: the (0,5) markers are BOTH the split points and the time-extension checkpoints (CSR_Checkpoint, exe 0x5AC600);
    # marker k grants value k of the stage's ArcadeDatabase time record (exe 0x5ABD40 / 0x661AA0), marker 1 is the gate just
    # after the start line in SEGA's five tracks (2..3 % of the lap) and counts as passed at the start. The slot (Desert4)
    # has two values per lap, so 'slot' = gate + ONE 1995 time checkpoint; 'classic' = gate + every 1995 time checkpoint
    # (needs the matching database from arcade_times.py); 'splits' = the 1995 split-time sections (package seven).
    mode = cfg.get('checkpoints', 'slot'); tp = os.path.join(os.path.dirname(WORK), 'classic', 'sr2_gameplay', cfg['game'], 'src_checkpoints_times.json')
    if mode != 'splits' and os.path.exists(tp) and g.get('ai_line') and cname:
        secs = [x for x in json.load(open(tp))[cname]['checkpoint_sections'] if x > 0]; na = len(g['ai_line'])
        cp = [sl(g['ai_line'][x % na]['position']) / n for x in secs]; i0 = sl(g['ai_line'][0]['position']); gate = ((i0 + 0.025 * n) % n) / n
        rel = lambda fr: (fr - i0 / n) % 1.0
        if mode == 'slot':
            cp = [min(cp, key=lambda fr: abs(rel(fr) - 0.45))] if cp else [((i0 + 0.5 * n) % n) / n]
        splits = sorted([gate] + cp, key=rel); CHECKPOINTS[cfg['name']] = dict(mode=mode, sections_1995=secs, lap_fractions_after_start=[round(rel(fr), 3) for fr in splits])
    return (out or geo), (splits or None)

def classic_ai_cells(cfg, rd):
    """AI map cells whose 8 lanes follow the 1995 AI line (gameplay.json ai_line, 300 points) instead of the road centre.
    The three lane-mask bytes of a cell are selected by a field of the driver's car record ([car + 0x300] + 0x28 = 0 / 1 / 2,
    exe 0x5E949A, 0x5E8CFA): three alternative lane systems, not "a racing line"; all three get the same lanes here, as in
    Desert4. Braking zones (the 1995 speed_zone byte) have no counterpart in the AI map and are not written."""
    import math, build_classic as BC
    p = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'gameplay.json')
    if 'wl' not in rd or not cfg.get('gameplay') or not os.path.exists(p) or cfg.get('ai', '1995') != '1995': return None
    A = np.array([q['position'] for q in json.load(open(p)).get('ai_line', [])], float)
    if len(A) < 10: return None
    A = np.stack([A[:, 0] + rd['ox'], A[:, 1], __import__('build_classic').ZS * A[:, 2] + rd['oz']], 1); B = np.vstack([A, A[:1]]); seg = np.linalg.norm(np.diff(B[:, [0, 2]], axis=0), axis=1); s_ = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, s_[-1], 0.5); L = np.stack([np.interp(t, s_, B[:, 0]), np.interp(t, s_, B[:, 2])], 1)
    cen = rd['V'][:, rd['hw']]; lat = rd['lat']; n = len(cen); idx = BC.Near(L, 8.0)(cen[:, [0, 2]]); a = ((L[idx] - cen[:, [0, 2]]) * lat[:, [0, 2]]).sum(1)
    far = np.hypot(*(L[idx] - cen[:, [0, 2]]).T) > 20; a[far] = 0.0; w_ = 15; k_ = np.ones(2 * w_ + 1) / (2 * w_ + 1); a = np.convolve(np.concatenate([a[-w_:], a, a[:w_]]), k_, 'valid')
    wl, wr = rd['wl'], rd['wr']; band = np.clip(0.4 * (wl + wr), 4.0, 8.0); band = np.minimum(band, np.maximum(wl + wr - 3.0, 2.0))
    a = np.clip(a, -wl + band / 2 + 1.5, np.maximum(wr - band / 2 - 1.5, -wl + band / 2 + 1.5)); cells = {}
    for i in range(n):
        for k in range(8):
            c = a[i] + band[i] / 2 - k * band[i] / 7.0; q = cen[i] + lat[i] * c
            key = (math.floor(q[0] / 2.0) * 2.0 + 1.0, math.floor(q[2] / 2.0) * 2.0 + 1.0); cells[key] = cells.get(key, 0) | (0x010101 << k)
    AI_INFO[cfg['name']] = '1995 AI line: lateral offset from the centre line median %.1f m, max %.1f m (%d slices where it was more than 20 m away ignored); lane band %.1f..%.1f m wide; %d cells' % (float(np.median(np.abs(a))), float(np.abs(a).max()), int(far.sum()), band.min(), band.max(), len(cells))
    return [(x, z, fl) for (x, z), fl in cells.items()]

AI_INFO = {}
def classic_grid(cfg, rd):
    """start slice and the 8 x (dist, col) SR3 grid from the classic start table (program ROM, 4 cars x {x, y, z} per course)"""
    import i960, build_testtrack as BT
    g = cfg.get('start_grid')
    if not g: return int(cfg.get('start', {}).get('slice', 10)), BT.LAKESIDE_GRID
    prog = open(os.path.join(i960.M2, 'maincpu.bin'), 'rb').read(); cen = rd['V'][:, rd['hw']]; n = len(cen); cars = []
    for k in range(4):
        x, y, z = struct.unpack_from('<3f', prog, int(g['offset'], 16) + 12 * k); p = np.array([x + rd['ox'], y, -__import__('build_classic').ZS * z + rd['oz']])       # game axes -> SR3 (rd['V'] uses game z)
        i = int(np.argmin(np.hypot(cen[:, 0] - p[0], cen[:, 2] - p[2]))); c = float((p - cen[i]) @ rd['lat'][i]); cars.append((i if i < n // 2 else i - n, c))
    front = max(i for i, c in cars); start = (front + 3) % n; rows = sorted(cars, key=lambda t: -t[0]); step = max(6, rows[0][0] - rows[-1][0])
    ent = [(front + 3 - i, int(round(c))) for i, c in rows]
    while len(ent) < 8: ent.append((ent[-4][0] + (step if len(ent) % 4 == 0 else ent[-4][0] * 0 + step) , ent[-4][1]))
    lim = int(max(1, np.floor(min(rd['wl'][start - 60:start + 1].min() if start >= 60 else rd['wl'].min(), rd['wr'][start - 60:start + 1].min() if start >= 60 else rd['wr'].min()) - 1.5))) if 'wl' in rd else rd['hw'] - 2; ent = [(max(2, int(d)), max(-lim, min(lim, c))) for d, c in ent[:8]]
    return start, tuple(v for e in ent for v in e)

FINISH_GATE = {}
PRIVATE = [None]
SAFARI_T = (0xe56e4a5c, 0x0558e395); SAFARI_G = (0x9cbfa41a, 0x6ec69183)

def main(game, crs, variant):
    assert variant in ('classic', 'mixed', 'allsr3')
    cfg = course.use(game, crs); name = 'step%02d_%s_%s_desert4' % (cfg['steps'][variant], cfg['name'], variant)
    # several builds side by side (one process each): --name <output folder under out\> and --set key=<json> (repeatable) give a build its own
    # folder, its own work folder for composed tiles and its own settings, so nothing is shared but the read-only sources
    av = sys.argv
    for k_ in range(len(av) - 1):
        if av[k_] == '--name': name = av[k_ + 1]; PRIVATE[0] = name
        if av[k_] == '--set': key_, val_ = av[k_ + 1].split('=', 1); cfg[key_] = json.loads(val_)
    prog_ = progress_start(cfg, name) if PRIVATE[0] else None      # a build with its own --name reports how far it is (work\tmp\progress_<name>.txt, once a second, from a side thread)
    stage_export(cfg, '--export' in sys.argv)
    if '--nobuild' not in sys.argv: stage_build(cfg, variant, name)
    if '--norender' not in sys.argv: stage_render(cfg, variant, name)
    if prog_: prog_()
    return name

if __name__ == '__main__':
    main(*sys.argv[1:4])
