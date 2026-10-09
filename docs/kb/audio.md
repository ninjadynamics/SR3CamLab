# Audio: speech, ambience, music

Folder `Rally\Audio`. Made with SEGA's "SAM" tool (paths `M:\Audio\Sega Rally SAM\...`).
Status tags as in game-runtime-and-frontend.md.

## Files

| File | What |
|---|---|
| `SFX_HashCode.h` | Text list of every event: `#define SP_Canyon ( 2276 )`. The best index of what exists. |
| `ProjectData.sfx` | Event records, 140 bytes each (name + ids). Not fully decoded. |
| `ALL_AUDIO.sfx` | The sound bank (157 MB): events, sample names, short samples. Not decoded. |
| `EnglishStreamHeader.stm` | Stream directory. |
| `EnglishStreamData.stm` | Stream samples (448 MB): speech, ambience, music. |
| `ID_TRACK_<ENV>_1_Events.bin` | 9612 bytes each (ALPINE, CANYON, DESERT, LAKESIDE, TROPICAL); loaded with the music. |
| `Reverb.bin`, `RowData.bin` | Not analysed. |

## Stream bank layout (VERIFIED by reading and rewriting clips)

- Header file: at 0x100 {u32 offset of first record (0x110), u32 record count (387)}.
  Records are 200 bytes: path[192] (`M:\Audio\Sega Rally SAM\__TempArcade\Temp PC\...`),
  u32 stream index, u32 offset of the info record. Info = source path[192]
  (`M:\Audio\Arcade Source\Speech\English\canyon.wav`), u32 channels, u32 rate,
  u32 byte count, more words.
- Data file: from 0x100, for each stream in INDEX order: the 192-byte source path, then the
  raw samples, 16-bit little-endian PCM. File length = 0x100 + sum(192 + bytes).
- Speech: mono 32000 Hz. Ambience: mono 24000 Hz, stored as _L and _R pairs. Music:
  stereo 32000 Hz.
- A clip can be replaced by overwriting its samples in place (same length; pad with silence
  or cut). SR3 Extras does this for the announcer and keeps the original bytes.

## Announcer stage names

- Routine 0x610DC0 compares the track's folder name and plays an event by NAME through
  0x643E70: `push <name>` operands at 0x610E10 (Tropical4 -> "SP_Tropical" 0x6CF084),
  0x610E3B (Alpine4 -> 0x6CF098), 0x610E67 (Canyon4 -> 0x6CF0AC), then Lakeside4
  (0x610E93), Desert4 "SP_Desert95" (0x610EBF). It is called when a stage is confirmed.
- Stage-name clips exist only for Tropical, Alpine, Canyon, Lakeside, Desert 95, Stadium.
  Revo's PS3 disc has no stage-name speech at all.
- Events that exist in the bank but that the arcade program never names (so their clips
  are free to reuse): SP_SEGARALLYREVO (stream segarallyrevo, 1.64 s, data offset
  0xB5D5E80, 105088 bytes) and SP_SEGARALLYREVOLUTION (segarallyrevolution, 2.04 s,
  0xB5EF9C0, 130816 bytes), plus SP_WOAH, SP_WELLDONE, SP_TRYAGAIN, SP_UNLUCKY, SP_FIRST..
  SP_SIXTH, SP_GAMEOVER and others (scratch `au8.py` lists them).
- SR3 Extras: `SR3CamLab\announcer\Arctic.wav` / `Safari.wav` (the user's own recordings;
  Windows tada.wav placeholders for now) are converted with ffmpeg, brought up to a peak of
  about 28000, and written over those two clips; the switcher repoints the `push` operand to
  the spare event's name. First in-game test: not heard - the placeholder peaked at 3874 of
  32767; now normalised. NOT YET CONFIRMED.

## Ambience, music, crowd of a race

