# 24 - Shaders: where they live, how a material picks one, and whether one can be replaced at run time

Static analysis of 2026-10-08 (files on disk only; the game was not started and no process was read). Question behind it:
can building walls of an imported track get parallax mapping (a height-based, view-dependent texture shift in the pixel
shader) without modifying any game file?

Tags: VERIFIED (and how: "file" = read from a data file with `sbfw`, "PE" = read from the executable's headers, "code" =
disassembly of `Rally.exe` with `tools/import/core/x86.py`, "shader" = `D3DDisassemble` of the bytecode, "count" = a measurement
over files), LIKELY, UNKNOWN. Nothing here was seen in game.

Working files of this analysis (parsers, full disassemblies, counts) are in the session scratch folder `shader_agent\`, not
in the knowledge base. SEGA's shaders are quoted only in fragments.

## 1. Verdict
Feasible with named risks, for imported walls only, with no file of the game changed and no file added to its folder.
- The shaders are precompiled Direct3D 9 bytecode in two library files; the "uber" material picks one of 1229 ready-made
  technique records by a bit mask built from its switches. VERIFIED (file + code).
- The pixel shader of every specular permutation already receives the view direction in tangent space per pixel, and the
  normal map's alpha channel is not read. VERIFIED (shader).
- At draw time the engine takes the `IDirect3DPixelShader9*` from a field of the shader record in memory (record + 0x10).
  Writing another pointer there changes what is drawn. VERIFIED (code) that the field is read on every bind; the write
  itself is untested.
- A permutation exists that no material of the game, of the installed added tracks, or of the 24 Revo conversions selects:
  `T_Lpse_Tdnl` (LITE PIXL SPEC DIFFM NORM LMAP REFL, SPECM off). Imported walls can be moved onto it by one switch, so a
  replacement touches nothing else. VERIFIED (count).

## 2. Is Rally.exe packed? No (resolves the conflict between 08 and 16 / 20)
VERIFIED (PE). File size 3,334,144 (0x32E000), image base 0x400000, entry point RVA 0xB155F inside `.text`, a normal
import directory of 19 DLLs.

| Section | VA | Virtual size | Raw offset | Raw size | Flags | Entropy of raw data |
|---|---|---|---|---|---|---|
| .text | 0x401000 | 0x272C80 | 0x1000 | 0x273000 | 60000020 | 6.68 |
| .rdata | 0x674000 | 0x092066 | 0x274000 | 0x093000 | 40000040 | 6.04 |
| .data | 0x707000 | 0x44585C | 0x307000 | 0x024000 | C0000040 | 2.61 |
| .tls | 0xB4D000 | 0x0012A1 | 0x32B000 | 0x002000 | C0000040 | 0 |
| .rsrc | 0xB4F000 | 0x0003A0 | 0x32D000 | 0x001000 | 40000040 | 3.67 |

- `.data` is 4.27 MB in memory and 147 KB on disk: only VA 0x707000 .. 0x72AFFF has file bytes; everything from 0x72B000
  to 0xB4C85B is zero-filled at load (uninitialised data). 0x9F1060, 0x9F1068, 0x7ED10C and 0x9F1084 all lie there, which
  is why reading them from the file failed. 0x729B0C (the shader rename table) is inside the raw part and reads fine.
- Code and constants are plain (entropy 6.7 / 6.0, strings and imports readable). So: not packed; statement of
  16_lighting_shadows_lightmaps.md section 1.3 ("packed") is wrong, 08_exe_loading.md ("not packed") is right. What 16 and
  20 conclude from it stays true: run-time values in the zero-filled part can only be read from the running process.

## 3. Where the shaders are
### 3.1 Compiled bytecode in data files (VERIFIED, file)
Every shader the renderer uses for materials is compiled bytecode (version token + `CTAB` comment, compiler string
"Microsoft (R) HLSL Shader Compiler 9.19.949.1104" in all of them), stored in kind 3 chunks ("effects").

| File (`Rally\system\`) | Stored | Effects (kind 3) | Techniques | Shader records | Of which | Bytecode bytes |
|---|---|---|---|---|---|---|
| `shaderlib3_data.sbf` | SBZ1, 348,292 raw | 33 | 175 | 232 | vs_2_0 75, ps_2_0 115, vs_3_0 13, ps_3_0 29 | 235,428 |
| `shaderlib3_uber_data.sbf` | SBZ1, 1,174,556 raw | 1 (`ubershadergame.fx`, id 2be3a2a9, 1,139,780 bytes, 7139 pointer fixups) | 1229 | 726 | vs_3_0 266, ps_3_0 450, vs_2_0 5, ps_2_0 5 | 1,014,456 |
| `shaderlib2_data.sbf` | SBZ1, 327,488 raw | 32 | 172 | 226 | vs_2_0 75, ps_2_0 115, vs_3_0 12, ps_3_0 24 | 215,636 |
| `shaderlib2_uber_data.sbf` | SBZ1, 804,860 raw | 1 (same id) | 1229 | 525 | vs_3_0 222, ps_3_0 294, vs_2_0 5, ps_2_0 4 | 670,420 |

- In `shaderlib3_uber`: pixel shaders 172 .. 2168 bytes, vertex shaders 396 .. 3400 bytes; all 726 bytecodes are distinct.
- `ShaderLib_data.sbf` and `shaderlib_uber_data.sbf` (the latter stored raw, 1,202,592 bytes, header version word 5 instead
  of 4, same shader counts as library 3) are not named anywhere in the executable. LIKELY leftovers; `sbfw` does not read
  version 5.
- Which pair is loaded (code, 0x65F160, called from 0x5922F3): `\system\ShaderLib2_data` + `ShaderLib2_Uber_data` when
  `[0x89A01C] == 0` or `[0xA3398C] != 0`, else `ShaderLib3_data` + `ShaderLib3_Uber_data`. VERIFIED (code). `[0x89A01C]` is
  one of the graphics quality globals next to DrawDistanceQuality (0x89A014); which `config.ini` key feeds it was not
  traced (LIKELY ShaderVersion or ShaderQuality; the owner's `config.ini` has ShaderVersion=3, ShaderQuality=2). The same
  global, when 0, strips every per-pixel bit from the material masks (section 4.2). Everything below is for library 3.
- Other files with bytecode: car model files (`sr_car_*.fx` chunks, the same names as in the library), `granny\*` and
  `osd\*` (a small `ubershadermax.fx` chunk each), `Particles\*`, `posteffects_data.sbf`, and
  `noncarmodels\oildrummodel_data.sbf` (`i_pl_with_damage.fx`, an effect the libraries do not have). Track files hold no
  bytecode: their kind 3 chunks are stubs carrying only the effect name (`ubershadermax.fx`, `3wayblend.fx`, `water.fx`).
  VERIFIED (file scan of every file under `Rally\`).

### 3.2 HLSL source in the executable: nine small utility shaders only (VERIFIED, code)
`Rally.exe` imports `D3DXCompileShader` from `d3dx9_41.dll` (IAT 0x6743D0, thunk 0x4C87EC). It is called nine times, all in
one start-up function (0x587060 .. 0x5873A4), on text that sits in `.rdata`:

| Call site | Source VA | Length | Profile |
|---|---|---|---|
| 0x587092 | 0x6B5100 | 2660 | vs_2_0 |
| 0x5870F6 | 0x6B5B68 | 2762 | vs_2_0 |
| 0x587159 | 0x6B6638 | 2470 | vs_2_0 |
| 0x5871BC | 0x6B6FE0 | 3666 | vs_2_0 |
| 0x58721E | 0x6B7E38 | 1900 | ps_2_0 |
| 0x587280 | 0x6B85A8 | 2945 | ps_2_0 |
| 0x5872E2 | 0x6B9130 | 2357 | ps_2_0 |
| 0x587341 | 0x6B9AF0 | 63 | ps_2_0 |
| 0x5873A4 | 0x6B9A68 | 128 | vs_2_0 |

None of them is the uber shader. No `#if` / `#ifdef` source for the uber material exists anywhere on disk; the
`gbUber...` strings in the executable are parameter names it looks up in materials, not preprocessor symbols.

