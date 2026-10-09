# 13 - The classic Mountain course retextured with SR3 textures (step20)

Scripts: `work/scripts/retex_survey.py` (contact sheets), `retex.py` (labels, box mapping, subdivision),
`build_classic.py` mode `retex` (step20), `preview_obj.py` + `render_all.py` (decode back and render).

## Method
1. Every classic tile was looked at (`work/retex/classic_tiles_contact.png`, numbers = row `index` of the CSV) and given
   a class. Labels live in `work/retex/tile_labels.csv` (columns index, tile, class, sr3_track, sr3_texture_id, note).
   The CSV is written once and READ BACK on every build: edit it to correct a label or to point a class at another
   texture id, then run `python build_classic.py step20` and `python render_all.py`.
2. Candidate SR3 textures: the diffuse textures (material word +0x1BC) of Alpine4's scenery, ranked by use, decoded to
   PNG (`work/retex/sr3_candidates_Alpine4.png`, `work/retex/sr3_tex/`), chosen by eye.
3. Replaced classes get the SR3 texture chunk copied from the user's own Alpine4 file, a cloned material, and NEW UVs
   in metres: box mapping (ground/roofs on x,z; walls on their horizontal axis and height), 3 m per repeat. Because the
   SR3 vertex format used holds uv 0..2, faces are first cut into pieces of at most 5.5 m.
4. Picture tiles keep the classic texture and UVs.

## Classes and choices
| Class | Classic tiles (index) | SR3 texture (Alpine4) | Pieces after cutting |
|---|---|---|---|
| rock | 0-7, 84-88, 108, 110 | e8a80b7c rock face | 14678 |
| asphalt (outside the SR3 road strip) | 8, 20-22, 107, 109 | 02b4772a dark asphalt | 132 |
| cobbles | 19, 111-113 | fc24c933 cobblestones | 1449 |
| stone_wall | 15 | 24a1910c stone blocks | 92 |
| gravel | 37, 42, 77 | 66f0ba6f earth with grass | 735 |
| plaster | 35, 36 | ee2e5509 white plaster | 696 |
| roof | 56-66 | 65f21786 slate tiles | 1000 |
| house_front (all facades, church, tower, arcade) | the remaining 67 | kept classic (pictures of windows/doors) | - |
| sign (SEGA / SEGASATURN boards) | 83 | kept classic | - |
| fence, lamp | 117, 121 | kept classic (cut-outs) | - |
| foliage (trees, trunks, bushes, backdrop trees) | 16, 38-41, 70-73, 89-92, 114-116, 122-125 | kept classic (cut-outs; an SR3 replacement needs an alpha-tested material, not available yet) | - |
The drivable road itself is the SR3 road (TrackDeform) with Desert4's Safari tarmac / gravel layers (11_importer_prototype.md).

## Result
step20: 126 scenery meshes, 104540 vertices (largest mesh 20720), 7 SR3 textures copied, 16 faces still clamped.
Pictures: `work/previews/blender_sr3tex_*.png` (decoded back from the built files) and `blender_compare_*.png`.
Known weaknesses: 3 m repeats are visible on the big rock faces (a larger repeat or a second detail texture would
help); the classes "roof" (dark mottled tiles 56-66) and "gravel" are my reading of small grey tiles and may be wrong;
facades stay 1995 resolution next to SR3-resolution walls; the trees stay grey classic cut-outs; the road in the
renders uses an arbitrary 6 m tiling of the layer texture because the game's own road mapping is not known.

## Fifth package changes
- Classic tiles are now coloured, so the kept classic parts (house fronts, boards, trees) are in colour.
- Rock faces use a 7 m repeat (`retex.REPEAT_BY_CLASS`), pieces cut at 13.5 m: 5157 pieces instead of 14678.
- Tiles 37 and 77 (town pavement) were relabelled from gravel to cobbles (they showed as grass).
- NOT done yet: classic lane markings/kerbs on the SR3 road, extra texture sources (Canyon4/Desert4/Lakeside4), an
  alpha-tested SR3 material for cut-outs, SR3 tree meshes, a full re-check of every label against the coloured tiles.

## Sixth package: mixed version (step20) changes
- Labels re-checked against the coloured contact sheet (`work/retex/classic_tiles_contact_colour.png`): tile 7 and 37
  are grass (were rock / cobbles), 35, 36 and 42 are sandy verge (dirt), 114 is a tree wall. New sources: grass =
  Lakeside4 d8dcd068, dirt = Canyon4 1ec88958, rock = Canyon4 53850d6a (user: sand-coloured rock, not grey).
- Classic lane markings (tiles 107, 109) and paved strips (111, 113) that lie on the road are draped on the SR3 road as
  decals 3 cm above it (`build_classic.road_decals`); the paint texels are cut out by alpha.
- The classic polygons under the SR3 road are no longer deleted but kept 20 cm lower (deleting upright ones left gaps).
- step23 = step20 + the SR3 tree row (Alpine4 484f0734) on the upright boards of the tree wall.

