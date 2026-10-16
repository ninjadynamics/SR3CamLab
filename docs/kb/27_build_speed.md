# 27. How long the route from a Blender scene to a game build takes (2026-10-13 / 14)

The owner asked for the route to be made fast ("turbo optimize everything in C. Multi threaded."), and chose R4 as the level every build
is made at (25_verbatim_road_and_milestones.md). All times are wall-clock seconds on the owner's PC (i9-13900K, 8 + 16 cores, 64 GB),
measured with nothing else running unless said. Scripts: `tools/import/core/rtbake/` (copies of the working files; they carry the
working folder's paths).

## The route
`fast_all.sh <scene.blend> <tag> ["4"]`:
1. scene -> patch, once: Blender dump (`blendpatch/bl_dump.py`), `scene_diff_local.py` against the base build, `tree_moves.py`.
2. the collecting importer pass of every level asked for, side by side (each is one thread of Python with bursts of C on every core).
3. per level, one after the other: the bake (`rt_bake_game5.py`, every core) and the compose (`rt_compose_game.py`); the level's game
   build starts when its bake ends and runs beside the next level's bake.

`build_variant.sh <tag> <level> <suffix> key=value ...` makes one more game build from the light already baked (a setting changed, no
new bake). `guard.sh <command>` runs a job only while the game is closed (see the last section).

## Measured (R4, scene v11: 406 166 polygons to light, 51.1 million texels, 16 pages)
| Stage | 2026-10-13 evening | now, run 1 | now, run 2 |
|---|---|---|---|
| scene -> patch | 16 | 12.2 | 11.0 |
| collecting pass | 104 | 77.3 | 75.3 |
| bake + compose | 216 | 175.1 | 148.8 |
| of which rays | 133 .. 143 | 162 | 137 |
| game build | 147 | 56.6 | 53.5 |
| whole route | 483 | 321.9 | 289.3 |

After those two runs the mesh writer's texture coordinates were put on arrays (`build_classic.faces_to_mesh`: two loops over the polygons, 427 000
a pass at R4): the two importer passes run again on run 1's inputs took 69.8 s and 48.1 s and wrote the same bytes as run 1.
What is left in the passes (profiler, R4): the seen-side rays 25 s of the collecting pass (2 144 million rays), then `load_visual` 11.5 s,
the patch stage 8 s and the rounding 5 s in EACH pass (the same work twice), the textures and meshes 12 .. 20 s, compression of the files 3 .. 4.5 s.

The evening's figures were taken while a comparison agent was rendering in the background, so they are somewhat high; the two "now"
runs had the machine to themselves. Building R1, R2 and R4 one after the other took 19 minutes that evening.
The two runs gave the same bytes in every file: both patch files, the collected polygons, the seen-side file, the raw light (470 MB),
the packing, the cars' pages, the composed pages and all eleven files of the build. VERIFIED (`cmp`).

## What made it faster, and how each was checked
Every item below gives the bytes the code before it gave, unless said. "Checked" names the comparison.
- **Levels side by side** (`fast_all.sh`). Checked: the builds found every polygon on a page ("not found 0").
- **Texture compression in C** (`fastdxt.c`, OpenMP): a 2048 x 2048 page 0.42 s -> 0.005 s. Checked: `SR3_FASTDXT_CHECK=1` compresses every
  picture of a build both ways - 4 124, 4 622 and 4 673 pictures (R1 collect, R1 build, R4 build), 0 different.
- **Patch stage** (`coursepatch.py`, 17.5 s of each pass under the profiler): triangle areas on plain floats (the same bits as np.cross /
  np.linalg.norm on 200 000 random triangles), the pool of mapped faces made once, `edge_uv` looking only at neighbours that share two
  corners, the build's tile-repeat cut asked only for polygons whose mapping does not fit. Checked: R1 collect and R1 build byte for byte.
