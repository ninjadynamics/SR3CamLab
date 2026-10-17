"""Drives a race along the track's own spline, for in-game tests (Bruno, 2026-10-15: "please use the game splines, because
I'm tired of seeing the car hitting the walls, driving like a blind cockroach").

    python tools\\autodrive.py [--seconds 60] [--laps N] [--quiet]     (in a race, with tools\\pad.py hook done)
    import autodrive; autodrive.drive(seconds=60)                      (from a test script)

The line: master_xdata's "DesignRouteSpline" (docs\\kb\\03_master_xdata_route.md: root [0x9DB48C] +0x18 -> {1, nSplines,
nMarkers, splines, markers}, spline {name, nPoints, points}; f32 xyz, 2 m apart, closed; root +0x30 = +1 if the race runs
towards increasing points, -1 the other way). The car: camera manager [0x9EB4EC] + 0x18, its +0x1C8 = the car; car +0xAC =
position, +0x135C = its matrix (rows right, up, forward at +0x00 / +0x10 / +0x20; kb game-runtime-and-frontend). Stadium4 has
no spline: refused.
Steering: Stanley (the line's heading 0.25 s ahead minus the car's, plus atan(2.5 x the distance to the line / speed)), a full
stick = 0.45 rad. Pure pursuit was tried first and cut the hairpins (its look-ahead reaches across them). Speed: each point's
corner speed sqrt(5.5 m/s2 x the radius of its bend, through the points 10 m back and ahead), braked for at 6.5 m/s2 over
the next 150 m; gas off and brake above it. In the game (2026-10-15, Championship stage 1, windowed, 70-75 s per run): about
2.1-2.3 km, up to 200 km/h, 3-7 m from the designer's line at worst, 1-2 "contacts" per run (18 km/h or more lost in 0.25 s
without braking: a wall, a car at the start, or a landing; the one at point ~300-310 of that stage comes back every run and
not with lower corner speeds, so it is the line or the ground there, not entry speed; not looked at yet: with the monitor off
no capture shows the game window).
The pad is TeknoParrot's XInput through tools\\pad.py's hook (its buffer written directly, 50 times a second); stick right = steer right.
This can actually be done with the game's own AI (an AI driver object on the player's car) the following way: the AI follows
the lanes of the AI map (kb 03) with its own throttle model; it's done this way because handing the player's car to the AI
needs code changes in the game we have not found yet, while the spline and the car's matrix are plain data. """
import ctypes, ctypes.wintypes as wt, json, math, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import pad as PAD
K = ctypes.WinDLL('kernel32', use_last_error=True); K.OpenProcess.restype = wt.HANDLE
K.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
K.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

class Game:
    def __init__(self):
        pid = PAD.pid_of('Rally.exe')
        if not pid: raise SystemExit('Rally.exe is not running')
        self.h = K.OpenProcess(0x0410, False, pid)
    def rd(self, a, n):
        b = ctypes.create_string_buffer(n); got = ctypes.c_size_t(0)
        return b.raw if a and K.ReadProcessMemory(self.h, a, b, n, ctypes.byref(got)) and got.value == n else None
    def u32(self, a): b = self.rd(a, 4); return struct.unpack('<I', b)[0] if b else 0
    def i32(self, a): b = self.rd(a, 4); return struct.unpack('<i', b)[0] if b else 0
    def f32(self, a, n): b = self.rd(a, 4 * n); return struct.unpack('<%df' % n, b) if b else None

class Pad:
    """TeknoParrot's pad 0 (tools\\pad.py hook), written in place: steer -1..1, gas / brake 0..1"""
    def __init__(self):
        st = json.load(open(PAD.STATE)); self.buf = st['buf']; self.packet = st.get('packet', 0)
        self.h = K.OpenProcess(0x1F0FFF, False, st['pid'])
        if not self.h: raise SystemExit('TeknoParrotUi is not running (tools\\pad.py hook first)')
    def set(self, steer=0.0, gas=0.0, brake=0.0, buttons=0):
        self.packet += 1; got = ctypes.c_size_t(0)
        d = struct.pack('<IHBBhhhh', self.packet, buttons, int(255 * max(0, min(1, brake))), int(255 * max(0, min(1, gas))), int(32767 * max(-1, min(1, steer))), 0, 0, 0)
        K.WriteProcessMemory(self.h, self.buf, d, len(d), ctypes.byref(got))

