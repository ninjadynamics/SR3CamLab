# 17 - Mountain (SEGA Rally Championship course 1) in SR3: build notes, limits, tools

Findings of 2026-10-07 / 08 from importing the Mountain course into the Classic slot (Desert4) and driving it on the cabinet.
"In game" = the user drove it. Lighting has its own file: [16_lighting_shadows_lightmaps.md](16_lighting_shadows_lightmaps.md).

## 1. How much geometry SR3 was built for (VERIFIED by counting the scenery file of each track)

| Track | Vertices | Vertex + index data |
|---|---|---|
| Desert4 (SEGA) | 185,779 | 9.9 MB |
| Stadium4 (SEGA) | 224,426 | 13.6 MB |
| Canyon4 (SEGA) | 282,738 | 14.6 MB |
| Tropical4 (SEGA) | 307,548 | 16.7 MB |
| Alpine4 (SEGA) | 355,174 | 19.0 MB |
| Lakeside4 (SEGA) | 367,755 | 19.9 MB |
| Mountain, no rounding | 730,020 | 37.2 MB |
| Mountain, rounded R8 | 1,824,660 | 93.0 MB |

- In game: 1.82 million vertices run fine. 5.18 million (R16) stayed in the loading loop for more than two minutes and was abandoned. The ceiling is between the two (not narrowed further).
- Why the import is heavy: every polygon was written with four corners of its own. `build_classic.share_corners` now merges vertices of a mesh that agree in everything (37% fewer on the scenery it applies to at R2; more at higher rounding). The tangent had to be made a function of the normal first: it followed each polygon's first edge, so no two polygons agreed.
- The road is the bulk: 430,164 of 649,695 vertices are the 1995 tarmac laid over the road in one-metre pieces. LIKELY inflated by a bug: `split_faces(..., 1.0)` makes pieces whose side is 1.0000000000000002 and `drape(..., maxlen=1.0)` halves them again (239,092 pieces became 336,981 in a unit test; not counted in a build).
- Classic alternatives must stay below 10 (the slot folders are single digits).

## 2. Rounding the natural ground (`round1995.py`, course setting `round`: 2, 4, 8 ...)
One level cuts every polygon in four; smoothing then moves free corners towards the mean of their neighbours. Passes are 2 x 8^(level - 1) so each step is also rounder (R2 0.50 m mean move, R4 0.69, R8 1.02 before the limits below).

What goes wrong with a strong rounding, all seen in game on R8:
| Symptom | Cause | Rule that fixes it |
|---|---|---|
| Village roofs bent into saddles | "natural" was decided by the tile's colour class; the roof tile `tex_s1_x0384_y0640_128x128` is labelled `dirt` | `round_exclude` names tiles never rounded |
| Spikes, stretched slabs beside the road | a kept corner next to a far-moved one | REACH: at most 2.5 m, and at most half the distance from the nearest kept corner |
| Ground through the tarmac and the verge | a moved layer crossing a fixed one | ORDER: a corner stays on the side of the road / fills it started on |
| Holes along the tarmac at rock and walls | rounded ground shrinks and sinks | APRON: corners within 0.75 m of road height on the road strip do not move (4,769 at R4). Not yet confirmed in game |
| Wasted polygons | flat patches cut finer | FLAT: a polygon whose pieces stay within 2 cm is written whole (few qualify: 109 of 4,375 at R8) |

- Above level 3 the smoothing is done on the level-3 mesh and further levels only cut finer.
- The user settled on R4.
- Sealing wall feet again after the rounding closed 3 places and cost 3 minutes: off by default (`seal_after_round`).
- A fuller "cut only as fine as the curvature needs" was measured, not built: 23% / 31% / 45% fewer pieces at 2 / 5 / 10 cm tolerance.

## 3. The 1995 gates (ROM objects 783 - 792; see also 15_spectators.md and 07)
- No START banner exists on Mountain. In the 1995 game there is nothing at the line at the start; after a lap a CHECK POINT gate (20 m banner, object 790); on the last lap the same gate reads FINISH (object 792). (User, Model 2.)
- In SR3 this is the `Start_Finish_Line` object: one mesh `0x4ec27d47` in game_objects with three "LODs" that are STATES (0 start, 1 race on and car more than 300 m away, 2 final lap within 300 m; code 0x61CAF0 / 0x632BE5, object +0x1B8). `finishgate.py` rewrites it.
- The banner hangs IN FRONT of the posts and reaches their outer edges (it had been fitted between them). The posts carry a blue section at 3.73 .. 4.69 m, just under the banner (4.6 .. 5.8 m): that is the 1995 model, the banner height matches the Model 2 screenshot.
- Why the lettering looked bad in game: the importer paints the letters (256 x 64) over the blue panel (64 x 32) into one picture, and sized that picture from the PANEL. `overlay_bake._recipe` now sizes it from the finer of the two tiles.
- Gate pictures are written 4 x larger, texel for texel (sharper under filtering; DXT blocks hold one colour).

