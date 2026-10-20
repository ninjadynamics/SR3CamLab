---
name: blender-remesh-cleanup
description: Remesh selected Blender terrain or scenery into well-shaped triangles while preserving shape, UVs, boundaries, and protected geometry; diagnose leftover wires and clean loose geometry. Use for localized game-track mesh repair and remesh validation, not texture upscaling or automatic game installation.
---

# Blender remesh and cleanup

Produce a clean replacement surface, not a second surface over the original. Preserve the user's chosen source, manual edits, material appearance, and protected geometry. A successful triangulation is only one part of the job: inspect the result visually and explicitly check for retired faces, loose edges, isolated vertices, and broken boundary connections.

Read [the technical procedure](references/remesh-procedure.md) when implementing a remesh. Read [the Mountain case notes](references/mountain-lessons.md) when continuing Ultimate Race Lab work or interpreting its historic results. Historic face IDs, names, axes, and tolerances are examples, never selection rules for another scene.

## Establish the actual starting point

- Inspect the connected Blender's file, active object, mode, visible objects, selection, and unsaved state. The filename alone does not prove that its contents match an earlier snapshot. A user can delete faces and save under the same filename while you work.
- Capture the current view before moving it. Identify the exact patch using the selected face, annotated image, surface connectivity, and materials. Do not guess scope from a shared texture or from an object named "1995 course"; that object may contain original and replacement geometry together.
- Snapshot the current geometry and custom data before editing. Preserve manual work in a recoverable file. Compute off-line from that snapshot when practical, then verify the live input still matches before applying results. If it changed, rebase the operation on the new state instead of overwriting it.
- Declare protected surfaces. For Ultimate Race Lab, the gameplay road is strictly protected; pavement is protected unless explicitly in scope. Do not remove road triangles because an overlap detector flagged them. Keep the castle itself out of island-wall remeshing.
- Inspect vertex groups, UV layers, color attributes, normals, sharp edges, material assignments, and other mesh data used by the exporter. A positions-only comparison is insufficient.

## Choose the geometry operation

- For sloped terrain with one height at each projected point, use constrained planar triangulation with height and per-corner UV transfer from the source surface. Preserve outlines, legitimate holes, important folds, and UV/material seams.
- For steep walls or overhangs, use local surface-plane charts or constrained patches. A single overhead projection can collapse a wall or merge different vertical layers.
- Prefer well-shaped, similarly sized triangles, subject to shape and boundary constraints. Do not voxel-remesh, shrinkwrap indiscriminately, flatten a plateau, or globally weld a track to make triangle statistics look better.
- Distinguish strict shape preservation from permission to repair shape. Flipping a diagonal across a nonplanar pair can change the surface. Measure and disclose that change; use a shape-preserving alternative when the request forbids it.
- Replace only the verified source faces. Build an explicit removal set and a replacement-to-source mapping. Do not infer successful replacement from equal face counts or absence of exact duplicates alone.

## Join the perimeter deliberately

Use shared vertex indices at genuine existing contacts. Coincident positions alone do not establish connectivity. Where allowed, split adjacent cliff faces on their existing edges, preserving their planes, winding, UVs, and materials. Avoid changing protected road or pavement topology merely to remove a pre-existing T-junction.

Classify exposed boundaries before filling anything. A legacy coastline may intentionally have an open perimeter. Compare old and new surface coverage and boundary location; do not turn every free edge into a patch. If the task asks to mark new fills pink, identify those faces separately and preserve their intended production material mapping.

## Cleanup is part of the remesh

Deleting faces with `FACES_ONLY` can leave their edges and vertices behind. These loose edges are visible as black wires in Object Mode even with selection cleared and the wire overlay disabled. They are not themselves surfaces and cannot cause surface z-fighting.

After replacement, count and remove obsolete face-less edges and isolated vertices within the authorized scope. Preserve intentional wire objects or geometry used procedurally. For a known surface-only course mesh, a user-authorized loose-geometry cleanup may cover that whole object. Recheck the vertices after deleting edges. Do not use a broad "merge by distance" or global "degenerate dissolve" as a substitute.

For cleanup-only work, verify that every surface retains its coordinates, winding, per-corner UVs, material, shading flags, and relevant custom data. Verify protected objects separately. Keep a backup and save only after these checks pass.

## Diagnose lines before reassuring the user

Inspect the live view and mode first:

- Orange/yellow edges may be selected geometry. Unselected black edges in Edit Mode are normal editing overlays.
- In Object Mode, inspect viewport wire overlays and per-object wire display. If both are off, count loose edges; check for overlapping surfaces if the marks are filled, flickering, or persist with overlays hidden.
- Compare the same view with overlays enabled and temporarily disabled, restoring settings afterwards. This distinguishes viewport drawing from rendered surface defects but does not alone prove that geometry is valid.
- Exact duplicate tests miss near-coplanar faces, intersecting layers, and different triangulations of the same region. Use spatial and surface-coverage checks when those symptoms remain.

State what was actually verified. "No duplicate replacement triangles" does not mean "the entire scene has no z-fighting." If earlier reassurance was wrong, identify the missed test plainly.

## Acceptance and delivery

Verify geometry and inspect at least the affected region in textured, flat/solid, and wire views. Include a deselected Object Mode view with wire display off to catch stray edges. Inspect perimeter joins and silhouette from oblique angles as well as overhead.

Report source and output files, old/new target face counts, measured deviation, coverage differences, boundary joins, remaining intentional open boundaries, loose-geometry counts, and protected-surface verification. Distinguish sampled deviations from proven bounds and numeric equality from byte identity.

Save to the requested version and leave Blender ready for inspection. Do not install into the game, run the patch chain, bake lighting, publish screenshots, or commit/push merely because a remesh is complete. Continue those actions only when covered by the user's task. Existing task-specific authorization remains valid.
