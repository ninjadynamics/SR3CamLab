# 30. The import stack, from the ROM set to the installed track (2026-10-15)

The public form of the work in 14, 16, 25 and 26: one runner (`tools\import\stack.py`) and its window (`IMPORT.bat` ->
`tools\import\stack_window.ps1`) that take your own `srallyc.zip` to a Classic mode track in SEGA Rally 3, every step
with an optional `.blend` of what it made. Folders come from `tools\import\settings.json` (`core\common.py`).

## 1. Steps and what each one reads

| Step | Writes | Reads |
|---|---|---|
| rom (`src\tracks\rom\rom_import.py`) | `<work>\tmp\m2\` region images + colour tables; `<classic>\obj\` collision and centre lines (all four courses); `<classic>\courses\src\course<N>_<name>\` objects, sky, low detail, tiles, props, gameplay.json, gates; `<work>\classic_tex\course<N>\` the importer's own export; `<classic>\sr2_gameplay\src\` checkpoint times and labelled pace notes; derived tiles; `<work>\retex\tile_labels.csv` (only when there is none); an empty `textures_hd\` | `srallyc.zip` only (the course JSON and patch files for the derived tiles, the shipped labels) |
| collect (patch, round, light) | `<work>\tmp\stack\<name>\` faces.pkl (GAPFILL_DUMP), patched.pkl (ROUND_IN, with a patch `.blend`), lm.*, gate.json | the rom step's files, the course JSON, its patch files, the recipe, SR3's own track templates |
| rt | lm.lm.npz, lmA.* (the composed light), lm.carshade.npz | the collect files |
| build | `<work>\out\<name>\Desert4\` the 8 game files, texmap.json, and now arcade_times.bin and road.txt (course JSON `arcade_times`, `road_txt`) | all of the above |
| install (`core\install_track.ps1`) | `Main_release\track<N>\Desert4\`, `_SR3Extras\classic.json`, `switch.json` | the build |

The recipe (`src_1.recipe.json`) holds what fast_all.sh / build_variant.sh passed as `--set` (raw_recipe.txt plus the R4
values and light_split 0.72), in the same order, so the importer's settings come out the same.

## 2. Tiles that are not in the ROM (core\derived_tiles.py)

The patch chain names two tiles no ROM export makes; they had been made once, as a side effect, and kept on disk:
- `<tile>_dk`: the tile at 0.32 of its brightness, rounded down (roadfill1995 rule T3 / gapfill_gen's forest floor). Patch 2
  and 3 name `tex_s1_x1280_y0256_256x256_c0D6_dk`. Remade from the vanilla tile it is the same file, byte for byte.
- the sea sheet's tile `tex_sea_blue_64x64_c1DF`: the 1995 sea-bowl tile `tex_s1_x0512_y0768_64x64_c1DF` scaled per
  channel and rounded down. The script that made it is lost; the factors 0.67005 / 0.93011 / 1.1401 were recovered from the
  two pictures (every pixel of a 15-level ramp fixes a narrow interval per channel) and give the file again bit for bit. They
  are in the course JSON (`sea.from`, `sea.scale`). They are not colour / mean of the tile (that is off by up to 1 level).
The nine other `_dk` tiles in the course folder came from gap-fill experiments; the R4 build reads none of them.

## 3. The clean-room checks

- **ROM side**: `rom_import.py` into an empty data folder: 694 files byte-identical to the ones the work has used, among them
  every input of the R4 chain. Different, and harmless: `src_course1_hi.obj`'s first comment line (the older exporter named
  the course), the file column of the pace notes (the sample index of the old audio extraction is not made; the importer
  reads course, section and name only).
- **Whole chain**: from that folder (plus the owner's three upscaled HD tiles, as a user's own choice) the chain gives the
  installed v15 build again: all 8 game files byte for byte, arcade_times.bin and road.txt too; texmap.json differs only in
  the folder path it records. The same through `stack.py` (396 s with every export).
- **Retexture labels** (`tile_labels.csv`) are our own data, not the ROM's: they ship beside the course JSON
  (`src_<N>.tile_labels.csv`) and are copied into `<work>\retex` when the folder has none.

## 4. Exports (core\export_blend.py)

rom = the export OBJs; patch / round = the dumps written as OBJ in the course-OBJ axes ((x - ox, y, oz - z), ox / oz from
`classic_xform.json`), composed tiles included (`BC.BAKED` from the round dump); rt = `rtbake\asbuilt_decode.py` +
`asbuilt_scene.py` (pictures x light maps, the sky dome); build = `preview_obj.py` + `blendpatch\bl_build_to_blend.py`.
Each runs in a thread beside the next step and Blender packs every picture.

## 5. Python and the C compiler (owner, 2026-10-15: docs\ROADMAP.md D3)

The only binaries SR3Lab ships are Python and a C compiler, in `SR3Lab-<date>-toolchain.zip` (`tools\release.py`), optional:
setup (`tools\setup_toolchain.ps1`, the window's "Python and gcc...") unpacks it offline into `tools\python` and `tools\mingw`;
`-Winget` fetches Python 3.11.3, gcc (WinLibs) and the pinned numpy / Pillow instead, and the zip can go. The mod zip itself holds
no binary (release.py refuses to stage one). The C helpers are compiled on the user's PC on first use from `core\cbuild.py`'s
table (sources, per-unit flags, the files that name each DLL); `python core\cbuild.py` builds them all and prints the commands.

- `tools\python` is this PC's CPython 3.11.3 (the stdlib zipped, no tests / IDLE / tkinter) with numpy 1.24.3 and Pillow 10.0.1,
  the versions every build here was made with. `python311._pth` makes it ignore PYTHONPATH / PYTHONHOME; with `._pth` Python
  also leaves the script's own folder off sys.path and still adds the user's site-packages after `import site`, so
  `Lib\site-packages\sr3lab_paths.py` (run by a .pth) puts the script's folder first and takes the user's site-packages off.
  Every script under `tools\` finds core\ itself (it no longer relies on PYTHONPATH or the current folder).
- `tools\mingw` is the part of WinLibs' gcc 13.2.0 (MinGW-w64 11.0.1, UCRT) that compiling and linking every helper touches:
  314 files, 74.7 MB of the 1.1 GB install, found with gcc -M (headers), -v (programs), -Wl,--trace (link inputs) and the
  DLLs those programs load. Shown enough: every helper built with it while PATH held only Windows' own folder.
- Licences: Python's (PSF), numpy's and Pillow's travel with them; GCC and binutils are GPL 3 (the runtime libraries under the
  GCC Runtime Library Exception): the toolchain zip names where the complete source is (winlibs.com, gcc.gnu.org,
  sourceware.org, mingw-w64.org) and carries the licence files. Whether that is enough for redistributing GCC binaries, or the
  source archives must be offered beside the zip, is the owner's call before a public release.
- The target: `SR3_MARCH` / settings `march`, 'native' by default; the release check builds for x86-64-v3 (AVX2 + FMA), so that
  every PC compiles the same code. winget's oldest WinLibs is gcc 14.2: the same bytes from it are not shown.
- Found by the release check (`release.py --check`: the whole stack in the staged tree, on an empty data folder, PATH = System32,
  LOCALAPPDATA elsewhere): the `._pth` script-folder and user-site points above; rtbake scripts that imported core through the
  current folder; `cbuild` building in %TEMP% and moving the DLL across drives (os.replace cannot: the build now happens beside
  the DLL, and a failed move is an error).

## 6. Not done yet

The C ports / threading pass, and making results independent of the thread count (27, "One run that differed").
