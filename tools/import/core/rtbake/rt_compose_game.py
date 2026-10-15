"""From the raw game bake to the light-map pages and table the importer reads (course setting lm_table=<out>).   python rt_compose_game.py <path> <out> <AMB> [BOUNCE]
    light = (1 - AMB) x sun seen x facing + AMB x (0.35 + 0.65 x sky seen) + BOUNCE x colour coming back         (open flat ground = 1)
The game multiplies its own brightness rule by the map, so a texel holds light / rule (never above 1). The road (lying polygons within 9 m of the
centre line) takes the light without its colour. AMB is the shade level: 0.34 = the look of RT2 ; higher = softer."""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..')))      # tools/import/core
import sys, pickle, numpy as np
import lightmap1995 as LM
PATH, OUT, AMB = sys.argv[1], sys.argv[2], float(sys.argv[3]); BOUNCE = float(sys.argv[4]) if len(sys.argv) > 4 else 0.55; PAGE = LM.PAGE
RAW = np.load(PATH + '.raw.npy', mmap_mode='r'); K = np.load(PATH + '.pack.npz'); page, x0, y0, nu, nv = K['page'], K['x0'], K['y0'], K['nu'], K['nv']; D = np.load(PATH + '.lm.npz'); P = D['P'].astype(float); N = D['N'].astype(float)
S = pickle.load(open(PATH + '.scene', 'rb')); cen = np.asarray(S['centre'], float); c = P.mean(1)[:, [0, 2]]; d = np.full(len(P), 1e9)
lying = N[:, 1] / np.maximum(np.linalg.norm(N, axis=1), 1e-9) > 0.9; li = np.nonzero(lying)[0]          # (only a lying polygon can be road: the distance is asked for those alone - at R4 a third of 400 000)
for s in range(0, len(li), 4000): d[li[s:s + 4000]] = np.sqrt(((c[li[s:s + 4000], None] - cen[None, ::2]) ** 2).sum(2).min(1))
road = (d < 9.0) & lying; npg = RAW.shape[0]; rmask = np.zeros((npg, PAGE, PAGE), bool)
for i in np.where(road)[0]: rmask[page[i] - 1, y0[i]:y0[i] + (nv[i] + 3) // 4 * 4, x0[i]:x0[i] + (nu[i] + 3) // 4 * 4] = True
pages = np.full((npg, PAGE, PAGE, 3), 255, np.uint8); over = 0; tot = 0; mean = 0.0
def one(p):
    r = RAW[p].astype(np.float32) / 255.0; V, A, B, F, I = r[..., 0], r[..., 1], r[..., 2:5] / 4.0, r[..., 5], np.maximum(r[..., 6], 0.05)
    L = (1 - AMB) * (V * F)[..., None] + AMB * (0.35 + 0.65 * A)[..., None] + BOUNCE * B
    lum = (L * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(2); L[rmask[p]] = lum[rmask[p]][:, None]
    val = L / I[..., None]; pages[p] = np.round(np.clip(val, 0, 1) * 255).astype(np.uint8); return int((val.max(2) > 1.02).sum()), val.shape[0] * val.shape[1], float(np.clip(L, 0, 1).mean())
import os, concurrent.futures
with concurrent.futures.ThreadPoolExecutor(max(1, min(npg, 8, int(os.environ.get('RTC_THREADS', '8'))))) as ex_: res_ = list(ex_.map(one, range(npg)))
for o_, t_, m_ in res_: over += o_; tot += t_; mean += m_ / npg
np.save(OUT + '.lm.pages.npy', pages); np.savez(OUT + '.lm.table.npz', K=LM.key(P), page=page, x0=x0, y0=y0, nu=nu, nv=nv, **({'ab': K['ab']} if 'ab' in K.files else {}))      # (ab: where a polygon's corners are in its rectangle - the pieces of a rounded polygon share one)
print('RTCG amb %.3f bounce %.2f ; road polygons %d of %d ; mean light over the pages %.2f ; texels that wanted more than the rule allows (clipped at 1): %.2f%% -> %s' % (AMB, BOUNCE, int(road.sum()), len(P), mean, 100.0 * over / tot, OUT))
