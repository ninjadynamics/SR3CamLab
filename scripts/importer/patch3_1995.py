"""PATCH 3 of a course, generated: our own authored geometry laid on the course as patches 1 and 2 leave it (owner, 2026-10-09: "patch 3
complements and enhances the track ... the cliffside and plateaus will be part of patch 3"; 2026-10-12: "re-add the old cliffside after
town square and the mesas/plateaus").

    python import_classic.py src 1 classic --norender --name <any> <RAW settings> --set patch=[1,2] --set patch_gen=3
    -> courses/<game>.<name>.patch.3.json   (needs [1, 2]; a build does not run this generator)

Two sources, both made earlier and kept beside the course export (classic/courses/<game>/<course>/):
  - the HAND MODEL (src_course<N>_handmodel.obj, plateau1995.py): the far rock screen completed into a mesa. Taken whole.
  - the HAND FILL  (src_course<N>_handfill.obj, gapfill_gen.py): the generated island. Only the CLIFF SIDE is taken: the ground and
    shore on the sea side of the road along the stretch named in the course setting "patch3_cliffside" (cells of the 1995 centre
    line, default 12 .. 70 = from the town square to the bend after the castle straight), out to `reach` metres.
What already has ground stays as it is: a hand-fill face is left out when the course (patches 1 and 2 applied) already has lying ground
under all of it, and when it would lie in the plane of a face that is there (overlay_bake.find_pairs: zero z-fighting comes first)."""
import os, json, collections
import numpy as np

REACH = 150.0            # m from the centre line, sea side
NEAR_Y = 4.0             # m: existing ground this close in height under / over a point counts as "there is ground here"
CELL = 4.0

def _tris(P):
    P = np.asarray(P, float); return [(P[0], P[i], P[i + 1]) for i in range(1, len(P) - 1)]
class Ground:
    """the lying faces of the course in a plan grid: heights of the ground at a point"""
    def __init__(self, faces):
        self.g = collections.defaultdict(list); self.T = []
        for fc in faces:
            if str(fc[0]).endswith('_t'): continue
            for a, b, c in _tris(fc[2]):
                n = np.cross(b - a, c - a); L = np.linalg.norm(n)
                if L < 1e-9 or abs(n[1]) / L < 0.35: continue
                k = len(self.T); self.T.append((a, b, c)); lo = np.floor(np.minimum(np.minimum(a, b), c)[[0, 2]] / CELL).astype(int); hi = np.floor(np.maximum(np.maximum(a, b), c)[[0, 2]] / CELL).astype(int)
                for i in range(lo[0], hi[0] + 1):
                    for j in range(lo[1], hi[1] + 1): self.g[(i, j)].append(k)
    def at(self, x, z):
        out = []
        for k in self.g.get((int(np.floor(x / CELL)), int(np.floor(z / CELL))), ()):
            a, b, c = self.T[k]; d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-12: continue
            l0 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d; l1 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d; l2 = 1 - l0 - l1
            if l0 >= -1e-6 and l1 >= -1e-6 and l2 >= -1e-6: out.append(l0 * a[1] + l1 * b[1] + l2 * c[1])
        return out
    def covered(self, p): return any(abs(y - p[1]) < NEAR_Y for y in self.at(p[0], p[2]))

def cliffside(faces, hf, rd, BC, cfg, log):
    """the hand fill's faces on the sea side of the named stretch that the course does not have ground for yet"""
    from common import WORK
    c0, c1 = cfg.get('patch3_cliffside', [12, 70]); reach = float(cfg.get('patch3_reach', REACH))
    csv_ = os.path.join(os.path.dirname(WORK), 'classic', 'courses', cfg['game'], cfg.get('gameplay', ''), 'src_course%s_centreline.csv' % cfg['course'])
    C = np.array([[float(x) for x in ln.split(',')[:3]] for ln in open(csv_) if ln.strip() and not ln.startswith('#')]); C = C[c0:c1 + 1]
    L = np.c_[C[:, 0] + rd['ox'], BC.ZS * C[:, 2] + rd['oz']]                                        # the stretch in the build's plan (x, z)
    T = np.gradient(L, axis=0); T /= np.linalg.norm(T, axis=1)[:, None]; N = np.c_[-T[:, 1], T[:, 0]]
    G = Ground(faces)
    # the sea side: the side with less ground 15 m and 30 m out
    cov = [np.mean([bool(G.at(*(p + s * d * n))) for p, n in zip(L, N) for d in (15.0, 30.0)]) for s in (1, -1)]; side = 1 if cov[0] < cov[1] else -1
    log('       patch 3 cliff side: cells %d .. %d of the 1995 centre line (%.0f m) ; ground found 15 / 30 m out: %.0f %% on one side, %.0f %% on the other -> the sea side is the %s one' % (c0, c1, np.linalg.norm(np.diff(L, axis=0), axis=1).sum(), 100 * cov[0], 100 * cov[1], 'first' if side == 1 else 'second'))
    kinds = collections.Counter(); keep = []; why = collections.Counter()
    for fc in hf:
        k = str(fc[1]).rstrip('0123456789_')
        if k not in ('hf_terrain', 'hf_weld', 'hf_cliff'): why['not ground (roof, lid)'] += 1; continue
        P = np.asarray(fc[2], float); c = P.mean(0); d = np.linalg.norm(L - c[[0, 2]], axis=1); i = int(d.argmin())
        if d[i] > reach: why['beyond the reach'] += 1; continue
        if i in (0, len(L) - 1) and abs(float((c[[0, 2]] - L[i]) @ T[i])) > 6.0: why['before or after the stretch'] += 1; continue
        if float((c[[0, 2]] - L[i]) @ N[i]) * side < 0.5: why['land side of the road'] += 1; continue
        pts = list(P) + [c] + [(P[j] + P[(j + 1) % len(P)]) / 2 for j in range(len(P))]
        if all(G.covered(p) for p in pts): why['the course has ground there already'] += 1; continue
        keep.append(fc); kinds[k] += 1
    log('       patch 3 cliff side: %d hand-fill faces taken %s ; left out %s' % (len(keep), dict(kinds), dict(why)))
    return keep

