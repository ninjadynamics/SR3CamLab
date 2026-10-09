# 15 - Spectators (SR3's animated crowd) and the 1995 crowd table

Tools: `work/scripts/crowd.py` (parsers, writers, 1995 table reader, builder), `work/scripts/check_crowd.py` (self-check).
In-game result of the first build and its cause: section 4. Tags: VERIFIED (how), LIKELY, GUESS, UNKNOWN.

## 1. Where SR3 keeps a spectator

Two files, both needed, linked by OBJECT INDEX (position in the object list):

| File | Holds |
|---|---|
| `*_game_objects_gfx_data.sbf` | root (last chunk, kind 5): the object list - one 0x54-byte record per object. Other chunks: textures, materials, one shader stub, meshes, particle definitions (kind 12), break shapes (kind 5). |
| `*_gameobj_gfx_dis_data.sbf` | root (last chunk, kind 5): "model sets" - which Granny model + animations belong to which objects. Other chunks: pairs of {kind 7 Granny file, kind 5 of 8 bytes `{u32 1 or 3, chunk id of the Granny file}`}. |

Spectators have NO link to road slices, to the scenery tree or to the pobj files. Position and facing are in the record's
matrix only. VERIFIED (data): the layout below predicts every chunk-id cell and every pointer cell of both roots on all
six arcade tracks, except 2 to 14 pointer cells per track that sit inside path parameters (`{u32 count, ptr points}`,
used by path animators, not by spectators); parse -> rebuild -> parse gives the same content on all six.

### game_objects root
| Off | Field |
|---|---|
| 00 | u32 3 (version) |
| 04 | u32 object count |
| 08 | ptr object records |
| 0C | ptr descriptor `{u32 1, u32 n, ptr entries}` - entries of 0x2C like the dis ones below, for particle objects and the start banner (their resource ids are kind 12 chunks of this file). Spectators are never listed here. |
| 10 | ptr MATERIAL BINDING table `{u32 n, n chunk ids}`: one kind 5 chunk per Granny model, `{u32 3, u32 n, n x {ptr material name, kind 2 chunk id}}` (e.g. `temp_male_01_body_VARIANT1..3`, `..._head_...`, `..._legs_...`, `crowd_airhorn`, `Zebra`). NOT break shapes (earlier guess, wrong). Must be kept for anything skinned: see section 4. |

Object record, 0x54 bytes:
| Off | Field | Spectator value |
|---|---|---|
| 00 | ptr group name | `Skinned_Objects` |
| 04 | ptr class name | `(A)Dumb_Temp_Spectator` |
| 08 | u16 = 1 in every record seen | 1 |
| 0A | u16 parameter count | 4 (0 for the animators) |
| 0C | u32 object id, unique, roughly ascending (Desert4 0xC92.., Canyon4 1..) | - |
| 10 | 16 x f32, rows: `(c,0,s,0) (0,1,0,0) (-s,0,c,0) (x,y,z,1)` | scale always 1 |
| 50 | ptr parameter list: count x `{ptr name, ptr value cell}`; lists and cells are shared between objects | see below |

Parameters of a standing spectator (value cell = 4 bytes): `Draw Distance` f32 (95 Desert4 / Stadium4, 150 most of
Canyon4), `Cast Shadow (Fwd)` u32, `Cast Shadow (Rvs)` u32, `Reflect in water` u32. A text parameter's value cell is a
pointer to the string. VERIFIED (data). What the u16 at +8 means: UNKNOWN.

Facing: the model looks along local -Z, i.e. world direction `-row2 = (s, 0, -c)`. VERIFIED statistically: all 1176
seated spectators of Stadium4 have row2 . (direction to the nearest centre-line point) = -1.00; Canyon4 median -0.96.
(Standing crowds are often turned along the road instead, so only the seated ones prove it.) `crowd.matrix(x, y, z, h)`
takes h = heading of the look direction, f = (sin h, 0, cos h).