### 3.3 The compiler DLLs
- `D3DCompiler_41.dll` is not imported by `Rally.exe` and its name does not occur in it. Its name occurs in
  `d3dx10_41.dll` and `D3DX11_41.dll`, which `Rally.exe` does not import either. `D3DX9_41.dll` (which the game does
  import) does not name it. VERIFIED (PE + strings). So the DLL is shipped but unused; the run-time compiling that does
  happen (3.2) is done inside `d3dx9_41.dll`.
- The executable imports from Direct3D only `d3d9.dll!Direct3DCreate9` and 21 functions of `d3dx9_41.dll` (maths,
  `D3DXCompileShader`, `D3DXSaveSurfaceToFileA`). No effect framework (`D3DXCreateEffect`) is used. VERIFIED (PE).

## 4. From material to shader
### 4.1 Layout of an effect chunk (kind 3) - VERIFIED (file; the parser reads all 67 effects of the four libraries)
| Offset | Content |
|---|---|
| +00 | u16 technique count, u16 shader record count |
| +04 | u32 parameter count |
| +08 | pointer to the technique array, 24 bytes each: `{ptr name, ptr VS record, ptr PS record, u32 flags, 0, ptr}` |
| +0C | pointer to the parameter name list (pointers to strings) |
| +10 | pointer to the shader record array, 20 bytes each: `{ptr bytecode, ptr entry name, u32 n, ptr map, 0}` |
| +14 | 0 on disk; at run time the engine stores a technique pointer here (code 0x59278F, 0x505E4E) |
| +18 | pointer to the effect name (`ubershadergame.fx` at chunk offset 0xACB0 in library 3) |

- `map` = n entries `{u16 register, u16 count, u32 parameter index}`: which constant or sampler register receives which
  named parameter. The engine binds by this table, not by the bytecode's own `CTAB`.
- Shader record + 0x10 is 0 on disk and holds the created `IDirect3DVertexShader9*` / `IDirect3DPixelShader9*` at run
  time (section 6.1).
- Technique flags look like the vertex inputs the technique needs (0x47 plain, 0x57 with vertex colour, 0x4000 instanced,
  0x8000 skinned). LIKELY.

### 4.2 The uber material: a bit mask selects one precompiled technique (VERIFIED, code)
- 0x4FB1D0 walks the material's parameter records (`u16` count at material +8, 16-byte records from +0xC: value pointer or
  texture reference, then name pointer) and builds a mask. A switch counts as on when its cell holds 1 or 0x74.

| Switch | Bit | Token in technique names | | Switch | Bit | Token |
|---|---|---|---|---|---|---|
| gbUberLITE | 0x0002 | `L` | | gbUberDIFFM | 0x0200 | `Td` |
| gbUberPIXL | 0x0004 | `Lp` | | gbUberNORM | 0x0400 | `Tn` |
| gbUberSPEC | 0x0008 | `Ls` | | gbUberLMAP | 0x0800 | `Tl` |
| gbUberVCOL | 0x0010 | `V` | | gbUberSPECM | 0x1000 | `Ts` |
| gbUberTWOS | 0x0020 | `2` | | gbUberREFL | 0x2000 | `Le` |
| gbUberSDRECV | 0x0040 | `Sd` | | gbUberGLITTER | 0x8000 | `Lg` |
| gbUberSSRECV | 0x0080 | `Ss` | | (instanced / dissolve / skinned) | 0x0001 / 0x0100 / 0x4000 | `I` / `D` / `G` |

  (name table 0x6A49B8, token table 0x6A4A10). ABLEND, ABLENDAdd, ATEST and DSIDE go to render-state flags in a separate
  word (bits 4, 0x20, 2, 0x10), not to the mask.
