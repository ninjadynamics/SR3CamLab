# Task: repair Classic game-card wraparound and rapid-input selection

## Request and testing boundary

Bruno wants another agent to investigate the native Classic game-selection
carousel. Fix the actual selection/animation behavior; the current workaround
is incomplete. **Do not launch or control the game. Bruno will perform all
in-game testing.** Build, run offline checks, install a concrete candidate and
stop with concise test instructions. Do not repeat the earlier automatic
windowed launches.

Use SR3's existing UI, fonts, card geometry and transitions. A separate custom
menu/overlay was explicitly rejected. Preserve the native reshuffle animation.
Do not alter gameplay, handling, tracks, lighting or POM. Build CPU budget is
all logical processors minus 2 (30 here).

## Latest user findings (authoritative)

Five Classic games in order:
1. SEGA Rally Championship
2. SEGA Rally 2
3. Daytona USA
4. Daytona USA 2
5. Scud Race

Before the last workaround:
- Right on the last game wraps to the first, but SR2 appears in front during
  the reshuffle.
- Left on the first wraps to the last, but Daytona 2 appears in front.
- Fast/repeated input can leave the visual selection on the second or
  second-to-last game rather than the intended endpoint.
- Quick Race's track-card wrap did not exhibit the foreground-video artifact.

**After the currently installed workaround, Bruno reports:**
> the sticky card is gone, but all the preview cards being reshuffled show
> black during the reshuffle. if I press right "too many times" it always end
> up on the second, or second to last game, instead of first or last,
> respectivly.

Interpretation: the unwanted stationary/foreground preview should disappear;
the moving cards in the native reshuffle should retain their artwork. Do not
blank every video surface. Correct rapid-input logical/visual synchronization
in both directions. Determine whether there is a real extra input/repeat or a
visual mismatch; this has not been established.

## Workspace and installed state

- Root: `F:\Jogos\Ultimate Race Lab`; PowerShell.
- Python: `C:\Users\bruno\AppData\Local\Programs\Python\Python311\python.exe -B`.
- GCC: `C:\mingw64\bin\gcc.exe` through repository build helpers.
- Branch `sr3lab`; HEAD `18c723c50e2f4762dbd570637b90e525df25dde6`.
- All frontend integration and fixes since that checkpoint are **uncommitted**,
  including new untracked C sources. Preserve this work; no reset/checkout.
- Installed plugin: `scratchpad/frontend-20261028/hide-shuffle-build/sr3mods.dll`.
  SHA256 `1202b69359fcc158903408ed58885c21ab44ae23bfebe7b3408965d735b8d27d`.
- Installed runtime `game/Rally/dinput8.dll` SHA256
  `8fbb447c60d757fc78df8b5ea25ee3a4776e8a66819d6aab06086c4d1550bd19`.
- Feature enabled by generated `config/frontend-tracks.json`.
- `config/accepted-baseline.json` has installed DLL hashes. Update these when
  installing a replacement; normal PLAY preflight checks them.
- Last install script: `scratchpad/frontend-20261028/install_hide_shuffle.py`.
  Review before reusing; it also recopies the existing runtime DLL and writes
  stale generic live-test wording. It does not run the game.
- Install report: `work/research/frontend-20261028/install-report.json`.
- Original accepted pre-frontend backups:
  `work/research/frontend-20261028/backup/`.
- More recent plugin backups: `scratchpad/frontend-20261028/before-wrap.dll`,
  `before-origin-fix.dll`, `before-hide-shuffle.dll`.
- `RESTORE FRONTEND.bat` uses the verified original backup and removes the
  generated catalog. Do not use it casually: it rolls back the whole frontend.

## Source map

- `source/tools/sr3mods/frontend.c`: native prerace state wrappers; input bits,
  WM_KEYDOWN edges, menu model, delayed page binding, route acknowledgment.
- `frontend_model.[ch]`: game/track catalog, modulo cursor, held-input repeat
  (350 ms initial, 120 ms subsequent), release gating and confirmation.
- `frontend_native.[ch]`: persistent native scene bank, subset rewiring,
  selector labels, carousel notification, latest workaround.
- `frontend_video.[ch]`: relocated native DirectShow video pool, rendering-thread
  preloading and per-menu pinning, eventual decoder eviction after menu exit.
- `source/standalone/runtime.c`: frontend input bridge; menu arrows and Start
  have 80 ms pulses to survive polling; modal WM_KEYDOWN edges are also sent.
  Inspect possible duplicate/stale edges in rapid input rather than assuming
  the visual issue is exclusively animation.
- `pc_live.c`, `pc_frontend.h`: track slot/directory request/ack before confirm.
- `source/standalone/frontend_catalog.py`: builds catalog from installed tracks.
- `source/tools/sr3mods/FRONTEND.md`: architecture notes; latest suppression
  paragraph describes implementation, not a successfully accepted fix.

## Native architecture and addresses

Classic uses the already loaded `ID_PAGE_CARSELECT` and its selector for native
labels, while displaying the native type-11 track-card scene. Quick Race uses
the actual track-selection page. A bank of 14 native cards is built once:
9 track entries + 5 games. Subsets rewire retained intrusive nodes. Maximum
bank 38; video pool 64. Real gameplay track database/IDs remain separate.

