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
- Mode 1 (the TeknoParrot pad), 0x5E0B20, measured in game 2026-10-14 (ST205, pad.py steps, one row per physics step):
  the pad's two steering bytes (driver + 0x1C84 left, + 0x1C85 right, 0..255 each) follow the stick linearly (0.25 -> 63,
  0.5 -> 127, 0.75 -> 191, 1.0 -> 253..255; 1 at rest on the left byte). s = (b1 - b0) / 300 (0x6EFCAC), clamped to +-1; the
  cubic term is multiplied by 0 (no curve); times the lock factor 0.8 - 0.2 x min(mph / 100, 1) (mph = |velocity| x 2.2369;
  stored at + 0x1C, handed to the vehicle by 0x448CA0); times the car's speed table (`[[0x9DB810] + 24 x [0x9DB944] + 0x18]`,
  pairs {mph, factor}; [0x9DB944] = 6 with the ST205: 1.5 @ 0, 1.4 @ 10, 1.3 @ 25, 1.2 @ 35, 0.72 @ 45, 0.66 @ 55, 0.62 @ 65,
  0.58 @ 75, 0.54 @ 90, 0.5 @ 110 mph; entries 1 / 2 (Focus, Impreza) end at 0.33; LIKELY one entry per car id), clamped to
  +- the table factor. No time smoothing or rate limit: a stick step shows on the next physics step. Then 0x448C00: wheel
  angle (wheel + 0x190) = value x wheel + 0x184 (0.345 rad for the ST205's fronts) + toe, Ackermann (0x45A9F0); 1.012 at rest
  gives 0.349 rad (20 deg). So a full stick is full lock at rest but 0.253 (5 deg) above 110 mph; half a stick at 180 km/h is
  0.127. The tail of 0x5E0B20 (0x5E0E00..0x5E19BD, mode 1 only) works out controls + 0x20 / + 0x24 / + 0x28 (assists, not
  decoded) and does not touch + 0x18. 0x5CFE90 hands the vehicle brake / accelerator (+0xC / +0x14, swapped in reverse),
  handbrake (+0x10), steering (+0x18 -> 0x448C00) and the lock factor (+0x1C -> 0x448CA0).
- The player's objects (sr3_recorder): car records 0x9DBAC8 + 0x1F18 x i, record + 4 = driver (human: vtable 0x6ED0C8, made
  at 0x5E73B0; driver + 0x7E4 = its record); controls = driver + 0x854 (+8 mode, +0xC brake, +0x10 handbrake, +0x14
  accelerator, +0x18 steering, +0x1C lock factor; accelerator / brake VERIFIED in game), input bytes driver + 0x1C84 ([2]
  accelerator, [3] brake), vehicle [[driver + 0x858] + 4] (CVehicle 0x678864), gears + 8 = gear index, engine + 0x18 =
  rad/s (VERIFIED in game). [0x9EB390] != 0: the game drives the car itself (0x5E9F04 -> 0x5EE350), as after a race.

