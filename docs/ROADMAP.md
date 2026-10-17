# Current workspace decisions (2026-10-17)

The root is now the Git repository: `source`, `docs`, `apps/camlab`, `toolchain`, local `game/content/config`, important `work`, disposable `scratchpad`, and preserved `screenshots`. This supersedes the earlier nested `repo/assets/backups` migration notes below. No directory links are required.

- [x] Root SETUP.bat creates local folders/configuration and builds the runtime, launcher, Race Settings, mods, and importer helpers; preserves existing assets and settings.
- [x] Race Settings Save & play uses the shared handling-aware launch flow; watchdog OFF.
- [x] Retain the existing CamLab binary and its launch behavior under apps/camlab.
- [ ] Build CamLab from source during setup ? explicitly deferred by Bruno.
- [ ] Add **Extract textures** in Race Settings ? TODO only; do not implement in this reorganization.
- [ ] Add **Update textures** in Race Settings ? TODO only; the convenience script stays under source/tools/workspace, not at root.
- [ ] Update and validate the release ZIP/toolchain packager for this layout on a clean Windows system. The old packager targets the earlier tree.
- [ ] Apply CamLab's UI/UX consistently to the remaining suite apps. TexLab remains an idea.

`work` contains important authoring/recovery/reference data and must never be cache-cleaned. `scratchpad` is disposable. The Blender files are in `work/blender`.

## Earlier planning notes (superseded where they conflict)

# Ultimate Race Lab roadmap

## Workspace migration completed (2026-10-17)

The development workspace is now `F:/Jogos/Ultimate Race Lab`. Public code/KB live in `repo`; local game, editable assets, reference inputs, work files, screenshots and backups live outside that Git root. See [WORKSPACE.md](WORKSPACE.md) for entry points, actual folders and remaining limitations. All 37,801 inventoried files matched SHA256 after 34 directory moves, before path updates. Old paths are temporary junctions for Blender references and historical scripts.

This completes the filesystem migration. Internal C/application source reorganization, the SETUP.bat release workflow, CamLab setup compilation and integration of the accepted handling helper into the settings app's own Launch button remain separate work. Use the workspace PLAY.bat for accepted handling, watchdog OFF.

## Current owner decisions (2026-10-17)

These decisions supersede older suite/app names and app-status descriptions below.

- Suite: **Ultimate Race Lab**, a collection of SEGA Rally 3 mods that work together as independent, interoperable pieces ("like lego pieces").
- Settings app: **Race Settings**, executable **settings.exe**.
- **CamLab is fully completed** and is the UI/UX reference for every app in the suite.
- **TexLab remains an idea**, not an implemented or completed application.
- All suite applications must follow CamLab's UI/UX.
- These are product and refactoring decisions; this documentation update does not rename deployed folders, executables, or the remote repository.


## Local screenshots (owner decision, 2026-10-17)

Screenshots belong in `<workspace>/screenshots/`, alongside `game/`, `assets/` and `repo/`, outside both the game installation and the public Git repository. The intended example is `F:/Jogos/Ultimate Race Lab/screenshots/`. Treat these as user files: preserve them during updates and cache cleanup.

- [x] Move existing screenshots and sidecars to the local workspace. Native and PowerShell capture code already uses the parent of the mod folder; with `patches.mod_folder: repo`, captures resolve to the workspace `screenshots/` (case-insensitive on Windows). No runtime rebuild was required. An explicit configurable capture path remains a future improvement.

## Installation decision and deferred CamLab build (2026-10-17)

End users start with `SETUP.bat`. The bundled Python and compilers build Race Settings (`settings.exe`), the standalone runtime and mod components locally. A prebuilt settings app is not the installation entry point. This is the target installation workflow, not a claim that setup migration is complete.

- [ ] Integrate CamLab source compilation into `SETUP.bat` using the bundled toolchain. **Deferred TODO**, explicitly requested by the owner; do not implement as part of the current reorganization. Preserve CamLab's accepted behavior and UI/UX.

For now, retain the existing prebuilt `camlab.exe` exception. The long-term goal is to build the whole suite locally; this exception ends only when CamLab's setup build is implemented and validated.


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