- Rules applied to the mask, in the code's order: dynamic shadow bit dropped when shadows are off (`[0x7EDD34]`,
  `[0x89A008]`); all of PIXL, SPEC, NORM, SPECM, REFL, GLITTER dropped when `[0x89A01C] == 0`; SPEC dropped without the
  specular constants; PIXL / SPEC / NORM / SPECM dropped without LITE; NORM and SPEC dropped without PIXL; SPECM dropped
  without SPEC; DIFFM, NORM, SPECM, LMAP dropped when the matching texture reference is 0 (message "Uber: A texture (%x)
  was specified but removed because it did not exist ...").
- 0x4FBE30 then searches a table in the uber effect object (entries of 0x28 bytes from object +0x320, count at +0xDDE0)
  for the entry with that mask and stores its index in the material (+0xA, u16). No match: message "WARNING: Ubershader
  did not support the combination of bools for the material (%x) -- fell back ..." and a default index.
- The table is made by PARSING the technique names of the library (0x4FAC70 reads two-letter tokens against the table at
  0x6A4A10). So the set of permutations is whatever the library chunk contains: 1229 techniques named
  `T[_I|_G][_L<p><s><e><g>][_T<d><n><s><l>][_V][_2][_S<d><s>][_D]`, plus `T_Z_*` (depth pre-pass) and `T_Show*` (debug).
- So: neither run-time compilation per combination nor one branching shader, but a fixed set of precompiled permutations.
  Several techniques share one shader record (a pixel shader record is shared by 1 to 7 techniques, typically the plain,
  instanced and vertex-colour variants of one mask).

### 4.3 Who uses the uber effect, and what tells two draws apart
- Uber materials occur in the six tracks (scenery, game objects, procedural objects), `granny\`, `osd\` and `Particles\`
  files: 3,916 materials in 35 of SEGA's files, 110 distinct effective masks. The cars use the separate `sr_car_*.fx`
  effects, terrain `3wayblend.fx`, water `water.fx`, the road `track.fx` / `trackmultiblend.fx`. VERIFIED (count, file).
- At shader level two uber draws differ by (a) the technique, i.e. which VS and PS record, chosen by the mask; (b) the
  per-material constants (`gf3AmbientCol` c0, `gf3DirCol` c1, `gfSpecColAndPower` c2, `gfBumpScale` c3, `gf3ReflCol` c10)
  and textures (diffuse s0, normal s1, specular s2, light map s3, shadow s4, reflection cube s10); (c) per-object
  constants (world matrix, tint). Fog, exposure, light direction, view position and shadow parameters are global.
  VERIFIED (shader constant maps).

## 5. The wall path: `T_Lpse_Tdnsl` today, and what its shaders receive
Imported walls are clones of a Stadium wall material with LITE PIXL SPEC DIFFM NORM LMAP SPECM REFL: mask 0x3E0E. In the
installed Mountain (`Main_release\track1\Desert4`) 549 of 646 uber materials have it. VERIFIED (count).

| | Technique `T_Lpse_Tdnsl` (#1203, record at chunk offset 0x70E4) | Unused twin `T_Lpse_Tdnl` (#1177, record at 0x6E74) |
|---|---|---|
| Vertex shader | record #303 at 0x8BA4, bytecode at 0x6FF04, 1744 bytes, vs_3_0, about 67 instruction slots | the same record #303 |
| Pixel shader | record #717 at 0xABFC, bytecode at 0x1122B8, 1360 bytes, ps_3_0, about 50 slots (5 texture, 45 arithmetic) | record #708 at 0xAB48, bytecode at 0x10E420, 1284 bytes, ps_3_0, about 48 slots (4 texture, 44 arithmetic) |
| PS constants | c0 c1 c2 c3 c4 c10 c31 + one literal (c5) | the same |
| PS samplers | s0 diffuse, s1 normal, s2 specular, s3 light map, s10 reflection cube | s0, s1, s3, s10 |
| PS record shared with | `T_I_Lpse_Tdnsl`, `T_Lpse_Tdnsl_V`, `T_I_Lpse_Tdnsl_V` | `T_I_Lpse_Tdnl`, `T_Lpse_Tdnl_V`, `T_I_Lpse_Tdnl_V` |
| Materials that select it | 18 in SEGA's files (Alpine4 10, Stadium4 4, Lakeside4 3, Canyon4 1), 131 in the Revo conversions, 549 imported walls | none anywhere |

Limits of the shader model against use: ps_3_0 guarantees 512 instruction slots, 224 float constants, 16 samplers and 10
interpolated inputs; the wall shader uses about 50, 8, 5 and 8. vs_3_0: 512 slots and 256 constants against 67 and 16.
The room is not a constraint.

What the vertex shader does (VERIFIED, shader #303 and its lighter sibling #490):
- Inputs: POSITION (xyz; w is used twice: uv0 is multiplied by it, and its sign flips the bitangent), NORMAL, BINORMAL
  (this is the mesh's "tangent" field), TEXCOORD (xy = uv0, zw = uv1).
- The bitangent is built as `cross(normal, tangent) x sign(position.w)`. This answers the open point of 16 section 3.5
  ("the handedness the engine gives the bitangent was not established").
- It moves the light direction and the view direction into tangent space per vertex, e.g. for the view vector:
  `dp3 r4.x, v2, r5` / `dp3 r4.y, r3, r5` / `dp3 r4.z, v1, r5`, then normalises and writes it to TEXCOORD2.
- Outputs: COLOR0 (x ambient weight, y fog amount, w sun weight), COLOR1 (tint and alpha), TEXCOORD0 (uv0 with the scroll
  offset in xy, uv1 in zw), TEXCOORD1 (light direction, tangent space), TEXCOORD2 (view direction, tangent space,
  normalised; w = a distance fade for the reflection), TEXCOORD5 / 6 / 7 (tangent, bitangent, normal, used to turn the
  reflection vector for the cube map), TEXCOORD8 (world x, z scaled by `gfLightmapOffsetAndScale`, not read by this PS).

What the pixel shader does (VERIFIED, shader #717 / #708 / #584):
- Lighting is done in tangent space: `texld_pp r2, v2, s1` then `add_pp r2.xyz, r2, c5.x` (minus 0.5), xy times
  `gfBumpScale`, normalise, N.L against TEXCOORD1, a half vector from TEXCOORD1 + TEXCOORD2 for the specular power.
- Only `.xyz` of the normal map is read. Its ALPHA channel is unused in all three shaders and can carry a height.
- The diffuse map's alpha is used (output alpha). The specular map's rgb scales the highlight and its alpha scales the
  reflection (#717). The light map is read with uv1 and multiplies the lit diffuse colour; the product is doubled before
  fog and the exposure constant c31.x.
- So everything parallax mapping needs is already at the pixel: the view direction in tangent space (TEXCOORD2), uv0, and
  a free channel in a texture that is already bound. The vertex shader needs no change.

## 6. Replacing a shader without touching a file
### 6.1 How the engine creates and binds shaders (VERIFIED, code)
- Every kind 3 chunk that is loaded goes through 0x58F9A0 (registered as the kind 3 handler at 0x597F0F). It looks the
  effect name up (0x5921F0; 0x592060 first renames `UberShaderMax.fx` to `UberShaderGame.fx`) in a registry of 8-byte
  entries at 0x9F1080 `{effect object, name pointer}`, count at `[0x9F1280]`. Known name: nothing more happens (this is
  what makes a track's stub resolve to the library). Unknown name: 0x592610 instantiates the chunk and 0x593000 registers
  it; if the libraries are already loaded it logs "Effects: WARNING! ShaderLib was loaded but the shader %s is being
  instantiated after -- could lead to problems especially on level restart".
- 0x592610 loops over the techniques and calls `IDirect3DDevice9::CreatePixelShader` (0x5926A0, vtable +0x1A8) and
  `CreateVertexShader` (0x592709, vtable +0x16C) on the record's bytecode pointer, once per distinct bytecode, and stores
  the result in the shader record: `mov dword ptr [eax + 0x10], ecx` (PS, 0x592766) and `[edx + 0x10]` (VS, 0x592760).
  Each created shader is also put on a resource list of its own (tag 0x70000000 / 0x80000000), LIKELY what releases them.
  The only other creation sites are 0x58E792 / 0x590572 (not examined) and the nine utility shaders of 3.2.
- Binding (0x402360, and inlined in the scenery draw loop at 0x505E4E): technique -> `[technique + 8]` (PS record) ->
  `[record + 0x10]`; compared with the last pointer set (`[0x80F648]`, VS `[0x80F644]`), and
  `IDirect3DDevice9::SetPixelShader` (vtable +0x1AC) is called when it differs. The pointer is re-read from the record on
  every bind; no second copy was found on this path.
- The stored name pointer of the registry points INTO the chunk (it is `[chunk + 0x18]`), so at run time
  `chunk base = [0x9F1084 + 8 x i] - 0xACB0` for the entry whose name is `ubershadergame.fx`, and the effect object holds
  the chunk pointer at +0x14 (seen in the draw loop, `[0x9C1044]`). LIKELY (derived from the code, not read live).
  Checks that confirm a base: `u32[base] == 0x02D604CD` (1229 techniques, 726 records: library 3),
  `[base + 0x70E4 + 8] == base + 0xABFC`, `[base + 0xABFC] == base + 0x1122B8`, `u32[base + 0x1122B8] == 0xFFFF0300`.

### 6.2 Routes
| Route | What it needs | Located? | Status |
|---|---|---|---|
| (a) patch HLSL source before it is compiled | source of the wall shader in memory | there is none: only the nine utility shaders of 3.2 are compiled from text | NOT APPLICABLE to the uber shader. Side benefit: `D3DXCompileShader` is in the IAT (0x6743D0), so injected code could compile text inside the game. LIKELY usable, untested |
| (b) patch the bytecode in memory before `CreatePixelShader` | be in the process before the library is loaded, or a hook at 0x592699 | bytecode at chunk offset 0x10E420 / 0x1122B8; call at 0x5926A0 | NOT PROVEN: the launcher patches at least 20 s after start-up, long after 0x5922B0 has loaded the libraries; patching earlier meets TeknoParrot's start-up checks (20, section 1). Not needed |
| (c) a wrapper `d3d9.dll` beside the exe | intercept `CreatePixelShader`, recognise the shader by a hash of its bytecode | the exe imports `d3d9.dll!Direct3DCreate9` by name, so a local `d3d9.dll` would be loaded | ADDS A FILE to the game folder, against the project's rule. No `d3d9.dll` is in the folder today. Whether TeknoParrot puts its own layer on Direct3D is UNKNOWN (it forces 3840 x 2160 while `config.ini` says 1920 x 1080, so it intervenes somewhere). Not recommended |
| (d) create a NEW pixel shader in the running game and store its pointer in the record | code on the render thread with the device; the bytecode; the record address | all located: device `[0x7ED10C]`, `CreatePixelShader` = vtable +0x1A8, record address from 6.1, the per-frame hook 0x591C4D of the launcher's block already runs injected code on the render thread and already calls into D3DX (20, section 5) | RECOMMENDED. Every piece is located; the pointer write is the one untested step |
| (d') swap in the pointer of ANOTHER existing shader | one 4-byte write by the launcher, no injected code | located | the first experiment (section 8) |
| (e) ship an effect of our own inside the imported track's file (a kind 3 chunk with a new name and bytecode, as `oildrummodel_data.sbf` does) | the non-uber material format, how such a material gets its global constants, whether the scenery tree draws it | handler located (0x58F9A0 instantiates unknown names) | UNKNOWN / more reverse engineering; the engine itself warns about effects instantiated after the libraries. Needs no memory patch at all, which is its attraction |

Notes on (d):
- The bytecode can be compiled by the launcher, outside the game, with `D3DCompile` of the system `d3dcompiler_47.dll`
  (target `ps_3_0`). VERIFIED here: a probe shader written for this purpose, with the same inputs, samplers and constant
  registers as record #708 plus the texture shift, compiles to 1048 bytes, about 36 slots (4 texture reads); a 16-step
  ray-marched variant to 1296 bytes, about 62 slots. Nothing has to be installed.
- If the new shader keeps the registers of the record it replaces, the record's map needs no change. `gf3ReflCol` (c10,
  three floats per material, material +0x644 in the 1848-byte layout) is a ready per-material channel for the parallax
  scale along u, along v and a bias; the reflection slot (s10, material +0x27C) could carry a separate height texture.
- Isolation: put the imported walls on a mask nothing else uses. `T_Lpse_Tdnl` (0x2E0E = today's wall mask with SPECM
  off, material cell +0x5B4 = 0) and its shadow variants 0x2E4E / 0x2E8E / 0x2ECE are selected by 0 materials in SEGA's
  files, 0 in the installed added tracks and 0 in the 24 Revo conversions (effective masks, rules of 4.2 applied; 18,428
  uber materials counted in all: 3,916 + 2,596 + 11,916). Its PS record #708 is shared only with its own instanced and vertex-colour variants,
  which are just as unused. Its VS record #303 is shared with techniques SEGA does use and is left alone.
  A second safeguard is available: the launcher already applies per-track values only while an imported track is chosen.

## 7. Risks and unknowns
Only a running game can settle these:
1. That a pointer written to record + 0x10 is honoured, survives a race restart and a track change, and that nothing else
   (a second cache, TeknoParrot, a device reset) puts the old one back. Biggest unknown; experiment of section 8.
2. That mask 0x2E0E resolves to `T_Lpse_Tdnl` and not to the fallback (the name is in the library and the mechanism is the
   one every other mask uses; LIKELY).
3. Which library is loaded on the cabinet (2 or 3). Library 2 has other offsets and no per-pixel permutations at all.
4. Whether the registry name pointer is the chunk's own string (6.1).
5. Sign conventions on screen: which way +v of the texture runs against the bitangent; settled by two scale constants.
6. Cost at 3840 x 2160 with multisampling of a ray-marched variant (the simple shift costs one texture read).

Known without running, and they shape the work:
- The importer's walls do not have true normals and tangents: the normal is chosen to give a wanted brightness (16,
  section 3.1) and the tangent is turned for the relief (16, section 3.5). Parallax needs the real surface basis, or the
  shift goes the wrong way. With a pixel shader of our own the brightness no longer has to come from N.L (the light map
  and a constant can carry it), so walls can be given true normals and tangents; this is a change in the importer, not in
  the game.
- Parallax needs a height per texel (normal map alpha, DXT5). The only source so far is "darker paint = further back"
  (`bump1995.py`), which is wrong for dark paint.
- A shift cannot move the silhouette or the edge of a polygon; near tile borders it reads outside the tile (clamp or
  wrap). The effect is a recessed-window look inside a flat wall, not geometry.
- The view vector is normalised per vertex and interpolated; on very large polygons seen from close by this bends the
  shift slightly. Renormalising in the pixel shader removes most of it.
- The depth pre-pass and shadow-cast techniques are separate shaders and stay as they are; fine for opaque walls.

## 8. Smallest first experiment (proposed, not run)
Purpose: prove that the shader a material draws with can be changed from the launcher, in memory, and put back.
No rebuild, no injected code, one 4-byte write. While it is on, it also changes SEGA's own 18 materials of this mask.
1. With a race on Mountain running, find `i < [0x9F1280]` whose string at `[0x9F1084 + 8 x i]` is `ubershadergame.fx`;
   `base = that pointer - 0xACB0`. Confirm with the four checks of 6.1.
2. Read `A = [base + 0xABFC + 0x10]` (pixel shader of `T_Lpse_Tdnsl`, record #717) and
   `B = [base + 0x8DFC + 0x10]` (pixel shader of `T_Lps`, record #333: lit, no texture, 628 bytes; its inputs COLOR0,
   COLOR1, TEXCOORD1, TEXCOORD2 are all written by vertex shader #303). Both must be non-zero.
3. Write `B` to `base + 0xABFC + 0x10`. Expected: every imported wall loses its texture and shows as a plain lit
   surface; road, sky, cars and terrain unchanged. Write `A` back: the textures return.
Second step (isolation): rebuild the track with SPECM off on the wall materials and do the same on record #708
(`base + 0xAB48 + 0x10`); a SEGA track driven afterwards must look untouched. Third step: the launcher's block creates a
shader from compiled bytecode and stores that pointer.

## 9. Open questions
- 0x58E792 / 0x590572: the other `CreatePixelShader` / `CreateVertexShader` sites (which objects they serve).
- Which `config.ini` key writes `[0x89A01C]`, and what `[0xA3398C]` is.
- Layout of the uber effect object (mask table +0x320, 0x28 bytes per entry) beyond the mask word.
- The non-uber material format and its constant binding (route e).
- What the unused `shaderlib_uber_data.sbf` (version 5 container) is.

## 10. POM continuation, 2026-10-19 — offline candidates, not installed

The investigation was resumed at the owner's request for rocks, roads and facades. Re-read the current local library-3 file: 1229 techniques / 726 records; `T_Lpse_Tdnl` remains at technique +0x6e74, VS +0x8ba4 and PS +0xab48. Its shadow variants have separate VS/PS records. These offsets and bindings are file-verified; runtime swapping, current material isolation and performance remain untested. The old TeknoParrot timing constraints above are historical: the standalone runtime now observes D3D9 device creation and already has a render-thread capture hook. No new proxy/watchdog is needed to investigate this route.

The retained prototype/report is [work/research/pom-20261019/README.md](../../work/research/pom-20261019/README.md); generated maps and the offline comparison viewer are under `scratchpad/pom-20261019/`. No installed asset or runtime was changed, and no game was started.

### Verified offline results

- 101 opaque source candidates, 44 shared geometry heads: 23 rock, 6 asphalt, 5 cobbles, 3 dirt, 1 stone wall and 63 facade. Tone siblings share height/normal pixels. Cutouts and other classes are skipped.
- Paired HLSL compiles with D3DCompiler_47 to vs_3_0 (63 static slots) and ps_3_0 (152 static slots for bounded 8/16/24/32-step POM; 90 for normal-only). Same static count does not imply same runtime cost. Register bindings fit the existing per-record maps.
- The paired VS sends world position/view/light to a PS that reconstructs a geometric basis from derivatives, while retaining the brightness-rule lighting inputs. This avoids relying on fake lighting normals for view displacement. **Clone the isolated VS record; never overwrite shared #303**, which other wall techniques use. This paired route is compiled, not in-game verified.
- Existing importer DXT5 encoding uses binary cutout alpha. It cannot preserve height in normal-map alpha. The isolated `encode_normal_height.py` creates continuous BC3 alpha, filters normal RGB independently of height, renormalizes normal mips, and avoids colour gain/gamma. Full mip dimensions are rounded up to powers of two to retain the SR3 uploader compatibility fix.
- Independent DDS decoding passed for all 44 heads. A 256-level alpha-ramp test survives (max error <=1), constant-alpha small mip cases are exact, and all mip sizes satisfy standard plus engine block formulas. Worst image height RMSE is 0.899/255; worst per-image 99th-percentile normal angular error is 3.032 degrees. Source colour hashes remain unchanged.

### Visual limits and integration gates

Rock candidates look plausible; asphalt is deliberately near-flat so paint/skid marks do not become deep channels. **Facade inference is not ready to install.** Dark-region heuristics produce inconsistent window/grille treatment, miss dormers and can confuse paint/shadows with depth. Facades need authored masks/heights or semantic correction on the geometry head, then reuse that map for colour children. POM does not change silhouettes or collision, and it does not replace R4 rounding.

The 44 exact unique DDS payloads total **31.7565 MiB**. Current installed slot SBF raw declarations total **287.1203 MiB**; adding source candidates gives **318.8768 MiB** under the 384 MiB track heap, leaving a theoretical **65.1232 MiB**. This is not measured peak headroom: derived/composed facade maps, alignment, metadata, other allocations and GPU copies are excluded. **Source map counts are not runtime coverage.** Follow composed facade recipes, crop/flip transforms, material clones and canonical texture aliases before claiming all selected in-game surfaces have relief.

Before enabling anything: recensus effective masks; validate private shader-record ownership/restoration and device resets; check UV handedness/normal-Y with an asymmetric test; preserve accepted fog/tint/exposure/lightmaps; measure actual frame cost; enforce normal-map linear sampling; and implement the road's `_Sd`/`_Ss`/`_Sds` shadow variants before touching road draws. The plain prototype does not yet preserve those shadow receivers. Next candidate should cover one rock and one authored facade in an opt-in staged build, not the entire installed course.


## 11. Opt-in POM runtime candidate (2026-10-19)

Implementation now lives in `source/standalone/pom.c`, `shaders/pom*.hlsl`,
`compile_pom.py`, and `stage_pom.py`; see `source/standalone/POM.md` for the contract.
It is default OFF (`SR3LAB_POM=1` opts in), patches seven known slots in the original driver vtable and
exact SHA-256 shader-pair identity, and restores the game VS/PS and normal sampler
states after each qualifying draw. No shared effect records are edited. Thus the
old private-engine-record proposal is not used in this candidate.

Current Mountain rocks ALSO receive both shadows. The candidate therefore implements
`T_Lpse_Tdnl_Sds`, preserving the inspected variance/dynamic and static-shadow
coordinates/equations, anchored lightmaps, fog/tint/exposure. It remains matte.
Only explicitly marked rock materials are staged; roads and facades stay unmarked.
The other shadow-selection variants fail closed pending their own implementations.

The first local stage is `scratchpad/pom-implementation-20261019`: 40 material
instances in the x0000/y0000 rock family, one continuous BC3 normal/height texture
1024x1024 with 11 mips, 0.008 UV depth. Unpacked track total 287.57 -> 288.91 MiB.
Chunk-level verification preserves all geometry, original textures, lightmaps and
shadow switches. No installation or game launch was performed.

Mocked x86/x64 D3D tests cover draw/state restoration, exact identity, unsupported
caps, malformed map rejection, recording state blocks, setup/draw/restore failures,
reset/recreation and COM cleanup. Shader compilation is verified; live GPU visual
quality, UV handedness, actual shadow equivalence and frame cost remain UNVERIFIED.
Do not describe the prototype as game-tested or extend it to automatic facade maps.

CPU preference: “all cores” always means all logical processors minus one (31 on
Bruno's 13900K). This isolated build used eight workers while he tested the game.


### POM first test crash and real-driver regression (2026-10-19)

The first game test exited 0xC0000005 immediately after device creation. The launcher
restored the accepted runtime and track. A hidden 64x64 real-D3D9 harness reproduced
the failure at Clear: cloning only the public device vtable discarded private
driver entries. The fix preserves the native table and replaces only seven known
slots, with other-device calls passed through. A second access violation during
teardown came from inspecting slots after final Release freed that table; hooks
are now restored before Release and reinstalled only if the device remains alive.

Verification: real GPU shader creation, three marked POM draws with original shader
restoration, non-final Release, Reset/recreation, and final cleanup all passed.
Full runtime regression suite passed. Actual game appearance, lighting and frame
cost still require the user's test. The optional harness is
`source/standalone/test_pom_device.c`; local original shader bytecode fixtures stay
out of the repository. Evidence: `scratchpad/pom-implementation-20261019/`
`test_pom_device-fixed.log`. Normal gameplay remains on the accepted baseline.


### Stage-loading packaging correction (2026-10-19)

The next user test reached stage loading, then exited 0xC0000005 without a POM
activation log. Static inspection found the staging script appended the normal
texture after the track root: the final chunk became kind 4 (0xc1b00010), replacing
the loader's expected last-chunk root kind 12 (0x65352b89), and 40 material refs
pointed forward. This violates the documented SR3 loader contract (KB01/08).

`stage_pom.py` now inserts the texture before its first material user, preserves
the original root and validates local dependency order again after readback.
`test_stage_pom.py` checks valid insertion and duplicate/unused/forward-reference
rejection. The rebuilt `track-ordered` candidate has the correct root and zero
forward refs; every chunk payload, type, fixup and reference list is identical
to the failed candidate. Only order/alignment changed. Test launcher preflight
passes and normal installed baseline hashes are unchanged. The launcher now
selects `track-ordered`; the previous failed candidate is retained for evidence.
This corrects a demonstrated packaging defect; live loading confirmation remains
pending. Crash itself had no dump, so no fault instruction was recovered.


### First loaded POM trial: exit freeze unresolved

User confirmed stage loads, but found shallow relief, washed contrast in direct light, and a freeze after finish/time-out. Rally PID 5472 was terminated on request; launcher restored both baseline files. Evidence is work/pom-tests/20261019-105957-0555c9. No marked-draw activation was logged, so actual POM activation is unconfirmed. Diagnostic runtime adds counts to the existing five-second log. TEST-POM-EXIT.bat starts a one-shot read-only state probe; after race-end it briefly samples/resumes threads three times and exits. Watchdog remains OFF. Sampler was verified on a disposable hidden x86 process. This prepares diagnosis, not a claimed freeze fix. User authorized broader non-flat coverage and stronger depth/contrast only after the freeze is resolved.


### State-block hook loss reproduced and repaired (2026-10-19)

Owner reported no crash on the next run (work/pom-tests/20261019-111920-6f2bda).
There were no exit-probe files in that run. Normal files restored. Counters showed
zero marked/replaced draws and froze at 8468 while the game continued. Treat the
previous end-of-race freeze as intermittent/unresolved, not fixed by logging.

A hidden real-D3D9 reproduction established that BeginStateBlock rewrites the
driver table in place, replacing the POM draw and EndStateBlock hooks. EndStateBlock
did not reinstall them. The old test covered state blocks only with mocks.
Now both transitions temporarily restore native slots, call the native transition,
capture the resulting native method table and wrap it again. Recording still skips
POM substitution. Real-driver checks pass five marked draws across Begin/End,
CreateStateBlock/Capture/Apply, non-final Release, Reset/recreation and final release.
Full runtime suite passes. Evidence: stateblock-before.log and
test_pom_device-stateblock-fixed.log in the local candidate folder.

This fixes a proven activation/lifecycle bug, not a proven cause of the prior freeze.
Actual in-game POM activation and another race-end transition still need checking.
Broader material rollout and depth/contrast tuning remain authorized but deferred
until the effect really activates and race-exit stability can be assessed.


## Mountain-wide installation — 2026-10-19

After Bruno approved the live rock-family POM test, relief was installed for normal
PLAY.bat launches. The exact accepted runtime is reused (SHA256
`189cc686a02100d40f341f1cbb2aadca94f5c3a2899ef646879bf7b313db5258`); no further
shader or hook changes were needed. The last live family test recorded 386,272
marked/replaced draws, zero rejected draws, setup failures or restoration failures.
This establishes the family runtime, not a completed stage-wide gameplay test.

Coverage: **411 material instances / 184 diffuse mappings / 143 deduplicated normal-height maps**:
119 rock, 201 facade, 36 roof, 19 grass, 13 cobbles, 8 asphalt, 8 dirt,
2 stone wall and 5 water. Opaque ivy/rock composites are included. Flat signs,
checkpoint/finish banners, sky, vegetation cards and alpha-cutout silhouettes are
excluded. Cutout castle silhouettes remain on their original material path; the
opaque masonry is included. Do not describe this as support for every transparent
surface or every SR3 material technique.

`source/standalone/stage_pom_wide.py` stages without installing. It uses the original
facade triangle UV recipes and overlay transforms to compose **scalar heights**,
then computes normals after composition. This matters for flipped facades: simply
flipping normal-map pixels would leave the tangent direction wrong. Palette siblings
share their chosen geometry head. Facade edges fade to height 1 (the reference
surface), making their parallax displacement zero at the border. Asphalt relief is
very shallow and does not turn skid-mark brightness into potholes. The accepted
simple rock-family DDS payload is reused byte-for-byte.

`pom_maps.py` supplies conservative material-dependent height inference;
`pom_dds.py` encodes continuous height alpha with normal-aware mipmaps. Height is
linear data. The old binary-cutout alpha encoder is unsuitable. New relief maps
are at most 512 pixels per side except the previously accepted 1024-square rock
map. This reduces map memory without touching the installed albedo resolution.
Maps alone add 36.86 MiB; the seven unpacked track SBFs grow from 287.57 to
324.65 MiB, below the retained 384 MiB ceiling.

Verification: all staged chunks read back byte-identically; only normal references,
SPECM and the reserved relief marker changed in selected existing materials.
Original albedo, geometry, collision, RT lightmaps, shadow switches and all other
track files are unchanged. Each new map precedes its users; the original last-chunk
root is retained, with no local forward references. Contact sheets for all 184
mapped images were inspected for spatial alignment and gross relief errors.
The hidden real-D3D9 smoke test passed five marked draws, Begin/EndStateBlock,
Capture/Apply, non-final Release, Reset/recreation and final cleanup. Run this test
outside the restricted sandbox; inside it device creation can fail with
D3DERR_INVALIDCALL before testing POM.

`config/workspace.json` now has `pom: true`. `source/tools/workspace/play.ps1`
sets SR3LAB_POM only for its child launch and restores the prior process environment
in finally. No persistent Windows environment setting is changed. Watchdog remains
OFF and the accepted SRC helper is retained. The accepted file manifest tracks the
installed runtime and main SBF hashes; the normal launcher check passes without
starting the game.

Local stage, map review and complete coverage/exclusion manifest:
`scratchpad/pom-stagewide-20261019/`. Verified pre-install rollback is in
`work/pom-backups/mountain-stagewide-20261019-114637/restore.ps1`; it refuses to
replace files changed after this installation and requires the game to be closed.
The install is backed up; a complete race with the expanded coverage still needs
Bruno's gameplay check. Refreshing source HD art requires rebuilding its relief maps
as well: the source hash guards deliberately reject stale height research assets.


## Live relief controls and visual correction — 2026-10-19

Bruno's screenshot SR3_20261019_120931.png showed apparently flat facades.
Millions of replaced draws with no failures established activation only; they
were not evidence of convincing relief. The original implementation had a
60-world-unit specular-distance fade reused for POM and a grazing fade starting
at cosine 0.28. Both could suppress the effect where it should be inspected.

Current runtime uses projected UV footprint fading, a much narrower extreme-
grazing fade (0.012–0.045), 24–64 ray layers with five binary refinement steps,
and bounded height-field self-shadow on direct light only. Albedo sampler 0
now explicitly uses up to 8x anisotropic minification, linear magnification and
linear mip filtering (capability fallback to linear). Sampler 1 stays linear,
non-sRGB. All modified sampler states, shaders and c30 controls are restored
per draw; restore errors disable relief until reset. OFF uses the same paired
shader and filtering with displacement, normal perturbation and relief shadow
zeroed, so filtering differences cannot be mistaken for depth.

Controls while the game is focused:
- Backtick (` / VK_OEM_3): ON/OFF, ignores keyboard auto-repeat.
- Plus/equal or numpad Add: increase depth by 0.1x.
- Minus or numpad Subtract: decrease depth by 0.1x.
- Range 0.0–4.0x; starts ON at 1.0x on launch. Session-only; reset/Alt-Tab retains
  the choice. High settings can stretch/disocclude window artwork; 1.0x is the
  tested starting point, not a claim that all higher values look good.

