# Glossary - the project's own terms

One or two plain sentences per term, with the file that explains it. Terms are grouped; within a group they run from the
general to the particular. "SRC" = SEGA Rally Championship (1995), "SR2" = SEGA Rally 2 (1998), "SR3" = SEGA Rally 3
(2008 arcade).

## Games, programs, people
| Term | Meaning | File |
|---|---|---|
| SRC, "the 1995 game", "classic" | SEGA Rally Championship, Model 2A arcade board. "Classic course" = one of its four courses | 18, classic-sources |
| SR2 | SEGA Rally 2, Model 3 Step 2.0 | 19 |
| SR3, "the arcade" | SEGA Rally 3, `Rally.exe` 3.8.4.1, run through TeknoParrot | all |
| Revo | SEGA Rally Revo, the home game SR3 descends from; exists for PC and PS3 with the same track data | ps3-to-pc-conversion, 13_revo_vs_arcade |
| PC demo | SEGA's free Revo PC demo with two tracks (canyon2, tropical2); the ground truth for the PS3 converter | ps3-to-pc-conversion |
| TeknoParrot | the loader the arcade game runs under; it refuses a modified `Rally.exe` | 20 |
| Model 2 control / reference | a screenshot of the 1995 game in the owner's Model 2 emulator, used to judge colours, gates and shadows | 16, 18 |
| the owner / "user" | the person who owns the project and drives every in-game test on the cabinet | README |
| in game | the owner drove the build on the arcade cabinet and reported or screenshotted the result | README |
| CamLab | the camera tuner (`camlab.exe`) and, loosely, the folder `SR3CamLab` holding the launcher | 20 |
| SR3 Extras, SR3Ultimate | successive names of the settings app (`extras.ps1`) that installs tracks, art and sounds | 21 |
| SR3Lab | the planned name of the whole suite and of its settings program (plan only) | 21 |
| TexLab | a planned fly-around texture painter (plan only) | 23 |
| PLAY.bat | the launcher: starts the game through TeknoParrot and applies every in-memory patch | 20 |

## SR3 files and containers
| Term | Meaning | File |
|---|---|---|
| SBF | the container format of SR3 / Revo data files: a table of chunks, each with a kind, an id, pointer fix-ups and id references | 01 |
| SBZ1 | the optional zlib wrapper of an SBF file (`SBZ1` + size + zlib stream) | 01 |
| chunk | one record of an SBF file | 01 |
| kind | the type number of a chunk: 1 mesh, 2 material, 3 shader stub, 4 texture, 5 pointer-linked structure, 7 raw bytes, 11 scenery tree, 12 small typed object | 01 |
| kind 5 | a pointer-linked structure with no type tag (road, AI map, spline, wall BSP, object lists) | 01 |
| kind 11 | the scenery tree of a track: a fixed-depth quadtree with the scenery meshes on its nodes and a visibility stream per leaf | 05 |
| kind 12 | a small typed object used directly as a C struct; the last chunk of a file is its root | 07 |
| fix / fixup | an offset inside a chunk's data where a pointer (an offset into the same data) is stored | 01 |
| ref | an offset inside a chunk's data where the id of another chunk is stored | 01 |
| resource id | the 32-bit hash that names a chunk; identical across platforms | 01 |
| root | the last chunk of a file, returned by the loader | 07 |
| forward reference | a reference to a chunk that comes later in the same file; not allowed | 01 |
| slot | one of the six hard-coded track folders (Tropical4, Canyon4, Alpine4, Lakeside4, Desert4, Stadium4) | 02, 21 |
| Classic, Classic slot | SR3's "Classic" game mode and its track Desert4 ("Desert '95"), the slot every imported course is built for | 21 |
| master_gfx / master_xdata | the two mandatory files of a track: graphics + road + walls, and the gameplay root | 02 |
| game_objects / dis file | the placed-object file and the file with Granny models and animations ("gameobj_gfx_dis_data") | 15 |
| pobj files | "procedural object" masters and placements; together with the grass cache they are required in a race | 02, 21 |
| grass cache | `<Route>_proc_cached.bin` | 02 |
| ArcadeDatabase | `arcadedatabase_xdata.sbf`: the track list and the seconds each checkpoint grants | 03 |

