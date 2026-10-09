# 21 - Installing extra tracks in SEGA Rally 3 and switching between them

How a track gets into the arcade game without replacing SEGA's files, how the running game is pointed at it, and which
side files a track folder may carry. Sources: comments of `SR3CamLab\extras.ps1` and `SR3CamLab\patch.ps1`, the owner's
persistent notes, `work/courses/src_1.json`, and the importer scripts named below. The patch sites themselves are also
listed in [game-runtime-and-frontend.md](game-runtime-and-frontend.md); the PS3 -> PC converter is in
[ps3-to-pc-conversion.md](ps3-to-pc-conversion.md).

Tags: VERIFIED (how), "in game" = seen by the owner on the cabinet, LIKELY, UNKNOWN.

## 1. The six slots
The game hard-codes six track folder names (Tropical4, Canyon4, Alpine4, Lakeside4, Desert4, Stadium4) in 15+ compare
sites; a folder with any other name shows blank cards and loads Tropical (VERIFIED in game). So every extra track is
written with a slot's file names (`<name>4_...`, `<xxx>_track_route4_...`) and stands in for that slot.
- The three stage cards are Tropical, Canyon and Alpine. Lakeside, Desert '95 (the "Classic" mode) and Stadium have no
  stage card.
- Desert4 is the track of the Classic mode. All imported 1995 courses are built for the Desert4 slot.

## 2. Two ways to install
| | Replace mode | Alternative mode |
|---|---|---|
| Where the files go | over the slot's own files in `Main_release\tracks\<slot>`; the originals are moved to `tracks\_SR3Extras\original\<slot>` first | `Main_release\track<k>\<slot>\` beside the game's own folder, k = 1..9 |
| What is replaced | the slot's track (Disable swaps it back from `...\parked\<slot>`, Remove restores for good) | nothing |
| Used for | any slot | the three stage cards, and the Classic slot (Desert4) |
| State kept in | `tracks\_SR3Extras\state.json` | `tracks\_SR3Extras\switch.json` (+ `classic.json` for Desert4) |

Both are done by the settings app (`extras.ps1`). Alternative mode is VERIFIED in game (owner: "alternative Classic folder
mechanism" is on the list of things proven in game; Arctic 2 / Safari 2 / Tropical 2 / Tropical 3 were installed as card
alternatives).