Window input only changes atomic integers. No input polling helper or watchdog
was added. The render thread draws a cached Segoe UI label into the backbuffer
through the existing frame callback. In-game verification exposed that SR3 can
leave an offscreen post-process render target bound: drawing onto that target
made the label invisible despite a passing simple GPU fixture. The HUD now
explicitly binds the backbuffer, removes the depth target, and restores target,
depth surface, viewport and complete graphics state afterward. No retained state
block; HUD texture is released on resource reset and device cleanup. Real-driver
regression now includes an offscreen target with pointer equality after HUD draw.

Height map provenance: the previous maps were filtered luminance heuristics;
facades detected coherent dark rectangles, missing many windows/arches. Purple
RGB encodes tangent-space surface normals for lighting, while grayscale scalar
height lives in continuous BC3 alpha. Neither is recovered true geometry.
`facade_relief.json` now defines visually authored source-space bounds for 182
window/door openings across 21 facade heads. `pom_maps.facade_height` makes
coherent beveled recesses and shallow jambs; local brightness contributes only
a small mullion correction. Roof/wall texture noise does not become facade depth.
Palette siblings reuse the head. The exact facade/crop/mirror recipes compose
scalar heights before normal generation. Default facade UV depth is 0.012;
other material depths and original accepted rock DDS remain unchanged. Natural
material heights still use band-limited luminance inference, not semantic
geometry; do not call those physically accurate depth reconstructions.

