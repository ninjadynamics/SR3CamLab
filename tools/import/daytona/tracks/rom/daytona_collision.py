"""Daytona USA: the road-surface quads in the coprocessor (TGP) data ROM (mpr-16537 / mpr-16536), per course.

Layout (own finding, checked by plotting the quads on the extracted course; docs/kb/daytona_usa_rom_data.md):
    0x00  a 4 x 4 identity matrix (16 floats)
    0x40  16 words: per course id the WORD offset of an index block (0x30, 0x8000, 0x10000, 0x18000; unused ids = 0x30)
    0x80  16 words: per course id the WORD offset of the quad block (0x19C90, 0x1E690, 0x3AB00, 0x465A0)
    quad block: 64-byte records = 4 corners (x, y, z floats, game axes), a centre point (x, y, z), one word
                (low 16 bits look like a heading, 65536 = 360 degrees; high 16 bits 0xFFFF or 0)
    index block: variable-length lists { count, count x quad number } (which quads to test for a position); the key that
                selects a list was not decoded.
The second 2 MB of the region repeats the first.

    python daytona_collision.py beginner     -> <COURSES>/<course>/daytona_<course>_collision.obj (+ _collision.png)
"""
import os, sys
import numpy as np
from daytona_paths import OUT, COURSES

COURSE_ID = {"beginner": 0, "expert": 1, "advanced": 2}


def quads(cid):
    c = np.fromfile(os.path.join(OUT, "copro_data.bin"), dtype="<u4")
    f = c.view("<f4")
    starts = sorted(set(int(x) for x in c[0x80 // 4:0x80 // 4 + 16]))
    a = int(c[0x80 // 4 + cid])
    nxt = [s for s in starts if s > a]
    if nxt: b = nxt[0]
    else:
        b = a
        while b + 16 <= len(c) // 2 and np.isfinite(f[b:b + 15]).all() and np.abs(f[b:b + 15]).max() < 1e5 and (c[b:b + 16] != 0xFFFFFFFF).any(): b += 16
    n = (b - a) // 16
    rec = f[a:a + n * 16].reshape(n, 16).astype(np.float64)
    last = c[a:a + n * 16].reshape(n, 16)[:, 15].copy()
    return rec[:, :12].reshape(n, 4, 3), rec[:, 12:15], last


if __name__ == "__main__":
    course = sys.argv[1]; cid = COURSE_ID[course]
    Q, C, last = quads(cid)
    folder = os.path.join(COURSES, course); os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "daytona_%s_collision.obj" % course), "w") as fo:
        fo.write("# Daytona USA course %d %s: road-surface quads of the coprocessor data ROM. Metres, Y up, Z = -gameZ\n" % (cid, course))
        for q in Q:
            for p in q: fo.write("v %.4f %.4f %.4f\n" % (p[0], p[1], -p[2]))
        for i in range(len(Q)):
            fo.write("f %d %d %d %d\n" % (4 * i + 4, 4 * i + 3, 4 * i + 2, 4 * i + 1))
    d = np.abs(Q.mean(1) - C).max(1)
    print("%s: %d quads ; centre word = mean of the corners within %.3f m for %d%% ; x[%.1f %.1f] y[%.1f %.1f] z[%.1f %.1f] ; last word high halves %s" % (
        course, len(Q), np.percentile(d, 95), 100 * (d < 0.05).mean(), Q[..., 0].min(), Q[..., 0].max(), Q[..., 1].min(), Q[..., 1].max(),
        Q[..., 2].min(), Q[..., 2].max(), sorted(set("%04X" % (x >> 16) for x in last))[:6]))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import PolyCollection
        import daytona_course as DC
        fig, ax = plt.subplots(figsize=(11, 11), dpi=110)
        ax.add_collection(PolyCollection([q[:, [0, 2]] for q in Q], facecolors=(0.3, 0.5, 0.9, 0.5), edgecolors=(0.1, 0.2, 0.5, 0.8), linewidths=0.2))
        L = DC.lines(cid)[0]
        ax.plot(L[:, 0], L[:, 2], color=(0.9, 0.2, 0.1), lw=0.6)
        ax.set_xlim(Q[..., 0].min() - 20, Q[..., 0].max() + 20); ax.set_ylim(Q[..., 2].min() - 20, Q[..., 2].max() + 20)
        ax.set_aspect("equal"); ax.set_title("Daytona USA %s: coprocessor-ROM quads (blue), driving line 0 (red); game x / z, metres" % course, fontsize=9)
        fig.savefig(os.path.join(folder, "daytona_%s_collision.png" % course), bbox_inches="tight")
    except ImportError:
        pass
