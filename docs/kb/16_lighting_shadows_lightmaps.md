# 16 - Lighting, shadows, light maps, normal maps (SEGA Rally 3) and the 1995 sun

Findings of 2026-10-08. Confidence tags as elsewhere: VERIFIED (and how), LIKELY, UNKNOWN.
"In game" means the user drove the build on the cabinet and reported or screenshotted the result.

## 1. How SR3 lights a track

### 1.1 The lighting sets (VERIFIED by patching and in-game runs)
`master_gfx` root +0x18 points at two sets of 49 floats.

| Floats | Meaning |
|---|---|
| [1:4] | direction the light TRAVELS (not "towards the sun") |
| [4:7] | ambient colour |
| [7:10] | sun colour |
| [10:14] | fog range |
| [14:17] | fog / sky colour |
| [23:26] | scale applied to the sun colour |
| [44:47] | tint |

- Both sets light cars AND scenery. They are NOT a "car set" and a "world set" (an experiment that assumed so darkened the sky and gave a green cast, build Z6).
- The game draws a visible sun flare at the light direction.
- Shading of a lit material: `ambient + sun x max(N.L, 0)` (LIKELY the exact form; VERIFIED in effect: a normal built to give a wanted brightness under that formula gives it in game, see 3.1).
- Tropical4's set, used for Mountain: ambient 0.64, sun 1.08 (1.14 with the scale), means of the three channels.

### 1.2 Uber material switches (VERIFIED: byte patches behave as named)
Material chunk kind 2, 1848 bytes (a 1728-byte variant exists: every offset below minus 120). The VALUE of a switch or constant is the u32 / floats right before its inline name string.

| Offset | Name | Offset | Name |
|---|---|---|---|
| +3AC | VCOL (vertex colours) | +51C | SCAST (casts shadow) |
| +3BC | LITE | +52C | SSRECV (receives static shadow) |
| +3CC | PIXL (per-pixel lighting) | +540 | SDRECV (receives dynamic shadow) |
| +3DC | SPEC | +554 | DIFFM (diffuse map) |
| +4D4 | ATEST (alpha test) | +574 | NORM (normal map) |
| +4E4 | ABLEND | +594 | LMAP (light map) |
| +4F8 | ABLENDAdd | +5B4 | SPECM |
| +50C | DSIDE (two-sided) | +5D8 | TWOS |
| +620 | REFL | +65C SCROLL, +670 DISCR | |

Constants: gf3AmbientCol +464, gf3DirCol +480, gf3SpecCol +498 (three floats each).
Texture references: diffuse +1BC, normal +1DC, light map +1FC, specular +21C, reflection +27C.
SEGA's own UNLIT material: Desert4 master `0x47948b52` (1728 bytes: ATEST DSIDE SCAST DIFFM). Used for the gates.

### 1.3 Dynamic shadows (LIKELY variance shadow maps)
- `gfShadowParamsPs` at 0x9F1068: y = variance floor (1/512) at 0x9F106C, z = power (10) at 0x9F1070. x and w not identified.
- A 5 x 5 Gaussian blur is called once, at 0x5A5467 (the only call of 0x50D960, bytes `E8 F4 84 F6 FF`); LIKELY the shadow-map blur.
- The two numbers shape the EDGE of the shadow only, not its darkness. A shadow removes the sun's share and leaves ambient: with Tropical's set, ground in shadow keeps about 0.39 of its lit brightness.
- Measured in game (screenshot, Mountain): the car's shadow on tarmac is at 34% of the lit tarmac's screen brightness.
- Config `ShadowQuality` maximum is 2.
- LIKELY (user observation, not isolated): with floor 0.0002, power 30 and the blur off, spectators stop casting shadows while the car still does.
- These values can only be read from the running process: they lie in the part of `.data` that is zero-filled at load (`.data` is 4.27 MB in memory, 147 KB on disk). CORRECTION 2026-10-08: this line first said the exe "is packed"; it is NOT packed (VERIFIED from the PE section table, see [24_shaders.md](24_shaders.md)).

### 1.4 What SEGA bakes (VERIFIED by counting in the files)
| | Tropical4 | Alpine4 |
|---|---|---|
| Materials (1848-byte) with VCOL = 1 | 377 of 874 | 185 of 793 |
| ... of which LITE = 0 (fully baked) | 119 | 73 |
| Materials with LMAP = 1 | 3 | 64 |
| Distinct light map textures | 27 | 53 |
| Light map sizes | 256 x 256 (18), 512 x 512 (9) | 256 (27), 512 (25), 128 (1) |
| Light map texels in total | 3.5 million | 8.3 million |

