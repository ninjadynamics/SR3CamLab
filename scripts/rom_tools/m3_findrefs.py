"""Find words in CROM images that point at valid VROM models (any top byte)."""
import sys, numpy as np, pickle
sys.path.insert(0, ".")
from m3_scene import decode_model, O
vrom = np.fromfile(O + "vrom_le.bin", dtype="<u4")

def quick_valid(addr, cache={}):
    if addr in cache: return cache[addr]
    ok = False; npoly = 0
    if 0x100000 <= addr < len(vrom) - 16:
        h0 = int(vrom[addr])
        # first polygon cannot share verts
        if (h0 & 0xF) == 0 and int(vrom[addr + 6]) != 0:
            polys, ok = decode_model(vrom, addr, maxpolys=6000)
            npoly = len(polys)
            if ok:
                # sanity: coordinates reasonable, tex words sane
                mx = max(abs(c) for vs, h in polys[:50] for v in vs for c in v[:3]) if polys else 0
                if npoly == 0 or mx > 4000: ok = False
    cache[addr] = (ok, npoly)
    return cache[addr]

res = {}
for nm in ("crom", "banked_crom"):
    c = np.fromfile(O + nm + ".bin", dtype=">u4")
    lowm = c & 0xFFFFFF
    cand = np.nonzero((lowm >= 0x100000) & ((c >> 24) <= 0x05) & (c != 0))[0]
    print(nm, "candidates", len(cand))
    hits = []
    for i in cand:
        ok, npoly = quick_valid(int(lowm[i]))
        if ok: hits.append((int(i) * 4, int(c[i]), npoly))
    print(nm, "valid model refs", len(hits), "unique", len(set(h[1] & 0xFFFFFF for h in hits)))
    res[nm] = hits
    h, e = np.histogram([x[0] for x in hits], bins=np.arange(0, len(c) * 4 + 1, 0x20000))
    print("  per 128KB:", [(hex(int(e[i])), int(h[i])) for i in range(len(h)) if h[i] > 20])
pickle.dump(res, open(O + "modelrefs.pkl", "wb"))
