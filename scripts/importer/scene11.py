"""Kind 11 chunk = SceneManager block tree (master_gfx root +0x04). Parser, checker and minimal builder.
See ../../05_scene_kind11.md"""
import struct, collections
import numpy as np
from common import *
import sbfw

class Node: pass
def parse11(c):
    d = c.data; s = type('S', (), {})(); s.c = c
    s.ver, s.nleaf, s.nnode, s.leafsize, s.p_light, s.bitbytes, s.scale = struct.unpack_from('<IHHfIHH', d, 0)
    s.nodes = []
    fix = set(c.fix); ref = set(c.ref)
    for i in range(s.nnode):
        o = 0x20 + 0x20 * i; n = Node(); n.i = i; n.o = o
        n.bb = struct.unpack_from('<6h', d, o); n.cont, = struct.unpack_from('<I', d, o + 0xc); n.ch = struct.unpack_from('<4H', d, o + 0x10)
        n.leafp, n.parent, n.gx, n.gz = struct.unpack_from('<IHBB', d, o + 0x18)
        n.meshes = []; n.inst = 0
        if n.cont:
            assert (o + 0xc) in fix
            n.inst, k = struct.unpack_from('<II', d, n.cont)
            n.meshes = list(struct.unpack_from('<%dI' % k, d, n.cont + 8))
            assert all((n.cont + 8 + 4 * j) in ref for j in range(k))
        n.stream = None
        if n.leafp:
            k, pa = struct.unpack_from('<II', d, n.leafp); n.leaf_n = k
            n.leaf_a = struct.unpack_from('<%dI' % k, d, pa); pb, = struct.unpack_from('<I', d, pa + 4 * k)
            n.leaf_pa = pa; n.leaf_pb = pb
            n.stream = d[pb:pb + 64]
        s.nodes.append(n)
    return s

def pvs_decode(stream, nnode):
    """leaf visibility stream -> bool list. 0xFF n = n*8 nodes visible, 0x00 n = n*8 nodes hidden, other = 8 literal bits (LSB first).
    (exe 0x4FFC30)"""
    out = []; p = 0
    while len(out) < nnode:
        b = stream[p]; p += 1
        if b == 0xff or b == 0:
            k = stream[p] * 8; p += 1
            out += [b == 0xff] * min(k, nnode - len(out))
            if k == 0: break
        else:
            out += [bool((b >> j) & 1) for j in range(8)]
    return out[:nnode], p

def pvs_all_visible(nnode):
    """stream marking every node visible (same shape as Stadium4's: FF <n//8> <literal for the remainder> 00)"""
    q, r = divmod(nnode, 8); s = b''
    while q > 0:
        k = min(q, 255); s += bytes([0xff, k]); q -= k
    if r: s += bytes([(1 << r) - 1])
    return s + b'\0'

