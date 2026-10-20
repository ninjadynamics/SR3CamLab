# Implementation and verification

## Snapshot and coordinate system

Use `bmesh.from_edit_mesh` to read live Edit Mode data; `object.data` can lag behind edits. Use a separate BMesh copy for candidate construction. Do not force a mode change just to inspect a scene while the user is editing.

Record object transforms and verify the actual up axis. Mountain's source course used local X/Z for ground and Y for height; do not assume Blender local Z is up. If comparing objects with different transforms, convert to one coordinate frame before distance/angle tests.

Record protected face signatures using oriented vertex positions and per-loop attributes, not vertex indices alone. Removal can legitimately renumber indices. Hash protected standalone objects' coordinates/topology and required attributes separately. Include face material identity, smooth/flat state, UV layers, color data, relevant named attributes, and custom normals where used. Avoid trusting an old hash after manual edits.

Keep masks for target faces, allowed neighboring faces, protected faces, and intentional wire geometry. Face indices are valid only for the snapshot from which they were obtained. Preserve provenance through the operation.

## Constrained triangulation

For a height-field patch:

1. Form its projected triangle union. Check for multiple components, legitimate holes, degenerate projections, and vertically overlapping layers before using that union. Choose the correct source layer rather than arbitrarily sampling the nearest projected triangle.
2. Build a planar straight-line graph from the boundary and constraints. Preserve material boundaries, UV seams, steep folds, corners, and existing attachment vertices. Keep polygon holes when they are part of the original shape.
3. Subdivide long permissible boundary segments using shared parameters. Quantization may help index candidates, but confirm actual distance before treating two points as identical. Choose tolerances from scene units and the smallest meaningful feature; do not globally round positions.
4. Triangulate with an area/edge target and minimum-angle preference. Python `triangle` plus Shapely/NumPy worked for this task, but they are not Blender built-ins. Use a suitable available implementation or isolated dependencies. The historic `pq28a10YQ` settings are not a universal preset: area is in squared scene units, and constrained edges may limit quality.
5. Interpolate heights using barycentric coordinates on source triangles. Preserve boundary coordinates exactly where possible. Measure source-to-output and output-to-source deviation; add constrained samples where needed and retry a bounded number of times. If tolerance is not met, stop applying candidates and change strategy rather than silently loosening it.
6. Transfer UVs per corner and per source side. At a seam, a tiny probe toward the destination triangle interior can identify the correct source side; evaluate the UV at the actual vertex. Preserve material regions explicitly. Do not hardcode a material slot from another file.
7. Preserve source winding using chart normals and source orientation. Imported courses may deliberately have conventions that differ from Blender's apparent "outside". Avoid a global normal recalculation.

For sea-facing walls, use a local orthonormal basis per source face or coherent patch, triangulate there, and map back to 3D. Canonical shared edge subdivisions prevent cracks between charts. Keeping every original diagonal preserves the surface but can preserve poor slivers too; where necessary, retriangulate a larger coplanar region. A noncoplanar diagonal flip needs a measured shape budget.

UV repair is a separate decision from remeshing. Do not smooth away a deliberate discontinuity. The Mountain workflow repaired a few verified wrong-scale fill faces using healthy neighbors; that exception must not become a generic averaging operation across seams.

## Attachments and replacement

- Build each new boundary from existing contacts. Split permissible neighboring edges at inserted rim vertices, and retriangulate those faces in their original plane with barycentric UV transfer. Leave protected neighbors unchanged.
- Reuse shared boundary vertices in the actual BMesh. Local welding is appropriate only for verified coincident intended contacts with compatible data; never merge nearby parallel surfaces or road layers globally.
- Delete the explicit retired-face set before creating the replacement. Preserve shared boundary data and remove only obsolete loose elements afterward.
- Snapshot all unaffected faces and compare them after application. Neighbor splits are separately accounted for and verified, not silently classified as unaffected.
- When testing for surviving retired faces, a replacement can intentionally have identical triangle geometry. Compare multiplicity and replacement provenance; one identical replacement is not a duplicate. Also test projected coverage/intersection to catch overlaps using different triangulations.

## Loose-geometry cleanup mechanics

On a surface-only BMesh, the relevant predicates are:

- Face-less edge: `not edge.link_faces`.
- Isolated vertex: `not vertex.link_edges`.
- Boundary edge: exactly one linked face; this is not a loose edge and should not be deleted as debris.

Collect face-less edges in scope, delete them with BMesh's edge deletion operation, then collect isolated vertices again. In some deletion contexts vertices may already have been removed with their edges, so report total vertex count delta separately if reporting a total. Preserve every face and its per-loop data. Do not save if the surface comparison changes unexpectedly; restore the snapshot instead.

Investigate pre-existing loose elements before deleting them outside the remesh's scope. A procedural construction mesh, wire curve substitute, or modifier input may use them intentionally. For the authorized Mountain course cleanup, the course was a surface mesh and the separate road object was excluded.

## Useful acceptance measurements

| Check | Evidence and limitation |
| --- | --- |
| Outline and holes | Projected union symmetric difference plus ordered boundary/contact comparisons; projection alone cannot detect different heights. |
| Shape | Bidirectional point-to-triangle distances, including vertices, edge midpoints, centroids, folds, and adaptive probes; report a sampled maximum unless a true bound was computed. |
| Triangle quality | Edge-length and area quantiles; quality `4*sqrt(3)*area / sum(edge_length_squared)` is 1 for equilateral triangles. Preserve constraints ahead of a flattering average. |
| Connections | Shared vertex/edge incidence and T-junction checks, not proximity alone. Classify old free coastlines separately from new cracks. |
| Overlap | Exact oriented/position signatures with multiplicity, plus spatial candidates and projected triangle intersection with normal/plane separation tests. Exclude legitimate separate layers. |
| Topology | No new zero-area faces, unwanted loose edges, isolated vertices, or internal nonmanifold edges. Do not require the entire legacy course to be watertight. |
| Preservation | Protected face coordinates, winding, UVs, materials, attributes and shading flags; separate road object verification. |
| Appearance | Textured and solid oblique views, wire view, and deselected Object Mode without wire display. Black lines must be explained by actual data or display state. |

Do not describe re-saved `.blend` files as byte-identical. Validate the relevant reconstructed mesh/export representation deterministically if byte identity is part of a later patch-chain task.
