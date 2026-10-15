"""Section geometry helpers: centre line through the 256 sections, ground height / surface lookup."""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2course import *

def tri(S, i):
    f = S['Pf'][i]; return np.array([f[4:7], f[7:10], f[10:13]], dtype=float)
def attr(S, i):
    a = int(S['Pu'][i, 74]); return a & 0xFFFF

def ground(S, sec, x, z, walls=False):
    """-> (y, surface type, poly index) of the polygon of section `sec` under (x, z); None if none."""
    best = None
    for i in S['lists'][sec]:
        a = attr(S, i)
        if (a & 0x8000) and not walls: continue
        T = tri(S, i); (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = T
        d = (z1 - z2) * (x0 - x2) + (x2 - x1) * (z0 - z2)
        if abs(d) < 1e-9: continue
        l0 = ((z1 - z2) * (x - x2) + (x2 - x1) * (z - z2)) / d; l1 = ((z2 - z0) * (x - x2) + (x0 - x2) * (z - z2)) / d; l2 = 1 - l0 - l1
        if min(l0, l1, l2) >= -1e-4:
            y = l0 * y0 + l1 * y1 + l2 * y2
            if best is None or y > best[0]: best = (y, a & 0xF, i)
    return best

def centreline(S):
    """entry mid points, centres, and cumulative distance (m) at each section entry; lap length."""
    q = S['quads']; n = S['n']
    entry = (q[:, 0] + q[:, 3]) / 2; exit_ = (q[:, 1] + q[:, 2]) / 2; cen = q.mean(axis=1)
    # path: entry0 -> cen0 -> entry1 -> cen1 ...
    seg = np.linalg.norm(cen - entry, axis=1) + np.linalg.norm(np.roll(entry, -1, axis=0) - cen, axis=1)
    dist = np.concatenate([[0], np.cumsum(seg)])
    return entry, cen, exit_, dist[:-1], float(dist[-1])

def road_centre(S, sec):
    """centre of the drivable (non-wall) polygons of a section, weighted by area; falls back to the quad centre"""
    P = []; Wt = []
    for i in S['lists'][sec]:
        if attr(S, i) & 0x8000: continue
        T = tri(S, i); ar = 0.5 * abs((T[1, 0] - T[0, 0]) * (T[2, 2] - T[0, 2]) - (T[2, 0] - T[0, 0]) * (T[1, 2] - T[0, 2]))
        P.append(T.mean(axis=0)); Wt.append(ar)
    if not P or sum(Wt) == 0: return None
    return np.average(np.array(P), axis=0, weights=Wt)

if __name__ == '__main__':
    from m3 import road_blocks, course_line
    for s in (1, 2, 3, 4, 5):
        S = sections(s); entry, cen, ex, dist, L = centreline(S); k = S['stage']['course_id'] - 2
        R = road_blocks(k); CL = course_line(k)
        d = np.linalg.norm(R[:, [0, 2]] - cen, axis=1)
        rc = [road_centre(S, i) for i in range(256)]
        print('stage', s, 'course idx', k, 'lap length via sections %.0f m' % L, 'road block[i] vs section centre[i]: median %.1f max %.1f' % (np.median(d), d.max()),
              'entry0', entry[0], 'cen0', cen[0], 'origin in section', [i for i in range(256) if ground(S, i, 0.0, 0.0)][:5], 'ground at origin', [ground(S, i, 0.0, 0.0) for i in (255, 0) if ground(S, i, 0.0, 0.0)])
        # nearest course line point to each section centre
        dd = [np.min(np.linalg.norm(CL[:, [0, 2]] - c, axis=1)) for c in cen]
        print('    course line to section centres: median %.1f max %.1f; line pts %d' % (np.median(dd), max(dd), len(CL)), 'widths', np.round(np.linalg.norm(S['quads'][:, 0] - S['quads'][:, 3], axis=1)[:5], 1))
