"""A course's hand patch (courses/<game>.<course name>.patch.<number>.json, e.g. src.mountain.patch.1.json, made from patch.blend by blendpatch/patch_to_json.py; since 2026-10-16
the files ship as one zip per course, <game>.<course name>.patches.zip, unpacked beside it by the chain's first step: patchzip.py) applied to the
1995 faces of a build: faces to add and corners of original polygons to move (user, 2026-10-09: "I'll try to patch the holes on
blender myself, you can then diff the .blend files and ship only the patches"). Course setting: "patch": true (every numbered file of the course, in order) or the numbers wanted.

The file's coordinates are those of the build decoded back (preview_obj.py): (SR3 x - ox, y, -(SR3 z - oz)), corners in the same order
(checked on a build, blendpatch/check_build.py: with the order reversed all 73 faces of Mountain's patch faced the other way).
A patch made on another export of the course is refused (base.course_export_sha1).
Without numpy since 2026-10-16 (kb 31): plain floats, each distance as numpy's norm makes it ((x x + y y) + z z for a row, npexact.ddot's order
for a 3-vector), corners found through x-sorted windows (bisect) in the order the numpy searches gave them; the numpy original of each
function stays as _old_<name> (the reference)."""
import json, hashlib, collections, math, bisect, array
import npexact

TOL = 0.0015                                                          # m: the decoded scene is 32-bit numbers written with 4 decimals
def export_sha1(path):
    """the 1995 course export without its comment lines (an older exporter worded the first line differently)"""
    return hashlib.sha1(b'\n'.join(l for l in open(path, 'rb').read().split(b'\n') if not l.startswith(b'#'))).hexdigest()
def _area_np(P):                                                      # (as it was written: the reference)
    import numpy as np
    P = np.asarray(P, float); return 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
def _area(P):
    """0.5 |(P1 - P0) x (P2 - P0)|, to the bit what _area_np gives: the cross product term by term, the length as sqrt(x.dot(x)) like np.linalg.norm"""
    a = P[0]; b = P[1]; c = P[2]; ax = float(a[0]); ay = float(a[1]); az = float(a[2])
    ux = float(b[0]) - ax; uy = float(b[1]) - ay; uz = float(b[2]) - az; vx = float(c[0]) - ax; vy = float(c[1]) - ay; vz = float(c[2]) - az
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx); return 0.5 * math.sqrt(npexact.ddot(n, n, 0))      # n.dot(n) of a fresh array
def _uvarea(U):
    a = U[0]; b = U[1]; c = U[2]; a0 = float(a[0]); a1 = float(a[1]); return 0.5 * abs((float(b[0]) - a0) * (float(c[1]) - a1) - (float(b[1]) - a1) * (float(c[0]) - a0))
def unmapped(P, U):                                                   # a face with a surface whose picture has none
    ar = _area(P); return ar > 1e-6 and _uvarea(U) < 1e-7 * max(1.0, ar)

def _f3(p): return (float(p[0]), float(p[1]), float(p[2]))
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _nrow(a, b):                                                      # np.linalg.norm(A - b, axis=1) of one row: sqrt((dx dx + dy dy) + dz dz)
    dx = a[0] - b[0]; dy = a[1] - b[1]; dz = a[2] - b[2]; return math.sqrt((dx * dx + dy * dy) + dz * dz)
def _nvec(v): return math.sqrt(npexact.ddot(v, v, 0))                # np.linalg.norm(v) of a fresh 1-D array (2 or 3 numbers)
def _uv_fits(UV, maxspan):
    """fastbuild._uv_fits for one polygon (uv_split's own test): v turned, (lo - floor(lo + 1e-6) + (hi - lo)).max() <= maxspan; False when
    the polygon has no uv (it is then asked as the numpy code asked every polygon)"""
    if not len(UV): return False
    us = [float(u[0]) for u in UV]; vs = [1.0 - float(u[1]) for u in UV]; a0, b0, a1, b1 = min(us), max(us), min(vs), max(vs)
    return max((a0 - math.floor(a0 + 1e-6)) + (b0 - a0), (a1 - math.floor(a1 + 1e-6)) + (b1 - a1)) <= maxspan
