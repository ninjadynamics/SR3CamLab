# SEGA Rally 3 (arcade, Rally.exe 3.8.4.1) - track format knowledge base

Goal: be able to AUTHOR a track, not only convert one, and to record every finding about the three games involved
(SEGA Rally Championship 1995, SEGA Rally 2 1998, SEGA Rally 3 2008 and its Revo relatives) so a wiki can be built from it.

How things are known. Files 01-15 began as static analysis (cross-file comparison of the 6 arcade tracks, byte-identical
re-builders, disassembly of Rally.exe) at a time when nothing had been run in the game; several of them still say so in
their opening lines. Since 2026-10-06 / 07 authored and imported tracks have been driven on the arcade cabinet, and the
later sections and files 16-23 record what that showed. Where a static conclusion was overturned in game, the file says
so and keeps the old conclusion as "disproved".
Confidence tags: VERIFIED (and how: static analysis, a byte-identical rebuild, a measurement on files, or "in game" =
the owner drove it on the cabinet and reported it), LIKELY, UNKNOWN. Some files written by other sessions use their own
equivalent tags (CONFIRMED / STATIC / OFFLINE, GUESS, DOCS); each says so at its top.

Start here by game: see "Entry points per game" below. Project terms (SBF, kind 11, drape, apron, build names such as R8
or L75 ...) are defined in [GLOSSARY.md](GLOSSARY.md). Everything still unknown or unconfirmed is collected in
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

## Index

