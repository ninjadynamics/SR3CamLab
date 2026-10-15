"""Build Model 2 srallyc region images (little-endian, as MAME ROM_LOAD32_WORD lays them out;
see mame/src/mame/sega/model2.cpp ROM_START( srallyc )) straight from your own srallyc.zip (settings 'roms').
    python m2_build.py        -> <work>/tmp/m2/{maincpu, main_data, copro_data, polygons, textures}.bin"""
import os, sys, zipfile
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'core'))
import common

REGIONS = dict(maincpu=([(0, "epr-17888c", "epr-17889c")], 0x200000),
               main_data=([(0, "mpr-17746", "mpr-17747"), (0x400000, "mpr-17744", "mpr-17745"), (0x800000, "mpr-17884", "mpr-17885")], 0xC00000),
               copro_data=([(0, "mpr-17754", "mpr-17755")], 0x400000),
               polygons=([(0, "mpr-17748", "mpr-17750"), (0x400000, "mpr-17749", "mpr-17751")], 0x800000),
               textures=([(0, "mpr-17753", "mpr-17752")], 0x400000))
SOUND = "epr-17890"                                  # the sound board's 68000 program (src_leftovers.py reads it from the zip)

def chips(path=None):
    """{file name: bytes} of the ROM set"""
    z = zipfile.ZipFile(path or common.rom_zip('srallyc')); return {n: z.read(n) for n in z.namelist()}

def find(ch, prefix):
    c = [n for n in ch if n.startswith(prefix)]
    assert len(c) == 1, (prefix, c)
    return c[0]

def load32(ch, pairs, size):
    buf = np.zeros(size // 2, dtype="<u2")
    for off, lo, hi in pairs:
        a = np.frombuffer(ch[find(ch, lo)], dtype="<u2"); b = np.frombuffer(ch[find(ch, hi)], dtype="<u2")
        buf[off // 2: off // 2 + 2 * len(a): 2] = a
        buf[off // 2 + 1: off // 2 + 1 + 2 * len(b): 2] = b
    return buf

def build(out=None, ch=None):
    out = out or os.path.join(common.TMP, 'm2'); os.makedirs(out, exist_ok=True); ch = ch or chips()
    for name, (pairs, size) in REGIONS.items():
        load32(ch, pairs, size).tofile(os.path.join(out, name + '.bin'))
    return out

if __name__ == '__main__':
    O = build()
    for f in sorted(os.listdir(O)): print(f, os.path.getsize(os.path.join(O, f)))
