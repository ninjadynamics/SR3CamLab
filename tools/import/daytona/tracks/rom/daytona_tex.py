"""Daytona USA (original Model 2): texture RAM, palette, luma and colour tables rebuilt from the ROM files.

Where the data is (own findings, each read from the game's code; see docs/kb/daytona_usa_rom_data.md):
  texels    main data ROM, uncompressed 4 bit, one 1 MB "set" per course + one common set:
            0x200000 Beginner, 0x400000 Expert, 0x300000 Advanced (table at program 0x15A0, index = course id),
            0x500000 common (program 0x145C). The upload routine (program 0x146C) copies the first 0x60000 words of a
            set straight to texture RAM (course set -> RAM 0, common set -> RAM 1) and then spreads the last 0x20000
            words (the mip levels) over BOTH RAMs; `upload` below is that routine, instruction for instruction.
  palette   main data 0x84F4EC, 1007 entries of 15 bit (red low), copied to 0x01802000 (program 0x5C7C): one table
            for all courses. colour base n of a texture header = entry n.
  luma      main data 0x802FC4: count (66), then 128-byte tables (program 0x13F8). Table 0 = texel * 4.
  colorxlat computed by program 0xA74: value = (level * 12 * luma + 4448) >> 6, capped at 255; 0 when level * luma = 0.
  light     texture parameters (diffuse, ambient per attribute index) at main data 0x805120 (program 0x5958).

Texel addressing follows MAME model2rd.ipp get_texel.
"""
import numpy as np
from daytona_objs import region

SETS = {0: 0x200000, 1: 0x400000, 2: 0x300000, 3: 0x200000}
COMMON = 0x500000
PALETTE = 0x84F4EC
PALETTE_N = 1007
LUMA = 0x802FC4
TEXPARAM = 0x805120
MIPTAB = [0x200, 0x100, 0x80, 0x40, 0x20, 0x10, 8, 4, 2, 1]


def upload(ram, src, g9):
    """program 0x146C. ram = [RAM0, RAM1] (0x80000 16-bit words each); src = word index into main data; g9 = 0
    (course set) or -1 (common set)."""
    rom = region("main_data", "<u2")
    g5 = src
    dst = ram[0] if g9 == 0 else ram[1]
    dst[0:0x60000] = rom[g5:g5 + 0x60000]
    g5 += 0x60000
    p = 0x60000                      # r7 / r8: same word index in both RAMs
    g9 = ~g9
    r9 = 0; r4 = 128; r6 = r4
    while True:
        while True:
            r12 = 512; r10 = 1; r13 = g9; r11 = MIPTAB[1]
            while True:
                (ram[0] if r13 == 0 else ram[1])[p] = rom[g5]
                g5 += 1; p += 1
                if r9 != 0:
                    c = 1 < r11; r11 -= 1
                    if not c:
                        r10 += 1; r11 = MIPTAB[r10] if r10 < len(MIPTAB) else 0
                        if not (r10 <= r9): r11 <<= 1
                        r13 = ~r13
                c = 1 < r12; r12 -= 1
                if not c: break
            c = 1 < r6; r6 -= 1
            if not c: break
        if r4 != 1: r4 >>= 1
        r6 = r4
        c = 8 > r9; r9 += 1
        if not c: break
    return g5 - src


_sheets = {}


