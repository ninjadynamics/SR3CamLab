# Track sources for the "Classic" epic: SEGA Rally Championship and SEGA Rally 2

Plan (user's): put imported classic tracks under SR3's "Classic" mode, swapping with
Desert 95 (slot Desert4). Phases: geometry with flat shading, then SR3 textures, then the
original textures; SR3's own skies, spectators and objects.

Everything here comes from an investigation that parsed the user's own romsets (read-only).
Scripts, emulator sources and outputs: `<scratchpad>\sr_classic\` (scripts, src, roms, obj).
VERIFIED = parsed from the ROMs; DOCS = taken from emulator sources.

## SEGA Rally Championship (Model 2A, `Model 2\Games\srallyc.zip`): easy

- ROM regions (DOCS: MAME model2.cpp, all ROM_LOAD32_WORD): program epr-17888c/17889c;
  main data mpr-17746/47, 17744/45, 17884/85 (maps to 0x02000000); coprocessor data
  mpr-17754/55 (collision); polygons mpr-17748/50, 17749/51; "textures" mpr-17753/52 (UV
  lists and texture headers, not texels).
- Object table at main-data offset 0x864B48: 1,508 entries of 16 bytes {polygon address |
  0x800000, polygon count, UV address, header address}. VERIFIED (counts match the decoder).
- Geometry (DOCS model2_v.cpp, VERIFIED on all objects): strips; two starting points
  (3 floats each), then 10 words per link: attribute, normal (3 floats), two points.
  Attribute bit 0 quad, bit 1 triangle, 0 end; bits 8-9 link type (type 0 = connector, not
  drawn). IEEE floats, metres, Y up, Z forward, left-handed.
- A course = 60 consecutive objects ALREADY IN WORLD COORDINATES, then 2-3 sky objects, then
  60 low-detail twins. Courses (numbering by collision block, names unconfirmed): 1 =
  objects 1259-1318 (3,494 m), 2 = 937-996 (3,210 m), 3 = 1379-1438 (3,147 m),
  4 = 1135-1194 (4,196 m).
- Collision (VERIFIED, own finding): one block per course in the coprocessor data: u32 cell
  count (300), padding to 0x40, 300 variable-length cells, index table. A cell = K polygon
  records of 16 floats (4 corners + 4 floats, often the plane equation) + one attribute word
  per polygon. Attribute bits 16-19 look like surface types (values 0,1,2,3,4,6,8,9), bit 23
  marks off-road side quads. Mapping to tarmac/gravel/mud not decoded.
- Section tables for course 1 at main-data offset 0: 300 sections, 600 boundary points,
  300 quads, 300 (cos, sin) direction pairs. Other courses' tables not located.
- Not found: start grid, checkpoints. Textures not decoded (4-bit luminance + palette base
  in texture RAM; emulator texture dump is the practical route).

## SEGA Rally 2 (Model 3 Step 2.0, `Model 3\ROMs\...\srally2.zip`): easy to moderate

- ROM regions (DOCS: Supermodel GameLoader/Model3.cpp; the user's Games.xml): fixed CROM
  epr-20632..20635 (8 MB, program + tables, copied to RAM at 0, so file offset = address);
  banked CROM mpr-20602..20613; VROM mpr-20616..20631 (64 MB polygon models, little-endian
  32-bit words).
- Geometry (DOCS New3D.cpp, VERIFIED on ~2,900 course models): 7 header words + 4 words per
  new vertex; quads or triangles; up to 4 vertices reused from the previous polygon;
  positions 13.11 fixed point, UV 16-bit pairs. Metres, Y up, Z forward, left-handed.
- A course is STATIC tables in the fixed CROM: scenery descriptor group at 0xCF180 (384,
  324, 1136, 341, 452 records for the five courses), road group at 0xDE1F8 (256 per
  course). Block record = 48 bytes big-endian: float x, y, z (world position), u32, then
  4 x {VROM model address in words, u32} for four LODs. Vertex world position = vertex +
  block xyz, no rotation. Road blocks are in driving order.
- Second per-course polyline at CROM 0xE2C0C (purpose unknown; AI line or map).
- Not found: roadside object placement (models are in the 2,716-entry table at 0xA4BA8),
  collision, surface types, checkpoints, start grid. Textures not decoded.

## Outputs (`sr_classic\obj\`)

- `src_course{1..4}_hi.obj` / `_low.obj` (+ .mtl, UVs, one object per section),
  `src_course{1..5}_collision.obj` (grouped by attribute), `src_course{1..5}_centreline.csv`.
- `sr2_course{0..4}_lod0.obj` (+ .mtl), `sr2_courseN_centreline.csv`,
  `sr2_courseN_pathline_raw.csv`, top-down PNG plots.
- Lap lengths 1.9 to 4.2 km, loops close within 7 to 17 m.

## Recommendation and open points

- Start with SEGA Rally Championship: simplest geometry, and it comes with collision and
  surface codes.
- Open: textures for both; course names and handedness (compare a plot with a course map;
  if mirrored negate X instead of Z); surface code meaning; SR2 object placement and
  collision; start grid and checkpoints for both; a few stray polygons on SRC course 2.

## SEGA Rally 2 audio (extracted; not yet installed or listened to)

Copies of the outputs are kept in `classic\` next to this file (obj, scripts, audio).

- Speech and effects: sound-board sample ROMs mpr-20614.22 + mpr-20615.24, raw signed 8-bit
  mono PCM, 16-bit words byte-swapped in the file. VERIFIED.
- Sound driver epr-20636.21 (68K, mapped at 0x600000): sample table at 0xA62A (230
  entries {start, length (top bit = loop), loop start}); tone table at 0x84D8 (268 x 12
  bytes {sample, SCSP pitch word, flags}; entries 155-267 are the 113 voice clips); request
  table at 0x9192 (groups 0x10-0x1A; a request = a small track of notes, multi-clip calls
  carry delays). Sound-test names (VO_, SE_, BM_) in the main program at 0xE3168, 3-byte
  request codes at 0xE2C4C. VERIFIED (own finding, not in emulator sources).
- Voice rate: the pitch word 0xF000 alone gives 11025 Hz, but that plays an octave low
  (heard in game: slow and muffled). 22050 Hz is right; the request's note must add the
  octave (rule not yet read from the data).
- 113 voice clips in `classic\audio\sr2_codriver\` with `index.csv`: 107 labelled with high
  confidence from request names, 6 medium. Unknown abbreviations: `K` (a corner grade,
  guessed tight/90 degrees) and `D` in D_TIGHTEN. Each length/"maybe" variant is its own
  recording; there are no single-word clips to combine.
- Music: MPEG board ROMs mpr-20637..20640, MPEG-1 Layer II 32 kHz stereo 128 kbps; 12
  tracks split without re-encoding in `classic\audio\sr2_music\` (which is which: unknown).
- SR3 side: 305 speech streams (111 corner calls, 71 hazards, 14 race flow, 16 praise, 20
  positions, 73 menu/names). `mapping.csv`: 93 exact, 19 close, 77 approximate, 116 with no
  SR2 equivalent (those keep the SR3 voice).
- `classic\audio\sr3_ready\`: 189 replacement WAVs, 32000 Hz mono, exactly the byte size of
  their SR3 slot, rendered at 22050 Hz: 186 fit unchanged, 3 are slightly sped up.

## Music of the classic games (prepared, not yet heard in SR3)

Outputs in `classic\music\` (sr2_music = exact cuts as .mp2 + index.csv, sr3_wav = stereo
32 kHz WAVs ready for the stream-bank rebuilder, sr3_mapping_proposal.csv, src_samples).

- SEGA Rally 2: tune table in the MPEG board program epr-20641.2 at 0x8000 (count 15, 14
  record pointers: routing, start, end, volume, loop start when flag 0x80). The main
  program's BM_ sound-test names carry request codes `AE 10 nn` = table index. VERIFIED.
  Tunes: BM_ADV1, ADV2 (attract), MOUNTAIN, FINISH, SNOWY, N_MOUNTAIN, RESERVE1/2 (cuts of
  other tunes), ENDING, RESULT, DESERT (137 s, loops whole), SELECT, IGNITION, GAMEOVER.
  Mountain, Snowy and N_Mountain loop after a ~25 s intro; SR3 streams can only restart at
  0, so the prepared files are the loop part (a *_with_intro variant exists).
- Proposed SR3 mapping: Classic/Desert stage <- BM_DESERT (natural fit); Alpine <- SNOWY;
  Canyon <- MOUNTAIN; menu <- SELECT; game over <- GAMEOVER; Tropical/Lakeside have no
  natural SR2 counterpart. Two rebuilt-bank sets: `F:\Jogos\_sr3_bank_sets\sr2_music_classic_only`
  and `sr2_music_full` (music only; merge manifests to combine with co-driver/Arctic).
- SEGA Rally Championship: music is SEQUENCED (sound program epr-17890.30 + PCM
  instruments), so there is nothing to cut out; it would have to be recorded from an
  emulator. 301 PCM samples extracted (five sample tables at 0x9C26, 0x9D7A, 0xA162,
  0xA446, 0xA5D6; 20-byte entries); the fifth table holds 112 speech clips (co-driver,
  "SEGA Rally Championship"...), 21 labelled by offline speech recognition, rate assumed
  22050 Hz.

## What later work superseded in the sections above (pointers; the old text is kept as written)
| Statement above | Now |
|---|---|
| SRC "courses (numbering by collision block, names unconfirmed)" | 1 Mountain, 2 Desert, 3 Lake Side, 4 Forest; the game's own ids are 0 Desert, 1 Forest, 2 Mountain, 3 Lake Side. VERIFIED: 18_src_1995_rom_data.md |
| SRC "attribute bits 16-19 look like surface types ... mapping not decoded" | decoded against the texture under each polygon: 18_src_1995_rom_data.md, section 7 |
| SRC "section tables for course 1 at main-data offset 0 ... other courses' tables not located" | all four located (main 0x0000, 0x3E00, 0x7C00, 0xBA00): 18, section 2 |
| SRC "not found: start grid, checkpoints" | start grid prog 0x3DB20, split points prog 0x1E790, time checkpoints and times: 18, sections 4 and 5 |
| SRC "textures not decoded" | texels, palette, luma and the exact colour table recovered from ROM: 12_classic_textures.md |
| SRC object table "1,508 entries"; later section "1507 objects" | both figures appear in the sources and are not reconciled there. Related fact: the texture pointers of row k belong to the object of row k+1 (12_classic_textures.md) |
| SRC speech: "21 labelled by offline speech recognition, rate assumed 22050 Hz" | 63 speech samples labelled through the sound-request key map: 18, section 6 |
| SR2 "second per-course polyline at CROM 0xE2C0C (purpose unknown; AI line or map)" | a designers' centre line used only by the built-in course-object editor: 19_sega_rally_2.md, section 6 |
| SR2 "not found: collision, surface types, checkpoints, start grid" | all found: 19_sega_rally_2.md, sections 2 to 4 |
| SR2 "five courses" at 0xCF180 / 0xDE1F8 | course ids 2..6 = Forest (unused), Mountain, Desert, Riviera, Snowy; descriptor bases 0xCF168 + 12 x id and 0xDE1E0 + 12 x id: 19, section 1 |
| SR2 block record "4 x {VROM model address in words, u32}" | the u32 is LIKELY a culling / LOD distance, not a count: 19, section 9 |
| SR2 "roadside object placement not found" | still not found; the editor's 20-byte record format is known: 19, section 9 |
| "handedness (compare a plot with a course map; if mirrored negate X instead of Z)" | settled in game for SRC: SR3 takes the game's own axes (11_importer_prototype.md, corrections) |
| SR2 voice rate "22050 Hz is right; the request's note must add the octave (rule not yet read from the data)" | confirmed by ear in SR3 (audio.md, "Co-driver"); the rule in the data is still not read |

## SEGA Rally Championship: is scenery missing from the course exports? (checked 2026-10-07)
- The polygon ROM is covered completely by the 1507 objects of the object table (0x864B48): no polygon data outside
  the table (the only gap, words 951731..1048575, is 0xFF padding). VERIFIED.
- Per course the table holds 60 high-detail objects, 60 low-detail twins and 2-3 backdrop objects. Mountain's low
  objects add nothing: 1254 of 1264 low polygons lie within 5 m of a high-detail polygon. VERIFIED.
- No other object uses a course's sheet-1 tiles in local coordinates at scenery size: there is no table of placed rocks /
  bushes / houses. The only world-placed objects outside the course blocks are 171 (Desert, 2 boards) and 172 (Mountain,
  4 x 2 boards): CHECK POINT banners, 13 m x 1 m, 2.8 m above the road, sheet 0 tile x1280 y0 256x32. Exported as
  `src_course<N>_props.obj` by `classic/courses/scripts/src_all.py props` (run it with work/scripts first on sys.path).
- Mountain trees: about 900 of 1285 trunk groups have NO polygon under them in the 1995 data (red in
  `work/previews/missing_scenery_plan.png`). The original hides the bases behind the roadside wall / bank from its low
  camera. The island is a cliff ring (y 0..18.5) + a foliage shelf and tree wall up to y 39.7, all in backdrop object 1257,
  with no cap; the tree-line tile covers the cliff down to about 5.6 m above the water by its own uv (v 68..128 of a
  128-row tile on the cliff faces). `work/previews/missing_scenery_compare.png`: emulator s069 / s070 against the OBJ.
