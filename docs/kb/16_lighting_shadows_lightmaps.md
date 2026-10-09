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
The TrackDeform overlay page texture is a sun / shadow map: green = sunlit, red = shadow; a car takes the value of the
nearest page. Written as all shadow it made the cars dark on the imported track (04_trackdeform_road.md). VERIFIED in
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
