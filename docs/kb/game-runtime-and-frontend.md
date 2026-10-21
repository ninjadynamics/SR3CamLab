# Rally.exe at run time, menus, card videos

Game: SEGA Rally 3 arcade, Rally.exe v3.8.4.1 (32-bit, image base 0x400000, file offset = VA - 0x400000
for the strings and code quoted here). The exe on disk is never modified (TeknoParrot checks it);
everything below is done by patching the running process (`SR3CamLab\sr3mods.ps1`).

Status tags: CONFIRMED = seen working in the game by the user; STATIC = read from disassembly,
not yet exercised; OFFLINE = only run against the emulator / fake-game tests.

## Standalone startup and video fixes (2026-10-16)

CONFIRMED: Bruno reported the combined standalone candidate fixed the long startup,
corrupted menu video, stutter and intermittent input symptoms after testing the normal
watchdog-stage launcher with watchdog enabled. Earlier isolated successes were not enough
to establish a fix; this confirmation follows the native boot-completion gate below.

- OFFLINE: early debugger attachment to the suspended child activated Windows debug heap
  flags 0x70. A hidden x86 heap probe took 6516 ms watched versus 47 ms normally.
  `standalone/watch_process.cs` supplies `_NO_DEBUG_HEAP=1` only in the child's environment,
  retaining early crash capture without changing the host environment. Ten launch checks
  cover ordinary heap flags, debugger presence at entry, Unicode, normal exit, early exception
  capture/minidump and host-environment preservation on success and failure.
- STATIC + OFFLINE: the system-data pointer at 0x9EB81C does not mean boot has finished.
  Native function 0x64D5E0 sets busy flag 0x9D6F7C at 0x64D602, calls video loading at
  0x64D618 and clears the flag at 0x64D718 after further initialization. Video handles
  are published before Pause and initial texture work. `tools/sr3mods/startup_gate.h`
  requires the busy flag clear before and after checking all 18 distinct valid video
  handles and their graph/control pointers. Failed reads or active boot delay camera
  installation (which suspends other threads); a 180-second timeout leaves the game
  unpatched. No COM calls or extra hook run on the waiting worker. Sixteen readiness
  checks include graphs available while boot remains busy and busy changing mid-scan.
- OFFLINE + CONFIRMED combined run: Hornet video loading exceeded the old three-second
  wait. A still-pending request was mistaken for permanent failure, leaving a static card.
  C and PowerShell now wait up to 30 seconds while the game is alive, then keep pending
  requests retryable. `test_delayed_card.py` delays acknowledgment five seconds in fake
  memory and requires video binding and identical C/PowerShell traces. It runs with the
  normal plugin build alongside 17 camera and 11 live parity scenarios.
- CONFIRMED in-game: the standalone runtime honors `SetCursor(NULL)` and hides the cursor
  over the active game client; deactivation restores the arrow. Explicit Alt-Tab testing
  remains outstanding.

Successful run PID24080 released the gate after 4813 ms, bound Hornet video and reached
Desert4 races with Hornet and ST205. One controller disconnect/reopen remains in that log;
do not infer that all disconnects were eliminated or their hardware cause established.
The SRC handling-profile steering issue is a separate outstanding report.

Tested plugin SHA256: `0935A6E2934138D1CD81B5CEC054C3DCDDA08971209A6188427A81FACB100A20`.
Tested runtime SHA256: `FC737EB57F33D541899A8631FF9A4E6819E29864CB118E86265D3348C30C0E23`.
Local evidence: `SR3-investigation/startup-stutter-20261016/FINDINGS.md` and
`boot-completion-user-run/` (outside the repository). Installed tested binaries stay
unchanged during source integration; these hashes describe the tested candidate.

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

- [0x9D6E3C] == 1 while the menus are up. CONFIRMED. (It is the number of menu scenes in the list at 0x9D6E38, raised
  by 0x62DD00 right after the scene is built at the start of a game; [0x9D6E50] = the scene. kb 20, section 10b.)
- [0x9C442C] = number of entries of the menu on screen: mode 3, cars 6 (10 with every car listed), transmission 2,
  stages 3. Order in the game: mode -> car -> AT/MT -> stage -> race. Each screen has a
  ~15 s timer (turned off by the launcher since 2026-10-14). Stage select = "3 entries, after having seen 6 or 2". CONFIRMED.