- So SEGA bakes light mostly into per-vertex COLOURS, and uses light map textures sparingly.
- Mesh vertex strides seen: 16, 20, 24, 32, 36, 40, 44, 48, 52, 56, 60. Only the 48-byte format is written by the importer (pos xyzw, normal, tangent, uv0 u16 x 2, uv1 u16 x 2). The formats that carry a colour are NOT decoded (UNKNOWN).
- SEGA Rally 3 roads also carry a baked sun / shadow map (the TrackDeform overlay page); the importer writes it as "all sun". Layout not decoded beyond that (UNKNOWN).

## 2. What a light map does (VERIFIED in game, build LM-TEST)
Every imported material is a clone of a Stadium wall material and has LMAP on. Test: the light map picture replaced by four squares (white, 128 grey, black, red) and each polygon pointed at one square by its place on a 16 m grid.

- Black squares came out pure black: the light map MULTIPLIES the finished colour, ambient included.
- Red squares came out red with the texture readable: it carries full colour.
- The boundaries were crisp per polygon: uv1 is honoured per vertex.
- White = 1.0. A light map cannot brighten.
- Grey 128 reads as about half; the exact curve was not measured (LIKELY linear in the stored value).
- uv1 is u16 with 32768 = 1.0, the same scale as uv0.
- A see-through (ABLEND) road material accepts a light map too once +594 is set to 1 (VERIFIED in game: the road rendered normally, build LIGHTMAP-RT 2).
- Five to six 2048 x 2048 DXT1 pages load and draw (VERIFIED in game). SEGA's own are 512 at most.

## 3. Lighting the imported course