### The tyre force models (chunk 27 + 8), read from the code (2026-10-15)
The names (Standard, SegaRally, PowerslideSteer, AlwaysSteer) are SR3's own class names (RTTI). What the code does with each
(Rally.exe, static reading; VERIFIED = read in the code, LIKELY = inferred):
- Built by 0x46D4B0 (called from 0x46E236 / 0x46E5FB with the vehicle being built) from chunk 27: + 4 the load model (0 or 2
  -> a 0x18-byte Topham object, vtable 0x679990, at vehicle + 0x34), + 8 the force model through the jump table 0x46D5C8 -> an
  object at vehicle + 0x38 (one per car; an earlier version of this page said tyre + 0x34 / + 0x38: wrong). Only + 4, + 8 and
  the pointer + 0xC (Topham's four floats) are read; + 0x20 .. + 0x2C (zero in every file) are not. VERIFIED.
  | + 8 | name | object (vtable, size, constructor) | reset (slot 2) | model number (slot 3) | per-step update (slot 4) |
  |---|---|---|---|---|---|
  | 0 | Standard | 0x6779EC, 0x38, 0x447800 | 0x46C6D0: + 8 .. + 0x1C only | 0x430AB0 -> 0 | 0x430AF0: none (ret) |
  | 1 | SegaRally | 0x6799A8, 0x38, 0x447800 | 0x46C5B0: + 8 .. + 0x34 | 0x471C80 -> 1 | 0x44FC30 |
  | 2 | PowerslideSteer (every SR3 car) | 0x6799C0, 0x3C, 0x46C630 | 0x46C650: + 8 .. + 0x38 | 0x4478D0 -> 2 | 0x4500C0 |
  | 3 | AlwaysSteer | 0x6799D8, 0x38, 0x447800 | 0x46C6D0 (Standard's) | 0x465DD0 -> 3 | 0x44FC20: none (ret) |
  The base class's vtable is 0x6779A4 (slot 2 purecall 0x4AEFD1). Slot 0 is the destructor, slot 1 0x4308E0 (sets + 4 = the
  vehicle) is shared by all. Common fields: + 8 .. + 0x10 force, + 0x14 .. + 0x1C torque (world), + 0x20 the yaw torque as a
  number, + 0x24 the hit flag, + 0x28 its timer, + 0x2C .. + 0x34 the direction to turn back to (below).
- Where the outputs go (VERIFIED): the vehicle step 0x44F5F0 (CVehicle 0x678864 slot 5 0x45C820 -> 0x45C9A1) calls 0x44DB80:
  the load model's update, every tyre's forces (0x453530), then the force model's update (0x44DBD2). 0x44D6C0 then adds the
  wheels' forces and torques (0x45E120, 0x45E1D0, 0x451B10, 0x451A60), two vectors of [vehicle + 0xC] (+ 0x18, + 0x24;
  LIKELY aero) and the model's + 8 .. + 0x1C
  (0x44D956) to the body's force (body + 0x1A4) and torque (+ 0x1D4) sums. + 0x20 is read by nothing. The tyres never look
  at the force model: 0x453530 branches on the tyre's own class (vtable 0x6781C4, its slot 3 = 0x430AB0 -> 0) and turns each
  tyre's axes by its wheel angle (0x45A980 -> wheel + 0x190, 0x452650, sin / cos table 0xA33A00).
- Where the game asks the model number: one place, 0x4490D0 (called every frame from the human driver's update 0x5EA0AB and
  from 0x5D1960): if slot 3 returns 2, + 0x38 = 90.0 ([0x6EDCC4]); nothing reads + 0x38 (LIKELY a leftover). No code compares
  the vtables (they are only written by the constructors; 0x4490F0, which would swap in a Standard model, is never called).
  VERIFIED (code).
- The + 0x24 flag is a HIT state, not a powerslide state (corrected; the earlier "no non-zero write found" was wrong):
  0x44F910 writes + 0x24 = 1, + 0x28 = 1.0 (s). It is reached only through the wrapper method 0x449080 from the contact
  handler 0x5B2F00 (0x5B34A3; called from 0x5B3654 when the car has contacts): for a contact with the car, when the contact's
  speed x 2.2369 (mph) > 40 and acos|n . a| x 57.3 > 40 degrees (n the contact normal, a a car axis from the car object's
  vtable + 0xC; LIKELY its forward axis, so a hit from the side or at an angle, not head on). Any model gets it. While it is
  set (VERIFIED): 0x448C00 and the second steering setter 0x45CF40 (from 0x449A4B) write 0 to every wheel's angle (wheel +
  0x190, 0x448C68 - 0x448C86, 0x45CF9D); 0x452B40 multiplies the tyre's load term (tyre + 0x50, and the value it hands to
  0x452570) by 0.3 (0x452C12); 0x45E4B0, the throttle getter (vehicle controls + 0x18, read by the engine 0x450B6A / 0x450BBC
  / 0x450D8C and the tyre forces 0x452DCA), returns half (0x45E4B4). + 0x2C .. + 0x34 is written by 0x449090 from 0x5AC27C
  (in 0x5ABE40; LIKELY the road direction at the car).
