# SR3 pipeline mechanics

Paths below are relative to the Ultimate Race Lab repo unless stated otherwise. `source/tools/import/core/` is abbreviated CORE. The repo can be outside the shell's writable workspace; use the approved filesystem mechanism rather than silently working in a different game copy.

## 1. Saved Blender source and material provenance

Background extraction uses:

```text
blender -b <saved.blend> -t <workers> --python <CORE/blendpatch/bl_dump.py> -- <scene.pkl>
```

Inspect the log as well as the exit code: Blender has returned success while a Python assertion failed. Verify the expected dump exists and belongs to this input. Dumps encode NumPy arrays as `('nd', dtype, shape, bytes)`; decode before counting, indexing or comparing. `blendpatch/check_build.py:load_pkl` demonstrates decoding. Never interpret the tuple's length, four, as the vertex count.

Material mapping helpers:

- `CORE/rtbake/scene_diff_local.py`: `from_dump` produces local-space triangle records, including faces already using named tiles.
- `CORE/blendpatch/check_build.py`: `tiles(texmap)` maps decoded material names to source tile identities. Its millimetre-tolerant comparison is useful for encoded output, **not** an exact source-identity proof.
- `CORE/blendpatch/facade_recipes.py` and `CORE/coursepatch.py:restore_texture_recipes`: retain/reconstruct composed-material dependencies.

For the Mountain v20 scene, material IDs originate from the original generated patch-3 build, `step99_mountain_p3_desert4`, not the current installation. Retained metadata is under `work/research/cleanup-20261017/retained-metadata/`. The reference edited-scene dump is `work/research/mountain-v13-treefix/scene_m.pkl`. These are case-specific provenance, not universal baselines for another track. Confirm they exist and match before reuse; work folders are not guaranteed in a fresh clone.

Known `shade<N>_` material aliases were normalized to their underlying IDs while preserving a mapping in the output JSON. Assert unchanged object transforms and explicitly verify the road object; do not silently bake unknown transforms.

## 2. Complete final-stage regeneration

Use multisets of exact face records, not sets. For each triangle, concatenate positions and their corresponding UVs as little-endian float32. Choose the lexicographically smallest of its **three cyclic rotations**, without reversing winding. Prefix the normalized material identity and use a deterministic length-delimited serialization for the complete sorted multiset. Preserve duplicate counts.

Let:

- `A` = accepted reference scene multiset.
- `E` = additions of the retained final edit stage that produced A.
- `B` = the new saved scene multiset.

First assert `E` is contained in `A`. The baseline retained from before that final stage is `R = A - E`. Preserve the old stage's removals. Additional source removals are `R - B`, surviving baseline is `R & B`, and new additions are `B - (R & B)`. Reuse matching old addition records where possible, then encode the remaining B faces. Earlier generated and board-move stages remain intact.

The source proof replays `(R minus additional removals) + new additions` and compares it exactly with B. Preserve `texture_recipes` and fail if an addition's material is unresolved. Record source hash, sizes, counts, aliases and proof hash in the patch/audit.

Additional removals needed only for real importer legacy remnants are separately established and audited. In v20, two tree assemblies needed 150 removal triangles covering 117 legacy polygons before the valid replacements survived cleanup. Carry those removals forward once; avoid blindly rerunning an append-only repair. The source-only algebra cannot detect legacy fragments absent from A.

Real chain audit points:

- Instrument `coursepatch.apply_file` after the final patch to retain its returned face list and origin offsets.
- `ROUND_IN=<path>` captures the input to rounding; `ROUND_IN_STOP=1` is used by the local audit driver to stop before R4.
- Compare changed faces in the correct coordinate frame, then repeat assembly checks after overlap cleanup. Deliberate full-tree replacements should retain all expected blade/trunk faces.
- Explain any known degenerate source triangle discarded by encoding separately. An old source error is not permission to modify unrelated geometry.

Package with `CORE/patchzip.py` and inspect the ZIP members to verify exact patch bytes and ordering. `stack.py` always performs its unzip step and preserves locally modified loose JSON according to its unpacked manifest; therefore ZIP, loose JSON and unpacked metadata must agree when installing the new source package.

## 3. Isolated stack and dependency controls

Current stack entrypoint:

```text
python source/tools/import/stack.py src 1 --steps light,rt,build --name <unique-run> --threads <workers>
```

Configure `SR3_SETTINGS` with the isolated `work_root`, correct game/content roots, ROM source and tool paths. The v20 wrapper also redirects `common.courses_dir` to the staged courses, maps the already extracted ROM source/texture data, and wraps child Python calls so they inherit those overrides. Merely redirecting the top-level process does not isolate children that import `common` again. Reuse or adapt the demonstrated wrapper rather than changing global settings in place. Also seed the complete verified extracted-ROM cache in the isolated `build/tmp/m2`: `crowd.py` resolves its own path there, independently of an `i960.M2` override. An unseeded Low run stopped before RT because its `maincpu.bin` was absent; copying the accepted extracted cache fixed preparation without changing the installed game.

