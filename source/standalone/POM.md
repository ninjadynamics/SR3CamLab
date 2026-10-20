# Opt-in POM implementation, 2026-10-19

Status: compiled candidate with mocked lifecycle checks and a passing hidden real-D3D9 device test; **live GPU appearance,
shadow matching, handedness and frame cost are not validated**. Nothing installs
or starts the game automatically. This is not the accepted playable baseline.

## First candidate

The paired VS/PS implement 16-step parallax occlusion, bounded grazing-angle and
distance fades, interpolated intersection, explicit gradients, matte normal relief,
original fog/tint/exposure and anchored baked lightmap coordinates. Static and dynamic
shadow equations/coordinates follow the locally inspected `T_Lpse_Tdnl_Sds` pair.
The shadow textures are sampled at the original surface, not the parallax offset.
The image-derived height maps are estimates, not recovered original geometry.

Only an exact shader pair plus a deliberately marked material activates the effect.
Material `gf3ReflCol` at +0x644 carries `(depth_u, depth_v, 1/1024)`; depth must be
positive in at least one direction and bounded to 0.05 UV units. This benign marker
also keeps the original reflection contribution small when the candidate is off.
The SPECM switch (+0x5B4) is cleared only for candidate materials. No shadow,
culling, transparency, mesh or lightmap changes are made. Shader fingerprints are
SHA-256 plus exact bytecode length; original copyrighted bytecode is not shipped.

The first staged family is `tex_s1_x0000_y0000_256x256_c0AE` and its six palette
siblings, 40 material instances. They share one linear BC3 normal-RGB/height-alpha
map, 1024 square, all 11 mips, depth 0.008 UV. Stage size increases from 287.57 to
288.91 MiB, below the accepted 384 MiB arena. No rebake is involved.

## Runtime behavior

Default OFF. Only an exact `SR3LAB_POM=1` environment value at CreateDevice attaches
seven known slots in the original driver vtable, preserving its private extension
and identity. Other devices pass through unchanged. With it absent, no POM draw
hooks or extra per-draw getters run. Engine technique records remain untouched.
Four draw methods are wrapped. A single constant-register read checks each draw for
the marker; qualifying draws check actual shader objects and a full-mip POT DXT5
normal map. This first implementation prioritizes actual state over a speculative
cache, so state-block Apply cannot silently desynchronize material detection.

Shader identity is cached with owned COM references for the last pair only. Around
a qualifying draw, save and restore both shaders plus s1 sRGB/min/mag/mip states.
Force linear normal/height sampling. Existing shader constants and shadow samplers
are not changed. Failed setup falls back to the original draw. Failed restoration
disables substitutions until Reset. The original draw's HRESULT is retained.
State-block recording is bypassed, rather than recording temporary POM bindings.

Reset releases our private shaders and identity cache. External device Release also
releases owned resources before forwarding, avoiding a device/resource reference
cycle; guards cover internal/reentrant release calls. Hooks are restored BEFORE
forwarding external Release, because the driver may free the table with the device.
A nonzero remaining reference count reinstalls the hooks. Private shaders are recreated
lazily. Events are logged once per category, not per frame; counts are logged on Reset.
These callbacks assume the game's render-thread-only D3D use.

## Build and stage

`compile_pom.py` compiles the authored HLSL using Windows D3DCompiler, and regenerates
`pom_bytecode.h`; `--check` fails if the header is stale. The normal standalone builder
then compiles the module and runs `test_pom`, alongside existing runtime tests.
Use at most CPU logical count minus one; this candidate was built with eight jobs
while the user tested the game. Both native GCC and CMake source lists include POM.

`stage_pom.py` requires explicit track, reviewed-map manifest, DDS folder, family
head and a NEW output folder. It reads but never overwrites the track. It rejects
stale source artwork, unsupported materials, ambiguous aliases, non-rock families,
incorrect mip sizes and output paths inside the source track. It checks every output
chunk against the input; only specified material bytes and one new texture differ.

Local candidate output: `scratchpad/pom-implementation-20261019/{runtime,track}`.
The runtime DLL and staged track file must be deployed together for a controlled
future test, with a backup and baseline validation first. Do not replace files while
Rally is running. Normal PLAY currently still uses the accepted runtime and track.

