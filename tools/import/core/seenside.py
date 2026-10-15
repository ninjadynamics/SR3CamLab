"""seenside.py - which side of a polygon does the road see?  (course setting "seen_sides": true; baked light only)

Why (Mountain RT, 2026-10-13): the game draws an opaque 1995 polygon from both sides and a light map holds ONE light for it. The bake lit both
faces and kept the brighter, so a rock wall turned away from the sun showed the sun that falls on its hidden back: a bright wall with its own
shadow lying at its foot, dark panels where something stands behind it (owner: "that bright piece of rock next to the shadowed faces looks
suspicious as hell"). Counted near the road: 2 168 standing polygons, 19 600 m2, against 26 900 m2 honestly sunlit.

The light a polygon shows must be the light on the side that is LOOKED AT, and the eyes are on the road (roadsight.py asked the same question
for the vertex-lit builds). Viewpoints every 3 m along the road, left / middle / right, at car and chase-camera height; six points on every
opaque polygon; a point counts for the side the viewpoint stands on when nothing is in the way:
    seen on its winding side only   -> stays as it is                       the bake lights that side
    seen on the other side only     -> wound the other way (see rewind)      the bake lights that side
    seen on both sides              -> material key + '|3': add_scenery writes it once per side, single-sided, each copy with its own light map
    never seen from the road        -> material key + '|4': drawn two-sided, the bake keeps the brighter of its two faces (what every polygon got before)
Nothing here moves a corner. A four-corner polygon is drawn as two triangles along corners 0 - 2; roadsight.py and lightside.py reversed the
corner list, which cuts a twisted polygon along its other diagonal - another surface (37% of Mountain's are twisted). rewind() keeps the diagonal.

    faces, sky, extra = seenside.orient((faces, sky, extra), rd, skip=BC.PAIRS, log=log)
Without numpy since 2026-10-15 (kb 31): the corners are packed by geobuf.pack, the triangles, normals, sample points, areas and the open-side
rays made by fastlm.c (lm_ss_prep, lm_open_sides: their comments quote the numpy lines), the viewpoints by roadsight.viewpoints, the
decisions in plain Python; the lists, the log and the keep file (lm.sides.npz, through npyio) are the numpy version's."""
import time, os, hashlib, math
from array import array
import npyio

STEP = 3; SIDE = (-3.5, 0.0, 3.5); HEIGHT = (1.1, 3.2); REACH = 220.0; MIN_HITS = 2; RATIO = 8.0
# OPEN SIDES (course setting seen_open, default on since 2026-10-14; owner: "fix the faces"): the road is not the only place a side is looked at from - a
# free camera sees the backs of cliff cards and the far sides of rock walls, and a polygon never seen from the road showed the brighter of its two faces'
# light (the sunlit far side, with the shadows of the fence posts on it, in a shaded wall). A side is OPEN when at least OPEN_MIN of the rays it sends
# over its half space (24 directions from each of the six points the road test uses) reach the sky; a side buried in rock or turned to the ground under
# a terrain sheet is not. Then: both sides open -> written once per side ('|3'); only the side the road does not see open -> wound round when the road
# sees neither ... i.e. every side that can be seen from anywhere open carries its own light.
OPEN_MIN = 0.06
_HEMI = [(math.sqrt((i + 0.5) / 24) * math.cos(i * 2.399963), math.sqrt((i + 0.5) / 24) * math.sin(i * 2.399963), math.sqrt(max(0.0, 1 - (i + 0.5) / 24))) for i in range(24)]      # (np.sqrt / np.cos of a number: the same functions as math's)

def _pw(v):
    """np.sum of a 1-D float64 array: numpy's pairwise sum (rtbake/rt_bake_game5.py pwsum)"""
    n = len(v)
    if n < 8:
        t = 0.0
        for x in v: t += x
        return t
    if n <= 128:
        r = list(v[:8]); e = n - n % 8
        for i in range(8, e, 8):
            for j in range(8): r[j] += v[i + j]
        t = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
        for x in v[e:]: t += x
        return t
    h = n // 2; h -= h % 8
    return _pw(v[:h]) + _pw(v[h:])

def _pack(allf, use):
    """the corners of every polygon (geobuf.pack); when a corner holds more than x, y, z, those three of the polygons used (numpy: np.asarray(P, float)[:, :3])"""
    import geobuf
    try: return geobuf.pack(allf)
    except (ValueError, TypeError):
        X = array('d'); off = array('q', [0]); lens = array('q')
        for fc, u in zip(allf, use):
            k = len(fc[2]) if u else 0; lens.append(k); off.append(off[-1] + k)
            if u: X.extend(float(v) for p in fc[2] for v in tuple(p)[:3])
        return X, off, lens

def rewind(P, UV):
    """the other winding of the SAME surface: corners 0 and 2 (the diagonal the game cuts along) stay, 1 and 3 change places"""
    P = list(P); UV = list(UV)
    if len(P) >= 4 and tuple(P[2]) != tuple(P[3]): return [P[0], P[3], P[2], P[1]], [UV[0], UV[3], UV[2], UV[1]]
    return [P[0], P[2], P[1]], [UV[0], UV[2], UV[1]]