Height: the origin is at the feet (Desert4 median 0.10 m above the road centre). Spacing in SEGA's crowds: median 1.0 m
between neighbours (Desert4), 0.69 m seated (Stadium4), never under 0.5 m.

### Classes on the arcade tracks (object counts)
| Class | Alp | Can | Des | Lak | Sta | Tro |
|---|---|---|---|---|---|---|
| `(A)Dumb_Temp_Spectator` | - | 561 | 624 | 597 | 186 | 992 |
| `(A)Dumb_Temp_Sitting_Spec` | - | - | - | 130 | 1176 | - |
| `(A)Dumb_Arctic_Spectator` | 806 | - | - | - | - | - |
| animators `(A)Temp_Spec_Anim`, `_Active_`, `_Female_`, `_Airhorn_`, `_Camera_` (Alpine: `(A)Arctic_...`) | 18 | 16 | 16 | 18+4 sitting | 16+6 | 16 |
| `TV_Cameraman_Temperate` / `_Cold` | 5 | 13 | 7 | 6 | 15 | 8 |
| `Crowd_SFX_Object` (params `Audio Path`, `Crowd Size`) | 5 | 5 | 0 | 0 | 14 | 4 |

Desert4 itself has the temperate crowd, so the Classic slot needs no foreign donor: model, animations and textures are
already in its two files.

The animators (16 per track) are the animated masters: no parameters, identity rotation, parked in a tight block away
from the road (Desert4 x 838, y 9.9, z 145 = outside the scenery square, 465 m from the road; Canyon4 47 m under the
road; Stadium4 at the origin). The "dumb" spectators copy their pose (LIKELY - the names say so and the dumb ones have no
animation object of their own; not traced in code). Whether an animator is drawn or needs to be near the camera:
UNKNOWN; crowd.py leaves them exactly where SEGA put them.

### dis root
`{u32 1, u32 n, ptr entries}`; entry, 0x2C bytes:
| Off | Field |
|---|---|
| 00 | ptr class name of the run-time object, e.g. `DumbArcadeTemperateSpectator1Obj` |
| 04, 08 | u32 1, u32 1 |
| 0C | ptr type string `granny` (`particle` / `model` in the game_objects descriptor) |
| 10, 14 | u32 object count, ptr u32 object indices |
| 18 | u32 resource count |
| 1C | ptr resource chunk ids (the 8-byte chunks; first = model, the rest = animations) |
| 20 | ptr resource name pointers (source paths, `.../Granny/Arcade_Crowd/temp_male_01.data`, `.../Animation/Ax_idle_01.data`) |
| 24, 28 | 0, 0 |

Every `Skinned_Objects` object is listed by at least one entry. EVERY dumb spectator is listed by ALL ELEVEN dumb
entries (Desert4: `DumbArcadeTemperateSpectator1..5Obj` = temp_male_01..05 + 10 idle animations,
`...ActiveSpectator1..3Obj` = idle + 3 active animations, `...CameraObj`, `...AirhornObj`, `...FemaleSpectatorObj`):
the game picks the look per spectator at run time (LIKELY at random or by id; not traced). The animators have one
entry per kind (`ArcadeTemperateSpectatorAnimatorObj`, ...). VERIFIED (data, Desert4: 624 objects x 11 entries).
Which entry names the arcade exe accepts was not checked in code; crowd.py only reuses SEGA's entries unchanged.

## 2. What crowd.py writes
- `crowd.build` (S2) game_objects: SEGA's file with a new root: the 16 animators (records as SEGA's) + one
  `(A)Dumb_Temp_Spectator` per spot; descriptor count 0; the material binding table KEPT (all 26 chunks). All other
  chunks stay, byte-identical (spectator textures / materials are found by id, so nothing is pruned).
- gameobj_dis: SEGA's file with a new root: the 16 spectator entries of 29, object lists rewritten; the Granny chunks
  of the zebras, elephants, balloon, marshal, flags, helicopter, birds, bollards and TV cameraman stay in the file
  unused (`prune=True` drops them).
