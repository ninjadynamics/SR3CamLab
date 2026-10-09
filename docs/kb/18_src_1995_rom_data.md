# 18 - SEGA Rally Championship (1995, Model 2A): gameplay tables, placed objects, how the course data is built

This file collects what is known about the 1995 game's own data beyond geometry and textures. ROM regions, the object
table and the polygon format are in [classic-sources.md](classic-sources.md); texels and colour are in
[12_classic_textures.md](12_classic_textures.md); the crowd table is in [15_spectators.md](15_spectators.md).

Sources of the statements below: the decode notes `classic/courses/src/gameplay.md` and `classic/sr2_gameplay/gameplay.md`
(section "SEGA Rally Championship leftovers"), and the docstrings of the importer scripts named in each section.
Tags: VERIFIED (how), LIKELY, GUESS, UNKNOWN. "In game" = the owner drove the result on the SR3 cabinet; "Model 2" = the
owner compared with the 1995 game running in the Model 2 emulator.

Address conventions: "prog" = file offset in the program ROM image `maincpu.bin`; the RAM copy of initialised data is at
offset + 0x59F000 (VERIFIED by executing the boot code, 12_classic_textures.md). "main" = offset in the main data ROM
(mapped at 0x02000000).

## 1. Course numbering

| Game course id (RAM 0x214354) | Course | Export number used by this project | Object table rows (hi detail) |
|---|---|---|---|
| 0 | Desert | 2 | 937..996 |
| 1 | Forest | 4 | 1135..1194 |
| 2 | Mountain | 1 | 1259..1318 |
| 3 | Lake Side | 3 | 1379..1438 |

- The course id has 179 code references; ids 4-7 repeat defaults. VERIFIED (table prog 0x3DAC8 maps id -> section table
  0x02003E00, 0x0200BA00, 0x02000000, 0x02007C00, and the four pace-note tables only fit the geometry in that order).
- The export numbers are the order of the collision blocks in the coprocessor data ROM. VERIFIED (same source).
- This settles the "names unconfirmed / LIKELY" notes of classic-sources.md and 12_classic_textures.md.

## 2. Section tables (the game's unit of progress)

main 0x0000 (Mountain), 0x3E00 (Desert), 0x7C00 (Lake Side), 0xBA00 (Forest): header `{300, ptr A, ptr B, ptr C}`.
| Table | Record | Content |
|---|---|---|
| A | 300 x 24 bytes | two boundary points (x, 0, z) = a gate across the course; 48 / 80 / 65 / 56 m wide |
| B | 300 x 12 bytes | `{4 | object index 0..59 in the low 16 bits, point indices}` = the quad between two gates |
| C | 300 x 8 bytes | (cos, sin) = heading of the section as (dx, dz) |

- Each is followed by the same structure with 60 entries (one per scenery object = 5 sections) at 0x33A0, 0x71A0, 0xAFA0,
  0xEDA0, and a 10-section set at 0xF800 (a non-race scene). VERIFIED layout; purpose LIKELY (a 2D "which section is the
  car in" map; 5 sections = one scenery object, used for culling).
- Sections are numbered in driving direction; section 0 is at the start line. Every table below is keyed by section number.
- Lake Side's gates are stored in a different order from the others (the gate mid points do not follow the headings); use
  the AI line for distances there. VERIFIED (data).

## 3. AI / ideal line and speed zones

Table prog 0x3DE70, 16 bytes per course id: `{300, 11 or 12, float 150 / 120 / 130 / 150, pointer}`. The pointers
(main 0x8012F0 Desert, 0x804BC0 Forest, 0x8025E0 Mountain, 0x8038D0 Lake Side) lead to 300 x 16 bytes:
`{x, y, z of the line through the section (with height), byte flag, 3 zero bytes}`. VERIFIED layout.
- Flag high nibble 0..5 (7 once): rises to 5 some sections before a corner and steps down 5, 4, 3, 2, 1, 0 through it.
  The pattern is VERIFIED; that it is a braking / target-speed zone for the computer cars is a GUESS.
- Flag low bits: code at prog 0x2BD80 uses (flag & 7) to pick a float from prog 0x2BBC0 `{4,3,3,3,4,4,4,4}` into RAM
  0x20CAE0. Lake Side is 1 everywhere, the others 0 except Mountain sections 110-118. Meaning UNKNOWN.
- In the exports: `gameplay.json` key `ai_line` (300 points, distance along it, speed_zone, variant).
- Use in SR3: `import_classic.classic_ai_cells` lays the eight SR3 AI lanes along this line instead of the road centre.
  The speed-zone byte has no counterpart in SR3's AI map and is not written (03_master_xdata_route.md).

## 4. Start grid

- prog 0x3DB20: per course id 4 positions (x, y, z) as f32, 48 bytes per id; ids 4-6 hold other scenes. The course
  settings file records Mountain's record as offset `0x3db80` (the third record). VERIFIED data.
- prog 0x3DC70: per course id a rotation (rx, ry, rz) in radians: Desert 0, Forest 0, Mountain ry = -1.57, Lake Side
  (0.03, -0.09, 0). ry = -atan2(dx, dz) of the start heading; it matches section 0's heading on all four (Mountain starts
  along +x, the others along +z). VERIFIED (data against geometry).
