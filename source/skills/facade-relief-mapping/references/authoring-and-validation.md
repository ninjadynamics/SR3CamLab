# Authoring and validation details

## Manifest and coordinate discipline

For each head, record a stable family ID, source filename/hash, width/height, origin convention, shape list, layer order, and depth convention. Record every child's source hash and the alignment evidence that permits geometry reuse. Derive cache keys from masks, source, transforms, depth profile, and encoder settings as well as filename.

Avoid coupling shape definitions to an index in a sorted list of filenames. Adding a new family can otherwise assign every later mask to the wrong building. Prefer an explicit family-to-recipe mapping. Fail on unreviewed families rather than silently substituting generic luminance depth.

Define whether coordinates mark pixel centers or pixel boundaries. If source dimensions change, scale coordinates, stroke widths, arch radii, and bevel widths consistently and review the result. A 512px authoring recipe cannot be applied unchanged to a 768px or 1024px source. Check aspect ratios; scaling alone cannot correct a crop or displaced child.

## Semantic height construction

Start with a wall plane. Build large architectural recesses first, then frames, mullions, sills, trim, and railings in a deliberate order. Store semantic labels separately if useful for review; the runtime height field is continuous scalar data, not a label image.

Useful distinctions:

- Open window/glass versus dark paint: only the actual opening gets a deep recess.
- Closed shutter versus open gap: the shutter stays nearer the facade plane; the gap behind it recedes.
- Blind panel versus glazed aperture: blind panels are shallower and need not share glass depth.
- Door leaf versus empty doorway: closed leaves usually sit forward of a deep opening.
- Arch and nested molding: trace the curved silhouette and distinct layers instead of a rectangular approximation.
- Balcony: separate the opening, slab, thin bars, and gaps. POM represents a single-valued field, so it cannot faithfully recover stacked disconnected surfaces or arbitrary overhangs. Keep this approximation conservative.
- Tracery: a reviewed aperture mask may constrain local luminance extraction of stone tracery; surrounding masonry and lighting must not leak into it.

Draw at a higher raster resolution, then area-downsample for antialiased boundaries. Supersampling improves mask coverage; it does not add new architectural detail. Preserve frame thickness at the target resolution. Verify that any smoothing preserves shape, rather than eroding openings or creating halos.

The wall/reference value and relative heights must agree with the shader's ray origin and sign. For example, an implementation whose zero-displacement boundary is height 1 cannot use an arbitrary mid-gray border without moving the texture at the rim. Keep values and physical/UV depth scale separate; a value of 0.3 is not a depth in meters.

## Composition, normals, and boundaries

Carry scalar height through the same triangles, UV transforms, crop/mirror operations, and overlay ordering as the diffuse texture. Preserve transparency/cutout semantics separately; height alpha is not cutout alpha. Resolve uncovered pixels using the material's reference surface, not an accidental black pit.

After composition, derive normalized tangent-space vectors from height gradients. Account for width and height when expressing gradients in UV space, and use the actual horizontal/vertical depth scales and tangent convention. Confirm normal-Y and mirrored-UV behavior using an asymmetric test feature. Do not simply flip RGB normal pixels; recomputing from the transformed scalar field is safer when the pipeline permits it.

For repeating materials, use periodic sampling and compatible edge values/derivatives. For bounded facade panels, blend a narrow rim toward the shader's zero-displacement reference only when needed to prevent pulling pixels across boundaries. Review windows and doors touching that rim; fading must not visibly flatten their defining shapes. Do not wrap unrelated atlas tiles into one another. Maintain adequate gutters and clamp/fade behavior for the supported displacement.

Generate a mip chain with linear height filtering and renormalized normal vectors. Thin mullions may disappear at low mips; inspect the transition and avoid sharpening that invents relief. Validate packed data with an independent decode. A format that stores height in alpha must preserve continuous alpha values; a binary-cutout encoder will destroy the depth field.

## Review and runtime evidence

For each head, inspect the source and overlay at native resolution. Mark boundaries from the actual rasterized height field, not just the original vector shapes, so rasterization errors are visible. Check opening corners, arch peaks, trim thickness, rail gaps, and features at texture edges.

For each composed mapping, compare final diffuse and final height alignment before compression and after decoding. A good source mask does not prove a mirrored/cropped/overlaid result is correct. Check missing mappings, wrong family assignment, stale-cache reuse, and material fallback.

Matched runtime checks should establish:

1. ON/OFF keeps diffuse filtering, exposure, camera and underlying lighting fixed.
2. Recesses move in the correct direction with camera motion; grazing angles reveal relief without swimming or tearing.
3. Depth gains affect displacement and normal relief coherently; material-specific tuning is not a reason to distort the height mask.
4. Direct light does not wash out the approved diffuse contrast, and self-shadowing does not double-darken baked lightmaps or ambient lighting indiscriminately.
5. Linear/bilinear filtering and mip transitions remain intact; height is not accidentally sampled as sRGB.
6. Stage loading, exit, reset, and normal gameplay remain stable if runtime or asset installation changed.

Shader activation logs and offscreen fixtures are useful supporting evidence but do not replace visual game confirmation. If only offline authoring was requested, report that limit without launching or installing anything.