- Gone: 735 of Desert4's 751 objects (zebras, elephants, balloon, marshals, flags, helicopters, birds, bollards,
  cameramen, waterfall sound, particles, start banner).
- pobj_master, pobj_plac, procobj_plac and the grass cache are not touched (the game needs them).
- `crowd.build_safe` (S1, `--safe`): SEGA's two files with ONLY the 64 matrix bytes of the 624 spectator records
  rewritten (548 spots; the 76 spare records parked in a block beside SEGA's hidden animators, outside the scenery
  square). Nothing removed: Desert4's animals, bollards, balloon, banner stay at their Desert4 coordinates.
Self-check (`check_crowd.py`): container checks, fix-up / ref lists equal the layout model, other chunks identical to
SEGA's, animators identical, matrix form, positions inside the +-750 m square, every object covered by as many model
sets as in SEGA's file.

What can still go wrong in game (not checkable statically): (a) an empty particle descriptor together with a full
dis file is a combination SEGA never ships (each was seen alone: step34b empty list, original full list); (b) a
spectator standing inside scenery or on a balcony edge; (c) crowd draw cost where the 1995 crowd is dense; (d) some
other file addressing objects by index or id (none found in the object files; cameras / helicopter in master_xdata were
not searched for object ids).

## 3. The 1995 crowd (SEGA Rally Championship)
The crowd is NOT in the course models (objects 1259..1318 for Mountain) and not in the exported OBJ: none of the 130
tiles of `src_course1_hi.obj` shows people (25 cut-out tiles = trees, bare trees, trunks, ivy, fence, lamp, tower
windows). So the importer draws no crowd cut-outs and has no material to drop.

- Sprites: objects 235..278 of the object table, in pairs (two per person), each ONE quad about 0.8 m x 1.9 m, origin at
  the feet, texture on sheet 0 (ROM page 0x300000 region: tiles `x0000..0448_y0416`, `x0640/0704_y0384`,
  `x0896/0960_y0416`, `x1280..1472_y0384`, `x1728..1920_y0384`, `x1984_y0320`, `x0128/0192_y0448`, 64 x 128 texels,
  translucent). VERIFIED (decoded with classic_export.decode).
- Placement: tables in the program ROM (`work/tmp/m2/maincpu.bin`), 32-byte records
  `{f32 angle, f32 x, f32 y, f32 z (game axes), u32 section, u32 kind, u32 model, u32 flag}`, sorted by road section,
  ended by section 99999.

| Course | Table offset(s) | Records | Check |
|---|---|---|---|
| 1 Mountain | 0x4AD00 | 572 | median 9 m from the centre line; y = the 1995 ground (see below). VERIFIED (data) |
| 3 Lakeside | 0x4F4C0 | 209 | median 9 m. LIKELY |
| 2 Desert | 0x50F00 (sections 0..127), 0x53120 (128..299) | 272 + 117 | median 12 / 18 m. LIKELY |
| 4 Forest | 0x54000 (0..139), 0x55EA0 (148..299) | 207 + 369 | median 12 m. LIKELY |

- kind 4 = a spectator; model 0..21 = which of the 22 people (LIKELY: 22 models, 22 sprite pairs; the code that maps
  model -> object number was not read); flag 0 / 1 about half each (GUESS: animation phase). Other kinds on Mountain:
  6 (6 records), 16 (4), 17 (8), 20 (6) - not identified.
- Mountain: 548 spectators in 109 of the 300 sections, on both sides (292 / 256), 2.6 .. 50 m from the centre line
  (median 9.1), nearest neighbour median 2.6 m, never under 0.56 m.
- y: 490 of 548 lie over a polygon of the exported course; there the table y is 0.09 m (median) under the polygon, 408
  within 0.15 m. VERIFIED: the table is the crowd's ground position, and the axis conversion is right.