`stage_pom_wide.py --base-main <verified pre-POM main SBF> --fresh-facades`
rebuilds from the clean track payload rather than appending another map set to
an already modified SBF. Final coverage remains 411 materials / 184 mappings,
with 138 deduplicated maps and 323.72 MiB unpacked seven-track total. No albedo,
geometry, collision, RT/lightmap, handling or other track files changed.

Validation: full runtime tests pass; real-D3D9 tests pass seven marked draws,
state-block recording/replay, HUD controls, offscreen target restoration,
non-final Release, Reset/recreation and final cleanup. All 182 authored opening
centers remain recessed (caught and repaired an accumulation error during staging).
Matched real-GPU renders of an actual facade at OFF/1.0x/2.5x show displacement,
with identical albedo/filtering/camera. Visual review reduced excessive mullion
height and refined ray intersections. This fixture is not a full-stage drive.
Live windowed launch verified backtick, keyboard increase, visible label and
normal exit of the first test. Final game left to Bruno at OFF 1.0x after user
input was detected; full race and final artistic acceptance remain pending.

Evidence: scratchpad/pom-live-relief-20261019/ (gpu-comparison.png, game-label.png,
gpu-lifecycle.log, render-checks.json, track-final/stage-report.json).
Verified pre-change backup: work/pom-backups/live-relief-20261019-124321/restore.ps1.
Older hard-coded linker-offset probes must NOT be used with this rebuilt runtime.
The new capture-game.py uses only the exported backbuffer API, no private offsets.


