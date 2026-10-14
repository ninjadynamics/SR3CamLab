"""Realism flavor: real specs (realism_specs.json, with sources) -> SR3 field values per car (flavor_realism.json for build_flavor.py).
    python realism_map.py [realism_specs.json] [flavor_realism.json]
Rules (each one keeps SR3's own model; numbers that do not fit it are listed in the output under "misfits"):
  mass         real kg (ch0 +4). In SR3 the tyre force is mu x load, so mass alone changes acceleration and braking, not g in corners.
  inertia      SR3's I/m factors (1.67, 2.5, 1.5 = pitch, yaw, roll) x the real (L2+H2, L2+W2, W2+H2) / a 4300 x 1800 x 1400 mm reference.
  torque       SR3 peak = real Nm x 1.2664 (870/650 x 1230/1300: the Impreza WRC2008 keeps SR3's acceleration per kg exactly).
  curve        13 points at SR3's rpm fractions: from 0.55 (turbo) / 0.5 (NA) at idle to 1.0 at the torque peak, down to the torque the
               power figure gives at the power peak, SR3's own limiter tail above 0.95.
  rev limit    sourced where a source gives it, else an estimate (flagged).
  gearbox      real gear count, ratios evenly spaced (geometric) from SR3's 1st (3.64) to its top (1.18), final drive x limit / 8000
               so the top speed at the limiter stays SR3's; the Hornet uses its Jerico example ratios scaled to the same top.
  drivetrain   4WD active / Group A centre: SR3's LimitedSlipBiased (2, 4) with SR3's split; mechanical (S2000, raid): LimitedSlip4WD
               (2, 0) with the Revo files' 0.2 / 0.2; Hornet: LimitedSlipRearWD (1, 0)."""
import json, sys, math, os
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'realism_specs.json')
dst = sys.argv[2] if len(sys.argv) > 2 else 'flavor_realism.json'
S = json.load(open(src, encoding='utf-8-sig'))['cars']
FR = [0, .125, .25, .375, .5, .625, .75, .875, .91, .95, .97, .99, 1.0]
TAIL = {0.95: 0.2 / 1.0, 0.97: 0.1, 0.99: 0.01, 1.0: 0.0}
LIMIT_EST = {'C4': 7500, 'RSFocus': 7500, 'SubaruImpreza': 7500, 'SX4': 7500, 'MitsubishiEvo': 7000, 'ST205': 7000, 'Delta_HF': 7500,
             'Bowler': 6500, 'Enduro': 4800, 'Hornet': 9000}
PEAKS_EST = {'SX4': (5500, 3500), 'MitsubishiEvo': (5500, 3500), '207': (8000, 6500), 'Bowler': (5500, 4000), 'Enduro': (4000, 2000), 'Hornet': (8000, 6000)}
NA = {'207', 'Bowler', 'Hornet'}
REF = (4300.0, 1800.0, 1400.0)
out = {'flavor': 'realism', 'folder_digit': '2', 'about': 'Real-car differences on SR3s model; built from the owners SR3 files by build_flavor.py.',
       'gearbox': None, 'engine': None, 'tyre': None, 'force_model': 2, 'cars': {}, 'misfits': []}
for car, s in S.items():
    o = {}; mis = []
    o['mass'] = float(s['mass_kg'])
    L, Wd, H = s.get('length_mm', REF[0]), s.get('width_mm', REF[1]), s.get('height_mm', REF[2])
    o['inertia_scale'] = [round((L * L + H * H) / (REF[0] ** 2 + REF[2] ** 2), 3), round((L * L + Wd * Wd) / (REF[0] ** 2 + REF[1] ** 2), 3), round((Wd * Wd + H * H) / (REF[1] ** 2 + REF[2] ** 2), 3)]
    tq = s.get('torque_nm')
    pr, tr = s.get('power_rpm'), s.get('torque_rpm')
    ep, et = PEAKS_EST.get(car, (None, None))
    if not pr: pr = ep; mis.append('power peak rpm estimated (%s)' % ep)
    if not tr: tr = et; mis.append('torque peak rpm estimated (%s)' % et)
    if not tq:
        tq = 700.0; mis.append('peak torque not found: 700 Nm estimated from %s bhp @ %s' % (s['power_bhp'], s['power_rpm']))
    o['torque_nm'] = round(tq * 1.2664, 1)
    lim = s.get('redline_rpm') or LIMIT_EST[car]
    if not s.get('redline_rpm'): mis.append('rev limit estimated %d' % lim)
    o['max_rpm'] = float(lim)
    t_at_p = s['power_bhp'] * 745.7 / (pr * 2 * math.pi / 60) / tq        # torque fraction at the power peak
    lo = 0.5 if car in NA else 0.55
    curve = []
    for f in FR:
        r = f * lim
        if f in TAIL: v = min(1.0, t_at_p) * 0.7 * TAIL[f] if f < 1 else 0.0
        elif r <= tr: v = lo + (1 - lo) * r / tr
        elif r <= pr: v = 1.0 + (min(1.0, t_at_p) - 1.0) * (r - tr) / max(1.0, pr - tr)
        else: v = min(1.0, t_at_p) * (1 - 0.3 * (r - pr) / max(1.0, lim - pr))
        curve.append([f, round(v, 3)])
    if t_at_p > 1.05: mis.append('power %.0f bhp @ %d needs %.0f%% of the peak torque there (> 100%%): torque or power figure off' % (s['power_bhp'], pr, 100 * t_at_p))
    o['torque_curve'] = curve
    n = s.get('gears') or 6
    if not s.get('gears'): mis.append('gear count not in the source: 6 kept')
    if s.get('ratios_example'):
        ex = s['ratios_example']; ratios = [round(x * 1.18 / ex[-1], 3) for x in ex]
    else:
        ratios = [round(3.64 * (1.18 / 3.64) ** (i / (n - 1)), 3) for i in range(n)]
    o['gears'] = {'ratios': ratios, 'fd_scale': round(pr / 5500.0, 4)}; o['top_kmh_est'] = round(233 * lim / 8000.0 / (pr / 5500.0))
    d = s.get('drive', '')
    if car == 'Hornet': o['diff'] = {'drive': 1, 'type': 0}
    elif car in ('207', 'Bowler', 'Enduro'): o['diff'] = {'drive': 2, 'type': 0, 'params': [0.2, 0.2, 0.0, 0.0]}
    else: o['diff'] = {'drive': 2, 'type': 4}
    if s.get('file'): o['file'] = s['file']
    o['src'] = s.get('src', [])
    out['cars'][car] = o
    out['misfits'] += ['%s: %s' % (car, m) for m in mis]
out['misfits'] += ['all: tyre width is not part of SR3s grip model (mu x load); per-car grip would need a per-car tyre class (only Tyre_Road and Tyre_AllTerrain are free) or a per-car grip field still to be found (ch13 1800 / 0.345 / 125, ch27 Topham parameters)',
                   'all: real ratios are not published: gears evenly spaced, final drive so that every car reaches the same road speed at its power peak as the Impreza WRC2008 at 5500 rpm (equal speed per power); the top speed at the limiter follows (top_kmh_est)',
                   'all: centre split field 0.56 kept: which axle it means is not known yet']
json.dump(out, open(dst, 'w'), indent=1)
for car, o in out['cars'].items():
    print('%-14s mass %5.0f torque %6.1f limit %5.0f gears %d fd x%.3f top ~%d km/h diff %s' % (car, o['mass'], o['torque_nm'], o['max_rpm'], len(o['gears']['ratios']), o['gears']['fd_scale'], o['top_kmh_est'], o['diff']))
print('\n'.join(out['misfits']))
