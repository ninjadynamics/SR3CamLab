# Interface and executable notes

Supported Rally.exe SHA-256:
`8eb7bdf01b8dc30ba40a43ac3d4065b9035cc59d58dd01b3c03113a1403171b5`.
The supplied installation already includes compatibility modifications according
to its readme. It is not being described as a verified pristine cabinet dump.
PE x86 base 0x400000; image size 0x750000; `.text` CRC32 dd097484 over
0x273000 bytes at RVA 0x1000. The DLL checks these before changing game memory.

The game's cabinet report is 15 bytes: steering at bytes 1/2, brake at 3,
accelerator at 4, buttons at 6, cabinet status 12 at byte 7. The five button
bits are Start/View/Handbrake/Up/Down. The current TP pipe comments swap the
View/Handbrake labels; its actual button/profile mappings establish the order.

Public reference implementations inspected:

- [OpenParrot SR3](https://github.com/teknogods/OpenParrot/blob/fc8ba632e1f67c5c340ff88f30efca743e8d38f5/OpenParrot/src/Functions/Games/Europa-R/SR3.cpp)
  identifies the cabinet initialization, reader, language/resolution hooks and
  four in-race HUD width operands. At 3840 wide the operand values are
  1365 / 1500 / 1425 / 1365 for timer / time extended / final lap / countdown.
  `hudAdjust` emits new immediate-load instructions at those inspected sites.
- [TP SegaRallyPipe](https://github.com/teknogods/TeknoParrotUI/blob/master/TeknoParrotUi.Common/Pipes/SegaRallyPipe.cs)
  describes the report layout.
- [TP AnalogHelper](https://github.com/teknogods/TeknoParrotUI/blob/master/TeknoParrotUi.Common/InputProfiles/Helpers/AnalogHelper.cs)
  and [JvsHelper](https://github.com/teknogods/TeknoParrotUI/blob/master/TeknoParrotUi.Common/Jvs/JvsHelper.cs)
  establish steering conversion, including ignoring the wheel mapping's
  IsAxisMinus flag. DigitalHelper uses signed stick thresholds of 15000.
  SDL's vertical stick direction is opposite XInput's and is converted on import.

The runtime implementation is new C code. No game executable or game code is
distributed with the source. SDL3 is statically linked under its zlib license.
Raylib is statically linked into the companion under its zlib license; both
license files accompany installed binaries.

The user's HyperSolar ps2client/dcload-ip host implementation was inspected
read-only. Its SDL3 event ownership and hotplug model informed this runtime:
one game input thread owns polling, stale controller state is released, and
reconnection is automatic. An in-process input provider does not need the UDP
transport used for the consoles. The first SDL controller is selected by default.

The game imports DirectInput8Create, so dinput8.dll forwards that export to the
system DLL. Only the game's inpout32 load is redirected to our user-mode Out32
export. Its last command is retained for future output integrations; no kernel
driver is loaded. Resolution, language, volume, free play and network isolation
are supplied through scoped game IAT hooks. D3D9 create/reset hooks keep the
backbuffer and game resolution consistent. Rendering was observed on an earlier
1280x720 probe; the final 4K settings build is not yet live-validated.

## Native toolchain validation, 2026-10-15

The private test installation now uses the GCC-built runtime, launcher and
raylib companion. Previous binaries are retained with `.before-native-gcc`
suffixes. Neither original nor private Rally.exe changed; the deployed YAML
also kept its exact bytes, including 4K and omitted controller bindings.

GCC 13.2 builds all three products using the setup compiler subset. A staged
copy contained only pinned SDL/raylib files, our source, and the compiler subset
plus the 349-file header/link-input closure. With PATH restricted to that
compiler's bin and System32, all native checks passed. Its runtime, launcher and
companion hashes matched the original development tree byte for byte.
`../../SR3-investigation/native-repro.json` records hashes, imports and sizes;
`native-install.json` records installation and backups. Sizes were 1,595,904,
11,776 and 970,240 bytes respectively. Imports are Windows DLLs only.

Checks cover cabinet input conversion, settings/patch scalar round trips,
default binding omission, strict UTF-8 file access, UCRT formatting/scanning,
SDL virtual gamepad controls and reconnect, unsupported-host refusal, and an
adjacent-only mock plugin with missing/disabled/failed-start cases. Nine Python
importer/overlay tests also pass. The source-built companion was rendered with
the imported profile and inspected. These results do not constitute a live
4K race, physical DualSense, audio, haptics or real sr3mods.dll integration test.

Subsequent build probe: removing x86 `-fdata-sections` restores a real BSS
section and reduces the runtime from 1,595,904 to 1,576,960 bytes. Native checks
pass and an isolated source/compiler rebuild is byte-identical; evidence is
`native-bss-comparison.json` and `native-bss-repro.json` in the investigation
folder. This probe has not replaced the installed build during Claude's live
mod comparisons.

An independent copy-mode mod overlay is prepared at
`../../SR3-investigation/modded/Rally`; `modded/PLAY-MODS.bat` selects the
existing PowerShell mod path. Its 820 copied source files passed hash and
private-file checks, and all six listed alternative-track folders are present.
The wrapper's previously skipped `-NoLaunch` lifecycle is now entered explicitly
using the original patcher's functions. This route still awaits live validation.

The subsequent private-overlay startup checks failed before game data or mods
loaded: D3D9 CreateDevice returned `0x8876086c` on both hardware attempts and
`0x8876086a` on the software-vertex attempt, in both fullscreen and windowed
3840x2160 configurations. D3D enumerates 60 Hz and 165 Hz at this resolution;
the desktop reports 165 Hz. The cause is unresolved. The windowed test used a
separate diagnostic YAML; saved user settings were unchanged. The modded copy
alone carries a BSS-optimized build with additional presentation-parameter
logging; the installed baseline remains at the recorded native-install build.
Logs are under `../../SR3-investigation/modded/`, including
`windowed-display-failure.log`. All game tests are on hold while the owner has
another game in use, until he says the PC is free. No modded-ready claim follows
from the build checks or copy audit.

Claude's shared-core handoff (chat #68): the owner selected one C implementation
for `sr3mods.dll` and external `sr3mods.exe`. Both currently cover cameras only;
three-way camera plans (PowerShell / DLL / external tool) pass 17 settings cases.
Do not switch `play.ps1 -WithMods` until the shared core also covers menu timers,
cars, handling, track switching, START shortcuts and watchdog behavior. The future
external command is `sr3mods.exe attach <explicit pid> --settings <absolute yaml>
--delay 0`, with optional `--log`; camera switches override YAML. Today it exits
after camera installation; the complete implementation will remain attached
until the game exits. Integration must preserve that lifetime and propagate
nonzero exit codes. Native SDL DualSense input must reach START shortcuts through
logical game input rather than relying on the controller also appearing in XInput.

Chat #71-73 agreed a screenshot bridge and external watchdog boundary. The
runtime now exports `sr3rt_grab_backbuffer` (see BUILD.md), servicing worker
requests before Present with a 250 ms wait limit. The BSS probe build passes
mock readback/lifetime checks and the existing native suite. No GPU or game was
started for those checks; this newer build has not replaced either playable
overlay's DLL. Live capture remains unverified. The runtime has no crash/freeze
recorder: Claude owns the planned external `sr3mods.exe watch <pid>` mode; the
launcher will integrate it when ready, avoiding a second watchdog on attach.

After the PC-free signal, terminal `Start-Process` still failed D3D creation,
but the same private copy/DLL started through the interactive native launcher
created its 3840x2160 fullscreen device successfully (PID 23008; log saved as
`modded/native-launch-fullscreen-success.log`). This distinguishes launch context
from the previous BeamNG hypothesis; it does not establish the exact cause.
Window capture failed with `FrameArrived timed out: timed out waiting on channel`.
The subsequent temporary capture plugin (PID 16548) also reached successful D3D
creation, but its eight requests, starting six seconds after plugin startup,
all timed out. Live pixels and START mapping remain unverified. Both games were
closed using the runtime's Escape handler. The test-only plugin was removed
after verifying its hash and the modded copy's previous runtime was restored.

Static follow-up: device pointer `0x7ED10C` is used for EndScene at `0x591C61`
and device Present at `0x591C72` (vtable offset `0x44`). The game does have a
device-Present path; a swap-chain-only explanation is unsupported. A subsequent
probe should distinguish no rendered frames during boot from a replaced hook.
Claude confirmed sr3mods.dll will own launching its adjacent `sr3mods.exe watch`
helper, while external attach owns its own watchdog. Native launchers must not
start a duplicate. That helper is still pending, not installed or verified here.

The longer fullscreen capture probe succeeded (PID 17696, 2026-10-15):
3840x2160, 33,177,600 pixel bytes, visually inspected as the game's blue
machine-information boot screen. First Present occurred 16 ms after device
creation. Requests at 6-12.75 seconds timed out, but the 15-second request
succeeded with matching device/vtable/hook pointers. A loading-period frame
gap explains the timeout in this run; it is not evidence that the hook was
missing. Evidence: `modded/Rally/capture-live.bmp`,
`modded/capture-success-runtime.log`, `modded/capture-success-probe.log`.
This proves fullscreen readback of a rendered boot frame, not a completed
modded race. The temporary probe was removed and prior runtime restored after
closing the game. The automated Return press produced no sampled input change.
Claude independently verified START index 53 (`0x9DBBA4`) and View index 15 in
menus/race, and updated both mod implementations (chat #87).

Superseding watchdog plan (chat #90): Claude is not porting watchdog.cs to C;
crash/freeze recording remains on the PowerShell route. There is currently no
watchdog on the DLL route, and no helper should be wired based on the earlier
proposal. Re-attach support and clarification of the final parity scope are
pending; the standalone wrapper remains on its complete interim PS lifecycle.


Current watchdog/integration status (supersedes the provisional chat #90 plan):
owner #102 selected the common external recorder; #110-117 specified explicit
watched launch, in-game Ctrl+Scroll Lock, and automatic startup ON by default.
The shared helper and both patch fronts are implemented and pass 17/17 camera
plus 11/11 live lockstep cases. Native launch and the raylib companion build and
pass the existing native suites. `play.ps1` now uses sr3mods.exe's full live loop,
with a tested explicit PID/settings/profile/exit-code contract. The new external
host reuses unchanged watchdog.cs. Native attach and suspended-launch fixtures
pass, including a real dump for an exception at target entry. Host crash/freeze,
duplicate and detach tests pass; see WATCHDOG-PROPOSAL.md. These are stand-in
checks, not a complete live-game validation. The new binaries are built under
native-bss-probe; installing them and reviewing the new companion controls are
separate remaining steps. No CamLab files were changed.


Unified names (owner approval, Claude b188f89): adjacent sr3mods.dll and export
sr3mods_start, sr3mods.log, sr3mods.ps1, tools/sr3mods. The renamed watchdog.ps1
now also runs inside a genuine x64 watchdog.exe host, without a PowerShell child.
Native build/loader tests pass with the new names. The shared launcher and
play.ps1 invoke watchdog.exe; its direct script entry remains available. Staged
launch.exe/settings.exe were rebuilt. Historical evidence directories and
previously installed game binaries are retained as their original evidence.
