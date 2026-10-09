# 03 - master_xdata: gameplay root, start grid, sectors, AI map, spline, cameras

Loader: 0x5C5C90. The root object is kept at global `[0x9DB48C]`; 75 code sites read it.
Important: the CENTRE LINE and LAP DISTANCE are not here. They come from the road chunk (04_trackdeform_road.md):
the unit of track position is the slice index, and `[0xA95C98]` = number of slices.

## Root: kind 12, type ecdb142b, 152 bytes
| Off | Type | Meaning | Confidence |
|---|---|---|---|
| 00 | u32 | 0x15 (version) | VERIFIED same in 6 tracks |
| 04 | ptr | written at load: pointer to the master_gfx root (0x5C5CD9) | VERIFIED exe |
| 08 | ref | AI map chunk | VERIFIED (0x415210, 0x5D49F0) |
| 0C | ref | kind 12 type 0b9214e0: `{1, ref, ref, ref}` = up to 3 trackside camera lists | LIKELY (SegaRally_TracksideCamera*.cpp; records hold positions, look directions, FOV-like params) |
| 14 | ref | kind 12 20f93164 "Helicopter" (Tropical, Canyon, Desert), 15c476ae stub (Alpine, Stadium), 0 (Lakeside) | VERIFIED presence, optional |
| 18 | ref | spline chunk "DesignRouteSpline"; 0 in Stadium4. Readers test for NULL (0x5AA156) | VERIFIED |
| 1C | u32 | switch 1..6 at 0x646308 (0 in all tracks?) | UNKNOWN |
| 20 | ptr | tested at 0x5A31D7 | UNKNOWN (0) |
| 24 | u32 | 0xB (0xC Tropical); copied to [0x7AAAA0] and looked up in a list (0x5E5578) | UNKNOWN |
| 28 | ref | Stadium4 only: f746b21b (animation: 217 x {quat, pos}) | UNKNOWN use |
| 2C | i32 | START LINE slice index | VERIFIED exe 0x5AF280 / 0x5C4630 |
| 30 | i32 | direction: +1 = race towards increasing slice index, -1 = decreasing (Desert4, Stadium4) | VERIFIED exe 0x5AF2B9 |
| 34 | 8 x {i32 dist, i32 col} | START GRID. For grid row r (0,2,4; odd car of a pair shares the entry): slice = start - dist (dir>0, wrapped) or (start + dist) mod n (dir<=0); column = A/2 + col (dir>0) or A/2 - col, clamped to [1, A-2], A = quads across that slice | VERIFIED exe 0x5AF280 |
| 74 | u32 | number of sector splits (2). Forced to 2 / 0.333 / 0.666 at load if < 2 (0x5C5CF0) | VERIFIED exe |
| 78, 7C | f32 | split positions as lap fraction (0.333, 0.666); recomputed into slice numbers by 0x5AA130 | VERIFIED exe |
| 80, 84 | f32 | 0, 0 | UNKNOWN |
| 88, 8C | f32 | 1.0, 1.0 | UNKNOWN |
| 90 | f32 | 180 (Lakeside, Stadium), 250 (Tropical, Alpine), 400 (Desert), 800 (Canyon) | UNKNOWN (a distance) |
| 94 | f32 | 0.02 | UNKNOWN |

Grid tables seen: Tropical/Canyon/Alpine `(4,3)(10,-3)(16,3)(22,-3)(28,3)(34,-3)(40,3)(46,-3)` (staggered),
Lakeside `(2,2)(2,-2)(14,2)(14,-2)(26,2)(26,-2)(38,2)(38,-2)` (side by side), Stadium same but first entry `(201,-7)`.
Start slices: Tropical 2824, Canyon 483, Alpine 2788, Lakeside 334, Desert 460, Stadium 0.

Sector splits (0x5AA130): if the spline has markers of type (0,5), each gives a split at `marker.start * nSlices`
(adjusted by start slice and direction); otherwise 4 equal parts are used.

