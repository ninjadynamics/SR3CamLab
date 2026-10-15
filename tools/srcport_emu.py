"""Runs the SRC turning port (build_srcport.py's blob, relocated the way sr3mods.ps1 does it) on an emulated CPU inside a
copy of Rally.exe's image, on a made-up car, and checks it against srcmodel.py (kb 29's chain in Python).

    python srcport_emu.py [--game <Rally folder>]        the last line counts the checks

The game's vehicle step 0x45C820 is replaced by a stub in the emulated image (SR3 adds nothing, or adds a made-up
"SR3 turn" the port must throw away); SetVelocity 0x45A120 / SetAngularVelocity 0x45A1A0 are the game's own code.
The made-up world: y up, the car's yaw psi, x (right) = (cos psi, 0, -sin psi), z (forward) = (sin psi, 0, cos psi);
a positive yaw rate turns the nose toward +x (the port's x_sign = yaw_sign = +1 case)."""
import os, sys, math, struct, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EIP
import build_srcport as B
import srcmodel as M
ap = argparse.ArgumentParser(); ap.add_argument('--game', default=r'F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally'); A = ap.parse_args()
EXE = os.path.join(A.game, 'Rally.exe')
blob, ENTRY, DATA, RELOCS, CLS = B.build(A.game)
CAVE, OBJ, STACK, RET = 0x10000000, 0x20000000, 0x30000000, 0x3FFFF000
img = open(EXE, 'rb').read()
SECS = [(0x1000, 0x1000, 0x273000), (0x274000, 0x274000, 0x93000), (0x307000, 0x307000, 0x24000)]
TARMAC = next(i for i, (n, k, w) in enumerate(CLS) if n == 'Tyre_Road_Tarmac_Top')
GRAVEL = next(i for i, (n, k, w) in enumerate(CLS) if n == 'Tyre_Road_Gravel_Top')
RALLY = next(i for i, (n, k, w) in enumerate(CLS) if n == 'Tyre_Rally_Tarmac_Top')
VEH, BODY, CTL, LIST, DRV, WRAP = OBJ, OBJ + 0x1000, OBJ + 0x2000, OBJ + 0x3000, OBJ + 0x4000, OBJ + 0xC000
REC0 = 0x9DBAC8

def machine(stub=b'\xc2\x04\x00'):
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(0x400000, 0x750000); u.mem_write(0x400000, img[:0x1000])
    for va, raw, n in SECS: u.mem_write(0x400000 + va, img[raw:raw + n])
    u.mem_write(0x45C820, stub)
    u.mem_map(CAVE, B.ALLOC); b = bytearray(blob)
    for r in RELOCS: struct.pack_into('<I', b, r, (struct.unpack_from('<I', b, r)[0] + CAVE) & 0xFFFFFFFF)
    u.mem_write(CAVE, bytes(b))
    u.mem_map(OBJ, 0x20000); u.mem_map(STACK - 0x10000, 0x10000); u.mem_map(RET, 0x1000); u.mem_write(RET, b'\xf4')
    wf(u, 0x78340C, 0.0, -9.81, 0.0)                                   # gravity
    return u
def wf(u, a, *v): u.mem_write(a, struct.pack('<%df' % len(v), *v))
def wu(u, a, *v): u.mem_write(a, struct.pack('<%dI' % len(v), *v))
def rf(u, a, n=1): return struct.unpack('<%df' % n, u.mem_read(a, 4 * n))
def ru(u, a): return struct.unpack('<I', u.mem_read(a, 4))[0]
def setp(u, **kw):
    off = dict(mode=8, ai=0xC, fps=0x10, counts=0x14, half_track_f=0x18, half_track_r=0x1C, axle=0x20, comp_scale=0x2C,
               comp_add=0x30, need_road_tyre=0x34, scrub=0x38, x_sign=0x3C, yaw_sign=0x40, use_gravity=0x44)
    for k, v in kw.items():
        (wf if isinstance(v, float) else wu)(u, CAVE + DATA + off[k], v)

