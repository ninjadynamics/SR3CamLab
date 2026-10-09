# 07 - Glue objects (kind 12) and the remaining files

Kind 12 data is used directly as a C struct after the loader replaced the ref fields by pointers; the chunk's
4th header word is a type hash. The last chunk of a file is the root returned by the loader (0x6530B0).

## master_gfx root: type f626b658, 68 bytes
| Off | Type | Meaning | Confidence |
|---|---|---|---|
| 00 | u32 | 3 | VERIFIED |
| 04 | ref | scenery tree, kind 11 (05). No null check (0x5C2275) -> mandatory | VERIFIED exe |
| 08 | ptr | -> +0x34 (boundary descriptor) or 0 | VERIFIED exe 0x5C9B13 |
| 0C | ref | TrackDeform (04). Loader 0x5C57F0: 0 skips the road setup; not a usable track | VERIFIED exe |
| 10 | ref | sky dome mesh (named "skydome"); 0x5A93CC tests for 0 | VERIFIED name, LIKELY optional |
| 14 | ref | a kind 5 chunk in 5 tracks, 0 in Stadium4 | UNKNOWN |
| 18 | ref | kind 12 c7975114 `{5, floats, ..., ref, ref}` -> two kind 12 b473b5a7 (196 bytes: fog/light colours, distances). 0x599FB0 copies 4 floats from the first | LIKELY lighting sets |
| 1C | ptr | alternative source for the same 4 floats when +18 is absent | LIKELY |
| 20, 24 | f32 | e.g. 85.7, 95.2 (Tropical); 0 in Stadium4 | UNKNOWN (sun angles?) |
| 28 | ref | 0 in Stadium4; object used by 0x65DEF0 / 0x65EBD0 when present | UNKNOWN |
| 2C, 30 | ref | two small DXT5 textures (71fc1a34 64x128, a76e504b 64x64), same ids in every track; copied to [0x9C9510] | VERIFIED, purpose UNKNOWN (particles?) |
| 34 | ref | boundary BSP (06) | VERIFIED |

## master_xdata objects
ecdb142b root (03); 0b9214e0 `{1, ref x3}` camera lists; 20f93164 "Helicopter" `{1, 1, name, ..., ref}` -> 58de89a7
(452-byte particle/effect description with a texture ref); 15c476ae `{1, 0}` stub.

## Object files (identified, not decoded)
- game_objects root kind 5: `u32 3, u32 nObjects, ptr objects (76 bytes each), ptr type table, ptr ..., ...` with
  asset paths ("M:/Development/SegaRally/Assets/Particles/sta_firework_03.xdata") and refs to kind 12 58de89a7
  effect objects and to small kind 5 name records (`{3, 1, ->name, id}`).
- gameobj_gfx_dis_data: pairs of kind 7 Granny file + kind 5 `{n, ref}`, and a final list chunk.
- pobj_master root a4dd8f06 `{2, ref list, ref d01419de, ref 20018776}` (0x5C5559 reads +4, +8, +0xC);
  pobj_plac root 690c0d8f `{1, ref placement chunk}`. Placement and list chunks reference materials in master_gfx.
- ArcadeDatabase track list (type 1bff7e65): see game-runtime-and-frontend.md.

