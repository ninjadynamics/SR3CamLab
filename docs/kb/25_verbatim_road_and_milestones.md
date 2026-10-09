# 25 - The 1995 road kept verbatim, the game's road not drawn, and the milestone plan

Findings of 2026-10-08 (late evening) and 2026-10-09. Confidence tags as elsewhere: VERIFIED (and how), LIKELY, UNKNOWN.
"In game" = the owner drove the build on the cabinet. This file supersedes the road handling described in
[22_gapfill_zfighting_scenery_rules.md](22_gapfill_zfighting_scenery_rules.md) section 3 for the builds named RAW onwards.

## 1. What turned out to be wrong with every build before RAW

A fly-through of the light-map build, then of two stripped builds (BASECLEAN: no rounding, no baked light; RAW: none of
the importer's fill either), sorted the defects by cause:

| Defect seen in game | Believed cause before | Actual cause | How it was established |
|---|---|---|---|
| Orange slivers and patches at the roadside and on the tarmac | rounding; then "the SR3 road filling 1995 holes" | SEGA Rally 3's own road (TrackDeform) showing THROUGH the 1995 surface | still present in RAW; the owner noticed its texture is high-resolution (cannot be 1995); the 1995 model inspected in Blender is clean at those places |
| Holes where the road meets walls and rock, on straights | missing 1995 geometry | the 1995 road polygons had been cut out and re-laid on the SR3 road, breaking the corners they shared with the walls | Model 2 lap (221 frames) shows far fewer such holes; measured: the SR3 road agrees with the 1995 ground to 3 cm at the centre and 3 m out, but at 6 m out 29% of points are more than 20 cm apart, at 8 m 43% |
| Dark, patchy forest floor; grass in islands; texture jump on the sea cliffs | 1995 authoring / missing geometry | the importer's own fill rules (forest-floor darkening, verge cells, generated hillside) meeting with hard edges | data check round the village checkpoint: the dark ground, the grass patches and the hillside are all importer sections (`hf_terrain`, `verge`) |
| Dark bands beside the road in the light-map build | - | the bake was given the whole 32 m SR3 road strip as a solid surface (224,576 of 449,531 scene triangles), on top of the fill's own darkening | counted in the bake's scene file |
| Fish-scale pattern on the tarmac in the light-map build | - | each 1 m road piece had its own light-map rectangle, lit and compressed independently | LIKELY (read from the screenshots; not isolated) |

- Is 1995 geometry missing from the export? Measured along the lap: 97 of 300 centre-line cells have almost no ground 6 to 20 m
  beside the road in the visual export (the village stretch among them); the 1995 COLLISION model has ground in 49% of that space.
  The owner's reading after the Model 2 lap: the chase camera is low and the roadside wall hides that area, "70-30 it's authored like
  that on purpose". Both the forest and the hairpins were then inspected in Blender and found clean. Treated as authored that way
  (LIKELY). The export takes 60 consecutive ROM objects (1259..1318) of about 1,500; whether others sit near those stretches was
  not checked (UNKNOWN).
- The owner's rule from this: baked light must be the ONLY lighting, applied to a flat-lit base. Layering it on the importer's
  direction shading was a mistake.

## 2. The verbatim road (course setting `road_verbatim`)

- The 1995 road polygons are NOT removed and re-laid. They stay as scenery, corner to corner with the walls and rock they were
  modelled against (`build_classic.load_visual`: no `split_at_road`, nothing goes to `DROPPED`, no decals).
- SEGA Rally 3's road still carries the driving. Its height against the 1995 polygons is the course setting `road_under`:
  -0.02 while it was still drawn (RAW2), 0.0 once the launcher stops the game drawing it (RAW3 on).
  In game with 0.0: "the wheels now sit PERFECTLY on the road, no float, no sink".
- Weight: RAW (road re-laid in 1 m pieces) 505,953 vertices; RAW2 / RAW3 77,551. Re-laying the road was 85% of the track.
  SEGA's own tracks: 186,000 to 368,000.
- Every scenery material gets the static and dynamic shadow-receive switches (+0x52C, +0x540 = 1) so the cars' shadows have
  something to fall on. VERIFIED in game: an ordinary solid uber material receives the car's shadow.
- Surfaces (`surface_default`): Mountain is asphalt end to end, soil only beside the road in the forest (owner). With the old
  default, cells without a 1995 surface code became Desert's loose gravel: 63,257 of 112,288 cells, "the car slides". With
  `surface_default: "tarmac"`: 107,743 tarmac, 4,545 gravel (the 1995 code 6). The tarmac is `Terrain_Tarmac_Top` (5), the
  plain dry asphalt. Which of the four dry tarmac entries has the most grip is UNKNOWN: `surfacepair_data.sbf` holds only the
  name table; the grip numbers were not located.

### Things that do NOT hide the SR3 road
- Zeroing the alpha of its layer textures (`road_alpha0`): the road stays visible. On TrackDeform that channel is not opacity
  (VERIFIED in game, RAW2: orange gravel at the roadside, white wedges on the banked hairpin, grey streaks on the tarmac).
- Sinking it 2 cm: its flat-celled 1 m grid does not follow banked 1995 polygons and pokes through (RAW2, in game).

## 3. Stopping the game from drawing its road (launcher, in memory)

Found by following the road's effect, `TrackMultiBlend.fx` (name strings at 0x6A19C0 and 0x6A1B98; effect object at 0xACEAB0,
getter 0x4283A0), and the indexed-draw calls next to the object at 0xACEB98:

