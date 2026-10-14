"""Daytona USA: objects the game places on top of the course cells (own findings; docs/kb/daytona_usa_rom_data.md).

Per course a table of 256 pointers (one per cell of the 16 x 16 grid) in the program ROM:
    program 0x33BFC -> { 0x233C0C Beginner, 0x234374 Expert, 0x234D90 Advanced, 0x2354B4 course 3 }   (CPU addresses;
    the second half of the program ROM is mapped at 0x220000, so file offset = address - 0x200000)
A non-zero pointer leads to { count, count x 24-byte record }:
    record = { float x, y, z ; u16 angle (65536 = 360 degrees) ; u16 parameter ; handler ; data }
    handler = address of the i960 routine that starts the object's task; data = an object-table record, or a list of
    object-table records (animation frames) in the program ROM.
The list of cell 0 holds the people (pit crews, marshals); they are built from body parts by their own routines.

What each handler does was read from its code; only the ones that draw an object with a fixed transform are exported:
    WORLD    the object is already in course coordinates (drawn with the current matrix)
    TR       translate (x, y, z), then rotate about Y by the angle  (TGP function 0x12, then 0x15)
    FRAMES   as TR, object = first entry of the frame list chosen by the parameter (table 0x236B50, 16 bytes each)
    BANNER   translate + scale (s, 1, s) + rotate Y, position and scale from table 0x236D60 (24 bytes per parameter)
For animated objects the first frame is exported. Everything else is listed in placed_objects.json as "not exported".
"""
import os, json, struct, math
import numpy as np
from daytona_paths import OUT, COURSES
from daytona_objs import OBJTAB, OBJTAB_END

CELL_TABLES = {0: 0x233C0C, 1: 0x234374, 2: 0x234D90}
FRAME_TABLE = 0x236B50
BANNER_TABLE = 0x236D60
OBJ_LO = 0x02000000 + OBJTAB; OBJ_HI = 0x02000000 + OBJTAB_END

WORLD = {0x2202C4: "row of flags / crowd strip (frame list)", 0x220698: "two-frame blinking object", 0x220730: "two-frame blinking object",
         0x2211FC: "row of flags (frame list)", 0x2212A4: "64-frame object in course coordinates", 0x221E40: "flags on the grandstand (frame list)",
         0x221EF8: "64-frame object in course coordinates", 0x222018: "static object in course coordinates",
         0x220A54: "start gantry panel (object 801; 802 on the final lap, 804 on a flag)", 0x220D34: "wind turbines: blades (frame list) + objects 854, 855"}
TR = {0x220118: "static object", 0x220898: "sign that turns about Y (exported at its start angle)", 0x2207C8: "sign that turns (exported at its start angle)"}
FRAMES = {0x2201BC: "sponsor board, 3 frames"}
BANNER = {0x2210A0: "waving banner, 64 frames"}
NOT = {0x2212E4: "people manager", 0x221700: "person built from parts (pit crew)", 0x221664: "person", 0x221698: "person", 0x2216CC: "person",
       0x221618: "people end marker", 0x220B08: "position / lap boards of the start gantry (digits drawn by code)",
       0x220364: "slot machine reels (drawn by code)", 0x220948: "banner with three rotations", 0x222080: "animated animal / bird",
       0x222314: "animated animal / bird", 0x2224F8: "animated animal / bird", 0x222608: "animated animal / bird", 0x222A20: "animated animal / bird"}

_p = None


def prog():
    global _p
    if _p is None: _p = open(os.path.join(OUT, "maincpu.bin"), "rb").read()
    return _p


def rd(a, fmt): return struct.unpack_from(fmt, prog(), a - 0x200000)
def is_obj(p): return OBJ_LO <= p < OBJ_HI and (p - OBJ_LO) % 20 == 0
def obj_index(p): return (p - OBJ_LO) // 20
def in_prog(p): return 0x220000 <= p < 0x240000


def records(cid):
    out = []
    ptrs = rd(CELL_TABLES[cid], "<256I")
    for cell, p in enumerate(ptrs):
        if not p: continue
        n = rd(p, "<I")[0]
        for i in range(n):
            x, y, z, ang, par, fn, dp = rd(p + 4 + 24 * i, "<3fHHII")
            out.append(dict(cell=cell, pos=(x, y, z), angle=ang, param=par, handler=fn, data=dp))
    return out


def rot_y(a16):
    """TGP rotate-Y as MAME's model1 matrix_roty writes it: local x -> (cos, 0, sin)"""
    a = a16 * 2 * math.pi / 65536.0
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])


def resolve(r):
    """-> (kind, [object indices], transform function or None, note)"""
    fn = r["handler"]; dp = r["data"]
    T = np.array(r["pos"], np.float64)
    def frame0(p):
        if is_obj(p): return obj_index(p)
        if in_prog(p):
            q = rd(p, "<I")[0]
            if is_obj(q): return obj_index(q)
        return None
    if fn in WORLD:
        if fn == 0x220A54: return "WORLD", [801], None, WORLD[fn]
        o = frame0(dp)
        objs = [o] if o is not None else []
        if fn == 0x220D34: objs = [obj_index(rd(0x2361B0, "<I")[0]), 854, 855]
        return "WORLD", objs, None, WORLD[fn]
    if fn in TR:
        o = frame0(dp); R = rot_y(r["angle"])
        return "TR", ([o] if o is not None else []), (lambda P, R=R, T=T: P @ R.T + T), TR[fn]
    if fn in FRAMES:
        lst, n, div, _ = rd(FRAME_TABLE + r["param"] * 16, "<4I")
        o = frame0(lst); R = rot_y(r["angle"])
        return "FRAMES", ([o] if o is not None else []), (lambda P, R=R, T=T: P @ R.T + T), FRAMES[fn]
    if fn in BANNER:
        s, x, y, z, la, lb = rd(BANNER_TABLE + r["param"] * 24, "<4f2I")
        o = frame0(la); R = rot_y(r["angle"]); S = np.array([s, 1.0, s]); Tb = np.array([x, y, z], np.float64)
        return "BANNER", ([o] if o is not None else []), (lambda P, R=R, S=S, Tb=Tb: (P * S) @ R.T + Tb), BANNER[fn] + " scale %.2f" % s
    if fn == 0x221618 and dp == 0x220E54:
        # the generic "start the task whose routine is in the data word" record; 0x220E54 draws object 1599 (the statue the
        # player can turn) at the record's position, without rotation until it is touched (program 0x220E78 .. 0x220F98)
        return "TR", [1599], (lambda P, T=T: P + T), "statue (object 1599), turns when the player stops in front of it"
    return "NOT", [], None, NOT.get(fn, "handler not read")


def add_placed(writer, cid, tab):
    from daytona_export import faces_of
    log = []; done = 0; skipped = 0
    for i, r in enumerate(records(cid)):
        kind, objs, xf, note = resolve(r)
        e = dict(cell=r["cell"], pos=[round(v, 3) for v in r["pos"]], angle="%04X" % r["angle"], param=r["param"],
                 handler="%06X" % r["handler"], data="%08X" % r["data"], kind=kind, objects=objs, note=note)
        if kind == "NOT" or not objs:
            e["exported"] = False; skipped += 1
        else:
            for o in objs:
                writer.add("placed_%03d_%s_obj%04d" % (i, kind.lower(), o), faces_of(o, tab), xf)
            e["exported"] = True; done += 1
        log.append(e)
    json.dump(log, open(os.path.join(writer.folder, "placed_objects.json"), "w"), indent=1)
    return "placed-object records: %d exported, %d not (people, digits, reels, animals: placed_objects.json)" % (done, skipped)
