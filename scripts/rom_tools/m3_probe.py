import sys, numpy as np
S = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic"
O = S + "/out/m3/"
pre = sys.argv[1]
for nm in ("_cull_lo", "_cull_hi", "_poly"):
    a = np.fromfile(O + pre + nm + ".bin", dtype="<u4")
    nz = np.count_nonzero(a)
    mp = np.nonzero(((a >> 24) == 1) & ((a & 0xFFFFFF) >= 0x100000) & ((a & 0xFFFFFF) < 0x1000000))[0]
    print(nm, "words", len(a), "nonzero", nz, "vrom-model-ptr-like", len(mp), "first idx", [hex(x) for x in mp[:10]], "last", [hex(x) for x in mp[-3:]])
    # nonzero extent by 64K-word blocks
    blk = a.reshape(-1, 0x4000)
    print("   nonzero per 16K-word block:", [int(np.count_nonzero(b)) for b in blk][:70])
vrom = np.fromfile(O + "vrom_le.bin", dtype="<u4")
blk = vrom.reshape(-1, 0x40000)
print("vrom nonzero per 256K-word (1MB) block:", [int(np.count_nonzero(b) * 100 // len(b)) for b in blk])
for nm in ("crom", "banked_crom"):
    c = np.fromfile(O + nm + ".bin", dtype=">u4")
    mp = np.nonzero(((c >> 24) == 1) & ((c & 0xFFFFFF) >= 0x100000) & ((c & 0xFFFFFF) < 0x1000000))[0]
    print(nm, "words", len(c), "vrom-ptr-like", len(mp))
    h, e = np.histogram(mp, bins=np.arange(0, len(c) + 1, 0x10000))
    print("  per 256KB:", [(hex(int(e[i]) * 4), int(h[i])) for i in range(len(h)) if h[i] > 50])
