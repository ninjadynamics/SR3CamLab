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
A third voice, the 1995 SEGA Rally Championship's, and the selector for all three: last section of this file.

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

## SEGA Rally Championship (1995): co-driver and music (added 2026-10-13)

Tools: `scripts\rom_tools\src_audio.py` (reads `srallyc.zip` directly: `info`, `codriver`, `dump`) and
`scripts\rom_tools\src_music.py` (`plan`, `record`, `build`). Tags: VERIFIED (how) / LIKELY / NOT RUN / NOT HEARD.
Nothing below was heard in SEGA Rally 3 yet.

### The 1995 sound board, as far as it was read
Sound program `epr-17890.30` (68000, bytes swapped in pairs, mapped at 0x600000; reset SSP 0x5000, PC 0x600100); samples
`mpr-17756.31`, `mpr-17757.32`, `mpr-17886.36`, `mpr-17887.37` (bytes swapped in pairs, mapped at 0x800000). All of this
section is VERIFIED by disassembly (capstone) and by the tool parsing every table without an error, unless tagged.

| What | Where | Content |
|---|---|---|
| Sample table | 0x609C24: u16 (bytes - 1), then 306 x 20 bytes | {start, length, loop start, loop length (0 = one shot), SCSP envelope words for registers 0x08 / 0x0A}; 68000 addresses. Copied to RAM 0x5000 at boot |
| Sample format | sample ROMs | signed 8-bit mono PCM, length in samples (checked: the 8-bit reading is the smooth one, the 16-bit readings are not) |
| How a sample is played | note-on 0x6008C4, main loop 0x602A20 | the SCSP only plays from sound RAM: each of the 32 voices has a 0x2000-byte buffer (RAM 0x10000 + 0x2000 x voice), filled from ROM 0x200 bytes at a time while it plays (LIKELY: read, not traced end to end). Slot register 0 gets 0x1030: 8-bit PCM, looping buffer |
| Request groups | 0x602F8E: u16 highest group, pointers; a group = u16 (count - 1), pointers | 0x10 tunes (32 entries, 17 used), 0x20 voice (71), 0x21 effects (83); 0x70.. engine / tyre parameters handled in code (0x6022B2) |
| Message path | MIDI-in interrupt 0x600582 | bytes from the main board are assembled into 4-byte entries of a ring at RAM 0x1000 (write index word 0x2504, count byte 0x2506, read index 0x2508); 0xFF restarts the program, 0xF0..0xFE are ignored. The main loop (0x6007EC) takes them out; `AE gg nn` goes to 0x6021D0 |
| Channels | 0x606236 -> 10 records for the tunes (MIDI channels 0-8, 15); 0x6061D4: 6 fixed ones (channels 9-14) | 16 bytes {flags, MIDI channel, program, ...}; flag bit 3 = key-map channel (one sample per key, fixed pitch). Channel 10 = the voice, program 0x40 |
| Programs | 0x60882E: u16, pointers | key map of program 0x40 at 0x608FF4: u16, then 8 bytes per key {sample, pitch, pan, effect send, priority, exclusive group}; key k -> sample 137 + k |
| Pitch word | routine 0x601332, table 0x603D24 | high nibble = SCSP octave (signed), next nibble = semitone, low byte = sixteenths of a semitone. 0xF000 = octave -1, no detune = **22050 Hz**. Every voice key has 0xF000 |
| A voice request | group 0x20 track | flag byte, then MIDI bytes: `BA 7B 00` (all notes off), `9A kk vv` (note on, channel 10), `FF 2F` |
| Sequencer | timer A interrupt 0x6026F6; 0x602770 reads events | 1 music slot (RAM 0x3000) + 7 effect slots, 16 bytes each {flags (bit 7 playing), -, delay, data pointer, list pointer}. It runs every 50 samples (timer A = 0xCE): 882 ticks a second, no tempo events, so every length is exact. It puts its events into the same ring as the MIDI interrupt (0x6028FA) |
| Event format | 0x60279A | status byte with running status; 8n: 1 data byte; 9n, An, Bn, En and 0n-7n: 2; Cn, Dn: 1; F0 .. F7 and FF nn len skipped; `FF 2F` ends the run. Bit 7 of the last data byte = "the next event follows at once", otherwise a delay of 1 byte, or 2 bytes (14 bits) when bit 7 is set |
| A tune | group 0x10 entry | 4 bytes `10 10 10 10`, then pointers to runs of events ("sections", 0x610000 .. 0x62FE00); FFFFFFFF = stop, FFFFFFF1 + pointer = go on at that list entry (0x602938). While entry k plays, the slot's list pointer is list + 4 (k + 1) |

