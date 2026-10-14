# scripts

| Folder | What |
|---|---|
| `importer\` | the classic-course importer (`import_classic.py`, `build_classic.py`, ...): SEGA Rally Championship / SEGA Rally 2 courses into SEGA Rally 3's files. Python with numpy and Pillow; the `.c` files are compiled to DLLs on first use (gcc) |
| `importerlendpatch\` | tools for hand patches made in Blender: diff two scenes, write the patch as JSON, apply and check it |
| `rom_tools\` | extraction from your own Model 2 / Model 3 ROM files and audio tools. For the settings app's "SEGA Rally Championship (1995)" co-driver and music: `src_audio.py codriver` (clips straight from the ROM) and `src_music.py all` (records the tunes from the sound board in MAME, without a window or sound) |

Course settings and patch files are in `..\courses\` (`<game>_<course>.json`, `<game>.<track>.patch.<number>.json`). Notes on every format and finding: `..\docs\kb\`.

No SEGA data is in this repository. The importer reads your own ROM files and your own copy of the game, and writes its builds, extracts and textures to a work folder outside the repository. On the author's PC that folder is `F:\Jogos\SEGA Rally 3\SR3 track format\work`, joined to this one by folder links: `out`, `tmp`, `classic_tex`, `previews`, `retex` and `courses` here are such links and are git-ignored (see `docs\kb_verbatim_road_and_milestones.md`, section 8). The scripts still carry that PC's paths (`importer\common.py`).
