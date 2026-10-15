# External watchdog host

Implemented following owner chat #102 and #110-117: one external recorder,
three entry points, automatic startup **on by default**. The game modifications
remain in sr3mods.dll (or the same core in sr3mods.exe for the external route).

`watchdog.exe` hosts `watchdog.ps1` in an in-process Windows PowerShell runspace.
The same script runs unchanged under 64-bit Windows PowerShell when invoked
directly. Both use `../watchdog.cs`. `watch_process.cs` only supplies
process creation and identity checks; it does not implement another recorder.
The host parses FreezeSeconds, GameWindowVA and WatchdogValues as literal AST
values from sr3mods.ps1, without executing that script.

- `launch.exe --watchdog`, the settings app's **Start with watchdog**, or
  `play.ps1 -GameFolder OVERLAY -Watchdog`: the host creates the target suspended,
  attaches the debugger, then resumes it. This covers crashes at game entry.
- `patches.watchdog: on` (also the omitted default): sr3mods.dll or sr3mods
  starts the host after camera installation. The native launcher starts it
  earlier when launching the game itself. A process-identity mutex prevents a
  second recorder. The TeknoParrot route keeps its existing attach delay.
- Ctrl+Scroll Lock while the modded game is in front requests the same host.
  Auto startup may be disabled without removing this manual control.

Set `patches.mod_folder` to the absolute SR3CamLab folder. That folder must
contain watchdog.cs, sr3mods.ps1 and standalone/watchdog.exe, watchdog.ps1
and watch_process.cs.
The native launcher's `--no-watchdog` overrides auto startup for that launch;
`sr3mods attach --no-watchdog` suppresses its auto startup. `--no-live` reattach
starts neither another live loop nor another recorder.

`watch_launcher.c/.h` is shared by the DLL, external patcher, launcher and
settings app. It launches the hidden 64-bit `standalone/watchdog.exe`, including from a
32-bit caller. There is no powershell.exe child. Output goes to `crash/watch-host-*.log`, not a pipe, so the
recorder can finish after the game/DLL exits. Only its output and NUL input
handles are inherited. Native polling forwards host messages into the patch
log; exit drains briefly without killing a still-finishing recorder.

Attach mode requires the exact PID, executable path and creation FILETIME.
The host retains the target handle, checks identity before and after compiling,
and holds a per-identity mutex. Launch mode uses the same recorder and identity
check, creates a suspended process, and resumes only after Attached is true.
A setup failure disposes its own never-resumed child. Once resumed, closing
the helper leaves the target alive (the existing recorder disables debugger
kill-on-exit). Launch mode's optional ReadyFile publishes identity atomically
for play.ps1 before resuming. Logs and minidumps remain in the crash directory.

Validation (owned stand-ins, no Rally):

- Host lifecycle: identity refusal, duplicate refusal, helper termination leaves
  target alive, normal exit, deliberate exception/minidump, hidden-window freeze
  with three samples/minidump/recovery. `watch-host-test-4`: all pass.
- Native x86 caller to x64 host: idempotent start, attachment and output polling,
  clean shutdown. `watch-native-test-1`: pass.
- Suspended launch: debugger present at entry, immediate exception recorded and
  dumped. `watch-launch-test-2` and `watch-native-launch-test-1`: pass.
- Front build: 17/17 camera settings and 11/11 live/reattach lockstep cases pass.
- play.ps1: exact owned PID/settings/profile, watchdog override, failure code,
  handle disposal, environment restoration and duplicate-patcher refusal pass.

Evidence directories are under ../../SR3-investigation. These tests do not
replace validation of a complete modded race or the new UI controls in-game.

Unified-name verification: the native suites passed with adjacent sr3mods.dll
and sr3mods_start. watchdog.exe lifecycle tests repeat the identity, duplicate,
detach, crash and freeze tests under watchdog-exe-test-1. The native x86 caller also verified
an immediate-entry crash through watchdog.exe in watchdog-native-launch-test-1.
The executable is built from watchdog_host.cs with Windows' installed x64 .NET
Framework compiler and references its installed PowerShell assembly. The GCC
runtime/launcher toolchain remains unchanged. This host is cached by source and
compiler/assembly hashes; the legacy C# compiler does not promise reproducible
bytes on a clean rebuild.
