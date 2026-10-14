# 28 - Handling flavors: SR3's car data, the 1995 / 1998 games measured, and switching a car's handling

The owner asked (2026-10-14) for optional handling flavors: SR3 (SEGA's, the default), SRC (SEGA Rally Championship 1995),
SR2 (SEGA Rally 2, later) and Realism (each car as the real one), chosen for all cars or per car. Tags: VERIFIED (how),
LIKELY, UNKNOWN. "In game" = run on the cabinet by the main session with `tools\pad.py` or by the owner.
(Number 28: 22 is the gap-fill page.)

## 1. SR3's handling data

### Which file a car reads
- The race loader 0x5C5D30 makes one data path per car slot of the race (player and computer cars, stride 0x1F18):
  `"\main_release\cars\%s%s_data"` (0x6C630C, pushed at 0x5C6144) with `"bespoke"` (0x6C6304) for the ten names the code at
  0x5C6000 knows, and the same pattern at 0x6C6360 with `"gravel"` for any other car (an added car: `<name>gravel_data`).
  0x5BFBDD falls back to `SubaruImprezaGravel_data` when a load fails. VERIFIED (code).
- So the per-surface files (`SubaruImprezaTarmac_data`, `MitsubishiEvoDesert_data`, `delta_hf*`, `enduro*` ...) are not
  read for the ten cars: they are SEGA Rally Revo leftovers (power 670-870, rpm 6000-8000, Tyre_Road / Tyre_AllTerrain).
- `0x6E08C0` / `0x6E087C` / `0x6E03E8` (copies of these patterns) are referenced by nothing (VERIFIED: no code or data
  reference) - changing them does nothing.

### `<car>bespoke_data.sbf` (42 chunks, the same layout for every car)
Builder: VehicleGenerator.cpp, 0x46DE30 (from 0x4664EC). Root chunk 41 -> 38 (physics), 39 (AI block "Tyre_AI_Rally", the
same in all cars), 40 (per-car camera: +4 distance 5.1-5.8, +8 height 1.39-1.72; LIKELY, matches the ~5.0 / 1.5 m measured
live). 38 -> 29 (the component list), 33 / 37 (two collision hulls each).

| Chunk | Class (RTTI / code) | Fields | Status |
|---|---|---|---|
| 0 | rigid body (0x46C4D0) | +4 mass 1300 (every car); +8/+0xC/+0x10 inertia = m x (1.67, 2.5, 1.5) (pitch, yaw, roll); +0x14..+0x1C centre of mass (0, 0.05, 0.04) | mass, inertia VERIFIED (code); CoM LIKELY |
| 2 | Aerodynamics | {0 @ 50, 0 @ 50}: no drag or lift | LIKELY |
| 3 | torque curve | count 13, pairs {rpm fraction, torque fraction} from +8: 0 -> 0.6, 0.5-0.75 -> 1.0, 0.875 -> 0.9, 0.91 -> 0.6, 0.95 -> 0.2, 1 -> 0 (all cars) | VERIFIED (file) |
| 4 | Engine (0x450A70, setup 0x46CD20) | +8 peak torque 870 (Nm, LIKELY); +0xC max rpm 8000 (x 2pi/60 -> rad/s, VERIFIED); +0x18 inertia 0.2 | |
| 5 | Turbo (0x471E80) | 16 values | UNKNOWN |
| 6 | Clutch (0x45F810) | +4 50, +8 2000 (capacity, Nm LIKELY) | |
| 7 | Gears (0x4507B0) | +4 final drive, +8 0.15 (shift time, LIKELY), +0xC count = forward + 2, +0x14 ratios R, N, forward (8 slots) | VERIFIED |
| 8 | AutoGearBox (0x45E530) | ups[8] at +0x20, downs[8] at +0x40, fractions of max rpm, INDEXED BY THE CURRENT GEAR INDEX (0 R, 1 N, 2 first ...): 0x45E660 compares engine rad/s / max rad/s with them. SEGA: 0.91 / 0.65 in every slot | VERIFIED (code; in game: hunting when a down point lies above the rpm an upshift leaves) |
| 10 | Differential | +4 drive (0 FWD, 1 RWD, 2 4WD), +8 type (2 open, 0 limited slip, 3 open biased, 4 limited-slip biased): (2,2) 4WD, (0,2) FrontWD, (1,2) RearWD, (2,0) LimitedSlip4WD, (1,0) LimitedSlipRearWD, (0,0) LimitedSlipFrontWD, (2,3) OpenBiased, (2,4) LimitedSlipBiased. SR3: (2,4), +0xC 0.56 (split; which axle UNKNOWN), +0x1C 3 | VERIFIED (RTTI) |
| 12/16/19/22 | Suspension F L/R, R L/R (0x46CA00) | 2.1 (spring Hz?), 0.6/0.6 (damping?), 2000, 0.4/0.4, 0.1, +0x20 0.05 F / 0.04 R (Focus, ST205, Delta, Enduro 0.07 / 0.09), 0.2, 350, mount | mostly UNKNOWN |
| 13/17/20/23 | tyre per wheel (0x46CA70) | 1800, 0.345, 125, +0x1C wheel inertia 2.0 (Bowler, Enduro 3.0) | inertia LIKELY |
| 14 | tyre type | name "Tyre_Rally" (its grip comes from the grip file) | VERIFIED |
| 25 | | {0, 16, 8} ints | UNKNOWN |
| 26 | wheel geometry | 4 x {hub xyz, hard points, radius, width} | |
| 27 | tyre modifiers (0x46D4B0) | +4 load model 2 = Topham (-8000, 16000, 0.25, 50); +8 force model 0 Standard, 1 SegaRally, 2 PowerslideSteer (SR3's), 3 AlwaysSteer | VERIFIED (RTTI) |
| 28 | RollSquatLimitEnforcer | 10 / 30 degrees | LIKELY |

Per car the ten differ only in final drive, gear count / ratios (six-speed 3.64 / 2.95 / 2.36 / 1.86 / 1.50 / 1.18;
ST205 and Delta five-speed 3.64 / 2.75 / 2.00 / 1.50 / 1.18), suspension +0x20, wheel inertia, wheel geometry and camera.
Mass, engine, curve, tyres and differential are the same for all. The ST205 "slippery, the Subaru plays like a dream"
remark (owner): same mass, engine and tyres; the ST205 has a 1.25 m track against 1.43 m, a shorter wheelbase and the other
suspension value (LIKELY the narrow track with the load-sensitive Topham tyre; not tested).

### Grip per surface: one file for all cars
`SurfacePairEffects\surfacepairdata_xdata.sbf`, chunk 0x6172A752: 102 linked records {next, mu, ...the rest identical..., name}
"<tyre>_<surface>[_Top|_Base]", read per race (0x5C6308 in the race loader 0x5C6290). Tyre_Rally: Tarmac 2.25 / 2.475,
BrokenTarmac 2.25 / 2.20, WetTarmac 1.5 / 1.65, Gravel 1.40 / 1.54, Sand 1.5 / 1.65, DryMud 1.40 / 1.54, WetMud 1.17 / 1.29,
snow 1.15, Ice 1.05. The same surfaces exist for Tyre_Road and Tyre_AllTerrain (no SR3 car uses them) and TyreAI* classes.
The mu meaning is LIKELY (ordering; in game the traction limit scales with it).

### Steering
- Input modes (controls + 8, switch 0x5E4430 / table 0x5E4540): mode 1 (the TeknoParrot pad) takes its steering from 0x5E0B20,
  mode 2 from 0x5D4D10. The player's steering routine 0x5D4D10 recomputes controls + 0x18 every frame from two
  input bytes: s = (b1 - b0) / 255, 2 x (0.8 s + 0.2 s|s|) clamped to +-1 (full lock at about half the range), times
  (1 - f) + 0.9 f with f = km/h / 120 capped at 1 (stored at + 0x1C), times a per-mode speed table when above 1. No time
  smoothing (VERIFIED, code); 0x448C00 / 0x45A9F0 then set the wheel angles (geometry only).
- The player's objects (sr3_recorder): car records 0x9DBAC8 + 0x1F18 x i, record + 4 = driver (human: vtable 0x6ED0C8, made
  at 0x5E73B0; driver + 0x7E4 = its record); controls = driver + 0x854 (+8 mode, +0xC brake, +0x10 handbrake, +0x14
  accelerator, +0x18 steering, +0x1C lock factor; accelerator / brake VERIFIED in game), input bytes driver + 0x1C84 ([2]
  accelerator, [3] brake), vehicle [[driver + 0x858] + 4] (CVehicle 0x678864), gears + 8 = gear index, engine + 0x18 =
  rad/s (VERIFIED in game). [0x9EB390] != 0: the game drives the car itself (0x5E9F04 -> 0x5EE350), as after a race.

## 2. The old games, measured

### SEGA Rally Championship (MAME 0.229 srallyc, headless, Lua; owner's laps in ElSemi's emulator)
- Model 2 RAM: player car object 0x500000: +0x14 position, +0x2C world velocity (m/frame; x 216 = HUD km/h, VERIFIED
  against the HUD), +0x38/0x3C/0x40 pitch / yaw / roll, +0x78 gear, +0x7C rpm. Input bytes 0x202050 steer, 0x202051
  accelerator, 0x202052 brake (copied from the ADC by 0x24E8 / 0x26B8; MAME 0.229 cannot set analog ports from Lua, so the
  two stores 0x2514 / 0x26DC were made no-ops in the ROM region and the script writes the bytes).
- Autopilot: pure pursuit on the course's AI line (data ROM 0x8012F0 Desert, 0x8025E0 Mountain), Practice, AT.
- The Celica and the Delta give frame-identical logs: one handling set (VERIFIED for AT).
- AT: 0-50 0.53-0.6 s, 0-100 1.12-1.3 s, 0-150 2.05-2.17 s, 0-180 2.9-3.4 s; upshifts 81 / 150 / 181 km/h; km/h per 1000 rpm
  2nd 15-19, 3rd 22.4-23.0, 4th 26.1-27.1; limit 8800; top 227-244 km/h.
- Grip (`surf_split.py`, 1995 collision attribute bits 16-19 under the car): tarmac sustained lateral p95 2.65 / 2.75 g
  (owner, Celica / Delta, Mountain), gravel 2.35 g, dirt 2.41 g (autopilot, Desert): gravel / tarmac 0.87. Slip angle
  4 / 5 / 7 / 10 degrees at 0.75 / 1.0 / 1.4 / >1.6 g; braking 3.1-3.9 g. Slides (robot) build up in about 1 s, recover in 0.7-1.1 s.
- Lap recorder for ElSemi's emulator: `scripts\handling\src_recorder.py` (read-only; finds the RAM by the car object and
  the display-slot list; VERIFIED in ElSemi's emulator by the owner's laps).

