# 29 - SEGA Rally Championship (1995): the steering and turning code

The owner (2026-10-15): "get the steering from code in SRC model 2. I still feel this guessing numbers game isn't the way
to go." This page is the player car's steering and turning chain as read from the i960 program, from the steering byte
0x202050 to the yaw rate and the heading. It replaces the fitted numbers of 28_handling_flavors.md section 2 for anything
that concerns steering. Tags: VERIFIED (code, plus how it was checked live), LIKELY, UNKNOWN.

Method: static disassembly of `maincpu.bin` (unidasm -arch i960, MAME 0.229), then MAME 0.229 headless (srallyc,
Practice, Celica AT, the autopilot of 28_handling_flavors.md) on Desert (gravel) and Mountain (tarmac) with a per-frame log
of every value named below. MAME 0.229 has no memory taps in Lua, so a small capture routine was put in the program ROM
region (the axle-force routine's last store at 0x38640 branches to 0xF0000, which stores r4..r15 and the torque
accumulator to RAM 0x23F000 and branches back). Scripts and logs: scratchpad `agent_srcsteer\` (section 11).

## 1. Where it runs, units

- Player car update: 0x34F40, car object g0 = 0x500000, once per frame (MAME: 57.5 frames/s; the game's own constants
  assume 60: km/h = m/frame x 216). Called through a pointer (no direct caller). VERIFIED (one call per frame in the log).
- The game executes this code from its RAM copy (ROM + 0x59F000, the same copy as the initialised data): return addresses
  like `lda 0x5D79A8,g14` are RAM addresses, and a relative branch patched into the ROM image lands at ROM target +
  0x59F000. A patch must use absolute branches (`bx`). VERIFIED (a relative branch crashed at 0x68F000).
- Units: metres, frames, radians (single floats). Car object: +0x14 position, +0x2C velocity (m/frame), +0x38 / +0x3C /
  +0x40 pitch / yaw / roll, +0x44 / +0x48 / +0x4C their rates (rad/frame), +0x50 mass 1000, +0x54 / +0x58 / +0x5C inertia
  1146 / 1146 / 300 (pitch, yaw, roll), +0x64..+0x70 suspension compression of wheels 0..3, +0x74 steering angle (rad).
  Set by the car init 0x34140. Forces are in "mass 1000" units: force / 1000 = m/frame squared. VERIFIED (code).
- The vector maths goes through the geometry coprocessor (TGP), a FIFO at 0x884000: a command word (function number in
  bits 23 and up) then arguments, then results are read back. The functions this code uses:

| TGP function | Arguments -> results | Meaning | Status |
|---|---|---|---|
| 0x20 / 0x21 | - | push / pop the matrix | LIKELY (always paired) |
| 0x25 | - | identity | LIKELY |
| 0x27 | x, y, z | translate | LIKELY |
| 0x29 / 0x2A / 0x2B | angle | rotate about x / y / z; 0x2A: (x, z) -> (x cos a - z sin a, x sin a + z cos a) | 0x2A VERIFIED (torque check, section 8) |
| 0x2C | x, y, z -> 3 | transform a point | LIKELY |
| 0x2F | x, y, z -> 3 | normalise | VERIFIED (slip check, section 4) |
| 0x42 / 0x43 / 0x44 / 0x48 | n, x, y, z / n -> 3 / n, x, y, z / n | load / read / add to / transform vector register n | VERIFIED (torque check) |
| 0x58 | two points -> 1 | distance (with (0, 0, 0): length) | VERIFIED (speed) |
| 0x59 / 0x5B | two vectors -> 1 / 3 | dot / cross product | LIKELY / VERIFIED (body slip sign) |
| 0x15 | x -> 1 | sin | VERIFIED (tyre force check) |
| 0x11 | x -> 1 | UNKNOWN (LIKELY sqrt) | |

## 2. Steering input: 0x395D8, 0x39A90, stored at 0x34F98

```
b  = byte at 0x202050 (the ADC copy of 0x24E8 / 0x26B8; 128 = centre)
s  = 0.84 * clamp(b - 128, -80, +80) / 80          0x395D8: 0.84 (double at 0x39620), 80 (0x39640)
y  = y + 0.9 * (s - y)                             0x39A90: 0.9 (0x39AAC); y kept at RAM 0x2142C0
car + 0x74 = -y      (0 while game state [0x2020A8] = 9)
```
- No dead zone, no curve, no speed dependence, no rate limit: a linear wheel angle of 0.84 rad (48 degrees) at 80 counts
  from the centre, followed by a one-pole filter that covers 90 % of a step in one frame and 99 % in two. 0x39AF0 sets y = s
  at the car init (0x34140 -> 0x377E0 -> 0x39540 -> 0x39AF0). VERIFIED (code; live: every frame of both runs matches to 1e-7, the byte read one frame later).
- With the pad's range of 95 counts (28_handling_flavors.md), full lock is reached at 84 % of the stick.
- No auto-centring of the value: on the cabinet the wheel is centred by the force feedback, which this code drives
  (0x39540 / 0x39750 / 0x39C40, output byte 0x202049, inputs: steering angle, front slip, front lateral force). VERIFIED
  (code); the feedback formula itself was not decoded.

## 3. Order of one frame in 0x34F40

1. 0x34F7C steering (section 2).
2. 0x34FB0 when [0x20A560] > 0: 0x33E90 sets the force scale G (section 9); 0x34FC4 0x2B0B0 (course contact, LIKELY).
3. 0x351A8 predicted pose = position + velocity, angles + rates; 0x34380 wheel contacts (returns the deepest contact,
   0 in the air).
4. 0x35260..0x35808 wheel points of the predicted and the current pose, offsets (x, y, z) = (-0.635, -0.4, 1.25),
   (0.635, -0.4, 1.25), (-0.66, -0.4, -1.25), (0.66, -0.4, -1.25) for wheels 0..3; their difference = each wheel's
   displacement over the frame.
5. 0x3580C..0x35AC0 body slip angle beta (RAM 0x214200) and its change dbeta (0x214204), from the frame-start yaw and
   velocity: beta = asin(v_unit . body_x), body_x = (cos yaw, sin yaw); 0 when |v| <= 0.01 m/frame. VERIFIED (sign, live).
6. 0x35AD8 wheel headings: front = rotY(yaw) rotY(car + 0x74) (0, 0, 1), rear = rotY(yaw) (0, 0, 1) (flat; current yaw).
7. 0x35B84..0x35C24 0x37200 for wheels 0, 1, 2, 3: suspension force, slip, surface (section 4).
8. 0x35D00 axle values: slip and speed of the front pair (0x21420C, 0x214210) and the rear pair (0x214214, 0x214218),
   the mean when both wheels touch, the one value when one does.
9. 0x35E2C..0x36350 suspension forces into the body frame: force sum and torques (section 8).
10. 0x3675C 0x37870 axle forces (sections 5 to 8).
11. 0x36760 rates += torque / inertia, each clamped to +-0.1 rad/frame; 0x368C4 pitch / roll levelling; 0x36A5C yaw damping;
    0x36BD4 low-speed alignment (section 8).
12. 0x36CC4 velocity += force / 1000, vertical velocity -= G, angles += rates, position += velocity; ground drag; speed cap.

## 4. Slip of each wheel (0x37200)

```
d     = wheel displacement over the frame (step 4), y set to 0, normalised (TGP 0x2F)
h     = wheel heading (step 6), front wheels steered, rear not
sigma = sign(d.x h.z - d.z h.x) * sqrt(1 - min(1, |d . h|)^2)     signed sine of the slip angle (backwards folded)
speed = |displacement| (3D)                                          -> 0x213890 + 4 i, sigma -> 0x213880 + 4 i
```
- 0 for a wheel without contact. Because the prediction uses angle + rate, the yaw rate enters each wheel's slip.
  VERIFIED (code; live: the same formula on the axle centres from the previous frame's logged pose gives the game's axle
  values with a median error of 0.0003).
- The same routine sets bit (surface code) in 0x214208 (code = the low 4 bits of the contact attribute) and writes the
  suspension force (spring from the record x compression, compression clamped to 0.2; 3600 and 100 appear as unit factors).

## 5. Surface record (0x37870 start)

0x214208's highest set bit (looked for from 9 down) picks a pointer from RAM 0x5D67A0 (prog 0x377A0), so one record per
frame for the whole car, the highest surface code under any wheel winning. The record is copied to RAM 0x2141C0..0x2141F0.

| Field (0x2141C0 +) | A: codes 0, 1, 8, 9 (tarmac) | B: 2, 3, 10-15 (gravel, dirt) | C: 4, 5 (water) | D: 6, 7 (verge) | Used at |
|---|---|---|---|---|---|
| +0x00 / +0x04 grip front / rear | 1.3 | 1.1 | 0.5 | 1.2 | tyre force |
| +0x08 front share of drive / brake force | 0.25 | 0.25 | 0.25 | 0.23 | 0x37A14 |
| +0x0C yaw damping on dbeta | 0.07 | 0.07 | 0.07 | 0.07 | 0x36A5C |
| +0x10 yaw damping on the yaw rate | 0.07 | 0.07 | 0.07 | 0.07 | 0x36A5C |
| +0x14 / +0x18 spring front / rear | 30 | 30 | 30 | 30 | 0x37200 |
| +0x1C / +0x20 damper front / rear | 8 | 3 | 3 | 3 | 0x37200 |
| +0x24 / +0x28 load transfer lag rising / falling | 0.1 / 0.4 | 0.05 / 0.4 | 0.1 / 0.4 | 0.1 / 0.4 | 0x37ACC |
| +0x2C | 0.998 | 0.998 | 0.998 | 0.998 | horizontal speed factor in the branch at 0x36EB4 (LIKELY slipstream) |
| +0x30 ground drag per contact depth | 0.28 | 0.28 | 0.28 | 0.35 | 0x36E3C |

Records at prog 0x376A0, 0x376E0, 0x37720, 0x37760. VERIFIED (code; live: grip 1.3 on Mountain codes 0 / 1 / 8, 1.1 on
Desert codes 2 / 3). Gravel / tarmac = 0.85 (the laps gave 0.87). This answers "physics per surface" of 18 section 7.

## 6. Load transfer (0x37900..0x37B50, 0x38A18)

```
Cf = c0 + c1, Cr = c2 + c3                     compressions car + 0x64..0x70
raw = (Cf - Cr) / (Cf + Cr)
lt  = raw - k (raw - lt_prev),  k = +0x24 if raw > lt_prev else +0x28
lt' = lt + 0.08 sin(pi lt) for lt > 0 (0x5D6688 = 0.08), lt for lt <= 0      -> RAM 0x21425C (next frame's lt_prev)
grip_front = grip (1 + lt'),  grip_rear = grip (1 - lt')
```
- Braking (nose down) gives front grip and takes rear grip; throttle the reverse (live: lt' -0.13 to -0.2 at 160-200 km/h
  on full throttle). VERIFIED (code; the logged lt' gives the logged forces).
- When an axle has no contact (Cf x Cr = 0) the drive force is 0 for both axles that frame.
- A left / right term is also kept: r14 = 1.1 (c1 - c0) / Cf, r13 = 1.1 (c3 - c2) / Cr (0 when that axle's force is
  negative); it only enters the yaw torque (section 8).

## 7. Tyre forces (0x37870)

```
G     = [0x214124] = 9.81 / 3500 (0x34140; 9.81 / 2800 when [0x2020B4] != 0, section 9)
v     = [0x20B0B4] = |velocity| (m/frame, 0x366AC; x TGP 0x11(G x 3500 / 9.81) when [0x20A560] > 0, 0x365E8)
Fmax  = G x 1000 x grip_axle x (1 + 0.3 v)                  per axle; (1 + 0.3 v) = 1.28 at 200 km/h
D     = [0x214258] drive (+) or brake (-) force from 0x3A320 (throttle 0x202051 - 48 over 143, gears, brake 0x3B128)
w     = [0x214254] longitudinal wheel slip 0..1 (wheelspin / lock, 0x3A740)

