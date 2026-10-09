"""hexw.py file endian(> or <) byteoffset nwords [cols] : dump 32-bit words with float interpretation"""
import sys, numpy as np, struct
f, en, off, n = sys.argv[1], sys.argv[2], int(sys.argv[3], 0), int(sys.argv[4], 0)
cols = int(sys.argv[5]) if len(sys.argv) > 5 else 8
with open(f, "rb") as fh:
    fh.seek(off); d = fh.read(n * 4)
a = np.frombuffer(d, dtype=en + "u4"); fl = a.view(en + "f4")
for i in range(0, len(a), cols):
    row = a[i:i + cols]
    s = " ".join("%08X" % x for x in row)
    fs = " ".join(("%9.3f" % v if (1e-4 < abs(v) < 1e7) else "        .") for v in fl[i:i + cols])
    print("%08X: %s | %s" % (off + i * 4, s, fs))
