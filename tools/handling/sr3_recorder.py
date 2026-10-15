"""SEGA Rally 3 (Rally.exe) handling recorder v3: READ-ONLY, one CSV row per physics step (~63 per second), race only.

    python sr3_recorder.py [--out sr3_lap.csv] [--seconds 0 (= until Ctrl+C)] [--all (also rows outside a race)]

Columns match analyse.py / surf_split.py (t, r, acc, steer, brk, gear, x, y, z, vx, vy, vz, w38, w3c, w40, rpm, wspd, psi);
velocities in metres per 1/60 s like the Model 2 logs (analyse.py x216 = km/h). Once a second it prints the live values.

Where the values come from (static analysis of Rally.exe, 2026-10-14):
  race     [0x728598] mode 5/6/7 (Quick Race, Championship, Classic) and [0x7ECE10] main state 0x27 (racing); other rows are
           marked valid = 0 and not written unless --all (the replay / attract loop runs in other modes)
  player   car records 0x9DBAC8 + 0x1F18 x i (i < 6); record + 4 = its driver object (written by the car setup at 0x5B1240);
           the human driver has vtable 0x6ED0C8 (constructed at 0x5E73B0, 0x87B8 bytes) and driver + 0x7E4 = its record
  controls driver + 0x854 (what 0x5E9D20 passes to 0x5E4430 and 0x5CFE90): +0x08 input mode, +0x0C brake, +0x10
           handbrake (0 / 1), +0x14 accelerator, +0x18 steering (after 0x5D4D10: shaped, speed limited), +0x1C speed lock
           factor (code 0x5E4476..; accelerator / brake VERIFIED in game 2026-10-14 with pad.py); flags at driver + 0x1C08
  inputs   driver + 0x1C84: bytes [0], [1] the steering pair (value = [1] - [0]), [2] accelerator, [3] brake, [4] handbrake
  end      the race is over (rows stop, the recorder exits) when the game drives the car itself: [0x9EB390] != 0 (0x5E9F04: then
           0x5EE350 fills the input bytes from a recorded / AI source; LIKELY the after-race drive), or when the car's elapsed
           time (record + 0x1DA0, ms) reaches the time limit [0x9DB4C8] (time over; 03_master_xdata_route.md)
  vehicle  [[driver + 0x858] + 4] (CVehicle, vtable 0x678864): +0x10 engine, +0x18 gears (vtable 0x677FDC), gear index =
           [gears + 8]: written as gear = index - 1 (1..n forward, 0 neutral / between gears while shifting, -1 reverse:
           VERIFIED in game); rpm = engine + 0x18 (rad/s) x 60/2pi (VERIFIED in game; also what the automatic gearbox 0x45E660
           compares with engine + 0x40, the max rad/s)
  position the camera manager's car matrix [[0x9EB4EC] + 0x18 + 0x1C8] + 0x135C (VERIFIED live); only trusted while racing
Nothing is written to the game; OpenProcess asks for PROCESS_VM_READ | PROCESS_QUERY_INFORMATION only."""
import ctypes, ctypes.wintypes as W, struct, sys, time, math, argparse, subprocess

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = W.HANDLE
k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
VT_DRIVER, VT_VEHICLE, VT_GEARS = 0x6ED0C8, 0x678864, 0x677FDC
RECORDS, STRIDE, N_REC = 0x9DBAC8, 0x1F18, 6

