# Accepted Mountain tunnel repair — 2026-10-20

The user manually repaired the exterior tunnel geometry in `mountain.patch3.v18.blend` and requested coherent retexturing at the original 1995 rock scale, without its stretching.

The live file contained unsaved edits. These were backed up before mapping work. Output was saved as `work/blender/mountain.patch3.v19.blend` in Ultimate Race Lab, with a report named `V19 - tunnel UV repair`. The user accepted the appearance. It was not installed in-game by this operation.

## Scope and outcome

- Main course object: `1995 course (RAW2)`, 69,904 vertices and 85,753 polygons at capture.
- Separate SR3 road object protected.
- Rock material family ending in `tex_c1a500f2`; existing shade variants preserved.
- Initial location/material selection: 2,245 faces.
- Final connected exterior shell: **2,226 faces**; 19 detached faces excluded.
- UV-only mutation: vertex coordinates, topology, materials, tunnel interior, road, and every UV outside the target loops remained unchanged.

The object used local Y as height. Hardcoded world-Z assumptions would have selected or measured the wrong surface.

## Successful approach

A temporary working mesh reconnected duplicate positions without welding the actual course. Angle-based unwrap produced coherent charts. Healthy original faces supplied the density reference; chart orientation, scale, and phase were then aligned to that reference.

The healthy reference set contained 1,448 faces. Its area-weighted median density was approximately **0.034736 repeats/metre**, or **one tile per 28.79 metres**, for this square texture. These values belong to this asset and are not a general rock scale.

The candidate mapping's actual Blender-triangle anisotropy was approximately 1.029 at the median, 1.079 at the 90th percentile, and 1.403 at the 99th percentile. Very thin triangles still produced large outliers. The appropriate conclusion was greatly reduced visible stretching, not mathematically zero distortion.

Overhead and opposing oblique textured views confirmed the crown and side flow. Working objects were removed before saving.

## Lessons to preserve

- A geometric component and a UV chart are different: the main shell spanned more than one UV chart.
- Triangle-fan diagnostics produced false extremes on complex polygons. Use Blender's real tessellation.
- A tool timeout did not mean the backup/export failed; files existed and had to be checked before retrying.
- NumPy pickle compatibility caused an avoidable transfer issue; plain Python numeric payloads resolved it.
- Overlays were disabled for the preview and accidentally saved that way. After reopening v19, the user could not see face-selection feedback. Restoring Show Overlays fixed the viewport state. Deliver future files ready for editing.
