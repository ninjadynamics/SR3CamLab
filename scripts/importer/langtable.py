"""SEGA Rally 3 text table: system\\system_data.sbf (and cze_ / jpn_ / pol_ / rus_system_data.sbf), the kind 7 chunk
that starts with the language count (7b65debd in system_data.sbf; raw bytes, no fixups / refs).

    t = LangTable.parse(chunk.data); t.get("LANG_ID_BOWLER") -> {"LANG_ENGLISH": "Bowler Nemesis", ...}
    t.add("LANG_ID_HORNET", "Hornet"); chunk.data = t.build()
    python langtable.py list [regex] [file]     python langtable.py roundtrip [file ...]

Layout (little-endian; a "length" is a byte count that includes the terminator):
  u32 nLang, nLang x u32 length, language names (UTF-16, LANG_ENGLISH ...)
  u32 nIds,  nIds  x u32 length, id names (ASCII, LANG_ID_BOWLER ...)
  nIds x u32  lookup2(id name + its NUL byte) (Bob Jenkins, start value 0; the game's string ids)
  u32 26 (meaning UNKNOWN, kept), nIds x u32 = the longest text of that id over the languages, in bytes, + 2
  per language: u32 nIds, nIds x u32 length, the texts in id order (UTF-16)
VERIFIED: the five system files rebuild byte for byte (roundtrip); every hash and every maximum checks.
"""
import os, sys, struct, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbfw

SYSTEM = r"F:/Jogos/SEGA Rally 3/GAME/Sega Rally 3/Rally/system/"
GAME_SYSTEM = SYSTEM + "system_data.sbf"


def lookup2(key, initval=0):
    """Bob Jenkins' lookup2 (exe 0x5470D0, start value 0). The text ids hash the name WITH its NUL byte."""
    if isinstance(key, str): key = key.encode("latin1")
    M = 0xFFFFFFFF
    def mix(a, b, c):
        a = (a - b - c) & M; a ^= c >> 13
        b = (b - c - a) & M; b ^= (a << 8) & M
        c = (c - a - b) & M; c ^= b >> 13
        a = (a - b - c) & M; a ^= c >> 12
        b = (b - c - a) & M; b ^= (a << 16) & M
        c = (c - a - b) & M; c ^= b >> 5
        a = (a - b - c) & M; a ^= c >> 3
        b = (b - c - a) & M; b ^= (a << 10) & M
        c = (c - a - b) & M; c ^= b >> 15
        return a, b, c
    a = b = 0x9E3779B9; c = initval; n = len(key); k = 0
    while n - k >= 12:
        a = (a + struct.unpack_from("<I", key, k)[0]) & M
        b = (b + struct.unpack_from("<I", key, k + 4)[0]) & M
        c = (c + struct.unpack_from("<I", key, k + 8)[0]) & M
        a, b, c = mix(a, b, c); k += 12
    c = (c + n) & M
    t = key[k:]
    for i in range(len(t)):
        if i < 4: a = (a + (t[i] << (8 * i))) & M
        elif i < 8: b = (b + (t[i] << (8 * (i - 4)))) & M
        else: c = (c + (t[i] << (8 * (i - 7)))) & M
    return mix(a, b, c)[2]


def text_hash(name): return lookup2(name.encode("latin1") + b"\0")


def _strings(d, o):
    n = struct.unpack_from("<I", d, o)[0]; o += 4
    lens = struct.unpack_from("<%dI" % n, d, o); o += 4 * n
    out = []
    for L in lens: out.append(d[o:o + L]); o += L
    return out, o


def _blk(items):
    return struct.pack("<I", len(items)) + struct.pack("<%dI" % len(items), *[len(x) for x in items]) + b"".join(items)


