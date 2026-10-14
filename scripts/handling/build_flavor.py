"""Build a handling flavor's car files and grip file from the owner's own SR3 files.  Only the numbers table ships.

    python build_flavor.py <numbers.json> --game "F:\\...\\Rally" --out <staging Rally folder> [--force-model 1|2] [--cars ST205,Delta_HF]
                           [--torque-scale x] [--grip-scale x] [--check]

Writes   <out>\\Main_release\\car<digit>\\<car>bespoke_data.sbf   (all ten cars, or --cars)
         <out>\\SurfacePairEffect<digit>\\surfacepairdata_xdata.sbf  (SEGA's file with the flavor's tyre records changed)
The game reads them when the launcher turns the 's' of "cars" (0x6C631D) and of "Effects" (0x6C6176) into the digit.

What is changed in each car file (chunk = index in SEGA's 42-chunk layout, checked by shape before writing):
  ch4  engine        +0x08 peak torque x torque_scale, +0x0C max rpm
  ch7  gears         +0x0C count (= forward + 2), ratios R, N, forward from km/h per 1000 rpm with the car's own wheel
                     radius (ch26 +0x28) and final drive (kept): ratio = 376.99 x r / (FD x v)
  ch8  auto gearbox  upshift / downshift fractions of max rpm
  ch14 tyre type     "Tyre_Rally" -> the flavor's tyre name (its records are the flavor's grip, in the grip file)
  ch27 tyre forces   +0x08 force model (0 Standard, 1 SegaRally, 2 PowerslideSteer = SR3's own, 3 AlwaysSteer)
Pace (a table with "pace": "sr3", Realism's default; the owner, 2026-10-14: "add a multiplier that matches the accel and
speed with SR3 default"): each car's peak torque (and clutch) is scaled so that a launch model run on the built file gives
the 0-100 and 0-150 km/h times the same model gives for SEGA's own file of that car (pace_scale), and a car with a design top
speed gets SEGA's file's top speed at the limiter instead. The model (launch_times): torque curve x peak x gear x final drive
/ wheel radius x 0.55, over the mass plus the wheels' and the engine's inertia, SEGA's shift points and shift time; fitted to
the game (2026-10-14): ST205 SEGA 1.36 / 3.24 s to 50 / 100 (measured 1.21 / 3.42), SRC test 4 0.67 / 1.48 / 2.49 / 3.30 s
to 50 / 100 / 150 / 180 (measured 0.62 / 1.44 / 2.50 / 3.12). "pace": "real" keeps the real torque.
Grip file: records <tyre>_<surface>[_Top|_Base] get  SR3's Tyre_Rally_Tarmac_<same layer> x ratio x grip_scale  for the
grouped surfaces, SR3's Tyre_Rally_<surface> x grip_scale for the rest. SR3's own Tyre_Rally records are not touched."""
import sys, os, json, struct, argparse, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'importer'))
from sbfw import read_sbf, write_sbf
CARS = ['C4', 'RSFocus', 'SubaruImpreza', 'SX4', 'MitsubishiEvo', '207', 'ST205', 'Delta_HF', 'Bowler', 'Enduro']
F = lambda c, o: struct.unpack_from('<f', c.data, o)[0]
U = lambda c, o: struct.unpack_from('<I', c.data, o)[0]
def setf(c, o, v): b = bytearray(c.data); struct.pack_into('<f', b, o, v); c.data = bytes(b)
def setu(c, o, v): b = bytearray(c.data); struct.pack_into('<I', b, o, v); c.data = bytes(b)

def rewrite(f):
    """bytes of f with SEGA's own layout and trailer (byte-identical when nothing was changed)"""
    tail = f.raw[len(f.raw) - f.tail:] if f.tail else 0
    f2 = type(f)(); f2.__dict__.update(f.__dict__); f2.tail = tail
    return write_sbf(f2, layout='keep')

def check_layout(f, name):
    ch = f.chunks
    ok = (len(ch) == 42 and len(ch[4].data) == 32 and len(ch[7].data) == 52 and ch[7].fix == [0x10] and len(ch[8].data) == 96
          and ch[14].data[0x18:0x22] == b'Tyre_Rally' and len(ch[27].data) == 48 and len(ch[26].data) == 180)
    if not ok: raise SystemExit('%s: not the layout this script knows; nothing written' % name)

def set_gears(ch, rat_fwd, reverse=None):
    rat = [reverse if reverse is not None else F(ch[7], 0x14), 0.0] + list(rat_fwd)
    if len(rat) > 8: raise SystemExit('at most 6 forward gears fit chunk 7')
    rat += [rat_fwd[-1]] * (8 - len(rat))
    setu(ch[7], 0x0C, len(rat_fwd) + 2)
    for i, x in enumerate(rat): setf(ch[7], 0x14 + 4 * i, x)

