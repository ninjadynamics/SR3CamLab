# Ultimate Race Lab / SR3 case study

This reference records the Mountain project state and observed failures as of 2026-10-19. It is not a universal recipe for modifying another game's executable. Recheck current code/KB before running an old one-off script. Do not infer authorization to install or patch from this document alone.

## Locations and division of responsibilities

Project root at the time: `F:/Jogos/Ultimate Race Lab`.

- Maintained importer: `source/tools/import/core`.
- Runtime source: `source/standalone/runtime.c`.
- Durable user Blender files/backups: `work/blender`, `work/texture-backups`.
- SD/HD source set: `content/classic/courses/src/course1_mountain/textures` and `textures_hd`.
- Installed Mountain alternative: `game/Rally/Main_release/track1/Desert4`.
- Accepted-baseline metadata: `config/accepted-baseline.json`.
- v14 investigation/build reports: `scratchpad/mountain-v14-20261019`.
- Final larger clean master set: `scratchpad/resolution-3x-20261019/clean`, then selective sign correction in the final installed set.

Source/KB/scripts are intended for public version control. Extracted SEGA data, imported game files, local images and work folders remain local. This skill intentionally ships no game artwork. Do not copy the local folders into a public skill package.

## Art contract changes during the session

The requested target evolved: exact 2x; then minimum side 128; then minimum side 256 using the image model; finally general 3x with minimum side 256 and facades 4x. Later instructions supersede earlier ones. The final artwork target preserves aspect ratio. Examples: 64x128 -> 256x512; 128x128 facade -> 512x512; 256x256 natural tile -> 768x768 artwork. Engine storage may need the next power of two, separately.

The final set contained 178 clean PNGs. Twenty-one new facade heads served their palette siblings. The owner accepted restrained unique-structure denoise and direct SD upscales for natural tiles/trunks. Roads should have sober grain, preserved skid contrast and reduced color noise. Later feedback requires SD-matched contrast, superseding an earlier acceptance of stronger foliage contrast. Labels are review-only. The LIBRAIRIE text-region correction is explicitly accepted; preserve it.

## Partial HD coverage: PNG replacement was insufficient

Some facades, one castle wall and the sky appeared SD despite HD files existing. Stored facade/overlay compositions and sky projections were not all rebuilt by the older generic fast texture updater.

The complete local coverage packer reconstructs facade recipes, derived ground/grass dependencies, overlay compositions and projected sky textures. One correction pass rebuilt 106 facade composites and both sky dome images; 419 texture chunks changed without altering geometry/materials/lightmaps. Every composed consumer must be traceable to its current clean source hashes.

`texmap.json` records texture IDs, source tiles and recipes. After exact-duplicate consolidation, it also retains `engine_compaction` aliases and reference changes. Direct `texfast.py` refresh refuses such compacted slots rather than silently updating only one of several formerly independent textures. Use a fresh unshared stage through the recorded full coverage packer, then apply compaction; do not blindly rerun the one-off repair against its own compacted output.

The current core encoder rounds non-power-of-two artwork upward to safe power-of-two storage within its supported maximum. Preserve the full artwork and UV footprint; do not pad a visible border into the sampled region or crop away content just to satisfy a size rule.

## Loading regression: two separate defects

The first larger v14 build passed offline file checks but entered an infinite loading loop. A subsequent power-of-two/compacted build still crashed. These were not evidence that artwork generation itself had failed.

### 1. Standards-valid DDS was not engine-compatible

Disassembly of Rally's DXT upload code at `0x4196E9` and `0x4197D1` showed block counts based on floor(width/4), floor(height/4), each clamped to at least one. Standard DDS block payloads use ceiling. A 384px or 768px side eventually reaches a 6px mip, where the byte counts differ. This is a confirmed compatibility defect; it did not by itself prove the exact cause of the initial hang.

Repair: regenerate 78 non-power-of-two chunks from precompression artwork at the next power-of-two size (384 -> 512, 768 -> 1024), without downscaling source detail. Check every mip under both the DDS rule and the game's arithmetic. Do not assume a successful generic decoder establishes engine support.

### 2. The complete track exceeded a fixed heap

Exact duplicate consolidation removed 145 byte-identical imported texture descriptors/payloads and redirected explicit chunk references. This was **not atlas repacking** and did not reduce resolution. Main SBF unpacked size fell from 319.63 to 254.88 MiB. The critical mistake would be checking that main file alone: all seven track SBFs still unpacked to 279.52 MiB, above the fixed 256 MiB track arena.

The supported executable's loader path `0x6530B0 -> 0x596BC0` allocates those SBFs from the track arena at `0x7ECE3C`. The separately authorized runtime repair changes the track allocation initializer at `0x5966F4` (immediate `0x5966FB`) from `0x10000000` to `0x18000000` before heap creation: 256 -> 384 MiB. Full supported `.text` CRC (`dd097484`) and exact expected instruction bytes guard the patch. The executable on disk and other heap sizes remain unchanged.

Unicorn replay of original initialization verifies that only the named track arena changes. The owner subsequently confirmed loading/racing worked. This acceptance applies to the loading repair, not every later visual build. Do not generalize the patch addresses to another build or increase heaps blindly.

Local evidence: `engine-fix/verify_heap.py`, `engine-fix/verify_heap.json`, `engine-fix/report.json`, runtime source and KB23. The historical JSON may say `live_test: pending` because it predates the later owner message; preserve that original evidence and record the later acceptance separately.

### Exact-duplicate consolidation invariants

