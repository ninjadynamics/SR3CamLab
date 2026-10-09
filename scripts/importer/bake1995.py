"""BAKED LIGHT for a classic course (user, 2026-10-08: "BASE, BASE-SHADOWS, BASE-RT").

The game lights a vertex with  ambient + sun x N.L ; the importer already hands it a normal that gives the brightness it wants
(build_classic.faces_to_mesh). Baking = deciding that brightness with RAYS, for every vertex of the scenery and of the road:
    V  how much of the sun reaches it (rays in a narrow cone towards the sun)                  -> cast shadows
    A  how much of the sky it sees (rays over the half space of its face)                       -> dim corners, narrow streets
    B  the light that comes back from what those rays hit (what they hit x how lit it is)      -> bounce
It takes two builds, because the vertices are only known when the meshes are written:
    1. course setting "bake_collect": <file>   the build writes every lit vertex and the scene to <file> (+ '.scene')
    2. python bake1995.py <file>               Blender casts the rays (bl_bake.py, several processes) -> <file> + '.light.npy'
    3. course settings "bake_table": <file>, "bake_mode": "shadows" | "rt"       the build reads the light back
The light is per VERTEX: a shadow is as sharp as the polygons are small, so "bake_refine": <metres> cuts the big polygons
near the road first (refine)."""
import os, sys, pickle, subprocess, time
import numpy as np

BLENDER = r'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'

def refine(faces, size, centre=None, reach=70.0, log=print):
    """polygons with an edge longer than `size` are cut into a grid of pieces no longer than it (texture coordinates follow).
    Cut-outs, the sea and polygons farther than `reach` from the road stay as they are."""
    out = []; ncut = 0; nnew = 0; cen = None if centre is None else np.asarray(centre, float)
    for fc in faces:
        mat, sec, P, UV = fc; m0 = str(mat).split('|')[0]
        if m0.endswith('_t') or str(sec) == 'sea' or len(P) not in (3, 4): out.append(fc); continue
        A = np.asarray(P, float); e = np.linalg.norm(A - np.roll(A, -1, axis=0), axis=1)
        if e.max() <= size * 1.25: out.append(fc); continue
        if cen is not None and np.sqrt(((cen - A[:, [0, 2]].mean(0)) ** 2).sum(1).min()) > reach: out.append(fc); continue
        U = np.asarray(UV, float); ncut += 1
        if len(P) == 4:
            nu = int(min(24, np.ceil(max(e[0], e[2]) / size))); nv = int(min(24, np.ceil(max(e[1], e[3]) / size)))
            s = np.linspace(0, 1, nu + 1); t = np.linspace(0, 1, nv + 1)
            def at(X, a, b): return (1 - a) * (1 - b) * X[0] + a * (1 - b) * X[1] + a * b * X[2] + (1 - a) * b * X[3]
            for i in range(nu):
                for j in range(nv):
                    c = [(s[i], t[j]), (s[i + 1], t[j]), (s[i + 1], t[j + 1]), (s[i], t[j + 1])]
                    out.append((mat, sec, [tuple(map(float, at(A, a, b))) for a, b in c], [tuple(map(float, at(U, a, b))) for a, b in c])); nnew += 1
        else:
            n = int(min(24, np.ceil(e.max() / size)))
            def at(X, a, b): return X[0] + a * (X[1] - X[0]) + b * (X[2] - X[0])
            for i in range(n):
                for j in range(n - i):
                    c = [(i / n, j / n), ((i + 1) / n, j / n), (i / n, (j + 1) / n)]
                    out.append((mat, sec, [tuple(map(float, at(A, a, b))) for a, b in c], [tuple(map(float, at(U, a, b))) for a, b in c])); nnew += 1
                    if j < n - i - 1:
                        c = [((i + 1) / n, j / n), ((i + 1) / n, (j + 1) / n), (i / n, (j + 1) / n)]
                        out.append((mat, sec, [tuple(map(float, at(A, a, b))) for a, b in c], [tuple(map(float, at(U, a, b))) for a, b in c])); nnew += 1
    log('       polygons cut finer for the baked light (bake_refine %.1f m): %d polygons -> %d pieces' % (size, ncut, nnew))
    return out

