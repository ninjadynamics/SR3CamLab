"""Export the Daytona USA (set `daytona`, original Model 2) cars from the ROM region images: one folder per car with
an OBJ (+ MTL, _lifted.obj for viewing, textures/, materials.json) and cars.json with what each object is.

    python daytona_build.py          # once: region images from the unpacked chips
    python daytona_cars.py           # -> <COURSES>/cars/

Axes of the OBJ as the course exports: metres, Y up, Z = -(game Z); the game's car faces +Z, so the OBJ car faces -Z.
Ground = y 0 (tyres touch it).

What the objects are (docs/kb/daytona_usa_rom_data.md, section 11; own findings from the program and data):
  player car struct (main data 0x0281E390): three arrays indexed by [RAM 0x501488]
      0x0281E390 body {1460, 1461, 1835}, 0x0281E39C window frames / nets {1462, 1463, 1793},
      0x0281E3A8 bonnet for the in-car view {1236, 1237, 1802}, 0x0281E3B4 roof / door numbers 1..8 {1794..1801}
      index 0 / 1 = single play (RAM 0x501464, LIKELY the transmission choice), 2 = linked play (code 0xEBF0..0xEC9C).
  opponents: 43 entries of 48 bytes at 0x0281E404 {7 LOD object pointers, shadow, int, int, float, int}
      over the 45 liveries of rows 0..179 (4 LODs each, identical geometry, own texture headers);
  linked-play cars: 8 entries at 0x0281EC14, rows 1803..1834 (4 LODs each);
  wheels: opponents draw a 4-wheel set after the body in car space (code 0x8800..0x8828: frames 0x93EC[(angle >> 11) & 7]
      = rows 180..187, low detail 0x940C = rows 188..195); single wheels 805 (left) / 806 (right) of 255 polygons are
      drawn on the transmission-select screen (table 0x238ED4); 793 / 794 are a 38-polygon pair.
"""
import os, sys, json
import numpy as np
from daytona_paths import COURSES
from daytona_objs import object_table
from daytona_export import faces_of, Writer

OUT = os.path.join(COURSES, "cars")

# wheel centres in game axes (x, y, z), from the opponent wheel sets (rows 180..195): rim discs at x = +-0.859..0.875,
# tread inner face x = +-0.487, radius 0.36, axles z = +1.412 (front) and -1.395 (rear). The single wheels 805 / 806 span
# x -0.401..0 / 0..0.401 with their rim face outside, so they are moved by +-(0.875 - 0.401).
WHEEL_Y = 0.36
WHEEL_Z = {"f": 1.412, "r": -1.395}
WHEEL_X_OUT = 0.875
WHEEL_W = 0.401
WHEELS = {}
for ax, z in WHEEL_Z.items():
    for side, sx in (("l", -1), ("r", 1)):
        WHEELS[ax + side] = dict(centre=[sx * (WHEEL_X_OUT - WHEEL_W / 2), WHEEL_Y, z],
                                 offset=[sx * (WHEEL_X_OUT - WHEEL_W), WHEEL_Y, z],
                                 hi=805 if sx < 0 else 806, lo=793 if sx < 0 else 794)

HORNETS = {
    "hornet_0": dict(body=1460, frames=1462, bonnet=1236, note="single play index 0: red / blue #41 (the Hornet as on the cabinet art)"),
    "hornet_1": dict(body=1461, frames=1463, bonnet=1237, note="single play index 1: yellow / red #41 (row 1459 is an identical copy)"),
    "hornet_link": dict(body=1835, frames=1793, bonnet=1802, numbers=list(range(1794, 1802)),
                        note="linked play: red Hornet without number; the cabinet number 1..8 is a separate object"),
}


def tab_rows():
    return object_table()


def write_car(name, parts, meta):
    """parts: list of (object name, row, offset (game axes) or None)"""
    folder = os.path.join(OUT, name)
    w = Writer(0, folder, name, "# Daytona USA car '%s' (rows %s). SEGA data - not for the repository.\n"
               % (name, ", ".join(str(r) for _, r, _ in parts)))
    tab = tab_rows()
    info = []
    for oname, row, off in parts:
        fs = faces_of(row, tab)
        xf = None
        if off is not None:
            o = np.array(off, float)
            xf = (lambda P, o=o: P + o)
        w.add(oname, fs, xf)
        info.append(dict(object=oname, row=row, faces=len(fs), offset=off))
    w.close()
    meta = dict(meta, folder=folder, objects=info, materials=len(w.mats), counts=w.count)
    return meta


def wheel_parts(kind="hi"):
    return [("wheel_" + k, v[kind], v["offset"]) for k, v in WHEELS.items()]


def main():
    os.makedirs(OUT, exist_ok=True)
    cars = {}
    for name, h in HORNETS.items():
        parts = [("body", h["body"], None), ("frames", h["frames"], None)] + wheel_parts("hi")
        if "numbers" in h: parts.append(("number_1", h["numbers"][0], None))
        cars[name] = write_car(name, parts, dict(kind="player", note=h["note"], bonnet=h["bonnet"]))
        cars[name + "_bonnet"] = write_car(name + "_bonnet", [("bonnet", h["bonnet"], None)], dict(kind="bonnet view model"))
    for k in range(45):
        rows = list(range(4 * k, 4 * k + 4))
        parts = [("lod%d" % i, r, None) for i, r in enumerate(rows)] + [("wheelset", 180, None), ("wheelset_lo", 188, None)]
        cars["opp_%02d" % k] = write_car("opp_%02d" % k, parts, dict(kind="opponent livery", rows=rows))
    for k in range(8):
        rows = list(range(1803 + 4 * k, 1807 + 4 * k))
        parts = [("lod%d" % i, r, None) for i, r in enumerate(rows)] + [("wheelset", 180, None)]
        cars["link_%d" % (k + 1)] = write_car("link_%d" % (k + 1), parts, dict(kind="linked-play car", rows=rows))
    extra = [("extra_r1836", [("lod%d" % i, r, None) for i, r in enumerate(range(1836, 1840))], "4 LODs, #99 livery, use UNKNOWN"),
             ("extra_r1840", [("body", 1840, None)], "red Hornet without number (frontend table 0x327E0, LIKELY)"),
             ("extra_r0796", [("body", 796, None)], "326-polygon car, use UNKNOWN"),
             ("extra_r0795", [("wheel", 795, None)], "427-polygon wheel, SEGA ENTERPRISES tyre lettering, use UNKNOWN")]
    for name, parts, note in extra:
        cars[name] = write_car(name, parts, dict(kind="extra", note=note))
    json.dump(dict(wheels=WHEELS, cars=cars), open(os.path.join(OUT, "cars.json"), "w"), indent=1)
    print("wrote", len(cars), "cars to", OUT)


if __name__ == "__main__":
    main()