- angle: spread evenly against the direction to the road, so it is not "face the road" (GUESS: start phase or a
  camera-facing sprite). crowd.py ignores it and turns every spectator to the nearest centre-line point.

Conversion (importer convention, ZS = -1): SR3 = (x + ox, y + 0.09, z_game + oz). `crowd.fit_offset` recovers ox / oz
from a built track (Mountain: ox 137.745, oz 52.842, centre-line residual median 0.25 m).
One SR3 spectator per 1995 sprite: 548, under Desert4's own 624. 214 of them stand inside the SR3 road strip (which is
wider than the 1995 road); they are moved sideways to the strip edge + 0.75 m (median move 0.19 m, three moves over 4 m).

## 4. First in-game run (step35, 2026-10-07) and its cause
Result: loads and races; the spectators were grey (no textures), T-posed, and seemed to stick to the cars and flicker.
The first build had EMPTIED the table at root +10, taken for "break shapes". It is the material binding table:
- VERIFIED (code): 0x5BF450 stores the table pointer in [0x9C0E68]; 0x55D7B0 (called from 0x6651FC while a Granny model is
  set up) walks every chunk of that table and compares material NAMES as strings to find the model's kind 2 materials.
  Empty table = no material found = untextured.
- VERIFIED (code): the loop 0x5BF4A6..0x5BF5C8 visits every material of every table chunk and, for Uber-shader materials,
  changes a shader option slot (words +4 / +0xA of the material object; warning text `Sega_ML_Uber_SetBoolOption`).
  LIKELY this is the skinning variant: without it the mesh is drawn unskinned = bind pose (T-pose).
- GUESS: an unskinned draw uses whatever world matrix was set last (the cars are drawn near by), hence figures that
  follow the cars and come and go. The record matrices themselves were right (self-check) and the dis index lists
  were consistent; neither was changed between the first build and S2.
- Matching is by NAME, not by position in the table (VERIFIED: the table order differs from the model chunk order in
  the dis file), so the table can be kept whole whatever objects are removed.
Fix: `crowd.build` keeps the table. Variants: `step35a_mountain_spectators_safe_desert4` (S1) and
`step35b_mountain_spectators_only_desert4` (S2 = the first build + the table). The old `step35_mountain_spectators_desert4`
is the faulty build.
If S1 shows correct spectators and S2 does not, the remaining differences are: empty particle descriptor, removed
objects, renumbered object ids, block order inside the root.

## Facing of the eleven looks (2026-10-08)

- In game, on Mountain build Z3 (every spectator's heading set towards the nearest centre-line point, checked in the
  written file: all 506 within 30 degrees), two women and one man stood with their backs to the road while their
  neighbours faced it (user screenshots SR3_20261008_001305 / 001315 / 001527). VERIFIED (screenshots).
- The Granny data does not explain it. Sampled with the game's own granny2.dll (2.7.0.8, 32-bit, from a 32-bit PowerShell):
  all 8 models (temp_male_01..05, temp_female_01, temp_airhorn_male, temp_camera_male) have the same skeleton placement,
  and in all 21 animations hips and chest stay within about 25 degrees of the model's forward axis. VERIFIED (data).
- So the turn is the game's doing (code not traced). A first guess - that it is 3 of the 11 looks (woman, camera man, airhorn
  man) - is WRONG: the user saw a plain man turned away too (2026-10-08). Which look a spectator gets is chosen at run time, so a heading cannot be corrected per person.
- `crowd.build(drop_looks=...)` can leave Dumb entries out of the dis root; default `()` = all eleven looks (a build with the
  three left out loaded and ran in game). Why some spectators turn away: UNKNOWN.
- SEGA's own Desert4 crowd: of 624 spectators 268 look at the nearest road point, 133 along the road, 223 away from it
  (whole groups). SEGA did not aim its standing crowds at the road.

