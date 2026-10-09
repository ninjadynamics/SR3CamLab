"""SBF container: full-fidelity reader + writer (little-endian PC/arcade form).

read_sbf(path)  -> SbfFile (list of Ch objects; remembers original padding so a rewrite can be byte-identical)
write_sbf(sbffile or list of Ch, compress=True, layout='auto') -> bytes

Layout rules (see ../../01_container.md):
  header: u32 4,0,0,0,0,count ; then count x (id, offset)
  chunk : kind, id, size, type(z), nfix, fix[nfix], nref, ref[nref], data[size]
  data alignment (file offset of data, modulo 16): kinds 5,6,11,13 -> 0 ; kind 4 -> 4 (and pixel data at
  offset %4096 == 0 in SEGA's own files, i.e. data %4096 == 0xF54) ; kind 7 -> 8 (granny files) ; others -> 4-byte.
  2048 zero bytes at the end.
"""
import struct, zlib

ALIGN16 = {5: 0, 6: 0, 11: 0, 13: 0, 4: 4, 7: 8}

class Ch:
    __slots__ = ('kind', 'id', 'z', 'fix', 'ref', 'data', 'gap', 'off')
    def __init__(self, kind, id, data, fix=(), ref=(), z=0, gap=None):
        self.kind = kind; self.id = id; self.z = z; self.fix = list(fix); self.ref = list(ref)
        self.data = bytes(data); self.gap = gap; self.off = None
    def u32(self, o): return struct.unpack_from('<I', self.data, o)[0]
    def f32(self, o): return struct.unpack_from('<f', self.data, o)[0]
    def refs(self): return [self.u32(o) for o in self.ref]
    def copy(self):
        return Ch(self.kind, self.id, self.data, self.fix, self.ref, self.z, self.gap)
    def __repr__(self): return 'Ch(k%d %08x z%08x size %d fix %d ref %d)' % (self.kind, self.id, self.z, len(self.data), len(self.fix), len(self.ref))

class SbfFile:
    def __init__(self):
        self.chunks = []; self.hdr = (4, 0, 0, 0, 0); self.first = None; self.tail = 2048; self.compressed = True; self.raw = None
    def byid(self): return {c.id: c for c in self.chunks}
    def get(self, cid): return self.byid()[cid]
    def kinds(self, k): return [c for c in self.chunks if c.kind == k]

_UNPACKED = {}                                                         # (path, size, time written) -> the unpacked bytes of a compressed file read before
def _unpacked(path):
    """a build reads some of SEGA's tracks several times (Tropical4's 132 MB three times for its light: 0.4 s each to unpack). The unpacked
    bytes of a file are kept and handed out again while the file is the same one (size and time); every read_sbf still makes its own chunks
    from them. Files written in the last two minutes (a build reading back what it just wrote) are not kept. SR3_FASTGEO=0 or SR3_FASTLM=0: nothing is kept."""
    import os, time
    if os.environ.get('SR3_FASTGEO', '1') == '0' or os.environ.get('SR3_FASTLM', '1') == '0': return None, None
    try: st = os.stat(path); key = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    except OSError: return None, None
    return key, _UNPACKED.get(key)
def read_sbf(path_or_bytes):
    key, d = _unpacked(path_or_bytes) if isinstance(path_or_bytes, str) else (None, None)
    b = (open(path_or_bytes, 'rb').read() if isinstance(path_or_bytes, str) else path_or_bytes) if d is None else b'SBZ1'
    f = SbfFile(); f.compressed = b[:4] == b'SBZ1'
    if d is not None: pass
    elif f.compressed:
        n = struct.unpack_from('<I', b, 4)[0]; d = zlib.decompress(b[8:])
        if n != len(d): raise ValueError('SBZ1 size field %d != %d' % (n, len(d)))
        if key is not None:
            import time
            if time.time() - key[2] / 1e9 > 120.0:
                if sum(len(v) for v in _UNPACKED.values()) + len(d) > (1 << 30): _UNPACKED.clear()      # (never more than 1 GB kept)
                _UNPACKED[key] = d
    else: d = b
    f.raw = d
    h = struct.unpack_from('<6I', d, 0)
    if h[0] != 4: raise ValueError('not an SBF v4 (LE) file')
    f.hdr = h[:5]; n = h[5]; pos = None
    for i in range(n):
        cid, off = struct.unpack_from('<II', d, 24 + 8 * i)
        kind, id2, size, z, nfix = struct.unpack_from('<5I', d, off)
        if id2 != cid: raise ValueError('chunk id mismatch')
        p = off + 20
        fix = struct.unpack_from('<%dI' % nfix, d, p); p += 4 * nfix
        nref = struct.unpack_from('<I', d, p)[0]; p += 4
        ref = struct.unpack_from('<%dI' % nref, d, p); p += 4 * nref
        c = Ch(kind, cid, d[p:p + size], fix, ref, z)
        c.off = off
        if pos is None: f.first = off; c.gap = 0
        else:
            c.gap = off - pos
            if c.gap < 0: raise ValueError('chunks out of order')
        pos = p + size
        f.chunks.append(c)
    f.tail = len(d) - pos if pos is not None else len(d) - 24
    return f