## SR3 track structures
| Term | Meaning | File |
|---|---|---|
| TrackDeform | the road chunk: visible road, deformable ground and the measure of track position at once | 04 |
| slice | one row of road vertices; slices are 1 m apart along the centre line and are the unit of lap distance | 04 |
| column | the lateral position of a road vertex in metres from the centre line (column 0) | 04 |
| cell | (road) the quad between two columns and two slices, with a 16 x 16 grid of height bytes. (AI map) a 2 m x 2 m square. (1995 centre line) one of the 300 sections | 04, 03, 18 |
| batch record | an 11-byte record per 4 slices naming up to 7 surface layers and an overlay page | 04 |
| layer, base / top | a road cell has a BASE layer (what shows where the road is worn) and a TOP layer (the driving surface); each is a 1024 x 1024 texture whose id selects the physics surface | 04, 10 |
| layer pair | a (base id, top id) combination SEGA uses together | 10 |
| overlay page | a local patch (about 100 m of road) with a sun / shadow map texture mapped over the road | 04 |
| height blob | the zlib stream of road height bytes (0xBF = undeformed) | 04 |
| AI map | a quadtree of 2 m cells with neighbour links and three lane-mask bytes | 03 |
| lane mask | 8 bits = 8 AI lanes across the road; three alternative sets chosen per car | 03 |
| spline, DesignRouteSpline | the designer's centre line with markers | 03 |
| marker (0,5) | a spline marker that is both a sector split and a time checkpoint | 03 |
| marker (3,2), Direction code | a pace-note marker; its "Direction" property is a code 1..102 = 17 x variant + type | 03 |
| PVS | potentially visible set: per leaf of the scenery tree, the list of nodes drawn when the camera is in that leaf | 05, 20 |
| leaf | a lowest-level cell of the scenery tree (46.875 m in the arcade tracks) | 05 |
| TrackBoundary, wall BSP, corridor | the invisible tunnel of walls, floor and ceiling around the road; the importer's version is a "corridor" between two polylines | 06 |
| Uber material | the 1848-byte (or 1728-byte) material of shader f398b7a8 with named switches and constants | 07, 16 |
| switch | a boolean option of the Uber material named `gbUber...` (ATEST alpha test, ABLEND alpha blend, DSIDE two-sided, SCAST casts shadow, SSRECV / SDRECV receives static / dynamic shadow, LMAP light map, NORM normal map, VCOL vertex colours, LITE lit ...) | 07, 16 |
| lighting set | one of the two 49-float records of a track holding light direction, ambient, sun, fog and tint | 16 |
| light map | a texture that multiplies the finished colour of a polygon, addressed by the second uv set | 16 |
| sky dome | the mesh at master_gfx root +0x10; it follows the camera | 07, 22 |
| horizon card | the far picture at master_gfx root +0x14 (Desert4: Kilimanjaro) | 07 |
| object record | a 0x54-byte record of the game_objects list: class name, id, matrix, parameters | 15 |
| model set | an entry of the dis root naming a Granny model, its animations and the objects that use them | 15 |
| material binding table | game_objects root +0x10: Granny material names -> material chunks; must be kept | 15 |
| animator / dumb spectator | the hidden animated master objects, and the spectators that copy their pose | 15 |
| look | one of the eleven model / animation sets a dumb spectator can be given at run time | 15 |
| Start_Finish_Line | SR3's banner object whose three "LODs" are three states (start, checkpoint, finish) | 15 |

