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
- numpy's matrix products go through OpenBLAS. Measured on a million random rows (numpy 1.24.3, this PC), each 100%:
  `(A * s).sum(1)` and `A @ M` (matrix x matrix, any thread count) are `(p0 + p1) + p2`; `np.dot(a, b)` of two 3-vectors
  and `A @ s` (matrix x vector) with OpenBLAS on 1 to 16 threads are `(p0 + p2) + p1`, the middle term last, no fused
  multiply-add. **At 32 threads `A @ s` changes**: from 20,000 rows up some thread chunks run another kernel and give other
  last bits, so numpy's own answer depends on the PC's core count. A C port uses the fixed formula and gives the same bits
  on every PC. The chain does not depend on it: with OPENBLAS_NUM_THREADS=8 it still gives v15's game files (checked
  2026-10-15).
- `A @ s` also adds each row's sum to y = 0 (dgemv with beta 0), so a row whose sum is -0.0 comes out +0.0
  (2 of 408,164 normals @ sun on Mountain). A port writes `0.0 + ((p0 + p2) + p1)`.
- A sum along the axis that is innermost in memory (`np.sum` / `np.mean` of a 1-D array or of a strided column view) is
  pairwise: below 8 elements one after the other from 0; up to 128 eight running sums added as
  `((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7))`, then the rest one by one; above that the two halves, cut at a
  multiple of 8; the result added to 0. Measured 100% on 300 arrays per size from 5 to 1,000.
- A sum along an OUTER axis (`mean(0)` of a C-ordered (n, 3) array) adds one row after the other from 0 (400 of 400,
  float32). Which one applies follows the memory layout, not the axis number: `v[:, [0, 2]]` (fancy indexing) comes out
  column-first, so its `mean(0)` is pairwise (the bake's tree axes), while `np.concatenate(...).mean(0)` is sequential
  (m2_collision's centre line).
- `np.cos` / `np.sin` of float64 arrays are the C runtime's (ucrtbase.dll; numpy's SVML loops need AVX-512, which this
  PC lacks): the same bits as Python's `math.cos`. A C port calls ucrtbase's own `cos` / `sin` through GetProcAddress,
  since gcc's or mingw's could differ. `np.hypot` is ucrtbase's `hypot` too; Python's `math.hypot` differs in 17% of
  cases.
- `np.percentile(v, 90)` ('linear'): the (n - 1) x 0.9-th sorted value, between its neighbours as numpy's `_lerp`:
  `a + (b - a) * g` below g = 0.5, `b - (b - a) * (1 - g)` from there.
- `np.random.RandomState(seed).rand()` is Python's `random.random()` once the state is numpy's: both are MT19937 and make
  a 53-bit float from two draws the same way, but numpy seeds with init_genrand, so set it with `random.setstate`.
- **`np.dot` of two 3-vectors depends on where the second one sits in memory** (OpenBLAS's small kernel): 16-byte
  aligned gives `(p0 + p2) + p1`, 8 bytes off gives `(p0 + p1) + p2`, each 100% (6,000 pairs per alignment class).
  `np.linalg.norm(v)` is `sqrt(v.dot(v))`, so it follows `v`'s alignment. A fresh numpy array is 16-byte aligned; the rows
  of an (n, 3) array alternate (24-byte rows). So a port reads each site: which operand is fresh, which is a row.

## Pickles

A pickle holding numpy objects needs numpy to load. `core\nfpickle.py` writes the stack's dumps (`faces.pkl`,
`patched.pkl`) without any: the pickler's `reducer_override` turns each numpy array into an `npyio.Arr` and each numpy
scalar into a Python number (the same bits), without walking the data; `load(numpy=True)` gives numpy readers numpy
arrays back through the unpickler's `find_class`. On the real 92 MB `faces.pkl`: the same values, dump 0.9 s, load
1.0 s (1.2 s with numpy=True), as fast as pickle was. The whole chain with it: v15's game files.

## Done

| Process | Was | Now | Check |
|---|---|---|---|
| `rtbake\rt_compose_game.py` | numpy, 8 pages at a time through float32 temporaries: 6.1 s warm (8.9 s cold) | `rtbake\rtcompose.c` (`rtc_road`, `rtc_pages` one page per thread, `rtc_key`) + npyio / scenefile: 0.6 s warm (3.5 s cold) | the pages file byte for byte numpy's (277 MB), every table member identical, the same log line, numpy never loaded |
| `rtbake\rt_bake_game5.py` | numpy around the C rays: 197.7 s on Mountain R4 (scene ready 4 s, cars 2 s, texel maths 1.3 s, store 9.4 s) | `rtbake\rtg5prep.c` (the scene's triangles, the once-edges under wall feet, normals and sun products, the cars' pages, the rectangles and their lattices, per batch the texels, fan turns, facing, other side and store) + plain Python (trees, skirts, buildings, page packing) + npyio / scenefile / nfpickle: 178.1 s (3 s, 1 s, 0.2 s, 0.2 s; the rays are the same C) | raw.npy byte for byte numpy's (646 MB), every member of pack.npz and carshade.npz identical (the deflated one too), every section's arrays equal numpy's at 11 checkpoints, the ray-bench dump equal in all 41 items, the same log lines, numpy blocked and never loaded |

| `src\tracks\rom\rom_import.py` and its 11 stages | numpy in 9 stages and in rom_import itself (regions ran in-process): 36 s | m2_build, m2xlat / m2colour (tables as bytes, npyio), m2_collision (float32 sums emulated), src_all / classic_export / classic_tex / m2tex (pages and tiles as bytes, `bytes.translate` for nibbles and colours, the page fit in exact integer sums), m2_gameplay / m2_game / m2_surface, gates1995, derived_tiles, src_leftovers; plain Python, no C needed: 30 s | all 708 files of the step byte for byte numpy's, numpy blocked in every stage (a sitecustomize on PYTHONPATH); the build-facing numpy functions (`load_pages`, `tile`, `tile_rgb`, `usable`, `palette`, `lumaram`, `table`) return the same arrays as before for all 12 pages and 130 tiles |

ROM stages: `course.use_tex()` sets only the export's folders (course.use() loaded the whole build, and numpy with it,
just for those). A stage's time includes about 3 s whenever it is the first process to read a freshly written region
image (the system scans the file); that hits the numpy and the numpy-free version alike.

The bake reads the material classes straight from `retex`'s CSV and takes `PAGE = 2048` by value: `retex.py` and
`lightmap1995.py` still import numpy. The two `.npz` files differ from numpy's only in their zip timestamps (numpy
writes the time of writing, `npyio` 1980-01-01).

The logged "mean light over the pages" is now summed in double (numpy summed in float32); it can differ in its last
digit, and nothing reads it.
