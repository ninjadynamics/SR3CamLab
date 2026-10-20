# 23 - Texture pipeline: from a 1995 tile to a texture and material inside an SR3 track

How the importer turns SEGA Rally Championship tiles into SR3 texture chunks (kind 4) and materials (kind 2), what went
wrong on the way and how it showed in game. Texel and colour recovery from the ROM is in
[12_classic_textures.md](12_classic_textures.md); the retexturing with SR3 art is in [13_retexture.md](13_retexture.md);
light maps and normal maps are in [16_lighting_shadows_lightmaps.md](16_lighting_shadows_lightmaps.md).
Sources: comments of `build_classic.py`, `overlay_bake.py`, `texfast.py`, `import_classic.py`, `finishgate.py`,
`bump1995.py`; the owner's notes. Tags: VERIFIED (how), "in game", LIKELY, UNKNOWN.

## 1. Steps
1. **Tile pixels.** `tile_pixels(name)` returns the picture of a material as it will be drawn: the ROM tile coloured by the
   game's own colour table (12), a backdrop PNG exported by the other session, a composed tile of the overlap resolver
   (22, section 2), or a re-authored tile (section 5). A material without a picture is a BUG and stops the build (the
   "grey forest floor" of build W1; flat-colour polygons `col_XXX` are the only exception).
2. **Brightness.** `vivid` applies (gain, saturation, gamma) = (0.95, 1.0, 1.7) to every classic tile. Reason: the 1995
   game shows its textures unlit and bright; inside SR3's lit, tone-mapped picture the same texels looked dull, and Model 2
   reference shots show the mid tones far darker than the decoded tiles while white stays white. History: gain 1.35 was
   "overbright washed out"; (1.0, 1.3) followed; gamma 1.7 gave "colors are perfectly matched" (owner, in game, against
   Model 2 shots). A further per-channel `scene_gain` compensates another track's lighting sets (16, section 1).
3. **Encoding.** Opaque tiles become DXT1 (endpoints = brightest / darkest texel of the block), cut-outs DXT5 with a 1-bit
   alpha channel (255 / 0), both with a full mip chain, under a header cloned from one of the slot's own textures. Sides
   are powers of two. See-through texels take the picture's mean colour, so filtering leaves no dark fringe.
4. **Material.** Every material is a clone of a SEGA material with the diffuse texture reference (+0x1BC) swapped
   (07_glue_and_other_files.md). Variants by switch: opaque two-sided; cut-out = alpha test + two-sided; tree-blade side =
   alpha test, NOT two-sided; road decal = alpha blend + shadow receive; gates = SEGA's own unlit material.
5. **UV.** Section 3.
6. **Map of what was made.** Every build writes `texmap.json` beside its files: texture id -> tile, how it was made, and
   the recipes of composed tiles. The fast lane (section 6) reads it.

## 2. The cloned material's other maps (first in-game run of Mountain)
The cloned material is a Stadium wall's (switches LITE PIXL SPEC DIFFM NORM LMAP SPECM REFL) and still pointed at that
wall's normal map, light map, specular map and reflection: in the game they painted bright window-grid patches over the
1995 textures. VERIFIED in game. Its shader stays (only switch combinations SEGA compiled exist; LIKELY), and the four
maps become neutral textures: flat normal (0, 0, 1), white light, no specular, no reflection.

## 3. UV rules learnt in game
| Finding | How it showed | Rule now |
|---|---|---|
| Mesh uv0 is SIGNED 16-bit, -1 .. +1 (32768 = one repeat). In SEGA's own meshes 95 % of the values are 0..0x7FFF and the rest small negatives | written as 0..2 unsigned, every face that crossed 1.0 had corners read as negative: boards mirrored or upside-down, walls smeared ("textures broken / wrong everywhere" in the first runs) | a face keeps its corners together: an axis that reaches 1.0 is moved down by one repeat; exactly 1.0 is stored as 0x7FFF. VERIFIED in game |
| No v flip is needed | a per-face v flip (`flip_v`) was added when the world was briefly built mirrored; with the signed-uv bug fixed, every texture was upside-down WITH the flip | `flip_v` is a no-op. DISPROVED guess, kept as a note in the code |
| A face spans at most about 2 repeats | - | faces whose uv span exceeds 1.999 are cut along their edges until every piece fits (`uv_split`); 1995 ground tiles that repeat absurdly are first normalised (22) |
| An axis along which the tile never repeats must be CLAMPED | with wrap, filtering pulled the opposite edge in: seams on the castle and on other transparent textures | the texture's sampler address mode is set to clamp on that axis (tree lines repeat sideways only). The sampler words are in 01_container.md |
| The clamp limit must equal the limit used to move a face down by a repeat | with 1.002 in one place, a board spanning 1.0005 was moved to negative uv on a clamped axis and showed one texel row smeared over its whole height ("the wall of green streaks in the forest") | one limit in both places |
| Handedness | with the world built from the OBJ axes (ZS = +1) board text and the whole layout were mirrored (castle on the wrong side) | SR3 uses the game's own axes (ZS = -1); see 14_importer.md |

