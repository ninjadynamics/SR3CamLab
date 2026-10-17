"""Split SRC drive logs by the 1995 surface under the car (collision attribute bits 16-19).
python surf_split.py <course 1..4> <log.csv> [t_from t_to]
Course numbers = the export numbers (1 Mountain, 2 Desert, 3 Lake Side, 4 Forest). The collision OBJ is (x, y, -game z).
Codes (18_src_1995_rom_data.md): 0/1/8/9 tarmac (9 tunnel), 2 gravel / light dirt, 3 dirt / mud, 4 water, 6 verge."""
import sys, os, csv, math, collections, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'import', 'core'))
import build_more as BM
course, path = sys.argv[1], sys.argv[2]
t_lo, t_hi = (float(sys.argv[3]), float(sys.argv[4])) if len(sys.argv) > 4 else (-1e9, 1e9)
GROUP = {0: 'tarmac', 1: 'tarmac', 8: 'tarmac', 9: 'tarmac', 2: 'gravel', 3: 'dirt', 4: 'water', 6: 'verge'}
OBJ = os.path.join(__import__('common').CLASSIC, 'obj', 'src_course%s_collision.obj' % course)   # SR3CamLab\classic = the link to the classic folder (git-ignored)
tris = BM.load_obj_tris(OBJ)
cell = 8.0; T = np.array([t for a, t in tris]); A = [(a >> 16) & 15 for a, t in tris]
grid = collections.defaultdict(list)
for i, t in enumerate(T):
    for gx in range(int(math.floor(t[:, 0].min() / cell)), int(math.floor(t[:, 0].max() / cell)) + 1):
        for gz in range(int(math.floor(t[:, 2].min() / cell)), int(math.floor(t[:, 2].max() / cell)) + 1): grid[(gx, gz)].append(i)
def code_at(x, z, y):
    best = None
    for i in grid.get((int(math.floor(x / cell)), int(math.floor(z / cell))), ()):
        a, b, c = T[i]
        d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
        if abs(d) < 1e-9: continue
        u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d; v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d; w = 1 - u - v
        if min(u, v, w) < -1e-4: continue
        h = u * a[1] + v * b[1] + w * c[1]
        if best is None or abs(h - y) < abs(best[0] - y): best = (h, A[i])
    return best[1] if best and abs(best[0] - y) < 3 else None
R = [r for r in csv.DictReader(open(path)) if t_lo <= float(r['t']) <= t_hi and r.get('vx') not in (None, '')]
t = np.array([float(r['t']) for r in R]); vx = np.array([float(r['vx']) for r in R]); vz = np.array([float(r['vz']) for r in R])
psi = np.array([-float(r['w3c']) for r in R]); brk = np.array([float(r['brk']) for r in R])
v = np.hypot(vx, vz) * 216 / 3.6
course_ang = np.unwrap(np.arctan2(vx, vz))
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
beta = np.degrees(np.abs(wrap(psi - np.arctan2(vx, vz))))
dt = np.gradient(t); alat = v * np.gradient(course_ang) / dt; along = np.gradient(v) / dt
med = np.array([np.median(np.abs(alat[max(0, i - 15):i + 16])) for i in range(len(t))])
imp = np.convolve((np.abs(along) > 12).astype(float), np.ones(30), mode='same') > 0
codes = [code_at(float(r['x']), -float(r['z']), float(r['y'])) for r in R]
grp = np.array([GROUP.get(c, 'none' if c is None else 'code%d' % c) for c in codes])
print('%s: %d samples; surface under the car: %s' % (path.split('\\')[-1], len(R), dict(collections.Counter(grp))))
ok = (v * 3.6 > 40) & ~imp
for g in sorted(set(grp)):
    m = ok & (grp == g)
    if m.sum() < 60: continue
    bins = []
    for lo, hi in ((0.6, 0.9), (0.9, 1.2), (1.2, 1.6), (1.6, 2.5)):
        s = m & (np.abs(alat) / 9.81 >= lo) & (np.abs(alat) / 9.81 < hi)
        bins.append('%.1f-%.1fg %.1f deg' % (lo, hi, np.median(beta[s])) if s.sum() > 15 else '%.1f-%.1fg -' % (lo, hi))
    bm = (v * 3.6 > 40) & (grp == g) & (brk > 200)
    print('  %-7s %5d samples (%4.1f s): sustained a_lat p95 %.2f g, p99 %.2f g | slip p50 %.1f p90 %.1f deg | slip by a_lat: %s | braking %s' % (
        g, m.sum(), m.sum() / 60, np.percentile(med[m], 95) / 9.81, np.percentile(med[m], 99) / 9.81, np.percentile(beta[m], 50), np.percentile(beta[m], 90),
        ', '.join(bins), ('%.2f g (%d)' % (-np.median(along[bm]) / 9.81, bm.sum())) if bm.sum() > 10 else '-'))