- Who clears the flag (VERIFIED): PowerslideSteer's update (the timer runs down by dt and the flag drops below 0, 0x4502A6;
  or earlier, 0x4503A7, once the heading is within 15 degrees of + 0x2C's direction and |yaw rate| < 0.262 rad/s), and the
  resets of SegaRally (0x46C5B0) and PowerslideSteer (0x46C650). Standard's / AlwaysSteer's reset 0x46C6D0 does NOT. So with
  model 2 a hard hit takes the steering away for at most 1 s while the model swings the car back toward the road; with
  models 0, 1 and 3 nothing runs the timer down: after the first such hit the wheels stay straight, the tyres keep 0.3 of
  their load term and the throttle half for the rest of the race, until the vehicle is reset (CVehicle slot 2 0x45BF10 calls
  every component's slot 2; when the game calls it was not traced, LIKELY a respawn or restart; for 0 and 3 not even then).
- PowerslideSteer's update 0x4500C0 (VERIFIED, read in full; X = body + 0xF8 side axis, Z = body + 0x104 forward axis, up =
  body + 0xEC, rows of the matrix at body + 0xA4 (0x459F80); the wheel hubs lie at x +-0.62, z +-1.2; m = body + 8 = mass;
  vehicle controls: + 8 steering, + 0xC lock factor, + 0x10 brake, + 0x14 handbrake, + 0x18 throttle (0x448BD0 / 0x448BE0 /
  0x448BF0 / 0x448C00 / 0x448CA0 from 0x5CFE90); wheel + 0x18 = spin rate, 0x45F310):
  ```
  F = T = 0
  sn = steer / |lock| ;  vs = |v.X| ; vf = |v.Z| ; r = w.up               (sn: the stick after the speed table)
  cap = |r| > 3.4 [0x707414] ? -5000 (r - 3.4 sign r) : 0                  yaw-rate cap, always on
  if hit:                                                                  timer -= dt; timer < 0 -> hit = 0
      d1 = dir.Z' , d2 = dir.X'   (Z', X' flattened, normalised)
      d1 >= 0: d1 > cos 15 deg and |r| < 0.262 -> hit = 0 ; else Th = 25000 (0.6 d2 + 0.4 sign d2)
      d1 <  0: Th = 25000 sign(d2) (1 - 2 d1)
  elif [0x707400] (= 2) and handbrake <= 0 and wheel[0].spin > 0:
      for each wheel: if in contact (susp + 0x58) and -susp+0x2C < susp+0x8C < susp+0x28 (LIKELY within its travel):
          if vs < 3 or vf < 3: break                                        (3 m/s, 0x677F30)
          t = m min(|v|, 25)
          r sn < 0 (turning against the steering):  T = t (0.84 sn - 0.4 r)            0x707408, 0x6F0098
          else:  k = 1 - min(|sn|, 0.3) / 0.3 ;   T = t (0.4 sn - 0.2 k^2 r)            0x707404, 0x6EFED0
          break
  T = hit ? Th : T + cap ;   torque = T x up ;  + 0x20 = T
  ```
  So the slide torque only exists with at least 3 m/s sideways (about 6 degrees of slip at 100 km/h): it turns the car with
  the stick in any slide (0.4 m v sn, e.g. 13 kN m = 4 rad/s^2 at 25 m/s and sn = 1 on 1300 kg / 3250 kg m^2; sn = the stick
  x the car's speed table, so about 0.66 at full stick and 25 m/s on the ST205) and
  catches it hard when the stick is against the rotation. Below that, SR3's cars turn by the tyres alone, as with model 1.
- SegaRally's update 0x44FC30 (VERIFIED, read in full):
  ```
  F = T = 0
  vs = v.X ; vf = |v.Z|
  |vs| < 3 and vf < 3 -> return ;  a tyre's + 0x4C < 0 -> return (LIKELY its load; nearly never)
  q = (|vs| - vf) / (|vs| + vf) ;  q <= 0 -> return                       only with more than 45 degrees of body slip
  steer <= 0 -> return                                                    only ONE steering sign (s > 0: right, LIKELY)
  sn = steer / |lock| ;  p = |m vs| ;  r = w.up
  r steer > 0: c = 0.75 |sn| (0x6F00B0); |r| >= c -> return; g = 1 - |r| / c      else g = 1
  Tt = (sum of every tyre's torque about the CoM, 0x451B10 + 0x451A60) . up
  T = (p - Tt) q g sn ;  torque = T x up (0x42DD50) ;  + 0x20 = T
  ```
  The car's yaw torque becomes Tt (1 - f) + p f, f = q g sn: pulled toward |m vs| (a momentum used as a torque) in a spin, to
  one side only. It never touches the hit flag. Nothing it reads comes from a file (mass, velocities, axes, steering, the
  tyres' torques, 3 and 0.75), so no SR3 file leaves a parameter of it at 0. LIKELY an unfinished experiment.
- Standard (0) and AlwaysSteer (3) are the same code (update `ret 4`, reset 0x46C6D0); the only reader of the number tests for
  2, so "AlwaysSteer" has nothing behind its name in this build. Against PowerslideSteer both lose the slide torque, the
  3.4 rad/s yaw cap and the swing back after a hit, and a hit leaves the wheels straight for good (even a reset keeps it).
- Files (VERIFIED, fm_list.py over Main_release\cars and \car1): every SEGA car file carries load model 2, Topham (-8000,
  16000, 0.25, 50) and force model 2: the ten bespoke files, the Revo leftovers (MitsubishiEvo / SubaruImpreza / delta_hf
  Desert / Gravel / Tarmac, hornetgravel; Topham 0.35 in the three Desert files, tyres Tyre_Road / Tyre_Rally /
  Tyre_AllTerrain); delta_hf_data, enduro{desert,gravel,tarmac}_data and subaruimprezadesertwheels_data are not physics
  files. None uses model 1. The installed SRC files (car1): model 1, Tyre_Road, torque 2175.
- In game (owner, 2026-10-15): the SRC files with + 8 = 1 - "steering seems to be completely disabled". Cause LIKELY (from the
  code; not yet seen live): the hit flag set by the first hard hit (over 40 mph, over 40 degrees) and never cleared, since
  only PowerslideSteer runs its timer: wheels straight, tyres at 0.3 of their load term, half throttle, for the rest of the
  race or until a reset. Before that hit model 1 steers with the tyres alone, with no slide torque. If the live check shows
  the steering gone with the flag still 0, the cause is the missing slide torque instead (the tyres alone too weak).
  Ways to make model 1 steer: (a) force model 2 again (the SRC port plans that); (b) only PowerslideSteer cars take the hit
  state: 0x449080 (16 bytes, now 8B 41 04 8B 48 38 E9 85 68 00 00 CC x5) -> `mov eax,[ecx+4]; mov ecx,[eax+0x38]; cmp byte
  [ecx],0xC0; je 0x44F910; ret` = 8B 41 04 8B 48 38 80 39 C0 0F 84 81 68 00 00 C3 (the four vtables' low bytes C0 / A8 / D8 /
  EC differ). (b) leaves model 1 without the slide torque, the yaw cap and the swing back after a hit.
- Live check (one race, about 5 minutes; scratch agent_fm1\fm_watch.py, read only: logs speed, side / forward speed, yaw rate,
  steering, lock, throttle, handbrake, the model's class, flag, timer, + 0x20 and the four wheel angles every 10 ms, and prints
  each flag change): SRC flavor (model 1) on the ST205, any track with walls. 1) 30 s of weaving at 40-60 km/h without touching
  anything: flag 0, wheel angles follow the stick, yaw rate follows it. 2) Hit a wall from the side above 65 km/h: flag 1,
  timer 1.00 that never runs down, wheel angles 0, the yaw rate no longer follows the stick. 3) Leave the course for a
  respawn: does the flag go back to 0? 4) The same hit on SR3's handling (key 1, model 2): flag 1, cleared within 1 s.