## AI map (root +08) - SegaRally_AIMap.cpp
A sparse graph of 2 m x 2 m cells (centres at odd integer x,z) in a quadtree. Parser/builder `grid.py`
(`build_grid` reproduces all 6 chunks byte for byte).

Header: `u32 1, u32 nCells, f32 cell (2.0), f32 origin offset (0), ptr root node (0x14)`.

Quadtree node, 0x28 bytes: `f32 minx, minz, maxx, maxz; u32 count; ptr cells; ptr child[4]`.
- root box = extent of the cell centres +- 4 m; split point = floor(mid/2)*2+2 on each axis;
  children order (-x,+z), (+x,+z), (+x,-z), (-x,-z); a node is split when it holds more than 50 cells;
  nodes are written depth-first, then the cell arrays leaf by leaf. VERIFIED (byte-identical rebuild).
- lookup: 0x5D49F0 (descend, then linear search with Chebyshev distance <= cell/2), 0x5D4A90 (try the 8 neighbours
  of a known cell first), 0x415210 (snap a point to a cell centre).

Cell, 0x30 bytes:
| Off | Type | Meaning | Confidence |
|---|---|---|---|
| 00 | f32 x, f32 z | centre | VERIFIED |
| 08 | 8 x ptr | neighbours N(+z), NE, E(+x), SE, S, SW, W, NW; 0 = none | VERIFIED |
| 28 | u16 | cell index = position in the file (0x5E7053 uses it as a bit number) | VERIFIED |
| 2A | u16 | 0 | - |
| 2C, 2D, 2E | u8 x 3 | lane masks; which byte is used depends on a mode 0/1/2 of the driver object (0x5E8CFA) | VERIFIED exe |
| 2F | u8 | 0 | - |

Lane masks: bit k (0..7) = AI lane k. An AI car owns a lane number and tests the cells under its wheels for that
bit (0x5E7B4F, 0x5E80A5). The 8 lanes are parallel lines across the central part of the road: on Desert4, at a given
slice, bit 0 sits on the highest-column side and bit 7 on the lowest, mean lateral span 5.7 m (max 16 m);
each lane is about one cell wide. VERIFIED statistically (mean column offset per bit is monotonic).
The map covers only ~40% of the road vertices (the central band). Desert4 has the three bytes equal; Tropical4 and
Lakeside4 have cells with only byte 1 or only bytes 0+2 (alternative lines; in Tropical4 the map even extends
325 m away from the road chunk) - meaning of the three sets UNKNOWN. Stadium4: a single line of cells, all 0xFFFFFF.

Authoring rule used (`aimap_cells`): for every slice, lane k at lateral column `w/2 - k*w/7`, `w = 0.4*A`;
OR bit k into all three bytes of the cell under that point.

## Spline chunk (root +18) - SegaRally_Spline.cpp / SegaRally_PaceNotes.cpp
`u32 1, u32 nSplines (1), u32 nMarkers, ptr splines, ptr markers`
spline record: `ptr name ("DesignRouteSpline"), u32 nPoints, ptr points` ; points = f32 xyz.
- points are 2.0 m apart, closed (last = first); point j lies on the centre of slice 2j+1 (max deviation
  0.5-10 m in SEGA's data, the spline is the designer's line). VERIFIED numerically on 5 tracks.
marker, 0x1C bytes: `u16 a, u16 b, u32 0, u16 1, u16 nProps, f32 start, f32 end, f32 small, ptr props`
props = nProps x `{ptr name, ptr value}`.
- (a,b) = (0,5): sector split AND time-extension checkpoint (exe 0x5AA17D compares exactly these two words). VERIFIED;
  semantics at the end of this file.
- (3,2) with one prop "Direction" = code 1..102: pace note. VERIFIED, full table at the end of this file.
- (0,2) with props "Grip" (int), "Length" (int), "Modifier" (float): surface/grip note. LIKELY.
- start/end are lap fractions 0..1.
Builder: `build_spline` (points + split markers only).

