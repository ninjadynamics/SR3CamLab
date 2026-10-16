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
- **Why the BLAS orders look odd: numpy's OpenBLAS 0.3.21 does not know this PC's CPU and runs its Prescott (SSE2) kernels**
  (`openblas_get_corename64_` in numpy's `libopenblas64_` DLL: "Prescott", MAX_THREADS 24). Its ddot, fitted 100% (9,600 random
  cases n 1 .. 40 with every alignment, 800 long ones up to n 2,000): four 2-lane accumulators, no fused multiply-add; when y is
  8 bytes off 16 its first product goes into accumulator 0's low lane; then two pairs a round, round robin over the four; a pair
  left over into accumulator 0, a single product into its low lane; each lane (a0 + a1) + (a2 + a3), then low + high, added to 0.
  `np.convolve(a, k, 'valid')` is that ddot per output (k copied, aligned): 4,982 of 4,982. `core\npexact.py` (ddot, pwsum) has it.
  On a PC whose CPU OpenBLAS knows, numpy itself gives other last bits; the ports keep this PC's numbers (v15 was made here).
- **`np.linalg.lstsq` is LAPACK 3.10's dgelsd on those Prescott kernels; `core\nplapack.c` reproduces it bit for bit** (m <= 8
  rows, n <= m, up to 8 right-hand sides). Each kernel was read off numpy's own DLL (`libopenblas64_` exports every BLAS and LAPACK
  routine, `dgelsd_64_`, `dbdsqr_64_`, ...: called through ctypes with 64-bit integers): `dgemv 'T'` peels row 0 when A is 8
  bytes off 16, then sums columns in groups of 4 (lda odd: also 2) with one 2-lane accumulator each and the rest one by one with
  two; `dgemv 'N'`, small `dgemm` add in order from 0; `dger` adds (alpha y_j) x_i; `dnrm2` adds the squares in order on the
  x87 unit. The addition trees were found with +2^60 / -2^60 / 1.0 probes (the sum counts the ones outside the subtree where the
  two big values meet). The LAPACK routines are the reference ones (dlartg the 3.10 form: p = 1 / d, c = |f| p, s = g sign(p, f)),
  each checked against the DLL's (0 mismatches in 70,000+ cases), the whole against `np.linalg.lstsq`: the 9,074 systems of a
  Desert build and 110,000 random / 1995-like ones (`core\test_nplapack.py`). numpy's wrapper puts A and B in ONE malloc'ed
  block, B right after A, and that layout matters (dgemv's peel), so nplapack.c builds the same block. `np.linalg.svd` (full
  matrices) is dgesdd JOBZ 'A'; nplapack's `svd` covers m >= n below dgesdd's QR threshold INT(n x 11 / 6) (every square matrix;
  fill1995.unsmear's 2 x 2): dgebd2, dbdsdc's small branch (dlasdq with U and VT, its selection sort), the Q and P reflectors on
  U and VT, in numpy's block (A, S, U, VT); U, S and Vh the same bits as numpy's on 63,000 matrices of 7 shapes.
- **The x87 precision is per thread.** Python's threads start with control word 0x27F (53 bits), gcc's OpenMP workers with 64
  bits; nplapack's dnrm2 ran x87 code and gave other sums in 1,399 of 8,911 systems until it set 53 bits itself for those
  instructions. Any C port of an x87 kernel has to do the same.
- `np.linalg.matrix_rank(A, tol)` takes np.linalg.svd's singular values (dgesdd); overlay_bake now counts dgelsd's, which can
  differ in the last bit: on the 3,060 rank tests of a build the decisions are all equal, the nearest value 3.7 decades from 1e-6.
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

### The importer (`import_classic.py`), module by module

The importer's two passes are one process with ~45 modules, so it stays numpy-dependent until the last of them is done. Split
(2026-10-15, agreed in the agents chat): Codex the geometry and the build's core (build_classic, import_classic, fastgeo /
geobuf, fastround, round1995, meshgen / meshbuf, fastbuild, fill1995, build_more, fastside / lightside, ...), Claude the light
maps, textures, overlays and helpers. Rule: a function whose callers still compute with numpy keeps its return type; a
numpy-free twin sits beside it until the caller switches. Each step checked with the stack's light / build steps on isolated
data roots, old against new (scratchpad tools lightrun.py / buildrun.py): every file byte for byte, faces.pkl by value.