def spline(g):
    root = g.u32(0x9DB48C); sp = g.u32(root + 0x18) if root else 0
    if not sp: raise SystemExit('this track has no DesignRouteSpline (Stadium4), or no race is loaded')
    rec = g.u32(sp + 12); n = g.u32(rec + 4); pts = g.f32(g.u32(rec + 8), 3 * n)
    if not pts or n < 10: raise SystemExit('the spline could not be read')
    P = [(pts[3 * k], pts[3 * k + 1], pts[3 * k + 2]) for k in range(n)]
    if P[-1] == P[0]: P = P[:-1]                                         # (closed: the last point repeats the first)
    return P, (1 if g.i32(root + 0x30) >= 0 else -1)

def car(g):
    mgr = g.u32(0x9EB4EC); c = g.u32(mgr + 0x18 + 0x1C8) if mgr else 0
    if not c: return None
    p = g.f32(c + 0xAC, 3); m = g.f32(c + 0x135C, 12)
    if not p or not m: return None
    return p, m[0:3], m[8:11]

def wrap(x): return (x + math.pi) % (2 * math.pi) - math.pi            # an angle into -pi..pi
LAT, BRAKE, VTOP = 5.5, 6.5, 58.0          # m/s2 of side grip and of braking on gravel (tuned in the game), top speed m/s
KE, WHEEL = 2.5, 0.45                      # Stanley's pull onto the line (1/s), and the steering angle (rad) a full stick stands for
def corner_speeds(P):
    """per point: the fastest speed its bend allows, sqrt(side grip x radius); the radius of the circle through the points
    5 back and 5 ahead (10 m chords). Precomputed once; the loop brakes back from the slowest point ahead."""
    n = len(P); out = []
    for j in range(n):
        a, b, c = P[(j - 5) % n], P[j], P[(j + 5) % n]
        ab = math.hypot(b[0] - a[0], b[2] - a[2]); bc = math.hypot(c[0] - b[0], c[2] - b[2]); ca = math.hypot(a[0] - c[0], a[2] - c[2])
        cross = abs((b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0]))
        r = ab * bc * ca / (2 * cross) if cross > 1e-6 else 1e9           # the circle through three points
        out.append(min(VTOP, math.sqrt(LAT * r)))
    return out

