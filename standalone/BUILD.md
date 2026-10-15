# Standalone build and plugin interface

The setup's WinLibs x64 UCRT GCC is the only compiler. `-m32` emits the runtime
and launcher; the same compiler emits the x64 raylib settings companion. The
builder is standard-library Python and never fetches tools or sources.

```
python standalone/build.py --jobs 31
python standalone/build.py --target runtime --sdl-source PATH
python standalone/build_companion.py --raylib-source PATH
```

Run from SR3CamLab, or supply the script's full path. Defaults:
`standalone/deps/SDL`, `standalone/deps/raylib`, `standalone/build/native`.
`--out` selects an independent output/cache. `--gcc` overrides the common setup
lookup: `SR3_GCC`, `tools/import/settings.json`'s `gcc`, shipped
`tools/mingw/bin/gcc.exe`, then the installed compiler fallbacks in cbuild.py.
`--jobs` defaults to logical CPUs minus one, minimum one. The embedded setup
Python can run the script directly; neither pip nor extra Python modules are needed.

## Why this build path

Normally GCC links MinGW startup objects, libgcc and Windows import libraries.
The installed compiler's 64-bit set contains no 32-bit CRT/libgcc libraries.
Its C frontend, assembler, linker and shared headers already support `-m32`.
We use those directly, with the Windows UCRT, small plain-C entry points,
`tools/x86/builtins.c`, and import libraries generated from the Windows export
names our objects actually reference. No bytes from Windows DLLs are bundled.

The x86 command uses `-nostdlib -nostartfiles`, explicit entry points, fixed
Pentium 4/SSE2 code generation and `-ffreestanding`. The latter prevents compiler
rewrites of low-level helpers into recursive calls. No C++ global constructors
are supported by these entry points. `ucrt_stdio.c` bridges C99 formatting to
UCRT's `__stdio_common_*` exports; the OS owns FILE, allocation and locale state.
The x64 companion uses the compiler's normal static CRT/library link.

SDL is configured for Windows controller input. HIDAPI, XInput, RawInput,
DirectInput, WGI and virtual controllers remain enabled. Audio, rendering, GPU
and camera backends are disabled. Optional C++ GameInput is omitted so a second
compiler frontend is unnecessary. SDL's float fallbacks replace math entry
points absent from the 32-bit OS UCRT. These decisions live in
`sdl_config/SDL_build_config.h`; the upstream sources are not edited.

Independent translation units compile concurrently. Python threads launch GCC
processes, so a Python process pool or OpenMP inside the builder would add
startup/coordination overhead without parallelizing more C compilation. Cache
keys include source/header content, flags and the compiler tools; object and
dependency hashes are checked before reuse. `-MD` records the actual include
closure for packaging. Fixed object order, timestamp-free linking, path maps,
deterministic import libraries and an explicit preferred DLL image base avoid
output-folder differences. DLL relocation and ASLR remain enabled.
On x86, data stays in ordinary `.data`/`.bss`: this toolchain's i386 linker
script does not collect `.bss.*`, so `-fdata-sections` would store zero-filled
statics in the DLL file. The x64 linker handles split data sections correctly.

## Pinned sources and outputs

`sdl-pin.json` records the required files from the inspected clean SDL
release-3.4.16 checkout, commit `fa2c02bb6e21974a89ea9824bc53c9932abe5f9c`.
`raylib-pin.json` records the local raylib 5.5 source snapshot. These are per-file
hash manifests, not purported release-archive checksums. File lists include each
upstream license. The builder rejects missing or modified pinned inputs.

The build emits `dinput8.dll`, `launch.exe`, `settings.exe`, license files and
`build-provenance.json` (compiler hashes, commands' flags, source/include closure,
artifact hashes). The `imports` folder records generated DLL import names and
library hashes. Tests and caches are development artifacts, not game installs.
`--write-toolchain-closure standalone/toolchain-closure.json` on an all-products
build records compiler headers and actual `ld -t` CRT/import-library inputs for
release.py. It hashes each file; packaging must reject mismatches. Link input
hashes also invalidate the build cache when a compiler library changes.
Do not ship the `test_*.exe` or mock plugin DLLs in the playable overlay.

Every runtime build runs input, settings, UCRT, SDL virtual controller, host
identity, screenshot readback and plugin loader checks. Screenshot tests use
mock D3D COM objects and real worker/event lifetimes, with no GPU access.
The standalone Python tests cover settings
import and overlay copy/link materialization. No game data is needed for these
tests. Physical controllers, game rendering/audio and actual mod integration
still need a live run; a virtual controller is not evidence of those.

## sr3mods.dll contract

The runtime calls only the DLL adjacent to itself. `LoadLibraryExW` restricts
dependency resolution to that directory and Windows. It calls, once:

```c
int __cdecl sr3mods_start(const char *absolute_settings_path_utf8);
```

Return 0 for success; 1 for invalid settings, 2 for unexpected game bytes, 3 for
internal errors. Any nonzero value stops startup visibly and points to
`sr3mods.log`. The module stays loaded for the process lifetime. Initialization
must return promptly; the plugin's worker waits for game data at `0x9EB81C`.