## 2. The old games, measured

### SEGA Rally Championship (MAME 0.229 srallyc, headless, Lua; owner's laps in ElSemi's emulator)
- Model 2 RAM: player car object 0x500000: +0x14 position, +0x2C world velocity (m/frame; x 216 = HUD km/h, VERIFIED
  against the HUD), +0x38/0x3C/0x40 pitch / yaw / roll, +0x78 gear, +0x7C rpm. Input bytes 0x202050 steer, 0x202051
  accelerator, 0x202052 brake (copied from the ADC by 0x24E8 / 0x26B8; MAME 0.229 cannot set analog ports from Lua, so the
  two stores 0x2514 / 0x26DC were made no-ops in the ROM region and the script writes the bytes).
- The steering and turning code itself (no fitting): 29_src_steering_code.md.
- Autopilot: pure pursuit on the course's AI line (data ROM 0x8012F0 Desert, 0x8025E0 Mountain), Practice, AT.
- The Celica and the Delta give frame-identical logs: one handling set (VERIFIED for AT).
- AT: 0-50 0.53-0.6 s, 0-100 1.12-1.3 s, 0-150 2.05-2.17 s, 0-180 2.9-3.4 s; upshifts 81 / 150 / 181 km/h; km/h per 1000 rpm
  2nd 15-19, 3rd 22.4-23.0, 4th 26.1-27.1; limit 8800; top 227-244 km/h.
- Grip (`surf_split.py`, 1995 collision attribute bits 16-19 under the car): tarmac sustained lateral p95 2.65 / 2.75 g
  (owner, Celica / Delta, Mountain), gravel 2.35 g, dirt 2.41 g (autopilot, Desert): gravel / tarmac 0.87. Slip angle
  4 / 5 / 7 / 10 degrees at 0.75 / 1.0 / 1.4 / >1.6 g; braking 3.1-3.9 g. Slides (robot) build up in about 1 s, recover in 0.7-1.1 s.
