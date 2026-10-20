# 35 - Faithful Mountain texture upscaling: art, review and delivery

Consolidation of the October 18-19, 2026 Mountain restoration and review session. This article records project decisions and evidence; the reusable operating procedure is [faithful-texture-upscaling/SKILL.md](../../source/skills/faithful-texture-upscaling/SKILL.md), with focused references for atlas recovery, art decisions, review and SR3 integration. No extracted game artwork is included in the skill package.

Confidence: **SOURCE** = inspected scripts/reports/files; **OWNER** = direct user feedback; **OFFLINE** = staged/encoded checks; **IN GAME** = owner test. A successful generation or launcher preflight is not in-game visual acceptance.

## Current contract and acceptance boundaries

- Final requested artwork: general 3x SD, minimum side 256px, facades 4x, preserving aspect ratio. Accepted larger native masters can be reused. Native masters and final artwork dimensions differ from engine storage dimensions.
- Current source set: 178 clean HD PNGs. Yellow diagnostic labels belong only in review copies, never installed textures.
- Owner preference: respectful restrained detail, SD-matched overall contrast, calm asphalt, no added skid contrast/color noise; direct SD enhancement for noisy natural tiles and trunks; preserve good unique castle structure with a targeted denoise pass.
- Palette families share one visually healthy HD head and pointwise tone children. Do not independently spatially register each sibling.
- Owner confirmed the guarded 384 MiB runtime fix allows Mountain to load and race. The later corrected authored-label lighting bake is installed and validated offline; comprehensive visual acceptance remains pending.
- Owner explicitly retained the LIBRAIRIE lettering-only mirror correction. The surrounding facade was never flipped.
- Preserve accepted handling and watchdog OFF. Texture work does not authorize unrelated runtime changes, game launches, or deletion of important work.

## Why the atlas decode failed

The user supplied `scratchpad/SegaRally_Atlas_v2/enhanced_atlases` as the desired HD source and identified `output_textures` and `repaired_textures` as contaminated, although their filenames were useful. Original layout crops were checked against SD. The JSON matched the original cells, but generated atlases had changed cell positions/coverage; applying original rectangles to the enhanced atlas displaced or broke textures.

Recovery therefore located and registered enhanced content per asset rather than trusting one atlas-wide scale. It recorded crop bounds, transform, feature/coverage evidence and fallback regions. A tile with only 80% recovered content retained the correct 80% placement over an authorized locally sharpened SD enlargement; it was not stretched to fill the whole canvas. Such fallbacks required renewed review when the owner later requested model-generated detail at a larger minimum size.

One reported facade (`tex_s1_x0896_y0448_128x128_c0EB`) had gray negative space in the top-right. A single example exposed a set-wide issue, so all files needed perimeter review. Other failures included gray gutters, a polluted sky top row, broken/truncated letters, and natural-material edge smudges. Exact dimensions and low average error did not detect all of them.

Evidence: `scratchpad/atlas-recovery/REVIEW-NOTES.md`, `recovery-report.json`, `input-hashes.json`, alignment/coverage reports and scripts. These are local historical artifacts, not guaranteed permanent public paths.

## Decisions that improved the artwork