def _far(cb, nc, P, tol):
    """cp_cut's second test for some candidate: at least tol from every corner of P, no distance NaN (its mindist, the same sums). cp_cut
    says yes only for such a candidate, so without one the polygon is kept whatever its pieces are (2026-10-16: uv_split skipped then)"""
    for k in range(nc):
        c0 = cb[3 * k]; c1 = cb[3 * k + 1]; c2 = cb[3 * k + 2]; m = math.inf; nan = False
        for q in P:
            dx = q[0] - c0; dy = q[1] - c1; dz = q[2] - c2; d = math.sqrt((dx * dx + dy * dy) + dz * dz)
            if d != d: nan = True
            elif d < m: m = d
        if not nan and m >= tol: return True
    return False
def _median(v):
    s = sorted(v); n = len(s); return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2      # np.median: the middle one, or the mean of the two
def continue_uv(add, faces, log):
    """Patch faces drawn without a mapping (Blender gives a new face the uv of one corner three times) take their tile on from a
    neighbour of the same tile across a shared edge, at the neighbour's density, unfolded flat about that edge; a face with no such
    neighbour gets the tile's usual density, laid flat in its own plane. -> number continued, number laid flat"""
    todo = [k for k, fc in enumerate(add) if unmapped(fc[2], fc[3])]
    if not todo: return 0, 0
    tiles = {str(add[k][0]) for k in todo}
    pool = []; tile_of = []
    for fc in faces:
        t_ = str(fc[0]).split('|')[0]
        if t_ in tiles and len(fc[2]) >= 3 and not unmapped(fc[2][:3], fc[3][:3]): pool.append((fc[2], fc[3])); tile_of.append(t_)
    by_tile = collections.defaultdict(list)                           # per tile: its mapped faces as Python numbers
    for (p, u), tt in zip(pool, tile_of): by_tile[tt].append(([_f3(q) for q in p], [(float(q[0]), float(q[1])) for q in u]))
    def touching(cl, Pk):
        """the candidates of cl that have two corners at corners of the face Pk (the test edge_uv makes per candidate), in their order
        (numpy: np.linalg.norm(Q[:, None] - Pk[None, :3, None], axis=3).min(2) < TOL, two or more; a quick box test first, wider than TOL)"""
        out = []; P3 = Pk[:3]; w = 2 * TOL
        for c in cl:
            Q = c[0]
            if not any(abs(q[0] - p[0]) < w and abs(q[1] - p[1]) < w and abs(q[2] - p[2]) < w for q in Q for p in P3): continue
            if sum(1 for p in P3 if min(_nrow(q, p) for q in Q) < TOL) >= 2: out.append(c)
        return out
    xidx = {}
    def touching_tile(t, Pk):
        """touching(by_tile[t], Pk) through the tile's corners sorted by x (2026-10-16): a face passes touching's box test only when one of
        its corners lies within the box's margin of a corner of Pk in x, so the faces with such a corner, in their order, are all the box
        test can pass; touching then tests those as before"""
        if t not in xidx:
            xs = sorted((q[0], i) for i, (Q, _) in enumerate(by_tile[t]) for q in Q if q[0] == q[0])      # (a NaN corner passes no box test)
            xidx[t] = ([x for x, _ in xs], [i for _, i in xs])
        xs, fi = xidx[t]; w = 4 * TOL; cl = by_tile[t]; near = set()      # (twice the box test's margin: no rounding of the bounds can drop a face)
        for p in Pk[:3]: near.update(fi[bisect.bisect_left(xs, p[0] - w):bisect.bisect_right(xs, p[0] + w)])
        return touching([cl[i] for i in sorted(near)], Pk)
    def edge_uv(k):
        """-> uv of the three corners of add[k] from a mapped face of its tile that shares an edge, or None"""
        P = [_f3(q) for q in add[k][2]]; t = str(add[k][0]); best = None
        cands = [([_f3(q) for q in add[j][2]], [(float(q[0]), float(q[1])) for q in add[j][3]]) for j in range(len(add)) if j != k and j not in left and str(add[j][0]) == t]
        cands = touching(cands, P) + (touching_tile(t, P) if t in by_tile else [])
        for Q, UQ in cands:
            hit = {}                                                  # corner of ours -> corner of the neighbour at the same place
            for i in range(3):
                d = [_nrow(q, P[i]) for q in Q]; j = d.index(min(d))      # np.argmin: the first of equals
                if d[j] < TOL: hit[i] = j
            if len(hit) < 2: continue
            (ia, ja), (ib, jb) = list(hit.items())[:2]; ic = 3 - ia - ib; A, B = P[ia], P[ib]; ua, ub = UQ[ja], UQ[jb]; e = _sub(B, A); le = _nvec(e); du = (ub[0] - ua[0], ub[1] - ua[1]); lu = _nvec(du)
            if le < 1e-6 or lu < 1e-9: continue
            jn = next((j for j in range(len(Q)) if j not in (ja, jb) and _nvec(_cross(_sub(Q[j], A), e)) / le > 1e-4), None)
            if jn is None: continue
            s = npexact.ddot(_sub(P[ic], A), e, 0) / le ** 2; h = _nvec(_cross(_sub(P[ic], A), e)) / le          # along the edge (in edge lengths), away from it (m)
            perp = (-du[1] / lu, du[0] / lu); side = npexact.ddot(perp, (UQ[jn][0] - ua[0], UQ[jn][1] - ua[1]), 0); perp = (-perp[0], -perp[1]) if side > 0 else perp      # unfolded: on the other side of the edge from the neighbour
            f = lu / le; U = [None, None, None]; U[ia] = ua; U[ib] = ub; U[ic] = tuple((ua[q] + s * du[q]) + (perp[q] * h) * f for q in (0, 1))
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
        t = str(add[k][0]); dens = [math.sqrt(_uvarea(u[:3]) / _area(p[:3])) for (p, u), tt in zip(pool, tile_of) if tt == t and _area(p[:3]) > 1e-4]
        dn = float(_median(dens)) if dens else 0.25; P = [_f3(q) for q in add[k][2]]; n = _cross(_sub(P[1], P[0]), _sub(P[2], P[0])); ln = _nvec(n); n = (n[0] / ln, n[1] / ln, n[2] / ln)
        e1 = _cross((0.0, 1.0, 0.0), n); l1 = _nvec(e1); e1 = (e1[0] / l1, e1[1] / l1, e1[2] / l1) if l1 > 1e-6 else (1.0, 0.0, 0.0); e2 = _cross(n, e1)
        add[k] = (add[k][0], add[k][1], add[k][2], [(npexact.ddot(_sub(_f3(p), P[0]), e1, 0) * dn, npexact.ddot(_sub(_f3(p), P[0]), e2, 0) * dn) for p in add[k][2]]); flat += 1
    return cont, flat

