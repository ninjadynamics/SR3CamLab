# 26 - Mountain's patches 1 and 2 as rules for any 1995 course (`genpatch1995.py`)

Written 2026-10-12 for an agent that has none of the conversation behind it. Confidence tags as elsewhere: VERIFIED (and how), LIKELY, UNKNOWN.
Read [25_verbatim_road_and_milestones.md](25_verbatim_road_and_milestones.md) first (RAW settings, what a course patch file is, sections 6, 7, 9).

Owner's definitions: "patch 1 fixes bad authoring, patch 2 fixes bad design decisions, patch 3 complements and enhances the track".
The task this file answers: "UNDERSTAND and GENERALIZE what patches 1 and 2 did, so it can be reapplied to a raw import of the mountain
track and produce similar results (doesn't need to be byte identical) and generalizes well enough to patch the other SRC tracks ... not a
script that simply repeats the patch steps, but a script that generalizes such things as 'expanding the pavement on the road sides, so that
it covers all adjacent buildings and facades'".

Mountain's own files are NOT replaced by this: `courses\src.mountain.patch.1.json` and `.2.json` remain the approved result (the scene
`blender\mountain.patch2.forest.v12.zfight.blend`, build `step99_mountain_p2final_desert4`). The rules below are how to get the same kind of
result on a course that has no hand patches, and what to compare a new attempt against.

## 1. What is where

| File | What it is |
|---|---|
| `scripts\importer\genpatch1995.py` | the rules (one function a rule), the snapshot writer the importer calls, the patch writer, the audit |
| `scripts\importer\roadfill1995.py` | rule F's generator (older; `genpatch1995.write` calls its `generate`). Two opt-in module switches added for section 10: `FILL_BRIDGES`, `KEEP_SLABS`, both off |
| `scripts\importer\blendpatch\patch_compare.py` | two patch files side by side, tile by tile (generated against reference) |
| `scripts\importer\import_classic.py` | two opt-in settings: `patch_rules` (make the snapshot / the patch and stop) and `patch_files` (apply patch files given by path) |
| `scripts\importer\coursepatch.py` | one opt-in key read from a patch file: `"whole_polygons": true` (section 6) |
| `work\tmp\genpatch\` | output, outside the repository: `<game>.<name>.snapshot.pkl`, `.rules.json` (the patch), `.rules.report.txt`, `.rules.views.json` |

Why a patch FILE and not an importer stage: the owner inspects, diffs and hand-corrects patches, later patches stack on earlier ones, and
"a build does not run the generator" was already the convention for patch 2 (25, section 9). Why the file is not written into `courses\`:
`"patch": true` applies every numbered file there, so a generated file beside the hand patches would be applied on top of them. To adopt a
generated patch for a course that has none, copy it to `courses\<game>.<name>.patch.1.json` (and take the `whole_polygons` key with it).

Why the rules read the importer's face list at the patch stage and not a decoded build: (a) a build cuts every polygon whose tile repeats
more than twice into pieces (`build_classic.uv_split`); Mountain's 243 roof polygons arrive as 10,261 triangles, and rules made on the
decoded scene mistook those cuts for 1995 data; (b) the labels (`retex.labels()`), the road tiles (`BC.ROAD_TILES`) and the tile pictures
exist only inside the importer; (c) the faces there are exactly what a patch is applied to.

## 2. How to run it on a course

RAW settings are the lines of 25 section 4 ("RAW as a recipe"); below they are `$RAW` = one `--set key=value` per setting
(`light_contrast=0 fill=false handfill=false handmodel=false roofs=false seal=false verge=false lower_trees=false unsmear=false
mirror_groups=[] road_verbatim=true road_under=0.0 surface_default="tarmac"`, plus `light_dir` / `scene_gain` as wanted). Git Bash, in `scripts\importer`:

```
# 1. snapshot of the faces at the patch stage + the forest floor (10 s). Stops before building.
python import_classic.py src <N> classic --norender --name step99_gen_<name>_desert4 $RAW --set patch_rules=true
# 2. the rules (7 s). The importer's Python has no shapely / scipy; uv brings them.
uv run --with "shapely>=2.1" --with numpy --with scipy python genpatch1995.py ../tmp/genpatch/src.<name>.snapshot.pkl [out.json] [key=value ...]
# 3. a build with the patch (under a minute)
python import_classic.py src <N> classic --norender --name step99_gen_<name>_desert4 $RAW \
    --set 'patch_files=["F:/Jogos/SEGA Rally 3/SR3 track format/work/tmp/genpatch/src.<name>.rules.json"]' --set 'gate_dump="<somewhere>/gate.json"'