| Routine | What it is | Calling convention | Reached from | Patch |
|---|---|---|---|---|
| 0x4EEF70 | draws the road (TrackDeform object 0xA95570) | cdecl, 2 arguments, plain `ret`; first bytes `55 8B EC 83 E4 F0` | wrappers 0x4EF4C0 and 0x4EF500, called from 0x4F00D3, 0x5A3F4D, 0x5A42CB | first byte 0x55 -> 0xC3 |
| 0x4EE920 | draws road cells AROUND EACH CAR from the same road data (LIKELY the patch that carries ruts and tyre marks) | cdecl, plain `ret`; first bytes `83 EC 3C 8B 00 6B` | twice from 0x5E0330, with a car's position | first byte 0x83 -> 0xC3 |

- `patch.ps1` `Set-RoadHide`: a track folder with `road.txt` holding `hide` patches the first routine while that track is
  selected; `hide all` patches both. The original bytes are put back for every other track; nothing is written unless the
  six expected bytes are there. VERIFIED in game: with `hide` the road is gone and the driving is unchanged; with `hide all`
  the artefact described next is gone too.
- With only the first routine patched and the roads at the same height (RAW3): the car's shadow came out in bands and the road
  under and around the car flickered, almost clean when stopped and worse with speed; nearly right on the flat start square,
  bad on banked road. Cause: the per-car patch, drawn in the same place as the 1995 road. What was tried before finding it:

| Test | Change against RAW3 | Result in game |
|---|---|---|
| stock shadows | `shadow.txt` removed | no change: not the hard-shadow settings |
| A | road polygons cut in place to 1 m | no change: not polygon size |
| B | road materials given SEGA's shadow-receive recipe (alpha blend) | clean, but dust is drawn in the wrong order (blended materials are drawn later, over the patch) |
| C | that recipe without alpha blend | no change |
| D | light-map switch off on the road | no change |
| E, F | single-sided; specular map and reflection off | no improvement, the artefact only looks different |
| G | `hide all` | fixed |

- Cost accepted by the owner: no tyre marks or ruts ("I can live without road marks").
- Also checked and ruled out: the wall material's shadow variant exists (`T_Lpse_Tdnsl_Sds`), so the game was not falling
  back to a wrong technique; imported materials do not cast shadows (+0x51C = 0).
- UNKNOWN: whether skid marks could be kept; what else, if anything, the three callers of the wrapper 0x4EF500 draw.
- Seen in RAW and not explained: on the climb before the hairpins the spoiler's shadow on the car's own boot lid appears
  and disappears, at the same places every lap, without the car's lighting or its ground shadow changing. Working assumption
  (owner): the rock walls. Not investigated.

## 4. Other tools and settings added on 2026-10-09
- Importer settings: `road_verbatim`, `road_under`, `surface_default`, `road_cut`, `road_recipe` (`sega` / `opaque` / `nolm` /
  `oneside` / `nospec`; tests only), `lm_bake` + `lm_mode` / `lm_strength` / `lm_shade` (light maps in ONE build: the mesh writer
  runs once on a throw-away copy to note the polygons, then the bake, then the real run; 57 s against 87 s for two builds),
  `own_shader_tiles` (materials of those tiles select the unused technique `T_Lpse_Tdnl`, see 24_shaders.md).