def orient(lists, rd, skip=(), also=(), single='~s', log=print, keep=None, read=None, open_=False):
    # keep = a file to write what was found to (the collecting build) ; read = that file, to take over instead of casting the rays again (the final
    # build: the two must agree polygon by polygon, and at R4 the rays are 28 s). Taken over only when the judged polygons are the very same.
    """also = cut-out tiles that take baked light (course setting lm_cutouts: a building drawn with cut-out pictures). They are not judged: each
    is written once per side, both copies single-sided (section mark `single`, as the tree boards' front / back pairs), so its outside and its
    inside each have their own light. They stand in the way of the viewpoints like walls."""
    import fastlm, roadsight
    t0 = time.time(); allf = [fc for L in lists for fc in L]; n = len(allf); skip = set(skip); also = set(also)
    cutj = lambda fc: str(fc[0]) in also and len(fc[2]) in (3, 4)
    opq = lambda fc: not str(fc[0]).split('|')[0].endswith('_t') and len(fc[2]) in (3, 4)
    def judged(fc): return opq(fc) and str(fc[1]) != 'sea' and not str(fc[1]).startswith('gate_') and '|' not in str(fc[0]) and id(fc) not in skip
    opaque = array('B', [(opq(fc) or cutj(fc)) and str(fc[1]) != 'sea' for fc in allf]); J = array('B', [judged(fc) for fc in allf]); use = array('B', [a or b for a, b in zip(opaque, J)])      # (a listed cut-out stands in the way like a wall: without that the tower's walls were seen from inside, through the tower)
    X, off, lens = _pack(allf, use); nop = sum(opaque); nj = sum(J); ad = lambda a: a.buffer_info()[0] if isinstance(a, array) else a.ptr()
    T = array('d', bytes(144 * nop)); nt = ctypes_ll(); idx = array('q', bytes(8 * nj)); Pj = array('d', bytes(96 * nj)); trij = array('B', bytes(nj)); nrm = array('d', bytes(24 * nj)); cen = array('d', bytes(24 * nj))
    S = array('d', bytes(144 * nj)); area = array('d', bytes(8 * nj))
    fastlm.lib().lm_ss_prep(n, ad(X), ad(off), ad(lens), ad(use), ad(opaque), ad(J), ad(T), nt.ref, ad(idx), ad(Pj), ad(trij), ad(nrm), ad(cen), ad(S), ad(area)); nt = nt.value      # (fastlm.c quotes the numpy lines)
    del T[9 * nt:]                                                    # what stands in the way: the triangles the game draws
    C, E = roadsight.viewpoints(rd, STEP, SIDE, HEIGHT); per = len(SIDE) * len(HEIGHT)
    Sk = []
    for k in range(6): a = array('d'); a.frombytes(memoryview(S).cast('B')[24 * nj * k:24 * nj * (k + 1)]); Sk.append(a)      # the three pairs of sample points
    front = [0] * nj; back = [0] * nj; nrays = 0; took = ''
    fp = hashlib.sha1(bytes(Pj) + bytes(T) + bytes(E)).hexdigest()      # the judged polygons, what stands in the way, the viewpoints
    if read and os.path.exists(read):
        Z = npyio.loadz(read)
        if npyio.string(Z['fp']) == fp and Z['front'].shape[0] == nj: front = Z['front'].tolist(); back = Z['back'].tolist(); nrays = int(Z['nrays'].tolist()[0]); took = ' ; taken over from the collecting build'
        else: log('       which side the road sees: the polygons of this build are NOT the ones the collecting build judged (%s): judged again - its light-map table may not fit' % read)
    sc = None; saved = None
    if not took:
        sc = fastlm.Scene(T, nt)
        for k in range(3):
            f_, b_, r_ = fastlm.roadsight(sc, cen, Sk[2 * k], Sk[2 * k + 1], nrm, C, E, per, REACH); front = [x + y for x, y in zip(front, f_)]; back = [x + y for x, y in zip(back, b_)]; nrays += r_
        if keep: saved = dict(fp=npyio.text(fp), front=npyio.Arr('<i8', (nj,), memoryview(array('q', front)).cast('B')), back=npyio.Arr('<i8', (nj,), memoryview(array('q', back)).cast('B')), nrays=npyio.scalar(nrays)); npyio.savez(keep, **saved)
    F = [f >= MIN_HITS for f in front]; B = [b >= MIN_HITS for b in back]
    onlyf = [f_ and (not b_ or f >= RATIO * b) for f_, b_, f, b in zip(F, B, front, back)]; onlyb = [b_ and (not f_ or b >= RATIO * f) for f_, b_, f, b in zip(F, B, front, back)]
    both = [f_ and b_ and not x and not y for f_, b_, x, y in zip(F, B, onlyf, onlyb)]; none = [not f_ and not b_ for f_, b_ in zip(F, B)]
    if open_:                                                          # (open sides, owner 2026-10-14) a side the road does not see but that faces open air gets its own light too
        fo_, bo_ = None, None
        if read and os.path.exists(read):
            Z = npyio.loadz(read)
            if 'fopen' in Z and npyio.string(Z['fp']) == fp and Z['fopen'].shape[0] == nj: fo_, bo_ = Z['fopen'].tolist(), Z['bopen'].tolist()
        if fo_ is None:
            fa = array('d', bytes(8 * nj)); ba = array('d', bytes(8 * nj)); H = array('d', [v for h in _HEMI for v in h])
            fastlm.lib().lm_open_sides((fastlm.Scene(T, nt) if took else sc).x, nj, ad(S), 6, ad(nrm), 0.05, ad(H), len(_HEMI), ad(fa), ad(ba)); fo_, bo_ = fa.tolist(), ba.tolist()      # (seenside._open_sides, numpy: see fastlm.c)
            if keep:
                Z = dict(npyio.loadz(keep)) if saved is None else saved; Z.update(fopen=npyio.Arr('<f8', (nj,), memoryview(fa).cast('B')), bopen=npyio.Arr('<f8', (nj,), memoryview(ba).cast('B'))); npyio.savez(keep, **Z)
        fo = [x >= OPEN_MIN for x in fo_]; bo = [x >= OPEN_MIN for x in bo_]; rest = [not x and not y and not z for x, y, z in zip(onlyf, onlyb, both)]
        both2 = [w or (x and b_) or (y and f_) or (r and f_ and b_) for w, x, y, r, f_, b_ in zip(both, onlyf, onlyb, rest, fo, bo)]
        onlyf2 = [(x and not b_) or (r and f_ and not b_) for x, r, f_, b_ in zip(onlyf, rest, fo, bo)]; onlyb2 = [(y and not f_) or (r and b_ and not f_) for y, r, f_, b_ in zip(onlyb, rest, fo, bo)]
        log('       open sides (seenside.py, %d rays a side, open = at least %.0f%% of them reach the sky): front open %d, back open %d ; written once per side %d -> %d ; lit on their winding side %d -> %d ; wound round %d -> %d ; neither side open %d'
            % (3 * 2 * len(_HEMI), 100 * OPEN_MIN, sum(fo), sum(bo), sum(both), sum(both2), sum(onlyf), sum(onlyf2), sum(onlyb), sum(onlyb2), sum(1 for r, f_, b_ in zip(rest, fo, bo) if r and not f_ and not b_)))
        both, onlyf, onlyb = both2, onlyf2, onlyb2
    out = list(allf); ar = area.tolist()
    for k, i in enumerate(idx):
        mat, sec, P, UV = allf[i][:4]
        if onlyb[k]: P2, U2 = rewind(P, UV); out[i] = (mat, sec, P2, U2) + tuple(allf[i][4:])
        elif both[k]: out[i] = (str(mat) + '|3', sec, P, UV) + tuple(allf[i][4:])
        elif not onlyf[k]: out[i] = (str(mat) + '|4', sec, P, UV) + tuple(allf[i][4:])
    sel = lambda m: _pw([a for a, x in zip(ar, m) if x])               # area[mask].sum(): numpy's pairwise sum over the polygons picked
    rest = [not x and not y and not z for x, y, z in zip(onlyf, onlyb, both)]
    log('       which side the road sees (seenside.py: %d viewpoints, %.1f million rays, %.1f s%s): %d polygons judged ;winding side %d (%.0f m2) ; other side, wound round %d (%.0f m2) ; both sides, written once per side %d (%.0f m2) ; never seen, brighter face kept %d (%.0f m2)'
        % (len(E) // 3, nrays / 1e6, time.time() - t0, took, nj, sum(onlyf), sel(onlyf), sum(onlyb), sel(onlyb), sum(both), sel(both), sum(none) + sum(1 for r, z in zip(rest, none) if r and not z), sel(rest)))
    more = []
    for i, fc in enumerate(allf):
        if cutj(fc) and '|' not in str(fc[0]) and str(fc[1]) != 'sea' and not str(fc[1]).startswith('gate_') and not str(fc[1]).endswith(single):
            mat, sec, P, UV = fc[:4]; P2, U2 = rewind(P, UV); out[i] = (mat, str(sec) + single, P, UV) + tuple(fc[4:]); more.append((mat, str(sec) + single, P2, U2) + tuple(fc[4:]))
    if more: log('       cut-out polygons that take baked light (lm_cutouts): %d written once per side, single-sided' % len(more))
    res = []; a = 0
    for L in lists: res.append(out[a:a + len(L)]); a += len(L)
    res[-1] = list(res[-1]) + more
    return res

class ctypes_ll:
    """an i64 the C side writes (ctypes.c_longlong and its address)"""
    def __init__(self):
        import ctypes
        self.c = ctypes.c_longlong(0); self.ref = ctypes.addressof(self.c)
    @property
    def value(self): return self.c.value
