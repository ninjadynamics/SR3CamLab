# 31. The stack without numpy

Started 2026-10-15. Goal (the owner): the toolchain no bigger than the tiniest Linux distros. numpy is 13 of its 48 zipped
MB; the user's path is moved off it, process by process, to our own C (OpenMP) and plain Python. Speed and parallelism
come first: nothing may get slower, and every step gives the same bytes as v15.

## What a user runs, measured

A full chain on an empty data folder, every Python process logging the modules it loads (a sitecustomize hook):

- the processes: `rom_import.py`, `import_classic.py` (collect and build passes), `rtbake\rt_bake_game5.py`,
  `rtbake\rt_compose_game.py`; plus the audio tools (`src_audio.py`, `src_music.py`) and `hd_textures.py`
- 54 modules of ours; 46 of them use numpy (about 3,200 calls with the process scripts), 7 use Pillow
- the other ~3,400 numpy calls are in development and investigation scripts (the generators of the shipped patch JSONs,
  the Blender-scene diff tools, the bake's bench and probe tools, the Daytona / SR2 explorers); not on the user's path

## How each process is moved

1. **Its files.** The processes hand each other arrays in numpy's `.npy` / `.npz` files. `core\npyio.py` reads and writes
   that format in plain Python (an `Arr`: dtype string, shape, raw bytes; `mmap` for the big ones), writing the header as
   numpy 1.24 does, so a file is byte for byte `np.save`'s (`core\test_npyio.py`, 49 checks). A process that is already
   numpy-free and one that isn't yet read each other's files unchanged.
2. **Pickles of numpy arrays** cannot be read without numpy; each becomes an `.npz`. The ray scene (`<path>.scene`) is
   the first: `core\scenefile.py` (tris, uv, mat, albedo, albedo_rgb, sun, centre, and the see-through masks as
   `holes_h / holes_w / holes_off / holes_bits`, the layout `rays.c` takes). `load(path, numpy=True)` gives the numpy
   readers the dict they always had; old pickles still load there.
3. **Its arithmetic** goes to C, matching numpy to the bit, built with `-ffp-contract=off` (cbuild.py `FOC`). Each C
   function quotes the numpy lines it replaced and says what of numpy's order it keeps.
4. **Checked**: the process's outputs against the numpy version's on the same inputs, then the whole chain against v15
   (`texmap.json` aside, it records a folder path), and timed.

## numpy's arithmetic, as found

- numpy 1.24 turns a Python float into float32 before using it with a float32 array, so `(1 - AMB) * x` with `x`
  float32 is `(float)(1.0 - AMB) * x`, every step rounded to float.
- A mean along an axis adds the elements one after another and then divides by their number;
  `np.linalg.norm(N, axis=1)` is `sqrt((x*x + y*y) + z*z)`; a short sum over the last axis of a big array is
  `(p0 + p1) + p2` (checked on real data: the composed pages are byte for byte).
- `np.round` rounds half to even (`rint` / `rintf`); `np.maximum` and `np.min` pass a NaN on.

## Done

| Process | Was | Now | Check |
|---|---|---|---|
| `rtbake\rt_compose_game.py` | numpy, 8 pages at a time through float32 temporaries: 6.1 s warm (8.9 s cold) | `rtbake\rtcompose.c` (`rtc_road`, `rtc_pages` one page per thread, `rtc_key`) + npyio / scenefile: 0.6 s warm (3.5 s cold) | the pages file byte for byte numpy's (277 MB), every table member identical, the same log line, numpy never loaded |

The logged "mean light over the pages" is now summed in double (numpy summed in float32); it can differ in its last
digit, and nothing reads it.