## 4. Gates and small lettering
- The gate pictures are small (CHECK POINT = 256 x 64 texels over 10 or 20 m): filtered and block-compressed at that size
  the letters came out soft and blotchy ("our checkpoint resolution is lower", owner, 2026-10-08). Each texel is now
  written as a block of 4 x 4: sharp edges, and each 4 x 4 compression block holds one colour.
- The letters (256 x 64) are composed over the blue panel (64 x 32, repeated); the composed picture used to be sized from
  the panel alone, half as fine as the letters ("why does it look so bad in-game, the source itself isn't half bad").
  `overlay_bake._recipe` now sizes it from the finer of the two tiles.
- Gates use SEGA's own UNLIT material (Desert4 `47948b52`, 1728 bytes: alpha test, two-sided, shadow casting, no lighting)
  so no light experiment or shade dulls them. Their gain is 0.94: at 1.075 (as bright as lit scenery) they read "a little
  bit overbright" (owner; the Model 2 gates are slightly shaded).

## 5. Re-authored ("HD") tiles
A PNG `<course>/textures_hd/<tile>.png` replaces the 1995 tile of that name, at an engine-safe power-of-two size (4-2048 pixels per side; non-power-of-two artwork rounds upward), when it
DIFFERS from the export in `<course>/textures` (so the folder may hold untouched copies). Transparent texels (alpha < 128)
are the cut-out's holes. Lookup: `build_classic.hd_tile`, used by `tile_pixels` and by `add_scenery`. At first it was only
read for the gates and the composed tiles ("HD texture pick up not working", owner, 2026-10-08); fixed. Not covered: the
road's tarmac pieces, and tiles the gap fill reads through `fill1995`. Details of the folders: 17_mountain_build_notes.md,
section 4.

## 6. The fast lane (`texfast.py`, `UPDATE_TEXTURES.bat`)
Reason: "every time I update an HD texture I need to rebake? Can't I just restart the game?" (owner, 2026-10-08). Nothing
of a track's shape or baked light depends on its pictures, so the tool opens the INSTALLED tracks and rewrites only the
textures whose tile changed, using `texmap.json`. Covered: scenery tiles, cut-outs, gate pictures, composed pictures
(made again from their two tiles). Not covered: the road's tarmac pieces and anything whose shape or see-through outline
decides geometry. All 332 textures of a track take 4.7 s. The game must be closed. Composed pictures come out about 1 % of
bytes different from the build's (cause not found, UNKNOWN).

## 7. Road layer textures
- The two SR3 layer textures of a surface keep SEGA's ids, alpha blocks, size and mip chain, because the id selects the
  physics surface (10_surfaces.md); only their colour is changed: either tinted towards the 1995 road colours (course
  setting `road_tint`: tarmac 0.42 / 0.45 / 0.52, gravel 0.62 / 0.48 / 0.36 for Mountain) or replaced by the tiled 1995
  asphalt tile (mode `layers`, rejected by the owner in favour of the draped road, 22 section 3).
- The alpha channel of a road layer texture is not transparency: road layers and some SR3 ground textures keep a blend
  height there (comment in `preview_obj.py`; LIKELY).
- Filtering: the texture header's sampler words (01_container.md). The authored road textures had max anisotropy 1 (SEGA's
  road layers: 4) and the road went soft a few metres ahead; course setting `road_lod_bias` -12 = mip level 0 everywhere.

## 8. Things in SR3's own art that shaped the pipeline
- SR3 has NO facade pictures: its buildings are 3D models skinned from 512 x 512 atlases of pieces (13_retexture.md).
- SR3's road paint is decal quads in the scenery meshes with an alpha-blend material (07_glue_and_other_files.md).
- SEGA's normal maps are plain tangent-space pictures (16, section 3.5).
- No real SR3 tree meshes were found as separate assets: Alpine4's trees are board quads inside the scenery tiles
  (09_authoring_status.md).

## 9. Planned, not built
- TexLab (`SR3CamLab\docs\TexLab-plan.md`, plan only, 2026-10-07): a fly-around texture painter that would write a project
  file applied by the importer (`--texlab`). The plan's own "CHECKED" facts agree with this file (uv0 signed, no v flip,
  ZS = -1, clamp sampler in use for cut-out textures).