- [0x9DBB0C] byte != 0 while View Change is held. CONFIRMED.
- The game's logical inputs: 90 dwords at 0x9DBAD0, one per input, whatever drives it (keyboard, TeknoParrot's
  mapping, a pad, a wheel): the low 15 bits = held this frame, the previous frame's shifted up by 15, bit 30 = pressed
  this frame (held: 0x7F80FF). View Change = entry 15 (0x9DBB0C), START = entry 53 (0x9DBBA4), gas = 29, handbrake = 32,
  the same in the menus and in a race. CONFIRMED (2026-10-15, each held alone with tools\pad.py and the array sampled).
  The launcher's START screenshot and VIEW CHANGE race exit read entries 53 and 15 since then (sr3mods.ps1
  Get-GameButtons, pc_live.c); before, they read XInput pad 0 and missed every other input.
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
  "missing Canyon and Alpine cards" bug). 0x4DE430 takes the FIRST object whose +4 is 0, so
  objects 18 and 19 can be used directly (REOPEN on an empty object only opens it) without
  touching the game's own: the launcher gives an added car's card object 19 (kb 20, 10b).
  The car select looks its cards up when its pages are built (first menus, then each new
  game), not when a card is shown. CONFIRMED 2026-10-14.
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
0x2700.. (sound names). `sr3mods.ps1` function `Watch-Tracks` drives it from outside (15 ms
loop); `tools\switch_mocktest.ps1` runs that loop against a scripted fake game.

## Other handy addresses

- [0xA65794] = 1: PVS off (scene manager marks every node visible). CONFIRMED.
- 0x9B8E1C: pointer to the path of the last sound played.
- [0x7ED10C] IDirect3DDevice9*, [0x728CF4] game window (class RacingClass; set at 0x558D4B). CONFIRMED 2026-10-14
  (an older note had [0xA339A4], which holds 1 in game).
- Debug commands "ProcUpdate"/"ProcWrite" (0x597060) could regenerate the grass cache
  (not tried).

## Later additions and corrections (2026-10-06 .. 08)

- "`..._proc_cached.bin` (grass cache; missing file = no grass, no crash)" above is true of the LOADER only. In a race a
  track without its pobj files and grass cache crashes at 0x5DE16C when a wheel touches the road (02_track_files.md).
  CONFIRMED in the game.
- The Classic mode (Desert4) has no stage select; its alternative tracks are chosen with View Change on the FIRST menu
  (Championship / Quick Race / Classic). The patch block field MODESEL (0x2278) holds that menu's selector value; which
  value is Classic is learnt once and kept in `tracks\_SR3Extras\classic_mode.txt`. CONFIRMED ("label only on Classic").
- Menu timers: the "~15 s timer" of each screen is a constant in each menu's code (15 s, gearbox 10 s, name entry 30 s);
  since 2026-10-14 the launcher turns them all off and hides the countdown. Sites: 20_launcher_inmemory_patches.md,
  section 10. CONFIRMED. With every car listed (section 10b) the car select has 10 entries, not 6.
- Menu order: this file says "mode -> car -> AT/MT -> stage -> race". For Classic there is no stage screen (mode, car,
  transmission, then the race loads; `tools\autorun.py`).
- Per-track overrides written by the switcher besides the folder digit: checkpoint seconds (`arcade_times.bin`), shadow
  edge values (`shadow.txt`), PVS held off; and a screenshot on START in a race. 20_launcher_inmemory_patches.md.
- Everything about the camera system, the camera-cycle block layout and the video-memory crash that this file only
  points at is written out in 20_launcher_inmemory_patches.md; installing and switching tracks in
  21_track_install_and_switching.md.
- Boot test 2 of the menu pictures file (the smaller file with 8 names): its result is not recorded in the sources
  (UNKNOWN). The alternatives' banners and backgrounds stay off by default.

## October 15-16 standalone runtime follow-up

See [32_session_2026_10_15.md](32_session_2026_10_15.md) for the launcher/settings/controller and watchdog work,
the reproduced texture-alias shutdown crash fixed in 9aee814, source-build provenance, and the physical-controller
and full-race checks still outstanding. Importer byte comparisons do not establish gameplay stability.

