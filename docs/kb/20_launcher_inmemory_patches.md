# 20 - The launcher's in-memory patches of Rally.exe: addresses, what each does, why

SEGA Rally 3 arcade, `Rally.exe` 3.8.4.1 (32-bit, image base 0x400000). The launcher is `SR3CamLab\PLAY.bat`, which runs
`SR3CamLab\patch.ps1`. Sources for this file: the comments of `patch.ps1`, `SR3CamLab\FINDINGS.md`, and the owner's
persistent notes. Menus, the track list in memory and the stage-card videos are in
[game-runtime-and-frontend.md](game-runtime-and-frontend.md); how tracks are installed and chosen is in
[21_track_install_and_switching.md](21_track_install_and_switching.md).

Tags: VERIFIED (live) = read from the running game and confirmed on screen or in memory; VERIFIED (code) = read from the
disassembly; "in game" = the owner saw it on the cabinet; LIKELY; UNKNOWN.

## 1. Why everything is patched in memory
- TeknoParrot's `TeknoParrot.dll` checks the executable from inside the running process and refuses a modified file
  ("Unsupported CRC"), including a file whose whole-file CRC32 was patched back to the original. So `Rally.exe` on disk is
  never changed; every modification is written to the process after it has started. VERIFIED (live).
- Executable facts: MD5 `d7c0b475fe593a43e0a37b603a324454`; MSVC, SSE2; `.text` RVA 0x1000, virtual size 0x272C80, raw size
  0x273000; large address aware (up to 4 GB on 64-bit Windows). Source tree named in asserts:
  `c:\perforce\development\segarally\sourcecode\main\code\...`. Libraries: Direct3D 9 + D3DX9 (`d3dx9_41.dll`), Granny 2,
  FMOD Ex, DirectShow. VERIFIED.
- Code cave: the tail 0x673C80-0x674000 of `.text` (896 bytes) is zero padding that is mapped and executable at run time.
  VERIFIED (live). The camera patch uses about 886 of the 896 bytes.
- CONFLICT between knowledge-base files: 08_exe_loading.md says the exe is "not packed"; 16_lighting_shadows_lightmaps.md
  (2026-10-08) says it "is packed (3.3 MB file, data addresses beyond the raw size)". Both agree that run-time data such
  as the shadow parameters can only be read from the running process. Which description of the file is right is recorded
  as open (OPEN_QUESTIONS.md).

## 2. Start-up sequence of `patch.ps1`
1. Start the game through TeknoParrot (`TeknoParrotUi.exe --profile=<profile>.xml`); paths come from `setup.yaml`, filled by
   `setup.ps1` (finds TeknoParrot, reads `UserProfiles\*.xml` for a profile whose `<GamePath>` is `Rally.exe`, checks the
   exe's MD5 and the game's DLLs).
2. As soon as `Rally.exe` appears, set its CPU affinity (`-Cores`, default 4; section 8).
3. Wait until `[0x9EB81C]` (the settings pointer) is non-zero, then 20 s more for TeknoParrot's checks.
4. Suspend the process (`NtSuspendProcess`), verify every original byte, write, verify the written bytes, resume.
5. While the game runs: `Watch-Tracks` (15 ms loop) serves the track switcher (21), the checkpoint-time and shadow
   overrides (sections 6, 7) and the screenshot button. After the game closes: key-ups for Alt, Ctrl, Shift and Win are
   sent, because leaving the game can leave a modifier key "held" in Windows. VERIFIED (live).