Dispatch occurs after `RacingClass` CreateWindowExA returns. The inspected call
is at `0x558D40` inside WinMain `0x558A50`, called by CRT startup at `0x4B14F1`.
The executable identity check and runtime configuration/HUD writes have already
finished. No plugin load happens inside DllMain or the runtime InitOnce callback.
The launcher currently uses ANSI paths; the loader explicitly converts ACP to
UTF-16 to UTF-8 at the ABI boundary. This does not imply general Unicode support
for the current launcher/YAML file access.

The shared reader exposes `sr3_patch_value(&settings, key)`: NULL is omitted,
an empty string is explicitly empty. `enabled` accepts auto/on/off. Other known
scalars are retained verbatim (after YAML unquoting) for plugin-owned validation:
`mod_folder`, `camera_profile`, `profiles_file`, `overlay`, `mouse_smoothing`,
`camera_blend`, `canary`, `watchdog`. The plugin owns their defaults and meanings.
Single quotes and literal path characters survive companion saves. Unknown,
duplicate or multiline keys are rejected. Existing cleared default controller
bindings stay omitted through saves.
Plugins can call `sr3_load_utf8` directly on the ABI filename; it opens with
Windows `_wfopen`. Ordinary launcher/runtime `sr3_load` retains ACP file paths.

`play.ps1 -WithMods` attaches the shared `tools/sr3mods/build/sr3mods.exe`
with an explicit PID and waits for its live loop. It refuses an overlay
with an adjacent sr3mods.dll to prevent two patchers from mutating one process.

## Screenshot bridge

`dinput8.dll` exports this cdecl worker-thread API (also declared in `capture.h`):

```c
int sr3rt_grab_backbuffer(void **bgra, int *width, int *height);
```

Return 1 gives top-down, tightly packed BGRA8 pixels with alpha 255; the caller
owns them and calls `HeapFree(GetProcessHeap(), 0, pixels)`. Return 0 clears all
supplied outputs and sets `GetLastError` (not-ready, busy, timeout or readback
failure). The caller waits up to 250 ms. Call from a mod worker, never from the
game's render thread. The plugin owns PNG encoding and filenames.

The render thread services a queued request immediately before device Present.
Idle frames only check a pointer; no allocation or D3D work occurs. Requests own
separate caller/render references so timeout during readback cannot free an
event or buffer still in use. Every surface is released within that call; no
surface or device reference is retained across Reset. Supported backbuffer
formats are A8R8G8B8 and X8R8G8B8. Multisampled buffers are first resolved to a
matching non-multisampled render target, then copied to system memory, following
the [D3D9 readback requirements](https://learn.microsoft.com/en-us/windows/win32/api/d3d9/nf-d3d9-idirect3ddevice9-getrendertargetdata)
and [multisample resolve documentation](https://learn.microsoft.com/en-us/windows/win32/api/d3d9/nf-d3d9-idirect3ddevice9-stretchrect).

`test_capture.c` checks row padding, opaque output, resolve, each COM failure,
single queued request, timeout before/after render-thread ownership, cleanup and
subsequent reuse. Passing those checks does not prove live fullscreen capture.

## Watchdog launch modes

Automatic recording defaults on. Set `patches.mod_folder` to the absolute
SR3CamLab folder (containing watchdog.cs, sr3mods.ps1 and standalone/watchdog.ps1
plus watchdog.exe and watch_process.cs). The native launcher follows `patches.watchdog`; use
`launch.exe --watchdog` or `--no-watchdog` to override it for one launch. The
settings app's Advanced tab has the auto toggle and Start with watchdog button.
Explicit/automatic native watched launch attaches before resuming the game;
a game launched directly is watched after sr3mods.dll installs its cameras.
Ctrl+Scroll Lock requests recording later. See WATCHDOG-PROPOSAL.md for APIs,
mutex/identity rules, evidence and remaining live validation.

The native build also emits `watchdog.exe` and installs it beside
`standalone/watchdog.ps1`. It uses Windows' installed x64 .NET Framework csc.exe
and Windows PowerShell assembly; no compiler download or Visual Studio install.
watchdog.exe runs that same script in its own process and accepts its named
attach/launch arguments. `--script PATH` selects an explicit script for tests.
The C# compiler output is cached; clean-build byte reproducibility is not claimed
for this small host. The runtime, launch.exe and settings.exe still use GCC.


Both apps accept an explicit settings copy:

```powershell
.\launch.exe --settings .\settings.windowed.yaml
.\launch.exe --settings .\settings.windowed.yaml --no-watchdog
.\settings.exe --settings .\settings.windowed.yaml
```

Omitting --settings keeps settings.yaml beside the executable. An explicit
relative path resolves from the caller's working directory; game_path remains
relative to the selected YAML. The companion loads, saves and launches that
same copy and shows its filename. Invalid or conflicting arguments are rejected
before any game launch. Launcher watchdog switches can precede or follow
--settings. The existing diagnostic --preview option remains supported by the
companion. test_command_line.c covers parsing and path selection.