Example retained wrapper and logs: `work/research/mountain-v20-r4b-20261021/{run.py,driver.py,settings.json}`. Their v20 paths and identifiers are examples, not a generic turnkey installer. Copy to a new run, replace explicit identifiers and validate every destination before execution. Never rerun the v20 install script against a new build unchanged.

Seed `src_1.tile_labels.csv` from the authored course copy into the isolated retexture workspace. The previous missing-label regression generated two tree canopies over 360 m in radius and shadowed much of the stage. Current RT rejects canopy radii over 50 m. Accepted Mountain v20 logged 588 tree solids and 33 lamps; a changed count must be explained against the source and labels, not automatically forced to these historical values.

The stack merges recipe `common`, then `round`, then `build`. R4B v20 values:

```json
{"round":4,"round_slide":false,"round_crease":80,"round_tol":2,"round_cap":1.5}
```

Accepted v20 RT quality is `slow`, composition `0.34`, build `light_split=0.72`. The recipe's scene gain and protected/flat-lit classes are part of the accepted appearance. Collect writes geometry/layout, side classification, gate and car-shadow inputs; RT writes illumination and car-shadow pages; composition produces the table read by the final importer. Verify `polygons found on a page ..., not found 0`.

### Sun-only variants

`light_dir` is the direction light **travels**, in the build's game coordinate convention. Preserve horizontal azimuth. For the accepted Mountain direction `[0,-9.4,3.4]`, elevation E becomes `[0,-sin(E),cos(E)]`, optionally multiplied by the old vector length. E is measured above the horizon in degrees. Use the same direction for collect, RT and final lighting sets; check the stored collect sun vector and final encoded sets. Do not just change the live car light while retaining old scenery maps.

Use a new course copy/run name, collect again and rebake. The stack's `choice()` signature covers patch enablement, rounding level and labels, but does not represent every sun/recipe/source change. A fresh directory avoids accidental reuse. Lighting-only work should leave patch bytes, HD source hashes and geometry coverage unchanged; investigate differences instead of attributing them to the light.

## 4. HD packing, lightmaps and native relief

The established full coverage packer rebuilds facade recipes, ivy/other overlays and projected sky from clean HD sources. The ordinary updater does not cover all historical compositions. Retained implementation: v20 `apply_hd.py`, followed by `engine_repair.py` and `prepare_lighting_final.py` in the research folder. These scripts contain run-specific paths and closed-game/install branches; adapt only the staging path for a new run.

Preserve `texmap.json` recipe/compaction metadata. Rebuild unshared textures first, then repair power-of-two storage and consolidate byte-identical payloads. Rally's floor-based DXT block arithmetic disagrees with standard DDS ceiling arithmetic at intermediate 6px mip sizes. Validate all mips, not merely the top level. Do not crop artwork or reduce its intended resolution to satisfy storage alignment.

Read all seven SBFs with `CORE/sbfw.py` and sum `len(sbf.raw)`. Mountain uses the separately established 384 MiB track arena; v20 with native relief was 323.0734 MiB. Preserve headroom. Validate reference order and required companions; do not omit pobj/grass files because a static decoder considers them optional.

Extract lightmaps from the final SBF's kind-4 chunks with ID prefix `0xc1ad`. Their DDS starts at `chunk.data[48:]` and needs the `DDS ` magic prepended for Pillow. Save chunk IDs, hashes and dimensions. v20 had 22 maps. Extract again for a rebake instead of presenting stale PNGs from an earlier folder.

Native relief staging:

```text
python source/standalone/stage_pom_wide.py --workspace <repo> --out <pom-stage> --track-dir <clean-stage> --base-main <clean-stage/main.sbf> --tuning <yaml> --hd-dir <HD-sources> --review-export <matching-manifest>
python source/standalone/integrate_pom_library.py --source-library <clean-original-library> --source-track <pom-stage/main.sbf> --material-report <pom-stage/stage-report.json> --texmap <clean-stage/texmap.json> --tuning <yaml> --out <native-stage>
```

Use the real slot filename, `desert4_master_gfx_xdata.sbf`, for Mountain. A changed clean track needs a matching reviewed manifest hash; source hashes must still match the approved images. Updating the manifest's base-track hash does not authorize changes to reviewed heights or depth gains.

Verify `geometry_unchanged`, `albedo_unchanged`, `lightmaps_unchanged`, no forward references, and YAML material settings/exceptions. When the native shader and its layout are expected unchanged, compare their bytes against the installed accepted version. Include final relief textures in the heap total.

## 5. Installation and durable configuration

`source/standalone/relief_apply.py` provides checked transactional replacement and its interrupted-install journal. Its existing-file replacement assumes backupable destinations; adding a new alternative requires handling new directory creation and rollback explicitly, not inventing empty preexisting files.