## SRC and SR2 data
| Term | Meaning | File |
|---|---|---|
| object table, object | (SRC) the table of 16-byte rows in the main data ROM; an object is one polygon model | classic-sources, 12 |
| hi model / low twin | the 60 high-detail objects of a course and their 60 low-detail copies | classic-sources |
| backdrop | the 2-3 extra objects of a course: sky dome, far ground, distant scenery (Mountain: 1257 / 1258) | 18 |
| section | the 1995 game's unit of progress (300 per course); in SR2, 256 per course | 18, 19 |
| trackside table | the 1995 per-course table of placed objects; kind 4 = spectator, 16 = gate, 17 = gate post | 18, 15 |
| gate | (1995) a CHECK POINT or FINISH banner on two posts, objects 783..792. (importer) see "gate" under z-fighting | 18 |
| gantry | the importer's own stand-in gate (plain geometry and a drawn texture), used before the real gates were found | 22 |
| sheet, page | (SRC) texture RAM has two sheets of 2048 x 1024 texels; a "page" is a 512 KB block of texels in the ROM | 12 |
| tile | one texture rectangle of a 1995 sheet; named `tex_s<sheet>_x<X>_y<Y>_<W>x<H>_c<colour base>[_t]` | 12 |
| `_t`, cut-out | a translucent 1995 material (texel 15 = hole); in SR3 an alpha-tested texture | 12, 23 |
| colour base, luma base, colorxlat | the three inputs of a 1995 texel's colour: palette entry, luminance ramp, colour translation table | 12 |
| `col_XXX` | a flat-coloured 1995 polygon without texture | 23 |
| stage / course id / round | (SR2) the three numbers that identify a course | 19 |
| rival line | (SR2) the recorded line the computer cars follow | 19 |

## The importer
| Term | Meaning | File |
|---|---|---|
| importer | `work/scripts/import_classic.py` and the modules it calls | 14 |
| variant: classic / mixed / allsr3 | 1995 textures inside SR3 files / SR3 surfaces with 1995 pictures / no 1995 texel at all | 14, 13 |
| step, stepNN | a built track folder `work/out/stepNN_<name>/<Slot>/`; the number orders the test ladder | work/out/README.txt |
| ladder | the sequence of test tracks that each change one thing | 09 |
| twin | the Desert4 copy of a ladder step first built on Stadium4 | 09 |
| package (one .. nine) | the successive work packages of the static phase; file sections are dated by them | 09 |
| course settings, course JSON | `work/courses/<game>_<course>.json`, plus `--set key=json` on the command line | 14, 17 |
| face | one polygon in the importer's list: (material, section, corners, uv) | 22 |
| material key suffix | `|1` single-sided cut-out, `|3` seen from both sides and written once per side, `|4` side not certain; section suffix `~s` = single-sided, `#L<n>` = layer number | 16, 22 |
| ZS | the sign applied to the classic exports' z; -1 = SR3 uses the game's own axes | 14 |
| ox, oz | the offsets that re-centre a course on SR3's origin | 14 |
| decode back | reading a BUILT track back into an OBJ to check or render it (`preview_obj.py`) | 14 |
| drape | to cut 1995 road polygons into pieces of at most 1 m and lay them on the SR3 road surface as decals | 22 |
| decal | a quad lying a little above another surface (road paint, the draped road) | 07, 22 |
| vivid | the gain / saturation / gamma applied to classic tiles | 23 |
| HD tile, re-authored tile | a PNG in `textures_hd` that replaces a 1995 tile | 23 |
| fast lane | `texfast.py` / `UPDATE_TEXTURES.bat`: rewriting only the textures of installed tracks | 23 |
| texmap | `texmap.json`, written by every build: texture id -> tile and recipe | 23 |
| byte-identical | same inputs give the same output files; the standard for rebuilders, compiled ports and any future restructuring | 17, 01 |
| golden set | the planned list of SHA-256 hashes of every output, to test byte-identity (plan only) | 21 |