class Car:
    """the made-up SR3 car in the emulated memory"""
    def __init__(self, u, player=True, surface=TARMAC, comp=(0.05, 0.05, 0.05, 0.05), contact=(1, 1, 1, 1)):
        self.u = u; self.psi = 0.0
        wu(u, VEH, 0x678864); wu(u, VEH + 8, BODY); wu(u, VEH + 0x28, CTL); wu(u, VEH + 0x2C, LIST); wu(u, VEH + 0x30, 4)
        wf(u, BODY + 8, 1300.0, 1 / 1300.0)
        wf(u, BODY + 0x10, *(1 / 2171.0 if i % 4 == 0 else 0.0 for i in range(9)))
        for i in range(4):
            a = OBJ + 0x5000 + 0x100 * i; s = OBJ + 0x6000 + 0x100 * i; w = OBJ + 0x7000 + 0x200 * i; t = OBJ + 0x9000 + 0x100 * i
            wu(u, LIST + 4 * i, a); wu(u, a + 0xC, s, w, t); wu(u, s + 0x58, contact[i]); wf(u, s + 0x8C, comp[i])
            wf(u, w + 0x184, 0.345); wu(u, t + 0x1C, surface)
        rec = REC0
        if player:
            wu(u, rec + 4, DRV); wu(u, DRV, 0x6ED0C8); wu(u, DRV + 0x7E4, rec); wu(u, DRV + 0x858, WRAP); wu(u, WRAP + 4, VEH)
        else: wu(u, rec + 4, 0)
        self.stick(0.0)
    def stick(self, x):                              # the pad bytes: left, right (0..255)
        b = int(round(255 * min(1.0, abs(x))))
        self.u.mem_write(DRV + 0x1C84, bytes([b if x < 0 else 0, b if x > 0 else 0]))
    def axes(self):
        c, s = math.cos(self.psi), math.sin(self.psi)
        return (c, 0.0, -s), (0.0, 1.0, 0.0), (s, 0.0, c)
    def set(self, v, w):
        X, U, Z = self.axes()
        wf(self.u, BODY + 0xA4, *(X + U + Z)); wf(self.u, BODY + 0xEC, *(U + X + Z))
        wf(self.u, BODY + 0x170, *v); wf(self.u, BODY + 0x17C, *w)
    def step(self, dt):
        u = self.u; esp = STACK - 0x100
        u.mem_write(esp, struct.pack('<If', RET, dt)); u.reg_write(UC_X86_REG_ESP, esp); u.reg_write(UC_X86_REG_ECX, VEH)
        u.emu_start(CAVE + ENTRY, RET, count=2000000)
        if u.reg_read(UC_X86_REG_ESP) != esp + 8: raise SystemExit('stack not balanced: %x' % (u.reg_read(UC_X86_REG_ESP) - esp))
        return rf(u, BODY + 0x170, 3), rf(u, BODY + 0x17C, 3)

def drive(car, kmh_frame, counts, frames, dt, F=57.5, hold=True, stick_fn=None):
    """speed held (km/h of SRC's speedometer = m / frame x 216), stick in SRC counts; returns per step (yaw rate in SRC
    units, beta) from the car's own state"""
    v = kmh_frame / 216.0 * F                                          # m/s
    X, U, Z = car.axes(); V = [v * z for z in Z]; W = [0.0, 0.0, 0.0]; out = []
    for i in range(frames):
        c = stick_fn(i) if stick_fn else counts
        car.stick(c / 95.0); car.set(V, W)
        V, W = car.step(dt)
        car.psi += W[1] * dt
        if hold:
            sp = math.hypot(V[0], V[2]); V = [V[0] * v / sp, V[1], V[2] * v / sp]
        X, U, Z = car.axes()
        vx = sum(a * b for a, b in zip(V, X)); vz = sum(a * b for a, b in zip(V, Z))
        out.append((-W[1] / F, math.asin(vx / math.hypot(vx, vz))))
    return out

def model(kmh, counts, frames, stick_fn=None):
    c = M.Car(speed=kmh / 216.0); y = None; out = []
    for i in range(frames):
        cc = stick_fn(i) if stick_fn else counts
        cc = math.copysign(95.0 * round(255 * min(1.0, abs(cc) / 95.0)) / 255.0, cc)      # what the pad bytes carry
        s = 0.84 * max(-80, min(80, cc)) / 80.0
        y = s if y is None else y + 0.9 * (s - y)
        o = c.step(-y); c.hold_speed(kmh / 216.0); out.append((c.w, o['beta']))
    return out

npass = nfail = 0
def check(what, ok):
    global npass, nfail
    npass += bool(ok); nfail += not ok; print('  %s %s' % ('ok    ' if ok else 'FAILED', what))

# 1. the chain itself: axle centres, one SRC frame per step: the same numbers as srcmodel.py
u = machine(); setp(u, half_track_f=0.0, half_track_r=0.0); car = Car(u)
for kmh, cnt in ((100, 20), (180, 10), (140, 48), (230, 80)):
    car.psi = 0.0
    for s in range(8): wu(u, CAVE + DATA + 0xE0 + 32 * s, 0)                   # fresh slots
    a = drive(car, kmh, cnt, 200, 1 / 57.5); b = model(kmh, cnt, 200)
    err = max(abs(p[0] - q[0]) for p, q in zip(a, b)); ref = max(abs(q[0]) for q in b)
    check('axle centres, k = 1: %d km/h, %d counts: yaw rate %.4f / %.4f rad/frame at the end (port / srcmodel), largest difference %.1e (%.2f %%)' % (
        kmh, cnt, a[-1][0], b[-1][0], err, 100 * err / ref), err < 2e-3 * ref + 1e-6)
    check('    body slip %.2f / %.2f deg' % (math.degrees(a[-1][1]), math.degrees(b[-1][1])), abs(a[-1][1] - b[-1][1]) < 0.002 + 0.01 * abs(b[-1][1]))