### SEGA Rally 2 (ROM; MAME 0.229 srally2 only boots with its comm-board wait 0x79434 skipped, then the car falls through the road)
- Cars 0 Celica, 1 Delta, 2 Impreza, 3 Stratos, 4 Corolla, 5 Escort, 6 Lancer, 7 Peugeot (names 0xF23EC).
- The debug tuning menu (0x5A16C-0x5AF30) names the fields; the 112-byte tuning block is copied by 0x58994 from the FIXED
  entry 2 (0xF493C) of the per-car table 0xF4A8C, so every car gets: base grip F/R 3.1 / 3.2, spring 5, damper 7, final 3,
  gears 3.5 / 2.0 / 1.5 / 1.25, power adjust 1.4. Engine curve 101 points (AT 0xF4190 peak 41.0, MT 0xF4324 peak 42.6),
  limit 7920 (LIKELY). Surface grip (0xF4B98 -> car + 316, the same for all): tarmac 1.0, gravel 0.84, dirt 0.60, wet 0.88,
  snow 0.90, water 0.38. Per-car geometry (0xF483C, 5 variants).

## 3. Flavors: files, build, switch

### Files (built on the owner's machine; only the numbers ship)
- `Main_release\car<digit>\<car>bespoke_data.sbf` (and `<name>gravel_data.sbf` for added cars), `SurfacePairEffect<digit>\
  surfacepairdata_xdata.sbf` when the flavor changes grip (it sets only its own tyre type's records: SR3's Tyre_Rally stays).
