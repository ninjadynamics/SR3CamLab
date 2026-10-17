"""Scan a ROM for tables whose records start with a strictly increasing small number (section index 0..299)."""
import numpy as np, sys
def scan(path, lo=0, hi=None, maxv=300, minlen=10):
    raw = np.fromfile(path, np.uint8)[lo:hi]; out = []
    for width, dt in ((2, '<u2'), (4, '<u4'), (1, 'u1')):
        for stride in (width, 2 * width, 4, 8, 12, 16, 20, 24):
            if stride < width or stride % width: continue
            for phase in range(0, stride, width if width > 1 else 1):
                n = (len(raw) - phase - width) // stride
                if n < minlen: continue
                idx = phase + np.arange(n) * stride
                if width == 1: v = raw[idx].astype(np.int64)
                else: v = raw[: (len(raw) // width) * width].view(dt)[idx // width].astype(np.int64) if phase % width == 0 else None
                if v is None: continue
                inc = (v[1:] > v[:-1]) & (v[1:] < maxv) & (v[:-1] >= 0) & (v[1:] - v[:-1] < 60)
                # runs of True
                e = np.flatnonzero(np.diff(np.concatenate([[0], inc.view(np.int8), [0]])))
                for a, b in zip(e[::2], e[1::2]):
                    if b - a + 1 >= minlen and v[b] - v[a] >= 100 and not (stride == width and (v[a + 1:b + 1] - v[a:b] == 1).mean() > 0.6):
                        out.append((lo + phase + a * stride, width, stride, b - a + 1, int(v[a]), int(v[b])))
    return out
if __name__ == '__main__':
    res = scan(sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16))
    seen = set()
    for r in sorted(res, key=lambda r: (r[0] // 64, -r[3])):
        if r[0] // 32 in seen: continue
        seen.add(r[0] // 32); print('%06x width %d stride %2d count %3d values %d..%d' % r)
