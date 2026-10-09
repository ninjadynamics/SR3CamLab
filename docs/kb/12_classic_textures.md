# 12 - SEGA Rally Championship (Model 2A) textures from ROM

## Correction (fourth package): the texture mapping bug and its cause
The first export (`classic/obj/src_course1_hi.obj`, and everything built from it in package three) had smeared
textures. Cause, VERIFIED: the object table at main-data 0x864B48 was read as rows {polygon address, polygon count, UV
address, header address}, but the UV and header addresses in row k belong to the object of row k+1. Proof: the UV list
that row k-1 points to is exactly (8 words per quad + 6 per triangle, connectors included) of object k long, for every
object checked (e.g. row 1259 list = 3518 words = object 1260's 424 quads + 21 triangles). MAME's rules themselves
were right: UVs are stored v,u as 13.3 fixed point texels, 4 pairs per quad and 3 per triangle in the order
v0 = P1(n-1), v1 = P0(n-1), v2 = P0(n), v3 = P1(n); the header pointer advances by the signed 5-bit field in
attribute bits 12-16 AFTER the polygon; link type 0 polygons are not drawn but still consume UVs.
With object k = (polygons of row k, texture pointers of row k-1): faces with a degenerate uv axis fall from 2198 to 6,
all 130 materials are textured, and the render shows house fronts, "SEGA" / "SEGASATURN" boards reading the right way
round, lamp posts and cut-out trees (`work/previews/blender_classic_road_1.png`).
New exporter: `work/scripts/classic_export.py` (also folds mirrored u/v - header word 0 bits 8/9 - and names
translucent materials `_t`: renderer type 3 in header word 0 bits 13-14, texel 15 = hole -> alpha in the PNG and `map_d`).
The tile set changed with the fix: 130 tiles (36 + 13 rectangles on the two pages), 25 translucent.

Scripts: `work/scripts/m2tex.py` (texel decoder), `classic_tex.py` (course 1 export).
Output: `work/classic_tex/course1/` - `sheets/course1_sheet1_2048x1024.png`, `textures/<material>.png` (117 tiles,
named exactly like the materials of `classic/obj/src_course1_hi.mtl`), `src_course1_hi.obj` + `.mtl` (loads in Blender
with the tiles; 19 cut-out tiles have alpha and a `map_d` line).
Tags: VERIFIED = decoded from the user's ROM and checked by eye; DOCS = from MAME (model2.cpp, model2_v.cpp, model2rd.ipp).

## Where the texels are
- Texture RAM (DOCS): two sheets, each 2048 x 1024 texels of 4 bits, stored as 1024 x 2048: one 16-bit word holds a
  2 x 2 block (`get_texel`: word index = (y/2)*512 + x/2; y even -> high byte, x even -> high nibble; x >= 1024 maps to
  x-1024, y+1024). Model 2A maps them at 0x12000000 / 0x12400000.
- ROM (VERIFIED): the texels are stored UNCOMPRESSED in the main data ROM (mpr-17746/47, 17744/45, 17884/85 interleaved
  as 32-bit words) in exactly that word layout, as 512 KB pages = 1024 x 1024 texels, from main-data offset 0x200000
  (the program holds the pair 0x02200000 -> 0x12000000 at maincpu 0x3954). Pages seen (offset: content):
  0x280000 menus/HUD text ("CHECK POINT", "CAR SELECT", "SELECT COURSE"); 0x300000 clouds, cobbles, trees, crowd;
  0x380000 rock, pines, Sonic/Saturn boards; 0x400000 grass, rock, elephant, zebra; 0x480000 savanna trees, zebras;
  0x500000 pines, fence, clouds; 0x580000 mountain backdrop, forest; 0x600000 TOWN BUILDINGS, rock, road;
  0x680000 road with white dashes, cobbles, lamp post, arcade building; 0x700000 grass, trees, swan;
  0x780000 "LAKESIDE" boards, pines. Mip levels are stored inside the pages (lower rows).
- Text in the pages reads normally (not mirrored). VERIFIED by eye.

## Which pages a course uses
A polygon's texture header (DOCS, used by the exporter): word 0 bits 0-2 width = 32 << n, bits 3-5 height, bit 14
textured; word 2 bits 0-5 x/32, bits 6-10 y/32, bit 12 sheet; word 3 bits 6-15 colour base; word 1 low byte luma base.
Course 1 uses sheet 1 only. Fitting its 47 distinct rectangles to every page: tile borders line up exactly with
page 0x600000 for x < 1024 and page 0x680000 for x >= 1024 (`work/tmp/texscan/c1_rects.png`). VERIFIED by eye.

## Which course is "course 1"
Its pages hold town houses, an arcade, cobbles, asphalt with tyre marks and white dashes, rock faces: it is the
MOUNTAIN course (the one "based on a shortened Monaco", all tarmac, narrow - matches 14-83 m of elevation and the
hairpin). By the same page test: course 2 (3210 m) uses the zebra/elephant/savanna pages = DESERT; course 4 (4196 m)
the pine/fence pages = FOREST; course 3 (3147 m) the "LAKESIDE" page = LAKE SIDE. LIKELY (page content; courses 2-4
were only matched by score, not inspected tile by tile).

## Handedness
The game is left-handed, Y up, Z forward (DOCS). The OBJ files in `classic/obj` store (x, y, -z): right-handed, correct
in Blender. SR3 is also left-handed Y up (LIKELY: its meshes use the Direct3D convention, front faces clockwise), so the
SR3 import must use the GAME coordinates (x, y, +z). The second-batch steps 14/15 used the OBJ coordinates and were
mirrored; fixed in `build_classic.py`. The data itself is not mirrored. `classic/obj/src_course1_top.png` draws the OBJ
x against OBJ z with z up, which is a mirror image of the real plan; `work/previews/overlay_top.png` is the real plan.

## Colour: RECOVERED STATICALLY (fifth package) - `work/scripts/i960.py`, `m2boot.py`, `m2colour.py`
- A small i960 disassembler + interpreter was written (`i960.py`: REG / COBR / CTRL / MEMA / MEMB formats, the integer
  instructions the routines use). Running the program from its reset vector (start IP 0x420 from the initial memory
  image) shows the boot code clearing work RAM and then copying the initialised data ROM 0x1000.. -> RAM 0x5A0000..
  (loop at 0x528; RAM address = ROM address + 0x59F000). VERIFIED by execution.
- The palette upload (0x267B0: `count = [0x5FB89C]; copy 16-bit words from 0x5FB89E to 0x1802000`, i.e. palram entry
  0x1000 + colour base) therefore reads program ROM 0x5C89C: a count (541) and 541 15-bit colours (5 bits each,
  red in the low bits). ONE global table for all four courses - there is no per-course palette. VERIFIED (disassembly
  + the values: asphalt tiles map to grey 104,104,104, tree tiles to greens, the rock tile to tan 208,144,96, house
  walls to sandstone and pink).
- Luma RAM: the self-contained routine at 0x4590 was executed in the interpreter: it fills two 128-entry ramps
  (base 0: texel*4, base 1: slightly steeper, up to 63). VERIFIED by execution; other bases are not written by it.
- colorxlat (0x1810000): 0x330A0 copies it from RAM tables at 0x210830 / 0x211830 / 0x212830 that other code computes
  (brightness / fade state at 0x213834, 0x213838). NOT emulated. The tiles assume a linear table
  (output = colour x luma / 63) and no gamma, and full polygon brightness; so hue is right, absolute brightness and
  contrast are approximate (the renders look somewhat dark).
- Result: coloured tiles in `work/classic_tex/course1/textures/`, coloured renders `work/previews/blender_classic_*.png`,
  and coloured DXT1 textures inside steps 17, 19, 20.
The MAME dump steps below are now only needed for an exact colorxlat/gamma.

## (older) manual MAME steps
The renderer (DOCS, model2rd.ipp `draw_scanline_tex`) computes
`luma = lumaram[lumabase + texel*8] * polygon_luma / 256` (clamped to 63), `colour = palram[0x1000 + colourbase]`
(15-bit, 5 bits per channel), then `colorxlat[channel][colour5][luma]` and a gamma table.
- palram (0x01800000): written from RAM (pointer cells 0x5FB89C / 0x5FB89E beside the constants 0x01800000 /
  0x01802000 at maincpu 0x267BC, 0x33400, 0x33780): built or faded at run time. Scans of both ROMs for 15-bit colour
  tables found only the 16-colour palettes of the 2D tile graphics.
- lumaram (0x12800000, code near maincpu 0x4594) and colorxlat (0x01810000, code near 0x330C0) are filled by code too.
A static reconstruction would need an i960 disassembler/interpreter for those routines; that was NOT done (no i960
tool at hand; the routines were only located, not traced). The practical route, about five minutes by hand:
1. Start MAME with the debugger: `mame srallyc -debug` (any recent MAME; in the debugger window press F5 to run).
2. Play until the MOUNTAIN course is on screen in daylight (Championship third stage, or Practice -> Mountain) and the
   car is driving on the first straight.
3. Press the debugger break key (` or F12 in the debugger window) and type these three commands in the main CPU console:
   `save palram.bin,1800000,4000`
   `save colorxlat.bin,1810000,c000`
   `save lumaram.bin,12800000,20000`
4. Copy the three files from the MAME folder to `F:\Jogos\SEGA Rally 3\SR3 track format\work\tmp\m2\`.
With them the tiles can be coloured exactly: per material colour base (the `_cXXX` in the name) and luma base
(header word 1 low byte, kept by `classic_export.material`). The tiles delivered now are LUMINANCE (texel x 17).

## Use in SR3 (step17)
Each classic tile becomes a DXT1 texture (grey, full mip chain) under a header cloned from a Stadium4 512 x 512 DXT1
texture, with one cloned material per tile (`build_classic.py`: `dxt1_grey`, `make_texture`). Translucent tiles are
written as DXT1 punch-through (transparent texels on the top mip level); whether the cloned SR3 material alpha-tests
is UNKNOWN (it is a clone of an opaque wall material), so in game the cut-outs may show a black surround. Classic uv
values run past 1 on tiling polygons; the SR3 vertex format used (uv = u16/32768) holds 0..2, so 422 of 13247 faces
are clamped (it was 3820 before the pointer fix).

## Exact colour table (sixth package) - `work/scripts/m2xlat.py`, `i960.py` (floating point added)
This replaces the "linear colorxlat" assumption above. VERIFIED by executing the game's own code in the interpreter.
- The boot code at 0x3720 calls 0x3C80, then 0x4350, then the luma routine 0x4590. The tables at RAM 0x210830.. that
  0x330A0 copies are only fade copies (state machine at 0x33180: read the hardware table back to 0x20D830.., scale it
  into 0x210830.., write it out); they are not the source.
- 0x3C80 fills the whole table: 3 channels x 32 colour levels x 256 entries (16 bit, high byte 0) at 0x01810000 /
  0x01814000 / 0x01818000. R = G = B. It is a gamma-like curve (constants 0.7 and 0.85 at ROM 0x3C70), e.g. level 31:
  luma 0,16,32,48,63 -> 0, 94, 146, 200, 255; level 16 -> 0, 74, 111, 144, 176. Largest difference from the old linear
  guess: 73 of 255. The values are used directly as display values.
- 0x4350 then OVERWRITES rows 1, 3, 5, .. 19 (luma 0..63) with ten key-frame colour gradients read from ROM 0x3EB0
  (`count, count x {position, r, g, b}` as floats). The palette only uses even channel values, except ten entries with
  r = g = b = 1, 3, .. 19: those are not greys, they select a gradient, and the texel luma then picks the colour.
  Mountain uses two: palette 0xEE (13,13,13) = row 13, black -> blue-grey -> warm white: the asphalt; palette 0xDF
  (15,15,15) = row 15: black / red-brown / yellow / white / blue bands: the SEGA boards. That is why the boards came out
  grey before: they are blue on white (SEGA), red (SEGA circle) and yellow (SEGA SATURN).
- Luma: the course's materials use luma base 0 (105) and base 1 (25); both are filled by 0x4590. Polygon brightness
  (lighting) is still taken as full.
Outputs: `work/tmp/m2/colorxlat.npy`, coloured tiles in `work/classic_tex/course1/textures/`,
`work/retex/classic_tiles_contact_colour.png`, and the textures inside steps 17 and 19..23.

---
# Later additions (2026-10-07 / 08)
- Course identification is no longer LIKELY: the game's own course-id tables give 0 Desert, 1 Forest, 2 Mountain, 3 Lake
  Side, and the export numbers 1 Mountain, 2 Desert, 3 Lake Side, 4 Forest (18_src_1995_rom_data.md, section 1). VERIFIED.
- Handedness: confirmed in game. SR3 takes the game's own coordinates, as the "Handedness" section says (importer constant
  `ZS = -1`); the opposite was tried for a few hours and mirrored the world (11_importer_prototype.md, corrections).
- The texel page of a course is one contiguous 1 MB block, recorded per course in the settings file (`texel_block`,
  Mountain 0x600000) (comment in `classic_tex.py`; agrees with the page fit above).
- Desert's and Forest's unreadable tiles (14_importer.md) were re-exported later "with the right texel block"
  (13_retexture.md, hand-over section).
- How the decoded colours compare with the real game: Model 2 emulator shots show the mid tones far darker than the
  decoded tiles while white stays white; a gamma of 1.7 applied to the tiles matches rock, sea and sky, and in game the
  owner judged "colors are perfectly matched" (23_texture_pipeline.md, section 1). So the colour TABLE above is exact, but
  the picture the emulator finally shows is darker in the mid tones than these tiles. Why is not traced in the sources
  (UNKNOWN; the renderer's gamma table and the per-polygon brightness named above were never recovered).
- Finding a model from a texture seen in the emulator (texture-cache dump method): 18_src_1995_rom_data.md, section 8.
- The polygons carry UVs that the importer must treat specially (front / back pairs with different picture halves,
  smeared and over-repeated uv): 18_src_1995_rom_data.md, section 10.
- Use of the tiles in SR3 beyond step17 (encoding, signed uv, clamp, re-authored tiles): 23_texture_pipeline.md. The
  statements "uv = u16 / 32768 holds 0..2" and "422 of 13247 faces are clamped" in "Use in SR3 (step17)" are superseded
  there: uv is signed and faces are cut instead of clamped.
