# 19 - SEGA Rally 2 (1998, Model 3 Step 2.0, `srally2`): courses, gameplay data, import into SR3

ROM regions, the polygon format and the audio extraction are in [classic-sources.md](classic-sources.md); how the co-driver
clips and music are used in SR3 is in [audio.md](audio.md). This file records the gameplay decode
(`classic/sr2_gameplay/gameplay.md`) and the SR2 -> SR3 import (`classic/sr2_sr3_import/README.md`).

Everything in sections 1-9 comes from static analysis of the ROM (no emulator run). Tags there: VERIFIED = read from ROM
and confirmed by the code that uses it or by geometry; LIKELY; GUESS. Nothing of the SR2 import (section 10) has been run
in SR3: the SR2 courses were built before the in-game fixes of 2026-10-07 and have not been rebuilt with them.

Addresses: plain hex = fixed CROM file offset = RAM address (the program runs from RAM at 0; code 0..0x8D000, data after).
`0xFFxxxxxx` = banked CROM address; file offset in `banked_crom.bin` = bank x 0x800000 + (address & 0x7FFFFF) (the bank
register code at 0x74EC8 writes bank ^ 0xFF to 0xFE100008). The game does not use r2 / r13 small-data addressing: every
global is a lis / addi pair (VERIFIED: 0 uses of r13).

## 1. Course identity

Three numbers exist. VERIFIED (code).
| Number | Where | Meaning |
|---|---|---|
| STAGE 0..7 | RAM 0x22CF44 | index of the stage table 0xE8408 (96 bytes per stage) and of every gameplay table below |
| COURSE ID | RAM 0x2259F8 = stage record word +4 | selects the geometry: scenery descriptors 0xCF168 + 12 x id, road descriptors 0xDE1E0 + 12 x id (code 0x14AF4, 0x14D5C) |
| ROUND 0..19 | RAM 0x22CF48 | table 0xE8714, 124 bytes; word 0 = stage (code 0x2BB08) |

- Debug stage names (table 0xF27B8, indexed by stage in code 0x4C484): 0 DESERT_OLD, 1 FOREST, 2 MOUNTAIN, 3 DESERT,
  4 RIVIERA, 5 SWEDISH, 6-7 INVALID.
- Stages 0..7 -> course ids 4, 2, 3, 4, 5, 6, 5, 5. The COURSE TABLE INDEX (the export number of this project) = id - 2.

| Export index | Course id | Course | Stage |
|---|---|---|---|
| 0 | 2 | FOREST (unused in the arcade release) | 1 |
| 1 | 3 | MOUNTAIN | 2 |
| 2 | 4 | DESERT (stage 0 "DESERT_OLD" = same geometry and collision, other checkpoints) | 3 |
| 3 | 5 | RIVIERA (stages 6, 7 are variants) | 4 |
| 4 | 6 | SNOWY, internal name SWEDISH | 5 |

- Course select menu: cursor (RAM 0x224328) -> table 0xF1F20 = stages {3, 2, 4, 5} = Desert, Mountain, Riviera, Snowy (code
  0x46AEC, 0x48474); the round is that stage + 6. Championship: round sequence 0xED740 = {3, 2, 5, 4} = Desert, Mountain,
  Snowy, Riviera (code 0x2C8A4, 0x2BBC4).
- FOREST is a complete course (geometry, collision, checkpoints, time table) that no menu entry or championship round
  reaches; its pace-note table is empty and its rival line is a byte-identical copy of Mountain's. LIKELY a leftover,
  reachable only through the debug stage select.
- Stage record (0xE8408 + 96 x stage): +0 stage id, +4 course id, +8 model-table index of the sky dome, +12 / +16
  model-table indices of the start / goal banners (the decode note's own summary line calls +8 "an extra model" and
  +12 / +16 "the backdrop"; its Sky section, which names the models and the code, is followed here), +20 s32, +24 light direction (3 floats), +64 fog / clear colour RGB, +72
  float (700 / 1500 / 800 / 200), +80 bank (byte 83), +84 pointer to the section header, +88 pointer to the section edge
  lines, +92 pointer to the pace-note table.

## 2. Sections, ground and surface lookup

