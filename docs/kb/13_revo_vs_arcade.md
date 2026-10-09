# SEGA Rally Revo tracks in the arcade engine: what is not handled the same way

Static analysis only (no game was started). Every finding is tagged:

- VERIFIED (data) - read directly from the track / library files
- VERIFIED (code) - read from the disassembly of Rally.exe (image base 0x400000)
- GUESS - an inference that nobody has seen in game yet

Sources compared: the six arcade tracks (`GAME\Sega Rally 3\Rally\Main_release\tracks\*4`), the Revo PC demo
(`F:\Jogos\_revodemo_dl\...\SEGA Rally Revo Demo`, tracks canyon2 and tropical2), the 24 converted PS3 tracks
(`F:\Jogos\_revo_ps3_converted\main_release\tracks`) and their PS3 sources.

Scripts: `..\scripts\revo_scan.py` (chunk index), `guess_scan.py`, `k11_classes.py`, `k11_check.py`, `small_unk.py`,
`partA_gaps.py`, `partA_gaps2.py`.

---------------------------------------------------------------------------------------------------

## 1. The three glitches the user saw on tropical2

First, what they are NOT: conversion errors. Converted tropical2 against the PC demo's tropical2, file by file
(VERIFIED data):

| file | result |
|---|---|
| `master_xdata`, `pobj_plac_gfx_xdata` | identical |
| `master_gfx_xdata` | all textures, materials, structures identical; the scenery tree (kind 11, id 377920af, 2,314,236 bytes, PVS included) is byte-identical; 347 meshes differ (half-float positions, strip joins: expected) |
| `pobj_master_gfx_xdata` | 27 meshes differ, nothing else |
| `game_objects_gfx_data` | 6 meshes + 24 structure chunks differ |
| `gameobj_gfx_dis_data` | 1 structure chunk differs; all 39 Granny animation files identical |

The structure differences that were inspected are 2-3 junk bytes after string terminators (the PS3 and PC builds
left different garbage there). The largest one (game objects root 7c1638ed, 1,974 words) was not checked word by word.

So all three glitches would also happen if the PC demo's own tropical2 files were dropped into the arcade game.
They are differences between the Revo engine and the arcade engine.

### 1.1 "Some missing textures (like 1 or 2)"

Cause: two Revo shaders that the arcade game does not have. Evidence: VERIFIED (data + code) for the missing
shaders; GUESS for how exactly the result looks on screen.

- A material names its shader through a kind 3 stub that holds a `.fx` file name. tropical2 uses five:
  `ubershadermax.fx`, `3wayblend.fx`, `water.fx`, `i_pl_psm.fx` (stub bf5a7529) and `i_pl.fx` (stub de3ada93).
- The arcade shader libraries (`system\shaderlib2_data.sbf`, `shaderlib3_data.sbf` and the `_uber` ones) contain
  no `i_pl.fx` and no `i_pl_psm.fx`. The Revo demo's libraries do. No arcade track uses either. (VERIFIED data.
  This corrects the knowledge base line "No PS3 track uses a shader or mesh format the arcade lacks".)
- In the exe (VERIFIED code): 0x592060 renames only `UberShaderMax.fx` to `UberShaderGame.fx` (table 0x729B0C);
  0x5921F0 looks the name up among the loaded library entries (names at 0x9F1084, count at [0x9F1280]) and returns
  0 when it is absent; the stub resolver 0x58F9A0 then logs "Effects: WARNING! ShaderLib was loaded but the s..."
  and at 0x58F955 a failed effect falls back to `GraphicsDebug.fx`. What `GraphicsDebug.fx` draws (flat colour,
  untextured, nothing) was not determined: that part is the GUESS.
- In tropical2 exactly two materials are affected, which matches "1 or 2":

| material | shader | used by | what it is |
|---|---|---|---|
| 97a9a06c (`tropical2_master_gfx_xdata.sbf`, 856 bytes, four 512x512 DXT1 textures: 67416668, 6da540ba, eee0d886, 8b884730) | i_pl_psm | scenery mesh 9e719aca, 3 detail levels, 1004 vertices | one flat object 14 m wide, 2 m high, 0.2 m thick in its own space: a banner / hoarding sized panel, referenced once by the scenery tree |
| 3e7bf191 (`tro_track_route2_pobj_master_gfx_xdata.sbf`, 660 bytes, textures e6294a4d 256x256 DXT5, 3e4e5729, 64ecbcaf) | i_pl | procedural object mesh 65a06881 "tro_bush_02_procedural_" (8 vertices, 0.6 m tall) | a small bush scattered by the procedural placement system (many copies) |