| Problem / feedback | Working direction | Important limit |
|---|---|---|
| Repeated enhancement interpreted first-pass noise as real detail | Direct SD-to-target regeneration for natural tiles and tree trunks | Preserve form, silhouette, major cracks and apparent scale |
| Castle brick layout was good, brick interiors excessively noisy | Denoise the accepted HD structure | Keep masonry courses and all structural boundaries; do not globally blur |
| Cliffs became noisy and developed color patches | Recover good enhanced-atlas heads and apply uniform Lab tone transforms | No SD-derived spatial color field; do not amplify source pixel noise to match variance |
| Asphalt gained contrast, gravel-like grain and colored speckles | Restrained asphalt denoise; retain original marks and paint masks | Check driving-distance mips, not just a zoomed PNG |
| Sea looked like rusty metal | Regenerate with explicit water semantics, recover original blue palette | Filename is a clue combined with SD/context, not proof by itself |
| Sea internal scale was unclear | Owner clarified waves 3x larger | Fewer/larger wave features within the same footprint, not more repeats |
| Cloud edges became fractal/crunchy | Direct SD-based reconstruction of broad masses and soft contours | Inspect the entire sky perimeter and projected in-game textures |
| Text was embossed or retained enlarged pixel stairs | Flat smooth high-resolution lettering, complete individual characters | Do not redesign text/font/layout or truncate the SEGA S |
| Fence rail ends changed material | Repair just the ends to match accepted weathered rail | Preserve posts, spacing, tone and repetition |
| Natural opaque edge smudges | Small authorized crop/zoom of clean HD interior, then recheck tiling | Do not apply to required facade/road/text/cutout geometry |
| Cutout fringes and noise | Preserve aligned silhouette, inspect alpha and bleed foreground RGB underneath | Transparent outside is not automatically a missing region |

Early acceptance of stronger foliage contrast was superseded by the owner's later SD-contrast request. The workflow must retain these changes in direction, rather than treating every old preference as simultaneously current.

A second enhancement pass is not synonymous with “more faithful.” The owner rejected blurry local enlargement when requesting minimum-size improvement through the image model. Conversely, a sufficiently large approved native model output can be reduced to a larger final export without another generation. Keep native masters and prompt provenance to make that possible.

## Color-family alignment

The user specifically corrected an interpretation: choose a healthy **HD head**, then align all family children to it; do not independently align them against SD. First check the head's structural correspondence against SD. Once approved, copy its exact pixel grid and alpha, applying only spatially uniform palette/tone transformations to the children.

`atlas-recovery/align-heads.py` records the family head and pointwise Lab parameters, with no child-specific spatial resampling. `resolution-3x-20261019/prepare.py` uses the same principle for new facade heads and natural-material families. Do not assume all similar filenames differ only in tone: inverted text panels or separately painted regions need verified masks or separate treatment.

The October 18 cliff correction restored 34 palette variants from clean `opaque_04` and `opaque_10` atlas crops. Uniform tone transforms replaced the earlier noisy spatial correction. All 178 clean PNGs were reviewed in SD / previous HD / corrected comparisons. Source: `scratchpad/contrast-rock-fix-20261018/README.md` and `report.json`.

## Resolution history and engine compatibility

The requested target evolved from exact 2x to minimum side 128, then minimum side 256, and finally general 3x with facades 4x. Use the latest contract; do not leave small assets at an obsolete target. Aspect-preserving examples:

| SD | Final artwork request | Compatible SR3 storage for this pipeline |
|---|---|---|
| 64x128 | 256x512 (minimum side 256) | 256x512 |
| 128x128 facade | 512x512 (4x) | 512x512 |
| 256x256 natural tile | 768x768 (3x) | 1024x1024, rounded upward |
| 256x128 natural tile | 768x384 (3x) | 1024x512, rounded upward |

The final preparation used 21 new facade heads and changed 134 of 178 clean PNGs; native outputs/prompts were retained. `roadSmoothV2` replaced an overly grainy first larger-road candidate. Changed pairs were inspected in 23 cyan-bordered sheets; composed facade/sky consumers have separate game-output reviews.

Do not encode arbitrary 3x dimensions merely because a DDS decoder accepts them. Rally's DXT upload arithmetic differs at non-power-of-two mips. Current storage rounds upward while preserving content and UV layout. Full diagnosis, deduplication and heap repair: [23_texture_pipeline.md](23_texture_pipeline.md). The in-game loading repair required both engine-compatible data and an adequate track arena, not lower-resolution artwork.

## Review tools and informative error labels

The owner requested dark gray backgrounds, bright cyan image boundaries, SD/HD side-by-side sheets, and an interactive overlay with a draggable vertical divider. Web layout: one texture per row, horizontal fit to 1024px, small semantic groups, individual and group annotation fields. Moving the divider left reveals HD, right reveals SD.

