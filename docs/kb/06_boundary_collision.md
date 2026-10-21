# 06 - Collision: what there is, and the TrackBoundary wall BSP

Tools: `tools/import/core/bsp.py` (parser, point classifier), `bsp_build.py` (serializer, corridor builder, checks).

## Where collision comes from
| Source | Physics class (strings in the exe) | Data |
|---|---|---|
| The road | ColRepLandscape / ColRepLandscapeDeformable | TrackDeform chunk (04) - no separate collision mesh |
| Invisible tunnel around the road | TrackBoundary / ColRepBSP, object name "Object_Track_Boundary" (0x5B2D78) | kind 5 chunk, master_gfx root +0x34 |
| Props | ColRepConvexHull etc. | game object files |

The scenery meshes (kind 11 tree) are visual only (LIKELY: no physics reader of them was found).

## Is the boundary required?
exe 0x5C9B0A: `edi = [gfxroot+8]; if (edi) 0x4557A0(edi) -> 0x466680 -> 0x46C440 -> 0x42C7F0`. With root +8 = 0 no
TrackBoundary object is created. VERIFIED by disassembly; in-game behaviour without walls UNKNOWN (ladder step3).
Root +8 is a fixup pointing at root +0x34, which holds the ref to the chunk.

## What the geometry is (VERIFIED numerically on Stadium4/Lakeside4)
A closed TUNNEL: vertical wall quads along both sides of the road (2 triangles each), plus floor triangles (normal +y,
about 2 m below the road) and ceiling triangles (normal -y, about 10 m above). All polygon normals point INTO the
drivable space. Stadium4: 512 wall + 256 floor + 256 ceiling triangles, y from -2.0 to 10.4.
Points 1 m above the road centre always land in a leaf whose faces are all in front (257/257 Stadium, 1084/1103
Lakeside); points outside the road edge, above the ceiling or below the floor land in solid leaves.

## Chunk layout (VERIFIED: `serialize(to_tree(parse))` is byte-identical on all 6 tracks)
Header 0x40:
| Off | Meaning |
|---|---|
| 00 | 1 |
| 04 | nKd: kd nodes (type 2) |
| 08 | nPlanes: plane nodes (type 1) |
| 0C | number of type 3 leaves (solid) |
| 10 | number of type 4 leaves (empty) |
| 14 | nLeaves: leaves with faces (type 5) |
| 18 | nPolys |
| 1C | nSurf |
| 20 | ptr kd records (0x2C) |
| 24 | ptr plane records (0x18) |
| 28, 2C | ptr (both equal +30: types 3 and 4 have no record) |
| 30 | ptr leaf records (0xC) |
| 34 | ptr node type list (u32 per node) |
| 38 | ptr polys (0x44) |
| 3C | ptr surface ids (u32) |

File order: header | kd | planes | leaf records | per leaf: face planes (16 bytes each) then face surface indices (u32
each) | type list | polys | surface ids. Fixups: the 8 header pointers + 2 per leaf record.

Records:
- kd (0x2C): `f32 minx, minz, maxx, maxz; u32 ix, iz; u32 hasPlane (always 1); f32 plane[4]`. (ix, iz) = index of the
  cell in the grid of its own depth: splitting on x makes children (2ix, iz) and (2ix+1, iz), on z (ix, 2iz) and
  (ix, 2iz+1). SEGA splits x, z, x, z (4 levels = 4x4 cells); the last level carries the first plane of the cell's
  sub-tree instead of an axis plane. VERIFIED on Stadium's 24 nodes.
- plane (0x18): `f32 nx, ny, nz, d; u32 flag; u32 surface index`. flag 0 = the plane of a wall/floor/ceiling polygon
  (same orientation as the polygon, 100% of 2182 in Stadium), flag 1 = auxiliary splitting plane (no polygon, surface 0).
- leaf (0xC): `u32 nFaces, ptr planes, ptr surface indices`. Every face plane equals a polygon plane with the same
  orientation (2700/2700 in Stadium).
- poly (0x44): `u32 3, f32 plane[4], 3 x f32 xyz, 12 zero bytes`.