- "RAW" as a recipe: `light_contrast=0` (flat), `fill`, `handfill`, `handmodel`, `roofs`, `seal`, `verge`, `lower_trees`, `unsmear`
  all false, `mirror_groups=[]`, plus the three road settings above. Left on: the overlap resolver (z-fighting gate), sea, sky,
  the 1995 gates, the spectators.
- The progress window assumed 330 s for a kind of build never made before; it now takes the last build's time.
- Launcher `Set-ShaderTest` (`shader.txt`: `untextured` / `untextured-own`): written, NOT yet run in game (24_shaders.md, first experiment).
- `SR3CamLab\mountain.blend`: the RAW2 import (1995 course and the game's road as two objects). Local only, not in the repository (it holds SEGA's geometry and textures).

## 5. Milestones for Mountain (owner, 2026-10-09)

Lighting is flat through every milestone; all lighting is left to RT.

| Milestone | Content | State |
|---|---|---|
| RAW | the 1995 course verbatim, drivable, the game's road not drawn | installed as the only Classic entry; "about to close" |
| PATCHED | every roadside hole under 2 m patched | next |
| BASE | authored geometry only: the forest patches, the mesa / plateau, the cliff side, the castle picture flipped correctly | |
| R4 | rounded polygons, nature only | |
| RT | ray-traced light from R4 | |

- "Full island infill is a waste of polygons": authored geometry only, and see whether that is enough.
- The code for rounding, fill, baked light and light maps is all still in the importer, switched off by the RAW settings.

## 6. Patching in Blender and the reproducibility check (2026-10-09)