| File | Topic |
|---|---|
| [01_container.md](01_container.md) | SBF container, chunk kinds, alignment rules, writer |
| [02_track_files.md](02_track_files.md) | The 7 files of a track, what each holds, which are mandatory |
| [03_master_xdata_route.md](03_master_xdata_route.md) | Gameplay root, start grid, sectors, AI map, spline + pace notes, cameras |
| [04_trackdeform_road.md](04_trackdeform_road.md) | The road surface (TrackDeform): geometry, surfaces, textures, height blob, lap logic |
| [05_scene_kind11.md](05_scene_kind11.md) | Scenery quadtree (kind 11), PVS streams, light map, meshes |
| [06_boundary_collision.md](06_boundary_collision.md) | TrackBoundary wall BSP (the only static collision besides the road) |
| [07_glue_and_other_files.md](07_glue_and_other_files.md) | Kind 12 typed objects, master_gfx root, object files, textures |
| [08_exe_loading.md](08_exe_loading.md) | How Rally.exe loads a track: addresses of loaders/parsers |
| [09_authoring_status.md](09_authoring_status.md) | What is authored vs borrowed in the test loop, open questions, next steps |
| [10_surfaces.md](10_surfaces.md) | Physics surface per texture id: the 90 terrain entries, importer table (id pairs per surface, per track), wall materials |
| [11_importer_prototype.md](11_importer_prototype.md) | SEGA Rally Championship course 1 centre line -> road; what the road format can and cannot express |
| [12_classic_textures.md](12_classic_textures.md) | SEGA Rally Championship texels from ROM, the texture-pointer fix, course identification (course 1 = Mountain), handedness, colours (palette, luma, exact colour table by executing the game code) |
| [14_importer.md](14_importer.md) | The importer command, per-course JSON, the four SEGA Rally Championship courses, start grid, pace notes |
| [15_spectators.md](15_spectators.md) | How SR3 stores its animated crowd (object record, model sets), the 1995 crowd table in the program ROM, `crowd.py` |
| [16_lighting_shadows_lightmaps.md](16_lighting_shadows_lightmaps.md) | SR3 lighting sets, material switches, dynamic shadows, what SEGA bakes, what a light map does (tested in game), baked light and real light maps for an imported course, relief from normal maps, the 1995 sun |
| [25_verbatim_road_and_milestones.md](25_verbatim_road_and_milestones.md) | What was really wrong with the builds before RAW, the 1995 road kept verbatim, the two routines that draw the game's road and the launcher patch that skips them, the shadow tests A to G, surfaces, and the milestone plan RAW / PATCHED / BASE / R4 / RT |
| [24_shaders.md](24_shaders.md) | Where the shaders live (compiled bytecode in the shader libraries), how the uber material's switches select one of 1229 precompiled techniques, the wall shader's inputs, and whether a pixel shader can be replaced at run time (parallax feasibility) |
| [17_mountain_build_notes.md](17_mountain_build_notes.md) | Vertex counts SR3 was built for and what it tolerates, rounding rules and their failure modes, the 1995 gates, re-authored textures and the fast lane, build pipeline speed, open bugs |
| [13_retexture.md](13_retexture.md) | Classic tiles classified by content and replaced by SR3 textures (step20, mixed); the all-SR3 version (step24); label CSV |
| [13_revo_vs_arcade.md](13_revo_vs_arcade.md) | SEGA Rally Revo tracks in the arcade engine: missing shaders, frozen birds, PVS, converter loose ends, the Revo fix pass |
| [18_src_1995_rom_data.md](18_src_1995_rom_data.md) | SEGA Rally Championship gameplay tables (course ids, sections, AI line, start grid, split and time checkpoints, pace notes and voice ids, surface codes), gate and banner objects, the trackside table, how a 1995 course is built |
| [19_sega_rally_2.md](19_sega_rally_2.md) | SEGA Rally 2: course identity, sections and surfaces, start / laps, checkpoints and time, pace notes, rival line, sky and banners, and the SR2 -> SR3 import |
| [20_launcher_inmemory_patches.md](20_launcher_inmemory_patches.md) | Why Rally.exe is patched in memory, every patch site and address (camera, camera cycle, PVS, video memory, menu timers, checkpoint times, shadow parameters), the camera system, driving the game from a script |
| [21_track_install_and_switching.md](21_track_install_and_switching.md) | Slots, replace and alternative mode, `track<k>` folders and the limit of nine, switch.json / classic.json, what a track folder must contain, side files, updating textures of an installed track |
| [22_gapfill_zfighting_scenery_rules.md](22_gapfill_zfighting_scenery_rules.md) | Z-fighting rules and the overlap resolver, the 1995 road on the SR3 road, the gap fill (every rule with its reason), trees, roofs, welds, sea, the sky dome in game |
| [23_texture_pipeline.md](23_texture_pipeline.md) | From a 1995 tile to an SR3 texture and material: brightness, encoding, signed uv, clamp, gates, re-authored tiles, the fast lane |
| [GLOSSARY.md](GLOSSARY.md) | The project's own terms and build names |
| [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | Every UNKNOWN and unconfirmed LIKELY, grouped by game, with the test that would settle it where known |
| work/out/README.txt | The ladder of built test tracks and what each one tests |
| work/previews/ | Pictures: classic course, SR3 road/walls/scenery decoded back from the built files (list below) |
| work/scripts/ | Python tools (reader/writer, parsers, builders, x86 helper, build_testtrack.py) |

Related files written by other sessions (same folder):
[game-runtime-and-frontend.md](game-runtime-and-frontend.md) (exe addresses, menus, track list in memory, card videos),
[audio.md](audio.md) (stream bank, announcer, ambience/music naming),
[ps3-to-pc-conversion.md](ps3-to-pc-conversion.md) (converter rules per chunk kind, bugs found),
[classic-sources.md](classic-sources.md) (SEGA Rally Championship / SEGA Rally 2 extraction results).

Material outside the top-level files that the files above summarise: `classic/courses/src/gameplay.md` and
`classic/sr2_gameplay/gameplay.md` (ROM gameplay decodes), `classic/sr2_sr3_import/README.md` (SR2 import),
`classic/revofix/` (Revo fix pass and its test results), `..\SR3CamLab\FINDINGS.md` (camera and run-time notes),
`..\SR3CamLab\docs\` (plans: SR3Lab, TexLab, Mountain gap fill).

## Entry points per game

### SEGA Rally Championship (1995, Model 2A) - "SRC"
| Looking for | File |
|---|---|
| ROM regions, object table, polygon format, collision blocks, music and speech samples, "is scenery missing?" | [classic-sources.md](classic-sources.md) |
| Texels, texture pointer pairing, pages per course, handedness, palette, luma, exact colour table | [12_classic_textures.md](12_classic_textures.md) |
| Course ids, section tables, AI line, start grid, split and time checkpoints, pace notes, voice ids, surface codes, gate objects 783-792, banners 171 / 172, trackside table kinds, how the course data is built (layers, front / back pairs, tree blades, sky picture) | [18_src_1995_rom_data.md](18_src_1995_rom_data.md) |
| The crowd table and the spectator sprites | [15_spectators.md](15_spectators.md), section 3 |
| The light vector and the sun's height; the castle painted lit from the left | [16_lighting_shadows_lightmaps.md](16_lighting_shadows_lightmaps.md), section 4 |
| What the 1995 gates look like and do at the line | [18_src_1995_rom_data.md](18_src_1995_rom_data.md) section 9, [17_mountain_build_notes.md](17_mountain_build_notes.md) section 3 |
| Importing a course into SR3 | [14_importer.md](14_importer.md), [11_importer_prototype.md](11_importer_prototype.md), [17_mountain_build_notes.md](17_mountain_build_notes.md), [22_gapfill_zfighting_scenery_rules.md](22_gapfill_zfighting_scenery_rules.md), [23_texture_pipeline.md](23_texture_pipeline.md) |

### SEGA Rally 2 (1998, Model 3) - "SR2"
| Looking for | File |
|---|---|
| ROM regions, polygon format, block records, exports | [classic-sources.md](classic-sources.md) |
| Course identity (stage / course id / round), sections and collision polygons, surface types, start, laps, checkpoints and time, pace notes, the 0xE2C0C lines, rival line, sky and banners | [19_sega_rally_2.md](19_sega_rally_2.md) |
| Audio extraction: sample ROMs, sound driver tables, voice clips, MPEG music, tune table | [classic-sources.md](classic-sources.md), sections "SEGA Rally 2 audio" and "Music of the classic games" |
| SR2 co-driver and music inside SR3 (sample rate found by ear, bank rebuild sets) | [audio.md](audio.md) |
| SR2 courses built as SR3 tracks (static only) | [19_sega_rally_2.md](19_sega_rally_2.md), section 10 |

### SEGA Rally 3 (2008 arcade) and SEGA Rally Revo (PC, PS3) - "SR3"
| Looking for | File |
|---|---|
| File formats of a track | 01 container, 02 files, 03 gameplay root / AI map / spline / pace notes / checkpoints, 04 road, 05 scenery tree and PVS, 06 wall collision, 07 glue objects / meshes / materials / sky dome, 10 surfaces |
| How the exe loads a track; addresses | [08_exe_loading.md](08_exe_loading.md), [game-runtime-and-frontend.md](game-runtime-and-frontend.md), [20_launcher_inmemory_patches.md](20_launcher_inmemory_patches.md) |
| What was proven in game, crashes and their causes | [09_authoring_status.md](09_authoring_status.md) (last section), [17_mountain_build_notes.md](17_mountain_build_notes.md) |
| Spectators, the lap-driven start / finish gate object | [15_spectators.md](15_spectators.md) |
| Lighting sets, material switches, dynamic shadows, light maps, normal maps | [16_lighting_shadows_lightmaps.md](16_lighting_shadows_lightmaps.md), [07_glue_and_other_files.md](07_glue_and_other_files.md) |
| Cameras, menus, videos, memory crash, in-memory patches | [20_launcher_inmemory_patches.md](20_launcher_inmemory_patches.md), [game-runtime-and-frontend.md](game-runtime-and-frontend.md) |
| Installing and switching tracks | [21_track_install_and_switching.md](21_track_install_and_switching.md) |
| Audio (stream bank, announcer, ambience, music, co-driver) | [audio.md](audio.md) |
| Revo: PS3 -> PC conversion; what the arcade engine does differently | [ps3-to-pc-conversion.md](ps3-to-pc-conversion.md), [13_revo_vs_arcade.md](13_revo_vs_arcade.md) |
| Performance: vertex budgets, what loads, build speed | [17_mountain_build_notes.md](17_mountain_build_notes.md) sections 1 and 5 |

## Status table

| Structure | Understanding | Builder | Proof |
|---|---|---|---|
| SBF container | VERIFIED | sbfw.py | 36/36 files re-written byte-identical (decompressed) |
| TrackDeform (road) chunk | VERIFIED layout, LIKELY semantics of a few fields | trackdeform.py | parse -> model -> rebuild byte-identical on all 6 tracks |
| Height blob (kind 7) | VERIFIED size rule, LIKELY meaning | build_testtrack.py | size = 256 x sum(A) on 6 tracks |
| AI map (2 m cell quadtree) | VERIFIED layout; lane bits VERIFIED statistically | grid.py | rebuild byte-identical on all 6 tracks |
| Start grid / direction / sectors | VERIFIED (exe 0x5AF280, 0x5AA130) | field patch | disassembly |
| Spline + pace-note markers | VERIFIED layout, LIKELY marker types | build_spline | geometry check (2 m steps, on centre line) |
| Scenery tree kind 11 | nodes/leaves/PVS stream VERIFIED; instance lists and light map NOT decoded | scene11.py (minimal trees only) | invariants hold on all nodes of 3 tracks; exe 0x502400, 0x4FFC30 |
| TrackBoundary BSP | layout + tree linking VERIFIED (exe 0x42C7F0, 0x42AD80); leaf meaning LIKELY | bsp_build.py (serializer + corridor builder) | serializer byte-identical on 6 tracks; built trees agree with geometry on random points |
| Surface ids | VERIFIED (lists behind 0x5B1820 dumped, 90 named entries) | 10_surfaces.md table | all road-layer ids of 32 tracks resolve (2 exceptions) |
| Scenery mesh + material (format 0x20C7) | layout VERIFIED, uv scale LIKELY | meshgen.py (clone a template) | identity clone byte-identical; winding matches the originals |
| Real centre-line import | prototype, handedness fixed, per-cell surfaces from the classic collision codes | build_classic.py | geometry self-checks + overlay pictures |
| Classic textures (Model 2A) | texels VERIFIED from ROM; colour needs run-time RAM | classic_tex.py, m2tex.py | readable text in the decoded sheets, tile borders fit |
| Classic scenery -> SR3 meshes | built (checker / classic luminance / an SR3 material) | build_classic.py | decoded back for the previews |
| Terrain-following walls | built (stepped floor/ceiling per cell) | bsp_build.py | every road point free, 12 m below and 24 m above solid |
| Trackside cameras (root+0x0C) | loader and default cameras VERIFIED (code); records not decoded | none (lists removed: the game builds its own) | 03_master_xdata_route.md |
| Object files (game_objects, dis) | root, object record, model sets, material binding table VERIFIED (data + code + in game) | crowd.py, finishgate.py | 548 spectators textured and animated in game; 15_spectators.md |
| pobj files, grass cache | identified only; REQUIRED in game (crash 0x5DE16C without them) | none (the slot's own are kept) | 21_track_install_and_switching.md |
| Other mesh formats / shaders | see ps3-to-pc-conversion.md; 0x20C3 written for the gate (finishgate.py); formats with a colour not decoded | finishgate.py (one mesh) | - |

Rows added after the tracks were driven in game (2026-10-06 .. 08):

| Structure | Understanding | Builder | Proof |
|---|---|---|---|
| Whole authored / imported track | loads and races | import_classic.py | SRC Mountain playable in game since 2026-10-07 (owner: driving, checkpoints, collision work) |
| Container, AI map, scenery tree, spline, wall BSP, authored meshes | the static builders hold | as above | each proven in game on the test ladder (09_authoring_status.md, last section) |
| Chunk order (no forward references) | VERIFIED (50,952 references in SEGA's files + a crash) | reforder.py | 01_container.md |
| Overlay pages of the road | count rule and local-patch rule VERIFIED (code + two crashes); texA is a sun / shadow map (in game) | build_testtrack.two_pages | 04_trackdeform_road.md |
| Mesh uv | signed 16-bit VERIFIED (in game) | build_classic.faces_to_mesh | 23_texture_pipeline.md |
| Texture sampler words (header +0x14) | VERIFIED (code 0x58DF40) | import_classic.py | 01_container.md |
| Lighting sets (49 floats x 2) | seven ranges VERIFIED by patching and in-game runs | import_classic.py | 16_lighting_shadows_lightmaps.md |
| Light maps | what a light map does VERIFIED in game | lightmap1995.py | 16_lighting_shadows_lightmaps.md |
| Start / finish gate object (3 states) | VERIFIED (code); replacement not yet confirmed in game | finishgate.py | 15_spectators.md |
| Checkpoint seconds per track | VERIFIED (code + in game) | arcade_times.py + patch.ps1 | 03_master_xdata_route.md, 20 |
| SRC gameplay tables | VERIFIED (ROM + geometry) | import_classic.py | 18_src_1995_rom_data.md |
| SR2 gameplay tables | VERIFIED (ROM + code) | classic/sr2_sr3_import (static only, not rebuilt) | 19_sega_rally_2.md |

Big corrections to earlier guesses: the 6 MB kind 5 "scene" chunk is the ROAD (TrackDeform) and it also defines lap
distance; the kind 11 chunk is the SCENERY tree, not collision; the kind 7 blob is a zlib stream of road height bytes;
the "route/spline" guess for the first chunk of master_xdata was wrong - it is the AI map. Stadium4 has no spline at all.

## Preview pictures (work/previews) - look at these first
All Blender pictures are rendered headless (`work/scripts/render_all.py`, Blender 5.1 `-b --factory-startup`).
Same nine camera positions in every set: `overview` and `road_1` .. `road_8` (driver height, along the centre line).
- `final_<course>_<variant>_<n>_<view>.png` and `fly_<course>_allsr3.mp4` - every course and variant (14_importer.md).
- `blender_final_1..9_*.png` - classic colour (left) against the ALL-SR3 version, step24 (right), 2560 px; `blender_allsr3_*.png` alone.
- `blender_sr3trees_*.png`, `blender_compare_5_sr3_trees.png` - step23.
- `blender_compare_1_start_town.png`, `blender_compare_2_rock_section.png`, `blender_compare_3_road.png`,
  `blender_compare_4_overview.png` - classic (left) against SR3-retextured (right), 1280 px wide, labelled.
- `blender_classic_overview.png`, `blender_classic_road_1..8.png` - SEGA Rally Championship MOUNTAIN course with its own
  textures from ROM, in colour (palette recovered statically from the program ROM, see 12_classic_textures.md).
- `blender_sr3tex_overview.png`, `blender_sr3tex_road_1..8.png` - step20: the same course retextured with SR3 textures,
  DECODED BACK from the built SR3 files (scenery meshes, their materials' textures, the SR3 road with its layer textures).
- `blender_sr3_step17_overview.png`, `blender_sr3_step17_road_1..4.png` - step17 (classic textures inside SR3 files) decoded back.
- `overlay_top.png`, `overlay_closeup_*.png`, `classic_course1_top.png`, `sr3_road_profile.png`, `persp3d_*.png` - plan
  views and profiles from the third package (the plan views are still valid; persp3d are superseded by the Blender sets).
- Decoded OBJ files behind the renders: `work/previews/sr3_decoded/<step>.obj` (+ .mtl, textures/).
- Classic export: `work/classic_tex/course1/src_course1_hi.obj` + `.mtl` + `textures/` (130 tiles) + `sheets/`.
- Retexture labels (editable): `work/retex/tile_labels.csv`; pictures used to choose: `work/retex/classic_tiles_contact.png`,
  `work/retex/sr3_candidates_Alpine4.png`.