- Which of the four slots the player takes was not traced (UNKNOWN). Race direction = increasing section number.

## 5. Split points, time checkpoints and time

Two different tables exist; an earlier note confused them.

| Table | Content | Values |
|---|---|---|
| prog 0x1E790 | SPLIT-TIME display points: 8 section numbers per course id (99999 = none) | Desert 68, 135, 218, 270; Forest 93, 158, 158, 206, 256; Mountain 80, 116, 147, 193, 226, 271; Lake Side 77, 137, 194, 264, 287 |
| RAM 0x5E5670 + 32 x course | TIME checkpoints (sections where time is added) | Desert 0, 115; Forest 0, 114, 192; Mountain 0, 63, 126, 198; Lake Side 0 |

- Split points: code prog 0x1EA9C stores the running time ([0x2020B8]) in an array at 0x20AED0, computes a difference and
  starts a 180-frame display timer (0x20AF98). No time is added there. VERIFIED (code path).
- Time: remaining time = RAM 0x20B0B0. Code 0x47330 builds `{section, time}` pairs in RAM 0x20ACA0. Times come from the
  block at [0x5E5CF0 + 4 x course] (championship) or [0x5E6310 + 4 x course] (practice); word index = laps x 16 +
  difficulty x 4 + n (difficulty = setting byte 0x20201C & 3; laps from 0x5E5570 / 0x5E55F0). VERIFIED tables.
- Section 0's time is the INITIAL time (code 0x1CC70 -> 0x1C830 stores entry 0 into 0x20B0B0); each later section adds its
  time with the CheckPoint sound and voice (code 0x1D230, 0x1D4C8); a negative time (-60) ends the list. VERIFIED (code).
- Units: frames, 60 per second. LIKELY.
- Championship, 1 lap, difficulty 0: Desert 60 s, +20 s at section 115; Forest +15 s at its start, +22, +27; Mountain +17,
  +16, +14, +19; Lake Side +70. All values: `classic/sr2_gameplay/src/src_checkpoints_times.json`.
- A second section table, prog 0x46010 (3 sections per course: Desert 75, 124, 155; Forest 35, 122, 194; Mountain 7, 111,
  228; Lake Side 54, 95, 236), is used by code at prog 0x461F4 that looks for the nearest other car on reaching the
  section. GUESS: rival / overtaking events. Exported as `event_sections`.
- Not resolved: the per-course values at prog 0xF460 (2950, 2950, 2950, 2895) and the float 150 / 120 / 130 / 150 in the
  0x3DE70 table (UNKNOWN meaning).

Use in SR3: the importer's course setting `checkpoints` chooses `slot` (gate + one 1995 time checkpoint), `classic` (gate +
every 1995 time checkpoint; needs a matching time table, see 21_track_install_and_switching.md) or `splits` (the split-time
sections). On Mountain, gantries at sections 63 / 126 / 198 fire the SR3 checkpoint in game (VERIFIED in game, owner).

## 6. Pace notes and voice ids

- prog 0x40770: 8 pointers (per course id) to tables at prog 0x40470 (Desert, 11 notes), 0x40500 (Forest, 12), 0x405A0
  (Mountain, 18), 0x40690 (Lake Side, 17). Record = 3 x u32 `{section, voice id, icon id}`; end = section 9999. Code at
  prog 0x40790 loads the table for the course id and the arrow graphics. VERIFIED.