- **Sealing** (`seal1995.py`): the corners that may lie on an edge are found in C (`fastseal.c`), the near places on arrays. Under the
  profiler the walk over every edge in Python was 46.6 s of a 195 s R4 build. Checked: R1 build byte for byte; the cluster labels on random
  sets and on the places of an R1 and an R4 build.
- **Seen sides taken over** (course setting `seen_sides_file`): the collecting pass writes its counts per judged polygon with a fingerprint
  of the polygons, of what stands in the way and of the viewpoints; the final pass takes them over when the fingerprint is the same.
  R4: 28 s -> 1 s. If the polygons differ it judges again and says so (then the light-map table may not fit either).
- **Bake set-up on arrays** (`rt_bake_game5.py`): the scene's triangles, the free lower edges for the skirts, and the distance of every
  polygon to the road's middle (`rtg5.c: lm5_mind`). To the first ray: R4 49 s -> 8 s, R1 13 s -> 4 s (measured on the efficiency
  cores). Checked: a dump of everything handed to the light, 41 arrays, identical for R1 and R4; cars' pages file identical.
- **Cars' pages in C** (`lm5_cars`): 20 s -> 2 s. Checked: the 33 pictures and their mapping identical.
- **One bake script for every level** (the fifth): on a whole R1 bake its sun, sky, colour and facing bytes are the fourth version's in all
  47 million texels; the rule's byte differs by 1 or 2 of 255 in 2.3 % of the texels (the fifth takes one value a polygon).
- **Compose**: the distance to the road only for lying polygons, the pages side by side in threads. R4 13.8 s -> 4.7 s. Checked: pages
  byte for byte.
- **scene_diff**: walks its keys sorted. It walked a Python set of names, whose order changes with every process, so the same scene gave
  patch files with the faces in another order each time (and builds that were not the same bytes). Faster keys and areas as well.

## Tried, measured, not adopted (the rays)
A ray costs on average 13.4 four-box nodes, 4.2 leaves, 12.5 triangle tests and 0.8 look-ups in a see-through mask (counted on a forest
batch of R1). Two changes that give the same answers were measured on every core, on samples of 2.9 million texel sides:
| | R1 sample | R4 sample |
|---|---|---|
| as it is | 4.80 s | 5.71 s |
| sun questions asked as "is anything hit" first (mode 2) | 5.07 s | 5.98 s |
| the four triangles of a leaf looked at in one go before the exact test | 4.83 s | 5.81 s |
| both | 5.13 s | 6.06 s |
The hashes of every number returned were equal in all four. Neither helps; the ray code is as it was.
The R4 bake casts 9 933 million rays; its time went from 137 s to 162 s between two otherwise identical runs (not explained).