def set_curve(ch, tc):
    c3 = ch[3]
    if len(tc) != U(c3, 4): raise SystemExit('torque_curve must have %d points' % U(c3, 4))
    for i, (a, b) in enumerate(tc): setf(c3, 0x08 + 8 * i, a); setf(c3, 0x0C + 8 * i, b)

def shift_points(ch, g):
    """ch8 automatic gearbox: ups[] and downs[] are indexed by the current gear index (0 R, 1 N, 2 first ...; read at
    0x45E660 against engine rad/s / max rad/s). Each gear's downshift point is kept below the rpm the upshift into that gear
    leaves (up x ratio / previous ratio - margin), or the gearbox hunts (SRC test 1: 1st <-> 2nd at 70 km/h)."""
    c8 = ch[8]; n_up, p_up, n_dn, p_dn = U(c8, 4), U(c8, 8), U(c8, 0xC), U(c8, 0x10)
    up = g.get('upshift_fraction', F(c8, p_up + 8)); down = g.get('downshift_fraction', F(c8, p_dn + 8)); margin = g.get('downshift_margin', 0.08)
    n = U(ch[7], 0xC); rat = [F(ch[7], 0x14 + 4 * i) for i in range(n)]
    per = g.get('upshift_fraction_per_gear') or []                       # 1st, 2nd, ... (gear index 2, 3, ...)
    ups = [per[i - 2] if 2 <= i < 2 + len(per) else up for i in range(max(n_up, n_dn))]
    for i in range(n_up): setf(c8, p_up + 4 * i, ups[i])
    for i in range(n_dn):
        d = down
        if 3 <= i < n and rat[i - 1] > 0: d = min(down, ups[i - 1] * rat[i] / rat[i - 1] - margin)
        setf(c8, p_dn + 4 * i, round(d, 3))

def car_params(ch):
    n = U(ch[3], 4); ng = U(ch[7], 0xC); c8 = ch[8]
    return dict(mass=F(ch[0], 4), curve=[(F(ch[3], 8 + 8 * i), F(ch[3], 12 + 8 * i)) for i in range(n)], T=F(ch[4], 8), rpm=F(ch[4], 0xC),
                Ie=F(ch[4], 0x18), fd=F(ch[7], 4), shift=F(ch[7], 8), ratios=[F(ch[7], 0x14 + 4 * i) for i in range(2, ng)],
                ups=[F(c8, U(c8, 8) + 4 * i) for i in range(U(c8, 4))], r=F(ch[26], 0x28), Iw=F(ch[13], 0x1C))
def top_kmh(p): return p['rpm'] * 0.10472 * p['r'] / (p['ratios'][-1] * p['fd']) * 3.6
def launch_times(p, scale=1.0, eta=0.55, launch=0.3):
    """seconds to 100 and 150 km/h (None if not reached in 30 s); see Pace in the header"""
    def tq(x):
        c = p['curve']
        if x <= c[0][0]: return c[0][1]
        for (a, va), (b, vb) in zip(c, c[1:]):
            if x <= b: return va + (vb - va) * (x - a) / max(1e-9, b - a)
        return c[-1][1]
    v = t = sh = 0.0; g = 0; dt = 1 / 600.0; wmax = p['rpm'] * 0.10472; out = {}
    while t < 30 and len(out) < 2:
        k = p['ratios'][g] * p['fd'] / p['r']; we = v * k
        if sh > 0: sh -= dt; f = 0.0
        else: f = p['T'] * scale * tq(min(max(we / wmax, launch if g == 0 else 0.0), 1.0)) * k * eta if we < wmax else 0.0
        v += f / (p['mass'] + 4 * p['Iw'] / p['r'] ** 2 + p['Ie'] * k * k) * dt; t += dt
        up = p['ups'][g + 2] if g + 2 < len(p['ups']) else 0.91
        if g + 1 < len(p['ratios']) and we / wmax >= up: g += 1; sh = p['shift']
        for m in (100, 150):
            if m not in out and v * 3.6 >= m: out[m] = t
    return out.get(100), out.get(150)
def pace_scale(stock, built):
    """torque factor that makes the built car's 0-100 + 0-150 equal the stock car's (bisection; slower = larger sum)"""
    s100, s150 = launch_times(stock)
    def gap(k):
        a, b = launch_times(built, k); return (a or 30) + (b or 30) - s100 - s150
    lo, hi = 0.2, 6.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if gap(mid) > 0: lo = mid
        else: hi = mid
    return (lo + hi) / 2

