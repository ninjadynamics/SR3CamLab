"""A course's hand patch (courses/<game>.<course name>.patch.<number>.json, e.g. src.mountain.patch.1.json, made from patch.blend by blendpatch/patch_to_json.py) applied to the
1995 faces of a build: faces to add and corners of original polygons to move (user, 2026-10-09: "I'll try to patch the holes on
blender myself, you can then diff the .blend files and ship only the patches"). Course setting: "patch": true (every numbered file of the course, in order) or the numbers wanted.

The file's coordinates are those of the build decoded back (preview_obj.py): (SR3 x - ox, y, -(SR3 z - oz)), corners in the same order
(checked on a build, blendpatch/check_build.py: with the order reversed all 73 faces of Mountain's patch faced the other way).
A patch made on another export of the course is refused (base.course_export_sha1)."""
import json, hashlib, collections, math
import numpy as np

TOL = 0.0015                                                          # m: the decoded scene is 32-bit numbers written with 4 decimals
def export_sha1(path):
    """the 1995 course export without its comment lines (an older exporter worded the first line differently)"""
    return hashlib.sha1(b'\n'.join(l for l in open(path, 'rb').read().split(b'\n') if not l.startswith(b'#'))).hexdigest()
def _area_np(P): P = np.asarray(P, float); return 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))      # (as it was written: the reference)
def _area(P):
    """0.5 |(P1 - P0) x (P2 - P0)|, to the bit what _area_np gives: the cross product term by term, the length as sqrt(x.dot(x)) like np.linalg.norm"""
    a = P[0]; b = P[1]; c = P[2]; ax = float(a[0]); ay = float(a[1]); az = float(a[2])
    ux = float(b[0]) - ax; uy = float(b[1]) - ay; uz = float(b[2]) - az; vx = float(c[0]) - ax; vy = float(c[1]) - ay; vz = float(c[2]) - az
    n = np.array((uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)); return 0.5 * math.sqrt(float(n.dot(n)))
def _uvarea(U):
    a = U[0]; b = U[1]; c = U[2]; a0 = float(a[0]); a1 = float(a[1]); return 0.5 * abs((float(b[0]) - a0) * (float(c[1]) - a1) - (float(b[1]) - a1) * (float(c[0]) - a0))
def unmapped(P, U):                                                   # a face with a surface whose picture has none
    ar = _area(P); return ar > 1e-6 and _uvarea(U) < 1e-7 * max(1.0, ar)

def continue_uv(add, faces, log):
    """Patch faces drawn without a mapping (Blender gives a new face the uv of one corner three times) take their tile on from a
    neighbour of the same tile across a shared edge, at the neighbour's density, unfolded flat about that edge; a face with no such
    neighbour gets the tile's usual density, laid flat in its own plane. -> number continued, number laid flat"""
    todo = [k for k, fc in enumerate(add) if unmapped(fc[2], fc[3])]
    if not todo: return 0, 0
    tiles = {str(add[k][0]) for k in todo}; base = str.split
    pool = []; tile_of = []
    for fc in faces:
        t_ = str(fc[0]).split('|')[0]
        if t_ in tiles and len(fc[2]) >= 3 and not unmapped(fc[2][:3], fc[3][:3]): pool.append((fc[2], fc[3])); tile_of.append(t_)
    by_tile = collections.defaultdict(list)                           # per tile: its mapped faces, and their corners as one array (a triangle's fourth row far away)
    for (p, u), tt in zip(pool, tile_of): by_tile[tt].append((np.asarray(p, float), np.asarray(u, float)))
    def corners(cl):
        Q = np.full((len(cl), max([len(q) for q, _ in cl] + [1]), 3), 1e30)
        for i_, (q, _) in enumerate(cl): Q[i_, :len(q)] = q
        return Q
    pool_q = {tt: corners(cl) for tt, cl in by_tile.items()}
    def touching(cl, Q, Pk):
        """the candidates of cl that have two corners at corners of the face Pk (the test edge_uv makes per candidate), in their order"""
        if not len(cl): return []
        d = np.linalg.norm(Q[:, None, :, :] - Pk[None, :3, None, :], axis=3).min(2); return [cl[i_] for i_ in np.nonzero((d < TOL).sum(1) >= 2)[0].tolist()]
    def edge_uv(k):
        """-> uv of the three corners of add[k] from a mapped face of its tile that shares an edge, or None"""
        P = np.asarray(add[k][2], float); t = str(add[k][0]); best = None
        cands = [(np.asarray(add[j][2], float), np.asarray(add[j][3], float)) for j in range(len(add)) if j != k and j not in left and str(add[j][0]) == t]
        cands = touching(cands, corners(cands), P) + (touching(by_tile[t], pool_q[t], P) if t in by_tile else [])
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