That pitch word settles two older notes: the SRC clips' rate was "assumed 22050 Hz" (it is 22050 Hz), and SEGA Rally 2's
voice table has the same 0xF000 words, which an earlier reading took for the SCSP register itself (11025 Hz, an octave low
in game). LIKELY the same rule there (same word, and 22050 Hz was right by ear); SEGA Rally 2's routine was not read.

### Tunes (lengths from the ROM: ticks x 50 / 44100)
| nn | Sound-test name | Plays | First part | Loop |
|---|---|---|---|---|
| 01 | GettingMuddy | once | 90.37 s | - |
| 02 | PowerGames | once | 55.40 s | - |
| 03 | Judgement | loops | 0.84 s | 13.03 s |
| 04 | EndRoadOfMonaco | once | 8.26 s | - |
| 05 | Ignition | loops | 13.46 s | 168.20 s |
| 06 | AroundLetter | loops | 2.36 s | 18.76 s |
| 07 | MyDearFriendLarry | once | 45.38 s | - |
| 08 | DesertLand | loops | 117.18 s (intro 3.3 s, a 43.5 s part twice, a 26.8 s bridge) | 43.52 s (that part again) |
| 09 | Fanfare | once | 7.40 s | - |
| 0A | MyDearFriendLarryF | loops | 6.74 s | 33.60 s |
| 0B | ConditionedReflex | loops | 2.12 s | 197.48 s |
| 0C | GameOver | once | 7.05 s | - |
| 0D | PutASign | once | 6.71 s | - |
| 0E | RecklessRunning | loops | 11.75 s | 134.12 s |
| 0F | CondReflexAdv | once | 55.15 s | - |
| 10 | GettingMuddyRef | loops | 11.72 s | 48.08 s |
| 11 | WaitEntry | loops | 0.41 s | 26.30 s |

Which tune a course plays (main program; VERIFIED code + table): right after request 3 ("Go"), code at prog 0x1D0D0 sends
the request at RAM 0x5BB6E0 + 4 x course id (prog 0x1C6E0), or the one at 0x5BB700 (prog 0x1C700) when the mode flag
0x202230 is not 0 and [0x20A560] <= 0. First table: Desert ConditionedReflex, Forest DesertLand, Mountain GettingMuddyRef,
Lake Side Ignition. Second table: MyDearFriendLarryF, RecklessRunning, GettingMuddyRef, Ignition. The flag is set from a
two-entry menu (prog 0x13D54): LIKELY 0 = Championship, 1 = Practice. The game's "all sound off" routine is prog 0x26150
(requests 154, 173, 181, 184, 186, 151, then 70).

### Co-driver: the 1995 calls in SEGA Rally 3's clips
`src_audio.py codriver` writes `codriver\src\<SR3 clip>.wav` (git-ignored) + `mapping.csv`: each clip is the 1995 call (or
two of them, 60 ms apart), silence trimmed, 22050 -> 32000 Hz (band-limited; checked against ideal sines and ffmpeg),
gained to the level of the SEGA Rally 3 clip it replaces (louder half of 50 ms frames, tanh ceiling, as for SEGA Rally 2).
VERIFIED offline: 151 files, all mono 32000 Hz 16-bit and no longer than their slot, levels within 2 % of the clips they
replace. NOT HEARD.

63 voice requests exist (0 .. 62). The 1995 game records every call as one phrase:

| 1995 calls (sound-test names) | SEGA Rally 3 clips | Match |
|---|---|---|
| Easy Left / Right, with Long, VeryLong, Maybe in every combination | the same 12 easy clips | exact |
| Mid Left / Right, with Long, Maybe (no VeryLong) | medium, long medium (+ maybe) | exact; "very long medium" says "long medium" |
| K Left / Right, LongK | ninety, long ninety | close: what the voice says for K is not known; K = 90 degrees is the importer's guess |
| Hairpin Left / Right | hairpin | exact; long / very long / maybe hairpins say the plain call |
| EasyLEasyR, EasyREasyL, MidRightMidLeft | the three double corners of the same words | exact, one recording |
| any other double corner (medium left + right, long ..., ... maybe) | built from two calls: first corner (with its length), second corner (with "maybe") | exact words |
| Caution, OverJump, TurnAround, Three, Two, One, Go, CheckPoint, HurryUp | caution, overjump, turnaround, Countdown_*, Checkpoint!, Hurry up! | exact |
| KeepLeft, KeepRight | stayleft, stayright | close ("keep") |
| Jump | bigjump, hugejump, long / very long jump | approximate |
| Wow1, SRC2 | woah, segarallychampionship | close (SRC0 .. SRC3 are four title calls; which is which is not known) |