## Camera lists (root +0C)
Each list chunk: `u32 0, u32 count, count x {u32 kind, ptr record}`; records of ~0x228 bytes with repeated
position / direction / distance groups and a property table `{id, count, ptr}`. Not decoded further; borrowed as is.

## Cameras: loader, kinds and what happens with none (sixth package)
VERIFIED by reading the code (addresses in Rally.exe 3.8.4.1); the game was not run.
- 0x5FB250: `cam = [root + 0x0C]`; if 0 the function returns. Otherwise three lists are handed to 0x5FB180:
  `[cam + 8]` -> intro manager (game object + 0x2B74), `[cam + 4]` -> trackside manager (+0x24D8),
  `[cam + 0xC]` -> post-race manager (+0x2D4C). Desert4: 1 intro camera, 26 trackside, 3 post-race.
- 0x5FB180 (one list `{u32 0, u32 count, count x {u32 kind, ptr record}}`): list pointer 0 -> returns, manager untouched;
  first word must be 0; kind 0 -> object of 0x368 bytes (ctor 0x5F9080), kind 1 -> 0x39C (0x5F9F90), kind 2 -> 0x35C
  (0x5F9800), any other kind aborts the list; each object reads its record through its virtual +0x88. After the loop
  the manager's flag +0x1C is set to 1. A list with count 0 ALSO sets the flag (the jump at 0x5FB1AE lands on the
  store), leaving a manager that is "loaded" but empty - do not write empty lists.
- No list (flag still 0): when a manager is first activated, 0x5ECAF0 sees flag 0 and calls the manager's virtual
  +0x10, which BUILDS DEFAULT CAMERAS:
  intro and post-race (0x5FAAA0): four cameras of the 0x35C class;
  trackside (0x5EB5C0 -> 0x5FA220): lap length / 100 cameras, at most 50, spread evenly round the lap (lap length =
  [0xA95C98], the slice count), none if the lap is shorter than 100 m.
  So with root +0x0C = 0 the intro fly-by, the replay/trackside shots and the post-race shots still exist; they are the
  game's generic ones instead of hand-placed ones. Where the default cameras stand was not traced (LIKELY relative to
  the car / route; the intro ones take random parameters from 0x410840).
- The file names `\cameras\%s_camera_intro_data`, `..._postrace_data`, `..._trackside_data` (and `%s-intro.cam`,
  `%s-postrace.cam`, `%s.cam`) belong to a second loader, 0x5FB4B0 (a virtual of the same managers): it looks the
  file up with 0x6530B0 and falls back to a raw .cam file `{u32 0, u32 count, {u32 kind, ...}}`. The shipped game has
  no `cameras` folder; the arcade tracks carry their cameras in master_xdata. Who calls 0x5FB4B0 was not traced
  (camera editor: `frontend/cameraeditor_xml_file.sbf` exists).
- Helicopter (root +0x14): 0x5C5489 tests for 0 (Lakeside4 has 0).
AUTHORED (step22): root +0x0C = 0 and +0x14 = 0, the camera lists, their holder and the helicopter chunks removed
(7 chunks); master_xdata is then 3 chunks: AI map, spline, root. `check_min.py` confirms.

---
# Package nine additions (pace-note codes, checkpoints and time, AI lane sets). Nothing was run in the game.

## Pace-note marker codes: the complete table (VERIFIED by disassembly + data)
- Parser 0x5ACD90 (SegaRally_PaceNotes.cpp): every marker with a = 3 and a property named "Direction" goes to one of three
  lists by b = 1 / 2 / 3 (counts 0x9C498C / 0x9C4994 / 0x9C499C, arrays 0x9C4990 / 0x9C4998 / 0x9C49A0); an entry is
  `{i32 code, i32 slice = start * nSlices}`. All five arcade tracks use b = 2 only, and the race code asks for list 1
  (= b 2) only (0x5AC3D9: eax = 1 before the call to 0x5AA5D0). b = 1 and b = 3 are unused alternatives.
