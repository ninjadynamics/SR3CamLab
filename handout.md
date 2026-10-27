# Ultimate Race Lab: first public release handoff for Claude

Prepared on **Friday, 2026-10-23**, Europe/Warsaw. Repository and local state were inspected on this date. This is a handoff for release preparation, not a claim that the public package has passed acceptance.

Building-scene status updated on **2026-10-27**: Bruno accepted v22 after his manual corrections. It is now the authoritative patch-3 source and installed as Mountain R4 after the complete R4B/RT/lightmap chain; live testing of this rebuilt version is pending.

## 1. Bruno's goal and confirmed scope

Bruno wants the first public release of **Ultimate Race Lab (URL)** this Friday. The implementation already exists in various parts of this workspace; the task is to make it a complete, reproducible, usable release.

His latest clarification explicitly includes **HD textures, the custom shader, and SRC handling**. Do not quietly omit these to meet the date.

Required features:

1. Standalone SEGA Rally 3, independent of TeknoParrot.
2. Accepted quality-of-life and stability patches, including startup improvements.
3. Camera patches and profiles, with CamLab functionality accessible to users.
4. Importing tracks from SEGA Rally Revo, both PC and PS3 sources.
5. Importing **only Mountain** from SEGA Rally Championship (SRC, Model 2).
6. Importing SRC music and co-driver audio from the user's source files.
7. Mountain's complete numbered patch chain, R4B rounding, RT bake, lightmap extraction and installation.
8. Verified checkpoint placement and race progression on the supported imported tracks.
9. All cars unlocked in all modes.
10. The accepted **HD texture set**.
11. The accepted **integrated custom relief/POM shader**, its authored maps, YAML settings and exceptions, and its configuration workflow.
12. The accepted **SRC handling**, including the later steering, low-speed wall-response and opponent-speed fixes.

Bruno identified missing/temporary menu art and awkward UX as unfinished work. The previous assistant recommended a **0.1 Public Preview**, a feature freeze and a clean-install go/no-go. That version label was a recommendation, not an explicit user decision.

Daytona and the other SRC tracks are outside this release scope. Daytona's invisible wall was fixed, but Bruno explicitly deferred its remaining problems. Do not expose unfinished experiments as supported release features. Do not remove his local experimental installs just to hide them in the public UI.

## 2. Workspace and source control

- Actual repository: `F:\Jogos\Ultimate Race Lab`.
- The coding shell may start in `F:\Jogos\SEGA Rally 3`; **that is not the URL repository or current standalone installation**. Set the working directory explicitly.
- Current branch: `sr3lab`.
- Current HEAD: `bce531d` — `Fix SRC race balance, startup, and classic-track collision boundaries`.
- Current standalone game: `game/Rally` underneath the URL repository.
- Entry points: root `SETUP.bat`, `PLAY.bat`, `settings.exe`, `RELIEF.bat`.
- Public code/docs: `source/`, `docs/`. Repository skills: `source/skills/`.
- Local, Git-ignored data: `apps/`, `config/`, `content/`, `game/`, `work/`, `scratchpad/`, `screenshots/`, `toolchain/`, root `settings.yaml`.

`work/` is important authored/research data, **not a disposable build directory**. Preserve Blender files, source textures, semantic height maps, reference fixtures and current rebuild inputs. Even old scratchpad paths must be checked for active dependencies before cleanup.

### Existing uncommitted work: preserve it

The following changes already existed before this handoff. They belong to the daylight/sunset lighting work and its documentation. Do not reset them or accidentally present them as new release work:

```text
 M docs/kb/16_lighting_shadows_lightmaps.md
 M docs/kb/17_mountain_build_notes.md
 M docs/kb/21_track_install_and_switching.md
 M source/skills/blender-track-patch-install/SKILL.md
 M source/skills/blender-track-patch-install/references/pipeline.md
 M source/tools/import/core/import_classic.py
 M source/tools/import/core/rtbake/rt_compose_game.py
 M source/tools/import/core/rtbake/rtcompose.c
 D source/tools/import/src/tracks/courses/src_1.low.recipe.json
 M source/tools/import/src/tracks/courses/src_1.recipe.json
 M source/tools/import/stack.py
?? source/skills/blender-track-patch-install/references/lighting-variants.md
?? source/tools/import/core/rtbake/lighting_tone.py
?? source/tools/import/core/rtbake/test_lighting_tone.py
```

Recheck status when picking up: other work could have happened since this snapshot. Keep the accepted runtime and installed content intact while preparing an isolated release candidate.

