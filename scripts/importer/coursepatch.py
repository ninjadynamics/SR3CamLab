"""A course's hand patch (courses/<game>.<course name>.patch.<number>.json, e.g. src.mountain.patch.1.json, made from patch.blend by blendpatch/patch_to_json.py) applied to the
1995 faces of a build: faces to add and corners of original polygons to move (user, 2026-10-09: "I'll try to patch the holes on
blender myself, you can then diff the .blend files and ship only the patches"). Course setting: "patch": true (every numbered file of the course, in order) or the numbers wanted.

The file's coordinates are those of the build decoded back (preview_obj.py): (SR3 x - ox, y, -(SR3 z - oz)), corners in the same order
(checked on a build, blendpatch/check_build.py: with the order reversed all 73 faces of Mountain's patch faced the other way).
A patch made on another export of the course is refused (base.course_export_sha1)."""
import json, hashlib, collections
import numpy as np

TOL = 0.0015                                                          # m: the decoded scene is 32-bit numbers written with 4 decimals
def export_sha1(path):
    """the 1995 course export without its comment lines (an older exporter worded the first line differently)"""
    return hashlib.sha1(b'\n'.join(l for l in open(path, 'rb').read().split(b'\n') if not l.startswith(b'#'))).hexdigest()
def _area(P): P = np.asarray(P, float); return 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
def _uvarea(U): U = np.asarray(U, float); a = U[1] - U[0]; b = U[2] - U[0]; return 0.5 * abs(float(a[0] * b[1] - a[1] * b[0]))
def unmapped(P, U): return _area(P) > 1e-6 and _uvarea(U) < 1e-7 * max(1.0, _area(P))      # a face with a surface whose picture has none

def continue_uv(add, faces, log):
    """Patch faces drawn without a mapping (Blender gives a new face the uv of one corner three times) take their tile on from a
    neighbour of the same tile across a shared edge, at the neighbour's density, unfolded flat about that edge; a face with no such
    neighbour gets the tile's usual density, laid flat in its own plane. -> number continued, number laid flat"""
    todo = [k for k, fc in enumerate(add) if unmapped(fc[2], fc[3])]
    if not todo: return 0, 0
    tiles = {str(add[k][0]) for k in todo}; base = str.split
    pool = [(fc[2], fc[3]) for fc in faces if str(fc[0]).split('|')[0] in tiles and len(fc[2]) >= 3 and not unmapped(fc[2][:3], fc[3][:3])]
    tile_of = [str(fc[0]).split('|')[0] for fc in faces if str(fc[0]).split('|')[0] in tiles and len(fc[2]) >= 3 and not unmapped(fc[2][:3], fc[3][:3])]
    def edge_uv(k):
        """-> uv of the three corners of add[k] from a mapped face of its tile that shares an edge, or None"""
        P = np.asarray(add[k][2], float); t = str(add[k][0]); best = None
        cands = [(np.asarray(add[j][2], float), np.asarray(add[j][3], float)) for j in range(len(add)) if j != k and j not in left and str(add[j][0]) == t]
        cands += [(np.asarray(p, float), np.asarray(u, float)) for (p, u), tt in zip(pool, tile_of) if tt == t]
        for Q, UQ in cands:
            hit = {}                                                  # corner of ours -> corner of the neighbour at the same place
            for i in range(3):
                d = np.linalg.norm(Q - P[i], axis=1); j = int(np.argmin(d))
                if d[j] < TOL: hit[i] = j
            if len(hit) < 2: continue
            (ia, ja), (ib, jb) = list(hit.items())[:2]; ic = 3 - ia - ib; A, B = P[ia], P[ib]; ua, ub = UQ[ja], UQ[jb]; e = B - A; le = float(np.linalg.norm(e)); du = ub - ua; lu = float(np.linalg.norm(du))
            if le < 1e-6 or lu < 1e-9: continue
            jn = next((j for j in range(len(Q)) if j not in (ja, jb) and np.linalg.norm(np.cross(Q[j] - A, e)) / le > 1e-4), None)
            if jn is None: continue
            s = float((P[ic] - A) @ e) / le ** 2; h = float(np.linalg.norm(np.cross(P[ic] - A, e))) / le          # along the edge (in edge lengths), away from it (m)
            perp = np.array([-du[1], du[0]]) / lu; side = float(perp @ (UQ[jn] - ua)); perp = -perp if side > 0 else perp      # unfolded: on the other side of the edge from the neighbour
            U = np.zeros((3, 2)); U[ia] = ua; U[ib] = ub; U[ic] = ua + s * du + perp * h * (lu / le)
            if best is None or le > best[0]: best = (le, U)
        return None if best is None else best[1]
    left = set(todo); cont = 0
    for _ in range(len(todo)):
        done = []
        for k in sorted(left):
            U = edge_uv(k)
            if U is not None: add[k] = (add[k][0], add[k][1], add[k][2], [tuple(float(x) for x in u) for u in U]); done.append(k)
        if not done: break
        left -= set(done); cont += len(done)
    flat = 0
    for k in sorted(left):                                            # no mapped neighbour of the tile: its usual density, flat in the face's plane
        t = str(add[k][0]); dens = [np.sqrt(_uvarea(u[:3]) / _area(p[:3])) for (p, u), tt in zip(pool, tile_of) if tt == t and _area(p[:3]) > 1e-4]
        dn = float(np.median(dens)) if dens else 0.25; P = np.asarray(add[k][2], float); n = np.cross(P[1] - P[0], P[2] - P[0]); n /= np.linalg.norm(n)
        e1 = np.cross([0.0, 1.0, 0.0], n); e1 = (e1 / np.linalg.norm(e1)) if np.linalg.norm(e1) > 1e-6 else np.array([1.0, 0.0, 0.0]); e2 = np.cross(n, e1)
        add[k] = (add[k][0], add[k][1], add[k][2], [(float((p - P[0]) @ e1) * dn, float((p - P[0]) @ e2) * dn) for p in P]); flat += 1
    return cont, flat

