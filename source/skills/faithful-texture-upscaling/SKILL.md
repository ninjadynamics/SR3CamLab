---
name: faithful-texture-upscaling
description: Restore and upscale existing game textures faithfully, recover tiles from enhanced atlases, align palette variants, review SD/HD pairs, and validate engine-ready installation. Use for texture enhancement or repair; not for unrelated image generation or geometry editing.
---

# Faithful texture upscaling

Produce high-resolution artwork that retains the identity, layout, material, silhouette, palette, and apparent feature scale of the source. Judge the result visually. Numerical error is diagnostic information, not an acceptance score. A smooth but misregistered facade, a sharp sea interpreted as metal, or a beautifully detailed but noisy trunk is a failed result.

This skill distills the Ultimate Race Lab Mountain texture restoration of October 2026. Its general workflow applies elsewhere; its minimum dimensions, UI preferences, and engine addresses do not become universal requirements. Current user instructions override the historical project profile.

## Select the relevant reference

- Recovering atlases, choosing sources, checking alignment, or producing tone siblings: [Atlas recovery and registration](references/atlas-and-alignment.md).
- Generating or correcting art, including roads, rocks, trees, sky, text, and repeated upscales: [Material decisions and prompts](references/material-decisions.md).
- Building contact sheets, collecting ordered notes, computing informative metrics, or delivering clean files: [Visual review and delivery](references/review-and-delivery.md).
- Packing/installing SR3 content, diagnosing partial SD coverage, loading freezes, crashes, or broad shadow regressions: [SR3 integration lessons](references/sr3-integration.md).

Read only the references needed for the current phase. The SR3 reference includes the past project's specific art preferences and dimensions; do not impose those on other games.

## Establish the source and the current contract

Identify the immutable SD originals, the latest approved HD artwork, native image-model outputs, review copies, and installed files. They have different authority. Never use a labeled review image as a clean master. A folder named `repaired` does not establish correctness.

Record a manifest keyed by exact filename or stable asset ID. Include source hashes, source dimensions, semantic material, alpha mode, intended repeat axes, family/head membership, target size, chosen master, transforms, output hashes, and review status. Include composed/derived consumers if installing into an engine.

Resolve these from the conversation and project before asking for clarification:

- Which output root is writable, whether installed/manual work must remain untouched, and whether installation is already authorized.
- Target scale, minimum side, category exceptions, aspect ratio, and any maximum engine dimension. Keep **artwork size** distinct from **engine storage size**.
- Whether missing areas may use a locally sharpened SD fallback or need regeneration.
- Whether the user wants diagnostic labels, clean files, a review page, or all three.
- Which art has already been accepted, and which corrections remain.

For a minimum-side policy, the usual aspect-preserving target is `s = max(category_scale, minimum_side / min(sd_width, sd_height))`, then round the two scaled dimensions consistently. Preserve a larger approved master unless the current request calls for a reduction. If the user asked for image-model detail at the target size, local enlargement alone does not satisfy that request. Reuse a sufficiently large accepted native master or regenerate.

## Recover and plan before generating

Inspect SD and existing HD side by side. Use names, neighboring textures, mappings, and in-game references to identify material when tiny pixels are ambiguous. Filenames are clues, not proof. Do not confidently label a decorative strip as road tread based only on resemblance.

For enhanced atlases, verify the layout against the original SD atlas, then independently locate the tile in the enhanced atlas. Generative outputs may move, crop, repeat, or omit cells even when the original layout JSON was correct. Reject gray gutters, neighboring cells, and displaced fragments before fitting to the target canvas.

Classify each asset as:

1. Approved master reusable at target size.
2. Good enhanced content needing deterministic extraction, alignment, edge repair, or tone adjustment.
3. Good structure with excessive invented microdetail: a restrained denoise candidate.
4. Wrong content, broken letters, missing coverage, or accumulated artifacts: direct SD-to-target regeneration candidate.

Group genuine palette-only families. Select one healthy HD **head** visually; derive children from that geometry using pointwise color/tone transforms. First verify the head's structural placement against SD, but do not independently register each child against SD. Different windows, shadows, ornaments, or alpha silhouettes mean the variants are not automatically one color-only family.