## 3. What is accepted, and what is still pending

### Accepted behavior to preserve

- Bruno confirmed standalone runs **"smooth as silk"** after the physical-core allocation and relief idle-callback fixes. Do not reintroduce the previous per-draw shader interception path or change accepted game affinity casually.
- Startup is accepted with **no blue cabinet screen**, and a faster PLAY launch. Real hardware/resource readiness remains checked; the fixes remove presentation/dwell and launcher overhead, not actual initialization.
- SRC steering is accepted as **"PERFECT"**. The low-speed wall response was subsequently accepted too.
- The excessively fast Lancia opponent was finally accepted as fixed. Preserve the final speed-envelope implementation, not an earlier engine-power-only attempt.
- The repeated-race checkpoint-time regression was fixed and Bruno reported no issues.
- The separate white-screen-after-second-race loader deadlock has a diagnosed fix and an offline regression. Its KB section still says specific live second-race confirmation pending; keep that scenario in release acceptance rather than assuming a later general success message proves it.
- FPS overlay and FPS measurement are **off**. Watchdog is **off** by default.

Evidence: the latest dated sections of `docs/kb/08_exe_loading.md`, `game-runtime-and-frontend.md`, `28_handling_flavors.md`, `29_src_steering_code.md`, and `20_launcher_inmemory_patches.md`.

### Mountain lighting and source version

The retained installed Mountain is **Mountain R4**, original sun direction `[0.0, -9.4, 3.4]`, elevation about **70.1148 degrees**, original lighting colours. The 35-degree sunset was rejected and its generated variant was deleted. Earlier 45/48-degree alternatives are retired. Do not restore them from historical instructions.

Current recipe: `source/tools/import/src/tracks/courses/src_1.recipe.json`.

Important accepted settings:

```text
round=4, round_slide=false, round_crease=80, round_tol=2, round_cap=1.5
bake quality=slow, compose=0.34, light_split=0.72
bake.canopy=perforated
lm_terrain_classes=[grass]
road_verbatim=true
boundary_inset=0, boundary_step=1, boundary_union=true
```

Perforated ray-only tree canopies and grass lightmap receivers must survive rebuilding. The visible tree artwork is not punctured. Keep the finish/checkpoint banner in front of its posts, and preserve the later tunnel/tree/texture repairs.

**Installed build now uses Bruno's corrected v22.** Patch 3 was regenerated and independently replayed byte-identically to its 84,279 canonical source triangles. All 2,092 changed triangles survive the real chain and cleanup. The road, runtime, HD art and relief YAML remain unchanged. See `work/research/mountain-v22-r4b-20261027/install-report.json` and `docs/kb/17_mountain_build_notes.md` for provenance and the cleanup fixes. Original 70-degree daylight, R4B, perforated canopy shadows and grass receivers are installed; 22 lightmap pages, final heap 324.0385 MiB. Launcher and staged config-page checks passed without launching the game.

| Editable scene | SHA-256 | State |
| --- | --- | --- |
| `work/blender/mountain.patch3.v20.blend` | `2b6a65ebe82add758dfd698a1b046fc055f30e343ead02f9f56b0ca98b529bb0` | Historical accepted source; superseded by corrected v22 |
| `work/blender/mountain.patch3.v21.blend` | `461b89e71eee6c1e9cbd9cebf0c87e1584603ebddb512421a504a58f5f210d15` | Roof simplification accepted; incorporated into later corrected v22 |
| `work/blender/mountain.patch3.v22.blend` | `2cf672dafc99e9b309205152a6c64a9d7f3e6e4d77ea8504651f4f2786e98223` | Owner-corrected authoritative patch-3 source; rebuilt and installed 2026-10-27; live test pending |

v21 contains 40 simplified flat-top roofs plus 26 further roof sections. Second pass reduced 959 triangles to 379, preserved 190 wall-contact vertices, and had a maximum sampled surface difference of about 3.3 cm. Earlier repairs remain. Gameplay road unchanged. Final course has 84,891 triangles.

Roof evidence: `work/research/mountain-v21-roofs-20261021/`, especially `additional-roofs/validation.json`, `coverage-validation.json`, and solid/wire/textured screenshots. V22 evidence is in `work/research/mountain-v22-buildings-20261025/`, including `final-validation.json`, `surface-audit.json`, reproduction scripts and before/after views. V22 replaces 2,710 building triangles with 2,109; the final course has 84,290 triangles, zero loose edges, no duplicate new triangles and no detected coplanar overlap above the audit's 0.02 m² threshold. Roof forms and eaves are intentionally regularized, so this is not a zero-deviation remesh. Those counts describe the earlier inspection snapshot. Bruno then corrected it manually; the accepted source exports 84,279 triangles and has completed patch extraction, rebuilding and installation.

