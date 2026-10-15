"""SEGA Rally Championship gameplay tables: section tables (main data) and pace-note tables (program ROM)."""
import numpy as np, struct, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'core')); import common   # tools/import/settings.json
MAIN = os.path.join(common.TMP, 'm2', 'main_data.bin'); PROG = os.path.join(common.TMP, 'm2', 'maincpu.bin')
SECT = {1: 0x0, 2: 0x3e00, 3: 0x7c00, 4: 0xba00}          # course (collision block order): 1 Mountain 2 Desert 3 Lake Side 4 Forest
NOTES = [0x40470, 0x40500, 0x405a0, 0x40690]
_d = np.fromfile(MAIN, '<u4'); _f = _d.view('<f4')
def sections(c):
    o = SECT[c] // 4; n = int(_d[o]); p = [int(x) - 0x02000000 for x in _d[o + 1:o + 4]]
    gate = _f[p[0] // 4:p[0] // 4 + 6 * n].reshape(n, 2, 3).astype(float)       # two boundary points (y = 0) per section
    quad = _d[p[1] // 4:p[1] // 4 + 3 * n].reshape(n, 3)                         # {4 | object index, point indices}
    dirs = _f[p[2] // 4:p[2] // 4 + 2 * n].reshape(n, 2).astype(float)           # (cos, sin) of the section's heading
    return gate, quad, dirs
def notes(k):
    raw = open(PROG, 'rb').read(); o = NOTES[k]; out = []
    while True:
        s, a, b = struct.unpack_from('<3I', raw, o)
        if s == 9999 or s == 0xffffffff: break
        out.append((s, a, b)); o += 12
    return out
if __name__ == '__main__':
    import collections
    for c in SECT:
        g, q, dr = sections(c); mid = g.mean(1); ang = np.unwrap(np.arctan2(dr[:, 1], dr[:, 0]))
        step = np.linalg.norm(np.diff(mid, axis=0), axis=1)
        print('course %d: %d sections, gate width %.1f m, step %.1f m, total turn %.0f deg, first mid (%.1f, %.1f) heading (%.2f, %.2f); direction vs next-mid agreement %.2f' % (c, len(g), np.linalg.norm(g[0, 0] - g[0, 1]), np.median(step), np.degrees(ang[-1] - ang[0]), mid[0, 0], mid[0, 2], dr[0, 0], dr[0, 1],
              np.mean([np.dot((mid[(i + 1) % len(mid)] - mid[i])[[0, 2]], dr[i]) / max(np.linalg.norm((mid[(i + 1) % len(mid)] - mid[i])[[0, 2]]), 1e-6) for i in range(len(mid))])))
    # which note table belongs to which course: a note's icon id (b) must always announce the same turn direction
    for k in range(4):
        nt = notes(k); row = []
        for c in SECT:
            g, q, dr = sections(c); ang = np.unwrap(np.arctan2(dr[:, 1], dr[:, 0])); n = len(ang); by = collections.defaultdict(list)
            for s, a, b in nt:
                turn = ang[min(s + 14, n - 1)] - ang[min(s + 1, n - 1)]; by[a].append(turn)
            good = sum(max(sum(1 for t in v if t > 0.05), sum(1 for t in v if t < -0.05)) for v in by.values()); mag = np.mean([abs(t) for v in by.values() for t in v])
            row.append('course %d: %2d/%d same-sign, mean |turn| %.0f deg' % (c, good, len(nt), np.degrees(mag)))
        print('table %d (%d notes): ' % (k, len(nt)) + ' | '.join(row))
