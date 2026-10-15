"""Handling numbers from a drive log (CSV with t, x, z, vx, vz [m/frame], psi or yaw, gear, acc, brk, steer).
python analyse.py <drive.csv> [--fps 60] [--speed-scale 216]
speed km/h = |(vx, vz)| * scale (SRC/SR2 logs in m/frame -> 216); a_lat from the turn rate of the velocity vector."""
import sys, csv, math, numpy as np
p = sys.argv[1]
args = sys.argv[2:]
scale = float(args[args.index('--speed-scale') + 1]) if '--speed-scale' in args else 216.0
R = list(csv.DictReader(open(p)))
R = [r for r in R if r.get('vx') not in (None, '')]
t = np.array([float(r['t']) for r in R]); rr = np.array([float(r['r']) for r in R])
vx = np.array([float(r['vx']) for r in R]); vz = np.array([float(r['vz']) for r in R])
v = np.hypot(vx, vz) * scale                                    # km/h
gear = np.array([int(float(r['gear'])) for r in R])
acc = np.array([float(r['acc']) for r in R]); brk = np.array([float(r['brk']) for r in R]); st = np.array([float(r['steer']) for r in R])
if acc.max() <= 1.5: acc = acc * 255; brk = brk * 255; st = 128 + st * 127                      # SR3 logs: inputs 0..1 / -1..1
psi = np.array([float(r['psi']) if r.get('psi') not in (None, '') else -float(r['w3c']) for r in R])
course = np.arctan2(vx, vz)
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
beta = np.where(v > 20, wrap(psi - course), 0.0)
dt = np.gradient(t)
dcourse = wrap(np.gradient(np.unwrap(course)))
vm = v / 3.6
alat = vm * np.gradient(np.unwrap(course)) / dt                 # m/s^2, signed
along = np.gradient(vm) / dt
def smooth(a, n):
    k = np.ones(n) / n; return np.convolve(a, k, mode='same')
alat_s = smooth(alat, 15); along_s = smooth(along, 15)
print('samples %d, %.1f s' % (len(t), t[-1] - t[0]))
# straight-line acceleration from the first throttle application
go = np.nonzero((acc > 200) & (rr >= 0))[0]
if len(go) and v[go[0]] < 5:                                     # only for a standing start
    i0 = go[0]
    moving = np.nonzero(v[i0:] > 1)[0]
    if len(moving):
        i0 = i0 + moving[0]
        for target in (50, 100, 150, 180, 200):
            k = np.nonzero(v[i0:] >= target)[0]
            if len(k): print('  0-%d km/h: %.2f s' % (target, t[i0 + k[0]] - t[i0]))
        ch = np.nonzero(np.diff(gear[i0:i0 + 900]) != 0)[0]
        for c in ch[:6]:
            j = i0 + c
            print('  gear %d -> %d at %.1f km/h (t+%.2f s)' % (gear[j], gear[j + 1], v[j], t[j] - t[i0]))
print('  max speed %.1f km/h; 99th pct %.1f' % (v.max(), np.percentile(v, 99)))
# speed / rpm per gear (if rpm logged)
if 'rpm' in R[0]:
    rpm = np.array([float(r['rpm']) for r in R])
    for g in sorted(set(gear)):
        m = (gear == g) & (v > 30) & (rpm > 2000) & (np.abs(beta) < 0.03)
        if m.sum() > 30:
            ratio = np.median(v[m] / rpm[m]) * 1000
            print('  gear %d: %.1f km/h per 1000 rpm, rpm max %.0f, speed max in gear %.1f' % (g, ratio, rpm[gear == g].max(), v[gear == g].max()))
# braking
bm = (brk > 200) & (v > 40)
if bm.sum() > 20: print('  braking decel (median while braking, >40 km/h): %.1f m/s^2 = %.2f g' % (-np.median(along_s[bm]), -np.median(along_s[bm]) / 9.81))
# lateral grip
ok = (v > 40)
a = np.abs(alat_s[ok])
print('  lateral accel |a_lat| (0.25 s smoothed, v>40): p50 %.1f  p90 %.1f  p98 %.1f  max %.1f m/s^2  (p98 = %.2f g)' % (np.percentile(a, 50), np.percentile(a, 90), np.percentile(a, 98), a.max(), np.percentile(a, 98) / 9.81))
# sustained cornering: rolling median over 0.5 s, impacts (|a_long| > 12 m/s^2 nearby) left out
def rollmed(a, n):
    out = np.empty_like(a); h = n // 2
    for i in range(len(a)): out[i] = np.median(a[max(0, i - h):i + h + 1])
    return out
med = rollmed(np.abs(alat), 30)
imp = np.convolve((np.abs(along) > 12).astype(float), np.ones(30), mode='same') > 0
okc = ok & ~imp
if okc.sum() > 100:
    print('  sustained a_lat (0.5 s median, no impacts): p90 %.1f  p95 %.1f  p99 %.1f m/s^2  (p95 = %.2f g)' % (np.percentile(med[okc], 90), np.percentile(med[okc], 95), np.percentile(med[okc], 99), np.percentile(med[okc], 95) / 9.81))
# slip angle / slides
b = np.degrees(np.abs(beta))
print('  slip angle |beta| (v>40): p50 %.1f  p90 %.1f  p98 %.1f deg; time >5 deg %.0f%%, >10 deg %.0f%%' % (np.percentile(b[ok], 50), np.percentile(b[ok], 90), np.percentile(b[ok], 98), 100 * np.mean(b[ok] > 5), 100 * np.mean(b[ok] > 10)))
# slide events: |beta| rises above 8 deg, until it falls below 3 deg
ev = []; i = 0
while i < len(b):
    if b[i] > 8 and v[i] > 40:
        j = i
        while j > 0 and b[j - 1] > 3: j -= 1
        k = i
        while k < len(b) - 1 and b[k] > 3: k += 1
        pk = j + int(np.argmax(b[j:k + 1]))
        ev.append((t[j] - t[0], t[pk] - t[j], t[k] - t[pk], b[pk], v[j], v[k], np.mean(st[j:k + 1]) - 128))
        i = k + 1
    else: i += 1
print('  slides (beta > 8 deg): %d' % len(ev))
for e in ev[:12]:
    print('    at %.1f s: build-up %.2f s, peak %.1f deg, recovery %.2f s, speed %.0f -> %.0f km/h, mean steer %+.0f' % (e[0], e[1], e[3], e[2], e[4], e[5], e[6]))
if ev:
    E = np.array(ev)
    print('  median slide: build-up %.2f s, peak %.1f deg, recovery %.2f s' % (np.median(E[:, 1]), np.median(E[:, 3]), np.median(E[:, 2])))
# steady cornering: slip angle vs lateral accel (how much the car drifts per g)
m = ok & (np.abs(alat_s) > 3) & (np.abs(alat_s) < 40)
if m.sum() > 50:
    g = np.abs(alat_s[m]) / 9.81; bb = b[m]
    for lo, hi in ((0.3, 0.6), (0.6, 0.9), (0.9, 1.2), (1.2, 1.6), (1.6, 2.5)):
        s = (g >= lo) & (g < hi)
        if s.sum() > 20: print('    a_lat %.1f-%.1f g: median slip %.1f deg (%d samples)' % (lo, hi, np.median(bb[s]), s.sum()))