## 4. Confirmed release gaps and practical priorities

### A. Release packaging is currently incomplete

`docs/WORKSPACE.md` explicitly records that the legacy packager needs updating. Inspection confirms `source/tools/release.py` still stages the old layout (`tools/python`, `tools/mingw`, old repo-root assumptions) and assumes local compiler paths. It is not a ready URL release command.

`SETUP.bat` delegates to `source/tools/workspace/setup.ps1` and `setup.py`. It builds the runtime, launcher, Settings, mod DLL and importer helpers, but needs Python/compiler and pinned SDL/raylib sources. On this machine `toolchain/` currently contains `deps/`; Python and GCC come from external local installations. A new user cannot rely on those.

CamLab source exists in `source/src/camlab.c` with `Makefile`/`build.bat`, but the unified setup does not compile it. It warns that the existing binary must be supplied. Resolve this within the chosen release build/package policy and ensure profiles and forwarding scripts are included.

Do not copy this machine's `config` wholesale into a release: it contains absolute game, ROM, Python, compiler, Blender and MAME paths. Produce appropriate templates and discover/select sources during setup.

### B. All three newly confirmed features need a reproducible asset/build path

HD artwork, approved relief heights/review metadata, and the accepted SRC native payload exist locally outside Git. Merely zipping tracked source does not deliver them.

Inventory the exact required inputs and provide a supported delivery/reconstruction path. Follow the project's existing source/asset separation policy in `README.md`, `.gitignore` and `docs/ROADMAP.md`; do not bundle Bruno's game install, ROMs, full imported tracks, screenshots or personal settings. **Do not silently fall back to SD textures, generic grayscale heights or an older handling flavor.**

The HD/relief artwork is authored work. A normal user installation must not depend on regenerating it interactively with an image model. Resolve the release asset mechanism explicitly while preserving the required feature scope.

The complete Mountain release path must include operations currently done by retained wrappers: correct patch chain, R4B, RT, HD-safe packing, extracted lightmaps, native relief integration, receipts/pins/baseline, installation. A successful `stack.py` run alone does not demonstrate every later integration step.

### C. Provide a coherent user workflow

Minimum practical flow: **Setup -> select owned sources -> Import -> Configure -> Play**.

The current Settings app covers display, controls, game and advanced settings; import/audio/camera/texture workflows still span separate tools. Root README calls texture update UI buttons TODO. Surface existing functionality through clear entry points; avoid a large redesign before the release gate is proven.

Show required input formats, supported game version, build/bake progress and errors, disk requirements, and a useful recovery path. Make Mountain-only SRC scope explicit. Accurate track labels/cards and understandable controls matter more than finishing every decorative asset for a preview.

### D. Validate advertised routes and modes, not just conversion success

REVO conversion has strong file-level evidence and some tracks were driven. This audit did **not** establish every route's checkpoint correctness or complete race behavior. Old KB pages contain contradictions and stale "pending" notes; check current evidence/code before treating them as live bugs.

Create a per-route matrix covering source platform, conversion/install, checkpoint positions/triggers, time awards, lap/finish behavior, AI progression, and at least one completed run for supported routes. Align visible banners with actual gameplay triggers, not only scenery coordinates.

The all-car-list patch exists (`source/tools/build_carlist.py`, `source/tools/sr3mods/pc_live.c`). Release testing must cover actual selection and race entry across Championship, Quick Race and Classic, including repeated sessions. A visible menu entry alone is insufficient.

### E. Freeze and rehearse the actual archive

Build an isolated release candidate, extract it into a different path with spaces, and use only the package's declared dependencies and explicitly selected user sources. Ensure it does not accidentally load Bruno's `config`, `work`, compiler, old SR3 folder, emulator installation or scratchpad artifacts.

The decisive release gate is **a clean-install rehearsal of the downloadable package**, followed by the targeted gameplay matrix. Do not call a run against the already-working development tree a clean install.

## 5. HD textures: preserve the known fixes

Read the repository skill `source/skills/faithful-texture-upscaling/SKILL.md` and its `references/sr3-integration.md` before touching artwork or packing.

