"""Reader for the SEGA Rally (Revo / 3) '.sfx' SoundBank container. Read-only.
Header: 0x100 bytes (name, version, platform 'PC'/'PS3', date, type string). At 0x100: 4 x {u32 offset, u32 count}:
  table0: events   200-byte records {char name[192]; u32 id; u32 offset_of_event_data}
  table1..3: 200-byte records {char path[196]; u32 offset}  (sample/wave descriptors)
Endianness: 'PC' little, PS3 big."""
import struct, sys

class Bank:
    def __init__(self, path, n=None):
        with open(path, "rb") as f:
            self.d = f.read() if n is None else f.read(n)
        self.platform = self.d[0xC4:0xC8].split(b"\0")[0].decode()
        self.e = "<" if struct.unpack_from("<I", self.d, 0xC0)[0] < 0x10000 else ">"
        self.tabs = [struct.unpack_from(self.e + "II", self.d, 0x100 + 8 * i) for i in range(4)]
    def u32(self, o): return struct.unpack_from(self.e + "I", self.d, o)[0]
    def cs(self, o, n): return self.d[o:o + n].split(b"\0")[0].decode("latin1")
    def events(self):
        off, cnt = self.tabs[0]
        out = []
        for i in range(cnt):
            o = off + 200 * i
            out.append((self.cs(o, 192), self.u32(o + 192), self.u32(o + 196)))
        return out
    def table(self, k):
        off, cnt = self.tabs[k]
        return [(self.cs(off + 200 * i, 196), self.u32(off + 200 * i + 196)) for i in range(cnt)]

if __name__ == "__main__":
    b = Bank(sys.argv[1], int(sys.argv[2], 0) if len(sys.argv) > 2 else None)
    print(b.platform, b.e, [(hex(o), c) for o, c in b.tabs], "size", len(b.d))
    ev = b.events()
    print(ev[:3], ev[-2:])
    for k in (1, 2, 3):
        t = b.table(k); print(k, t[:2], t[-1])

def parse_event(b, off):
    """event = 452-byte header {name[192], id, fields...} + n x 260-byte entries {name[192], id, type, fields...}"""
    import struct
    e = b.e
    name = b.cs(off, 192)
    hdr = struct.unpack_from(e + "65I", b.d, off + 192)
    n = hdr[44]            # entry count: header word 44 (offset +0x170)
    ents = []
    for k in range(n):
        o = off + 452 + 260 * k
        ents.append((b.cs(o, 192), struct.unpack_from(e + "17I", b.d, o + 192), o))
    return name, hdr, ents

def nz(words):
    import struct
    out = []
    for i, w in enumerate(words):
        if w == 0: continue
        f = struct.unpack("<f", struct.pack("<I", w))[0]
        out.append("%d:%s" % (i, ("%g" % f) if 1e-6 < abs(f) < 1e6 and w > 0x10000 else str(w)))
    return " ".join(out)