- Workflow (owner): the RAW import is opened in Blender (`SR3CamLab\mountain.blend`, the build decoded back by `preview_obj.py`), holes are patched by hand in a copy, and the difference is taken "like a code diff". Only the patch is kept; the 1995 geometry is never copied into it.
- `patch.blend` = three objects in the course object's own frame (same matrix; the matrix is a pure axis swap, so stored numbers can be copied without arithmetic): `patch` (faces to add, with material and texture coordinates), `... as they were (before)` and `... (as edited)` (original faces some corners of which were moved; same face and corner order in both).
- First patch (owner, deliberate): 44 new faces in 15 places (cobbles, rock, dirt, grass; 240 m2), cut to 73 triangles; 31 vertices of one lawn (58 triangles at 16% of the lap) moved 2.2 m. Dropped from the diff: 48 quads with no area (two corners on each end: what extruding an edge without moving it leaves). A face of six vertices was a 1 m square with two corners doubled.
- Tools: `work\scripts\blendpatch\` (`bl_dump.py`, `blend_diff*.py`, `bl_make_patch.py`, `bl_apply_patch3.py`, `bl_fingerprint.py`, `fp_compare.py`, `repro1.py`).
- A mistake to avoid: `mesh.materials.clear()` resets every face's material index to 0. Set the indices AFTER rebuilding the slot list. (The first `patch.blend` gave 70 of 73 faces the wrong material; a check of positions and areas did not show it. Compare material and texture coordinates face by face.)
- REPRODUCIBILITY, VERIFIED 2026-10-09 against the control `mountain_patched_fixed.blend`:

| Stage | Compared with | Result |
|---|---|---|
| ROM archive `srallyc.zip` -> 34 chip files | the unpacked copy | identical |
| chips -> region images (`maincpu`, `main_data`, `polygons`, `textures`) | `work\tmp\m2\` | identical, byte for byte |
| images -> course export | `work\classic_tex\course1\` | `.mtl` and `materials.json` identical; `.obj` identical except its first comment line (an older exporter wrote "(Mountain)" there) |
| export -> build (RAW2 settings) -> decoded model | the model `mountain.blend` was made from | identical except the two lines that carry the build's name |
| decoded model -> Blender scene | `mountain.blend` | all 565 fingerprint items equal |
| scene + `patch.blend` | control | all 566 fingerprint items equal |

  A fingerprint item is a hash of stored data: vertex numbers (float32 bytes), face tables, corner-to-vertex table, edges, texture coordinates, material slots and indices, vertex groups, object matrix, material node set-up, packed image bytes.
- The `.blend` FILES are not byte-identical and cannot be: the same script run twice, saving the same scene to the same path, gives files of different length with 48% of the bytes different (Blender writes memory addresses into the file). File bytes are therefore not a test; the fingerprint is.
- Applying the patch inside the importer: section 7.

## 7. The patch as a file of the mod (2026-10-09)

The `.blend` files are the local workspace (`SR3CamLablender\`, never committed: they hold the whole course). What ships is a small JSON file per patch.

- **Name and order** (owner, 2026-10-09): `courses\<game>.<track>.patch.<number>.json` - `src.mountain.patch.1.json`, then `.2`, and so on. Patches are applied in the order of their numbers, each on the result of the one before. Course setting `patch`: `true` = every numbered file of the course, a number or a list = those.
- **Content**: `add` = faces to add, one a line: 1995 tile name, three corners, three texture coordinates. `move` = original triangles some corners of which move: the corners `before` and `after`. Plain coordinates in metres, in the space of the build decoded back by `preview_obj.py` (SR3 x - ox, y, -(SR3 z - oz)), written with the shortest decimals that give the stored 32-bit numbers back. `base.course_export_sha1` = fingerprint of the 1995 course export (comment lines aside) the patch was made on; it is the only fingerprint the importer reads, and a patch made on another export is refused. Mountain's patch 1: 73 faces, 58 triangles with moved corners, 28 kB.
- **What may be shipped** (owner, 2026-10-09): parts of SEGA's data such as coordinates are fine; a whole track, modified or not, is not. The `before` corners of a patch are such parts.
- **Tools** (`scripts\importerlendpatch\`): `bl_dump.py` + `patch_to_json.py` (patch.blend -> JSON), `bl_apply_json.py` (JSON onto a base scene in Blender; refuses a scene that is not the base), `check_build.py` (a decoded build against a Blender scene, face by face), `bl_build_to_blend.py` (a decoded build as a scene to inspect, patch faces in vertex group PATCH). Importer side: `coursepatch.py`.
- **Applying in the importer**: after the 1995 faces are loaded and before anything else works on them. An edited triangle is found as three corners (within 1.5 mm) of ONE polygon of the build, and only that polygon's corners move; a triangle that is not found stops the build. Added faces keep the corner order of the file (with the order reversed all 73 faces faced the other way - checked on a build).
- **Faces drawn without a mapping**: Blender gives a new face the texture coordinates of one corner three times. 32 of Mountain's 73 were like that. The build continues the tile from a neighbouring face of the same tile across the shared edge, at the neighbour's density, unfolded flat about that edge (all 32 found a neighbour); with none, the tile's usual density laid flat in the face's plane. `patch_uv: false` leaves them as drawn. Not yet judged in game.
- **Checks made**:

| Test | Result |
|---|---|
| JSON applied to the untouched `mountain.blend` in Blender, against control | all 566 fingerprint items equal |
| JSON applied to the control scene (already patched) | refused |
| build with the patch (RAW settings, 18 s) | z-fight gate 0 + 0, 0 consistency problems, 77,667 vertices |
| that build decoded, against control, face by face | 63,029 faces on both sides, every one found with the same tile and corners; none facing the other way; texture coordinates equal except on the 32 faces continued on purpose |

- A mistake of the checker worth knowing: 6 original triangles with two corners at the same place were first reported as different, because corners were paired by nearest place. Corners are now paired over all orderings.

## 8. Where things live since 2026-10-09

The importer, the ROM tools, the course files and this knowledge base moved into the launcher's repository (`SR3CamLab`): `scripts\importer\`, `scriptsom_tools\`, `courses\`, `docs\kb\`. The data they work on stays outside it, in `SR3 track format\work\` (`out`, `tmp`, `classic_tex`, `previews`, `retex`) and `SR3 track format\classic\`. Folder links (junctions) join the two in both directions, so every older path in these notes still works: `SR3 track format\work\scripts`, `...\work\courses`, `...\classic\scripts` and `...\kb` lead into the repository, and `SR3CamLab\scripts\{out,tmp,classic_tex,previews,retex,courses}` and `SR3CamLab\classic` lead out of it (those are git-ignored). The scripts find their data as `..\<folder>` from their own place, which is why the links exist on the repository side too: a shell that resolves links (Git Bash does on `cd`) runs them from there.
