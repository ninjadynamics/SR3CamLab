# sr3mods.dll and sr3mods.exe

**One implementation** (Bruno, 2026-10-15, option B): the patch logic is `patchcore.c`, written once against a small
game-memory interface (`patchcore.h`: read, write, alloc, suspend / resume, alive). Two front ends run it:

- `sr3mods.dll` (`sr3mods_dll.c`): inside the game, the game's own memory; started by the TeknoParrot-free runtime.
- `sr3mods.exe` (`sr3mods_exe.c`): from outside, ReadProcessMemory / WriteProcessMemory on a running Rally.exe (the
  TeknoParrot route):
  `sr3mods attach [<pid>] [--settings <yaml>] [--mod <dir>] [--delay <s>] [--camera-profile <n>] [--profiles-file <f>]
  [--overlay <px>] [--mouse-smoothing <s>] [--camera-blend <s>] [--canary] [--log <f>]`, or `sr3mods plan <out.json> ...`.
  (Not "sr3patch": Windows treats an unmanifested 32-bit exe with "patch" in its name as an installer and asks for
  administrator rights.)

`sr3mods.ps1` keeps its own PowerShell implementation until patchcore covers all of it (the live loop: track switcher,
cars and handling, START / race exit, watchdog); then it keeps only setup, the TeknoParrot launch and CamLab's options,
and runs `sr3mods.exe attach`.

## sr3mods.dll

