---
name: blender-track-patch-install
description: Extract an edited SR3 classic-track Blender scene into its numbered JSON patch, verify the complete patch chain, rebuild rounding and RT lightmaps, and stage a validated game installation. Use for full Blender-to-game rebuilds or lighting variants of an accepted track; not for authoring mesh repairs or texture artwork.
---

# Blender track patch and installation

Preserve the user's accepted scene and runtime while producing a reproducible track build. The repo copy under `source/skills/` is authoritative; synchronize the installed skill when updating it.

Read [references/pipeline.md](references/pipeline.md) for extraction mechanics, current tool paths, the Mountain case, and installation details. Resolve all paths against the actual workspace, not the shell's current directory: the game checkout and lab repo can be different folders.

## Choose the requested scope

- **Edited Blender scene:** regenerate the complete final patch stage, prove source reconstruction, run the real importer chain, then rounding, lighting, packing and installation.
- **Lighting-only variant:** reuse the accepted patch package and art. Use a separate recipe/work directory and collect again with the new light direction before RT and build. Do not regenerate geometry or overwrite the accepted recipe merely to lower the sun.
- **Named alternative:** preserve existing alternatives and install into an unused Classic slot, or update the exact requested existing title. Keep its metadata and rollback coverage separate.

Installation, launching a game, and committing/pushing are separate actions. Follow the user's existing authorization and requested order. A request to finish the full installation authorizes the necessary staged build and reversible installation; it does not require another confirmation. Do not launch the game when the user reserves testing.

## Establish the inputs

Record the saved `.blend` hash, patch package, course/recipe, authored material-label CSV, source texture set, texture recipes, runtime baseline, installed track slot, native relief YAML and receipt. Preserve the accepted source file and back up the installed files before replacement.

Verify the correct Blender instance/file before using live MCP. Prefer a background read of the saved file for extraction when Blender is closed. Do not silently save over unsaved manual edits. Count nontriangular faces; triangulation changes require scope-aware handling before claiming a triangle-exact result.

The gameplay road is protected. Compare the separate road object and gameplay payload against the accepted baseline. Include collision/checkpoint data, handling, and banner placement in the preservation checks relevant to the build.

Use the current CPU budget, including inherited affinity for child processes when responsiveness matters. This project's latest heavy-build preference is all logical processors minus two; earlier requests for “all cores” meant minus one. Resolve against current instructions and machine topology. Serial stages need not reach 100% utilization.

## Extract the complete patch

Map source material identities using the texmap from the build that originally produced that Blender scene. A current installed texmap can assign the same IDs to different images. Normalize only known material aliases, accounting for every face; fail on unresolved identities.

Preserve earlier numbered patches, generated stages, board moves, texture recipes, and explicit legacy removals. Regenerate the whole final edit stage from the saved scene, not only the latest selected region. Keep multiplicity and winding; intentional opposite-facing cutout panels are distinct surfaces.

Produce two independent proofs:

1. **Source reconstruction:** replay the retained baseline plus removals and additions and compare canonical float32 triangle positions, winding, per-corner UVs and normalized material identities byte-for-byte.
2. **Actual importer chain:** apply the complete ordered package to the real ROM-derived input and inspect the pre-rounding result and post-cleanup result. Check changed faces and repaired assemblies, including thin trunks, against the source.

The first proof does not substitute for the second. Legacy slices absent from the edited source can survive in the importer, causing cleanup to delete the correct replacement. Remove only the verified legacy assembly and prove the replacement survives the cleanup.

Do not describe `.blend` containers or the later quantized game meshes as byte-identical to JSON. State the exact payload and representation compared. Explain inherited degenerates or intentional importer-only surfaces separately; do not hide differences behind a loose tolerance.

## Build the requested stack

Use an isolated work root and course copy. Seed the authored labels before the first collect; these labels affect rounding and ray-only tree/lamp blockers. Retain recipe values unless the request changes them.

Run collect, RT/composition, then final encoding. A changed sun, geometry, material label, ray-blocker input or rounding configuration invalidates the old lighting inputs. Prefer a new run name; do not trust the stack's partial cache signature to detect every changed recipe field.

Diagnose missing shadows at both ends: verify the caster and the final receiving material. Transparent terrain must retain alpha while receiving a real lightmap; do not route it through sprite flat-lighting or building closure. For dappled stand-in canopies, use coherent world-scale openings that pass through both sides of the shell and test actual ray transmission. See the reference for the proven implementation.

For accepted Mountain R4B, retain outward level 4, slide false, crease 80, tolerance 2 and cap 1.5 unless requested otherwise. Source fairing is not an algorithm improvement. RT quality, composition and scene gain are separate choices; do not compensate an unexplained shadow defect by brightening everything.

Rebuild all HD consumers, including facade/overlay recipes and sky projections. Preserve albedo, cutout alpha, accepted lettering, texture scale and current height maps. Apply engine-compatible power-of-two/mip packing and exact-duplicate compaction after rebuilding unshared consumers. Do not update a compacted slot through an updater that does not understand its aliases.

If native relief is installed, stage it from the new clean RT track with the matching texmap, reviewed-family manifest and current YAML. Verify that relief staging preserves geometry, albedo and lightmaps. Keep the accepted native shader/runtime binaries when their behavior has not changed.

## Validate and install

Extract the lightmap PNGs from the **final encoded SBF** and record chunk IDs, dimensions and hashes. Validate references, nonempty meshes, engine mip arithmetic, required companion files, and total unpacked bytes across all seven SBFs. Compressed disk size is not the track heap requirement.

Inspect the rebuilt regions or representative views. Distinguish source defects, texture defects, baked lighting and renderer-specific culling. Offline Blender views do not prove the game's raster state or successful stage loading.

Install transactionally while the game is closed, verify hashes, and preserve rollback data. For native relief, update the accepted receipt and any pinned clean-track/review-track inputs that belong to this slot so a later settings-page Apply cannot restore older geometry. Do not redirect the main slot's pins to an independent lighting alternative.

When the user retires old alternatives or requests disk cleanup, follow the promotion and cache-cleanup guidance in the reference. Keep the accepted main slot and config-page inputs aligned before removing redundant stages.

Run the launcher check without launching the game. Where the config-page build inputs changed, exercise a staged-only rebuild with a temporary gain change and verify both geometry preservation and that live files stayed untouched. Restore no settings that were never installed.

Deliver the source/output paths, patch proof, variant/slot title, RT/lightmap results, unchanged gameplay/runtime settings, backup location and remaining live-test boundary. Update the relevant KB and skills with demonstrated failures and fixes; distinguish owner acceptance from automated verification.