- "SRC enhanced": an optional variant with smoothed terrain and re-authored / upscaled tiles from an override folder;
  the override folder exists (section 5), the toggle does not.
- Historical upscaling plan (2026-10-08): Upscayl batch upscaling plus Photoshop re-authoring, with "UltraMix Balanced" / "UltraSharp" trials. That plan was not applied then; it is superseded by the image-model restoration, visual review and installed HD workflow in section 10 and [35](35_faithful_texture_upscaling.md).


## 10. Mountain 3x / facade 4x preparation and recovery (2026-10-19)

Current outcome: the owner confirmed loading/racing after the guarded 384 MiB track-heap fix. The later authored-label lighting rebuild is installed and checked offline; its visual acceptance remains separate. The art process is documented in [35_faithful_texture_upscaling.md](35_faithful_texture_upscaling.md). The paragraphs below preserve the failed first attempt and subsequent corrections in order.

Owner requested general 3x SD, minimum side 256, and 4x for facades. Preserve aspect ratio: 64x128 becomes 256x512; 256x256 ground becomes 768x768; 128x128 facade becomes 512x512. Already larger accepted files stay at their current size.

Local clean set: `scratchpad/resolution-3x-20261019/clean`, 178 PNGs, 134 changed. The comparison page has one SD/HD slider per row, small family groups and separate new annotations. Existing review pages/storage are retained. Native image-model outputs and prompts remain alongside the set. Twenty-one new facade heads serve their tone children; children get a pointwise colour transform of the same aligned head, never separate spatial resampling. The castle uses its accepted denoised native master. Cutout alpha follows the accepted silhouette; RGB fringes are cleaned and bled before packing. Installed PNGs carry no diagnostic labels.

Asphalt model denoise preserves the accepted broad wear, skid layout and paint. The first smooth-road result was rejected for excessive grain; `roadSmoothV2` is selected. Plain painted road uses the SD paint mask over this surface. All 134 changed pairs were visually reviewed in 23 cyan-bordered sheets.

**Superseded first attempt:** the HD loader briefly preserved 384/768 dimensions instead of rounding to powers of two. NumPy DXT1/DXT5 fallback padded each mip to block boundaries with edge pixels. Eight encode/decode checks passed for opaque/cutout 384x384, 768x384, 768x768 and 512x512, including size, alpha and mip payload. These established standards-valid files only. The game upload arithmetic below disproved the assumption that this was enough. Current encoders round non-power-of-two artwork upward to compatible storage dimensions, without downscaling the artwork.

The local v14 packer reconstructs facade recipes at 4x (2048 maximum), composed overlays and the projected HD sky. PNG replacement alone does not refresh these stored compositions. The older `texfast.py` fast lane still does not consume facade/sky recipe metadata; use the full local coverage packer for this set until it is extended.

Preparation and visual checks completed. Successful installation and backup are recorded in `scratchpad/mountain-v14-20261019/install-report.json`.

Installation completed and launcher `-Check` passed on 2026-10-19. All 11 track files and 178 clean HD PNGs were verified against their staged hashes. Backup: `work/texture-backups/mountain-before-v14-3x-20261019-013644`. Twenty-two lightmaps extracted. Packed textures remain within 2048 per side and valid mip limits; the track has 544 distinct DDS payloads (previously 528), about 122 MiB more texture data. Live loading, visual appearance and performance remain untested. Source/KB changes are local, not committed or pushed in this round.


### 2026-10-19: loading regression and engine-compatible texture repair

Owner reported an infinite Mountain loading screen after the v14/3x update; Rally was terminated on request. The earlier offline DDS checks did not establish live engine support for arbitrary dimensions. Disassembly of Rally's DXT upload routine at 0x4196E9 and 0x4197D1 shows floor(width/4), floor(height/4), clamped to at least one block. Standard DDS requires ceiling instead. A 384/768 texture reaches a 6-pixel mip, so its later mip offsets disagree. This is a confirmed compatibility defect, not yet proof of the particular loading hang's cause.

Repair installed: 78 non-power-of-two texture chunks regenerated from their precompression artwork at the next power-of-two size (384 -> 512, 768 -> 1024), preserving UV layout and never downscaling artwork. Consolidated 145 byte-identical imported texture descriptors/payloads; redirected their explicit chunk references. Main SBF unpacked size falls from 319.63 to 254.88 MiB. This is duplicate consolidation, not a new atlas layout. Geometry and encoded lightmaps verified unchanged; other nontexture changes limited to the recorded texture-ID references. All slot texture mip sizes were checked against both the DDS block rule and the game's upload arithmetic. SBF roundtrip/reference validation and launcher -Check passed. Source PNGs untouched. Live loading still awaits owner test.