## Checks and remaining work

x86 and x64 mocks cover all draw routes, unmarked bypass, unsupported shader caps,
bytecode rejection, missing mip/format rejection, state blocks, shader/map references,
partial shader/sampler setup failure, original draw failure, restoration failure,
disable/recovery, device reset/recreate and teardown.

`test_pom_device.c` is a separate optional Windows x86 real-driver test using a
hidden 64x64 window. It creates the paired GPU shaders and executes three marked
draws, including after a non-final Release and Reset; checks restored shader
pointers; and releases the device. It requires locally extracted `original-vs.bin`
and `original-ps.bin` in its working directory (not shipped in source). This test
passes, but does not establish in-game visual quality or performance.

The initial copied public vtable caused a first-Clear access violation on the
real driver: private entries beyond IDirect3DDevice9 were missing. Preserving the
original table fixed startup. The real draw test then exposed a second teardown
error: reading hook slots after final Release freed the driver-owned table.
Restoring slots before Release fixed that too. Both failures escaped the mocks.

Before widening scope: test the rock family in-game, log real activation, compare
lighting with POM off, check mirrored UV/normal-Y with an asymmetric pattern, inspect
seams and grazing angles, Alt-Tab/reset and measure frame cost. If the GetFunction
bytecode identity differs at runtime, investigate; do not weaken to a loose match.
Shadow-disabled `_Sd`, `_Ss` and plain variants currently reject safely; add their
own verified pairs if needed. Roads remain unmarked; tune very shallow depth only
after rock validation. Automatic facade height maps need semantic correction and
must follow composition/crop/flip recipes before any facade rollout.


### Stage-loading packaging correction (2026-10-19)

The next user test reached stage loading, then exited 0xC0000005 without a POM
activation log. Static inspection found the staging script appended the normal
texture after the track root: the final chunk became kind 4 (0xc1b00010), replacing
the loader's expected last-chunk root kind 12 (0x65352b89), and 40 material refs
pointed forward. This violates the documented SR3 loader contract (KB01/08).

`stage_pom.py` now inserts the texture before its first material user, preserves
the original root and validates local dependency order again after readback.
`test_stage_pom.py` checks valid insertion and duplicate/unused/forward-reference
rejection. The rebuilt `track-ordered` candidate has the correct root and zero
forward refs; every chunk payload, type, fixup and reference list is identical
to the failed candidate. Only order/alignment changed. Test launcher preflight
passes and normal installed baseline hashes are unchanged. The launcher now
selects `track-ordered`; the previous failed candidate is retained for evidence.
This corrects a demonstrated packaging defect; live loading confirmation remains
pending. Crash itself had no dump, so no fault instruction was recovered.


### State-block hook loss reproduced and repaired (2026-10-19)

Owner reported no crash on the next run (work/pom-tests/20261019-111920-6f2bda).
There were no exit-probe files in that run. Normal files restored. Counters showed
zero marked/replaced draws and froze at 8468 while the game continued. Treat the
previous end-of-race freeze as intermittent/unresolved, not fixed by logging.

A hidden real-D3D9 reproduction established that BeginStateBlock rewrites the
driver table in place, replacing the POM draw and EndStateBlock hooks. EndStateBlock
did not reinstall them. The old test covered state blocks only with mocks.
Now both transitions temporarily restore native slots, call the native transition,
capture the resulting native method table and wrap it again. Recording still skips
POM substitution. Real-driver checks pass five marked draws across Begin/End,
CreateStateBlock/Capture/Apply, non-final Release, Reset/recreation and final release.
Full runtime suite passes. Evidence: stateblock-before.log and
test_pom_device-stateblock-fixed.log in the local candidate folder.

This fixes a proven activation/lifecycle bug, not a proven cause of the prior freeze.
Actual in-game POM activation and another race-end transition still need checking.
Broader material rollout and depth/contrast tuning remain authorized but deferred
until the effect really activates and race-exit stability can be assessed.


## Mountain-wide installation — 2026-10-19