## Source-pixel facade masks and material tuning — 2026-10-19

Bruno accepted rock at 4.0x and facades at 1.0x, but rejected approximate
facade depth placement. `facade_semantics.py` replaces the old normalized
opening rectangles and whole-image luminance guesses with manually authored
source-pixel masks for all 21 HD heads. Doors, glass, shutters, blind panels,
arches, ledges and balcony rails use different heights. The rose-window
tracery is selected inside its explicitly reviewed ellipse; fine ironwork is
selected only inside reviewed rail regions, excluding broad dark doors.
Paint, lettering, stains and stone grain do not become facade recesses.

Palette children share the source head's geometry. Scalar height passes through
the installed facade/overlay crop and mirror recipes; normals are calculated
after composition. 117 texture mappings cover 201 facade materials. All 21
native-resolution source overlays and all 117 composed overlays were inspected.
Source coordinates are carefully authored, not a mathematical pixel-perfect
segmentation guarantee: small ornamental relief remains approximate, and BC3
compression/mips limit runtime precision. Final aesthetic acceptance needs a
gameplay check.

The runtime recognizes the reserved .008 UV rock profile and applies a 4x
material gain; other profiles start at 1x. Thus the accepted rock map remains
byte-identical and both its normal and parallax components receive the same
gain as the user's successful 4x test. Live +/- changes the global multiplier;
effective material gains are capped at 4x. HUD shows actual Rock / Facades
values. Backtick compares ON/OFF with identical albedo filtering.

