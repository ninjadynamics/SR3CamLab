"""TrackBoundary BSP: serializer (byte-identical on SEGA's 6 chunks) and a builder for a corridor between two polylines.
Semantics (see ../../06_boundary_collision.md): binary tree in pre-order; child A = negative side of the node plane,
child B = positive side; walls/floor/ceiling polygons face INTO the drivable space."""
import struct, math, collections
import numpy as np
from bsp import parse_bsp, classify

def serialize(tree, polys, surf_ids):
    """tree: nested nodes
         ('kd', (minx,minz,maxx,maxz), ix, iz, plane, A, B) | ('pl', plane, flag, surf, A, B) | ('solid',) | ('empty',)
         | ('leaf', [(plane, surf), ...])
       polys: list of (plane, [3 xyz]). Returns (data, fix).
       Layout = SEGA's: header 0x40 | kd | planes | leaf records | leaf face data | types | polys | ids."""
    types = []; kd = []; pls = []; leaves = []; n3 = n4 = 0
    stack = [tree]
    while stack:                                                    # pre-order, child A before child B
        nd = stack.pop(); k = nd[0]
        if k == 'kd': types.append(2); kd.append(nd); stack.append(nd[6]); stack.append(nd[5])
        elif k == 'pl': types.append(1); pls.append(nd); stack.append(nd[5]); stack.append(nd[4])
        elif k == 'solid': types.append(3); n3 += 1
        elif k == 'empty': types.append(4); n4 += 1
        else: types.append(5); leaves.append(nd[1])
    assert types[0] == 2, 'the root must be a kd node (the exe starts at kd record 0)'
    p_kd = 0x40; p_pl = p_kd + 0x2c * len(kd); p_leaf = p_pl + 0x18 * len(pls); p = p_leaf + 12 * len(leaves)
    lrec = bytearray(); ldat = bytearray(); fix = [0x20, 0x24, 0x28, 0x2c, 0x30, 0x34, 0x38, 0x3c]
    for i, faces in enumerate(leaves):
        pa = p + len(ldat); pb = pa + 16 * len(faces)
        lrec += struct.pack('<III', len(faces), pa, pb); fix += [p_leaf + 12 * i + 4, p_leaf + 12 * i + 8]
        for pl, s in faces: ldat += struct.pack('<4f', *pl)
        for pl, s in faces: ldat += struct.pack('<I', s)
    p_types = p + len(ldat); p_poly = p_types + 4 * len(types); p_surf = p_poly + 0x44 * len(polys)
    out = bytearray(struct.pack('<16I', 1, len(kd), len(pls), n3, n4, len(leaves), len(polys), len(surf_ids),
                                p_kd, p_pl, p_leaf, p_leaf, p_leaf, p_types, p_poly, p_surf))
    for nd in kd: out += struct.pack('<4f3I4f', *nd[1], nd[2], nd[3], 1, *nd[4])
    for nd in pls: out += struct.pack('<4fII', *nd[1], nd[2], nd[3])
    out += lrec + ldat + struct.pack('<%dI' % len(types), *types)
    for pl, v in polys:
        out += struct.pack('<I4f', 3, *pl) + b''.join(struct.pack('<3f', *q) for q in v) + bytes(12)
    out += struct.pack('<%dI' % len(surf_ids), *surf_ids)
    return bytes(out), fix

def to_tree(b):
    """parsed chunk -> nested tree accepted by serialize (lossless)"""
    def conv(i):
        t, k, a, bb = b.nodes[i]
        if t == 2:
            r = b.kd[k]; return ('kd', tuple(r['box'].tolist()), int(r['ix']), int(r['iz']), tuple(r['pl'].tolist()), conv(a), conv(bb))
        if t == 1:
            r = b.pl[k]; return ('pl', tuple(r['pl'].tolist()), int(r['flag']), int(r['surf']), conv(a), conv(bb))
        if t == 3: return ('solid',)
        if t == 4: return ('empty',)
        pl, sf = b.leaves[k][:2]; return ('leaf', [(tuple(p.tolist()), int(s)) for p, s in zip(pl, sf)])
    polys = [(tuple(p['pl'].tolist()), [tuple(q.tolist()) for q in p['v'][:3]]) for p in b.poly]
    return conv(b.root), polys, b.surf