def write_raw(chunks, first=None, tail=2048, hdr=(4, 0, 0, 0, 0), layout='auto', tex4k=True):
    """layout: 'keep' = reuse each chunk's recorded .gap / the given first offset (byte-identical rewrite of a read file);
               'auto' = compute padding from the alignment rules."""
    n = len(chunks)
    if layout == 'keep' and first is not None: pos = first
    else: pos = max(0x1000, (24 + 8 * n + 3) & ~3)
    body = bytearray(); table = []; start = pos
    for c in chunks:
        hl = 24 + 4 * len(c.fix) + 4 * len(c.ref); cur = start + len(body)
        if layout == 'keep' and c.gap is not None: pad = c.gap
        else:
            want = ALIGN16.get(c.kind)
            if c.kind == 4 and tex4k: pad = (0xF54 - (cur + hl)) % 4096
            elif want is None: pad = -cur % 4
            else: pad = (want - (cur + hl)) % 16
        body += b'\0' * pad
        table.append((c.id, start + len(body)))
        body += struct.pack('<5I', c.kind, c.id, len(c.data), c.z, len(c.fix)) + struct.pack('<%dI' % len(c.fix), *c.fix)
        body += struct.pack('<I', len(c.ref)) + struct.pack('<%dI' % len(c.ref), *c.ref) + c.data
    head = struct.pack('<6I', *(tuple(hdr) + (n,))) + b''.join(struct.pack('<II', *t) for t in table)
    if len(head) > start: raise ValueError('chunk table overruns first chunk')
    return head + b'\0' * (start - len(head)) + bytes(body) + b'\0' * tail

def write_sbf(f, compress=None, layout='auto', level=9, tex4k=True):
    if isinstance(f, SbfFile):
        raw = write_raw(f.chunks, f.first, f.tail, f.hdr, layout, tex4k); comp = f.compressed if compress is None else compress
    else:
        raw = write_raw(f, layout=layout, tex4k=tex4k); comp = True if compress is None else compress
    if not comp: return raw
    return b'SBZ1' + struct.pack('<I', len(raw)) + zlib.compress(raw, level)

# ---------------------------------------------------------------- validation
def validate(f, name='', extern_ids=None, quiet=False):
    """consistency checks on an SbfFile (or raw bytes / path). Returns list of problem strings."""
    if not isinstance(f, SbfFile): f = read_sbf(f)
    probs = []; ids = {}
    for c in f.chunks:
        if c.id in ids: probs.append('duplicate id %08x' % c.id)
        ids[c.id] = c
    ext = set(extern_ids or ())
    for c in f.chunks:
        n = len(c.data); tag = 'k%d %08x' % (c.kind, c.id)
        if c.off is not None:
            dataoff = c.off + 24 + 4 * len(c.fix) + 4 * len(c.ref)
            want = ALIGN16.get(c.kind)
            if want is not None and dataoff % 16 != want and not (c.kind == 7 and c.data[:2] == b'\x78\x9c'):
                probs.append('%s data at %x: alignment %d, want %d' % (tag, dataoff, dataoff % 16, want))
        fs = set()
        for o in c.fix:
            if o % 4 or o + 4 > n: probs.append('%s fixup offset %x out of range/unaligned' % (tag, o)); continue
            if o in fs: probs.append('%s duplicate fixup %x' % (tag, o))
            fs.add(o)
            v = c.u32(o)
            if v > n: probs.append('%s pointer at %x -> %x beyond data (%x)' % (tag, o, v, n))
        for o in c.ref:
            if o % 4 or o + 4 > n: probs.append('%s ref offset %x out of range' % (tag, o)); continue
            if o in fs: probs.append('%s offset %x is both fixup and ref' % (tag, o))
            v = c.u32(o)
            if v and v not in ids and v not in ext: probs.append('%s ref at %x -> id %08x not in file' % (tag, o, v))
    if not quiet:
        for p in probs[:40]: print('  PROBLEM', name, p)
    return probs