def drive(seconds=60.0, laps=None, quiet=False, log=None, pad=None):
    """drives until seconds pass, laps are done (by the line's index), the menus come back or the car is gone; returns a summary.
    pad: any object with set(steer, gas, brake, buttons=0) (Codex's input path for the TeknoParrot-free route); TeknoParrot's by default."""
    g = Game(); pad = pad or Pad(); P, d = spline(g); n = len(P); say = log or (lambda *a: None if quiet else print(*a, flush=True))
    c = car(g)
    if not c: raise SystemExit('no car (not in a race?)')
    near = min(range(n), key=lambda k: (P[k][0] - c[0][0]) ** 2 + (P[k][2] - c[0][2]) ** 2)
    VC = corner_speeds(P)
    say('autodrive: %d spline points, direction %+d, the car near point %d' % (n, d, near))
    t0 = time.time(); last_p = c[0]; track = [(t0, c[0])]; v = 0.0; travelled = 0; worst = 0.0; slow = 0; hits = []; hist = []; brake = 0.0; off_at = 0.0
    try:
        while time.time() - t0 < seconds:
            if (g.rd(0x9D6E3C, 1) or b'\0')[0] == 1: say('autodrive: the menus are back'); break
            c = car(g)
            if not c: say('autodrive: the car is gone'); break
            pos, right, fwd = c; now = time.time()
            if pos != last_p: track.append((now, pos)); last_p = pos           # (a read inside the same game frame sees the car not moved: not a sample)
            track = [x for x in track if now - x[0] <= 0.3]
            if len(track) >= 2 and track[-1][0] - track[0][0] > 0.1:           # speed over the last 0.1-0.3 s
                v = math.hypot(track[-1][1][0] - track[0][1][0], track[-1][1][2] - track[0][1][2]) / (track[-1][0] - track[0][0])
            best = near; bd = 1e18
            for k in range(-30, 31):                                     # the nearest point, near the last one
                j = (near + k) % n; e = (P[j][0] - pos[0]) ** 2 + (P[j][2] - pos[2]) ** 2
                if e < bd: bd, best = e, j
            step = (best - near) * d
            if step < -n // 2: step += n
            if step > n // 2: step -= n
            travelled += step; near = best; worst = max(worst, math.sqrt(bd))
            if math.sqrt(bd) > 7.0 and now - off_at > 2.0: off_at = now; say('autodrive: %.1f m off the line at point %d, %d km/h' % (math.sqrt(bd), near, round(3.6 * v)))
            # Stanley: the line's heading a little ahead minus the car's, plus a pull back onto the line (left-handed world:
            # atan2(x, z) grows to the right, so both terms are "steer right" when positive)
            pre = int(max(2, min(10, 0.25 * v / 2)))                         # the line's heading 0.25 s ahead (4..20 m)
            a0, a1 = P[(near + d * pre) % n], P[(near + d * (pre + 3)) % n]
            herr = wrap(math.atan2(a1[0] - a0[0], a1[2] - a0[2]) - math.atan2(fwd[0], fwd[2]))
            lat = (P[near][0] - pos[0]) * right[0] + (P[near][2] - pos[2]) * right[2]
            steer = max(-1.0, min(1.0, (herr + math.atan2(KE * lat, v + 3.0)) / WHEEL))
            vmax_ms = min(math.sqrt(VC[(near + d * k) % n] ** 2 + 2 * BRAKE * 2 * k) for k in range(0, 76, 2))   # every bend of the next 150 m, braked for in time
            if v > vmax_ms + 2: gas, brake = 0.0, min(1.0, (v - vmax_ms) / 8.0)
            elif v > vmax_ms - 3: gas, brake = 0.55, 0.0
            else: gas, brake = 1.0, 0.0
            if now - t0 > 3 and v < 2.0: slow += 1
            hist.append((now, v, brake)); hist = [x for x in hist if now - x[0] <= 0.25]
            if len(hist) > 3 and hist[0][1] - v > 5.0 and max(x[2] for x in hist) < 0.3 and (not hits or now - hits[-1][0] > 1.0):
                hits.append((now, round(3.6 * hist[0][1]), round(3.6 * v), near))             # a contact: 18 km/h or more lost in 0.25 s, not braking
                say('autodrive: contact at point %d, %d -> %d km/h' % (near, hits[-1][1], hits[-1][2]))
            pad.set(steer, gas, brake)
            if laps and travelled >= laps * n: say('autodrive: %d lap(s) by the line' % laps); break
            time.sleep(0.02)
    finally:
        pad.set(0, 0, 0)
    s = dict(seconds=round(time.time() - t0, 1), metres=2 * travelled, worst_off_line_m=round(worst, 1), stuck_ticks=slow, last_kmh=round(3.6 * v),
             contacts=len(hits))                                       # (a contact: speed lost suddenly without braking: a wall, a car, a spin)
    say('autodrive: %s' % s); return s

if __name__ == '__main__':
    a = sys.argv[1:]
    drive(seconds=float(a[a.index('--seconds') + 1]) if '--seconds' in a else 60.0, laps=int(a[a.index('--laps') + 1]) if '--laps' in a else None, quiet='--quiet' in a)
