# Open questions - every UNKNOWN and every unconfirmed LIKELY, by game

Collected from all files of this knowledge base on 2026-10-08. Each line: the question, the file that discusses it, and
the test or work that would settle it. A test marked **[S]** is named by a source (a file of this knowledge base, a script
comment or a plan). A test without the mark is only the plain next step that the wording of the item implies ("not yet
driven" -> drive it); it is the curator's reading, not a finding. "-" means nothing is proposed.
Items marked CONFLICT are places where two sources disagree and neither withdraws the other.
Things that were open in older sections but have since been answered are NOT listed here; the files mark them as
corrected.

## A. SEGA Rally 3 (arcade) - file formats

| # | Question | File | Test that would settle it |
|---|---|---|---|
| A1 | Texture header words: which numeric address mode is wrap and which clamp; exact pairing of the observed (a, b, c) with the sampler fields | 01 | read 0x58DF40 once more against two textures of known behaviour |
| A2 | Is the 4096-byte alignment of SEGA's texture pixels needed? (converted tracks without it load: LIKELY not) | 01 | - |
| A3 | Class hash in the 4th header word of kind 12 chunks: where it comes from (not found as a constant in the exe) | 01 | - |
| A4 | Files `tropical4_master_data.sbf`, `*_procobj_*`, `Alpine4.rar` (85 MB, encrypted headers): content and purpose. 02 says `*_procobj_*` is not loaded; crowd.py says the game "needs" the procobj file | 02, ps3-to-pc-conversion | - |
| A5 | game_objects file: is it really required (LIKELY, result passed on unchecked at 0x5C5E0D) | 02 | - |
| A6 | master_xdata root fields +1C, +20, +24, +80 / +84, +88 / +8C, +90 (a distance: 180 .. 800), +94; Stadium4's animation chunk at +28 | 03 | - |
| A7 | Trackside camera records (about 0x228 bytes each); where the game's default cameras stand; who calls the second camera loader 0x5FB4B0 | 03 | - |
| A8 | Spline marker types (0,4) (10 per track, no property) and (0,2) Grip / Length / Modifier | 03 | - |
| A9 | AI map: what selects one of the three lane-mask sets per car (the field at [car + 0x300] + 0x28); why Tropical4 and Lakeside4 have differing sets; where the AI takes its target speed from | 03 | - |
| A10 | How well the AI drives on an authored 8-lane map, and on lanes laid along the 1995 AI line | 03 | in game: watch the AI race |
| A11 | ArcadeDatabase time record: that the three sub-blocks are difficulty (LIKELY); what modes 1 and 2 are | 03 | - |
| A12 | TrackDeform: header +10 (= 2); slice +7C (LIKELY water level), +80 / +84; vertex +10, +14, +16; the exact slice -> batch record mapping (about 16 % of weights index past the list in four tracks); batch type 1 / 2 and flags | 04 | - |
| A13 | Overlay page texA: layout of the sun / shadow map beyond "green = sunlit, red = shadow"; what texB is | 04, 16 | - |
| A14 | Height blob: meaning of values below 0xBF (LIKELY pre-baked ruts) | 04 | - |
| A15 | Is a track closed-circuit only? Point-to-point (Revo stages) was not examined | 09, 11 | - |
| A16 | Scenery tree: the instance lists (0x24-byte entries for library objects); the light-map structure at +0x0C; what the load-time pass over material type 6 meshes is for (water?) | 05 | - |
| A17 | Why the race intro and attract cameras do not show PVS popping | 20 | - |
| A18 | Boundary BSP: leaf type semantics (3 solid, 4 empty, 5 with planes: LIKELY); which engine paths use type 4; SEGA's splitting heuristic | 06 | - |
| A19 | What happens at the road edge on a track without the boundary chunk | 06 | in game (it loaded; behaviour was not written down) |
| A20 | Wall surface ids: the group -> name pairing (Armco, Brick, Tyres ...) | 10 | - |
| A21 | master_gfx root +14 (horizon card: LIKELY; kind of the referenced chunk stated two ways), +1C, +20, +24 (LIKELY sky dome height), +28, +2C / +30 (two small textures, purpose unknown) | 07 | - |
| A22 | Mesh: model record and tail (copied verbatim, LIKELY); the vertex formats other than 0x20C7 / 0x2041 / 0x20C3, in particular those that carry a COLOUR (SEGA's main way of baking light); the handedness the engine gives the bitangent | 07, 16 | **[S]** decode format 0x20D7 (52 bytes), one in-game test (TexLab plan, spike list) |
| A23 | Uber material: are the switch names assigned correctly (LIKELY, by order + statistics; byte patches "behave as named"); can a switch combination SEGA never compiled be used (LIKELY not) | 07, 16, 23 | - |
| A24 | Which material field drives the polygon-offset render state (globals 0x8123C8 / 0x8123CC) | 20 | trace 0x590404..0x590486 back to the material |
| A25 | Surface per terrain entry: the audio / particle class of each (terrain property chunks, root +0x1C..+0x24, +0x44 of surfacepairdata); the heading classes in 10 are inferred from names | 10 | decode those chunks |
| A26 | The alpha channel of road layer textures (LIKELY a blend height) | 23 | - |
| A27 | Object record +8 (u16 = 1); whether animators are drawn or must be near the camera; how a look is chosen per spectator; that dumb spectators copy the animators' pose (LIKELY) | 15 | - |
| A28 | Why some spectators turn their backs to the road (game code; the "three looks" theory was disproved in game) | 15, 17 | trace the code that sets a spectator's orientation |
| A29 | `classic/revofix/exe_types.txt`: is it the exe's type table (LIKELY)? | 15, 13_revo | check how the file was produced |
| A30 | What else reads the game_objects file by id (particle / effect definitions) | 07 | - |
| A31 | Can empty-but-valid pobj_master / pobj_plac / grass cache files be authored, so the slot's grass and procedural objects do not appear on an imported course | 21, 09 | author them; one in-game run. **[S]** the debug commands "ProcUpdate" / "ProcWrite" (0x597060) might regenerate the grass cache (not tried) |

## B. SEGA Rally 3 - lighting, shadows, rendering

| # | Question | File | Test |
|---|---|---|---|
| B1 | Lighting sets: the 34 floats outside the seven known ranges; exact form of the shading (ambient + sun x max(N.L, 0): LIKELY) | 16 | - |
| B2 | CONFLICT: Mountain's light direction - settings file [-4, -6, 4] (47 degrees up, "where the 1995 game has it") against (0, -0.94, 0.34) (70 degrees, the ROM vector) and the 16:30 variant (0, -0.737, 0.676); which the owner kept | 16 | ask the owner; read the `--set` of the installed build |
| B3 | The 1995 light vector is INFERRED to be the direction the light travels (no code trace) | 16 | trace its use in the 1995 program |
| B4 | CONFLICT: `gfShadowParamsPs` x and w - 07 says w = -1/512 and x is recomputed at 0x59B537; 16 says both are not identified. Is the technique variance shadow maps (07 VERIFIED, 16 LIKELY) | 07, 16 | - |
| B5 | Is the 5 x 5 blur at 0x50D960 the shadow-map blur (LIKELY)? Why do spectators lose their shadows with floor 0.0002, power 30 and the blur off? Does `shadow.txt` change anything visible ("the two numbers alone changed nothing visible") | 16, 20 | in game with "noblur", one change at a time |
| B6 | Light map: exact response curve of a value (LIKELY linear); is a partial mip chain accepted | 16 | a grey-ramp page in game |
| B7 | Relief: the second method (rule normal + turned tangent) "not yet judged in game" | 16 | in game |
| B8 | CONFLICT: is `Rally.exe` on disk packed? 08 says not packed; 16 says packed (3.3 MB file) | 08, 16, 20 | compare section raw sizes with the file |
| B9 | Trees read about twice as bright as in the Model 2 control | 17 | - |
| B10 | Frame rate of heavy builds: no figure recorded; the vertex ceiling lies between 1.82 and 5.18 million | 17 | load builds in between; measure |
| B11 | `GraphicsDebug.fx`: what a material with a missing shader draws | 13_revo | in game on an unfixed Revo track |

## C. SEGA Rally 3 - run time, menus, launcher

| # | Question | File | Test |
|---|---|---|---|
| C1 | Menu pictures file: why 12 added pictures crash at boot (LIKELY a fixed pool by size); result of boot test 2 | game-runtime-and-frontend, 21 | **[S]** boot test 2; if it still crashes, reuse existing names instead of adding any |
| C2 | A flag that tells a race from the attract loop; any input address inside Rally.exe | 20 | - |
| C3 | Where the car's origin is (ground, axle, centre of mass); what `mgr+0x1BC` / car rotate `cam+0x34` control; the classes of cameras `mgr+0x1FDC` and `mgr+0x2F24`; the debug settings block in a running game | 20 | - |
| C4 | Whether the race starts on the operator setting `VIEW=` | 20 | - |
| C5 | Crash at 0x447A20 on an early flat loop: cause | 09 | - |
| C6 | The finer road ladder (5a-5f), the rebuilt step5 and the flat loop were not tested after the page fix | 04, 09 | in game |
| C7 | Lap-driven gate: in-game result of the rewritten Start_Finish_Line mesh | 15 | in game: start, lap 1, final lap |
| C8 | Rounding: the APRON rule "not yet confirmed in game" | 17 | in game on R4 |
| C9 | Suspected bugs not fixed: road pieces cut twice (1.0000000000000002); second seal pass finds 1,086 open samples and carries down 0 walls; `round(x, 2)` differs between Python and numpy floats; `Near` beyond 512 m | 17 | count in a build |
| C10 | Composed pictures from the fast lane differ by about 1 % of bytes from the build's | 17, 23 | - |
| C11 | Is the full track build deterministic (only the terrain generator was checked) | 17 | build twice, compare hashes |

## D. SEGA Rally 3 - audio

| # | Question | File | Test |
|---|---|---|---|
| D1 | `ProjectData.sfx` (not fully decoded), `Reverb.bin`, `RowData.bin` (not analysed) | audio | - |
| D2 | Zone value v selects sub-slot v + 1 (INFERRED from value ranges) | audio | - |
| D3 | Not yet heard in game: the announcer recordings after normalising; Arctic ambience on the arcade; music / events switching by ear; the SR2 co-driver at 22050 Hz (second listen pending) | audio | **[S]** listen in game |
| D4 | The rebuilt stream bank was never booted (three prepared sets: minimal_test, codriver_natural, arctic_full; two music sets) | audio, classic-sources | **[S]** boot them in the order given in audio.md |

## E. SEGA Rally Revo in the arcade engine

| # | Question | File | Test |
|---|---|---|---|
| E1 | In-game look of the materials rebuilt by the Revo fix | 13_revo | **[S]** in game on tropical2: the 14 m panel and the small bushes (13_revo section 4, question 2) |
| E2 | Birds (Thrush): do they fly on the arcade's own Tropical; mechanism of the frozen birds (default 10.0 at [0x6BED54] or the path lookup) | 13_revo | **[S]** section 4 questions 3 and 4; patch [0x6BED54] to 500.0 in memory |
| E3 | Particle emitters: meaning of the float at +0x10C (2000.0 / 500.0 in arcade objects, 0 in Revo's) | 13_revo | **[S]** write 2000.0 (the fix pass has this step, off by default) and look for smoke / spray (section 4, question 7) |
| E4 | Missing `g_alpha` parameter on terrain and water materials: any visible effect | 13_revo | **[S]** compare water / terrain with an arcade track (section 4, question 8) |
| E5 | Vertex format 0x20C1 (one mesh in three tropical tracks): effect | 13_revo | - |
| E6 | Gameplay root type 6e9ca290 vs ecdb142b: effect of the differing floats and the extra texture reference | 13_revo | - |
| E7 | Far clip plane and fog distance of the arcade track setup (not excluded as a cause of distant cut-off) | 13_revo | **[S]** section 4 question 1 |
| E8 | arctic1 / arctic6 / tropical1 with the v2 converter files: in-game check | 13_revo | **[S]** section 4 questions 5 and 6 |
| E9 | AI stopping at the first checkpoint of arctic2: fix confirmed? (LIKELY; two statements of the same day differ) | ps3-to-pc-conversion | race arctic2 |
| E10 | The largest structure difference between converted and demo tropical2 (game objects root 7c1638ed, 1,974 words) was not checked word by word | 13_revo | - |

## F. SEGA Rally Championship (1995)

| # | Question | File | Test |
|---|---|---|---|
| F1 | Trackside table: kinds 6 and 20; the code that maps a record's model number to an object (spectator model -> sprite pair; gate model -> banner / post); the flag (GUESS: animation phase); the angle | 18, 15 | disassemble the code that reads the tables |
| F2 | Crowd tables of Desert, Lake Side and Forest are matched by distance only (LIKELY) | 15 | same check as Mountain |
| F3 | The player's grid slot among the four start positions | 18 | - |
| F4 | Time: units (frames, LIKELY); the values at prog 0xF460 and the float in the 0x3DE70 table | 18 | - |
| F5 | AI line: that the flag's high nibble is a speed zone for computer cars (GUESS); the low bits (Lake Side 1 everywhere, Mountain sections 110-118) | 18 | - |
| F6 | The event sections at prog 0x46010 (GUESS: rival / overtaking events) | 18 | - |
| F7 | Pace-note icons 7, 4, 26 (GUESS: crest / caution); "K" (GUESS: 90 degrees); "D" in D_TIGHTEN | 18, classic-sources | listen to the labelled samples |
| F8 | Surface physics: grip / drag numbers, sounds per type, which CPU evaluates them | 18 | - |
| F9 | Per-polygon sort priority (layer order is a guess) and per-polygon brightness (taken as full); the renderer's gamma | 18, 12 | **[S]** MAME dump of the three RAM tables for an exact gamma (12); nothing proposed for the sort priority |
| F10 | Why the decoded tiles are brighter in the mid tones than the emulator picture (a gamma of 1.7 matches by eye) | 12, 23 | - |
| F11 | Object table: 1,508 rows against 1507 objects | classic-sources | - |
| F12 | Other tiles of courses 2 and 4 that decode to black | 14 | - |
| F13 | Music is sequenced: nothing extracted; speech sample rate assumed 22050 Hz | classic-sources | **[S]** record from an emulator |
| F14 | Desert, Lake Side, Forest in SR3: rebuilt but never installed or driven; Desert reaches outside the +-750 m scenery square | 09, 14 | install and drive |
| F15 | Gap-fill rule that skips rock-top anchors (250 skipped lap-wide) was checked in one place only | 22 | look round the lap |
| F16 | Which pace-note scheme the current Mountain build writes (full code table or the earlier three grades) | 14 | read the built spline with pacenotes.py |

## G. SEGA Rally 2

| # | Question | File | Test |
|---|---|---|---|
| G1 | Is FOREST an unused leftover (LIKELY) | 19 | - |
| G2 | That the polygon's low 4 bits index the ROAD STATUS array (LIKELY; the indexing instruction was not located); the grip / decay numbers | 19 | find the instruction; export car spec +316 |
| G3 | Which difficulty index is the factory default; the meaning of game types 1 and 3 | 19 | - |
| G4 | Rival behaviour: speed profile, the two floats per car; that the line is a recorded drive (LIKELY); cars per round at round record +112 (LIKELY) | 19 | - |
| G5 | Does the sky dome follow the camera (LIKELY); is stage +16 the goal banner (LIKELY) | 19 | - |
| G6 | Roadside object placement tables (record format known, tables not located) | 19 | - |
| G7 | Block record value after each LOD address (LIKELY a culling / LOD distance); the car reflection zone table (LIKELY) | 19 | - |
| G8 | Voice clips: the octave rule in the request data; abbreviations K and D; which of the 12 music tracks is which (classic-sources says unknown; the tune table names 14 tunes) | classic-sources | - |
| G9 | The SR2 -> SR3 builds were never run and predate every in-game fix; a batch record with 5 or 7 layers and a damp-mud top over a dry-mud base are untested | 19 | rebuild with the current importer; in game |
| G10 | Pace-note icon graphics (numbers only) | 19 | - |

## H. Tools and plans (not about a game)
| # | Question | File |
|---|---|---|
| H1 | SR3Lab restructuring, TexLab, the per-track on / off switch, "restore everything and compare against a clean install": all plans, nothing built | 21, 23 |
| H2 | Whether the generated terrain file holds only own geometry and 1995 texture NAMES (to be verified before any release) | SR3CamLab\docs\SR3Lab-plan.md |
| H3 | The owner's formal sign-off of Mountain (it gates the restructuring) | 09 |
