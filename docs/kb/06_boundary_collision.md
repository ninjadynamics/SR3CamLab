# 06 - Collision: what there is, and the TrackBoundary wall BSP

Tools: `work/scripts/bsp.py` (parser, point classifier), `bsp_build.py` (serializer, corridor builder, checks).

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