def classify_tree(tree, p):
    nd = tree
    while nd[0] in ('kd', 'pl'):
        pl = nd[4] if nd[0] == 'kd' else nd[1]
        s = pl[0] * p[0] + pl[1] * p[1] + pl[2] * p[2] + pl[3]
        if nd[0] == 'kd': nd = nd[5] if s < 0 else nd[6]
        else: nd = nd[4] if s < 0 else nd[5]
    return nd

def depth_stats(tree):
    mx = 0; tot = 0; n = 0; st = [(tree, 1)]
    while st:
        nd, d = st.pop()
        if nd[0] == 'kd': st += [(nd[5], d + 1), (nd[6], d + 1)]
        elif nd[0] == 'pl': st += [(nd[4], d + 1), (nd[5], d + 1)]
        else: mx = max(mx, d); tot += d; n += 1
    return mx, tot / max(n, 1), n

# ------------------------------------------------------------------ corridor builder
def _clip(poly, a, b, c, keep_pos):
    out = []; n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        sp = a * p[0] + b * p[1] + c; sq = a * q[0] + b * q[1] + c
        if not keep_pos: sp, sq = -sp, -sq
        if sp >= 0: out.append(p)
        if (sp > 0 and sq < 0) or (sp < 0 and sq > 0):
            t = sp / (sp - sq); out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out
def _area(poly):
    return 0.5 * abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly))))
def _centroid(poly):
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))