- All three names are built from the track's SOUND ID (node +0x1C, e.g. "ID_TRACK_CANYON_1"):
  - ambience: 0x644E90, `"%s%s"` (0x6D5EF0) of "SFX_AMBIENT_" + id; operand of the pattern
    push at 0x644EA5.
  - music: 0x6451B0, "MU_RACE_" + id; pattern operand at 0x6451C5 (own pattern 0x6D5E7C).
  - music events file: 0x633810, `"%s%s%s"` (0x6D5EA0) of "\Audio\" + id + "_Events.bin";
    pattern operand at 0x63382B.
  - crowd: "SFX_CROWD_LARGE_" / "SFX_CROWD_SMALL_" + id (only Tropical 1-3 exist).
- Repointing a pattern operand at a complete literal name (no % in it) makes the game use
  that name whatever the track. CONFIRMED for ambience: Safari 2 on the Alpine card plays
  SFX_AMBIENT_ID_TRACK_DESERT_2 ("zebras next to zebras"). Music/events switch the same
  way (MU_RACE_ID_TRACK_DESERT_1); not separately confirmed by ear.
- What the arcade bank has:
  - ambience events: ALPINE 1,2,3,6,7 + ALPINE; CANYON 1,2,3,7 + CANYON; DESERT 1,2,3,6 +
    DESERT; LAKESIDE 1; TROPICAL 1,2,3,7,8 + TROPICAL. "DESERT" is Revo's Safari (zebra,
    elephant sounds; streams Safari_Forest/Plain/Village).
  - music events: MU_RACE_ID_TRACK_{ALPINE,CANYON,DESERT,TROPICAL,LAKESIDE}_1, MU_MENU,
    MU_MENU_2, MU_GameOverYeah. Music streams: alpine1_1, alpine2_1, coastal1_1,
    coastal2_1, Hyper Conditioned Reflex, Menu 1, Menu 2, GameOverYeah.
  - NO Arctic ambience or music in the arcade files.
- The PS3 disc (`USRDIR\audio\englishstreamheader.stm` + data) has Arctic ambience streams
  (ArcticBathingLake, ArcticFactory_Close/_Distant, ArcticFarm, ArcticLake, ArcticPort,
  each _L/_R) and music arctic1_1, arctic2_1, safari1_1, safari2_1, canyon1_1, canyon2_1,
  lakeside1_1, tropical1_1, tropical2_1, Championship, Victory (5.1 versions).
- Arctic on the arcade (INSTALLED, not yet heard in game): arctic2 uses the unused event
  SFX_AMBIENT_ID_TRACK_TROPICAL_7; the Tropical "night" streams (slots 9 and 10, asked for by
  no installed track) are overwritten with GenericQuiet + low wind and ArcticLake + high
  wind from the PS3 disc; `Audio\ID_TRACK_TROPICAL_7_Events.bin` = the PS3 arctic_2 zones
  remapped to 8 and 9. Music stays the Canyon card's tune (no free music stream).

## The sound bank, decoded (ALL_AUDIO.sfx; PS3 .sfx = same, big-endian)

Parsed on both platforms (scripts `classic\scripts\sfx_bank.py`, `ps3_streams.py`); table of
every ambience/music event with file offsets: `classicudio_arcticrcade_event_stream_table.csv`.

- Header 0x100 bytes; at 0x100 four {offset, count} pairs. Table 0 = events, 200-byte
  records {name[192], id, offset of event data} (arcade: 1142 events, table at 0x40C).
  Tables 1-3 = bank samples.
- Event data: 452-byte header (name[192], id, 64 words; word 10 volume, word 44 entry
  count), then entries of 260 bytes: name[192] + 17 words. Word 0 = stream index (type 1),
  referenced event id (type 2) or bank sample index (type 0); word 1 = type; word 10 =
  volume; word 16 = sub-slot tag.
- Sub-slot tags index the name list at exe 0x6B1B9C: 60-69 Ambient1..10, 70-79
  Ambient_Left1..10, 80-89 Ambient_Right1..10. Each _L stream has 70+k, its _R twin 80+k.
