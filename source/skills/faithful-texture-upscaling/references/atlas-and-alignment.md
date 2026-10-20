# Atlas recovery, registration, and color families

Use this reference when the source consists of enhanced atlases or when visually equivalent variants have drifted apart.

## Source authority and inventory

Keep four identities separate:

| Source | Authority | Frequent trap |
|---|---|---|
| SD originals | Asset identity, layout, silhouette, original palette and scale | Treating their low-resolution noise as desirable new detail |
| Original atlas and layout | Original cell locations and filenames | Assuming generated atlas geometry is unchanged |
| Enhanced atlas/native generation | Candidate HD pixels | Trusting its gutters, cell dimensions, labels, or completeness |
| Accepted clean master | Current approved visual decision | Replacing it with an older “final” script or a labeled review PNG |

Hash input files before the pass. Record all expected filenames from the SD set and legitimate source metadata. Compare output names/counts, dimensions, alpha mode, duplicate names, and missing/extra files. A contaminated output folder can be a filename reference without becoming an artwork source.

In Mountain, the two old output folders had valid names but displaced/broken content. The original layout JSON crops agreed with SD; the enhanced atlases had changed layout. The failure therefore could not be fixed by blindly applying one new global scale to all JSON rectangles.

## Locate enhanced pixels

1. Confirm the layout rectangle against the original atlas/SD, accounting for padding and coordinate convention.
2. Locate the corresponding structure in the enhanced atlas. Search nearby first but allow for nonuniform cell changes. Check repeated patterns and neighboring similar tiles explicitly.
3. Compare low-frequency luminance/edges as well as RGB. A palette shift should not defeat structural matching; a lookalike adjacent facade should not pass because its colors match.
4. Fit the simplest transform supported by evidence: translation/crop, uniform scale, then constrained affine if necessary. Avoid free-form warps that bend straight architecture or invent local correspondence.
5. Require spatially distributed features. Four matches around one window do not prove the whole facade's scale/crop. Inspect top, bottom, both sides, and internal landmarks.
6. Create a coverage mask for genuinely recovered pixels. Gray background, atlas labels, margins, and cells from neighboring assets are invalid coverage even if the matcher finds them convenient.
7. Store crop bounds, transform, correspondence quality, coverage, and visual decision per asset. A high score does not override an obvious mismatch.

If an enhanced tile contains only 80% of the original texture, do not stretch that 80% over 100% of the canvas. Align it to the correct region. If the user permits fallback, place it over a locally sharpened aspect-preserving SD enlargement, blend only where needed, and retain the coverage map. Review the junction at native size. If the missing region is prominent, architecture, text, or a silhouette, regenerate that region or the tile rather than hide it with a blurred background, when generation is within the current scope. For recovery-only work, retain the partial recovery and report missing coverage instead of silently expanding the task. Later minimum-resolution requests may invalidate an earlier SD fallback as a final result.

## Diagnose bad margins before cropping

Typical contamination:

- A uniform gray strip occupying real plaster/rock area.
- A top sky row containing an unrelated atlas texture.
- A washed-out border from resampling outside the cell.
- An apparent frame that repeats conspicuously in game.
- Parts of a facade missing even though its canvas dimensions are correct.

Different problems need different repairs. A facade margin may need a small inpaint or continuation of the corresponding material without moving windows. A natural opaque tile may tolerate a small centered crop/zoom. A cutout's transparent exterior may be entirely intentional and must not be filled. Do not use “remove empty borders” as a global rule.

Mountain's `tex_s1_x0896_y0448_128x128_c0EB` had a reported top-right defect; it was one example, not permission to audit only that file. Expand read-only review to the relevant delivered set and families once a systemic extraction defect is found. Correct assets within the authorized scope; report unrelated affected assets rather than silently editing them.

## Alignment to SD

The requirement is corresponding **structure**, not equality of all pixels. New legitimate HD detail should differ at fine scales. Compare reduced HD and SD, edge overlays, and slider reveals for:

- Window/door centers and wall divisions.
- Letter extents and baseline.
- Road stripe/skid placement and width.
- Horizon and broad cloud masses.
- Object bounds, roots, branches, holes, and transparency.
- Scale and orientation of large natural features.

Run registration on low-frequency images to avoid matching hallucinated fine grain. When using normalized square coordinates, convert the transform back into the real rectangular image coordinates correctly. Check scale, determinant/reflection, shear, translation, introduced blank areas, and interpolation effects. Refuse an implausible transform rather than force a score. Numerical thresholds from one image family are not universal acceptance criteria.

If a transform is uncertain, retain the original candidate and flag it for visual review/regeneration. Never record “aligned” solely because an optimizer ran successfully. For cutouts, inspect both RGB structure and alpha; copying the old silhouette onto misaligned RGB creates a clipped or ghosted object.

## One healthy HD head, exact color-only children

For confirmed palette-only families, especially when the current user requests shared-head alignment, **align siblings to a good HD head**, rather than independently fitting every sibling to its SD copy. This was the explicit Mountain requirement; preserve a different current user contract when applicable.

1. Prove that members share layout/content. Similar names or palette suffixes suggest a family but are not sufficient.
2. Choose the head by visual completeness, clean detail, correct edges, and coverage. Error scores are only supporting clues.
3. Repair/register/size the head once. Keep its accepted geometric transform fixed.
4. Copy the exact head pixel grid for every child. Apply a spatially uniform color/tone transform; preserve the head alpha exactly where the family shares alpha.
5. Estimate target tones from reliable child SD or accepted child references, excluding transparent matte, labels, gutters, clipped highlights, and unrelated parts.
6. Record head hash, tone parameters, alpha identity, and absence of child-specific spatial resampling.
7. Review the entire family in color and grayscale. Geometry should coincide; palette differences should match the intended family.

A per-channel affine transform in floating-point Lab is a useful starting point: `out_c = scale_c * head_c + offset_c`. Robust medians/quantiles or matched valid samples can reduce outlier influence. Clamp unreasonable scales and inspect clipping. A single global transform is not appropriate for inverted sign panels or variants with independent painted regions; use a verified shared glyph/region mask or separate the family.

Avoid an SD-derived spatial color field laid over the HD surface. It can reproduce source blocks, create color patches on rocks, or emphasize microcontrast. Also avoid matching SD variance blindly: low-res noise is not a target texture characteristic. Match broad tone/color, then judge the surface visually.

## Resolution and provenance manifest

Useful per-file fields (adapt to the project):

```json
{
  "file": "texture.png",
  "sd_sha256": "...",
  "sd_size": [128, 128],
  "semantic_material": "plaster facade",
  "family": "facade_07",
  "head": "texture.png",
  "native_master": "models/facade_07.png",
  "native_master_sha256": "...",
  "artwork_size": [512, 512],
  "engine_size": [512, 512],
  "repeat_axes": [],
  "alpha_mode": "opaque",
  "crop": null,
  "registration": {"method": "identity", "visually_checked": true},
  "tone_transform": null,
  "enhanced_coverage_percent": 100,
  "clean_sha256": "...",
  "review_status": "reviewed",
  "composed_consumers": []
}
```

Do not manufacture confidence or hashes. A real manifest can use `pending` or `unknown`. Keep source paths relative where portable; local case-study paths belong in a local report. Preserve a small manifest and accepted masters rather than every failed giant atlas forever, but do not delete source/manual work without authorization.