- 0x5AA5D0 (per car, called from the car update at 0x5AC3E5): when the car's slice passes an entry, the code is stored at
  car + 0x1CE0. 0x5A4628 puts it in the HUD queue (max 10) and 0x5AB0A0 prepares the co-driver speech.
- Two tables indexed by the code, used only for 1..102 (`code - 1 <= 0x65`, both readers check it, so a code outside
  the range is ignored, not a crash): `0x70CD28[code]` = speech event number (the SP_ ids of Audio/SFX_HashCode.h; file
  offset 0x30CD2C for code 1), `0x70CB88[code]` = HUD arrow icon 0..16.
- code = 17 x variant + type. Variant 0 plain, 1 LONG, 2 VERYLONG, 3 ...MAYBE, 4 LONG...MAYBE, 5 VERYLONG...MAYBE.

| type | call (SP_ name of variant 0) | codes for variant 0 / 1 / 2 / 3 / 4 / 5 |
|---|---|---|
| 1 | BRIDGE | 1 / 18 / 35 / 52 / 69 / 86 |
| 2 | CAUTION | 2 / 19 / 36 / 53 / 70 / 87 |
| 3 | EASYLEFT | 3 / 20 / 37 / 54 / 71 / 88 |
| 4 | EASYLEFTEASYRIGHT | 4 / 21 / 38 / 55 / 72 / 89 |
| 5 | EASYRIGHT | 5 / 22 / 39 / 56 / 73 / 90 |
| 6 | EASYRIGHTEASYLEFT | 6 / 23 / 40 / 57 / 74 / 91 |
| 7 | HAIRPINLEFT | 7 / 24 / 41 / 58 / 75 / 92 |
| 8 | HAIRPINRIGHT | 8 / 25 / 42 / 59 / 76 / 93 |
| 9 | MEDIUMLEFT | 9 / 26 / 43 / 60 / 77 / 94 |
| 10 | MEDIUMLEFTMEDIUMRIGHT | 10 / 27 / 44 / 61 / 78 / 95 |
| 11 | MEDIUMRIGHT | 11 / 28 / 45 / 62 / 79 / 96 |
| 12 | MEDIUMRIGHTMEDIUMLEFT | 12 / 29 / 46 / 63 / 80 / 97 |
| 13 | 90LEFT | 13 / 30 / 47 / 64 / 81 / 98 |
| 14 | 90RIGHT | 14 / 31 / 48 / 65 / 82 / 99 |
| 15 | OVERJUMP | 15 / 32 / 49 / 66 / 83 / 100 |
| 16 | ROADNARROWS | 16 / 33 / 50 / 67 / 84 / 101 |
| 17 | WATER | 17 / 34 / 51 / 68 / 85 / 102 |

  Speech ids of variant 0: 49 SP_ENG_BRIDGE, 50 SP_CAUTION, 51 SP_EASYLEFT, 53 SP_EASYLEFTEASYRIGHT, 52 SP_EASYRIGHT,
  54 SP_EASYRIGHTEASYLEFT, 57 SP_HAIRPINLEFT, 58 SP_HAIRPINRIGHT, 63 SP_MEDIUMLEFT, 65, 64 SP_MEDIUMRIGHT, 66, 59 SP_90LEFT,
  60 SP_90RIGHT, 69 SP_OVERJUMP, 466 SP_ROADNARROWS, 73 SP_WATER (variants 1..5: SP_LONGWATERSPLASH 448, 539, 544, 449, 540).
  `pacenotes.code_name(code)` names any of them. The SEGA Rally 2 import session found the same table independently
  (its `pacemap.py`); the reading code above is what makes "Direction indexes this table" VERIFIED.
- Left / right: checked on the arcade data (Tropical, Canyon, Alpine, Lakeside; heading change over the 150 m after the
  marker in driving direction): 16 of 19 left-coded markers (3, 7, 9, 13, 26, 71) turn with d(atan2(dz, dx)) > 0 and 21 of 21
  right-coded ones (5, 8, 11, 14, 22, 28, 39, 79) with < 0; the three exceptions are notes placed before a short opposite
  kink. So + = left in SR3 world coordinates, as the importer assumed.