## An option that changes the result: REFUSED by the owner (2026-10-14: "Don't sacrifice the bake quality for speed")
Kept here as a measurement only. The bake's quality settings are not a place to look for speed.
`RTG_TURNS=1` asks 32 sky rays a texel instead of 96 (the sun's 19 stay, so shadow edges are the same). R4: 3 991 million rays, bake
63 s instead of 149 .. 175 s. Against the full bake, over 55.4 million texels of the composed pages: mean difference 0.48 of 255, 99.9 %
under 4; 8 027 texels off by more than 8, 172 by more than 64 (LIKELY polygons the road never sees, where "the brighter of two sides"
falls the other way). For scale, the game's own texture compression changes the full bake's pages by 2.07 on average, 14 % of the texels
by more than 4. `opt/turns_compare.py` makes the figures and a picture.

## Not while the game runs
Jobs "out of the way" on the efficiency cores at low priority still made the game stutter (owner: "Are you using the CPU? The game is
choking"). `guard.sh <command>` does not start while Rally.exe runs (`WAIT=1`: waits until it has been closed for 20 s) and stops the
job with its whole process tree within 2 s when the game starts. Checked with a stand-in process.

## One run that differed
An R4 build made on 16 threads of the efficiency cores judged one polygon of 371 580 differently from its collecting pass (made on every
core) and 23 polygons came out without a light map. UNKNOWN why; not seen between passes run the same way. The fingerprint in the
seen-side file now reports such a build; "not found 0" in the build log remains the thing to read.

## 2026-10-15: the stack (stack.py), x86-64-v3 builds
| Stage | before | now |
|---|---|---|
| light (the first importer pass) | 88 .. 90 | 77 |
| rt (bake + compose) | 206 .. 211 | 206 |
| build (the second pass) | 62 .. 64 | 56 |
| whole chain (light + rt + build) | 358 .. 366 | 338 |
- `round1995._bends` (41 calls a pass, 8.4 s under the profiler): its cross products, norms and three-term sums in C (fastgeo.c fg_bends,
  numpy's order: the sums run left to right), arccos and degrees left to numpy. 10x faster; on 1.5 million random edges the angles are
  bit-identical, on the real faces the rounding's output and info are identical; the rounding 13.3 s -> 6.6 s a pass.
- `seenside._open_sides`: the 24 sky directions of a point in one batch of rays (12 casts instead of 288), the hits counted as whole
  numbers as before: identical on a random scene, 7.5x faster.
- The track's seven files written, read back and checked side by side (zlib lets go of the interpreter).
Every one checked by the whole chain: v15's game files byte for byte. Not taken: the sealing's edge test and similar small loops go
through numpy's BLAS (matrix x vector), whose summation order C cannot be sure to follow, so a port could change bytes.

## Final October 15-16 batch, through fd8707c

The BLAS caution above describes the earlier state of the investigation. The later ports identified the specific
OpenBLAS/NumPy arithmetic, including address-dependent dot order, and reproduced it; see [31](31_numpy_free.md).
This does not imply that algebraically equivalent expressions, arbitrary CPU kernels or blanket compiler flags
are interchangeable.

Claude's final clean-tree chaincheck6 used ROM plus the selected existing HD input, then light, RT and build.
Codex independently SHA256-compared all ten saved game files against v15: all equal. `texmap.json` records the
output folder and is excluded. Execution conditions and times below are Claude-reported, not a Codex rerun.
The [manifest](../../../SR3-investigation/import-numpy-audit/claude-chaincheck6-v15-comparison.json) records the
independent saved-output comparison.

| Stage | Earlier October 15 stack | Final fd8707c chaincheck6 |
|---|---:|---:|
| ROM | not included in the earlier table | 11 s |
| Light | 77 s | 40 s |
| RT (bake + compose) | 206 s | 180 s |
| Build | 56 s | 32 s |
| Light + RT + build | 338 s reported whole-chain total | 252 s |

The earlier whole-chain total and rounded stage times differ by one second. These are historical runs, not an
alternating same-environment experiment. Earlier sections also use different scenes (406,166 polygons / 51.1 M
texels versus the later Mountain's 385,493 / 73.3 M); do not combine them into one controlled speedup claim.
The final RT ray work accounts for about 170 s and 12,244 million rays. Bake quality was not reduced.

### Controlled light comparison and corrected baseline

Clean alternating runs against worktree `e1f339c`, after `394018b` road sight, `172b892` save_scene and `faccfcd` GC:

| Run | Old | New |
|---|---:|---:|
| 1 | 62 s | 45 s |
| 2 | 63 s | 44 s |

Codex read the `@@ step light done` lines in `romcheck/t_old1`, `t_old2`, `t_new1`, `t_new2` light.log files.
Claude reported road-sight portions 28.5/29.4 -> 11.3/10.8 s. A separate recorded-call bench changed three two-sample
calls (27.2 s) to one six-sample call (10.4-11.0 s). Those are different timing boundaries.

The earlier **70 -> 52** and **70 -> 55** light-step claims are withdrawn: the 70-second `rsCap` run included a probe
writing roughly 100 MB of pickles. It was not a clean performance baseline. Its captured data remain useful for
correctness replay. The corrected alternating measurements above include three changes, not road sight alone.

GC thresholds `(20000, 20, 100)` are set at the start of `import_classic.main`, after variant validation; importing
the module alone does not change GC settings. Separate site-import-to-exit trials: light 43.5/43.9/44.4 s default
versus 40.8/41.5/41.5 s tuned; build 38.3/38.5 versus 36.2/36.1. Peak working set was approximately 2212 -> 2214 MB
for light and 2782 -> 2788 MB for build, peak commit +3/+9 MB. The roughly 80,000 cycles observed were a measurement,
not a memory bound or a guarantee that arbitrary future workloads have the same behavior.

### What changed, and what was measured only inside a component

The adopted road-sight occlusion walk first tries the leaf that hid the previous ray, then its nearby subtree,
before the remaining tree. Six sample points share one call while preserving the old sums. Its answer can be
checked against cast_one independently of traversal order; the nearest-hit RT bake has different requirements.
The 24.7-million-ray selftest had zero differences, and recorded-call counts matched.

| Commit(s) | Change / reported component observation |
|---|---|
| `172b892` | Faster scene saving; same scene bytes. |
| `f9a4a59` | Coursepatch x-index and skipping unnecessary UV splits; all 1,163 observed light/build split calls identical. Later apply probe 5.8 -> 4.75 s. |
| `5c2f281` | Round texture-stretch counts in C, about 0.3 s saved per process. |
| `426b26d`, `7fb8663` | Seal records in C, radix sorting and five cluster searches. Three-pass components: unique 0.27 -> 0.10 s, joints 0.92 -> 0.55 s, clusters 0.44 -> 0.32 s. |
| `3cc57c6` | load_visual batches/preparation, retaining NumPy compatibility branches: 7.97 -> 4.70 s, split_at_road 3.64 -> 1.11, normalise_uv 0.90 -> 0.33, split_pairs 0.61 -> 0.45. |
| `1777436` | Sky float-to-byte clipping in C; about 0.28 s saved per process. |
| `5368018` | Legacy face smoothing and texture mips in C: face assembly 4.23 -> 2.26 s, make_texture 3.86 -> 1.73, add_scenery 16.2 -> 10.9. |
| `bfcb280`, `fd8707c` | Smoothing cancellation/order correction and actual row-address parity; required for NumPy-compatible results on offset normal buffers. |

These are probe/profile component measurements, not additional independent whole-chain speedups. In particular,
a 48-second cProfile build cannot be compared directly with the earlier unprofiled 39-second build. All changes
were checked against saved light/build baselines by Claude; final chaincheck6 includes the corrections and was
independently hash-compared by Codex. Chaincheck4's mixed pre/post-fix source state is not single-revision evidence.

### Tried and rejected in this batch

- RT nearest-hit remembered-leaf walk: same recorded sample hash `1f26f4c6d8e3c2a1` and 1,392,673 handovers, but
  16-batch time rose from 8.6 to 9.4-10.3 s. Scratch experiment only; it was not adopted in rtbake. Keeping the
  required rays.c leaf semantics matters for cast_one's answers. This failure is not proof that every possible
  exact RT optimization has been exhausted.
- `builduv.uv_split` in add_scenery: values equal in 464/464 calls, but 120 calls changed np.float64 scalars to Python
  floats; large batches were slower (1.91 versus 1.52 s). Not adopted there. Its audited use in other call sites,
  including coursepatch and finishgate, remains valid; matching values alone does not establish caller compatibility.

Scratch evidence tools: `rsbench/bench.py`, `rsdata`, `rtdump`, `lvprobe`, `f2mprobe`, `texprobe`, `sarprobe`,
`splitprobe`, `memprobe`, `gcprobe`, under Claude's session scratchpad. Durable comparison manifests and the
investigation ledger live in `SR3-investigation/import-numpy-audit`. [32](32_session_2026_10_15.md) records the
session's final scope and remaining runtime checks.