| Module | Now | Check |
|---|---|---|
| roadsight.orient | geobuf.pack + fastlm.c lm_rs_prep, plain Python decisions | 335,604 items and the log identical, 3.37 -> 3.22 s |
| seenside.orient | geobuf.pack + lm_ss_prep / lm_open_sides; lm.sides.npz through npyio ('<U' text, 0-d scalars). 2026-10-16: the road-sight rays through fastlm_rays.c rx_nearer_h (the leaf that hid the last ray tried first, then the subtree round it, then the rest: rx_nearer's answer does not depend on the order it looks at the leaves in, point 5 there), the six sample points in one call (lm_roadsight_n: the sums the three calls of two gave) | lists, logs, sides file identical; ~24 -> 22.7 s; the rays (1,886 million on Mountain) 25.6 -> 11.9 s, the light step 70 -> 55 s, the counts the same in a bench of the recorded calls and fastlm.selftest's 24.7 million rays against cast_one (0 different) |
| lightmap1995.save_collect / key_buf / lookup_buf / load_table_buf | buffer protocol in, fastlm.c lm_key12 / lm_gather / lm_lookup | lm.lm.npz identical; lookup 0.27 -> 0.12 s (not called yet) |
| bake1995.save_scene, scenefile.save_arrays | lm_albedo (UCRT pow, numpy's pairwise / row-by-row means) | lm.scene identical |
| sky1995 | its own operations in fastlm.c sky_dirs / sky_tile / sky_fill; build_classic.vivid / dxt1_rgb through a numpy bridge | all 10 game files identical |
| fastdxt | buffer protocol, dxt1_bytes | all 10 game files identical |
| layers | plain floats in numpy's per-call orders | pairs and layers identical on 334,229 faces; 237 -> 30 s |
| facadebake.compose | fastlm.c fb_paint / fb_fill on bytes; `compose` a numpy bridge | the facade pictures identical; 1.05 -> 0.22 s |
| crowd.classic_spots / matrix / build_safe | plain floats; `fit_offset` keeps numpy | all 10 game files identical |
| pacenotes.corners | unwrap / convolve (npexact.ddot) / gradient written out | the same notes on 4 centre lines, all 10 game files identical; 6-10 ms where numpy took 0-3 ms (once a build) |
| bsp.parse_bsp, bsp_build.build_corridor / to_tree | records as struct rows (`numpy=True`: the old structured arrays, for preview.py); the corridor's two all-triangle / all-quad loops in fastlm.c bc_inside / bc_limits; check_corridor (flat corridors only, a log line) keeps numpy's random numbers | the wall BSP of a build identical (bytes, fixups, stats, cells), all 10 game files identical, SEGA's 6 boundary chunks still round-trip byte for byte with numpy blocked; 0.207 -> 0.060 s |
| scene11, retex_contact | numpy was imported, never used | - |
| finishgate.install / check | build_classic's buffer twins (tile_pixels_buf, vivid_buf, make_texture_dxt5_buf, faces_to_mesh_buf) and builduv.uv_split; numpy's float32 steps (gain, vertex - centre, the bounds' centre) as double then rounded to float32; `_old_install` the reference | the build step's game files (the gate is in the game-objects file) and its finish-gate log lines identical |
| trackdeform, build_testtrack | import without numpy: parse_td(numpy=False) (vertex records as bytes), VDT made on first use, td_to_model / build_td take either; page_for / aimap_cells / build_spline / two_pages take numpy rows or Python ones; check_authored numpy-free (UCRT hypot as np.hypot, pairwise lap sum); td_rows / road_frame / lateral keep numpy for build_classic / build_more / import_classic | build step identical, check_authored's lines (incl. "TD parse->rebuild identical True") the same |
| export_adapter, allsr3, build_allsr3, preview_obj | export_adapter numpy-free (flat_uv bit-identical on 20,000 polygons, the centre-line reader = np.loadtxt on 6 real lines); the other three import numpy only inside the functions using it | build step identical |
| coursepatch.apply / remove / continue_uv / move_boards | Python numbers in numpy's orders; corners found through x-sorted windows in fastlm.c cp_near (one call for all), a polygon's removal corners and the cut test in cp_cand / cp_cut; uv_split asked only for polygons the build's own fit test fails AND that have a removal corner in their box (it is kept otherwise either way); `_old_<name>` the references | the build step's game files, composed tiles and all 11 patch log lines identical, the light step's files identical; apply 7.4 -> 3.7 s (remove 4.4 -> 1.6 s, of it 1 s uv_split) |
| round1995.round_outward (round = 4, the default mode) | round1995.c: hard edges, lying triangles, the polygons' normals / smooth edges / fan normals (the label propagation = the lowest node of each joined set) / curve offsets / hollowness, the pieces' curve offsets, the weld (np.unique + np.bincount means), cap, order, the drawn triangles and shared edges, the O3 loop with UCRT acos on every core, flat-stays-coarse; fastround's buffer kernels for subdivision, gap / order limits, corner / canon keys; PATCH as buffers (patch_lookup bridges to numpy for build_classic); `_old_round_outward` the reference; round_natural ('shrink') keeps numpy | the recorded build call: all 335,598 faces, every figure (in key order), PATCH and the log line identical, numpy blocked; the build step's game files and the light step's files identical; 6.3 -> 1.1 s (2.6 s with the faces written out) |
| seal1995.seal ("stitch") | fastseal.c: the places as numpy's np.unique of 12-byte void rows (memcmp order, stable), the clusters (union to the lowest number: order-free), the representatives (np.lexsort), the edges and the joint test in numpy's dot orders, the quads to cut; meshbuf for the meshes; the cutting and new vertices on Python numbers; `_seal_numpy` the reference (SR3_FASTSEAL=0); the unit now -ffp-contract=off (the old filter's 1 % margins are unaffected) | the three seal passes of a build give the same chunks, ids and counts with numpy blocked; all 10 game files identical; 6.65 -> 2.7 s a build |
| checkpoints1995.gantries (the stand-in gantries of a course without a gate file) | plain floats, the centre line read as numpy's loadtxt does | the faces of every SRC course identical (repr) |
| overlay_bake.resolve / find_pairs / gate | plain floats in numpy's orders, nplapack for lstsq, geobuf.prep + fastgeo.c's pair search bound without numpy; `_recipe`'s texels in fastlm.c ob_recipe (numpy only to hand the pictures back to build_classic: tile_pixels / save_baked take numpy arrays); the functions other modules call stay numpy | all 10 game files, the 492 composed-tile files and the 138 recipes identical (`_recipe` against `_old_recipe`: 3,000 random cases); numpy blocked: resolve, find_pairs, gate run; resolve 3.61 -> 1.49 s, find_pairs 0.29 -> 0.25 s a build |
| texfast, grid, fastlm, m2colour, ... | numpy imported only inside the functions that still use it | - |

ROM stages: `course.use_tex()` sets only the export's folders (course.use() loaded the whole build, and numpy with it,
just for those). A stage's time includes about 3 s whenever it is the first process to read a freshly written region
image (the system scans the file); that hits the numpy and the numpy-free version alike.

The bake reads the material classes straight from `retex`'s CSV and takes `PAGE = 2048` by value: `retex.py` and
`lightmap1995.py` still import numpy. The two `.npz` files are byte for byte numpy's as whole files too: numpy's
`savez` opens each member with `ZipFile.open(name, 'w')`, whose ZipInfo carries 1980-01-01 and mode 0600, as npyio's.

The logged "mean light over the pages" is now summed in double (numpy summed in float32); it can differ in its last
digit, and nothing reads it.
