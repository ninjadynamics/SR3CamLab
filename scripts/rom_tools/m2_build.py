"""Build Model 2 srallyc region images (little-endian, as MAME ROM_LOAD32_WORD lays them out;
see mame/src/mame/sega/model2.cpp ROM_START( srallyc ))."""
import os, numpy as np
S = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic"
R = S + "/roms/srallyc/"
O = S + "/out/m2/"
os.makedirs(O, exist_ok=True)

def find(prefix):
    c = [f for f in os.listdir(R) if f.startswith(prefix)]
    assert len(c) == 1, (prefix, c)
    return R + c[0]

def load32(pairs, size):
    buf = np.zeros(size // 2, dtype="<u2")
    for off, lo, hi in pairs:
        a = np.fromfile(find(lo), dtype="<u2"); b = np.fromfile(find(hi), dtype="<u2")
        buf[off // 2: off // 2 + 2 * len(a): 2] = a
        buf[off // 2 + 1: off // 2 + 1 + 2 * len(b): 2] = b
    return buf

load32([(0, "epr-17888c", "epr-17889c")], 0x200000).tofile(O + "maincpu.bin")
load32([(0, "mpr-17746", "mpr-17747"), (0x400000, "mpr-17744", "mpr-17745"), (0x800000, "mpr-17884", "mpr-17885")], 0xC00000).tofile(O + "main_data.bin")
load32([(0, "mpr-17754", "mpr-17755")], 0x400000).tofile(O + "copro_data.bin")
load32([(0, "mpr-17748", "mpr-17750"), (0x400000, "mpr-17749", "mpr-17751")], 0x800000).tofile(O + "polygons.bin")
load32([(0, "mpr-17753", "mpr-17752")], 0x400000).tofile(O + "textures.bin")
for f in sorted(os.listdir(O)): print(f, os.path.getsize(O + f))
