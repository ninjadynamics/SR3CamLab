"""Model 3 (Real3D Pro-1000) scene-graph walker for Supermodel save states.
Logic follows Supermodel Src/Graphics/New3D/New3D.cpp (RenderViewport, DescendCullingNode,
DescendNodePtr, DescendPointerList, MultMatrix, CacheModel) with frustum/LOD culling removed.
usage: m3_scene.py <state prefix e.g. srally2_st0> [--obj out.obj] [--tree]
"""
import sys, struct, os
import numpy as np

S = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic"
O = S + "/out/m3/"

class Scene:
    def __init__(self, prefix):
        self.lo = np.fromfile(O + prefix + "_cull_lo.bin", dtype="<u4")
        self.hi = np.fromfile(O + prefix + "_cull_hi.bin", dtype="<u4")
        self.poly = np.fromfile(O + prefix + "_poly.bin", dtype="<u4")
        self.vrom = np.fromfile(O + "vrom_le.bin", dtype="<u4")
        self.lo_f = self.lo.view("<f4"); self.hi_f = self.hi.view("<f4")
        self.models = []      # (vp index, modelAddr, 4x4, path)
        self.nodes_visited = 0
        self.log = []

    def cull(self, addr):
        addr &= 0xFFFFFF
        if 0x800000 <= addr < 0x840000:
            return self.hi, self.hi_f, addr & 0x3FFFF
        if addr < 0x100000:
            return self.lo, self.lo_f, addr
        return None, None, 0

    def matrix(self, idx):
        arr, f, base = self.mbase
        s = f[base + idx * 12: base + idx * 12 + 12]
        m = np.eye(4)
        m[0, :3] = s[3:6]; m[1, :3] = s[6:9]; m[2, :3] = s[9:12]
        m[:3, 3] = s[0:3]
        return m

    def walk_viewports(self, want_tree=False, lod=0):
        addr = 0x800000
        vpi = 0
        seen = set()
        while True:
            arr, f, o = self.cull(addr)
            if arr is None or addr in seen: break
            seen.add(addr)
            vp = arr[o:o + 0x30]
            pri = (int(vp[0]) >> 3) & 3
            self.mbase = self.cull(int(vp[0x16]) & 0xFFFFFF)
            m0 = self.matrix(0)
            print("viewport %d @%06X word0=%08X pri=%d child=%08X next=%08X matbase=%06X size=%.0fx%.0f" % (
                vpi, addr, vp[0], pri, vp[2], vp[1], int(vp[0x16]) & 0xFFFFFF, (int(vp[0x14]) & 0xFFFF) / 4, (int(vp[0x14]) >> 16) / 4))
            print("   matrix0:\n", np.round(m0, 3))
            self.vpi = vpi
            self.lod = lod
            self.want_tree = want_tree
            if not (int(vp[0]) & 0x20):
                self.node_ptr(int(vp[2]), np.eye(4), 0, ())
            nxt = int(vp[1])
            if nxt == 0x01000000 or (nxt & 0xFFFFFF) == 0: break
            addr = nxt & 0xFFFFFF
            vpi += 1

    def node_ptr(self, ptr, mat, depth, path):
        if (ptr & 0xFFFFFF) == 0: return
        t = (ptr >> 24) & 5
        if t == 0: self.node(ptr & 0xFFFFFF, mat, depth, path)
        elif t == 1: self.models.append((self.vpi, ptr & 0xFFFFFF, mat, path))
        elif t == 4:
            arr, f, o = self.cull(ptr & 0xFFFFFF)
            if arr is None: return
            i = 0
            while i < 4096:
                e = int(arr[o + i])
                if e & 0x01000000: break
                self.node(e & 0xFFFFFF, mat, depth, path)
                if e & 0x02000000: break
                i += 1

    def node(self, addr, mat, depth, path):
        # iterate siblings instead of recursing
        while True:
            if depth > 64: return
            arr, f, o = self.cull(addr)
            if arr is None: return
            n = [int(x) for x in arr[o:o + 10]]
            self.nodes_visited += 1
            ntype = n[0] & 3
            child = n[7] & 0x7FFFFFF
            sib = n[8] & 0x1FFFFFF
            mi = n[3] & 0xFFF
            if ntype == 0: return
            if self.want_tree and depth <= self.want_tree:
                self.log.append("%s%06X f=%08X mat=%03X tr=(%.1f,%.1f,%.1f) child=%08X sib=%08X rad=%08X" % (
                    "  " * depth, addr, n[0], mi, f[o + 4], f[o + 5], f[o + 6], n[7], n[8], n[9]))
            if (n[0] & 0x300) != 0x300:
                m = mat
                if n[0] & 0x10:
                    t = np.eye(4); t[:3, 3] = f[o + 4:o + 7]; m = mat @ t
                elif mi:
                    m = mat @ self.matrix(mi)
                p2 = path + (addr,)
                if n[0] & 0x08:
                    la, lf, lo_ = self.cull(child)
                    if la is not None:
                        # choose first LOD entry present (highest detail) unless self.lod given
                        ent = [int(x) for x in la[lo_:lo_ + 4]]
                        e = ent[self.lod]
                        if n[3] & 0x20000000:
                            self.node(e & 0xFFFFFF, m, depth + 1, p2)
                        else:
                            self.models.append((self.vpi, e & 0xFFFFFF, m, p2))
                else:
                    self.node_ptr(child, m, depth + 1, p2)
            if (n[0] & 7) != 6 and not (sib & 0x1000000) and sib:
                addr = sib
                continue
            return

    def model_data(self, maddr):
        maddr &= 0xFFFFFF
        if maddr < 0x100000: return self.poly, maddr
        return self.vrom, maddr