Per track (materials that use a shader the arcade lacks; VERIFIED data):

| track | i_pl_psm | i_pl |
|---|---|---|
| alpine2, alpine7 | 1 | - |
| arctic3 | - | 1 |
| canyon1 | 3 | 1 |
| canyon2, canyon7 | 3 | - |
| canyon3 | 3 (1 mesh) | - |
| lakeside1 | 6 | - |
| safari1, safari6 | - | 2 (1 mesh) |
| safari3 | 3 | 2 |
| tropical1 | 4 (5 meshes) | 1 |
| tropical2, tropical3, tropical7, tropical8 | 1 | 1 |
| alpine1, alpine3, alpine6, arctic1, arctic2, arctic6, arctic7, safari2 | none | none |

Proposed automatic fix (not implemented): at import time, replace every material whose stub names `i_pl.fx` or
`i_pl_psm.fx` by an Uber material: take an Uber material of the same track that is used with the same vertex
format (0x20C7 for the panel, 0x2047 for the bush), keep the i_pl material's chunk id, and put the i_pl
material's first texture (gTexture0, the reference at +0xBC / +0xCC) in the Uber material's diffuse slot (+0x1BC),
its second in the normal-map slot when the donor has one. The mesh then needs no change. Cheaper alternative
with the same visible result as today or better: nothing; cheapest "hide it" alternative: drop the two meshes.

### 1.2 "Some birds frozen in the sky"

