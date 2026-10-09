# Converting SEGA Rally Revo (PS3) tracks to the arcade's PC format

Status: CONFIRMED in the game. arctic2 and safari2 (PS3) load, drive, have grass, and the AI
races normally; tropical2/tropical3 and the PC demo's canyon2 load too. The converter is
`SR3CamLab\ps3conv.cs` + `ps3model.txt` (C#, byte-identical to the Python reference
`ps3conv.py` in the scratch folder on all 144 files + 24 grass caches).

## Sources

- PS3 disc "SEGA Rally" BLES00107 (= Revo): `USRDIR\main_release\tracks`, 24 routes
  (alpine, arctic, canyon, safari, tropical, lakeside...). Big-endian; textures in `.vbf`.
- Ground truth: SEGA's free Revo PC demo (archive.org item SEGAPCDemo) has canyon2 and
  tropical2 in PC format, same data as the PS3 disc. Everything below was learned by
  comparing those two tracks on both platforms.
- The arcade exe loads only 7 files per track (see game-runtime-and-frontend.md). The PS3
  `master_gfx_data` / `master_data` / discard files are an older duplicate build: ignore.
- No PS3 track uses a shader or mesh format the arcade lacks. CORRECTED later (13_revo_vs_arcade.md, section 1.1): 16 of
  the 24 tracks have materials on the shaders `i_pl.fx` / `i_pl_psm.fx`, which the arcade shader libraries do not
  contain, and three tracks have a mesh in vertex format 0x20C1 that no arcade mesh uses. A fix pass rebuilds those
  materials after conversion (13_revo_vs_arcade.md, section 5).

## Container (see also the container notes of this knowledge base)

- `SBZ1` + u32 size + zlib, or raw. Header u32 4, ..., count at 0x14, then (id, offset).
  Chunk = kind, id, size, 0, nfix, fix[], nref, ref[], data. Ids are resource hashes and are
  the same on both platforms.
- The arcade `.sbf` = PS3 `.sbf` + `.vbf` merged (the vbf holds the kind 4 pixel data).
- Writer rules that crash the game when broken: chunk DATA at file offset %16 == 0 for kinds
  5/6/11/13, == 4 for kind 4, == 8 for kind 7 (pad before the chunk header); chunks start at
  0x1000 or later; 2048 zero bytes at the end.

## Per chunk kind

- 1 mesh: per-LOD header is 0x108 bytes on PS3, 0x48 on PC. Positions are half floats on
  PS3 (precision loss is visible only up close), normals/tangents packed 11/11/10 in 32 bits,
  UVs 2 x u16 with the same values. Index strips: PS3 uses 0xFFFF restarts, PC joins strips
  with repeated (degenerate) indices. Same triangles on both.
- 2 material: PS3 has 0xC8 bytes of padding after word 0; otherwise swap32 with strings
  left raw (strings start on a word boundary).
- 3 shader stub: tiny; arcade tracks use 3 shader ids, all present on PS3.
- 4 texture: 11 header words (word 1 = self-relative pointer on PS3), then "DDS " + the
  124-byte DDS header (32-bit swapped on PS3) + pixels. Blob length = chunk size - 48.
  Pixel data is identical on both platforms.
- 5 and 11 pointer-linked structures: no type tags. Layouts were LEARNED from the demo
  pair (`learn2.py` -> `ps3model.pkl` -> `ps3model.txt`): cut each chunk into blocks at
  pointer targets; a block's role = the path of pointer-field offsets that leads to it; per
  role, each word gets a byte permutation (swap32, 2 x swap16, raw, and three mixed ones).
  Block layouts are uniform, records (header + period) or fixed. A chunk's first record is
  a header. Fallbacks, in order: signature (size + pointer positions, only when the block
  has pointers), string (3+ printable chars with a NUL in the last 7 bytes), nearest sibling
  role, size-only signature (8+ words), text-mask guess.
- 6: swap32. 7: raw bytes. 12 typed objects: per (type, size) byte permutation.
- Grass cache `*_proc_cached.bin`: header 16 x u32; section 0 {u32, u16, u16}; section 1
  96-byte records (two u16 at 0x54); section 2 u32; section 3 a bitfield 8,5,8,10,1
  (PS3 MSB first) -> PC `A | F<<8 | Y<<13 | X<<23 | Z<<31`; sections 4-6 u32; section 7 u16
  count then per cell u16 id + byte pairs until `ff 00` (`ff ff` = empty). Byte-exact
  against the demo.

## Accuracy

- Zero residual words against the demo tracks; cross-test (learn on one, convert the other)
  9 or fewer wrong words out of 6 to 8 million.
- 22 of 24 tracks have 0% guessed words; arctic1 and arctic6 about 8%; tropical1 has one
  mesh that fails. Both loose ends were fixed afterwards (mesh header limit 16 -> 64; unknown scenery-tree class falls
  back to the model's tree class): 13_revo_vs_arcade.md, section 3.
- How the facts in this file were first learnt (owner's notes, 2026-10-06): PS3 and arcade TRACKS share 2,080 resource
  ids (261 meshes, 450 kind 2, 3 kind 3, 993 textures, 327 kind 5, 32 kind 7, 14 kind 12); 295 files exist on both
  platforms; of 864 matched textures 837 are byte-identical and the rest are real art changes; the simple kind 5 rule
  (fixup words and everything else swap32, text runs raw) is exact on 1088 of 1430 shared structures; PS3 tracks use
  about 70 (stride, format) mesh combinations, arcade tracks 42; PS3 tracks carry 15 shader ids, arcade tracks 3.
  VERIFIED (measurement on files).
- `Alpine4\Alpine4.rar` in the arcade dump: an 85 MB RAR with encrypted headers, dated 2008-04-09 (20 days before the
  track files); nothing is known about its content (UNKNOWN).

## Bugs found the hard way (each one was a crash or broken gameplay)

- Unaligned chunk data: crash while loading.
- A pointerless signature matched the wrong layout (a count stayed big-endian), and a chunk
  header folded into the record period: crash. Signatures now need pointers; the chunk root
  has its own header rule.
- One-word blocks holding round floats (0.75, 3.0) look like text and were left unswapped
  in the route data: AI cars stopped at the first checkpoint of arctic2. Strings now need 3+
  characters. Evaluation must compare string blocks strictly, not mask them.
- New folder names via the database: blank cards (names are hard-coded in the exe).

## How SR3 Extras installs a track

- Replace mode (any slot): files renamed to the slot's prefixes (`<xxx>_track_route<N>_`,
  `<name><N>_`), originals moved to `tracks\_SR3Extras\original\<slot>`.
- Alternative mode (the three stage cards): `Main_release\track<k>\<slot>\` beside the
  game's own, a card video `LANG_<lang>_<TR|CA|AL><k>.wmv`, and `tracks\_SR3Extras\switch.json`
  for the in-memory switcher. Nothing original is replaced. CONFIRMED in the game.
- Full description (the `track<k>` digit and the limit of nine, switch.json, classic.json, side files):
  21_track_install_and_switching.md.
- AI cars stopping at the first checkpoint of arctic2 (bug list above): the suspected cause was the unswapped round floats
  in the "Route Path Spline" chunk of master_xdata; the status line at the top of this file ("the AI races normally") is
  the later statement, the owner's notes of the same day still say "fix NOT yet confirmed in game". Recorded as LIKELY
  fixed.
