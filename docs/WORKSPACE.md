# Ultimate Race Lab - local workspace

Use PLAY.bat for the accepted standalone setup (profile 2 = SRC handling, watchdog OFF).
Race Settings is settings.exe. It edits settings.yaml; use PLAY.bat afterward for the accepted handling helper. Its own Launch button still launches the native setup without that process-only helper, as before this migration.

UPDATE_TEXTURES.bat uses the existing fast texture updater against this standalone installation and refreshes the launcher's file manifest. Close the game before updating. No light bake is needed for texture-only edits.

- repo: public source and KB (repo/docs/kb). Internal source folders retain their existing names during this filesystem migration.
- game: the playable standalone install, local only. Rally/Rally.exe and sibling Shell/ShellData keep the original package layout.
- assets/tracks/mountain/blender: editable Blender scenes.
- assets/tracks/mountain/textures_hd: Mountain HD PNGs.
- assets/cars/hornet/textures_hd: Hornet HD PNGs (Hornet atlas rebuilding remains its separate tool).
- assets/imported: extracted tracks/cars and their authoring data, local only.
- assets/audio and assets/frontend: local audio/art inputs.
- sources: classic reference data, third-party sources, regression fixtures. ROM libraries stay at their existing external locations.
- work/import: track build outputs, previews and caches.
- work/build: compiled tool caches. work/releases: generated packages.
- work/research: historical experiments and their evidence/rollback files.
- work/runs: new recordings and audit logs.
- backups/vanilla: retained baseline. Historical per-experiment backups also remain in work/research.
- screenshots: local captures and sidecars; never cache cleanup targets.
- config: local workspace configuration and accepted file hashes.

Old SEGA Rally 3 project folders are temporary junctions into this workspace, not duplicate data. They preserve older Blender texture references and diagnostic scripts. Leave them until those historical references are migrated. The original TeknoParrot and GAME folders remain untouched.

Do not run historical restore/install scripts without reviewing their targets. Their old paths may resolve through compatibility links to the active workspace.

The Revo converted/demo reference directories were deleted separately by the owner. Active importer settings no longer refer to them. They are not required to play this installed mod.

SETUP.bat compilation and the public-release layout remain planned work. This is a migration of the existing accepted development setup, not a fresh installer. CamLab source compilation remains a deferred TODO.

The installed mod DLL requires `patches.mod_folder` in local `settings.yaml` to be the absolute path to this workspace's `repo` folder. Update it if moving the workspace; `PLAY.bat -Check` validates this and the mod configuration files.
