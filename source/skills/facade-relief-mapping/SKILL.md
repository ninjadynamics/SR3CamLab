---
name: facade-relief-mapping
description: Visually author semantic height maps for facade POM, tracing windows, doors, frames, shutters, balconies, and architectural trim against approved textures. Preserve source alignment and palette-family geometry, compose crop/mirror recipes before deriving normals, and validate convincing relief. Use for facade depth authoring and correction, not texture upscaling or general shader development.
---

# Facade relief mapping

Author a plausible architectural height field from visually identified features. This is semantic height-map authoring: programmatically rasterized, human-reviewed masks, not whole-image grayscale conversion and not recovered metric building geometry. Keep approved diffuse artwork unchanged unless editing it is separately requested.

Read [authoring and validation](references/authoring-and-validation.md) for implementation. For Ultimate Race Lab, read [the SR3 integration notes](references/sr3-integration.md) to locate the existing implementation and its known limitations.

## Inspect before assigning depth

Use the actual approved HD source at native resolution, its filename/context, and the SD source when meaning is unclear. Identify each window opening, glass area, closed door, shutter, blind panel, arch, frame, mullion, sill, ledge, and balcony railing. A dark rectangle may be paint, shadow, a closed shutter, or an opening; brightness alone cannot decide.

Inspect every distinct architectural head. Group palette variants only after confirming identical feature placement, dimensions, crop, and orientation. Similar filenames are candidates, not proof. Reuse one height field across verified aligned tone variants; never adjust height to match their colors. If the diffuse children are misaligned, address that explicitly instead of silently shifting approved artwork or applying an unaligned mask.

## Author interpretable masks

- Trace bounds and contours in source-pixel coordinates with declared dimensions and origin. Use rectangles, polygons, ellipses, arch profiles, and narrow strokes as appropriate. Keep masks keyed by stable texture-family identifiers.
- Assign a consistent wall plane and meaningful relative depths. Glass/open apertures usually recess farther than closed doors or blind panels. Frames, sills, trim, and shutters can sit forward; mullions and railings require distinct depth from the opening behind them.
- Make overlapping shapes' precedence explicit. Recesses must not erase their frames; railing gaps must not become a solid slab. Do not stamp a uniform rectangular recess over a decorated arch or an entire balcony.
- Restrict brightness-based refinement to visually reviewed regions, such as intricate ironwork or rose-window tracery. Never let broad shadows, lettering, paint, stone grain, stains, or upscale noise become facade cavities.
- Rasterize masks with subpixel coverage and only a narrow bevel where warranted. Avoid a broad blur that shifts boundaries or rounds every window into a soft dent. Do not invent extra ornament to make depth more obvious.
- Keep a float or 16-bit scalar master. Declare whether larger values mean raised surfaces and what height corresponds to zero displacement in the shader. Do not normalize every facade independently and thereby change its depth hierarchy.

## Preserve the full mapping chain

The installed material may use a crop, mirror, repeated section, overlay, or composite rather than a source PNG directly. Apply the same mapping operations to scalar heights, then derive tangent-space normals from the final composed height field. Flipping purple normal-map pixels as though they were color pixels can reverse lighting incorrectly.

Treat normal/height data as linear data. A scalar height field drives POM displacement; the purple tangent-space normal map changes lighting. Neither proves the other is working. Protect edge behavior, atlas gutters, alpha footprints, and mipmaps according to the actual material and loader. Preserve flat banners/checkpoints unless relief is explicitly wanted there.

## Review all heads and composed outputs

Produce source/contour-overlay/height/normal comparisons. Use bright cyan outlines on a dark gray review background where helpful. Inspect native-size crops of all openings and complex details, not just a contact-sheet thumbnail. Review the final composed images too, including mirrored variants.

Test matched ON/OFF views with identical camera, albedo, exposure, and filtering. Inspect grazing angles for actual parallax and head-on lighting for retained contrast. Check at multiple distances to expose mip/filtering problems. Do not mistake high-resolution color detail or increased contrast for working POM.

Report authored versus approximate features, alignment problems, packing losses, and what was actually observed in game. Pixel-aligned tracing does not justify claiming mathematically pixel-perfect segmentation. Record source hashes and invalidate derived maps when artwork, recipes, depth settings, or authoring masks change.

Keep source recipes and reusable implementation in the repo; keep extracted copyrighted textures and generated game assets in the project's local content/work areas. Stage changes for review and install only within the user's authorization, preserving a known-good restore path. Skill use itself does not authorize a game launch, publication, or shader rewrite.
