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
  scripts are written as files. A TAB written this way into `sr3mods.ps1` stopped the track switcher for one test run.
- `arcade_times.bin` and `shadow.txt` are not written by the importer: they are copied into the step folder by hand
  before installing.
- A build with given settings takes the same time every run (used by the progress file).
- The terrain generator was checked to be deterministic (same hash on two runs); the full track build was not checked
  (SR3Lab plan, 2026-10-07).

## 7. Blender previews
`tools\import\core\preview_obj.py <step>` decodes a built track back to an OBJ (it reads the strips, so shared corners are fine). A Cycles flyover of the decoded track was rendered once; the settings that matched the user's Photoshop grade: sun 3 degrees wide, sky model at strength 0.03 (it is about 20 times brighter than a flat colour at 1.0), bounce from the un-darkened tiles through a light-path switch, Filmic high contrast, exposure +1.4.


## 2026-10-16: corrected tree assembly beside the edited cliff

Owner rejected the uniform v12 tree-piece translation: disconnected/misplaced faces remained. Replaced the complete damaged assembly at course X/Z (-34.2218,-425.738) with the intact nearby SRC tree assembly, keeping its target base height and width. 275 local polygons replaced by 84 triangles; all other 82,132 source polygons and the separate road object are identical. Original user v11 is preserved; working repaired copy is `blender/mountain.patch3.v13.treefixed.blend` (SHA256 3b582b6580db9001ccd16552f51f21c5fb430fbdfa379909ecf080be15f5eb69).

Full JSON regenerated from that copy, not a cliff-only patch. R4 build `mountain_v13_treefixed_20261016`, four workers, decoded game-file views checked front/back. Installed all 11 files by hash; only scenery graphics/texmap differ. No misplaced loose pieces or disconnected trunk in those previews; ordinary crossed-sprite seams remain. This is a whole-tree replacement, not a proven general exporter fix. Owner game confirmation pending. Audit, build logs, before files and renders: `SR3-investigation/mountain-v13-treefix`.

### 2026-10-16: HD tiles refreshed after v13 tree repair

Owner updated Mountain textures_hd PNGs. Ran existing core/texfast.py refresh on a staged copy of the installed standalone track1/Desert4: 103 changed HD tiles, 211 texture chunks rewritten in 5 seconds. Installed scenery SBF, finish/object SBF and texmap.json. Verified all nontexture chunks including geometry are identical, other eight installed files unchanged, and updated texture dimensions at most 2048. No light rebake. Audit, source hashes, pre-refresh backup, validated/installed manifests: SR3-investigation/mountain-hd-refresh-20261016. TEST-SRC-HD.ps1 now checks this manifest and passes --no-watchdog as requested; accepted handling candidate unchanged. Live visual confirmation pending.


### Owner confirmation, 2026-10-16
Owner confirms v13 tree repair and refreshed HD Mountain textures both work in game. Accepted geometry and texture baseline remains installed.


## Mountain v14 regeneration (2026-10-19)

Source: `work/blender/mountain.patch3.v14.blend`, SHA-256 `6d99f9ab00dc68ae97177d3cd387b91f3aa812cbfcdb8088b55dccf68ba5913b`. Regenerated the complete final patch stage against the retained accepted base, preserving earlier generated stages and board moves.

Canonical comparison: v13 has 82,221 triangles; v14 has 82,220. 82,189 match exactly. 32 old triangles are removed/changed and 31 new triangles replace them. The road object is unchanged. The JSON reconstructs every v14 float32 position/UV/material triangle exactly. This compares canonical geometry, not literal JSON versus Blender file bytes.

The applied chain contains all 31 changed v14 triangles exactly. Two further differences are explained: an unchanged surviving half of an edited quad, and an already degenerate source UV face whose importer fallback changes by at most 0.000265 when edits alter the density pool. No unexplained differences remain. R4 and game encoding intentionally transform this geometry afterward.

