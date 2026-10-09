# 04 - The road: TrackDeform chunk + height blob

master_gfx root +0x0C -> kind 5 chunk (6 MB Stadium4 ... 26 MB Canyon4). Code: Sega_ML_TrackDeform_Init.cpp,
init function 0x4E28F0 (called from the loader 0x5C5A38 via 0x4F0170). Tools: `trackdeform.py`
(`parse_td`, `td_to_model`, `build_td`): parse -> model -> rebuild is BYTE-IDENTICAL on all six tracks.

This chunk is at once the visible road, the drivable (deformable) ground and the measure of track position:
`[0xA95C98]` = slice count = lap length; start grid, sector splits and AI all work in slice numbers.

## Geometry model (VERIFIED numerically)
- The road is cut into SLICES 1 m apart along the centre line (Lakeside: 3307 slices, spline length 3311 m).
- Each slice is a row of vertices 1 m apart across the road; the first/last spacing is shorter (road edge).
- Vertex k of a slice is lateral COLUMN `off + k`; column 0 is the centre line. With d = direction of increasing slice
  index and lat = direction of increasing column: (d x lat).y > 0 on every slice of all 6 tracks, i.e. lat = (d.z, 0, -d.x).
- Slices 1..n are real. Slice 0 is a byte copy of slice n and slice n+1 a copy of slice 1 (closed circuit).
- A quad between vertex k, k+1 and slice i, i+1 is a CELL; it owns a 16x16 grid of height bytes (deformation).

## Header (0x30)
| Off | Type | Meaning | Confidence |
|---|---|---|---|
| 00 | u32 | 5 (version) | VERIFIED |
| 04 | u32 | max A over all slices | VERIFIED (6 tracks); exe stores +1 at [0xA95F3C] |
| 08 | u32 | n = number of slices | VERIFIED exe 0x4E29E8 |
| 0C | u32 | nSurf = entries in the two id tables | VERIFIED |
| 10 | u32 | 2 | UNKNOWN |
| 14 | u32 | byte size of the compressed height blob | VERIFIED (6 tracks) |
| 18 | ref | kind 7 height blob | VERIFIED |
| 1C | ptr | slices (n+2 records of 0x88) | VERIFIED |
| 20 | ptr | nSurf texture refs (one DXT5 1024x1024 texture per surface layer) | VERIFIED |
| 24 | ptr | batch records, 11 bytes each, (n+3)/4 + 1 of them | VERIFIED |
| 28 | ptr | nSurf surface ids (same values as the texture ids, stored as plain numbers) | VERIFIED |
| 2C | ptr | overlay pages, 0x18 each, count = highest page index + 1 | VERIFIED |

File order: header | slices | batch records + at least one 0 byte, padded to 16 | texture refs (+>=1 zero word, padded
to 16) | surface ids (same padding) | vertex blocks of slices 1..n, then a second copy of slice 1's block | pages.
Fixups: the 5 header pointers + one per slice (+0x78). Refs: +0x18, the texture refs, 2 per page.

## Slice record (0x88)
| Off | Type | Meaning | Confidence |
|---|---|---|---|
| 00..6B | - | zero in the file; filled at run time (corner positions, direction, plane; 0x4E2F90..) | VERIFIED exe |
| 6C | u8 | A = number of quads across | VERIFIED |
| 6D | s8 | off = column number of vertex 0 (negative) | VERIFIED |
| 6E | s8 | off(i) - off(i-1) (-1, 0, +1) | VERIFIED rule on 6 tracks |
| 6F | u8 | 1 when +6E is positive | VERIFIED rule |
| 70..74 | - | 0 | - |
| 75 | u8 | B = number of vertex records = max(A(i), A(i-1) + off(i-1) - off(i)) + 1 (one more in a few dozen slices where the offset grows) | VERIFIED rule |
| 78 | ptr | vertex block | VERIFIED |
| 7C | f32 | -99999; 14.0 or 13.16 on parts of Lakeside4 | LIKELY water level |
| 80, 84 | u32 | 1, 2 | UNKNOWN (constant) |

## Vertex block
Size (B+1)*0x30 + (A+1)*0x100.
- 0x30 header: `u16 A` at +0, `s8 off` at +0x10, 0xFF at +0x11, copy of slice+6E at +0x12, (slice+6E != 0) at +0x13, rest 0.
  Rewritten at run time (0x4E2B70: offsets to neighbours, sizes).
- B records of 0x30 (below).
- (A+1)*0x100 zero bytes: run-time height maps (filled from the blob).

