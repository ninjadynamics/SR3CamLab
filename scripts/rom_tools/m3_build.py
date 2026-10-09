"""Build Model 3 srally2 address-space images (big-endian byte streams) and split save states.
Layout taken from Supermodel Config/Games.xml (<game name="srally2">) and
Src/GameLoader.cpp (LoadRegion/ApplyLayout) + Src/Model3/Model3.cpp (LoadGame).
"""
import sys, os, struct
import numpy as np

S = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic"
R = S + "/roms/srally2/"
O = S + "/out/m3/"
os.makedirs(O, exist_ok=True)

def interleave(files, stride, chunk, size, swap):
    buf = np.zeros(size, dtype=np.uint8)
    for off, name in files:
        d = np.fromfile(R + name, dtype=np.uint8)
        n = len(d) // chunk
        base = off % stride
        start = off - base
        view = buf[start:start + n * stride].reshape(n, stride)
        view[:, base:base + chunk] = d.reshape(n, chunk)
    if swap:
        b = buf.reshape(-1, 2)[:, ::-1].reshape(-1)
        buf = np.ascontiguousarray(b)
    return buf

crom = interleave([(0, "epr-20635.20"), (2, "epr-20634.19"), (4, "epr-20633.18"), (6, "epr-20632.17")], 8, 2, 0x800000, True)
crom.tofile(O + "crom.bin")       # maps to FF800000-FFFFFFFF, big-endian
banked = interleave([
    (0x0000000, "mpr-20605.4"), (0x0000002, "mpr-20604.3"), (0x0000004, "mpr-20603.2"), (0x0000006, "mpr-20602.1"),
    (0x1000000, "mpr-20609.8"), (0x1000002, "mpr-20608.7"), (0x1000004, "mpr-20607.6"), (0x1000006, "mpr-20606.5"),
    (0x2000000, "mpr-20613.12"), (0x2000002, "mpr-20612.11"), (0x2000004, "mpr-20611.10"), (0x2000006, "mpr-20610.9"),
], 8, 2, 0x3000000, True)
banked.tofile(O + "banked_crom.bin")
vfiles = ["mpr-20616.26", "mpr-20617.27", "mpr-20618.28", "mpr-20619.29", "mpr-20620.30", "mpr-20621.31", "mpr-20622.32",
          "mpr-20623.33", "mpr-20624.34", "mpr-20625.35", "mpr-20626.36", "mpr-20627.37", "mpr-20628.38", "mpr-20629.39",
          "mpr-20630.40", "mpr-20631.41"]
vrom = interleave([(i * 2, f) for i, f in enumerate(vfiles)], 32, 2, 0x4000000, False)
# Supermodel reads this buffer as host little-endian uint32; store as LE words
vrom.tofile(O + "vrom_le.bin")
print("crom", crom[:16].tobytes().hex(), "vrom", vrom[:32].tobytes().hex())

# save states
for st in sys.argv[1:]:
    d = open(st, "rb").read()
    name = os.path.splitext(os.path.basename(st))[0] + "_" + os.path.basename(st)[-3:]
    pos = 0
    print(st, len(d), d[:64])
    # generic block walk
    # find header
    i = 0
    blocks = []
    # try from several starts
    for start in (0, 8, 12, 16):
        pos = start; ok = []
        try:
            while pos < len(d):
                ln, nl, cl = struct.unpack_from("<III", d, pos)
                if ln < 12 or nl > 256 or cl > 1024: raise ValueError
                nm = d[pos + 12:pos + 12 + nl].split(b"\0")[0].decode("latin1")
                ok.append((nm, pos + 12 + nl + cl, pos + ln))
                pos += ln
        except Exception:
            pass
        if len(ok) > 3:
            blocks = ok; break
    for nm, a, b in blocks:
        print("  block %-20s data %08X..%08X (%d)" % (nm, a, b, b - a))
        if nm == "Real3D":
            p = d[a:b]
            open(O + name + "_cull_lo.bin", "wb").write(p[0:0x400000])
            open(O + name + "_cull_hi.bin", "wb").write(p[0x400000:0x500000])
            open(O + name + "_poly.bin", "wb").write(p[0x500000:0x900000])
            open(O + name + "_texram.bin", "wb").write(p[0x900000:0x1100000])
            open(O + name + "_r3d_tail.bin", "wb").write(p[0x1200000:])
        if nm == "Model 3":
            p = d[a:b]
            # find ram: fields before ram: inputBank.. unknown sizes; ram is 8MB; block is ram+0x40000+small
            extra = len(p) - 0x800000 - 0x40000
            print("   model3 extra bytes", extra)
            open(O + name + "_m3_block.bin", "wb").write(p)