Scene layout inferred from executable:
- `+A4` list head, `+A8` end sentinel, `+AC` tail link.
- list entry `+0C` points to card node.
- card `+80`: index; `+B0`: child containing video elements.
- child `+104`: native selected/foreground flag set by `61E6B0`.
- scene `+88`: selected index; `+98`: target movement phase;
  `+9C`: interpolated phase; `+D8`: previous phase; `+B4`: animation active;
  `+DC`: spacing; `+BC/+C0`: range.
- `62A930(cursor)` stdcall notifies active 3D carousel via global `9D6E50`.
- `628DF0` dispatches to `622270`; `622270` computes selected-index difference,
  invokes `621130` and updates selected flags.
- `621130` invokes `61D960(scene, direction, count)` (callee pops 12).
- `61D960` builds per-card reshuffle interpolation paths and sets `+B4=1`.
- `622E40` advances phase; `622FF3..623003` reaches target and clears `+B4`.
- `61DF50` builds/render-orders card geometry recursively; may be relevant to
  the unwanted foreground copy and ordering.
- `6271C0` creates native video elements. Element `+10` is video handle.
- Video-element vtable `6EA2D0`: draw slot `+8` at `6EA2D8` is `621300`.
- `621300` is thiscall with **120 bytes of stack arguments, ret 0x78**; it draws
  a video surface and calls native GetFrame `4DE370`.

Do not treat all prior explanations as proven root causes. A multi-card
endpoint jump is visible in the native code, but why Quick Race works better,
and why rapid input lands on adjacent games, remain unresolved.

## Changes tried and their observed limits

1. Wait for asynchronous ShowPage selector binding. Fixed the original Car A
   label/locked navigation. Notify both selector and native 3D carousel.
2. Native Open creates a stopped DirectShow graph; request Run before first
   frame. Fixed black previews at ordinary menu entry.
3. Preload and pin all current-menu videos (incrementally, render thread).
   Logs confirm all five game videos open at menu entry. Decoder reopening is
   not the explanation for the persistent wrap artifact.
4. Clear stale game-child `+104` flags before selecting a new card. User saw
   improvement, but intermediate video still appeared in both wrap directions.
5. Reset Classic scene `+98/+9C/+D8/+B4` when rebuilding a subset. Did not
   resolve the reported wrap artifact.
6. **Current workaround:** `reshuffling` is armed on logical 4->0 or 0->4.
   Byte-guarded vtable wrapper `preview_draw` calls `hide_game_preview` and
   skips `621300` for *all five game preview handles* while scene `+B4` is set.
   Sticky foreground disappears, but this also blacks all moving cards.
   Replace/refine this approach; do not present it as the completed fix.

The current code still calls 62A930 on cursor changes. Native animations,
logical cursor, repeat pulses/edges and persistent list phase need coherent
handling when new input arrives during a wrap. Avoid stacking speculative
timers or hiding every preview as a substitute for that investigation.

## Video assets

User gameplay clips were trimmed from 00:01 to 00:04: silent, 640x360, 30 fps,
WMV2. Re-encoded directly from originals at q:v=2 with Lanczos downscaling;
user accepted quality and insertion. Installed dedicated game previews:
`game/Rally/frontend/PC/Videos/URL_GAME_{SRC,SR2,DAYTONA,DAYTONA2,SCUD}.wmv`.
Originals: `C:\Users\bruno\Videos\Captures`.
Preparation script: `scratchpad/frontend-20261028/prepare-game-videos.py`.
Do not downgrade compression or overwrite the Mountain track preview.
MP4 has not been tested: native pipeline explicitly builds DirectShow graphs,
so H.264 decoder availability alone does not prove MP4 container compatibility.

## Offline evidence/tools and next steps

`work/research/rally-disassembly.txt` is the full executable disassembly.
`scratchpad/frontend-20261028/inspect_video.py code ADDRESS:HEX_LENGTH` prints
Capstone disassembly from local `game/Rally/Rally.exe` without launching it.
`work/research/track-cards-20261027/` contains older native scene/selector/video
investigation. `scratchpad/frontend-20261028/RESUME.md` is **stale**; this handout
supersedes its installed hashes, lazy-video policy and live-test statements.

Build/check commands (from repo root):

```powershell
python -B source/tools/sr3mods/test_frontend.py --out scratchpad/frontend-next-tests
python -B source/tools/sr3mods/build.py --out scratchpad/frontend-next-build
& source/tools/workspace/play.ps1 -Workspace 'F:\Jogos\Ultimate Race Lab' -Check
```

Latest full build `hide-shuffle-build` passed startup/boot/loader-join checks,
17 camera and 13 live C/PowerShell parity scenarios, delayed Hornet, checkpoint
lifecycle. `hide-shuffle-abi-tests` passed video pool/lifetime/model/native list
checks, actual wrapper stack cleanup/register preservation, native constructor
emulator and catalog tests. These do **not** validate visual reshuffle behavior;
the user's feedback above overrides any optimistic wording in prior reports.

Recommended first step: reproduce logical/visual selection and both wrap paths
offline using native executable replay with repeated/reversed input, including
input while animation is active. Investigate a targeted foreground draw/order
fix that preserves the moving cards' video textures. Build/install only after
checks pass, keep a reversible backup, and hand testing to Bruno.

Acceptance for Bruno: both endpoint wraps keep the native textured reshuffle,
no stationary/foreground intermediate video, correct final game/title/track
confirmation, stable rapid taps/holds/reversals, Quick Race still correct.