def save_scene(path, faces, rd, tile_pixels, sun, log=print):
    """what the rays can hit: every polygon of the scenery (cut-outs with their see-through mask) and the road"""
    T = []; UV = []; M = []; mats = {}; alb = []; albc = []; holes = []
    for mat, sec, P, U in faces:
        if str(sec) == 'sea' or len(P) < 3: continue
        m0 = str(mat).split('|')[0]
        if m0 not in mats:
            px = None
            try: px = tile_pixels(m0)
            except Exception: px = None
            if px is None: a_ = 0.35; h_ = None; c_ = (0.35, 0.35, 0.35)
            else:
                rgb, hole = px; rgb = np.asarray(rgb, float); rgb = rgb if rgb.ndim == 3 else np.dstack([rgb] * 3)
                keep = ~hole if hole is not None and hole.shape == rgb.shape[:2] and (~hole).any() else np.ones(rgb.shape[:2], bool)
                a_ = float(((rgb[keep] / 255.0) ** 2.2).mean()); c_ = tuple(((rgb[keep] / 255.0) ** 2.2).mean(0)); h_ = hole if hole is not None and hole.shape == rgb.shape[:2] and hole.any() else None
            mats[m0] = len(alb); alb.append(a_); albc.append(c_); holes.append(None if h_ is None else np.asarray(h_, bool))
        A = np.asarray(P, float); B = np.asarray(U, float)
        for i0, i1, i2 in (((0, 1, 3), (1, 2, 3)) if len(P) == 4 else ((0, 1, 2),)): T.append((A[i0], A[i1], A[i2])); UV.append((B[i0], B[i1], B[i2])); M.append(mats[m0])      # (four corners: split along 1 - 3 as the game draws them)
    if rd is not None:
        R = np.asarray(rd['V'], float); R2 = np.roll(R, -1, axis=0); a, b, c, d = R[:, :-1], R[:, 1:], R2[:, 1:], R2[:, :-1]; k = len(alb); alb.append(0.22); albc.append((0.2, 0.22, 0.24)); holes.append(None)
        for q in (np.stack([a, b, c], 2).reshape(-1, 3, 3), np.stack([a, c, d], 2).reshape(-1, 3, 3)):
            T += list(q); UV += [np.zeros((3, 2))] * len(q); M += [k] * len(q)
    D = dict(tris=np.array(T, np.float32), uv=np.array(UV, np.float32), mat=np.array(M, np.int32), albedo=np.array(alb, np.float32), albedo_rgb=np.array(albc, np.float32), holes=holes, sun=np.asarray(sun, float), centre=(np.asarray(rd['V'], float)[:, rd['hw']][:, [0, 2]] if rd is not None else np.zeros((1, 2))))
    pickle.dump(D, open(path + '.scene', 'wb'), protocol=4); log('       baked light: the scene for the rays, %d triangles, %d materials (%d with see-through texels) -> %s.scene' % (len(T), len(alb), sum(h is not None for h in holes), path))

def save_points(path, chunks, log=print):
    if not chunks: return
    P = np.concatenate([c[0] for c in chunks]).astype(np.float32); N = np.concatenate([c[1] for c in chunks]).astype(np.float32); U = np.concatenate([c[2] for c in chunks]).astype(bool)
    K = keys(P, N); _, first = np.unique(K, return_index=True); first.sort()
    np.savez(path, P=P[first], N=N[first], U=U[first]); log('       baked light: %d vertices to light (%d written by the meshes) -> %s' % (len(first), len(P), path))

