"""SR2 course block tables. Record (48 bytes, big-endian, fixed CROM):
   float x,y,z; u32 w; 4 x {u32 vrom_model_addr (words), u32 n}   (FFFFFFFF = none)
Descriptor triples {count, kind, ptr} at 0xCF180 (group A) and 0xDE1F8 (group B)."""
import numpy as np
O = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic/out/m3/"
crom = np.fromfile(O + "crom.bin", dtype=">u4")
cf = crom.view(">f4")
GROUPS = {"A": 0xCF180, "B": 0xDE1F8}

def descriptors(off):
    out = []
    i = off // 4
    while True:
        n, kind, ptr = int(crom[i]), int(crom[i + 1]), int(crom[i + 2])
        if n == 0 or ptr == 0: break
        out.append((n, kind, ptr)); i += 3
    return out

def records(ptr, n):
    out = []
    for r in range(n):
        i = ptr // 4 + r * 12
        xyz = tuple(float(v) for v in cf[i:i + 3])
        w = int(crom[i + 3])
        lods = [(int(crom[i + 4 + 2 * k]), int(crom[i + 5 + 2 * k])) for k in range(4)]
        out.append((xyz, w, lods))
    return out

if __name__ == "__main__":
    from collections import Counter
    for g, off in GROUPS.items():
        for ti, (n, kind, ptr) in enumerate(descriptors(off)):
            recs = records(ptr, n)
            xyz = np.array([r[0] for r in recs])
            have = [r for r in recs if r[2][0][0] != 0xFFFFFFFF]
            nolod0 = sum(1 for r in recs if r[2][0][0] == 0xFFFFFFFF)
            anyl = sum(1 for r in recs if any(l[0] != 0xFFFFFFFF for l in r[2]))
            addrs = [l[0] for r in recs for l in r[2] if l[0] != 0xFFFFFFFF]
            nvals = Counter(l[1] for r in recs for l in r[2] if l[0] != 0xFFFFFFFF)
            ws = Counter(r[1] for r in recs)
            d = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
            print("group %s table %d: n=%d kind=%d ptr=%06X | with-any-model=%d lod0-missing=%d | x[%.0f..%.0f] y[%.0f..%.0f] z[%.0f..%.0f]" % (
                g, ti, n, kind, ptr, anyl, nolod0, xyz[:, 0].min(), xyz[:, 0].max(), xyz[:, 1].min(), xyz[:, 1].max(), xyz[:, 2].min(), xyz[:, 2].max()))
            print("    model addr range %06X..%06X unique=%d ; consecutive-centre dist median=%.1f max=%.1f sum=%.0f ; w top=%s ; n range %d..%d" % (
                min(addrs), max(addrs), len(set(addrs)), np.median(d), d.max(), d.sum(), ws.most_common(3), min(nvals), max(nvals)))
            for r in recs[:6]:
                print("      (%.1f,%.1f,%.1f) w=%04X " % (r[0] + (r[1],)) + " ".join("%06X/%04X" % l if l[0] != 0xFFFFFFFF else "------/----" for l in r[2]))
