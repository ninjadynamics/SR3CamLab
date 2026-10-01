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
| `build_cycle.py` | The camera-cycle block: camera list, name popup, debug-camera controls, PVS switch, driver's-seat cockpit, stage-reset fix. Position-independent x86 assembled with keystone. Writes `cycle.json`. The data layout and the game facts it relies on are documented at the top of the file. |
| `embed.py` | Copies `cycle.json` into `../patch.ps1` (`$CycleCode` and the entry offsets). |

The workflow after changing `build_cycle.py`:

```
python build_cycle.py
python cycle_emu.py                                            (check the results)
python embed.py
powershell -ExecutionPolicy Bypass -File cycle_mocktest.ps1
```

Then try it on the running game with
`patch.ps1 -NoLaunch -DelaySeconds 0`. A changed block is installed alongside the old one,
never over it.

## Tests

| Script | What it does |
|---|---|
| `cycle_emu.py` | Runs the camera-cycle block on an emulated CPU (Unicorn) against a fake game (camera manager, cars' camera data, D3DX and Win32 stubs). It steps through View Change, the popup, the steerable cameras, the limits and stage resets, and prints each result next to the expected one. |
| `cycle_mocktest.ps1` | Runs `patch.ps1`'s install, update and remove functions against fake process memory. It checks the hooks, the data written, moving to a new block, and that removing restores everything. |

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