def remove(faces, rem, sr3, path, log, split=None, keep=()):
    """version 2: triangles of the decoded build to take out. A triangle is three corners of ONE polygon of the build, in that polygon's own
    order (a triangle listed the other way round is the back the build writes for a polygon seen from both sides: the polygon goes only
    when its front goes). A polygon all of whose triangles go is dropped; one that keeps some is cut down to them (corner by corner,
    keeping its mapping)."""
    if split is not None:                                              # the decoded build shows a polygon whose tile repeats more than twice as the PIECES the build cut it into (build_classic.uv_split):
        B_ = np.array([[sr3(p) for p in r['p']] for r in rem], float).reshape(-1, 3)      # a polygon one of whose pieces has a corner of a triangle to remove, at a place that is no corner of the polygon itself, is cut the same way here
        faces = list(faces); kx = np.argsort(B_[:, 0], kind='stable'); bx = B_[kx, 0]; ncut = 0; out_ = []
        fit_ = None
        try: import fastbuild; fit_ = fastbuild._uv_fits([fc[:4] for fc in faces], 1.999)          # which polygons the build does not cut at all (uv_split's own test, for all at once)
        except Exception: fit_ = None
        if fit_ is not None and getattr(split, '__defaults__', None) != (1.999,): fit_ = None           # (another splitter than the build's: ask it for every polygon)
        for kf_, fc in enumerate(faces):
            if id(fc) in keep or len(fc[2]) < 3: out_.append(fc); continue
            if fit_ is not None and fit_[kf_]: out_.append(fc); continue
            pcs, n = split([tuple(fc[:4])])
            if not n: out_.append(fc); continue
            P = np.asarray(fc[2], float); lo, hi = np.searchsorted(bx, [P[:, 0].min() - TOL, P[:, 0].max() + TOL]); cand = B_[kx[lo:hi]]
            cand = cand[np.all((cand >= P.min(0) - TOL) & (cand <= P.max(0) + TOL), axis=1)]
            Q = np.array([p for pc in pcs for p in pc[2]], float)
            if len(cand) and any(np.linalg.norm(Q - c, axis=1).min() < TOL and np.linalg.norm(P - c, axis=1).min() >= TOL for c in cand[:400]):
                out_ += [(pc[0], pc[1], [tuple(p) for p in pc[2]], [tuple(u) for u in pc[3]]) + tuple(fc[4:]) for pc in pcs]; ncut += 1
            else: out_.append(fc)
        faces = out_; log('       patch %s: %d polygons cut into the pieces the build shows (their tile repeats more than twice), so single pieces can be removed' % (path.replace(chr(92), '/').split('/')[-1], ncut))
    C = np.array([p for fc in faces for p in fc[2]], float); n_ = [len(fc[2]) for fc in faces]; own = np.repeat(np.arange(len(faces)), n_); first = np.concatenate([[0], np.cumsum(n_)[:-1]])
    order = np.argsort(C[:, 0], kind='stable'); xs = C[order, 0]
    def at(b):
        lo, hi = np.searchsorted(xs, [b[0] - TOL, b[0] + TOL]); i = order[lo:hi]; return i[np.linalg.norm(C[i] - b, axis=1) < TOL]
    cut = collections.defaultdict(list); lost = back = 0
    for r in rem:
        B = np.array([sr3(p) for p in r['p']]); a = [at(b) for b in B]; best = None; anyp = False
        for k in sorted(set(own[a[0]].tolist()) & set(own[a[1]].tolist()) & set(own[a[2]].tolist())):
            anyp = True; n = n_[k]
            for i0 in a[0][own[a[0]] == k] - first[k]:
                for i1 in a[1][own[a[1]] == k] - first[k]:
                    for i2 in a[2][own[a[2]] == k] - first[k]:
                        if len({int(i0), int(i1), int(i2)}) < 3: continue
                        t = (int(i0), int(i1), int(i2)); fwd = ((t[1] - t[0]) % n) < ((t[2] - t[0]) % n)
                        if fwd and frozenset(t) not in [frozenset(x) for x in cut[k]] and best is None: best = (k, t)
        if best is not None: cut[best[0]].append(best[1])
        elif anyp: back += 1
        else: lost += 1
    out = []; whole = trimmed = stuck = 0
    for k, fc in enumerate(faces):
        if k not in cut: out.append(fc); continue
        idx = list(range(n_[k])); todo = [set(t) for t in cut[k]]; go = True
        while todo and go and len(idx) >= 3:
            go = False
            for j in range(len(idx)):
                ear = {idx[j - 1], idx[j], idx[(j + 1) % len(idx)]}
                if ear in todo: todo.remove(ear); idx.pop(j); go = True; break
        if todo and len(idx) >= 3: stuck += 1; out.append(fc); continue
        if len(idx) < 3: whole += 1; continue
        trimmed += 1; out.append((fc[0], fc[1], [fc[2][i] for i in idx], [fc[3][i] for i in idx]) + tuple(fc[4:]))
    log('       patch %s: %d triangles to remove -> %d polygons dropped, %d cut down ; %d are the back of a two-sided polygon (it goes with its front) ; NOT FOUND among the polygons of this build: %d ; polygons that could not be cut down: %d' % (
        path.replace('\\', '/').split('/')[-1], len(rem), whole, trimmed, back, lost, stuck))
    return out