## Z-fighting and scenery repair
| Term | Meaning | File |
|---|---|---|
| layer, stack | (1995 scenery) polygons lying on one another in one plane, drawn by priority on Model 2 | 18, 22 |
| overlay | a cut-out polygon on the same corners as an opaque one (ivy on rock) | 22 |
| front / back pair | two polygons on the same corners with opposite winding | 18, 22 |
| blade | one of the planes a 1995 tree is made of, running outwards from the tree's axis | 18 |
| overlap resolver, overlay bake | `overlay_bake.resolve`: every stack is resolved in its plane (cut, drop, or compose) instead of being offset | 22 |
| composed tile, `bake_<hex>` | a picture made of a lower tile with an upper tile's opaque texels painted over | 22, 23 |
| gate (z-fight gate) | `overlay_bake.gate`: the count of face pairs that could still z-fight; faces that would fail it are left out | 22 |
| lift, far_scale | the earlier method: moving a layer off its base by a gap that grows with distance; disproved | 22 |
| gap fill | geometry the 1995 game never needed but SR3's cameras show to be missing | 22 |
| hand fill / hand model | the generated-once fill file `src_course<N>_handfill.obj` / a hand-made model file `..._handmodel.obj` | 22 |
| verge | 1995 collision ground beside the road that the 1995 game never drew | 22 |
| shelf, skirt | early fill pieces: a level strip beside the road and a short strip hanging from it (now off). "Skirt" is also a wall carried down into the ground | 22 |
| hillside, terrain | the one height grid of generated ground under the whole course | 22 |
| shoulder | the distance the generated land stays level beside the road before it falls | 22 |
| shore | the cliff the generated land forms where it meets the open sea | 22 |
| foot | the lowest edge of an upright polygon that does not stand on another upright polygon | 22 |
| weld, seam | a filler strip that closes the opening (seam) between ground and a wall's foot | 22 |
| seal | the last pass that carries any still-open wall foot straight down | 22 |
| screen | a tall cliff face made of a single curtain of polygons with no back and no top | 18, 22 |
| plateau, mesa | the far rock screen of Mountain completed by a hand model | 22 |
| sea sheet | the flat sheet of the sea tile under an imported course | 22 |
| sky drop | how far the sky dome mesh is lowered for an imported course | 22 |
| round, R<n> | cutting natural ground finer and smoothing it; `round` 2 / 4 / 8 / 16 = one / two / three / four levels | 17 |
| natural | tile classes that may be rounded or used as fill: rock, grass, dirt, sand, gravel | 17, 22 |
| REACH, ORDER, FLAT, APRON | the limits of the rounding: how far a corner may move; staying on its side of fixed surfaces; flat polygons written whole; corners near road height on the road strip do not move | 17 |
| apron | the ground the tarmac lies on and the feet of rock and walls beside it, kept fixed by the rounding. Also (gap fill) a short fill in a notch | 17 |

## Lighting
| Term | Meaning | File |
|---|---|---|
| design sun | the direction used by the brightness rule: the real sun's compass direction, 45 degrees up | 16 |
| light_contrast, K, L<nn> | the strength of the brightness rule (floor = 1 - 0.6 K); build suffix L75 = K 0.75 | 16 |
| scene gain | per-channel gain on the tiles to compensate another track's lighting sets | 16 |
| lightside | the ray test "which side of a polygon is open to the sky" | 16 |
| roadsight | the ray test "which side of a polygon is seen from the road"; it overrules lightside | 16 |
| sure / unsure | whether the seen side of a polygon is certain; unsure ones are drawn two-sided and lit as their brighter side | 16 |
| bake (light) | computing light with rays and storing it per vertex (`bake1995.py`) or per texel (`lightmap1995.py`) | 16 |
| V, A, B | the three baked quantities: share of the sun seen, share of the sky seen, light bounced back | 16 |
| shadows / rt | the two bake modes: cast shadows only / plus sky dimming and bounce | 16 |
| collect / table | the two passes of a bake: a first build COLLECTS the vertices or polygons into a file (`bake_collect`, `lm_collect`), the rays are cast, and a second build reads the result back as a TABLE (`bake_table`, `lm_table`) | 16, 17 |
| page (light map) | one 2048 x 2048 light-map texture; each page needs its own copy of the material | 16 |
| relief | the normal map made from a facade tile's own picture | 16 |
| VSM | variance shadow map, the technique of SR3's dynamic shadows | 07, 16 |

## Launcher and switching
| Term | Meaning | File |
|---|---|---|
| in-memory patch | a change written to the running process, never to `Rally.exe` on disk | 20 |
| cave | the unused 896 bytes at 0x673C80 holding the chase-camera patch (signature "SR3C") | 20 |
| patch block, cycle block | the 0x3000-byte block allocated in the game (signature "SR3V") that runs every frame | 20 |
| profile | a named set of chase-camera values in `profiles.yaml`; "Baseline" = SR3's own camera | 20 |
| Watch-Tracks | the launcher's loop that serves the track switcher while the game runs | 20, 21 |
| stage card | one of the three stage-select entries; a short video | game-runtime-and-frontend |
| replace mode / alternative mode | installing a track over a slot's files / beside them in `track<k>\<slot>` | 21 |
| alternative | a track installed beside a slot's own, chosen with View Change; at most nine per slot | 21 |
| switch.json, classic.json | the lists of alternatives the switcher reads | 21 |
| arcade_times.bin, shadow.txt | optional side files of a track folder: checkpoint seconds, shadow edge values | 20, 21 |
| revofix | the pass that rebuilds materials of shaders the arcade lacks after a Revo track is converted | 13_revo_vs_arcade |
| ps3model | the learnt layout model the PS3 -> PC converter uses (`ps3model.txt`) | ps3-to-pc-conversion |