front: sf = axle slip, dead band 0.01 (0x5D6690): sf = sign(sf)(|sf| - 0.01), 0 inside
       Fy = Fmax sin(min(|sf| x 2 pi / 3, pi / 2))          peak at |sf| = 0.75 (slip angle 49 degrees)
       Fx = 0.25 D                                          (record +0x08)
rear:  sr = axle slip (no dead band)
       Fy = Fmax sin(min(|sr| x pi, pi / 2))                peak at |sr| = 0.5 (30 degrees): stiffer than the front
       Fx = D - front Fx
each:  if (1 + w) hypot(Fy, Fx) > Fmax:  q = Fmax / ((1 + w) hypot(Fy, Fx)),  f = c sqrt(q) + (1 - c) q^2
          Fy = Fy x f x 1.1,  Fx = Fx x f            c = 1.2 front (0x38958, 0x5D6680), 0.4 rear (0x389B8, 0x5D6684)
       Fy = -sign(slip) Fy                                  (against the slip)
       if |slip| x axle speed < 0.02 m/frame: Fy = Fy x |slip| x axle speed / 0.02
then:  if front Fx < 0: rear Fx += front Fx, front Fx = 0   (front braking acts along the body, not the steered wheel)
```
- Every constant above is in the code at the address given (0x37BF0 2 pi, 0x37C34 3.0, 0x37F44 pi, 0x37C04 1000,
  0x37A6C 0.3, 0x37E54 0.02). VERIFIED (live: front and rear lateral force recomputed from the logged values match the
  game's to 2e-7 median, front over 3286 and rear over 4258 frames of both runs; the few misses are frames on the
  friction-circle border, where the x 1.1 step switches on).
- Grip in "g": each axle can give grip x G x 1000 = 1.3 x the car's weight on tarmac, so 2.6 g for the car, times
  (1 + 0.3 v). The tyre curve is a sine of the slip sine, very wide: normal cornering uses front slips of 0.1-0.3.
- Braking turns the car: 75 % of the brake force goes through the rear friction circle and lt' moves grip to the front.

## 8. Yaw torque and the yaw rate

```
front force in the body frame (TGP 0x2A by the steering angle d = car + 0x74):
       Xf = Fy_f cos d - Fx_f sin d,   Zf = Fy_f sin d + Fx_f cos d