def keys(P, N):
    """one key per vertex and facing: the place to the millimetre and the direction to a third"""
    q = np.concatenate([np.round(np.asarray(P, np.float64) * 1000.0), np.round(np.asarray(N, np.float64) * 3.0)], 1).astype(np.int32)
    return np.ascontiguousarray(q).view(np.dtype((np.void, 24))).ravel()

def load_table(path):
    D = np.load(path if path.endswith('.npz') else path + '.npz'); L = np.load(path + '.light.npy'); K = keys(D['P'], D['N'])
    full = {k.tobytes(): i for i, k in enumerate(K)}; place = {k.tobytes()[:12]: i for i, k in enumerate(K)}
    return dict(full=full, place=place, L=L, miss=[0, 0])

def lookup(tab, P, N):
    """-> (n, 3) array V, A, B ; a vertex the table does not know is taken as lit and open"""
    K = keys(P, N); idx = np.empty(len(K), np.int64); full, place = tab['full'], tab['place']
    for j, k in enumerate(K):
        b = k.tobytes(); i = full.get(b, -1)
        if i < 0: i = place.get(b[:12], -1); tab['miss'][0] += 1
        if i < 0: tab['miss'][1] += 1
        idx[j] = i
    out = np.where((idx >= 0)[:, None], tab['L'][np.maximum(idx, 0)], np.array([1.0, 1.0, 0.0], np.float32)); return out

def run_native(path, log=print):
    """the rays of bl_bake.py cast by rays.c (same fans, same rules) -> <path>.light.npy"""
    import rays, math
    t0 = time.time(); S = pickle.load(open(path + '.scene', 'rb')); D = np.load(path + '.npz'); P = D['P'].astype(float); N = D['N'].astype(float); U = D['U'].astype(bool)
    T = S['tris'].astype(float); TM = S['mat']; ALB = S['albedo'].astype(float); SUN = np.asarray(S['sun'], float); SUN = SUN / np.linalg.norm(SUN)
    sc = rays.Scene(T); sc.masks(TM, S['uv'], S['holes']); TN = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); TN /= np.maximum(np.linalg.norm(TN, axis=1), 1e-12)[:, None]
    def frame(n):
        ax = np.where((np.abs(n[:, 1]) < 0.9)[:, None], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]); t = np.cross(n, ax); t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]; return t, np.cross(n, t)
    st, sb = frame(SUN[None]); R = math.radians(1.6); SD = [SUN] + [SUN + math.tan(R) * (math.cos(a) * st[0] + math.sin(a) * sb[0]) for a in np.arange(6) * math.pi / 3]; SD = np.array([d / np.linalg.norm(d) for d in SD])
    KS = 16; HEMI = np.array([(math.sqrt((i + 0.5) / KS) * math.cos(i * 2.399963), math.sqrt((i + 0.5) / KS) * math.sin(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / KS))) for i in range(KS)])
    def light(p, n, k):
        o = p + n * 0.03; V = np.zeros(len(p)); fr = (n @ SUN) > 0.02
        if fr.any():
            oo = np.repeat(o[fr], len(SD), axis=0); dd = np.tile(SD, (int(fr.sum()), 1)); hit, _ = sc.cast(oo + dd * 0.12, dd, 1e9); V[fr] = (hit.reshape(-1, len(SD)) < 0).mean(1)
        t, b = frame(n); ang = (k * 0.618034) % 1.0 * 2 * math.pi; ca, sa = np.cos(ang)[:, None], np.sin(ang)[:, None]
        hx = HEMI[None, :, 0] * ca - HEMI[None, :, 1] * sa; hy = HEMI[None, :, 0] * sa + HEMI[None, :, 1] * ca
        d = (t[:, None, :] * hx[..., None] + b[:, None, :] * hy[..., None] + n[:, None, :] * HEMI[None, :, 2, None]).reshape(-1, 3); oo = np.repeat(o, KS, axis=0) + d * 0.12
        hit, dist = sc.cast(oo, d, 1e9); sky = (hit.reshape(-1, KS) < 0).mean(1); back = np.zeros(len(hit)); h = np.nonzero(hit >= 0)[0]
        if len(h):
            hn = TN[hit[h]]; hn = np.where(((hn * d[h]).sum(1) < 0)[:, None], hn, -hn); loc = oo[h] + d[h] * dist[h][:, None]; lit = np.full(len(h), 0.3); can = (hn @ SUN) > 0.05
            if can.any():
                o2 = loc[can] + hn[can] * 0.03; d2 = np.tile(SUN, (int(can.sum()), 1)); h2, _ = sc.cast(o2 + d2 * 0.12, d2, 1e9); cc = np.nonzero(can)[0][h2 < 0]; lit[cc] = 0.3 + 0.7 * (hn[cc] @ SUN) / max(SUN[1], 0.3)
            back[h] = ALB[TM[hit[h]]] * np.minimum(lit, 1.0)
        return np.stack([V, sky, back.reshape(-1, KS).mean(1)], 1)
    out = np.zeros((len(P), 3), np.float32)
    for a in range(0, len(P), 150000):
        p = P[a:a + 150000]; n = N[a:a + 150000]; n = n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]; k = np.arange(a, a + len(p)).astype(float); r = light(p, n, k); u = U[a:a + 150000]
        if u.any():
            r2 = light(p[u], -n[u], k[u]); better = (r2[:, 0] + r2[:, 1]) > (r[u][:, 0] + r[u][:, 1]); ru = r[u]; ru[better] = r2[better]; r[u] = ru
        out[a:a + len(p)] = r
    np.save(path + '.light.npy', out)
    log('baked light: %d vertices in %.1f s (rays.c, %d threads): sun reaches %.0f%% of them fully and none of %.0f%% ; mean sky seen %.2f ; mean light coming back %.3f' %
        (len(P), time.time() - t0, rays.lib().rt_threads(), 100.0 * (out[:, 0] > 0.99).mean(), 100.0 * (out[:, 0] < 0.01).mean(), out[:, 1].mean(), out[:, 2].mean()))
    return out