- Lap recorder for ElSemi's emulator: `tools\handling\src_recorder.py` (read-only; finds the RAM by the car object and
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
- Build: `python tools\handling\build_flavor.py tools\handling\flavor_src.json --out <staging>\Rally` (refuses a folder
  inside the game; checks the layout and a byte-identical round trip of each SEGA file first), then copy into the game.
  Realism: `python tools\handling\realism_map.py` (realism_specs.json -> flavor_realism.json), then build_flavor.py.
- `handling.json` next to PLAY.bat (`handling.example.json`): `{version, default, cars{name: flavor}, flavors{name:
  {digit, grip_file}}}` (older files' steer_rate / steer_return_s / steer_linear are ignored: every handling steers with SEGA's own steering).

### The launcher (patches.ps1: Read-Handling, Set-Handling, Sync-RaceFlavor, Remove-SteerHook, Install-SrcPort)
| What | Where |
|---|---|
| all ten known cars on one flavor | the 's' of "cars" at 0x6C631D -> the digit |
| a per-car mix | 0x5C6144 `push 0x6C630C` -> `call` CARPATH (tools\build_flavorhooks.py, 231 bytes): compares ebp with the ten names (0x4AF410), pushes its own pattern with the car's digit (flags at +8 + 12 x i in 0x5C6000's order) or SEGA's |
| added cars (Hornet) | the 's' at 0x6C6371, one flavor for all of them |
| grip file | the 's' of "Effects" at 0x6C6176, when a flavor in use has one (one per race) |
| steering | SEGA's own for every handling. The STEER hook of 2026-10-14 / 15 (0x5CFF32 `call 0x448C00` -> a routine of ours: steering return, then 1:1, then a steering rate) is gone; Remove-SteerHook writes SEGA's call back when a game still holds it (PLAY.bat run again on a game an earlier launcher had hooked) |
| turning of the SRC handling | CVehicle vtable 0x678864 slot 5, the entry 0x678878 (= 0x45C820, the vehicle step) -> SRCPORT (tools\build_srcport.py from tools\srcport.c, about 9.5 KB plus a zero-filled log, relocated by Install-SrcPort): after each step, a car whose tyres stand on Tyre_Road records (the SRC files) gets SRC's yaw rate and side velocity (29_src_steering_code.md section 12). Installed by Set-Handling when the SRC flavor is built, taken out when it is not and by -Off. Log: "SRC turning: in (0x...)" |
All but the turning take effect when the next race loads. A missing folder or car file: that car keeps SEGA's file (Log line).
The turning acts at once on any car that loaded the SRC files.

