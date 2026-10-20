# Mountain remesh case notes

These are historical findings from Ultimate Race Lab on 2026-10-19. They explain decisions and failures, not a recipe to select those same indices again.

## Scope and local conventions

- Project: `F:\Jogos\Ultimate Race Lab`; important authored Blender files live in `work\blender`. `work` is not disposable. `scratchpad` is for experiments and temporary recovery copies.
- The user manually repaired v15 and saved v16. That manual source was the starting point for the castle-island sea-wall remesh. The castle and existing island ground were excluded.
- The course object was called `1995 course (RAW2)` even after custom patches had been incorporated. Its name did not imply that every face was original geometry.
- The separate gameplay road was `SR3 road (the game's own - hide with H)`. Never remove it on an overlap detector's recommendation. Materials and names are cues; verify actual scope.
- v17 held the castle-island wall remesh; v18 added the two grass plateaus left of the road after town. Those versions are historical, not a guarantee of the current source.
- For Bruno, "all cores" means all available workers minus one to keep the desktop responsive. Do not launch a heavy bake or remesh for a simple inspection or cleanup.

## Castle-island walls

278 source faces became 3,040 triangles. Median edge length was about 3.81 scene meters. Boundary displacement measured about 0.0000062 m. Local diagonal repairs had a measured maximum surface deviation around 0.1599 m; this is why "unchanged shape" must be qualified and verified, not inferred from a matching outline. Such a repair is not suitable for a new strict-zero-change request without a different method or permitted tolerance.

## Two grass patches

154 and 396 source faces became 673 and 1,423 triangles, respectively: 2,096 total. The triangle size was roughly 3.6-3.8 m typically, with constraints allowed to override uniformity. Heights were sampled from the subtly sloping original surfaces, not flattened. Maximum probe differences were about 7.91 mm and 9.94 mm; these were sampled values, not exhaustive mathematical bounds.

Projected coverage stayed equivalent within floating-point noise. Twenty-three adjacent cliff faces were split into 52 coplanar faces to share rim vertices. Ninety-nine boundary segments had actual neighboring face connections. Eighty-three free perimeter segments were existing exposed coastline, not automatically new holes. One protected pavement T-junction was deliberately retained instead of altering pavement topology.

One fully overlapped source triangle was removed after verifying unchanged surface union. Three verified wrong-scale UV fills were repaired. All 84,334 faces outside the permitted changes were checked for preserved geometry, UVs, materials, and shading flags. The separate road was checked independently. These counts describe that exact snapshot only.

## Failure: the misleading black lines

The user saw lines after deselecting everything. The initial response incorrectly treated the concern as selected mesh edges. An exact duplicate-face check also missed the cause: it asked the wrong question.

Live inspection in Object Mode showed wire overlays off and per-object wire display off, yet visible wire triangles remained around the castle island. The mesh contained 396 face-less edges and 285 isolated vertices. Face deletion had left obsolete wire geometry that the face-focused remesh checks did not catch.

The cleanup removed the loose elements, verified all 86,055 then-current faces retained surface coordinates/UVs/materials/shading, verified the separate road unchanged, saved v18, and visually confirmed that the lines disappeared. The user had edited the scene between earlier remesh validation and cleanup; the different total face count was not attributed to cleanup.

Lessons to carry forward:

1. Count loose edges and isolated vertices before and after every replacement operation.
2. Include deselected Object Mode in visual acceptance, not just a selected wire preview.
3. A face-less edge is not a z-fighting face. Conversely, no exact duplicate triangles does not prove there are no near-overlaps.
4. Reinspect the user's current state before diagnosing; do not treat an earlier screenshot or saved report as live evidence.
5. Preserve current manual edits. Cleanup snapshots and comparisons must use the current state, not restore a previous face count.
6. Separate what was checked from what was assumed. When a test missed visible debris, correct the explanation and the acceptance test.