## Meshes (kind 1) - tool `work/scripts/meshgen.py`
Static scenery mesh with one LOD and one group (example Stadium4 79d17eed, 4520 bytes):
| Part | Layout | Confidence |
|---|---|---|
| LOD header 0x48 | `stride, 0, format, 0, 0, nVerts, 0, nIdx, nGroups, 1, 0, ptr groups, ptr verts, ptr idx, 0, 0, 0, 0` | VERIFIED (identity clone byte-identical) |
| group, 20 bytes | `0, nVerts, firstIndex, flags<<16 or indexCount, material ref` | VERIFIED |
| vertex, format 0x20C7, 48 bytes | `f32 x,y,z,w (w = 1.0 on 74 of 77 vertices), f32 normal[3], f32 tangent[3], u16 uv0[2], u16 uv1[2]` | VERIFIED sizes; uv = value/32768 LIKELY (uv0 max is exactly 32767; uv1 = light-map coordinates) |
| indices | u16 triangle strip, degenerate joins, padded to 4 | VERIFIED |
| model record | `0, ptr name, ..., 4x4 identity matrix, ...` then a pointer list, a second record `{ptr model, ptr name2, 0, 0, ptr LODs(0), matrix}` | LIKELY (copied verbatim) |
| tail record (last fixup) | `ptr model, 2, 0, 0, f32 min xyz, max xyz, centre xyz, ...` | VERIFIED (equals the vertex bounding box) |
Winding: strip triangles at even positions are CLOCKWISE seen from the normal side (score -35/-35, -82/-82, -1022/-1022
on three SEGA meshes). Scenery meshes are in world space (identity matrix); library objects are instanced through the
kind 11 instance lists (not decoded).
Other formats seen: 0x2041 = position + uv (stride 20, sky dome); 0x20D7 stride 52; 0x21F7 stride 60; 0x2053 / 0x20C3 stride 36.

Authoring by cloning (`clone_mesh`): keep header shape, model/tail records and names of a template, replace group,
vertices and strip, relocate the pointers behind the index data, rewrite the bounding box. `make_verts` builds one
quad = 4 vertices with uv0 0..1; `quads_to_strip` emits SEGA's winding. Checked: an identity clone reproduces the
template byte for byte; authored meshes get the same winding score sign as the template.

## Materials (kind 2)
Stadium4 7e9488ff (the wall material used as template): word 0 = ref to the shader stub (kind 3 f398b7a8), then a
parameter table; "Uber" shader parameter names in the string area (gTextureDiffuse, gTextureNormal, gTextureLight,
gbUberLMAP, gfLightmapOffsetAndScale ...). Texture refs at +0x1BC (diffuse, DXT1 512x512), +0x1DC, +0x1FC, +0x21C,
+0x27C, +0x32C (a light-map page shared with the road overlay pages), +0x33C. `clone_material` copies the chunk under
a new id and swaps the diffuse ref (+0x1BC) - everything else stays borrowed. LIKELY sufficient; untested.

## Material switches and alpha test (sixth package) - `work/scripts/matscan.py`
Materials of shader f398b7a8 and size 1848 (the "Uber" family; 363 opaque and 121 alpha-textured ones in Alpine4) hold a
parameter record table `{ptr name, 0, 0, ptr value cell}`; boolean switches are 4-byte cells. Cells that matter:
| Cell | Switch (by position in the name list) | Evidence (Alpine4, materials whose diffuse texture has transparent texels vs not) |
|---|---|---|
| +0x4D4 | gbUberATEST (alpha test) | 1 in 61 alpha-textured materials, 0 in all 367 opaque ones |
| +0x4E4 | gbUberABLEND (alpha blend) | 1 in 54 alpha-textured and 52 others (smooth-alpha DXT5), never together with +0x4D4 |
| +0x50C | gbUberDSIDE (two-sided) | 1 in 9 alpha-tested and 10 opaque materials |
CORRECTION (2026-10-07, replaces the by-position guesses above): each switch VALUE is the u32 right BEFORE its inline name
string. Find the names with the regex `gbUber[A-Za-z]+` in the 1848-byte material; value = u32 at match.start() - 4.
| Cell | Switch | | Cell | Switch | | Cell | Switch |
|---|---|---|---|---|---|---|---|
| +0x4D4 | gbUberATEST | | +0x52C | gbUberSSRECV (static shadow receive) | | +0x5B4 | gbUberSPECM |
| +0x4E4 | gbUberABLEND | | +0x540 | gbUberSDRECV (dynamic shadow receive) | | +0x5D8 | gbUberTWOS |
| +0x4F8 | gbUberABLENDAdd | | +0x554 | gbUberDIFFM | | +0x620 | gbUberREFL |
| +0x50C | gbUberDSIDE | | +0x574 | gbUberNORM | | +0x65C | gbUberSCROLL |
| +0x51C | gbUberSCAST | | +0x594 | gbUberLMAP | | +0x670 | gbUberDISCR |
ATEST / ABLEND / DSIDE keep the cells found statistically. Road decals that must show the cars' shadows use the combination
of Desert4 3546ce1e (163 SEGA materials: blend + static and dynamic shadow receive): ABLEND, SSRECV, SDRECV, DIFFM, NORM = 1,
all others 0 (`build_classic.SHADOW_CELLS`, `shadow_recv`). The earlier cell list had SDRECV at 0: no car shadow on the
draped 1995 road (seen in game). In-game result of the corrected cells: being tested as this is written.
VERIFIED statistically; the names are assigned by order (LIKELY). Example alpha-tested two-sided material: Alpine4
1b5e8346 (pennant flags, DXT5 256x128). It also has vertex colours on and lighting off, so it is not cloned as it is:
`meshgen.clone_material(..., cutout=True)` takes the opaque wall template and sets +0x4D4 and +0x50C to 1.
Check on the built step17: all 25 cut-out materials differ from the template in exactly three words (+0x1BC texture,
+0x4D4, +0x50C), same fixups and refs; their textures are DXT5 with a 255/0 alpha channel (`make_texture_dxt5`).