Reproducible repair and provenance: scratchpad/mountain-v14-20261019/engine_repair.py and engine-fix/report.json. Backup path is recorded in the report. The former failed HD stage and pre-v14 accepted backup remain available. Texmap retains original semantic mappings plus engine_compaction aliases and exact reference rewrites; direct texfast refresh refuses compacted slots rather than silently updating only some formerly independent pictures. Regenerate coverage from its recorded updater, then apply engine compaction to the resulting fresh unshared stage before reinstalling.


### 2026-10-19: fixed track-arena budget for HD Mountain

Owner's follow-up test of the power-of-two/compacted build still crashed. Do not treat that build as live-accepted. Static executable initialization replay now verifies a separate hard memory deficit: SegaRally_Track_Heap is fixed at 256 MiB; the compacted track's seven SBF files alone unpack to 279.52 MiB, versus 254.88 MiB for just the main gfx file. The loader 0x6530B0 -> 0x596BC0 allocates unpacked SBFs from this track arena (0x7ECE3C).

Standalone runtime now changes the track descriptor initializer at 0x5966F4 (immediate at 0x5966FB) from 0x10000000 to 0x18000000, allocating 384 MiB before heap creation. Entire supported text CRC and exact instruction bytes are checked first. Rally.exe on disk is untouched; other arenas and all track assets are untouched. scratchpad/mountain-v14-20261019/engine-fix/verify_heap.py replays the original initialization up to heap creation in Unicorn and asserts only the named track arena changes, with over 100 MiB remaining after the seven SBF allocations. This proved the budget correction offline. The owner subsequently confirmed that it loaded and raced ("it worked!!"). The initial static report retains its original pending field because it predates that confirmation. The loading fix is live-confirmed; the subsequent visual lighting correction is tracked separately in KB17.


### Coverage, final installed state, and future refreshes

The earlier partial-HD report (facades, sky and a castle wall remaining SD) was a coverage problem: source PNG replacement alone did not rebuild stored facade compositions and projected sky images. The complete October 18 correction rebuilt 106 facade composites, the grass dependency, and both sky dome images; 419 texture chunks changed with geometry, materials, collision and lightmaps unchanged. Evidence: `scratchpad/contrast-rock-fix-20261018/stage-report.json` and `README.md`. Future refreshes must cover those dependencies as well as directly mapped tiles.

After the authored-label lighting repair described in [17](17_mountain_build_notes.md), the final seven SBFs total **287.1203 MiB unpacked** under the 384 MiB track arena; 163 byte-identical texture payloads were consolidated. The 11 installed track files, 178 HD source PNGs and 22 extracted lightmaps were checked against the staged records; launcher `-Check` passed. This later build differs from the intermediate 145-duplicate / 279.52 MiB loading-repair build, so those counts must not be mixed. `scratchpad/mountain-v14-20261019/lighting-final/report.json` is the final installation record. Live visual acceptance of the latest rebake remains pending.

Do not call duplicate consolidation “atlas packing”: no sampled texture layout or artwork resolution was changed by merging identical chunks. Each alias must retain source identity, canonical texture ID, and all explicit reference rewrites. A later differing edit must rebuild from the unshared semantic stage before compaction. The current direct fast updater deliberately refuses compacted slots to prevent partial or cross-aliased updates.

For future budgets, sum all relevant **unpacked** track files, mip chains and expected runtime allocations; do not compare compressed disk bytes or only `master_gfx` against the track heap. The approximately 96.88 MiB difference between the final seven files and 384 MiB is not a measurement of total runtime peak headroom. Power-of-two/mip checks and memory checks solve different problems; both are required.

### 2026-10-21: apparent alpha failure was contaminated opaque ivy RGB

v20 repairs two palette variants of `tex_s1_x1664_y0000_256x256_*_t.png`. Camera/UV probes traced the black/green artifacts to gray atlas gutter and abnormal colored pixels with alpha=255. The correction changes a 1.927% RGB mask, preserves alpha exactly and rebuilds composed cliff recipes before compaction. Do not erase black pixels or change alpha to fix an unverified "transparency" diagnosis. See [v20 build evidence](17_mountain_build_notes.md#2026-10-21--v20-tunnel-tree-and-ivy-repairs).

For native relief builds, install the updated clean track and texmap into `work/pom-native-inputs`, refresh its pins and the reviewed-family manifest, and update the native receipt/baseline transactionally. Otherwise the settings page can restore stale geometry. The shader library, approved scalar maps, YAML gains and runtime binaries remain unchanged by this visual repair.
