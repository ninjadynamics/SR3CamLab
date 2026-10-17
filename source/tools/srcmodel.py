"""srcmodel.py : SEGA Rally Championship (1995) lateral / yaw model as read from the i960 code (planar, axle centres).
Units are the game's: metres, frames, radians; forces in the game's units (mass 1000).  Angles / rotations use the
game's convention: rot(a, x, z) = (x cos a - z sin a, x sin a + z cos a); heading = rot(yaw, 0, 1)."""
import math
G = 9.81 / 3500.0          # [0x214124]: gravity per frame^2 and the tyre force scale (9.81 / 2800 for the hidden car)
MASS, IYAW = 1000.0, 1146.0
A = 1.25                   # axle distance from the centre (both axles)
SURF = {'tarmac': (1.3, 0.25, 0.07, 0.07), 'gravel': (1.1, 0.25, 0.07, 0.07), 'water': (0.5, 0.25, 0.07, 0.07),
        'verge': (1.2, 0.23, 0.07, 0.07)}   # grip (front = rear), front drive share, yaw damping on d(beta), on w
def rot(a, x, z): return (x * math.cos(a) - z * math.sin(a), x * math.sin(a) + z * math.cos(a))
def slip(vx, vz, hx, hz):
    l = math.hypot(vx, vz)
    if l < 1e-10: return 0.0, 0.0
    x, z = vx / l, vz / l
    d = min(1.0, abs(x * hx + z * hz))
    return math.copysign(math.sqrt(1 - d * d), x * hz - z * hx if x * hz - z * hx != 0 else 1.0), l
def steer_angle(byte, y_prev):
    """0x395D8 + 0x39A90: byte 0..255 -> filtered steering angle (car + 0x74 = -y)."""
    s = 0.84 * max(-80, min(80, byte - 128)) / 80.0
    return y_prev + 0.9 * (s - y_prev)
def tyre(sig, vlat_speed, fmax, k, fx, wsp, c):
    fy = fmax * math.sin(min(abs(sig) * k, math.pi / 2))
    tot = math.hypot(fy, fx) * (1 + wsp)
    if tot > fmax:
        q = fmax / tot; f = c * math.sqrt(q) + (1 - c) * q * q
        fy, fx = fy * f * 1.1, fx * f
    if sig >= 0: fy = -fy
    ls = abs(sig) * vlat_speed
    if ls < 0.02: fy *= ls / 0.02
    return fy, fx
class Car:
    def __init__(self, yaw=0.0, speed=0.0, surf='tarmac'):
        self.yaw, self.w = yaw, 0.0
        self.vx, self.vz = rot(yaw, 0, speed)
        self.beta = 0.0; self.surf = surf
    def step(self, delta, drive=0.0, lt=0.0, wsp=0.0, g=G):
        grip, share, kb, kw = SURF[self.surf]
        sp = math.hypot(self.vx, self.vz)
        bx = rot(self.yaw, 1, 0)
        beta = math.asin(max(-1, min(1, (self.vx * bx[0] + self.vz * bx[1]) / sp))) if sp > 0.01 else 0.0
        dbeta = beta - self.beta; self.beta = beta
        if sp <= 0.01: dbeta = 0.0
        d = []
        for L in (A, -A):
            a0, a1 = rot(self.yaw, 0, L), rot(self.yaw + self.w, 0, L)
            d.append((self.vx + a1[0] - a0[0], self.vz + a1[1] - a0[1]))
        hf, hr = rot(self.yaw + delta, 0, 1), rot(self.yaw, 0, 1)
        sf, vf = slip(d[0][0], d[0][1], hf[0], hf[1])
        sr, vr = slip(d[1][0], d[1][1], hr[0], hr[1])
        sf = 0.0 if abs(sf) < 0.01 else sf - math.copysign(0.01, sf)
        fmaxf = g * MASS * grip * (1 + lt) * (1 + 0.3 * sp)
        fmaxr = g * MASS * grip * (1 - lt) * (1 + 0.3 * sp)
        fyf, fxf = tyre(sf, vf, fmaxf, 2 * math.pi / 3, share * drive, wsp, 1.2)
        fyr, fxr = tyre(sr, vr, fmaxr, math.pi, drive - share * drive, wsp, 0.4)
        if fxf < 0: fxr += fxf; fxf = 0.0
        bxf = fyf * math.cos(delta) - fxf * math.sin(delta)
        bzf = fyf * math.sin(delta) + fxf * math.cos(delta)
        ty = A * (fyr - bxf)
        w = self.w + ty / IYAW
        w = max(-0.1, min(0.1, w))
        w = w - (kb * dbeta + kw * w)
        fw = rot(self.yaw, bxf + fyr, bzf + fxr)
        self.vx += fw[0] / MASS; self.vz += fw[1] / MASS
        self.w = w; self.yaw += w
        return dict(sf=sf, sr=sr, fyf=fyf, fyr=fyr, ty=ty, beta=beta)
    def hold_speed(self, speed):
        sp = math.hypot(self.vx, self.vz)
        if sp > 0: self.vx, self.vz = self.vx * speed / sp, self.vz * speed / sp