## Empty object list (sixth package) - `build_classic.minimal_objects`, `check_min.py`
game_objects root (kind 5, last chunk), as read by 0x5BF450 / 0x5BBFF0 / 0x5BCC40 / 0x5C04B0 (VERIFIED by reading that code):
| Off | Field | Loader behaviour |
|---|---|---|
| 00 | u32 version (3 in all six tracks) | `< 3`: the shape-table pointer is taken as 0 and dereferenced at 0x5BF49A, so it must be >= 3; `>= 2` (0x5C5E27): the gameobj_dis file is looked up |
| 04 | u32 object count | every loop is `count` bounded; 0 skips them all |
| 08 | ptr object records, 0x54 bytes each (not 76): `{ptr, ptr class name, u16, u16, id, 4x4 matrix rows, ptr parameters}` | copied to a run-time array by 0x5BCC40 |
| 0C | ptr descriptor `{1, n, ptr entries of 0x2C}` (animated models; n = 5 Desert4, 3 Stadium4, 9 Lakeside4) | 0x5BE010: returns 0 when the descriptor or the dis-file root is 0 |
| 10 | ptr shape table `{count, refs}` | 0x5BF49A loop, skipped when count is 0 |
Class names seen: Dumb_Temp_Spectator, Generic_Animator, Animatable_break_event, TV_Cameraman_Temperate, Thrush,
Generic_Particle, SFX_Object, Crowd_SFX_Object, Generic_Breakable, Lap_Distance_Animator_With_Emitter.
Missing files: 0x6530B0 returns 0 for a file that is not there. The callers test it: game_objects root 0 -> 0x5BF450
returns 0 and 0x5C04B0 returns at once; gameobj_dis 0 -> 0x5BE010 returns 0; pobj_master 0 -> 0x5C5509 skips pobj_master,
pobj_plac and the grass cache together.
AUTHORED empty file (step21, step22): ONE kind 5 chunk of 64 bytes, same id as the original root,
`{3, 0, ptr +0x30, ptr +0x14, ptr +0x24}`, descriptor at +0x14 `{1, 0, ptr +0x30}`, table at +0x24 `{0}`, pointers at
+8, +0xC, +0x10, +0x1C. The gameobj_dis, pobj_master, pobj_plac files and the grass cache are left out.
Risk (not checkable statically here): the original file also carries particle/effect definitions and textures that
other code may look up by id; step19 (count set to 0, everything else kept) remains as the fallback.
Camera files: see 03_master_xdata_route.md.