## All-SR3 version (step24) - `work/scripts/allsr3.py`, `build_allsr3.py`, `sr3_art.py`
User: "take liberties, so that all textures are SR3's high res ones". step24 holds no 1995 texel.
Survey: `sr3_art.py <Track>` writes every texture of a track as PNG (`work/retex/art/`) and contact sheets
(`work/retex/art_<Track>_gfx_N.png`); gridded close-ups `work/retex/pick_1..4.png`. Finding: SR3 has NO facade pictures.
Its buildings are 3D models skinned from 512x512 atlases of pieces (wall patches, single windows, doors). So facades
are COMPOSED: a wall patch mirror-tiled into a seamless fill, one SR3 window or door pasted into the bay
(`work/retex/allsr3_proof_1.png` shows every composed bay).
| Classic class (CSV) | Treatment in step24 |
|---|---|
| house_plaster | styles plaster_white (Lakeside4 05d9d287 plaster, dc5e6f91 sash window and door), plaster_beige (Alpine4 6fdfabb4 plaster and shutter window, a33fab8f door), plaster_rough; the plaster is tinted cream / pink / yellow / ochre / blue after the classic house colour |
| house_stone | stone_rubble (Lakeside4 efadc649, 972c2b1c window), stone_block (a057c011), plaster_rough |
| house_brick | brick (Lakeside4 9ad7a350, a1c60215 windows and door), plaster_beige |
| church, arcade | Lakeside4 9885b7b5 church stone, tracery and lancet windows, arched door; a057c011 ashlar |
| roof | Alpine4 65f21786 slate, 2.2 m per repeat |
| rock | Canyon4 53850d6a / 89f2eea0 / c24eb36a, one per classic rock tile, 7 m per repeat, mapped in the plane of each face |
| grass, dirt, cobbles, stone_wall, asphalt, gravel | as step20 |
| sign | SR3 sponsor boards (Alpine4 SEGA 55644df5, WRC cd719948, Pirelli efff912e, easynet d07234f4, Karcher 4939c3df, Abu Dhabi aeec9c24), one per panel, centred band of the 2:1 logo |
| crown, tree, ivy | SR3 cut-outs (Lakeside4 a057c011 leaf mass, 6ebafe84 tree) laid out like the classic tile, classic UVs kept |
| trunk, bare | Alpine4 bark 2fde3ae7 behind a drawn trunk shape |
| tree_wall | Lakeside4 tree row 0fcf0f84 |
| lamp, fence (guard rail) | the classic SILHOUETTE as alpha mask, filled with SR3 metal texels (liberty: no SR3 lamp post or rail texture was found) |
| untextured classic polygons | Lakeside4 1c24d989 roughcast |
Facade rule: a wall quad is cut into bays x storeys (bay 6 m, storey 6 m: the 1995 town is about twice life size),
whole bays only, so no window is cut; upper cells get the window bay, the ground row a window or one door; gables and
slivers get the plain wall in metres. Style = hash of (building, classic tile); a building = facade faces sharing corners.
Road (user: "select the best visual match"; `road_match.py`, `work/retex/road_match.png`): the classic asphalt is a
blue-grey (mean 120,129,137). Of all tarmac layers of the six arcade tracks only Lakeside_Tarmac 7f8b9a62 + 6025fa42 is
blue-grey (87,93,94), every other tarmac is neutral or brown; chosen for the tarmac cells. Loose cells: Lakeside_Dirt
029be493 + ed8aec61 (124,117,103), nearest to the classic sandy tile (124,108,96). The four layer textures are copied
into the Desert4-slot file; the surface lookup is by texture id in the global table, so they select Lakeside tarmac and
dirt physics (10_surfaces.md). Markings: the 1995 course has painted lines only in the town; they are kept there as
alpha-blended decals (the classic paint layout, SR3 line texels from 54c156ac), nowhere else.
Editable: `work/retex/tile_labels.csv` (class per tile; texture for the tiled classes); styles and pieces in `allsr3.py`.
Pictures: `work/previews/blender_final_1..9_*.png` (2560 px, classic left / step24 right), `blender_allsr3_*.png`.
Known flaws: a thin gap under one rock foot in picture 3 (cause not found; it is in step20 too); texture direction
changes from face to face on large rock triangles; composed bays repeat on long walls; boards read correctly from the
road side only; nothing was seen in the game.

## Status note (2026-10-07 / 08)
- Nothing of the mixed or all-SR3 variants was driven in game; the lane is frozen and the owner will curate by hand.
- A planned tool, TexLab (`SR3CamLab\docs\TexLab-plan.md`, plan only), is meant to replace the label-CSV workflow below by
  pointing at a wall in a fly-around viewer; see 23_texture_pipeline.md, section 9.
- The classic variant took another route for sharper pictures: re-authored tiles in a `textures_hd` folder
  (23_texture_pipeline.md, section 5).
- The uv statement in "Method" ("the SR3 vertex format used holds uv 0..2") is superseded: uv is signed, -1 .. +1
  (23_texture_pipeline.md, section 3). The retexture steps were built before that was known.