### Why at most nine alternatives per slot
The game builds its paths from patterns that contain `\main_release\tracks\%s\...`. The switcher rewrites ONE character,
the 's' of "tracks", at six places (0x6C607B, 0x6C60A3, 0x6D57C3, 0x6E034F, 0x6E03A3, 0x6E055B) to a digit '1'..'9', so
the game loads from `Main_release\track1\<slot>\` .. `track9\<slot>\`. One character means one digit: a slot can hold
nine alternatives, and `extras.ps1` refuses a tenth ("already has nine alternatives; remove one first"). VERIFIED in game
for the mechanism; the limit follows from the single character (stated in 17_mountain_build_notes.md as "Classic
alternatives must stay below 10").

## 3. `switch.json`, `classic.json`, `classic_mode.txt`
- `tracks\_SR3Extras\switch.json` lists, per slot, the tracks the switcher may choose (entry 0 = the game's own track): a
  title, the folder digit, the card video, the announcer clip name and the sound ids (ambience, music, events file).
  Written by `extras.ps1` (`Write-SwitchFile`).
- `tracks\_SR3Extras\classic.json` (`[{ title, dir }]`) lists the Classic alternatives, whose files sit in
  `Main_release\track<dir>\Desert4`; `Write-SwitchFile` adds them to `switch.json` as slot Desert4.
- `tracks\_SR3Extras\classic_mode.txt` remembers which value of the first menu's selector is "Classic". It is learnt the
  first time Classic is picked (the current track becomes Desert4 right after); until then the hint text shows on all
  three entries of that menu. The owner's notes record Classic = entry 2.
- An "art" key in `switch.json` turns on the second set of banner / background names (section 5).

## 4. How the running game is switched (`patch.ps1`, `Watch-Tracks`)
- On the stage-select screen, View Change steps the HIGHLIGHTED card through its tracks. The highlighted card is read
  from the game's own selector every frame (game-runtime-and-frontend.md) and the popup shows the track's title.
- Classic has no stage select: its alternatives are stepped through with View Change on the game's FIRST menu
  (Championship / Quick Race / Classic), and only while that menu is on Classic. VERIFIED in game ("label only on
  Classic").
- A new game puts every card back on its own track.
- While choosing, the game reads the files of the highlighted card's chosen track; after confirmation, of the current
  track.
- What is rewritten in memory for the chosen track (nothing on disk):
  | What | Where |
  |---|---|
  | track folder | the six 's' sites above |
  | stage-card video | the card's own video object is closed and reopened on the other file (the game has 20 video objects and uses 18) |
  | announcer clip | the `push <name>` operand in the routine at 0x610DC0: Tropical4 0x610E10 (own name at 0x6CF084), Alpine4 0x610E3B (0x6CF098), Canyon4 0x610E67 (0x6CF0AC) |
  | race sounds | the pointers to the name patterns: ambience 0x644EA5 (own pattern 0x6D5EF0), music 0x6451C5 (0x6D5E7C), events file 0x63382B (0x6D5EA0), turned to whole names kept in the patch block (audio.md) |
  | scenery visibility | [0xA65794] held at 1 while an added track is raced |
  | checkpoint times | `arcade_times.bin` of the track folder (20, section 6) |
  | shadow edge | `shadow.txt` of the track folder (20, section 7) |
  | menu art (only when "art" is on) | the 'D' of `BKGD_NAME_%s` at 0x6BCF0F and the last 'R' of `MENU_BANNER_%s` at 0x6BD79E, 0x6D96E6, 0x6E2AB2, 0x6E336E, 0x6E5A36, rewritten to the digit |

## 5. Stage cards, banners, backgrounds
- A card alternative gets a stage-card video `frontend\PC\Videos\LANG_<language>_<TR|CA|AL><k>.wmv`: 6 seconds that loop
  (a slow zoom, a cross-fade into a slow pan, a cross-fade back), made with ffmpeg from the card picture the game itself
  still carries for Revo's environments (TRACKSLIDE_<TRACK>). The picture is enlarged first so the movement is smooth.
  Without ffmpeg the slot keeps its own card. Videos made with `-c:v wmv2` play in game (VERIFIED in game).
- Banners and backgrounds per alternative (`BKG<k>_NAME_<slot>`, `MENU_BANNE<k>_<slot>` added to
  `frontend\arcade permanent resources_data.sbf`) are OFF by default (`SR3Ultimate.bat -AltArt on / off`): the first boot
  test with 12 new full-size pictures crashed at start-up (game-runtime-and-frontend.md). The background is a blur, so it
  is stored at a quarter of the size; "the game does not start with this file much bigger than it was" (comment in
  `extras.ps1`; LIKELY cause, not proven).
- The name shown on a card is the environment without the route number ("arctic2" -> "Arctic"); the switcher's popup
  shows "Arctic 2".

## 6. What a track folder must contain
- All seven files (02_track_files.md). Static analysis had found the pobj files and the grass cache optional; IN GAME they
  are not: without `pobj_master`, `pobj_plac` and `proc_cached.bin` the grass set-up 0x506FD0 never runs, the arrays at
  [0xA95D24 / 28 / 2C] are never created, and the game dies at 0x5DE16C (function 0x5DE0C0) about 2 s into the race, when
  a wheel touches the road. VERIFIED in game (runs of 2026-10-07; course setting note `props_note`). So the importer's
  `props: minimal` (3-file track) is not usable; the course settings use `slot` (keep the slot's props) or `noobjects`.
  Empty-but-valid pobj / grass files were not authored (open).
- A converted Revo track is first written to a folder of its own and then passed through the Revo fix
  (`revofix.cs`, 13_revo_vs_arcade.md section 5) before it is installed.

Optional side files, read by the launcher or the tools, never by the game itself:
| File | Written by | Read by | Purpose |
|---|---|---|---|
| `arcade_times.bin` | `arcade_times.py classic` (copied into the step folder by hand; the importer does not write it) | `patch.ps1 Set-ArcadeTimes` | checkpoint seconds for this track |
| `shadow.txt` | by hand | `patch.ps1 Set-ShadowParams` | shadow edge values, optional "noblur" |
| `texmap.json` | every importer build | `texfast.py` (`UPDATE_TEXTURES.bat`) | which texture chunk shows which 1995 tile, and the recipe of composed tiles |

## 7. Updating textures of an installed track without a rebuild
`UPDATE_TEXTURES.bat` runs `work/scripts/texfast.py`, which opens every installed Classic alternative that has a
`texmap.json` and rewrites only the textures whose PNG in the course's `textures_hd` folder changed (the old texture is
the template: its header, wrap modes included, is kept; only size and pixels change). `watch` keeps it running. The game
must be closed, because it holds the files open. Details and limits: 23_texture_pipeline.md.

## 8. Other content the settings app installs (pointers)
- Announcer stage names for Arctic and Safari, co-driver voice, race sounds of alternative tracks: audio.md.
- The app was first called "SR3 Extras", then "SR3Ultimate" (`SR3Ultimate.bat`, `extras.ps1`); the planned name of the
  whole suite is SR3Lab (`SR3CamLab\docs\SR3Lab-plan.md`, plan only). The game-side state folder keeps the name
  `tracks\_SR3Extras`.
- Requested but not built: an on / off switch per added track in the app (today a track can only be installed or
  removed), and a full "restore everything and compare against a clean install" check.

## 9. Test ladder helper
The built test tracks live in `work\out\<step>\<Slot>\`. `F:\Jogos\SEGA Rally 3\track ladder.ps1 -Step <folder>` /
`-Step off` swapped a step into the slot during the first test rounds (work/out/README.txt). The ladder steps 0..24
were deleted on 2026-10-07 after they had passed or been superseded; the scripts rebuild them.