- Assignment check: with the tables given to the courses in that order, every note of Mountain (18/18), Lake Side (17/17)
  and Forest (12/12) is followed by a turn of the same hand as every other note with the same voice id. VERIFIED (geometry).
- The voice id is a SOUND REQUEST number: code 0x40850 calls 0x26140(id), which sends the 3 bytes at RAM 0x5C3CE0 + 3 x id.
  A sound-test NAME table sits beside it (pointers at RAM 0x5C48C0, 189 names): 0 Three, 1 Two, 2 One, 3 Go, 4 CheckPoint,
  5 Finish, 6 Caution, 7 TurnAround, 8 HurryUp, 9 Jump, 10 OverJump, 11-17 Oh / Wow / OhGod, 18 KeepRight, 19 KeepLeft,
  20 EasyRight, 21 EasyLeft ... 58 LongLeft, 59-62 SRC0-3 (title calls), then effects and music. VERIFIED (code + table).
  Every pace note therefore has its original name: `classic/sr2_gameplay/src/src_pace_notes_labelled.csv`.
- Request code `AE 20 nn` = sound-driver group 0x20, track nn (pointer list at 0x30AE of epr-17890, byte-swapped image): a
  MIDI note-on, channel 10, key nn. Key map at 0x8FF6 (8 bytes per key, word 0 = sample slot): key k -> slot 137 + k; slots
  count the 20-byte sample entries from 0x9C26, so key k = sample k + 13 of the fifth sample table. VERIFIED; cross-check:
  12 of the 14 earlier speech-recognition guesses give the same words. 63 speech samples are labelled
  (`src_speech_labels.csv`); all 189 requests are in `src_sound_requests.csv`. This supersedes "21 labelled by offline
  speech recognition" in classic-sources.md.
- Icon ids, derived from the heading change over the 16 sections after each note (geometry, not heard): icon 0 easy left
  (voices 21, 23), 1 easy right (20), 15 medium left (25, 27, 29), 16 medium right (26, 28, 30), 19 left, tighter (36, 38),
  20 right, tighter (35, 37), 21 right (44), 10 hard left (40, 42), 11 hard right (39), 8 hairpin left (46, 50), 9 hairpin
  right (45), 6 long hairpin right (55). LIKELY. Icons 7 (voice 10), 4 (32), 26 (33) come before almost straight road
  (GUESS: crest / caution calls).
- Mapping to SR3 codes (`pacenotes.code_for_name`): the sound-test name gives the call; "K" (the 1995 call between Mid and
  Hairpin) is written as SR3's 90 LEFT / 90 RIGHT (GUESS); a leading C / Caution sets a flag only, because SR3 has no
  combined call. Code table in 03_master_xdata_route.md.

## 7. Surface types (collision attribute bits 16-19)

VERIFIED by the texture under each polygon (`classic/courses/src/surface_types_contact.png`); physics values not traced.
| Code | Surface | Where |
|---|---|---|
| 0 | tarmac | Mountain road with centre dashes, Forest tarmac |
| 1 | tarmac, second kind | Mountain plain asphalt with tyre marks |
| 2 | gravel / light dirt | Desert pale sand, Lake Side, Forest dirt |
| 3 | brown dirt / mud | Desert |
| 4 | water crossing | Desert: 29 polygons at the river, splash sprite |
| 6 | verge beside the road | grass, rough earth; all courses |
| 8 | tarmac under cover | 11 polygons, Mountain |
| 9 | tunnel floor | Forest |
- Bit 23 = side polygon (bank / wall), always type 0. Bits 20-22 are never set. VERIFIED (data).
- UNKNOWN: the grip / drag numbers, the sounds each type triggers, and whether the TGP or the main CPU evaluates them.
- The importer maps 0, 1, 8, 9 to tarmac and 2, 3, 4, 6 to loose (course setting `surface_codes`).

## 8. Objects outside the course blocks

The object table (main 0x864B48) covers the whole polygon ROM (classic-sources.md, last section). Objects that matter
outside the 60 + 60 + 2-3 objects of a course:

| Objects | What | How known |
|---|---|---|
| 171 (Desert, 2 boards), 172 (Mountain, 4 x 2 boards) | a white hand-written "CHECK POINT" text overlay, 13 m x 1 m, 2.8 m above the road, sheet 0 tile x1280 y0 256x32. NOT the trackside banner: on Mountain it stands about 65 m off the road and crossing it triggers nothing | VERIFIED (data); "fake" status in game (owner, 2026-10-07: "wrong texture, it should be blue and yellow") |
| 235..278 | the 22 spectator sprites, in pairs (15_spectators.md) | VERIFIED (decoded) |
| 783 / 784 | gate post, 0.6 m wide, 6 m tall | VERIFIED (decoded), found 2026-10-08 |
| 785 / 786 | gate post, 1.0 m wide | same |
| 787 / 788 | gate post with a SEGA RALLY CHAMPIONSHIP sign | same |
| 789 | CHECK POINT banner, 10 m (blue panel + yellow letters, y 4.6 .. 5.8) | same |
| 790 | CHECK POINT banner, 20 m, with sponsor panels | same |
| 791 | FINISH! banner, 10 m (grey panel + red letters) | same |
| 792 | FINISH! banner, 20 m | same |
| 1257 / 1258 | Mountain's backdrop: the castle island (cliff ring y 0..18.5, foliage shelf and tree wall up to y 39.7, no cap), a second copy of one rock top, the far sky and ground | VERIFIED (data) |

How the gate set was found (method, VERIFIED to work): the owner's Model 2 emulator (ElSemi) has a "dump texture cache"
function that writes greyscale PNG files named `<hhhhhhhh>_<hash>.png`; the first 4 hex digits are texture header word 2
(x = 32 x (w & 0x3F), y = 32 x ((w >> 6) & 0x1F)), the last 4 are header word 0 (size). Searching every ROM object for
polygons with that header finds the model. The "CHECK POINT" letters are tile sheet 0 x1792 y0064 256x64; the blue panel
uses colour base c208 and the yellow letters c0A0, on ROM pages 0x200000 / 0x280000.

## 9. The trackside table (placed objects)

Per-course tables in the program ROM, 32-byte records `{f32 angle, f32 x, f32 y, f32 z (game axes), u32 section, u32 kind,
u32 model, u32 flag}`, sorted by section, ended by section 99999. Offsets: 15_spectators.md, section 3.