def _old_continue_uv(add, faces, log):
    """(the numpy original of continue_uv: the reference)"""
    import numpy as np
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

class _Corners:
    """every corner of the faces as Python numbers, with its polygon (own) and the polygon's first corner (first), sorted by x"""
    def __init__(self, faces):
        self.x = []; self.y = []; self.z = []; self.own = []; self.first = []; self.n = []
        for k, fc in enumerate(faces):
            self.first.append(len(self.x)); self.n.append(len(fc[2]))
            for p in fc[2]: self.x.append(float(p[0])); self.y.append(float(p[1])); self.z.append(float(p[2])); self.own.append(k)
        self.order = sorted(range(len(self.x)), key=self.x.__getitem__); self.xs = [self.x[i] for i in self.order]      # np.argsort(C[:, 0], kind='stable')
        self.X = array.array('d', [v for t in zip(self.x, self.y, self.z) for v in t]); self.O = array.array('q', self.order); self.XS = array.array('d', self.xs)
    def near_many(self, pts, wlo, whi, tol):
        """for every point b: the corners within tol of b among those whose x is in [b0 - wlo, b0 + whi) (np.searchsorted, side left), in x
        order (fastlm.c cp_near)"""
        import fastlm
        L = fastlm.lib(); nq = len(pts); Q = array.array('d', [v for b in pts for v in b]); cnt = array.array('q', bytes(8 * max(nq, 1))); ad = lambda a: a.buffer_info()[0]
        if not nq: return []
        L.cp_near(nq, ad(Q), ad(self.X), ad(self.O), ad(self.XS), len(self.O), wlo, whi, tol, ad(cnt), None, None)
        off = array.array('q', [0]) * (nq + 1)
        for q in range(nq): off[q + 1] = off[q] + cnt[q]
        out = array.array('q', bytes(8 * max(off[nq], 1))); L.cp_near(nq, ad(Q), ad(self.X), ad(self.O), ad(self.XS), len(self.O), wlo, whi, tol, ad(cnt), ad(off), ad(out))
        o = out.tolist(); return [o[off[q]:off[q + 1]] for q in range(nq)]