Conversion ruled out (VERIFIED data, see the table above: the bird animation files and object data are the demo's).
Mechanism: GUESS, with one concrete lead.

- The birds are game objects of class `Skinned_Objects`, type `Thrush` (exe classes CSR_ThrushObject,
  CSR_BirdsOnTrackObject; animation `granny/thrush/thrush.data`, present in both games' track files).
  Tropical4 (arcade) has 10, tropical2 (Revo) has 20.
- Their parameter lists differ (VERIFIED data):

| parameter | arcade Tropical4 | Revo tropical2 |
|---|---|---|
| Path1 | a path id | a path id (e.g. 42) |
| Animation Speed | 0.8 | 1.0 |
| Spline Time | 500 | absent |
| Draw Distance | 800 | 10000 |
| X/Y/Z Offset, Orientate on spline, Cast Shadow (Fwd)/(Rvs), Reflect in water | present | absent |

- VERIFIED (code): the Thrush constructor 0x62C0B0 reads "Spline Time" by name (0x630120) and uses 10.0
  ([0x6BED54]) when the parameter is missing, storing it at object +0x350; 0x62C940 reads "Path1" and hands the
  id to 0x641FA0.
- GUESS: the arcade build flies a bird along its path over "Spline Time" (500 in arcade data); the Revo data
  never gives that parameter, and the arcade code's path lookup or its 10.0 default leaves the bird parked at
  the start of its path, still drawn because of the 10 km draw distance. Which of the two it is was not settled.
- Other object types changed name between the builds too (arcade `(A)Dumb_Temp_Spectator`,
  `Lap_Distance_Animator`, `Generic_Path_NF_Animator`; Revo `Dumb_Temperate_Spectator`, `Generic_Path_Animator`,
  `Gen_Path_NF_Anim_With_Emitter`, `Generic_Breakable`): objects of a type name the arcade exe does not know are a
  likely source of other missing / static props. Not surveyed per track.

Proposed automatic fixes, simplest first (none implemented):
1. Hide them: set each Thrush object's "Draw Distance" float to a tiny value (one 4-byte write per bird, no
   structure change). Certain to remove the frozen birds; loses the birds.
2. Make them fly: add a "Spline Time" 500 parameter to each Thrush (the parameter pointer list has to grow, so the
   game objects chunk must be rebuilt with shifted fixups). Only worth doing after an in-game test of fix 1's
   opposite: patch the default at [0x6BED54] from 10.0 to 500.0 in memory and see whether the birds move.

### 1.3 "Missing geometry in the distance, depending on camera position and angle"

Cause: the Revo track's own PVS (potentially visible set), used by an arcade camera it was never computed for.
Evidence: VERIFIED (data + code) for everything below except the last sentence of each answer, tagged there.

Does the Revo PVS differ in kind from the arcade's? No, same format, different numbers (VERIFIED data):

- Same structure version (header word 0 = 2), same node record (32 bytes), same leaf record and stream coding
  (FF n / 00 n runs, literal bytes), same 1/16 m box scale. A checker written for this task
  (`..\scripts\k11_check.py`) parses arcade and Revo trees with the same code: every child inside its parent,
  every leaf stream decoding to exactly the node count.
- What differs is only the leaf cell size at header +8: arcade 46.875 m (Tropical4, Canyon4; also Revo
  tropical1), Revo tropical2 58.92 m, arctic1 54.23 m, arctic2 68.21 m. The exe holds no hard-coded 46.875,
  1/46.875 or -750 (VERIFIED code: no such constants), and the leaf lookup 0x5003C0 walks the node boxes read from
  the data, so the different cell size is handled.
- The tree in converted tropical2 is byte-identical to the PC demo's, so nothing was lost in conversion.

Why it shows: 0x500EA0 looks up the camera position (0x9EB9A0 + 0x4D0 * [0x9F05F0]) in the tree and shows only
the nodes listed in that leaf's stream. Revo's streams were computed for Revo's cameras and Revo's draw
distances; the arcade cameras (and the user's raised chase camera) sit higher / further back and see over
occluders, so nodes the PVS calls hidden are in view (GUESS for "that is why", VERIFIED that the hiding is done
by this stream and nothing else on this path).

Can anything other than the PVS hide distant geometry by camera angle? Statically, nothing that fits the
description:

- When the camera is in no leaf (lookup returns 0), the code takes the same "all nodes visible" branch (0x4231E0)
  as when [0xA65794] != 0. So leaving the tree's area does not hide anything; it shows everything.
- Frustum culling against the node boxes remains with the PVS off. The boxes are the demo's own data, verified
  consistent, so this only removes what is off screen.
- Distance limits ("Draw Distance" parameters of game objects, detail levels of meshes) remain. They depend on
  distance only, not on angle, and apply to props, not to the scenery tree's terrain and buildings.
- Not excluded statically (GUESS): the far clip plane and fog distance of the arcade track setup, which would cut
  the same distant geometry at any angle once the PVS no longer hides it first.

Will holding [0xA65794] = 1 cure it completely? Expected yes for the angle- and position-dependent part: with
the flag set the stream decoder (0x4FFC30) is never consulted and every node is a candidate, exactly as on a
track with no leaf under the camera. The cost is drawing more (the mod already accepts that on drone cameras).
What could still be left afterwards is a fixed-distance cut-off (far plane), which would look different: a
constant horizon line, the same from every angle.

---------------------------------------------------------------------------------------------------

## 2. Ranked list of likely visible issues, all Revo tracks

| # | issue | tracks | evidence | automatic fix |
|---|---|---|---|---|
| 1 | Scenery tree converted as plain 32-bit data: node and leaf counts swapped, boxes scrambled, PVS streams byte-reversed. Scenery culling of the whole track is garbage (missing scenery or a crash are both plausible) | arctic1, arctic6 | VERIFIED (data): old output fails every check of `k11_check.py` | DONE in Part B (section 3) |
| 2 | PVS hides geometry the arcade camera can see | all Revo tracks | VERIFIED (data + code) | hold [0xA65794] = 1 (already in the mod) |
| 3 | Shaders `i_pl.fx` / `i_pl_psm.fx` not in the arcade shader libraries: those objects draw with the debug fallback | 16 tracks, table in 1.1 | VERIFIED (data + code); look on screen GUESS | rebuild those materials as Uber materials at import |
| 4 | Birds (Thrush) do not fly: no "Spline Time" parameter, draw distance 10 km | tropical2 verified; any track with Thrush objects | data VERIFIED, mechanism GUESS | set Draw Distance tiny (hide), or add Spline Time |
| 5 | One scenery object missing (mesh bf13e642, 23 detail headers, rejected by the converter's limit of 16); the tree still referenced it | tropical1 | VERIFIED (data) | DONE in Part B (section 3) |
| 6 | Particle / effect emitters: object type 5a1bb4a6 (Revo) vs 58de89a7 (arcade), same 452-byte layout, but the float at +0x10C is 2000.0 (29 objects) or 500.0 (4) in every arcade object and 0 in all 87 Revo ones. If it is a draw / activation distance, Revo's effects (smoke, waterfalls, dust) never show | routes 1, 2, 3, 6, 7, 8 and master files | data VERIFIED, meaning GUESS (reader not found in the exe) | write 2000.0 at +0x10C of every 5a1bb4a6 object |
| 7 | Terrain (3WayBlend) and water materials lack the arcade's extra parameter `g_alpha` (arcade 35 / 44 parameters, Revo 34 / 43; `g_alpha` exists in the arcade shader libraries, not in the demo's, and not as a string in the exe). The shader's default value applies | all Revo tracks | data VERIFIED, effect GUESS (possibly none) | append the parameter, copied from an arcade material of the same shader, if a difference is seen |
| 8 | Object type names the arcade exe may not know (`Dumb_Temperate_Spectator`, `Generic_Path_Animator`, `Gen_Path_NF_Anim_With_Emitter`, `Generic_Breakable`...) | all Revo tracks | names VERIFIED (data); whether the exe accepts them not checked | rename to the arcade's equivalents where the parameter lists match |
| 9 | Vertex format 0x20C1 (stride 24), used by no arcade mesh: mesh eb94ad66 in `game_objects_gfx_data` (121,916 bytes) | tropical1, tropical2, tropical7 | data VERIFIED, effect GUESS | none proposed until seen |
| 10 | Gameplay root object: Revo type 6e9ca290 vs arcade ecdb142b (both 152 bytes); Revo has a reference at +0x20 to a 256x256 texture the arcade roots lack; floats near +0x8C / +0x90 differ (-0.2 in tropical2; 180/600/850 vs arcade 250/800/400) | all Revo tracks | data VERIFIED, effect GUESS | none proposed |
| 11 | Small structures still converted by the fallback (all are 32-bit integers and floats, for which the fallback is the right conversion): a 1,020-byte convex shape chunk and a 48-byte "defaultRigidBody" chunk in `game_objects` (alpine1, alpine6, arctic3), three 40-byte blocks in `master_xdata` (safari1, safari6; one each in arctic1, arctic6, safari3, tropical3); typed objects 15c476ae (8 bytes; alpine, arctic, lakeside, safari) and fbcb17b3 (252 bytes, a name-hash list; safari1, safari6) | listed | VERIFIED (data); judged harmless | none needed |

Not a problem (VERIFIED data): tracks reference nothing outside their own files (0 external resource ids in all
6 arcade and 24 Revo tracks; tropical1's single dangling id was the mesh of row 5); all textures of converted
tropical2 equal the demo's; Uber material sizes occur on both sides; the kind 12 size differences
(5ca5eb35 / ab035dde / fbcb17b3 vs arcade 20018776) are variable-length name-hash lists.

---------------------------------------------------------------------------------------------------

## 3. Part B: the converter's loose ends, fixed

Files in this folder:

| file | what |
|---|---|
| `ps3conv_v2.py` | copy of `ps3conv.py`, one change (mesh header limit) |
| `convtrack_v2.py` | copy of `convtrack.py`, one change (scenery tree class), imports `ps3conv_v2`, loads the unchanged model |
| `run_all_v2.py`, `run_all_v2.log`, `run_all_v2_step1_meshcap_only.log` | converts all 24 PS3 tracks and compares with `F:\Jogos\_revo_ps3_converted` |
| `converted_v2\{tropical1,arctic1,arctic6}\*_master_gfx_xdata.sbf` | the three files that changed (the 165 identical ones were deleted after comparison) |
| `csharp\ps3conv.cs`, `csharp\ps3model.txt`, `csharp\ps3conv.cs.diff` | patched copy of the app's converter; the model file is unchanged |
| `csharp\test.ps1`, `csharp\compare.py`, `csharp\test_results.txt` | C# against Python v2 |

### 3.1 tropical1: the mesh that failed

Mesh bf13e642 in `tropical1_master_gfx_xdata.sbf` (113,760 bytes, 169 pointers, 28 references). A PS3 mesh
starts with one 0x108-byte header per detail level / part; this one has 23, and `conv_mesh` rejected more than
16 as "unexpected mesh header". Arcade meshes have 1, 2, 3, 4, 5, 6 or 12 headers, so many headers are normal;
the limit was only a sanity bound. Fix: limit 16 -> 64 (Python line 90; C# `ConvMesh`). The mesh converts to
148,196 bytes (first header stride 52 format 0x20D7, the others stride 32 format 0x2043). The scenery tree
d02e417c referenced it, so the old output had a dangling reference; now all 316 mesh references of the tree
resolve.

### 3.2 arctic1 / arctic6: the "8% guessed words"

All of it is one chunk: the scenery tree (kind 11; 234cad72 in arctic1, 17519915 in arctic6; 351,528 words).
The model keys its layouts by a chunk class that includes the first three pointer offsets of the chunk. Every
other tree starts 12, 44, 76 (the content pointers of nodes 0, 1, 2). In arctic1 / arctic6 node 2 has no
content, so the offsets are 12, 44, 140, the class is unknown to the model, and the whole tree fell to the
fallback (32-bit swap). That is wrong for this structure: it is full of 16-bit fields and byte streams. In the
old output the header reads "1047 leaves, 777 nodes, scale 131" for a tree of 777 leaves, 1047 nodes, scale 16.

Fix: a kind 11 chunk whose class the model does not know takes the model's (single) scenery tree class of the
same file type and version. No model change is needed: the block roles inside the tree come out the same, since
a missing pointer is a zero word in the same column. Guessed words: arctic1 351,538 -> 10, arctic6 351,547 -> 10.

Proof that the new trees are right (`..\scripts\k11_check.py`, the same checks pass on arcade Tropical4 and Canyon4 and on demo-identical tropical2):

| | old arctic1 | v2 arctic1 | v2 arctic6 |
|---|---|---|---|
| header | 1047 leaves, 777 nodes, scale 131, 16 bit bytes | 777 leaves, 1047 nodes, scale 16, 131 bit bytes (= nodes / 8) | same |
| leaves found by walking the nodes | 576 | 777 | 777 |
| boxes with min <= max | 194 of 777 | 1047 of 1047 | 1047 of 1047 |
| children whose parent field points back | 0 of 782 | 1046 of 1046 | 1046 of 1046 |
| child box inside parent box | 131 | 1046 of 1046 | 1046 of 1046 |
| leaf PVS streams that decode to the node count | (meaningless) | 777 of 777 | 777 of 777 |
| mesh references that resolve to a mesh in the file | 212 | 232 of 232 | 232 of 232 |

### 3.3 Nothing else changes

`run_all_v2.py` converts all 24 PS3 tracks and compares the 168 output files byte for byte with
`F:\Jogos\_revo_ps3_converted`:

- mesh limit only: 167 identical, changed: `tropical1\tropical1_master_gfx_xdata.sbf`
- both fixes: 165 identical, changed: the same file plus `arctic1\arctic1_master_gfx_xdata.sbf` and
  `arctic6\arctic6_master_gfx_xdata.sbf`

Inside those three files (chunk by chunk): tropical1 has 1236 -> 1237 chunks, one added (mesh bf13e642), none
changed; arctic1 and arctic6 have the same 1066 chunks with exactly one changed each (the kind 11 tree).

### 3.4 C# port

`csharp\ps3conv.cs` = the app's file with the same two changes (see `ps3conv.cs.diff`, 5 hunks: a `Classes` set
filled while loading the model, `TreeClass()`, the kind 11 call site, limit 16 -> 64). ASCII, LF, C# 5.
`csharp\ps3model.txt` is byte-identical to the app's.

`test.ps1` compiles it with Add-Type as `extras.ps1` does, converts arctic1, arctic6, tropical1 and four control
tracks (tropical2, alpine1, canyon2, safari1); `compare.py` compares each output with the Python v2 output after
decompression (the two zlib encoders produce different compressed bytes; the content must be equal):
49 files compared, 0 different. The C# report for arctic1 / arctic6 now says 10 guessed words and no
"data of a kind the converter has not seen" note; tropical1 reports 0 failed meshes.

---------------------------------------------------------------------------------------------------

## 4. What needs a look in game (yes / no)

1. tropical2, PVS flag held at 1: does distant geometry still disappear when the camera turns? (expected: no)
2. tropical2: is one of the "missing textures" a single flat panel about 14 m wide and 2 m high (banner or
   hoarding), and the other small knee-high bushes repeated along the route? (expected: yes to both)
3. tropical2: do the frozen birds flap their wings on the spot, or are they completely still?
4. Arcade Tropical (original track): are birds seen flying there? (tells whether the arcade bird code works at all)
5. arctic1 or arctic6, old conversion: does the track load with scenery missing / flickering, or crash?
   With the v2 files: is the scenery complete? (expected: broken before, complete after)
6. tropical1 with the v2 file: does it load, and is there no new hole or stray object? (mesh bf13e642, 23 parts,
   is larger than any arcade mesh's 12)
7. Any Revo track: are smoke, waterfall spray or other particle effects that Revo shows missing? (finding 6)
8. Any Revo track: does the water or the terrain look more transparent / differently blended than on arcade
   tracks? (finding 7)

---------------------------------------------------------------------------------------------------

## 5. Update: the Revo fix pass exists (`classic/revofix/revofix.py`, `SR3CamLab\revofix.cs`)

The "proposed automatic fix (not implemented)" of section 1.1 was implemented as a post-pass over a converted (PC layout)
Revo track. Source: the docstrings of `revofix.py` / `revofix.cs`, `classic/revofix/test_results.txt` and
`validate_results.txt`, and the comment in `extras.ps1` (`Convert-Ps3Track`).

| Step | What it does | Default | Why that default |
|---|---|---|---|
| shaders | materials whose shader the arcade game lacks (`i_pl.fx`, `i_pl_psm.fx`) are rebuilt as copies of a genuine Uber material of the same track: same chunk id, the i_pl textures put in the Uber diffuse / normal / specular / light slots (gTexture0 diffuse, 1 normal map; `i_pl_psm`: 2 specular, 3 baked light on the second UV set) | ON | what uses those shaders ("finish banners, some bushes") would not be drawn |
| birds | hides the Thrush flocks by moving them 10 km below the ground | OFF | "the arcade engine treats them exactly as on its own Tropical track" (docstring; this bears on question 4 of section 4, LIKELY) |
| emitters | writes 2000.0 at +0x10C of Revo particle emitters (type 5a1bb4a6) | OFF | "the meaning of that field is not proven" |

- The settings app converts a PS3 track into a folder of its own and then runs the fix with shaders on, birds off,
  emitters off, before the track is installed.
- The list of effects in the arcade shader libraries used by the pass (`system\shaderlib3_data.sbf` + the Uber library and
  its alias) has 35 names, among them `3wayblend.fx`, `water.fx`, `grass.fx`, `horizon.fx`, `impostor.fx`,
  `smallinstances.fx`, `track.fx`, `trackmultiblend.fx`, `shadows_cast.fx`, the `sr_car_*` family, `graphicsdebug.fx`,
  `ubershadergame.fx`, `ubershadermax.fx`; `i_pl.fx` and `i_pl_psm.fx` are not in it. VERIFIED (data).
- Validation (static): on tropical2 the two affected materials change size (k2 3e7bf191 660 -> 1580 bytes, k2 97a9a06c
  856 -> 1296 bytes), no chunk is added or removed, "materials 679; with a shader the arcade lacks: 0 (before: 2);
  unparsed 0; Uber materials with a parameter list no genuine Uber material has: 0; dangling references: 0". arctic2 and
  safari2 have no such material and come out as unchanged copies. VERIFIED (measurement on files).
- C# against Python: 56 files of 8 tracks compared, 0 differences. VERIFIED.
- Counts from the test run with all three steps on, per track (materials rebuilt i_pl / i_pl_psm; flocks; emitters):
  tropical2 1 / 1; 20; 5. tropical3 1 / 1; 16; 3. arctic2 0 / 0; 0; 3. safari2 0 / 0; 8; 8. tropical1 1 / 4; 15; 8.
  canyon1 1 / 3; 0; 6. lakeside1 0 / 6; 0; 6. safari3 2 / 3; 18; 5. Some rebuilt materials use "an approximate donor".
- In-game result of the rebuilt materials: not recorded in the sources (UNKNOWN).
- Row 8 of section 2 (type names the arcade exe may not know): `classic/revofix/exe_types.txt` lists Revo's names
  (`Dumb_Temperate_Spectator`, `Generic_Path_Animator`, `Gen_Path_NF_Anim_With_Emitter`, `Generic_Breakable` ...) next to
  run-time object names. LIKELY the exe's own type table, in which case the exe knows them; the file does not say how it
  was made.
- Row 2 (PVS): the launcher now holds [0xA65794] = 1 while any added track is raced
  (21_track_install_and_switching.md).
- In game: converted arctic2 and safari2 load, drive, have grass, and the AI races normally; tropical2 / tropical3 and
  the PC demo's canyon2 load too (ps3-to-pc-conversion.md).