```

`key=value` after the snapshot overrides an entry of `CFG` for that run: `towns=all`, `only=FPW` (rules to run, letters of section 4),
any threshold. Per course, permanently: course JSON `"patch_rules_cfg": {...}` and `"patch_roles": {"paving": ["cobbles", ...]}`.
Step 1 runs the rules itself when shapely and scipy can be imported by the importer's Python.
NEVER run `--set patch_gen=2`: that is the old generator's own switch and it overwrites `courses\<game>.<name>.patch.2.json`.

## 3. How to check a result (do all four; numbers alone have misled before)

1. **The rules' own report** (`.rules.report.txt`, also printed): per rule what was found, made and left alone, with coordinates. Rule A's
   line must read `without area 0 ; thinner than 2 cm 0 ; ... lying on another face ... 0`.
2. **The build log** of step 3: `NOT FOUND among the polygons of this build: 0` (every triangle to remove was found), `z-fight gate: 0 coplanar + N
   near-coplanar` with every pair explained (the `gate_dump` file lists them; a pair whose other face is a board in front of a wall is the
   case of rule W below), `0 consistency problems`.
3. **Look.** Decode the build and render it: `preview_obj.main(<build>)` with `preview_obj.WORK` pointed at a folder OF YOUR OWN
   (the decoder writes `textures\tex_<id>.png` into ONE shared folder under `work\previews\sr3_decoded\`; every decode overwrites the
   pictures of the one before, so two sessions decoding at once show each other's textures - this happened, see section 9), then
   `blender -b --factory-startup --python blendpatch\bl_build_to_blend.py -- <decoded.obj> <out.blend> <patch.json>` and
   `blender -b <out.blend> --python blendpatch\bl_views.py -- <views.json> <ABSOLUTE out folder>` (a relative folder lands in `C:\`).
   `.rules.views.json` holds views of every town, hole and forest stretch the rules touched. Read the `_a` (textured) and `_b`
   (patch faces magenta with their edges) pictures: the wireframe must look hand-authored (few, large, fan-like triangles; no shards).
4. **Against a reference**, where there is one: `patch_compare.py <reference.json> <generated.json>`.

To audit a patch that was NOT made here (a hand patch, an edited scene):
`uv run ... python genpatch1995.py audit <snapshot.pkl> <patch 1.json> [<patch 2.json> ...]`. VERIFIED on Mountain: on the scene before the
owner's last fixes (scratch `p2_v12.json`) it lists the kerb top folded onto its side face (6 hits round (-384, 62, 8)) and the forest-floor
sliver lying on a bigger face ((-404.1, 68.1, 149.9)); on the final patches 1 + 2 it lists nothing lying on anything, and ONE triangle
thinner than 2 cm at (-218.8, 27.6, 520.9) (in patch 2, not looked at further).

## 4. The rules

What a polygon IS comes from its label class (`retex.labels()`, the CSV under `work\retex\...`), grouped into ROLES:

| Role | Label classes (default) | Used for |
|---|---|---|
| building | `house*`, `church`, `arcade`, `plaster_wall`, `brick_wall`, `window`, `door` | upright: walls. Lying or sloping (|normal y| >= 0.3): ROOF (Desert has no roof class; its flat roofs carry wall tiles) |
| roof | `roof`, and the tiles named in the course JSON `roof_tiles` / `round_exclude` (Mountain's village roof tile is labelled `dirt`) | roofs |
| paving | `cobbles` | town floor (and kerbs: told apart by width) |
| board | `sign`, `fence`, `lamp` | things standing in front of walls |
| forest | `tree_wall` | where the forest floor ends |

Everything else that is not a cut-out is "solid" (ground, rock, kerbs, low walls). A wrong label is a wrong role: check the contact sheet
(`work\retex\...\classic_tiles_contact_colour.png`) before trusting a run on a new course.

A TOWN is a group of buildings: the plan of all building and roof faces, closed up (grown by `close + margin` = 4 m, shrunk by `close` = 3 m),
pieces nearer than 2 x `town_link` = 40 m together. A town is PAVED when lying paving faces wider than `floor_min_width` = 2 m (a kerb top
is 1 m) of one tile cover at least `floor_min_area` = 25 m2 within 5 m of it; that tile is its floor tile. Mountain: 3 towns, 1 paved
(the town; the two villages in the forest are not).

### H - holes (patch 1)

- **What patch 1 is** (VERIFIED by sorting its 73 added faces into 15 connected places against the raw import): ten 2-triangle uprights of
  0.5 to 2 m2 in the stone kerb (missing end caps, slots between kerb pieces; kerb tile, 6 to 11 m from the centre line); three pieces of
  lying ground of 10 to 99 m2 (rock, dirt) 8 to 10 m out; and ONE place at 17 % of the lap: a lawn whose 31 corners were all moved by the
  same 2.2 m (1.44, 0, -1.64), four new lawn faces (85 m2) and a 98 m kerb of 30 faces drawn along it. Half of the small pieces stand on
  corners that are in no 1995 face: the owner drew them where it looked right.
- **Intent**: a hole the driver can see beside the road, small enough to be a slip of authoring, is closed with the surface it is a hole in.
- **Rule**: among the solid polygons within `hole_reach` + 15 m of the centre line, an edge used by ONE polygon is open (corners welded at
  1 cm). (a) RING: open edges that close into a ring of at most `hole_corners` = 8 corners, flat (within 35 cm of its plane), whose
  smaller extent is under `hole_max` = 2.5 m, with a neighbour facing the way the hole does (walked against the neighbours' own corner
  order, a hole turns the way its filling must; the outline of a face standing alone turns the other way and is skipped). (b) NOTCH:
  three open edges in a row making a U - two parallel jambs of the same length (25 %) and what joins them - flat (5 cm), mouth and back no
  wider than `hole_max`, both mouth corners held by another polygon. Neither is closed when a face of any kind already lies there
  (`Cover.on`: a board, a wall of another class). The filling is cut over the hole's own corners (ears), takes the tile of the neighbour
  with the longest shared border and is written WITHOUT a mapping: the importer carries the neighbour's picture on across the shared edge
  (`coursepatch.continue_uv`).
- **Thresholds**: 2.5 m is the owner's "every roadside hole under 2 m" with slack for a diagonal; 20 m is as far as the low chase camera shows
  ground; 8 corners keeps it to slips (a real opening has more).
- **How far it gets on Mountain: 1 of patch 1's 14 places** (the kerb end cap at (171.2, 16.1, 42.5); the other notch it closes, at (125.8, 15.6, 142.3), is NOT one of the owner's - corrected in section 10, which also has the opt-in rules that do find his kerb ends); 11 rings are
  found and none passes. The other small pieces are not bounded by open edges on all sides (their fourth side lies on the middle of a longer
  edge or on corners the owner invented), the ground pieces are larger than a slip, and the moved lawn is a judgement no rule here makes.
  **Patch 1 is NOT generalised; it is hand authoring.** JUDGEMENT CALL: nothing wider was attempted because 2,564 open edges lie within
  reach on Mountain and nearly all are meant (the far side of everything the camera never sees); a looser rule fills those.

### F - forest floor (patch 2)

- **Intent** (owner: "connect the forest sides of the road to the upright vegetation with the matching dark texture ... an accordion of
  triangles, no weird shapes, just a seesaw"): in the forest the soil verge ends in the air 5 to 15 m from the road and the forest wall
  stands on nothing further out.
- **Rule**: `roadfill1995.generate` as it stands (its own text lists rules R1 .. R13 and T1 .. T7, and 25 section 9 the history): cuts every
  metre find where the level ground ends and where the forest wall's foot is; ONE row of triangles from the one to the other, in the
  dark copy (0.32) of the soil tile most of the forest's roadside ground is made of; bridges are logged, not filled. It runs inside the
  importer (it writes the `_dk` picture beside the course's tiles) and its faces travel in the snapshot.
- **On RAW it gives exactly what it gave on the patch-1 build** (VERIFIED: the same 2,041 triangles in plan as the scratch
  `p2_generated_v6_backup.json`), so patch 1 is not a precondition.
- Faces of this rule count as ground already there for rule P (the pavement stops at them: the first run laid 40 pavement triangles on the
  forest floor at the town's west end; the audit found them).

### S - sea (patch 2)

`"settings": {"sea": {"clip": false}}` whenever the course JSON has a `sea`. Reason: the importer cut the sea sheet out under "land" and
counted the game's own road as land, which is not drawn any more (holes in the sea). Not geometry.

### P - pavement (patch 2), paved towns only

- **Intent** (owner: "expanding the pavement on the road sides, so that it covers all adjacent buildings and facades"; "sensible and simple
  (yet solid) geometry with no holes"; "Don't over complicate"): the 1995 square is a patchwork that stops at the facades' feet or short
  of them; from any camera but the 1995 one the buildings stand on nothing. The floor is taken out whole and laid again.
- **Rule**: area = the old floor's extent (every lying face of the floor tile within 40 m of the town, holes inside it closed)
  + the buildings' closed-up plan (so it is `margin` = 1 m "larger than the building's footprint") + the strip between town and road
  (anything narrower than 2 x `road_strip` = 5 m between the two: a facade 1.1 m from the road had left a 10 cm slit), less the road and
  less every other lying ground already there within 3 m of road height (kerb tops, rock, the forest floor of rule F). The outline is
  simplified by `simp` = 0.15 m; a corner that falls on the border of existing ground is moved onto one of that ground's own corners (of the
  four nearest: the one that keeps the piece valid, off the ground, and largest) - so every pavement corner on the road IS the road's
  corner. Each part is cut by constrained Delaunay over its outline corners only: no points inside. Heights: an existing corner keeps its
  own; a new outline corner is level with the road beside it (its two nearest road corners, weighted by distance); an existing corner more
  than `level` = 0.3 m off the road beside it is a wall top or a bank, not floor, and gets a new corner at road level. Picture: the floor
  tile, with the mapping of the old floor's largest face carried on in plan. Faces turn the way the old floor's did.
- **Not done when the town has no paved floor** (JUDGEMENT CALL): the owner dropped ground under the forest villages after seeing it
  ("let the trees and buildings float", patch 3), and on Desert the ground sheet already runs under every building.

### W - facades (patch 2)

- **Intent** (owner, 2026-10-12: "one facade, 2 triangles"): a 1995 house front is dozens of small faces, windows and shutters as faces of
  their own a few centimetres proud, each a z-fighting risk and a seam; every front becomes ONE flat four-cornered face with ONE picture.
  "A new facade at each change of height or change of building; neighbouring facades share corners"; "The bottom most edge of a building
  must touch the ground" / "no floating walls".
- **Rule**, in this order:
  1. WALL PLANES: the upright (|normal y| < 0.3), non-cut-out faces of building and roof role, unlabelled faces and boards within 40 m of the
     town, as triangles. A plane grows from its largest triangle and takes triangles within `thru` = 3 cm of THAT triangle's plane whose
     corners come within `near` = 15 cm (a row of houses round a bend is several planes). Small pieces up to 8 cm proud of a big plane
     (at most 15 m2 and 8 triangles, or touching it and under 40 % of it) join it: shutters, banners, door panels. A BOARD (sign) joins a
     wall only when it lies within `board_absorb` = 10 cm of it and wholly inside its span - it then goes into the wall's picture; a row of
     advertising boards that runs on past the wall stays a row of boards.
  2. STRETCHES: a plane's outline (openings inside it ignored) is cut at every step of its top or bottom line; quads that continue each
     other within 8 cm join. A plane is also cut where two BUILDINGS stand in it: an upright line no face crosses, at least 3 m from the ends
     and from the last cut, with less than 15 % of tile area in common within 8 m to its left and right, where a roof stands on the wall or
     the mean colour of the two sides differs by more than 0.06.
  3. FACADES: stretches that follow one another (ends within `join` = 0.30 m, turning less than `ang` = 14 degrees, top lines within
     `topdev` = 0.20 m, staying within `dev` = 0.25 m of the straight line between the far ends, not two different buildings) become one,
     laid flat between its two ends. A narrow strip with small pieces stacked over or under it is one strip; a small piece within the
     span of a facade three times its size joins it.
  4. CORNERS: facade ends within `join` are one point in plan; there, heights within 15 cm are one corner (so neighbours share corners, or
     an edge where their heights differ; a corner part-way along a neighbour's edge is put exactly on it, up to 8 cm). A corner within
     0.35 m / 0.15 m of a 1995 corner that a roof or anything else hangs on takes that corner's place.
  5. FEET: at each end the foot goes down to `under` = 2 cm below the floor (new pavement, road, lying ground) when the floor is within
     `maxgap` = 2 m under it. Not when a POST stands there: an upright face narrower than `post_width` = 0.6 m and at least 1 m tall,
     within `post_reach` = 1.5 m, reaching from the floor to the foot (Desert's verandas: the upper wall stands on posts and was first
     carried down behind them as a smeared slab).
  6. PICTURE: every triangle of the planes used becomes a source of the patch's `bake` entry (`facadebake.py` composes it at import time:
     nothing of SEGA's ships, only the recipe); bigger triangles first so a window painted over its wall wins; texels no source reaches
     (the part carried down, closed openings) take the nearest painted one. Size: width and height in metres x the 90th percentile of the
     sources' texel density, rounded up to a power of two, at most 2048; all pictures of a town together at most `facade_megapixels` = 12
     (the largest is halved until they fit; Mountain's town needs 7.9, Desert's 148 halvings).
  7. A wall that already IS one flat face with one tile on its own corners is left as it is (Mountain: 16, Desert: 83).
- **Boards in front of walls** (owner's finding, 2026-10-12): two Mountain facades had a 1 m slot at the foot exactly where a row of SEGA
  advertising boards stands 6 to 8 cm in front: 1995 left the wall out behind the board. Carried down, the wall stands just behind the
  board and the importer's z-fight gate lists a near-coplanar pair. The owner ACCEPTED those two pairs. The rule therefore carries the foot
  down and REPORTS every board within `board_gap` = 0.30 m in front of a facade (line `BOARDS standing ...`); the generated Mountain build
  shows the same two pairs as the reference and no others. JUDGEMENT CALL: leaving the slot would also be right ("the board hides it") and
  would cost no gate pair; the owner's "no floating walls" decided it.
- **Things hanging on a wall between its ends** are brought onto the flat facade: roof corners (rule R reads the moved places). Corners of
  OTHER things (not roofs) at such places are not moved - UNKNOWN whether any exist on the other courses; none was seen on Mountain.

### R - roofs (patch 2)

- **Intent**: every roof reduced to its flat sides, welded to the facade tops and to the next roof ("everything connected (vertices)").
  The thousands of small roof triangles of a decoded build are the build's own cuts, not 1995 data: at the patch stage Mountain's town has
  443 roof triangles and the rule gives 366 for the 33 roofs it lays again; the gain is the welding, not the count.
- **Rule**: roof-role faces of the town as triangles; PIECES by shared corners; in a piece, FLAT SIDES = triangles facing the same way
  (0.999) within 5 cm of the largest one's plane and touching; a side's outline is simplified by `roof_simp` = 5 cm; outline corners of
  different sides are one point within `roof_join` = 8 cm (same roof) or `snap_r` = 0.35 m (neighbouring roofs); a point with a facade corner
  within `snap_f` = 0.6 m in plan and 0.35 m in height goes onto it; a corner of another side standing on an edge (4 cm) becomes a corner of
  that edge (no corner on another face's edge); constrained Delaunay over the corners only. Mapping: the side's own when all its faces
  agree (0.02), else one even mapping at their median density. A roof that would come out with as many triangles on the very same corners
  stays as it is; a roof one of whose sides cannot be laid out stays as it is and is named in the report.

### D - walls down (patch 2)

A building wall that was NOT made into a facade and whose foot edge hangs above the floor (within `maxgap`) is carried straight down to
2 cm under it, by two triangles a foot edge, in the wall's own tile using only its lowest 15 cm (no window or door of the wall above
lands in the base). Not where another face of the same wall stands under the edge. Mountain: none needed (the facades took them all).

### A - audit

Run on everything the patch adds, against itself and against what stays: faces without area; faces thinner than `sliver` = 2 cm (twice the
area over the longest edge); added faces LYING ON another face (normals within 2 degrees, every corner within `onface` = 3 cm of the other's
plane, overlap over 0.02 m2 and 2 % of the smaller). The last one is what catches a face folded onto its neighbour and a sliver lying on a
bigger face - the two defects the owner repaired by hand in the final scene. It is a report, not a gate: read it.

## 5. What the rules keep, and the trap

- "no z-fighting bait allowed": nothing added may lie on anything (rule A; the build's gate is the second opinion).
- "everything connected (vertices)": pavement corners on the road are the road's own; facade neighbours share corners; roof corners sit on
  facade corners. Nothing here welds by distance over the whole mesh, and nothing may: **tree blades are back-to-back face pairs on the same
  corners and a global merge-by-distance deletes one side of each.**
- "all new geometry should be triangulated": every added face is a triangle.
- no zero-area faces (dropped at writing, counted by A).
- "must look hand-authored in wireframe": no interior points anywhere; fans from the road's corners; two triangles a facade.
- gap fills are natural ground or the surface the hole is in, never invented structures (which is why the side walls of section 7 are not made).

## 6. The patch file it writes

Format of 25 section 7, version 3 when it carries pictures. Coordinates: the decoded scene's (SR3 x - ox, y, -(SR3 z - oz)).
`remove` lists triangles of the IMPORTER'S OWN polygons (fan 0-1-2, 0-2-3, in the polygon's corner order), not of a build's pieces, and the
head carries `"whole_polygons": true`: `coursepatch.remove` otherwise cuts a polygon into the pieces a build shows whenever some triangle to
remove has a corner at one of those pieces' corners - a coincidence on Desert that left 3 walls in place under their new facades
(60 coplanar pairs at the gate; VERIFIED gone with the key). Hand patches made by `scene_diff.py` do not carry the key and behave as before.
`base.needs` is empty: the file stands on the raw import alone.

## 7. What it deliberately does not do (found by elimination: what is in patch 2 that no script explains)

(Section 10 goes through each of these place by place and gives the opt-in rules that were then tried for them.)

| In the approved Mountain scene | Size | Why not here (by default) |
|---|---|---|
| Side walls on 8 buildings, wearing their facade's picture (facades of 4 and 6 triangles) | 13 walls, about 3,600 m2 | an invented wall and a choice of picture; `roofs1995.eave_walls` (off in RAW) is the nearest existing code |
| Forest floor on both sides of the bridge | 2 x 1,700 m2 | rule F logs bridges and leaves them (owner's rule R7), the owner then filled this one by hand |
| 20 forest-floor faces in the soil tile as it is, not the dark copy, at the two villages | 427 m2 | the owner's taste per place ("within 15 m of houses" was tried as a rule and dropped) |
| 5 kerb-top faces round (-384, 62, 8) | 10 m2 | a repair of a fold that is NOT in the raw import (the raw kerb tops there are sound; the fold came in during editing) |
| The moved lawn and its 98 m kerb (patch 1) | 31 corners, 34 faces | see H |
| A sliver deleted, corners nudged | - | hand fixes; the audit finds their like |

Also not done: ground under unpaved villages and under trees (patch 3); cliff sides, plateaus (patch 3); anything about cut-out faces
(trees, fences); the backdrop.

## 8. Results (2026-10-12, builds `step99_gen_<name>_desert4`, patches in `work\tmp\genpatch\`)

### Mountain, generated on RAW, against the approved patch 2 (`patch_compare.py`)

| Operation | Reference | Generated | Notes |
|---|---|---|---|
| Forest floor | 2,059 tri, 41,261 m2 | 2,041 tri, 38,062 m2 | 37,195 m2 in common; the reference's extra is the bridge (hand); 329 m2 only here are faces the owner deleted or made bright |
| Pavement | 326 tri, 14,405 m2 | 322 tri, 13,965 m2 | 13,957 m2 in common; 448 m2 only in the reference in scattered strips (largest 28 m2), 7 m2 only here; 212 of its corners are the road's own |
| Facades | 106 pictures, 238 tri, 8.4 MP | 92 pictures, 184 tri, 7.9 MP | 73 are the same facade (middle within 1.5 m, width within 1 m), feet within 5 cm; 16 walls left as the single face they were; the rest differ by a seam more or less (5 places) and by the 13 hand side walls |
| Roofs | 548 tri, 10,739 m2 | 366 tri, 8,380 m2 + 10 roofs left untouched | with the untouched ones the plan areas agree to 30 m2 |
| Walls taken out | 19,409 m2 | 18,022 m2 | the difference is the 16 walls left as the single face they were |
| Holes (patch 1) | 14 places, 73 faces | 2 places, 4 faces (1 of them his) | see H, and section 10 (opt-in rule C finds all 11 of his kerb ends) |
| Sea setting | yes | yes | |
| Build | gate 0 + 2 (the two boards) | gate 0 + 2 (the same two boards), 0 not found, 0 consistency problems | 91,339 vertices |

Looked at side by side from 9 places (square from both sides, the west and east rows, street level, straight down; textured and
wireframe): the two builds are hard to tell apart except for the hand side walls and the church tower (a facade in the reference, left as
its own faces here).

### Desert (course 2), `towns=all` (it has no paving class: with the default `towns=paved` only F and H run)

93 facades from 909 triangles (83 walls left as the single face they were), 58 feet carried down, 1 left on its posts, 33 roof triangles
for 8 roofs (45 untouched, 5 could not be laid out and were left), 148 picture halvings to stay within 12 MP; forest floor 180 triangles
(267 m2, six narrow bands). Build: every triangle found, gate 0 + 0 (the raw build: 0 + 0). Looked at: fronts read as before, each wall two
triangles. WRONG OR DOUBTFUL there: (a) 58 feet carried down is a lot - the town stands on sloping ground and many walls end above it at one
end; the smear of the wall's lowest row over up to 1.7 m is visible on pale walls; (b) only 1 of the veranda walls was recognised as
standing on posts, the post test looks at the facade's two ENDS only; (c) the picture budget halves Desert's facades hard (55.7 MP wanted):
either its tiles are denser than Mountain's or the 90th percentile is pulled up by small faces - not examined; (d) a gable wall becomes a
four-cornered face with a sloping top, which fits only when the outline test passes - worth a look per house.

### Forest (course 4) and Lake Side (course 3): no buildings, so F and H only

Forest: 2,129 forest-floor triangles (24,314 m2, ten bands), 1 notch closed (a stone wall slot at (-200.6, 95.8, -33.8)); the build's gate
shows 677 pairs, NONE with a patch face (the raw course's own: an unlabelled tile `col_000` under cut-outs - a matter for the import, not
for these rules). Lake Side: 1,003 triangles (19,906 m2, six bands), no holes; gate 1 pair, not a patch face. Looked at (two views each):
the band runs from the verge to the forest wall as on Mountain. On Lake Side it has upright slivers where the forest wall steps (a known
blemish of the generator: 25 section 9.1 (d)); on Lake Side 235 tiles count as road surface, which says the labels there need a pass
before anything is trusted.

## 9. Open problems and judgement calls, most important first

1. **Patch 1 is generalised only in part** (default rules: 1 of 14 places; with the opt-in rules of section 10: its 11 kerb ends and 1 of its 3 ground wedges; the lawn not). A rule for the kerb slots needs the notion "this kerb continues": follow the kerb's top
   edge and close where its side face is missing. Not attempted.
2. **`towns`**: `paved` (default) reproduces the scope the owner approved on Mountain; `all` is what the rules mean ("every building front").
   With `all`, Mountain's two forest villages get 29 + 16 facades and their roofs welded - built, not looked at closely, not shown to the owner.
3. **Side walls** (section 7) are the largest thing the approved scene has that the rules do not make.
4. **The building seam test** (W2): the rule it was ported from asked for "a roof corner at the line", which on a decoded scene was true
   nearly everywhere because the build had cut the roofs into pieces. Here it is "a roof stands on this wall, or the colours differ".
   Against the reference that splits three 13 m fronts in two that the owner's scene keeps whole, and misses three 7.2 + 7.8 m pairs.
5. **Feet behind posts and boards** (W5): ends only; and the board case follows the owner's acceptance, not a principle.
6. **Role tables are label-driven**: a course whose buildings carry a class not in `ROLES` gets no town. Desert worked by adding
   `plaster_wall`, `brick_wall`, `window`, `door` to the defaults; `wood` (roofs, porches) is NOT a building class and its faces stay.
7. **Quads are cut 0-1-2 / 0-2-3 for the pictures**; where a 1995 quad is not flat and the build cuts it the other way the picture can
   differ by a texel row. Not measured.
8. **The decoder's shared texture folder** (section 3, point 3): fix it properly by giving `preview_obj.main` an output folder argument.
9. The thin triangle in the approved patch 2 at (-218.8, 27.6, 520.9) (section 3).

## 10. The owner's hand edits, place by place: what, why, and whether a rule can do it (added 2026-10-12, second pass)

Everything in Mountain's patches that no script made. How the list was drawn up: patch 1 is hand work whole (73 added faces sorted into
places by shared corners and nearness: 14 places; an earlier count of 15 took the lawn and its kerb as two). For patch 2, every added face
of the approved file was tested against (a) what the rules generate on the raw import and (b) the raw faces themselves: a face whose middle
lies on neither is unexplained (143 faces, 8,466 m2, 27 clusters). Each place was then rendered from the road side and from behind, in
three scenes: the raw import, the approved scene, and (for the forest floor) the generated patch before the owner touched it. Coordinates
are the decoded scene's (x, y, z). "Lap" = how far round the lap the place is. Where a reason is not known it says so.

### 10.1 Patch 1 (14 places)

| Place | Where (x, y, z), lap | Raw import | What the owner did | Why (read from the stills) |
|---|---|---|---|---|
| Kerb ends, 10 places | (180.9, 21.3, -146.6) 23 % ; (191.6, 21.9, -162.1) 24 % ; (-12.0, 37.3, -143.3) 31 % ; (-159.4, 79.0, -430.5) 51 % ; (-374.9, 68.8, 160.8) and (-366.8, 68.8, 152.0) 73 % ; (-422.1, 35.7, 366.2) and (-431.2, 35.7, 346.3) 86 % ; (-355.5, 24.5, 476.8) and (-361.0, 24.5, 487.2) 92 % | the stone kerb / low wall beside the road (an upright face towards the road, 0.7 to 2 m tall, and a flat top 0.3 to 1 m wide; some have a back face too) simply stops: its END is open | one upright rectangle (2 triangles, 0.5 to 2 m2, kerb tile) closing the kerb's cross-section at its end | a car coming towards the start of a kerb looks straight into its open end: a hollow shell with the sea or the forest floor showing through where the stone should be. In the forest (73 %, 86 %, 92 %) both ends of a kerb piece are met one after the other; on the cliff road (23 %, 31 %, 51 %) the kerb ends against the rock and the gap between the two showed the sea. One more of these is inside the lawn place below, at (171.2, 16.1, 42.5) |
| Ground wedges, 3 places | (44.3, 32.2, -110.0) 29 %, 18 m2 of rock ; (-188.8, 55.8, -276.1) 39 %, 10 m2 ; (-148.5, 57.6, -288.2) 40 %, 99 m2 in 14 faces | where the verge, the kerb's end and the foot of the rock meet, the three do not close: a wedge with nothing in it, 8 to 10 m from the centre line | the wedge filled with ground in the neighbouring tile, drawn over the surrounding corners plus some corners of his own | the SEA shows through the wedge. The second and third are in plain sight from the road at the foot of the rock; the first lies behind the 1 m kerb and is seen from above it. The third fill is much larger than the hole that shows (seen from above the hole is 18 m2): he carried the ground on behind the rock foot - why that far is not known |
| The lawn | (112..171, 15.1..15.6, 43..142), 16 to 17 %: 34 new faces, 31 corners moved | a lawn lies between the road and the top of the sea cliff; its far edge stops about 2 m short of the rock's rim along 98 m, and at its east end a bay is not covered | the lawn's far row of corners moved 2.2 m outwards, all by the same (1.44, 0, -1.64); a skirt of 28 upright rock faces up to 1.2 m tall along the new edge; 4 lawn faces (85 m2) over the bay; a kerb end cap | the sea showed as a blue band between the grass and the rock, from the road (over the roadside kerb) and from above. The uniform shift says he selected the edge and dragged it, then closed the height step it left against the rock with the skirt |

### 10.2 Patch 2

| Place | Where | Before | What the owner did | Why |
|---|---|---|---|---|
| Flanks ("side walls"), 13 on 8 buildings | all round the town square: south side fronts at z about 503 (x -76 to 0), north side z 545 to 566 (x -127 to -19); for example (-52.5, 25.4, 495.4), (-36.1, 25.1, 494.7), (-97.8, 25.2, 566.3), (-125.0, 23.0, 549.6) | every building is ONE front (a board) with a roof behind it; nothing on its sides or back | from each end of the front a wall running BACK along the roof's side eave (10 to 19 m), as tall as the front, showing the front's whole picture; at (-5, 31, 511) also 3 roof faces closing the roof above the new flank | square-on from the road nothing changes (checked: the stills are the same). From behind and from above the buildings were boards with a roof hanging behind them; with flanks they read as boxes. WHY he wanted that is NOT known. Possibilities: (a) a flank is seen from the road above a lower neighbour and through the gaps of the square; (b) replay and free cameras; (c) the cliff side of patch 3 looks at the south row from behind; (d) the later ray-traced light needs walls to cast and stop light. Why these 8 and not the other fronts with a free eave (rule B finds 57) is not known either |
| The "bridge" | both sides of the road from (-417, 62, -126) to (-386, 59, -59), 65 %: 62 faces, 3,520 m2 | a 74 m stretch between the two forest villages with a 2 m parapet on both sides, round trees standing in the air beside it, the forest wall 19 m out; the forest-floor generator calls it a bridge and leaves it | the dark forest floor laid on both sides, parapet to forest wall, as everywhere else in the forest | from the driver's seat nothing shows (the parapet hides it; checked). From any higher camera the trees stood over the sea. He treated it as a walled road through the forest, not as a bridge: there is nothing under it to bridge |
| Village gaps, 7 places | between two houses each: (-399, 72, -238), (-428, 70, -227), (-395, 59, -23), (-374, 61, 11), (-408, 62, 9), (-425, 66, 59), (-418, 68, 110) | the generated band runs behind the houses and sends a tongue forward between each pair of houses to the road; there its corners stood on the TOP of the 1 m kerb, so the tongue climbed a metre and showed a kink | the three triangles of each tongue laid again with those corners 1.0 m lower, at the kerb's foot | the generator's own rule ("uprights are met at their foot, never at their top") was broken at the kerb; the owner at the time: "after four tries at the village's floor height ... I'll fix it myself" |
| Village ends, 3 places | (-381, 78, -300) and (-398.5, 78.5, -322.5), 59 % ; (-397, 68.5, 145), 72 % | where the 1995 soil verge ends and the first house begins, the generated band came forward to the road as a black slab; in two places a sliver of sea showed inside the band where it steps | the slab cut again as a fan; its part beside the road in the verge's own BRIGHT soil tile (20 faces, 427 m2), dark only behind; the slivers closed | the black slab at the roadside read as a hole next to the lit verge. The bright soil contradicts the rule he gave earlier for the generator ("dark patching. always."): taste per place, decided by looking |
| Kerb top | 5 faces round (-384, 62, 8) | NOT a defect of the raw import (its kerb tops there are sound): two top corners had been dragged 1.4 m down onto the foot during editing, folding the top onto the side | the top put back (made in the main session) | repair of an editing slip; `genpatch1995.py audit` finds its like |
| Smaller differences | roof face at (96, 35, 332); pavement pieces at (59, 14, 494), (105, 15, 143), (-189, 15, 552), (-192, 15, 510) | - | - | LIKELY not hand edits but the earlier scripts cutting the same outline differently from this file's rules; elimination cannot tell them apart |

### 10.3 The kinds, and the rules tried

All of them are OPT-IN. With none switched on, the generated patch is byte for byte the one of section 8 (VERIFIED by comparing the files).
Switches: `only=` takes the extra letters `C` (kerb caps), `G` (holes seen from above), `B` (flanks); `forest=bridges` / `gaps` / `bridges+gaps`;
`forest_foot=true`. Example: `... genpatch1995.py <snapshot.pkl> out.json only=HFSPWRDACG forest=bridges forest_foot=true`. The forest
variants are made in the importer and travel in the snapshot (make the snapshot again with this version). A Mountain build with all of them
on (`step99_gen_mountainmanual_desert4`): every triangle found, gate 0 + 2 (the same two boards), audit clean.

| Kind of edit | Rule | His places reproduced | Other places it touches on Mountain | Desert / Forest / Lake Side |
|---|---|---|---|---|
| Kerb end caps (11) | `C`: an open end edge of an upright face and an open end edge of a flat top, of ONE kerb (the two faces share an edge), meeting at the top corner at a right angle, each 0.2 to 2.5 m long: the rectangle they span is the cap; its fourth corner is new, straight under the top's far corner. Plus the older notch rule in `H` (three open edges) | **10 of 10** by `C`, with his areas; the 11th by `H` | 3 by `C`: kerb ends that butt against the rock at a tunnel mouth, (182.2, 19.4, -109.5), (194.2, 19.4, -109.5), (194.0, 17.9, -70.9): the cap is hidden against the rock (looked at: no visible change). 1 by `H`: a kerb end beside a house at (125.8, 15.6, 142.3). CORRECTION: the first report counted that one as his; it is not | 0 / 2 (stone wall ends at (-186.4, 95.8, -38.9), (-74.0, 88.1, -313.4), not looked at) / 0 |
| Ground wedges (3) | `G`: seen from straight above, a hole of 0.3 to 20 m2 in everything that is there, all of it within 20 m of the centre line, its rim within 2 m in height: closed over the corners round it, in the tile of the ground beside it | **1 of 3** (the third, and only the 18 m2 that show, not his 99 m2). The second is 0.7 m2 from above and has too few corners round it; the first is a BAY open towards the sea, not a hole | 1: 2.1 m2 at (179.0, 17.9, -57.0) (under a tree; not judged) | 0 / 0 / 9 small holes (1.8 to 6.5 m2) along (-450..-330, 43..52, -377..-337) and one at (114, 50, -399), not looked at |
| The lawn; the first wedge | NOT MADE. Tried: closing the plan over gaps of 2.6 m and of 5 m | 0 | that closing fills 51 and 59 bays (764 and 1,324 m2) and finds neither the lawn's gap nor the wedge | - |
| Flanks (13) | `B`: for every front made by rule W, a level roof edge at least 3 m long that starts at the front's top corner and runs back (more than 50 degrees off the front) gets a wall under it, unless an upright building face stands under that edge already; one flank where two buildings meet (the taller's) | **9 of 13** (within 2.5 m). 3 of his have no such roof edge at their corner | **48**: 11 more on the square itself, 37 in the street rows (most between two adjoining buildings, where nobody can see them; some at row ends that stand free and that he left open). `flank_expose=<m>` keeps only fronts that much taller than their neighbour; it does not separate his from the rest (his: -0.8 to 4.8 m; the others: -4.8 to 16.3 m) | 19 on Desert (every building there has a free eave; not looked at) / - / - |
| The bridge (2 sides) | `forest=bridges`: the generator's bridge exclusion off (`roadfill1995.FILL_BRIDGES`) | one side whole (99.9 % of his area), the other 38 %; 2,340 of his 3,497 m2 | **0**: nothing outside his area | Desert: no change / Forest: +132 triangles / Lake Side: +1,155 triangles (the generator calls 10 stretches there bridges, 2 km in all; most are surely not bridges: look before using) |
| Village gaps (7) | `forest_foot=true`: a corner of the forest floor that stands on the top corner of an upright face 0.3 to 1.5 m tall, while the floor's other corners there are lower, goes down to that face's foot | 18 of the 20 corner uses he lowered by 1.0 m, to his height | **0**: every other corner of the band stays at the height it has in his scene | 0 / 0 / 0 |
| Village ends: bright soil | NOT MADE | - | - | - |
| Village ends: slivers in the band | covered by `G` in principle (it runs last and counts holes inside the band); on Mountain the two slivers are under 0.3 m2 from above and stay | 0 of 2 | 0 | - |
| Kerb top repair | not a rule: `audit` | - | - | - |

`forest=gaps` (bands wider than they are long are kept: `roadfill1995.KEEP_SLABS`) was made on the guess that the village gaps were
slabs the generator had dropped. They were not (the default band already covers them, at the wrong height): it changes nothing on Mountain,
adds 12 triangles on Desert and 45 on Lake Side, and none of that was looked at. It is left in as a switch, not as a recommendation.

### 10.4 What a rule would lack, kind by kind

- **The lawn**: that the grass SHOULD reach the rock. In the data there are two open borders 2 m apart for 98 m; the course has
  thousands of metres of such pairs (every roadside wall has open ground behind it) and nothing in the geometry says this pair is one
  surface cut short. He saw the sea between them. A rule would need to know what is seen from the road: rays from the driver's eye along
  the lap that pass between two surfaces and reach the sea. That test was not built; it is the honest general form of "a hole the driver sees".
- **The first wedge, and how far he carried the third**: where the fill ends. A bay has no rim on its open side; he chose the corners.
- **Which buildings get flanks**: unknown (see 10.2). Geometry offers "a roof edge with no wall under it", which is true of 57 places.
  If the answer is "all of them", rule B is his rule and the 48 are places he had not got to; if it is "those seen from somewhere",
  the rule needs that somewhere.
- **3 of his 13 flanks**: there is no level roof edge leaving the front's corner; he laid the flank by eye (two are exactly as long as
  the front is wide: a copy of the front turned about its end).
- **Bright or dark soil**: nothing in the data. His stated rule says dark; his hand said bright beside the road at a village's end.
- **The bridge's second side**: the generator's own march ends early there (38 %); why was not examined.

## 11. Extending it

Each rule is one function taking the `Scene` (faces in decoded coordinates with class, role, normal, area; `sc.rm` = triangles to remove,
`sc.put(tile, corners, uv, rule letter)` = a face to add, `sc.note(rule, text)` = a report line, `sc.view(name, place)` = a picture to
take). Add the function, call it in `run()` in the order its inputs need (ground before pavement, pavement before facades, facades before
roofs), give its thresholds to `CFG` with the reason, and let rule A see what it adds. Work on the snapshot (seconds), build only to check.

## 12. Patch 3 (the Blender scene v11, accepted 2026-10-15): what the owner did, why, and what goes by rule

The owner, 2026-10-15: "Mountain R4 is accepted, which means v11 is accepted too" (25, section 5.3: `courses\src.mountain.patch.3.json`, staged:
the generated patch 3 of 2026-10-12, the board moves, the v11 scene's 4d); then "pick up generalization" - the task of 2026-10-11 / 12 now for
patch 3: "explain my manual patches (what and why I did it) ... AND, IF POSSIBLE generalize them as well", results "sound, with proper
geometry and no holes", "generalizes well enough to patch the other SRC tracks".

### 12.1 What it holds, measured (`blendpatch\patch_places.py`, `patch_kinds.py`, `kind_places.py`)
- Stage 1, the generated patch 3 of 2026-10-12 (`patch3_1995.py`): 3,641 faces, 80,000 m2 in two places: the PLATEAU hand model (51,500 m2 of
  rock, 64 % upright, at (-267, 108, -204)) and the CLIFF SIDE along the coast road (28,600 m2, mostly lying rock and grass, x 59..262, 676 m long).
- Stage 3, the v11 scene against the patch 1 - 3 build: 34,385 faces added (512,000 m2), 27,860 triangles removed (209,000 m2). An added face
  is RECUT when a removed triangle of its tile lies in its plane under its middle (the same surface in other triangles), MOVED when one is
  within 1.5 m but not in its plane, NEW otherwise: RECUT 130,000 m2 (25 %), MOVED 3,900 m2 (1 %), NEW 378,000 m2 (74 %).
- NEW by kind (classes from the labels; a picture composed from tiles = a facade): rock walls 120,000 m2 (16 places) ; grass and soil lying
  107,000 m2 (16) ; facades 95,000 m2 (18) ; rock lying 20,000 m2 ; pavement 11,800 m2 (2) ; roofs 9,900 m2 (16) ; trees 8,700 m2 (15).

### 12.2 The kinds, place by place (renders before = the patch 1 - 3 build, after = v11; `scratchpad\patch3\kinds_a.jpg`, `kinds_b.jpg`)
| Kind | Where (decoded x, y, z) | Before | After | Why (the owner's words, 2026-10-12 / 13) |
|---|---|---|---|---|
| The castle island | (385, 21, 22), 280 m across: grass 44,500 m2, rock ground 4,800, trees 8,700, castle courtyard paving 3,400, castle walls | a ring of trees and the castle's boards standing over the sea | a whole island: grass top at the rim's height, rock cliff round it down to the sea, the castle standing on it, trees on the grass | "complete the castle island and infill with natural terrain ... using the existing 1995 texturization, don't deviate" ; "use natural ground but not much higher (or lower for that matter) than the 1995 rim" ; "trees should stand on grass which may give in to rock" |
| The mesa / plateau | (-275, 70, -210): walls 34,000 m2, top grass 14,200 at y 122..127, a composed rock picture on the walls (33,000 m2) | the generated plateau model (rock everywhere) | walls carried down to the sea, a grass top | "Redo the big mesa/plateau from the old version. Make it pretty and natural without straying away from the 1995 look. Fill all the mesa/plateau tops you can find" ; "make the top of the mesa look like every other seastack (with grass)" |
| Sea cliffs and stacks | (-81, 29, -332) walls 38,300 m2 ; (72, 12, -391) 14,600 ; tops (77, 106, -344) and (73, 99, -430), 2,366 m2 each | the 1995 cliffs stop in the air above the sea; stack tops open | walls down to the water; grass caps | "cliff it down" ; "fix the hole that seastack/karst" ; the tops as above |
| Ground under the floating trees, the coast road | (160, 10, 120): rock walls 8,700 m2, rock ground 10,800 m2 | trees standing over the sea beside the road (the 1995 game's own: "lot's of trees floating in the air, above the sea, in the Model 2 lap, lol what was SEGA thinking?") | a cliff edge widened where trees stand near it and narrowed where none do, natural ground under the trees | "widen the cliff in places where trees are close to the edge and narrow the cliff in places with no trees. the widening and narrowing should be rough (natural), but graceful" ; "make sure the ground at the top of the cliff is irregular (yet natural) enough to ensure no tree is floating in the air (roots underground allowed)" |
| The tunnel top | (7, 34, -104): grass 2,900 m2 ; rock (-64, 30, -172) 7,200, (20, 13, -163) 4,600 | holes in the arch, the rock top open | arch holes closed, the top filled | "fill the top of the tunnel, using the trees as reference to the ground level" ; "patch all these holes in the tunnel arch ... longitudinally the arch should bulge slightly up at the middle" |
| The town | (-5, 23, 389) facades 51,700 m2, pavement 8,400, roofs 9,900 in 16 places ; south side ground (-15, 13, 388) 17,300 | fronts as cardboard, many small faces | every building a box with roof; a second row behind the front row; the facades welded (rule W's "one facade, 2 triangles") | "Expand the town inwards as well, using copy-pasted completed buildings (4 walls and roof) and completing the existing ones" (v6) ; v10: weld window / door faces into the wall, "one facade, 2 triangles", "every facade connects ... to the next one" |
| Re-cut, welded, re-mapped | everywhere (130,000 m2 RECUT) | thin triangles, corners nearly on each other, smeared pictures | the same shapes in mid-sized triangles, corners merged, pictures re-mapped | "I want mid-sized triangles ... the shapes themselves !!!!!CANNOT CHANGE!!!!!" ; "merge all [vertices sharing the same position], excluding sprites" ; "fix all the 1995 smeared textures" |
| Trees moved | 792 cut-out polygons moved whole (the board moves stage) | trees clipping through rock or standing beside the new ground | on the new ground | "the tree on the left is clipping through the rock. move it to the corner of the grass" |
What he did NOT keep: the island infill inside the track ("I'm dropping the island infill for now because I want to get this project moving to
other tracks"; "the full island infill will be patch-4"). His standing rules for all of it: "don't change or protrude (through) 1995 geometry
unless I ask you to"; ground at the lowest level that makes sense; extend ground from the road's vertices; textures as asked (the memory note
"infill ground rules"); "The inner side of the track shouldn't be cliffs"; "it shouldn't scream 'this wasn't here before' to seasoned
players"; "We're adding all this stuff because of 2 things: 1. We want to fix 1995's mistakes and missing geometry 2. the extra camera angles".

### 12.3 The rules made (OPT-IN letters K and T; the default `only=HFSPWRDA` writes the patch of 2026-10-12 byte for byte, VERIFIED)
- **K - cliffs down**: a natural face standing upright (label class rock / grass / dirt / sand / gravel, no role) whose foot is an open edge
  (used by one polygon), level, at least 0.5 m long, hanging more than 0.3 m (and up to 80 m) above the sea or the ground, is carried straight
  down to it, in its own tile with its own mapping continued. Not: the sides of the road deck or verge (within 12 m of the centre line, top
  less than 2 m above it: the first try hung curtains under the bay's bridge, which the owner left open), anything standing on or within 6 m
  of the road, and FINS (a run of foot edges joined end to end shorter than 6 m or than a quarter of its drop). Mountain: 245 foot edges,
  490 triangles, 51,000 m2, drop median 22 m (the owner's NEW rock walls: 120,000 m2, much of it on the mesa and the island, which K cannot
  find on the raw import). Build: z-fight gate 0 + 0, 0 consistency problems. Looked at (`scratchpad\patch3\kt_sheet2.jpg`): the stacks' and
  the sea cliffs' walls reach the water as his do; LEFT WRONG: one long foot edge high on the cliff over the bay carried 79 m down as a
  single thin sheet, and a few narrow strips beside the mesa (a fin test by the run's own width would be the next step).
- **T - tops**: seen from straight above, a hole of 20 .. 16,000 m2 whose rim is level (within 3 m + 0.08 x its width) and whose own faces
  hang at least 1 m DOWN from the rim (a stack, a mesa, a rock - this keeps bays and the island inside the track out) is capped over the
  rim's own corners; grass (the course's grass tile nearest by) when the course has grass, else the rim's tile. Mountain: 5 tops, 68
  triangles, 9,470 m2 - among them the two stack tops he capped (2,361 m2 each against his 2,366, the same places), the top at (14, 65, -209)
  (2,271 against his 2,275) and one more stack (-19, 83, -266). The mesa top is not on the raw import (the plateau model is patch 3's own).
- Other courses (snapshots of 2026-10-12): Desert, Forest and Lake Side have no sea; K finds cliff feet with NOTHING under them (Desert 29,
  Forest 147, Lake Side 1) and T finds no tops. Patch 3's kinds are coastal: on those courses the void under the scenery is the question,
  and it needs a ground to stand on first (an island infill, patch 4 in the owner's numbering).

### 12.4 Not made, and what a rule would need
- **The castle island**: the rim is a ring of cut-out trees and boards, not edges; a rule would take the plan of a ring of trees standing
  over the sea, lay grass over it at the trees' feet, and a cliff from its outline down to the sea (rule K on the new outline).
- **Ground under floating trees by the coast road**: patch 2's generator already lays a shoulder under trees within reach of the road (25,
  section 9.1, R10); the owner's cliff edge that widens where trees stand and narrows where none do would follow the trees' feet as its
  outline with a margin (his: rough but graceful), then K for its face to the sea.
- **The town's second row and the buildings as boxes**: copies of completed buildings placed behind the front row; rule B makes flanks; a
  back wall and a copied row need a decision per town (he did it by hand, "copy-pasted").
- **Re-cutting and welding**: a shape-keeping re-triangulation into mid-sized triangles and a merge of corners within a few millimetres
  (cut-outs excepted) are general and safe; to be made as a rule that writes RECUT faces only (remove + add of the same surface).
- **Smeared pictures**: a face whose mapping is stretched far beyond its neighbours' (texels per metre) gets its neighbours' mapping
  continued; not attempted.
- **Trees moved**: after new ground exists, a cut-out tree whose foot is above or inside it moves to stand on it (board moves).