### 3.1 Brightness through the normal (VERIFIED in game: "lighting model issues mostly solved")
The 1995 textures carry their own shading, and the real N.L of a 70 degree sun leaves every wall dim (cos 70 = a third of the ground). So the importer decides how bright a polygon should be and hands the game a normal that gives exactly that under the slot's light:

    d          = polygon direction . design sun      (the real sun's compass direction, 45 degrees up)
    brightness = floor + (1 - floor) x clamp((d + 0.2) / 0.907)        floor = 1 - 0.6 K     (K = course setting light_contrast)
    N.L wanted = (brightness x ground - ambient) / sun                  ground = ambient + sun x sun_y
    normal     = cosT x L + sinT x e                                    e = the true normal's part across L

- K = 0.75 (floor 0.55) matched the Model 2 control screenshot on the start grid within a few levels.
- Cut-outs, signs and gates are flat-lit (brightness 1).
- Range available: 0 to 1.04 x flat ground.

### 3.2 Which side of a polygon is lit
- `lightside.py`: 32 rays from each side of every polygon; the side open to the sky is the seen side. Rules in order: escape share, lying faces look up, few rays, free path, enclosed polygons follow their neighbours, coplanar touching polygons vote as one wall. Polygons it is not sure of are drawn two-sided and lit as their brighter side (material key suffix `|4`).
- `roadsight.py` (later the same day, and it overrules): 3,512 viewpoints on the road (every 4 m, 3.5 m left and right, 1.1 m and 3.2 m up), rays to the polygons within 170 m. The side the rays arrive on is the seen side.
  Result on rounded Mountain (112,522 polygons judged): 65,048 confirmed, 2,707 turned round (2,043 of them ones lightside had been SURE of), 3,988 seen from both sides, 40,779 never seen from the road (left as lightside decided); 21,333 "unsure" polygons became sure.
- A four-cornered polygon is drawn as two triangles along corners 1 - 3 (`meshgen.quads_to_strip`); Blender's BVH splits the same way. 37% of Mountain's four-cornered polygons are twisted by more than 5 cm, so any ray test must use that split: with the 0 - 2 split, 8,521 of 49,192 polygons scored differently; with 1 - 3, 26.

### 3.3 Baked light per vertex (`bake1995.py`; builds BASE-SHADOWS, BASE-RT; superseded by 3.4)
Per vertex: V = share of the sun's disc seen (7 rays in a 1.6 degree cone), A = share of the sky seen (16 cosine-weighted rays), B = light coming back from what those rays hit (albedo of the hit x 1 if the sun reaches it, 0.3 if not). The brightness of 3.1 is then lowered towards a shade level where V is low ("shadows"), and additionally by `0.45 + 0.55 A` plus `0.6 B` ("rt").
- Needs two builds (collect the vertices, then read the table back) and polygons cut to 2 m near the road, or shadows have nowhere to land. 598,683 vertices; 1.13 million vertices in the mesh.
- User: could not tell "rt" from "shadows"; in the data rt is 14% darker on average, an even dimming.

### 3.4 Real light maps (`lightmap1995.py`; in game: "looks quite nice ... feels natural and pleasant")
- Every lit polygon gets a rectangle of nu x nv texels (3 per metre within 60 m of the road, thinning to 0.75), rounded up to whole 4 x 4 blocks so a DXT block holds one polygon only; texel (i, j) sits at the polygon's own grid point, corner to corner, so two polygons sharing an edge are lit alike along it and bilinear filtering never reads outside the rectangle.
- Shelf-packed on 2048 x 2048 pages. Mountain: 228,639 polygons (107,000 of them road pieces), 17.8 million texels, 6 pages.
- A texel holds what the rule's brightness is multiplied by; shade level 0.33 (0.42 read as "lacks a little contrast").
- A material shows ONE light map, so each page gets a copy of the material (ids 0xc1ac0000+) and the polygons of a page become a mesh of their own; page textures 0xc1ad0000+page.
- Texels MUST be placed on the two triangles the game draws, not on the bilinear patch: on a twisted polygon the patch lies under the surface and the texels shadow themselves (first build: "quite a few polys lit the wrong way, dark where they should be light").
- Bounce is in colour (mean colour of the tile that was hit), but only shows where something else took light away, because a light map cannot brighten.

### 3.5 Relief on facades (`bump1995.py`; in game: relief reads correctly, direction right)
- SEGA's normal maps (136 in Tropical4): plain tangent-space, x in red, y in green, z in blue, flat = (127, 127, 255); DXT1, or DXT5 with solid alpha. Vertex tangents are unit and perpendicular to the normal.
- Normal map made from the tile's own picture: darker paint = further back (right for windows and joints, wrong for dark paint).
- First test lit those walls by the game's sun on their TRUE normal: relief fine, but neighbouring panels of one wall differed in brightness and walls turned from the sun went dark.
- Second method keeps the rule's normal and turns the TANGENT so that a slope of the map changes N.L the way it would on the true wall (`build_classic.relief_tangent`; checked on 4,000 random cases: same direction, cosine 1.000000). Amplitude is fainter on the brightest walls (about a third), so the map's strength was doubled. Not yet judged in game.
- The handedness the engine gives the bitangent was not established from SEGA's meshes (their tangents did not line up with +u or +v in my test, UNKNOWN why); the test wall looked right with tangent along +u and green not flipped.

### 3.6 RT rules (owner's decisions of 2026-10-08, collected from the session on 2026-10-13; they were not written down at the time)
- **The look:** a bright early-summer noon. The approved reference is the graded ray-traced stills `work\previews\raytraced_v2\final2_1..7.jpg`: sunlit road about 160 172 180, sunlit rock about 179 140 97, cobbles about 167 165 146, sea about 2 102 199, sky deep saturated blue (about 0 57 222 at the top). "Ugly" was: knife-edge shadows, too little fill light, grey desaturated shade.
- **One system only:** baked light is the only lighting, on a flat base. Layering the bake on the direction shading of 3.1 darkens twice (owner, 2026-10-09; repeated by mistake on 2026-10-13).
- **The stored textures are dark.** The game (and any preview) must add brightness on top: on screen, rock and tarmac are about twice the stored display value. A ray tracer fed the stored tiles as albedo gets almost no bounce; bounce must be computed from the brightened colours.
- **Light against shadow:** in game, cast shadows at 33% of full light (42% read as "lacks a little contrast"). Average brightness and saturation of LIGHTMAP-RT were "on point".
- **The road:** it must receive shadows, and the light on it carries NO colour (bounce keeps its brightness, loses its tint), so white lines stay white beside brick. Scenery keeps coloured bounce.
- **Sprites take no baked light** (trees, lamps, the castle, every cut-out board): they only get one flat level that matches the scene's colour and brightness (the mean light on solid surfaces, no tint). They still cast shadows. The roadside banners are solid faces (tile c0DF), not sprites, and are baked like any wall (owner, 2026-10-13: "banners ok though").
- **Sun:** the 1995 ROM direction, 70 degrees up (3.4, section 4); soft-edged, not a point.
- **Sky:** the visible sky is a saturated blue backdrop of its own; whatever lights the scene must not tint the shade with that blue push.
- **A look change is not a rebake:** keep the raw quantities (sun seen, sky seen, colour coming back) and apply the formula afterwards.

### 3.7 The bake as it stands (2026-10-13, after two broken game builds; scripts in `scripts\importer\rtbake\`)
Owner, on the builds that guessed a lit side per polygon: "there's a light source, there's an angle and there's geometry. just shine a light on it".
- **No side is chosen** (SUPERSEDED the same day by 3.8: it lit walls from their hidden back). Every texel is lit from both faces of its polygon and keeps the brighter result. Guessing one "seen side" per polygon (road first, then sky) lit 952 pieces of ground from below and made neighbours on one surface disagree: dark wedges on the road, dark panels on cliffs.
- **A four-corner polygon is drawn along corners 0 - 2, not 1 - 3.** VERIFIED on a built file: the strips are `[1, 0, 2, 3]` (`meshgen.quads_to_strip` with `ccw` False). `lightmap1995.py`, `bake1995.save_scene` and `lightside.py` all assume 1 - 3. Three consequences, all seen in game:
  - a triangle (corners 2 and 3 equal) shows texels `b <= a` of its rectangle; the old formula filled `a + b <= 1`, so every triangle had sheared light (the saw-teeth along the road edge);
  - the ray scene cut twisted polygons along the other diagonal, so half their texels lay behind their own occluder (black panels and half-panels; 465 polygons are twisted by more than 10 cm, some by metres);
  - `lightside` / `roadsight` turn a polygon round by reversing its corners, which moves the diagonal: a turned twisted polygon is another surface. Course setting `lit_sides: false` leaves every polygon as it is (with light maps as the only lighting nothing needs a seen side).
- **The importer's own SR3 road mesh is in `save_scene`** (224,000 triangles a few cm over and under the 1995 road, hidden in game). It must not be among the occluders: it cast the "ghost shadows".
- **Trees and lamp posts** are not occluders as boards. Each tree is a trunk cylinder and a canopy ball that lets 25% of the rays through, each lamp post a cylinder; boards themselves take no baked light. (First attempt: every canopy sat at the origin because of a shadowed variable - no tree cast a shadow. Test a stand-in with a ray before trusting it.)
- **The sea sheet takes no baked light** (it came out at 0.35 under the cliffs' sky dimming).
- **Speed:** the per-texel loop is in C (`rtg2.c`): 22 million texels, both faces, 19 sun + 96 sky rays each, about 100 s on 31 threads (was 10 minutes in numpy, byte-identical).
- **Check before installing:** `asbuilt_decode.py` + `asbuilt_scene.py` read the BUILT files back (strips, uv1, light-map pages, single-sided boards) and render them. Renders of the bake's own arrays are not enough: both broken builds passed those.
- A Blender scene goes into a build as a local patch made by `scene_diff.py` against the patch-3 build (`game_cycle.sh`); it holds most of the course and must never be shipped. Moved trees are moved as whole original polygons (`board_moves`), overlaps the patch leaves are settled by `patch_clean`.

### 3.8 After the owner's second drive (2026-10-13; `rt_bake_game4.py`, `rtg4.c`, `seenside.py`, `seal1995.py`; build route `game_cycle2.sh`)
What was seen in game, the cause found in the data, and what was changed. All of it checked on the BUILT files before installing.
- **Bright rock beside its own shadow, hard dark panels on walls** (owner: "that bright piece of rock next to the shadowed faces looks suspicious as hell"). "Brighter of both faces" shows, on a wall turned away from the sun, the sun that falls on its hidden back. Counted within 16 m of the road: 2,168 standing polygons, 19,600 m2, against 26,900 m2 honestly sunlit. The dark panels were the places where something stood behind the wall.
  - Now a polygon shows the light of the side the ROAD sees (`seenside.py`, course setting `seen_sides`): 7,020 viewpoints (every 3 m, left / middle / right, 1.1 and 3.2 m up), six points per polygon, 203 million rays in 2.4 s. Seen on the winding side: stays. On the other side only: wound round. On both: material key `|3`, written once per side, single-sided, each copy with its own texels. Never seen: key `|4`, both faces lit and the brighter kept (the old rule, now only where the road cannot look). Mountain: 16,615 / 492 / 1,148 / 23,954 polygons.
  - Winding a polygon round must keep the diagonal the game cuts along: corners 0 and 2 stay, 1 and 3 change places (`seenside.rewind`). `lightside` / `roadsight` reverse the list and change twisted polygons; `add_scenery`'s per-side copies did the same and now use `rewind`.
  - The collect file carries the flag (`U` = never seen); the bake lights `U` polygons on both faces and all others on their winding side.
- **"Light seeping under the rock"**: a lit line on the road along the foot of a wall, inside the wall's shadow. A texel on a polygon's edge lies exactly in the plane of the wall standing on that edge; lifted 2 cm it is BEHIND any wall that leans over the road, in full sun, and the game blends it half a texel into the road. Where the ground goes on behind a wall the texel behind it does the same.
  - The point a texel is lit from is kept 4 cm inside its polygon's edges. Eight feelers along the surface (one texel long) find what crosses it; a point standing behind something whose back the road never sees is moved 5 cm in front of it (74,000 texels on Mountain). `rtg4.c`: `lm4_light`.
  - Wall feet that hang up to 60 cm over the ground get a skirt in the ray scene only (199 edges, most of them cliffs standing in the sea). The game's geometry is not touched.
- **Pixelated shadows.** 3 texels a metre, one sun sample per texel (0 or 1, blended by the game into steps), and a cap of 64 texels per polygon side that starved the big two-triangle fronts. Now 6 a metre within 20 m of the road, thinning with distance to 0.75; never-seen polygons at most 2; cap 256; every texel asks the sun from 19 points spread over its own square (points cut off from the texel's own point by something are not used). 47 million texels on 14 pages (22 million on 7 before), 204 s.
- **Pages by material.** A material shows one light map, so every (material, page) pair is a material copy and a mesh. The shelf packer scattered each material over all pages: 595 copies, 711 meshes. Materials are now dealt out to pages by area and each page packed as a whole: 375 copies, 494 meshes, pages 87% full. (A shelf per material was tried first and wasted half of every page.) `save_collect` writes the material index `G` for this.
- **"White pixels" in 4K screenshots** are pixels the game never drew: black with alpha 0 (an image editor shows the transparency as white), 26 to 102 per frame, on cliffs, parapets and house fronts. Hairline gaps between polygons, two kinds, counted in the built file: 1,655 places with another place within 1 mm that is not the same number (mostly one float32 step: a polygon that went through the Blender scene is rounded in course coordinates, its untouched neighbour in the slot's), and 8,008 corners lying on a neighbour's edge without being one of its corners (pieces cut by `uv_split`, two-triangle fronts beside finer ones). `seal1995.py` (course setting `stitch`) works on the finished meshes: near places become one, and a triangle with a foreign corner on an edge is cut there, fan-wise from the opposite corner, the new vertex taking the edge's own uv and light-map uv. After: 0 and 7; drawn area unchanged to 0.01 m2; 8,256 triangles added. TWO THINGS IT MUST NOT DO, both found the hard way on 2026-10-13: (1) leave a mesh with no triangle - the first sealed builds had one mesh of slivers whose corners all became one place, written with 16 vertices and 0 indices, and the game died on it as the track loaded (0x580B24; 09_authoring_status.md, crash table): such a mesh now keeps its own indices on the moved corners (triangles of no area) ; (2) skip a mesh because its cut strip passes 65,535 indices - at R4 that left 1,516 joints open in one mesh of 10,000 rounded pieces: it is now written as several meshes (the new ones take numbers at the end of the scene's mesh list). The search for corners on edges is filtered in C (`fastseal.c`; that walk over every edge in Python was the longest single step of an R4 build), the search for near places is on arrays; R1 builds come out byte for byte as with the Python loops.
- **The checkpoint and finish gates were missing** in every build since RAW: the code that adds them stood inside the `fill` block and the RAW recipe sets `fill: false`. It is now a function called in both cases. (25_verbatim_road_and_milestones.md said the gates were left on; they were not.)
- **The church tower** (owner, the same evening: "make an exception for the church tower"). Cut-outs take no baked light by rule (3.6), and the village tower is drawn with cut-out pictures (`tex_s1_x0960_y0576_64x128_c10D_t`, `..._c10F_t`): it stayed bright whichever way it faced. Course setting `lm_cutouts` lists tiles that take baked light all the same. `seenside` judges them too; they are never written twice (a cut-out is drawn two-sided) and they must stand in the way of the viewpoints like walls - the first try left them out and every wall was "seen" from inside, through the tower: the sunny face came out shaded. As built: sunny wall 0.87, the other two 0.25 and 0.29. Then the inside (owner: "the inner side of the tower must be shaded independently or all in shadow"): drawn two-sided with one light map, the far wall showed its outside light through the arches. Every listed cut-out polygon is now written once per side, both copies single-sided (section mark `~s`, as the tree boards' pairs), each with its own texels; they are not judged by `seenside` any more. The tower is three walls and three roof faces, so the bake closes such a building for the rays (a lid on its walls, a blocker where a side of the walls' box has no wall; ray scene only). As built: outside as before, inside 0.16 on all three walls - at 70 degrees the sun that enters an arch lands on the floor, not on the far wall.
- **A trap in the check itself:** `asbuilt_decode.py` kept pictures already present in its output folder, and light-map pages keep their ids from build to build: decoding a second build into the same folder showed the new uv on the OLD pages (a tower lit from every side, which the built file did not have). It now empties the folder's pictures first.
- **The cars in baked shadow** (owner: "the cars don't get shadowed when entering one of our baked RT shadows"): the road's overlay pages, see 6.4 and 04_trackdeform_road.md. Built and read back; NOT yet seen in game. A build without it is installed beside it as a fall-back.
- **Open sides** (2026-10-14; owner's free-camera screenshot SR3_20261014_224424 of a shaded rock wall with bright rectangles in it, the dark bars in them LIKELY the shadows of the fence posts on the other side; "fix the faces"): the road is not the only place a side is looked at from. A polygon never seen from the road showed the brighter face (often the sunlit far side), and one seen on one side showed that side's light on its back too. Course setting `seen_open` (default true): each side of every judged polygon sends 24 rays over its half space from each of the six test points; it is OPEN when at least 6 % of them go up and reach the sky (`seenside._open_sides`, `OPEN_MIN`); a side buried in rock or turned to the ground under a terrain sheet is not. A side the road sees or an open side is a side someone looks at: two of them -> `|3` (written once per side), one -> that side lit (wound round when it is the other one), neither -> `|4` as before. First outward R4 (v12): written once per side 7,924 -> 37,050 (93,000 m2), lit on their winding side 92,283 -> 183,082, never-seen brighter face 134,526 polygons / 50,000 m2 left; light maps 15 -> 22 pages, 51 -> 73 million texels, bake 157 -> 213 s. The result goes into the collect file (`fopen` / `bopen`) so the final build takes it over.
- `seenside` does not take `BC.PAIRS` as a skip list: that set holds `id()` numbers of polygons long replaced, and a different handful of live polygons matched them by chance in every run. The number of judged polygons still differs by one or two between runs of the same build (42,211 .. 42,215), from somewhere earlier in the importer; the area judged is the same. Watch `polygons found on a page ..., not found 0` in the final builds: a polygon missing from the collected set would keep the white picture.

## 4. The 1995 game (SEGA Rally Championship, Model 2A)

- ROM `maincpu.bin`: the hand-typed unit vector (0, -0.94, 0.34) at 0x13CD0 and 0x14810. INFERRED to be the direction the light travels (not proven by a code trace): sun 70 degrees up, squarely to the RIGHT of the start grid. The user confirmed the shadow angle against Model 2.
- 70 degrees is the midsummer solar NOON sun at about 42.5 degrees north (computed: 70.5). The Mountain course's light is noon in summer on the Mediterranean.
- The car's shadow in the 1995 game is a fixed patch under the car, always at the same angle (user, Model 2).
- The castle (three boards, one folded screen of 177 m) is painted lit from the LEFT while the sun stands to its right. Fix in the importer: the picture is laid on the boards from the other end, the boards themselves stay (course setting `mirror_groups`).

## 5. Sun position as a setting
With light maps nothing of the scenery depends on the live sun; `light_dir` plus a rebake moves it. Built for comparison: 16:30 clock time in midsummer at that latitude = 47.7 degrees up (hour angle 45.5), light travels (0, -0.737, 0.676), shadows about 0.9 x height instead of a third. Flat ground gets 0.87 of the light, compensated in the texture level.

## 6. Additions from the importer's comments and the owner's notes (same two days)

### 6.1 Lighting sets: values seen and what each did in game
- Location: master_gfx root +0x18 -> kind 12 `c7975114` -> 2 x `b473b5a7` (07_glue_and_other_files.md).
- Desert4's own sets are warm: sun 0.97 / 1 / 0.82, scale 1.12 / 1.05 / 1, tint 0.45 / 0.33 / 0.26. On the 1995 colours
  they gave an overall SEPIA cast. VERIFIED in game (cast gone with neutral sets).
- Neutral sets: the owner liked the colder tone but wanted no blue tint, so scale 1 / 1 / 1 with ambient 0.40 / 0.41 /
  0.43 was used; later ambient and the fog / sky colour were made neutral too, because with ambient 0.40 / 0.41 / 0.43 and
  Desert4's fog / sky colour 0.55 / 0.82 / 0.92 the car's white read 211 / 222 / 255 (owner, 2026-10-08).
- `lighting_from`: another track's two sets copied float for float (the cars are then lit as on that track). Mountain
  uses Tropical4's.
- `scene_gain`: per-channel gain on the classic tiles so that lit scenery keeps its look under the donor's light. The
  importer's own light gives flat ground 1.14 (ambient 0.41 + sun 1.0 x 0.73). Computed from the donor's numbers the gain
  gave a green cast; MEASURED from screenshots of six surfaces ("Light A" / "Light B", 2026-10-08), Tropical's light shows
  lit scenery 1.53 / 1.50 / 1.39 times brighter (R / G / B) than the importer's own. The gain is applied to the lit
  scenery only: in build Z6 it had reached the sky textures (sky at 0.68 of its brightness). Mountain's setting is
  0.8 / 0.8 / 0.8.
- Fog: floats 10..13 of each set. The 1995 game has no fog, and with fog the fogged far edge of the sea sheet stood as
  blue bars on the horizon; the importer switches it off, and the owner dropped all fog variants for the 1995 courses.
- Sun direction: floats [1:4], the direction the light TRAVELS, written to both sets (the cast shadows and the shading
  must agree).
- CONFLICT on Mountain's light direction. (a) The course settings file (modified 2026-10-08 12:55) has `light_dir`
  [-4, -6, 4], and a comment in `import_classic.py` says "Desert4's own -4 -6 4 = sun ahead and to the right on the start
  grid, 47 degrees up, which is where the 1995 game has it (left houses lit, church front and right houses in shade)".
  (b) Section 4 of this file gives the 1995 vector (0, -0.94, 0.34), 70 degrees up, squarely to the right of the grid,
  and the comment at the top of `fastlm.c` (2026-10-08, evening) says "Mountain: light_dir 0, -9.4, 3.4". (c) Section 5
  describes a 16:30 variant, (0, -0.737, 0.676), built for comparison; the newest build folders are named
  `..._sun1630_...`. The later sources are (b) and (c): LIKELY the builds of the evening of 2026-10-08 pass the direction
  with `--set` and the settings file still holds the earlier value. Which direction the owner finally kept is not
  recorded (OPEN_QUESTIONS.md).
  RESOLVED 2026-10-08 (evening): the owner drove both the 70 degree and the 16:30 (47.7 degree) build and kept the 70
  degree sun ("let's keep the 70deg sun as well (remove the alternative)"). The settings file now holds
  `light_dir` [0.0, -9.4, 3.4]; the [-4, -6, 4] value was a guess from before the ROM vector was found. VERIFIED in game
  as the owner's choice; that the ROM vector IS the 1995 light remains an inference (section 4).
- How dark a car's (and any live) shadow is on a lying surface: ambient / (ambient + sun x scale x NL), NL = how steeply
  the sun stands (the course setting `light_split` changes it, import_classic.py). The SR3 tracks' own two sets
  (computed from their master_gfx, 2026-10-14): Tropical4 38 / 37 % (sun 73 degrees up), Canyon4 37 / 29 % (59), Alpine4
  40 / 39 % (53), Lakeside4 36 / 48 % (27), Desert4 35 / 35 % (47), Stadium4 28 / 30 % (88). Mountain with Tropical's sets
  and its 70 degree sun: 37 % ("Classic 1"); the variants Classic 2 / 3 / 4 keep 27 / 21 / 16 %.
- Changing the light live (for a shadow-darkness switch in game, owner 2026-10-14): NOT found yet. Established: the
  shaders get ambient and sun through 0x402060 (via 0x402750, called from 0x402B40 when the material changes), which
  keeps a shadow copy of the constant registers at 0x80F690 + 16 x register and uploads only what differs; 0x402750 reads
  the light state at 0x9F0FB8 (ambient) / 0x9F0FC8 (sun), which is slot 2 of a render-state stack (0x9F0600 + 0x4D0 x
  depth; 16 templates at 0x9EB8F0, pushed by 0x416140). In a race none of these changed the picture: the slot, the slot
  with the constant copy filled with no-numbers (every value should then be sent again), and 156 other copies of the
  ambient + sun floats in the heap, one at a time (none of them feeds the slot). Writing ALL 517 copies of the sun colour
  at once crashed the graphics driver (some are in buffers the driver uses). So the values reach the GPU at track load by
  a path not found yet. Until then the four RT builds (View Change on the mode menu) are the comparison.

### 6.2 Things tried in the lighting of the import and dropped
| Tried | Result |
|---|---|
| Up-normals on every classic face (lit like flat ground) | used at first so that crossed tree boards do not shade differently; replaced by the brightness rule of 3.1 |
| The plain physical N.L of the 1995 sun (70 degrees up) | build Z13L75: every wall dim, polygons turned from the sun nearly black ("these faces are way too dark for something exposed to direct sunlight") |
| `light_contrast` 0.5 meaning "half of each face's own normal in the lighting" (build Z4L50) | what the setting meant on 2026-10-08 in the morning (owner's notes); section 3.1 defines K differently (floor = 1 - 0.6 K). The owner's verdict on Z4L50 is not recorded |
| Mirroring the horizontal part of the normals | switched on after a report of shade on the sunny side (really the far side of free-standing rock); with it ON, build Z7L25 measured inverted (sun on the left, left houses lit). OFF |
| Lighting the road as flat ground | it came out nearly white |
| "The lower ground is the open side" (and "lower by 2 m") for upright faces | turned house walls and the church front inwards wherever the fill lay lower inside them (builds Z8 / Z9: sunny houses dark, the church front lit in three different ways) |
| "Faces the road" as the seen side | wrong for rock seen from its far side |
| Writing EVERY polygon twice, once per side | right, but twice the scenery ("brute-forcish and dumb ... fix things properly") |
| "Sure" only when NO ray escapes on the other side | one stray ray of 32 made the ground floor of the church "not sure" and lit differently from the wall above; now the open side needs at least 4 times the escaping rays of the other |
| A brighter light-map fallback colour in the exe | washed the picture out (20_launcher_inmemory_patches.md, section 12) |
| Reflecting the castle boards themselves to fix their painted light | the L-shaped screen hung 20 m out over the sea (build Z15: "the castle position needs to be adjusted"); the picture is mirrored in place instead |

### 6.3 Side detection: numbers behind 3.2
- `lightside`: "open" = at least 3 of the 32 rays escape (a ray that hits nothing within 600 m); enclosed polygons are
  settled by the mean free path (at least 1.0 m and 2.5 times the other side's) or by their neighbours' winding; a floor
  under everything stops rays escaping downwards; cut-outs are neither tested nor block. Ground with no sky above it (the
  hillside under the 1995 ground) is turned up. Walls in one plane that touch vote as one wall ("I don't get why the
  church + tower is unevenly lit when all those faces are coplanar").
- `roadsight`: viewpoints every 4 m, 3.5 m left and right, 1.1 m and 3.2 m up, reach 170 m; a drone camera off the road
  can still find a polygon turned away ("right" means right from where the cars are).
- Material key suffixes: `|3` = seen from both sides, written once per side, single-sided; `|4` = side not certain, drawn
  two-sided and lit as its brighter side; `|1` / section suffix `~s` = single-sided cut-out (tree blade side).
- Ray casting moved from Blender's BVH (150 .. 200 s for the 440,000 polygons of a build with baked light) to `rays.c`
  (about two seconds).

### 6.4 The road's sun / shadow overlay page
The TrackDeform overlay page texture is a sun / shadow map laid over the cars from above: green = how much sun, red = how
much of the sky light is shut out (decoded 2026-10-13: 04_trackdeform_road.md, "texA decoded"); a car takes the nearest page. Written as all shadow it made the cars dark on the imported track (04_trackdeform_road.md). VERIFIED in
game. This narrows the open question below; the layout beyond the two colours is still not decoded.

### 6.5 Light-map and bake implementation notes
- Light-map bake: 7 rays round the sun and 16 over the half space per texel; the bounce takes the mean colour of the tile
  that was hit. `fastlm.c` lights the texels in about 10 s where the numpy version took 85 s (17, section 5).
- The road is on the light maps too: the first light-map build had none ("the road has no shadows").
- Per-vertex bake: a vertex the table does not know is taken as lit and open; a ray that meets a see-through texel of a
  cut-out goes on; the first 0.12 m of a ray do not count.
- Gates are unlit (SEGA's material); their gain is 0.94 (23_texture_pipeline.md, section 4).

## Open questions
- The vertex formats that carry a colour (SEGA's main way of baking).
- The road's own sun / shadow overlay page.
- What `gfShadowParamsPs` x and w are; why spectators lose their shadows with the hard-edge settings.
- Whether a partial mip chain is accepted (light map pages currently carry a full chain; deep levels mix unrelated places).
- The exact response curve of a light map value.