## Tree semantics (exe 0x42AD80, the linker called from 0x42C7F0)
- The type list is the tree in PRE-ORDER. For a node of type 1 or 2 the linker reads the next type as CHILD A
  (attached through vtable +0x1C, recursing if it is a node), then the following sub-tree as CHILD B (vtable +0x20).
  Records of each type are consumed in order from their own array. Root = kd record 0. VERIFIED (disassembly; and
  (nodes of type 1+2) + 1 = (leaves of type 3+4+5) on all tracks).
- CHILD A = negative side of the plane (n.p + d < 0), CHILD B = positive side. VERIFIED on the kd level (child boxes
  lie on the matching side) and consistent with every point test below.
- Type 3 = SOLID leaf, type 4 = EMPTY leaf, type 5 = leaf carrying the polygon planes that touch its cell: all face
  values >= 0 for a free cell, all <= 0 for a solid cell next to a wall. LIKELY (statistics: random points in Stadium
  never reach type 4 and the road never reaches type 3; in Lakeside open space far from walls is type 4).
- Typical shape: a polygon-plane node has child A = solid (type 3) and child B = leaf or more planes.

## Surface ids
nSurf texture-like ids; each face/plane holds an index into this table. They are resolved through
`[0x9C4DA0]->vtable+0x20` into a boundary material (Armco, Brick, Tyres, ...); see 10_surfaces.md, last section.
Stadium: ee64dc3d floor/ceiling (and some walls), e2671eda and 3ac3a983 walls.

## Builder (`bsp_build.build_corridor`)
Input: two closed polylines (left and right barrier lines, same number of points), floor and ceiling heights, surface
indices. Output: a chunk with the same record types as SEGA's.
1. Wall segments get planes facing into the corridor (the union of the quads between the two lines).
2. 2D build over the plan view: 4 kd levels (x, z, x, z, median of the cell box), then auxiliary axis planes (flag 1)
   while a cell holds more than 4 wall pieces, then wall planes as splitters (flag 0, longest piece first).
   A cell without wall pieces is free if its centroid lies in the corridor, else solid (type 3).
3. Every free 2D cell becomes: floor plane node (A = solid) -> ceiling plane node (A = solid) -> type 5 leaf holding
   the wall planes on its edges + floor + ceiling.
4. Polys: 2 triangles per wall segment, 2 floor + 2 ceiling triangles per corridor quad.
Differences from SEGA's own builder (not reproducible: their splitting heuristic is unknown): no type 4 leaves, solid
cells never carry faces, floor/ceiling are single horizontal planes for the whole track (SEGA's follow the road
height segment by segment), deeper/shallower trees (Stadium: SEGA max depth 33 / mean 14.5; ours on the same road 22 / 13.8).

Checks run at build time (work/out/build_log.txt): 6000 random points per track agree with the geometric definition
(0 mismatches on every build); every road centre point 1 m above the road is free; the chunk parses back with the
independent parser and re-serializes identically.
NOT verified: that the engine is happy with solid leaves without faces and with free leaves that list distant-looking
planes; contact behaviour at wall joints. Ladder step10 swaps only this chunk into the original Stadium4.

## Terrain-following floor and ceiling (third package)
`build_corridor(..., heights=..., below=, above=)`: every free plan-view cell gets its own horizontal floor plane 2 m
(+ half the largest cross-fall) under the lowest and a ceiling 10 m above the highest road point of the corridor
quads it overlaps. Stepped, not sloped like the original chunks. Checks in the build log: every road point (centre and
2 m inside both edges, 1 m above the road) is free; 12 m below and 24 m above the road is solid. Desert4's own road:
1384 cells, tunnel height 13.9-18.7 m. Classic Mountain: 1520 cells, 13.2-16.8 m (the flat version was 81 m tall).