- Target artwork: general **3x**, minimum side **256 px**, facades **4x**, preserving aspect ratio. Engine storage dimensions are a separate concern.
- Retained texture sources are under `content/` (including `content/classic/courses/src/course1_mountain/` and `content/texture-sources/`); use current texmaps/manifests to resolve the final authored files rather than assuming an older scratchpad set is canonical.
- Non-power-of-two mip tails caused an engine-specific DXT upload mismatch. The accepted solution uses safe power-of-two storage and compatible mip payloads while retaining source detail.
- Exact duplicate texture consolidation reduces memory without reducing resolution. Do not substitute lossy downscaling or arbitrary atlas repacking.
- Sum the unpacked bytes of **all seven track SBFs**, not only the main file. Preserve the guarded **384 MiB track arena** runtime fix; the old 256 MiB arena crashed larger HD builds. Historical v20 native-relief totals were about 323 MiB; recalculate for the release candidate.
- Black/neon-green ivy patches were traced to contaminated opaque RGB artwork, not a blanket alpha failure. The accepted repair preserved alpha and changed only the diagnosed source mask. Carry that artwork forward.
- LIBRARIE text orientation is deliberately corrected without mirroring the entire facade. Keep the accepted version.
- Preserve road paint; the request to flatten skid marks applied to skid marks only.

## 6. Custom shader: current architecture and settings

Read the latest sections of `docs/kb/24_shaders.md`, especially **Native library integration and YAML**, **Mountain relief page: automatic Apply**, and **Native relief idle callback**. Earlier hook-based POM experiments are historical.

- Runtime uses `source/standalone/pom_native.c`, not the old `pom.c` interception path.
- Shader records are integrated into the game's native shader library. POM no longer owns per-draw/state-block/Release hooks or GPU shader lifetimes. This does not mean the standalone runtime has no hooks at all.
- Canonical local config: `config/mountain-pom-depth.yaml`.
- Current values: `global_depth_initial: 0.6`, minimum `0.0`, maximum `1.0`, `live_tuner: true`, `fps_overlay: false`, `fps_measurement: false`.
- +/- adjusts global relief. **0.0 selects the original shader pair**, providing an actual bypass rather than merely zeroing depth while paying the full shader cost.
- Preserve all approved family gains and `excluded_variants: tex_s1_x0000_y0000_256x256_c1A6` (the green-rock variant on the large grass plateaus). Do not substitute old default 1x/4x guesses for the tuned YAML.
- Current receipt: `config/pom-native-install.json`; snapshot reports **390 active materials and 16 excluded materials**. Older docs report 391 for older builds: use current matching metadata and explain changes.
- Height/review inputs referenced by YAML: `work/pom-tuning/20261020/height` and `work/pom-tuning/20261020/review-export.json`.
- Clean native integration inputs: `work/pom-native-inputs/clean-rt.sbf`, `shaderlib3_uber_data.sbf`, `pins.json`. They must match the current track and remain separate from already-integrated outputs.

`RELIEF.bat` opens the localhost editor at `http://127.0.0.1:8768/`. Apply stages the YAML, rebuilds materials/maps and integrates when necessary, updates the receipt/baseline and installs with backups. Global-only changes avoid unnecessary map rebuilds. Editing family gains or exclusions is not per-frame YAML hot reload: the page performs the required restaging for the user.

Preserve guards against stale tabs, wrong source hashes, running-game installation and interrupted commit journals. Applying a depth change must not silently restore old collision geometry, old lighting or an old patch version.

Primary source files: `relief_apply.py`, `relief_page_server.py`, `stage_pom_wide.py`, `integrate_pom_library.py`, `pom_native_config.py`, `pom_native_layout.h`, `reviewed_relief.py`, `surface_relief.py`, `relief_normalization.py`, and `shaders/` under `source/standalone/`.

Facade depths were visually authored for architectural features, not simply converted from brightness. Preserve windows/doors, masonry joints, the deeper library awning, corrected fence polarity, and skid-mark treatment. See `source/skills/facade-relief-mapping/`.

## 7. SRC handling: use the final accepted implementation

