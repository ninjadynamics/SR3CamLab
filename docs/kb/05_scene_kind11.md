# 05 - Scenery tree (kind 11) - Sega_ML_SceneManager_Block.cpp

master_gfx root +0x04. Init 0x5022E0 / 0x502400; global pointers `[0x9C10C0]` and `[0x9C10D4]`.
Tool: `scene11.py` (parser, invariant checker, minimal builder `build11`).
This is NOT collision. It is a fixed-depth quadtree of the world with the scenery meshes hung on its nodes.

## Header (0x20)
| Off | Type | Meaning | Confidence |
|---|---|---|---|
| 00 | u32 | 2 (version; 0x500EF8 tests == 2) | VERIFIED exe |
| 04 | u16 | number of leaves (recounted at load, 0x423664) | VERIFIED |
| 06 | u16 | number of nodes (recounted at load) | VERIFIED |
| 08 | f32 | 46.875 = leaf size (1500 m / 32) | VERIFIED (all tracks) |
| 0C | ptr | light map structure or 0. Reader 0x640D65 falls back to colour 0xFF808080 when NULL; init 0x5024D9 checks NULL | VERIFIED exe |
| 10 | u16 | (nodes + 7) / 8 = bytes of a node bit set | VERIFIED (6 tracks) |
| 12 | u16 | 16 = fixed-point scale of the node boxes | VERIFIED exe 0x502415 |
| 14 | f32 | run time: 1/scale | VERIFIED exe |
| 18 | ptr | run time buffer | VERIFIED exe |

## Node (0x20), node i at 0x20 + 0x20*i
| Off | Type | Meaning | Confidence |
|---|---|---|---|
| 00 | s16 x6 | box min x,y,z, max x,y,z in 1/16 m. Loose: grown to contain the meshes | VERIFIED |
| 0C | ptr | content or 0 | VERIFIED exe (null checks in 0x423680, 0x4236E0, 0x4235A0, 0x5C1EB0) |
| 10 | u16 x4 | child node indices, 0 = none. Order (x0,z0), (x1,z0), (x0,z1), (x1,z1) | VERIFIED (all nodes of 3 tracks) |
| 18 | ptr | leaf record; present on every leaf, absent on inner nodes | VERIFIED |
| 1C | u16 | parent index, 0xFFFF for the root | VERIFIED |
| 1E, 1F | u8, u8 | 1-based cell coordinates of the node inside its level (root 1,1; leaves 1..32) | VERIFIED |

Depth is always 5 (root + 5 levels, leaves 46.875 m); missing quadrants are simply absent. Nodes are numbered so that
parent < child (pre-order). Root box about [-750, 750] in x and z.

Content: `ptr instances (or 0), u32 nMeshes, ref mesh[nMeshes]`. Static scenery meshes hold world-space vertices and are
named `<route>_l<level>_x<..>_z<..>`. The instance list (`{count, 0x24-byte entries ...}`, used for library objects
such as hoardings, tyre walls, tents) is NOT decoded.

Leaf record: `u32 1, ptr a (-> next word), u32 0, ptr b (-> next word), visibility stream`.

## Visibility stream (PVS) - decoder 0x4FFC30
One byte code per step, over node indices 0..nodes-1:
`FF n` = next n*8 nodes visible; `00 n` = next n*8 nodes hidden; any other byte = 8 literal bits (LSB first).
Stadium4 example `FF 22 7F 00` = 272 + 7 nodes visible (all 279). VERIFIED (decoder matches the node count).
Refresh 0x500EA0: finds the leaf containing the camera (0x5003C0); no leaf -> everything visible (0x4231E0);
`[0xA65794] != 0` also forces everything visible.

## Light map (+0x0C), not decoded
`u32 1, ptr, ptr, u16, u16, f32 minx, minz, sizex, sizez, f32 cellx, cellz, 2 x f32 run-time inverses` + a tree of
u16 pairs. Sampled by 0x500170 for an ambient colour at a position. Optional.

## Other things done with the tree at load
0x5019C0 collects every mesh whose material type is 6 (0x5000C0), extracts its triangles (0x5004D0) and relates them
to road slices (table `[0xA66954]`, 2 bytes per slice). None in a tree without meshes. Purpose UNKNOWN (water?).

## Minimal tree written by `build11`
Header (light map 0), nodes in pre-order for the requested leaf cells, optional content on the root only, one leaf
record per leaf with an all-visible stream. Boxes exact (not loose), y from -50 to 200.
Not proven in game: `step4` of the ladder swaps only this chunk into the original Stadium4.

## In-game results and run-time facts (2026-10-01 .. 08)
- The authored tree works: "authored scenery tree" and "authored ground + box meshes" are on the owner's list of things
  proven in game, and the imported Mountain course hangs all of its meshes on such a tree. VERIFIED in game. So none of
  the feared needs (a light map, instance lists, loose boxes, meshes of material type 6) is a requirement.
- No light map (+0x0C = 0) is safe: the fallback colour 0xFF808080 is the NEUTRAL value. A patch that raised it to 0xE8 at
  four reader sites (0x5001A6, 0x51186C, 0x5D6441, 0x640D89) washed the whole picture out (DISPROVED as a cure for dark
  cars; 20_launcher_inmemory_patches.md, section 12).
- The mesh list of a node is walked by 0x5C1EB0; a mesh chunk that comes AFTER the kind 11 chunk in the file is a dangling
  entry there and crashes (0x5C1ED6). Rule and fix: 01_container.md, "Chunk order".
- The tree spans +-750 m. Imported Desert reaches outside it (x -793, z -999..933; owner's notes: "expect trouble", not
  tested). Far 1995 backdrop faces that do not fit inside +-740 m are left out (14_importer.md).
- The importer hangs its world-space meshes on the ROOT node of the authored tree (11_importer_prototype.md); a build
  with 1.82 million scenery vertices runs in game (17_mountain_build_notes.md, section 1). VERIFIED in game.
- PVS at run time (contexts at 0xA65650, the switch [0xA65794], the freeze flag [0xA65790], the render-pass flag
  [0x9F0FAC] that must not be used): 20_launcher_inmemory_patches.md, section 9. The sets were built for road-level
  eyes; a high or roaming camera sees scenery flicker. VERIFIED (live).
- Leaf size differs between games: 46.875 m in the arcade tracks, other values in Revo tracks (13_revo_vs_arcade.md).