def build_corridor(left, right, y0=-2.0, y1=10.0, surf_wall=0, surf_floor=0, surf_ids=(0,), kd_depth=4, max_segs=4, margin=30.0, heights=None, below=2.0, above=10.0):
    """left/right: closed polylines [(x,z)] with the same number of points; the drivable corridor is the union of the quads
    (left[i], left[i+1], right[i+1], right[i]). Walls stand on both polylines; a floor at y0 and a ceiling at y1 close the
    tunnel (as in SEGA's data). y0/y1 may be arrays per point is NOT supported: flat limits only.
    Returns (data, fix, tree, polys, stats, in_corridor)."""
    n = len(left); L = [tuple(map(float, p)) for p in left]; R = [tuple(map(float, p)) for p in right]
    quads = [(L[i], L[(i + 1) % n], R[(i + 1) % n], R[i]) for i in range(n)]
    T = np.array([(q[0], q[1], q[2]) for q in quads] + [(q[0], q[2], q[3]) for q in quads]); TB = np.roll(T, -1, axis=1)
    def in_corridor(pt):
        x, z = pt
        cr = (TB[:, :, 0] - T[:, :, 0]) * (z - T[:, :, 1]) - (TB[:, :, 1] - T[:, :, 1]) * (x - T[:, :, 0])
        return bool(((cr >= -1e-9).all(1) | (cr <= 1e-9).all(1)).any())
    segs = []                                                         # (p, q, (a, b, c)), corridor on the positive side
    for i in range(n):
        for (p, q), other in (((L[i], L[(i + 1) % n]), R[i]), ((R[i], R[(i + 1) % n]), L[i])):
            ex, ez = q[0] - p[0], q[1] - p[1]; ln = math.hypot(ex, ez)
            if ln < 1e-6: continue
            a, b = -ez / ln, ex / ln; c = -(a * p[0] + b * p[1])
            if a * other[0] + b * other[1] + c < 0: a, b, c = -a, -b, -c
            segs.append((p, q, (a, b, c)))
    allp = np.array(L + R); x0, z0 = allp.min(0) - margin; x1, z1 = allp.max(0) + margin
    P3 = lambda ln: (ln[0], 0.0, ln[1], ln[2])
    floor = (0.0, 1.0, 0.0, -y0); ceil = (0.0, -1.0, 0.0, y1)
    stats = collections.Counter()
    # terrain following: heights = road height at each polyline point; a free cell gets a horizontal floor `below` the lowest
    # and a ceiling `above` the highest road point of the corridor quads it overlaps (stepped, not sloped like the originals)
    if heights is not None:
        H = np.asarray(heights, float); Hn = np.roll(H, -1)
        qlo = np.minimum(H, Hn); qhi = np.maximum(H, Hn)
        Qa = np.array(quads); qx0 = Qa[:, :, 0].min(1); qx1 = Qa[:, :, 0].max(1); qz0 = Qa[:, :, 1].min(1); qz1 = Qa[:, :, 1].max(1)
    def limits(cell):
        if heights is None: return floor, ceil, y0, y1
        xs = [p[0] for p in cell]; zs = [p[1] for p in cell]
        m = (qx1 >= min(xs)) & (qx0 <= max(xs)) & (qz1 >= min(zs)) & (qz0 <= max(zs))
        if not m.any(): return floor, ceil, y0, y1
        a = float(qlo[m].min()) - below; b = float(qhi[m].max()) + above
        return (0.0, 1.0, 0.0, -a), (0.0, -1.0, 0.0, b), a, b
    cells_out = []
    def split_segs(S, a, b, c):
        neg = []; pos = []; on = []
        for p, q, ln in S:
            sp = a * p[0] + b * p[1] + c; sq = a * q[0] + b * q[1] + c
            if abs(sp) < 1e-5 and abs(sq) < 1e-5: on.append((p, q, ln)); continue
            if sp >= -1e-5 and sq >= -1e-5: pos.append((p, q, ln))
            elif sp <= 1e-5 and sq <= 1e-5: neg.append((p, q, ln))
            else:
                t = sp / (sp - sq); m = (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
                (pos if sp > 0 else neg).append((p, m, ln)); (pos if sq > 0 else neg).append((m, q, ln))
        return neg, pos, on
    def leaf(cell, faces):
        if len(cell) < 3 or _area(cell) < 1e-6 or not in_corridor(_centroid(cell)):
            stats['solid'] += 1; return ('solid',)
        mine = []                                                    # wall faces that really lie on an edge of this cell
        for p, q, ln in faces:
            for i in range(len(cell)):
                u, v = cell[i], cell[(i + 1) % len(cell)]
                if abs(ln[0] * u[0] + ln[1] * u[1] + ln[2]) < 1e-3 and abs(ln[0] * v[0] + ln[1] * v[1] + ln[2]) < 1e-3 and math.hypot(v[0] - u[0], v[1] - u[1]) > 1e-4:
                    if P3(ln) not in [m[0] for m in mine]: mine.append((P3(ln), surf_wall))
                    break
        stats['free'] += 1
        fpl, cpl, fa, cb = limits(cell); cells_out.append((cell, fa, cb))
        fl = [(fpl, surf_floor), (cpl, surf_floor)]
        return ('pl', fpl, 0, surf_floor, ('solid',), ('pl', cpl, 0, surf_floor, ('solid',), ('leaf', mine + fl)))
    def build(cell, S, faces, depth, ix, iz, axis, box):
        if len(cell) < 3 or _area(cell) < 1e-6: stats['solid'] += 1; return ('solid',)
        if not S: return leaf(cell, faces)
        if depth < kd_depth or len(S) > max_segs:
            xs = [p[0] for p in cell]; zs = [p[1] for p in cell]
            if depth >= kd_depth: axis = 0 if (max(xs) - min(xs)) >= (max(zs) - min(zs)) else 1
            mid = ((min(xs) + max(xs)) / 2) if axis == 0 else ((min(zs) + max(zs)) / 2)
            a, b, c = (1.0, 0.0, -mid) if axis == 0 else (0.0, 1.0, -mid)
            neg, pos, on = split_segs(S, a, b, c)
            useless = depth >= kd_depth and (len(neg) >= len(S) or len(pos) >= len(S)) and len(S) <= 6 * max_segs
            if not useless:
                for sgm in on:                                       # a wall exactly on the split line goes to its front side
                    (pos if (sgm[2][0] * a + sgm[2][1] * b) > 0 else neg).append(sgm)
                cn = _clip(cell, a, b, c, False); cp = _clip(cell, a, b, c, True)
                if axis == 0: bn = (box[0], box[1], mid, box[3]); bp = (mid, box[1], box[2], box[3]); idn = (ix * 2, iz); idp = (ix * 2 + 1, iz)
                else: bn = (box[0], box[1], box[2], mid); bp = (box[0], mid, box[2], box[3]); idn = (ix, iz * 2); idp = (ix, iz * 2 + 1)
                A = build(cn, neg, faces, depth + 1, idn[0], idn[1], 1 - axis, bn); B = build(cp, pos, faces, depth + 1, idp[0], idp[1], 1 - axis, bp)
                if depth < kd_depth: stats['kd'] += 1; return ('kd', box, ix, iz, (a, 0.0, b, c), A, B)
                stats['aux'] += 1; return ('pl', (a, 0.0, b, c), 1, 0, A, B)
        k = max(range(len(S)), key=lambda i: math.hypot(S[i][1][0] - S[i][0][0], S[i][1][1] - S[i][0][1]))
        a, b, c = S[k][2]
        neg, pos, on = split_segs(S, a, b, c)
        same = [s for s in on if s[2][0] * a + s[2][1] * b > 0]; opp = [s for s in on if s[2][0] * a + s[2][1] * b <= 0]
        A = build(_clip(cell, a, b, c, False), neg, faces + opp, depth + 1, ix, iz, axis, box)
        B = build(_clip(cell, a, b, c, True), pos, faces + same, depth + 1, ix, iz, axis, box)
        stats['wall plane'] += 1
        return ('pl', (a, 0.0, b, c), 0, surf_wall, A, B)
    import sys; sys.setrecursionlimit(100000)
    box = (float(x0), float(z0), float(x1), float(z1))
    tree = build([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], segs, [], 0, 0, 0, 0, box)
    polys = []
    for k, (p, q, ln) in enumerate(segs):                             # wall quads as 2 triangles, like SEGA
        wy0, wy1 = y0, y1
        if heights is not None: i = min(k // 2, n - 1); wy0 = float(qlo[i]) - below; wy1 = float(qhi[i]) + above
        a3 = (p[0], wy0, p[1]); b3 = (p[0], wy1, p[1]); c3 = (q[0], wy1, q[1]); d3 = (q[0], wy0, q[1])
        polys.append((P3(ln), [a3, b3, c3])); polys.append((P3(ln), [c3, d3, a3]))
    for i, qd in enumerate(quads):
        fy0, fy1 = y0, y1
        if heights is not None: fy0 = float(qlo[i]) - below; fy1 = float(qhi[i]) + above
        for y, pl in ((fy0, (0.0, 1.0, 0.0, -fy0)), (fy1, (0.0, -1.0, 0.0, fy1))):
            v = [(p[0], y, p[1]) for p in qd]; polys.append((pl, [v[0], v[1], v[2]])); polys.append((pl, [v[2], v[3], v[0]]))
    data, fix = serialize(tree, polys, list(surf_ids))
    in_corridor.cells = cells_out
    return data, fix, tree, polys, stats, in_corridor

def check_corridor(tree, in_corridor, bbox, y0, y1, n=20000, seed=3):
    """random points: tree says free <=> point inside the corridor and between floor and ceiling"""
    rng = np.random.default_rng(seed); bad = 0; free = 0; near = 0
    for _ in range(n):
        x = rng.uniform(bbox[0], bbox[2]); z = rng.uniform(bbox[1], bbox[3]); y = rng.uniform(y0 - 3, y1 + 3)
        lf = classify_tree(tree, (x, y, z)); is_free = lf[0] in ('leaf', 'empty')
        want = in_corridor((x, z)) and y0 < y < y1
        free += is_free
        if is_free != want:
            # tolerate points within 2 cm of a boundary
            ok = False
            for dx, dz, dy in ((0.02, 0, 0), (-0.02, 0, 0), (0, 0.02, 0), (0, -0.02, 0), (0, 0, 0.02), (0, 0, -0.02)):
                if (in_corridor((x + dx, z + dz)) and y0 < y + dy < y1) == is_free: ok = True
            if ok: near += 1
            else: bad += 1
    return dict(points=n, free=free, mismatches=bad, boundary_cases=near)

if __name__ == '__main__':
    import os, sys
    from common import *
    import sbfw
    for tr in sys.argv[1:] or SR3:
        f = sbfw.read_sbf(track_files(os.path.join(TRACKS, tr))['master_gfx_xdata']); by = f.byid(); r = f.chunks[-1]
        c = by[r.u32(0x34)]; b = parse_bsp(c)
        tree, polys, surf = to_tree(b); data, fix = serialize(tree, polys, surf)
        print(tr, 'serialize(to_tree(parse)) identical', data == c.data, 'fix', sorted(fix) == sorted(c.fix), 'depth max/mean/leaves', depth_stats(tree))
