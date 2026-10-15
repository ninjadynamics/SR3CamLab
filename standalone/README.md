# SR3Lab standalone

One x86 `dinput8.dll` supplies cabinet input, native SDL3 controller support and
display/configuration hooks. `launch.exe` starts the private game copy directly;
`settings.exe` is a static raylib 5.5 companion with CamLab's palette and Segoe UI.
Neither executable needs TeknoParrot, Python, a browser, or a background service.
The companion is x64; the runtime and launcher are x86.

## Current local test installation

In `../../SR3-investigation/`, run `settings.exe` to edit settings or `launch.exe`
to play. Both use the adjacent `settings.yaml`, which points at the private
`baseline/Rally/Rally.exe`. The launcher passes its absolute YAML path to the DLL
via the child process environment (`SR3LAB_SETTINGS`). Paths in YAML are resolved
relative to YAML, never to the shell's working directory.

The imported profile is **3840 x 2160 fullscreen at 60 Hz, VSync on, English,
free play and in-race HUD adjustment on**. Music/effects/voice are 80/70/80.
Left stick steers; R2/L2 accelerate/brake; Options starts; Cross changes view;
R1 is handbrake; right stick up shifts up; right stick left shifts down;
Create/Back inserts a coin when free play is off. The imported steering curve
has no added deadzone and reproduces TP's integer conversion. SDL indices can
differ from XInput slots when multiple devices are connected.

The complete original XML and an import report are adjacent to YAML as
`teknoparrot-import.xml` and `settings-import.json`. Disabled online score,
capture/upload, FFB Blaster, and cabinet-output features are recorded there.
They are not implemented by this runtime. Force feedback, haptics and linked
cabinet play are not implemented. Unoverridden graphics/gameplay settings come
from the private game's existing `config.ini`.

## Settings app

Four pages: Display, Controls, Game, Advanced. Click an option to choose it;
click a number to edit, Ctrl+A to replace, Enter to confirm, Esc to cancel.
Save uses a temporary file, preserves the previous file as `settings.yaml.bak`,
and replaces YAML atomically. External edits require Reload before saving.
Closing with unsaved edits offers Save, Discard, or Keep editing. Ctrl+S saves;
Ctrl+Enter saves and plays. Changes take effect on the next launch.

The YAML reader deliberately supports a small versioned schema: scalar fields
under the sections shown in `settings.yaml`, two spaces of indentation,
single-quoted literal strings, booleans and integers. Unknown or invalid keys
are rejected. It is not a general YAML implementation: no anchors, sequences,
multiline values or escaped double-quoted paths. Keep paths within the Windows
ANSI code page for this first runtime version.

## Build and import

```
python build.py --sdl-source PATH_TO_PINNED_SDL --raylib-source PATH_TO_RAYLIB
python -m unittest discover -s . -p "test_*.py"
python overlay.py PATH_TO_RALLY_FOLDER NEW_OVERLAY_FOLDER
python import_settings.py PATH_TO_UserProfiles/SR3.xml NEW_OVERLAY_FOLDER/settings.yaml --game-ini PATH_TO_RALLY_FOLDER/config.ini
```

`build.py` uses the setup's single WinLibs UCRT GCC for all three products.
It needs only standard-library Python and pinned source caches; it invokes no
download, Git, CMake or Visual Studio. Independent C files build in parallel;
content-hashed sources, included headers, compiler and objects govern reuse.
Binaries and third-party licenses land in `build/native`. No game data is
required to build. See [BUILD.md](BUILD.md) for flags, source pins and tests.
The importer currently accepts single-controller XInput profiles and rejects
unsupported active options or bindings. It reads the source XML/INI without
changing either. Importing over existing YAML first creates `.yaml.before-import`.

Overlay mode defaults to independent copies. `--mode hardlink` and `--mode junction`
share asset directories, so run `overlay.py --materialize DESTINATION` before
editing those assets. Root executables/configs are always private copies.
The source executable must match the supported SHA-256 in `overlay.py`.
Existing destinations and source reparse points are rejected.

For the existing SR3CamLab mod stack, `play.ps1 -GameFolder OVERLAY -WithMods`
passes its owned PID and settings to the shared `sr3mods.exe` live patcher.
An optional `-SettingsPath FULL_PATH_TO_YAML` selects settings outside the overlay.
It propagates patcher failure and refuses an adjacent sr3mods.dll, preventing
both patch routes from attaching to one game. `-NoWatchdog` suppresses automatic
recording; `-Watchdog` starts the recorder before the game runs its first code.
The regression `test_play.ps1 -StubExe PATH_TO_TEST_PLAY_STUB` uses a native
argument-recording stub, never the game. See WATCHDOG-PROPOSAL.md for the three
watchdog entry points and the host lifecycle evidence.
The runtime can instead load an adjacent `sr3mods.dll` after game window creation.
`patches.enabled` is `auto` by default (absent means no mods), `on` requires it,
and `off` disables it. A present plugin that fails initialization stops startup
with its error; see `sr3mods.log`. The two patching paths must not run together.
The companion preserves the agreed `patches` scalar options when saving, and
omits controller bindings that equal the defaults.

## Validation and limits

Native tests cover input reports, the entire signed steering range, imported
gear directions/thresholds, YAML round trips and invalid input. Python tests cover
the importer and copy/hardlink/junction independence/materialization. The original
raylib UI has been rendered and visually inspected; its new watchdog controls
have been built but still need visual review. A private native-launch test
created the fullscreen 4K device and captured a visible 3840x2160 boot frame
through the runtime's screenshot bridge. A complete modded race and physical
DualSense controls still need validation on this build; the boot frame does not
prove those. See INVESTIGATION.md for evidence and current integration limits.
The runtime logs configuration, controller connection and D3D creation results
in the private game's `sr3lab.log`.

No changes are made to `Rally.exe` on disk. This build supports the inspected
3.8.4.1 executable only; see `INVESTIGATION.md`. It does not claim support for
every cabinet dump or unknown modified executable. CamLab's source and executable
are independent of this component and are not rebuilt by these scripts.


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