- Every SFX_AMBIENT_ID_TRACK_<ENV>_<n> is one reference to SFX_AMBIENT_<ENV>: all routes of
  an environment share one stream set. Slots in order:
  - ALPINE: Hillside, Open, Forest, GenericQuiet, Town, Lake (Village has no tag: unused)
  - CANYON: Dam, Exposed, NonExposed, Plain, GenericQuiet, Town
  - LAKESIDE: Town, Forest, Harbour, Lake, Pub, Meadow, GenericQuiet
  - DESERT: Safari_Forest, Safari_Plain, Safari_Village, TropicalLake, GenericQuiet
  - TROPICAL: Forest, Lake, Swamp, CloseOcean, DistantOcean, Safari_Plain, Village,
    GenericQuiet, SwampNight, ForestNight
- Music events -> streams: ALPINE_1 coastal1_1, CANYON_1 alpine2_1, DESERT_1 Hyper
  Conditioned Reflex, TROPICAL_1 alpine1_1, LAKESIDE_1 coastal2_1.
- Streams no installed track asks for: TropicalSwampNight L/R (64.4 s), TropicalForestNight
  L/R (65.2 s), Canyon_Dam L/R (10.3 s), AlpineVillage L/R (22.1 s). No music stream is free.

## `<id>_Events.bin` = reverb and ambience zones along the route (not music)

- Always 9612 bytes, read whole to 0x78DAB0 (loader 0x633810, consumer 0x647930). Two
  tables of 12-byte records {route position (slice), side 0 = left / 1 = right, value}:
  at 0 the reverb zones (count, up to 500; values index the 148-byte presets of
  Reverb.bin), at 0x1774 the ambience zones (count, up to 300; values 0-9).
- Each update the game takes, per side, the latest record behind the car. Zone value v
  selects sub-slot v+1 (tags 70+v / 80+v): INFERRED from value ranges matching slot counts.