The source retains composed materials whose old overlay polygons no longer recreate their recipes. Patch stages now accept `texture_recipes`; `coursepatch.restore_texture_recipes` resolves missing dependencies recursively, rejects cycles/missing inputs and keeps composition metadata. All 132 saved recipes reconstruct from local SD pixels. The full import found nine otherwise missing named materials. Recipes embed no pixel data.

Isolated run: `scratchpad/mountain-v14-20261019`, patch chain, R4, collect, slow RT with two low-priority workers, composition at 0.34, build with light_split 0.72. Reports: `source-audit.json`, `chain-audit.json`, `recipe-check.json`. Final texture packing applies the 3x/4x set without changing non-texture chunks. Encoded light maps are extracted as PNGs with source chunk hashes into `lightmaps` before install. `install-report.json` records success, backup and hashes; live gameplay remains the owner's acceptance step.

Installation completed and launcher `-Check` passed on 2026-10-19. All 11 track files and 178 clean HD PNGs were verified against their staged hashes. Backup: `work/texture-backups/mountain-before-v14-3x-20261019-013644`. Twenty-two lightmaps extracted. Packed textures remain within 2048 per side and valid mip limits; the track has 544 distinct DDS payloads (previously 528), about 122 MiB more texture data. Live loading, visual appearance and performance remain untested. Source/KB changes are local, not committed or pushed in this round.


### 2026-10-19: loading regression, texture compatibility and track heap

The initial v14/3x pack entered an infinite loading loop. The first correction made every mip compatible with Rally's floor-based DXT block arithmetic and consolidated 145 byte-identical texture chunks, without reducing artwork resolution. That candidate still crashed because all seven SBFs unpacked to 279.52 MiB, exceeding the fixed 256 MiB track heap even though the main SBF alone was 254.88 MiB.

