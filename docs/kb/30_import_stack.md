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

## 5. Not done yet

The bundled Python (embedded CPython + numpy + Pillow + cffi, the prebuilt DLLs and the MinGW runtime they need) and the
C ports / threading pass. The DLLs are built with `-march=native` today; a release build must be portable and give the same
bytes (`rays.c`, `fastdxt.c`, `fastseal.c` are compiled without `-ffp-contract=off`, so FMA contraction must stay as it is:
`x86-64-v3` keeps FMA on).
