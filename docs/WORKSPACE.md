# Workspace and setup

The Ultimate Race Lab root is the Git repository. `source/` and `docs/` are public; the local folders are excluded by `.gitignore`. There is no nested `repo/` directory and no compatibility directory links.

## User workflow

1. Extract a prepared release into a writable folder. The source ZIP alone requires separately supplied Python/compiler and pinned SDL/raylib sources; the legacy release packager still needs updating for this layout.
2. Run `SETUP.bat`. When there is no local game, it asks for the original SR3 Rally folder. The supported executable hash is verified before copying. Sources are never modified.
3. Open `settings.exe` (Race Settings), or `PLAY.bat`. Save & play now uses the shared workspace launcher and its optional accepted handling helper. Watchdog remains OFF.
4. CamLab stays in `apps/camlab`. Its existing binary uses forwarding scripts to launch with its selected/unsaved camera profiles without replacing saved settings.

Setup builds the runtime, native launcher, Race Settings, mod DLL, watchdog host, and importer helper DLLs. Building the watchdog does not enable it. Native tests and C/PowerShell patch-equivalence checks must pass before installation. It defaults to two compiler workers. CamLab source compilation is deferred; include the existing prebuilt CamLab when packaging.

`SETUP.bat --check` checks the compiler and pinned source dependencies without building. `--configure-only` creates/repairs local paths while preserving user edits. `--build-only --jobs 2` builds and tests without replacing game binaries. `--game-source "path to Rally"` supplies a game source without prompting. Replaced installed binaries go to `work/setup-<timestamp>/`.

## Local data

- `work/` is **important and never disposable**: `work/blender/` contains all Mountain scenes (v11, v13 and edit history); retained research, reference fixtures, vanilla recovery data and migration audits also live here.
- `scratchpad/` is disposable: compiler caches, temporary import outputs, experiments, diagnostic logs and recordings. Rebuild/reimport as needed after removing it.
- `content/` holds retained imported tracks/cars, HD textures and audio sources. Installed texture maps must never depend on scratchpad data; Daytona's retained texture sources are in `content/texture-sources/`.
- `game/` holds the local Rally/Shell/ShellData package. It is not a build cache.
- `screenshots/` holds user captures and sidecars. Never include it in cache cleanup.
- `config/import.json` is the importer configuration. `config/workspace.json` selects the game and optional accepted SRC helper. Local root `settings.yaml` is Race Settings' configuration.
- Camera profiles are shared between CamLab and the game via `apps/camlab/profiles.yaml`. The installed mod DLL uses absolute `patches.mod_folder` (`config`) and `profiles_file` paths. Rerun setup after relocating the workspace.

The convenience texture updater is `source/tools/workspace/UPDATE_TEXTURES.bat`; `-Check` verifies source paths without modifying textures. Planned Race Settings extraction/update buttons are not implemented yet.

`work/layout-20261017/` records directory moves and byte-preservation checks. Historical scripts under `work/research` may contain old paths: they are retained evidence, not supported entry points. Do not run restore/install experiments without reviewing their targets.
