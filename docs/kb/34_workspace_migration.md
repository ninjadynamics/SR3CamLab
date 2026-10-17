# 34. Local workspace migration (2026-10-17)

The suite's development workspace moved from the TeknoParrot tree to `F:/Jogos/Ultimate Race Lab`. The original TeknoParrot installation and `GAME` remain where they were. This is a filesystem/path migration, not the unfinished SETUP.bat installer or internal source-code restructuring.

## Everyday entry points

- **PLAY.bat** at the workspace root: accepted process-only SRC handling, watchdog OFF. Select profile 2 in the game. It validates accepted file hashes before launching.
- **settings.exe**: edit Race Settings. Its own Launch button still bypasses the handling helper; use PLAY.bat afterward. This pre-existing integration limitation is explicitly retained, not reported fixed.
- **UPDATE_TEXTURES.bat**: existing texture-only fast lane for installed tracks, followed by updating the local launch manifest. Close the game first. Hornet atlas generation remains its separate tool.
- **screenshots/**: local captures and sidecars, outside Git and outside the game. Both capture implementations derive this from the parent of the configured `repo` mod directory. START's render-hook repair still requires live confirmation.

## Where files live

| Purpose | Workspace path |
|---|---|
| Public source, scripts and KB | `repo/`, `repo/docs/kb/` |
| Standalone game package | `game/Rally/`, with sibling `game/Shell/` and `game/ShellData/` |
| Mountain Blender scenes | `assets/tracks/mountain/blender/` |
| Mountain HD PNGs | `assets/tracks/mountain/textures_hd/` |
| Hornet HD PNGs | `assets/cars/hornet/textures_hd/` |
| Imported track/car authoring data | `assets/imported/` |
| Local audio and frontend art | `assets/audio/`, `assets/frontend/` |
| Reference extracts, dependencies, regression fixtures | `sources/classic/`, `sources/dependencies/`, `sources/fixtures/` |
| Import outputs/previews/cache | `work/import/` |
| Compiled caches and release packages | `work/build/`, `work/releases/` |
| Historical experiments, evidence and per-experiment rollback files | `work/research/` |
| New run records | `work/runs/` |
| Retained vanilla baseline | `backups/vanilla/` |
| Local configuration and accepted hashes | `settings.yaml`, `config/` |

Texture convenience folders and legacy paths are junctions to a single data copy. The old `SR3CamLab`, `SR3 track format`, `SR3-investigation`, `SR3Lab Art` and `Screenshots` entries under the old tree are compatibility junctions. They preserve Blender's embedded texture paths and historical tools; do not recursively delete through them. No physical project data remains in those old entries. Audit all historical restore/install script targets before use: their old paths can now reach the active workspace.

## Configuration and evidence

The importer now supports separate `work_root` and `classic_root` settings, preserving previous defaults when omitted. Its local `sr3_game` selects the standalone `game/Rally`. The standalone Blender preview resolver honors the same classic-data setting. Existing installed texture maps were rebased; an obsolete Daytona `repo/scripts/classic_tex` reference was corrected to retained local texture sources. No track or texture was rebaked, and accepted runtime/game binaries and handling payload stayed identical.

The handling host and read-only recorder are now public source under `tools/handling/`; the accepted generated payload remains local in `assets/handling/`. Workspace launcher/texture wrapper sources and batch templates live in `tools/workspace/`.

The owner separately deleted the three external Revo converted/demo reference directories. They were comparison/rebuild inputs, not prerequisites for playing the installed mod. Their stale active settings were cleared; no recovery is claimed.

All 37,801 inventoried files matched SHA256 after the first 34 directory moves, before configuration changes. Three further same-drive moves retained the original Rally/Shell/ShellData sibling layout. Final protected-file verification, junction audit and exact mapping are local in `work/runs/migration-20261017/`. All 25 SRC integration checks and eight Hornet mip cases passed from the migrated repo. Launcher checks and both texture-source checks passed without launching the game or taking desktop captures. Live gameplay remains for the owner to confirm.

See [WORKSPACE.md](../WORKSPACE.md) for local usage and [SR3Lab-plan.md](../SR3Lab-plan.md) for remaining refactor/installer work. CamLab compilation through SETUP.bat remains a deferred TODO; the existing binary was retained unchanged.

## First-launch correction

The first owner launch exposed two gaps in the offline migration check. The installed patch DLL interprets `patches.mod_folder` from the game working directory, so relative `repo` failed to load `profiles.yaml`. Local settings now use the absolute workspace repo path, and the wrapper rejects relative paths and checks the camera and handling configuration files. Keep this absolute path updated when relocating the workspace.

PowerShell's direct GUI executable invocation also left `LASTEXITCODE` unset, falsely reporting launch failure and stopping the handling helpers. The wrapper now starts the native launcher with `Start-Process`, waits for that launcher process to exit, and reads its actual exit code. It does not wait for the game to close. Runtime binaries and handling data remain unchanged.

Verification: the installed DLL's offline plan reproduced the missing-profile error (exit 1) from the real game working directory before the correction, then generated its camera patch plan successfully (exit 0) afterward. The workspace preflight also passed. No game was launched during these checks.
