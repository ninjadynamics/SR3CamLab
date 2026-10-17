# Ultimate Race Lab workspace migration

## Final layout (2026-10-17)

The Git repository is the Ultimate Race Lab root. Public code moved into `source/`, KB and instructions stay in `docs/`. CamLab is in `apps/camlab`; the native launch helper is in `apps/runtime`. `settings.exe`, `SETUP.bat`, and `PLAY.bat` are the user entry points.

Local game and imported assets live in `game/` and `content/`. `work/` is important and never disposable: it contains Blender scenes (including v11/v13), retained research, reference fixtures, vanilla recovery files and former backups. `scratchpad/` is disposable builds, temporary imports and diagnostics. Screenshots remain local in `screenshots/`. All these local payloads are Git-ignored. The initial 39 internal junctions and five old-project compatibility junctions were removed; their target data was retained.

The physical move verified 28,591 protected files unchanged with no missing files. Both active Blender scenes contain packed images and needed no path edits. Every Blender file remains byte-identical. The rebuilt runtime and mod DLL also match the accepted installed binaries byte-for-byte. The accepted generated SRC candidate remains local under `content/handling/`.

SETUP creates local folders, preserves edited profiles/settings/content, builds runtime/settings/mod/helper components, runs their native/equivalence checks, and keeps replaced binaries under important `work`. CamLab's binary is unchanged and its launch contracts are preserved by ordinary forwarding files. Source compilation for CamLab stays TODO. Race Settings now uses the same handling-aware launcher as PLAY; no watchdog is enabled by setup. The texture updater lives under `source/tools/workspace`; Race Settings texture extraction/update buttons are deferred TODOs.

See [WORKSPACE.md](../WORKSPACE.md) for setup and [ROADMAP.md](../ROADMAP.md) for remaining release-packaging work. Local audit evidence is in `work/layout-20261017` and build checks in `scratchpad/setup-build.log`. No game was launched during this reorganization; owner gameplay confirmation remains pending.

## Initial migration and launch correction (historical)

The first migration introduced a nested repo folder and compatibility links. That was replaced with the final layout above following Bruno's correction. Its first launch exposed two issues: a relative mod folder failed from the game's working directory, and direct PowerShell invocation of a GUI launcher left LASTEXITCODE unset. The current launcher validates absolute mod/config paths and waits for the native launcher process using Start-Process -Wait -PassThru. Native patch planning reproduced the original missing-profile failure and passed with the corrected configuration.

The Revo converted/demo reference folders were deleted separately by the owner. They were rebuilding/comparison inputs, not prerequisites for playing the installed mod; stale configuration was cleared. No recovery is claimed.