def apply(faces, path, ox, oz, export, log, fill_uv=True, applied=(), settings=None, pixels=None, save=None, origin=None, split=None, keep=()):
    """faces: the build's (material, section, [corners in SR3 coordinates], [uv]) -> the same list with the patch applied"""
    J = json.load(open(path)); assert J.get('format') == 'sr3lab course patch' and J.get('version') in (1, 2, 3), 'not a course patch file this importer knows: ' + path
    want = J['base'].get('course_export_sha1'); got = export_sha1(export)
    if want and want != got: raise SystemExit('PATCH REFUSED: %s was made on another export of the course (%s; this build reads %s)' % (path, want[:12], got[:12]))
    miss = [k for k in J['base'].get('needs', []) if k not in applied]                                 # patches are made one on the result of the other (owner, 2026-10-09)
    if miss: raise SystemExit('PATCH REFUSED: %s needs patch %s of this course applied before it' % (path, miss))
    if settings is not None:                                           # build settings a patch brings along (patch 2: the sea sheet is left whole), merged one level deep by the importer
        for k, v in J.get('settings', {}).items(): settings[k] = {**settings.get(k, {}), **v} if isinstance(v, dict) else v
    sr3 = lambda p: (float(p[0]) + ox, float(p[1]), -float(p[2]) + oz)
    # corners to move: an edited triangle is found as three corners of ONE polygon of the build (other polygons with a corner at the same place stay)
    faces = list(faces); C = np.array([p for fc in faces for p in fc[2]], float); own = np.repeat(np.arange(len(faces)), [len(fc[2]) for fc in faces]); first = np.concatenate([[0], np.cumsum([len(fc[2]) for fc in faces])[:-1]])
    moves = collections.defaultdict(dict); lost = 0
    for m in J['move']:
        B = np.array([sr3(p) for p in m['before']]); A = [sr3(p) for p in m['after']]; at = [np.nonzero(np.linalg.norm(C - b, axis=1) < TOL)[0] for b in B]
        fs = set(own[at[0]].tolist()) & set(own[at[1]].tolist()) & set(own[at[2]].tolist())
        if not fs:
            if 'fallback' in m: J.setdefault('remove', []).append(dict(p=m['before'])); J['add'].append(m['fallback']); fell = locals().get('fell', 0) + 1; continue      # a move that carries its own remove + add (2026-10-13: a moved board whose triangle is a PIECE of a polygon the build cut up)
            lost += 1; continue
        for c in range(3):
            if np.linalg.norm(B[c] - np.array(A[c])) < 1e-6: continue
            for i in at[c].tolist():
                if int(own[i]) in fs: moves[int(own[i])][i - int(first[own[i]])] = A[c]
    if locals().get('fell'): log('       patch %s: %d moved faces are pieces of cut-up polygons: taken out and added again instead' % (path.replace(chr(92), '/').split('/')[-1], fell))
    if lost: raise SystemExit('PATCH REFUSED: %d of the %d faces whose corners move are not among the polygons of this build' % (lost, len(J['move'])))
    for k, mv in moves.items(): fc = faces[k]; P = list(fc[2]); [P.__setitem__(c, a) for c, a in mv.items()]; faces[k] = (fc[0], fc[1], P) + tuple(fc[3:])
    if J.get('whole_polygons'): split = None                            # OPT-IN by the patch file (genpatch1995.py): its triangles to remove are corners of the importer's own polygons, never of the pieces a build cuts them into
    nrem = remove(faces, J.get('remove', []), sr3, path, log, split=split, keep=keep) if J.get('remove') else None
    if nrem is not None: faces = nrem
    if J.get('bake'):                                                   # version 3: pictures composed from the course tiles (facadebake.py), named as tiles of their own
        import facadebake
        assert pixels is not None and save is not None, 'this patch composes pictures: the importer must hand over its tile reader'
        facadebake.apply(J['bake'], pixels, save, origin, log)
    add = [(f_['tile'], 'patch', [sr3(p) for p in f_['p']], [tuple(u) for u in f_['uv']]) for f_ in J['add']]
    add = [fc for fc in add if _area(fc[2]) > 1e-9]; cont = flat = 0
    if fill_uv: cont, flat = continue_uv(add, faces, log)
    log('       patch %s: %d faces added (%.0f m2; %d had no mapping: %d continued from a neighbour, %d laid flat), %d corners of %d polygons moved' % (path.replace('\\', '/').split('/')[-1], len(add), sum(_area(fc[2]) for fc in add), cont + flat, cont, flat, sum(len(v) for v in moves.values()), len(moves)))
    return faces + add