## In-game result of the fixed crowd (2026-10-07)
548 SR3 spectators stand on imported Mountain, textured and animated; the fix was to keep the material binding table at
game_objects root +0x10. VERIFIED in game (seen in runs of 2026-10-07; the crowd is the importer's default since). The
notes do not say which of the two variants of section 4 (S1 safe, S2 objects removed) the verifying run used; the
importer's default path is `crowd.build` (S2).

## Where the importer finally puts each spectator (`import_classic.stage_build`, 2026-10-07 / 08)
- Every spectator stands ON the final ground: the lying surface NEAREST the 1995 foot height within 3 m of it; no such
  surface = no spectator. (Taking the HIGHEST surface put people on top of the roadside walls.)
- A spectator hidden behind a stone wall or rock right beside the road (the person is hidden, the shadow lies on the
  tarmac alone) is moved back to 5.5 m from the road edge.
- After any move the spectator is turned to face the road again.
- The owner asked for "every NPC must face the track"; the written headings are right, the run-time turning is not
  explained (section "Facing of the eleven looks").

## Run-time type names (from `classic/revofix/exe_types.txt`)
That file pairs class names with run-time object names, for example `(A)Dumb_Temp_Spectator` ->
`DumbArcadeTemperateSpectator1Obj`, `(A)Dumb_Arctic_Spectator` -> `DumbArcadeArcticSpectator1Obj`, `(A)Temp_Spec_Anim` ->
`ArcadeTemperateSpectatorAnimatorObj`, and also Revo's names (`Dumb_Temperate_Spectator` -> `DumbTemperateSpectator2Obj`,
`Generic_Path_Animator`, `Gen_Path_NF_Anim_With_Emitter`, `Generic_Breakable`, `Lap_Animator`, `Distance_Animator` ...).
LIKELY the type table of the arcade exe (the file name says so; how it was extracted is not written in it). If so, the
arcade exe knows Revo's type names too, which bears on 13_revo_vs_arcade.md, row 8.

## The lap-driven start / finish gate: SR3's `Start_Finish_Line` object (2026-10-08)
- SR3 has one object per track of class `Start_Finish_Line` (exe class CSR_StartFinishObject), model type
  `StartFinishObj` = ONE mesh chunk with three LODs; in Desert4's game_objects file the mesh is chunk `4ec27d47`. Its
  parameter record holds a path written where a value is (not a pointer cell) (`crowd.parse_objects`).
- The object forces the LOD itself: object +0x1B8 is read at 0x632BE5 as the LOD to draw, and 0x61CAF0 (called every
  frame from the object's update 0x61FD30) sets it. So the three "LODs" are three STATES:
  | LOD | When | SEGA's content |
  |---|---|---|
  | 0 | from the start | START banner in front |
  | 1 | race running and the car more than 300 m away | CHECKPOINT |
  | 2 | final lap ([0x9DD614] == laps - 1) and the car within 300 m | FINISH |
  VERIFIED (code).
- This matches what the 1995 game does at the line (nothing at the start, CHECK POINT after a lap, FINISH on the last
  lap; 18_src_1995_rom_data.md, section 9). `finishgate.install` therefore rewrites the mesh with three face lists
  [nothing, CHECK POINT gate, FINISH gate]; a state with nothing to show is one quad of no size under the ground, because
  a LOD needs a group. The mesh keeps its id and its tail (node names, LOD table); vertices are format 0x20C3 (36 bytes:
  position xyzw, normal, uv0, uv1), relative to the object's centre; every vertex points at one texel of the banner's
  light map. Materials are clones of the banner's own (blend, two-sided, shadow casting, light map) or, with `unlit`,
  SEGA's unlit material, because the banner's lit one "came out dull".
- `crowd.build(finish_at=(x, y, z))` keeps the slot's own Start_Finish_Line object record and stands it there with
  identity rotation. Without the crowd files the gate at the line stays plain scenery reading FINISH.
- In-game result of THIS replacement: not confirmed when the sources were written (UNKNOWN).