# 2. kb 29's steady turns with the port as it runs in the game (4 wheels with SRC's track width, SR3 steps of 1/60 s)
def fresh(u):
    for s in range(8): wu(u, CAVE + DATA + 0xE0 + 32 * s, 0)
u = machine(); car = Car(u)
F = 57.5; dt = 1 / 60.0
print('  steady turns, stick right (port, 4 wheels, dt 1/60 s; SR3 speed = SRC km/h x 57.5 / 60): yaw rate rad/s / body slip deg')
KB = {100: (2.3, 0.70), 140: (2.05, 0.55), 180: (1.8, 0.45), 230: (1.6, 0.39)}
rows = {}
for kmh in (100, 140, 180, 230):
    line = []
    for cnt in (5, 10, 20, 30, 48, 80):
        fresh(u); car.psi = 0.0; r = drive(car, kmh, cnt, 300, dt)
        line.append((-r[-1][0] * F, -math.degrees(r[-1][1])))          # a right turn: SRC's yaw rate and slip < 0
    rows[kmh] = line
    print('    %3d km/h: ' % kmh + '  '.join('%2d: %.2f / %4.1f' % (c, w, b) for c, (w, b) in zip((5, 10, 20, 30, 48, 80), line)))
for kmh, (gain, ceil) in KB.items():
    g = rows[kmh][2][0] * 95 / 20; top = max(w for w, b in rows[kmh])
    check('%d km/h: small-stick gain %.2f rad/s per full stick (kb 29: %.2f), yaw-rate ceiling %.2f rad/s (kb 29: %.2f), slip at 30 counts %.1f deg' % (
        kmh, g, gain, top, ceil, rows[kmh][3][1]), abs(g - gain) < 0.12 * gain and abs(top - ceil) < 0.12 * ceil)
# step response: 20 counts for 1 s, then released, 200 km/h
fresh(u); car.psi = 0.0
r = drive(car, 200, 0, 120, dt, stick_fn=lambda i: 20 if i < 60 else 0); ws = [x[0] for x in r]; wss = ws[59]
t50 = next(k for k in range(60) if abs(ws[k]) >= 0.5 * abs(wss)) + 1; t90 = next(k for k in range(60) if abs(ws[k]) >= 0.9 * abs(wss)) + 1
pk = max(abs(x) for x in ws[:60]) / abs(wss)
r25 = next(k for k in range(60, 120) if abs(ws[k]) <= 0.25 * abs(wss)) - 59
check('turn-in, 200 km/h, 20 counts: half the yaw rate after %d steps, 90 %% after %d, overshoot %.0f %%, 25 %% %d steps after the release (kb 29: 2-3 / 4-6 / about 25 %% / 3-5 frames)' % (
    t50, t90, 100 * (pk - 1), r25), t50 <= 4 and t90 <= 8 and r25 <= 7)
# right stick turns right: the nose toward +x (psi grows), the velocity left of the nose
fresh(u); car.psi = 0.0; r = drive(car, 120, 20, 60, dt)
check('stick right: the car turns right (yaw %.3f rad after 1 s) with the velocity to the left of the nose (body slip %.1f deg)' % (car.psi, math.degrees(r[-1][1])), car.psi > 0.2 and r[-1][1] < 0)

# 3. what the port leaves alone
def one(stub=b'\xc2\x04\x00', player=True, surface=TARMAC, contact=(1, 1, 1, 1), **kw):
    u = machine(stub); setp(u, **kw); car = Car(u, player=player, surface=surface, contact=contact); car.stick(0.5)
    V = (2.0, 0.0, 30.0); W = (0.0, 0.3, 0.0); car.set(V, W)
    v, w = car.step(1 / 60.0); return u, v, w
