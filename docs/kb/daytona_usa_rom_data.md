# Daytona USA (1994, original Model 2): course data in the ROM set, and how it was extracted

Daytona USA's three courses were taken out of the owner's ROM set as geometry with texture coordinates and textures,
without running the game or an emulator: Beginner "Three Seven Speedway", Advanced "Dinosaur Canyon" and Expert
"Seaside Street Galaxy". This page lists what is known about the data. The SEGA Rally Championship pages it is compared
with are [18_src_1995_rom_data.md](18_src_1995_rom_data.md), [classic-sources.md](classic-sources.md) and
[12_classic_textures.md](12_classic_textures.md).

Tags: VERIFIED (how), LIKELY, UNKNOWN. DOCS = taken from MAME (model2.cpp, model2_v.cpp, model2rd.ipp: the copies in
`<scratchpad>\sr_classic\src\mame\`). "Code" = read in the i960 program with `daytona_i960.py`, which uses the
project's `scripts/importer/i960.py`.

Scripts: `scripts/rom_tools/daytona_*.py` (section 10). Extracted data: `SR3 track format\classic\courses\daytona\<course>\`.
Nothing extracted is committed (SEGA data rule).
The Beginner course's import into SEGA Rally 3 (Classic slot, in game 2026-10-14): 14_importer.md, last section.

## 1. ROM set and regions

Archive `F:\Emulators\SEGA Arcade\Model 2\Games\daytona.zip`: a merged set (66 files) that also holds the clones
(daytona93, daytonas, daytonase, Turbo / Maxx / GTX hacks). Only the parent set `daytona` (Japan, Revision A) is used.
All 22 chips used have the CRC32 of MAME's `ROM_START( daytona )`. VERIFIED (unzip -v against model2.cpp).

| Region (MAME name) | Chips (ROM_LOAD32_WORD pairs: first chip = low 16 bits) | Size | CPU address | Content |
|---|---|---|---|---|
| maincpu | epr-16722a.12 + epr-16723a.13 | 256 KB | 0x00000000; second half also at 0x00220000 | i960 program; per-course tables of placed objects (section 6) |
| main_data | mpr-16528.10 + mpr-16529.11 @0, mpr-16808.8 + mpr-16809.9 @0x400000, epr-16724a.6 + epr-16725a.7 @0x800000 (1 MB, mirrored up to 0xFFFFFF) | 9 MB used | 0x02000000 | course gameplay blocks (0x000000..), texels (0x200000..0x5FFFFF), course directory and driving lines (0x600000..), program data, object table, palette (0x800000..) |
| copro_data | mpr-16537.28 + mpr-16536.29 | 4 MB (2 MB repeated) | TGP | road-surface quads per course (section 8) |
| polygons | mpr-16523.16 + 16518.20, 16524.17 + 16519.21, 16525.18 + 16520.22, mpr-16772.19 + 16771.23 | 16 MB | geometry engine 0x800000 + word | polygon strips |
| textures | mpr-16522.25 + 16521.24 @0, mpr-16770.27 + 16769.26 @0x800000 | 16 MB (0x400000..0x7FFFFF empty) | rasterizer, 16-bit words | texture-coordinate lists and texture headers (NOT texels) |

- mpr-16524/16519, mpr-16525/16520 and mpr-16537/16536 hold 1 MB each and repeat it in their second half. VERIFIED
  (halves compared).
- Region images are built by `daytona_build.py` exactly as MAME lays them out. DOCS + VERIFIED (all tables below
  decode from them).
- Difference from SEGA Rally (Model 2A): the program is 256 KB instead of 2 MB; much of the game's table data lives in
  the 1 MB EPROM pair at 0x02800000 (the TGP program upload starts there, ROM text "Interrupt Halt #" at 0x02800000).

## 2. Object table

- main data 0x83FBB4 .. 0x84F4EC (CPU 0x0283FBB4), 3190 records of 20 bytes `{oba, tpa, tha, obc, 0}`. VERIFIED: code
  at program 0x17ACC checks a pointer against exactly these two bounds before drawing it; the polygon count `obc`
  matches the strip decoded at `oba`; the texture-header pointer, advanced by every polygon's signed step, lands on the
  next record's `tha` for 3112 of 3161 consecutive pairs (the rest are block boundaries).
  - `oba` = 0x800000 | word index in the polygon ROM (records 2139..2165 use polygon RAM: 0x0000xxxx).
  - `tpa` / `tha` = 16-bit word index into the "textures" region (bit 23 set = texture RAM).
  - `obc` = polygon count; 0 = up to the end word (MAME geo_object_data: 0 rolls over).
  - The texture-point list of a record with `obc > 0` ends with 8 extra zero words (the end record); with `obc = 0` it
    does not. VERIFIED (1935 + 1014 of 3161 chains exact).
- Rows: 0..195 = 49 models of 1.8 x 1.3 x 5 m in 4 levels of detail (the cars, LIKELY by size), then animation frame
  sets in course coordinates (wind turbines 196..259, banners 260..515 ...), the flat course maps of the HUD (768
  Beginner, 1192 Expert, 779 Advanced: table main data 0x8052DC, drawn by program 0x1308C turned 90 degrees about X),
  people built from parts, 1599 the Jeffry statue, the polygon-RAM rows, and the four course grids 2166..3189
  (section 4). VERIFIED for the rows that sections 4 and 6 name; the rest were only classified by size.
- Difference from SEGA Rally: SRC's table (main 0x864B48) has 16-byte rows; its "texture pointers of row k belong to
  object k+1" is the same thing seen with a different start alignment. Daytona's record is self-contained.

## 3. Polygons and texture coordinates

- Strip format as MAME geo_parse_np_ns: P0, P1, then 10 words per link {attribute, normal, P0(n), P1(n)}; floats, metres,
  Y up, Z forward (left-handed). The ROM is laid out in uniform 10-word records: `oba` points 4 words into the first one.
  VERIFIED (all 3190 objects decode to their counts).
- Attribute bits (DOCS): 0 quad, 1 triangle (0 = end), 8-9 link type (0 = connector, not drawn), 10-11 z-sort (1 = nearest
  vertex, 2 = farthest; the course cells use only these two), 12-16 signed texture-header step, 17 double sided, 18-22
  light-parameter index, 27-31 texture LOD coefficient index.
- Visible side: the stored normal points away from the viewer (MAME: front when normal . point >= 0); the exporter turns
  faces so that their winding shows that side. VERIFIED in the renders (no inside-out walls, text reads right).
- Double-sided polygons (attribute bit 17): Beginner 1576, Advanced 687, Expert 2851 (cells + placed objects). The OBJ
  writes them once, into a separate object `<name>_2s`, so an importer can give them a back face. VERIFIED (counted).
- Texture coordinates: per vertex two 16-bit words, v then u, unsigned 13.3 fixed point texels, in the vertex order
  v0 = P1(n-1), v1 = P0(n-1), v2 = P0(n), v3 = P1(n). VERIFIED: 0 degenerate uv on the Beginner course, 14 and 31 on the
  others (0.1 %); every sign, banner and board reads the right way round in the renders; the 72 Expert polygons with
  u above 4095 are 1 km strips whose u runs 0 .. 8191.875 (unsigned is right, signed would break them).
- Texture header (4 words, DOCS): word 0 bits 0-2 width 32 << n, 3-5 height, 8/9 mirror, 12 microtexture, 13 translucent,
  14 textured, 15 checker; word 1 low byte luma table; word 2 bits 0-5 x / 32, 6-10 y / 32, 12 sheet; word 3 bits 6-15
  colour (palette entry). The courses use no mirrored or micro textures. VERIFIED (counted).
- Layering: there is no depth buffer. Decals, the Sonic figure on its rock frame, signs on walls, lie exactly in the
  plane of a larger polygon. 640 / 1036 / 937 such polygons (Beginner / Advanced / Expert) were found by the exporter's
  plane-and-overlap test; the `_lifted.obj` moves them 1.5 cm per layer. VERIFIED (the Sonic figure shows only in the
  lifted file).

## 4. How a course is stored

- Course id = byte RAM 0x501460, about 80 code references: 0 Beginner, 1 Expert, 2 Advanced, 3 a fourth grid. VERIFIED:
  the lap table at main data 0x805248 holds {8, 2, 4, 8} laps for normal play, {20, 5, 10, 20} and {80, 20, 40, 20} for
  the longer races, which are the known Beginner / Expert / Advanced counts; the texture sets (section 5) carry the
  matching scenery (casino and Sonic / Jeffry and the town / fossils).
- Each course is a 16 x 16 grid of 128 m cells, one object per cell, ALREADY IN COURSE COORDINATES: pointer tables of 256
  object-table addresses at main data 0x84FCCC (Beginner), 0x8500CC (Expert), 0x8504CC (Advanced), 0x8508CC (id 3);
  program 0x464C loads them from 0x02805298 + 4 x id. Cell (row r, column c) covers x = 128 (c - 8) .. 128 (c - 7),
  z = 128 (r - 8) .. 128 (r - 7). Empty cells point to a 1-quad dummy object. VERIFIED (pointers; the decoded bounding
  boxes fall in their cells).
- Grids: Beginner rows 2678..2933, Expert 2422..2677, Advanced 2166..2421, id 3 2934..3189 (a round 680 m layout lit
  with the Beginner textures; not exported; purpose UNKNOWN).
- One level of detail only: no low-detail twins (SEGA Rally has 60 high + 60 low objects per course). VERIFIED (the
  pointer table has one entry per cell).
- Course directory (program 0x46E8, 0x4770): main data 0x600020 + 0x20 x id, 8 pointers; word 4 = eight {pointer,
  count} pairs of driving lines (section 7). Word 1 (Beginner 0x02000000) = a section block {195 sections, 503, then
  section -> list words}; word 5 (Beginner 0x020007EC) = {195, 8, 1537} + 20-byte points {x, y, z, heading << 16, 0}:
  8 points 3 m apart ACROSS the road per row (a lane grid). Layout VERIFIED by reading; use UNKNOWN.

## 5. Texels, palette and colour

- Texels: 4 bit, uncompressed, in main data as 1 MB sets: 0x200000 Beginner (and id 3), 0x400000 Expert, 0x300000
  Advanced (table program 0x15A0, read with the course id at 0x1438), 0x500000 common (program 0x1454). VERIFIED (code +
  pictures).
- Upload (program 0x146C): the first 0x60000 words of a set go straight to texture RAM (course set to RAM 0 = sheet 0,
  common set to RAM 1 = sheet 1, one 16-bit word per 32-bit address); the last 0x20000 words are the mip levels and are
  spread over BOTH RAMs, alternating with a step table at 0x1578 (mip level 1 of a sheet lives in the other sheet, as
  the renderer expects). `daytona_tex.upload` is that routine; the mip quarter of each sheet shows half-size copies of
  the other sheet. VERIFIED (code, and the picture of the result).
- Texel addressing as MAME get_texel. In that (x, y) space Daytona's pictures are TRANSPOSED (text runs down the sheet);
  the texture coordinates compensate, so the textures read normally on the polygons. VERIFIED (renders). SEGA Rally's
  pages read upright.
- Palette: main data 0x84F4EC, 1007 15-bit entries (red in the low bits), copied unchanged to palette RAM 0x01802000 by
  program 0x5C7C. One table for all courses. VERIFIED (code). (SEGA Rally: 541 entries in the program ROM's data.)
- Luma tables: main data 0x802FC4 = count 66, then 128-byte tables copied to luma RAM by program 0x13F8. Table 0 =
  texel x 4 (0..60), 1 = 63 - texel x 4, 2..65 = 64 phases of a wave (animated water / shimmer; Advanced and Expert use
  a few). VERIFIED (code + values).
- Colour table (colorxlat) is computed by program 0xA74: value = (level x 12 x luma + 4448) >> 6, capped at 255, 0 when
  level x luma = 0 (setting [0x5FE5E2] = 0 assumed; the other setting uses 10 / 0x1920). A straight line, not SEGA
  Rally's curve with gradient rows. VERIFIED (code).
- Brightness of a polygon: luminance = |normal . light| x diffuse + ambient from the light parameters at main data
  0x805120 (32 entries, uploaded by program 0x5958): index 0 = diffuse 127 / ambient 63, 2 = 127 / 111, 3 = full
  brightness, 4 = 127 / 127, 1/5/7 add specular (cars). VERIFIED (code + table). The light vector was not found
  (UNKNOWN), so the tiles are baked flat with |normal . light| = 0.7 (assumption, `daytona_tex.FLAT_DIFFUSE`), and the
  light index is part of the material name (`_p<n>`).
- Display curve: MAME's (value - 64) x 255 / 191 is applied. DOCS; how close this is to a real cabinet is UNKNOWN.

## 6. Placed objects (on top of the cells)

- Program 0x33BFC: per course id a table of 256 pointers (one per cell): 0x233C0C Beginner, 0x234374 Expert, 0x234D90
  Advanced, 0x2354B4 id 3 (all zero). A pointer leads to {count, count x 24 bytes {float x, y, z; u16 angle (65536 =
  360 degrees); u16 parameter; handler; data}}. 35 / 63 / 32 records. VERIFIED (code at 0x4534..0x46E4 and the
  handlers; positions land on the course).
- Handlers read (TGP function numbers: 0x05 push, 0x06 pop, 0x12 translate, 0x13 scale, 0x14 / 0x15 / 0x16 rotations,
  0x15 = about Y; "local x -> (cos a, 0, sin a)" as MAME's model1 matrix_roty). VERIFIED: pit-wall boards placed at
  60 degrees lie flat on the diagonal pit wall and read right.
  - 0x220118 static object: translate + rotate Y, object = data.
  - 0x2201BC sponsor board: object = frame 0 of the list chosen by the parameter (table 0x236B50, 16 bytes {list,
    24, 8, 0}; 3 frames cycling).
  - 0x2210A0 waving banner: position and scale (s, 1, s) from table 0x236D60 (24 bytes {s, x, y, z, list, final-lap
    list}), angle from the record, frame = counter & 63.
  - 0x220898 / 0x2207C8 signs that turn; 0x220A54 start-gantry panel (object 801, 802 on the final lap);
    0x220D34 wind turbines (blades = frame list 0x2361B0, towers 854 / 855); 0x2202C4, 0x220698, 0x220730, 0x2211FC,
    0x2212A4, 0x221E40, 0x221EF8, 0x222018: frame lists already in course coordinates (flags, water, lights).
  - 0x221618 + data 0x220E54 (Expert): the Jeffry statue, object 1599 at (-1028, 86.7, 868); it turns when the player
    stops in front of it (code 0x220E78..0x220F98).
  - Not exported: people (0x2212E4 manager, 0x221700 / 0x221664 / 0x221698 / 0x2216CC, built from body parts), the
    position / lap digits of the start gantry (0x220B08), the slot machine reels (0x220364), the turning banner
    0x220948, and the animals / birds of the Expert course (0x222080, 0x222314, 0x2224F8, 0x222608, 0x222A20).
    `placed_objects.json` lists every record with its status.
- Animated objects are exported at frame 0. Difference from SEGA Rally: SRC places sprites and gates through a
  trackside table of {angle, x, y, z, section, kind, model}; Daytona puts code addresses in the records.

## 7. Driving lines, length, checkpoints

- Eight driving lines per course (course directory word 4), records of 28 bytes {x, y, z, float, 6 x u16}; Beginner 196
  points, Advanced 487, Expert 991, about 8 m apart, closed (last to first one step). The float is 0.6 .. 1.42 (meaning
  UNKNOWN). VERIFIED (data).
- Lap length (line 0): Beginner 1.56 km, Advanced 3.83 km, Expert 7.57 km. With the lap counts 8 / 4 / 2 this gives
  races of 12.5, 15.3 and 15.1 km, i.e. about 3 minutes at 300 km/h. Scale = metres: LIKELY (consistent, not measured
  against the real game).
- Every point of driving lines 0, 1 and 5 of all three courses lies on a coprocessor road quad at the same height
  (within 0.25 m) and on a floor polygon of the export (Advanced: 477..486 of 487 within 0.25 m, all within 0.51 m;
  the misses are on the descent after the tunnel). VERIFIED (`daytona_check.py`).
- Race direction = increasing point number. Beginner runs counter-clockwise seen from above (left turns, as an oval
  should). VERIFIED (plan + line direction).
- Checkpoints: main data 0x823C10 + 4 x id -> {count, driving-line point numbers}: Beginner none, Advanced 142, 275,
  Expert 150, 257, 404, 539, 730. VERIFIED: each lies 3 .. 8 m from a "Check Point" banner record (Expert banner
  parameters 0..4; Advanced 7 and 8). The start / finish banners are Expert parameter 5 (point 990) and Advanced 6.
- Start grid: not found (UNKNOWN).

## 8. Coprocessor ROM: road-surface quads (collision)

- copro_data 0x00 identity matrix; 0x40 sixteen word offsets of an index block per course id (0x30, 0x8000, 0x10000,
  0x18000); 0x80 sixteen word offsets of a quad block (0x19C90, 0x1E690, 0x3AB00, 0x465A0). VERIFIED (layout).
- Quad block: 64-byte records = 4 corners (x, y, z), the centre (equal to the corners' mean for 96..98 %), one word
  (low 16 bits LIKELY a heading; high half 0 or 0xFFFF, meaning UNKNOWN). Beginner 1184 quads, Advanced 2986, Expert
  7239: road, pit lane, run-off and banking. VERIFIED (plotted on the course with the driving line).
- Index block: lists {count, quad numbers}; the key that selects a list was not decoded (UNKNOWN). Surface types and
  walls were not found (UNKNOWN; SEGA Rally's collision carries a per-polygon attribute word, Daytona's records show no
  such field besides the last word).

## 9. What is not in the export

- The sky and the far scenery: no polygon object for them was found; the background code draws the mini-map and car
  markers only. LIKELY a 2D scroll layer (tile graphics), not extracted.
- People, digits, reels, animals (section 6); the id-3 grid. (Cars: section 11.)
- Polygon light per face (flat bake, section 5); the 64-phase luma animations are frozen at the phase in the header.

## 10. Scripts (`scripts/rom_tools/`, run from that folder)

| Script | Does |
|---|---|
| `daytona_paths.py` | paths (scratch, output); override with DAYTONA_SCRATCH / DAYTONA_COURSES |
| `daytona_build.py` | region images from the chips unpacked to `<scratch>/daytona/roms/` |
| `daytona_objs.py` | object table and strip decoder (`python daytona_objs.py` lists every object) |
| `daytona_tex.py` | texture upload, palette, luma, colour; tile baking |
| `daytona_export.py <course or all>` | OBJ + MTL + tiles + materials.json + placed_objects.json + plan.png, and the `_lifted.obj` |
| `daytona_placed.py` | the placed-object tables and handlers (used by the exporter) |
| `daytona_course.py <course>` | driving lines, centre line CSV, camera views |
| `daytona_collision.py <course>` | coprocessor quads as OBJ + plot |
| `daytona_check.py` | the checks quoted on this page |
| `daytona_contact.py <course>` | contact sheet of the tiles |
| `daytona_render.py`, `daytona_preview.sh <course>` | Blender stills through the CPU guard |
| `daytona_i960.py dis <addr> [n]` / `xref <lo> <hi>` | disassembly and literal search in the program |
| `daytona_cars.py` | every car (section 11) as OBJ + MTL + tiles into `<COURSES>/cars/`, with `cars.json` |

## 11. Cars (2026-10-14)

All cars are objects of the table of section 2; geometry in car space, metres, y 0 = ground, game +z = front.
Export: `daytona_cars.py` -> `SR3 track format\classic\courses\daytona\cars\` (63 folders, `cars.json`,
`hornet_0_preview.png`, `all_cars_sheet.png`).

| What | Rows | Polygons | How known |
|---|---|---|---|
| Player Hornet #41, red / blue | 1460 | 359 (325 drawn) | VERIFIED: player struct main data 0x0281E390 = body[3] {1460, 1461, 1835}, 0x0281E39C window frames / nets {1462, 1463, 1793}, 0x0281E3A8 bonnet {1236, 1237, 1802}, 0x0281E3B4 numbers 1..8 {1794..1801}; code 0xD12C and 0xEC8C load them by [RAM 0x501488] |
| Player Hornet #41, yellow / red | 1461 (1459 = identical copy, unreferenced) | 359 | index 1; index 0 / 1 = [0x501464] in single play, LIKELY the transmission choice (not checked) |
| Linked-play Hornet, red without number | 1835 + number 1794..1801 | 345 | index 2, set when [0x5FE588] != 0 (code 0xEBF0) |
| Bonnet (in-car view) models | 1236 / 1237 / 1802 | 170 | the same struct |
| 45 opponent liveries | 0..179, 4 LODs each (144 / 103 / 91 / 16) | | VERIFIED: one geometry, own texture headers (per-polygon palette colour = livery); 43 entries of 48 bytes at 0x0281E404 {7 LOD pointers, shadow 770, int, int, float, int} (the player's entry, LODs {1460, 1461, 1460 ...}, is the one before, at 0x0281E3D4); rows 64 and 172 are in no entry |
| 8 linked-play cars (Hornets #1..#8, eight colours) | 1803..1834, 4 LODs (164 / 119 / 103 / 16) | | VERIFIED: 8 entries at 0x0281EC14, shadows 2121..2135 |
| Opponent wheels: a 4-wheel set in car space, 8 rotation frames | 180..187 (47), low 188..195 (43) | | VERIFIED: code 0x8800..0x8828 draws [car+0x14] then 0x93EC[(angle >> 11) & 7]; LIKELY also the player's in-race wheels |
| Single wheels left / right (tyre + 8-spoke rim) | 805 / 806 (255), low 793 / 794 (38) | | VERIFIED: table 0x238ED4 {805, 806, 805, 806} of the transmission-select screen (code 0x268B4 draws two cars) |
| Others | 796 (326-polygon untextured red / blue body), 795 (427-polygon wheel, SEGA ENTERPRISES tyre), 1836..1839 (#99 livery, 4 LODs), 1840 | | use UNKNOWN |

- Wheel centres (from the wheel sets): x +-0.675 (tyre x +-0.475 .. +-0.875), y 0.36 (= radius), z +1.412 front and
  -1.395 rear: wheelbase 2.81 m. VERIFIED (geometry; the Hornet's arches fit them in the render).
- Textures: all cars use sheet 1 (the common set, main data 0x500000) at x < 1024, outside the mip area, so they do not
  depend on the course. Colour per polygon = palette entry x texel luminance, as the courses (section 5).
- Coplanar decals (numbers, logos) need the `_lifted.obj` as on the courses. Polygon-RAM rows 2139..2141, drawn after
  the body at 0x8808 / 0x8C00, are filled at run time (not in the ROM; content UNKNOWN).
