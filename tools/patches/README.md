# patches.dll

SR3Lab's in-game patches applied from inside the game: the same bytes `patches.ps1` writes from outside. The
TeknoParrot-free runtime (`standalone\`, Codex's) loads `patches.dll` from the game folder after its own check of
Rally.exe and calls

    int __cdecl patches_start(const char *utf8_absolute_settings_path)    0 started, 1 settings, 2 game bytes, 3 internal

It returns at once; its own thread waits for the game's data (the dword at 0x9EB81C, as `patches.ps1` waits), checks
every site's original bytes, suspends the game's other threads, writes, and resumes them. Log: `patches.log` beside it.
Settings: the `patches:` section of `settings.yaml` (`mod_folder`, `camera_profile`, `profiles_file`, `overlay`,
`mouse_smoothing`, `camera_blend`, `canary`, `watchdog`; `enabled` is the runtime's), read with `standalone\settings.c`.

**Done (step 1, 2026-10-15): the cameras.** The chase camera's cave and hooks (`$Patches`) and the camera cycle block
(`Install-Cycle`). To do: the Classic tracks (track folder, switcher), cars and handling (car lists, cards, flavors,
SRC turning), the rest (START screenshots, race exit, watchdog).

## Lockstep with patches.ps1

The owner (2026-10-15): every change must reach both variants, checked by a script. So:

- **The bytes have one source**, `patches.ps1` (where `tools\build_*.py` and `embed.py` put them). `gen_blobs.py` copies
  its patch table and machine code into `blobs.h` at every build, and stamps the SHA-256 of that `patches.ps1` into the
  DLL (`patches_source()`); a DLL built from another `patches.ps1` is stale and `lockstep.py` refuses it.
- **The logic is checked**: `lockstep.py` asks both what they would write into a freshly started game, for 17 settings
  combinations (every profile, the built-in SR3 cameras, popup size, smoothing and blend at off / default / other
  values, canary, a profiles file with hiddenCameras off and its own fallbacks). `patches.ps1` answers through
  `plan_ps1.ps1` (its own code against a fake game holding the original bytes, as the mock tests run it), the DLL
  through `patches_plan()` (`plan32.exe`, the code `patches_start` runs). Every site, hook, pointer, the camera block's
  16 KB image, the profile and the camera list must be the same. `build.py` runs it; a difference fails the build.
- **Checked in the running game** (TeknoParrot route, 2026-10-15): the game patched by `PLAY.bat`, then patched by
  `patches.dll` (loaded in and started): every site, hook and pointer the same; the camera block the same but for 80
  bytes in its run-time state (0x2275-0x2278 the cockpit-seat copy, 0x2440-0x246e and 0x2500-0x251f smoothing and blend
  state), which the block's code changes every frame.

## Building

    python tools\patches\build.py [--out DIR] [--no-lockstep]

The toolchain's 64-bit gcc as 32-bit code (`-m32 -march=pentium4 -msse2 -mfpmath=sse`, the runtime's flags),
`tools\x86\implib.py` and `builtins.c`, no mingw start-up code, image base 0x63000000, no build paths in the DLL. No
`-fdata-sections`: the 32-bit link script puts `.bss.*` sections into `.data`, written out as zeros (493 KB instead of
48 KB). The machine code is still the hex `patches.ps1` carries (assembled with keystone on the author's PC); moving
its assembly to gcc's own assembler, so it is built on the user's PC, is the next step for it.