## Build names (imported Mountain, 2026-10-07 / 08)
A build name is the label an installed Classic alternative carried in the switcher; names were reused freely, so the
date matters. Only what the sources state is listed.
| Name | What it was | Source of the name |
|---|---|---|
| R6, R7 | ladder labels: R6 = `step5_authored_road_surface_desert4`, R7 = the flat loop | owner's notes |
| S1, S2 | three different uses: (a) the two in-game runs that proved overlay pages must be local; (b) the crowd variants S1 = `build_safe` (only matrices rewritten), S2 = `build`; (c) the builds `step49/50_mountain_full*` on which "z-fighting fixed, sky fixed, shadows fixed" | build_testtrack.py, 15, owner's notes |
| W1, W2 | first playable Mountain: W1 = `step34a_mountain_with_slot_props_desert4`, W2 = `step34b_mountain_no_objects_desert4` | owner's notes |
| B | the build with gamma 1.7 on the tiles ("colors are perfectly matched") | owner's notes |
| C1, C2, C3 | Mountain; Mountain + crowd; Mountain + crowd (safe) | owner's notes |
| D | builds on which distant z-fighting was still seen | owner's notes |
| F1, F2, F3 | Mountain filled with blend road; Mountain with the 1995 road only (SR3 layers alpha 0); Mountain + crowd | owner's notes |
| U1 | the fill build whose tiles were the nearest natural ground / rock ("everything makes sense now") | owner's notes |
| Y1, Y2 | the build with tree blades kept as single-sided pairs | owner's notes |
| Z, Z1, Z2 | the reference state of Mountain's fill: `step57/58_mountain_z*` | owner's notes |
| Z3 | Z + the completed plateau: `step60_mountain_z3_desert4` | owner's notes |
| Z4 | the "final refinements" build: `step61_mountain_z4_desert4` | owner's notes |
| Z4L50, Z4R2, Z4R4 | Z4 with `light_contrast` 0.5; with `round` 2; with `round` 4 (steps 62-64) | owner's notes |
| Z1R2 | Z1 with all natural surfaces rounded by a factor of 2 (the first rounding experiment) | round1995.py |
| Z6, Z7L25, Z8, Z9, Z13L75, Z15, Z15R8 | lighting and rounding experiments of 2026-10-08; the number counts the experiment, L<nn> = light_contrast x 100, R<n> = round | build_classic.py, import_classic.py, round1995.py |
| R2, R4, R8, R16 | rounding levels; the owner settled on R4; R8 = 1.82 million vertices runs; R16 = 5.18 million did not load | 17 |
| L25, L50, L75, L100 | `light_contrast` 0.25 .. 1.0; K = 0.75 matched the Model 2 control | 16, owner's notes |
| BASE, BASE-SHADOWS, BASE-RT | the three builds the owner asked for on 2026-10-08 when light was first baked per vertex: BASE-SHADOWS = bake mode `shadows`, BASE-RT = bake mode `rt`; BASE is LIKELY the same build without baked light (the sources name it without defining it) | bake1995.py |
| LM-TEST | the four-squares experiment that showed what a light map does | lightmap1995.py |
| LIGHTMAP-RT, LIGHTMAP-RT 2 | the first real light-map builds | 16 |
| FACADE-TEST | the first relief (normal map) test on facades | build_classic.py |
| Light A / Light B | two screenshots used to measure Tropical's light against the importer's own | import_classic.py |
| `..._lm_...`, `..._sun1630_...` | suffixes of the newest step folders: light maps; the 16:30 sun | folder names, 16 |
