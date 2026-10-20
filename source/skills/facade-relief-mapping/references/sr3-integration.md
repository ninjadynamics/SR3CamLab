# Ultimate Race Lab implementation notes

Verified from the local repository on 2026-10-20. Paths below are relative to the Ultimate Race Lab repository; inspect the current implementation before reusing assumptions.

## Existing implementation

- `source/standalone/facade_semantics.py`: manually authored source-pixel shapes, mask rasterization, family lookup, and source/overlay/height review sheets. This is the semantic facade path.
- `source/standalone/facade_relief.json`: reference-head mapping and earlier normalized opening bounds. The precise shapes are in `facade_semantics.py`; do not treat the old rectangles as the final pixel masks.
- `source/standalone/pom_maps.py`: material depth profiles, height candidates, and normal derivation. Named facade textures route to semantic masks. Generic luminance inference remains for other materials and a legacy facade fallback; it is not the accepted semantic-authoring method.
- `source/standalone/stage_pom_wide.py`: composes scalar heights through the installed facade/overlay recipes, applies boundary treatment, computes normals afterward, and stages packed maps.
- `source/standalone/pom_dds.py`: continuous-alpha BC3/DXT5 encoding and normal-aware full mip chains. The importer's binary-cutout alpha encoder is unsuitable for these heights.
- `source/standalone/POM.md`: runtime integration, test history, failures, material tuning, and evidence locations. Consult it before installing or changing the runtime.

## Observed authoring choices

Twenty-one heads were visually authored at 512px source height: twenty were 512x512, one 256x512. `render` asserts these dimensions. Its masks use a wall level of 0.84, many glass recesses near 0.28, closed doors near 0.61, frames near 0.93, and sills near 0.98; individual features vary. These values are relative artistic choices, not recovered dimensions or universal presets.

Rasterization is at 2x with BOX downsampling for subpixel coverage. The semantic path avoids adding general facade micrograin. Local brightness refinement is limited to reviewed rail/tracery regions. Palette children reuse head geometry.

The implementation currently dispatches the shapes by the index of a sorted family list. Preserve the existing mapping when maintaining it; adding/reordering families requires updating dispatch consistently. Prefer explicit stable-key dispatch if extending the system, with a regression check for every existing family.

Historic validation covered all 21 native source overlays and 117 composed mappings for 201 facade material instances. It explicitly did not promise perfect segmentation of every small ornament. BC3 compression and mips impose further precision limits. Do not report those historical counts as evidence that a new revision has been reviewed.

## Packing and runtime conventions

The SR3 experiment packs tangent normals into RGB and scalar height into continuous alpha, sampled as linear data. Keep alpha coverage/cutouts separate from this height channel. The selected loader/encoder path requires power-of-two dimensions and a full mip chain; this is an SR3 implementation constraint, not a universal POM requirement.

The final nonrepeating facade composition fades a narrow border toward height 1, its zero-displacement reference. Normal generation happens after composition and this fade. Check rim-touching architectural features for unwanted flattening.

Bruno accepted rock at 4.0x and facades at 1.0x in this build. The documented facade UV depth profile was 0.012. These are starting points for the existing art/runtime, not a requirement to exaggerate new buildings. Live backtick compares ON/OFF with identical albedo filtering; +/- changes the live multiplier and the HUD reports effective material values. Verify that the current build still supports these controls before instructing the user.

Earlier apparent flatness persisted despite activation logs, so matched visual evidence is essential. Source HD changes require rebuilding relief maps. Preserve accepted albedo, geometry, lightmaps, handling, input behavior, and watchdog-OFF preference when staging relief-only updates.

## Evidence and delivery boundaries

Prior evidence was written under `scratchpad/pom-facade-semantic-20261019/`, including `review.html`, `validation.json`, `gpu-lifecycle.log`, and `track/stage-report.json`. These are optional local evidence, not skill dependencies and not assets to publish automatically.

Authoring code and recipes belong in the public repository. Imported textures and game payloads remain local. Backups and important authored work belong in `work`; disposable trials belong in `scratchpad`. A request to create or improve this skill does not authorize rebuilding or installing game assets.
