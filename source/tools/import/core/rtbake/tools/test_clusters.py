"""seal1995._clusters against the dictionary walk it replaces: random places with planted near twins and chains, and the places of built meshes.
    python test_clusters.py [<step> ...]     (from the importer folder)"""
import sys, os, time, struct
import numpy as np
sys.path.insert(0, os.getcwd())
import seal1995 as S
rs = np.random.RandomState(5); bad = 0
for trial in range(40):
    n = int(rs.randint(2, 6000)); U = rs.uniform(-700, 700, (n, 3)) if trial % 3 else rs.uniform(-0.01, 0.01, (n, 3))
    k = n // 5; src = rs.randint(0, n, k); U[rs.randint(0, n, k)] = U[src] + rs.uniform(-0.0012, 0.0012, (k, 3)) * (0.5 if trial % 2 else 1.0)      # twins, and chains of them
    U = np.unique(U.astype(np.float32), axis=0).astype(np.float64); a = S._clusters(U, 0.001); b = S._clusters_py(U, 0.001); bad += not np.array_equal(a, b)
print('random sets where the labels differ, of 40:', bad)
if len(sys.argv) > 1:
    from common import *
    import sbfw, meshgen
    for step in sys.argv[1:]:
        f = sbfw.read_sbf(track_files(os.path.join(OUT, step, 'Desert4'))['master_gfx_xdata']); P = []
        for c in f.chunks:
            if c.kind == 1 and (c.id >> 16) == 0xc1a7: P.append(meshgen.parse_mesh(c)['verts']['p'][:, :3])
        V = np.concatenate(P).astype(np.float32) + np.float32(0); raw = np.ascontiguousarray(V).view(np.dtype((np.void, 12))).ravel(); U = V[np.unique(raw, return_index=True)[1]].astype(np.float64)
        t0 = time.perf_counter(); a = S._clusters(U, 0.001); t1 = time.perf_counter(); b = S._clusters_py(U, 0.001); t2 = time.perf_counter()
        print('%s: %d places, %d groups of more than one ; arrays %.2f s, dictionary %.2f s ; the same labels: %s' % (step, len(U), int((np.bincount(a) > 1).sum()), t1 - t0, t2 - t1, bool(np.array_equal(a, b))))