After Bruno approved the live rock-family POM test, relief was installed for normal
PLAY.bat launches. The exact accepted runtime is reused (SHA256
`189cc686a02100d40f341f1cbb2aadca94f5c3a2899ef646879bf7b313db5258`); no further
shader or hook changes were needed. The last live family test recorded 386,272
marked/replaced draws, zero rejected draws, setup failures or restoration failures.
This establishes the family runtime, not a completed stage-wide gameplay test.

Coverage: **411 material instances / 184 diffuse mappings / 143 deduplicated normal-height maps**:
119 rock, 201 facade, 36 roof, 19 grass, 13 cobbles, 8 asphalt, 8 dirt,
2 stone wall and 5 water. Opaque ivy/rock composites are included. Flat signs,
checkpoint/finish banners, sky, vegetation cards and alpha-cutout silhouettes are
excluded. Cutout castle silhouettes remain on their original material path; the
opaque masonry is included. Do not describe this as support for every transparent
surface or every SR3 material technique.

`source/standalone/stage_pom_wide.py` stages without installing. It uses the original
facade triangle UV recipes and overlay transforms to compose **scalar heights**,
then computes normals after composition. This matters for flipped facades: simply
flipping normal-map pixels would leave the tangent direction wrong. Palette siblings
share their chosen geometry head. Facade edges fade to height 1 (the reference
surface), making their parallax displacement zero at the border. Asphalt relief is
very shallow and does not turn skid-mark brightness into potholes. The accepted
simple rock-family DDS payload is reused byte-for-byte.

`pom_maps.py` supplies conservative material-dependent height inference;
`pom_dds.py` encodes continuous height alpha with normal-aware mipmaps. Height is
linear data. The old binary-cutout alpha encoder is unsuitable. New relief maps
are at most 512 pixels per side except the previously accepted 1024-square rock
map. This reduces map memory without touching the installed albedo resolution.
Maps alone add 36.86 MiB; the seven unpacked track SBFs grow from 287.57 to
324.65 MiB, below the retained 384 MiB ceiling.

Verification: all staged chunks read back byte-identically; only normal references,
SPECM and the reserved relief marker changed in selected existing materials.
Original albedo, geometry, collision, RT lightmaps, shadow switches and all other
track files are unchanged. Each new map precedes its users; the original last-chunk
root is retained, with no local forward references. Contact sheets for all 184
mapped images were inspected for spatial alignment and gross relief errors.
The hidden real-D3D9 smoke test passed five marked draws, Begin/EndStateBlock,
Capture/Apply, non-final Release, Reset/recreation and final cleanup. Run this test
outside the restricted sandbox; inside it device creation can fail with
D3DERR_INVALIDCALL before testing POM.

`config/workspace.json` now has `pom: true`. `source/tools/workspace/play.ps1`
sets SR3LAB_POM only for its child launch and restores the prior process environment
in finally. No persistent Windows environment setting is changed. Watchdog remains
OFF and the accepted SRC helper is retained. The accepted file manifest tracks the
installed runtime and main SBF hashes; the normal launcher check passes without
starting the game.

Local stage, map review and complete coverage/exclusion manifest:
`scratchpad/pom-stagewide-20261019/`. Verified pre-install rollback is in
`work/pom-backups/mountain-stagewide-20261019-114637/restore.ps1`; it refuses to
replace files changed after this installation and requires the game to be closed.
The install is backed up; a complete race with the expanded coverage still needs
Bruno's gameplay check. Refreshing source HD art requires rebuilding its relief maps
as well: the source hash guards deliberately reject stale height research assets.


## Live relief controls and visual correction — 2026-10-19

Bruno's screenshot SR3_20261019_120931.png showed apparently flat facades.
Millions of replaced draws with no failures established activation only; they
were not evidence of convincing relief. The original implementation had a
60-world-unit specular-distance fade reused for POM and a grazing fade starting
at cosine 0.28. Both could suppress the effect where it should be inspected.