def remove(faces, rem, sr3, path, log, split=None, keep=()):
    """version 2: triangles of the decoded build to take out. A triangle is three corners of ONE polygon of the build, in that polygon's own
    order (a triangle listed the other way round is the back the build writes for a polygon seen from both sides: the polygon goes only
    when its front goes). A polygon all of whose triangles go is dropped; one that keeps some is cut down to them (corner by corner,
    keeping its mapping). (Python numbers in the numpy original's orders; _old_remove is that original.)"""
    if split is not None:                                              # the decoded build shows a polygon whose tile repeats more than twice as the PIECES the build cut it into (build_classic.uv_split):
        B_ = [_f3(sr3(p)) for r in rem for p in r['p']]                 # a polygon one of whose pieces has a corner of a triangle to remove, at a place that is no corner of the polygon itself, is cut the same way here
        kx = sorted(range(len(B_)), key=lambda i: B_[i][0]); bx = [B_[i][0] for i in kx]; faces = list(faces); ncut = 0; out_ = []
        import fastlm
        FL = fastlm.lib(); Bs = array.array('d', [v for i in kx for v in B_[i]]); cb = array.array('d', bytes(24 * 400)); ad = lambda a: a.buffer_info()[0]      # (the corners by x, as numpy took B_[kx])
        own_test = getattr(split, '__defaults__', None) == (1.999,)        # (the build's uv_split: polygons its own test passes are not cut at all)
        if own_test:                                                    # (2026-10-16) the build's uv_split through builduv.uv_split, its numpy-free twin (the same pieces in
            import builduv                                              # the same order, as plain floats; 0.8 ms -> a few us a polygon); the build's own when builduv refuses one
            def split(fl, _bc=split):
                try: return builduv.uv_split(fl)
                except ValueError: return _bc(fl)
        for fc in faces:
            if id(fc) in keep or len(fc[2]) < 3: out_.append(fc); continue
            if own_test and _uv_fits(fc[3], 1.999): out_.append(fc); continue
            P = [_f3(q) for q in fc[2]]; mn = [min(q[c] for q in P) for c in range(3)]; mx = [max(q[c] for q in P) for c in range(3)]
            mna = array.array('d', mn); mxa = array.array('d', mx)       # (named: the C reads them by address)
            nc = FL.cp_cand(ad(Bs), bisect.bisect_left(bx, mn[0] - TOL), bisect.bisect_left(bx, mx[0] + TOL), ad(mna), ad(mxa), TOL, ad(cb), 400)      # numpy: cand = B_[kx[lo:hi]], then inside the box +- TOL
            if not nc: out_.append(fc); continue                        # (kept whatever the cut: so uv_split is asked only here, the same result)
            if not _far(cb, min(nc, 400), P, TOL): out_.append(fc); continue      # (cp_cut would say no: kept)
            pcs, n = split([tuple(fc[:4])])
            if not n: out_.append(fc); continue
            Qa = array.array('d', [float(v) for pc in pcs for q in pc[2] for v in q]); Pa = array.array('d', [v for q in P for v in q])
            if FL.cp_cut(ad(cb), min(nc, 400), ad(Qa), len(Qa) // 3, ad(Pa), len(P), TOL):      # any(|Q - c|.min() < TOL and |P - c|.min() >= TOL for c in cand[:400])
                out_ += [(pc[0], pc[1], [tuple(p) for p in pc[2]], [tuple(u) for u in pc[3]]) + tuple(fc[4:]) for pc in pcs]; ncut += 1
            else: out_.append(fc)
        faces = out_; log('       patch %s: %d polygons cut into the pieces the build shows (their tile repeats more than twice), so single pieces can be removed' % (path.replace(chr(92), '/').split('/')[-1], ncut))
    Cn = _Corners(faces); own = Cn.own; first = Cn.first; n_ = Cn.n
    hits = Cn.near_many([_f3(sr3(p)) for r in rem for p in r['p']], TOL, TOL, TOL)      # at(b) of every corner of every triangle: x in [b0 - TOL, b0 + TOL), within TOL
    cut = collections.defaultdict(list); lost = back = 0
    ho = 0
    for r in rem:
        a = hits[ho:ho + len(r['p'])]; ho += len(r['p']); best = None; anyp = False
        for k in sorted({own[i] for i in a[0]} & {own[i] for i in a[1]} & {own[i] for i in a[2]}):
            anyp = True; n = n_[k]
            for i0 in [i - first[k] for i in a[0] if own[i] == k]:
                for i1 in [i - first[k] for i in a[1] if own[i] == k]:
                    for i2 in [i - first[k] for i in a[2] if own[i] == k]:
                        if len({i0, i1, i2}) < 3: continue
                        t = (i0, i1, i2); fwd = ((t[1] - t[0]) % n) < ((t[2] - t[0]) % n)
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

def _old_remove(faces, rem, sr3, path, log, split=None, keep=()):
    """(the numpy original of remove: the reference)"""
    import numpy as np
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

def move_boards(faces, BM, ox, oz, log):
    """cut-out boards moved in Blender: see _old_move_boards (the numpy original, the reference); here on Python numbers"""
    rows = [tuple(float(v) for v in r) for r in BM]; ob_ = sorted(range(len(rows)), key=lambda i: rows[i][0]); bx_ = [rows[i][0] for i in ob_]; nb_ = 0
    def shift_(p_):                                                     # the listed corner within 3 mm of p_ (decoded coordinates) -> its shift, or None
        q_ = (float(p_[0]) - ox, float(p_[1]), -(float(p_[2]) - oz)); c_ = [rows[i] for i in ob_[bisect.bisect_left(bx_, q_[0] - 0.003):bisect.bisect_left(bx_, q_[0] + 0.003)]]
        if not c_: return None
        d_ = [_nrow(c, q_) for c in c_]; k_ = d_.index(min(d_)); return c_[k_][3:6] if d_[k_] < 0.003 else None      # np.argmin: the first of equals
    for fc in faces:
        if not str(fc[0]).split('|')[0].endswith('_t') or len(fc[2]) < 3: continue
        sh_ = [s_ for s_ in (shift_(p_) for p_ in fc[2]) if s_ is not None]
        if len(sh_) < 3 or any(max(abs(s_[q] - sh_[0][q]) for q in range(3)) > 0.004 for s_ in sh_): continue
        d_ = sh_[0]; fc[2][:] = [(p_[0] + float(d_[0]), p_[1] + float(d_[1]), p_[2] - float(d_[2])) for p_ in fc[2]]; nb_ += 1
    log('       boards moved whole (board_moves): %d cut-out polygons' % nb_)
    return faces

def _old_move_boards(faces, BM, ox, oz, log):
    """cut-out boards moved in Blender (trees lifted onto new ground, 2026-10-13): the ORIGINAL polygons are moved whole, so they keep their
    corner count, their front / back marks and their mapping (owner: "reimport the trees ... at the right positions"). BM: [[x, y, z, dx, dy, dz],
    ...] per corner, in the decoded scene's coordinates. A polygon moves when at least three of its corners are listed with the same shift (its
    other corners go along). Was import_classic's board_moves block (course setting board_moves); here since 2026-10-15 so that a staged patch
    file can carry its board moves (apply_file)."""
    import numpy as np
    BMv_ = np.array(BM, float); ob_ = np.argsort(BMv_[:, 0], kind='stable'); bx_ = BMv_[ob_, 0]; nb_ = 0
    def shift_(p_):                                                     # the listed corner within 3 mm of p_ (decoded coordinates) -> its shift, or None
        q_ = np.array([p_[0] - ox, p_[1], -(p_[2] - oz)]); lo_, hi_ = np.searchsorted(bx_, [q_[0] - 0.003, q_[0] + 0.003]); c_ = BMv_[ob_[lo_:hi_]]
        if not len(c_): return None
        d_ = np.linalg.norm(c_[:, :3] - q_, axis=1); k_ = int(np.argmin(d_)); return c_[k_, 3:6] if d_[k_] < 0.003 else None
    for fc in faces:
        if not str(fc[0]).split('|')[0].endswith('_t') or len(fc[2]) < 3: continue
        sh_ = [s_ for s_ in (shift_(p_) for p_ in fc[2]) if s_ is not None]
        if len(sh_) < 3 or any(float(np.abs(s_ - sh_[0]).max()) > 0.004 for s_ in sh_): continue
        d_ = sh_[0]; fc[2][:] = [(p_[0] + float(d_[0]), p_[1] + float(d_[1]), p_[2] - float(d_[2])) for p_ in fc[2]]; nb_ += 1
    log('       boards moved whole (board_moves): %d cut-out polygons' % nb_)
    return faces

def restore_texture_recipes(entries, pixels, save, origin=None):
    """Recreate composed source materials retained by an edited Blender scene.

    These are recipes, not game pixels. Resolve dependencies recursively so a
    moved/deleted overlay polygon does not orphan an otherwise unchanged tile.
    """
    if not entries: return
    import numpy as np
    import overlay_bake as OB
    assert pixels is not None and save is not None, 'source texture recipes need the importer tile reader'
    active = set(); ready = {}
    def resolve(name):
        if name in ready: return ready[name]
        value = pixels(name)
        if value is not None: return value
        if name not in entries: raise ValueError('Missing source texture for patch recipe: ' + name)
        if name in active: raise ValueError('Cyclic source texture recipe: ' + name)
        active.add(name)
        lo, up, mapping, rect = entries[name]
        value = OB._recipe(lo, up, np.asarray(mapping).reshape(3, 2), resolve, rect)
        if value is None: raise ValueError('Cannot reconstruct source texture recipe: ' + name)
        save(name, *value); ready[name] = value; OB.RECIPES[name] = entries[name]
        # Retained source materials keep their existing lighting classification.
        active.remove(name)
        return value
    for name in entries: resolve(name)


def apply_file(faces, path, ox, oz, export, log, applied=(), **kw):
    """a numbered patch file: a plain patch (apply), or a STAGED one (2026-10-15, owner: "Mountain R4 is accepted, which means v11 is accepted
    too. Create patch 3 out of it"): {"stages": [patch, {"board_moves": [...]}, patch, ...]} applied one after the other exactly as separate
    patches and a board_moves setting would be, so the file holds a chain that was built in steps and gives the same build."""
    J = json.load(open(path))
    if 'stages' not in J: return apply(faces, path, ox, oz, export, log, applied=applied, **kw)
    assert J.get('format') == 'sr3lab course patch', 'not a course patch file this importer knows: ' + path
    miss = [k for k in J.get('base', {}).get('needs', []) if k not in applied]
    if miss: raise SystemExit('PATCH REFUSED: %s needs patch %s of this course applied before it' % (path, miss))
    name = path.replace('\\', '/').split('/')[-1]
    for i, st in enumerate(J['stages']):
        if 'board_moves' in st: faces = move_boards(faces, st['board_moves'], ox, oz, log); continue
        st = dict(st); st['label'] = '%s stage %d' % (name, i + 1); st['base'] = {k: v for k, v in st.get('base', {}).items() if k != 'needs'}      # (the file's needs are checked above)
        faces = apply(faces, st, ox, oz, export, log, applied=applied, **kw)
    return faces

def apply(faces, path, ox, oz, export, log, fill_uv=True, applied=(), settings=None, pixels=None, save=None, origin=None, split=None, keep=()):
    """faces: the build's (material, section, [corners in SR3 coordinates], [uv]) -> the same list with the patch applied.
    path: a patch file, or one stage of a staged patch file as a dict (its 'label' names it in the log; see apply_file)"""
    if isinstance(path, dict): J = path; path = str(J.get('label', 'patch stage'))
    else: J = json.load(open(path))
    assert J.get('format') == 'sr3lab course patch' and J.get('version') in (1, 2, 3), 'not a course patch file this importer knows: ' + path
    want = J['base'].get('course_export_sha1'); got = export_sha1(export)
    if want and want != got: raise SystemExit('PATCH REFUSED: %s was made on another export of the course (%s; this build reads %s)' % (path, want[:12], got[:12]))
    miss = [k for k in J['base'].get('needs', []) if k not in applied]                                 # patches are made one on the result of the other (owner, 2026-10-09)
    if miss: raise SystemExit('PATCH REFUSED: %s needs patch %s of this course applied before it' % (path, miss))
    if settings is not None:                                           # build settings a patch brings along (patch 2: the sea sheet is left whole), merged one level deep by the importer
        for k, v in J.get('settings', {}).items(): settings[k] = {**settings.get(k, {}), **v} if isinstance(v, dict) else v
    sr3 = lambda p: (float(p[0]) + ox, float(p[1]), -float(p[2]) + oz)
    # corners to move: an edited triangle is found as three corners of ONE polygon of the build (other polygons with a corner at the same place stay)
    faces = list(faces); Cn = _Corners(faces); own = Cn.own; first = Cn.first
    moves = collections.defaultdict(dict); lost = 0
    mh = Cn.near_many([_f3(sr3(p)) for m in J['move'] for p in m['before']], 2 * TOL, 2 * TOL, TOL)      # (numpy: every corner with np.linalg.norm(C - b, axis=1) < TOL, in index order: the same set from a window twice as wide)
    mo = 0
    for m in J['move']:
        B = [_f3(sr3(p)) for p in m['before']]; A = [sr3(p) for p in m['after']]; at = [sorted(h) for h in mh[mo:mo + len(B)]]; mo += len(B)
        fs = {own[i] for i in at[0]} & {own[i] for i in at[1]} & {own[i] for i in at[2]}
        if not fs:
            if 'fallback' in m: J.setdefault('remove', []).append(dict(p=m['before'])); J['add'].append(m['fallback']); fell = locals().get('fell', 0) + 1; continue      # a move that carries its own remove + add (2026-10-13: a moved board whose triangle is a PIECE of a polygon the build cut up)
            lost += 1; continue
        for c in range(3):
            if _nvec(_sub(B[c], A[c])) < 1e-6: continue
            for i in at[c]:
                if int(own[i]) in fs: moves[int(own[i])][i - int(first[own[i]])] = A[c]
    if locals().get('fell'): log('       patch %s: %d moved faces are pieces of cut-up polygons: taken out and added again instead' % (path.replace(chr(92), '/').split('/')[-1], fell))
    if lost: raise SystemExit('PATCH REFUSED: %d of the %d faces whose corners move are not among the polygons of this build' % (lost, len(J['move'])))
    for k, mv in moves.items(): fc = faces[k]; P = list(fc[2]); [P.__setitem__(c, a) for c, a in mv.items()]; faces[k] = (fc[0], fc[1], P) + tuple(fc[3:])
    if J.get('whole_polygons'): split = None                            # OPT-IN by the patch file (genpatch1995.py): its triangles to remove are corners of the importer's own polygons, never of the pieces a build cuts them into
    nrem = remove(faces, J.get('remove', []), sr3, path, log, split=split, keep=keep) if J.get('remove') else None
    if nrem is not None: faces = nrem
    restore_texture_recipes(J.get('texture_recipes', {}), pixels, save, origin)
    if J.get('bake'):                                                   # version 3: pictures composed from the course tiles (facadebake.py), named as tiles of their own
        import facadebake
        assert pixels is not None and save is not None, 'this patch composes pictures: the importer must hand over its tile reader'
        facadebake.apply(J['bake'], pixels, save, origin, log)
    add = [(f_['tile'], 'patch', [sr3(p) for p in f_['p']], [tuple(u) for u in f_['uv']]) for f_ in J['add']]
    add = [fc for fc in add if _area(fc[2]) > 1e-9]; cont = flat = 0
    if fill_uv: cont, flat = continue_uv(add, faces, log)
    log('       patch %s: %d faces added (%.0f m2; %d had no mapping: %d continued from a neighbour, %d laid flat), %d corners of %d polygons moved' % (path.replace('\\', '/').split('/')[-1], len(add), sum(_area(fc[2]) for fc in add), cont + flat, cont, flat, sum(len(v) for v in moves.values()), len(moves)))
    return faces + add
