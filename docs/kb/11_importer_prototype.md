# 11 - Importer prototype: a real centre line into the road format

Script: `work/scripts/build_more.py` (`import_classic`, steps 14 and 15). Input: SEGA Rally Championship course 1,
`classic/obj/src_course1_centreline.csv` (300 points about 11.6 m apart) and `src_course1_collision.obj`
(polygons grouped by attribute; the ones without attribute bit 23 are treated as drivable). See classic-sources.md.

## Pipeline
1. Closed Catmull-Rom spline through the 300 points, re-sampled by arc length to an integer number of slices:
   3509 slices, 0.999-1.002 m apart (the road format wants 1 m; the tiny residual is spread evenly).
2. Height of every slice centre from the collision mesh (triangle under the point, nearest to the csv height),
   smoothed over 7 slices. Found on 3509/3509 slices.
3. Cross profile: walk sideways in 1 m steps while a drivable triangle continues smoothly -> drivable half width per
   side (median 6 m left, 7 m right; minimum 4 / 5). Banking = least-squares slope across +-5 m, smoothed.
4. Road: constant half width (20th percentile of the narrower side, here 5 m -> 10 m road), columns placed along the
   banked lateral vector, uniform surface cell borrowed from the slot, undeformed height blob, one overlay page.
5. AI map, spline, start grid exactly as for the flat loop; start line arbitrarily at slice 10.
6. Course re-centred on the origin (extent x +-326, z +-479; scenery tree limit +-750).
7. Step 15 adds walls 0.5 m inside the road edges, floor = lowest road point - 2 m, ceiling = highest + 10 m.

Numbers for course 1: elevation 14.0-83.3 m, maximum grade 15.1%, maximum bank 2.6 degrees, minimum centre-line
radius 8.9 m, no plan-view crossings.

## What the road format can and cannot express
| Feature | Status |
|---|---|
| Curvature | free; the inner edge needs radius > half width or the slices fold (the exe prints a warning, message 0x6A10CC, when consecutive slice planes cross) |
| Elevation / grade | free in the data (positions are plain floats); SEGA's own tracks reach about 60 m of height range; no limit found in the init code. Jumps/steps: every slice is one straight row, so a vertical step needs two slices 1 m apart |
| Banking, crown | free: each vertex has its own position, so any cross profile sampled every 1 m |
| Width | 1 m columns; A (quads across) is a byte and SEGA's maximum is 38 (Desert4); changing width needs the stitch bytes +6E/+6F and duplicated end vertices - rules verified on SEGA's data but the importer only writes constant width |
| Road narrower/wider than a multiple of 1 m | SEGA uses fractional edge columns; the importer rounds to whole metres |
| Closed loop | required by every example (slice 0 = slice n, slice n+1 = slice 1). Point-to-point stages were not examined |
| Self-crossing (bridge over the road, figure of 8) | the road chunk itself allows it (slices are independent), but the AI map (2 m cells keyed by x,z only), the boundary BSP built here (2D plan build with one floor/ceiling) and the start-grid/track-position lookups by x,z would confuse the two levels. Not supported by these builders |
| Pit lane / forks | no structure for it in the road chunk (one row sequence) |
| Lap length | n is a u32 in the header but per-slice tables index with 16 bits in places (0x4E2B82 stores the slice number in a u16): keep n < 65536; SEGA's longest is 3772 |
| Surface changes along/across the road | per cell (two layer indices + corner weights) - the importer writes one uniform cell; the collision OBJ attribute bits 16-19 could drive it later |
| Off-road ground | not in the road chunk: needs scenery meshes for looks and has NO collision except the walls |

## Known weaknesses of the prototype
- Handedness of the classic data is unconfirmed (classic-sources.md): if the course is mirrored, negate X before import.
- Start line position and direction are arbitrary; pace notes are not generated.
- Height comes from the "nearest triangle in y" rule; on bridges or overlapping polygons it could pick the wrong sheet.
- The walls use one global floor/ceiling: on a course with 69 m of height range the tunnel is 81 m tall. Harmless for
  driving on the road; a per-segment floor like SEGA's needs the 3D form of the builder.
- The borrowed Desert4 objects and cameras stay where Desert4 had them and will stand in the way in places.