Review every pair, including all four edges, native-size detail, alpha against light/dark backgrounds, and repeated views for tileable materials. Registration/metric scripts do not replace visual inspection. A low error can conceal a disastrous narrow top-edge contamination or broken glyph.

The historical yellow labels were measured before annotation, after area-reducing HD to SD dimensions:

- Pixel error: alpha-weighted mean absolute grayscale difference, divided by 255 and expressed as percent.
- Color error: alpha-weighted Euclidean distance in float Lab a/b chroma only, divided by `255 * sqrt(2)` and expressed as percent.

These measure change, not quality, damage, full Delta E, or alpha fidelity. The user explicitly prioritized appearance over numerical error. Preserve metric definitions with reports; never compare differently defined percentages as though equivalent.

Annotation exports must retain stable texture IDs, group membership, exact top-to-bottom order and reviewed image version. “Same as above” was real feedback and depends on the original visible order. Keep verbatim notes and resolved actions. A later request to hide no-comment/praised assets defined them as approved for that review only. Clearing comments should use a fresh review state without destroying prior exported notes.

## Clean exports and full installation coverage

Separate clean masters from labeled review copies. Never inpaint/erase yellow labels to manufacture a clean release. Finalization must consume the latest hash-checked accepted clean versions; older recovery scripts must not silently overwrite later fixes.

A source PNG can be HD while the game still shows SD. In this pipeline facade recipes, overlay compositions, derived grass/ground and sky projections can store separate encoded images. The October 18 complete refresh rebuilt 106 facade composites, both sky images and the grass dependency; 419 texture chunks changed while geometry/material/collision/lightmaps stayed unchanged. The generic texture updater alone did not cover everything.

Back up installed PNGs, affected SBFs, texmap and baseline metadata; stage all consumers; decode packed output for review; verify install hashes. After exact-duplicate texture consolidation, direct fast refresh is refused until a full unshared stage is regenerated and compacted again. See [23](23_texture_pipeline.md) for the alias/compaction invariants.

For broad shadows after a rebuild, check classification inputs before modifying artwork. The v14 isolated workspace lost authored labels, generated two giant false tree canopies, and changed road shadow coverage from 36% to 54%. Restored labels and cache/size guards fixed that cause. Source geometry edits were preserved; full explanation and pending acceptance are in [17](17_mountain_build_notes.md).

## Evidence map

All paths below are relative to the local project and may eventually be distilled/cleaned; maintained conclusions above and the skill are the reusable record.

| Evidence | Purpose |
|---|---|
| `scratchpad/atlas-recovery/REVIEW-NOTES.md`, `hd-head-alignment.json`, `alignment-audit.json` | Original atlas recovery, metric definitions, family alignment |
| `scratchpad/material-refinement-20261018/refinement-report.json` | Unique-structure denoise versus direct natural-material/trunk pass |
| `scratchpad/contrast-rock-fix-20261018/report.json`, `stage-report.json` | SD tone, restored rock heads, restrained sky and complete runtime coverage |
| `scratchpad/annotation-fixes-20261018/annotation-actions.json` | Resolved ordered owner annotations |
| `scratchpad/fence-rail-fix-20261019/report.json` | Accepted rail material correction |
| `scratchpad/review-round2-20261019/clean` | Approved clean set before larger resolution pass |
| `scratchpad/resolution-3x-20261019/texture-report.json`, `alignment.json`, model manifests | 3x/min256 and 4x facades, native-master provenance and changed files |
| `scratchpad/mountain-v14-20261019/engine-fix/report.json`, `verify_heap.json` | NPOT/compaction/memory correction, original offline evidence |
| `scratchpad/mountain-v14-20261019/lighting-final/report.json` | Latest install hashes, 287.12 MiB SBF total, 22 lightmaps, 178 HD source files, sign regions and label hash |
| `work/texture-backups/` | Durable pre-install states, not disposable cache |

The source skill is maintained under `source/skills/faithful-texture-upscaling`; a byte-identical discoverable copy is installed in the user's Codex skills folder. Updates should change the maintained source and resync/verify the installed copy. No commit or push is implied by this documentation update.