class LangTable:
    def __init__(self, langs, ids, texts, unk=26):
        self.langs = langs; self.ids = ids; self.texts = texts; self.unk = unk

    @classmethod
    def parse(cls, d):
        raw, o = _strings(d, 0)
        langs = [s.decode("utf-16-le")[:-1] for s in raw]
        raw, o = _strings(d, o)
        ids = [s[:-1].decode("latin1") for s in raw]
        n = len(ids)
        hashes = struct.unpack_from("<%dI" % n, d, o); o += 4 * n
        assert all(h == text_hash(i) for h, i in zip(hashes, ids)), "hash table is not lookup2(name + NUL)"
        unk = struct.unpack_from("<I", d, o)[0]; o += 4
        maxl = struct.unpack_from("<%dI" % n, d, o); o += 4 * n
        texts = {}
        for L in langs:
            raw, o = _strings(d, o)
            assert len(raw) == n
            texts[L] = [s.decode("utf-16-le")[:-1] for s in raw]
        assert o == len(d), "bytes after the last language"
        t = cls(langs, ids, texts, unk)
        assert list(maxl) == t.maxlens(), "maximum table differs from the texts"
        return t

    def maxlens(self):
        return [max(2 * len(self.texts[L][i]) + 2 for L in self.langs) + 2 for i in range(len(self.ids))]

    def build(self):
        out = _blk([(s + "\0").encode("utf-16-le") for s in self.langs])
        out += _blk([(s + "\0").encode("latin1") for s in self.ids])
        out += struct.pack("<%dI" % len(self.ids), *[text_hash(i) for i in self.ids])
        out += struct.pack("<I", self.unk) + struct.pack("<%dI" % len(self.ids), *self.maxlens())
        for L in self.langs:
            out += _blk([(s + "\0").encode("utf-16-le") for s in self.texts[L]])
        return out

    def get(self, key):
        i = self.ids.index(key)
        return {L: self.texts[L][i] for L in self.langs}

    def add(self, key, text):
        """text: str (every language) or {language: str} (missing languages get the first language's text)"""
        assert key not in self.ids, key
        h = text_hash(key)
        assert all(text_hash(i) != h for i in self.ids), "hash collision"
        self.ids.append(key)
        for L in self.langs:
            self.texts[L].append(text if isinstance(text, str) else text.get(L, text[self.langs[0]] if self.langs[0] in text else list(text.values())[0]))


def find_chunk(f):
    """the text-table chunk of a system file: kind 7 whose data parses as a LangTable"""
    for i, c in enumerate(f.chunks):
        if c.kind == 7 and len(c.data) > 8 and struct.unpack_from("<I", c.data, 0)[0] < 16:
            try: LangTable.parse(c.data); return i
            except Exception: pass
    return None


if __name__ == "__main__":
    if sys.argv[1] == "roundtrip":
        paths = sys.argv[2:] or [SYSTEM + n for n in ("system_data.sbf", "cze_system_data.sbf", "jpn_system_data.sbf",
                                                     "pol_system_data.sbf", "rus_system_data.sbf")]
        for p in paths:
            f = sbfw.read_sbf(p); i = find_chunk(f)
            if i is None: print("%-22s no text table" % os.path.basename(p)); continue
            c = f.chunks[i]; t = LangTable.parse(c.data)
            same = t.build() == c.data
            raw = sbfw.write_raw(f.chunks, f.first, f.tail, f.hdr, layout="keep")
            print("%-22s chunk %08x languages %s ids %d: chunk identical %s, file (unpacked) identical %s" % (
                os.path.basename(p), c.id, ",".join(x.replace("LANG_", "") for x in t.langs), len(t.ids), same, raw == f.raw))
    elif sys.argv[1] == "list":
        p = sys.argv[3] if len(sys.argv) > 3 else GAME_SYSTEM
        f = sbfw.read_sbf(p); t = LangTable.parse(f.chunks[find_chunk(f)].data)
        pat = re.compile(sys.argv[2] if len(sys.argv) > 2 else ".")
        for i, k in enumerate(t.ids):
            if pat.search(k): print("%3d %-28s %s" % (i, k, " | ".join(t.texts[L][i] for L in t.langs)))
