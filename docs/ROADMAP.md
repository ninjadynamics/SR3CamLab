# SR3Lab roadmap

The owner's roadmap (2026-10-15), in their words where it matters, with notes on what exists and what each item means for the
code. Every component is standalone and plays nicely with the others, "like lego pieces".

## A. SEGA Rally 3 without TeknoParrot

Free SR3 from TeknoParrot by patching the executable; **side-loading a .dll that the game calls is fine, even preferable**.
(An example of a TeknoParrot-free arcade PC game: Daytona USA Championship, which the owner has.)

- Side-loading (a DLL the game loads by itself, e.g. one it already imports, placed beside Rally.exe) keeps Rally.exe
  unmodified on disk, as every patch so far has kept it.
- To find out first: what TeknoParrot's loader does for SR3 (the arcade I/O and inputs, the platform checks, window /
  resolution), so the DLL can do the same. Only our own code goes in; nothing of SEGA's is copied or shipped.
- The game folder can then be set up as an overlay of a vanilla install (copies, hard links or junctions, the user's choice:
  `C:\Games\TeknoParrot\...` untouched, the mod in its own folder, e.g. `C:\Games\UltraRally`, name not decided).

## B. Patches on the TeknoParrot-free game

In-memory patching (as patch.ps1 does today) or more side-loaded DLLs, on the TeknoParrot-free version.

## C. Quality-of-life improvements

1. New camera options: CamLab (exists).
2. Import tracks from SEGA Rally Championship, SEGA Rally 2, Daytona USA, Daytona USA 2 and Scud Race (SRC Mountain: done, the
   import stack; Daytona USA course export: started; the rest to do).
3. Import cars from those games (Daytona's Hornet: started).
4. Import audio from those games (SRC co-driver and music, SR2 samples: exist in tools\audio).
5. Import gameplay settings from those games, limited (SRC handling flavor and the SRC turning port; checkpoint times).
6. Support for HD textures (textures_hd: exists).

## D. 100% transparent

1. Python scripts and C source code / makefiles alongside the executables; ideally the bundled Python also contains a C
   compiler.
2. Intermediate files on demand: Blender files, WAVs, PNGs and the like (the stack's .blend per step: exists).
3. **The user is never forced to run a single bundled executable or binary.** "Hey, here's Python and a C compiler: you
   don't need to download anything or an internet connection at all (just click next and we'll set everything up for you
   automagically), but if you insist, we provide that option too - winget will fetch the necessary tools instead."
   - **The only binaries the mod includes are Python and a C compiler, in one zip.** Using it is optional, and it is safe to
     delete when the user picks the winget option. Everything else (the C helpers' DLLs, CamLab's exe, the machine code
     patch.ps1 writes into the game) is built on the user's PC from the shipped sources.
   - Default: setup unpacks the toolchain zip (Python with numpy and Pillow, MinGW-w64 gcc) into the mod folder, offline.
     Option: winget installs Python and WinLibs gcc, and pip the pinned numpy / Pillow.
   - Status (2026-10-15): the import stack works this way (tools\release.py makes both zips; tools\setup_toolchain.ps1).
     Not yet: patch.ps1 still carries its machine code as hex made on the author's PC (the sources and their build scripts,
     tools\build_*.py, ship; they need keystone and clang, which the toolchain zip does not have yet), and camlab.exe is built
     with the author's raylib setup (src\).
   - Builds must stay byte-identical across PCs: the C helpers are compiled for one fixed target (x86-64-v3) rather than
     each PC's own, and the Python packages are pinned to the versions the builds were checked with. winget's oldest WinLibs
     is gcc 14.2 (the zip's is 13.2): that the winget compiler gives the same bytes is still to be shown.

## F. 100% legal

No SEGA assets or code, except "where our pieces fit": coordinates for 3D, audio, video, textures and code (addresses, offsets,
hooks). Partial data may bend this rule a little, but 1. it should not be necessary, and 2. if it is, keep it to the bare
minimum. (Earlier rule, still standing: a whole track, modified or not, is never shipped.)

## Where things are

- The import stack: `tools\import\` (README there), `IMPORT.bat`; knowledge base `docs\kb\` (30 = the stack).
- The launcher and the in-memory patches: `PLAY.bat`, `patch.ps1`; the settings app: `SR3Ultimate.bat` / `extras.ps1`; CamLab:
  `src\`, `camlab.exe`; the SR3Lab app plan: `docs\SR3Lab-plan.md`.
