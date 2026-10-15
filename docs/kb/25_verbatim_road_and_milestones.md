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
| R4 | rounded polygons, nature only | CHOSEN 2026-10-13: the owner drove R1, R2 and R4 with baked light (scene v11) and took R4 ("R4 is the way to go!!! make it the default step"). Every edge cut in four (16 pieces a polygon), corners moved along the surface's normal only (`round: 4`, `round_slide: false`), with the two rules added that day: the ground stays where spectators stand, and no piece turns over (round1995.py, rules 6 and 7) |
| RT | ray-traced light from R4 | installed 2026-10-13 as Classic 1 "Mountain RT" (R1 and R2 kept after it for comparison). The build route makes R4 unless told otherwise |
| R4 (pinned) | R4 without its horns | INSTALLED 2026-10-14 as the only Mountain entry, Classic "Mountain R4" (track1\Desert4 = `step99_mountain_r4nv11h_d_desert4`: scene v11, baked light, shadows 27 % = `light_split 0.72`); the owner had the other Mountain variants deleted from the game. See 5.1 |
| R4 (outward) | R4 rounded outwards, every seen side lit | ACCEPTED 2026-10-15 ("Mountain R4 is accepted, which means v11 is accepted too"): `step99_mountain_r4nv15_d_desert4` in track1\Desert4 (round_mode outward, open sides, the far-side light rectangles shared). See 5.2, 5.3 and 16_lighting 3.8. The v11 scene became patch 3 (5.3) |

### 5.1 R4's horns and lips, and the fix (2026-10-14)
The owner's screenshots of R4 RT showed horns standing up on rims and tops, an overhanging lip on a pillar's top and odd
raised blocks / pits. Measured on the rounding itself (a measuring copy of round1995.py dumped every piece before and after;
a corner "stands" when it did not move while a neighbour sank more than 0.25 m along its normal): 2 395 corners, 204 more
than 1 m. Why they stayed: rule 7 put a folding piece's corners back to where they began AFTER their neighbours had sunk
(62 %, 80 % of the over-1 m ones); open borders of the Blender patch (31 %, kept by design; only ~5 % of them have a partner
within 10 cm, so welding would not join them); the road apron / spectators (5 %); lids put back whole by rule 4 (2 %, the
lip: the walls under a lid shrink 0.3 - 0.5 m while the lid stays). Filled hollows (corners pushed out of a concave crease) are
NOT a defect: smoothing should fill them, and a plain "moved outward" measure counts them too.
Fix (round1995.py rule 8, course settings `round_pin` default true and `round_fade` default 0.25 with it): the corners that have
to stay are pinned and the stage's smoothing is run again from its start, so rule 1's reach fades the surface into them; the
fade is halved (0.25 m per metre from a kept corner). Standing corners 2 395 / 870 / 204 (> 0.25 / 0.5 / 1 m) -> 1 078 / 249 / 34;
mean move 0.166 -> 0.157 m. `round_pin false` + `round_fade 0.5` builds the old R4 byte for byte (checked). Left: tops may still
sink up to `CAP` 2.5 m, which leaves a pit with a step where a few corners are held (spectators); lowering the cap to about 1 m
was proposed, not done.

### 5.2 Rounding outwards (2026-10-14, `round_mode: outward`, the default from then on)
The owner's screenshots of the pinned R4 (SR3_20261014_2243xx) showed clefts between cliff blocks, notches in cliff tops and
an inward crease between two rock masses: "no concave shapes should be formed! always convex!!", then "I want shit to get
rounded outwards (or remain straight) unless something is clearly concave in low-poly". Measured on the pinned R4 (every edge
two pieces share, its bend before and after; `scratchpad\convex\hollow.py`): 2 605 edges in 538 places bent inward by more than
20 degrees and at least 15 more than the 1995 shape (587 by more than 45). Not the cause: separate blocks pulling apart - only
one place in the whole course has corners of two different blocks within 0.3 m that moved apart. The cause is the shrinking
itself: corners that must stay (verge, walls, open borders, spectators, pins) stand while the rim beside them sinks.
`round1995.round_outward` (rules O1 - O4 in the file) never moves a 1995 corner: each polygon becomes a curved patch through its
own corners (PN triangle; a four-corner polygon blended from its four edge curves), with each corner's normal the mean of the
polygons joining it smoothly; edges bent more than `round_crease` (45 degrees), edges of anything not rounded, open borders and
polygons wound against each other stay straight. Then no new hollow: an edge the game draws may bend inward only up to the
largest inward bend of the 1995 edges round its polygons (a 1995 hollow is rounded over several pieces, a fillet) plus
`round_tol` (2 degrees); beyond that the curving of its corners is halved, 16 times, then taken away. First try without the
fillet allowance: 55 994 such edges, almost all the gentle foot of a bulge beside a 1995 hollow, cut down to a mean move of 2.5
cm (nearly flat). With it: 5 248 to fix, 0 left; 124 000 of 228 000 corners curved, mean 5.9 cm, at most `round_cap` 1.5 m;
by the counter above 168 edges over 20 degrees (all fillets of 1995 inside corners) against 2 605. `round_mode: shrink` builds
the rule set before (pinned R4 with round_pin / round_fade as in 5.1).