def apply(faces, path, ox, oz, export, log, fill_uv=True):
    """faces: the build's (material, section, [corners in SR3 coordinates], [uv]) -> the same list with the patch applied"""
    J = json.load(open(path)); assert J.get('format') == 'sr3lab course patch' and J.get('version') == 1, 'not a course patch file this importer knows: ' + path
    want = J['base'].get('course_export_sha1'); got = export_sha1(export)
    if want and want != got: raise SystemExit('PATCH REFUSED: %s was made on another export of the course (%s; this build reads %s)' % (path, want[:12], got[:12]))
    sr3 = lambda p: (float(p[0]) + ox, float(p[1]), -float(p[2]) + oz)
    # corners to move: an edited triangle is found as three corners of ONE polygon of the build (other polygons with a corner at the same place stay)
    faces = list(faces); C = np.array([p for fc in faces for p in fc[2]], float); own = np.repeat(np.arange(len(faces)), [len(fc[2]) for fc in faces]); first = np.concatenate([[0], np.cumsum([len(fc[2]) for fc in faces])[:-1]])
    moves = collections.defaultdict(dict); lost = 0
    for m in J['move']:
        B = np.array([sr3(p) for p in m['before']]); A = [sr3(p) for p in m['after']]; at = [np.nonzero(np.linalg.norm(C - b, axis=1) < TOL)[0] for b in B]
        fs = set(own[at[0]].tolist()) & set(own[at[1]].tolist()) & set(own[at[2]].tolist())
        if not fs: lost += 1; continue
        for c in range(3):
            if np.linalg.norm(B[c] - np.array(A[c])) < 1e-6: continue
            for i in at[c].tolist():
                if int(own[i]) in fs: moves[int(own[i])][i - int(first[own[i]])] = A[c]
    if lost: raise SystemExit('PATCH REFUSED: %d of the %d faces whose corners move are not among the polygons of this build' % (lost, len(J['move'])))
    for k, mv in moves.items(): fc = faces[k]; P = list(fc[2]); [P.__setitem__(c, a) for c, a in mv.items()]; faces[k] = (fc[0], fc[1], P) + tuple(fc[3:])
    add = [(f_['tile'], 'patch', [sr3(p) for p in f_['p']], [tuple(u) for u in f_['uv']]) for f_ in J['add']]
    add = [fc for fc in add if _area(fc[2]) > 1e-9]; cont = flat = 0
    if fill_uv: cont, flat = continue_uv(add, faces, log)
    log('       patch %s: %d faces added (%.0f m2; %d had no mapping: %d continued from a neighbour, %d laid flat), %d corners of %d polygons moved' % (path.replace('\\', '/').split('/')[-1], len(add), sum(_area(fc[2]) for fc in add), cont + flat, cont, flat, sum(len(v) for v in moves.values()), len(moves)))
    return faces + add
