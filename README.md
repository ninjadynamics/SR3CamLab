# Ultimate Race Lab

A modular SEGA Rally 3 mod suite. Public source and documentation live here; your game, imported SEGA content, screenshots, and personal work stay local and are ignored by Git.

Run **SETUP.bat** first. It creates the local folders, builds Race Settings, the standalone runtime, mod DLL, and importer helpers from readable source, and copies your own supported SR3 installation into `game` when needed. Existing content and settings are preserved; replaced binaries are retained in `work`. It does not download anything. A release must include the pinned dependencies and optional Python/compiler toolchain, or those tools must already be configured locally.

After setup, open **settings.exe (Race Settings)** or **PLAY.bat**. Both use the same standalone launch flow. Watchdog is OFF. The locally accepted SRC handling helper is preserved when configured; a fresh installation does not contain SEGA-derived handling or imports.

| Folder | Purpose |
| --- | --- |
| `apps/camlab` | CamLab, its local profiles, and forwarding launch scripts |
| `source` | Readable application code, scripts, and factory templates |
| `docs` | Instructions and knowledge base |
| `toolchain` | Bundled Python/compiler when supplied, plus pinned dependency sources |
| `game` | Private game copy created from your own SR3 files |
| `content` | Imported assets and retained texture/audio sources needed by your mods |
| `config` | Local paths, handling settings, and accepted-file manifests |
| `work` | **Important. Never treat this as disposable.** Blender files, retained research, reference material, and upgrade recovery copies |
| `scratchpad` | Disposable builds, experiments, temporary import outputs, and diagnostic runs |
| `screenshots` | Your captures and sidecars; preserve these |

Your Mountain scenes, including v11 and v13, are in `work/blender`. Do not automatically clean `work`, `content`, `game`, `config`, or `screenshots`.

Texture updates currently use `source/tools/workspace/UPDATE_TEXTURES.bat`. It is a developer convenience, not a root-level end-user command. Texture extraction and update buttons in Race Settings are TODOs. No light bake is needed for a texture-only update.

CamLab source compilation during setup remains an explicit deferred TODO; the existing prebuilt CamLab is retained in `apps/camlab`. TexLab is an idea, not an implemented app. CamLab remains the UI/UX reference for the suite.

See [workspace/setup details](docs/WORKSPACE.md), [the KB](docs/kb/README.md), and [the roadmap](docs/ROADMAP.md). Historical entry points under `source` are retained for reference; use the root SETUP/PLAY and Race Settings for this installation.
