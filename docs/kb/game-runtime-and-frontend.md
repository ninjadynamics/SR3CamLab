# Rally.exe at run time, menus, card videos

Game: SEGA Rally 3 arcade, Rally.exe v3.8.4.1 (32-bit, image base 0x400000, file offset = VA - 0x400000
for the strings and code quoted here). The exe on disk is never modified (TeknoParrot checks it);
everything below is done by patching the running process (`SR3CamLab\patch.ps1`).

Status tags: CONFIRMED = seen working in the game by the user; STATIC = read from disassembly,
not yet exercised; OFFLINE = only run against the emulator / fake-game tests.

## Tracks: how the game names and finds them

- Six track folder names are hard-coded in the exe (15+ compare sites): Tropical4, Canyon4,
  Alpine4, Lakeside4, Desert4, Stadium4. A folder with any other name shows blank cards and
  loads Tropical. CONFIRMED (tried Arctic2/Safari2 through the database, reverted).
- Track list: `ArcadeDatabase\arcadedatabase_xdata.sbf`, chunk type 0x1BFF7E65, linked records
  (index, flags, LANG name, folder, ID_TRACK sound id).
- In memory: [0xB2A850] -> object; [[0xB2A850]+8]+8 = first node of a linked list of tracks.
  Node: +0 next, +4 track id, +0x14 debug name, +0x18 -> folder name ("Canyon4"),
  +0x1C -> sound id ("ID_TRACK_CANYON_1"). STATIC + CONFIRMED (the switcher walks it).
- Current track ("the last one confirmed", NOT the highlighted card): struct at 0x9DBDA0,
  [0x9DBDB0] = its node. CONFIRMED the hard way: it does not follow the cursor.
- Files loaded per track (7): `<name>_master_gfx_xdata.sbf`, `<name>_master_xdata.sbf`,
  `<xxx>_track_route<N>_game_objects_gfx_data.sbf`, `..._gameobj_gfx_dis_data.sbf`,
  `..._pobj_master_gfx_xdata.sbf`, `..._pobj_plac_gfx_xdata.sbf`, `..._proc_cached.bin`
  (grass cache; missing file = no grass, no crash).