- Left out of what is said (the clip plays the nearest 1995 call): "opens", "tightens", "very long" for medium and K,
  "long" for hairpin / jump / caution / stay, "maybe" where 1995 has none, and the kind of surface after "caution".
- 47 race calls keep SEGA Rally 3's voice: 46 because 1995 has nothing for them (bridge, water, road narrows, stay
  tight / wide / central / straight, water hazard, water splash, with their long / maybe forms; Lap 2 .. 4, final lap,
  time extended, time over), and "finish", whose 1995 call (1.31 s) does not fit the 0.86 s clip.
- 1995 calls not used: Finish, Oh1-3, Wow2-3, OhGod, EasyREasyLEasyR, LongLeft / LongRight, SRC0 / 1 / 3, and the
  calls with "caution" in them (CHairpin, CautionK, CLongK, CMidRightMidLeft): SEGA Rally 3 has no combined call.
- Result: 51 exact, 8 close, 92 approximate. The policy is the one of the SEGA Rally 2 set: the nearest call rather than
  a second voice, and the game's own voice only where nothing fits.

### Music: only for the 1995 courses (owner's rule, 2026-10-13)
"The SRC music should only match the imported SRC tracks": a 1995 tune is heard on an imported 1995 course and nowhere
else; SEGA Rally 3's own stages (Desert '95 included) and the menus keep their music whatever is chosen. A first version
that wrote the tunes over the Tropical / Canyon / Alpine / Lakeside streams was withdrawn for that reason.

What stands in the way, and the way round it:
- Every music stream belongs to an event that SEGA's own stages play; "Hyper Conditioned Reflex", the Classic mode's tune
  (MU_RACE_ID_TRACK_DESERT_1), is also Desert '95's. No stereo stream of minutes is unused. So nothing in the bank can be
  overwritten.
- The stream file can take more data: the game never walks it. A stream is opened by 0x5686F0 (VERIFIED by disassembly):
  it takes `[0x9C4EC4]` (table A, an absolute pointer) and `[0x9C4EC8]` (table B), reads the info offset and the data
  offset of record `index x 200 + 0xC4`, and keeps a POINTER to the info record in its stream object (+0x230) and the file
  position `offset + 0xC0` (+0x1F0). The read routine 0x5681C0 takes the byte count from that info record every time
  (+0xC8); when a read would pass the end it reads the rest and, if +0xD0 (loop) is set, moves the position to
  **+0xCC, the loop start** (position += loop start - bytes), else ends the stream. So a loop start other than 0 is honoured
  by the engine (all 387 streams have 0, which is why the earlier notes took "restarts at 0" for a limit).
- Hence: the tunes are APPENDED to `EnglishStreamData.stm` after SEGA's last stream (192-byte block + samples each, the way
  the game's own streams lie), and the launcher turns the in-memory record of stream 20 (Hyper Conditioned Reflex) to a
  tune - data offset, byte count, loop start, loop flag - only while a course that owns one is the chosen track of the
  Classic slot, and puts SEGA's values back for every other track (`patch.ps1`, `Set-CourseTune`, next to the per-track
  checkpoint times which work the same way). The event, its name and its routing stay SEGA's. On disk only the end of one
  file is added to; `Rally.exe`, the header file and the sound bank are untouched.
- NOT RUN in the game. What could still go wrong there: the game minding a longer stream file (nothing in the code read
  looks at its size), or a stream already open when the record changes (it is changed in the menus; the next race opens it).

How a tune file is made (`src_music.py`; the recording itself is the owner's step and was NOT RUN):
- MAME 0.229 (`F:\Emulators\Mame`), headless: `-video none` (VERIFIED in that exe: `win_window_info::complete_create`
  returns before `ShowWindow` when the video mode is 0, and the start-up screens routine tests for "none"), `-sound none`,
  `-wavwrite`. It also wants `epr-17891.ic12`, `epr-16726.bin` and `epr-18022.ic2` (drive board, link board, billboard),
  which the owner's set lacks: blank stand-ins in the work folder let it start. VERIFIED by one run of 45 emulated seconds
  (16.5 s, idle priority): the game boots silent for 24 s, then its attract mode makes sound.
- That MAME's Lua has no memory taps, so the script cannot filter what the main board sends. It clears the MIDI-in bit of
  the SCSP's interrupt enable register (0x10041E = 0x00C0) every frame instead (VERIFIED in the exe:
  `scsp_device::CheckPendingIRQ` raises the MIDI interrupt only when bit 3 of the enable word is set; the sound program
  writes that register once, at start-up), and queues `AE 10 nn` in the sound program's ring the way the sequencer
  does. The script itself was NOT RUN: a second emulator run was refused while ray-tracing jobs had the CPU. If the
  tunes come out silent, `record --after-boot` lets the game start the board first.