# ------------------------------------------------------------------ minimal builder
def build11(leaves, root_meshes, world=750.0, depth=5, scale=16, ybox=(-50.0, 200.0), light=None):
    """leaves: iterable of (ix, iz) leaf cells (0..2^depth-1) that must exist; root_meshes: list of mesh chunk ids drawn from the
    root node (always considered; culled only by the root box). Returns (data, fix, ref).
    Layout: header 0x20 | nodes (pre-order) | root content | leaf records {1, ->a, a0=0, ->b, stream padded to 4}."""
    size = 2 * world; nside = 1 << depth
    leaves = sorted(set(leaves))
    nodes = []
    def make(level, gx, gz, parent):
        """gx,gz 0-based cell at this level"""
        side = 1 << level; span = nside >> level
        inside = [(x, z) for (x, z) in leaves if gx * span <= x < (gx + 1) * span and gz * span <= z < (gz + 1) * span]
        if not inside: return 0
        idx = len(nodes); nd = dict(level=level, gx=gx, gz=gz, parent=parent, ch=[0, 0, 0, 0]); nodes.append(nd)
        if level < depth:
            for q, (dx, dz) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                nd['ch'][q] = make(level + 1, gx * 2 + dx, gz * 2 + dz, idx)
        return idx
    make(0, 0, 0, 0xffff)
    nn = len(nodes); nleaf = sum(1 for n in nodes if n['level'] == depth)
    p_nodes = 0x20; p = p_nodes + 0x20 * nn
    p_cont = p if root_meshes else 0
    if root_meshes: p += 8 + 4 * len(root_meshes)
    stream = pvs_all_visible(nn); stream += b'\0' * (-len(stream) % 4)
    rec = 4 + 4 + 4 + 4 + len(stream)
    out = bytearray(struct.pack('<IHHfIHH', 2, nleaf, nn, size / nside, 0, (nn + 7) >> 3, scale)) + bytes(12)
    fix = []; ref = []
    q = lambda v: int(round(v * scale))
    for i, nd in enumerate(nodes):
        cell = size / (1 << nd['level'])
        x0 = -world + nd['gx'] * cell; z0 = -world + nd['gz'] * cell
        o = len(out)
        leafp = 0
        if nd['level'] == depth:
            leafp = p; p += rec; fix.append(o + 0x18)
        cont = p_cont if i == 0 else 0
        if cont: fix.append(o + 0xc)
        out += struct.pack('<6hI4HIHBB', q(x0), q(ybox[0]), q(z0), q(x0 + cell), q(ybox[1]), q(z0 + cell), cont, *nd['ch'],
                           leafp, nd['parent'], nd['gx'] + 1, nd['gz'] + 1)
    if root_meshes:
        o = len(out); out += struct.pack('<II', 0, len(root_meshes)) + struct.pack('<%dI' % len(root_meshes), *root_meshes)
        ref += [o + 8 + 4 * j for j in range(len(root_meshes))]
    for nd in nodes:
        if nd['level'] == depth:
            o = len(out)
            out += struct.pack('<IIII', 1, o + 8, 0, o + 16) + stream
            fix += [o + 4, o + 12]
    assert len(out) == p
    return bytes(out), sorted(fix), ref

if __name__ == '__main__':
    import sys
    for tr in sys.argv[1:] or SR3:
        f = sbfw.read_sbf(track_files(os.path.join(TRACKS, tr))['master_gfx_xdata'])
        by = f.byid(); r = f.chunks[-1]; s = parse11(by[r.u32(4)])
        st = collections.Counter(); nn = s.nnode
        for n in s.nodes:
            kids = [k for k in n.ch if k]
            for q, k in enumerate(n.ch):
                if not k: continue
                cb = s.nodes[k].bb; st['child idx > parent'] += k > n.i
                st['parent field ok'] += s.nodes[k].parent == n.i
                st[('quadrant', q, s.nodes[k].gx - 2 * n.gx + 2, s.nodes[k].gz - 2 * n.gz + 2)] += 1
                st['child box in parent'] += all(cb[j] >= n.bb[j] for j in (0, 2)) and all(cb[j] <= n.bb[j] for j in (3, 5))
            if kids and n.ch != tuple(sorted(n.ch, key=lambda v: (v == 0, v))) and False: st['unsorted'] += 1
            if n.leafp:
                vis, used = pvs_decode(n.stream + s.c.data[n.leaf_pb + 64:n.leaf_pb + 4096], nn)
                st['leaf streams'] += 1; st['leaf all-visible'] += all(vis); st[('leaf_n', n.leaf_n, n.leaf_a)] += 1
                st[('leaf rec contiguous', n.leaf_pa - n.leafp, n.leaf_pb - n.leaf_pa - 4 * n.leaf_n)] += 1
                st[('leaf xz size', (n.bb[3] - n.bb[0]) / s.scale, (n.bb[5] - n.bb[2]) / s.scale)] += 1
        pre = all(s.nodes[i].parent < i or s.nodes[i].parent == 0xffff for i in range(nn))
        print(tr, 'nodes', nn, 'leaves', s.nleaf, 'preorder parent<child', pre, 'root', s.nodes[0].bb, s.nodes[0].gx, s.nodes[0].gz, 'root meshes', len(s.nodes[0].meshes), 'inst', s.nodes[0].inst)
        for k, v in sorted(st.items(), key=str): print('    ', k, v)