Merge only descriptors/payloads proven byte-identical, including relevant sampler/header data. Redirect all recorded explicit references to an existing canonical ID, preserve order/reference rules, and validate no dangling or forward-reference regressions. Keep semantic source mappings for future edits. If two aliased sources later diverge, rebuild from the unshared semantic stage; do not let a refresh silently change both or only one.

Validate nontexture chunks against the precompaction stage. Geometry/lightmap content stays unchanged; the allowed differences are the listed texture-ID references. Disk compression ratio is not the heap budget. The final lighting-corrected build removes 163 duplicate textures and totals 287.12 MiB for seven unpacked SBFs under the 384 MiB arena; the approximately 96.88 MiB difference is not a measured guarantee of all runtime headroom.

## Broad shadows: classification data is a build input

After the loading repair, the owner reported roughly half the course in shadow. The v14 isolated workspace had skipped extraction without seeding the authored `src_1.tile_labels.csv`. Automatic labels changed R4 classification and ray-only tree solids. Two false tree canopies had radii 362.2m and 389.2m, shadowing large regions.

With the same geometry, authored labels restored road-shadow coverage from 54% to 36%, and tree/lamp counts from 624/0 to 588/33, consistent with the retained v13 bake. Sun/composition settings were unchanged. Do not “fix” this symptom by brightening all textures or weakening the intended sun.

The maintained fix seeds a missing workspace label CSV from the saved course without overwriting manual edits, includes the effective label hash in bake signatures, and rejects canopy radii above 50m with a diagnostic. This threshold is an SR3 Mountain sanity guard, not a universal maximum tree size. Label seeding, manual-edit preservation, cache invalidation and the false-canopy rejection were tested.

Restored sign classification also exposed a legacy SD gate magnifier applied to existing HD art. The boost now stops once the authored sign reaches 1024px. Higher resolution must not cascade accidentally through old multipliers.

The final install report verifies 11 track files, 178 HD source PNGs, 22 extracted lightmaps and launcher `-Check`. All 31 changed v14 triangles are present before R4. Latest rebake visual acceptance remains separate from those checks.

## LIBRAIRIE: only the letters were flipped

In-game screenshots proved horizontal mirroring of the sign. The fix mirrored only region `(180,328)-(350,350)` in the 512px versions of the three `tex_s1_x0512_y0640_128x128` variants (`c0AD`, `c10D`, `c10E`). Every pixel outside that region was preserved. The facade was not flipped. The owner confirmed it works and explicitly chose to keep it. Do not regenerate/reorient the whole texture based on the earlier misunderstanding.

## Evidence and source entry points

For an actual project update, prefer current maintained sources and KB over copying historical one-off commands:

- `docs/kb/23_texture_pipeline.md`: authoritative consolidated NPOT/heap/coverage recovery.
- `docs/kb/17_mountain_build_notes.md`: v14 geometry and authored-label regression, final install evidence.
- `docs/kb/35_faithful_texture_upscaling.md`: art workflow and decisions from the review session.
- `docs/kb/08_exe_loading.md`: loader index and track arena.
- `docs/kb/16_lighting_shadows_lightmaps.md`: lighting and classification dependency.
- `source/tools/import/core/build_classic.py`, `buildpixels.py`, `texfast.py`, `course.py`, `stack.py`, `rtbake/rt_bake_game5.py` and `source/standalone/runtime.c`: current implementation.

Preserve accepted handling, watchdog OFF and the user's launch/test preferences during texture work. Do not start a live game or a rebake merely because this skill has been read.

## v20: opaque ivy contamination and durable relief-page inputs

The October 20 screenshots showed black rectangles with bright green/pink fragments on ivy-covered cliffs. Exact camera/UV probes traced them through `bake_9fff0b0a` / `bake_b0c14c6b` to `tex_s1_x1664_y0000_256x256_c1A6_t.png` and its c1D6 palette sibling. The affected source pixels were opaque; alpha coverage had not been lost. Gray extraction gutter and abnormal colored fragments had entered the accepted HD art.

The authorized deterministic repair restores only the contaminated RGB mask plus its small halo from corresponding alpha-normalized SD samples. It changes 11,366 pixels (about 1.927%) per 768-square image, preserves alpha byte-for-byte, and leaves all other HD pixels unchanged. These mask colors/tolerances belong to this diagnosis; they are not a rule to erase gray, green, or dark pixels from another asset. Rebuild all overlay consumers from the repaired unshared source, then deduplicate/pack and inspect the decoded consumer at the original UV.

The v20 stage retains all 178 source images, rebuilds facade/overlay/sky consumers, and extracts 22 RT lightmaps. After native relief integration the seven SBFs total about 323.07 MiB before compression under the separately established 384 MiB arena. Neither a passing PNG test nor the compressed disk size establishes this budget.

Native POM settings remain in `config/mountain-pom-depth.yaml`. `stage_pom_wide.py --hd-dir ... --review-export ...` permits verified isolated build inputs; hashes remain mandatory. Source edits do not authorize changing approved heights/depth gains. After installation, refresh `work/pom-native-inputs/clean-rt.sbf`, its `review-track/` files, `pins.json`, and the YAML-referenced reviewed-family manifest. Keep the original clean shader library. Also update `pom-native-install.json` and accepted-baseline hashes transactionally. This prevents the Mountain relief page from reapplying the previous track when only a slider changes.

The accepted smooth runtime is a separate invariant. The user confirmed smooth gameplay before visual work; preserve its binary, affinity/settings, native shader code, global depth and exceptions. Do not launch the game when the user has reserved testing for later. Offline material/geometry/alpha checks do not constitute an in-game play test.