Record = vertex k plus the cell to its right:
| Off | Type | Meaning | Confidence |
|---|---|---|---|
| 00 | f32 x3 | position | VERIFIED |
| 0C | f32 | 0 in file; run time: softness = min of the 4 neighbouring surfaces, capped 0.07 (0x4E2DAF) | VERIFIED exe |
| 10 | u32 | 0xFFFFFFFF | UNKNOWN (constant) |
| 14 | u8 | per-track flag byte (0xC1 Stadium; 0x3B/0x75/3/5 Lakeside); 0 on the last vertex of a slice (no cell). Recomputed at run time (0x4E2E82) | LIKELY irrelevant in file |
| 16 | u8 | 0 Stadium; 3/5 Lakeside, 2/8 Tropical; overwritten at run time (0x4E2EA2) | LIKELY irrelevant |
| 18 | u8 | BASE layer index (into the id table): the `..._Base` terrain under the surface | VERIFIED exe (remapped at load 0x5C5880) + names (10_surfaces.md) |
| 19 | u8 | TOP layer index: the `..._Top` terrain = the driving surface; its global properties drive softness/grip (0x4E2D80) | VERIFIED exe + names |
| 1C | u32 | id table[byte 19] | VERIFIED (100% of vertices) |
| 20 | u32 | texture weights at corner (k, i) | LIKELY |
| 24 | u32 | ... corner (k, i+1) | LIKELY |
| 28 | u32 | ... corner (k+1, i)   (= +20 of the next vertex) | LIKELY |
| 2C | u32 | ... corner (k+1, i+1) | LIKELY |

Weights: 8 nibbles (low nibble of byte 0 first) that always sum to 16; nibble j is the weight of texture j of the
slice's batch record. Stadium: batch list [3,0,2,1], weight 0x8080 = surfaces 0 and 1 at 8/16 each (the dominant
road cell, surf bytes (0,1)); 0x0808 = surfaces 3 and 2 (road edge, surf bytes (3,2)); 0x4444 = transition.
Desert: dominant cell surf (9,5), batch list [9,6,5,14,2,10], weight 0x0808. Consistent in both; in the other tracks
about 16% of weights index past the list with my slice->batch mapping, so the exact mapping is not fully settled.

## Batch record (11 bytes, one per 4 slices)
`u8 surf[7]` (0xFF unused), `u8 count`, `u8 flags`, `u8 type (1 or 2)`, `u8 page index`.
Init (0x4E2A90) clamps surf[] to nSurf, rewrites count/flags/type and sets a flag when the page changes.

## Surface ids -> physics surface
At load (0x5C5880) bytes +18/+19 of every vertex are translated through the id table and `0x5B1820`, which searches
the id in a list loaded from a data base (`[0x9DB80C]+0x2C/+0x30`) and returns a global surface type (0 if unknown).
So the physical surface of a cell is decided by the TEXTURE ID of its layer: keep SEGA's ids to keep the surface type.
The lists are dumped and named in 10_surfaces.md (90 terrain entries, importer table of id pairs per surface).

## Overlay pages (0x18)
`ref texA, ref texB, f32 u0, f32 v0, f32 su, f32 sv` with u = x*su + u0, v = z*sv + v0.
VERIFIED: all 10 Stadium pages map their slices into 0..1. texA = DXT1 1024x1024 (or 512x1024), mean colour
R 205 G 49 B 0 (a control/light map, not a colour picture); texB = 32x32 grey in Stadium.

## Height blob (kind 7)
zlib stream; inflated size = 256 x sum of A over slices 1..n (VERIFIED on 6 tracks). 16x16 bytes per cell,
0xBF = undeformed (most common value), lower = pre-baked ruts. Authoring: all 0xBF (LIKELY fine, untested).

## Authoring subset used by the test loop
Constant width: every slice A = 14, off = -7, B = 15, +6E/+6F = 0; all cells = the most common uniform cell of the
slot's own road (`uniform_pattern`), one page, blob all 0xBF. `step5` of the ladder tests exactly this content on
the original Stadium geometry.

## Variable width: how SEGA lays out the records (package nine, VERIFIED numerically)
- Interior vertices sit on whole-metre columns; the FIRST and LAST vertex of a slice sit on the road edge (any
  fraction), so the first / last spacing is 0..1 m. off = floor(left edge), right column = ceil(right edge), A = their
  difference. Ranges in the six tracks: A 15..38, off -18..-7, right column 6..20, at most one column of change per
  slice on each side.