def build_car(path, T, args, car):
    """flavor-wide settings (gearbox / engine / tyre / force_model), then the car's own row of T['cars'] if there is one"""
    f = read_sbf(path); check_layout(f, os.path.basename(path))
    ch = f.chunks; g = T.get('gearbox'); e = T.get('engine'); ty = T.get('tyre'); P = (T.get('cars') or {}).get(car, {})
    r = F(ch[26], 0x28); fd = F(ch[7], 4)
    if g:
        set_gears(ch, [376.99 * r / (fd * v) for v in g['forward_kmh_per_1000rpm']], g.get('reverse_ratio'))
    if e:
        ts = args.torque_scale if args.torque_scale is not None else e.get('torque_scale', 1.0)
        setf(ch[4], 0x08, F(ch[4], 0x08) * ts)
        setf(ch[6], 0x08, F(ch[6], 0x08) * max(1.0, ts))                  # clutch capacity (2000, LIKELY Nm) follows the torque
        if e.get('max_rpm'): setf(ch[4], 0x0C, float(e['max_rpm']))
        if e.get('torque_curve'): set_curve(ch, e['torque_curve'])
    if P:                                                                   # per-car row (Realism)
        if 'mass' in P: setf(ch[0], 4, P['mass'])
        for k, o in zip(P.get('inertia_scale', ()), (8, 0xC, 0x10)): setf(ch[0], o, F(ch[0], o) * k)
        if 'torque_nm' in P: setf(ch[4], 8, P['torque_nm'] * (args.torque_scale or 1.0))
        if 'torque_nm' in P: setf(ch[6], 0x08, F(ch[6], 0x08) * max(1.0, F(ch[4], 8) / 870.0))   # clutch capacity follows the torque (SEGA's 2000 for 870)
        if 'max_rpm' in P: setf(ch[4], 0xC, P['max_rpm'])
        if 'torque_curve' in P: set_curve(ch, P['torque_curve'])
        if 'gears' in P:
            gr = P['gears']; set_gears(ch, gr['ratios'])
            if 'top_kmh' in gr: setf(ch[7], 4, F(ch[4], 0xC) / 1000.0 * 376.99 * r / (gr['ratios'][-1] * gr['top_kmh']))   # design top speed at the limiter
            else: setf(ch[7], 4, fd * gr.get('fd_scale', 1.0))
        if 'diff' in P:
            dd = P['diff']; setu(ch[10], 4, dd['drive']); setu(ch[10], 8, dd['type'])
            for k, x in enumerate(dd.get('params', ())): setf(ch[10], 0xC + 4 * k, x)
        if 'wheel_inertia' in P:
            for i in (13, 17, 20, 23): setf(ch[i], 0x1C, P['wheel_inertia'])
        if 'tyre' in P: ty = {'name': P['tyre']}
    shift_points(ch, g or {})
    if ty:
        name = ty['name'].encode()
        b = bytearray(ch[14].data); b[0x18:0x18 + 12] = (name + b'\0' * 12)[:12]; ch[14].data = bytes(b)
    fm = args.force_model if args.force_model is not None else P.get('force_model', T.get('force_model', 2))
    setu(ch[27], 0x08, int(fm))
    n = U(ch[7], 0xC) - 2
    c8 = ch[8]; downs = [round(F(c8, U(c8, 0x10) + 4 * i), 2) for i in range(2, n + 2)] + ['up'] + [round(F(c8, U(c8, 8) + 4 * i), 3) for i in range(2, n + 2)]
    return rewrite(f), dict(radius=r, fd=F(ch[7], 4), ratios=[round(F(ch[7], 0x1C + 4 * i), 3) for i in range(n)], torque=F(ch[4], 8), rpm=F(ch[4], 0xC), downs=downs,
                            mass=F(ch[0], 4), force_model=fm, diff=(U(ch[10], 4), U(ch[10], 8)))