## 4. Re-authored textures
- Originals for reference: `classic\courses\src\course1_mountain\textures\` (179 PNG). Do not edit those.
- Put a PNG of the same name into `...\course1_mountain\textures_hd\`; it replaces the tile when it DIFFERS from the original (so untouched copies may sit there). Any power-of-two size; alpha below 128 = see-through.
- The lookup is `build_classic.hd_tile`, used by `tile_pixels` (gates, composed tiles) and by `add_scenery` (course tiles). Not covered: the road's tarmac pieces, and tiles the gap fills read through `fill1995`.
- FAST LANE: `UPDATE_TEXTURES.bat` (`texfast.py`). Every build writes `texmap.json` beside its files (texture id -> tile, how it was made, recipes of composed tiles); the tool rewrites only the textures of installed tracks whose PNG changed. All 332 textures of a track: 4.7 s. The game must be closed. Composed pictures come out about 1% of bytes different from the build's (cause not found).

## 5. Build pipeline and speed
A build is `python import_classic.py src 1 classic --norender --name <step> --set key=json ...`.

| | Plain build | Baked / light-map build |
|---|---|---|
| Morning of 2026-10-08 | 604 s | 832 s |
| After `rays.c`, plain-arithmetic helpers, array vertex builder | 172 s | 248 s |
| After `fastgeo.c`, `fastside.py`, `fastbuild.py`, `fastround.py` | 55 s | not re-timed |

- `rays.c`: BVH ray caster, OpenMP, about 20 million rays a second on the Mountain scene; replaces Blender for side detection (18.5 s -> 0.4 s) and for the bake (25 s -> 3.7 s per-vertex).
- `SR3_FASTGEO=0` switches the compiled / array paths off; `SR3_FASTGEO_CHECK=1` runs both and counts differences. Verified 2026-10-08: all 9 output files byte-identical with the switch on and off (plain build).
- The pattern that made it slow: Python loops over 100,000 polygons calling numpy on three numbers (`np.cross`, `np.linalg.norm`: 100 microseconds a polygon, 1.2 million times a build).
- Heredocs in this shell mangle backslashes: patch scripts are written as files.

### Course settings added on 2026-10-08 (all via `--set` or the course JSON)
`round`, `round_passes`, `round_exclude`, `seal_after_round`, `light_contrast`, `light_dir`, `lighting_from`, `scene_gain`, `roadsight`, `mirror_groups`, `gates_unlit`, `finish_gate`, `bake_refine`, `bake_collect`, `bake_table`, `bake_mode`, `bake_strength`, `bake_shade`, `lm_collect`, `lm_table`, `lm_test`, `bump_tiles`, `bump_classes`, `bump_strength`, `bump_flip_green`, `bump_true`, `bump_gain`.

## 6. Things that look like bugs, not fixed (2026-10-08)
- The road pieces cut twice (section 1).
- The second `seal` pass finds 1,086 open samples and carries down 0 walls.
- `round(x, 2)` gives 2.67 for a Python float 2.675 and 2.68 for a numpy float64: the same point can get two corner keys in `lightside` and `overlay_bake._key`.
- `build_classic.Near` beyond 512 m takes the nearest point in its search window, not necessarily the nearest.
- Spectators facing away from the road: cause UNKNOWN (the "three looks" theory was disproved in game).
- Trees read about twice as bright as in the Model 2 control.

## 6b. Additions from the scripts' comments and the owner's notes (performance, numerics, working rules)

### Performance findings in game
- 1.82 million scenery vertices run; 5.18 million do not finish loading (section 1). No frame-rate figure is recorded
  anywhere in the sources (UNKNOWN).
- Five to six 2048 x 2048 DXT1 light-map pages load and draw (16, section 2).
- Imported Mountain had 730,000 vertices against 186,000 .. 368,000 for SEGA's six tracks, and 1.8 million rounded 8 times
  (counted 2026-10-08), because every polygon was written with four corners of its own.
- Largest mesh in early builds: 20,720 vertices (step20); limit 65,535 per mesh group.
- A separate memory finding: each cached menu video costs about 140 MB of the 32-bit game's address space on a
  32-thread CPU, which ends in "Out of memory for VB" unless the process is limited to a few cores
  (20_launcher_inmemory_patches.md, section 8).

### Where build time went (profile of 2026-10-08)
| Hot spot | Cost before | After |
|---|---|---|
| `np.cross` / `np.linalg.norm` on three numbers in `overlay_bake._newell` | 100 microseconds a polygon, 1.2 million times a build = 140 s | plain arithmetic |
| `gapfill_weld._closest` through numpy | 2.5 million calls x 35 microseconds = 90 s | plain numbers; then `fastgeo.LyingC` |
| `fill1995.Index` | 4 s to build for a whole course, ten times a build; 170 microseconds a look-up | `fastgeo.IndexC` |
| `gapfill_weld.Lying` | 8 s to build (a least-squares plane per polygon), 80 microseconds a look-up | `fastgeo.LyingC` |
| Side detection through Blender (`bl_sides.py`) | 150 .. 200 s for 440,000 polygons (28 million calls into `ray_cast`) | `rays.c`: about 2 s |
| `lightside.orient` loops | 20 .. 50 s | `fastside.py`: 5 s |
| `roadsight.orient` | 20 s | `fastlm.c`: 2 s |
| `lightmap1995.bake` | 85 s (numpy) | `fastlm.c`: 10 s |
| `meshgen.make_verts` setting every field of every vertex in a Python loop | "a million and more times a build" | arrays |
| `fill1995.road_faces` asked for eleven times a build | 0.25 s each | made once per road |
- Earlier, a build took about 7 minutes (gap-fill generation 3 + import 4), which the owner named as the main frustration
  of 2026-10-07.

### Numerical rules the compiled ports had to obey to stay byte-identical (VERIFIED by comparison, 2026-10-08)
- Compile with `-ffp-contract=off` (no fused multiply-add) and never with `-ffast-math`; sums run in the order the Python
  code or numpy adds them.
- Python's `x ** 0.5` is the C runtime's `pow(x, 0.5)`, which is not `sqrt(x)` to the last bit (2 in 1000 differ); the
  ports look up `pow` in `ucrtbase.dll`, the runtime `python.exe` uses. `x ** 2` is not `x * x` to the last bit either.
- `np.linalg.norm` of three numbers goes through BLAS, which adds them as (x*x + z*z) + y*y for a freshly made array
  (measured with numpy 1.24.3: 60,000 of 60,000 equal to the last bit, against 53,000 for x*x + y*y + z*z). 30 % of the
  dot products of two 3-vectors change in the last bit with the memory alignment.
- `(n, 3) @ sun` goes through BLAS `dgemv`, whose order of adding depends on the length of the array and on the row
  ((x + z) + y up to about 2000 rows, mixed above). It is the same number whenever one component of the sun is exactly 0.
- Python rounds a float to the nearest decimal exactly; numpy rounds x * 100. The two differ only when x * 100 lands on a
  half (this is the `round(x, 2)` item of section 6).
- `rays.c`'s traversal stack holds 96 nodes: a tree deeper than 93 levels would silently lose triangles, so the faster
  walks are only used on shallower trees. The faster walks rest on one assumption (a triangle is never computed more
  than 1e-6 x (1 + distance) nearer than the ray's entry into a box that holds it) and hand doubtful rays to the
  reference walk.
- One DLL file per version of the source (`fastgeo.<hash>.dll`): a running build keeps its DLL loaded and Windows will
  not replace it.

### Working rules recorded with the builds
- Shell heredocs in the working environment mangle backslashes (`\t`, `\0` became real control characters): patch
  scripts are written as files. A TAB written this way into `patch.ps1` stopped the track switcher for one test run.
- `arcade_times.bin` and `shadow.txt` are not written by the importer: they are copied into the step folder by hand
  before installing.
- A build with given settings takes the same time every run (used by the progress file).
- The terrain generator was checked to be deterministic (same hash on two runs); the full track build was not checked
  (SR3Lab plan, 2026-10-07).

## 7. Blender previews
`work\scripts\preview_obj.py <step>` decodes a built track back to an OBJ (it reads the strips, so shared corners are fine). A Cycles flyover of the decoded track was rendered once; the settings that matched the user's Photoshop grade: sun 3 degrees wide, sky model at strength 0.03 (it is about 20 times brighter than a flat colour at 1.0), bounce from the un-darkened tiles through a light-path switch, Filmic high contrast, exposure +1.4.
