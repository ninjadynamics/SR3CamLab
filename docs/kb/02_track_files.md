# 02 - The files of a track

Folder `Main_release\tracks\<Slot>` (six hard-coded slot names). `<env>` = lower-case slot name (stadium4),
`<route>` = `<3 letters>_track_route4` (sta_, des_, lak_, alp_, can_, tro_).

| File | Root chunk | Content | Needed? |
|---|---|---|---|
| `<env>_master_gfx_xdata.sbf` | kind 12 type f626b658 | road (TrackDeform + height blob), scenery tree + meshes/materials/textures, sky dome, lighting objects, boundary walls | MANDATORY (loader 0x5C5770 hangs in an error loop if it fails) |
| `<env>_master_xdata.sbf` | kind 12 type ecdb142b | gameplay root: start grid, sectors, AI map, cameras, spline/pace notes | MANDATORY (0x5C5C90 uses the result without a null check) |
| `<route>_game_objects_gfx_data.sbf` | kind 5 `{3, nObjects, ...}` | placed objects (76-byte records), particle effect definitions, their meshes/textures | LIKELY required (result passed on unchecked at 0x5C5E0D) |
| `<route>_gameobj_gfx_dis_data.sbf` | kind 5 list | Granny files (kind 7) for breakable/animated objects | loaded only if the game_objects root version >= 2 |
| `<route>_pobj_master_gfx_xdata.sbf` | kind 12 type a4dd8f06 | "procedural objects" masters (meshes/materials) | OPTIONAL: 0x5C5507 returns when the load gives NULL |
| `<route>_pobj_plac_gfx_xdata.sbf` | kind 12 type 690c0d8f | placement of those objects | OPTIONAL (same function) |
| `<Route>_proc_cached.bin` | - | grass cache | OPTIONAL (0x506FD0) |

CORRECTION from in-game runs (2026-10-07): the "OPTIONAL" entries for the two pobj files and the grass cache are what the
loader code allows, not what a race survives. Without `pobj_master`, `pobj_plac` and `proc_cached.bin` the grass set-up
0x506FD0 (reached via the pobj_plac root, globals 0x9C491C..28) never runs, the arrays at [0xA95D24 / 28 / 2C] are never
created (they are allocated only at 0x4F0259 / 0x507C84), and the game dies with an access violation at 0x5DE16C (function
0x5DE0C0) about 2 s into the race, when a wheel touches the road. VERIFIED in game. A track therefore needs all seven
files; see 21_track_install_and_switching.md. (An earlier note, "missing file = no grass, no crash", in
game-runtime-and-frontend.md describes the loader only and is superseded by this.)
The Desert4 folder also holds `..._procobj_plac_gfx_xdata.sbf`, which the project's reader does not parse; it travels with
the props unchanged (`build_testtrack.write_track`).

Cross-file references: the pobj files reference ids that live in master_gfx (found when a garbage collection of
master_gfx broke 334 references). Keep those chunks when trimming master_gfx.

Extra files present in some folders and NOT loaded by the arcade exe: `tropical4_master_data.sbf`,
`*_procobj_*`, `Alpine4.rar`.

## Stadium4 inventory (the base of the test tracks)
master_gfx (478 chunks): 35 meshes, 299 materials, 2 shaders, 134 textures, kind 11 scenery tree b66f69a8 (0.5 MB),
kind 5 TrackDeform 515fa2e5 (6.2 MB), kind 7 height blob 52afc7dd (1.3 MB zlib -> 4.9 MB), kind 5 boundary BSP
0c8e586e (0.24 MB), kind 12: 2 x b473b5a7 (196-byte lighting sets), c7975114 (refers to both), root f626b658.

master_xdata (7 chunks): AI map a6cdd28b, camera lists 40512d61 + be9ef667 held by kind 12 0b9214e0, kind 12 15c476ae
stub, Stadium-only chunk f746b21b (217 keyframes of quaternion + position; root +0x28), root ecdb142b.
Stadium4 has NO spline chunk (root +0x18 = 0); the other five tracks have one.

## World conventions (VERIFIED numerically)
Metres, Y up. The scenery tree spans x,z in [-750, 750]. Lap distance is counted in road slices (1 m each).