## How to curate by hand (automated retexturing is SUSPENDED; this is the hand-over)
The mixed and all-SR3 steps, scripts, contact sheets and label tables are left as they were when the lane stopped.
Note: Desert and Forest tiles were re-exported with the right texel block AFTER their mixed / all-SR3 steps were last
built, and a few label overrides were added for the newly readable tiles (Desert 107..114, Forest 36..40); those steps
(26, 27, 32, 33) therefore predate these labels. The Mountain mixed / all-SR3 steps (35, 36) and all Lake Side steps
are current with their tables. step20 / step24 are the older Mountain builds.

Where things live (per course; Mountain uses `work/retex/`, the others `work/retex/src_<N>/`, N = 2 Desert, 3 Lake Side, 4 Forest):
| File | What |
|---|---|
| `classic_tiles_contact_colour.png` | every 1995 tile with its index and current class (magenta = transparent) |
| `classic_tiles_index.json` | index -> tile name |
| `tile_labels.csv` | THE mapping table: `index, tile, class, sr3_track, sr3_texture_id, note` |
| `work/courses/src_<N>.json` | per-course choices: `label_overrides` {index: class} (re-applied to the CSV on every build, so change a class HERE or delete the entry), `textures` {class: [track, id]} for the tiled classes, `art` (all-SR3 only) |
| `work/retex/art/<Track>/<id>.png`, `work/retex/art_<Track>_gfx_N.png` | SR3 textures decoded from the user's game files, and contact sheets with the ids |
| `work/scripts/allsr3.py` | composed pieces: `STYLES` (facade styles), `PIECES`, `BOARDS`, `CLASS_STYLES` |
Classes allowed in the CSV column `class`:
- tiled in metres with the texture of columns `sr3_track` / `sr3_texture_id` (hex id of a kind 4 chunk in that track's
  master_gfx file; empty = the class default from the JSON `textures` or `retex.SR3_FOR_CLASS`): rock, grass, dirt, sand,
  gravel, asphalt, cobbles, stone_wall, brick_wall, plaster, roof, wood, water. In the all-SR3 variant rock ignores
  the columns and uses `art.rocks` (+ `art.rock_tint` 0..1).
- picture classes (mixed keeps the 1995 tile; all-SR3 replaces it): house_plaster, house_stone, house_brick, church,
  arcade (composed facades), plaster_wall (tinted plain wall; sloping faces become roof), window, door, sign (SR3
  sponsor boards), tree_wall (SR3 tree row), crown, tree, bush, ivy, bare, trunk (cut-outs), lamp, fence (the 1995
  silhouette filled with SR3 metal), flat (grey roughcast), unlabelled (treated as flat).
JSON `art` keys: `rocks` [[track, id]..], `rock_tint`, `road_tarmac` / `road_dirt` [track, base id, top id] (must be a
pair listed in 10_surfaces.md: the ids select the physics), `tree_row` [track, id, width/height, v top, v bottom],
`class_styles` {class: [style names]}, `pieces` {windows, doors: [[track, id, [x0, y0, x1, y1]]..], crown, tree, bush,
ivy, wallfill, bark: [track, id, rect or null]}.
Adding a new SR3 source texture: `python work/scripts/sr3_art.py <Track>` (decodes every texture of that track to
`work/retex/art/<Track>/<id>.png` and makes the sheets) -> read the 8-digit id under the picture ->
`python work/scripts/art_grid.py out.png <Track>:<id>` for a gridded close-up when a sub-rectangle is needed -> put
track + id in the CSV row (tiled classes) or in the JSON `textures` / `art` (per course) or in `allsr3.py` (pieces).
The texture chunk is copied from that track's file at build time; nothing else to register.
Rebuild + re-render one course variant: `python work/scripts/import_classic.py src <N> <mixed|allsr3>`
(N = 1 Mountain, 2 Desert, 3 Lake Side, 4 Forest; writes `work/out/step.._<course>_<variant>_desert4` and
`work/previews/final_<course>_<variant>_*.png`). Proof sheet of the composed bays: `python work/scripts/allsr3.py`.
Known flaws, all-SR3 variant:
- all courses: rock texture seams where the projection axis changes, stretched on slanted faces; boards readable from
  the road side only; composed bays repeat on long walls; lamp posts / guard rails are 1995 silhouettes (the darker
  fill is in the script but those steps were not rebuilt with it: in the built Mountain step they still look like a
  white picket fence); tree crowns are one SR3 leaf mass stretched to each tile.
- Mountain: Canyon rock is redder than the 1995 tan even after the tint; church and tower are plain stone walls with
  gothic windows, the 1995 detail (rose window, arcades) is gone.
- Desert: brick walls use dark Lakeside brick where 1995 is light grey; SR3 window pieces are stretched to the 1995
  opening; shop signs are replaced by rally sponsor boards; the dirt road (Desert4 DryMud) is more orange than 1995.
- Lake Side: autumn colours are lost (all trees green); grass (Lakeside4 2ce6d1af) is much greener than the 1995 dry grass.
- Forest: the green cliff tiles are labelled rock and come out as Alpine rock with a visible repeat; the tunnel and the
  water crossing have no special treatment; one ivy tile shows as a green square on a wall.