def build_grip(path, T, args):
    f = read_sbf(path)
    c = [x for x in f.chunks if x.id == 0x6172a752][0]; d = bytearray(c.data)
    recs = {}; o = 8
    while True:                                                            # linked list {next, mu, ..., name}
        nxt = struct.unpack_from('<I', d, o)[0]; end = nxt if o in c.fix else len(d)
        runs = list(re.finditer(rb'[A-Za-z_][ -~]{3,}', bytes(d[o + 4:end])))
        if runs: recs[runs[-1].group().decode()] = o + 4                  # offset of the record's mu
        if o not in c.fix: break
        o = nxt
    ty = T['tyre']; gs = args.grip_scale if args.grip_scale is not None else ty.get('grip_scale', 1.0)
    group_of = {s: g for g, ss in ty['groups'].items() for s in ss}
    mu = lambda n: struct.unpack_from('<f', d, recs[n])[0]
    changed = []
    for n in sorted(recs):
        m = re.match(r'Tyre_Rally_(.+?)(_Top|_Base)?$', n)
        if not m: continue
        surf, layer = m.group(1), m.group(2) or ''
        target = '%s_%s%s' % (ty['name'], surf, layer)
        if target not in recs: continue
        if surf in group_of:
            ref = 'Tyre_Rally_Tarmac' + (layer or '_Top')
            v = mu(ref) * ty['surface_ratio_to_tarmac'][group_of[surf]] * gs
        else: v = mu(n) * gs
        struct.pack_into('<f', d, recs[target], v); changed.append((target, round(v, 3)))
    c.data = bytes(d)
    return rewrite(f), changed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('table'); ap.add_argument('--game', default=r'F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally')
    ap.add_argument('--out', required=True); ap.add_argument('--cars', default='')
    ap.add_argument('--force-model', type=int); ap.add_argument('--torque-scale', type=float); ap.add_argument('--grip-scale', type=float)
    args = ap.parse_args()
    T = json.load(open(args.table, encoding='utf-8-sig')); dg = T['folder_digit']
    if os.path.abspath(args.out).lower().startswith(os.path.abspath(args.game).lower()):
        raise SystemExit('--out lies inside the game folder: build into a staging folder; installing is the launcher\'s job')
    out_cars = os.path.join(args.out, 'Main_release', 'car' + dg); os.makedirs(out_cars, exist_ok=True)
    extra = [c for c, p in (T.get('cars') or {}).items() if p.get('file')]          # added cars (Hornet: <name>gravel_data)
    want = [c.lower() for c in args.cars.split(',') if c]
    for car in [c for c in CARS + extra if not want or c.lower() in want]:
        fn = (T['cars'][car]['file'] if car in extra else car.lower() + 'bespoke_data.sbf')
        src = os.path.join(args.game, 'Main_release', 'cars', fn)
        if not os.path.exists(src): print('%-14s %s not found: skipped' % (car, fn)); continue
        f0 = read_sbf(src)                                   # round trip: SEGA's file rewritten unchanged gives the same bytes
        if read_sbf(rewrite(f0)).raw != f0.raw: raise SystemExit('%s: round trip differs; nothing written' % car)
        data, info = build_car(src, T, args, car)
        if T.get('pace') == 'sr3' and car in (T.get('cars') or {}):            # Realism at SEGA's pace for this car
            stock = car_params(f0.chunks); row = T['cars'][car]
            if 'top_kmh' in row.get('gears', {}):
                row = dict(row); row['gears'] = dict(row['gears'], top_kmh=round(top_kmh(stock), 1)); T2 = dict(T, cars=dict(T['cars'], **{car: row}))
                data, info = build_car(src, T2, args, car)
            k = pace_scale(stock, car_params(read_sbf(data).chunks)) * row.get('pace_trim', 1.0)   # pace_trim: a measured correction (realism_map.py)
            t_args = argparse.Namespace(**dict(vars(args), torque_scale=k * (args.torque_scale or 1.0)))
            data, info = build_car(src, T2 if 'top_kmh' in T['cars'][car].get('gears', {}) else T, t_args, car)
            built = car_params(read_sbf(data).chunks)
            print('%-14s pace sr3: torque x%.3f -> 0-100 / 0-150 %.2f / %.2f s (SEGA file %.2f / %.2f), top %.0f km/h (SEGA file %.0f)' % ((car, k) + launch_times(built) + launch_times(stock) + (top_kmh(built), top_kmh(stock))))
        open(os.path.join(out_cars, fn), 'wb').write(data)
        print('%-14s mass %4.0f FD %.2f ratios %s down %s torque %.0f rpm %.0f diff %s fm %d' % (car, info['mass'], info['fd'], info['ratios'], info['downs'], info['torque'], info['rpm'], info['diff'], info['force_model']))
    if T.get('tyre'):
        data, changed = build_grip(os.path.join(args.game, 'SurfacePairEffects', 'surfacepairdata_xdata.sbf'), T, args)
        gdir = os.path.join(args.out, 'SurfacePairEffect' + dg); os.makedirs(gdir, exist_ok=True)
        open(os.path.join(gdir, 'surfacepairdata_xdata.sbf'), 'wb').write(data)
        print('grip file: %d %s records set, e.g. %s' % (len(changed), T['tyre']['name'], changed[:4]))
    else: print('grip file: none (the flavor keeps SR3\'s tyre records)')

if __name__ == '__main__': main()