def generate(faces, rd, BC, cfg, log):
    import fill1995, overlay_bake as OB
    hm = fill1995.handmodel(cfg, rd, faces, log=log); hf = fill1995.handfill(cfg, rd)
    assert hm or hf, 'no hand model and no hand fill beside the course export'
    cs = cliffside(faces, hf, rd, BC, cfg, log) if hf else []
    new = [(str(fc[0]).split('|')[0], 'patch3_' + str(fc[1]), [tuple(map(float, p)) for p in fc[2]], [tuple(map(float, u)) for u in fc[3]]) for fc in hm + cs]
    new = [(OB.ORIGIN.get(m, m), s, P, U) for m, s, P, U in new]                                    # a composed tile is named by the tile under it
    # nothing may lie in the plane of a face that is there, or of another new face
    road = np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]]; n0 = len(faces); dropped = 0
    for _ in range(3):
        all_ = list(faces) + new; bad = {max(p[0], p[1]) - n0 for p in OB.find_pairs(all_, road, active=set(range(n0, len(all_)))) if max(p[0], p[1]) >= n0}
        if not bad: break
        new = [fc for k, fc in enumerate(new) if k not in bad]; dropped += len(bad)
    area = lambda P: sum(0.5 * np.linalg.norm(np.cross(np.subtract(P[i], P[0]), np.subtract(P[i + 1], P[0]))) for i in range(1, len(P) - 1))
    log('       patch 3: %d faces (%.0f m2): hand model %d, cliff side %d ; left out because they would lie in the plane of another face: %d ; tiles %s' % (
        len(new), sum(area(fc[2]) for fc in new), sum(1 for fc in new if fc[1].startswith('patch3_hm')), sum(1 for fc in new if fc[1].startswith('patch3_hf')), dropped, dict(collections.Counter(fc[0][-22:] for fc in new).most_common(8))))
    return new

def write(faces, rd, BC, cfg, number, needs, log):
    import coursepatch
    from common import WORK
    out = generate(faces, rd, BC, cfg, log); ox, oz = rd['ox'], rd['oz']; r = lambda x: round(float(x), 4); add = []
    for mat, sec, P, U in out:                                         # triangles only ("all new geometry should be triangulated")
        for i in range(1, len(P) - 1): add.append(dict(tile=mat, p=[[r(P[k][0] - ox), r(P[k][1]), r(-(P[k][2] - oz))] for k in (0, i, i + 1)], uv=[[r(U[k][0]), r(U[k][1])] for k in (0, i, i + 1)]))
    head = dict(format='sr3lab course patch', version=1, course=dict(game=cfg['game'], course=str(cfg['course']), name=cfg['name']),
                base=dict(course_export_sha1=coursepatch.export_sha1(BC.HI), needs=list(needs)), made_by='patch3_1995.py (generated: the plateau hand model, the cliff side of the old hand fill)',
                space='the build decoded back (preview_obj.py): x, y up, z = -gameZ of the 1995 course, metres; uv as Blender has them (v up)')
    path = cfg['patch3_out'] if cfg.get('patch3_out') else os.path.join(WORK, 'courses', '%s.%s.patch.%d.json' % (cfg['game'], cfg['name'], number))
    with open(path, 'w', newline='\n') as fo:
        fo.write('{\n' + ''.join(' %s: %s,\n' % (json.dumps(k), json.dumps(v)) for k, v in head.items()))
        fo.write(' "add": [\n' + ',\n'.join('  ' + json.dumps(a) for a in add) + '\n ],\n "move": [\n ]\n}\n')
    log('       patch %d written: %d triangles, %d bytes -> %s' % (number, len(add), os.path.getsize(path), path)); return path