---
# Update (third package): the importer as it is now - `work/scripts/build_classic.py`
- Course 1 is the MOUNTAIN course (12_classic_textures.md).
- Handedness fixed: SR3 = (x_obj + ox, y, -z_obj + oz), i.e. the game's own left-handed coordinates re-centred
  (`work/tmp/classic_xform.json`). The earlier step14/15 were mirrored; they were rebuilt under the same names.
- Heights: every road vertex (15 across, 1 m apart) takes its own height from the collision mesh (drivable polygon
  first, off-road polygon second, interpolation last), smoothed over 5 slices along the track. So crown, banking
  (max cross-fall 8.6%) and kerb-less shoulders come from the data instead of a fitted plane.
- Width: constant 14 m (7 columns each side). The collision mesh has a drivable polygon under every one of those
  columns on every slice (median = minimum = 7 per side), so 14 m is inside the classic drivable strip everywhere;
  VARIABLE width was not implemented (the classic strip is wider in places and the SR3 stitch bytes are only verified
  on original data).
- Surfaces per cell from the collision attribute bits 16-19:
  | code | where it occurs (3158 polys) | texture there | SR3 surface used |
  |---|---|---|---|
  | 1 | 782 polys on the racing line (median 3.8 m from the centre) | asphalt tiles with tyre marks (x0000_y0256, x0256_y0128) | tarmac |
  | 0 without bit 23 | 229 polys on the road in the town part | between house fronts | tarmac |
  | 8 | 11 polys, flat-coloured (start/finish area) | - | tarmac |
  | 6 | 336 polys 7-12 m from the centre | rough stony tile x0512_y0256 | gravel |
  | 0 with bit 23 | 1800 polys 9-15 m out, rock-face tiles | not drivable | (gravel if a cell reaches them) |
  SR3 layers: the Desert4 file already contains Terrain_Safari_Tarmac (base e56e4a5c, top 0558e395) and
  Terrain_Safari_Gravel (base 9cbfa41a, top 6ec69183), so those four textures are used; result 44852 tarmac cells and
  4274 gravel cells. Corner weights blend over the cells sharing a corner (0x8080 tarmac, 0x0808 gravel, 0x4444 half).
- Scenery: 14955 classic faces, 1236 inside the road strip dropped (the SR3 road replaces them), 13719 kept as SR3
  meshes in world space on the scenery-tree root: 60 meshes (one per classic section) for the checker and SR3-material
  versions, 152 (one per classic material) for the textured version; 54876 vertices in total, largest mesh 3532.
  Limits found: 65535 vertices and 65535 strip indices per mesh group (u16 counts), scenery tree +-750 m (course
  extent after centring: x +-369, z +-533, y -25..125).
- Walls follow the terrain (06_boundary_collision.md, last section).
- Props: `step19` sets the object count of the borrowed game_objects list to 0 and leaves out the pobj files and the
  grass cache. A true minimal object file and camera lists were NOT authored (formats still undecoded): the trackside
  cameras remain Desert4's.

---
# Later corrections to this file (2026-10-07 / 08, in-game runs)
- Handedness: the formula above, SR3 = (x_obj + ox, y, -z_obj + oz), i.e. the game's own axes, is the one that holds. In
  the importer it is the constant `ZS = -1`. For a few hours on 2026-10-07 the opposite (`ZS = +1`, SR3 = the OBJ axes)
  was used after a report that the course looked mirrored; that report was really the signed-uv bug. With +1 the board
  text and the whole layout were mirrored (castle on the wrong side). Settled in game on 2026-10-07, checked against a
  frame of the real game: the castle must be on the right and the SEGA boards on the left, reading correctly.
- "Weaknesses" resolved since: start line and grid from the ROM table; pace notes from the game's own calls; variable
  width from the 1995 drivable ground (04_trackdeform_road.md); walls follow the terrain; the slot's cameras are removed
  and the game builds default ones; the slot's props are replaced by the crowd objects (15_spectators.md).
- Still true: off-road ground has no collision; self-crossing is not supported by the builders.
- Step 19's approach (leave out the pobj files and the grass cache) is NOT usable: the game crashes in the race without
  them (02_track_files.md).
- The uv range of the mesh format is -1 .. +1 signed, not "0..2" (23_texture_pipeline.md); the limits of 65,535 vertices
  and strip indices per mesh group stand.
- Current state of the importer: 14_importer.md (last section), 17_mountain_build_notes.md.