def decode_model(arr, off, vf=1.0 / 2048.0, maxpolys=20000):
    """Return list of polys: (verts[n][3], uv[n][2], header7)."""
    polys = []
    prev = [None] * 4
    pos = off
    n = len(arr)
    for _ in range(maxpolys):
        if pos + 7 > n: break
        h = [int(x) for x in arr[pos:pos + 7]]
        if h[6] == 0: break
        nv = 4 if h[0] & 0x40 else 3
        vs = []
        for i in range(4):
            if h[0] & (1 << i):
                if prev[i] is None:
                    return polys, False
                vs.append(prev[i])
        d = pos + 7
        while len(vs) < nv:
            if d + 4 > n: return polys, False
            ix, iy, iz, it = [int(x) for x in arr[d:d + 4]]
            def s24(v):
                v >>= 8
                return v - 0x1000000 if v & 0x800000 else v
            vs.append((s24(ix) * vf, s24(iy) * vf, s24(iz) * vf, it >> 16, it & 0xFFFF))
            d += 4
        if not ((h[0] & 0x300) == 0x300):
            polys.append((vs[:nv], h))
        for i in range(nv): prev[i] = vs[i]
        if h[1] & 4: return polys, True
        pos = d
    return polys, False


if __name__ == "__main__":
    prefix = sys.argv[1]
    sc = Scene(prefix)
    tree = 0
    if "--tree" in sys.argv: tree = int(sys.argv[sys.argv.index("--tree") + 1])
    sc.walk_viewports(want_tree=tree)
    print("nodes visited", sc.nodes_visited, "model refs", len(sc.models))
    from collections import Counter
    c = Counter()
    for vpi, ma, m, p in sc.models:
        c[(vpi, "vrom" if ma >= 0x100000 else "polyram")] += 1
    print(c)
    uniq = set(ma for _, ma, _, _ in sc.models)
    print("unique models", len(uniq), "vrom range", [hex(x) for x in (min([u for u in uniq if u >= 0x100000] or [0]), max(uniq))])
    if tree:
        open(O + prefix + "_tree.txt", "w").write("\n".join(sc.log))
        print("\n".join(sc.log[:120]))