- `-NoLaunch` attaches to a running game; `-Off` unpatches; a profile named `Baseline` means "no patch".
- The monitor must be on when the game starts: without one the game reports "failed to create d3d device" or shows a white
  window (owner's notes, 2026-10-07).

## 3. Chase-camera patch (cave at 0x673C80, signature "SR3C")

| Site | Original | New | What |
|---|---|---|---|
| 0x5F72DD | `e81eabe0ff` | `e82eca0700` | chase cam: target-direction hook (the call to 0x401E00 that normalises the target direction) |
| 0x5F7E29 | `e8d2a7ffff` | `e8b2c00700` | chase cam: eye placement (`call 0x5F2600`) goes through a wrapper |
| 0x5F724D | `e4ff6e00` | `d03c6700` | operand of `mulss xmm1, [0x6EFFE4]` at 0x5F7249: stiffness multiplier x7.5 -> the cave's (1.0) |
| 0x5F76B0 | `50056f00` | `a03c6700` | operand of `mulss ..., [0x6F0550]` (-15) at 0x5F76AC: damping constant -> the cave's |
| 0x6EB8A8 / 0x6EB8AC | `c0c45e00` / `b0c45e00` | `c03e6700` / `d03e6700` | vtable 0x6EB808 (chase): max / min stiffness getters |
| 0x6EB958 / 0x6EB95C | same | same | vtable 0x6EB8B8 (far chase): max / min stiffness getters |

- The chase camera's update is 0x5F71C0. Hooking only the target direction did not move the eye: the angle passed to
  0x5F2600 (arguments angle, distance, height; ecx = camera) must change too. VERIFIED (live, by patching).
- Stock values: stiffness table 15 / 90, times 7.5 = 112.5 / 675 (the live stiffness is at camera +0x24; it read about 364
  unpatched, mid-blend); damping -15; camera +0x30 is a dynamic pull-back added to the distance; +0x3B0 is the FOV in
  degrees (constructor default 60; it is the vertical field of view). The far chase multiplies distance by 1.25 and height
  by 1.15. VERIFIED (live).
- Cave layout: +0x00 "SR3C" and version; +0x08 strength, fade start (m/s), 1/fade range, slip factor, stiffness min, max,
  damping; +0x34..+0x4C diagnostics (canary flag, call counters); +0x50 stiffness multiplier; +0x54 soft angle limit (knee,
  range, 1/range in radians); +0x68 framing (enabled, distance, height, fov); +0x78 far-chase factors; +0x80 SR3's own
  distance / height / fov recorded each frame; +0x90 code.
- SR3's own chase framing, measured live: the view looks straight at the "car point" (camera +0x90), which sits about 0.85
  - 0.89 m behind the car's origin and 1.0 m above it in the car's frame; at rest the eye is `distance` behind that point
  and `height - 1 m` above it. Stock Chase: 5.04 m behind, 0.57 m above (5.1 / 1.6 / 60 in the patch's units). The field
  +0xCC ("look-at", about 3.9 m ahead of the car point) is not what the view uses. VERIFIED (live + screen captures).
- At speed the eye-to-car-point distance shrinks (one profile sampled: 3.85 m at 20-60 km/h, 3.5 at 100-150, 2.95 at 200),
  but the car point trails the car, so in screen captures the car stays the same size from 0 to 200 km/h. VERIFIED (live).

## 4. The camera manager and the cameras

The local player's camera manager is at `[0x9EB4EC] + 0x18` ("mgr"). VERIFIED (live).
| mgr offset | Meaning |
|---|---|
| +0x000 | frame time (seconds) |
| +0x190 | pointer to the camera in use |
| +0x1A8..+0x1C4 | 8 floats: developer camera inputs; the arcade game never writes them and clears them every frame |
| +0x1C8 | the player's car object |
| +0x22C / +0x230 / +0x234 | race camera list: count, current index, 21 pointers |
| +0x50C | pointer to the base framing of the car rotate cam: distance 5.10, height 1.57 |

View Change does `index = (index + 1) % count`. A race normally offers Chase, Bumper, Bonnet. The game resets the index at
a stage start or continue and rebuilds the list for a new race.

| mgr offset | vtable | Official name (vtable slot 18) | In the arcade game |
|---|---|---|---|
| +0x0510 | 0x6EB808 | Chase cam | race list |
| +0x08C4 | 0x6EB8B8 | Chase cam far | not offered |
| +0x1700 | 0x6EBD00 | Bumper cam | race list |
| +0x189C | 0x6EBD78 | Bonnet cam | race list |
| +0x1A38 | 0x6EBDF0 | Cockpit cam | not offered |
| +0x1BD0 | 0x6EBC88 | Wheel cam | not offered |
| +0x0EEC | 0x6EBB30 | Car rotate cam | developer |
| +0x0C78 | 0x6ECB98 | Free cam | developer |
| +0x1D68 | 0x6ECC88 | Car free cam | developer |
| +0x1FDC | ? | race intro fly-by (observed) | - |
| +0x2F24 | ? | trackside camera on Time Over / Continue (observed) | - |

- Putting a pointer to any hidden camera into the race list works; View Change then switches to it. VERIFIED (live).
- Common vtable slots: 1 reset; 3 update (`thiscall(mgr)`, `ret 4`); 6 get the car (`[mgr+0x1C8]`, 0x5ECB20); 18 name;
  19 camera type id (cockpit 6, wheel 3); 27 / 28 / 29 eye point, up vector, look point of the in-car cameras. Common
  fields: +0x08 heading history, +0x48 eye position (world), +0x174 vertical FOV in radians, +0x184 FOV in degrees.
- In-car cameras place the eye and look point from a 6-float record in the car's frame, pointed to by camera +0x194:
  Bumper eye (0, 0.75, 1.45) look (0, 0, 20); Bonnet (0, 1.19, 0.94) / (0, 0, 20); Cockpit (0.35, 0.95, -0.10) / (0.35,
  0.95, 0.90); Wheel (-1.3, 0.3, 2.1) / (-1.2, 0, 1.2). The cockpit cam sits in the passenger seat (the cars are left-hand
  drive); pointing +0x194 at a copy with both x values negated gives a driver's-seat view. VERIFIED (live).
- Developer cameras: car rotate update 0x5F1E00, input handler 0x5EED30, reset 0x5EEFC0; free cams update 0x5F3FE0, reset
  0x5F8840. The car rotate handler adds inputs without limits; holding one drives the camera through the car and the game
  crashes soon after. The patch clamps distance to 3-30 m and height to 0.5-20 m. VERIFIED (live: the crash and the fix).
  The car rotate cam disables the race timer while selected (observed).
- The car: `car = [mgr+0x1C8]`; `car + 0x135C` is its world matrix (three axis rows of 4 floats: right, up, forward, then
  the position). VERIFIED (live). Where the origin sits (ground, axle, centre of mass) is UNKNOWN.
- Final view matrix (camera-to-world rows right / up / forward / eye) at 0x9EB970 and 0x9F0680. The static view /
  projection block near 0x9F0640 is shared by several render passes and must not be read for the chase camera.

## 5. The camera-cycle block ("SR3V") and its hooks
One block of 0x3000 bytes allocated in the game with `VirtualAllocEx`, position-independent, starting on a 64 KB boundary
with the signature "SR3V" (built by `tools\build_cycle.py`, tested on an emulated CPU by `tools\cycle_emu.py`).

| Hook | Original bytes | Purpose |
|---|---|---|
| 0x591C4D | `a10cd17e00` (`mov eax, [0x7ED10C]` right before EndScene / Present) | per-frame entry on the game's render thread |
| 0x591B01 | `e81af7ffff` (`call 0x591220`, frees D3D resources before a device Reset) | release the block's fonts first |
| 0x6EBB3C (orig 0x5F1E00) | vtable slot 3 of the car rotate cam | wrapper writes mouse / keyboard input, then the original update |
| 0x6ECBA4, 0x6ECC94 (orig 0x5F3FE0) | vtable slot 3 of the free cams | same |

What the per-frame entry does: extends the race camera list (Chase + the game's cameras + one Chase entry per profile + the
hidden cameras; an entry `0x80000000 | offset` adds a camera a second time as a patched variant, the driver's-seat
cockpit); on an index change that is not "previous + 1" it puts the previous index back (that is the game resetting the
camera); loads the slot's settings into the cave; sets PVS off for CamLab and debug cameras; draws the camera name with a
`D3DXCreateFontA` font for 2 seconds, 14 % down the screen.

Fields used by the track switcher and other features (offsets in the block): LOADVIDEOS 0x2264, PHINT 0x2268 (second
popup line), HILITE 0x226C (highlighted stage card id, -1 = no selector), REOPEN 0x2270, REOPENPATH 0x2274, MODESEL 0x2278
(the first menu's selector value); scratch strings at 0x2400 (popup text), 0x2500 (video path), 0x2600 / 0x2640 / 0x2680
(announcer names), 0x2700 / 0x2740 / 0x2780 (ambience, music, events names). A running block whose code differs is never
rewritten in place: a new block is allocated and the hooks are redirected.

Rendering addresses: `[0x7ED10C]` IDirect3DDevice9*; `[0x7EDB74]` / `[0x7EDB78]` back buffer width / height; `[0xA339A4]`
the game window; IAT `GetModuleHandleA [0x6741F4]`, `GetProcAddress [0x674204]`. VERIFIED (live).

## 6. Checkpoint times per track (`Set-ArcadeTimes`)
The seconds every checkpoint marker grants live in the loaded ArcadeDatabase, one block of 0xC60 bytes per track at
`[[0xB2A850] + 0xC] + 4 + 0xC60 x track` (reader 0x661AA0, called at 0x5ABDF8 whenever a marker is crossed). A track folder
may bring `arcade_times.bin` (that block); it is written into the loaded table while the track is chosen, and SEGA's block
is put back when another one is. The file on disk is never touched. In game on Mountain the gantries at the three 1995
time checkpoints fire (owner confirmed), with the times swapped in memory this way. The block is made by `python work/scripts/arcade_times.py classic
<game> <course>`; its lap-1 and later-lap seconds for a classic course are a GUESS of that script (1995 practice mode, its
shortest lap setting, frames / 60; at the line on later laps the largest 1995 extension).

## 7. Shadow parameters per track (`Set-ShadowParams`)
- The pixel shaders read `gfShadowParamsPs` from four floats at 0x9F1068, set once at start-up by 0x594570: +4 (0x9F106C) =
  the smallest variance allowed (1/512), +8 (0x9F1070) = the power the result is raised to (10). VERIFIED (code + shader,
  07_glue_and_other_files.md).
- A track folder may bring `shadow.txt` ("<variance floor> <power>", for example "0.0002 30"); the two values are written
  while that track is chosen and SEGA's are put back otherwise. A third word "noblur" also replaces the call at 0x5A5467
  (bytes `E8 F4 84 F6 FF`, the only call of the 5 x 5 Gaussian blur 0x50D960) by five NOPs.
- Result in game (run of 2026-10-08): "the two numbers alone changed nothing visible". That the blurred target is the
  shadow map is LIKELY. With floor 0.0002, power 30 and the blur off, spectators stop casting shadows while the car still
  does (LIKELY, owner's observation, not isolated; 16_lighting_shadows_lightmaps.md).
- A first version of this function had a TAB character in a path (written through a shell heredoc), which stopped
  `Watch-Tracks` ("Alternative tracks stopped: Illegal characters in path" in play.log): no screenshot button and no
  shadow tweak in that run.

## 8. Video memory: "Out of memory for VB" and the affinity fix
- Symptoms, also in the unmodified game: an "Out of memory for VB" message box (from 0x577F00, the game's
  `CreateVertexBuffer` wrapper) or a white-screen freeze, after game over, when attract mode reloads, or on exit, on a
  many-core CPU at high settings. VERIFIED (live).
- Cause: `Sega_ML_Video_Decoder.cpp` keeps every video it plays in one of 20 slots at 0xAD2F90 (0x16C bytes each) and
  never releases a DirectShow graph (open 0x4DE430 -> 0x4DDC80; stop 0x4DE3F0 / 0x4DE3B0 only call Stop). The game
  preloads all of its about 18 videos at boot. Windows' WMV decoder (`wmvdecod.dll`) starts one worker thread per CPU the
  process may use: measured 139 MB of address space per graph with 32 CPUs allowed (30 threads), 69 MB with 4 (8 threads),
  61 MB with 2 (5 threads). One run at 3840 x 2160 with maximum settings: 589 threads, 4,010 MB used, largest free block
  27 MB, then a freeze. VERIFIED (measured).
- Fix: `-Cores 4` (default) sets the process affinity as soon as `Rally.exe` appears (mask 0x55 on SMT machines: one per
  physical core); `-Cores 0` disables it. With 4: 72 decoder threads, 2.5 GB used, 1.5 GB free in one block, no crash.
  VERIFIED (live).

## 9. Scenery visibility (PVS) switches
Format of the visibility data: 05_scene_kind11.md. Run-time addresses, VERIFIED (live):
| Address | Meaning |
|---|---|
| 0x500EA0 | refresh the visible set for the current context |
| 0xA65650 | 16 PVS contexts x 20 bytes: +0 node bitset pointer, +4 leaf bitset pointer, +8 current leaf, +0xC previous leaf, +0x10 node count (1365 on Tropical) |
| [0x9F05F4] | current context index |
| 0x9EB9A0 + 0x4D0 x [0x9F05F0] | camera position used for the leaf lookup ([0x9F05F0] = viewport) |
| [0xA65794] | non-zero = every node visible (0x4231E0). Nothing in the game writes it; safe to toggle at any time |
| [0xA65790] | freeze: skip the refresh |
| [0x9F0FAC] | also forces "all visible", but it is a special render pass flag (10 readers; the pass at 0x5C7900 sets a 10000 m draw distance). Do not use |

- The sets were built for road-level eyes: a high or roaming camera sees scenery (water, distant hillsides) flicker in and
  out. The race intro and attract cameras do not trigger it (why: UNKNOWN).
- The patch holds [0xA65794] = 1 for CamLab and debug cameras and while an added track is raced (an added track's scenery
  was sorted for its own game's cameras), and puts the game's value back otherwise.
- Draw distance: setting `DrawDistanceQuality` -> [0x89A014] (0-3) -> [0x9C10DC] = scale squared with scale 0.5 / 0.75 /
  1.0 / 1.5. VERIFIED (code).

## 10. Menu timers
The arcade's menus count down from 15 seconds and then choose for the player. The time is a constant in each menu's code
(15000 ms, compared with the time the menu has been up and handed to the on-screen countdown). All 18 sites are set to one
value while the game runs: 0x63D900, 0x6480FA, 0x6481A5, 0x648333, 0x648563, 0x64862D, 0x648795, 0x6487B0, 0x6488A2,
0x648933, 0x648AD2, 0x648B7B, 0x64E209, 0x64E2A6, 0x650B84, 0x65B489, 0x666223, 0x666C39. VERIFIED in game ("menu timers
120 s (18 sites)" is in the owner's list of things proven in game).

## 11. Screenshot button
START takes a screenshot, in a race only. The game has no known flag that tells a race from the attract loop, so the patch
treats "what follows the menus" as a race and holds the picture back for 1.5 s: if the menus come up in that time, START
was "begin a game" and the picture is dropped. The file name is shown only after the capture.

## 12. Things tried and removed
| Attempt | Result |
|---|---|
| A brighter stand-in for the light-map fallback colour 0xFF808080 at 0x5001A6, 0x51186C, 0x5D6441 and 0x640D89 (value 0xE8), to cure dark cars on an imported track | DISPROVED in game (2026-10-07): it washed the whole picture out and did not help the cars. 0x80 is the neutral value. The cars were dark because the road's overlay page texture, a sun / shadow map, had been written as all shadow (04_trackdeform_road.md) |
| Adding stage-card videos beyond the game's own | fails after two (20 video objects, 18 used); see game-runtime-and-frontend.md |
| Renaming a track folder through the database | blank cards, loads Tropical (folder names are hard-coded) |

## 13. Related run-time findings not used by a patch yet
- Polygon offset: SR3 has the render state (globals 0x8123C8 slope, 0x8123CC bias, applied at 0x590404..0x590486, reset at
  0x41863C), but which material field drives it was NOT found (UNKNOWN). VERIFIED (code) for the globals.
- Debug settings block at 0x9EB420-0x9EB4DC (defaults set in code around 0x4175xx): 0x9EB4C4 developer menu ("PRESS ESCAPE
  TO EXIT TO DEVELOPER MENU"), 0x9EB470 `ID_PAGE_TESTPOP`, 0x9EB450 performance overlay, 0x9EB458 replay page, 0x9EB4D8
  front end, 0x9EB47C all cameras. Static only; not explored in a running game.
- The executable still contains SEGA Rally Revo front-end strings and "ROBOSEAT TEST". The arcade operator (test) menu is
  not present as text; TeknoParrot's SR3 profile has no Test button.
- Crash diagnosis: the Windows Application Error log gives the fault offset even when an attached debugger logger sees
  nothing.

## 14. Driving the game from a script (`tools\pad.py`, `tools\autorun.py`)
`XInputGetState` of every `xinput*.dll` loaded in TeknoParrotUi is redirected, in memory only, to a stub that copies a
16-byte XINPUT_STATE from a buffer the script owns (pad 0 only). The real controller is ignored until TeknoParrotUi is
closed. SR3 profile bindings: Coin = Back, Start = Start, wheel = left stick X, gas = right trigger, brake = left trigger,
View Change = A, handbrake = right shoulder, shift up = right stick Y+, shift down = right stick X-. `autorun.py` presses
Start, steers to Classic (Championship -> Quick Race -> Classic), presses View Change n times, confirms and drives a fixed
pattern. VERIFIED (it was used for unattended runs on 2026-10-07). No input address inside `Rally.exe` is known (UNKNOWN).

## Road not drawn on tracks that ask for it (2026-10-09)
`Set-RoadHide`: a track folder with `road.txt` (`hide` or `hide all`) has the first byte of the road drawing routine 0x4EEF70 (and, with `hide all`, of the per-car road patch 0x4EE920) replaced by `ret` (0xC3) while that track is selected; restored for every other track; refused unless the expected six bytes are there. VERIFIED in game on the Mountain build RAW. Details, the search and the tests: [25_verbatim_road_and_milestones.md](25_verbatim_road_and_milestones.md).

`Set-ShaderTest`: `shader.txt` (`untextured` / `untextured-own`) swaps a pixel shader pointer of the uber effect; written, not yet run in game ([24_shaders.md](24_shaders.md)).
