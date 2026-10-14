"""SR3 car model files: the kind-1 model chunk of chassismodel / bespokemodel / gravelmodel / mud / snow / bonnet files
as objects, and back, byte for byte. Plus id remapping for a set of car files (a car cloned under a new name).

    m = read_model(chunk)          # sbfw.Ch of kind 1 -> Model
    ch = m.to_chunk(chunk.id)      # Model -> sbfw.Ch (data, fixup list, ref list) - identical to SEGA's for their files
    python carmodel.py roundtrip <file or folder> ...    # proves it (decompressed file bytes compared)

Layout of the chunk data (all offsets relative to the chunk data; found on the ten arcade cars, docs/kb):
  [mesh headers]   0x48 bytes each: stride, 0, format, 0, 0, nVerts, 0, nIdx, nGroups, 0, 0, ptr groups, ptr verts,
                   ptr idx, 0, 0, 0, 0
  per mesh, in header order: groups (20 bytes each: firstVertex, nVerts, firstIndex, flags << 16 | indexCount,
                   ref material), vertices (nVerts * stride), u16 strip indices (nIdx), padding to 4
  [node records]   0x9C bytes each: +0 ptr parent (or 0), +4 ptr name, +8 flags, +0xC 0, +0x10 ptr mesh header (or
                   not a pointer), +0x14 4x4 matrix (row-major, translation at +0x44), +0x54 64 bytes (zero; run time),
                   +0x94 child count, +0x98 ptr child list (or 0)
  [child lists]    one list of node pointers per node that has children, in node order
  [names]          0-terminated, in node order, padded to 4
  [tail record]    ptr first node, node count, 0, 0, f32 bbox min xyz, max xyz, centre xyz, ... (kept as raw words)
Fixup order: the 3 pointers of every header; then per node in record order: child-list pointer and its entries, parent,
name, mesh; then the tail pointer. Ref order: the material of every group, headers in order.
Vertex formats seen: 0x2047 (44 bytes: xyzw, normal, tangent, u16 uv0 / 32768), 0x2057 (48), 0x2051 (24, shadows),
0x2001 (16), 0x23d7 (60, mud shell).
"""
import os, sys, struct, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbfw

HDR = 0x48
NODE = 0x9C
GROUP = 20


class Mesh:
    __slots__ = ("hdr", "groups", "vdata", "idx", "pad")

    def __init__(self, hdr, groups, vdata, idx, pad=b""):
        self.hdr = list(hdr)            # 18 u32; words 11..13 (pointers) are rewritten on output
        self.groups = [list(g) for g in groups]   # [firstVertex, nVerts, firstIndex, flags<<16 | count, material id]
        self.vdata = bytes(vdata)
        self.idx = bytes(idx)
        self.pad = bytes(pad)           # bytes after the indices (padding to 4)

    stride = property(lambda s: s.hdr[0])
    fmt = property(lambda s: s.hdr[2])
    nverts = property(lambda s: s.hdr[5])
    nidx = property(lambda s: s.hdr[7])


class Node:
    __slots__ = ("parent", "name", "flags", "w3", "mesh", "matrix", "rt", "nch", "children")

    def __init__(self, name, parent=None, mesh=None, flags=0, w3=0, matrix=None, rt=None, nch=None, children=()):
        self.name = name; self.parent = parent; self.mesh = mesh; self.flags = flags; self.w3 = w3
        self.matrix = bytes(matrix) if matrix is not None else struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        self.rt = bytes(rt) if rt is not None else bytes(64)
        self.children = list(children)
        self.nch = len(self.children) if nch is None else nch

    def translation(self): return struct.unpack_from("<3f", self.matrix, 48)

    def set_translation(self, x, y, z):
        m = bytearray(self.matrix); struct.pack_into("<3f", m, 48, x, y, z); self.matrix = bytes(m)