For the main Mountain slot, update together as applicable:

- Final stage files, native receipt, patch ZIP/loose metadata, approved changed HD sources.
- `config/accepted-baseline.json` hashes.
- `work/pom-native-inputs/clean-rt.sbf`, `review-track/`, `pins.json` and the YAML-referenced reviewed manifest. Keep the original clean shader library.

These pins are the settings page's rebuild source. Test a staged-only relief-page gain change and prove geometry preservation with live files untouched. Do not install the temporary test setting.

For a separate named alternative, inspect `game/Rally/Main_release/tracks/_SR3Extras/classic.json` and `switch.json`. A slot is `Main_release/track1` through `track9`, with `Desert4` inside. The same digit can be used for other environments; never overwrite an unlisted `Desert4` directory. Preserve existing Classic entries, music/video metadata and other environment slots. The new title should be exactly the user's requested name.

`CORE/install_track.ps1 -Build <stage/Desert4> -Title <title> -Video MTN -Tracks <game/Main_release/tracks>` uses the lowest unused slot and preserves unrelated list entries. Inspect its current implementation and back up affected metadata before use. Do not use `rtbake/install_set.ps1` to add a single variant: it replaces the entire Classic list. Do not point the accepted main slot's native receipt/pins at a different lighting alternative.

Hash the staged and installed files, confirm the source slot/runtime/YAML remain unchanged for an added alternative, and run:

```text
pwsh -NoProfile -File source/tools/workspace/play.ps1 -Workspace <repo> -Check
```

When called from Python, inherited `PSModulePath` from another PowerShell version previously hid `Get-FileHash`; remove only that inherited value in the child's environment or invoke the matching runtime. A failed check triggers rollback, not a reported successful install.

Retain an install report, before/after hashes, scripts/configuration, logs and extracted maps under a durable research folder. Do not claim the whole build is reproducible from Git if required proprietary ROMs, artwork or local baseline dumps are intentionally excluded.

## Proven v20 result and references

The owner accepted v20 in game on 2026-10-21. Canonical source: 86,838 triangles, 7,953,182 serialized bytes, SHA256 `b2bc3ca5dbd9f86ca65c1f7cb843eef7ec0c9919576aaf320ef4e9cddc755edc`. All 3,376 changed source triangles survived the chain; both repaired trees retained 84 faces including twelve trunk faces. One inherited degenerate triangle was separately reported. Road/gameplay payloads and the accepted smooth runtime were preserved.

- `docs/kb/17_mountain_build_notes.md`: versions, failures and acceptance.
- `docs/kb/16_lighting_shadows_lightmaps.md`: RT and sun conventions.
- `docs/kb/21_track_install_and_switching.md`: Classic slots and metadata.
- `docs/kb/23_texture_pipeline.md`: DDS, packing and memory failures.
- `source/skills/blender-remesh-cleanup/`: geometry authoring and source/chain diagnostics.
- `source/skills/blender-uv-retexture/`: UV density and repeat seams.
- `source/skills/faithful-texture-upscaling/`: faithful art and HD consumer validation.
- `source/skills/facade-relief-mapping/`: reviewed semantic height maps.


### Installed 48-degree lighting alternative

The maintained alternative recipe is `source/tools/import/src/tracks/courses/src_1.low.recipe.json`. Copy it to the isolated run's `src_1.recipe.json`; the normal recipe remains the accepted high-sun R4. This is a complete v20 recipe snapshot, so when advancing geometry/configuration compare it with the new accepted recipe and carry forward only its intended sun override.

The 2026-10-21 run `work/research/mountain-r4-low-20261021/` records the exact installation and final validation. It occupies `Main_release/track2/Desert4`, title **Mountain R4 Low**, alongside the unchanged **Mountain R4** in track1. Both native lighting sets and the RT collect use 48 degrees at the old azimuth. The pre-R4 dump matches accepted v20 byte-for-byte. Final positions, UVs, topology, groups and bounds also match; lighting normals and their derived tangents intentionally change. All 22 lightmap pages were freshly extracted. The main relief-page pins/receipt and original shader/YAML remain intact; the alternative contains the same reviewed family gains/exclusions at installation and shares the global +/- shader control. Its family-map payload is a separate installed snapshot; the existing main-slot relief page does not automatically rebuild this alternative when family gains change.

Do not demand whole mesh-chunk equality after changing the sun. `build_classic.py` encodes target brightness into vertex normals against the actual light vector and derives tangents from those normals. Verify every byte outside those known fields instead: position/UV/index data, headers, bounds and reference/fixup tables must remain identical. In this run, 570 scenery meshes changed normals and 509 changed tangents. Legacy object mesh `0x4ec27d47` has three LOD headers and 36-byte vertices; only the normal fields of LODs 1 and 2 changed. Inspect all LOD headers rather than assuming the first vertex array covers the whole chunk. Never restore old normals just to pass a byte comparison under a different sun.