In-memory patching (as sr3mods.ps1 does today) or more side-loaded DLLs, on the TeknoParrot-free version.

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
     delete when the user picks the winget option. Everything else (the C helpers' DLLs, the machine code sr3mods.ps1
     writes into the game) is built on the user's PC from the shipped sources.
   - **The exception: CamLab** (`camlab.exe`) stays a shipped binary, as it is now, and CamLab is not to be changed (owner,
     2026-10-15).
   - Default: setup unpacks the toolchain zip (Python with numpy and Pillow, MinGW-w64 gcc) into the mod folder, offline.
     Option: everything obtainable via winget with curl fallbacks (owner, 2026-10-15): winget installs Python and WinLibs gcc
     + clang, pip the pinned numpy / Pillow; where winget is missing or fails, curl fetches python.org's embeddable Python,
     the wheels from PyPI and WinLibs' exact gcc 13.2.0 + LLVM 17.0.6 build from its GitHub releases (setup_toolchain.ps1
     -Online). Pinned versions, SHA-256 checked.
   - 32-bit code (Rally.exe is 32-bit): the planned sr3mods.dll, which carries the in-memory patches, and the
     TeknoParrot-free runtime (Codex's, `standalone\`) are built with WinLibs' i686 gcc 13.2.0 (same release and C runtime
     as the 64-bit one; winget has no 32-bit WinLibs, so it comes by curl from WinLibs' GitHub release). The runtime starts
     sr3mods.dll through `int __cdecl sr3mods_start(const char *utf8_settings_path)` after its own executable check, outside
     the loader lock; sr3mods.dll's own thread waits for the game's data like sr3mods.ps1 does (agreed with Codex,
     2026-10-15). Shown earlier the same day: clang + lld also build a working 32-bit DLL (kept as a fallback).
   - Names (Bruno, 2026-10-15, unified: "descriptive and Windows doesn't bitch about it"): one name per family, the same for
     the .dll, the .exe and the .ps1 that mirror each other. The mods: sr3mods.dll (inside the game), sr3mods.exe (from
     outside), sr3mods.ps1 (the PowerShell mirror and PLAY.bat's launcher; patches.ps1 / patches.dll that morning, patch.ps1
     before), sources in tools\sr3mods. The watchdog: watchdog.exe (its host), watchdog.ps1, watchdog.cs (the recorder). No
     "patch" in an exe name: Windows takes an unmanifested 32-bit exe called so for an installer and asks for admin rights.
     patch.ps1 stays as a forwarder because CamLab, which is not changed, looks for it.
   - Status (2026-10-15): the import stack works this way (tools\release.py makes both zips; tools\setup_toolchain.ps1).
     Not yet: sr3mods.ps1 still carries its machine code as hex made on the author's PC (the sources and their build scripts,
     tools\build_*.py, ship; they need keystone and clang, which the toolchain zip does not have yet).
   - Builds must stay byte-identical across PCs: the C helpers are compiled for one fixed target (x86-64-v3) rather than
     each PC's own, and the Python packages are pinned to the versions the builds were checked with. winget's oldest WinLibs
     is gcc 14.2 (the zip's is 13.2): shown 2026-10-15 to give the same bytes (the whole chain = v15).

## F. 100% legal

No SEGA assets or code, except "where our pieces fit": coordinates for 3D, audio, video, textures and code (addresses, offsets,
hooks). Partial data may bend this rule a little, but 1. it should not be necessary, and 2. if it is, keep it to the bare
minimum. (Earlier rule, still standing: a whole track, modified or not, is never shipped.)

The toolchain zip's GPL parts (owner, 2026-10-15: "regarding the GPL stuff, we provide only links"): the zip carries the
licences (GPL v3, the GCC Runtime Library Exception, LGPL 2.1 and 3, from `tools\licenses`) and SOURCES.txt, which names
every component, its version and licence and links to its unchanged upstream source archive, plus WinLibs' build recipes
at the commit r5 was built from (GPL v3 section 6d allows the source on a third-party server with clear directions next to
the object code). We stay responsible for those links while the zip is offered, so `tools\release.py` checks that every
one still answers before it makes a release (HEAD requests; nothing is downloaded). Python, numpy and Pillow need only
their licences, which they carry.

## Where things are

- The import stack: `tools\import\` (README there), `IMPORT.bat`; knowledge base `docs\kb\` (30 = the stack).
- The launcher and the in-memory patches: `PLAY.bat`, `sr3mods.ps1`; the settings app: `SR3Ultimate.bat` / `extras.ps1`; CamLab:
  `src\`, `camlab.exe`; the SR3Lab app plan: `docs\SR3Lab-plan.md`.