### 5.3 Accepted: Mountain R4, and the v11 scene as patch 3 (2026-10-15)
Owner: "Mountain R4 is accepted, which means v11 is accepted too. Create patch 3 out of it and reapply the chain to reobtain an identical
version of v11." Until then the v11 builds took patches 1, 2 and 3 from `courses\` (3 = the GENERATED patch of 2026-10-12: the plateau
hand model and the cliff side, 3,641 faces), then the tree boards moved in the Blender scene v11 (`board_moves`, 1,139 corners, 792 cut-out
polygons moved whole) and the scene's own patch (`scene_diff` patch 4 against the patch 1 - 3 build, the tree moves taken out: 4d; 27,860
triangles removed, 34,385 faces added, 99 composed pictures) from a scratch folder. One ordinary patch file cannot hold that chain: a patch
removes before it adds, and 4d removes and cuts down faces the generated patch 3 adds, with the board moves in between. So
`courses\src.mountain.patch.3.json` is now a STAGED patch (`blendpatch\stage_patch.py`; `coursepatch.apply_file`): `{"stages": [the
generated patch 3, {"board_moves": [...]}, 4d]}`, needs 1 and 2, 12.8 MB, applied stage after stage exactly as the separate steps were
(`coursepatch.move_boards` is the importer's old board_moves block). The generated patch 3 of 2026-10-12 is its first stage and in git history.
Checked: the importer's polygons as the rounding gets them (`rtbake\chain_dump.sh`, old chain against new) are the same 58,156 polygons in the
same order, pickled byte for byte; then the whole R4 build (collect, bake, compose, 27 % shadows) from the course patches alone
(`NO_SCENE_PATCH=1 rtbake\fast_all.sh` / `build_variant.sh`, which now also read the repo's own raw_recipe, bake and compose scripts)
against the installed build `step99_mountain_r4nv15_d_desert4`: all 11 files the same byte for byte (VERIFIED 2026-10-15, build v16, 357 s).
The next Blender round on Mountain starts from this chain: its scene is diffed against a build of patches 1 - 3 (the p3 base build
`step99_mountain_p3_desert4` used for v11 is the OLD patch 3 and must be built again first), and becomes patch 4.

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

The importer, the ROM tools, the course files and this knowledge base moved into the launcher's repository (`SR3CamLab`): `scripts\importer\`, `scripts
om_tools\`, `courses\`, `docs\kb\`. The data they work on stays outside it, in `SR3 track format\work\` (`out`, `tmp`, `classic_tex`, `previews`, `retex`) and `SR3 track format\classic\`. Folder links (junctions) join the two in both directions, so every older path in these notes still works: `SR3 track format\work\scripts`, `...\work\courses`, `...\classic\scripts` and `...\kb` lead into the repository, and `SR3CamLab\scripts\{out,tmp,classic_tex,previews,retex,courses}` and `SR3CamLab\classic` lead out of it (those are git-ignored). The scripts find their data as `..\<folder>` from their own place, which is why the links exist on the repository side too: a shell that resolves links (Git Bash does on `cd`) runs them from there.

## 9. Patch 2: the roadside fill, generated (2026-10-09, awaiting the owner's verdict)

Owner: "patch 1 fixes bad authoring, patch 2 fixes bad design decisions, patch 3 complements and enhances the track". Patch 2 is made by a program (`scripts\importer\roadfill1995.py`, run with `--set patch=[1] --set patch_gen=2`) and shipped as `courses\src.mountain.patch.2.json` in the format of patch 1; it carries `"needs": [1]` and the importer refuses it without patch 1. A build does not run the generator.

- **What the course is missing, measured** (cuts across the road every metre): the first solid upright scenery stands 0.24 m (median) from the road's edge, 95 % within 4 m, and there is ground in front of it nearly everywhere (61 m of cut line missing on the whole course). What is missing lies BEHIND it: about 68 000 m2 within 20 m. In the forest the soil verge is 5 to 15 m wide and ends in the air; the forest wall (class `tree_wall`) stands on nothing 5 to 20 m further out. In the village inside the forest there is a 1 m kerb and then nothing up to the forest wall; the houses stand on nothing.
- **Four versions were thrown away** (the module's text lists them): a grid of cells under the holes in front of the first scenery (62 triangles: nothing is missing there); cuts that each closed their own gaps and started from the top of rock (upright sheets, shards, 19 "bridges" - owner: "huge fuck up"); a band per gap between two pieces of cover (every house cut the bands apart); "level" measured from the road's height (the verge is terraced: half the forest was skipped).
- **The rules that hold** (owner: "patch 2 always marches from the road, it's an horizontallity patch" ; "connected triangles, fans, make things sensibly authored" ; "it should look (both in-game AND wireframe) human hand authored"): the cuts only FIND the missing ground. From the end of the ground the road lies on (followed over its terraces; a bank or step of more than 1.5 m ends it) the march passes whatever stands within 20 m and ends at the next ground a slope of 0.35 reaches, or at the last thing standing. ONE band is laid from where it started to where it ended, UNDER the houses. Its two sides are the 1995 geometry's own corners; between them a ladder (rungs every 6 m, rails 6 m apart, the outer rows sewn to the true corners). Uprights are met at their foot, never at their top.
- **Not patch 2, and logged with coordinates instead**: the bridge (74 m, decoded scene (-416.9, 61.7, -126.2) to (-385.8, 58.9, -59.0): no verge, nothing at the edge but a 2 m parapet, on both sides); the cliff side (a band wider than 3 m is laid only along the forest stretch and only where it ends at the forest wall, has houses on it, or ends on the forest's own soil); ground under the band (the lower leg of a hairpin).
- **Things learnt on the way**: the village's roof tile is labelled 'dirt' (the course setting `round_exclude` names it; the generator takes that list as roofs). The verge's soil tile `tex_s1_x1280_y0256_256x256_c0D6` is painted black along its top 48 rows: repeated across a band it made stripes, so only the evenly lit rows are used and the picture runs back and forth over them. Between the soil verge and the forest wall the tile's dark copy (`_dk`, 0.32) is used, as in the accepted fill before; where houses stand on the band (15 m either way) the tile as it is. A triangle whose texture spans more than one repeat is cut up by the importer (`uv_split`: the first band version went from 2 026 to 34 000 vertices that way), hence cells of at most one repeat.
- **How it is checked before the owner sees it** (the second version went to the owner unseen - never again): `blendpatch\bl_views.py` renders stills of a scene from given places, textured / with the patch faces in magenta and their edges drawn / straight down; the generator writes the places (`ROADFILL_VIEWS`), and prints why the march ended at given slices (`ROADFILL_TRACE=<from>-<to>`).
- **Result as handed over**: 3 325 triangles, 37 982 m2, median 10.4 m2 (the 1995 polygons: 8.4), 20 bands; build with patches 1 + 2: 81 200 vertices, z-fight gate 0 + 0. Known blemishes: 47 triangles left out and 56 set 6 cm lower because something lies in their plane; small notches at two bend tips; the scan still finds 5 800 m of cut line open, nearly all of it cliff side.

### 9.1 Second round after the owner's inspection (2026-10-09)

The owner's verdict on the first hand-over: "good job, but there were still quite a few misses, especially under each building on main square", and four additions:

- **No floating trees** (R10): "the existence of a tree requires ground to be created underneath ... don't just create squares of ground under floating trees, otherwise we end up with floating ground ... connects both latitudinal and longitudinal". One shoulder from the roadside ground to 2 m beyond the trees, sloping through each tree's foot, running on from tree to tree where they stand less than 45 m apart on one side; narrowing towards its two ends; its outer edge smoothed along the road. Not behind something taller than 2.5 m (two trees linked across a tunnel had hung a shoulder outside the tunnel's wall).
- **No floating buildings** (R11): "the generated terrain underneath should be larger / bigger / wider than the building's footprint". One band per row, from the pavement's edge under the buildings to 2 m beyond their back and end walls. The main square had been missed because every band wider than 3 m outside the forest was classed as cliff side. Many town buildings on the left are a facade with nothing behind: there the ground goes 2 m behind the facade.
- **Forest floor dark again**: the first hand-over darkened only bands that ended exactly on a forest-wall board, about half of them. Now everything in the forest stretch is the dark copy except within 15 m of houses standing on the band.
- **The sea had holes**: the importer cut the sheet out under "land" and still counted the game's own road strip, which is not drawn. Not 1995 geometry, so not faces in the patch: patch 2 carries `"settings": {"sea": {"clip": false}}`, the importer merges a patch's settings into the build's (`coursepatch.apply(..., settings=)`). RAW is unchanged.
- **Misses and their causes**: (a) slivers where a verge begins or ends: the band's side went diagonally from one edge to the next; the corner of the step is now put in (R12). (b) spikes and a notch at the tip of bends: corners were ordered by metres along the tangent, which is wrong on the inside of a bend; they are ordered by the cut planes they lie between, and a band runs on over a break of up to 8 cuts. (c) holes inside bands: of the triangles left out "in the plane of another face", nearly all lay in the plane of ANOTHER TRIANGLE OF THE FILL, and both were removed; now one of the two is set lower (6, 12, 20 cm) and only then left out. Triangles are left out as too steep only beyond 60 degrees. (d) slivers in front of curved walls: a band that has no foot edge to follow ends 0.5 m behind what stands there.
- **As handed over**: 5 707 triangles, 55 156 m2, build 84 281 vertices, z-fight gate 0 + 0.
