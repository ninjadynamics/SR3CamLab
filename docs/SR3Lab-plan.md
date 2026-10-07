# SR3Lab - restructuring plan

Status: PLAN ONLY. Nothing here is implemented. Written 2026-10-07 from the user's brief.

## The brief (user's words)

> "we could give camlab and texlab each their sub directories and call the settings app SR3Lab. Furthermore it should be
> an .exe with the same ui, look and feel as camlab (made with raylib). SR3Lab is the anchor of the whole mod suite. To
> avoid confusion, we call the suite and rename the directory to SR3Lab as well. SR3Lab is tidy and user friendly. Helps
> you find your copy of Revo (PC or PS3) and Model 2 and 3 rom sets. We can add another subdirectory called scripts and
> it would be nice if they were standalone instead of asking the users to install Python or Blender or whatever. Outputs
> should be byte identical to what we have now. Save this as a plan, don't implement now."

Also on record from the same day:
- "the tracks should be toggleable, at least in UI."
- TexLab answers: second exe is fine; public release; SR3 atlas pieces; "send to game" also installs.
- Earlier standing rules that still hold: `PLAY.bat` keeps its name and stays the transparent launcher; `Rally.exe` is
  never modified on disk; no SEGA data is shipped; originals are always restorable.

## Names

This replaces the earlier naming (suite "UltimateSR3", app "SR3Ultimate").

| Thing | Old name | New name |
|---|---|---|
| Suite, folder, GitHub repo | SR3CamLab (planned: UltimateSR3) | **SR3Lab** |
| Settings app | SR3Ultimate (`extras.ps1`, `SR3Ultimate.bat`) | **SR3Lab** (`SR3Lab.exe`) |
| Camera tuner | CamLab (`camlab.exe`) | CamLab, in `camlab\` |
| Texture authoring | TexLab (planned) | TexLab, in `texlab\` |
| Game launcher | `PLAY.bat` | `PLAY.bat` (unchanged) |

## Target layout

```
SR3Lab\
  SR3Lab.exe            the anchor: settings, sources, tracks on / off, launch buttons
  PLAY.bat              starts the game with every in-memory mod (runs scripts\patch.ps1)
  README.md
  camlab\               camlab.exe, profiles.yaml, defaults.yaml
  texlab\               texlab.exe, projects\
  scripts\              everything that does work without a window:
                          patch.ps1, setup.ps1             (launcher, in-memory patches)
                          the importer, converters, audio tools (see "Standalone scripts")
  src\                  C sources of the three programs, shared ui code, build.bat
  docs\                 plans and user documentation
  tools\                developer tools (not needed by users)