- A slice's records span columns min(off, previous off) .. max(right column, previous right column); the surplus
  records are collapsed onto the edge (zero-width cell). That is the B rule of the table above, including the "one
  more where the offset grows" case (the extra record is the FIRST one, so record k is column off - max(+6E, 0) + k).
  Checked: B exact on all slices of Tropical, Lakeside, Desert, Alpine; lateral position of every record =
  clamp(column, left edge, right edge) within 6 cm on 97..100 % of the slices. The SEGA Rally 2 import session derived
  the same rules (its `varwidth.py`, all 16,818 slices of the six tracks).
- `trackdeform.columns(t, i)` / `road_frame(t)` read it back; `build_classic.road_model` writes it (classic variant).
- In the importer (2026-10-07 on): `build_classic.classic_edges` finds, per slice, how far the 1995 drivable ground
  (collision polygons without bit 23) reaches left and right of the centre line, walking outwards in 25 cm steps until
  the ground ends or steps by more than 30 cm; then the minimum over the neighbouring slices, at least a minimum half
  width, at most a cap, and no more than 0.5 m change per slice (SEGA's edges move at most one column per slice). The
  variable-width Mountain road loads and drives (VERIFIED in game). The mixed / all-SR3 variants keep the constant 14 m.

## Overlay page count: one page crashes (found in game, 2026-10-06)
- TrackDeform init 0x4E28F0 counts the pages as (highest page index of the batch records) + 1 ONLY when that index is
  not 0. A road whose batch records all use page 0 gets a page count of 0, and 0x5D27B0 (nearest page to a car)
  dereferences an uninitialised record: access violation at 0x5D2D3F. VERIFIED (code) and in game: the first authored
  road (step5, one page for the whole track) crashed exactly there.
- Control ladder (`build_road_ladder.py`, every step = the original Desert4 with one thing changed): 5a identity; 5b ONLY
  the pages reduced to one (expected to crash: the control that proves the cause); 5c the same page written twice, second
  half of the batch records on page 1; 5d only the height blob all 0xBF; 5e only the cells uniform; 5f + uniform batch
  records. The owner's notes list these finer steps as untested after the fix; the fix itself is proven by every later
  build.
- Fix: write at least two pages (`patch_pages.py` repairs built steps: the page listed twice, the second half of the batch
  records on page 1).

## Overlay pages are local patches (found in game, 2026-10-07)
In the six arcade tracks every page spans 39..120 m a side, about 100 m of road each (Desert4 27 pages, Alpine4 35). One
page stretched over a whole imported track (760 x 1080 m) crashed the game when the road was drawn (0x40201A, bad texture
pointer); the same road with SEGA's mapping numbers ran. VERIFIED in game. `build_testtrack.two_pages` now lays pages out
SEGA's way: consecutive batch records (4 slices each) share a page until their bounding box would pass 110 m; the page
maps that box (padded, at least 60 m a side) to 0..1; all pages use the single page's textures.

## What the page texture texA is: a sun / shadow map (found in game, 2026-10-07)
This replaces "a control / light map, not a colour picture" above. texA is a sun / shadow map: green = sunlit, red =
shadow. A car takes its lighting from the nearest page (0x62FC50, table [0xA95F18]). The first authored pages were filled
with the mean colour of SEGA's pages (205, 49, 0) = all shadow, and the cars were dark on the imported track; the importer
now writes (0, 255, 0) = all sun, and the owner reported "car lighting fine". VERIFIED in game for the effect on the cars;
the exact layout of the map beyond the two colours is not decoded (UNKNOWN; 16_lighting_shadows_lightmaps.md).

## Surface ids in game
The texture id of a layer selects the physics surface AND what the wheels throw up: Desert4's own tarmac pair is
Terrain_Safari_Tarmac, which raises dust clouds on asphalt ("lifts a lot of dirt into the air on asphalt", owner,
2026-10-08); Alpine4's Terrain_Tarmac pair (5186a744 + 7e6973ab) is clean tarmac. VERIFIED in game for the dust; the
importer copies the layer textures of another track with their ids (course setting `road_layers`).
SR3's own road effects (car shadows, skid marks, ruts) are drawn on this road, so a mesh laid over it hides them unless
its material receives dynamic shadows (22_gapfill_zfighting_scenery_rules.md, section 3).

## Height blob in game
An all-0xBF (undeformed) blob works: the imported Mountain road is built with one (11_importer_prototype.md) and loads
and drives. VERIFIED in game (it was "LIKELY fine, untested").
The road is deformable in game (ruts form), which is why the gap-fill welds run under the road's edge (22).
