# tools

The sources of the in-game patch and the scripts used to investigate SEGA Rally 3 while
building it. You don't need any of this to play; it's here so you can rebuild, extend or
check the patch. [FINDINGS.md](../FINDINGS.md) explains what they found.

**Requirements:** Python 3 with `keystone-engine`, `capstone` and `unicorn`
(`pip install keystone-engine capstone unicorn`), and Windows PowerShell 5.1. The scripts
that read the exe need `SR3_EXE` set to your `Rally.exe` (v3.8.4.1):

```
set SR3_EXE=C:\TeknoParrot\GAME\Sega Rally 3\Rally\Rally.exe
```

## Building the patch

`patch.ps1` carries two pieces of machine code as hex. These scripts generate them:

| Script | Builds |
|---|---|
| `build_patch.py` | The chase camera patch: the code cave at `0x673C80` (travel follow, spring constants, soft angle limit, framing) and the hooks into SR3's chase camera. Writes `patch.json`; `patch.ps1`'s `$Patches` table holds those bytes (the cave's tunables are filled in per profile at run time). Needs `SR3_EXE`. |
| `build_cycle.py` | The camera-cycle block: camera list, name popup, debug-camera controls and their mouse / key smoothing, the blend between cameras on View Change, PVS switch, driver's-seat cockpit, stage-reset fix. Position-independent x86 assembled with keystone, in two code areas of the block (`0x1000` and `0x2800`). Writes `cycle.json`. The data layout and the game facts it relies on are documented at the top of the file. |
| `embed.py` | Copies `cycle.json` into `../patch.ps1` (`$CycleCode`, `$CycleCode2` and the entry offsets). |

The workflow after changing `build_cycle.py`:

```
python build_cycle.py
python cycle_emu.py                                            (check the results; the last line counts the new checks)
python cycle_real.py                                           (needs SR3_EXE; the last line counts)
python embed.py
powershell -ExecutionPolicy Bypass -File cycle_mocktest.ps1
powershell -ExecutionPolicy Bypass -File settings_mocktest.ps1
```

Then try it on the running game with
`patch.ps1 -NoLaunch -DelaySeconds 0`. A changed block is installed alongside the old one,
never over it.

## Tests

| Script | What it does |
|---|---|
| `cycle_emu.py` | Runs the camera-cycle block on an emulated CPU (Unicorn) against a fake game (camera manager, cars' camera data, D3DX and Win32 stubs). It steps through View Change, the popup, the steerable cameras, the limits and stage resets, and prints each result next to the expected one. Then, under "NEW CHECKS", the smoothing (raw at 0, the time constant at several update rates, ending on the raw target, keys, limits) and the blend (starts on the old view, the eased path, ends on the new camera to the bit, real-time duration, cuts of the game's own, what it must not trip over), each with an `ok` / `FAILED` and a count on the last line. |
| `cycle_real.py` | The same block against the game's own code: `Rally.exe` is loaded into the emulated CPU (read only, needs `SR3_EXE`). The blend's hook runs around the real `0x5F1690` and the real camera interpolation, and the view is read back through the game's accessors; the update wrappers run into the real free cam and car rotate updates. Checks what `cycle_emu.py`'s fake game takes on trust. |
| `cycle_mocktest.ps1` | Runs `patch.ps1`'s install, update and remove functions against fake process memory. It checks the hooks (the blend's too, and that it is left out when its site holds other bytes), the data written, moving to a new block, and that removing restores everything. |
| `settings_mocktest.ps1` | Runs `patch.ps1`'s reading of `mouseSmoothing` and `cameraBlend` on made-up profile files: defaults, 0 and `off`, limits, the switches, and a Launch file without the keys. Counts on the last line. |
| `sound_copytest.ps1` | Runs the settings app's co-driver and music switching (`extras.ps1`) on a copy of the game's sound files, never on the game. Every voice goes in and out and the replaced streams must hold exactly their WAV files; the tunes are appended and SEGA's part of the file must not change by a byte, only the 1995 courses of the Classic mode may get a tune in `switch.json`, and taking them out must leave the file as it was; at the end the copy must be byte-identical to the game's own file with the same kept originals. Needs about 500 MB for the copy (`-Work <folder>` to choose where; deleted afterwards unless `-Keep`). |
| `start_mocktest.ps1` | Runs `patch.ps1`'s START logic without a game: a short press saves a screenshot when START is let go, a long one (1.2 s) leaves the race, a press seen during the menus does nothing, pictures stay 2 s apart, a picture is dropped when the menus come up. Then the race exit against a fake game memory: the flag and the fade written as the game writes them, the Championship's stage number and leader position, the refusals (attract demo, loading, results, pause), and the safety nets (a request the game does not take is withdrawn, a stuck fade is let go). Counts on the last line. |
| `watchdog_test.ps1` | Runs `watchdog.cs` against two small 32-bit stand-in programs it builds with Visual Studio's C compiler (never the game): a handled and an unhandled access violation, a message loop stuck for 8 s, a box built like a MessageBox (off screen and transparent), detaching with `Stop()`, the watchdog's own process killed while attached (the program must run on), and a second watchdog that cannot attach. `-Work <folder>` for the build and the logs, `-Keep` to keep them. Counts on the last line. |
| `tune_mocktest.ps1` | Runs `patch.ps1`'s switcher against a scripted fake game to check a track's own tune: the stream record of the Classic mode's music must point at the tune only while a track that has one is the chosen one, hold SEGA's values at every other moment, and no other record may change. |

## Live readers (the game must be running)

All read-only, except `pvs.ps1 -Set`.

| Script | Shows |
|---|---|
| `probe.ps1` | The chase camera's eye, car point, look-at, pitch and FOV, plus the cave settings. `-Shot file.png` also saves a screenshot. |
| `carpoint.ps1` | Where the camera's car point and eye sit in the car's own frame (`car+0x135C`). |
| `viewmat.ps1` | Finds the chase camera and the final camera-to-world matrices whose eye matches it (slow: scans memory). |
| `looklog.ps1` | Logs the chase camera's framing against speed to `looklog.csv`. |
| `shotloop.ps1` | A screenshot plus camera state every few seconds, into `shots/`. |
| `vtcheck.ps1` | Which block the frame hook points at, and whether the camera vtable entries use it. |
| `pvs.ps1` | The visibility (PVS) state; `-Set 1` / `-Set 0` turns the "draw everything" switch on or off. |
| `vslots.ps1` | The game's 20 video slots: file, graph and interface pointers. |
| `threads.ps1` | Groups the game's threads by start address and module, and lists its windows. Run it with the 32-bit PowerShell (`C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`) to see module names. |
| `memlog.ps1` | Logs memory use, the largest free address block, the PVS flag and the thread count every 2 s to `memlog.csv` (waits for the game). |

## Other

| Script | |
|---|---|
| `sr3.py` | Loads `Rally.exe` and offers disassembly (`dis(va, n)`), reads (`rd`, `u32`, `f32`) and string search. Used by `build_patch.py`. |
| `wmvtest.ps1` | Measures what one DirectShow WMV graph costs (threads, memory) with a given number of CPUs: `wmvtest.ps1 -File <a game .wmv> -Cores 4`. Run it with the 32-bit PowerShell and `-STA`. |