```

Decisions inside this layout that need the user's word are listed under "Open questions".

## SR3Lab.exe (the anchor)

Built like CamLab: C99 + raylib, statically linked, source in the repo, exe published as a release download. Same
colours, fonts, DPI scaling, rounded panels, tooltips, no modal dialogs. The UI code CamLab already has moves to a shared
`src\ui.h` so the three programs cannot drift apart.

Screens (first version):
1. **Home** - Launch game (runs `PLAY.bat`), Open CamLab, Open TexLab, status of every source and mod at a glance.
2. **Sources** - "helps you find your copy of ...":
   - SEGA Rally 3 arcade + TeknoParrot (what `setup.ps1` finds today);
   - SEGA Rally Revo, PC or PS3 copy;
   - Model 2 ROM set (SEGA Rally Championship, `srallyc`);
   - Model 3 ROM set (SEGA Rally 2, `srally2`).
   Each source: automatic search of the usual places, a browse fallback, and a plain verdict ("found, complete",
   "found, 2 files missing: ...", "not found"). Verification is by file list and checksum, never by trusting a name.
3. **Tracks** - every added track and Classic course with its own on / off switch (the requested toggle), plus
   import / rebuild / remove. Off = stays on disk, left out of the list the launcher reads.
4. **Sound and art** - announcer, co-driver, race sounds, menu art: what `extras.ps1` offers today, each with on / off
   and restore.
5. **Restore** - put every original game file back; shows what would change before doing it.

What SR3Lab.exe does NOT do itself: parse SEGA formats or patch memory. It calls the programs in `scripts\` and shows
their progress and log. That keeps the work scriptable and transparent, and keeps the exe small.

## Standalone scripts

Goal: a user installs nothing - no Python, no Blender.

What exists today and what it needs:

| Piece | Today | Needs to become |
|---|---|---|
| Launcher and in-memory patches | PowerShell (`patch.ps1`, `setup.ps1`) | stays PowerShell: ships with Windows, readable, already standalone |
| Settings app logic | PowerShell + C# compiled at run time (`extras.ps1`, `menuart.cs`, `ps3conv.cs`, `revofix.cs`) | UI moves to `SR3Lab.exe`; the converters become command-line tools in `scripts\` |
| Classic course importer | about 40 Python files using numpy and Pillow, outside the repo (`SR3 track format\work\scripts`) | a standalone tool |
| ROM extraction (Model 2, Model 3) | Python, outside the repo | a standalone tool |
| Audio tools (banks, co-driver, music) | Python + a C# port in progress | a standalone tool |
| Blender | used only for preview renders and flyover videos | NOT needed by users: no build step depends on it |

Two ways to make the Python part standalone:

- **A. Freeze it** (bundle the Python runtime and libraries into one exe per tool). Byte-identical output is almost
  automatic because the same code runs. Cost: a large download (tens of MB), slower start, an opaque exe that some
  antivirus products flag, and the source is still Python.
- **B. Port it** to C (or C#). Small, fast, matches the rest of the suite. Cost: weeks of work, and byte-identical
  output must be proven function by function - floating-point order, DXT texture encoding, zlib level and sorting all
  have to match exactly.

Recommendation: **A first, B later, guarded by the same test.** Freeze to ship; port tool by tool behind a comparison
test, and only switch a tool over when its output is identical.

## Byte-identical outputs

"Outputs should be byte identical to what we have now" becomes a test, not a hope:

1. **Golden set.** For every output we care about, record the SHA-256 of each file: the Mountain track folder
   (9 files), the other imported courses, a converted Revo track, the rebuilt sound banks, the menu-art files,
   the generated terrain file.
2. **One command** rebuilds everything from the sources and compares against the golden set. It runs before every
   release and after every move, rename, freeze or port.
3. **Preconditions to check first** (unknown today):
   - Is the current build deterministic at all? The terrain generator was checked (same hash on two runs); the full
     track build was not. Anything that depends on file order, dictionary order, timestamps or the PC's paths must be
     found and pinned.
   - Does the build depend on files that only exist on this PC (working folders, caches, a label table that the
     scripts edit while they run)? Those must become inputs or generated files.
4. The golden set is refreshed deliberately, with a note saying why, whenever a build change is accepted in game.

## Migration steps (order matters; each step ends with the comparison test)

0. **Freeze a baseline.** Put the importer under version control as it is, record the golden set. Nothing moves before
   this exists.
1. **Rename and restructure** the repo to the target layout; `PLAY.bat` keeps working from the new place; old paths
   in `setup.yaml` and the game's `_SR3Extras` folder are migrated or regenerated.
2. **Shared UI code** out of `camlab.c`; CamLab rebuilt from it, compared by screenshots.
3. **SR3Lab.exe v0**: Home + Sources, read-only (finds and verifies, changes nothing).
4. **Converters as command-line tools**; SR3Lab.exe gains Tracks, Sound and art, Restore; `extras.ps1` retired once
   every function has moved and been compared.
5. **Importer into `scripts\`**, frozen (way A), driven by SR3Lab.exe.
6. **TexLab** per its own plan, in `texlab\`.
7. **Ports** (way B), one tool at a time.
8. **Release**: one zip, tested on a clean Windows install with nothing else installed.

## Risks

- **The importer is still changing daily** (Mountain is under review, three Championship courses and four SEGA Rally 2
  courses are not redone). Freezing a baseline too early means refreshing it constantly; too late means restructuring
  without a safety net.
- **Byte-identity and porting pull against each other.** A port that is "visually the same" but not identical is a
  different promise; decide which one a port must meet.
- **Source detection across four kinds of media** (arcade dump, PC game, PS3 disc or folder, two ROM sets in several
  packagings) is where "user friendly" is won or lost; each needs real samples to test against.
- **Frozen Python exes** can trip antivirus heuristics, which sits badly with a suite whose selling point is
  transparency.
- **Renaming a public repo and its folder** breaks existing links, the users' `setup.yaml` paths and any shortcuts.

## Open questions for the user

1. **`scripts\` and transparency.** Is a frozen exe acceptable there as a first step (way A), or must everything in
   `scripts\` be readable source from day one?
2. **Where does `PLAY.bat` live** - in the root next to `SR3Lab.exe` (as planned here), or in `scripts\`?
3. **Byte-identical forever, or only across the restructuring?** After a port, is "identical files" required, or is
   "identical in game" enough?
4. **Which courses are in the first public release** - Mountain only, or all eight classic courses once they are
   redone to Mountain's standard?
5. **Timing.** Start the restructuring now, or after Mountain is signed off?
6. **GitHub.** Rename the existing public repo to SR3Lab (keeps history and stars, breaks links), or start a new one?
