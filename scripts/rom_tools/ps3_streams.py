"""PS3 SEGA Rally (Revo) stream bank reader + ATRAC3 extraction (read-only on the disc dump).
Header file: big-endian, same layout as the arcade one (0x100: first record offset, count; 200-byte records
{path[192], index, info offset}; info = {source path[192], channels, rate, byte count, 0, loop flag, 0, 2, float}).
Data file: from 0x100, per stream in index order: 192-byte path + payload.
Payload = headerless ATRAC3, 192-byte sound units, one unit per channel per 1024-sample frame (channels stored
as consecutive mono units inside each 192*channels block). Wrapped here into a RIFF/WAVE (tag 0x270) for ffmpeg."""
import struct, os, subprocess, sys
P = "D:/Roms/PS3/Sega Rally 3/PS3_GAME/USRDIR/audio/"

def cs(b): return b.split(b"\0")[0].decode("latin1")

def load():
    h = open(P + "englishstreamheader.stm", "rb").read()
    first, count = struct.unpack_from(">II", h, 0x100)
    recs = []
    for i in range(count):
        o = first + i * 200
        path = cs(h[o:o + 192]); idx, info = struct.unpack_from(">II", h, o + 192)
        w = struct.unpack_from(">8I", h, info + 192)
        recs.append(dict(idx=idx, path=path, name=path.split("\\")[-1], src=cs(h[info:info + 192]), ch=w[0], rate=w[1], nbytes=w[2], loop=w[4], words=w))
    recs.sort(key=lambda r: r["idx"])
    pos = 0x100
    for r in recs:
        r["off"] = pos + 192; pos += 192 + r["nbytes"]
    return recs

def payload(r):
    with open(P + "englishstreamdata.stm", "rb") as f:
        f.seek(r["off"]); return f.read(r["nbytes"])

def at3_wav(r, path):
    data = payload(r); ch = r["ch"]; ba = 192 * ch
    extra = struct.pack("<HIHHHH", 1, 0x400 * ch, 0, 0, 1, 0)   # coding mode 0 = independent channels
    fmt = struct.pack("<HHIIHHH", 0x270, ch, r["rate"], ba * r["rate"] // 1024, ba, 0, len(extra)) + extra
    nsamp = len(data) // ba * 1024
    fact = struct.pack("<II", nsamp, 1024)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"fact" + struct.pack("<I", len(fact)) + fact + b"data" + struct.pack("<I", len(data)) + data
    open(path, "wb").write(b"RIFF" + struct.pack("<I", len(body)) + body)

def decode(r, out_wav, tmpdir):
    t = os.path.join(tmpdir, "%03d.at3" % r["idx"])
    at3_wav(r, t)
    res = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", t, "-c:a", "pcm_s16le", out_wav], capture_output=True, text=True)
    os.remove(t)
    return res.returncode, res.stderr.strip()[:300]

if __name__ == "__main__":
    recs = load()
    from collections import Counter
    print(len(recs), Counter((r["ch"], r["rate"], r["loop"]) for r in recs))
