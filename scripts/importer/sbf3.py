"""SBF container reader (both byte orders). Chunk = kind, id, size, 0, nfix, fix[nfix], nref, ref[nref], data[size].
fix = offsets (in data) of pointers (values are offsets in data); ref = offsets of resource-id references."""
import zlib, struct, os
PS3 = r"D:\Roms\PS3\Sega Rally 3\PS3_GAME\USRDIR"; ARC = r"F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally"
def raw(path):
    b = open(path, 'rb').read()
    return zlib.decompress(b[8:]) if b[:4] == b'SBZ1' else b
class Chunk: pass
class Sbf:
    def __init__(self, path, be=None):
        self.path = path; self.d = d = raw(path)
        if be is None: be = d[:4] == b'\0\0\0\4'
        self.be = be; self.f = f = '>' if be else '<'
        self.hdr = struct.unpack(f + '6I', d[:24])
        self.chunks = []
        for i in range(self.hdr[5]):
            cid, off = struct.unpack(f + 'II', d[24+8*i:32+8*i])
            c = Chunk(); c.id = cid; c.off = off
            c.kind, c.id2, c.size, c.z, nfix = struct.unpack(f + '5I', d[off:off+20])
            p = off + 20
            c.fix = list(struct.unpack(f + '%dI' % nfix, d[p:p+4*nfix])); p += 4*nfix
            nref = struct.unpack(f + 'I', d[p:p+4])[0]; p += 4
            c.ref = list(struct.unpack(f + '%dI' % nref, d[p:p+4*nref])); p += 4*nref
            c.data = p; c.sbf = self
            self.chunks.append(c)
        self.byid = {c.id: c for c in self.chunks}
    def bytes(self, c): return self.d[c.data:c.data + c.size]
def hexd(b, off, n, f, base=0):
    for i in range(off, min(off+n, len(b)), 16):
        row = b[i:i+16]; k = len(row)//4
        w = struct.unpack(f + '%dI' % k, row[:4*k])
        print('  %06x  %s  %s' % (i - base, ' '.join('%08x' % x for x in w), ''.join(chr(c) if 32 <= c < 127 else '.' for c in row)))
