# Material decisions and image-model guidance

Use this reference for new generations and selective corrections. It captures failure modes and useful decisions, not a mandatory visual style for every game.

## Direct upscale, denoise, or deterministic repair?

| Observed state | Preferred starting point | Preserve/check |
|---|---|---|
| High-quality large native master already exists | Reuse it; make a separately sized delivery derivative if needed, retaining the native master | Correct version, alpha, crop and native detail |
| Correct unique structure, attractive brick layout, but noisy brick interiors | Targeted denoise of accepted HD | Brick courses, major chips, windows and silhouette |
| Natural tile/trunk with repeated-upscale “GAN” noise | Direct generation from SD to adequate native resolution | Material, form, scale, broad cracks, silhouette |
| Only palette varies across siblings | One good HD head plus programmatic tone copies | Identical pixel geometry and alpha |
| Border smear or atlas gutter | Deterministic crop/repair when authorized and structurally safe | Repeat axes, all required content |
| Wrong material interpretation or broken text | Regenerate from SD with explicit semantic guidance | Exact identity/layout, complete glyphs |
| Good letters, mirrored in game | Verify mapping and change only necessary text region | Facade/layout outside region unchanged |

Do not stack enhancement passes blindly. Fine artifacts from pass one can become “features” in pass two, producing noisy stone, wiry bark, or faces in knots. Retain both candidates for a small representative A/B comparison when the user has not chosen a direction. In Mountain, the user chose **denoise for unique castle structures; direct SD upscales for tileable rock and tree trunks**. That preference should guide this project, not override a different user's request.

“Denoise” here means remove fine hallucinated detail while retaining authored structure. It does not mean smear the entire picture with blur, plasticize stone, erase weathering, or round all architectural corners.

## Prompt construction

Provide the actual source image, describe its material and use, and identify the exact defects. Keep native outputs large enough for the target. Do not imply that requesting a size guarantees the returned file has that size; inspect it afterward.

A general prompt pattern:

> Faithfully reconstruct this [material/object] game texture at high resolution. Preserve the original canvas, relative feature positions, silhouette, large forms, color balance, contrast and apparent feature scale. The result is a texture used on [surface], not a photograph of a new scene. Add restrained plausible detail inside the existing forms. Keep lighting consistent with the source; no invented relief, edge frames, labels or background changes. [Specific material constraints.] [Transparency/repeat-axis constraints.] Do not introduce new objects or redesign the composition.

Use targeted edit prompts for isolated defects. A long generic negative list is less effective than naming the observed mistake and the protected features. Prompt success is established only by inspecting the output.

## Asphalt and road markings

Asphalt should remain extremely faithful and visually quiet. Typical failed results increase skid-mark contrast, turn fine grain into coarse gravel, add multicolored noise, or create high-frequency detail that shimmers while driving.

- Keep original road paint, skid positions, widths, worn areas, and their low-frequency contrast.
- Ask for sober neutral fine grain and smooth asphalt interiors, without colored speckles or embossed wear.
- Preserve broad wear even when suppressing fine noise.
- If a clean surface and exact paint mask are available, combine them deterministically when authorized instead of having the model reinvent stripes.
- Check only the intended repeat axis for directional roads. Do not blur/copy paint across an axis that must retain a start/end.
- Inspect the packed mip chain and road appearance at distance; sharp source PNGs do not establish in-game quality.

Mountain's first larger smooth-road candidate was still too grainy; a second restrained candidate was selected. This is why a generic “denoise completed” status is inadequate without visual review.

## Rock, grass, soil, and other natural tiles

Natural material may have creative interior detail when its form, scale, palette, and large features remain faithful. It should not acquire decorative bands, embossed edges, huge new fissures, rusty-metal coloration, or a field of unrelated colored patches.

