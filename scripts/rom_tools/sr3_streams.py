"""Read-only inventory of SEGA Rally 3 English stream bank. Writes audio/sr3_streams_all.csv."""
import struct, csv, os, sys
A = r"F:/Jogos/SEGA Rally 3/GAME/Sega Rally 3/Rally/Audio/"
S = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic/audio/"

def cs(b): return b.split(b"\0")[0].decode("latin1")

def load():
    h = open(A + "EnglishStreamHeader.stm", "rb").read()
    first, count = struct.unpack_from("<II", h, 0x100)
    recs = []
    for i in range(count):
        o = first + i * 200
        path = cs(h[o:o + 192]); idx, info = struct.unpack_from("<II", h, o + 192)
        src = cs(h[info:info + 192]); ch, rate, nbytes = struct.unpack_from("<III", h, info + 192)
        extra = struct.unpack_from("<I", h, info + 204)
        recs.append(dict(path=path, idx=idx, info=info, src=src, ch=ch, rate=rate, nbytes=nbytes, extra=extra))
    return h, recs

def data_offsets(recs):
    """Walk data file: from 0x100, per stream in index order: 192-byte path then PCM."""
    out = {}
    pos = 0x100
    with open(A + "EnglishStreamData.stm", "rb") as f:
        for r in sorted(recs, key=lambda r: r["idx"]):
            f.seek(pos); p = cs(f.read(192))
            out[r["idx"]] = (pos + 192, p)
            pos += 192 + r["nbytes"]
    return out, pos

if __name__ == "__main__":
    h, recs = load()
    offs, end = data_offsets(recs)
    print("records", len(recs), "walk end", hex(end), "file size", hex(os.path.getsize(A + "EnglishStreamData.stm")))
    bad = sum(1 for r in recs if offs[r["idx"]][1] != r["path"])
    print("path mismatches in data walk:", bad)
    with open(S + "sr3_streams_all.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["idx", "path", "src", "channels", "rate", "bytes", "seconds", "data_offset"])
        for r in sorted(recs, key=lambda r: r["idx"]):
            w.writerow([r["idx"], r["path"], r["src"], r["ch"], r["rate"], r["nbytes"], "%.3f" % (r["nbytes"] / 2 / r["ch"] / r["rate"]), hex(offs[r["idx"]][0])])
    from collections import Counter
    print(Counter((r["ch"], r["rate"]) for r in recs))
    print(Counter(r["path"].replace("\\", "/").rsplit("/", 1)[0] for r in recs).most_common(40))
    for r in sorted(recs, key=lambda r: r["idx"])[:5]: print(r)
