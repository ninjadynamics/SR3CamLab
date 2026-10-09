"""Locate the 48-byte 'course block' records in SR2 fixed CROM: 4x{VROM model addr, word} + xyz float + word."""
import sys, numpy as np, pickle
O = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic/out/m3/"
c = np.fromfile(O + "crom.bin", dtype=">u4")
f = c.view(">f4")

def rec_ok(i):
    if i + 12 > len(c): return False
    anyp = False
    for k in range(4):
        p, n = int(c[i + 2 * k]), int(c[i + 2 * k + 1])
        if p == 0xFFFFFFFF and n == 0xFFFFFFFF: continue
        if 0x100000 <= p < 0x1000000 and n < 0x10000: anyp = True; continue
        return False
    for k in range(3):
        v = float(f[i + 8 + k])
        if not (abs(v) < 1e5) or (v != 0 and abs(v) < 1e-6 and False): return False
    if int(c[i + 11]) >= 0x100000: return False
    return True

runs = []
i = 0
N = len(c)
ok = np.zeros(N, dtype=bool)
# prefilter: positions where word i+11 small and floats sane
for i in range(0x90000 // 4, 0x200000 // 4):
    ok[i] = rec_ok(i)
i = 0x90000 // 4
while i < 0x200000 // 4:
    if ok[i]:
        j = i; n = 0; nreal = 0
        while j < N and (ok[j] or all(int(c[j + t]) == 0xFFFFFFFF for t in range(8))):
            if ok[j]: nreal += 1
            n += 1; j += 12
        if nreal >= 8:
            runs.append((i * 4, n, nreal)); i = j; continue
    i += 1
tot = 0
for off, n, nreal in runs:
    xyz = np.array([[float(f[off // 4 + r * 12 + 8 + k]) for k in range(3)] for r in range(n)])
    w = [int(c[off // 4 + r * 12 + 11]) for r in range(n)]
    print("run @%06X n=%4d real=%4d  x[%.0f..%.0f] y[%.0f..%.0f] z[%.0f..%.0f]  w11 %d..%d" % (off, n, nreal, xyz[:, 0].min(), xyz[:, 0].max(), xyz[:, 1].min(), xyz[:, 1].max(), xyz[:, 2].min(), xyz[:, 2].max(), min(w), max(w)))
    tot += n
print("runs", len(runs), "records", tot)
pickle.dump(runs, open(O + "area_runs.pkl", "wb"))
