# 08 - How Rally.exe (3.8.4.1, image base 0x400000, not packed) loads and uses a track

Helper: `work/scripts/x86.py` (`dis`, `fn`, `str`, `xref`); `work/tmp/rally.asm` is a linear disassembly for grep
(regenerate with the snippet in x86.py if missing). The exe was only read.

## Loaders
| Address | What |
|---|---|
| 0x6530B0 | generic "load sbf, return root object" (out pointer in arg 1) |
| 0x5C5770 | master_gfx: path `\main_release\tracks\%s\%s_master_gfx_xdata` (0x6C6090); root -> [obj+0x30]; on error prints and loops forever; remaps surface bytes of every road vertex (0x5C5850-0x5C59DB); calls TrackDeform init (0x4F0170 -> 0x4E28F0); then hard-coded per-name tweaks (strings "Safari3", "Arctic", "Tropical", "Lakeside", "Canyon7", "Canyon2", "Alpine1") |
| 0x5C5C90 | master_xdata: root -> [0x9DB48C], root+4 = gfx root; forces 2 sector splits |
| 0x5C5D30 | game_objects_gfx_data, then gameobj_gfx_dis_data if root version >= 2 |
| 0x5C54B0 | pobj_master_gfx_xdata, pobj_plac_gfx_xdata, proc_cached.bin (all skipped when missing) |
| 0x61B3B0 | builds `\main_release\tracks\%s\%s_track_route...` names (0x6D57B0) |
| 0x599FB0 | reads lighting floats from gfx root +0x18 / +0x1C |
| 0x5C9B0A | creates the TrackBoundary physics object when gfx root +8 != 0 |

## Globals
| Address | Content |
|---|---|
| 0x9DB48C | master_xdata root (gameplay root) |
| 0x9DBDB0 | current track record; +0x18 = folder name used in the paths |
| 0x9C10C0 / 0x9C10D4 | scenery tree chunk |
| 0xA95C94 | slice array (after init: +0x88, i.e. slice 1) ; 0xA95C98 slice count ; 0xA95C9C count-1 |
| 0xA95F18 | copy of the overlay page table ; 0xA95F10 batch records ; 0xA95F14 texture table |
| 0xABC7C4 | global surface type table (pointers; +0x10 softness, +0x18 flags, +0x1C, +0x20, +0x24) |
| 0xAE3220 | surface/material name table object (vtable 0x6EA064: +8 = find by name, 0x5B1820 = find by id) |
| 0x728B00 / 0x728B04 | start slice / direction copied from the root (0x5C4630) |
| 0xA65794 | 1 = ignore PVS |

## Users of the gameplay root (by field)
+08 AI map: 0x415210, 0x5CF3E0, 0x5CF400, 0x5E4251, 0x5E6044, 0x5E6F80 (marks touched cells), 0x5E7AC0/0x5E8050/0x5E8CC0 (lane tests).
+0C cameras: 0x5FB251. +14: 0x5C5485. +18 spline: 0x5AA14F, 0x5ACD94, 0x5D3407, 0x5E61CA.
+2C/+30 start/direction: 0x5AF291, 0x5C4631, 0x5C63ED, 0x5E7A10, 0x5FA077; +30 alone in 15 more places.
+34 grid: 0x5AF2B1. +74..: 0x5AA130, 0x5C5CE4.

## TrackDeform init 0x4E28F0 in order
1. copy page table (count = max page index + 1), 2. store header fields, 3. normalise batch records (0x4E2A90),
4. per slice: fill the block header from the slice bytes (0x4E2B70), 5. per vertex: softness and flags from the
global surface table (0x4E2D80), 6. per slice: corner positions, direction and plane into the first 0x6C bytes
(0x4E2F90), consistency message 0x6A10CC when consecutive slices fold, 7. allocate working buffers
(`(n/16 + n/64 + 2) * 96` bytes), 0x4E2190, 0x4E1BF0.

## Scenery
0x5022E0 / 0x502400 init, 0x423B30/0x423B80/0x423BD0 tree walks (count, assign buffers, create), 0x5C1EB0 material
setup per node, 0x500EA0 visibility refresh, 0x4FFC30 stream decoder, 0x5003C0 leaf lookup, 0x640D65 light map sample.

## Addresses found after this file was written (index; each is discussed in the file named)
| Address | What | File |
|---|---|---|
| 0x5D27B0 (fault 0x5D2D3F) | nearest overlay page to a car; crashes when the page count is 0 | 04 |
| 0x40201A | fault when one overlay page covers a whole large track (bad texture pointer) | 04 |
| 0x62FC50, table [0xA95F18] | a car takes its sun / shadow value from the nearest overlay page | 04 |
| 0x506FD0; globals 0x9C491C..28; arrays [0xA95D24 / 28 / 2C] (allocated at 0x4F0259 / 0x507C84) | grass set-up, reached via the pobj_plac root | 02 |
| 0x5DE0C0 (fault 0x5DE16C) | dies when a wheel touches the road and the grass arrays are missing | 02 |
| 0x5C1EB0 (fault 0x5C1ED6) | scenery mesh list walk; crashes on forward references | 01 |
| 0x447A20 | fault on an early flat-loop build; cause not established, not seen again after the page fix | 09 |
| 0x58DF40 | reads the sampler words of a texture header (+0x14) | 01 |
| 0x5BF450, 0x55D7B0, 0x5BF4A6..0x5BF5C8; [0x9C0E68] | material binding table of Granny models | 15 |
| 0x61CAF0 (called from the object update 0x61FD30), 0x632BE5; object +0x1B8; [0x9DD614] | start / finish banner: forced LOD = state; final-lap test | 15 |
| 0x661AA0 (called at 0x5ABDF8); [[0xB2A850] + 0xC] + 4 + 0xC60 x track | checkpoint seconds per track | 03, 20 |
| 0x9F1068 (set by 0x594570), 0x9F1028, 0x59B537, 0x50D960 (called once at 0x5A5467) | dynamic shadow parameters and blur | 07, 16, 20 |
| 0x8123C8 / 0x8123CC, 0x590404..0x590486, 0x41863C | polygon-offset render state (slope, bias; applied; reset) | 20 |
| 0x5001A6, 0x51186C, 0x5D6441, 0x640D89 | readers of the light-map fallback colour 0xFF808080 | 05, 20 |
| 0x9EB81C | settings pointer, non-zero once system data is loaded | 20 |
| [0x9EB4EC] + 0x18 | camera manager | 20 |
| 0x9EB970, 0x9F0680 | final view matrix | 20 |
| 0xA65650, [0x9F05F4], [0xA65790], [0x9F0FAC] | PVS contexts and flags | 20 |
| 0x577F00 | CreateVertexBuffer wrapper ("Out of memory for VB") | 20 |
| 18 menu timer sites (0x63D900 ...) | 15000 ms constants | 20 |

Note on "not packed" in the title of this file: 16_lighting_shadows_lightmaps.md (2026-10-08) calls the exe on disk
"packed (3.3 MB file, data addresses beyond the raw size)". The two statements conflict; see OPEN_QUESTIONS.md.
