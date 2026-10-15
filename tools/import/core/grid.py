"""Parser for the 'route grid' chunk (track root +0x08): a quadtree over 2 m cells with 8-neighbour links."""
import struct, collections
import numpy as np
from common import *
import sbfw

class Grid: pass
def parse_grid(c):
    d = c.data; g = Grid()
    g.ver, g.n, g.cell, g.w3, g.root = struct.unpack_from('<IIfII', d, 0)
    fix = set(c.fix)
    g.nodes = []; g.cells = {}; g.leaf_of = {}
    def node(o, depth):
        x0, z0, x1, z1, cnt, ptr, c0, c1, c2, c3 = struct.unpack_from('<4f6I', d, o)
        g.nodes.append((o, depth, x0, z0, x1, z1, cnt, ptr, (c0, c1, c2, c3)))
        for k, ch in enumerate((c0, c1, c2, c3)):
            if ch:
                assert (o + 0x18 + 4 * k) in fix
                node(ch, depth + 1)
        if cnt:
            assert (o + 0x14) in fix
            for i in range(cnt):
                p = ptr + 0x30 * i
                x, z = struct.unpack_from('<ff', d, p); nb = struct.unpack_from('<8I', d, p + 8); idx, fl = struct.unpack_from('<II', d, p + 0x28)
                g.cells[p] = (x, z, nb, idx, fl); g.leaf_of[p] = o
    node(g.root, 0)
    return g

if __name__ == '__main__':
    import sys
    for t in (sys.argv[1:] or SR3):
        f = sbfw.read_sbf(track_files(os.path.join(TRACKS, t))['master_xdata'])
        root = f.chunks[-1]; c = f.get(root.u32(8)); g = parse_grid(c)
        cells = g.cells
        xs = np.array([v[0] for v in cells.values()]); zs = np.array([v[1] for v in cells.values()])
        idx = sorted(v[3] for v in cells.values())
        print(t, 'ver', g.ver, 'n', g.n, 'cell', g.cell, 'w3', g.w3, 'cells parsed', len(cells), 'nodes', len(g.nodes), 'idx contiguous', idx == list(range(len(cells))),
              'x', xs.min(), xs.max(), 'z', zs.min(), zs.max(), 'size expected', max(cells) + 0x30, len(c.data))
        print('   flags', collections.Counter('%08x' % v[4] for v in cells.values()).most_common(8))
        print('   coords mod 2:', collections.Counter((v[0] % 2, v[1] % 2) for v in cells.values()).most_common(4))
        # neighbour direction per slot
        dirs = collections.defaultdict(collections.Counter)
        for p, (x, z, nb, i, fl) in cells.items():
            for k, q in enumerate(nb):
                if q: dirs[k][(cells[q][0] - x, cells[q][1] - z)] += 1
        for k in range(8): print('   nb slot', k, dirs[k].most_common(3))
        nn = collections.Counter(sum(1 for q in v[2] if q) for v in cells.values()); print('   neighbour count hist', sorted(nn.items()))
        depth = collections.Counter(n[1] for n in g.nodes if n[6]); print('   leaf depth', sorted(depth.items()), 'leaf sizes max', max(n[6] for n in g.nodes))
        leafdim = collections.Counter((n[4] - n[2], n[5] - n[3]) for n in g.nodes if n[6]); print('   leaf dims', leafdim.most_common(6))
        print('   root', g.nodes[0][:8])

# ------------------------------------------------------------------ builder
NB = [(0, 2), (2, 2), (2, 0), (2, -2), (0, -2), (-2, -2), (-2, 0), (-2, 2)]
def build_grid(cells, cell=2.0, leaf_max=50):
    """cells: list of (x, z, flags) with x,z odd integers (cell centres). Returns (data, fix).
    Quadtree: root bbox = extent of centres +-4; split point floor(mid/2)*2+2; children order (-x+z, +x+z, +x-z, -x-z);
    a node with more than leaf_max cells is split; nodes are written depth-first, then the cells leaf by leaf."""
    import math
    xs = [c[0] for c in cells]; zs = [c[1] for c in cells]
    nodes = []            # dict(bbox, cells(list idx) or None, children[4])
    def make(idx, x0, z0, x1, z1):
        nd = dict(b=(x0, z0, x1, z1), cells=None, ch=[None] * 4); nodes.append(nd)
        if len(idx) <= leaf_max: nd['cells'] = idx; return nd
        mx = math.floor((x0 + x1) / 2 / cell) * cell + cell; mz = math.floor((z0 + z1) / 2 / cell) * cell + cell
        quads = [[], [], [], []]
        for i in idx:
            x, z = cells[i][0], cells[i][1]
            q = (0 if x < mx else 1) if z >= mz else (3 if x < mx else 2)
            quads[q].append(i)
        boxes = [(x0, mz, mx, z1), (mx, mz, x1, z1), (mx, z0, x1, mz), (x0, z0, mx, mz)]
        for q in range(4):
            if quads[q]: nd['ch'][q] = make(quads[q], *boxes[q])
        return nd
    root = make(list(range(len(cells))), min(xs) - 2 * cell, min(zs) - 2 * cell, max(xs) + 2 * cell, max(zs) + 2 * cell)
    off = 0x14
    for nd in nodes: nd['o'] = off; off += 0x28
    order = []
    for nd in nodes:
        if nd['cells']:
            nd['p'] = off; order += nd['cells']; off += 0x30 * len(nd['cells'])
    pos = {}; where = {}
    for k, i in enumerate(order):
        where[(cells[i][0], cells[i][1])] = nodes_cell_off = None
    base = [nd for nd in nodes if nd['cells']][0]['p'] if order else off
    for k, i in enumerate(order): where[(cells[i][0], cells[i][1])] = base + 0x30 * k
    out = bytearray(struct.pack('<IIfII', 1, len(cells), cell, 0, 0x14)); fix = [0x10]
    for nd in nodes:
        o = nd['o']; assert len(out) == o
        cnt = len(nd['cells']) if nd['cells'] else 0
        out += struct.pack('<4f6I', *nd['b'], cnt, nd['p'] if cnt else 0, *[(c['o'] if c else 0) for c in nd['ch']])
        if cnt: fix.append(o + 0x14)
        for q in range(4):
            if nd['ch'][q]: fix.append(o + 0x18 + 4 * q)
    for k, i in enumerate(order):
        x, z, fl = cells[i]; o = len(out)
        nb = [where.get((x + dx, z + dz), 0) for dx, dz in NB]
        out += struct.pack('<ff8IHHI', x, z, *nb, k, 0, fl)
        fix += [o + 8 + 4 * j for j in range(8) if nb[j]]
    return bytes(out), sorted(fix)

def grid_cells(g):
    return [(v[0], v[1], v[4]) for p, v in sorted(g.cells.items())]