- Prefer direct-from-SD generation if a repeated upscale has accumulated noise.
- If an enhanced atlas already has a superior clean rock interpretation, recover that good head rather than force a worse regenerated candidate.
- Keep palette variants on the same HD geometry.
- Match contrast/tone globally; avoid SD spatial color-field transfers.
- View a 2x2 or 3x3 repetition at expected surface scale. A subtle frame becomes obvious when tiled.
- For a purely natural opaque tile with edge smudges, an authorized small centered transform (roughly 103% was the user's example) can remove bad edge pixels while preserving the canvas. Choose the smallest sufficient inset, document it, and recheck tiling. This is not a universal fixed crop percentage.
- Do not apply that crop to cliffs with required feature alignment unless the resulting placement remains acceptable.

## Tree trunks and foliage cutouts

Trunk interiors need ordinary plausible bark. Excessive tiny knots, curls, holes, carved faces, high contrast crevices, and “2019 GAN” texture are failures, even when the image is sharp.

- For a direct trunk upscale, preserve branch directions, widths, root placement, major knots, gaps, silhouette and pixel scale of the form.
- Reconstruct restrained bark within those boundaries. No added branches or new holes.
- Keep intentional black/transparent surroundings distinct from dark bark. Never remove the object's dark regions with a crude color-key.
- Inspect alpha over black, white, gray, and a contrasting color when needed. Check branch tips and small holes at final resolution and after compression/mips.
- Extend foreground RGB under transparent pixels to avoid dark or colored filtering halos; do not expand visible alpha as a side effect.
- Do not blindly paste SD alpha over misaligned new RGB. Align the object first; preserve antialiasing appropriate to the engine's cutout threshold.

The owner briefly accepted stronger foliage contrast because old photographic scans can lack contrast, then explicitly requested matching SD contrast across the set. The later request governs the Mountain set. Do not preserve a superseded preference silently.

## Sky and water

Sky is a particularly poor place for invented fine structure. Match horizon, broad cloud masses, simple original outlines, and soft cloud edges. Reject fractal wisps, crunchy contours, checker noise, and any unrelated strip at the top edge. Inspect the entire perimeter, not just the central cloud. Confirm the engine's sky projection is rebuilt from the new master.

Water must look like water. An ambiguous low-resolution sea tile was once interpreted as rusty metal. Use the filename, adjacent artwork, course context and SD appearance together. State surface scale explicitly; “waves 3x larger” means fewer, larger features within the same texture footprint, not tripling the canvas or increasing repeat count. Do not infer wave size from “internal scale” when the direction is unresolved.

## Facades, castle walls, and unique structures

Keep windows, doors, rooflines, masonry courses, ornament placement, perspective, silhouette and apparent scale. Individual bricks can gain natural surfaces without becoming noisy. Avoid moving windows while repairing a missing margin.

For accepted castle geometry with excellent brickwork but poor brick interiors, ask the model to remove microtexture while keeping brick boundaries. For a new 4x facade target, generate one sufficiently large family head and derive palette children. Do not independently regenerate each colored facade.

Transparency of a castle cutout is structural: its crenellations and outline should not become rounded or filled. A blurry local enlargement from a tiny cutout fails a request for model-generated high-resolution detail.

## Text, signs, and fences

Text requires character-level inspection. Check every glyph, spacing, baseline, thickness, counters and edges, including words near texture boundaries. A truncated SEGA “S” is not acceptable just because OCR reads the word correctly. Smooth high-resolution lettering should not preserve enlarged pixel stairs when the user asks for no pixel art. Preserve the source design, spelling and layout; do not replace it with a vaguely similar font without review.

Flat print must remain flat. Checkpoint art became embossed in an early pass; add an explicit flat-painted/printed constraint when correcting this. Do not bake a bevel or live-lighting effect into albedo just to make it look “HD.”

Inspect material continuity across the entire object. One fence revision had appropriate weathered posts and rail interior but smooth metallic-looking rail ends. Repair the ends to match the same material/tone without redesigning the whole fence. Compare a repeated fence run if it tiles horizontally.

Game UVs can mirror artwork. Determine whether the whole texture or only readable text requires compensation. For Mountain's LIBRAIRIE facade, only the lettering region was mirrored; the facade and all other pixels stayed unchanged. That exact fix was accepted. Do not impose a global texture flip or a new V flip on the importer.

## Restrained prompt examples

**Castle denoise:**
> Keep this exact castle silhouette, masonry courses, windows and all major chips. Remove the excessive fine hallucinated grain inside the stones. Reconstruct calm believable stone surfaces with restrained variation. Preserve existing color and contrast. Do not soften brick boundaries, invent new relief or change transparency.

**Direct bark:**
> Use the SD reference as the structural source. Reconstruct this same trunk with natural, restrained bark. Preserve every major branch, hole, outline and the scale of the trunk. No extra knots, wormlike swirls, faces, tiny cavities or exaggerated contrast. Keep the background transparent and the edge clean.

**Asphalt:**
> Preserve the exact broad wear, skid marks and paint from the reference. Create calm smooth asphalt with subtle neutral fine grain. Do not intensify the skid marks, add gravel, color speckles, relief or a border. Keep the intended road-direction repetition and original tone.

Adapt these to the actual image and current request; they are not excuses to ignore a visibly bad result.