T_tyre = 1.25 (Fy_r - Xf) + 0.66 r13 Fx_r - 0.635 r14 Fx_f              stored at the routine's fp + 0x54
body force (Fy_r + Xf, 0, Fx_r + Zf) rotated by the yaw into the world force sum; roll torque -0.2 x lateral sum,
pitch torque 0.2 x longitudinal sum
T_yaw  = T_tyre + suspension terms (0x35E2C: 1.35 x (rear - front lateral components of the suspension forces),
         left / right differences of their longitudinal components x 0.635 / 0.66; small on level road)

w = car + 0x48 (rad/frame)
w = clamp(w + T_yaw / 1146, -0.1, +0.1)                                   0x36760..0x36864
w = w - (0.07 x dbeta + 0.07 x w)                                         0x36A5C, record +0x0C / +0x10
if the wheels touch and v < 0.0463 m/frame (10 km/h):                       0x36BD4
       w = w - 0.015 pi x (heading x section direction).y                 section direction = RAM 0x214360, written
                                                                          at 0x3B5D8 from a (cos, sin) table (LIKELY
                                                                          the section headings, 18 section 2)
yaw = yaw + w                                                             0x36D5C
```
- VERIFIED: the tyre torque recomputed from the captured registers matches fp + 0x54 to 3e-6 in every frame (and only with
  the rotation sign above); the yaw-rate update matches the logged yaw rate to 3e-10 median in 4177 of 4244 frames above
  10 km/h (both runs); the 67 others have a wheel in the air or against a wall / bank (another routine changes the yaw rate
  there).
- The yaw rate is a state with its own damping: 7 % of it is removed every frame, plus 7 % of the change of the body slip
  angle (so the heading is pulled along with the path). The yaw inertia (1146) is small against mass x 1.25^2 (1562).
- The steering angle is never reduced with speed. What limits the turn at speed is grip: the yaw rate saturates where the
  rear axle runs out of force, and full lock (48 degrees) turns less than half lock at speed (the front force is tilted
  48 degrees and drags).

## 9. Other things in the same code

- Speed cap 1.157 m/frame (250 km/h, 0x37118); on the ground the velocity is multiplied by max(0, 0.997 - depth x record
  +0x30) every frame (Lake Side: 0.99 - 1.8 x depth, 0x36DF0). VERIFIED (code).
- [0x2020B4] is set from 0x13BF0, a shifter-position sequence checked at the car select (sound 0x7D on success); with it G
  = 9.81 / 2800 (+25 % force and gravity per frame), the front share 0.2 instead of the record's, the tyre speed v = the
  forward speed, other wheelspin rules (0x38158). LIKELY the hidden car (Lancia Stratos); not driven here.
- 0x33E90 (only when [0x20A560] > 0): G = 9.81 / (3500 + 10 m), m = the smallest of 0 and, per other car, min(10 x
  section difference, signed distance); at most 9.81 / 2600. LIKELY a catch-up between cars; G stayed 9.81 / 3500 in
  Practice (VERIFIED, log).
- Landing after more than 10 frames in the air: 0x388D0 returns 5.0 for one frame (sound 0x47); it only feeds the force
  feedback.
- 0x3A320 also measures the forward speed along yaw + steering angle (TGP 0x59) for the wheel speed.

## 10. What it adds up to

Model `srcmodel.py` (the chain above on the two axle centres, about 60 lines): driven from a logged state with the logged
steering, load transfer, drive and speed it follows the game's yaw rate frame by frame through a step (Mountain, 220 km/h,
max error 0.0012 rad/frame median over 1 s windows against yaw rates of 0.008-0.016). LIKELY faithful to 10-15 % (it leaves
out the suspension yaw terms and the track width).

Steady turns from the model (tarmac, coasting, speed held; yaw rate in rad/s at 57.5 frames/s / body slip angle in
degrees; stick in counts from the centre, 95 = the pad's full range):

| km/h | 5 | 10 | 20 | 30 | 48 | 80 (full lock) |
|---|---|---|---|---|---|---|
| 60 | 0.13 / 1.6 | 0.28 / 1.9 | 0.51 / 2.0 | 0.72 / 3.0 | 0.94 / 4.3 | 0.85 / 4.0 |
| 100 | 0.13 / 1.8 | 0.25 / 3.2 | 0.49 / 6.4 | 0.63 / 8.9 | 0.70 / 10.7 | 0.55 / 8.3 |
| 140 | 0.11 / 2.1 | 0.24 / 4.7 | 0.43 / 9.1 | 0.53 / 12.1 | 0.55 / 13.4 | 0.42 / 10.0 |
| 180 | 0.10 / 2.6 | 0.22 / 5.7 | 0.38 / 10.9 | 0.45 / 14.0 | 0.45 / 14.9 | 0.34 / 10.8 |
| 230 | 0.09 / 3.0 | 0.20 / 6.5 | 0.34 / 12.3 | 0.39 / 15.6 | 0.38 / 16.0 | 0.28 / 11.4 |

- Small-stick gain, scaled to a full 95-count stick: 2.3 (100 km/h), 2.05 (140), 1.8 (180), 1.6 (230) rad/s; the owner's
  laps gave 2.0-2.5 by regression on |stick| < 0.5. Above about 30 counts the yaw rate stops growing (lateral 2.3-2.7 g).
- Step of 20 counts: half the yaw rate after 2-3 frames, 90 % after 4-6, an overshoot of about 25 % while the body slip
  builds, back to 25 % 3-5 frames after the release. In the game (Mountain, 220 km/h, full throttle): 0.0020 rad/frame in
  the first frame, half after 3, peak 0.0097 after 13 frames, body slip 9 degrees after 0.7 s.

## 11. Files, open points

Scratchpad `agent_srcsteer\` (nothing in the repository): `dis.txt` (full disassembly, local only), `f*.txt` (the routines
above), `srcsteer.lua` + `prog_steer.lua` (logger and steering steps; uses agent_handling's runmame.py, prog_drive.lua and
roms stand-ins), `tramp.py` (the capture routine), `chk_filter.py`, `chk_yaw.py`, `chk_slip.py` (the checks of sections 2,
7, 8, 4), `srcmodel.py`, `replay.py`, `steady.py`; logs `run2\steer.csv` (Desert) and `run3\steer.csv` (Mountain).

Open: the force-feedback formula (0x39C40); the drive / brake force and wheelspin in detail (0x3A320, 0x3B128, 0x3AA38);
the suspension yaw terms in detail; the meaning of game state 9 and of record +0x2C; the hidden car's set not driven.

## 12. The port: SRC's turning inside SEGA Rally 3 (2026-10-15)

The owner: "I still feel this guessing numbers game isn't the way to go". So SR3 does not get fitted numbers for SRC. After
every SR3 vehicle step, a car on the SRC handling gets its yaw rate and side velocity from the chain of sections 2 to 8.
That chain runs on SR3's own state. Tags as above; "emulated" = checked on an emulated CPU (tools\srcport_emu.py) inside a
copy of Rally.exe's image, not yet in a running game.

What each game contributes:
| From SRC (this page) | From SR3 |
|---|---|
| the steering filter (section 2) from the pad's two bytes: counts = 95 x stick (the pad's range in SRC), full lock 0.84 rad at 84 % of the stick | the speed along the car (engine, gears, brakes, drag: the SRC files' torque and gears) |
| the slip of each wheel from the frame's displacement (section 4), SRC's wheel offsets (+-0.635 / +-0.66, +-1.25) | which wheels touch, and each wheel's surface, mapped to SRC's four records (section 5) |
| load transfer with its lags and the 0.08 sin term (section 6) | the suspension compressions that feed it |
| the tyre forces, friction circle, front-braking move (section 7) | the drive / brake force D: SR3's own change of speed along the car over the step, gravity taken out, x 1000 in SRC's units |
| yaw torque / 1146, the +-0.1 clamp, the 7 % + 7 % damping (section 8) | vertical motion, pitch, roll, walls, the air, SR3's hit recovery |
| the side force's change of the side velocity, and the front side force's drag (Fy_f sin d) | gravity along the car's x (a sideways slope) |

Units: SRC's frame is 1 / 57.5 s (the cabinet), so one SR3 step of dt seconds is k = dt x 57.5 frames. Speeds become m /
frame (/ 57.5) and the yaw rate rad / frame. Per-frame rules run for k frames: the filter and the lags as powers of k
(0.1^k, K^k), the damping as 1 - 0.93^k, the torque and the forces x k. An SR3 car at 100 km/h is therefore SRC at
104 km/h on its speedometer (SRC's km/h = m / frame x 216 assume 60 frames). Directions: SRC's body x = SR3's body x, and
both are the car's right (SR3's wheel 0 has hub x -0.624 and is the front left). SRC's yaw rate is positive to the left:
w_src = -(omega . up) / 57.5. Two sign switches in the data block, x_sign and yaw_sign, can turn either the right/left
mapping or the yaw sense around. The live session checks both.

Not ported: SRC's wheelspin w (the friction circle uses 1 + 0, because SR3 does the wheelspin); the suspension yaw terms
(0x35E2C, small on level road); the low-speed alignment below 10 km/h (0x36BD4, it needs SRC's section headings); the
hidden car's set.

SR3's side (Rally.exe 3.8.4.1, static reading 2026-10-15, VERIFIED (code) unless marked):
- The hook: CVehicle (RTTI, vtable 0x678864) slot 5 = 0x45C820 is the vehicle step (thiscall, one float: dt). It is
  reached only through the vtable (no direct call), and sr3mods.ps1 points the entry 0x678878 to the port, which calls
  0x45C820 itself. The step works in sub-steps (count from 0x45C6B0). At its end it puts the body's position (+0x88) and
  orientation (+0xA4, 0x45A7E0) back as they were, so the pose is moved afterwards from the velocities, by the collision
  code. The port runs between the two, which is why SR3's walls stay SR3's. CVehicleSimple (0x678A10, slot 5 0x45D410)
  is not hooked.
- Body = [vehicle + 8] (CRigidBody3D, vtable 0x6786D4): +8 mass, +0xC 1 / mass, +0x7C local centre of mass, +0x88
  position, +0xA4 3 x 3 rows = the body's x, y, z axes in the world, copied by 0x459F80 to +0xF8 (x, the right), +0xEC
  (up), +0x104 (z, forward), +0x158 momentum, +0x170 velocity (m/s), +0x17C angular velocity (rad/s). The setters are
  0x45A120 SetVelocity(&v) and 0x45A1A0 SetAngularVelocity(&w) (thiscall; they set the momenta too). The port uses them.
- Wheels: [vehicle + 0x2C][i], i < [vehicle + 0x30] = 4: entry + 0xC suspension (CVehicleSuspension, vtable 0x678AEC;
  +0x58 non-zero while touching, set by 0x44F740 SetContact with +0x5C.. contact, +0x6C.. the surface block, +0x8C /
  +0x90 two floats; the port takes +0x8C as the compression: LIKELY, checked live), entry + 0x10 wheel (+0x184 lock,
  +0x190 angle), entry + 0x14 tyre (+0x1C = the index of its surface-pair record: 0x451BC0, CVehicleTyre slot 11, walks
  [0x7833CC] + 8 that many links; the chunk 0x6172A752 of the grip file, 102 records, +4 = count, name at record + 0x78).
- Gravity: [0x78340C] vec3, set by 0x457A50; the force sum multiplies it by the mass (0x44D9E0). LIKELY (0, -9.81, 0).
- The force model is at vehicle + 0x38 (kb 28). Its + 0x24 is SR3's hit flag. While it is set the port leaves the car
  to SR3, so the wheels straighten after a crash as SR3 does it.
- What the port replaces: it starts from the yaw rate and side velocity the car had BEFORE the step (they already hold
  last frame's port values and SR3's collision response). Everything SR3 did to them inside the step is dropped: the
  tyres' side forces, the force model's slide torque (PowerslideSteer) and its yaw cap. SR3's change of the forward speed
  is kept. Emulated: +1 rad/s of yaw and +3 m/s sideways added inside the step leave the result the same to 1e-5; +0.5 m/s
  forward is kept.

Which car: a car whose tyres stand on Tyre_Road records. Only the SRC files use that tyre (flavor_src.json "tyre"), so
SR3's own files and Realism (Tyre_Rally) are never touched (emulated). build_srcport.py writes a class table of the 102
records into the blob, in file order (the flavor builder only changes the mu values, so the order is the same in every
grip file). Each record is classed by its name: Grass / Swamp = D verge, Water = C, Tarmac / Cobbles / Bridge (no snow or
ice) = A. The rest is classed by its Tyre_Rally grip against Tyre_Rally_Tarmac_Top: 0.92 and above A, 0.5 and above B,
below that C (ice, slush). SRC's priority applies: D > C > B > A, under any touching wheel. The Classic courses' SR3
surfaces are Safari tarmac (A) and Safari gravel (B) (importer, 14_importer.md). The player only (the human driver,
vtable 0x6ED0C8). Computer cars only with ai = 1 (see below). Nothing in the air (no wheel touching) or during SR3's hit
recovery, but the steering filter and the body slip keep running there, as in SRC. SRC's state (the filter, the body slip, the load
transfer) starts afresh when the car moves more than 20 m between two steps (a new race, the car put back on the road).

Checked on the emulated CPU, the blob as sr3mods.ps1 relocates it, the game's own setters (tools\srcport_emu.py, 26 checks):
- The chain itself (axle centres, one SRC frame per step): yaw rate and body slip the same as srcmodel.py to 1e-7 rad /
  frame at 100 / 140 / 180 / 230 km/h and 10 to 80 counts.
- As it runs in the game (4 wheels, SR3 steps of 1 / 60 s), steady turns, stick right, speed held (SRC km/h; yaw rate
  rad/s / body slip deg). The same as section 10's table to 0.01 rad/s:

| km/h | 5 | 10 | 20 | 30 | 48 | 80 |
|---|---|---|---|---|---|---|
| 100 | 0.12 / 1.8 | 0.26 / 3.2 | 0.49 / 6.5 | 0.63 / 9.0 | 0.70 / 10.7 | 0.55 / 8.3 |
| 140 | 0.11 / 2.0 | 0.24 / 4.7 | 0.43 / 9.2 | 0.53 / 12.2 | 0.55 / 13.4 | 0.42 / 10.0 |
| 180 | 0.10 / 2.5 | 0.22 / 5.7 | 0.38 / 10.9 | 0.45 / 14.1 | 0.45 / 14.9 | 0.34 / 10.8 |
| 230 | 0.09 / 2.9 | 0.20 / 6.6 | 0.34 / 12.4 | 0.39 / 15.6 | 0.38 / 16.0 | 0.28 / 11.4 |

  Small-stick gain 2.32 / 2.06 / 1.83 / 1.61 rad/s per full stick (section 10: 2.3 / 2.05 / 1.8 / 1.6), ceiling 0.70 /
  0.55 / 0.45 / 0.39, body slip 9-16 degrees at 30 counts. Turn-in (200 km/h, a 20-count step): half the yaw rate after
  2 steps, 90 % after 5, 25 % again 5 steps after the release. The peak is 45 % above the steady value (srcmodel.py:
  46 % by the same measure; the "about 25 %" of section 10 was a looser reading). Gravel (record B) turns less than
  tarmac; nose-down load transfer (0.1) turns more; stick right turns right with the velocity to the left of the nose.
- Left alone: Tyre_Rally files, the air, the hit flag, a computer car with ai = 0, mode 0; mode 1 logs and changes
  nothing.

The tyre force model of the SRC files: back to 2 (PowerslideSteer, SR3's own). The port drops whatever the model does to
the yaw inside the step, so for the player's car the model does not matter. The computer cars, though, keep SR3's turning
on the SRC files (ai = 0), and with model 1 SR3's cars had no turning (kb 28). The rebuild (flavor_src.json force_model
2) differs from the installed car1 files only in chunk 27 + 8, 1 -> 2, in all ten. The grip file is byte-identical. It is
staged in scratchpad agent_srcport\stage_src\Rally, not installed yet.

The computer's cars: the hook sees them too (they are CVehicles). With ai = 1 a computer car on the SRC files gets the same
chain, with its steering value (controls + 8, a fraction of SR3's lock) taken as SRC's stick x ai_gain (1.8). That gain
gives SRC's small-stick yaw per value about what SR3's own turning gives per value (3.7 rad/s at 120-150 km/h, kb 28), so
the AI's own steering controller sees a car it knows. Its speed plan and braking stay SR3's. Taking SR3's lock as a wheel
angle instead would have given the AI 4-5 times less yaw per value than it expects. Not applied (ai = 0) and not driven:
whether the AI then keeps its line needs one race (its path, mean speed, resets).

Files (repository): tools\srcport.c (the port, C, built with clang for i686), tools\build_srcport.py (build, surface
table, --embed into sr3mods.ps1), tools\srcmodel.py (the reference model), tools\srcport_emu.py, tools\srcport_mocktest.ps1;
sr3mods.ps1 Install-SrcPort / Remove-SrcPort (in Set-Handling when the SRC flavor is built; -Off removes it). The data block
(blob + $SrcPortData, 0x23E0 in this build): +8 mode (0 off, 1 observe, 2 on), +0xC ai, +0x10 57.5, +0x14 95, offsets and sign switches,
+0x4C ai_gain, +0x50 the surface classes, +0xD0 counters, +0xDC last_err (1 not SRC files, 2 air, 3 hit recovery), +0xE0 eight per-car states, +0x1E0
-> a ring of 256 player steps x 40 floats (stick, filter, slips, forces, torque, load transfer, D, SR3's own yaw rate and
side velocity after its step, the hit timer ...). The live session (one race, about 4 minutes) is scratchpad
agent_srcport\session.py: observe first, set the signs and the compression field from SR3's own motion, then weaves, a
step and a short full stick with the port on, SR3's own for comparison, optionally (--ai) the opponent.

Open: everything live (not yet run in the game: no SR3 launches on 2026-10-15 night): whether + 0x8C is the compression,
the signs, the override holding to the next step, the gains in game against the table above, the AI with ai = 1;
SR3's dt per step (1 / 60 assumed in the table).