The guarded standalone runtime patch raises only the track arena to 384 MiB before heap creation. The owner confirmed that this corrected build loads and races. Preserve this fix with later geometry/lighting updates. The complete addresses, independent evidence, failed assumptions, memory accounting and compaction/refresh rules are maintained in [23_texture_pipeline.md](23_texture_pipeline.md#10-mountain-3x--facade-4x-preparation-and-recovery-2026-10-19), rather than duplicated here. The original staged reports remain historical snapshots.

### 2026-10-19: v14 broad-shadow regression — authored labels omitted

Owner confirmed that the 384 MiB track-heap repair loads and races successfully, then reported broad dark regions and mirrored LIBRAIRIE lettering. The isolated v14 workspace skipped ROM extraction and did not seed `src_1.tile_labels.csv`; its first import generated coarse automatic labels. This changed both R4 classification and the ray-only tree solids. Direct ray tracing identified two false canopies of radius 362.2 m and 389.2 m. They shadowed large parts of the course. The defective bake reported 624 trees/no lamps and 54% car-road shadow coverage; authored labels restore 588 trees/33 lamps and 36%, consistent with the retained v13 bake. Sun direction and composition settings were unchanged.

Fixes: `course.use` seeds a missing workspace label CSV from the course's saved file without replacing existing manual edits. Stack bake signatures include the effective label SHA-256, so a later label change requires a fresh collect/bake. RT rejects canopy radii above 50 m with a label-diagnostic error. A regression check reproduces and rejects the bad 362.2 m canopy. Label seeding, manual-edit preservation and signature invalidation were tested. Restored sign classification also exposed the old SD-only 4x gate magnifier multiplying existing HD pictures; this boost now stops once the authored sign already reaches 1024 pixels.

The three `tex_s1_x0512_y0640_128x128` facade variants have only their LIBRAIRIE lettering mirrored in the authored image (512px image region 180,328 to 350,350), preserving the facade layout and all other pixels. This compensates for the observed mirrored in-game UV mapping. Clean image originals are preserved in `scratchpad/mountain-v14-20261019/sign-fix`; the orientation preview checks both authored and in-game directions.

Corrected R4/slow-RT build and final install report: `scratchpad/mountain-v14-20261019/lighting-final/report.json`. Keep the power-of-two mip repair, exact-duplicate consolidation, 384 MiB runtime patch, watchdog OFF, accepted handling, and v14 source edits. Owner requested all logical cores minus one (31 workers on this machine) and High process priority for this rebuild.

Corrected build installed 2026-10-19 02:26. All 11 track files and 178 HD source PNGs verified; 22 lightmaps extracted; launcher -Check passed. Final seven SBFs occupy 287.12 MiB unpacked under the unchanged 384 MiB track heap. Exact duplicate consolidation removes 163 texture payloads. Visual inspection of compressed sign variants confirms readable LIBRAIRIE after mirrored mapping; controlled car-shadow comparison isolates the label defect (same geometry: 54% automatic labels, 36% authored labels). All 31 changed v14 triangles remain present before R4. Backup: `work/texture-backups/mountain-before-lighting-fix-20261019-022639`. Live visual acceptance remains pending.


### Owner decision: LIBRAIRIE retained

The owner confirmed the lettering correction works, then explicitly chose to keep it after clarification that only the lettering region was flipped. No whole-facade reflection or additional regeneration is requested. This confirms the sign decision, not visual acceptance of every area of the latest lighting bake. The reusable art workflow and current source/installation distinctions are in [35_faithful_texture_upscaling.md](35_faithful_texture_upscaling.md).


## 2026-10-19 — v15 patch 3, selected R4 B, RT installation

Owner approved `work/blender/mountain.patch3.v15.blend` as patch 3. Five plateau vertex heights repair the narrow steep strip that produced the long dark crease in v14. Original v14 is retained. Source v15 SHA256: `6259bbfb2df9b31cc48cd5da21038fc468ee54f31946938687ebd9534197c06e`.

Regenerated complete final patch stage; canonical float32 triangle positions, UVs and material identities reconstruct all 82,220 triangles exactly (7,548,036 bytes; both SHA256 `a71dd3aeb80c3f28307c32cc169e03425e9b9e50efc1db0320e7944a31fb4434`). This is source payload identity, not Blender-file or quantized-game-file identity. Actual chain comparison against v14 under identical authored labels: 56,728 polygons unchanged, exactly 23 removed and 23 replacement triangles; all 23 exact, no unexplained differences. Comparing against old auto-labelled audit inputs gives misleading differences: use matching authored labels.

Selected B is the existing outward R4 algorithm with `round=4`, `round_slide=false`, `round_crease=80`, `round_tol=2`, `round_cap=1.5`; area-weighted normals and normal gain 1. Source recipe and zipped patch chain updated. Rounded natural geometry: 313,614 polygons, maximum movement 1.5 m, zero new hollows left. Rebuilt RT with all 32 logical processors, High priority; 22 lightmaps, 588 tree solids and 33 lamp solids, 36% car-shadow texels. Actual stack: collect 61 s, RT 263 s, build 78 s. All-core availability does not make serial preparation steps saturate the CPU.

Restored the accepted 178 HD source images and composed coverage; retained POT/mip safety, exact duplicate texture consolidation (164 duplicates), and the existing 384 MiB heap fix. Installed seven SBFs total 287.57 MiB unpacked; 22 lightmaps extracted. Banner fix described below. Prior installed track and patch package backed up under `work/texture-backups/mountain-before-v15-r4b-20261019-093424`. Audit reports, build logs, lightmaps and install hashes: `work/research/mountain-v15-r4b-20261019/`. Installation hash checks pass; owner driving test pending. No handling or watchdog changes.

### Town-square lap banner in front of the posts

Raw gate OBJ already puts the banner 5 cm ahead of the ROM post boxes. The overlay resolver subsequently pushes textured post skins outward to avoid coplanar overlap. The installed old mesh therefore had skins about 12.78 cm ahead of the banner. Moving the raw geometry alone without checking resolved geometry misses this cause.

`gates1995.banner_in_front` now runs after overlay resolution, opted into by Mountain recipe `finish_banner_clearance=0.05`. It moves all banner panels/letter layers together along the gate-plane normal toward the approach, leaving post positions and all UVs unchanged. Both CHECK POINT and FINISH move about 17.78 cm; packed float32 mesh clearance is 0.0500023 m. Packed post vertices are byte-identical to the previous installation. The empty first-lap state stays empty. This is physical geometry placement with ordinary depth testing, not an always-on-top material.


## 2026-10-20 — v19 patch 3, backdrop removal, R4 B and full installation

Owner saved and triangulated `work/blender/mountain.patch3.v19.blend`, then requested the full chain, R4 B, RT, lightmaps and installation with all logical processors minus two. Source SHA256: `00f4354c1112ea90bbd511999024250927158125c3212b15db63ad1f741ab619`. The source contains 85,792 triangles; the separate SR3 road object remains byte-identical to the retained reference.

Patch 3's final stage was regenerated against the retained original stage base, preserving its generated stages, board moves and texture recipes. Explicitly replaying its additional removals and additions reconstructs all 85,792 canonical float32 triangle records (positions, winding, UVs and normalized material identities): 7,854,052 bytes, SHA256 `2423759fcf5d86dd0c3ae5d56259772e06d4f5567c1c8003b1b02cf07434ad86` on both sides. This is source-payload identity, not `.blend` container identity or identity of later quantized game files.

The real importer chain retains all 7,509 nondegenerate triangles changed since v15 exactly and none of the removed source triangles. One changed source triangle has two identical positions: the JSON retains it, while the importer deliberately discards this zero-area face. Other audit differences are verified unchanged backdrop polygons, deterministic UV-split pieces, surviving halves of old quads, and the existing density-based fallback for one unchanged unmapped face. These distinctions are recorded explicitly; the importer polygon list is not literally the Blender triangle array.

**Backdrop bug found before installation:** the importer split nearby backdrop into `sky` before applying patches to `faces` alone. Castle-island wall removals therefore could not reach the original `obj_1257` surfaces. The staged v19 build exposed 374 new near/coplanar overlaps beneath the remeshed walls. Patch JSON now has opt-in `include_backdrop: true`; the numbered importer pass applies that patch to course plus backdrop, then restores surviving backdrop sections. Other patches retain their former scope. This removed 17 original backdrop polygons and eliminated all 374 new overlap warnings. The two previously accepted near-overlap warnings at facade_024/facade_076 remain; this is not a claim of globally perfect geometry.

R4 B settings remain level4, outward, slide=false, crease80, tolerance2, cap1.5. Authored material labels were verified against the course CSV. RT again used 588 tree solids and 33 lamps, avoiding the former giant-canopy shadow regression. Full stack timing: collect96s, RT/compose248s, build59s, total403s; 22 lightmap pages and 73.84 million lit texels. Heavy workers were limited to 30 logical processors with two excluded by inherited affinity.

Accepted 178 HD sources, LIBRAIRIE lettering, POT/mip safeguards, exact duplicate consolidation and the existing 384MiB runtime arena were retained. POM staging now accepts `--track-dir` so a rebuilt SBF uses its matching staged texmap, instead of accidentally reading installed metadata. Stage-wide relief was reapplied to 409 materials / 182 texture mappings / 139 unique normal-height maps, including all 201 facade materials. Geometry, albedo and new lightmaps remain unchanged by POM staging. Final seven SBFs total 324.2804MiB unpacked. No runtime, handling, watchdog or relief-control changes.

Banner mesh bytes match the previous accepted front-of-post placement both before and after texture packing. `desert4_master_xdata.sbf`, `arcade_times.bin` and `road.txt` match the accepted installation byte for byte. All 22 encoded lightmaps were extracted and hashed. Installation checked every final track hash, repacked the patch ZIP and updated the accepted baseline. Launcher `-Check` passes, including a direct Windows PowerShell check through the normal PLAY script. Earlier checks from a Python subprocess could not load Get-FileHash and triggered automatic rollback; final verification succeeded with the available PowerShell runtime and independently with normal Windows PowerShell.

Backup: `work/texture-backups/mountain-before-v19-r4b-20261020-130330/`. Durable audits, scripts, logs, extracted lightmaps and final installation hashes: `work/research/mountain-v19-r4b-20261020/`. Installed and ready for owner driving test; no game was launched for this rebuild. Source/KB changes are local, not committed or pushed in this round.

## 2026-10-21 — v20 tunnel, tree and ivy repairs

The owner first confirmed the standalone runtime was smooth. That accepted state was committed and pushed as `f09758e` before visual edits. This build preserves `Rally.exe`, `dinput8.dll`, `sr3mods.dll`, the native shader library, and `mountain-pom-depth.yaml` byte-for-byte. The 0.6 global depth, +/- controls, 38 approved families and explicit green-rock variant exclusion remain. No game was launched.

Source is `work/blender/mountain.patch3.v20.blend` (SHA256 `2b6a65ebe82add758dfd698a1b046fc055f30e343ead02f9f56b0ca98b529bb0`). v19 remains intact. All 86,838 source triangles reconstruct as identical canonical float32 position/UV/material/winding payloads: 7,953,182 bytes, SHA256 `b2bc3ca5dbd9f86ca65c1f7cb843eef7ec0c9919576aaf320ef4e9cddc755edc`. This does not mean the Blender container or quantized game meshes are byte-identical. All 3,376 changed source triangles were verified in the full applied chain. The separate gameplay road is unchanged.

Screenshot camera coordinates came from the `SR3Lab` PNG metadata in `screenshots/SR3_20261020_223633.png` through `223910.png`; ray probes associated marked pixels with decoded installed triangles and UVs.

- Tunnel wedges were present in geometry before RT. A bounded exterior control-mesh fairing moved 1,011 vertices by at most about 1.0 m, holding 205 boundary/shared contacts fixed. The mapped exterior comprises 2,231 source triangles. Alternating reflected rock repeats, with triangles split at integer UV boundaries first, gives 3,253 triangles at the same texture feature scale. R4 B itself is unchanged (`crease=80`, `tol=2`, `cap=1.5`, four subdivision levels). A separate local fairing moved 17 vertices around the marked narrow rock ridge by at most about 1.5 m. These are intentional shape corrections, not zero-deviation remeshing or a new R4 algorithm.
- The old v13 tree repair was still intact in v19. Old baked slices survived the patch chain, causing cleanup to drop eight repaired trunk faces. Explicitly remove the verified legacy blade-plane assemblies before replacement additions (150 removal triangles, 117 legacy polygons across both locations). Both trees now retain 84 source/chain/post-cleanup faces, including all twelve trunk faces. The half-tree was replaced by a translated intact assembly at its existing base; the other tree retains the v13 repair. Carry these removals into later patch regeneration.
- Black/neon fragments on ivy cliffs were opaque RGB contamination in the c1A6/c1D6 `tex_s1_x1664_y0000_256x256_*_t.png` images, not missing alpha. Restored only the 11,366 contaminated/halo pixels per image from the corresponding SD content (about 1.927%). HD alpha and all other pixels are unchanged. Rebuilt all overlay recipes so composed cliff textures inherit the correction.
- Source topology cleanup removes 1,161 isolated vertices and joins 8,367 newly generated corners at exact positions. Original vertex identities are not globally welded. The surface payload remains byte-identical through this cleanup. Source-array decoding must respect the `('nd', dtype, shape, bytes)` serialization used by `bl_dump.py`.

R4B / RT / final encoding completed with 30 logical CPUs available (two reserved). Authored label hash is unchanged. There are 22 extracted lightmaps, 166 exactly duplicated textures consolidated, and 323.0734 MiB of unpacked SBF payload under the established 384 MiB track arena. Main-file texture/mip/reference checks pass. Gameplay data and checkpoint/finish object SBFs are byte-identical; two existing village facade overlap warnings remain outside scope. Native object-file validator findings are unchanged because those files remain byte-identical.

Native relief staging now accepts optional `--hd-dir` and `--review-export` for verified isolated track builds, retaining all source/track hash guards. The installed material count is 390 active and 16 variant-excluded (38 families); the old redundant tree composition no longer contributes its extra material. Pinned clean track, review track, source-hash manifest and native receipt were updated together so the relief-page Apply operation cannot restore v19 geometry. Approved height maps and gains were preserved.

Launcher `-Check` passes, including native YAML/exception checks. Offline diagnostic renders inspect decoded geometry, textures and RT maps; they approximate rendering and are not a play test. Do not interpret `gbUberDSIDE` alone as the SR3 raster culling rule in Blender: doing so produced false missing faces in a diagnostic view. Live visual acceptance is pending the owner's test.

Backup: `work/texture-backups/mountain-before-v20-20261021-000903`. Durable reports, reproducible repair scripts, logs and extracted maps: `work/research/mountain-v20-r4b-20261021/`. The three relevant repo skills were updated, validated and synchronized with their installed copies.


### Owner acceptance and relief-page check, 2026-10-21

The owner drove v20 and accepted the result ("it's awesome"). The staged-only relief-page test also passed: a temporary 0.01 facade gain change rebuilt materials while retaining installed geometry, all live files were unchanged, and the test setting was never installed. Evidence: `work/research/mountain-v20-r4b-20261021/relief-page-rebuild-check.json`.

The complete source extraction, exact canonical proof, actual patch-chain audit, R4/RT/HD/native-relief build and transactional install workflow is now maintained in [blender-track-patch-install](../../source/skills/blender-track-patch-install/SKILL.md), with version-specific mechanics in its linked reference. This supersedes any impression that the older one-off v20 paths form a generic installer. The owner requested that this accepted work and skill be committed/pushed before preparing a separate 48-degree sun alternative named Mountain R4 Low.


## 2026-10-21 — Mountain R4 Low, separate 48-degree sun alternative

Following owner acceptance, v20 and the new Blender-to-install skill were committed/pushed as `973489b` before the lighting variant began. The Low build reuses v20's patch package, 178 HD inputs, authored labels and unchanged R4B parameters. Only the sun elevation changes to 48 degrees at the accepted horizontal azimuth; light travel direction is `[0, -7.428475080718247, 6.688629005644433]`. Full recipe snapshot: `source/tools/import/src/tracks/courses/src_1.low.recipe.json`. Normal `src_1.recipe.json` and Mountain R4 are preserved.

Collect/RT/build ran on 30 logical processors (two reserved), High priority: 62s / 231s / 49s, 341s total. The isolated run initially lacked the crowd reader's local ROM cache; it stopped before RT and was corrected by seeding the verified extracted files. Authored labels yield 588 tree solids and 33 lamps. The lower sun raises the sampled car-road shadow coverage to 45%, consistent with longer shadows.

Both encoded lighting sets measure 48 degrees, and the collected RT sun is the opposite travel vector. The pre-R4 dump is byte-identical to accepted v20 (`f2fc51f6007be0915d8996fc597e9b333a2ef08aece01bd840dfb38d7550c94a`). All 575 checked shape chunks (kinds 1,5,7,11) retain exact positions, UVs, topology, groups and bounds. Expected sun-dependent fields change: normals in 570 scenery meshes, derived tangents in 509, and only normal fields in two LODs of object mesh `0x4ec27d47`. Gameplay data, road, object/banner placement and checkpoint timings match. 22 of 22 lightmap pages changed; 22 final encoded pages were extracted and hashed. Final native-relief seven-SBF footprint: 323.0734 MiB under the existing 384 MiB arena. DDS/mip and reference checks pass; unchanged native object validator findings remain inherited.

Installed as **Mountain R4 Low**, `track2/Desert4`, with Mountain's MTN video and music metadata. Existing Classic alternatives and other environment slots remain unchanged. The shader/runtime binaries, YAML, global depth 0.6, +/- controls, 38 families and sixteen excluded material instances remain intact. Main Mountain relief-page rebuild pins and receipt remain attached to track1; the Low variant is an independent snapshot of current family tuning, with its own receipt retained in the research folder. The main page does not automatically restage the Low family maps after a later family-gain edit.

Launcher `-Check` and installed-file hashes pass. No game launched; Low's in-game visual acceptance remains pending. Select Classic, then cycle View Change to **Mountain R4 Low**. Backup: `F:\Jogos\Ultimate Race Lab\work\texture-backups\before-mountain-r4-low-20261021-010250`. Evidence, scripts, logs, recipe and maps: `work/research/mountain-r4-low-20261021/`.


## 2026-10-21 — Mountain R4 Low updated to 45 degrees and dappled canopy shadows

Updated the existing `track2/Desert4` alternative; no new menu entry. New maintained recipe: 45-degree sun, perforated ray-only crowns, alpha grass receivers. Ground artwork, v20 patch chain, R4B shape, roads/gameplay, native shader library, smooth runtime, YAML family gains/exclusions, global 0.6 and +/- remain unchanged. Original Mountain R4 in track1 is byte-preserved.

Source-chain pre-R4 hash remains `f2fc51f6007be0915d8996fc597e9b333a2ef08aece01bd840dfb38d7550c94a`. All 575 encoded shape chunks were validated. Expected lighting differences include normals/tangents, 127 lightmap-UV meshes and 132 material-page references. The grass mesh requires 84 vertices rather than 61 to represent lightmap seams; its expanded indexed positions, UV0, winding/topology and bounds match exactly. Material albedo and alpha flags were checked across changed groups. Gameplay files remain byte-identical. All 22 freshly encoded lightmaps and 553 texture chunks passed DDS/mip/reference validation. Native audit retains 38 families, 390 active material instances and 16 exclusions. Seven-SBF unpacked size: 323.0773 MiB.

The two first bake startups stopped on a helper import path and a progress-print argument; both were corrected before the completed pass. The final slow bake completed in 184s and encoding in 71s. New receiver validation identifies exactly the 21 alpha grass faces and confirms the installed material uses a real page rather than white. The standalone actual-ray test confirms coherent sunlight through both canopy shell sides. Details and reusable guidance are in KB16 and the Blender-to-install skill.

Installation and launcher `-Check` pass without starting the game. Visual acceptance pending. Evidence/scripts/maps: `work/research/mountain-r4-low45-20261021/`. Verified rollback backup: `F:\Jogos\Ultimate Race Lab\work\texture-backups\before-mountain-r4-low45-20261021-015858`.


## 2026-10-21: accepted 45-degree build retained, redundant builds removed

The owner accepted the 45-degree sun, perforated canopy shadows and grass receivers in game, and asked to keep only this Mountain. **Mountain R4 Low** is now the sole Mountain alternative in `Main_release/track1/Desert4`; the previous high-sun R4 and duplicate track2/Desert4 were removed. Daytona and other stage alternatives remain. The retained final main SBF is byte-identical to the accepted Low: `fd6213b29d694a4d7bd1642936fa34d77e6cab8e17694f0ac7c20fc36ac0c0d9`.

Both main and low recipes now use the accepted 45-degree configuration. The main relief-page clean track/review pins, reviewed manifest and receipt were promoted together. A temporary family-gain change rebuilt all 390 active materials and 16 exclusions in staging; geometry, diffuse and lightmaps were preserved and live files were unchanged. That temporary tuning was never installed.

Owner-authorized cleanup removed 2,090 generated/cache/obsolete binary files, totaling 20,951,880,398 bytes (20.95 GB / 19.51 GiB). Protected hashes checked 6,083 retained files: Blender sources, canonical content and patches, reviewed height maps, current relief inputs, final extracted lightmaps and the relevant race trace. Old build directories keep their scripts/reports/images but no longer contain complete runnable cached stages. Historical backup entries in old receipts describe prior installations; use the current accepted pins and maintained source to rebuild. Manifest and reports: `work/research/checkpoint-cleanup-20261021/`.