Evidence: `scratchpad/pom-facade-semantic-20261019/review.html`,
`validation.json`, `gpu-lifecycle.log`, `track/stage-report.json`.
All 1,005 protected non-POM chunks remain byte-identical, including albedo,
geometry and lightmaps. Total track unpacked size 324.23 MiB; full-mip DXT5
normal/height payloads 36.44 MiB. Runtime/input/capture tests pass, including
draw-time gain checks and state restoration. Real GPU state blocks, offscreen
HUD, reset and final release pass. Blender's unwanted old geometry and stray
shadows are deferred and separately reminded; no geometry changed here.


### Shader creation churn correction - 2026-10-20

The live game rebuilt the POM shader pair roughly once per frame because its
ordinary non-final device Releases cleared the draw-hook cache. Reproducing
this in a one-pixel real-D3D9 fixture cost 9.40-9.62 ms per iteration; timing
isolated about 9 ms in CreateVertexShader/CreatePixelShader. Lowering depth
could not remove that CPU/driver cost.

The accepted fix uses native texture private data (D3DSPD_IUNKNOWN) to retain
the compiled pair with game-owned height textures. It does not retain those
textures or skip device Release cleanup. Private data releases its shader
references with the texture; an attach-generation tag prevents reuse across
attachments. GetPrivateData returns owned references for the draw cache.
No guessed device refcount threshold is used. The proposed threshold shortcut
was rejected and never executed. GPU shader bytecode remains byte-identical.

100 non-final Release/draw iterations now cost 0.37-0.46 ms each, with only
two shader creations total. Real device tests pass state-block recording,
full state capture/apply, offscreen HUD, reset/recreation and zero references
at final device destruction. Runtime regressions and launcher validation pass.
Full-game 60 FPS still needs the user's test. Approved YAML, track, albedo,
height/normal maps, RT lighting and normal display settings remain unchanged.
Evidence: scratchpad/pom-fixed-cost-20261020-165527/install-report.json and
scratchpad/pom-performance-20261020/cache_lifecycle_final/.


## Native-track hook overhead - 2026-10-20

