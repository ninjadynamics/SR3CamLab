# 01 - SBF container

Tool: `work/scripts/sbfw.py` (`read_sbf`, `write_sbf`, `validate`). Older reader: `sbf3.py` (also big-endian PS3).

## File
| Offset | Type | Meaning | Confidence |
|---|---|---|---|
| 0 | char[4] `SBZ1` + u32 raw size + zlib stream | optional wrapper (Desert4 `gameobj_gfx_dis_data` is stored raw) | VERIFIED (all 36 files) |
| 0 | u32 = 4 | version | VERIFIED |
| 4..0x13 | 4 x u32 = 0 | unused in every track file | VERIFIED |
| 0x14 | u32 | chunk count | VERIFIED |
| 0x18 | count x {u32 id, u32 offset} | table, same order as the chunks in the file | VERIFIED |
| >= 0x1000 | chunks | first chunk never starts before 0x1000 | VERIFIED |
| end | 2048 zero bytes (2056 in the two game-object files) | tail | VERIFIED |

## Chunk
`kind, id, size, type, nfix, fix[nfix], nref, ref[nref], data[size]` (all u32).
- `type`: 0 except for kind 12, where it is a class hash (not found as a constant in the exe).
- `fix[]`: offsets in data of pointer fields; the stored value is an offset into the same data.
  A pointer slot may hold 0xFFFFFFFF (null marker; seen in kind 11 only).
- `ref[]`: offsets in data of fields holding the id of another chunk (same file, or another file of the same track:
  the pobj files reference materials/textures stored in master_gfx).
- ids are resource hashes, identical across platforms.

VERIFIED: `sbfw.write_raw(..., layout='keep')` reproduces the decompressed bytes of all 36 arcade track files.
The zlib stream itself is not reproducible with Python zlib levels 1-9 (irrelevant to the game).

## Kinds seen in track files
| Kind | Content |
|---|---|
| 1 | mesh (LOD headers 0x48, groups, vertices, u16 strips, model record with name + matrix + bbox) |
| 2 | material |
| 3 | shader stub |
| 4 | texture: 11 words + `DDS ` + 124-byte header + pixels |
| 5 | pointer-linked structure (TrackDeform, AI map, spline, cameras, boundary BSP, object lists...) |
| 7 | raw bytes: zlib stream (road heights) or Granny file (magic 29 DE 6C C0...) in gameobj_gfx_dis_data |
| 11 | scenery block tree (one per track) |
| 12 | small typed object; ties other chunks together by id; the last chunk of a file is its root |

## Alignment of chunk DATA (file offset modulo 16)
| Kind | Rule | Confidence |
|---|---|---|
| 5, 6, 11, 13 | 0 | VERIFIED on all files (and known to crash otherwise, see ps3-to-pc-conversion.md) |
| 4 | 4; in SEGA's files additionally data %4096 == 0xF54 so the pixels start on a 4096 boundary | VERIFIED in files; the 4096 part is not required (converted tracks without it load) |
| 7 | 8 for Granny files; the zlib blob in master_gfx sits at 0, 4 or 12 | VERIFIED in files |
| 1, 2, 3, 12 | 4-byte only | VERIFIED |

Padding goes before the chunk header. `write_raw(layout='auto')` applies these rules; `step1` of the ladder tests them.

## Texture header (kind 4), 11 words
`1, 0, width, height, 0, a, a, 1, b, 0, c` then `DDS `. Observed (a,b,c): DXT1 pages (3,3,1); DXT5 surface
textures 1024x1024 (1,3,4); small DXT5 (1,2,1). Authored textures keep a borrowed header and replace only the pixel
blocks (`tex_fill` in build_testtrack.py).

Sampler words (found 2026-10-07, replaces "meaning of a,b,c UNKNOWN"): the header from +0x14 on is the sampler set-up read
by 0x58DF40: `{addrU, addrV, addrW, filter (3 = min anisotropic / mag linear / mip linear, i.e. trilinear), f32 mip LOD
bias, u16 max anisotropy}`. VERIFIED (code). Read against the word list above, a = address mode U and V, b = filter, the
0 = LOD bias, c = max anisotropy (LIKELY correspondence: SEGA's road layer textures have max anisotropy 4, matching
c = 4 of the 1024x1024 surface textures). Which numeric value means wrap and which clamp is not written down in the
sources (UNKNOWN here; the importer sets clamp on axes a tile never repeats along, 23_texture_pipeline.md).
Seen in game: an authored road texture with max anisotropy 1 went soft a few metres ahead; a LOD bias of -12 forces mip
level 0 everywhere; a LOD bias of 2.0 with no anisotropy blurs the sea sheet towards the horizon (import_classic.py).

## Chunk order: no forward references (found in game, 2026-10-07)
A chunk may only reference chunks that come EARLIER in the same file. All six arcade tracks obey it: 0 forward references
among 50,952 id references of their master_gfx files (VERIFIED, measurement). The steps that put authored meshes on the
scenery tree did not (the kind 11 chunk stood before its meshes), and the first in-game run of step34 crashed in 0x5C1EB0
walking exactly that list (149 dangling entries; fault at 0x5C1ED6, first pointer unmapped). VERIFIED in game.
`reforder.py` reports and repairs built steps (`topo`: a stable dependency order, the root stays last);
`build_testtrack.write_track` calls it, so new builds are always ordered.

## In-game status of the writer (2026-10-06 / 07)
The writer and its layout rules ("our SBF writer + layout") are on the owner's list of things proven in game: a track
re-written with computed padding loads and races. VERIFIED in game.