- The four course tunes (the championship table above) are recorded from their start through two passes of their loop,
  about 18 emulated minutes. `build` checks the logged list times against the lengths above, the silence between tunes,
  that the second pass sounds like the first, and one co-driver call against the ROM clip at 11025 / 22050 / 44100 Hz.
  VERIFIED on a stand-in recording (beeps at the ROM's note times): the build passes, and it flags a wrong tempo, a wrong
  clip rate and sound in the pauses.
- It writes `music\src\desert.wav`, `forest.wav`, `mountain.wav`, `lakeside.wav` (stereo 32000 Hz; git-ignored) and
  `tunes.json`: the first part of the tune, then the SECOND pass of the loop (it begins with the ring of the notes before
  it, as every later pass does), both seams blended over 20 ms into the samples that precede the second pass; loop start
  and loop length are multiples of 16 frames, like the sizes of SEGA's streams. With that loop start the game plays what
  the arcade plays: first part once, then the loop for ever. Level: the louder half of 1 s frames matched to Hyper
  Conditioned Reflex, tanh only when peaks would clip.
- SEGA Rally 3's music streams, for reference (stereo 32000 Hz): Menu 1 125.3 s, coastal1_1 243.7 s, alpine2_1 242.1 s,
  alpine1_1 248.0 s, coastal2_1 241.8 s, Menu 2 132.8 s loop (flag +0xD0 = 1); "Hyper Conditioned Reflex_FullQualityVersion"
  (stream 20, 83.2 s) and GameOverYeah 4.7 s do not. One name is used twice: "gameoveryeah" is stream 24 (the tune) and
  stream 72 (a speech clip).

### In the settings app (`extras.ps1`, Options tab) and the launcher
- "Co-driver": SEGA Rally 3 / SEGA Rally 2 (`codriver\`) / SEGA Rally Championship (`codriver\src\`). In place, one routine
  (`Set-StreamClips`): the game's own samples of every replaced clip are kept in `tracks\_SR3Extras\original\codriver\`
  (`<stream>.bin`) and put back before another voice goes in; `state.json` keeps "codriver".
- "Music": SEGA Rally 3 / SEGA Rally Championship (`music\src\`). `Set-MusicSource` appends the tune files that are there
  and writes `tracks\_SR3Extras\music.json` {source, dataLength (the file's own length), appended, stream (20), tunes
  [{course, file, offset of the 192-byte block, bytes, loopstart}]}; picking SEGA Rally 3 cuts the file back to
  dataLength (only when music.json fits the header's own end of data) and deletes music.json. `Get-AnnouncerStreams`
  accepts the stream file with exactly that tail, so the in-place parts (announcer, Arctic, co-driver) work either way.
- Which track gets a tune: `Write-SwitchFile` gives a Classic alternative a "tune" entry in `switch.json` only when it is a
  1995 course and its tune is in the file. The course is told by the importer's `texmap.json` in the track's folder
  (`...\courses\src\course1_mountain\...` in its first line; a path of another game means no tune), by the title when
  that file is missing. Everything else, and a 1995 course without a tune, plays the Classic mode's own music as before.
- Command line: `SR3Ultimate.bat -CoDriver sr3|sr2|src` (`on` = sr2, `off` = sr3), `-Music sr3|src`.
- Nothing is put in or taken out without a click: the two lists are only filled when the window opens, a pick asks before
  it acts, and the only other callers are the two command-line switches.
- VERIFIED on a copy of the game's files, never on the game (`tools\sound_copytest.ps1`, stand-ins for the tunes): every
  voice in and out with the replaced streams holding exactly their WAV; with the tunes appended, SEGA's 447,755,200 bytes
  are unchanged and the tail is exactly the tunes; the three installed Mountain builds get the mountain tune while a
  made-up course of another game called "Mountain" and a plain test track get none; the tunes taken out leave the file
  byte for byte as before; at the end the copy has the game's SHA-256 and the same kept originals. The launcher reads
  back exactly what the app wrote, and `tools\tune_mocktest.ps1` (the switcher against fake game memory) shows stream 20
  turned to the tune only while a course with a tune is the Classic choice, SEGA's values at every other moment, and no
  other record touched; `tools\switch_mocktest.ps1` gives the same output as before the change.