def run(path, procs=8, log=print):
    """casts the rays for <path>(.npz) with several Blender processes -> <path>.light.npy"""
    n = len(np.load(path + '.npz')['P']); t0 = time.time(); here = os.path.dirname(os.path.abspath(__file__)); ps = []
    for k in range(procs):
        a, b = n * k // procs, n * (k + 1) // procs
        ps.append(subprocess.Popen([BLENDER, '-b', '--factory-startup', '--python', os.path.join(here, 'bl_bake.py'), '--', path, str(a), str(b)], stdout=open('%s.log%d' % (path, k), 'w'), stderr=subprocess.STDOUT))
    rc = [p.wait() for p in ps]
    parts = [np.load('%s.part_%d_%d.npy' % (path, n * k // procs, n * (k + 1) // procs)) for k in range(procs)]; L = np.concatenate(parts).astype(np.float32); np.save(path + '.light.npy', L)
    for k in range(procs): os.remove('%s.part_%d_%d.npy' % (path, n * k // procs, n * (k + 1) // procs))
    log('baked light: %d vertices in %.0f s (%d processes, exit codes %s): sun reaches %.0f%% of them fully and none of %.0f%% ; mean sky seen %.2f ; mean light coming back %.3f' %
        (n, time.time() - t0, procs, rc, 100.0 * (L[:, 0] > 0.99).mean(), 100.0 * (L[:, 0] < 0.01).mean(), L[:, 1].mean(), L[:, 2].mean()))
    return L

if __name__ == '__main__':
    run(sys.argv[1], int(sys.argv[3]) if len(sys.argv) > 3 else 8) if (len(sys.argv) > 2 and sys.argv[2] == 'blender') else run_native(sys.argv[1])