## In-game results (2026-10-06 / 07)
- A track WITHOUT the boundary chunk loads ("no-walls" is on the owner's list of things proven in game). What exactly
  happens at the road edge then was not written down (UNKNOWN in the sources).
- The authored wall BSP works: "authored wall BSP" is on the same list, and on imported Mountain the owner reported that
  "driving in general, checkpoints, collision detection" work well. VERIFIED in game. The worries listed above (solid
  leaves without faces, no type 4 leaves, stepped floors) did not show.
- Where the corridor stands for an imported course and what has no collision: 14_importer.md (last lines).
- Not a collision fault: the crash at 0x5DE16C "when a wheel touches the road" came from missing grass arrays
  (02_track_files.md).


## Mountain wall offset repair (2026-10-21)

User evidence: `screenshots/SR3_20261021_085226.png`, car position
(327.3574, 16.1926, 50.7400), forward (-0.4752, -0.0147, 0.8798).
This race used native SR3 handling, so the displaced collision wall is separate
from the SRC handling fixes. The screenshot alone does not prove a particle-emitter bug.

The old importer used `corridor_lines(..., every=4, inset=0.5)`: a wall half a metre
inside the physical road, connected by chords that skipped three road slices.
On the rightward ray at the screenshot, the installed BSP was 1.811791 m from the
car reference point. The first visible vertical stone wall was 2.630698 m away:
0.818907 m of visible-wall/BSP separation. The native car hull is separate from
this point ray; do not interpret these as car-body-to-wall clearances.

Mountain's recipes now use `boundary_step: 1`, `boundary_inset: 0.0`, and
`boundary_union: true`. The boundary follows the outer footprint of the existing
TrackDeform road triangles. It does not widen or move any road vertex. Raw edge
polylines fold over themselves at two tight bends: simply increasing their sampling
still left 13 real classification errors in near-edge probes. `road_footprint.py`
splits the existing triangle-edge arrangement and keeps only pieces separating
supported road from outside, avoiding internal collision walls at those folds.
The union path rejects overlapping road decks separated by more than 1 m instead
of flattening overpasses. Mountain checked 1,617 such plan-near pairs: no separated
decks overlapped. Legacy recipes retain their old defaults; rebuilding the installed
original with those defaults reproduced its 802,092-byte BSP and fixups exactly.

Corrected ray distance: 2.469959 m, leaving 0.160740 m between the protected road edge
and visible wall. This residual is explicit: do not push the collision wall farther
out without proving the wheel-contact footprint remains supported. No car hull,
particle emitter, physics road, rendered wall, texture, shader, or RT lightmap changed.
The likely particle-position improvement from aligning its collision surface still
requires an in-game check; no gameplay was launched during this repair.

Validation and reproducibility:

- `rebuild_boundary.py SOURCE STAGED --report REPORT` refuses in-place writes,
  changes only BSP chunk `b0d1e001`, independently parses/reserializes it, then rereads
  the staged SBF and checks every other chunk's data, type, fixups, refs and flags.
- Road `44e94c8c` SHA-256 remains
  `dd9240f9eda8f669f05f6d9fea83d9f1c041f7f939f981f849b412ee13d9b101`.
- 52,635 tests against the serialized BSP: both sides of every edge at 2 cm / 10 cm,
  plus samples across every slice. Zero mismatches against the actual road footprint.
- 3,510 centre/interior tests free; their below-floor / above-ceiling probes solid.
- 1,667 non-boundary chunks unchanged in the native-POM game file; 1,523 unchanged
  in each clean/review source. New BSP has 7,013 wall segments, max/mean search depth
  37/19.3 (old 29/16.5); performance still needs gameplay confirmation.
- Seven regression cases include preserving legacy edge sampling, rejecting invalid
  widening, overlap/fold handling, separated-deck refusal and keeping the C triangle
  buffer alive after `build_corridor` returns. The returned oracle previously kept
  only its raw pointer, making post-return checks unreliable after memory reuse.
- Staging reports and installation mapping: `work/research/collision-boundary-20261021/`.
  Update BOTH clean/review POM pins, their `pins.json`, and only `main_sha256` in the
  reviewed-family export. A later relief-page Apply must preserve the corrected BSP.
  Keep YAML family gains, notes, exceptions and material settings unchanged.


## Daytona Big Curve: false support edges (2026-10-21)

The owner reported invisible walls in the middle of the visible banking. This is
not just the Mountain-style wall inset: Daytona's physical road itself had false
width pinches. `classic_edges` compared the coprocessor collision mesh with the
visible asphalt using a 30 cm height tolerance. Different triangulations of
banked, twisted quads disagree by 31-39 cm in a few places. Those asphalt points
were mistaken for the outer edge; the 3.5 m minimum width and adjacent-slice width
limiter spread the resulting pinches along the western curve. Re-running that
rule on the accepted road reproduces its widths within 0.000030 m.

The reviewed course recipe keeps the inner curb's 30 cm rule and 25 m cap, and
sets `edge_visual_right: 0.4` for the positive-column/outer side. 40 and 50 cm
produce the same outer widths; 35 cm still produces false pinches. Upright-wall,
raised-ground and collision-support checks remain active. `boundary_step: 1`,
`boundary_inset: 0.0`, `boundary_union: true` then follow the corrected support
without coarse chords cutting back across it. At slice 1200 the former BSP wall
was 4.978 m from the reference line and old support ended at 6.000 m; corrected
support/wall reaches 10.500 m under the asphalt already drawn there. These are
reference-line distances, not native car-body clearances. The existing conservative
width walk/rate limiter still leaves approximately 0.6 m to the drawn outer barrier
at that section; no zero-clearance or particle-emitter fix is claimed.

`source/tools/import/daytona/tracks/repair_support.py SOURCE STAGED --report REPORT`
is the offline repair for the accepted installed Daytona. It refuses in-place
writes and requires the 1,548-slice road plus reproduction of the old width
profile. It extends only the 144 affected outer rows, samples new heights from
the INSTALLED rendered opaque ground, retains collapsed edge duplicates exactly,
and keeps all 47,205 strictly interior vertex records and the reference line
byte-identical. This avoids changing the approved interior surface and AI route.
It does not redraw, widen or remesh the visible scenery. The only changed chunks
are road `44e94c8c`, its undeformed blob `8d245f33`, and boundary `b0d1e001`;
834 other chunks are exact, including all image/material/scenery chunks.
Road page 12/13 bounds expand only after both referenced images decode as uniform;
no nonuniform lightmap is remapped and no image pixels change. Maximum native row
size remains 78 records against the proven 132-record limit (38 quads maximum).

Offline checks of staged SHA-256
`49f67d08da74ce6903d1f86ba990d9de57aaddbe932e7282556384f5a20438b8`:

- 244,584 supported road samples: 32,342 obstructed by the old wall BSP, zero new.
- 24,010 supported 4.5 x 1.8 m test rectangles at -30/0/+30 degrees: 2,247 old
  blocked poses, zero new. Nine support points per pose; not native hull emulation.
- 23,220 near-edge/across-road classifications: zero mismatches; 1,548 floor,
  ceiling and center probes pass. 1,973 plan-near pairs contain no separated decks.
- 6,033 samples on 2,011 nondegenerate changed support triangles match drawn ground
  within 3.69 cm (99th percentile 2.18 cm); no unsupported probes, page UV overflows
  or vertical slivers. Seven zero-area triangles are intentional collapsed edges.
- The banking-aware below/above validation distances include crossfall. This only
  corrects the validator: rebuilding Mountain's boundary in memory remains byte-
  and fixup-identical, and its installed file is unchanged.
- Nine boundary regressions pass, including the false asphalt-edge reproduction
  and banked floor probes. Live gameplay still requires owner confirmation.

Evidence and image: `work/research/daytona-boundary-20261021/`. Install only the
`support-stage` candidate, not the earlier boundary-only experiment. Both the
Classic catalog and switch list refer directly to `track5/Desert4`; there is no
second Daytona catalog artifact. Keep stock `tracks/Desert4`, Mountain `track1`,
all route files and both catalog JSON files unchanged. The installation manifest
records source/staged hashes and the protected files. No game was launched here.


### Daytona owner validation (2026-10-21)

Bruno confirmed the invisible wall is no longer present. The installed Big Curve
collision repair is accepted for that issue. Daytona still needs other track
work, which the owner explicitly deferred; do not treat this as approval of the
whole track or start additional Daytona changes automatically.
