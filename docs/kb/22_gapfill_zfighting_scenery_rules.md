# 22 - Imported 1995 scenery in SR3: z-fighting rules, the overlap resolver, the gap fill and why each rule exists

Scope: the rules the importer applies to SEGA Rally Championship scenery so that it survives SEGA Rally 3's Z-buffer and
its higher, freer cameras. All of it was worked out on the Mountain course (2026-10-07 / 08). Sources: the docstrings and
comments of `overlay_bake.py`, `layers.py`, `build_classic.py`, `fill1995.py`, `gapfill_gen.py`, `gapfill_weld.py`,
`trees1995.py`, `roofs1995.py`, `plateau1995.py`, `import_classic.py`; `SR3CamLab\docs\Mountain-gap-fill-plan.md`; the
owner's notes. Why the 1995 data looks the way it does: [18_src_1995_rom_data.md](18_src_1995_rom_data.md), section 10.
Rounding of the ground and lighting have their own files (17, 16).

Tags: VERIFIED (how), "in game" = the owner drove the build and reported, LIKELY, UNKNOWN. Build names such as Z1 or U1
are explained in [GLOSSARY.md](GLOSSARY.md). A "face" is one entry of the importer's list
`(material, section, [corner xyz in SR3 coordinates], [uv per corner])`.

## 1. Z-fighting: the requirement and what failed

The owner's requirement is zero z-fighting ("I hate z-fighting in games with enormous passion"). The 1995 data lays
polygons in one plane because Model 2 paints by priority (18, section 10); with a Z-buffer such pairs flicker.

| Attempt | What it did | Result |
|---|---|---|
| Fixed offsets | upper layers moved `LAYER_STEP` = 2 cm per layer off the surface (`stack_layers`), cut-out overlays `OVERLAY_LIFT` = 4 cm off their base on both sides (`dedupe_overlays`), draped road decals 3 cm above the SR3 road | flicker in the distance, in game |
| Offsets that grow with distance from the road (`far_scale`) | the gap is multiplied by (d / 50)^2 for a face d metres from the NEAREST road point (2 cm at 50 m, 0.72 m at 300 m; capped at 60 x), on the reasoning that the depth buffer resolves about d^2 / (near x 2^24) | DISPROVED in game: a rock 22 to 124 m from one part of the road is watched from 290 to 470 m away across the course; by the script's own rule it needed 0.7 m to 1.8 m, ten times what it got (MEASURED in the gap-fill plan) |
| Opaque road decals 3 cm above the road | - | z-fought in the distance, in game. SEGA's own road paint (Alpine4's centre dashes) is decal quads 1-2 cm over the road with the alpha-BLEND switch and does not z-fight |
| **Resolve every stack in its plane (`overlay_bake.py`)** | section 2 | "z-fighting fixed" (owner, 2026-10-07, builds S1 / S2) |

Related run-time fact: SR3 has a polygon-offset render state but the material field that drives it was not found (20,
section 13), so a depth bias per material is not available.

## 2. The overlap resolver (`overlay_bake.resolve`) and the gate

