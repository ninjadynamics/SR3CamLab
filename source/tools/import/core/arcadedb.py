"""The car library of SEGA Rally 3: ArcadeDatabase\\arcadedatabase_xdata.sbf, kind 12 chunk ef990745 (type f38d4db3).

    cars = read_cars(chunk)            # -> list of Car
    chunk2 = cars_chunk(cars, chunk)   # -> sbfw.Ch, byte-identical to SEGA's for the unchanged list
    python arcadedb.py list [file]     # prints the records
    python arcadedb.py roundtrip [file]

Chunk data: u32 1, u32 count, then the records as a linked list (the first at +8):
  +0x00 ptr next record (0 and no fixup on the last)   +0x04 car id   +0x08 6000   +0x0C 1.0f
  +0x10 Classic flag   +0x14 bonus (secret page) flag  +0x18 ten u32 per-mode numbers (not decoded)
  +0x40 ptr name (LANG_ID_..., shown in the car select)   +0x44 ptr folder (car file prefix, CARSLIDE_<FOLDER>_GRAVEL_1)
  +0x48 ptr sound name (ID_CAR_..., engine bank SFX_<it>_PLAYER / _CPU, exe 0x644D60)
  +0x4C strings, each 0-terminated and padded to 4: name (a copy nothing points at), name, folder, sound name.
Fixups per record in order: next (when there is one), name, folder, sound.
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbfw

from common import GAME as _GAME
GAME_DB = os.path.join(_GAME, "ArcadeDatabase", "arcadedatabase_xdata.sbf")
CARS_ID = 0xEF990745


class Car:
    def __init__(self, cid, name, folder, sound, classic=0, bonus=0, nums=(1, 0, 2, 1, 3, 2, 4, 3, 5, 4), w2=6000, w3=0x3F800000,
                 name0=None):
        self.id = cid; self.name = name; self.folder = folder; self.sound = sound
        self.classic = classic; self.bonus = bonus; self.nums = list(nums); self.w2 = w2; self.w3 = w3
        self.name0 = name if name0 is None else name0       # the first (unreferenced) copy

    def __repr__(self):
        return "Car(%d %s folder %s sound %s classic %d bonus %d nums %s)" % (self.id, self.name, self.folder, self.sound,
                                                                           self.classic, self.bonus, self.nums)


def _s(b):
    b = b.encode("latin1") + b"\0"
    return b + b"\0" * (-len(b) % 4)


def read_cars(c):
    d = c.data; fix = set(c.fix)
    one, count = struct.unpack_from("<2I", d, 0)
    assert one == 1
    out = []; o = 8
    while True:
        w = struct.unpack_from("<19I", d, o)
        s = lambda a: d[a:d.index(b"\0", a)].decode("latin1")
        out.append(Car(w[1], s(w[16]), s(w[17]), s(w[18]), w[4], w[5], w[6:16], w[2], w[3], s(o + 0x4C)))
        if o not in fix: break
        o = w[0]
    assert len(out) == count, "count %d, list %d" % (count, len(out))
    return out


def cars_bytes(cars):
    out = bytearray(struct.pack("<2I", 1, len(cars))); fix = []
    for k, car in enumerate(cars):
        o = len(out)
        strs = [_s(car.name0), _s(car.name), _s(car.folder), _s(car.sound)]
        p0 = o + 0x4C
        pn = p0 + len(strs[0]); pf = pn + len(strs[1]); ps = pf + len(strs[2])
        end = ps + len(strs[3])
        nxt = end if k + 1 < len(cars) else 0
        out += struct.pack("<6I", nxt, car.id, car.w2, car.w3, car.classic, car.bonus) + struct.pack("<10I", *car.nums)
        out += struct.pack("<3I", pn, pf, ps) + b"".join(strs)
        if nxt: fix.append(o)
        fix += [o + 0x40, o + 0x44, o + 0x48]
    return bytes(out), fix


def cars_chunk(cars, like):
    d, fix = cars_bytes(cars)
    return sbfw.Ch(like.kind, like.id, d, fix, [], like.z, like.gap)


def add_car(f, car):
    """append a record to the car list of an SbfFile (in place); returns the new list"""
    i = [k for k, c in enumerate(f.chunks) if c.id == CARS_ID][0]
    cars = read_cars(f.chunks[i])
    assert all(c.id != car.id for c in cars), "car id %d exists" % car.id
    assert all(c.folder.lower() != car.folder.lower() for c in cars), "folder %s exists" % car.folder
    cars.append(car)
    f.chunks[i] = cars_chunk(cars, f.chunks[i])
    return cars


def write_db(f):
    raw = sbfw.write_raw(f.chunks, f.first, f.tail, f.hdr, layout="keep")
    return b"SBZ1" + struct.pack("<I", len(raw)) + __import__("zlib").compress(raw, 9) if f.compressed else raw


if __name__ == "__main__":
    p = sys.argv[2] if len(sys.argv) > 2 else GAME_DB
    f = sbfw.read_sbf(p)
    c = f.byid()[CARS_ID]
    cars = read_cars(c)
    if sys.argv[1] == "list":
        for car in cars: print(car)
    elif sys.argv[1] == "roundtrip":
        d, fix = cars_bytes(cars)
        print("chunk data identical:", d == c.data, "fixups identical:", fix == c.fix)
        f.chunks[[k for k, x in enumerate(f.chunks) if x.id == CARS_ID][0]] = cars_chunk(cars, c)
        print("file identical:", write_db(f) == open(p, "rb").read())