After disabling the FPS overlay, vanilla-track logs still showed tens of thousands of device Releases per five-second interval with zero POM replacements. The hook transition previously changed page protection separately for each of seven slots (28 VirtualProtect calls per Release round trip). Batch by unique vtable page instead, restoring each page's original protection; restore native slots before Release and rehook only after a nonzero return, without guessed COM thresholds. On a real D3D9 device, 10,000 AddRef/Release pairs dropped from 201.747-203.363 ms to 46.969-47.506 ms (native 0.113-0.443 ms). Native regression and real-device state-block/reset/final-release tests passed. Runtime installed with initial gain 0.6 and no overlay/FPS sampling. This demonstrates reduced hook cost, not yet a confirmed in-game stutter fix. Missed Mountain checkpoint does not establish timer drift; timer and handling remain unchanged. Evidence: scratchpad/runtime-stutter-20261020/install-report.json.


## Native library integration and YAML — 2026-10-20 (current)

The runtime now links `pom_native.c`, not `pom.c`. POM installs no D3D draw,
state-block or Release hooks and owns no GPU shader objects. The native kind-3
loader creates and releases the records in `shaderlib3_uber_data.sbf`. All 726
original shader records are preserved; only `T_Lpse_Tdnl_Sds` selects the added
pair. The extra `url_pom_controls_v1.fx` effect holds 0.0–1.0 variants. At a frame
boundary, the existing capture callback selects native technique record pointers
only after a gain change or Reset. 0.0 selects the exact original VS and PS.
This still uses the standalone runtime's existing frame/control infrastructure;
it is not a claim that all game hooks have been removed.

`config/mountain-pom-depth.yaml` remains the settings source:

- `global_depth_initial` is read once on device creation, from the configured
  `patches.mod_folder`. Supported values are 0.0–1.0 in steps of 0.1.
- `live_tuner` controls +/- input. Current start is 0.6 and live tuning is on.
  Missing/invalid startup settings disable relief and log the error. No file
  access occurs in a draw or idle frame callback. Edits take effect on restart;
  this is not file hot reload.
- `families`, `excluded_variants`, height directory and normalization are consumed
  during map staging (`stage_pom_wide.py --tuning ...`). These values are baked
  into normal/height textures and material constants, not parsed per draw.
  Changing them requires map restaging and native integration. Merely changing
  an exclusion must not be presented as a live material update.
- `pom_native_config.py` checks the installed receipt against YAML before PLAY.
  Stale family settings or exceptions fail preflight with a restaging message.
  `integrate_pom_library.py` independently audits the YAML-staged material report,
  recipe-resolved exclusions, depth constants and normal/height payload hashes.
  Current audit: 38 families, 391 active materials, 16 excluded c1A6 materials.
  FPS overlay and measurement remain off; unsupported enable requests are rejected.

Native normal-map dimensions come from small uniform BC3 metadata textures in
the unused specular slot s2. Four endpoint bits encode width/height powers of two
without sensitivity to sRGB conversion. Existing albedo, heights, normals,
lightmaps, geometry, collision, timing and handling are unchanged by integration.

Rebuild sequence:
1. For family/exclusion changes, stage maps with `stage_pom_wide.py --tuning`
   from the verified clean RT base and matching texmap/review export.
2. Run `integrate_pom_library.py --source-library ORIGINAL.sbf --source-track
   YAML_STAGED.sbf --material-report STAGE_REPORT.json --out NEW_SCRATCHPAD`
   (optional `--tuning` / `--texmap`). Never use an already integrated library
   as the original input. Original bytecode identity and reserved IDs are checked.
3. Copy the generated `pom_native_layout.h` into source and rebuild the runtime.
   Deploy library, track, DLL and generated `pom-native-install.json` receipt
   together after backup; update accepted-baseline hashes.
4. Run `pom_native_config.py --workspace ROOT` and normal PLAY `-Check`.

Evidence is in `scratchpad/pom-native-library-20261020`: prior matched 4K real-GPU
comparisons of rock, facade, asphalt and fence produced zero pixel difference
from accepted POM at 0.6. Native library startup was observed with `applied=6`
and zero POM draw hooks before the user requested no further game launches.
Offline controls tests cover gain selection, original zero pair, Reset, idle,
YAML start values and invalid/missing YAML. A mocked registry is deliberately
allocated away from low-address loader/heap allocations in the test only.
Actual Mountain rendering and race performance await the user's test; these
checks do not prove timer, stutter, frame-rate or all-track behavior.

Pre-integration backup:
`work/pom-backups/before-native-library-20261020-192155`.


## Mountain relief page: automatic Apply — 2026-10-20

Run `RELIEF.bat` at the workspace root to open the local relief editor
(`http://127.0.0.1:8768/`). It displays installed YAML family gains, starting global
depth, the +/- toggle, and per-variant exclusion checkboxes. `Apply to game`
saves a staged YAML and automatically calls `stage_pom_wide.py` then
`integrate_pom_library.py` when material settings differ. Global-only changes
skip map rebuilding. No action launches the game. The old file page has an
editor link which transfers its notes/camera locally via a URL fragment.

`relief_apply.py` uses hash-pinned rebuild inputs in `work/pom-native-inputs`.
The clean RT base and the original shader library are separate from installed
assets, so repeated Apply never accumulates POM maps. The review-track snapshot
matches the export's original texture metadata and identity. Rebuilds run below
normal priority with bounded math-library threads. Native layout must match the
installed runtime header before deployment; family edits require no DLL rebuild.

Apply checks the YAML/receipt/baseline revision before and after building and
checks accepted game hashes. Invalid values, unknown variants and stale tabs
are rejected. A localhost-only server uses exact Host/Origin checks and a
per-session token for writes. It serves only its page, preview assets and API,
not arbitrary workspace files. A single Apply runs at a time.

Installation backs up every changed file under `work/pom-backups/page-apply-*`,
atomically replaces each file, checks its hash and restores the entire set on
failure. A journal blocks PLAY during commit or after an interrupted commit.
The game must be closed at preparation and commit, and is checked between file
replacements. This is not a cross-file OS transaction; a hard process/power
failure leaves the recovery journal and complete backup. Do not remove the
journal without restoring/validating that backup.

Validation: a real staged family-depth change rebuilt maps and native shaders
with 391 active and 16 excluded materials; a UI Apply with current approved
settings completed and saved a verified backup. Tests cover bad/stale payloads,
running-game refusal, successful deployment and injected mid-install failure
rollback. Preview rendering is approximate; gameplay/performance acceptance
remains with the user. Removing POM draw/Release hooks addresses measured hook
overhead but does not establish that all sources of stutter are gone.


## Native relief idle callback — 2026-10-20

The standalone frame hook now queues native relief-control work on startup,
Reset and +/- changes and retries until applied. Settled frames bypass the C
callback and floating-point save/restore; screenshots retain their own request
path. Global 0.6, all 38 YAML families, the 16 material exclusions and native
shader ownership are unchanged. Offline callback and native controls tests pass.
The same runtime update corrects the standalone two-physical-core allocation to
match TP's four separate P cores on this host. See [runtime findings](08_exe_loading.md).
No live stutter claim: the owner will test; no game launched during this update.