- Path patterns contain `\main_release\tracks\%s\...`. The 's' of "tracks" sits at
  0x6C607B, 0x6C60A3, 0x6D57C3, 0x6E034F, 0x6E03A3, 0x6E055B. Writing '1'..'9' there makes
  the game load from `Main_release\track1\<slot>\` etc. CONFIRMED (this is how alternative
  tracks are loaded without replacing anything).
- Other per-track-name lookups: `\frontend\loading\loading_%s_data`,
  `\cameras\%s_camera_{intro,postrace,trackside}_data`.

## Menus

- [0x9D6E3C] == 1 while the menus are up. CONFIRMED.
- [0x9C442C] = number of entries of the menu on screen: mode 3, cars 6, transmission 2,
  stages 3. Order in the game: mode -> car -> AT/MT -> stage -> race. Each screen has a
  ~15 s timer. Stage select = "3 entries, after having seen 6 or 2". CONFIRMED.
- [0x9DBB0C] byte != 0 while View Change is held. CONFIRMED.
- Highlighted stage card: the game itself asks the selector widget only when a stage is
  confirmed (0x6669C0): `hash = 0x5470D0(ecx = "ID_SELECTOR_TRACKSELECT" @0x6E53FC, push 23)`
  (Jenkins-style string hash, cdecl), then `0x606490` with edi = hash returns the selected
  track id (-1 when there is no such selector), guarded by [0x9C0F48] != 0; then
  `0x5AF700(this = id, push 0x9DBDA0)` finds the node. The patch calls the first two every
  frame from its draw hook and leaves the id at block+0x226C. CONFIRMED (labels follow the
  cursor, per-card switching works).
- 0x6669C0 also plays SFX_Select1 (0x610020) and the stage announcer (0x610DC0), so the
  announcer speaks when a stage is CONFIRMED, not when it is highlighted.

## Stage cards are videos

- `frontend\PC\Videos\LANG_<LANGUAGE>_<TRO|CAN|ALP>.wmv`, 640x360, WMV3, 30 fps, 6 s.
  Files made with ffmpeg `-c:v wmv2 -b:v 9M` play fine. CONFIRMED.
- Menu video table at 0x728630: 18 x {name ptr, file ptr, per-language flag, handle}
  (TROPICAL 0x728710, ALPINE 0x728720, CANYON 0x728730). 0x621600 loads every entry whose
  handle is -1 (except LOADING_TEXTURE, loaded by 0x6214A0); 0x61C2C0 looks one up by name.
- Video objects: 20 x 0x16C bytes at 0xAD2F90. +0 playing flag, +4/+8 in use, +0xC path
  (0x100 bytes), +0x11C IGraphBuilder, +0x120 IMediaControl, +0x124 IMediaEvent (later
  IMediaSeeking), +0x128 IBasicAudio, +0x12C IFileSourceFilter, +0x130 the game's renderer
  filter, +0x134/+0x138 events, +0x140 texture descriptor (+0x144 IDirect3DTexture9).
  0x4DE430 = allocate a free object and open (returns -1 when all 20 are used);
  0x4DDC80 = open (ecx = path, edi = object); 0x4DE370(handle, play, x) = start/stop and
  return &object+0x140. The game NEVER frees a video.
- The game uses 18 of the 20 objects. Loading extra videos fails after two, and if they are
  loaded before the game's own, the game's last cards come up blank. CONFIRMED (that was the
  "missing Canyon and Alpine cards" bug).
- Working way to change a card live: on the game's own thread, IMediaControl::Stop, Release
  +0x12C..+0x11C and the texture, zero +0, +4, +8, +0x130, call 0x4DDC80 with the new path
  on the SAME object, then Run and 0x4DE370(handle, 0, 1) as the loader does. Widgets hold
  &object+0x140, so they pick the new texture up by themselves. CONFIRMED ("cards change
  live"). Request fields in the patch block: REOPEN 0x2270 (handle + 1), REOPENPATH 0x2274.
  Two event handles leak per reopen (not closed).
- Video memory: see the "Out of memory for VB / white screen" note in the project memory
  (cached WMV graphs x decoder threads; PLAY.bat pins the game to 4 cores).

## Menu pictures (banner, background)

- `frontend\arcade permanent resources_data.sbf`. A named texture = kind 5 record
  {2, 0, texture id, 0x10 -> name} (fix [12], ref [8]) + the kind 4 texture.
- The LAST chunk is an index {1, -> list A, -> list B}; each list = record ids, 0-terminated.
  Adding named records without adding their ids to list A crashes the game at boot. CONFIRMED.
- Names the game asks for: `BKGD_NAME_%s` (1280x720 DXT5; the 'D' at 0x6BCF0F) and
  `MENU_BANNER_%s` (1024x128 DXT5; last 'R' at 0x6BD79E, 0x6D96E6, 0x6E2AB2, 0x6E336E,
  0x6E5A36), %s = folder name. SR3 Extras adds `BKG<k>_NAME_<slot>` / `MENU_BANNE<k>_<slot>`
  and the switcher rewrites those letters to <k>.
- Boot test 1 (2026-10-06): CRASH at start-up with the index correctly extended and 12 new
  names, each with a full-size texture (file 10.5 -> 16.7 MB uncompressed). The same file
  merely read and re-written by our writer boots. Ids are not name hashes (checked against
  the Jenkins hash at 0x5470D0); list A holds the 37 picture records, list B the 2 font
  records; textures and the two big font structures are not listed. Working theory, NOT
  proven: the file's size is the problem (fixed pool for permanent menu resources). Second
  attempt adds only the 8 names in use, backgrounds at 320x180 (they are blurs): 11.2 MB.
  Awaiting boot test 2. If it still crashes, the next suspects are the new records
  themselves (e.g. the file must keep its original chunk count) - then reuse existing
  names instead of adding any.
- Art already in the arcade data for Revo's environments: TRACKSLIDE_<TRACK> 512x512
  (`frontend\track cards_data`), SR_LOGO_<TRACK>_L, ENVSLIDE_ID_ENV_<ENV>.

## The patch block (SR3CamLab)

One 0x3000-byte block allocated in the game (code at +0x1000, built by
`tools\build_cycle.py`, tested by `tools\cycle_emu.py`). Its draw hook runs on the game's
render thread every frame, which is what makes game-thread-only work possible (video
loading and reopening, selector query, text drawing). Track-switcher fields: LOADVIDEOS
0x2264, PHINT 0x2268 (second popup line), HILITE 0x226C, REOPEN 0x2270, REOPENPATH 0x2274;
scratch strings at 0x2400 (popup text), 0x2500 (video path), 0x2600.. (announcer names),
0x2700.. (sound names). `patch.ps1` function `Watch-Tracks` drives it from outside (15 ms
loop); `tools\switch_mocktest.ps1` runs that loop against a scripted fake game.

## Other handy addresses

- [0xA65794] = 1: PVS off (scene manager marks every node visible). CONFIRMED.
- 0x9B8E1C: pointer to the path of the last sound played.
- [0x7ED10C] IDirect3DDevice9*, [0xA339A4] game window.
- Debug commands "ProcUpdate"/"ProcWrite" (0x597060) could regenerate the grass cache
  (not tried).

## Later additions and corrections (2026-10-06 .. 08)

- "`..._proc_cached.bin` (grass cache; missing file = no grass, no crash)" above is true of the LOADER only. In a race a
  track without its pobj files and grass cache crashes at 0x5DE16C when a wheel touches the road (02_track_files.md).
  CONFIRMED in the game.
- The Classic mode (Desert4) has no stage select; its alternative tracks are chosen with View Change on the FIRST menu
  (Championship / Quick Race / Classic). The patch block field MODESEL (0x2278) holds that menu's selector value; which
  value is Classic is learnt once and kept in `tracks\_SR3Extras\classic_mode.txt`. CONFIRMED ("label only on Classic").
- Menu timers: the "~15 s timer" of each screen is a 15000 ms constant in each menu's code, at 18 sites; the launcher
  sets them all (120 s). Sites: 20_launcher_inmemory_patches.md, section 10. CONFIRMED.
- Menu order: this file says "mode -> car -> AT/MT -> stage -> race". For Classic there is no stage screen (mode, car,
  transmission, then the race loads; `tools\autorun.py`).
- Per-track overrides written by the switcher besides the folder digit: checkpoint seconds (`arcade_times.bin`), shadow
  edge values (`shadow.txt`), PVS held off; and a screenshot on START in a race. 20_launcher_inmemory_patches.md.
- Everything about the camera system, the camera-cycle block layout and the video-memory crash that this file only
  points at is written out in 20_launcher_inmemory_patches.md; installing and switching tracks in
  21_track_install_and_switching.md.
- Boot test 2 of the menu pictures file (the smaller file with 8 names): its result is not recorded in the sources
  (UNKNOWN). The alternatives' banners and backgrounds stay off by default.
