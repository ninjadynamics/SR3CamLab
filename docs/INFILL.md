# INFILL — adding missing ground to a classic course

How to fill the holes a 1995 course leaves open (sea showing where there should be land, trees standing in the air) so that a seasoned player
cannot tell anything was added. Distilled from the patch-3 work on SEGA Rally Championship "Mountain" (2026-10-12): the cliffside, the corner
south of the tunnel, the lawn behind the town (A) and the plateau beside the road (B), including the owner's own manual edits and corrections.

Read this before touching an infill. The rules are the owner's; the rest is what worked and what went wrong.

## 1. Why we infill

Two reasons only: SEGA left geometry out (it was never seen from the 1995 cameras), and SR3's cameras see more. We are **not** changing how the
track looks. The test for every piece: *from the road it must look as if it was always there*.

## 2. The rules (owner's, "85%+" — follow unless told otherwise)

1. **Leave 1995 geometry alone.** Don't move it, don't re-texture it, don't poke through it. Exceptions come from the owner, usually in a later
   clean-up pass. Adding a corner on a 1995 edge so grass can be welded to it is allowed *when the owner asks for a stitch* (shape and picture
   stay the same).
2. **Lowest level that makes sense.** Find the level the neighbours imply and stay on it: tree feet, the base of the kerb, the crest or base of
   the rock beside the gap. Never build up.
3. **Grow from the road.** If the ground can reach the road-edge corners or the inside/base of the kerb, start from those corners. If a 1995
   bank stands in between, start from the bank's own crest corners.
4. **Textures as asked; otherwise an educated guess** from what 1995 uses right next to the gap.

Standing constraints that apply to all generated geometry:

- Everything triangles. No zero-area faces, no loose edges, no holes, nothing coplanar with another face (zero z-fighting).
- Corners shared with what is there wherever possible ("everything connected").
- Sober natural terrain only: no boulders, no invented structures, nothing that sticks out from the road.
- No tree in the air (roots underground are fine). Never move part of a tree: a tree moves as a whole or not at all.
- Nothing obviously tiled.
- Don't overcomplicate. Simple, solid, mid-poly.
- When the owner places or shapes something by hand, **keep it**. Trim and weld what was asked; never re-position, lift or rebuild it on your
  own initiative. If it cannot work as placed, say so with pictures and wait.

## 3. Workflow

Work live in Blender through MCP so the owner watches it happen.

1. **Right file first.** Read `bpy.data.filepath` before anything. If the owner named a new version, that file must exist on disk before the
   first change. Never write over the owner's scene files.
2. **Survey before building.** Dump the area and plot it in plan: faces by tile, open edges with heights, tree feet. Scan heights from above
   (rays on a 0.5 m grid against everything solid except sea and cut-outs). The picture tells you the level, the anchors and the outline.
3. **Decide the level and the anchors** (rules 2 and 3) and say them in one line.
4. **Build** (section 4).
5. **Check by numbers:** loose edges, zero-area faces, tree feet against the ground, holes seen from above (sea ringed by land in a new scan).
6. **Look at it yourself** before reporting: from above, from the road in both directions at driver and chase height, from standing height on
   the new ground, and in wireframe. Render from a saved copy of the open scene, never from the scene itself.
7. **Report plainly:** what was built, what connects to what, what is still open and why. Leave the scene unsaved; the owner saves.
8. **After every fix, search for the same defect elsewhere** and report what turned up, separating what you caused from what was already there.

## 4. Recipes

### 4.1 Flat ground from existing corners (the corner, plateau B)

- Outline = existing corners in order (road edge / kerb base / rock base / bank crest), found by position with a small tolerance, plus new
  corners only where nothing exists.
- Inside: a loose jittered grid (about 3 m spacing in a small corner, 6 to 7 m on a large plateau), no point closer than 1.5 to 3 m to the
  outline.
- Height: the level, plus slow unevenness of ±10 to 20 cm that fades to nothing at the outline. Clamp so it never drops under the highest tree
  foot it carries.
- Triangulate with a constrained Delaunay over outline + inside points. Lying faces in this mesh look down (normal y < 0).
- Tree feet: find **whole trees** (boards joined through their corners), take the lowest corner of each as the foot, and make sure the ground is
  5 to 40 cm over it. Raise only free inside corners, a few centimetres at a time, capped.

### 4.2 Extrusion in the plane (lawn A)

When an existing flat surface simply stops short of the rock behind it: no inside points at all. Outline = the surface's own edge corners + the
corners on the rock, triangulated as a strip. Check that the result stays in the surface's plane (A: within 13 cm).

### 4.3 Meeting rock

In order of preference:

1. **Share the rock's corners** where it has them at the right height (rim base, bank crest).
2. **Stitch**: where the rock has no corner at that height, put the grass corner exactly on the rock's edge, split that edge there, cut the
   rock's faces into triangles again, weld. Interpolate the rock's mapping at the new corner so its picture does not move.
   *Check the edge really is the wall's surface.* A wall whose top and foot share a plan position is upright; if the corner in between is
   offset, the wall leans and the grass set under its top stands a metre short of it (this happened on lawn A).
3. **Cross a little**: run the ground 1.5 m into the rock at the same height and stop. Accepted for rough rock flanks (the corner's rock arm,
   the tunnel rock on plateau B) when asked for or when a stitch would mean cutting many faces.

### 4.4 Outlines: walk every corner

When an outline follows a crest or an edge, use **every** corner along it. Going straight from one corner to the next-but-one leaves an open
triangle (18.5 m² on the rim beside plateau B).

### 4.5 Textures