## Later startup decoder crash (2026-10-16, 12:18)

OBSERVED: combined SRC/HD test crashed in `wmvdecod.dll+0x1AFA14` during state 4, with the native boot gate still busy and before the experimental handling helper installed any code. Three headless DirectShow cycles did not reproduce it. A reversible WMV2 transcode of the 18 original startup clips passed full decode checks and three Windows decoder cycles and was installed in the standalone test tree; dimensions, fps and decoded frame counts match. This is a compatibility workaround, not a verified root-cause fix. Original clips are backed up. Live retry pending. Evidence and guarded restore: `SR3-investigation/decoder-startup-20261016/FINDINGS.md` and `install-compat.ps1 -Restore`.

2026-10-16 owner confirmation: HD Hornet textures work after the 2048/mip-chain correction; latest combined run reached both races. WMV2 remains a compatibility workaround, not a proven decoder root-cause fix.


2026-10-16 owner reports watchdog ON still degrades performance and makes controls unresponsive/noisy compared with OFF. Do not consider watchdog regression resolved. Keep standalone test profile patches.watchdog: off and TEST-SRC-HD.ps1 --no-watchdog. Accepted handling remains frozen.


## Startup presentation fast path (2026-10-21)

The first version removed the blue cabinet-info screen's 120-update hold at
`0x64A3F3`; the owner confirmed that startup was faster but the blue frame still
flashed. The current version bypasses the screen's whole rendering body.

Native state 4 (`0x64D900`) calls the synchronous loader at `0x64D956` and only
returns state 9 after it completes. In state 9, the guarded first 20 bytes of
`0x649E50` remain intact, including shared update `0x646CC0`. The next 56 bytes at
`0x649E64` reset the display text count, retain lazy network getter `0x404070`, then
return the original calibration/menu choice (10 or 13). No BeginScene, blue Clear,
text draw, EndScene or Present executes. The skipped IP-info vector copies and
address objects were display temporaries; they are no longer created or freed.

The original render flags are never changed. The native initialization/loader,
18 DirectShow graphs and initial loading logo remain intact; readiness is not
faked. The optional patch runs synchronously before the DLL worker/boot loop; the
late external-attach route is unchanged. Exact original/patched bytes are checked;
foreign or partial bytes are refused. No changes to the accepted runtime, POM,
affinity, watchdog or Rally.exe on disk.

Validation: mandatory native byte-guard/idempotence/error checks plus 193 actual-x86
full-handler executions offline. Fast runs call only shared-update and network-
getter, preserve stack/registers/calibration routing, perform no blue rendering,
and never construct the skipped display temporaries. Only the approved 56-byte
span differs; initialization and retained functions are byte-identical. Windows
and graphics callees are stubbed in the emulation. No game launch or new live
visual/timing claim. Evidence: `work/research/startup-fastpath-20261021/NO-BLUE-FINDINGS.md`
and `no-blue-flow-check.json`; earlier hold-only evidence remains in FINDINGS.md.


## Second-race loader/message deadlock (2026-10-21)

The owner finished a second Mountain race in the same standalone session and
heard game-over audio, then the picture stayed white without touching controls.
Before closing frozen PID 18864, 233 thread contexts, a small minidump and native
state were captured. Main thread 28676 was waiting at `0x587802`, returning to
`0x5C6D53` (the second loader join); helper thread 30072 was inside synchronous
`SendMessageA(WM_COPYDATA)`, returning to `0x5C710C`. The loader object's done flag
was 1 and abort flag was 0. The actual resource worker had already exited.

Native `0x5C6C60` pumps window messages while work is unfinished, then blindly
joins both workers. Its progress helper `0x5C2290` can still be sending the last
cabinet message when the real worker marks done. In standalone mode, the cabinet
connection `0x5C76E0` defaults to the game's own main window. The main thread
waits for the sender; the sender waits for the main thread to receive its message.
This is distinct from the known explicit load-abort infinite sleep and does not
require pressing START during loading. It is also distinct from decoder or
many-core loading failures. Accepted SRC steering was not involved.