class Model:
    def __init__(self, meshes, nodes, tail_root, tail_words, gap_after_headers=b"", gap_after_meshes=b"", names_pad=None):
        self.meshes = meshes; self.nodes = nodes
        self.tail_root = tail_root          # node index the tail record points at
        self.tail_words = bytes(tail_words)  # tail record after its pointer (node count is rewritten)
        self.gap_after_headers = gap_after_headers; self.gap_after_meshes = gap_after_meshes
        self.names_pad = names_pad

    def node(self, name):
        for i, n in enumerate(self.nodes):
            if n.name == name: return i
        return None

    def to_chunk(self, cid, kind=1, z=0):
        d, fix, ref = self.serialize()
        return sbfw.Ch(kind, cid, d, fix, ref, z)

    def serialize(self):
        out = bytearray(); fix = []; ref = []
        nh = len(self.meshes)
        out += bytes(HDR * nh) + self.gap_after_headers
        hpos = []
        for m in self.meshes:
            g = len(out)
            for gr in m.groups: out += struct.pack("<5I", *gr)
            v = len(out); out += m.vdata
            ix = len(out); out += m.idx + m.pad
            hpos.append((g, v, ix))
        out += self.gap_after_meshes
        nstart = len(out)
        noff = [nstart + NODE * i for i in range(len(self.nodes))]
        out += bytes(NODE * len(self.nodes))
        lists = {}
        for i, n in enumerate(self.nodes):
            if n.children:
                lists[i] = len(out); out += b"".join(struct.pack("<I", noff[c]) for c in n.children)
        names = {}
        for i, n in enumerate(self.nodes):
            names[i] = len(out); out += n.name.encode("latin1") + b"\0"
        out += (b"\0" * (-len(out) % 4)) if self.names_pad is None else self.names_pad
        tail = len(out)
        out += struct.pack("<I", noff[self.tail_root]) + self.tail_words
        # headers
        for k, m in enumerate(self.meshes):
            h = list(m.hdr); h[11], h[12], h[13] = hpos[k]
            struct.pack_into("<18I", out, HDR * k, *h)
            fix += [HDR * k + 0x2C, HDR * k + 0x30, HDR * k + 0x34]
        # nodes
        for i, n in enumerate(self.nodes):
            o = noff[i]
            rec = struct.pack("<5I", noff[n.parent] if n.parent is not None else 0, names[i], n.flags, n.w3,
                              HDR * n.mesh if n.mesh is not None else 0) + n.matrix + n.rt + struct.pack(
                              "<2I", n.nch, lists.get(i, 0))
            out[o:o + NODE] = rec
            if n.children:
                fix.append(o + 0x98); fix += [lists[i] + 4 * j for j in range(len(n.children))]
            if n.parent is not None: fix.append(o)
            fix.append(o + 4)
            if n.mesh is not None: fix.append(o + 0x10)
        fix.append(tail)
        struct.pack_into("<I", out, tail + 4, len(self.nodes))
        for k, m in enumerate(self.meshes):
            ref += [hpos[k][0] + GROUP * j + 16 for j in range(len(m.groups))]
        return bytes(out), fix, ref


def read_model(c):
    d = c.data; fix = set(c.fix)
    g0 = struct.unpack_from("<I", d, 0x2C)[0]
    nh = 0
    while HDR * (nh + 1) <= g0 and HDR * nh + 0x34 in fix: nh += 1
    meshes = []; end = HDR * nh
    gap_h = d[HDR * nh:g0]
    for k in range(nh):
        h = list(struct.unpack_from("<18I", d, HDR * k))
        g, v, ix = h[11], h[12], h[13]
        assert g == end + (len(gap_h) if k == 0 else 0), "mesh %d groups not where expected (%x, %x)" % (k, g, end)
        groups = [list(struct.unpack_from("<5I", d, g + GROUP * j)) for j in range(h[8])]
        assert v == g + GROUP * h[8] and ix == v + h[0] * h[5], "mesh %d layout" % k
        e = ix + 2 * h[7]; pe = e + (-e % 4)
        meshes.append(Mesh(h, groups, d[v:ix], d[ix:e], d[e:pe]))
        end = pe
    tail = c.fix[-1]
    first = struct.unpack_from("<I", d, tail)[0]
    count = struct.unpack_from("<I", d, tail + 4)[0]
    gap_m = d[end:first]
    noff = {first + NODE * i: i for i in range(count)}
    nodes = []
    for i in range(count):
        o = first + NODE * i
        w = struct.unpack_from("<5I", d, o)
        par = noff[w[0]] if o in fix else None
        name = d[w[1]:d.index(b"\0", w[1])].decode("latin1")
        mesh = w[4] // HDR if (o + 0x10) in fix else None
        nch, lp = struct.unpack_from("<2I", d, o + 0x94)
        ch = [noff[struct.unpack_from("<I", d, lp + 4 * j)[0]] for j in range(nch)] if (o + 0x98) in fix else []
        nodes.append(Node(name, par, mesh, w[2], w[3], d[o + 0x14:o + 0x54], d[o + 0x54:o + 0x94], nch, ch))
    # names end / padding before the tail
    last_name = struct.unpack_from("<I", d, first + NODE * (count - 1) + 4)[0]
    ne = d.index(b"\0", last_name) + 1
    m = Model(meshes, nodes, noff[first], d[tail + 4:], gap_h, gap_m, d[ne:tail])
    return m


def model_chunks(f):
    return [c for c in f.chunks if c.kind == 1]


# ------------------------------------------------------------------------------------------------ textures (kind 4)
class Texture:
    """kind 4 data = 11 u32 (1, 0, width, height, 0, sampler words ...) + 'DDS ' + 124-byte DDS header + pixels"""
    def __init__(self, data):
        self.words = list(struct.unpack_from("<11I", data, 0))
        assert data[44:48] == b"DDS ", "not a texture chunk"
        self.dds = data[48:48 + 124]
        self.pixels = data[48 + 124:]

    width = property(lambda s: s.words[2])
    height = property(lambda s: s.words[3])
    fourcc = property(lambda s: s.dds[80:84])

    def to_bytes(self):
        return struct.pack("<11I", *self.words) + b"DDS " + self.dds + self.pixels


