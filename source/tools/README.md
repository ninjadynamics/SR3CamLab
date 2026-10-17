# tools

The sources of the in-game patch and the scripts used to investigate SEGA Rally 3 while
building it. You don't need any of this to play; it's here so you can rebuild, extend or
check the patch. [FINDINGS.md](../FINDINGS.md) explains what they found.

The subfolders are the other tool sets: [`import\`](import/README.md) (other games' courses and cars into
SEGA Rally 3, from your own ROM sets), `audio\` (co-driver, music and sound banks) and `handling\` (the
handling flavors).

**Requirements:** Python 3 with `keystone-engine`, `capstone` and `unicorn`
(`pip install keystone-engine capstone unicorn`), and Windows PowerShell 5.1. The scripts
that read the exe need `SR3_EXE` set to your `Rally.exe` (v3.8.4.1):

```
set SR3_EXE=C:\TeknoParrot\GAME\Sega Rally 3\Rally\Rally.exe
```

## Building the patch

`sr3mods.ps1` carries two pieces of machine code as hex. These scripts generate them:

| Script | Builds |
|---|---|
| `build_patch.py` | The chase camera patch: the code cave at `0x673C80` (travel follow, spring constants, soft angle limit, framing) and the hooks into SR3's chase camera. Writes `patch.json`; `sr3mods.ps1`'s `$Patches` table holds those bytes (the cave's tunables are filled in per profile at run time). Needs `SR3_EXE`. |
| `build_cycle.py` | The camera-cycle block: camera list, name popup, debug-camera controls and their mouse / key smoothing, the blend between cameras on View Change, PVS switch, driver's-seat cockpit, stage-reset fix. Position-independent x86 assembled with keystone, in two code areas of the block (`0x1000` and `0x2800`). Writes `cycle.json`. The data layout and the game facts it relies on are documented at the top of the file. |
| `embed.py` | Copies `cycle.json` into `../sr3mods.ps1` (`$CycleCode`, `$CycleCode2` and the entry offsets). |
| `build_srcport.py` | The SRC turning (SEGA Rally Championship's turning for the cars on the SRC handling, `docs\kb\29_src_steering_code.md` section 12): compiles `srcport.c` with clang (i686, freestanding; `C:\mingw64\bin`), lays it out as one relocatable blob, classes the grip file's surface records for SRC's four records, writes `srcport.json`; `--embed` writes `$SrcPortCode`, the offsets and the relocation list into `../sr3mods.ps1`. Needs SEGA's `SurfacePairEffects\surfacepairdata_xdata.sbf` (`--game`). `srcmodel.py` is kb 29's chain in Python, the reference the tests compare with. |

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
`sr3mods.ps1 -NoLaunch -DelaySeconds 0`. A changed block is installed alongside the old one,
never over it.

## 32-bit builds (`x86\`)

Rally.exe is 32-bit; the DLLs that go into it (sr3mods.dll, the TeknoParrot-free runtime) are built with the same 64-bit
gcc the toolchain ships, as `gcc -m32 -nostdlib -nostartfiles`. That gcc has no 32-bit libraries, so these supply the rest:

| File | What it is |
|---|---|
| `x86\implib.py` | Import libraries made from what the objects call. `python implib.py --out DIR [--dll kernel32 --dll ucrtbase ...] OBJECTS_OR_LIBS...`: every symbol the inputs use and none defines is looked up, by name only, in Windows' own 32-bit DLLs (SysWOW64; nothing copied), first match in the `--dll` order (default: kernel32, user32, gdi32, winmm, ole32, oleaut32, setupapi, shell32, advapi32, imm32, version, cfgmgr32, hid, ucrtbase). Writes `DIR\<dll>.def` (sorted), `DIR\lib<dll>.a` (binutils' dlltool, deterministic) and `DIR\imports.json`; the same files in any folder. A symbol no DLL exports stops it (exit 2) with the list. |
| `x86\builtins.c` | The helpers gcc's 32-bit code calls in place of libgcc: 64-bit divide and remainder (`___udivdi3 ___umoddi3 ___udivmoddi4 ___divdi3 ___moddi3 ___divmoddi4`), 64-bit bit counts and the stack probe `___chkstk_ms`. `gcc -m32 -O2 -c builtins.c`, then link `builtins.o`. |
| `x86\test_builtins.py` | Builds a 32-bit test program with the two above and runs it: about 60,000 division vectors against Python's exact integers (boundaries, high-bit divisors, signed minimums, random), the bit counts, stack frames of 4 KB to 3 MB in a thread with only reserved stack, registers kept across the probe; a negative control (probes off) that must crash; implib.py's output compared across two folders. `RESULT: PASS` on the last line. |

A link: `gcc -m32 -nostdlib -nostartfiles -shared -Wl,-e,_DllMain@12 -Wl,--kill-at OBJECTS builtins.o -LDIR -lkernel32 ...`.

## Tests

| Script | What it does |
|---|---|
| `cycle_emu.py` | Runs the camera-cycle block on an emulated CPU (Unicorn) against a fake game (camera manager, cars' camera data, D3DX and Win32 stubs). It steps through View Change, the popup, the steerable cameras, the limits and stage resets, and prints each result next to the expected one. Then, under "NEW CHECKS", the smoothing (raw at 0, the time constant at several update rates, ending on the raw target, keys, limits) and the blend (starts on the old view, the eased path, ends on the new camera to the bit, real-time duration, cuts of the game's own, what it must not trip over), each with an `ok` / `FAILED` and a count on the last line. |
| `cycle_real.py` | The same block against the game's own code: `Rally.exe` is loaded into the emulated CPU (read only, needs `SR3_EXE`). The blend's hook runs around the real `0x5F1690` and the real camera interpolation, and the view is read back through the game's accessors; the update wrappers run into the real free cam and car rotate updates. Checks what `cycle_emu.py`'s fake game takes on trust. |
| `cycle_mocktest.ps1` | Runs `sr3mods.ps1`'s install, update and remove functions against fake process memory. It checks the hooks (the blend's too, and that it is left out when its site holds other bytes), the data written, moving to a new block, and that removing restores everything. |
| `settings_mocktest.ps1` | Runs `sr3mods.ps1`'s reading of `mouseSmoothing` and `cameraBlend` on made-up profile files: defaults, 0 and `off`, limits, the switches, and a Launch file without the keys. Counts on the last line. |
| `sound_copytest.ps1` | Runs the settings app's co-driver and music switching (`extras.ps1`) on a copy of the game's sound files, never on the game. Every voice goes in and out and the replaced streams must hold exactly their WAV files; the tunes are appended and SEGA's part of the file must not change by a byte, only the 1995 courses of the Classic mode may get a tune in `switch.json`, and taking them out must leave the file as it was; at the end the copy must be byte-identical to the game's own file with the same kept originals. Needs about 500 MB for the copy (`-Work <folder>` to choose where; deleted afterwards unless `-Keep`). |
| `start_mocktest.ps1` | Runs `sr3mods.ps1`'s START / VIEW CHANGE logic without a game: a short START saves a screenshot when it is let go, VIEW CHANGE held 1.2 s leaves the race (and the camera that hold stepped to is put back), a press seen during the menus does nothing, pictures stay 2 s apart, a picture is dropped when the menus come up. Then the race exit against a fake game memory: the flag and the fade written as the game writes them, the Championship's stage number and leader position, the refusals (attract demo, loading, results, pause), and the safety nets (a request the game does not take is withdrawn, a stuck fade is let go). Counts on the last line. |
| `watchdog_test.ps1` | Runs `watchdog.cs` against two small 32-bit stand-in programs it builds with Visual Studio's C compiler (never the game): a handled and an unhandled access violation, a message loop stuck for 8 s, a box built like a MessageBox (off screen and transparent), detaching with `Stop()`, the watchdog's own process killed while attached (the program must run on), and a second watchdog that cannot attach. `-Work <folder>` for the build and the logs, `-Keep` to keep them. Counts on the last line. |
| `srcport_emu.py` | Runs the SRC turning blob, relocated as `sr3mods.ps1` does it, inside an emulated copy of `Rally.exe` on a made-up car (the game's own SetVelocity / SetAngularVelocity, the vehicle step replaced by a stub). Checks it against `srcmodel.py` frame by frame (axle centres, one SRC frame per step: the same numbers), kb 29's steady turns and turn-in with SR3's 1/60 s steps, the turning direction, and what it must leave alone (SR3 / Realism files, the air, SR3's hit recovery, computer cars unless asked, modes 0 / 1), that SR3's own turning inside the step is thrown away and its change of speed kept. Counts on the last line. |
| `srcport_mocktest.ps1` | Runs `sr3mods.ps1`'s `Install-SrcPort` / `Remove-SrcPort` on fake process memory: the vtable entry, every relocation, a second PLAY.bat (kept), an older version (replaced), removing, a foreign hook left alone. |
| `tune_mocktest.ps1` | Runs `sr3mods.ps1`'s switcher against a scripted fake game to check a track's own tune: the stream record of the Classic mode's music must point at the tune only while a track that has one is the chosen one, hold SEGA's values at every other moment, and no other record may change. |

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