One pass over course + backdrop faces together (the backdrop used to be handled alone, which left the 29 duplicated rock
faces of object 1257 fighting with the course's own).

| Case | What is done |
|---|---|
| Same corners, opaque on opaque | one of them goes |
| Same corners, a cut-out on anything (ivy on rock) | ONE face with a composed texture: the lower tile's texels with the upper tile's opaque texels painted over |
| Overlap in one plane, upper face opaque | the lower face is cut back to what the upper one does not cover (nothing hidden is drawn) |
| Overlap in one plane, upper face a cut-out | the shared region becomes one face with a composed texture; what is left of each face stays |
| Parallel, a few centimetres to decimetres apart (a sign in front of a wall) | the face behind loses what the opaque face in front covers; a cut-out in front is moved off until the gap is safe (the only offsets left: "a handful") |
| Backdrop face on the corners of a course face | dropped; the course face wins |
| Front / back pair (same corners, opposite winding, same tile) | kept single-sided, each 5 mm off the shared plane on its own side, out of the overlap handling |
| Tree blade front / back (cut-outs with different halves of the picture) | both kept, each single-sided (alpha test, not two-sided), no offset; front and back are treated as separate boards |

- Which of two faces in one plane is the upper one: cut-out over opaque, smaller over larger, later over earlier
  (`layers.py`; a GUESS chosen so the result looks like the game, because the 1995 sort bits were not decoded). Of two
  parallel faces apart, the front one is the one on the side of the nearest road point (lying faces: the higher).
- When two faces count as a pair (`find_pairs`): both are drawn towards one viewer, their normals are within 2 degrees,
  they overlap in their plane by more than a sliver (`EPS_AREA` 2e-3 m2), and the gap between them is below
  `K_DEPTH` x d^2 with `K_DEPTH` = 1.0e-6 (24-bit depth, near plane about 0.1 m gives 0.6e-6; times 1.7), d = the largest
  distance they are looked at from: the FARTHEST road point, at most `MAX_VIEW` = 600 m, and no further than where the
  overlap is still `PIXELS` = 6 wide on screen (`FOCAL` = 935: 1080 lines, 60 degrees). Faces whose corners stay within
  5 cm of each other's plane are treated as one plane. A pair is listed when the gap is below max(needed gap, 1.5 cm).
- Composed tiles: when the two uv mappings differ by a symmetry of the tile (identity, mirror, quarter turn, any shift)
  and the tiles have one size, one tile-sized repeating picture serves every face of that combination (all ivy on rock: a
  few tiles); otherwise the picture covers just the shared region. Names `bake_<8 hex of the recipe>[_t]`. Deterministic:
  no random numbers, sorted iteration. The picture is sized from the FINER of the two tiles (17, section 3).
- **The gate** (`overlay_bake.gate`, course setting `gate`: "report" (default) | "fail" | false): after every stage that
  adds faces, coplanar or near-coplanar overlapping pairs are counted (exact = gap below 1.5 cm, near = gap below the
  needed one). Faces that would fail it are left out instead: a verge cell, a weld, a lid, a trunk extension, a new roof
  wall or a moved tree that would lie in the plane of another face is dropped or put back ("zero z-fighting comes first").
  On the build the owner approved the gate reported 0 exact + 0 near.
- Result on Mountain: 408 same-corner overlay pairs composed (393 + 15 backdrop), plus shared regions. VERIFIED in the
  built file; "z-fighting fixed" in game.
- Static check of a built track: `check_classic.py` section 2b counts drawn quads that lie in the same plane (3 degrees,
  closer than 8 mm) and overlap, and measures the decal height above the SR3 road.
- Known weak point (17, section 6): corner keys are `round(x, 2)`; Python and numpy round a value such as 2.675 differently,
  so the same point can get two keys.

## 3. The 1995 road on the SR3 road
- The SR3 road (TrackDeform) carries the physics; the 1995 road polygons that fall on it are cut into pieces of at most
  1 m and DRAPED on the SR3 road surface as decals (`classic_road`, `drape`), because SR3's road is its own mesh with its
  own heights. Lying faces that reach into the road are cut at its edge (`split_at_road`); a piece that touches the road
  becomes a decal so no sliver of the SR3 texture shows at the edge. Upright faces are never touched.
- Car shadows: SR3 draws car shadows, skid marks and ruts on ITS road, and an opaque draped road hides them (in game: "no
  shadow with the SR3 road hidden"). What was tried: painting the main 1995 asphalt tile into the SR3 tarmac layers
  (mode `layers`), a slightly see-through draped road, fully transparent SR3 layers. The owner rejected the opacity tricks
  and the layer painting. What worked: the draped decals use the alpha-blend material with the dynamic-shadow-receive
  switch set (the switch combination of Desert4 material 3546ce1e; 07_glue_and_other_files.md). "shadows fixed" in game
  (owner, 2026-10-07).
- Shiny road: the cloned decal material had the SPEC switch on, no specular map and specular colour 0.5; "the roads are
  too reflective ... even the dirt is reflective there" (owner, 2026-10-08). SEGA's own materials with SPEC and no SPECM
  carry specular colour 0; so do the decals now (course setting `road_spec`).
- Dust on asphalt: Desert4's own tarmac layer pair is Terrain_Safari_Tarmac, which throws dust clouds ("lifts a lot of
  dirt into the air on asphalt", owner, 2026-10-08). The texture id of the layer decides the physics surface AND what the
  wheels throw up, so the course setting `road_layers` takes Alpine4's Terrain_Tarmac pair (5186a744 + 7e6973ab).
- Soft road a few metres ahead: the authored road textures had max anisotropy 1 (SEGA's road layers: 4); see the sampler
  words in 01_container.md.
- Bands across the road: road pieces whose tile repeats more than twice had been clamped (smeared). Fixed by uv handling
  (23_texture_pipeline.md).

## 4. Polygons that are seen from the wrong side
- Opaque 1995 polygons without a back twin are drawn two-sided in SR3 (`two_sided`): a culled wall is a hole in the
  scenery ("see-through holes in geometry" in the first in-game runs).
- Classic faces under the SR3 road: deleting them left gaps, lowering them whole left a 20 cm slit at the rock foot. Now
  they are cut to 2 m pieces; corners covered by the SR3 road go 20 cm down, corners beyond its edge or rising above it
  stay (14_importer.md).

## 5. The gap fill

### 5.1 The owner's rule
"The gap fill should respect the game's original design. Adding a wall triggers a 'wait, I don't remember this wall back
in the 90's' response ... while adding a more natural slope triggers the exact opposite response ... so every gap fill
should be sober, proper and minimalistic ... enough to fill the gap and if the gap is huge, so should be the filling ...
use a group of rocks when it's more sensible than a huge rock with an eye-sore repeating texture" (2026-10-07). Scope: the
whole lap. Later: "visual flow is more important than being byte perfect accurate to the original game", and "don't add
unnecessary ... geometry".

### 5.2 Where the fill lives
`gapfill_gen.py` writes the fill ONCE into `classic/courses/<game>/<course>/src_course<N>_handfill.obj` (classic OBJ
coordinates, one `o` block per object, `usemtl` = a 1995 tile of the course). `fill1995.handfill` merges that file on
every build; the build never regenerates it, so it can be edited by hand, and a ROM re-export never touches it. Hand-made
models go into `src_course<N>_handmodel.obj` (`fill1995.handmodel`); a material `@near:x,y,z` means "the material of the
course polygon whose centre is nearest that point", so a model can continue a rock face in that face's own (possibly
composed) tile without naming it. Nothing is random: every choice comes from a hash of the slice number or of the corner.

### 5.3 Pieces of the fill and the reason for each

| Piece | Rule | Why (and who said so) |
|---|---|---|
| Verge (`ground_skirts`) | the 1995 game has collision ground beside the road that it never draws; every such 1 m cell outside the SR3 road strip that no lying visual face covers (within 3 m of its height) is drawn, 5 cm lower | holes beside the road seen from SR3's higher camera |
| Verge tile along the forest stretch (`retile_verge`) | verge cells there take the tile of the nearest lying 1995 rock ground instead of the course's grass tile | "beside the brown cracked ground of the forest road a green patch stood out" (owner's mock-up, 2026-10-07) |
| Hillside (`gapfill_gen.terrain`) | ONE height grid (`CELL` 4 m) under the whole course: from every piece of ground of the ribbon the land stays level `SHOULDER` = 20 m, then falls at `HILL` = 24 degrees; the hillside is the highest of these cones, held `D0` = 0.7 m under every lying polygon it passes below | "no floating skirts, no open backs from the free camera". Level 20 m because trees stand about that far out. The slope was 38 degrees first: "the land beside the road should read as uneven, mostly level ground, not as a ridge the road runs along". 0.7 m because parallel faces closer than 0.36 m could flicker |
| Hillside finish | rougher with distance from the ribbon (two waves and a 12 m value noise, only ever downwards); three passes of a 3 x 3 mean; a corner more than 1.5 m above the mean of its eight neighbours comes down; no rise steeper than 65 degrees between grid corners; away from the ribbon 2 x 2 blocks that touch no ground and lie more than 20 m out become one 8 m cell | flat cones, pointed peaks ("pyramids" behind short rock-wall tops) and wasted polygons |
| Island rule | water only where it hangs together with the open sea round the course; what is under water but shut in by land becomes a valley floor just above sea level | the owner wanted the land to be an island like Tropical: "sea only at the true coast, no sea visible inland" |
| Shore | within `SHORE_NEAR` = 10 m of open sea the land is level only `SHORE_SHOULDER` = 6 m out from the roadside ground (`SHORE_TREES` = 4 m beyond a tree) and then falls at 62 degrees, as one continuous rock picture at 32 m a repeat | "the terrain script added too much land ... the shore should be more cliffy, instead of a gentle slope ... a lot of verticality ... we're supposed to see a lot of sea" (owner, 2026-10-08). Half a tile restarted in every cell "stood as terraces" |
| Tiles | ground tile of the place where it is gentle, ONE rock tile (the nearest) where it is steep; chosen by the slope AROUND a cell (3 x 3 cells); only evenly lit tiles and only their evenly lit rows; labels 'dirt' / 'sand' / 'gravel' are never used | mixing "two or three rock tiles of the place" put dark rock teeth in front of an orange formation; a pale sandy tile stood out as a bright band; the dark forest rock tile has a black band that stood as black patches; those three labels turned out to hold roof planks and pale wall tiles |
| Forest floor | the DARK tile (the local ground / rock tile at brightness `FOREST_DARK` = 0.32) ONLY in the void between the roadside ground and the foot of the 16 m wide forest-wall boards (class tree_wall, sections 1291 .. 1317, 14 .. 35 m from the road), within `FOREST_REACH` = 26 m | owner, three times: "ONLY for the forest sections where it perfectly MATCHES the void between the ground and the vegetation" |
| Village inside the forest | where houses stand nearer than the forest wall, with forest wall before AND after them along the road, the ground between road and house is the 1995 ground's own brown cracked tile, level up to the house wall | owner's screenshot and mock-up (2026-10-07): the verge had ended in a black hole in front of the house |
| Rock walls beside the road | a rock wall that stands ON the roadside ground (a cutting) is backed by the hill up to its top; a rock that rises out of a drop beside the road is not | backed, the hill "came round its front as a dark pyramid between the road wall and the rock" (section 1279) |
| No rock floats | every free lower edge of a rock polygon with nothing under it goes down as a cliff to the hillside or the sea - but not within 25 m of the road | near the road such curtains "stood as a flat upright slab of rock at the roadside" (owner: "what are those vertical 2d rectangular slabs") |
| Welds (`gapfill_weld.weld`) | along the foot of every opaque upright polygon within 40 m of the road, every 2 m at most: where ground lies within 1.5 m sideways and 1 m of height, a filler strip from the ground's edge to the foot line; it ends 2 cm BEHIND the foot line, runs 20 cm under the ground's edge, always falls at least 8 % from the wall end and is tilted more than 3 degrees against the ground it tucks under. Where no ground is near, the wall is carried down as a skirt, at most `CARRY_MAX` = 1.2 m | "I asked for the seams to be welded shut". The tilt keeps the pair out of the z-fight gate; running under the edge means ruts in the deformable road cannot open it |
| Final seal (`gapfill_weld.seal`) | every wall foot the seam scan still finds open gets its wall carried straight down to the surface under it, the texture continuing | "WHY? still open" |
| Trees set on the ground (`trees1995.lower_boards`) | a tree is LOWERED as a whole by ONE amount (the largest gap under one of its lowest boards); nothing is raised, no trunk is stretched, the ground is not heaped up | "either we have trees with missing trunks or floating trees, lower those trees". Heaping ground under each tree gave "rows of pointed mounds" ("eye-sore") |
| What one tree is | every blade strip that touches the same vertical axis (a plan corner where boards of two or more plane directions meet), plus crossing boards and boards on the same footprint; classes crown, trunk, bare, tree, lamp only | grouping by centre distance, by touching corners in 3D and by "hangs on" each broke trees in game; with other classes "the tower's cut-out top went down with the trees" |
| Trunk extension (`extend_trunks`) | a hanging board whose lowest tile row shows a stem gets one quad down to 0.3 m under the first ground below; only for stem classes, never further than a limit; a board whose lowest tile row is leaf green is skipped | the first version ran stems 15 m into the sea ("stilts"); continuing CROWN boards gave green posts ("wtf are those green posts, almost every tree has one") |
| Stems with no ground at all | the whole tree or post is removed (every cut-out board within 1.5 m of it) | a stem over water or in mid-air |
| Castle island lid (`island_cap`) | a lid on every run (at least 80 m, turning at least 150 degrees in plan) of upright backdrop cut-out boards whose top edges join into a loop or arc; it lies where the wall's tile rows become 90 % opaque, 2 m inside the wall, in the wall's own foliage tile | the island is a cliff ring with a tree wall and no cap; SR3's cameras look down into it |
| Roof gables (`roofs1995.gables`) | a sloping edge of a roof polygon that no other polygon shares is an open end: two meeting at the ridge get one gable triangle, a single one a triangle down to eave height | from a free or replay camera the roof "reads as a slab hanging in the air" ("add the missing wall/roof part to that building (like 1 triangle)") |
| Walls under open eaves (`roofs1995.eave_walls`) | a free, level low edge of a roof polygon with no upright face below it (within 2.5 m) gets a wall down to the surface under it, in the tile of the nearest house wall | the side of a house the 1995 game never showed. 2.5 m because an eave may overhang its facade and a new wall in front would hide its windows. 96 walls and gables were added on Mountain |
| Houses open from above | a house wall whose top has no roof within 2 m on either side gets a roof falling away from the road into the hillside | "the 1995 street fronts are cards" |
| Sea | a flat sheet of the sea tile (40 m cells, level -0.5, about 15 m below the start straight) under the whole course; pieces of 10 m are left out where land covers them and all eight neighbours (`sea_clip`) | the 1995 bowl is outside SR3's +-750 m scenery square; "no water under land", with a ring of water left under every shore |
| Smeared cliff end caps (`fill1995.unsmear`) | natural-ground polygons whose tile is stretched more than 10 times further one way than the other get the density of their good direction both ways | "a face of horizontal streaks" (owner, 2026-10-08); only ratio > 10, so textures the owner liked stay |
| Over-repeated tiles (`normalise_uv`) | a face more than 8 times denser than the median of its tile is scaled back | the "wall of green streaks in the forest" and "bands across the road" of object 1291 |
| The far plateau (`plateau1995.py`, hand model) | the rock screen of sections 1280 .. 1282 becomes the front of a mesa: a back wall swept through hand-placed control points, a low dome on top, the screen's own tile at its own scale (0.023 repeats per metre along, 0.0195 per metre up) | "it's a plateau that can be seen from anywhere in track. The least you could do is complete its shape in a natural way (make it round) and apply the same texturing" |

### 5.4 Tried in the fill and switched off (kept in the code as off)
| What | Why it went |
|---|---|
| Shelf + skirt strips beside the road (`PROFILES`) | "long flat triangles with straight creases and knife edges"; the hillside grid alone carries the ground now |
| Separate slopes per slice (`ground_skirts(slopes=True)`) | the pieces came out as separate ramps, some over the sea |
| Boulders in groups (`BOULDERS`) | "big boulders 'scream this was not here before'; uneven ground suffices" |
| Automatic bodies behind rock screens (`BODIES`) | their flat back walls "looked like quarry faces" (owner: "No, come on"); screens are completed by hand models instead |
| Plateau variants | flat rejected; rough first preferred ("looks more natural"), then "too rough and created some very weird geometry" -> the rough version's jitter scaled to 0.45 with the rim heights averaged; a slab on its rim was the cap's inner band landing outside the outline at sharp corners |
| ROM object 172 as checkpoint banner | a white text overlay 65 m off the road (18, section 8). Stand-in gantries (`checkpoints1995.py`: fixed 12 m wide, posts just outside the SR3 road edges, 1 m into the ground) were used until the real gates were found |
| A sea wall instead of a bank | an option of the plan; the natural bank was built |
| Fog-on variants | dropped: "it doesn't add anything to the game, at least not in SRC stages"; fog off is the importer default (the fogged far edge of the sea sheet had stood as blue bars on the horizon) |

### 5.5 Checks
- `gapfill_audit.py <dump>`: stems more than 5 cm above the surface under them, fill tiles that are "not natural", fill
  faces thinner than 1 : 8, and the seam scan. `gapfill_weld.scan` samples every wall foot every 0.5 m and prints a
  histogram of the distance to the nearest lying surface.
- `gapfill_seamask.py`: from an eye 1.5 m above the centre line every 30 m, 48 directions at three downward pitches for
  up to 240 m; counts rays that reach the sea inside the lap and outside it (an upper bound: upright faces are ignored).
- `gapfill_preview.py`: before / after pictures from the places of the owner's annotated screenshots.
- A face-list dump for these tools is written when the environment variable `GAPFILL_DUMP=<file.pkl>` is set.
- In game: build U1 "everything makes sense now"; builds Z1 / Z2 "I must say I'm very happy with Z1/2"; Z4 "other than the
  finish gate being on the middle of the road, everything is great". Z is the reference state of Mountain's fill.
- Not checked: the rule that skips rock-top anchors when a rock rises out of a drop removed 250 anchors lap-wide and was
  only looked at in one place.

## 6. Sky dome and sea line for an imported course (`sky1995.py`)
Format of the dome: 07_glue_and_other_files.md.
- First method (DISPROVED in game, three runs): every dome texel was ray-cast from the course centre against the 1995 far
  backdrop; the picture came out smeared near the horizon.
- Working method ("sky fixed", owner, 2026-10-07): the 1995 sky picture is laid on SR3's dome directly, its bottom row on
  the horizon and its top row at `sky_top` = 28.28 degrees (tan-spaced), `sky_repeat` times around. The 1995 data says 6
  repeats; in game 3 read "squished", 12 "too stretched", 8 was kept.
- Above the picture the dome is ONE colour: the picture's top row is not perfectly even, and repeated upwards it drew
  faint vertical lines, one per copy.
- The dome follows the camera and sits about 110 m above it for the Desert4 slot (in game the sea / sky line stood 2.3
  degrees over the road's vanishing point; Desert4's master_gfx root +0x24 is 128.0, LIKELY the dome's height). Below its
  equator ring the dome has about 1 % of the texture rows, so painting cannot move the horizon: the MESH is lowered
  (`sky_drop`, 300 m for Mountain). SEGA's widest ring is at y = 435.87.
- Below the horizon one flat colour = the colour the sea sheet has on screen (course setting `sea.screen_colour`, measured
  from a screenshot); a per-texel sea colour had come out as "a pale wall with dark vertical bars". The sea sheet's own
  texture has a mip LOD bias of 2.0 and no anisotropy so the 64-pixel tile does not sparkle towards the horizon.
- The slot's far horizon card (master_gfx root +0x14; Desert4: Kilimanjaro) is removed.
