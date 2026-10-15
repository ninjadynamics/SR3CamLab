"""Build the Daytona USA (original Model 2, MAME set `daytona`) region images from the unpacked ROM chips.
Layout taken from MAME model2.cpp ROM_START( daytona ): every pair is ROM_LOAD32_WORD (two 16-bit chips make
one little-endian 32-bit word; the first chip is the low half).

    python daytona_build.py            # unpacks nothing: expects the chips in <scratch>/daytona/roms/

Regions written to <scratch>/daytona/out/ :
    maincpu.bin    0x040000  i960 program            (mapped at 0x00000000; second half also at 0x00220000)
    main_data.bin  0x900000  main data ROM           (mapped at 0x02000000)
    copro_data.bin 0x400000  coprocessor data ROM
    polygons.bin   0x1000000 polygon ROM             (geometry engine address 0x800000 | word index)
    textures.bin   0x1000000 "texture" ROM           (texture coordinate lists and texture headers, 16-bit words)
"""
import os
import numpy as np
from daytona_paths import ROMS, OUT

SETS = {
    "maincpu":    (0x040000,  [(0x000000, "epr-16722a.12", "epr-16723a.13")]),
    "main_data":  (0x900000,  [(0x000000, "mpr-16528.10", "mpr-16529.11"),
                               (0x400000, "mpr-16808.8", "mpr-16809.9"),
                               (0x800000, "epr-16724a.6", "epr-16725a.7")]),
    "copro_data": (0x400000,  [(0x000000, "mpr-16537.28", "mpr-16536.29")]),
    "polygons":   (0x1000000, [(0x000000, "mpr-16523.16", "mpr-16518.20"),
                               (0x400000, "mpr-16524.17", "mpr-16519.21"),
                               (0x800000, "mpr-16525.18", "mpr-16520.22"),
                               (0xC00000, "mpr-16772.19", "mpr-16771.23")]),
    "textures":   (0x1000000, [(0x000000, "mpr-16522.25", "mpr-16521.24"),
                               (0x800000, "mpr-16770.27", "mpr-16769.26")]),
}


def load32(pairs, size):
    buf = np.zeros(size // 2, dtype="<u2")
    for off, lo, hi in pairs:
        a = np.fromfile(os.path.join(ROMS, lo), dtype="<u2")
        b = np.fromfile(os.path.join(ROMS, hi), dtype="<u2")
        buf[off // 2: off // 2 + 2 * len(a): 2] = a
        buf[off // 2 + 1: off // 2 + 1 + 2 * len(b): 2] = b
    return buf


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, (size, pairs) in SETS.items():
        load32(pairs, size).tofile(os.path.join(OUT, name + ".bin"))
        print("%-14s 0x%07X bytes  <- %s" % (name + ".bin", size, ", ".join("%s+%s @%06X" % (lo, hi, off) for off, lo, hi in pairs)))