### One handling per race, the stick 1:1 for SRC (2026-10-14)
The owner: "Ok, let's give SRC handling a chance, but only if the 'pace' applies to all cars in the race (balance) and you fix
the under steering with the wheels tracking the analog pad 1:1 (as much as possible) just like SRC".
- Race-wide flavor (`Sync-RaceFlavor`, every pass of Watch-Tracks): all ten flags of the per-car routine, the added cars'
  character and the grip file's character are set to the flavor of the player's car (the library node [0x9DBDA0 + 0xC],
  set when the car select is confirmed, before the gearbox page and the load), so the computer's cars load the same files; a
  car with no file in the flavor keeps SEGA's. It writes only when the player's car or its flavor changes (the next car
  select, a handling key). Log at the race start: "Handling: this race on <flavor>, the player's car's (<car>); every car in
  it loads that handling." The per-car choice in handling.json now means "the handling a race gets when you drive this car".
  VERIFIED in game: with the ST205 on SRC the Classic opponent (record 1, the Lancia) read 2175 x 1.31 = 2844 Nm (the AI's
  own torque factor: 870 -> 1138 on SEGA's files), max 921.5 rad/s (8800 rpm) and SRC's four gears 2.855 / 1.465 / 1.276 /
  1.154 (its own wheel radius), where the old per-car flags left it on SEGA's 870 Nm and six speeds.
- The opponent on SRC (Classic, Desert '95, the player standing at the start, 40 s from the green light, positions every
  0.25 s): 1855 m, 168 km/h mean, no reset or jump, height range as on SEGA's files; on SEGA's files 1550 m, 140 km/h.
  It keeps to the road and runs about 20 % faster, as the player's car does.
- The stick 1:1 (STEER routine's LINEAR, + 8; handling.json `flavors.<name>.steer_linear`, on for src by default, off for
  realism; SEGA's own never): the player's value becomes (b1 - b0) / 255 from the two pad bytes, clamped to +-1, so full stick
  = full lock at any speed, at once; SRC's steering return is 0 (off) by default. Log: "Steering: <car> (src) follows the
  stick 1:1 ...". Emulated (unicorn): stick 0.5 -> 0.498, full -> +-1.0, LINEAR 0 -> the game's value, the return limit still
  works on top, other vehicles pass unchanged.
- Yaw response, the same measure for both games: yaw rate regressed on the stick (|stick| < 0.5, best lag), per speed band.
  SRC (the owner's Mountain laps, ElSemi; stick = (byte - 127) / 95, the pad's range 32..222): Celica 2.49 (100-140 km/h),
  2.00 (140-180), 2.05 (180-230, r = 0.87) rad/s per full stick, lag 2 frames; Delta 2.37 / 2.20 / 2.07. SR3, ST205 on SRC,
  a weave of +-0.2 stick at 0.7 Hz on Desert '95's start straight: SEGA's steering chain 1.13 rad/s per stick (118-153 km/h,
  r = 0.37, its value 0.305 x stick there); with the stick 1:1 1.95 rad/s per stick (159-221 km/h, r = 0.61; value 0.26
  x stick was the game's own there). So 1:1 brings the yaw gain to SRC's (2.0-2.1) without a change of the tyre force model;
  SR3's lag is longer (about 10 physics steps, 0.16 s, against 2 frames in SRC).
- Not tried: the force models 0 / 1 / 3 (chunk 27 + 8) for the lag; they need their own car files and a race each.

### Steering rate in place of the return and of 1:1 (2026-10-15)
The owner, having driven SRC with the stick 1:1: "steering return knobs are useless. off is ok. replace those knobs with
rad/s steering rate. let's try 1.5. 1:1 was a bad idea". So the steering return and the 1:1 mode are gone (handling.json
steer_return_s / steer_linear are ignored); each handling has a steering rate R (`flavors.<name>.steer_rate`, rad/s, the turn
rate a full stick asks for; 0 = SEGA's own chain). Defaults: src 1.5, realism and sr3 0. Keys 4 / 6 -/+ 0.1 (0.5 .. 3.0),
5 off / back on; label "Steering: 1.5 rad/s at full stick" / "SEGA Rally Championship handling, Toyota Celica ST205"; the
settings app's handling pop-up has SRC's rate as a number (0 = the game's own). The STEER routine keeps the stick linear and
makes the wheels at full stick min(lock, R x (L + K v^2) / v): A = R L / lock, B = R K / lock, value = stick x min(1, A / v
+ B v), v from the wrapper's vtable + 0x30 (m/s). L per car (chunk 26, front minus rear hub z): C4 2.601, Focus 2.654,
Impreza 2.622, SX4 2.487, Evo 2.604, 207 2.550, ST205 2.519, Delta 2.473, Bowler 2.712, Enduro 2.628, Hornet 2.847 m; the
ST205's lock 0.345 rad (read in the race). K = 0.0023 s^2/m (the main session's estimate from the two earlier runs).
In game 2026-10-15 (ST205 on SRC's files for every car, Classic Desert '95's start straight, a speed held by the throttle and
a weave of the stick, yaw rate regressed on the stick over the part before any knock, the same measure as above):
| speed | full-stick fraction used | amplitude | yaw rate per full stick | r | asks for 1.5 at full stick |
|---|---|---|---|---|---|
| 64 km/h | 0.797 (K 0.0023) | 0.3 | 1.60 rad/s | 0.93 | 0.75 |
| 64 km/h | 0.745 / 0.742 / 0.751 (K 0.0016 / 0.0016 / fit) | 0.3 | 1.60 / 1.48 / 1.28 | 0.96 / 0.95 / 0.97 | 0.70 / 0.75 / 0.88 |
| 124 km/h | 0.558 / 0.529 | 0.15 | 1.58 / 0.96 | 0.79 / 0.63 | 0.53 / 0.83 |
| 183 km/h | 0.617 | 0.2 | 2.37 (at the grip limit, 2.4 g: not the linear gain) | 0.91 | - |
| 183 km/h | 0.569 | 0.08 | 0.76 (0.7 s clean only) | 0.62 | - |
At 60 km/h the yaw per full stick is R within -15 / +7 %, at 120 km/h the two clean runs scatter 0.96-1.58 around R (the
model's 0.66 there against 0.53 / 0.83 asked for); at 180 km/h the straight leaves too little clean distance for a weave
small enough to stay in the linear range, so 180 is NOT verified. K stays 0.0023 (a fit through the noisy 120 km/h point,
K 0.0013, did worse in the check race). The 1:1 run's 1.95 rad/s at 190 km/h was also at the grip limit (2.4 g), not linear.
Not continued: the owner had the steering rate taken out the same night (next section).

### Taken out again: the steering rate; SRC on SEGA's SegaRally tyre model (2026-10-15)
The owner, after kb 29 (SRC's steering read from the Model 2 code): "remove the rads tuning and put realism on realism default
with the (resulting) acceleration scaled to SR3 <-- nothing else. make sure SR3's default model is untampered with. install C on
the SRC option (key 2)". C = kb 29's cheap experiment: SR3's own tyre force model 1 "SegaRally" in the SRC files.
- Launcher and settings app: the steering rate, its keys, labels, handling.json fields and the pop-up's field are gone; every
  handling steers with SEGA's own chain (Remove-SteerHook above). handling.json / handling.example.json: no steer_* fields.
- SRC (`flavor_src.json` `force_model` 2 -> 1): built with build_flavor.py into a staging folder and copied into
  Main_release\car1; against the files it replaced, chunk by chunk, the ONLY change in all ten is chunk 27 + 8, 2 -> 1
  (the five compressed files differ in every byte, their chunks do not). The grip file SurfacePairEffect1 is byte-identical.
- Realism: realism_map.py's defaults (pace sr3: each car's torque scaled to its SEGA file's launch, the Bowler with its measured
  pace_trim 0.84) and nothing else (SR3's force model 2, no grip file); identical to the agent's stage_r2 build, which differs
  from the one installed before only in the Bowler.
- SR3's own: SEGA's files are untouched (Main_release\cars: the ten bespoke files and SurfacePairEffects dated 2008-04-29; the
  only newer files there are the added Hornet's); a car on SR3 loads SEGA's paths (flag 0 / 's'), and no steering hook.
- Not yet driven in game.

### SRC's turning from SRC's code, in SR3 (2026-10-15, "option B")
The owner: "I still feel this guessing numbers game isn't the way to go". So after every SR3 vehicle step, the player's car
on the SRC files gets its yaw rate and side velocity from SRC's own chain (29_src_steering_code.md sections 2-8). That chain
runs on SR3's speed, surfaces and suspension. SR3 keeps the speed along the car (the SRC files' engine and gears, SR3's
brakes), pitch, roll, walls, the air and its hit recovery. How it works, the SR3 objects it uses and the checks:
29_src_steering_code.md section 12.
- Which car: the port recognises the SRC files by their tyre (Tyre_Road), so SR3's own files and Realism are never touched.
  It runs for the player's car; the computer's cars only with ai = 1 (data block + 0xC, not set by the launcher).
- The force model of the SRC files goes back to 2 (PowerslideSteer). The port throws away what the model does to the yaw
  inside the step, so the player's car does not depend on it, but the computer cars keep SR3's turning on these files
  and model 1 left SR3's cars without turning (above). Built (flavor_src.json force_model 2) into scratchpad
  agent_srcport\stage_src\Rally. Against the installed car1 files the only change is chunk 27 + 8, 1 -> 2, in all ten;
  the grip file is byte-identical. NOT installed yet: it needs the owner's OK.
- Emulated (the blob in a copy of Rally.exe's image, the game's own setters): kb 29's steady-turn table to 0.01 rad/s
  (small-stick gain 2.32 / 2.06 / 1.83 / 1.61 rad/s per full stick at 100 / 140 / 180 / 230 km/h, ceiling 0.70 / 0.55 /
  0.45 / 0.39, body slip 9-16 degrees), turn-in in 2 / 5 steps (half / 90 %), srcmodel.py frame for frame. Not yet in the game.
- The computer's cars on the SRC files: with ai = 0 they keep SR3's turning with SRC's engine and gears (driven before,
  section above). With ai = 1 the port turns them too, taking their steering value as SRC's stick x 1.8 (the gain that gives
  them about SR3's yaw per steering value, so their own controller copes). Not driven yet: one race tells whether they
  keep their line.
- Live check, one race of about 4 minutes: scratchpad agent_srcport\session.py (observe with SR3's own turning first,
  settle the signs and the compression field, then the port on: weaves, a step, a short full stick; SR3's own for
  comparison; --ai for the opponent).

### Live keys (owner, 2026-10-14: "Do A and A+, assign to num keys. Live labels ... (camlab style)")
Whenever a flavor is built (Main_release\car1 / car2), the per-car routine and the steering hook go in even with no
handling.json (every car on SEGA's handling), and while the game window is in front ([0x728CF4] = the foreground window):
| Key (number row or keypad) | Does |
|---|---|
| 1 / 2 / 3 | SR3's own / SRC / Realism for the car: on the car select the HIGHLIGHTED one (camera block + 0x227C CARSEL: 0x606510 with the hash 0x6EACE04A of "ID_SELECTOR_CARSELECT" = the highlighted entry's data, the car id; 0x606490 gives its place in the list instead, which made the first try pick C4 for the highlighted ST205), anywhere else the player's car ([0x9DBDA0 + 0xC] +4). Its flag in the per-car routine (an added car: the shared 's' at 0x6C6371), the grip file's 's'; from that car's next race; handling.json is written |
| 0 | show what the car has |
Each key shows a label for 2.5 s: the camera block's popup (first line at block + 0x2400, second at + 0x2480, the green of the
alternative-track titles), e.g. "Handling: SEGA Rally Championship" / "Toyota Celica ST205, from its next race". (Keys 4 / 6 / 5 were the steering return, then the steering rate: taken out 2026-10-15.)
VERIFIED in game 2026-10-14: ST205 highlighted -> 2 -> "Handling: SEGA Rally Championship / Toyota Celica ST205, from its next
race"; the next car (Focus) -> keypad 3 -> Realism; in a race 6 / 5 / 5 -> rate 0.333 / 0 / 0.333 per frame.

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

### Realism at SR3's pace (realism_map.py --pace sr3, the default; 2026-10-14)
The owner: "add a multiplier that matches the accel and speed with SR3 default". With "pace": "sr3" in the table
build_flavor.py scales each car's peak torque (and the clutch with it) so that a launch model gives the built car the same
0-100 + 0-150 km/h as SEGA's own file of that car, and gives a car with a design top speed (the Hornet) SEGA's file's top
speed at the limiter. The model: torque curve x peak x gear x final drive / wheel radius x 0.55 over the mass plus the wheels'
and engine's inertia, SEGA's shift points and 0.15 s shifts; fitted to the game: ST205 SEGA 1.36 / 3.24 s to 50 / 100 km/h
(measured 1.21 / 3.42), SRC test 4 0.67 / 1.48 / 2.49 / 3.30 s to 50 / 100 / 150 / 180 (measured 0.62 / 1.44 / 2.50 /
3.12). Factors (model): C4 x1.53, Focus x1.59, Impreza x1.56, SX4 x1.50, Evo x1.68, 207 x2.36, ST205 x1.70, Delta x1.41,
Bowler x2.85, Enduro x2.76, Hornet x1.07 (and its top 265 -> 211 km/h, its SR3 file's). Model 0-100 then 3.0-3.35 s
against SEGA's 3.20-3.32. `--pace real` gives the earlier numbers (real Nm x 1.2664).
In game 2026-10-14 (Classic, Mountain R4, full throttle from the start, 0-50 / 0-100 km/h from the first movement; the
installed build had no trim): ST205 SEGA 1.03 / 3.19 s, Realism 0.98 / 3.31 s (1078 Nm read from memory); Bowler SEGA
1.05 / 3.59 s, Realism (x2.85, 1498 Nm) 1.09 / 3.12 s, so the model misjudges SEGA's Bowler (it gives it the ST205's time)
and a measured trim x0.84 (`PACE_TRIM` in realism_map.py, `pace_trim` in the table) brings the Bowler to x2.39 for the next
build; Hornet Realism (x1.07, 948 Nm, 9000 rpm) 1.74 s to 50 km/h: rear-wheel drive, held by wheelspin, which a torque
factor cannot make up (the model assumes 4WD traction; SEGA's file for it is 4WD). Not measured yet: the other eight cars and
the trimmed Bowler.

## 4. Open
The SRC turning in the game (the session above) and the staged model-2 SRC files' install; the AI with the SRC turning;
SR3's own cornering grip and slip curve; the SegaRally force model's behaviour; caching of car / grip files between races;
the force models 0 / 1 / 3 for SR3's longer yaw lag; SR2 driving data (Supermodel with an external reader); per-car
grip for Realism (a free tyre class or a per-car grip field still to be found).
