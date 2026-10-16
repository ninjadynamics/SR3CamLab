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
`-Online` fetches Python 3.11.3, gcc + clang (WinLibs) and the pinned numpy / Pillow instead (winget first, curl as the fallback, SHA-256 checked), and the zip can go. The mod zip itself holds
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
- Licences (the owner left it to me, "lean and legal friendly"): tools\mingw\licenses carries SOURCES.txt (each component,
  version, licence and source archive: GCC 13.2.0, binutils 2.42, GMP 6.3.0, MPFR 4.2.1, MPC 1.3.1, libiconv 1.17, gettext
  0.22.4, MinGW-w64 11.0.1, isl 0.26, zlib 1.3.1, zstd 1.5.5, dlfcn-win32), the GPL v3 and the GCC Runtime Library
  Exception (from numpy's licence file, which carries both). The owner's later choice (`665c4fd`) superseded the proposed
  `--sources` archive: current `release.py` provides exact upstream source archive links and WinLibs build-recipe links
  in SOURCES.txt, checks those links before staging, and requires them to remain available while the toolchain is offered.
  Python, numpy and Pillow carry their own licences. This records the implemented packaging, not a new legal assessment.
- The target: x86-64-v3 by default (`SR3_MARCH` / settings `march`; 'native' still possible, with its own DLL names), so every
  AVX2 + FMA PC compiles the same code. On the author's PC it gives the native build's bytes (the release check rebuilt v15).
  The compiler matters through the fused multiply-adds: every helper built with `-ffp-contract=off` changes 4 939 bytes in 16
  light-map pages of `desert4_master_gfx_xdata.sbf` (of 42 MB; every other file the same), so a compiler that fuses less or
  more would not give v15. winget's WinLibs gcc 14.2.0 (19.1.1 / 12.0.0 r2) does: every helper built with it, the chain gives
  v15 byte for byte (2026-10-15). `SR3_CFLAGS` (tests) adds flags to every unit and gives those DLLs names of their own.
- Found by the release check (`release.py --check`: the whole stack in the staged tree, on an empty data folder, PATH = System32,
  LOCALAPPDATA elsewhere): the `._pth` script-folder and user-site points above; rtbake scripts that imported core through the
  current folder; `cbuild` building in %TEMP% and moving the DLL across drives (os.replace cannot: the build now happens beside
  the DLL, and a failed move is an error).

## 6. Threads

The whole chain on 8 OpenMP threads with numpy's OpenBLAS on 1 (as an 8-thread PC runs it, 637 s) gave the v15 game files
byte for byte, as 32 threads do: the results do not depend on the thread count. So the settings' `threads` (all / all but one /
a number) now sets OMP_NUM_THREADS and OPENBLAS_NUM_THREADS for every step of the stack, not only the bake. (27's "one run
that differed" was not seen again; it was made on the efficiency cores alone, beside other work.)

## 7. Final October 15-16 batch status

The current C ports / speed batch is integrated through `fd8707c`. Final reported light + RT + build time is 252 s
(40 + 180 + 32); ROM separately 11 s. Codex independently compared all ten saved final game files with v15: equal.
See [27](27_build_speed.md) for timing boundaries and rejected experiments, [31](31_numpy_free.md) for the completed
process/helper migrations and compatibility fallbacks, and [32](32_session_2026_10_15.md) for final session evidence.
The importer as a whole still uses NumPy; the toolchain cannot yet remove it. The later compiler-closure work also
covers standalone x86 builds (`3f0fd27`, `f61d10d`), with dependency hashes; the earlier 314-file importer-only snapshot
above should not be read as the final combined closure size.
