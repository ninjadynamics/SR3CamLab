# SRC Mountain: gap fill plan

*Plan only. Nothing was built, the game was not started, no source file was changed.*

The imported 1995 Mountain course shows holes that the 1995 game hid behind its low
camera, plus one flickering rock in the distance. This plan says which marks are our
pipeline's fault and which are original authoring, how to fix the first kind in the
importer, and how to fill the second kind in Blender so the additions survive a re-import.

Evidence tags: **MEASURED** = computed for this plan from the 1995 OBJ
(`classic\courses\src\course1_mountain\`) or read in the scripts; **SEEN** = judged by eye
from the screenshots; **ESTIMATE** = position inferred, not measured.

Coordinates are the game's (SR3): `x = obj x + 137.74`, `z = -obj z + 52.84`, y unchanged.
"Cell" is the index in `src_course1_centreline.csv` (300 cells, about 11.6 m each, cell 0 at
the start). Right and left are as driven.

---

## 0. The one fact that explains most of it

The 1995 course is a ribbon, not a landscape (MEASURED, plan drawn from the hi model):
the road, a low stone wall 5.5 to 8.6 m from the centre line and about 1 m high, and beside
it either a rock strip a few metres wide or nothing at all. On the sea side of the town
there is **no polygon** beyond the wall: no shore, no ground. Tree and lamp boards stand in
empty space with their feet at road height. The sea itself was a bowl kilometres away; our
importer replaces it with a flat sheet at y -0.5, about 15.5 m below the town road (y 15).

So the "bare water right behind the wall" is the original's emptiness seen from SR3's
higher camera, with our sea sheet showing through it.

---

## 1. Gap inventory

Screenshot positions are ESTIMATES from the scenery (within about 4 cells).

### 1.1 Yellow marks

| # | Shot(s) | Where | 1995 data there (MEASURED) | Emulator | Verdict | Confidence |
|---|---|---|---|---|---|---|
| Y1 | 091206, 091214, 091220, 091223, 091230 | Right (sea) side of the town, cells 14 to 62, 556 m. From (200, -430) to (326, 103) | Wall only. Beyond it: 849 cut-out boards (45 lamp, 276 trunk, 126 bare tree, 210 tree, 192 crown), 95 % within 16 m of the centre line, feet at road height (median 0.0 m), and 2 lying faces in the whole stretch | s068, s069: water behind the wall too; the low camera and the wall hide every tree foot | **Original authoring gap** | High |
| Y1b | same | The same strip: trunks as 15 m stilts into the water, lamp posts floating, a green verge strip that ends abruptly | Not 1995 data: these are `fill1995.extend_trunks` (floor = sea level - 0.5) and `fill1995.ground_skirts` verge cells | not there | **Our fill, a stop-gap that looks wrong** (not an extraction fault) | High |
| Y2 | 091220 (small mark ahead), 091245 | Both sides of the bend after the rock arch, cells 67 to 72, about (326, 160) to (300, 230) | 54 trunk boards right, 36 left, 7 to 15 m out, feet 0 to 1.6 m below the road. No ground: the rock arms of the arch end at cell 67 and start again at 72 | s070, s071: hidden by wall and camera | **Original authoring gap** | High |
| Y3 | 091240 (mark far left under the rock band) | Left of the castle straight, cells 44 to 54: the far edge of the grass field (x 239..308, z -89..10, y 15.0..15.6) | The field is 29 grass faces. West of it stands a cliff (obj_1268 / 1269, tile c0AE + ivy) from y -25 to +39, a little way off the field's edge; north of it a rock arm at y 15.6..19.7. Nothing joins field and cliff | s070: no water there; field meets rock | **Mixed.** The slit is original authoring. That it shows *water* is ours: the sea sheet in `import_classic.stage_build` covers the whole 1480 m square, inland too | Medium (the slit's exact width was read off a plan, not rendered) |

Checked and ruled out as extraction faults for Y1 to Y3:

- The polygon ROM has no data outside the object table (previous finding, VERIFIED there).
- The low-detail twins hold nothing extra here: the only 13 low polygons further than 5 m
  from the hi model are coarse copies of one rock (tile c0D9, around (140, 290)), not shore.
- The backdrop objects 1257 / 1258 hold the island, a second copy of one rock top (R2
  below) and the far sky / ground: no shore for the town.
- `load_visual` drops or lowers faces only inside the road strip; the strip beyond the wall
  is 5.5 m or more outside it.

### 1.2 Red marks

| # | Shot(s) | Where | Verdict | Confidence |
|---|---|---|---|---|
| R1 | 091220, 091223, 091240, 091245 | The flat-topped rock up-left: sections obj_1285, 1286, 1287, x 98..264, z 377..533, y 21..106. It stands 22 to 124 m from the road at cells 132 to 140 but is watched from the town, 290 to 470 m away (bearing and elevation from shots 091240 / 091245 fit: about 12 degrees up, 17 to 25 degrees left) | **Import fault**: `build_classic.far_scale` | High for the cause, medium-high that this is the marked rock |
| R2 | not marked; found by analysis | Top of the neighbouring rock, x 63..141, z 290..351, y 68..80 (sections obj_1279, 1284) | **Import fault**: `import_classic.backdrop` + `stage_build` | High |

Not marked, seen in passing (not analysed): dark blue upright bars on the horizon in
091206, 091214 and 091240 (sky dome painting or the edge of the sea sheet), and a
translucent green shape in 091223. Open question 6.

---

## 2. The red marks in detail

### R1: ivy overlay on the far rock

- **Faces** (MEASURED): the 1995 model draws ivy as a second, cut-out polygon on the *same
  corners* as the rock face. In obj_1285 there are 58 such pairs (rock c0AE + c1A6_t), in
  obj_1286 29 and in obj_1287 32 (c0AE + c1D6_t). Course-wide: 393 pairs in the hi model
  (248 c0AE + c1A6_t, 84 c101 + c1A6_t, 61 c0AE + c1D6_t) and 15 in the backdrop (island
  shelf c0DA + c0C2_t).
- **Why it flickers**: `dedupe_overlays` moves the overlay `OVERLAY_LIFT x far_scale` off
  its base, on both sides. `far_scale` grows with the distance from the face to the
  **nearest road point**, on the assumption that the camera is always near the road. This
  rock is near *a* road point (22 to 124 m, so the lift is 4 to 25 cm) but is looked at
  from the other side of the course. By the script's own rule (2 cm x (d / 50)^2) it needs
  0.7 m at 290 m and 1.8 m at 470 m. Ten times too little.
- The same flaw applies to `stack_layers` (1,562 coplanar overlapping polygons, 2 cm per
  layer times the same factor).
- **Fix: bake, do not offset.** For every same-corner pair of an opaque base and a cut-out
  overlay, drop the overlay polygon and give the base a composed tile (base texels with the
  overlay's opaque texels painted over). Base and overlay have identical UV spans in all
  393 pairs and identical UVs up to a whole-tile shift in at least 271 (MEASURED); the
  other 122 need their UV relation read (probably mirrored) and fall back to a per-face
  bake. Result: three new 256 x 256 tiles (c0AE+c1A6, c101+c1A6, c0AE+c1D6), 393 polygons
  fewer (786 with the back copies), no offset anywhere, nothing left to flicker.
- For `stack_layers` (different outlines, so no simple bake): clip the lower face by the
  upper one where the upper is opaque (remove what is hidden); where the upper is a
  cut-out, bake as above after cutting the base along the overlay's outline. Offsets stay
  only as a last resort, and then from the **largest distance at which the face can be
  seen from any road point**, not the nearest.

### R2: the rock top that exists twice

- **Faces** (MEASURED): 29 opaque faces of backdrop object 1257 (tile c0D9) have exactly
  the corners of 29 hi-model faces (tile c101) of obj_1279 / 1284, which also carry an ivy
  overlay. Three polygons in one plane.
- **Why**: `backdrop()` returns the near backdrop faces and `stage_build` runs
  `dedupe_overlays` and `stack_layers` on that list alone, then concatenates
  `faces + sky + extra`. Nothing compares backdrop against course. The build log agrees:
  for the backdrop it reports 15 overlays and 0 layers.
- **Fix**: run the duplicate / overlay / layer pass once over `faces + sky` together, and
  drop a backdrop face whose corners equal a course face's (the course face wins).

---

## 3. Importer fixes (before any modelling)

| # | Script, function | Change | Fixes |
|---|---|---|---|
| I1 | `build_classic.dedupe_overlays` | bake overlay into base (new composed tiles through `classic_tex`), drop the overlay polygon | R1, all 393 + 15 pairs |
| I2 | `import_classic.stage_build` | one overlay / layer pass over course + backdrop together; backdrop duplicates dropped | R2 |
| I3 | `build_classic.stack_layers`, `far_scale` | clip hidden parts instead of lifting; any remaining lift from the largest viewing distance | far flicker in general |
| I4 | `import_classic.stage_build`, sea block | keep sea quads only where the sea is: drop quads whose centre lies inside the outline of the course's land (hi model + hand fill, grown by a few metres), keep the rest | water inland (Y3) |
| I5 | `fill1995.extend_trunks` | run after the hand fill and stop at the first ground below (hand fill included); never extend to the sea floor when there is no ground | stilts (Y1b) |
| I6 | `fill1995.ground_skirts` | skip every cell that has hand-fill ground within 3 m of height (its existing "a lying face covers it" test does this once hand fill is in the list it is given); delete the `slopes` option | verge strips (Y1b), no near-coplanar pair with the new shelf |
| I7 | new `fill1995.handfill(cfg, rd)` | read `src_course1_handfill.obj` exactly like `props()` reads `src_course1_props.obj` | merge of section 4 |
| I8 | `fill1995.coplanar_report` | extend into a build gate: all faces against all faces, plus a near-coplanar test (parallel within 1 degree, closer than the gap needed at that face's largest viewing distance, overlapping in plan). The build fails when the count is not 0 | the zero z-fight rule |

Order in `stage_build`: course faces, backdrop, hand fill, then the joint overlay / layer
pass, then verge, then trunks, then sea, then the gate.

I1 to I3 change the frozen classic build on purpose. Check: decode back with
`preview_obj.py` and compare face counts and textures per section before and after.

---

## 4. Blender workflow for the true gaps

### 4.1 Getting the course into Blender

Coordinate convention: the hand-fill file lives in **classic OBJ coordinates**, the same
as `src_course1_hi.obj` and `src_course1_props.obj`. The importer already converts those.

1. Build the track with fixes I1 to I6, hand fill empty.
2. `python preview_obj.py step37_mountain_filled_desert4` decodes the built track to OBJ +
   PNG in classic OBJ axes. This is the reference: it is what the game gets.
3. `blender --background --python gapfill_scene.py` (new, modelled on `bl_render.py`)
   makes `work\blender\mountain_gapfill.blend` with three collections:
   - `REF_built`: the decoded build, locked, not selectable. Import as the existing
     scripts do: `wm.obj_import(forward_axis='NEGATIVE_Z', up_axis='Y')`.
   - `REF_1995`: `src_course1_hi.obj` + sky + props, locked. Its materials are the
     palette to model with (one material per 1995 tile, named as the tile).
   - `HANDFILL`: empty, the only editable collection.
   - Also: the centre line as a curve with cell numbers, an empty at each screenshot
     position, a camera per screenshot (SR3 chase height, about 2 m above the road, 4 m
     behind), and the sea plane at y -0.5 for reference.
4. With Blender open, the same script runs through the MCP bridge (port 9876); the
   background route is the one that must always work.

### 4.2 Modelling rules

- **Tiles**: only tiles that the same or the neighbouring section already uses. Seaside
  shelf: grass c1A6 (the field's tile). Slopes and rock: c101 (the tan rock of cells 50
  to 72). Under the town wall: wall tile c06A for a wall foot. No new textures.
- **Texel density**: match the neighbours. Measure the metres per repeat of the adjacent
  1995 faces (the script prints it per section) and use it; as a rule about 8 m per
  repeat for 256 px tiles.
- **UV limits**: at most 1.9 repeats across a face in u and in v, UVs in the 0..1 tile
  convention of the 1995 OBJ. Larger faces are cut. No mirrored UVs on tiles with
  lettering.
- **Shape**: quads or triangles, flat, convex. Low and plain like 1995: edges 5 to 12 m.
- **Budget**: about 700 faces for the whole course (work list below is about 520). The
  build has about 15,000 course faces and 5,667 fill faces today.
- **Where to stop**:
  - at the sea: carry slopes to y -1.5, one metre under the sheet, so the waterline is
    a clean intersection and never an edge;
  - at a wall: start 2 cm outside the wall's outer foot and 2 cm below its lowest vertex,
    sharing no plane with it;
  - at rock: end on the rock surface or run 0.3 m into it at an angle. Faces that cross
    at an angle do not flicker; faces that share a plane do;
  - at section borders with real 1995 ground: stop at its edge, share the edge, never
    overlap in plan.
- **No overlap, ever**: no hand-fill face may lie over or under another lying face within
  the gap rule of I8. No two-sided duplicates; single-sided faces, normals up or out.
- **Lamps and trees**: the shelf passes under their feet at their foot height (road
  height), so I5 has nothing left to extend.

### 4.3 Names and ids

- One Blender object per gap item, named `hf_<item>_<cell from>_<cell to>`, for example
  `hf_shore_014_062`. On export each becomes one OBJ `o` block; the importer uses the name
  as the face's section, so logs, checks and TexLab ids can name it (`hf_shore_014_062#0031`).
- Vertex and face order inside an object is kept by the exporter (sorted by position when
  written), so the file is stable under re-export and diffs stay small.

### 4.4 Export and merge

- `gapfill_export.py` (Blender, background or bridge) writes
  `classic\courses\src\course1_mountain\src_course1_handfill.obj` + `.mtl`: classic OBJ
  axes, `o` per object, `usemtl <1995 tile name>`, `v` / `vt` / `f v/vt`, fixed float
  format, sorted. It refuses to write when a check of 4.5 fails.
- Textures: none are exported; the materials name existing tiles. If a composed tile is
  ever needed it goes into `course1_mountain\handfill_textures\` and the importer's
  `EXTRA_TEX` lookup finds it.
- The importer reads it through `fill1995.handfill` (I7), only when the file exists and
  the course JSON says `"handfill": true`. The ROM export never writes this file, so a
  re-export or re-import cannot touch it. The `.blend` is the working file; the OBJ is
  the source of truth and goes under version control with the scripts.

### 4.5 Verification

1. **In Blender, before export** (script, prints a table per object): face count, non-flat
   or concave faces, UV span per face, texel density against neighbours, overlap in plan
   with `REF_1995` and with other hand-fill faces, coplanar and near-coplanar pairs.
2. **At build**: the gate I8. Zero pairs or no track.
3. **Renders**: `--background` renders from the seven screenshot cameras, before and
   after, side by side with the annotated shots (`work\previews\gapfill_<n>.png`).
4. **Decode back**: `preview_obj.py` on the new build, same cameras, to prove the built
   files hold what Blender showed.
5. **In game**: the user drives the same stretch and takes the same seven shots. Short
   numbered steps will be given at that point.

---

## 5. Work list for Mountain

Ordered by how visible the gap is. Face counts are rough.

| # | Item | Location | Geometry | Tiles | Faces | How |
|---|---|---|---|---|---|---|
| 1 | Importer fixes I1 to I6, I8 | whole course | none | 3 composed tiles | minus about 800 | code |
| 2 | Seaside shore | right, cells 14 to 62, 556 m | Shelf at road height from the wall's outer foot to 18 m from the centre line (carries all lamps and 95 % of the trees), then a bank down to y -1.5 at about 40 m (15.5 m drop, about 35 degrees), in two rows | shelf: grass c1A6; bank: rock c101 | about 290 | generated, then touched up by hand |
| 3 | Bend after the arch | both sides, cells 67 to 72, about 60 m each | Shelf under the trees (7 to 15 m out) joined to the rock arms at both ends, bank to the sea on the right, to the cliff foot on the left | c101, c1A6 | about 80 | by hand on a generated start |
| 4 | Field edge | left, cells 44 to 54 | Apron from the field's west and north edges to the cliff face and the rock arm, at field height, ending on the rock | grass c1A6, a rock c0AE strip at the cliff foot | about 30 | by hand |
| 5 | Outliers of the seaside | the few trees further out than 18 m, and feet lower than the shelf | Local widening of the shelf or a small mound | as item 2 | about 20 | by hand |
| 6 | Island | castle island | Keep `island_cap`; look at it from the seven cameras and replace it by a modelled top only if it looks flat | island tiles | 0 to 60 | decide after item 2 |
| 7 | Rest of the lap | open stretches with boards over nothing (MEASURED with a crude test: no ground beyond 25 m, nothing opaque rising 3 m, boards beyond the ground): right 85 to 92, 104 to 126, 143 to 150, 160 to 173, 194 to 198, 218 to 287; left 56 to 61, 160 to 176, 194 to 198, 219 to 287 | Shelf + bank as item 2, but falling into the valley, to 14 m below the road or the sea, whichever comes first | rock c101 / c0AE, grass | about 500 more | generated; only after the user has looked at those stretches |

### What to generate instead of modelling

The shore (items 2, 3, 7) is one rule applied along the road, so a script should draw it
first: `gapfill_generate.py`, run in Blender.

- Take the wall's outer foot as **one polyline** per side and stretch, offset it sideways
  for each row (shelf edge, mid-bank, bank foot) and connect neighbours. Shared vertices
  make it one continuous surface. This is what the old `slopes` option lacked: it built
  each slice by itself and got separate ramps.
- On the inside of bends clamp the offset to the local radius so rows cannot cross.
- Stop a run where 1995 ground or rock already exists (the same test that marks the open
  stretches), and where another part of the course comes within 10 m.
- The output lands in `HANDFILL` as ordinary objects. It is generated **once**, then
  edited by hand and exported. The build never regenerates it, so builds are deterministic
  and hand edits are safe. Re-running the generator is a deliberate act on one object.

### What `fill1995.py` stops doing once hand fill exists

| Function | After |
|---|---|
| `ground_skirts` verge | off wherever hand fill covers; in practice off for the seaside. `slopes` removed |
| `extend_trunks` | only down to real ground or hand fill, a metre or two at most; no stilts |
| `island_cap` | stays, unless item 6 replaces it |
| `props` (banners) | stays |
| `coplanar_report` | becomes the build gate I8 |

---

## 6. Risks and open questions

### Risks

| Risk | Mitigation |
|---|---|
| The marked rock is a neighbour of obj_1285..1287, not that one | The fix is course-wide (all 408 pairs), so it holds either way |
| Baking changes the look of ivy edges (cut-out edge becomes texels on rock) | Compare decode-back renders of two rocks before and after; the 1995 picture is the same texels |
| 122 pairs with a UV relation not yet read | Per-face bake fallback; count reported in the build log |
| Clipping the sea sheet opens a view under the world somewhere | Sea outline grown outwards by a few metres; check from the seven cameras and a top view |
| The new shore looks too clean or too modern next to 1995 art | Same tiles, same density, coarse faces; the user sees renders before the in-game pass |
| The 35 degree bank reads as a ramp into the sea | Alternative profile in open question 1 |
| Spectators stand on the wall and beyond it (a separate system) | Their positions are not touched here; the shelf gives those beyond the wall something to stand on |
| I1 to I3 alter the build that loads today | One change at a time, decode-back comparison, in-game pass after the lot |

### Open questions

1. **Shore profile.** Grass shelf then a rock bank into the sea (planned), or a sea wall:
   the stone wall carried straight down to the water with a narrow quay? The second is
   fewer faces and very "harbour town"; the first matches the island's look.
2. **How far to go.** Only what you marked (items 1 to 5, about 420 faces), or the whole
   lap now (item 7)? I would wait for your marks on the rest of the lap.
3. **Baking the ivy.** Accepted as the cure for the far flicker? It removes the overlay
   polygons for good.
4. **Sea inland.** Should the valleys inside the course stay empty (as in 1995), get the
   sea (as now), or get ground in item 7?
5. **Who models.** Generated shore reviewed by you in renders, or do you want to open the
   `.blend` and shape it yourself with the bridge?
6. **The blue bars on the horizon** and the translucent green shape in 091223: are these
   known, or should they be looked at next?
7. **Trees with feet below the shelf** (down to 16 m under the road in a few places):
   raise nothing and let the shelf dip to them, or leave those few on short trunks?