Current runtime uses projected UV footprint fading, a much narrower extreme-
grazing fade (0.012–0.045), 24–64 ray layers with five binary refinement steps,
and bounded height-field self-shadow on direct light only. Albedo sampler 0
now explicitly uses up to 8x anisotropic minification, linear magnification and
linear mip filtering (capability fallback to linear). Sampler 1 stays linear,
non-sRGB. All modified sampler states, shaders and c30 controls are restored
per draw; restore errors disable relief until reset. OFF uses the same paired
shader and filtering with displacement, normal perturbation and relief shadow
zeroed, so filtering differences cannot be mistaken for depth.

Controls while the game is focused:
- Backtick (` / VK_OEM_3): ON/OFF, ignores keyboard auto-repeat.
- Plus/equal or numpad Add: increase depth by 0.1x.
- Minus or numpad Subtract: decrease depth by 0.1x.
- Range 0.0–4.0x; starts ON at 1.0x on launch. Session-only; reset/Alt-Tab retains
  the choice. High settings can stretch/disocclude window artwork; 1.0x is the
  tested starting point, not a claim that all higher values look good.

Window input only changes atomic integers. No input polling helper or watchdog
was added. The render thread draws a cached Segoe UI label into the backbuffer
through the existing frame callback. In-game verification exposed that SR3 can
leave an offscreen post-process render target bound: drawing onto that target
made the label invisible despite a passing simple GPU fixture. The HUD now
explicitly binds the backbuffer, removes the depth target, and restores target,
depth surface, viewport and complete graphics state afterward. No retained state
block; HUD texture is released on resource reset and device cleanup. Real-driver
regression now includes an offscreen target with pointer equality after HUD draw.

Height map provenance: the previous maps were filtered luminance heuristics;
facades detected coherent dark rectangles, missing many windows/arches. Purple
RGB encodes tangent-space surface normals for lighting, while grayscale scalar
height lives in continuous BC3 alpha. Neither is recovered true geometry.
`facade_relief.json` now defines visually authored source-space bounds for 182
window/door openings across 21 facade heads. `pom_maps.facade_height` makes
coherent beveled recesses and shallow jambs; local brightness contributes only
a small mullion correction. Roof/wall texture noise does not become facade depth.
Palette siblings reuse the head. The exact facade/crop/mirror recipes compose
scalar heights before normal generation. Default facade UV depth is 0.012;
other material depths and original accepted rock DDS remain unchanged. Natural
material heights still use band-limited luminance inference, not semantic
geometry; do not call those physically accurate depth reconstructions.

`stage_pom_wide.py --base-main <verified pre-POM main SBF> --fresh-facades`
rebuilds from the clean track payload rather than appending another map set to
an already modified SBF. Final coverage remains 411 materials / 184 mappings,
with 138 deduplicated maps and 323.72 MiB unpacked seven-track total. No albedo,
geometry, collision, RT/lightmap, handling or other track files changed.

Validation: full runtime tests pass; real-D3D9 tests pass seven marked draws,
state-block recording/replay, HUD controls, offscreen target restoration,
non-final Release, Reset/recreation and final cleanup. All 182 authored opening
centers remain recessed (caught and repaired an accumulation error during staging).
Matched real-GPU renders of an actual facade at OFF/1.0x/2.5x show displacement,
with identical albedo/filtering/camera. Visual review reduced excessive mullion
height and refined ray intersections. This fixture is not a full-stage drive.
Live windowed launch verified backtick, keyboard increase, visible label and
normal exit of the first test. Final game left to Bruno at OFF 1.0x after user
input was detected; full race and final artistic acceptance remain pending.

Evidence: scratchpad/pom-live-relief-20261019/ (gpu-comparison.png, game-label.png,
gpu-lifecycle.log, render-checks.json, track-final/stage-report.json).
Verified pre-change backup: work/pom-backups/live-relief-20261019-124321/restore.ps1.
Older hard-coded linker-offset probes must NOT be used with this rebuilt runtime.
The new capture-game.py uses only the exported backbuffer API, no private offsets.


## Source-pixel facade masks and material tuning — 2026-10-19

Bruno accepted rock at 4.0x and facades at 1.0x, but rejected approximate
facade depth placement. `facade_semantics.py` replaces the old normalized
opening rectangles and whole-image luminance guesses with manually authored
source-pixel masks for all 21 HD heads. Doors, glass, shutters, blind panels,
arches, ledges and balcony rails use different heights. The rose-window
tracery is selected inside its explicitly reviewed ellipse; fine ironwork is
selected only inside reviewed rail regions, excluding broad dark doors.
Paint, lettering, stains and stone grain do not become facade recesses.

Palette children share the source head's geometry. Scalar height passes through
the installed facade/overlay crop and mirror recipes; normals are calculated
after composition. 117 texture mappings cover 201 facade materials. All 21
native-resolution source overlays and all 117 composed overlays were inspected.
Source coordinates are carefully authored, not a mathematical pixel-perfect
segmentation guarantee: small ornamental relief remains approximate, and BC3
compression/mips limit runtime precision. Final aesthetic acceptance needs a
gameplay check.

The runtime recognizes the reserved .008 UV rock profile and applies a 4x
material gain; other profiles start at 1x. Thus the accepted rock map remains
byte-identical and both its normal and parallax components receive the same
gain as the user's successful 4x test. Live +/- changes the global multiplier;
effective material gains are capped at 4x. HUD shows actual Rock / Facades
values. Backtick compares ON/OFF with identical albedo filtering.

Evidence: `scratchpad/pom-facade-semantic-20261019/review.html`,
`validation.json`, `gpu-lifecycle.log`, `track/stage-report.json`.
All 1,005 protected non-POM chunks remain byte-identical, including albedo,
geometry and lightmaps. Total track unpacked size 324.23 MiB; full-mip DXT5
normal/height payloads 36.44 MiB. Runtime/input/capture tests pass, including
draw-time gain checks and state restoration. Real GPU state blocks, offscreen
HUD, reset and final release pass. Blender's unwanted old geometry and stray
shadows are deferred and separately reminded; no geometry changed here.


## Optimized tuned POM and FPS counter — 2026-10-20

This supersedes the live-tuning description above. Approved family gains are
stored in config/mountain-pom-depth.yaml and baked into per-material depths.
Backtick and +/- tuning remain disabled. A top-right FPS counter measures
present callback frequency over half-second windows; it is not simulation FPS.

Height-ray samples use explicit derivative-derived mip LOD. Adaptive 8–48
steps, two binary refinements and bracket interpolation replace the previous
24–64 steps and five refinements. Self-shadow uses four taps and reuses the
final normal/height sample. Albedo filtering and original-UV cutout alpha remain.
A 16-entry COM-owned shader-pair cache includes rejected pairs. Sampler writes
are skipped only when actual device state already matches; restoration and
reset cleanup remain mandatory. Maps, approved depths, RT, geometry and timing
settings were not changed.

Matched 3840x2160 hidden D3D9 fixtures measured 49–53% less shader GPU time
across rock, facade, asphalt and fence. This is not an in-game FPS measurement
or a claim of identical pixels. Before/after images were visually inspected.
Native tests, real GPU state-block/offscreen-overlay/reset/release checks and
normal launcher validation passed. No game launched for this installation.


### FPS timer lifecycle correction � 2026-10-20

The first FPS build stayed at `FPS --` in game: non-final device Release
invokes resource cleanup, which incorrectly also reset the sampling clock.
Resource cleanup now preserves FPS timing. Attach and device Reset still reset
it. The real-driver regression performs a non-final AddRef/Release after every
HUD update and requires a positive reading after half a second; both runs pass.
Runtime logs include HUD calls, successful draws, stage/error and FPS tenths.
Depths, shader bytecode and timing settings were not changed by this fix.


### Green grass/rock exclusion and global attenuation � 2026-10-20

The c1A6 variant of tex_s1_x0000_y0000_256x256 uses the ordinary shader:
16 material payloads restored exactly from the v19 RT base; all other chunks
unchanged. config/mountain-pom-depth.yaml records excluded_variants, and the
wide stager resolves exact palette variants through derived/composed recipes.
Other palette variants of this family retain POM.

Plus/equal or numpad Add increases global relief by 0.1; minus or numpad
Subtract decreases it. Range 0.0�1.0, initial 1.0 each launch, no auto-repeat.
The top-right FPS label also displays Depth. Approved per-material depths are
multiplied directly, including normal relief; obsolete .008 UV rock gain
heuristics were removed. Native tests check both endpoints and half gain.


### True 0.0x baseline � 2026-10-20

0.0x now returns from the draw hook before constant reads, shader identity,
map checks, sampler changes or shader substitution. Native draw methods run
with the original shaders/state. The FPS overlay stays active and labels this
POM OFF. 0.1�1.0 re-enables POM. FPS averaging restarts on gain transitions.
The baseline retains installed HD assets, geometry, RT and height-map memory;
it measures bypassing POM, not the unmodified retail game.
Four-route mock tests prove zero constant reads/sampler writes/replacements at
zero and successful re-enable. Hidden real GPU tests show replaced=0. One
matched 4K rock fixture measured 0.292�0.302 ms native shader time versus
~1.16�1.20 ms with POM; this is not whole-game FPS. Live comparison remains
necessary: same view, wait for the FPS window to settle, compare 0.0 and 1.0.


### Shader creation churn correction - 2026-10-20

The live game rebuilt the POM shader pair roughly once per frame because its
ordinary non-final device Releases cleared the draw-hook cache. Reproducing
this in a one-pixel real-D3D9 fixture cost 9.40-9.62 ms per iteration; timing
isolated about 9 ms in CreateVertexShader/CreatePixelShader. Lowering depth
could not remove that CPU/driver cost.

The accepted fix uses native texture private data (D3DSPD_IUNKNOWN) to retain
the compiled pair with game-owned height textures. It does not retain those
textures or skip device Release cleanup. Private data releases its shader
references with the texture; an attach-generation tag prevents reuse across
attachments. GetPrivateData returns owned references for the draw cache.
No guessed device refcount threshold is used. The proposed threshold shortcut
was rejected and never executed. GPU shader bytecode remains byte-identical.

100 non-final Release/draw iterations now cost 0.37-0.46 ms each, with only
two shader creations total. Real device tests pass state-block recording,
full state capture/apply, offscreen HUD, reset/recreation and zero references
at final device destruction. Runtime regressions and launcher validation pass.
Full-game 60 FPS still needs the user's test. Approved YAML, track, albedo,
height/normal maps, RT lighting and normal display settings remain unchanged.
Evidence: scratchpad/pom-fixed-cost-20261020-165527/install-report.json and
scratchpad/pom-performance-20261020/cache_lifecycle_final/.


## Native library integration and YAML — 2026-10-20 (current)

The runtime now links `pom_native.c`, not `pom.c`. POM installs no D3D draw,
state-block or Release hooks and owns no GPU shader objects. The native kind-3
loader creates and releases the records in `shaderlib3_uber_data.sbf`. All 726
original shader records are preserved; only `T_Lpse_Tdnl_Sds` selects the added
pair. The extra `url_pom_controls_v1.fx` effect holds 0.0–1.0 variants. At a frame
boundary, the existing capture callback selects native technique record pointers
only after a gain change or Reset. 0.0 selects the exact original VS and PS.
This still uses the standalone runtime's existing frame/control infrastructure;
it is not a claim that all game hooks have been removed.

`config/mountain-pom-depth.yaml` remains the settings source:

- `global_depth_initial` is read once on device creation, from the configured
  `patches.mod_folder`. Supported values are 0.0–1.0 in steps of 0.1.
- `live_tuner` controls +/- input. Current start is 0.6 and live tuning is on.
  Missing/invalid startup settings disable relief and log the error. No file
  access occurs in a draw or idle frame callback. Edits take effect on restart;
  this is not file hot reload.
- `families`, `excluded_variants`, height directory and normalization are consumed
  during map staging (`stage_pom_wide.py --tuning ...`). These values are baked
  into normal/height textures and material constants, not parsed per draw.
  Changing them requires map restaging and native integration. Merely changing
  an exclusion must not be presented as a live material update.
- `pom_native_config.py` checks the installed receipt against YAML before PLAY.
  Stale family settings or exceptions fail preflight with a restaging message.
  `integrate_pom_library.py` independently audits the YAML-staged material report,
  recipe-resolved exclusions, depth constants and normal/height payload hashes.
  Current audit: 38 families, 391 active materials, 16 excluded c1A6 materials.
  FPS overlay and measurement remain off; unsupported enable requests are rejected.

Native normal-map dimensions come from small uniform BC3 metadata textures in
the unused specular slot s2. Four endpoint bits encode width/height powers of two
without sensitivity to sRGB conversion. Existing albedo, heights, normals,
lightmaps, geometry, collision, timing and handling are unchanged by integration.

Rebuild sequence:
1. For family/exclusion changes, stage maps with `stage_pom_wide.py --tuning`
   from the verified clean RT base and matching texmap/review export.
2. Run `integrate_pom_library.py --source-library ORIGINAL.sbf --source-track
   YAML_STAGED.sbf --material-report STAGE_REPORT.json --out NEW_SCRATCHPAD`
   (optional `--tuning` / `--texmap`). Never use an already integrated library
   as the original input. Original bytecode identity and reserved IDs are checked.
3. Copy the generated `pom_native_layout.h` into source and rebuild the runtime.
   Deploy library, track, DLL and generated `pom-native-install.json` receipt
   together after backup; update accepted-baseline hashes.
4. Run `pom_native_config.py --workspace ROOT` and normal PLAY `-Check`.

Evidence is in `scratchpad/pom-native-library-20261020`: prior matched 4K real-GPU
comparisons of rock, facade, asphalt and fence produced zero pixel difference
from accepted POM at 0.6. Native library startup was observed with `applied=6`
and zero POM draw hooks before the user requested no further game launches.
Offline controls tests cover gain selection, original zero pair, Reset, idle,
YAML start values and invalid/missing YAML. A mocked registry is deliberately
allocated away from low-address loader/heap allocations in the test only.
Actual Mountain rendering and race performance await the user's test; these
checks do not prove timer, stutter, frame-rate or all-track behavior.

Pre-integration backup:
`work/pom-backups/before-native-library-20261020-192155`.


## Mountain relief page: automatic Apply — 2026-10-20

Run `RELIEF.bat` at the workspace root to open the local relief editor
(`http://127.0.0.1:8768/`). It displays installed YAML family gains, starting global
depth, the +/- toggle, and per-variant exclusion checkboxes. `Apply to game`
saves a staged YAML and automatically calls `stage_pom_wide.py` then
`integrate_pom_library.py` when material settings differ. Global-only changes
skip map rebuilding. No action launches the game. The old file page has an
editor link which transfers its notes/camera locally via a URL fragment.

`relief_apply.py` uses hash-pinned rebuild inputs in `work/pom-native-inputs`.
The clean RT base and the original shader library are separate from installed
assets, so repeated Apply never accumulates POM maps. The review-track snapshot
matches the export's original texture metadata and identity. Rebuilds run below
normal priority with bounded math-library threads. Native layout must match the
installed runtime header before deployment; family edits require no DLL rebuild.

Apply checks the YAML/receipt/baseline revision before and after building and
checks accepted game hashes. Invalid values, unknown variants and stale tabs
are rejected. A localhost-only server uses exact Host/Origin checks and a
per-session token for writes. It serves only its page, preview assets and API,
not arbitrary workspace files. A single Apply runs at a time.

Installation backs up every changed file under `work/pom-backups/page-apply-*`,
atomically replaces each file, checks its hash and restores the entire set on
failure. A journal blocks PLAY during commit or after an interrupted commit.
The game must be closed at preparation and commit, and is checked between file
replacements. This is not a cross-file OS transaction; a hard process/power
failure leaves the recovery journal and complete backup. Do not remove the
journal without restoring/validating that backup.

Validation: a real staged family-depth change rebuilt maps and native shaders
with 391 active and 16 excluded materials; a UI Apply with current approved
settings completed and saved a verified backup. Tests cover bad/stale payloads,
running-game refusal, successful deployment and injected mid-install failure
rollback. Preview rendering is approximate; gameplay/performance acceptance
remains with the user. Removing POM draw/Release hooks addresses measured hook
overhead but does not establish that all sources of stutter are gone.
