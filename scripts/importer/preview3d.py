"""Fallback perspective previews with matplotlib (no Blender): classic model (grey, shaded by height) + decoded SR3 road.
    python preview3d.py [step]"""
import os, sys, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import preview as PVW

def main(step='step17_classic_scenery_textured_desert4'):
    D = PVW.decode_step(step); V, VT, faces = PVW.load_classic(); out = []
    cen = np.array([r[len(r) // 2] for r in D['road']]); n = D['n']
    def render(name, centre, half, elev, azim, title):
        fig = plt.figure(figsize=(13, 9), dpi=120); ax = fig.add_subplot(111, projection='3d')
        polys = []; cols = []
        for mat, vi, ti in faces:
            P = V[vi]
            if half and (abs(P[:, 0].mean() - centre[0]) > half or abs(P[:, 2].mean() - centre[2]) > half): continue
            polys.append(np.stack([P[:, 0], P[:, 2], P[:, 1]], 1)); nrm = np.cross(P[1] - P[0], P[2] - P[0]); l = np.linalg.norm(nrm)
            sh = 0.55 + 0.4 * abs(nrm[1] / l) if l > 0 else 0.7; cols.append((sh * 0.8, sh * 0.82, sh * 0.78, 1.0))
        ax.add_collection3d(Poly3DCollection(polys, facecolors=cols, edgecolors=(0, 0, 0, 0.15), linewidths=0.2))
        rq = []; rc = []; st = 1 if half else 4
        for i in range(0, n, st):
            a = D['road'][i]; b = D['road'][(i + st) % n]
            if half and (abs(a[0][0] - centre[0]) > half or abs(a[0][2] - centre[2]) > half): continue
            for k in range(0, len(a) - 1):
                q = np.array([a[k], a[k + 1], b[k + 1], b[k]]); rq.append(np.stack([q[:, 0], q[:, 2], q[:, 1] + 0.2], 1))
                rc.append((0.85, 0.1, 0.1, 0.9) if D['surf'][i][k] == 1 else (0.95, 0.6, 0.1, 0.9))
        ax.add_collection3d(Poly3DCollection(rq, facecolors=rc, edgecolors='none'))
        if half:
            ax.set_xlim(centre[0] - half, centre[0] + half); ax.set_ylim(centre[2] - half, centre[2] + half); ax.set_zlim(centre[1] - half * 0.4, centre[1] + half * 0.6)
        else:
            ax.set_xlim(V[:, 0].min(), V[:, 0].max()); ax.set_ylim(V[:, 2].min(), V[:, 2].max()); ax.set_zlim(0, 400)
        ax.set_box_aspect((1, (ax.get_ylim()[1] - ax.get_ylim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0]), (ax.get_zlim()[1] - ax.get_zlim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0])))
        ax.view_init(elev=elev, azim=azim); ax.set_xlabel('x'); ax.set_ylabel('z'); ax.set_zlabel('height'); ax.set_title(title, fontsize=10)
        p = os.path.join(PVW.PV, name); fig.savefig(p, bbox_inches='tight'); plt.close(fig); out.append(p)
    d = np.roll(cen, -1, 0) - cen; d[:, 1] = 0; d /= np.linalg.norm(d, axis=1)[:, None]
    turn = np.arccos(np.clip((d * np.roll(d, -1, 0)).sum(1), -1, 1)); it = int(np.convolve(np.concatenate([turn[-10:], turn, turn[:10]]), np.ones(21), 'valid').argmax())
    ig = int(np.abs(np.roll(cen[:, 1], -20) - cen[:, 1]).argmax()) + 10
    render('persp3d_overview.png', None, None, 35, -60, 'Classic Mountain course (grey) with the decoded SR3 road (red tarmac / orange gravel), whole course')
    render('persp3d_start.png', cen[D['start'] - 1], 90, 25, -70, 'start line area')
    render('persp3d_tightest_bend.png', cen[it], 90, 35, -120, 'tightest bend (hairpin)')
    render('persp3d_steepest.png', cen[ig], 110, 20, -50, 'steepest section')
    print('\n'.join(out))

if __name__ == '__main__':
    main(*sys.argv[1:2])