## Alpha blend switch and how SR3 paints road markings (sixth package) - `markscan.py`
Alpine4's centre dashes are NOT in the road data. They are decal quads inside the ordinary scenery meshes (85 mesh
groups, 1661 vertices): about 3 m long and 0.33 m wide, 1 to 2 cm above the road vertices, median 0.45 m from the centre
line, uv on one stripe of the 128x256 DXT5 texture 54c156ac (u 0.17..0.43, v 0.02..0.93). Their materials (61b54d97,
21169864, ...) are 1848-byte Uber materials with +0x4E4 = 1 (alpha blend), +0x4D4 = 0, +0x50C = 0. VERIFIED (data).
`meshgen.clone_material(blend=True)` sets the same cell; step24's road paint uses it.

## Sky dome (root +0x10), package nine
Mesh format 0x2041, stride 20: `f32 x, y, z, f32 1.0, u16 u, u16 v` (32768 = 1.0); 572 vertices, 1340 strip indices
(Stadium 1332), TWO groups = two materials (1728 bytes, shader f398b7a8), each with one DXT5 texture at material +0x1BC
and no mip chain (Tropical 512 x 512, Canyon 1024 x 512, Alpine 1024 x 1024, Lakeside / Desert 2048 x 1024, Stadium
4096 x 2048). A closed shell around the ORIGIN, radius 2.2 .. 2.8 km (Tropical / Alpine 1.8 .. 2.3 km); Canyon,
Lakeside, Desert and Stadium have identical vertex positions. v runs from the zenith (0.002) to the nadir (0.994); each
group covers half of the shell. 0x5A93CC only tests root +0x10 for 0.
How the dome is placed each frame (world origin or camera) was NOT traced; at 2.2 km radius both look the same from
a track inside the +-750 m square.
Authoring: `sky1995.py` keeps mesh, materials and texture headers and rewrites the texture pixels only.

## Uber material: specular colour, and the dynamic shadow parameters (2026-10-08)

- Constants of the 1848-byte material sit right BEFORE their inline name, like the switches: gf3AmbientCol +464 (3 floats),
  gf3DirCol +480, gf3SpecCol +498, gfBumpScale +4B0, gfSpecularPower +4C0. VERIFIED (names and offsets in Desert4 3546ce1e).
- SEGA materials with SPEC = 1 and SPECM = 0 carry gf3SpecCol 0 (5 of 5 in Desert4 / Stadium4 / Lakeside4 / Canyon4). Our road
  decals had SPEC 1, SPECM 0 and the template's 0.5: the whole draped road shone. `build_classic.shadow_recv` now writes
  ROAD_SPEC (0) there.
- Dynamic shadows are variance shadow maps. Pixel shader (system\shaderlib_uber_data.sbf, disassembled with D3DDisassemble):
  `p = var / (var + (d - mean)^2)` with `var = E[x^2] - mean^2 + gfShadowParamsPs.y`, then `p ^ gfShadowParamsPs.z`, lit when
  `d <= mean`; `.x` is added at the end. The four floats live at 0x9F1068 (set by 0x594570 at start-up: y = 1/512, z = 10,
  w = -1/512; x is recomputed at 0x59B537). gfShadowParams at 0x9F1028 = (20, 0.05, ..). VERIFIED (code + shader).
- `patch.ps1 Set-ShadowParams`: a track folder may bring `shadow.txt` ("<variance floor> <power>"); written to 0x9F106C / 0x9F1070
  while the track is chosen, SEGA's values put back otherwise. Effect in game NOT YET CONFIRMED.
  Later the same day: "the two numbers alone changed nothing visible" in a run of 2026-10-08 (comment in patch.ps1); a
  third word "noblur" was added (20_launcher_inmemory_patches.md, section 7).
- CONFLICT between files: this section says the technique is variance shadow maps (VERIFIED: code + shader) and that
  w = -1/512 and x is recomputed at 0x59B537; 16_lighting_shadows_lightmaps.md, written later the same day, says "LIKELY
  variance shadow maps" and "x and w not identified". Neither source withdraws the other. Recorded as LIKELY for the
  meaning of x and w; the formula above is what the disassembled shader contains.

---
# Corrections and additions from in-game runs (2026-10-07 / 08)