`source/tools/sr3mods/loader_join.h` guards the native ESI-based join ABI and
replaces only calls at `0x5C6D44/0x5C6D4E`, before the startup loop. Its wait uses
`MsgWaitForMultipleObjectsEx` with `QS_SENDMESSAGE`; `PeekMessage` services sent
messages without removing queued input. When the thread really finishes, the
unchanged native join retrieves its exit code, closes its handle and clears the
native group. No fake readiness, timeout, gameplay polling or asset skipping.
The old runtime, Rally.exe, affinity, shader and handling remain untouched.

Mandatory `test_loader_join.c` reproduces the circular wait using real Windows
threads and a hidden message-only window, then executes the real x86 thunk/native
join bytes. Repeated waits, register ABI, exit codes/handle cleanup, queued-input
preservation and byte guards pass. Full patch/live lockstep and checkpoint tests
also pass. No game was launched for validation; owner second-race confirmation is
pending. Evidence: `work/research/second-race-freeze-20261021/FINDINGS.md`,
`validation.json` and `capture/`. Standalone startup installation only; late
external attachment does not acquire this change.

## Remaining blank-blue screen and PLAY startup cost (2026-10-21)

Owner feedback after the cabinet-info body bypass: blue still appeared, now with
no text. The earlier fix was limited to state 9. Independent state-10 and state-11
calibration renderers use the same blue clear, and state 11 adds another fixed
120-update dwell after calibration has completed.

STATIC + ACTUAL-X86 OFFLINE: native state 10 at `0x64AB60` calls cabinet poll
`0x62DED0` when `[0x9EB8CC]` is set. Status 19/21 advances to 11 and writes the
original result globals `0x9C4398/0x9C439C`; pending statuses stay in 10. The entire
handler is unchanged. Its only drawing calls target `0x63EE60`; that helper's
9-byte prefix is replaced by its original display-counter increment and return.
State 11 at `0x64AB40` keeps shared update `0x646CC0`, skips the independent
`0x63ED10` blue drawing and returns 13 immediately, instead of waiting 120 updates.
Exact guards cover both spans before either write. A failed second write rolls
back the first. Pending hardware calibration still waits for the real result.

Validation now executes 385 original/patched x86 handler runs: 193 state-9 runs,
160 state-10 runs over enabled/disabled polling, completed/pending/error statuses
and frame/alignment combinations, and 32 state-11 runs. Routing, result writes,
display counter, stack/registers and shared update match; the patched paths never
call blue Clear/Present. State 4, resource loader, videos, native readiness gate,
accepted physical-core affinity, POM/YAML and second-race message-aware joins are
unchanged. Full native build and mandatory regression suites pass.

MEASURED OFFLINE: PLAY's two hidden redirected `Start-Process` helper launches
blocked about 2845 and 2810 ms merely creating the child processes. Running the
same harmless `--help` paths via direct hidden `Popen` took 2.6 and 2.8 ms; both
completed within 57 ms and exited before any process search/attachment. Existing
run logs showed the same approximately three-second spacing. New
`tools/workspace/launch_session.py` starts both helpers this way, then waits only
for `launch.exe` itself, never its Rally descendant. Argument vectors, scoped POM
environment, logs, watchdog-off flag and failure cleanup are preserved. No helper
is removed and no Python memory-attachment behavior is changed.

PLAY still fully hashes all 31 accepted files each launch. Those actual digests
are passed to the same-launch POM receipt verification, avoiding a second read of
the 105 MB track and shader library. No mtime or persistent cache is used; absent
entries still hash their contents. Warm `PLAY -Check` measured 169-190 ms versus
235-236 ms before. A cold Python invocation occasionally took about 3 seconds;
that cold/warm difference is not claimed as an optimization. Latest real native
initialization logged 2437 ms; its loader is retained, not replaced by fake-ready
flags. New `launch-timing.json` records preflight and each helper/launcher milestone
for the owner's next launch.

Ten mocked-process launch tests cover no-launch check mode, invalid relief,
settings paths, exact child arguments, hidden flags, environment preservation,
launcher-only wait, no-candidate mode and cleanup on child/launcher failures.
YAML receipt tests cover full verification and freshly measured hash reuse.
The agent did not launch Rally or install the staged DLL. Live visual and total
startup-time confirmation remain pending. Evidence:
`work/research/startup-fastpath-20261021/AGGRESSIVE-STARTUP-FINDINGS.md` and
`aggressive-build-receipt.json`.
