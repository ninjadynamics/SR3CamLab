---
name: blender-uv-retexture
description: Repair stretched or disordered UV mapping on edited Blender scenery while preserving geometry and the original apparent texture scale. Use for retexturing existing terrain or rock shells with existing materials, not mesh remeshing or image upscaling.
---

# Blender UV Retexture

Restore coherent texture placement on a user-edited surface. Match healthy original texture scale, reduce stretching, and preserve the user's geometry.

## Establish the scope

- Inspect the live Blender file, mode, active object, selection, transforms, and UV layers. Capture unsaved edits in a separate backup before modifying UVs.
- Identify the requested surface using its location, materials, connectivity, and the user's view. Material names alone are not a sufficient selector: one imported object may contain roads, scenery, and replacement geometry.
- Define protected surfaces explicitly. For the Mountain workflow, protect the road and tunnel interior unless the user requests them.
- Snapshot vertex positions, topology, material assignments, and per-corner UVs. Preserve an explicit mapping from working faces and corners back to the source.

## Repair mapping

Read [mapping-and-validation.md](references/mapping-and-validation.md) for density estimation, temporary unwrap meshes, chart alignment, and distortion measurements.

1. Estimate texture scale from healthy original faces, excluding stretched and degenerate samples.
2. Unwrap a temporary copy of the requested surface. Reconnect imported duplicate seam vertices in the working copy only where they represent the same surface.
3. Align charts to the original material orientation and normalize their scale uniformly. Choose seams and phase deliberately; avoid independently scaling each face.
4. Apply only the approved source UV loops. Keep unrelated surfaces and detached objects out of scope.
5. Inspect a tiled preview as well as the single texture. Coherent UVs can still expose discontinuous image borders. For nondirectional natural rock, alternating mirrored repeats is an option when appropriate: split triangles at integer UV boundaries before reflecting each cell so interpolation never crosses a fold. Preserve density, winding, per-corner material identity, and surface coverage. Avoid this treatment for text, directional features, or unreviewed relief-map orientations.
6. Verify unchanged geometry, materials, and all UVs outside scope. Inspect overhead and opposing oblique views with the existing textures.

Do not promise distortion-free mapping on arbitrary curved surfaces. Balance visible stretching, seams, orientation, and density; inspect outliers rather than trusting averages.

## Deliver an editable result

Save a new version when that fits the user's versioning workflow. Remove temporary objects and unused working meshes. Include a concise scope and validation report, with residual issues if any.

Restore an editable viewport before handing it back: **Show Overlays on**, source object selectable, and an appropriate mesh selection mode. Overlays may be hidden briefly for beauty previews, but saving them off makes Edit Mode appear broken. Do not overwrite unsaved user work merely to persist a viewport preference.

Retexturing does not imply permission to rebuild or install the game.

For the concrete accepted Mountain tunnel repair, read [mountain-tunnel-case.md](references/mountain-tunnel-case.md). Its bounds, material IDs, and density are historical examples, not defaults for new assets.
