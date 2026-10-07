# TexLab - design plan

*Part of the SR3CamLab / UltimateSR3 suite. Plan only: no code exists yet.*

TexLab is a fly-around texture painter for imported classic courses. You fly through the
track, point the crosshair at a wall, and spin the mouse wheel to give it another texture
from SEGA Rally Championship (SRC), SEGA Rally 2 (SR2) or SEGA Rally 3 (SR3). It replaces
the frozen hand-curation lane (`13_retexture.md`: label CSV, contact sheets, rebuild,
render) with direct manipulation.

How to read the confidence tags: **CHECKED** = I read it in the repo or knowledge base
while writing this plan; **ASSUMED** = not checked, must be confirmed before building on
it; **SPIKE** = needs an experiment, usually one in-game test.

Contents: [1 Goals](#1-goals-and-non-goals) · [2 Technology](#2-technology) ·
[3 Data model](#3-data-model) · [4 Interaction](#4-interaction-design) ·
[5 Session log](#5-the-session-log) · [6 Picking](#6-picking-and-selection) ·
[7 Transforms, lighting, world](#7-texture-transforms-vertex-lighting-sky-sea-lighting) ·
[8 Fidelity and round trip](#8-preview-fidelity-and-the-round-trip) ·
[9 Milestones](#9-milestones-risks-open-questions)

---

## 1. Goals and non-goals

### v1 (SRC Mountain only)

- Load SRC Mountain exactly as the importer builds it: all faces textured, sky, sea, road.
- Fly with WASD and mouse, crosshair in the middle.
- Backtick cycles select mode: Off, Mesh, Face, World (World is my addition, for sky / sea /
  road / light; see 4.3).
- Change the texture of a mesh or a face from three libraries (SRC, SR2, SR3), with a
  vertical strip of 32 px colour thumbnails.
- Move, rotate and scale the texture on a mesh, then refine single faces.
- Infinite undo / redo with camera jump, autosave, save / load / reload / defaults.
- Session log with the 3-second settle rule.
- Every action has a key. No modal dialogs. Nothing destructive that undo cannot bring back.
- Export the result into the real track through `import_classic.py` (milestone v2 below; it
  is part of "TexLab 1.0", the milestones just order the work).

### Not in v1

- No geometry editing: TexLab never moves, adds or deletes a face. This is also what keeps
  the no-z-fight rule safe (overlay lifts and layer stacking stay the importer's job).
- No other course or game as the *track* (the libraries of all three games are available).
- No painting of texels, no texture import from arbitrary files.
- No physics changes: road surface ids are never changed (the texture id selects the
  physics, `10_surfaces.md`).
- No in-game live preview. The game is tested by the user from the cabinet.
- Per-vertex colour gradients (see 7.4: the mesh format in use has no colour channel).

### Later versions

| Version | Adds |
|---|---|
| 1.1 | The other three SRC courses (course picker), favourites, camera bookmarks |
| 1.2 | SR2 courses as tracks |
| 1.3 | Vertex colours / glow if the spikes in 7.4 succeed; light-map baking |
| 2.0 | SR3's own tracks as editable tracks (needs the scenery instance lists, not decoded) |

---

## 2. Technology

### 2.1 What CamLab is (CHECKED)

CamLab is **one C99 file** (`src/camlab.c`, 2249 lines) on **raylib 5.5**, statically linked
into `camlab.exe` by `src/build.bat` or `src/Makefile` (w64devkit that ships with raylib).
The exe is git-ignored and published as a release download; the source is in the repo. It
is not PowerShell and not WinForms. Its conventions, which TexLab copies:

| Convention | CamLab | TexLab |
|---|---|---|
| Window | resizable, MSAA 4x, vsync | same |
| DPI | `S = max(1, GetWindowScaleDPI().x)`, every size through `U(x) = x*S` | same; thumbnails are `U(32)` |
| Font | Segoe UI from `%WINDIR%\Fonts`, raylib font as fallback, sizes baked at `size*S` | same |
| Colours | panel `20,22,28 a228`; text `236,238,244`; sub `158,164,178`; faint `104,110,124`; accent orange `255,138,76`; green `76,196,120`; blue `64,140,255` | same constants |
| Shapes | rounded panel on the right, rounded buttons, pills in the top-left HUD | same |
| Unsaved value | orange, with a reset icon | orange dot on changed meshes / faces in the panel, reset icon |
| Tooltips | hover anything for a plain-words explanation | same, plus the key for it |
| Keys | Tab panel, F12 screenshot `camlab_<time>.png` | Tab panel, F12 `texlab_<time>.png` |
| Files | plain YAML subset next to the exe, hand-editable, `defaults.yaml` for resets | same idea (3.2) |
| Launch | blue Launch button runs `PLAY.bat` | blue "Send to game" builds; Launch stays the user's action |
| Command line | `--shots`, `--seed`, self-test build | `--shots`, `--selftest` (9) |

### 2.2 Options weighed

| Option | Fits "same UX/UI as CamLab" | Suite rules | Cost | Verdict |
|---|---|---|---|---|
| **C99 + raylib, `src/texlab.c`** | Identical: the UI code is copied from `camlab.c` | Same standing as CamLab: source in repo, exe built by `build.bat`. An exe, but a transparent one | Lowest. Textured meshes, mip-maps, alpha test, shaders, mouse capture and ray picking are a few calls each | **Recommended** |
| C# compiled at run time (`Add-Type`, as `menuart.cs` / `ps3conv.cs` already are) + OpenGL by P/Invoke in a WinForms window | Look must be re-drawn by hand to match | Best for "transparent scripts": no exe at all | High: no UI kit, no font / texture / input layer; all of it written from scratch on raw GL | Runner-up, only if "no new exe" is a hard rule |
| PowerShell / C# + WPF `Viewport3D` | WPF look, not CamLab's | Script only | Medium to write, but poor result: hundreds of materials, no mip control, weak mouse capture, slow hit testing | Rejected |
| Python + moderngl / pyglet | Look re-drawn by hand | Needs pip packages on the user's PC | Medium; the pipeline is already Python (3.11 with numpy and Pillow is installed here) | Rejected for the app; Python stays the pipeline |
| Local web view + three.js | HTML look | Needs a shipped JS library or a CDN, plus a local file server | Medium; pointer lock and file writing are awkward | Rejected |

Rendering load is not the deciding factor. The scene is about 15k quads (hi model 14,955
faces CHECKED, plus fill, backdrop and about 1,400 sea quads), 157 SRC tiles and a 2048 x
1024 sky. Batched per texture that is a few hundred draw calls: 60 fps on integrated
graphics in any of these stacks. The deciding factor is the UI: only the raylib option
gets CamLab's look and feel for free.

### 2.3 Recommended split

```
texlab.exe  (C99 + raylib)      viewer + editor. Reads a scene cache and PNG files,
                                 writes the project file and the session log.
                                 Never parses a SEGA format.
texlab_scene.py                  Python, beside the importer. Dumps the scene cache and
                                 the texture libraries from the user's own extracts.
import_classic.py --texlab X     Python, existing importer + one new stage: applies the
                                 project file and builds the real track.
TEXLAB.bat                       launcher: builds the cache if missing, starts texlab.exe.
```

What it costs:

- A second exe in the suite (same SmartScreen note as `camlab.exe`), built from source.
- About 400 lines of UI code duplicated from `camlab.c`. Later they can move to a shared
  `src/ui.h`; not in v1, so CamLab is not touched.
- Python 3 with numpy and Pillow is needed for the cache and for export. It already is
  for the classic importer.
- A small text parser on both sides (C and Python) for the project file.

---

## 3. Data model

### 3.1 The scene cache (generated, never shipped, never edited)

One function in Python produces the final face list: the same list `stage_build` hands to
`BC.add_scenery` (`faces + sky + extra`: hi model after `load_visual`, near backdrop, fill
geometry, sea sheet). `texlab_scene.py` dumps that list; the exporter consumes that list.
One source, so what TexLab shows is what gets built.

Location: `SR3CamLab\texlab\cache\src_mountain\` (git-ignored, like `sounds/` and
`codriver/`: data derived from the user's own copies).

| File | Content |
|---|---|
| `scene.txt` | one line per face: `id`, `mesh id`, original texture key, flags (cutout, two-sided, overlay layer, kind: scenery / backdrop / fill / sea / road-decal), 3 or 4 corners, UVs. About 3 MB, parsed in milliseconds |
| `sky.txt` + `sky_0.png`, `sky_1.png` | the slot's dome mesh (572 vertices, two groups) and the two painted dome pictures from `sky1995` |
| `road.txt` | the SR3 road strip as plain triangles with a flat colour per surface, for display only |
| `world.txt` | lighting set values, sea level / cell / tile, fog, course centre, start position |
| `hash.txt` | hash of the inputs; the project file records it (3.3) |

The 4-tuple face format `(material, section, [xyz], [uv])` stays as it is in the importer.
Ids are computed from it (3.3), not threaded through it.

### 3.2 The project file (the editable document)

`SR3CamLab\texlab\projects\Mountain 1.texlab` - plain text, a YAML subset like
`profiles.yaml` (no lists, no anchors, one value per line), sorted by id so diffs stay
small. It stores **only what differs from the original**.

```yaml
texlab: 1
course: src/1                      # game / course number, as import_classic takes them
scene: 5f3a9c12                    # hash of the scene cache it was authored on

world:
  sky: SRC/mountain/sky            # or SRC/desert/sky, SR3/Lakeside4/sky, slot
  sea.texture: SRC/mountain/tex_sea_blue_64x64_c1DF
  sea.level: -0.5
  light.ambient: 0.40 0.41 0.43
  light.sun: 1.00 1.00 1.00
  light.scale: 1.00 1.00 1.00
  light.tint: 0.40 0.40 0.40
  light.fog: 0.62 0.70 0.78
  road.tarmac.tint: 0.42 0.45 0.52

mesh obj_1262:c0E0:3 @ -212.40 31.05 -405.10:      # id, then anchor (centre, metres)
  texture: SR3/Canyon4/53850d6a
  map: tile 7.0                    # keep | fit | tile <metres per repeat>
  move: 0.250 0.000                # in repeats
  rotate: 23                       # degrees
  scale: 1.10 1.10
  tint: 1.00 0.95 0.90             # flat colour multiplier, 1 1 1 = none

face obj_1262#0037 @ -210.02 33.50 -404.88:
  texture: SRC/mountain/tex_s1_x0576_y0512_128x128_c0E0
  rotate: 90                       # on top of its mesh's transform
```

A face entry overrides its mesh for the keys it names and inherits the rest. Unknown keys
are kept on load and written back, so a newer file survives an older TexLab.

Factory state = an empty document. "Back to defaults" clears it (as one undo step).
`texlab\projects\defaults\` can hold named starting points later (the same role as
`defaults.yaml`).

### 3.3 Stable ids

| Thing | Id | Example |
|---|---|---|
| Original face | section object + ordinal of the `f` line inside that `o` block of the hi OBJ | `obj_1262#0037` |
| Piece cut by the importer (road strip, long faces) | parent id + piece number | `obj_1262#0037.2` |
| Backdrop / fill / sea face | source + ordinal | `sky_1#0102`, `fill.skirt#0412`, `sea#0031` |
| Mesh | section + short original tile code + ordinal of the patch (patches ordered by their lowest face ordinal) | `obj_1262:c0E0:3` |

Every entry also carries an **anchor**: the centre in metres, to the centimetre. On load
and on export each entry is resolved in this order: exact id; else the face or mesh with
the same original texture whose centre lies within 5 cm of the anchor; else it is an
**orphan**. Orphans are listed in the panel ("3 changes lost their wall"), kept in the
file, and never dropped silently. This is what lets a document survive a re-import that
renumbers faces, as long as the geometry did not move.

If the cache hash differs from `scene:`, TexLab says so in a banner, resolves by anchor
and carries on.

### 3.4 Texture libraries

A texture has a key `GROUP/SET/NAME`:

| Group | Sets | Source on this PC (CHECKED) | Count |
|---|---|---|---|
| SRC | mountain, desert, lakeside, forest | `classic\courses\src\<course>\textures\*.png`, `materials.json` (size, alpha flag) | 157 for Mountain |
| SR2 | the five courses | `classic\courses\sr2\course0..4\textures\` | 34 to 45 each |
| SR3 | Alpine4, Canyon4, Desert4, Lakeside4, Stadium4, Tropical4 | decoded by `sr3_art.py` into `work\retex\art\<Track>\<id>.png` from the user's `master_gfx_xdata.sbf` | 2 to 463 each |

`texlab_scene.py --libraries` writes per set, into `texlab\cache\lib\<GROUP>\<SET>\`:

- `index.txt`: key, width, height, has-alpha, mean colour, category, display name.
- `thumbs.png`: one atlas of 64 x 64 cells. Drawn at `U(32)`: sharp up to 200 % scaling.
  Cut-outs are composited on a checker so their shape reads.
- The full-size PNGs stay where they are; `index.txt` holds the path. TexLab loads them on
  demand (Mountain's own tiles at start, anything else when it is first shown large or
  applied) and keeps a least-recently-used cache on the GPU.

Details:

- SR3 files contain normal maps, light-map pages and atlases. The indexer lists only
  textures that some scenery material uses as diffuse (material word `+0x1BC`), and marks
  atlases (pieces of windows and doors) as such.
- Categories seed from `work\retex\tile_labels.csv` (rock, roof, cobbles, house_plaster,
  tree ...). The panel gets a category drop-down. Names shown to the user are the category
  plus a number ("Rock 12"), with the real key in the tooltip and the log.
- Nothing in `texlab\cache\` or `texlab\projects\` ships. The release zip holds
  `texlab.exe`, `TEXLAB.bat` and the docs. A missing library shows as an empty group with
  one line telling how to make it.

### 3.5 How the document feeds `import_classic.py`

New, additive, and off unless asked for: `python import_classic.py src 1 classic --texlab
"<project file>"` (or `"texlab": "<path>"` in `work\courses\src_1.json`).

1. `stage_build` builds the face list as today.
2. New module `texlab_apply.py`: assigns ids and meshes (same code as the cache dump),
   resolves the document, and returns the faces with the assigned texture key and the final
   UVs (transform applied, 7.1). Faces without an entry pass through untouched.
3. `add_scenery` gets a mode that groups by **assigned texture + flags** instead of the
   original tile, and resolves a key to a texture chunk:
   - SRC / SR2: PNG to DXT1, or DXT5 when it has transparent texels, through the existing
     `make_texture` / `make_texture_dxt5` (VIVID gamma as today for classic tiles).
   - SR3: the chunk is copied byte for byte from the user's own game file, as `retex` mode
     already does.
   - Material: the cloned Uber material, with alpha test + two-sided for cut-outs.
4. `world` keys map onto existing course-JSON keys: `lighting`, `sea`, `sky`, `road_tint`,
   `road_tile_repeat` (all CHECKED in `stage_build`).
5. The build report lists orphans and every face that had to be cut for UV range.

Without `--texlab` the importer behaves exactly as now.

---

## 4. Interaction design

### 4.1 Screen

```
+--------------------------------------------------------------+-------------------+
| [FLY] [MESH] [FACE] [WORLD]   Mountain 1 *   10 m            | Group  [ SR3   v] |
|                                                              | Set    [Canyon v] |
|                                                              | Kind   [ rock  v] |
|                                                              | +----+            |
|                          ( + )                               | |tex | Rock 11    |
|                  Rock wall - 38 faces                        | |tex | Rock 12  < |
|                  Rock 12 (SR3 Canyon)                        | |tex | Rock 13    |
|                                                              | +----+            |
|                                                              | Move  0.25  0.00  |
|                                                              | Turn  23 deg      |
|                                                              | Size  110 %       |
|                                                              | Save Reload Reset |
|  Hold E and spin the wheel to change the picture       [F1]  | Send to game      |
+--------------------------------------------------------------+-------------------+
```

- Top left: mode pills (the active one in orange), project name (`*` and orange when
  unsaved), pick distance.
- Centre: crosshair and a two-line label of what it selects.
- Bottom: **one hint line** that always says the most useful next step for the current
  state. It is the main noob-friendliness device.
- Right: the panel (Tab hides it). Three drop-downs, the vertical thumbnail strip (32 px
  relative to DPI, the current texture centred and enlarged to a 128 px preview beside it),
  transform read-outs, buttons.

### 4.2 Two mouse states

- **Fly** (default): the cursor is hidden, the mouse looks around.
- **Free**: Esc releases the cursor to click the panel; a click in the 3D view goes back
  to Fly. Everything in the panel also has a key, so Free is never required.

### 4.3 Select modes (backtick cycles, Shift+backtick goes back)

| Mode | Crosshair selects | Then |
|---|---|---|
| Off (FLY) | nothing | just fly |
| Mesh | the whole patch under the crosshair within the pick distance | texture and transform apply to every face of it |
| Face | one face within the pick distance | overrides on top of its mesh |
| World | sky, sea or road under the crosshair at any distance; Up / Down also step through Sky, Sea, Road tarmac, Road gravel, Sun, Shade, Fog, Tint | E + wheel changes its picture; B / N / V change its light or colour |

The backtick is the key left of `1`, under Esc. raylib (GLFW) reports keys by position, so
it is that physical key on a Portuguese keyboard too (ASSUMED: check on the cabinet
keyboard in v0).

The selection **freezes while a tool key is held**, so a shaky hand cannot slide onto the
neighbour while scrolling. `L` locks it until pressed again.

### 4.4 Keyboard map

One pattern everywhere: **hold a letter and spin the wheel**. Without a wheel, hold the
letter and press Left / Right. Shift makes the step fine.

| Key | Action | Notes |
|---|---|---|
| W A S D | fly forward / left / back / right | |
| Space / F | fly up / down | |
| Shift (hold) | fly fast | with a tool key held it means "fine step" instead |
| Mouse | look | Fly state |
| Wheel alone | fly speed | shown as a pill for a second |
| `` ` `` / Shift+`` ` `` | next / previous select mode | commits a pending change (5.2) |
| Esc | free / capture the mouse; closes the help first | never quits |
| Tab | show / hide the panel | as CamLab |
| **Q** + wheel | pick distance, 1 to 100 m, default 10 m | |
| **E** + wheel | next / previous texture in the current set | applies live to the selection |
| **C** + wheel | texture group: SRC, SR2, SR3 | also `1` `2` `3` |
| **X** + wheel | set inside the group (course or SR3 track) | |
| **K** + wheel | kind filter (all, rock, roof, wall ...) | |
| **R** + wheel | rotate texture, 15 deg; Shift 1 deg | |
| **T** + wheel | size, 10 %; Shift 1 % | T + Left / Right = width only, T + Up / Down = height only |
| Arrow keys | slide texture, 1/16 repeat; Shift 1/128 | in World mode Up / Down step the world list |
| **G** + wheel | reach of a mesh selection: patch, whole section, everywhere this tile is used | Mesh mode |
| **M** | mapping: keep, fit, tile | 7.2 |
| **H** / **J** | mirror the texture left-right / up-down | |
| **B** + wheel | brightness | selection tint, or the chosen light in World mode |
| **N** + wheel | colour (hue) | |
| **V** + wheel | vividness (saturation) | |
| **I** or middle click | pick up: copy texture + transform from under the crosshair | "eyedropper" |
| **P** or left click | paint: put the picked-up texture + transform on the selection | commits at once |
| Backspace or right click | selection back to the original | undoable |
| Enter | done: commit the pending change now | skips the 3 s wait |
| PgDn / PgUp | select the next thing behind / in front along the crosshair | overlays, cut-outs |
| **L** | lock / unlock the selection | |
| Home / End | jump to the start line / to the last change | |
| Ctrl+Z | undo (no limit), camera jumps to the change | |
| Ctrl+Alt+Z | redo, camera jumps | Ctrl+Y and Ctrl+Shift+Z also work |
| Ctrl+S | save | |
| Ctrl+Shift+S | save a numbered copy ("Mountain 2") | no dialog |
| Ctrl+O | next project in the project list | no dialog; the panel shows the list |
| Ctrl+N | new empty project | |
| F1 | help overlay: this table, drawn over the view | hold or toggle |
| F2 | hints on / off | |
| F3 (hold) | show the original 1995 textures | compare |
| F4 | view: textured, + wireframe, + changed faces tinted | |
| F5 | reload from disk | undoable |
| F6 | preview light: game-like / flat | |
| F8 | back to defaults (empty project) | undoable |
| F9 | send to game (build the track) | status in the hint line |
| F11 | full screen | |
| F12 | screenshot `texlab_<time>.png` | as CamLab |

Conflict check:

- Each letter has one meaning. Used: W A S D F Q E C X K R T G M H J B N V I P L. Free: O
  U Y Z.
- Ctrl+S and plain S: flying is ignored while Ctrl is held. Same for Ctrl+O / N / Z.
- Shift is "fast" for flying and "fine" for tools: while a tool key is held it is fine
  only, and the speed boost is off.
- Arrows are never movement keys, so sliding a texture cannot move the camera.
- F is fly-down; the F-keys are separate keys. F7 and F10 are unused (F10 is a Windows
  menu key and is left alone).
- Ctrl+Alt+Z equals AltGr+Z on European layouts; it produces no text in TexLab, so it is
  safe.
- No punctuation key other than the backtick is used, because those move between layouts.

### 4.5 The 7-year-old test

- The hint line always names the next step in plain words ("Point at a wall", "Hold E and
  spin the wheel", "Press the key under Esc to pick single pieces").
- First run: four hints in sequence (fly, select, change, undo), each ticks off when done.
- Big labels: the selection label and the mode pills use the large font; while a tool key
  is held its value is shown large beside the crosshair ("10 m", "23 deg", "110 %").
- No modal dialogs at all. No file picker: projects are a list. No "are you sure?":
  reload, defaults and reset are undo steps instead.
- Autosave of a recovery copy every 30 s and on exit. Closing the window never loses work.
- Esc never quits. The window's close button saves the recovery copy and exits.
- Wrong moves are cheap: Ctrl+Z always works, and it flies you to what changed.
- Colour, not text, carries state: orange = selected / unsaved, green = saved, blue = game.
- Out of range, the crosshair is a small grey dot; in range it becomes a ring.

---

## 5. The session log

### 5.1 File

`SR3CamLab\texlab\logs\<epoch of start>.log`, UTF-8, one line per event, append-only,
flushed after every line. Git-ignored. One file per run of the app.

Timestamps are unix epoch seconds (integers). Each line ends with a running number so two
events in the same second stay distinct and reverts can name their target exactly.

### 5.2 The settle rule

Scrolling through fifty textures is one change, not fifty.

- A change that is still being adjusted is **pending**. Each further step on the same
  target and of the same kind (texture, rotate, scale, move, tint ...) updates it and
  restarts a 3-second timer.
- When the timer runs out the change is **applied**: one log line, one undo step. Its
  timestamp is the moment of the last step, that is, the time of writing minus 3 seconds.
- These apply it at once, also stamped with the moment of the last step:
  - cycling the select mode (backtick);
  - the crosshair selecting another face or mesh;
  - Enter, paint (P / click), starting a different kind of change on the same target;
  - save, send to game, reload, defaults, undo, redo, closing the app.
- A pending change that ends where it began (scrolled away and back) writes nothing and
  makes no undo step.
- Amounts are net over the pending period: three 15-degree turns and one back log as
  "by 30deg"; two +10 % steps log as "by +21%".

### 5.3 Line formats

```
<ts> Session started: "<project>" on <course> (TexLab <version>)                        #0
<ts> Replaced <old> with <new> in <mesh>                                                #n
<ts> Replaced <old> with <new> in <mesh, face>                                          #n
<ts> Moved <tex> in <mesh[, face]> by (<du>, <dv>)                                      #n
<ts> Rotated <tex> by <a>deg in <mesh[, face]>                                          #n
<ts> Scaled <tex> in <mesh[, face]> by <+p>%                                            #n
<ts> Scaled <tex> in <mesh[, face]> by <+p>% wide, <+q>% high                           #n
<ts> Mirrored <tex> in <mesh[, face]> <left-right|up-down>                              #n
<ts> Mapped <tex> in <mesh[, face]> as <keep|fit|tile 7.0m> (was <...>)                 #n
<ts> Tinted <mesh[, face]> brightness <+p>%, colour <r g b>                             #n
<ts> Painted <tex> onto <mesh[, face]> (copied from <mesh[, face]>)                     #n
<ts> Reset <mesh[, face]> to original                                                   #n
<ts> Changed sky from <old> to <new>                                                    #n
<ts> Changed sea texture from <old> to <new>                                            #n
<ts> Changed light <ambient|sun|scale|tint|fog> from <r g b> to <r g b>                 #n
<ts> Reverted back to <ts of the state now showing> (#<its number>)                     #n
<ts> Restored forward to <ts> (#<number>)                                               #n
<ts> Reverted back to defaults                                                          #n
<ts> Reloaded "<project>" from disk                                                     #n
<ts> Saved "<project>" (<k> changes)
<ts> Sent to game: <output folder> (<ok|failed: reason>)
<ts> Session ended
```

Example:

```
1791370000 Session started: "Mountain 1" on SRC Mountain (TexLab 0.1) #0
1791370042 Replaced SRC/mountain/c0E0 with SR3/Canyon4/53850d6a in <obj_1262:c0E0:3> #1
1791370061 Rotated SR3/Canyon4/53850d6a by 23deg in <obj_1262:c0E0:3, obj_1262#0037> #2
1791370070 Scaled SR3/Canyon4/53850d6a in <obj_1262:c0E0:3, obj_1262#0037> by +10% #3
1791370120 Reverted back to 1791370042 (#1) #4
```

### 5.4 Undo and redo in the log

- One undo step = one applied change (one numbered line).
- Undo and redo presses follow the settle rule too: a burst of Ctrl+Z writes **one**
  "Reverted back to" line naming the state that ends up showing, 3 seconds after the last
  press (or at once on the commit events of 5.2). Undoing everything writes "Reverted back
  to 1791370000 (#0)".
- A burst of redo writes one "Restored forward to" line.
- Ctrl+Z while a change is pending first applies it (logged), then undoes it. Honest log,
  and redo can bring it back.
- A new change after an undo drops the redo branch from memory, as usual. The log keeps
  the dropped lines: it is a history, not a state.
- Every undo step stores the camera position and direction at the moment of the change.
  Undo and redo glide the camera there (about 0.3 s) and flash the affected faces.

Depth is unlimited: a step is a few hundred bytes (target id, key, old value, new value,
camera). Open question 9: whether undo should survive closing the app (a replay journal
beside the project).

---

## 6. Picking and selection

### 6.1 The ray

One ray per frame from the camera through the crosshair, tested against the triangles of
every face within the pick distance (Q + wheel, default 10 m). About 30k triangles: a
uniform grid over the course keeps it far below a millisecond.

- Faces are single-sided like in the game: a face seen from behind is invisible and
  cannot be picked. Two-sided faces (the importer's front / back pairs and cut-outs) pick
  from both sides and count as **one** face.
- **Cut-outs**: the ray reads the texel it hits. A transparent texel lets the ray through,
  so the wall behind a tree's empty corner is selectable. Alt held picks the cut-out by its
  whole quad.
- **Stacked overlays** (decals, layered 1995 polygons a few centimetres apart): the top
  one wins. PgDn / PgUp step to the next hit along the same ray, and the label says
  "2 of 3".
- Nothing within range: no selection, grey dot. In World mode there is no range limit and
  only sky, sea and road answer.

### 6.2 What a "mesh" is for 1995 data

The 1995 model has no meshes: Mountain is 60 section objects (`obj_1259` .. `obj_1318`)
with 1,808 material runs (CHECKED). Neither is what a person calls "that wall". Definition:

> A mesh is a **patch**: faces of one section that carry the same original texture and
> are joined by shared corners.

That gives a rock face, one house front, one roof, one row of tree boards. `G` + wheel
widens the reach when the patch is too small:

| Reach | Selects |
|---|---|
| Patch (default) | the connected patch |
| Section | every face with that original texture in the section |
| Everywhere | every face with that original texture on the course |

"Everywhere" reproduces the old CSV workflow (one class, one texture) in one gesture.
Reach is a selection aid; the document still stores one entry per patch, so any patch can
be changed again alone.

Risk: patches may come out too small (each quad its own patch where the 1995 strips do
not share corners exactly) or too large (a rock wall running the length of a section).
v0 prints the patch statistics; the corner-merge tolerance and an optional angle limit
are tuned then. Open question 9.

### 6.3 Highlight

- Mesh: orange outline round the patch border, faint orange fill (12 %), slow pulse.
- Face: bright outline on the face, faint outline on its patch.
- Drawn after the scene with a depth bias, so it never z-fights; parts hidden behind other
  geometry are drawn dimmer rather than not at all.
- Changed faces carry a small orange corner mark in view mode F4.

---

## 7. Texture transforms, vertex lighting, sky, sea, lighting

### 7.1 What the game stores (CHECKED in `build_classic.faces_to_mesh`)

Scenery vertices are format `0x20C7`, 48 bytes: position, normal, tangent, `uv0`, `uv1`.
`uv0` is **signed 16-bit, -1 .. +1** (32768 = one repeat). Textures wrap. There is no V
flip and handedness is ZS = -1.

Consequences, all handled by the exporter and invisible in the editor:

- A whole-number shift of a face's UVs changes nothing on screen, so each face is shifted
  to sit inside -1 .. +1.
- A face that spans more than about 2 repeats cannot be stored: it is cut into pieces
  (`uv_split` does this today). Scaling a texture *down* (more repeats) therefore adds
  polygons; the panel shows the count and warns above a threshold.
- Pieces are cut along the face's own plane, so no new overlap or z-fight can appear.

### 7.2 Mapping modes (`M`)

| Mode | UV before the transform | Use |
|---|---|---|
| keep | the face's own 1995 UVs | default; keeps how the tile was laid out |
| fit | 0 .. 1 across the bounding rectangle of the selection, in its plane | one picture across a whole wall: boards, facades |
| tile | planar projection in metres divided by the repeat size (ground on x, z; walls on their horizontal axis and height, as `retex.box_uv`), axis from a normal smoothed over the patch | SR3 surface textures: rock, plaster, cobbles |

Default when a texture is first applied: `keep` for SRC and SR2 tiles; `tile` at a
per-category repeat (rock 7 m, others 3 m, from `retex.REPEAT_BY_CLASS`) for SR3 surface
textures; `fit` for textures marked as pictures.

### 7.3 Move, rotate, scale

`uv' = pivot + R(rotate) * S(1 / scale) * (uv - pivot) + move`, with the rotation done in
texel-aspect-corrected space so a 256 x 32 tile does not shear.

- **Mesh**: one transform for the patch. Pivot: the tile centre (0.5, 0.5) in `keep`, the
  patch centre in `fit` and `tile`. In `tile` the result is continuous across faces; in
  `keep` every face turns its own tile the same way.
- **Face**: its own transform applied after the mesh's, pivot at the face centre. A face
  with its own texture but no transform keys inherits the mesh's.
- Rotation is free (any angle): it is only UV arithmetic. 90-degree steps are exact.
- Scale 110 % makes the picture 10 % bigger (fewer repeats). Width and height can differ.

**Tiles that must not repeat** (signs, facades, single windows): in `fit` the editor
clamps move and scale so the picture rectangle always covers the selection, so no second
copy can enter. Mirror and rotation by 90 degrees stay free. A real clamp sampler exists
in the texture header (`+0x14`: address U / V / W, read by 0x58DF40, CHECKED in the
importer comments) but setting it to clamp is untested: **SPIKE**. If it works, pictures
get a clamped copy and the editor rule relaxes.

### 7.4 Vertex lighting: what applies

| Wish | Can SR3 carry it? | Plan |
|---|---|---|
| Per-vertex colour (soft shadows, gradients) | **Not with the mesh format in use**: `0x20C7` has no colour field. SEGA has other formats (`0x20D7`, 52 bytes, probably the same + 4 colour bytes) and at least one material with "vertex colours on, lighting off" (Alpine4 1b5e8346), but neither the field nor the switch is decoded | **Not applicable in v1.** SPIKE for 1.3: decode `0x20D7`, find the switch, one in-game test |
| Flat tint / brightness per mesh or face | Yes, by baking: the tint goes into a tinted copy of the texture (the importer already does this for rock, `allsr3.tinted_texture`, and for VIVID) | **v1**: B / N / V. Tints are quantised to 16 levels per channel so the number of texture copies stays bounded; the panel shows the count |
| Painted shadows | Possibly through the light map: the Uber material has `gTextureLight` / `gbUberLMAP` and `uv1` is the light-map coordinate; the layout is not decoded | SPIKE for 1.3 |
| Glow (unlit / additive) | A lighting-off switch and `gbUberABLENDAdd` exist in the material name list; cells not identified | SPIKE for 1.3; until then "glow" = brightness above 100 %, clipped at white |
| 1995 per-polygon brightness | Not recovered from the ROM (`14_importer.md`) | out of scope |

Classic faces are built with up-normals, so the game lights them all alike. That is why a
flat tint is the honest control today.

### 7.5 Sky

The game's sky is the slot's dome mesh with two 2048 x 1024 DXT5 pictures; `sky1995.py`
repaints only their pixels. TexLab offers a list of whole skies, changed with E + wheel in
World mode:

- SRC skies: each course's far backdrop painted through `sky1995` (Mountain today; the
  other three need their `sky.obj`, which exists).
- SR3 skies: the two dome pictures of another arcade track, resampled to the slot's size.
- `slot`: Desert4's own sky.

The cache holds each sky pre-rendered as the two dome pictures, so the viewport shows the
real dome. Free positioning of a sky (turning it round the course) is a single number
(yaw) and is included; painting on the sky is not.

### 7.6 Sea and other elements

- **Sea**: a flat sheet of 40 m quads. Editable: its texture (E + wheel), level (T +
  wheel in World mode), tint, and the texture transform as for a mesh. The colour below
  the horizon on the dome follows the sea colour, as `sky1995` does now.
- **Backdrop, fill geometry, CHECK POINT banners**: ordinary faces, selectable like any
  other (their ids carry the source).
- **Road**: a separate SR3 system (TrackDeform). The layer texture ids select the physics
  and are never changed. Editable in World mode: tint of the tarmac and gravel layers
  (`road_tint`), the asphalt tile painted into the tarmac layers and its repeat
  (`road_tile_repeat`). The draped 1995 road decals are faces and are selectable in Mesh /
  Face mode (ASSUMED: needs the cache dump to be taken after draping; check in v0).

### 7.7 Overall lighting

The slot has two lighting sets of 49 floats (master_gfx root `+0x18`). The importer
already overrides five triples in both: ambient (index 4), sun (7), fog (14), scale (23),
tint (44). TexLab exposes exactly those five as World items "Shade", "Sun", "Fog",
"Brightness", "Tint", each with B / N / V. The other 34 floats are unknown and not
exposed. Sun direction is not known to be in the set (root `+0x20`, `+0x24` may be sun
angles: UNKNOWN in the knowledge base), so no sun-direction control in v1.

---

## 8. Preview fidelity and the round trip

### 8.1 What the viewport reproduces

| Aspect | Viewport | Match |
|---|---|---|
| Geometry, UVs, wrap, handedness | the importer's own face list and the exporter's own UV code path | exact |
| Texture pixels | PNG with the same VIVID gamma the importer applies, mip-mapped, trilinear + anisotropy | close; no DXT block artefacts (optional "as compressed" view later) |
| Cut-outs | alpha test at 0.5, two-sided | close |
| Overlays | drawn with the same lifts | exact layout; z precision differs from the game |
| Sky | the real dome mesh with the painted pictures | close |
| Sea | the same sheet | close |
| Lighting | `texture * (ambient + sun) * scale`, then tint, with up-normals: my reading of the five triples, not SEGA's shader | **approximate**; F6 switches it off |
| Fog | linear fog in the fog colour; distances guessed | approximate |
| Road | flat-coloured strip + the draped decals | rough: SR3's layer blending is not reproduced |
| Slot props, grass, spectators, car shadows, PVS popping | not shown | absent |
| Tone / gamma of the game's final image | not modelled | unknown |

Calibration (v2): build the track once, take game screenshots from two or three known
camera positions (the suite has `tools\viewmat.ps1` and `shotloop.ps1`), take
`texlab.exe --shots` from the same positions, and fit the preview's light constants. The
user runs the game part.

### 8.2 Round trip

1. F9 saves the project and starts `import_classic.py src 1 classic --texlab <project>` in
   the background. The hint line shows progress; TexLab stays usable.
2. The importer writes its usual output folder (`work\out\step..._desert4\Desert4`) and
   build log; TexLab shows "Track built" or the last error line.
3. Installing into the game uses the suite's existing classic-import path (ASSUMED: the
   same mechanism SR3Ultimate uses, originals restorable, exe untouched; not read for this
   plan).
4. The user starts the game with `PLAY.bat` and tests from the cabinet. TexLab does not
   launch the game by itself.
5. Anything that looks wrong goes back into TexLab; Home / End and bookmarks help find the
   place.

---

## 9. Milestones, risks, open questions

### Milestones

| Milestone | Content | Accepted when |
|---|---|---|
| **v0 Viewer** | `texlab_scene.py` (cache + libraries), `texlab.exe`: load, fly, crosshair, sky, sea, road strip, panel shell with thumbnails, F1, F12, `--shots` | Mountain loads in under 5 s and holds 60 fps at 1080p. `--shots` pictures match the `blender_mountain_classic_*` renders from the same cameras: board text reads the right way round, the castle is on the correct side, no z-fight flicker while flying the lap. Thumbnails are 32 px at 100 % and sharp at 150 % and 200 %. Patch statistics printed |
| **v1 Edit + save** | select modes, pick distance, E / C / X / K, mapping, move / rotate / scale, flat tint, eyedropper / paint, undo / redo with camera jump, project file, autosave, session log, hints | Self-test (`--selftest`, no window): scripted edits, then undo all, gives a byte-identical empty document; redo all gives the same document as before. Save, close, load shows the same picture. Scrolling 50 textures in 10 s writes one log line stamped at the last step; cycling the mode or selecting another face writes it at once. Every row of the key table works with the mouse unplugged except "look". A person who has not seen the app retextures a wall and undoes it using only the hint line |
| **v2 Export** | `texlab_apply.py`, `--texlab` in the importer, UV range cutting, tinted copies, F9, calibration | With an empty project the built track is byte-identical to today's step34. With edits: `preview_obj.py` decode-back shows the assigned textures and UVs on the right faces; `check_classic.py` still passes; coplanar report clean. In game (user): edited walls look as in TexLab, no z-fighting, no mirrored pictures |
| **v3 World** | sky list, sea, road tint, five lighting triples | Changing each one in TexLab and rebuilding changes exactly that in the game; preview agrees after calibration |
| **v4 More tracks** | the other SRC courses, then SR2 | Each course loads, edits and exports with its own project file |
| Spikes (any time) | clamp sampler; `0x20D7` vertex colours; light map; additive / unlit | one in-game test each; result written into `07_glue_and_other_files.md` |

### Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Patch definition does not match what the eye calls a wall | Mesh mode feels random | v0 statistics, tolerance tuning, the reach key G, face mode as fallback |
| Ids drift when the ROM export changes | changes land on the wrong face | anchors, orphan list, scene hash banner |
| Scaling down multiplies polygons (2-repeat limit per face) | bigger meshes; SR3 mesh limits (16-bit indices, so 65,535 vertices per mesh; the largest in the old step20 build was 20,720) | live polygon count, warning, exporter splits meshes |
| Many tints or many SR3 textures | texture memory in the game (512 to 1024 px SR3 textures, tens of them) | counts and total megabytes in the panel; quantised tints |
| Preview lighting differs from the game | colours chosen in TexLab look different in game | F6 flat view, calibration step, F3 compare |
| The Python pipeline is a personal workspace outside the repo | TexLab only works on this PC | open question 2 |
| Importer change breaks the frozen classic build | regression in tracks that load today | additive code path, byte-identical test with an empty project |
| Backtick on the cabinet keyboard is somewhere else or dead | select mode unreachable | test in v0; F7 as a second binding if needed |
| Coplanar faces after per-face texture changes | none expected: geometry and lifts are untouched, cutting stays in-plane | coplanar report in the export |

### Open questions for the user

1. **Exe or script?** TexLab as a second raylib exe (recommended: exact CamLab look,
   least work), or must it be a run-time-compiled script with no exe, at several times the
   effort and a re-drawn look?
2. **Who is it for?** Only this PC (the cache comes from your ROM extracts and
   `SR3 track format\work\scripts`), or a public release? A release needs the extraction
   pipeline packaged for other people's own ROMs, which is a project of its own.
3. **What is a mesh?** Is "connected faces with the same original tile inside one section"
   the right unit, with G to widen? Or do you think in whole buildings (all walls and the
   roof of one house together)?
4. **Fourth mode.** Is "World" as a fourth backtick stop acceptable for sky / sea / road /
   light, or should backtick stay at three and World move to its own key?
5. **Log timestamps.** Whole seconds plus a running `#n` (as planned), or milliseconds?
6. **Undo across sessions.** Should Ctrl+Z still work after closing and reopening a
   project (a replay journal beside it), or is per-session undo enough?
7. **Fly keys.** Space up / F down / Shift fast / wheel speed: fine, or do you want the
   same keys as the game's free cameras?
8. **SR3 atlases.** SR3 building textures are atlases of pieces (single windows, doors).
   Should v1 let you pick a rectangle out of an atlas, or only whole textures?
9. **Mixed resolution.** 1995 tiles beside 512 px SR3 textures look uneven. Any wish for
   an optional upscale / filter of the classic tiles, or leave them as they are?
10. **Vertex lighting priority.** Is flat tint per mesh / face enough for now, or is
    real per-vertex shading worth an early spike (one or two in-game tests from you)?
11. **Install step.** Should F9 stop at "track built", or also install it into the game
    folder the way SR3Ultimate does?
12. **Road.** Is tint + asphalt tile enough, or do you expect to retexture the road
    surface itself (limited by the physics-by-texture-id rule)?

---

## 10. Decisions (user, 2026-10-07) - these override the sections above

1. **Second exe: yes.** TexLab is a raylib program built from source like CamLab.
2. **Public release.** The ROM-extraction and import pipeline must be packaged so other people can run it on their own
   ROMs and their own game files; nothing SEGA is shipped. This is now part of the project, not an afterthought.
3. **"Mesh" means object, judged by uniformity.** One building wall is a mesh (each wall can differ in real life); a
   whole rock is a mesh. So the unit is "connected faces that look like one thing", not "one whole building".
   The patch definition in 6.2 stands as the starting point; a rock that spans several patches must still select as one.
4. **No "World" backtick mode.** Backtick cycles Off / Mesh / Face only. Sky, sea and other world elements are
   changed by pointing at them (the pick distance does not apply to the sky and the sea).
5. **Atlas pieces: yes**, picking a piece out of an SR3 atlas is in, and it must be simple enough for a 7-year-old
   (pieces shown as ready-made thumbnails, never a rectangle editor).
6. **"Send to game" builds AND installs** the track.

Agreed scope changes: v1 ships with a small key set (fly, select modes, Q / E / C + wheel, rotate / scale / slide,
undo / redo, save, help); the remaining bindings in 4.4 wait until they are missed. Matching the game's look (same
camera, same colours as an in-game screenshot) is an acceptance test of v0, not v2. Export to the game follows a
minimal editor directly. Known stale points above: the clamp sampler is already in use (cut-out textures), and the
"byte-identical to step34" test must name whatever the current Mountain build is.
