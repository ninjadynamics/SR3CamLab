# tools\import

Everything that turns another SEGA game's courses into SEGA Rally 3 tracks: extraction from your own ROM set, the
numbered patch files, the importer, rounding, the light bake and the install into the game.

No SEGA data is in this repository. The scripts read your own ROM set and your own copy of SEGA Rally 3, and write
every extract, build and texture to a data folder outside the repository.

## Python and a C compiler

The stack is Python with C helpers. `SR3Lab-<date>-toolchain.zip`, which comes with the release, holds both - CPython 3.11.3
with numpy 1.24.3 and Pillow 10.0.1, and the part of MinGW-w64 gcc 13.2 the helpers need - and the window's "Python and gcc..."
button (or `tools\setup_toolchain.ps1`) unpacks it into `tools\python` and `tools\mingw`: no internet, nothing installed in
Windows. Or `setup_toolchain.ps1 -Online` fetches every part from its own publisher instead - winget first, curl when winget
is not there or fails (python.org's Python 3.11.3, numpy and Pillow from PyPI, WinLibs' gcc and clang), each pinned and
checked against its SHA-256 - and the zip can be deleted. These are
the only binaries SR3Lab ships. The C helpers (`core\*.c`, `core\rtbake\*.c`) are compiled on your PC the first time they are
needed: `core\cbuild.py` holds how each one is built (`python core\cbuild.py --list`; `python core\cbuild.py` builds them all
and prints every gcc command).

## The stack

`IMPORT.bat` (beside PLAY.bat) opens the stack window: the folders below, a course, and a checklist of the steps, each
with its own `.blend` export. The same from a command line:

```
python tools\import\stack.py src 1                                  every step
python tools\import\stack.py src 1 --steps rom                      only the ROM import
python tools\import\stack.py src 1 --steps build                    the game files again, with the light baked before
python tools\import\stack.py src 1 --round 2 --patch off            other settings (then light and rt must run again)
python tools\import\stack.py src 1 --blend round,rt                 also a .blend after the rounding and of the lit track
python tools\import\stack.py src 1 --steps install --title "Mountain"
```

The patch chain and the rounding are settings of both importer passes, not steps of their own: a bake remembers the ones
it was made with, and a build that would use that light with other settings is refused.

| Step | What it does | Made by |
|---|---|---|
| 1. ROM | the 1995 game's geometry, tiles, gameplay data and times from your `srallyc.zip` (about 30 s) | `src\tracks\rom\rom_import.py` |
| 2. Patch chain | the course's numbered patch files, in order | the importer's first pass |
| 3. Rounding | natural surfaces rounded outwards (R4 by default) | the importer's first pass (`core\round1995.py`) |
| 4. Light maps | the polygons to light, laid out on pages | the importer's first pass |
| 5. Ray tracing | the light baked (C, every worker thread), then composed | `core\rtbake\rt_bake_game5.py`, `rt_compose_game.py` |
| 6. Game files | SEGA Rally 3's track files in `<data>\work\out\<name>\Desert4` (flat-lit when 4 and 5 are off) | the importer's second pass |
| 7. Install | into the game as a Classic mode alternative; the same title replaces its earlier copy | `core\install_track.ps1` |

How a course is built (the importer's settings for both passes, the bake quality) is in
`<game>\tracks\courses\<game>_<course>.recipe.json`. The `.blend` files go to `<data>\work\blend\<name>\`, in the axes of
the course's OBJ export (those of the Blender patch files); Blender runs beside the next step.

What the stack makes from a new, empty data folder is the installed Mountain build byte for byte (checked 2026-10-15:
the ROM import, then every step; see `docs\kb\30_import_stack.md`).

## Layout

| Folder | What |
|---|---|
| `core\` | The engine, for every game: `import_classic.py` (the importer), `round1995.py` (rounding), `rtbake\` (the light bake, C), `blendpatch\` (patches made in Blender: dump, diff, write as JSON, check), the SR3 file readers and writers (`sbfw.py`, ...), `hd_textures.py`. The `.c` files beside the Python are compiled to DLLs on first use. |
| `src\tracks\rom\` | SEGA Rally Championship (Model 2A, `srallyc.zip`): region images, collision, objects, textures, gameplay data, checkpoint times and pace notes. |
| `src\tracks\courses\` | `src_<course>.json` (everything course-specific) and `src.<track>.patch.<number>.json` (the patch chain, applied in order). |
| `sr2\tracks\rom\` | SEGA Rally 2 (Model 3): the geometry, texture and gameplay readers. |
| `daytona\tracks\rom\`, `daytona\tracks\courses\` | Daytona USA (Model 2 or verified PS3 PKG): courses and cars. See [source selection](daytona/tracks/rom/README.md). |
| `..\audio\` | Co-driver, music and sound-bank tools: `src_audio.py codriver` (the 1995 co-driver's clips from the ROM), `src_music.py all` (the 1995 tunes recorded from the sound board in MAME), SEGA Rally 2's samples, the SR3 / Revo sound banks. |
| `..\handling\` | The handling flavors (`build_flavor.py`). |

## Settings

`settings.json` here (copy `settings.example.json`; it is not committed) says where things are:

| Key | Default when empty | |
|---|---|---|
| `data_root` | `<repository>\data` | `work\` (`out` = builds, `tmp`, `classic_tex`, `previews`, `retex`) and `classic\` (`courses\<game>\<course>\` with `textures\` and `textures_hd\`, `obj\`, ...) |
| `roms` | `<repository>\roms` | the folder with your own `srallyc.zip` (and `daytona.zip`, `srally2.zip`) |
| `sr3_game` | the `game:` line of `setup.yaml` (PLAY.bat writes it) | SEGA Rally 3's folder, the one with `Rally.exe` |
| `blender` | none | `blender.exe`, only for the optional `.blend` exports and previews |
| `mame` | none | `mame.exe`, only for recording the 1995 music |
| `threads` | `all_but_one` | `all`, `all_but_one` or a number: the worker threads of the bake and the other parallel steps |

`core\common.py` reads it; `python core\common.py` prints every folder it resolved.

## HD textures (optional)

`<data_root>\classic\courses\<game>\<course>\textures_hd\` sits beside `textures\` (the 1995 tiles as exported). A PNG
there replaces the tile of the same name, at any size, when it differs from the vanilla tile, so untouched copies build
exactly as an empty folder does. `python core\hd_textures.py src 1 vanilla` fills it with the vanilla tiles to upscale
or repaint; `... status` lists the ones the build will use.

Notes on every format and finding: `..\..\docs\kb\`.
