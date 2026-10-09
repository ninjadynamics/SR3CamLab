# 14 - The classic course importer (seventh package)
Nothing here has been run in the game. Evidence is static (data, code reading, decode-back renders).

## One command
`python work/scripts/import_classic.py <game> <course> <variant> [--export] [--norender] [--nobuild]`
- game `src` (SEGA Rally Championship, Model 2A, ROM extracts in `work/tmp/m2`), course `1..4`,
  variant `classic` (1995 textures inside SR3 files) | `mixed` (SR3 surfaces, 1995 pictures) | `allsr3` (no 1995 texel).
- Stages: export OBJ + coloured tiles from ROM (`classic_export.py`, `classic_tex.py`) -> labels (`retex.py`: CSV written
  from an automatic guess, then the course JSON's `label_overrides`) -> road, walls, AI map, spline with splits and pace
  notes, start grid (`build_classic.py`, `pacenotes.py`) -> scenery (`build_classic.add_scenery` / `build_allsr3.py`) ->
  authored empty object list and no camera lists (JSON `props: minimal`; see 07, 03) -> `work/out/stepNN_<name>_<variant>_desert4/Desert4`
  -> decoded back (`preview_obj.py`) and rendered from nine cameras + 2560 px composites.
- `run_all_courses.py` runs every course and variant; `fly_all.py` makes the fly-through videos.
- Everything course-specific is in `work/courses/<game>_<course>.json` (`course.py` applies it): object table rows of
  the 60 hi-detail sections, half width, collision code -> surface, start grid table offset, ladder step numbers,
  label overrides (tile index -> class), tiled texture per class, and the all-SR3 art choices (rock set and tint, road
  layer pairs, tree row, single pieces for windows / doors / bushes / trees). The texel pages are found automatically
  per course (`classic_tex.fit_pages`) and cached in `work/classic_tex/course<N>/pages.json`.
- Collision and centre line are read from `classic/obj/src_course<N>_collision.obj` / `_centreline.csv` (written by the
  other session's `classic/scripts/m2_collision.py`); the importer does not regenerate those two files.

## The four courses (identified by eye from the coloured tiles and renders, and by the start table order)
| ROM course | Object rows | Identity | Evidence | Ladder steps (classic, mixed, allsr3) |
|---|---|---|---|---|
| 1 | 1259..1318 | Mountain | town, church, rock walls | 34, 35, 36 |
| 2 | 937..996 | Desert | "YEM BANK", "KAMO STORE", savannah trees, sand | 25, 26, 27 |
| 3 | 1379..1438 | Lake Side | boards reading LAKESIDE, autumn trees | 28, 29, 30 |
| 4 | 1135..1194 | Forest | conifers, wet tarmac, tunnel, "AM3 RALLY PROJECT" | 31, 32, 33 |
Road surface: the collision attribute code (bits 16..19) per cell; 0, 1, 8, 9 are taken as tarmac, 2, 3, 4, 6 as loose
(GUESS from where they occur: Mountain is 0/1 with 6 on the verge; Desert and Lake Side are 2/3; Forest is 0 and 9 with
2 on the gravel part).
Course 2's texel page for one sheet half was not found (8 tiles, shown black in the classic renders and treated as
untextured); course 4 has three tiles that decode to black as well.

## Start grid, direction, splits, pace notes
- Classic start positions: program ROM 0x3DB20, four records of 4 x (x, y, z) f32, in the order Desert, Forest, Mountain,
  Lake Side (each lies on cell 0 of that course's collision centre line: VERIFIED by coordinates). A fifth record
  repeats one point. `import_classic.classic_grid` projects the four cars on the imported centre line: start slice =
  3 slices ahead of the front car, the four cars become the first four (dist, col) grid entries, the pattern is
  repeated backwards for cars 5..8. Result: Mountain slice 5, Desert 8, Lake Side 19, Forest 5.
- Direction is +1 (increasing slice = the order of the collision cells, which is the classic driving order: the grid
  cars stand behind cell 0 facing it). LIKELY.
- Sector splits: NOT taken from the classic game (its checkpoint table was not found); two splits at thirds of the lap
  from the start slice.
- Pace notes (`pacenotes.py`): SR3 markers of type (3,2) carry one integer property "Direction". Across the 57 notes of
  Desert4, Alpine4, Canyon4, Lakeside4 and Tropical4 the codes that follow the geometry of the next 120 m are:
  3 / 4 / 9 = one turning sense, gentle-medium / tighter (about 46..58 deg, radius 25 m) / hairpin (51..92 deg, radius
  20 m); 5 / 6 / 14 = the other sense, same grades. LIKELY (small sample; which sense is "left" on screen was not
  established, the sign convention is the one measured in SR3's own data). Other codes (1, 7, 8, 10, 11, 13, 15, 22,
  26, 28, 39, 63, 71, 79, 90) do not follow the turn (cautions, crests, ...) and are not written.
  Authored: one note 60 m before each corner tighter than 90 m radius that turns at least 22 degrees
  (Mountain 13, Desert 7, Lake Side 17, Forest 14 notes). Types (0,4) and (0,2) are not written.
  `build_testtrack.build_spline` now writes the note markers; the property layout copies Lakeside4's.

## Polish of the all-SR3 look (package seven)
- Gap beside the road: FIXED. Cause: classic faces inside the road strip were dropped (or, later, lowered whole), which
  left a slit where they met the rock foot or a bank. Now they are cut into 2 m pieces; corners covered by the SR3 road
  go 20 cm down, corners outside it or rising above it stay (`build_classic.load_visual`).
- Storey height clamped to 7.5 m and bay width tied to the storey height (`build_allsr3.py`).
- Rock colour: each SR3 rock texture is pulled a fraction (`rock_tint`, Mountain 0.6) towards the mean colour of the
  course's classic rock tiles and stored as a new texture (`allsr3.tinted_texture`). The Uber colour parameter was not
  used.
- Rock direction: the projection axis of a rock face now comes from a normal smoothed over neighbouring faces
  (`smooth_axes`), so the texture no longer turns on every triangle. PARTLY: where the axis changes a seam is visible,
  and faces far from their axis are stretched.
- New classes for the other courses: plaster_wall (tinted SR3 plaster, sloping faces become roofs), window / door (an
  SR3 window or door stretched over the classic opening), brick_wall, sand, wood, bush.

## Pictures and videos (`work/previews/`)
`final_<course>_<variant>_<1..9>_<view>.png` (2560 px, 1995 left / SR3 right) for mountain, desert, lakeside, forest and
classic, mixed, allsr3; the single renders `blender_<course>_rom_*.png` and `blender_<course>_<variant>_*.png`;
`fly_<course>_allsr3.mp4` (20 s, 1280x720, one lap).

## Classic variant, state after the retexture lane was suspended
This supersedes the "Start grid, direction, splits, pace notes" section above where they differ.
Built: step34 Mountain, step25 Desert, step28 Lake Side, step31 Forest (`..._classic_desert4`), each 3 files.
Data used (other session's decode, `classic/courses/src/<course>/gameplay.json`, `classic/sr2_gameplay/src/`):
- start grid from program ROM 0x3DB20 (as before), direction +1 = increasing section; check: start heading matches.
- sector splits = the classic split sections (Mountain 6, Desert 4, Lake Side 5, Forest 5 - Forest's table repeats 158).
- pace notes = the game's own notes with their sound-test names, placed at the classic section: Easy.. -> code 3 (left)
  / 5 (right), Mid.. -> 4 / 6, K.. and ..Hairpin.. -> 9 / 14. Which SR3 code family is "left" was settled by a vote of
  the 1995 calls against the turn sign of the imported centre line (Mountain +17, Lake Side +14, Forest +9, Desert +8,
  all positive): left = 3 / 4 / 9. LIKELY. "OverJump" (Desert 2, Lake Side 2) has no known SR3 code and is not written;
  "Long", "VeryLong", "Caution", "Maybe" qualifiers are dropped.
- surface codes: 0, 1, 8, 9 tarmac; 2, 3, 4, 6 loose (6 is the verge). The road is SR3's own: Desert4 Safari tarmac /
  Safari gravel layers. The 1995 road texture and its painted lines are NOT in the classic variant (they are scenery
  polygons under the SR3 road).
NOT used: gates (variable width - the road is 14 m everywhere), AI line and braking zones (the AI map is built from the
road cells), time-extension checkpoints (where SR3 keeps checkpoint times was never decoded: only the split markers of
the spline and the sector fields at master_xdata root +0x74.. are known; the arcade's time bonus is probably in the
ArcadeDatabase, see game-runtime-and-frontend.md), water crossing, tunnel.
Skies / backdrop (`import_classic.backdrop`): the backdrop objects mix near scenery (lake, far houses, tree lines:
radius < 750 m) with a sky dome and ground plane 2..100 km away. SR3's scenery tree is a +-750 m square, so the faces
that fit inside +-740 m are added as ordinary classic scenery (Mountain 92, Desert 100, Lake Side 216, Forest 0) and
the far faces are left out (185 / 106 / 20 / 202); the Desert4 slot's own sky dome (master_gfx root +0x10) is kept.
The 1995 sky colours are therefore NOT in the tracks. Scaling the dome into the scenery square was rejected (it would
cut through the course); replacing the root +0x10 mesh needs its vertex format and material, which are not decoded.
Cut-outs: alpha-tested two-sided material (Mountain 29, Desert 69, Lake Side 47, Forest 9). Per-polygon brightness: not
recovered (full brightness). Animals / animated objects: not present.
Static checks: `python work/scripts/check_classic.py src <N>` reads the built files back:
| Course | drivable 1995 area inside the 14 m road | road height error (95%) | upright scenery inside the road | start heading | grid cars to 1995 slots |
|---|---|---|---|---|---|
| Mountain | 98% | 0.06 m | 193 quads | matches | < 1.6 m |
| Desert | 84% (16% is wider than 14 m) | 0.12 m | 46 | matches | < 1.5 m |
| Lake Side | 100% | 0.05 m | 535 (the 1995 road is narrower than 14 m: banks stand in the SR3 road) | matches | < 1.5 m |
| Forest | 100% | 0.07 m | 0 | matches | < 0.8 m |
Walls: the collision corridor follows the SR3 road edges at 7 m, not the classic barriers. Scenery standing inside the
road is drawn but has no collision.

---
# The importer after the in-game work on Mountain (2026-10-07 / 08)
This supersedes the sections above where they differ. Source: the docstrings and comments of `import_classic.py`,
`build_classic.py` and the modules they call, the course settings file `work/courses/src_1.json`, and the owner's notes.
Only Mountain (course 1, variant `classic`) follows all of this; the other courses and variants were last built earlier.

## Command
`python import_classic.py src 1 classic --norender --name <output folder under out\> --set key=<json> ...`
- `--name` and `--set` (repeatable) give a build its own output folder, its own work folder for composed tiles and its own
  settings, so several builds can run side by side (one process each).
- A build with its own `--name` reports how far it is in `work\tmp\progress_<name>.txt`, once a second: the percentage is
  the time gone over the time the last build with the same `round` / `light_contrast` took (`work\tmp\build_times.json`;
  330 s when there is none).
- Environment: `GAPFILL_DUMP=<file.pkl>` dumps the face list for the gap-fill tools; `SR3_FASTGEO=0`,
  `SR3_FASTGEO_CHECK=1`, `SR3_FASTLM=0`, `SR3_FASTLM_ORDERED=0` control the compiled paths (17, section 5).

## Coordinates
SR3 = (x_obj + ox, y, ZS x z_obj + oz) with `ZS = -1`, where the classic OBJ exports are (x, y, -gameZ): SR3 uses the
game's own axes. Mountain: ox 137.74, oz 52.84 (so SR3 x = OBJ x + 137.74, z = -OBJ z + 52.84). VERIFIED in game
(11_importer_prototype.md, corrections).

## Order of the build (`stage_build`)
(Simplified; taken from the order in which the comments of `stage_build` appear, not from a trace of a run.)
1. Road: centre line -> slices; per-vertex heights and per-cell surface from the collision mesh; VARIABLE width from the
   1995 drivable ground for the classic variant (04_trackdeform_road.md); layer pair from `road_layers`; walls; AI map
   along the 1995 AI line; spline with checkpoint markers (`checkpoints`) and the 1995 pace notes; start grid from ROM.
2. Scenery faces: the hi model (`load_visual`), the near backdrop (`backdrop`), the gates (`gates: "1995"` default, or
   `"gantries"`), the hand fill and hand models.
3. ONE overlap pass over course + backdrop (`overlays: "bake"` default, or `"lift"` = the old 2 / 4 cm offsets).
4. Picture mirroring for `mirror_groups` (16, section 4).
5. Fill: verge, hillside file, trees set down, trunk extension, sea sheet and its clipping, roofs, final seal; each
   followed by the z-fight gate (22).
6. Optional rounding of natural ground (`round`, 17 section 2).
7. Side detection (`lightside`, then `roadsight`), lighting by the normal (`light_contrast`), optional baked light or
   light maps (16).
8. Sky (`sky1995`; `sky: "slot"` keeps Desert4's), far horizon card removed, lighting sets (`lighting_from`), no fog.
9. Objects: `props: "slot"` keeps the slot's object and pobj files and grass cache; `"noobjects"` empties the object
   list; `"minimal"` is the unusable 3-file form (21). Then, unless `crowd: false`, the 1995 spectators as SR3's crowd and
   the start / finish gate object (15).
10. Camera lists removed (`cameras: "default"`); `texmap.json` written.

## Course settings in `work/courses/src_1.json` (Mountain) and their notes
| Key | Value for Mountain | Note |
|---|---|---|
| `objects` | 1259..1318 | hi-detail object rows |
| `start_grid` | rom maincpu, offset 0x3db80 | "4 cars x (x, y, z) f32; table order in ROM = Desert, Forest, Mountain, Lake Side" |
| `texel_block` | 0x600000 | - |
| `gameplay` | course1_mountain | folder of the gameplay decode |
| `props` | slot | "every track needs its pobj files + grass cache: without them the grass set-up (0x506FD0) never runs and the game dies at 0x5DE16C when a wheel touches the road (in-game runs 2026-10-07). 'minimal' is not usable." |
| `cameras` | default | - |
| `checkpoints` | classic | 03_master_xdata_route.md |
| `sea` | tile tex_sea_blue_64x64_c1DF, level -0.5, cell 40.0, colour 62 / 107 / 160, screen_colour 25 / 63 / 129, lod_bias 2.0 | 22, sections 5 and 6 |
| `road_tint` | tarmac 0.42 / 0.45 / 0.52, gravel 0.62 / 0.48 / 0.36 | 23, section 7 |
| `road_layers` | tarmac: Alpine4 5186a744 + 7e6973ab | "Alpine4's Terrain_Tarmac pair: clean tarmac (Desert4's own Safari tarmac throws dust clouds)" |
| `sky_drop`, `sky_repeat`, `sky_top` | 300.0, 8, 28.28 | 22, section 6 |
| `lighting_from` | Tropical4 | 16 |
| `scene_gain` | 0.8 / 0.8 / 0.8 | 16 |
| `light_dir` | -4.0, -6.0, 4.0 | 16 (conflict noted there) |
| `mirror_groups` | three castle tiles | "the castle (three boards, one folded screen) shows its picture mirrored as a whole, in place: it is painted lit from the left, the 1995 sun is to its right" |
| `round_exclude` | tex_s1_x0384_y0640_128x128 | "the village's roof tile (labelled 'dirt'): never rounded" |
| `surface_codes`, `art`, `steps`, `half_width`, `label_overrides` | as in the sections above | - |
More settings passed with `--set`: 17_mountain_build_notes.md, section 5.
Note: the file still holds `"start": {"slice": 10, "direction": 1}` from the prototype; the start slice actually used
comes from the ROM start table (`classic_grid`).

## Start grid, splits, notes: what changed
- Pace-note codes: the full code table of 03_master_xdata_route.md exists since package nine, and
  `pacenotes.code_for_name` maps a 1995 sound-test name to a code. The comments of `import_classic.classic_notes` still
  describe the earlier scheme too (severity from the call, the side by a vote against the centre line); which of the two
  the current Mountain build writes was not checked for this file (UNKNOWN here).
- Checkpoints carry time (03); the split-only mode remains as `checkpoints: "splits"`.
- The AI map follows the 1995 AI line (03).

## Crowd, gates
The 1995 spectators are placed as SR3's own animated crowd and the 1995 gates as scenery plus SR3's lap-aware banner
object: 15_spectators.md. Gate objects and their placement in the ROM: 18_src_1995_rom_data.md.

## Static checks
`check_classic.py` gained section 2b (coplanar overlapping quads, decal height above the SR3 road). The decode-back
preview (`preview_obj.py`) reads uv as signed and matches road cells by column number (variable width).

## Courses other than Mountain
Desert, Lake Side and Forest were rebuilt on 2026-10-07 (steps 25 / 28 / 31, 8 files, empty object list) but are not
installed and not tested; Desert's scenery reaches outside the +-750 m square. Their crowd tables are located but only
Mountain's is verified (15_spectators.md).