def pid_of(name='rally.exe'):
    out = subprocess.run(['tasklist', '/fo', 'csv', '/nh'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        p = [x.strip('"') for x in line.split('","')]
        if p and p[0].lower() == name: return int(p[1])

class Proc:
    def __init__(self, pid):
        self.h = k32.OpenProcess(0x10 | 0x400, False, pid)
        if not self.h: raise OSError('OpenProcess failed (%d)' % ctypes.get_last_error())
    def read(self, a, n):
        if not a: return None
        b = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        ok = k32.ReadProcessMemory(self.h, ctypes.c_void_p(a), b, n, ctypes.byref(got))
        return b.raw if ok and got.value == n else None
    def u32(self, a):
        d = self.read(a, 4); return struct.unpack('<I', d)[0] if d else 0
    def f32(self, a):
        d = self.read(a, 4); return struct.unpack('<f', d)[0] if d else 0.0

def racing(p): return p.u32(0x728598) in (5, 6, 7) and p.u32(0x7ECE10) == 0x27
def race_over(p, rec):
    lim = p.u32(0x9DB4C8); el = p.u32(rec + 0x1DA0)
    return p.u32(0x9EB390) != 0 or (lim > 0 and el >= lim), el, lim

def locate(p):
    drv = rec = None
    for i in range(N_REC):
        r = RECORDS + STRIDE * i; d = p.u32(r + 4)
        if d and p.u32(d) == VT_DRIVER and p.u32(d + 0x7E4) == r: rec, drv = r, d; break
    if not drv: return None
    mgr = p.u32(0x9EB4EC); cam = p.u32(mgr + 0x18 + 0x1C8) if mgr else 0
    veh = p.u32(p.u32(drv + 0x858) + 4)
    parts = {'rec': rec, 'drv': drv, 'ctl': drv + 0x854, 'cam': cam, 'veh': None, 'eng': None, 'gears': None}
    if veh and p.u32(veh) == VT_VEHICLE:
        parts['veh'] = veh; parts['eng'] = p.u32(veh + 0x10)
        g = p.u32(veh + 0x18); parts['gears'] = g if p.u32(g) == VT_GEARS else None
    return parts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='sr3_lap_%s.csv' % time.strftime('%Y%m%d_%H%M%S'))
    ap.add_argument('--seconds', type=float, default=0.0); ap.add_argument('--all', action='store_true')
    a = ap.parse_args()
    pid = pid_of()
    if not pid: sys.exit('Rally.exe is not running')
    p = Proc(pid)
    try: ctypes.WinDLL('winmm').timeBeginPeriod(1)
    except OSError: pass
    parts = None
    while not parts or not parts['cam']:
        parts = locate(p)
        if not parts or not parts['cam']: print('  player not found yet (start a race); trying again in 2 s'); time.sleep(2)
    print('  record %#x (player %d) driver %#x controls %#x vehicle %s gears %s camera car %#x; writing %s' % (
        parts['rec'], (parts['rec'] - RECORDS) // STRIDE, parts['drv'], parts['ctl'], hex(parts['veh'] or 0), hex(parts['gears'] or 0), parts['cam'], a.out))
    f = open(a.out, 'w', newline='')
    eng_cols = ['e%02x' % o for o in range(0x10, 0x38, 4)]
    f.write(','.join(['t', 'r', 'acc', 'steer', 'brk', 'gear', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'w38', 'w3c', 'w40', 'rpm', 'wspd', 'psi',
                      'hb', 'lockf', 'mode', 'flags', 'in0', 'in1', 'in_acc', 'in_brk', 'in_hb', 'g08', 'valid', 'elapsed_ms', 'limit_ms'] + eng_cols + ['step_rate', 'host_t']) + '\n')
    t0 = time.perf_counter(); last = None; hist = []; pending = None; n = 0; misses = 0; next_print = 0.0; relocate = 0.0; seen_race = False
    try:
        while True:
            now = time.perf_counter() - t0
            if now > relocate:                                               # a new race makes new objects
                relocate = now + 1.0; q = locate(p)
                if q and q['cam']: parts = q
            m = p.read(parts['cam'] + 0x135C, 0x40)
            if m is None:
                misses += 1
                if misses > 4000: print('  car gone'); break
                time.sleep(0.0005); continue
            if m == last: time.sleep(0.0003); continue
            last = m; misses = 0
            R = struct.unpack('<16f', m); pos = R[12:15]
            hist.append((now, pos)); hist = hist[-200:]
            if len(hist) < 3: continue
            span = hist[-1][0] - hist[0][0]; rate = (len(hist) - 1) / span if span > 0 else 63.0
            (_, p0), (tm, p1), (_, p2) = hist[-3], hist[-2], hist[-1]
            vel = [(p2[i] - p0[i]) * rate / 2.0 for i in range(3)]                    # m/s at the middle step
            ctl = p.read(parts['ctl'] + 8, 0x18) or b'\0' * 0x18
            mode, brk, hb, acc, steer, lockf = struct.unpack('<I5f', ctl)
            inp = p.read(parts['drv'] + 0x1C84, 5) or b'\0' * 5
            flags = p.u32(parts['drv'] + 0x1C08)
            gear = p.u32(parts['gears'] + 8) if parts['gears'] else -1
            eng = struct.unpack('<10f', p.read(parts['eng'] + 0x10, 40) or b'\0' * 40) if parts['eng'] else (0.0,) * 10
            rpm = eng[2] * 60 / (2 * math.pi)
            fx, fy, fz = R[8:11]; ry = R[1]
            psi = math.atan2(fx, fz); pitch = math.asin(max(-1, min(1, fy))); roll = math.asin(max(-1, min(1, ry)))
            over, el, lim = race_over(p, parts['rec'])
            ok = racing(p) and not over
            if over and seen_race and not a.all:
                print('  race over (elapsed %d ms, limit %d ms, auto-drive %d): stopping' % (el, lim, p.u32(0x9EB390))); break
            seen_race = seen_race or ok
            row = ','.join(['%.4f' % tm, '%.4f' % tm, '%.4f' % acc, '%.4f' % steer, '%.4f' % brk, str(gear - 1 if gear >= 1 else gear),
                            '%.4f' % p1[0], '%.4f' % p1[1], '%.4f' % p1[2]] + ['%.6g' % (v / 60.0) for v in vel] +
                           ['%.5f' % pitch, '%.5f' % (-psi), '%.5f' % roll, '%.1f' % rpm, '0', '%.5f' % psi,
                            '%.4f' % hb, '%.4f' % lockf, '%d' % mode, '%d' % flags] + ['%d' % b for b in inp] + [str(gear), '1' if ok else '0', str(el), str(lim)] +
                           ['%.5g' % x for x in eng] + ['%.2f' % rate, '%.4f' % now]) + '\n'
            if pending and (pending[1] or a.all): f.write(pending[0]); n += 1
            pending = (row, ok)
            if now >= next_print:
                next_print = now + 1.0; f.flush()
                print('  %6.1f s %s %5.0f km/h | acc %.2f brk %.2f steer %+.2f hb %.0f lock %.2f mode %d | bytes %s | gear %d rpm %.0f | time %d/%d ms | e10..e1c %s' % (
                    now, 'RACE' if ok else 'not racing', math.sqrt(vel[0] ** 2 + vel[2] ** 2) * 3.6, acc, brk, steer, hb, lockf, mode,
                    ' '.join('%3d' % b for b in inp), gear - 1, rpm, el, lim, ' '.join('%.1f' % x for x in eng[:4])))
            if a.seconds and now > a.seconds: break
    except KeyboardInterrupt: pass
    if pending and (pending[1] or a.all): f.write(pending[0]); n += 1
    f.close(); print('%d rows written to %s' % (n, a.out))

if __name__ == '__main__': main()