def sheets(course):
    """-> two uint8 arrays [1024 rows (y), 2048 columns (x)] of 4-bit texels: sheet 0 (course set), sheet 1 (common)."""
    if course in _sheets: return _sheets[course]
    ram = [np.zeros(0x80000, "<u2"), np.zeros(0x80000, "<u2")]
    upload(ram, SETS[course] // 2, 0)
    upload(ram, COMMON // 2, -1)
    out = []
    for r in ram:
        w = r.reshape(1024, 512)                   # word rows; one word = a 2 x 2 block of texels
        img = np.zeros((2048, 1024), np.uint8)     # as stored: 1024 wide, 2048 high
        img[0::2, 0::2] = (w >> 12) & 15
        img[0::2, 1::2] = (w >> 8) & 15
        img[1::2, 0::2] = (w >> 4) & 15
        img[1::2, 1::2] = w & 15
        out.append(np.concatenate([img[:1024], img[1024:]], axis=1))   # x >= 1024 lives at y + 1024
    _sheets[course] = out
    return out


def palette():
    """-> (PALETTE_N, 3) array of 5-bit levels (r, g, b)"""
    p = region("main_data", "<u2")[PALETTE // 2:PALETTE // 2 + PALETTE_N].astype(np.int32)
    return np.stack([p & 31, (p >> 5) & 31, (p >> 10) & 31], axis=1)


def luma_tables():
    d = region("main_data", np.uint8)
    n = int(d[LUMA:LUMA + 4].view("<u4")[0])
    return d[LUMA + 4:LUMA + 4 + n * 128].reshape(n, 128).astype(np.int32)


def texparams():
    """-> list of 32 (diffuse, ambient, specular scale, specular control)"""
    m = region("main_data", "<u4")
    o = TEXPARAM // 4
    n = int(m[o + 1])
    return [(int(v) & 255, (int(v) >> 8) & 255, (int(v) >> 16) & 255, (int(v) >> 24) & 255) for v in m[o + 2:o + 2 + n]]


def xlat(level, luma):
    """colorxlat as program 0xA74 fills it (monitor setting [0x5FE5E2] = 0), then MAME's display curve
    (model2_v.cpp video_start: (value - 64) * 255 / 191). level 0..31, luma 0..63 (arrays allowed)."""
    level = np.asarray(level, np.int64); luma = np.asarray(luma, np.int64)
    p = level * 12 * luma
    v = np.where(p == 0, 0, np.minimum((p + 4448) >> 6, 255))
    return np.clip((v - 64) * 255.0 / 191.0, 0, 255)


# share of the diffuse term assumed when a tile is baked "flat" (the real value is |normal . light| per polygon)
FLAT_DIFFUSE = 0.7


def poly_luma(param):
    """polygon luminance 0..255 the geometry engine would send for a light parameter index, flat-lit"""
    d, a, _, _ = texparams()[param]
    return min(255.0, a + FLAT_DIFFUSE * d)


def tile_rgba(course, sheet, x, y, w, h, cbase, lbase, param, translucent, mirror_x=False, mirror_y=False):
    """one texture as the header describes it -> uint8 [h (x2 when mirrored), w (x2), 4]"""
    s = sheets(course)[sheet]
    xs = (x + np.arange(w)) & 2047; ys = (y + np.arange(h)) & 1023
    t = s[np.ix_(ys, xs)].astype(np.int32)
    lt = luma_tables()[lbase if lbase < len(luma_tables()) else 0]
    lum = np.minimum(lt[t * 8] * poly_luma(param) / 256.0, 63).astype(np.int64)
    pal = palette()
    c = pal[cbase] if cbase < len(pal) else np.array([31, 31, 31])
    img = np.zeros((h, w, 4), np.uint8)
    for k in range(3): img[:, :, k] = xlat(c[k], lum)
    img[:, :, 3] = 255
    if translucent: img[:, :, 3] = np.where(t == 15, 0, 255)
    if mirror_x: img = np.concatenate([img, img[:, ::-1]], axis=1)
    if mirror_y: img = np.concatenate([img, img[::-1]], axis=0)
    return img


def solid_rgb(cbase, param):
    pal = palette()
    c = pal[cbase] if cbase < len(pal) else np.array([31, 31, 31])
    return [float(xlat(c[k], int(poly_luma(param)) >> 2)) for k in range(3)]


if __name__ == "__main__":
    import sys, os
    from PIL import Image
    from daytona_paths import WORK
    for c in (0, 1, 2):
        s = sheets(c)
        for i in (0, 1):
            Image.fromarray((s[i] * 17).astype(np.uint8)).save(os.path.join(WORK, "sheet_c%d_s%d.png" % (c, i)))
    print("palette", len(palette()), "luma tables", len(luma_tables()), "texparams", texparams()[:8])