- CORRECTION of packages seven / eight: 4 and 6 are NOT "tighter left / right" but EASY LEFT-EASY RIGHT / EASY RIGHT-EASY
  LEFT, 9 is MEDIUM LEFT (not hairpin), 14 is 90 RIGHT (not hairpin). Hairpins are 7 / 8, mediums 9 / 11.
- Other marker types seen: (0,4) x 10 per track with no property and (0,2) Grip / Length / Modifier - still not traced.

## Checkpoints, time limit and time extension (VERIFIED code path; values = data)
- The (0,5) markers are the CHECKPOINTS: 0x5AA130 turns each into a slice number relative to the start line (reversed for
  direction < 0), sorts them (qsort, compare 0x5A9A00) and keeps them in the struct at 0x9DD60C (+4 + 4k slices, +0x1C
  count). There is room for 6 and no bound check: a 7th marker would overwrite the count. Without markers: 4 equal parts.
  The same function then writes every checkpoint slice as a float to master_xdata root +0x78 + 4k: with more than 2
  markers this runs over root +0x80.. (Canyon and Alpine, 3 markers, overwrite +0x80), with 5 or 6 over +0x88 / +0x8C
  (1.0, 1.0, meaning unknown). SEGA never has more than 3. The classic steps of package eight had 4..6 markers.
- CSR_Checkpoint::Update 0x5AC600: when the player's slice passes checkpoint k (0-based index at [0x9EB388]) the time
  limit grows: `[0x9DB4C8] (u64 ms) += 0x5ABD40(.., k + 1)`, then the next index is (k + 1) mod count. At the start of a
  race (0x5ADDE9 / 0x5ADE2A, edi = 1) the limit is set (or, inside a multi-stage game, increased) with value number 1 and
  the next checkpoint is index 1: checkpoint 0 counts as passed. In SEGA's five tracks the first marker lies 0.8 .. 3 %
  of a lap after the start line (the start / finish gate), the others in mid lap (Tropical 0.535; Canyon 0.427, 0.752;
  Alpine 0.322, 0.657; Lakeside none; Desert 0.38).
- The HUD countdown (0x5A6C90) shows `[0x9DB4C8] - elapsed ms (car + 0x1DA0)`; "Time Over? ..." is its debug string.
  0x5A61D0 plays SFX_CheckpointSFX and, when more than 0.05 s was granted (state + 0x14), SP_TimeExtended; else SP_Checkpoint.
- The seconds come from the ARCADE DATABASE, not from the track: 0x5ABD40 -> 0x661AA0(table = [[0xB2A850] + 0xC], track
  id, mode, checkpoint number 1..6; edx = difficulty block, eax = laps setting, edi = lap), result x 1000.
  File `GAME/.../Rally/ArcadeDatabase/arcadedatabase_xdata.sbf`, chunk e9e6b4fb, 19012 bytes: `u32 2`, then
  `[track 0..5][mode 0..2][laps setting 0..2]` blocks of 0x160 bytes = 3 x {u32 nLaps, 4 x {u32 lap number, u32 seconds[6]}}
  (the three = difficulty, LIKELY) + one u32. track = position in the track list (Tropical, Canyon, Alpine, Lakeside,
  Desert, Stadium); laps setting index = setting - 2 (records for 2, 3, 4 laps); mode 1 / 2 are other game modes.
  Desert4, mode 0: lap 1 = 50 + 21 s (21 / 18 / 13 by difficulty), every later lap 18 + 31 s. The number of non-zero
  values equals the number of markers of the track (Tropical 2, Canyon 3, Alpine 3, Lakeside 1, Desert 2).
  `python work/scripts/arcade_times.py dump` prints everything.