SR3Lab's in-game patches applied from inside the game: the same bytes `sr3mods.ps1` writes from outside. The
TeknoParrot-free runtime (`standalone\`, Codex's) loads `sr3mods.dll` from the game folder after its own check of
Rally.exe and calls

    int __cdecl sr3mods_start(const char *utf8_absolute_settings_path)    0 started, 1 settings, 2 game bytes, 3 internal

It returns at once; its own thread waits for the game's data (the dword at 0x9EB81C, as `sr3mods.ps1` waits), checks
every site's original bytes, suspends the game's other threads, writes, and resumes them. Log: `sr3mods.log` beside it.
Settings: the `patches:` section of `settings.yaml` (`mod_folder`, `camera_profile`, `profiles_file`, `overlay`,
`mouse_smoothing`, `camera_blend`, `canary`, `watchdog`; `enabled` is the runtime's), read with `standalone\settings.c`.

**Done (step 1, 2026-10-15): the cameras.** The chase camera's cave and hooks (`$Patches`) and the camera cycle block
(`Install-Cycle`).

**Done (step 2, 2026-10-15): the live loop, in C and in lockstep, run by both front ends.** `pc_live.c` is
`Release-StuckKeys`' middle: `Set-MenuTimers`, `Set-CarLists` (+ `Complete-CarLists`, `Open-CarCards`), `Set-Handling`
(flavors, per-car path routine, the added cars, grip file, SRC turning, steering hook removal) and `Watch-Tracks`
(track switcher with folder routine, card videos, announcer, sounds, tunes, checkpoint times, shadows, road, shader
test, scenery visibility, popups, START screenshot with its JSON, VIEW CHANGE race exit, handling keys,
`Sync-RaceFlavor`). The outside world goes through GameMem too (`now`, `sleep`, `pad`, `key`, `front`, `shot`,
`news`), real in `pc_host.c` (GDI grab, or the runtime's back buffer in sr3mods.dll; PNG by WIC with the tEXt chunk),
fake in the tests. START and View Change are the game's own inputs (entries 53 and 15 at 0x9DBAD0), not a pad.
`pc_json.c` reads switch.json / handling.json (JSON's grammar, keys case-insensitive as PowerShell's).
`sr3mods attach` runs the loop until the game closes (then releases stuck modifier keys, as PLAY.bat); sr3mods.dll's
worker runs it after the cameras for the game's life. In the game (sr3mods attach, TeknoParrot route, 2026-10-15): the
live loop's start-up, the Classic popup stepping three tracks, a Classic race on track5 with its checkpoint times and
road, a START screenshot (3840x2160, SR3Lab chunk), VIEW CHANGE held leaving the race.

**Done (step 3, 2026-10-15): the re-attach path.** `pc_install_cameras` is sr3mods.ps1's `Test-CameraSites` +
`Install-CameraPatch` (moved into functions for this) write for write: a fresh game; a game already patched (the block
kept, its settings rewritten, the blend's hook taken out when the blend is 0); an older build (its hooks taken out
first); a newer build's block (a fresh block, the old one's camera list and cockpit seat carried over); foreign bytes
(refused, nothing written). Nothing is logged while the game is held. The camera plan (`pc_plan`) is now that same
install run on a fake memory, so plan and install are one code path. PLAY.bat run again on a running game:
`sr3mods attach <pid> --no-live` (the first attach keeps running the live loop; sr3mods.ps1 likewise starts its loop
only when it launched the game).

**Open (Bruno's decision, 2026-10-15): the crash and freeze watchdog.** It is watchdog.cs, started by sr3mods.ps1 on the
PowerShell route only; sr3mods.exe and sr3mods.dll have none. Until that is settled the routes are not equivalent there.
Then `PLAY.bat` and play.ps1 switch to sr3mods.exe.

## Lockstep with sr3mods.ps1

The owner (2026-10-15): every change must reach both variants, checked by a script. So:

- **The bytes have one source**, `sr3mods.ps1` (where `tools\build_*.py` and `embed.py` put them). `gen_blobs.py` copies
  its patch table and machine code into `blobs.h` at every build, and stamps the SHA-256 of that `sr3mods.ps1` into the
  DLL (`sr3mods_source()`); a DLL built from another `sr3mods.ps1` is stale and `lockstep.py` refuses it.
- **The logic is checked**: `lockstep.py` asks both what they would write into a freshly started game, for 17 settings
  combinations (every profile, the built-in SR3 cameras, popup size, smoothing and blend at off / default / other
  values, canary, a profiles file with hiddenCameras off and its own fallbacks). `sr3mods.ps1` answers through
  `plan_ps1.ps1` (its own code against a fake game holding the original bytes, as the mock tests run it), the DLL
  through `sr3mods_plan()` (`plan32.exe`, the code `sr3mods_start` runs), and `sr3mods.exe plan` with the same settings
  as switches (CamLab's way). Every site, hook, pointer, the camera block's 16 KB image, the profile and the camera list
  must be the same, three ways. `build.py` runs it; a difference fails the build.
- **The re-attach path too**: six more scenarios install once (not traced), change the game the way a second run
  finds it, and trace the second install: `retune`, `reblend` (other profile, popup, smoothing, blend, canary),
  `altfile` (another profiles file), `newer` (the block's code changed), `older` (a hook site of another build),
  `foreign` (someone else's bytes). The install's log lines other than its decision are worded differently on the
  two sides (sr3mods.ps1's for PLAY.bat's window, sr3mods' contract line for its callers) and are left out there.
- **The live loop is checked write for write**: `live_lockstep.py` runs both on five scripted fake games (`switch`:
  alternative tracks, Classic learnt, tunes, checkpoint times, shadows, road, shader test, card videos loaded on request;
  `start`: screenshots and their JSON, race exits taken, withdrawn and refused; `handling`: handling.json with good and bad
  flavors, the keys on the car select and in a race, two keys at once; `late`: car lists completed when the menus close, a
  car card opened; `odd`: unexpected bytes and broken files everywhere). `sr3mods.ps1` runs through `live_ps1.ps1` (its
  own code, `[Sr3Mem]` and the outside world faked), `pc_live.c` through `livetest.exe` (`livetest.c`'s fake GameMem, the
  same game: keep the two fakes alike). Every write (address, keep-writable, bytes), suspend / resume, allocation, log
  line, screen grab and frame mark must be the same, and handling.json (by value) and classic_mode.txt after. A wrong
  byte shows as e.g. `trace line 78 (after F 3): ps1 W 20000E60 1 3aff9cff | c W 20000E60 1 3bff9cff`. `build.py` runs
  it after `lockstep.py`. PowerShell's own ways that show in the writes are kept on purpose in the C (case-insensitive
  string compares and keys, ASCII `?` for other characters, `[long]` addresses, .NET number text); where sr3mods.ps1 had
  no set order (a hashtable's keys) it was given one ([ordered], file order), and four defects found on the way were
  fixed in it (the shader test's `0xFFFF0300` check and the screenshot's patched-cockpit name could never match, as
  PowerShell reads those literals as negative ints; two unreadable-memory cases stopped the loop; NaN got through
  shadow.txt's range checks).
- **Checked in the running game** (TeknoParrot route, 2026-10-15): the game patched by `PLAY.bat`, then patched by
  `sr3mods.dll` (loaded in and started): every site, hook and pointer the same; the camera block the same but for 80
  bytes in its run-time state (0x2275-0x2278 the cockpit-seat copy, 0x2440-0x246e and 0x2500-0x251f smoothing and blend
  state), which the block's code changes every frame.

## Building

    python tools\sr3mods\build.py [--out DIR] [--no-lockstep]

The toolchain's 64-bit gcc as 32-bit code (`-m32 -march=pentium4 -msse2 -mfpmath=sse`, the runtime's flags),
`tools\x86\implib.py` and `builtins.c`, no mingw start-up code, image base 0x63000000, no build paths in the DLL. No
`-fdata-sections`: the 32-bit link script puts `.bss.*` sections into `.data`, written out as zeros (493 KB instead of
48 KB). The machine code is still the hex `sr3mods.ps1` carries (assembled with keystone on the author's PC); moving
its assembly to gcc's own assembler, so it is built on the user's PC, is the next step for it.
