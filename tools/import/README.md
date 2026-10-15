# tools\import

Everything that turns another SEGA game's courses into SEGA Rally 3 tracks: extraction from your own ROM set, the
numbered patch files, the importer, rounding, the light bake and the install into the game.

No SEGA data is in this repository. The scripts read your own ROM set and your own copy of SEGA Rally 3, and write
every extract, build and texture to a data folder outside the repository.

## Layout

| Folder | What |
|---|---|
| `core\` | The engine, for every game: `import_classic.py` (the importer), `round1995.py` (rounding), `rtbake\` (the light bake, C), `blendpatch\` (patches made in Blender: dump, diff, write as JSON, check), the SR3 file readers and writers (`sbfw.py`, ...), `hd_textures.py`. The `.c` files beside the Python are compiled to DLLs on first use. |
| `src\tracks\rom\` | SEGA Rally Championship (Model 2A, `srallyc.zip`): region images, collision, objects, textures, gameplay data, checkpoint times and pace notes. |
| `src\tracks\courses\` | `src_<course>.json` (everything course-specific) and `src.<track>.patch.<number>.json` (the patch chain, applied in order). |
| `sr2\tracks\rom\` | SEGA Rally 2 (Model 3): the geometry, texture and gameplay readers. |
| `daytona\tracks\rom\`, `daytona\tracks\courses\` | Daytona USA (Model 2): courses and cars. |
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