V0, W0 = (2.0, 0.0, 30.0), (0.0, 0.3, 0.0)
same = lambda a, b: max(abs(x - y) for x, y in zip(a, b)) < 1e-6
u, v, w = one(surface=RALLY); check('a car on Tyre_Rally records (SR3 / Realism files): velocity and yaw rate untouched', same(v, V0) and same(w, W0))
u, v, w = one(contact=(0, 0, 0, 0)); check('no wheel on the ground: untouched (SR3\'s own in the air); last_err %d' % ru(u, CAVE + DATA + 0xDC), same(v, V0) and same(w, W0) and ru(u, CAVE + DATA + 0xDC) == 2)
u, v, w = one(player=False); check('a computer car with ai = 0: untouched', same(v, V0) and same(w, W0))
def one_hit():
    u = machine(); car = Car(u); car.stick(0.5); wu(u, VEH + 0x38, OBJ + 0xE000); wu(u, OBJ + 0xE024, 1); wf(u, OBJ + 0xE028, 0.6)
    car.set(V0, W0); v, w = car.step(1 / 60.0); return u, v, w
u, v, w = one_hit(); check("SR3's hit recovery (force model + 0x24 set): untouched; last_err %d" % ru(u, CAVE + DATA + 0xDC), same(v, V0) and same(w, W0) and ru(u, CAVE + DATA + 0xDC) == 3)
u, v, w = one(player=False, ai=1); check('a computer car with ai = 1: turned by the port (yaw rate %.3f -> %.3f)' % (W0[1], w[1]), not same(w, W0))
u, v, w = one(mode=1); n = ru(u, CAVE + DATA + 0xD4)
check('mode 1 (observe): untouched, one log record written (%d)' % n, same(v, V0) and same(w, W0) and n == 1)
u, v, w = one(mode=0); check('mode 0: untouched, nothing counted', same(v, V0) and same(w, W0) and ru(u, CAVE + DATA + 0xD4) == 0)
u, v, w = one(); check('mode 2: changed (yaw rate %.3f -> %.3f rad/s, side velocity %.2f -> %.2f m/s)' % (W0[1], w[1], V0[0], v[0]), not same(w, W0))
# SR3's own turning inside the step is thrown away, its change of speed along the car kept: the stub adds 1.0 rad/s
# of yaw rate, 3 m/s to the side and 0.5 m/s forward
stub = bytes.fromhex('8b4108') + bytes.fromhex('f30f108080010000') + bytes.fromhex('f30f5805') + struct.pack('<I', OBJ + 0xF000) + \
    bytes.fromhex('f30f118080010000') + bytes.fromhex('f30f108070010000') + bytes.fromhex('f30f5805') + struct.pack('<I', OBJ + 0xF004) + \
    bytes.fromhex('f30f118070010000') + bytes.fromhex('f30f108078010000') + bytes.fromhex('f30f5805') + struct.pack('<I', OBJ + 0xF008) + \
    bytes.fromhex('f30f118078010000') + b'\xc2\x04\x00'
u0, va, wa = one()
u = machine(stub); car = Car(u); car.stick(0.5); wf(u, OBJ + 0xF000, 1.0, 3.0, 0.0); car.set(V0, W0); vb, wb = car.step(1 / 60.0)
check("SR3's own yaw (+1 rad/s) and side velocity (+3 m/s) inside the step are thrown away: yaw %.4f / %.4f, side %.4f / %.4f rad/s, m/s (without / with)" % (
    wa[1], wb[1], va[0], vb[0]), abs(wa[1] - wb[1]) < 1e-5 and abs(va[0] - vb[0]) < 1e-4)
u = machine(stub); car = Car(u); car.stick(0.0); wf(u, OBJ + 0xF000, 0.0, 0.0, 0.5); car.set(V0, (0.0, 0.0, 0.0)); vb, wb = car.step(1 / 60.0)
u = machine(); car = Car(u); car.stick(0.0); car.set(V0, (0.0, 0.0, 0.0)); vc, wc = car.step(1 / 60.0)
check("SR3's change of speed along the car is kept: +0.5 m/s in the step -> %.3f -> %.3f m/s forward" % (vc[2], vb[2]), abs((vb[2] - vc[2]) - 0.5) < 0.01)
# gravel: SRC's record B (grip 1.1): a lower ceiling than on tarmac
u = machine(); car = Car(u, surface=GRAVEL); r = drive(car, 140, 80, 300, dt)
check('gravel (record B): full-lock yaw rate %.2f rad/s at 140 km/h, below tarmac\'s %.2f' % (-r[-1][0] * F, rows[140][5][0]), -r[-1][0] * F < rows[140][5][0])
# braking moves grip to the front: front compression up
u = machine(); car = Car(u, comp=(0.055, 0.055, 0.045, 0.045)); r = drive(car, 140, 20, 120, dt)
check('nose down (front compressed, load transfer 0.1): more yaw rate at 20 counts (%.3f against %.3f rad/s level)' % (-r[-1][0] * F, rows[140][2][0]), -r[-1][0] * F > rows[140][2][0])
print('SRCPORT CHECKS: %d passed, %d failed' % (npass, nfail))
