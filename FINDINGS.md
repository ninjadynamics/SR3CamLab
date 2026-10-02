# SEGA Rally 3 (PC arcade) – reverse-engineering notes

*From [SR3CamLab](README.md), by Ninja Dynamics.*

Everything learned about `Rally.exe` while building SR3CamLab: the camera system, the hidden
debug cameras, rendering, the video memory bug, and how the patch hooks the game. It's
written for modders. Addresses are virtual addresses in the running game; offsets are
hexadecimal.

**Status markers:** *(verified)* was read live from the running game and confirmed on screen
or in memory. *(static)* was read from the disassembly only. *(observed)* is behaviour seen
while playing, not fully explained.

## Contents

1. [The executable](#1-the-executable)
2. [Method and tools](#2-method-and-tools)
3. [The camera manager](#3-the-camera-manager)
4. [The cameras](#4-the-cameras)
5. [The chase camera in depth](#5-the-chase-camera-in-depth)
6. [The developer cameras and their inputs](#6-the-developer-cameras-and-their-inputs)
7. [The car](#7-the-car)
8. [Rendering: device, frame hooks, visibility](#8-rendering-device-frame-hooks-visibility)
9. [Video playback and the "Out of memory for VB" crash](#9-video-playback-and-the-out-of-memory-for-vb-crash)
10. [Debug settings and leftovers](#10-debug-settings-and-leftovers)
11. [Game data](#11-game-data)
12. [How SR3CamLab patches the game](#12-how-sr3camlab-patches-the-game)
13. [Open questions](#13-open-questions)

---

## 1. The executable

| | |
|---|---|
| File | `Rally.exe`, version 3.8.4.1, 32-bit x86, MSVC, SSE2 |
| MD5 | `d7c0b475fe593a43e0a37b603a324454` |
| Image base | `0x400000` |
| `.text` | RVA `0x1000`, virtual size `0x272C80` (raw `0x273000`) |
| Large address aware | yes: up to 4 GB of address space on 64-bit Windows |
| Source tree (from asserts) | `c:\perforce\development\segarally\sourcecode\main\code\…`; module names like `Sega_ML_SceneManager_Block.cpp`, `Sega_ML_Video_Decoder.cpp`, `Sega_ML_Granny_Mesh.cpp`, `SegaRally_GameObjectAssetsHandler.cpp` |
| Libraries | Direct3D 9 + D3DX9 (`d3dx9_41.dll`), Granny 2 (animation), FMOD Ex (audio), DirectShow (video) |

**TeknoParrot's integrity check.** TeknoParrot's `TeknoParrot.dll` checks the executable from
inside the running process and refuses a modified file ("Unsupported CRC"). That includes a
file whose whole-file CRC32 was patched back to the original. So every modification has to
happen in memory, after the game has started. *(verified)*

**Free space.** The `.text` section's raw size (`0x273000`) is larger than its virtual size
(`0x272C80`), and the tail `0x673C80`–`0x674000` (896 bytes) is zero padding. Since memory
is mapped in 4 KB pages, that area is mapped and executable at run time: a convenient code
cave. *(verified)*

## 2. Method and tools

- Static: Python with capstone for disassembly, keystone for assembling patches, `pefile`
  for imports.
- Live: PowerShell scripts using `ReadProcessMemory` / `WriteProcessMemory` /
  `VirtualQueryEx` on the running game, plus screen captures (`CopyFromScreen` works with
  the game in fullscreen).
- Patches were tested on an emulated CPU (Unicorn) against a fake game state, and in a mock
  install test, before going into the real game.
- Thread start addresses come from `NtQueryInformationThread(ThreadQuerySetWin32StartAddress)`.
  Module names need a 32-bit PowerShell (`SysWOW64`) to enumerate.
- The patch sources, the tests and most of these scripts are in [tools/](tools/README.md).

## 3. The camera manager

The local player's camera manager is at **`[0x9EB4EC] + 0x18`** (call it `mgr`). *(verified)*

| Offset | Type | Meaning |
|---|---|---|
| `+0x000` | float | frame time (dt, seconds) |
| `+0x190` | ptr | the camera in use (a pointer to one of the camera objects below) |
| `+0x1A8`–`+0x1C4` | 8 × float | **developer camera inputs** (see [section 6](#6-the-developer-cameras-and-their-inputs)); the arcade game never writes them and clears them every frame |
| `+0x1C8` | ptr | the player's car object (see [section 7](#7-the-car)) |
| `+0x22C` | int | race camera list: count |
| `+0x230` | int | race camera list: current index |
| `+0x234` | 21 × ptr | race camera list: camera pointers (room for 21) |
| `+0x50C` | ptr | base framing used by the car rotate cam: `[+0]` distance 5.10, `[+4]` height 1.57 (SR3's chase values) |
| `+0x510` … | objects | the camera objects themselves, embedded in the manager (next section) |

**View Change** does `index = (index + 1) % count`, then switches to `list[index]`. A race
normally offers three entries: Chase (`+0x510`), Bumper, Bonnet. *(verified)* The race
presumably starts on the operator setting `VIEW=` in `config.ini`. *(not checked)*

**Stage start / continue:** the game resets the index to its default camera *(verified)*,
and for a new race it rebuilds the list from scratch *(static: the list count changes)*.

## 4. The cameras

All cameras live inside the manager. Their official names come from each class's vtable
slot 18 (a function that returns the name string). *(verified)*

| `mgr+` | vtable | Name | In the arcade game |
|---|---|---|---|
| `0x0510` | `0x6EB808` | Chase cam | race list |
| `0x08C4` | `0x6EB8B8` | Chase cam far | not offered (same class; distance ×1.25, height ×1.15) |
| `0x1700` | `0x6EBD00` | Bumper cam | race list |
| `0x189C` | `0x6EBD78` | Bonnet cam | race list |
| `0x1A38` | `0x6EBDF0` | Cockpit cam | not offered |
| `0x1BD0` | `0x6EBC88` | Wheel cam | not offered |
| `0x0EEC` | `0x6EBB30` | Car rotate cam | not offered (developer) |
| `0x0C78` | `0x6ECB98` | Free cam | not offered (developer) |
| `0x1D68` | `0x6ECC88` | Car free cam | not offered (developer) |
| `0x1FDC` | ? | – | race intro fly-by *(observed)* |
| `0x2F24` | ? | – | trackside camera on Time Over / Continue *(observed)* |

Putting a pointer to any of the hidden cameras into the race list works. The game's own View
Change then switches to it, and its update runs normally. *(verified)*

**Common vtable slots** (byte offset = slot × 4):

| Slot | Offset | Meaning |
|---|---|---|
| 1 | `+0x04` | reset to defaults (`ecx` = camera); car rotate `0x5EEFC0`, free cams `0x5F8840` |
| 3 | `+0x0C` | update, `thiscall(mgr)`, `ret 4` |
| 6 | `+0x18` | get the car: `return [mgr+0x1C8]` (`0x5ECB20`) |
| 18 | `+0x48` | name string |
| 19 | `+0x4C` | camera type id (cockpit 6, wheel 3) |
| 27 | `+0x6C` | in-car cams: eye point (car space); developer cams: input handler |
| 28 | `+0x70` | in-car cams: up vector (0, 1, 0) |
| 29 | `+0x74` | in-car cams: look point (car space) |

**Common fields:** `+0x08` heading history (the chase cam reads the car's heading here),
`+0x48` eye position (world), `+0x174` vertical FOV in radians, `+0x184` FOV in degrees
(60).

### The in-car cameras

Bumper, Bonnet, Cockpit and Wheel share the update `0x5F20F0` (Cockpit/Wheel) or a close
sibling. They place the eye and look point from a 6-float record **in the car's frame**,
pointed to by **`cam+0x194`** (x = right, y = up, z = forward, metres from the car's
origin). *(verified)*

| Camera | Eye (x, y, z) | Look (x, y, z) |
|---|---|---|
| Bumper | (0, 0.75, 1.45) | (0, 0, 20) |
| Bonnet | (0, 1.19, 0.94) | (0, 0, 20) |
| Cockpit | (0.35, 0.95, −0.10) | (0.35, 0.95, 0.90) |
| Wheel | (−1.3, 0.3, 2.1) | (−1.2, 0, 1.2) |

These records are per car (they live in the car's data). The **cockpit cam sits in the
passenger seat** (x = +0.35; the cars are left-hand drive). Pointing `cam+0x194` at a copy
with both x values negated gives a driver's-seat cockpit view. That's what SR3CamLab's
"Cockpit cam (patched)" does, restoring the pointer when you leave it. *(verified)*

## 5. The chase camera in depth

The chase camera's update is **`0x5F71C0`**. *(static, verified by patching)*

### Spring and aim

- **Aim direction:** at **`0x5F72DD`** it calls `0x401E00` (normalise a 2-D vector) on the
  target direction (the car's heading). Replacing that call is the cleanest place to bend the
  aim (SR3CamLab blends in the direction of travel there).
- **Stiffness:** a min/max pair from the vtable getters `+0xA0` (max, orig `0x5EC4C0`) and
  `+0xA4` (min, orig `0x5EC4B0`). The raw table values are **15 / 90**, multiplied by
  **7.5** at `0x5F7249` (`mulss xmm1, [0x6EFFE4]`; the operand is at `0x5F724D`), giving
  112.5 / 675. The live stiffness is at `cam+0x24` (it read ~364 unpatched, mid-blend).
- **Damping:** `mulss …, [0x6F0550]` (−15) at `0x5F76AC`; the operand is at `0x5F76B0`.
- Both vtables (`0x6EB808` near, `0x6EB8B8` far) share the code.

### Placement

- The eye is placed by **`call 0x5F2600`** at **`0x5F7E29`** with arguments
  `(angle, distance, height)` on the stack (`[esp+4]`, `[esp+8]`, `[esp+0xC]`, `ecx` = camera).
  Changing only the aim direction (above) does **not** move the eye; the angle passed here
  must change too. *(verified)*
- `cam+0x30` is a dynamic pull-back added to the distance.
- `cam+0x3B0` is the chase camera's FOV in degrees (constructor default 60).
- The far chase multiplies distance by 1.25 and height by 1.15.

### Fields

| Offset | Meaning |
|---|---|
| `+0x08` / `+0x10` | car heading x / z (horizontal unit vector) |
| `+0x24` | current spring stiffness |
| `+0x30` | dynamic pull-back |
| `+0x48` | eye position (world) |
| `+0x90` | **car point**: the smoothed point the camera aims at |
| `+0xCC` | a "look-at" point ~3.9 m ahead of the car point; **not** what the view uses |
| `+0x3B0` | FOV (degrees, vertical) |

### Framing, measured *(verified)*

From the camera object, the **final view matrix** (camera-to-world rows right / up /
forward / eye at `0x9EB970` and `0x9F0680`; its eye row equals `cam+0x48`) and frames
captured from the screen:

- **The view looks straight at the car point (`+0x90`).** The final view's pitch equals the
  angle from the eye to that point to 0.01°. The `+0xCC` field is not the aim.
- **The car point** sits ~0.85 – 0.89 m behind the car's origin and 1.0 m above it, in the
  car's own frame (`car+0x135C`, [section 7](#7-the-car)). In turns it drifts sideways with
  the spring.
- **At rest the eye is `distance` behind the car point and `height − 1 m` above it.** Stock
  Chase: 5.04 m behind, 0.57 m above (5.1 / 1.6 / 60 in SR3CamLab's units). Daytona profile
  3.8 / 1.9: 3.74 – 3.79 behind, 0.90 above.
- **At speed the eye-to-car-point distance shrinks** (Daytona: 3.85 m at 20 – 60 km/h,
  3.5 at 100 – 150, 2.95 at 200; height steady). But the car point trails the car, so in
  screen captures the car stays the same size from 0 to 200 km/h.
- The FOV value is the **vertical** field of view.

### Other chase-camera facts

- The car rotate cam **disables the race timer** while it's selected. *(observed)*
- The static view/projection block near `0x9F0640` is shared by several render passes; don't
  read the chase camera from it.

## 6. The developer cameras and their inputs

The arcade build has no input wired to these cameras. Their update reads
**`mgr+0x1A8`–`+0x1C4`**, which the game clears every frame before the cameras update.
Writing them from the camera's own update (wrapping vtable slot 3) is what makes them
steerable. *(verified)*

### Car rotate cam (`mgr+0xEEC`, vtable `0x6EBB30`)

- Update `0x5F1E00`; input handler (slot 27) **`0x5EED30`**; reset (slot 1) `0x5EEFC0`.
- The handler adds the inputs to the camera's state **without any limits**:

| Input | Scaled by | Adds to | Meaning |
|---|---|---|---|
| `+0x1A8` | dt × π/2 | `cam+0x0C` | orbit angle (reset π/2) |
| `+0x1AC` | dt × 10 | `cam+0x20` | distance offset (reset 0) |
| `+0x1B8` | dt × 10 | `cam+0x48` | height offset (reset 0) |
| `+0x1BC` | dt × 10 | `cam+0x34` | (reset −0.6) |

- Effective distance = `[[mgr+0x50C]] + cam+0x20`, height = `[[mgr+0x50C]+4] + cam+0x48`.
- **Crash:** holding an input drives the offsets without bound. The camera passes through
  the car and keeps going, and the game crashes soon after (probably an out-of-range lookup
  far outside the stage). SR3CamLab clamps distance to 3 – 30 m and height to 0.5 – 20 m.
  *(verified: the crash and the fix)*
- Past the end of the tilt the camera starts moving in and out (tilt and zoom interact).
  *(observed)*

### Free cam (`mgr+0xC78`, vtable `0x6ECB98`) and Car free cam (`mgr+0x1D68`, vtable `0x6ECC88`)

- Update `0x5F3FE0` (both); reset (slot 1) `0x5F8840`; slot 27 is a no-op (`ret 0x18`), so
  the inputs are used raw.
- Angles: `cam+0x268` **pitch** (fed to `D3DXMatrixRotationX`), `+0x26C` yaw (`…RotationY`),
  `+0x270` roll (`…RotationZ`).
- `angle += cam+0x230 × input`: pitch from `+0x1AC`, yaw from `+0x1A8`, roll from `+0x1C4`.
  `cam+0x230` is the rotation rate (0.02).
- Movement: `+0x1B0` forward/back, `+0x1B4` sideways, `+0x1B8` up/down. The movement speed
  builds up in `cam+0x22C` (by 5% of the input's length per frame, capped at half of it) and
  decays when there is no input.
- Position: `cam+0x25C`.
- Pitch is unlimited; looking past vertical flips the view. SR3CamLab stops it at ±89.99°.

## 7. The car

`car = [mgr+0x1C8]` (also what camera vtable slot 6 returns). *(verified)*

- **`car+0x135C`: the car's world matrix.** Three axis rows of 4 floats (x = right, y = up,
  z = forward) at `+0x00`, `+0x10`, `+0x20`, then the position at `+0x30`. All the cameras
  build from it.
- The origin is probably near the axle height (in-car cam eyes are ~1 m above it); not
  pinned down.

## 8. Rendering: device, frame hooks, visibility

### Device and frame

| | |
|---|---|
| `[0x7ED10C]` | `IDirect3DDevice9*` |
| `[0x7EDB74]` / `[0x7EDB78]` | back buffer width / height (present parameters) |
| `0x591C4D` | `mov eax, [0x7ED10C]` right before EndScene/Present: a clean per-frame hook site (5 bytes) |
| `0x591B01` | `call 0x591220`: frees D3D resources before a device Reset. Hook it to release your own fonts/textures |
| `[0xA339A4]` | the game window (TeknoParrot's window may differ; compare process ids instead) |
| IAT | `GetModuleHandleA [0x6741F4]`, `GetProcAddress [0x674204]` |
| D3DX | `d3dx9_41.dll` is loaded; `D3DXCreateFontA` works for text on top of the frame |

### Visibility (PVS) *(verified)*

The scene manager (`Sega_ML_SceneManager_Block.cpp`) culls the stage with a precomputed
**BSP-leaf potentially-visible set**. It finds the leaf the camera is in, and only nodes that
leaf lists are drawn. The sets were built for road-level eyes. A high or roaming camera sees
past them, and scenery (water, distant hillsides) flickers in and out as it crosses leaves.
The race intro and attract cameras don't trigger it.

| | |
|---|---|
| `0x500EA0` | refresh the visible set for the current context (leaf lookup → node bitset) |
| `0xA65650` | 16 PVS contexts × 20 bytes: `+0` node bitset ptr, `+4` leaf bitset ptr, `+8` current leaf, `+0xC` previous leaf, `+0x10` node count (1365 on Tropical) |
| `[0x9F05F4]` | current context index |
| `0x9EB9A0 + 0x4D0 × [0x9F05F0]` | the camera position used for the leaf lookup (`[0x9F05F0]` = viewport) |
| **`[0xA65794]`** | **PVS off:** when non-zero the refresh marks every node visible (`0x4231E0`). Nothing in the game writes it; it looks like a leftover developer switch. Safe to toggle at any time |
| `[0xA65790]` | freeze: skip the refresh |
| `[0x9F0FAC]` | also forces "all visible", but it is a special render pass flag (10 readers; the pass at `0x5C7900` sets a 10000 m draw distance). Don't use it |

Draw distance: the setting `DrawDistanceQuality` → `[0x89A014]` (0 – 3) → `[0x9C10DC]` =
scale² with scale 0.5 / 0.75 / 1.0 / 1.5.

## 9. Video playback and the "Out of memory for VB" crash

**Symptoms** (also in the unmodified game): an "Out of memory for VB" message box, or a white
screen freeze. These hit after game over, when attract mode reloads, or on exit, on a
many-core CPU at high settings. *(verified)*

**The message** comes from `0x577F00`, the game's `CreateVertexBuffer` wrapper
(`IDirect3DDevice9::CreateVertexBuffer` failing). That's an address-space failure, not a
pool limit: vertex buffers are only created while loading.

**The cause** is in `Sega_ML_Video_Decoder.cpp`. The game plays its front-end videos
(`frontend\PC\Videos\*.wmv`: loading, champ, QR, classic, C4, the car-select clips, the stage
intros…) through DirectShow, and it **never releases a video graph**:

| | |
|---|---|
| `0xAD2F90` | 20 video slots × `0x16C` bytes |
| slot `+0x000` | playing |
| slot `+0x004` | loaded (a slot with 0 here is free) |
| slot `+0x00C` | file name (0x100) |
| slot `+0x11C` | `IGraphBuilder` |
| slot `+0x120` | `IMediaControl` |
| slot `+0x124` | `IMediaEventEx` |
| slot `+0x128` | `IMediaPosition` |
| slot `+0x12C` | the source filter's `IFileSourceFilter` |
| slot `+0x130` | the game's own texture renderer filter (`0x1B8` bytes) |
| slot `+0x134` / `+0x138` | events |
| `0x4DE430` → `0x4DDC80` | open: take a free slot, build the graph |
| `0x4DE3F0`, `0x4DE3B0` | stop: `IMediaControl::Stop`, clear "playing"; nothing is ever released |

The open routine also queries `IMediaControl` twice into `+0x120`, and two different
interfaces into `+0x124`, without releasing the first ones (extra references). In practice
the game **preloads all ~18 videos at boot** and keeps every graph for the whole session.

On Windows 10/11 each graph runs the **WMV decoder (`wmvdecod.dll`) with one worker thread
per CPU the process may use**. Measured with one of the game's own WMVs in a standalone
DirectShow graph:

| CPUs allowed | Threads per graph | Address space per graph |
|---|---|---|
| 32 | 30 | 139 MB |
| 4 | 8 | 69 MB |
| 2 | 5 | 61 MB |

At 18 graphs on a 32-thread CPU that's ~2.5 GB of the game's 4 GB. One run at 3840×2160
with maximum settings: 589 threads (432 of them decoder workers), 4,010 MB used, the largest
free block 27 MB, then a freeze when the game-over reload needed more.

**Fix:** limit the process to a few CPUs before it loads its first video
(`SetProcessAffinityMask` / `Process.ProcessorAffinity`). With 4: 72 decoder threads, 2.5 GB
used, 1.5 GB free in one block, no crash. SR3CamLab's `PLAY.bat` does this (`-Cores`). Fixing
the graph lifetime itself is possible but unnecessary.

## 10. Debug settings and leftovers

*(static; partly explored)*

- A block of debug settings at `0x9EB420`–`0x9EB4DC`, defaults set in code around `0x4175xx`.
  Identified flags: `0x9EB4C4` developer menu ("PRESS ESCAPE TO EXIT TO DEVELOPER MENU"),
  `0x9EB470` `ID_PAGE_TESTPOP`, `0x9EB450` performance overlay, `0x9EB458` replay page,
  `0x9EB4D8` front end, `0x9EB47C` all cameras.
- The executable still contains SEGA Rally Revo front-end strings and "ROBOSEAT TEST".
- PVS debug strings: "Refreshing PVS %f ms, (leaf %d), %d/%d nodes visible, %d/%d leaves
  visible", "No Leaf for this place…" (their print calls are compiled out).
- The arcade operator (test) menu isn't present as text. TeknoParrot's SR3 profile has no
  Test button.

## 11. Game data

- **Stage routes:** `Main_release\tracks\<Stage>4\<stage>4_master_xdata.sbf`. SBZ1 files are
  an 8-byte header followed by zlib data. The `DesignRouteSpline` holds the stage's centre
  line as vec3 points about 2 m apart, in metres. CamLab's stage generator is calibrated
  against these.
- `config.ini` (game folder): operator and graphics settings (`VIEW=`, `DrawDistanceQuality`,
  resolution). TeknoParrot's `teknoparrot.ini` overrides the resolution.

## 12. How SR3CamLab patches the game

All of it is done by `patch.ps1` on the running process.

### Start-up

1. Start the game through TeknoParrot (`TeknoParrotUi.exe --profile=<profile>.xml`). Which
   TeknoParrot and which profile comes from `setup.yaml`. `setup.ps1` fills it the first time:
   it finds TeknoParrot (a running instance, or the folders above SR3CamLab) and reads
   `UserProfiles\*.xml` for a profile whose `<GamePath>` is `Rally.exe` (relative paths are
   relative to the TeknoParrot folder). It checks the exe's MD5 and the game's DLLs, and asks
   in a window when something is missing.
2. As soon as `Rally.exe` appears, set its CPU affinity ([section 9](#9-video-playback-and-the-out-of-memory-for-vb-crash)).
3. Wait until `[0x9EB81C]` (the settings pointer) is non-zero, then 20 s more for
   TeknoParrot's checks.
4. Suspend the process (`NtSuspendProcess`), verify every original byte, write, verify the
   written bytes, resume.

### The chase camera cave (`0x673C80`, signature `"SR3C"`)

| Offset | Content |
|---|---|
| `+0x00` | `"SR3C"`, version |
| `+0x08` | strength, fade start (m/s), 1/fade range, slip factor (2), stiffness min, max, damping (negated) |
| `+0x24`–`+0x30` | constants 0, 1, ε, speed ε |
| `+0x34`–`+0x4C` | diagnostics and scratch (canary flag, call counters, angle delta, target x/z, dot) |
| `+0x50` | stiffness multiplier (1.0; 7.5 = stock) |
| `+0x54` | soft limit: knee, range, 1/range (radians) |
| `+0x60` | abs / sign masks |
| `+0x68` | framing: enabled, distance, height, fov |
| `+0x78` | far chase factors 1.25, 1.15 |
| `+0x80` | SR3's own distance / height / fov, recorded each frame |
| `+0x90` | code: aim hook, stiffness getters, eye wrapper |

Patched sites:

- `0x5F72DD`: `call` → the aim hook. It normalises the target as before, blends it towards
  the direction of travel (by strength × speed fade × slip fade), and stores the angle
  between the result and the heading.
- `0x5F7E29`: `call` → the eye wrapper. It records SR3's framing, overrides distance
  (+ the dynamic pull-back) / height / fov if framing is set (×1.25 / ×1.15 for the far
  chase), adds the angle delta, applies the soft limit, then jumps to `0x5F2600`.
- `0x5F724D`: multiplier operand → the cave's multiplier.
- `0x5F76B0`: damping operand → the cave's damping.
- `0x6EB8A8` / `0x6EB8AC` and `0x6EB958` / `0x6EB95C`: stiffness getters → the cave
  (`fld [kmax]; ret` / `fld [kmin]; ret`).

### The camera-cycle block (`VirtualAllocEx`, `0x3000` bytes, signature `"SR3V"`)

Position-independent (code finds its own base with `call`/`pop`).

| Offset | Content |
|---|---|
| `0x0000` | settings and state: popup frames, size, last index, slot count, start slot, extended count, the manager, font and `D3DXCreateFontA` pointers |
| `0x0100` | slot names (21 × 32): slot 0 = SR3's stock chase, then one per profile |
| `0x0500` | slot settings (21 × `0x5C`: the cave's `+0x08`–`+0x34` and `+0x50`–`+0x80`), copied into the cave when a slot is selected |
| `0x0E00` | slot colours |
| `0x0EA0`–`0x0F80` | API names (user32, kernel32) and resolved pointers for the mouse/keyboard controls |
| `0x0F10` | mouse constants: radians per pixel, the game's input rates |
| `0x0F90` | free cam pitch limits (±1.5706) |
| `0x0F98` | hint font, hint flag, text pointer |
| `0x0FA8` | the camera you picked (index + 1), kept across stages |
| `0x0FB0` | hint text |
| `0x0FD0` | car rotate tilt per pixel, reset-key state |
| `0x0FE0` | car rotate limits: distance 3 – 30, height 0.5 – 20 |
| `0x1000` | code: per-frame entry (`0x591C4D` hook), camera update wrappers, device-lost entry |
| `0x2000` | game camera names (12 × 32) |
| `0x2180` | the game's list entries, camera offsets, hidden-camera list, colours (12 each) |
| `0x2240` | driver's-seat cockpit eye/look copy (24 bytes), then the game's original pointer |

Hooks:

- `0x591C4D` (5 bytes, `mov eax,[0x7ED10C]` → `call block`): every frame, before Present.
- `0x591B01` (`call 0x591220` → `call block`): release the fonts before a device reset.
- Vtable slot 3 of the car rotate cam (`0x6EBB3C`, orig `0x5F1E00`) and the free cams
  (`0x6ECBA4`, `0x6ECC94`, orig `0x5F3FE0`): wrappers that write the mouse/keyboard input,
  then jump to the original update.

What the per-frame entry does:

- **Extends the race list** when the game (re)builds it: `[Chase] + the game's cameras + one
  Chase entry per profile + the hidden cameras`. An entry `0x80000000 | offset` adds a camera
  a second time as a patched variant (the driver's-seat cockpit).
- **On an index change:** if it isn't `previous + 1` (wrapping), it's the game resetting the
  camera, so the previous index is put back. Otherwise it loads the slot's settings into the
  cave, sets PVS off (`[0xA65794]`) for CamLab and debug cameras (on for the game's own),
  swaps the cockpit eye pointer, and starts the name popup.
- **Draws the popup:** `D3DXCreateFontA` (Arial bold), an 8-direction dark outline plus the
  text, 14% down the screen; a half-size hint for steerable cameras.

**Input:** cursor delta from the screen centre (the cursor is re-centred each frame) and
`GetAsyncKeyState`, only while the game's window is in front (compared by process id).
Inputs are scaled so the game's own `× dt × rate` gives the intended motion.

**Updating a running game:** a block whose code differs is never rewritten in place. A new
block is allocated, the state is copied over, and the hooks are redirected to it. The old
block stays allocated, since a thread may still be inside it.

**Removing:** restore the hooks, the vtable entries, the game's own camera list, the cockpit
pointer and the PVS flag.

## 13. Open questions

- Where exactly the car's origin is (ground, axle, centre of mass), and the car models'
  dimensions.
- What `mgr+0x1BC` / car rotate `cam+0x34` control.
- Cameras `mgr+0x1FDC` and `mgr+0x2F24` (intro and trackside): their classes and
  parameters.
- The full debug settings block: the developer menu wasn't explored in a running game.
- Whether the race-intro and attract cameras avoid the PVS problem by being placed inside
  well-covered leaves, or use a different visibility path.