# ------------------------------------------------------------------------------------------------ id remapping
def all_ids(f):
    return {c.id for c in f.chunks}


def remap(f, mapping):
    """rename chunk ids and every ref field (all chunks) with mapping {old: new}; kind 13 texture-pack tables also
    have their placeholder ids (the word after each texture ref) remapped. In place; returns the file."""
    for c in f.chunks:
        d = bytearray(c.data)
        for o in c.ref:
            v = struct.unpack_from("<I", d, o)[0]
            if v in mapping: struct.pack_into("<I", d, o, mapping[v])
        if c.kind == 13:
            n = struct.unpack_from("<I", d, 4)[0]
            for j in range(n):
                o = 8 + 8 * j + 4
                v = struct.unpack_from("<I", d, o)[0]
                if v in mapping: struct.pack_into("<I", d, o, mapping[v])
        c.data = bytes(d)
        if c.id in mapping: c.id = mapping[c.id]
    return f


def placeholders(f):
    """placeholder ids of a texture-pack file (kind 13 table {1, n, n x (ref texture, placeholder)})"""
    out = []
    for c in f.chunks:
        if c.kind == 13:
            n = struct.unpack_from("<I", c.data, 4)[0]
            out += [struct.unpack_from("<I", c.data, 8 + 8 * j + 4)[0] for j in range(n)]
    return out


def fresh_id(tag, old, taken):
    k = 0
    while True:
        v = zlib.crc32(("%s:%08x:%d" % (tag, old, k)).encode()) & 0xFFFFFFFF
        if v not in taken and v not in (0, 0xFFFFFFFF): taken.add(v); return v
        k += 1


# ------------------------------------------------------------------------------------------------ writing files
def tail_of(f):
    """the file's tail: its bytes when they are not all zero (bonnet files carry a trailer), else the zero count"""
    t = f.raw[len(f.raw) - f.tail:] if f.tail else b""
    return t if any(t) else f.tail


def write_file(f, path, keep_layout=True):
    """write an SbfFile read with sbfw.read_sbf (and possibly edited): same compression as read; original padding
    when keep_layout and the chunk sizes allow it, else the alignment rules. Returns the bytes written."""
    raw = sbfw.write_raw(f.chunks, f.first, tail_of(f), f.hdr, layout="keep" if keep_layout else "auto")
    b = b"SBZ1" + struct.pack("<I", len(raw)) + zlib.compress(raw, 9) if f.compressed else raw
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, "wb").write(b)
    return b


# ------------------------------------------------------------------------------------------------ round trip
def roundtrip_file(path):
    """-> (ok, message). Rebuilds every kind-1 chunk from its Model and rewrites the file with the original layout;
    compares the decompressed bytes."""
    f = sbfw.read_sbf(path)
    n = 0
    for i, c in enumerate(f.chunks):
        if c.kind != 1: continue
        m = read_model(c)
        d, fx, rf = m.serialize()
        if d != c.data: return False, "chunk %08x data differs (%d vs %d bytes)" % (c.id, len(d), len(c.data))
        if fx != c.fix: return False, "chunk %08x fixup list differs" % c.id
        if rf != c.ref: return False, "chunk %08x ref list differs" % c.id
        f.chunks[i] = sbfw.Ch(c.kind, c.id, d, fx, rf, c.z, c.gap)
        n += 1
    for i, c in enumerate(f.chunks):
        if c.kind == 4:
            b = Texture(c.data).to_bytes()
            if b != c.data: return False, "texture %08x differs" % c.id
            f.chunks[i] = sbfw.Ch(c.kind, c.id, b, c.fix, c.ref, c.z, c.gap)
    raw = sbfw.write_raw(f.chunks, f.first, tail_of(f), f.hdr, layout="keep")
    if raw != f.raw: return False, "file bytes differ"
    return True, "%d model chunk(s), %d bytes identical%s" % (n, len(raw), " (SBZ1 file: zlib stream not compared)" if f.compressed else "")


if __name__ == "__main__":
    if sys.argv[1] == "roundtrip":
        paths = []
        for a in sys.argv[2:]:
            if os.path.isdir(a):
                for root, _, fs in os.walk(a):
                    paths += [os.path.join(root, x) for x in sorted(fs) if x.lower().endswith(".sbf")]
            else: paths.append(a)
        bad = 0
        for p in paths:
            try: f = sbfw.read_sbf(p)
            except ValueError as e: print("skip %s (%s)" % (os.path.basename(p), e)); continue
            if not model_chunks(f): continue
            try: ok, msg = roundtrip_file(p)
            except Exception as e: ok, msg = False, "%s: %s" % (type(e).__name__, e)
            bad += not ok
            print("%-4s %-42s %s" % ("OK" if ok else "FAIL", os.path.basename(p), msg))
        print("failures:", bad)