## Generate selectively and retain provenance

Use the available image generation/editing tool according to its current instructions. Do not promise a marketing model name that the tool does not expose. If an image skill is available, apply it for generation/editing. Keep native outputs and exact prompts so a later size increase can reuse existing detail.

Prefer individual textures or small coherent groups for repairs. A large atlas is appropriate only when extraction can be proven. A request for a faithful upscale is not permission to redesign typography, add relief, sharpen every crack, or normalize every surface into one material.

Provide semantic material, target shape, exact invariants, and a short list of observed defects. Choose direct-from-SD generation for noisy natural tiles/trunks when earlier upscales have accumulated fake detail. Preserve accepted large-structure geometry with a targeted denoise pass when that is the user's chosen direction.

Task authorization may already cover necessary deterministic steps; do not ask repeatedly for permission already given. Follow the available image tool's current rules, including any requirement for an explicit user request before local image editing. When deterministic processing is authorized, use it for exact crops, registration, shared-head tones, alpha restoration, seam treatment, and export sizing. Do not quietly substitute a local interpolation pass for requested generative enhancement. Do not keep regenerating an accepted head just to obtain different palette siblings.

## Finish without losing identity

- Align HD structure with SD at corresponding normalized coordinates, using low-frequency structural evidence and visual confirmation. Validate transforms, not just their correlation score.
- Diagnose apparent alpha failures by sampling the exact source/composite UV and alpha. An opaque black/neon fragment may be contaminated atlas RGB even when alpha is correct. Do not make dark pixels transparent or change all black colors as a shortcut.
- Remove atlas gutter/edge contamination. For opaque natural material and with user authorization, a small crop/zoom of the clean HD interior can remove smudged margins. It is unsuitable for clipping lettering, architecture, road markings, or cutout silhouettes.
- Match source tone/contrast with restrained, spatially uniform transforms. Do not transfer a low-resolution color field into rocks; this can create mottled patches and amplify noise.
- Preserve cutout shape, holes, and coverage. Inspect alpha against both light and dark backgrounds and after mip/compression. Foreground RGB should extend under transparent edges without adding visible halos.
- Inspect repeat boundaries with a tiled preview on the actual repeat axes. Edge equality alone is insufficient; visible repeated bands, gutters, and bright frames still fail.
- Verify letters individually and through the actual UV orientation. A mirrored text region does not justify mirroring the entire facade.
- Export clean artwork separately from annotated review copies. Never erase labels from a labeled PNG and call it the clean original.

## Review, revise, and install within scope

Build visual SD/HD comparisons at matched display size, with filenames, actual pixel dimensions, and visible image boundaries. Inspect every pair in the delivered/affected set; broader read-only diagnosis does not authorize unrelated edits. Use native-size crops for fine detail and tiled/alpha views for the applicable assets. Log inspected filenames and unresolved issues. Large pages or contact sheets are not evidence of inspection unless they were actually viewed.

Keep annotation identity and ordering stable, including group-level notes and inherited “same as above” context. After a correction, review the modified family and all composed consumers. Do not overwrite later accepted corrections with an older finalization script.

When a configuration page can rebuild installed content, refresh its pinned clean input track and matching recipe/source manifest with the new build. Otherwise a later settings Apply can silently restore old geometry. Preserve approved family depths, exceptions, and height maps; update provenance hashes only after verifying the new inputs. Never bypass mismatch assertions.

If installation is authorized, back up the current live set and metadata, build a complete stage, validate encoded outputs and memory budgets, install while the relevant game is closed, and read back hashes. Diagnose engines with their actual loader rules: valid PNGs or standards-compliant DDS files do not prove the game can load them. Preserve unrelated handling/runtime/settings changes.

A generated-image task does not itself authorize modifying an executable. The SR3 runtime patch in the case study was a separately authorized repair with exact-build checks, not a reusable blanket action.

Report the clean/review/install locations and what is verified: source art review, encoded output review, installation hashes, launch check, and actual play test are separate evidence levels. If the user is away, finish the authorized work and leave a concrete reviewable result; do not claim visual/gameplay acceptance on their behalf.