- Consequence for a track in the Desert4 slot: only checkpoints 1 and 2 grant time. A third marker grants 0 s.
  The importer therefore writes TWO markers by default (gate + one 1995 time checkpoint); see 14_importer.md.

## AI map: what the three lane-mask bytes are (VERIFIED code, meaning of the selector LIKELY)
0x5E8CFA picks cell +0x2C, +0x2D or +0x2E by `[driver + 0x5C]` = 0 / 1 / 2 (anything else: +0x2D). The AI driver init
0x5E9470 copies that value from `[[car + 0x300] + 0x28]`, a field of the car's own record (car = 0x9DBAC8 + i x 0x1F18).
So the three bytes are three alternative lane systems chosen per CAR (class / type), not "racing line, overtaking, ..."
Desert4 has the three equal; an authored map should write the same lanes into all three (what `aimap_cells` does).
There is no speed or braking field in a cell; where the AI takes its target speed from was not traced.

---
# Additions after the tracks were driven in game (2026-10-06 .. 08)

## What was proven in game
- An authored AI map (the 8-lane rule) and an authored spline load and race: both are on the owner's list of things
  proven in game on the test ladder. VERIFIED in game. How well the AI drives on an authored map was not judged.
- Checkpoints: on imported Mountain the (0,5) markers placed at the 1995 time-checkpoint sections 63 / 126 / 198 fire
  when the car passes the gantry there (owner confirmed that they fire; the seconds come from the track's own time
  block, next section). VERIFIED in game for the firing.
- Default cameras: with root +0x0C = 0 the game builds its own intro, trackside and post-race cameras, as the code
  reading predicted (the imported Mountain runs with course setting `cameras: default`). Complaints from the first runs
  that concern them: "game-over camera in the wrong place" and "no ground in the pre-countdown intro" (the 1995 data has
  no ground where the default cameras look; 22_gapfill_zfighting_scenery_rules.md). VERIFIED in game.

## Checkpoint seconds per track without touching the database file
The loaded ArcadeDatabase holds one block of 0xC60 bytes per track at `[[0xB2A850] + 0xC] + 4 + 0xC60 x track` (reader
0x661AA0, called at 0x5ABDF8 whenever a marker is crossed). The launcher writes a track's own `arcade_times.bin` into
that block while the track is chosen (20_launcher_inmemory_patches.md, section 6). With it the importer's course setting
`checkpoints: classic` can write the gate marker plus EVERY 1995 time checkpoint instead of two markers. The seconds
`arcade_times.py classic` writes for a classic course are a GUESS (1995 practice mode, its shortest lap setting, frames /
60; at the line on later laps the largest 1995 extension).
Importer modes: `slot` = gate + ONE 1995 time checkpoint (the Desert4 slot has two values per lap); `classic` = gate +
every 1995 time checkpoint (needs the matching time block); `splits` = the 1995 split-time sections (package seven).
Lap fractions of the spline start at slice 1, like the slices (import_classic.py).

## AI lanes along a source game's line
`import_classic.classic_ai_cells` lays the 8 lanes along the 1995 AI line (gameplay.json `ai_line`, 300 points;
18_src_1995_rom_data.md) instead of the road centre, writing the same lanes into all three mask bytes as Desert4 does.
The 1995 speed-zone byte has no counterpart in the AI map and is not written. The selector field is read at exe 0x5E949A
/ 0x5E8CFA. In-game quality of the result: not reported (UNKNOWN).

## Pace-note code as a formula
The SEGA Rally 2 import session wrote the same table as: code = 1 + call + 17 x length + 51 x maybe, with the speech table at
file offset 0x30CD2C of Rally.exe (the owner's notes quote the formula; the ranges of call, length and maybe are not
spelled out there). It is consistent with "code = 17 x variant + type" above. VERIFIED (two independent derivations).
`pacenotes.code_for_name` maps a 1995 sound-test name to a code: K (the 1995 call between Mid and Hairpin) becomes 90 LEFT
/ 90 RIGHT (GUESS); a leading C / Caution only sets a flag, because SR3 has no combined call.