- The arcade ships only the five `_1` files. The PS3 disc has one per route; byte-swapping
  every 32-bit word gives a usable arcade file (slot order is the same). Converted copies:
  `classicudio_arctic\events_converted\` (PS3 names: SAFARI_n, ARCTIC_n). SR3 Extras
  copies the matching one into `Audio\` under the arcade id for each alternative track.
- Unknown: what the game uses when the file for an id is missing (probably stale data).

## PS3 streams

Same container, big-endian; info record format code 2 = headerless ATRAC3, 48000 Hz,
192-byte sound units per channel per 1024-sample frame; wrap in a WAV header (tag 0x270)
and ffmpeg decodes it. Music is 6 channels (order looks like L, C, R, Ls, Rs, LFE).

## Rebuilding the stream bank (tool built and verified offline; NOT yet booted)

How the game reads streams (disassembly):
- 0x568CC0 loads the whole header file once ([0x9C4EC0]); table A = base + [0x100], table B
  = base + [0x108]; the counts at 0x104/0x10C are not read there.
- 0x5686F0 opens a stream: record = table + index * 200 (records must be in index order;
  no bounds check); info = base + tableA[+0xC4]; file position = tableB[+0xC4] + 0xC0. So
  table B's absolute offsets ARE used; the game does not walk the data file.
- Header layout: at 0x100 {table A offset, count, table B offset, count}; table A =
  {path[192], index, offset of info record}; table B = {path[192], index, absolute offset
  of the stream's 192-byte path block in the data file}.
- Info record: +0xC0 channels, +0xC4 rate (0x5747F0), +0xC8 byte count, +0xCC loop start
  in bytes (0 everywhere), +0xD0 loop flag (0x5681C0), +0xD8 format (2 = compressed path,
  else PCM), +0xDC gain.
- To resize a stream: new payload, new byte count, shift table B offsets of all later
  streams. Nothing outside the two .stm files holds stream sizes or offsets.
- Limits: data file under 2 GB (SetFilePointer with a 32-bit distance at 0x581F00); 11
  simultaneous stream slots; stream index in an event entry is 24 bits.
- Sound bank: name -> id through ProjectData.sfx (0x577300), id -> event by linear search
  of the bank's event table (0x5718D0). ALL_AUDIO.sfx is loaded whole into a pre-sized pool
  and the loader fails if the file is bigger (0x57257A): do not grow that file. Events can
  be rewritten in place (same size), absorbing adjacent unused events.
- A missing `<id>_Events.bin`: the read is skipped and the buffer at 0x78DAB0 keeps the
  previous track's zones.

Tool: `classic\scriptsebuild_bank.py` (replace / add / repoint / setevent, independent
verifier, empty manifest reproduces the files byte for byte). Three prepared sets in
`F:\Jogos\_sr3_bank_sets\` (manifests in `classicank_rebuild\`), to be booted in this
order:
1. `minimal_test`: only `Checkpoint!` made 50% longer (three beeps after the word) - tests
   that resizing works at all.
2. `codriver_natural`: the 189 SEGA Rally 2 clips at natural length.
3. `arctic_full`: plus 26 new streams (all Arctic ambience, wind, three pre-mixed pairs,
   music arctic1/2 and safari1/2) and in-place event rewrites in a copy of ALL_AUDIO.sfx:
   SFX_AMBIENT_ID_TRACK_ALPINE_2 becomes the Arctic event (3 zones), TROPICAL_7 points at
   it, and the CANYON_2 / CANYON_3 / DESERT_3 / DESERT_6 ambience aliases become music
   events (arctic2_1, arctic1_1, safari1_1, safari2_1); the switcher must then play those
   names as the music. All three sets start from the ORIGINAL contents.

## Co-driver

Pace notes are SP_ events with streams under `Speech\English\` (305 speech streams).
SEGA Rally 2 voice set: see classic-sources.md. First in-game listen (2026-10-06): clips
rendered at 11025 Hz were slow, muffled and quiet -> the true rate is 22050 Hz (at that
rate 186 of 189 fit SR3's slots unchanged). Re-rendered at 22050 Hz with loudness matched
to the SR3 clip each replaces (louder half of 50 ms frames, tanh soft limit) and installed
with `codriver ON.bat` (`extras.ps1 -CoDriver on|off`; originals in
`tracks\_SR3Extras\original\codriver\`). Second listen pending.

## Pointers added later
- Which code makes the co-driver speak, and the full table from pace-note code to SP_ event: 03_master_xdata_route.md.
- The 1995 game's voice ids are sound-request numbers with sound-test names (EasyRight, KLeft, OverJump ...); 63 speech
  samples are labelled through the driver's key map: 18_src_1995_rom_data.md, section 6.
- SEGA Rally 2's pace-note records, distance calls (VO_30 .. VO_900) and praise / cheer conditions:
  19_sega_rally_2.md, section 5.
- How the switcher redirects announcer, ambience, music and events names per chosen track (the patch sites):
  21_track_install_and_switching.md, section 4.
- Announcer loudness (from `extras.ps1`): the game's own stage-name clips are pressed hard against full scale (the louder
  half of "Canyon" averages about 10000 of 32767), so a recording is brought to that level with a soft ceiling instead of
  clipping; a shorter recording is padded with silence, a longer one cut with a short fade. Without a recording, Arctic
  and Safari use the "Secret" clip (SP_Secret) as a stand-in.
- Arctic ambience zones (from `extras.ps1`): PS3 zone values 0, 4 and 5 are remapped to sub-slot 8 (quiet + low wind),
  every other zone to 9 (lake + high wind); Arctic's clips are 16-bit mono 24000 Hz; added events files are listed in
  `tracks\_SR3Extras\sounds_added.txt` and removed with the track.
- 0x9B8E1C holds a pointer to the path of the last sound played (for example
  `M:\Audio\Arcade Source\Speech\English\...wav`); it was used to find the announcer clips. The stage-name events
  SP_Tropical / SP_Alpine / SP_Canyon have ids 2274-2276 in `SFX_HashCode.h`.
- Owner's decision recorded on 2026-10-06: music of a Classic course should loop.
