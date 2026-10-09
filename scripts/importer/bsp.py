"""TrackBoundary wall BSP (master_gfx root +0x34): parser, point classifier, builder. See ../../06_boundary_collision.md
Reader in the exe: 0x42C7F0 (arrays) and 0x42AD80 (tree linker: pre-order type list, child A then child B)."""
import struct, collections, math
import numpy as np
from common import *
import sbfw

KD = np.dtype([('box', '<f4', 4), ('ix', '<u4'), ('iz', '<u4'), ('has', '<u4'), ('pl', '<f4', 4)])
PL = np.dtype([('pl', '<f4', 4), ('flag', '<u4'), ('surf', '<u4')])
PO = np.dtype([('n', '<u4'), ('pl', '<f4', 4), ('v', '<f4', (4, 3))])
assert KD.itemsize == 0x2c and PL.itemsize == 0x18 and PO.itemsize == 0x44

class Bsp: pass
def parse_bsp(c):
    d = c.data; b = Bsp(); b.c = c
    h = struct.unpack_from('<16I', d, 0); b.h = h
    b.ver, b.nkd, b.npl, b.n3, b.n4, b.nleaf, b.npoly, b.nsurf = h[:8]
    b.p_kd, b.p_pl, b.p_a, b.p_b, b.p_leaf, b.p_types, b.p_poly, b.p_surf = h[8:]
    b.kd = np.frombuffer(d, KD, b.nkd, b.p_kd); b.pl = np.frombuffer(d, PL, b.npl, b.p_pl)
    b.leaves = []
    for i in range(b.nleaf):
        n, pa, pb = struct.unpack_from('<III', d, b.p_leaf + 12 * i)
        b.leaves.append((np.frombuffer(d, '<f4', 4 * n, pa).reshape(n, 4), np.frombuffer(d, '<u4', n, pb), pa, pb))
    ntypes = b.nkd + b.npl + b.n3 + b.n4 + b.nleaf
    b.types = np.frombuffer(d, '<u4', ntypes, b.p_types)
    b.poly = np.frombuffer(d, PO, b.npoly, b.p_poly); b.surf = list(struct.unpack_from('<%dI' % b.nsurf, d, b.p_surf))
    # link the tree: nodes = (type, record index, childA, childB)
    cnt = collections.Counter(); pos = [0]; b.nodes = []
    def read():
        t = int(b.types[pos[0]]); pos[0] += 1; k = cnt[t]; cnt[t] += 1
        me = len(b.nodes); b.nodes.append([t, k, -1, -1])
        if t in (1, 2):
            a = read(); bb = read(); b.nodes[me][2] = a; b.nodes[me][3] = bb
        return me
    import sys; sys.setrecursionlimit(100000)
    b.root = read(); assert pos[0] == ntypes, (pos[0], ntypes)
    return b

def classify(b, p):
    """descend: child A = negative side of the node plane, child B = positive side. Returns node index of the leaf."""
    i = b.root
    while True:
        t, k, a, bb = b.nodes[i]
        if t == 2: pl = b.kd[k]['pl']
        elif t == 1: pl = b.pl[k]['pl']
        else: return i
        s = pl[0] * p[0] + pl[1] * p[1] + pl[2] * p[2] + pl[3]
        i = a if s < 0 else bb

if __name__ == '__main__':
    import sys
    for tr in sys.argv[1:] or ['Stadium4']:
        f = sbfw.read_sbf(track_files(os.path.join(TRACKS, tr))['master_gfx_xdata']); by = f.byid(); r = f.chunks[-1]
        b = parse_bsp(by[r.u32(0x34)])
        print(tr, 'kd', b.nkd, 'planes', b.npl, 'n3', b.n3, 'n4', b.n4, 'leaves', b.nleaf, 'polys', b.npoly, 'types', collections.Counter(b.types.tolist()))
        # where does each poly centroid (pushed slightly inside along -normal) fall
        res = collections.Counter(); inside_ok = collections.Counter()
        for p in b.poly:
            c = p['v'][:3].mean(0); n = p['pl'][:3]
            for sgn, tag in ((-0.05, 'behind'), (0.05, 'front')):
                q = c + n * sgn; leaf = classify(b, q); t, k = b.nodes[leaf][:2]
                res[(tag, t)] += 1
                if t == 5:
                    pl = b.leaves[k][0]; s = pl[:, :3] @ q + pl[:, 3]
                    inside_ok[(tag, bool((s >= -1e-3).all()), bool((s <= 1e-3).all()))] += 1
        print('   poly centroid +-5cm along poly normal -> leaf type', dict(res)); print('   type-5 hits: (side, all faces >=0, all <=0)', dict(inside_ok))
        # random points
        rng = np.random.default_rng(1); V = b.poly['v'][:, :3].reshape(-1, 3); lo = V.min(0); hi = V.max(0)
        rt = collections.Counter(); t4 = []
        for q in rng.uniform(lo - 20, hi + 20, (20000, 3)):
            leaf = classify(b, q); t = b.nodes[leaf][0]; rt[t] += 1
            if t == 4: t4.append(q)
        print('   random points -> leaf types', dict(rt))
        if t4: t4 = np.array(t4); print('   type 4 points: bbox', t4.min(0).round(1), t4.max(0).round(1), 'poly bbox', lo.round(1), hi.round(1))
        print('   kd has-plane', collections.Counter(b.kd['has'].tolist()), 'plane flags', collections.Counter(b.pl['flag'].tolist()))
        # per plane node: is its plane coplanar with a face of a leaf in subtree B / A ?