- **Grass:** take the mapping of the 1995 grass next door and carry it on by position. The Mountain lawn spreads its tile over about
  95 × 65 m; a new patch mapped at 5 to 9 m per repeat screams "tiled".
- If the neighbouring surface does not follow one mapping, map each new face from the face it shares an edge with (extend that face's own
  mapping across the edge). Measure the picture jump on shared edges afterwards.
- **New rock faces:** continue the neighbour's picture across the longest shared edge at the neighbour's grain (unfold the new face about that
  edge); map further new faces from the first so they read as one patch. Compare grain (tile repeats per metre) with the neighbours: a face ten
  times denser than its surroundings shows as a striped smear.
- **Paving, walls, anything else:** same method. Match tile, grain and direction to the faces it touches.
- Never re-map 1995 faces to make a join look better.

### 4.6 Cliff down to the sea (the cliffside)

Only where the outer side of the road really is a cliff and the owner asks for one.

- Ribs start on the kerb's base corners. A level strip beside the kerb sized by the trees it carries (wider where trees stand near the edge,
  narrow where there are none), a rounded shoulder, then the face.
- Roughness grows towards the water: graceful at the top, rough at the bottom. Mid-poly.
- Grass by the kerb gives way to rock in irregular shapes, never in a row of quads. Light rock next to the grass, darker (wet) rock towards
  the sea, as a gradient over several bands.
- Keep it slim: about 90% of the road's width. A cliff fatter than the road gets noticed.
- The inner side of the track is not a cliff: the track is the outline of an island that a later patch fills.

### 4.7 Closing a gap with a copied piece of rock (owner's method)

The owner duplicates a piece of 1995 rock, turns it and sets it in the gap. Our part:

- **Trim only the excess:** faces that hide nothing from the road or from the new ground because rock stands right behind them. Test with
  sightlines from driver height, chase height and standing height. Faces that hide the sea *or far scenery* stay.
- **Weld** rim corners onto rock corners within about 3 m, never dragging a corner so far that the piece changes shape. Where the piece's own
  parts meet, make coincident corners one.
- Keep its texture; re-lay only a face whose picture was stretched by a moved corner.
- If it leaks from some viewpoint, count leaking sightlines for a few candidate shifts on a **copy**, show the numbers, and let the owner
  choose. Moving it sideways is rarely the answer; nearer the gap usually is.
- A piece standing far behind the gap cannot be both trimmed small and closed: sightlines fan out. Say so early.

### 4.8 Moving a tree

Move all of its boards together. Test candidate spots on the ground for boards cutting through rock and take the nearest clean one; a narrow
corner may have none at its very tip. Foot 10 cm into the ground. Afterwards compare the tree face by face with the data as generated.

## 5. Checks to run every time

| Check | How | Pass |
|---|---|---|
| Right file | `bpy.data.filepath` | the version the owner named |
| Loose edges | edges with no face | 0 (they show as orange lines) |
| Zero-area faces | area < 1e-5 | 0 |
| Trees | whole-tree foot vs ground under it | ground 5 to 40 cm over every foot |
| Half boards | tree triangles with no second half in their plane | no new ones compared with the previous version |
| Holes | scan from above, sea cells ringed by land | none new; list what remains |
| Texture grain | repeats per metre vs neighbours | same order; no visible seam |
| 1995 untouched | faces not in the new set unchanged | yes, except stitches the owner asked for |
| From the road | renders both directions, driver and chase height | reads as always there |

## 6. Mistakes already made — don't repeat

- **Building up.** A taller tunnel top, raised verges and steep rock banks all changed the road view and were undone. Lowest level.
- **Changing the owner's work.** Lifting and re-placing a hand-set piece without being asked. Do what was asked; propose the rest.
- **Reporting before looking.** A slab over grass, a hole and a smeared texture were reported as fine. Render, look, then report.
- **Guessing from a short list.** Assuming a wall was upright from two corners; skipping a crest corner. Check the actual edges.
- **Selecting by a loose rule.** A cleanup that matched "grass with new corners in this box" also hit the cliff strip; a restore matched the
  tree next door. Match by position against a saved list, and verify the count before deleting or adding.
- **Wrong reference.** An earlier save can already contain the damage. For "as it was", use the scene as generated, not a later save.
- **Tearing trees.** Moving or deleting part of a tree. Whole trees only.
- **Wrong Blender instance / wrong file.** Check the path first.
- **Leftovers.** Removing faces leaves loose edges; removing a fill can leave its plugs. Clean and re-scan after every removal.

## 7. Technical notes for this project

- Scene object `1995 course (RAW2)`; mesh coordinates are course coordinates with **y up** (the object is turned 90° about X).
  `vert.co` and ray casts are in that local space.
- New corners go in the vertex group `PATCH`; that is how new faces are told from 1995 ones.
- Materials map to tiles through the scratch table `p3_tiles.json`. Useful Mountain tiles: grass `…x0000_y0000_256x256_c1A6`, rock
  `…x0000_y0000_256x256_c101` and `…x0768_y0064_256x256_c101`, town paving `…x0704_y0512_64x64_c0DE`, kerb `…c06A`, road `c0EE/c103/c07C`,
  sea `c1DF`; cut-outs (trees) end in `_t`.
- The 1995 mesh is only partly welded: neighbouring faces often have corners of their own at the same place. Find corners by position.
- Never Merge by Distance over the whole mesh: tree boards are back-to-back pairs.
- Darkened copies of a tile (wet rock) exist only inside the scene; the patch format cannot carry them yet.
- Helper scripts from this session live in the session scratchpad and are **not** in the repo. The methods above are what to rebuild from.
- Shipping rule: coordinates and recipes may ship; a whole track, modified or not, never. Scenes, builds and textures stay out of git.