Stage +84 -> banked header `{u32 count = 256, pointer A, pointer B}`: Desert 0xFF52EDEC (bank 2), Forest 0xFF350794 (bank
1), Mountain 0xFF2EE070 (bank 2), Riviera 0xFF1274EC (bank 3; stage 6 uses 0xFF1860F0, a 336-polygon variant), Snowy
0xFF5FAD1C (bank 3). VERIFIED.
- A: 256 x 44 bytes: the quad of the section as 5 (x, z) points (entry-left, exit-left, exit-right, entry-right, first
  again) + a pointer to a -1-terminated list of polygon numbers (the list also holds the neighbours' polygons).
- B: polygon array, 304 bytes each: +0 centre xyz, +12 radius squared, +16 three vertices xyz (+52 first again), +64 four
  normals, +112.. curved-surface terms, +280 / +284 / +288 neighbour polygon per edge (-1 none), +296 attribute.
- Stage +88: 256 x 3 lines (a, b, c): exit edge, left edge, right edge of each section.
- Section i = road block i: the block position equals the quad centre for all 256 blocks of all five courses.
- Lookup code: 0xC014(result, pos, flag, header): 0xAB74 finds the section (starting from the last one), then the polygon
  list is scanned (bounding circle, then 2D edge tests); 0xB0F4 gives height + normal; result +16 = attribute, +20 =
  section. The player's section is car +72 (car pointer RAM 0x2242B0), copied to RAM 0x22CFB8.
- Attribute word: bits 16+ = polygon number, bit 15 = wall / blocked zone (edge response in 0xBDA4), low 4 bits = SURFACE
  TYPE 0..13.

### Surface types
Names = the ROAD STATUS tuning menu built at 0x5A3A4 (GRIP) and 0x5A67C (DECAY), which edits an 8-byte-per-type array (car
spec +316) in this order: 0 TARMAC, 1 TARMAC2, 2 GRAVEL, 3 GRAVEL2, 4 WATER, 5 WATER2, 6 DIRT, 7 DIRT2, 8 TUNNEL, 9 TUNNEL2,
10 SNOW, 11 SNOW2, 12 WET, 13 WET2. Names and order VERIFIED; that the polygon nibble indexes this array is LIKELY (value
range 0..13 fits, and the pace notes agree: "in tarmac" / "in gravel" calls land on the TARMAC / GRAVEL boundaries of
Mountain and Desert; the indexing instruction itself was not located).
- Second evidence: table 0xF4D30 (indexed by the car's surface, code 0x59A44) = {1,1, 0xE,0xE, 0,0, 6,6, 1,1,
  0x10,0x10,0x10,0x10}: bit 0 enables the tyre-squeal channel (SV_SLIP, code 0x59880) = tarmac and tunnel only.
- Types used: Forest TARMAC, GRAVEL; Mountain TARMAC, TARMAC2, GRAVEL, GRAVEL2; Desert GRAVEL, DIRT, TARMAC (start
  straight), WATER (three splashes); Riviera TARMAC only; Snowy SNOW, SNOW2, WET, WET2. The "2" types are the strips beside
  the main line.
- The grip / decay numbers live in the car spec records and were not exported (UNKNOWN values).
- Not the surface: `SetCarMaterialEffect` (0x1CAA8) uses a per-section zone table (0x12D8C8 + 640 x (id - 1), 20-byte
  entries {last section + 1, 2 texture codes, 2 floats}) = car body / window reflection maps (LIKELY).

## 3. Start, laps, direction (VERIFIED)
- Player start: round record (0xE8714 + 124 x round; rounds 0-5 = stages 0-5, practice round = stage + 6) +12 = position,
  s16 heading at +24, s32 at +28 (code 0x31F80 copies them into the car). Desert, Mountain, Snowy, Forest: (0, 1.0, 0),
  heading 0 = game +Z: the world origin, dropped from 1 m. Riviera: (-276.245, 5.0, 190.848), heading 0xC000 = game +X,
  +28 = 181: it starts in section 180 / 181 (ground y = 4.0), 75 sections before the lap line.
- Linked cabinets use slots +32.. (side by side: -2, +2, -6, +6 m; practice rounds -1.5, +1.5, -5, +5), slot = link id
  (code 0x31FEC).
- Direction = increasing section number. Lap line = entry edge of section 0 (game z = 8.33 Desert, 3.33 Mountain, -1.42
  Forest, -0.57 Riviera, 0 Snowy).
- Laps: table 0xE8388[game type][stage] (code 0x404C4): type 0 = 1 lap (Riviera 2), types 1 and 2 = 3 (Riviera 5), type
  3 = 10. Game type (RAM 0x22CF14): 0 / 1 = championship (4 rounds), 2 / 3 = practice; the odd ones are picked by an
  operator setting bit (code 0x2C854, 0x2C978).
- Lap lengths through the section centres: Forest 4253 m, Mountain 3490, Desert 3576, Riviera 1905, Snowy 3180. Riviera's
  figure is overestimated by the wide paddock sections; the rival line gives about 1660 m.

## 4. Checkpoints, split points and time (VERIFIED)
- Checkpoints: 0xE5828 + 20 x stage = {count, sections}. Stage 0: 95, 256; 1 Forest: 43, 141, 256; 2 Mountain: 121, 256;
  3 Desert: 109, 256; 4 Riviera: 256; 5 Snowy: 127, 256; 6, 7: 85, 170, 256. 256 = the lap line. Code 0x3E130 (on reaching
  one): SE_CHECK1 + VO_CHECKPOINT, then adds the next time-table entry to the pending time.
- Split points: 0xE5708 + 36 x stage = {count, 8 sections} (32, 64, ... with small shifts); code 0x3DFDC stores the sector
  time and the difference to the record; no time is added.
- Time: table 0xE8348[game type] = {5, 8, K, pointer}; entry = pointer[((difficulty x 8 + stage) x K + n)] (code 0x404BC).
  K = 4 / 12 / 12 / 40, pointers 0xE58C8, 0xE5B48, 0xE62C8, 0xE6A48. n = 0 is given at the stage start, n = k at the k-th
  checkpoint passage, -1 = none. Units = frames, 60 per second (the remaining time drops 1 per frame; code 0x3EE6C).
- Difficulty = 3 bits of the settings word (RAM 0x22CF18, values 0..4); which value is the factory default was not traced.
- Championship, difficulty index 0: Desert 50 s + 30 s; Mountain +30 s at start, +27 s; Snowy +30, +26; Riviera +38, +34
  (lap 1 line). All values: `classic/sr2_gameplay/course<N>/gameplay.json` (`checkpoints.times_s`, `times_raw`).
- Names in the unused debug overlay strings at 0xF1738: AREA, POINT, LAP, NEXT CP, NEXT GP, NEXT SP, NEXT LP, NEXT NV.

## 5. Pace notes (VERIFIED)
- Stage +92 -> table of 24-byte records, ended by section -1: Mountain 0xE50A8 (21 notes + 2 events), Desert 0xE52E8
  (10 + 1), Riviera 0xE5408 (9 + 2), Snowy 0xE5528 (15 + 3), Forest 0xE5090 (empty). Record: s32 section, s32 condition,
  s32 distance-call index, s32 icon 1, s32 icon 2, s32 VO request.
- Code 0x3E5C8 (init: skip notes behind the car) and 0x3E68C (per frame): when the player's section equals the next note's
  section, play table 0xF160C[distance index].request (VO_30, 50, 70, 100, 150, 200, 300 ... 900), wait
  0xF160C[..].delay frames (27..46), then play the VO request; icon 1 is shown 45 frames, then icon 2 for 90.
- Request numbers index the name table 0xE3168 / the 3-byte code table 0xE2C4C (sound call 0x1788).
- Condition: -1 always; 1 first lap only; 2 every lap except the last; 3 praise point (VO_EXCELLENT / OUTSTANDING / YOUARE /
  GRATE by a score in RAM 0x22D610 + crowd cheer); 4 crowd cheer; 5 last lap: goal cheer (0xF16D4).
- Check: in the plots every call sits before a bend of the called hand; Mountain "in gravel" / "in tarmac" land on the
  GRAVEL / TARMAC changes; Desert "... water" calls come before WATER polygons. All notes: `classic/sr2_gameplay/sr2_pace_notes.csv`.
- Icon numbers seen (from co-occurrence with the requests; graphics not extracted): 0 narrow bridge, 3 crest jump, 5 easy
  left, 6 easy right + left, 7 easy right, 9 hairpin right, 10 water, 14 K right, 19 long easy left, 20 long easy right,
  21 long K left, 23 long medium left, 24 long medium right, 25 medium left + right, 26 medium left, 27 medium right + left,
  28 medium right, 30 open hairpin left.
- The SR2 import session derived SR3's pace-note code independently (its `pacemap.py`): code = 1 + call + 17 x length +
  51 x maybe, table in Rally.exe at file offset 0x30CD2C. It agrees with the table of 03_master_xdata_route.md.

## 6. The lines at 0xE2C0C are a designers' centre line, not AI (VERIFIED use)
Table base 0xE2BFC + 8 x course id = {count - 1, pointer}. The only code reference is 0x5D358, in the creation of the
built-in course-object editor's "car" (task 0x5CD00, debug strings "CAR : %+6.1f...", "{CO_%-24s, %3d, {..."), whose
auto-run (0x5C538) follows the line. The race code never reads it. This answers "purpose unknown (AI line or map)" in
classic-sources.md.

## 7. Rival (computer car) line (VERIFIED table, behaviour not traced)
- Pointer table 0x1353DC[stage] (banked, same bank as the stage): 0xFF139A10 Forest, 0xFF0D37F0 Mountain, 0xFF0D5730
  Desert, 0xFF70770C Riviera, 0xFF70964C Snowy; node count 0xEE100[stage] = 342, 342, 353, 165, 314.
- Node = 4 floats: x, y, z, heading (radians, 0 = +Z, -pi/2 = +X). Nodes about 10 m apart, starting 10 m ahead of the
  start position, y about 0.5-0.65 above the road. LIKELY a recorded drive (it cuts corners like a racing line).
- Used by the other-car code 0x325AC / 0x3298C. Per car: 0xEE140 + 256 x stage + 16 x car = {float speed value (211, 210,
  200 ...), float, float, s32 start node (e.g. 42 = 420 m ahead)}. Cars in a round: round record +112 (LIKELY).

## 8. Sky and banners (VERIFIED)
- Stage record +8 = model-table index (table 0xA4BA8, 16 bytes per entry, word 0 = VROM address) of the SKY DOME: Forest
  10 (0x3C4935), Mountain 2467 (0x61E05C), Desert 2442 (0x61B81F), Riviera 2443 (0x61BDDF), Snowy 2468 (0x61E78F). Code
  0x14FA8 hangs it as the last node of the course scene. Domes are 5 to 7 km across, 64-128 polygons. Whether the dome
  follows the camera was not traced (LIKELY).
- Stage +12 / +16 = start banner / goal banner models (2-30 polygons, 14-24 m wide; Riviera's sits at the Riviera start
  position). +16 is swapped in by code 0x3E3B4 when the last checkpoint is next (LIKELY "goal").
- Textures: every rectangle the sky and banner models use lies inside the texture set already matched to the course
  (coverage 100 % for all five).

## 9. Block records and what was not found
- Correction to classic-sources.md: in the 48-byte block record (x, y, z, u32, then 4 x {model address, value}) the value
  after LOD0 is not a count. Code 0x14E30 turns it (x 1.2 for scenery, low 16 bits for road) into culling-node word +70
  (LIKELY a culling / LOD distance). No rotation is applied.
- Roadside object placement: the editor record format is known from its print strings ("{CO_name, area, {x, y, z}, 0x%04x
  ry, para, 0}", 20-byte records: u16 kind, s16 area, 3 floats, u16 ry, s16 para; code 0x5BB88) but the per-course tables
  were not located (UNKNOWN).
- Not done: grip / decay numbers per surface; the meaning of game types 1 and 3 beyond their lap counts; rival behaviour
  (speed profile, how the two floats per car are used); pace-note icon graphics.

## 10. SR2 courses as SR3 tracks (`classic/sr2_sr3_import/`)
Built statically on a copy of the Championship importer plus `sr2_prep.py`, `import_sr2.py <k>`, `check_sr2.py`. NOTHING
here has been run in the game.

| | Desert | Mountain | Snowy | Riviera |
|---|---|---|---|---|
| Final step folder | step43_sr2_desert_classic_desert4 | step47_sr2_mountain_classic_desert4 | step51_sr2_snowy_classic_desert4 | step55_sr2_riviera_classic_desert4 |
| slices (= lap, m) | 3561 | 3500 | 3167 | 1699 |
| SR3 road width (constant) | 16 m | 14 m | 10 m | 12 m |
| SR2 drivable area inside it | 66 % | 75 % | 70 % | 86 % |
| elevation range | -17..2 m | -8..18 m | -1..46 m | 0..4 m |
| tightest centre-line radius | 68 m | 13.7 m | 11.7 m | 9.6 m |
| start slice | 3554 | 3493 | 3162 | 1202 |
| splits (SR2 sections) | 109 (checkpoint), 175 | 121 (checkpoint), 192 | 127 (checkpoint), 192 | 128 |
| pace notes written / in SR2 | 8 / 10 | 17 / 21 | 14 / 15 | 9 / 9 |
| scenery meshes / vertices | 31 / 109,552 | 37 / 102,220 | 41 / 184,464 | 48 / 89,536 |

- Height of the built road against the SR2 collision under it: median 3 cm (the importer's lift), 95 % within 4 cm (Snowy
  12 cm). Surface of the built cell against the polygon under its middle: same on 94.5 % (Desert), 96.6 %, 96.6 %, 100 %.
  VERIFIED (measurement on the built files).
- Surface mapping (SR2 type -> SR3 layer pair, 10_surfaces.md): TARMAC, TARMAC2 -> Terrain_Safari_Tarmac (e56e4a5c +
  0558e395); GRAVEL, GRAVEL2 -> Terrain_Safari_Gravel (9cbfa41a + 6ec69183); DIRT -> Desert4's dry-mud pair (5b5f7bf7 +
  5196e5b9); WATER -> base 5b5f7bf7 + top 52f4c707 (Terrain_DampMud_Top: SR3's lists have no water surface); SNOW, SNOW2 ->
  Terrain_20mmSnow (51c4595d + c05d56a7); WET -> Terrain_WetTarmac (791862c4 + cc2bb0dc); WET2 -> Terrain_Super_Slush
  (791862c4 + 53cb9b5e).
- Start: SR3 start line = the SR2 lap line; the first grid row stands at the SR2 start position, rows of two at +-2 m, 12 m
  apart; direction +1. Riviera starts 497 m before its lap line in SR2; SR3 has one line, so it was put 3 slices ahead of
  the start position.
- Pace notes: every SR2 call that names a turn becomes an SR3 (3,2) marker with the early code families (left 3 / 4 / 9,
  right 5 / 6 / 14 for easy / medium or K / hairpin). The meaning of those codes was later CORRECTED in
  03_master_xdata_route.md (4 / 6 are the easy-left-easy-right combinations, 9 is medium left, 14 is 90 right); the SR2
  builds were made before that correction and have not been rebuilt.
- Differences from the Championship importer: `road_model_n` writes up to 7 layer ids in the one uniform batch record;
  missing layer textures are copied from Alpine4; scenery tiles are RGB PNG; repeating faces are cut to stay within the
  uv range (13 / 1 / 73 faces of Mountain / Snowy / Riviera still clamped); the course is re-centred on road + scenery and
  14 Desert faces beyond +-745 m are left out.
- The SR2 session also derived SEGA's variable-width record rules (its `varwidth.py`, all 16,818 slices of the six arcade
  tracks; 04_trackdeform_road.md).
- Not carried into SR3: time extension at the checkpoint, crowd / praise points, distance calls and hazard calls, the
  rival line, car reflection zones, SR2's lighting and fog, the 5-7 km sky dome (Riviera's night look is lost), painted
  lane markings.
- Risks named by the builder: a batch record with 5 or 7 layers (Snowy, Desert) and the damp-mud top over a dry-mud base
  (not a pair SEGA uses); the largest mesh has 40,000 vertices (Snowy; limit 65,535).
- These builds predate the in-game findings of 2026-10-07 (an imported track needs its pobj files and grass cache, mesh
  uv are signed, overlay pages must be local, chunks may not reference later chunks: 21, 07, 04, 01). The owner's notes
  say the SR2 imports "have NOT been rebuilt with these fixes"; the "final" steps hold 3 files, the form that the
  Championship work found unusable in game.