- Build: `python scripts\handling\build_flavor.py scripts\handling\flavor_src.json --out <staging>\Rally` (refuses a folder
  inside the game; checks the layout and a byte-identical round trip of each SEGA file first), then copy into the game.
  Realism: `python scripts\handling\realism_map.py` (realism_specs.json -> flavor_realism.json), then build_flavor.py.
- `handling.json` next to PLAY.bat (`handling.example.json`): `{version, default, cars{name: flavor}, flavors{name:
  {digit, grip_file, steer_return_s}}}`.

### The launcher (patch.ps1: Read-Handling, Set-Handling, Install-SteerReturn, Set-SteerRate)
| What | Where |
|---|---|
| all ten known cars on one flavor | the 's' of "cars" at 0x6C631D -> the digit |
| a per-car mix | 0x5C6144 `push 0x6C630C` -> `call` CARPATH (tools\build_flavorhooks.py, 231 bytes): compares ebp with the ten names (0x4AF410), pushes its own pattern with the car's digit (flags at +8 + 12 x i in 0x5C6000's order) or SEGA's |
| added cars (Hornet) | the 's' at 0x6C6371, one flavor for all of them |
| grip file | the 's' of "Effects" at 0x6C6176, when a flavor in use has one (one per race) |
| steering return | 0x5CFF32 `call 0x448C00` (the human driver's steering handed to the vehicle in 0x5CFE90, every input mode) -> STEER routine (142 bytes): only for the player's vehicle (ecx = [[0x9DBAC8 + 4] + 0x858], record 0's human driver, vtable 0x6ED0C8; the Classic opponent runs the same code and passes unchanged), toward / across the centre at most RATE per call, outward at once, result to the vehicle only (controls + 0x18 stays raw: mode 1's 0x5E0B20 builds its next value from it, and writing it back held the steering, in game 2026-10-14); RATE = 1 / (s x 60) written at each race start from the player's car (library node [0x9DBDA0 + 0xC], +4 id). A first hook on 0x5D4D10's exits (0x5D4F28 / 0x5D4F31) never ran: with the TeknoParrot pad (input mode 1) the value comes from 0x5E0B20 (in game 2026-10-14) |
All take effect when the next race loads. A missing folder or car file: that car keeps SEGA's file (Log line).

### SRC flavor numbers (flavor_src.json) and the four in-game tests (ST205, Classic Mountain RT, AT, pad.py pattern)
| | gears km/h per 1000 rpm (design) | torque | grip | 0-50 / 0-100 / 0-150 / 0-180 s | upshifts km/h | notes |
|---|---|---|---|---|---|---|
| SR3 stock | 6-speed SEGA | 870 | SR3 | 1.21 / 3.42 / - / - | 62 / 82 / 114 | baseline |
| test 1 | 9.6 / 18.9 / 22.7 / 26.6 | 870 | SR3 | - | - | AT hunted 1st <-> 2nd: one 0.60 down point above the rpm the 1->2 upshift leaves |
| test 2 | same | x2.5 | SR3 | 0.80 / 1.60 / 2.66 / 3.52 | 62 / 132 / 160 | per-gear down points: no hunting; 0.45 s at the limiter at launch, slip 15-20 % |
| test 3 | 11.8 / 23.0 / 26.4 / 29.2 (slip corrected) | x2.0 | x1.35 | 0.69 / 1.65 / 2.77 / - | 82 / 165 / - | measured 9.4 / 19.5 / 22.5 |
| test 4 (candidate) | same, upshift 0.89 / 0.823 / 0.91 | x2.5 | x1.35 | 0.62 / 1.44 / 2.50 / 3.12 | 73 / 138 / 187 | installed; the owner's laps next |
| SRC target | 9.6 / 18.9 / 22.7 / 26.6 | | | 0.53 / 1.12 / 2.17 / 3.37 | 81 / 150 / 181 | |
Grip scale 1.35 from SR3's own traction limit (steady 1.85 g in 2nd at full throttle) against SRC's 2.4 g launch and
2.65-2.75 g cornering; SR3's cornering grip is still unmeasured (the steering step hit the scenery twice). Clutch capacity
follows the torque scale. Tyre_Road records = SR3's Tyre_Rally tarmac x SRC's surface ratio (gravel 0.87, dirt 0.89) x 1.35.

### Realism (realism_specs.json: one row per car with source URLs; realism_map.py)
Real mass; inertia scaled by the real dimensions; SR3 torque = real Nm x 1.266 (the Impreza WRC2008 keeps SR3's
acceleration per kg); curve from the torque and power peaks; real gear count, evenly spaced ratios, final drive x limit / 8000
so every car keeps SR3's own top speed at its limiter (228-235 km/h design; a first version matched the road speed at the
power peak and left the Hornet at 141 km/h and the others at 170-218), the Hornet a design top of 265 km/h with 1st good for
~100 km/h (a road-course Cup setup); drivetrain classes as in chunk 10 (Hornet: LimitedSlipRearWD). Evo X = Group N
(SR3 is 2008, R4 came in 2011). Where real numbers do not fit SR3's model: tyre width is not in SR3's grip (mu x load), real
ratios are not published, the split field's axle is unknown, several rev limits / peak rpms are estimates (marked in the file).

## 4. Open
SR3's own cornering grip and slip curve; the SegaRally force model's behaviour; caching of car / grip files between races;
the AI's pace on flavored cars (they load the same files); SR2 driving data (Supermodel with an external reader); per-car
grip for Realism (a free tyre class or a per-car grip field still to be found).