| Kind | Meaning | Confidence |
|---|---|---|
| 4 | one spectator sprite; model 0..21 | VERIFIED position (15_spectators.md); model -> object mapping LIKELY |
| 16 | a gate (one record per gate); model 0 = CHECK POINT, model 1 = FINISH (the start / finish line) | LIKELY (from distances; the code that maps a record's model number to an object was not read) |
| 17 | a gate post; at every gate one kind-17 record lies 9 .. 11 m from the kind-16 record, across the road | LIKELY (all four Mountain gates come out 9.5 .. 10.2 m wide) |
| 6 (6 records on Mountain), 20 (6 records) | not identified | UNKNOWN |

Gate reading used by `gates1995.py`: a gate = two posts, at the kind-16 position and at the kind-17 position 9 .. 11 m from
it, with the 10 m banner between them. The start / finish line differs: its two posts are the kind-17 records of model 2
beside it, and the FINISH gate is the 20 m one (object 792) centred on the kind-17 record FARTHER from the kind-16 record,
with posts at +-10 m. A first reading ("gate between the two records") put a post in the middle of the road - DISPROVED
in game (owner, 2026-10-08: "the finish gate being on the middle of the road"). Post style per gate is a choice of the
course settings, not data.

What the 1995 game shows at the line (owner, Model 2, 2026-10-08): nothing at the start of the race (the owner's texture
dump taken at Mountain's start has no START or gate tile); after one lap a 20 m CHECK POINT gate with its posts outside the
road (object 790); on the final lap the same gate reads FINISH (object 792). The banner hangs in front of the posts, on the
side the cars come from, and reaches their outer edges. How SR3 reproduces this: 15_spectators.md, last section.

## 10. How a 1995 course is built (findings that drive the importer)

All measured on Mountain unless stated; VERIFIED (data) by the importer's own counts.
- **A ribbon, not a landscape.** Road, a low stone wall 5.5 to 8.6 m from the centre line and about 1 m high, then either a
  rock strip a few metres wide or nothing. On the sea side of the town (cells 14 to 62 of the 300-cell centre line, 556 m)
  there are 849 cut-out boards (45 lamp, 276 trunk, 126 bare tree, 210 tree, 192 crown) with their feet at road height and
  2 lying polygons in the whole stretch. About 900 of 1285 trunk groups have no polygon under them
  (classic-sources.md). The low 1995 camera and the wall hide every foot.
- **No Z-buffer, so polygons are layered in one plane.** The hardware sorts and paints by priority; the data lays road
  paint, tyre marks, kerb stripes, shadows, windows, signs and ivy exactly on top of other polygons. Counts: 393 ivy / rock
  pairs on the same corners in the hi model (248 c0AE + c1A6_t, 84 c101 + c1A6_t, 61 c0AE + c1D6_t) and 15 in the backdrop;
  1,562 coplanar overlapping polygons with different outlines. The per-polygon sort mode bits were not decoded (UNKNOWN);
  `layers.py` guesses the order: cut-out over opaque, smaller over larger, later over earlier.
- **Front / back pairs.** 2819 polygons are listed twice on the same corners with opposite winding and the same tile: the
  hardware culls back faces, so a board or wall meant to be seen from both sides is two polygons, each with its own uv so
  text reads right from its side.
- **Trees are blades.** A tree is a set of upright blades that all start on one vertical axis and run outwards in three
  directions; a blade is a strip of boards in one plane (trunk, a composed joint, crown inner part, crown outer part); each
  board is listed once per side with a DIFFERENT half of the picture: front u 0.5 .. 0, back u 0.5 .. 1. VERIFIED (data,
  2026-10-07; dropping the second face as "the same board again" showed fat trunks as slivers in game).
- **Which side shows is not reliable in the data.** Opaque polygons without a back twin carry a stored normal that is not
  reliable for every polygon (LIKELY; the importer stopped trusting the winding, see 16_lighting_shadows_lightmaps.md 3.2).
- **Backdrop duplicates.** 29 opaque faces of backdrop object 1257 (tile c0D9) have exactly the corners of 29 hi-model
  faces (tile c101) of objects 1279 / 1284, which also carry an ivy overlay: three polygons in one plane.
- **Smeared and over-repeated uv exist in the original.** Object 1291: two tree-line boards with u 1..27 over 9 and 14 m
  and a road polygon with 28 repeats over 5 m. Sections 1284 / 1285: cliff end caps with 6 texels across 12 m and 256 texels
  up 30 m. Some polygons have uv on a line (one texel row smeared).
- **Scale.** The town is built about twice life size (lamp posts 8 m, three-storey houses 25 m).
- **Sky.** One 256 x 256 picture: clear blue at the top, clouds, soft haze along its bottom edge (the horizon). On the
  dome (objects 1257 / 1258) a wall of radius 100 km from the horizon up to 53.8 km (= 28.3 degrees) carries the picture
  once in height (v linear in height) and once per 60 degrees of azimuth (6 times around); above the wall the cone uses
  the top row. VERIFIED (measured on the dome).
- **Sea.** A bowl 2 .. 100 km out and 3.6 km down.
- **Far rock screens.** The big ivy-covered rock of sections 1280 .. 1282 is a curved screen of cliff faces about 100 m
  long from y 54 to 125, with no back and no top.
- **Light.** The hand-typed unit vector (0, -0.94, 0.34) at prog 0x13CD0 and 0x14810 (16_lighting_shadows_lightmaps.md,
  section 4). The castle (three boards) is painted lit from the left while that sun stands to its right.
- **Brightness of the tiles.** Model 2 emulator shots show the mid tones far darker than the decoded tiles while white
  stays white; a gamma of 1.7 on the tiles matches rock, sea and sky (owner on the build with it: "colors are perfectly
  matched"). VERIFIED in game against Model 2 reference shots (`Screenshots/ref_model2`).

## 11. What nobody found
The time awarded was found (section 5); still UNKNOWN: the player's grid slot, rival car lines other than the single AI
line, physics per surface, per-polygon brightness (the importer assumes full), the kind 6 / 20 trackside records, the code
that maps a trackside record's model number to an object, and the per-polygon sort priority.