- `config/workspace.json` currently selects `content/handling/src-candidate.json` as its accepted helper candidate.
- The launcher uses `source/tools/handling/candidate_host.py`; inspect the candidate's references and accepted hashes to locate its actual payload/source dependencies. Do not assume `flavor_src.json` alone recreates the final behavior.
- Final opponent-fix blob accepted on 2026-10-21: SHA-256 `dd5326fc43b5e531c0495316012c260aa90761b541999c7cb8253518512d640e` (recorded in KB 28).
- Relevant retained evidence: `work/research/src-ai-pace-envelope-20261021/`; final steering/contact fixes are documented in KB 29 sections 17-18.
- Preserve player/AI ownership guards, fresh versus replay behavior, the contact-slip fix, low-speed/reverse wall response, and native SR3 handling when SRC is not selected.
- The final AI governor limits actual acceleration/forward speed for identified local AI under SRC; the earlier engine-power-only adjustments did not fix the Lancia. Do not regress to those.
- Fresh setup deliberately does not enable an arbitrary candidate merely because a file exists. Build/derive and verify the required accepted payload, then configure it through a supported installation step.
- Local `config/handling.json` currently has default `sr3`, ST205 mapped to `src`, and C4 mapped to `realism`. This is Bruno's personal selection, not an instruction to impose Realism or these per-car choices on every public user. SRC must be available and usable in the release.

Relevant code: `source/tools/handling/`, `source/tools/workspace/play.ps1`, `launch_session.py`, and the mod runtime. Source/build recipes for any remaining ignored native payload must be brought into the supported reproducible flow; copying only an opaque local JSON reference is insufficient.

## 8. Mountain rebuild and install rules

Use the repository skill `source/skills/blender-track-patch-install/SKILL.md` with `references/pipeline.md` and `references/lighting-variants.md`. The latter supersedes older retired lighting notes.

1. Pin the accepted saved Blender source and materials/provenance. Preserve manual work and the gameplay road.
2. Preserve the accepted corrected v22 patch-3 package and its source/chain proofs. Future rebuilds must preserve earlier patches and verified legacy removals that keep repaired trees and facades intact.
3. Replay the **entire** patch chain and prove exact source reconstruction before R4. Compare canonical face records including positions, winding, multiplicity, UVs and material identities. Do not equate a visually similar result with byte identity; distinguish canonical mesh identity from Blender container bytes and later game quantization.
4. Synchronize the zipped chain, unpacked JSON and unpack manifest. Local loose patches are ignored by Git; a changed loose JSON alone does not ship the fix.
5. Rebuild using the current R4B parameters and 70-degree recipe. Retain authored material labels: missing labels previously created enormous false tree canopies and shadowed half the stage.
6. Bake RT with perforated ray canopies and grass receivers, compose, build, preserve HD-safe packing and native shader integration.
7. Extract the **final encoded lightmaps** and record source chunk/hash provenance.
8. Validate protected road/gameplay chunks, alpha, texture references, collision boundaries, memory budget and installed hashes.
9. Update the matching clean RT base, review pins, relief receipt, accepted baseline and menu/switch metadata coherently. Exercise a staged relief Apply to prove it cannot revert the new track.

Normal users consuming the prepared patch chain should not need Blender merely to import Mountain. Blender is for authoring/extraction/optional exports unless a specific verified build dependency proves otherwise.

The gameplay road is explicitly protected. Do not move/remesh it to solve visual scenery defects. Boundary fixes must preserve native road support and operate on the intended boundary data; avoid reintroducing the old inset or internal folded-road walls.

## 9. Suggested execution order and acceptance checklist

1. Inventory accepted runtime, sources, maps, textures, candidate payloads, current hashes and existing dirty files. Produce a short concrete plan without reopening accepted artistic/physics choices.
2. Fix the release packager and dependency layout. Finish the missing reproducible paths for CamLab, HD/relief assets and SRC handling.
3. Consolidate the existing setup/import/configure/play entry points and supported-feature selection. Document user source requirements and minimum hardware/OS actually supported. Check CPU instruction requirements of compiled helpers against that claim.
4. Use owner-corrected v22 as the settled patch-3 source and the 2026-10-27 installed rebuild as the current content candidate; obtain its in-game acceptance before the release freeze.
5. Run focused build/regression checks, then the isolated archive rehearsal. Repair failures before broad live testing.
6. Validate gameplay with Bruno, record results per route/mode, and prepare release notes/known limitations plus archive hashes. Do not label an unchecked feature as tested.

Required acceptance evidence:

- [ ] Clean archive setup with no TeknoParrot and no developer PATH/dependencies.
- [ ] Supported source detection and actionable rejection of unsupported/missing inputs.
- [ ] REVO PC and PS3 import paths, including all routes advertised as supported.
- [ ] SRC selection limited to Mountain; music/co-driver import and correct switching verified by listening.
- [ ] Full Mountain chain/source proof and explicit provenance of the chosen saved scene, including the status of the requested v22 follow-up.
- [ ] R4B, original 70-degree RT, perforated tree shadows, grass receiving, final lightmap extraction.
- [ ] Accepted HD artwork survives packing; all mip layouts and total track memory checked.
- [ ] Integrated shader renders, YAML gains/exclusions apply, +/- works, zero bypass works, overlay/measurement remain off.
- [ ] Accepted SRC player behavior, crawl/reverse wall contact and fair opponent pace; native handling still works.
- [ ] Correct checkpoint triggers/banner positions, time awards, lap/finish and AI progression per supported route.
- [ ] Cars selectable and able to start races in every supported mode.
- [ ] Camera profile selection/save and launcher forwarding work after relocation/setup.
- [ ] Consecutive races, retry/continue, game over, loading and normal exit do not freeze; no second-race timer regression.
- [ ] Vanilla tracks/cars remain smooth; startup has no blue screen; no unintended background watchdog/FPS polling.
- [ ] Recovery from failed/interrupted import/apply and return to vanilla are clear and tested where supported.
- [ ] Final archive contains intended files only, with versions, dependency notices, checksums and concise instructions.

## 10. Navigation, checks and working preferences

Read first: `README.md`, `docs/WORKSPACE.md`, `docs/kb/34_workspace_migration.md`, and the latest dated KB sections relevant to the change. `docs/kb/OPEN_QUESTIONS.md` is an old inventory, not a current release-blocker list.

| Area | Start here |
| --- | --- |
| Packaging/setup | `source/tools/release.py`, `source/tools/workspace/setup.py`, `setup.ps1`, `test_setup.py` |
| Standalone runtime | `source/standalone/BUILD.md`, `build.py`, `cpu_affinity.c`, `settings_ui.c` |
| Launch/preflight | `source/tools/workspace/play.ps1`, `launch_session.py`, `test_launch_session.py` |
| Core mods | `source/tools/sr3mods/build.py`, `pc_live.c`, `loader_join.h`, `test_checkpoint_reload.py` |
| CamLab | `source/src/camlab.c`, `source/tools/workspace/camlab_play.ps1`, `apps/camlab/profiles.yaml` |
| REVO | `source/ps3conv.cs`, `source/revofix.cs`, `source/extras.ps1`, KB `ps3-to-pc-conversion.md` and `13_revo_vs_arcade.md` |
| SRC/Mountain | `source/tools/import/stack.py`, `core/`, `src/tracks/courses/`, KB 17/21/30 |
| Audio | `source/tools/audio/src_audio.py`, `src_music.py`, `source/tools/sound_copytest.ps1`, KB `audio.md` |
| HD | `source/tools/workspace/update_textures.py`, `source/tools/import/core/hd_textures.py`, KB 23/35 and the upscaling skill |
| Shader | `source/standalone/` files listed above; `test_native_yaml_receipt.py`, `test_native_library_controls.py`, `test_relief_apply.py`, KB 24 |
| SRC handling | `source/tools/handling/`, current candidate references, KB 28/29 |

Useful **no-game-launch** checks, after selecting the intended workspace and Python:

```powershell
Set-Location -LiteralPath 'F:\Jogos\Ultimate Race Lab'
git status --short
.\SETUP.bat --check
.\PLAY.bat -Check
python source/standalone/pom_native_config.py --workspace 'F:\Jogos\Ultimate Race Lab'
```

These have different purposes: dependency availability, launcher preflight, and native YAML/receipt consistency. Passing them does not replace a clean-install test or a race. Inspect each tool's help/build instructions before running mutation commands in a staging workspace. This handoff did not rerun the entire test suite.

Bruno's preferences:

- Be practical and move quickly; do not repeatedly ask permission for routine authorized work.
- Keep progress updates concise and distinguish offline proof from in-game observation.
- Keep the PC responsive. His standing clarification is that "all cores" means leave one free; his latest explicit full bake request used **all logical cores minus two**. Use the latter for heavy bake work unless he changes it. This is separate from the accepted game's CPU affinity.
- Use hidden windows for background helpers and keep diagnostics bounded. He may need the PC while work proceeds; do not unexpectedly take it over for a play test.
- Keep skill files in `source/skills/` and update relevant skills/KB when procedures or findings change.
- Preserve his source files, screenshots and existing settings. Do not perform speculative broad cleanup.

## Handoff status

The preceding work was a read-only release assessment, followed by creation of this handoff. No release-preparation implementation, fresh full bake, game launch, commit/push or public publication was performed as part of writing it. The main definite gap is the outdated package/dependency path; other release gates above require evidence rather than being declarations that the accepted game is broken.