## master_gfx root: fields that are no longer UNKNOWN
| Off | Was | Now |
|---|---|---|
| 14 | "a kind 5 chunk in 5 tracks, 0 in Stadium4: UNKNOWN" | the slot's FAR HORIZON CARD: in Desert4 the Kilimanjaro picture, mesh format 0x2041. 0 in Stadium4, so optional; the importer sets it to 0 and the imported course runs without it (import_classic.py; owner's notes: "Desert4's Kilimanjaro horizon card (root +14) removed"). LIKELY (how the card was identified is not recorded; note that the table above calls the referenced chunk "kind 5" while the importer's comment gives it a mesh format) |
| 18 | "LIKELY lighting sets" | two sets of 49 floats; seven ranges identified by patching and in-game runs: 16_lighting_shadows_lightmaps.md, section 1.1 |
| 24 | "e.g. 95.2 (Tropical): UNKNOWN (sun angles?)" | Desert4 has 128.0 here; LIKELY the height of the sky dome above the camera (in game the dome sits about 110 m above the camera in the Desert4 slot). +20 stays UNKNOWN |

## Sky dome in game
The dome FOLLOWS THE CAMERA (this answers "how the dome is placed each frame was NOT traced"): VERIFIED in game by the
position of the horizon. What follows from it for an imported course, and how the 1995 sky is laid on the dome:
22_gapfill_zfighting_scenery_rules.md, section 6.

## game_objects root +0x10 is the material binding table, not a shape table
The tables of this file above call root +0x10 a "shape table" and the first authored empty file wrote it empty. It is
the MATERIAL BINDING table of the Granny models (15_spectators.md, sections 1 and 4): emptied, spectators came out grey,
T-posed and misplaced in game. Separately, the AUTHORED EMPTY 3-file form described above is not usable in a race (the
pobj files and grass cache are required: 02_track_files.md); the importer now keeps the slot's files (`props: slot`) or
only empties the object list (`noobjects`).

## Mesh uv is signed
The vertex table above gives "uv = value / 32768 LIKELY". In game: uv0 is a SIGNED 16-bit value, -1 .. +1, with 32768
= one repeat (SEGA's own meshes: 95 % of the values are 0..0x7FFF, the rest small negatives). VERIFIED in game
(23_texture_pipeline.md, section 3). uv1 has the same scale and is the light-map coordinate, honoured per vertex
(16_lighting_shadows_lightmaps.md, section 2).

## More mesh facts
- A four-cornered polygon written by `quads_to_strip` is drawn as two triangles along corners 1 - 3 (16, section 3.2).
- Limit per mesh group: 65,535 vertices and 65,535 strip indices (u16 counts). `share_corners` merges vertices that agree
  in everything; the tangent is made a function of the normal first (17_mountain_build_notes.md, section 1).
- Format 0x20C3 (36 bytes: position xyzw, normal, uv0, uv1) is the format of the start / finish banner mesh `4ec27d47` in
  game_objects; `finishgate.py` writes it (15_spectators.md, last section). Its three LODs are states, not detail levels.
- A second 1728-byte variant of the Uber material exists: every offset of the 1848-byte one minus 120 (16, section 1.2).
  SEGA's unlit material Desert4 `47948b52` is of that size.

## Cloning a material: what else it drags along
A cloned Stadium wall material (switches LITE PIXL SPEC DIFFM NORM LMAP SPECM REFL) still points at that wall's normal
map, light map, specular map and reflection; in game they painted bright window-grid patches over the new diffuse
texture. This corrects "LIKELY sufficient; untested" above: swapping only +0x1BC is NOT sufficient. The importer binds
neutral maps instead (23_texture_pipeline.md, section 2). VERIFIED in game.

## In-game result of the corrected shadow cells
The combination ABLEND, SSRECV, SDRECV, DIFFM, NORM = 1 on the draped road decals: "shadows fixed" (owner, 2026-10-07).
VERIFIED in game. This closes "being tested as this is written" above.
