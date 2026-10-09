"""SEGA Rally 3 (arcade) stream-bank rebuilder.  Never writes into the game folder: output goes to --out.

usage:
  python -I rebuild_bank.py --out DIR [--manifest changes.csv] [--audio GAME\\Rally\\Audio]
                            [--originals DIR ...] [--bank] [--verify-only]

Manifest (CSV with header; unused columns may be empty):
  action,stream,wav,loop,group,event,entry,space,template,tags,note
  replace  : stream = existing stream name or index; wav = 16-bit PCM WAV of any length (rate/channels are written
             to the info record; a warning is printed if they differ from the original).  loop = 0/1 or empty (keep).
  add      : stream = new name; wav; loop = 0/1; group = folder used in the stored paths (e.g. Environment\\Ambience).
  repoint  : (needs --bank) event = event name, entry = entry number (0-based), stream = target stream.
             Same-size edit of that entry's name + stream index in a COPY of ALL_AUDIO.sfx.
  setevent : (needs --bank) rewrite an existing event in place.  event = event to rewrite, template = event whose
             452-byte header is copied (id and name of 'event' are kept), stream = ';'-separated list of stream names
             (or '@EventName' for an event reference), tags = ';'-separated sub-slot tags (same count, 0 = none),
             space = ';'-separated names of ADJACENT events whose bytes may be absorbed (their table records are
             re-pointed at the rewritten event).  Fails if the new event does not fit.
Originals: every file '<stream>.bin' or 'announcer_<stream>.bin' (case-insensitive, exact slot size) found in an
--originals directory replaces that stream's samples BEFORE the manifest is applied (undo of in-place installs).

Formats (see report): header = [0x100]{tableA off, n, tableB off, n}; tableA rec {path[192], index, info offset};
tableB rec {path[192], index, data offset of the 192-byte path block}; info rec (224) {src path[192], channels,
rate, byte count, loop start byte, loop flag, 0, format(0=PCM), gain float}; data = 0x100 header, then per stream
path block[192] + PCM.  The game indexes both tables directly by stream index and seeks with a signed 32-bit offset.
"""
import os, sys, csv, struct, argparse, hashlib, shutil

GAME_AUDIO = r"F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally\Audio"
ALIGN = 64
MAX_DATA = 0x7FFFFFFF          # SetFilePointer is called with a signed 32-bit distance and no high part (0x581F00)

def cs(b): return b.split(b"\0")[0].decode("latin1")
def fix(s, n):
    b = s.encode("latin1")
    if len(b) >= n: raise ValueError("name too long: " + s)
    return b + b"\0" * (n - len(b))

def read_wav(path):
    d = open(path, "rb").read()
    if d[:4] != b"RIFF" or d[8:12] != b"WAVE": raise ValueError("not a WAV: " + path)
    p = 12; fmt = None; data = None
    while p + 8 <= len(d):
        cid = d[p:p + 4]; n = struct.unpack_from("<I", d, p + 4)[0]
        if cid == b"fmt ": fmt = struct.unpack_from("<HHIIHH", d, p + 8)
        elif cid == b"data": data = d[p + 8:p + 8 + n]; break
        p += 8 + n + (n & 1)
    if fmt is None or data is None: raise ValueError("bad WAV: " + path)
    tag, ch, rate, _, ba, bits = fmt
    if tag not in (1, 0xFFFE) or bits != 16: raise ValueError("WAV must be 16-bit PCM: " + path)
    data = data[:len(data) // (2 * ch) * 2 * ch]
    return ch, rate, data

class StreamBank:
    def __init__(self, hdr_path, data_path):
        self.h = open(hdr_path, "rb").read(); self.data_path = data_path
        self.ta, self.na, self.tb, self.nb = struct.unpack_from("<4I", self.h, 0x100)
        assert self.na == self.nb
        self.streams = []
        for i in range(self.na):
            a = self.ta + 200 * i; b = self.tb + 200 * i
            ia, info = struct.unpack_from("<II", self.h, a + 192); ib, off = struct.unpack_from("<II", self.h, b + 192)
            assert ia == i and ib == i, "tables are not in index order"
            w = struct.unpack_from("<7I", self.h, info + 192)
            self.streams.append(dict(index=i, path=self.h[a:a + 192], path_b=self.h[b:b + 192], src=self.h[info:info + 192],
                                     ch=w[0], rate=w[1], nbytes=w[2], loop_start=w[3], loop=w[4], w5=w[5], fmt=w[6],
                                     tail=self.h[info + 220:info + 224], off=off, new=None, block=None))
        self.info0 = min(struct.unpack_from("<I", self.h, self.ta + 200 * i + 196)[0] for i in range(self.na))
        self.byname = {}
        for s in self.streams: self.byname.setdefault(cs(s["path"]).split("\\")[-1].lower(), s)
        with open(data_path, "rb") as f: self.data_head = f.read(0x100)
    def find(self, key):
        key = key.strip()
        if key.isdigit() and key.lower() not in self.byname: return self.streams[int(key)]
        if key.lower() not in self.byname: raise KeyError("no stream named " + key)
        return self.byname[key.lower()]
    def original_samples(self, s):
        with open(self.data_path, "rb") as f:
            f.seek(s["off"] + 192); return f.read(s["nbytes"])
    def original_block(self, s):
        with open(self.data_path, "rb") as f:
            f.seek(s["off"]); return f.read(192)

    def write(self, out_hdr, out_data):
        n = len(self.streams)
        ta = 0x110; tb = ta + 200 * n; info0 = tb + 200 * n
        head = bytearray(self.h[:0x110]); struct.pack_into("<4I", head, 0x100, ta, n, tb, n)
        A = bytearray(); B = bytearray(); I = bytearray()
        pos = 0x100
        with open(out_data, "wb") as fo, open(self.data_path, "rb") as fi:
            fo.write(self.data_head)
            for i, s in enumerate(self.streams):
                if s["new"] is not None: block = s["block"] if s["block"] is not None else self.original_block(s); payload = s["new"]
                else:
                    fi.seek(s["off"]); block = fi.read(192); payload = None
                fo.write(block)
                if payload is None:
                    left = s["nbytes"]
                    while left:
                        chunk = fi.read(min(left, 1 << 22)); fo.write(chunk); left -= len(chunk)
                    nb = s["nbytes"]
                else:
                    fo.write(payload); nb = len(payload)
                A += s["path"] + struct.pack("<II", i, info0 + 224 * i)
                B += s["path_b"] + struct.pack("<II", i, pos)
                I += s["src"] + struct.pack("<7I", s["ch"], s["rate"], nb, s["loop_start"], s["loop"], s["w5"], s["fmt"]) + s["tail"]
                pos += 192 + nb
        if pos > MAX_DATA: raise ValueError("data file would exceed 2 GB (%d bytes)" % pos)
        open(out_hdr, "wb").write(bytes(head) + bytes(A) + bytes(B) + bytes(I))
        return pos

def pad_payload(data, ch, loop):
    frame = 2 * ch
    if loop: data = data[:len(data) // ALIGN * ALIGN]          # never pad a loop with silence
    elif len(data) % ALIGN: data = data + b"\0" * (ALIGN - len(data) % ALIGN)
    assert len(data) % frame == 0
    return data

# ---------------- ALL_AUDIO.sfx (same-size edits only) ----------------
class SfxBank:
    HEAD_BYTES = 0x400000        # all event tables/data live in the first 4 MB; samples follow
    def __init__(self, path):
        with open(path, "rb") as f: self.d = bytearray(f.read(self.HEAD_BYTES))
        self.t0, self.n0 = struct.unpack_from("<II", self.d, 0x100)
        self.rec = {}
        for i in range(self.n0):
            o = self.t0 + 200 * i; self.rec[cs(self.d[o:o + 192])] = o
        self.changes = []
    def ev_off(self, name): return struct.unpack_from("<I", self.d, self.rec[name] + 196)[0]
    def ev_id(self, name): return struct.unpack_from("<I", self.d, self.rec[name] + 192)[0]
    def ev_size(self, name):
        offs = sorted(set(struct.unpack_from("<I", self.d, o + 196)[0] for o in self.rec.values()))
        o = self.ev_off(name); k = offs.index(o)
        return (offs[k + 1] if k + 1 < len(offs) else struct.unpack_from("<I", self.d, struct.unpack_from("<I", self.d, 0x108)[0] + 196)[0]) - o
    def nentries(self, name): return struct.unpack_from("<I", self.d, self.ev_off(name) + 192 + 4 * 44)[0]
    def repoint(self, event, entry, sname, sindex):
        if entry >= self.nentries(event): raise ValueError("%s has no entry %d" % (event, entry))
        o = self.ev_off(event) + 452 + 260 * entry
        if struct.unpack_from("<I", self.d, o + 196)[0] != 1: raise ValueError("entry %d of %s is not a stream entry" % (entry, event))
        self.d[o:o + 192] = fix(sname, 192); struct.pack_into("<I", self.d, o + 192, sindex)
        self.changes.append("repoint %s[%d] -> %s (%d)" % (event, entry, sname, sindex))
    def setevent(self, event, template, entries, space):
        """entries = list of (name, word0, type, tag)"""
        start = self.ev_off(event); avail = self.ev_size(event); nxt = start + avail
        for sp in space:
            if self.ev_off(sp) != nxt: raise ValueError("%s is not adjacent to the space being built (expected offset 0x%X)" % (sp, nxt))
            sz = self.ev_size(sp); avail += sz; nxt += sz
        need = 452 + 260 * len(entries)
        if need > avail: raise ValueError("event %s needs %d bytes, only %d available" % (event, need, avail))
        t = self.ev_off(template)
        hdr = bytearray(self.d[t:t + 452])
        hdr[0:192] = fix(event, 192); struct.pack_into("<I", hdr, 192, self.ev_id(event)); struct.pack_into("<I", hdr, 192 + 4 * 44, len(entries))
        body = bytearray()
        for name, w0, typ, tag in entries:
            e = bytearray(260); e[0:192] = fix(name, 192)
            struct.pack_into("<I", e, 192, w0); struct.pack_into("<I", e, 196, typ); struct.pack_into("<f", e, 192 + 40, 1.0); struct.pack_into("<I", e, 192 + 64, tag)
            body += e
        self.d[start:start + avail] = bytes(hdr) + bytes(body) + b"\0" * (avail - need)
        for sp in space: struct.pack_into("<I", self.d, self.rec[sp] + 196, start)
        self.changes.append("setevent %s (id %d) @0x%X: %d entries, template %s, absorbed %s" % (event, self.ev_id(event), start, len(entries), template, ",".join(space) or "-"))
    def save(self, src, dst):
        shutil.copyfile(src, dst)
        with open(dst, "r+b") as f: f.write(self.d)

# ---------------- independent verifier ----------------
def verify(orig_hdr, orig_data, new_hdr, new_data, changed, restored, log=print):
    """Re-reads the output with separate code. changed = set of stream indices expected to differ, restored = {index: bytes}."""
    H = open(new_hdr, "rb").read(); OH = open(orig_hdr, "rb").read()
    ta, na, tb, nb = struct.unpack_from("<4I", H, 0x100); ota, ona, otb, onb = struct.unpack_from("<4I", OH, 0x100)
    errs = []
    if na != nb: errs.append("table counts differ")
    if H[:0x100] != OH[:0x100]: errs.append("header preamble changed")
    size = os.path.getsize(new_data)
    if size > MAX_DATA: errs.append("data file larger than 2 GB")
    expect = 0x100; same = 0; diff = 0
    with open(new_data, "rb") as fn, open(orig_data, "rb") as fo:
        if fn.read(0x100) != fo.read(0x100): errs.append("data preamble changed")
        for i in range(na):
            a = ta + 200 * i; b = tb + 200 * i
            ia, info = struct.unpack_from("<II", H, a + 192); ib, off = struct.unpack_from("<II", H, b + 192)
            if ia != i or ib != i: errs.append("stream %d: index fields %d/%d" % (i, ia, ib))
            if H[a:a + 192] != H[b:b + 192]: errs.append("stream %d: table A/B paths differ" % i)
            if info + 224 > len(H) or info < tb + 200 * na or (info - (tb + 200 * na)) % 224: errs.append("stream %d: bad info offset" % i); continue
            ch, rate, nbytes, lstart, loop, w5, fmt = struct.unpack_from("<7I", H, info + 192)
            if off != expect: errs.append("stream %d: data offset 0x%X, size chain says 0x%X" % (i, off, expect))
            if ch not in (1, 2) or rate not in (11025, 16000, 22050, 24000, 32000, 44100, 48000) or fmt != 0 or nbytes % (2 * ch): errs.append("stream %d: odd format ch=%d rate=%d fmt=%d bytes=%d" % (i, ch, rate, fmt, nbytes))
            if lstart >= max(nbytes, 1): errs.append("stream %d: loop start beyond end" % i)
            fn.seek(off); block = fn.read(192)
            if block != H[info:info + 192]: errs.append("stream %d: data path block != info source path" % i)
            if i < ona:
                oa = ota + 200 * i; oinfo = struct.unpack_from("<I", OH, oa + 196)[0]; ooff = struct.unpack_from("<I", OH, otb + 200 * i + 196)[0]
                och, orate, onbytes = struct.unpack_from("<3I", OH, oinfo + 192)
                if H[a:a + 192] != OH[oa:oa + 192]: errs.append("stream %d: name changed" % i)
                if i in changed: diff += 1
                else:
                    if (ch, rate, nbytes) != (och, orate, onbytes) or H[info:info + 224] != OH[oinfo:oinfo + 224]: errs.append("stream %d: info changed but stream is not in the manifest" % i);
                    else:
                        h1 = hashlib.md5(); h2 = hashlib.md5(); left = nbytes
                        fn.seek(off + 192)
                        if i in restored: h2.update(restored[i]); h1.update(fn.read(nbytes))
                        else:
                            fo.seek(ooff + 192)
                            while left:
                                k = min(left, 1 << 22); h1.update(fn.read(k)); h2.update(fo.read(k)); left -= k
                        if h1.digest() != h2.digest(): errs.append("stream %d: samples differ from the original" % i)
                        else: same += 1
            expect = off + 192 + nbytes
    if expect != size: errs.append("data file size 0x%X != end of size chain 0x%X" % (size, expect))
    if len(H) != 0x110 + na * (200 + 200 + 224): errs.append("header size inconsistent")
    log("verify: %d streams (%d original), %d bit-identical to original, %d changed as requested, %d new; data %d bytes; %s" % (
        na, ona, same, diff, na - ona, size, "OK" if not errs else "%d ERRORS" % len(errs)))
    for e in errs[:20]: log("   ERROR " + e)
    return not errs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--manifest"); ap.add_argument("--audio", default=GAME_AUDIO)
    ap.add_argument("--originals", action="append", default=[]); ap.add_argument("--bank", action="store_true")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    if os.path.abspath(a.audio).lower() in out.lower() or "sega rally 3\\game" in out.lower(): sys.exit("refusing to write into the game folder")
    os.makedirs(out, exist_ok=True)
    oh = os.path.join(a.audio, "EnglishStreamHeader.stm"); od = os.path.join(a.audio, "EnglishStreamData.stm")
    sb = StreamBank(oh, od)
    restored = {}
    for d in a.originals:
        for fn in os.listdir(d):
            if not fn.lower().endswith(".bin"): continue
            key = fn[:-4]
            for cand in (key, key[len("announcer_"):] if key.lower().startswith("announcer_") else None):
                if cand and cand.lower() in sb.byname:
                    s = sb.byname[cand.lower()]; p = os.path.join(d, fn)
                    if os.path.getsize(p) == s["nbytes"]:
                        s["new"] = open(p, "rb").read(); restored[s["index"]] = s["new"]
                    else: print("WARNING: backup %s has the wrong size for stream %s - ignored" % (fn, cand))
                    break
    print("originals restored from backups: %d streams" % len(restored))
    changed = set(); log = []
    bank = SfxBank(os.path.join(a.audio, "ALL_AUDIO.sfx")) if a.bank else None
    rows = list(csv.DictReader(open(a.manifest, newline="", encoding="utf-8"))) if a.manifest else []
    base = os.path.dirname(os.path.abspath(a.manifest)) if a.manifest else "."
    def wavpath(p): return p if os.path.isabs(p) else os.path.join(base, p)
    for r in rows:
        act = (r.get("action") or "").strip().lower()
        if not act or act.startswith("#"): continue
        if act == "replace":
            s = sb.find(r["stream"]); ch, rate, data = read_wav(wavpath(r["wav"]))
            if (ch, rate) != (s["ch"], s["rate"]): print("WARNING: %s was %d ch %d Hz, WAV is %d ch %d Hz" % (r["stream"], s["ch"], s["rate"], ch, rate))
            if (r.get("loop") or "").strip() != "": s["loop"] = int(r["loop"])
            old = s["nbytes"]; s["ch"], s["rate"] = ch, rate; s["new"] = pad_payload(data, ch, s["loop"]); s["loop_start"] = 0
            changed.add(s["index"]); restored.pop(s["index"], None)
            log.append("replace %d %s: %d -> %d bytes (%.3f s)" % (s["index"], r["stream"], old, len(s["new"]), len(s["new"]) / 2 / ch / rate))
        elif act == "add":
            name = r["stream"].strip()
            if name.lower() in sb.byname: raise ValueError("stream already exists: " + name)
            ch, rate, data = read_wav(wavpath(r["wav"])); loop = int(r.get("loop") or 0); grp = (r.get("group") or "Added").strip("\\")
            path = fix("M:\\Audio\\Sega Rally SAM\\__TempArcade\\Temp PC\\%s\\%s" % (grp, name), 192)
            src = fix("M:\\Audio\\Arcade Source\\%s\\%s.wav" % (grp, name), 192)
            s = dict(index=len(sb.streams), path=path, path_b=path, src=src, ch=ch, rate=rate, nbytes=0, loop_start=0, loop=loop, w5=0, fmt=0,
                     tail=struct.pack("<f", 1.0), off=None, new=pad_payload(data, ch, loop), block=src)
            sb.streams.append(s); sb.byname[name.lower()] = s
            log.append("add %d %s: %d bytes (%.3f s) %d ch %d Hz loop=%d" % (s["index"], name, len(s["new"]), len(s["new"]) / 2 / ch / rate, ch, rate, loop))
        elif act == "repoint":
            s = sb.find(r["stream"]); bank.repoint(r["event"].strip(), int(r["entry"]), cs(s["path"]).split("\\")[-1], s["index"])
        elif act == "setevent":
            ents = []; names = [x.strip() for x in r["stream"].split(";") if x.strip()]; tags = [int(x) for x in (r.get("tags") or "").split(";") if x.strip()] or [0] * len(names)
            if len(tags) != len(names): raise ValueError("setevent: tags and streams differ in count")
            for nm, tg in zip(names, tags):
                if nm.startswith("@"): ents.append((nm[1:] + " *", bank.ev_id(nm[1:]), 2, tg))
                else:
                    s = sb.find(nm); ents.append((cs(s["path"]).split("\\")[-1], s["index"], 1, tg))
            bank.setevent(r["event"].strip(), r["template"].strip(), ents, [x.strip() for x in (r.get("space") or "").split(";") if x.strip()])
        else: raise ValueError("unknown action: " + act)
    nh = os.path.join(out, "EnglishStreamHeader.stm"); nd = os.path.join(out, "EnglishStreamData.stm")
    size = sb.write(nh, nd)
    if bank:
        bank.save(os.path.join(a.audio, "ALL_AUDIO.sfx"), os.path.join(out, "ALL_AUDIO.sfx")); log += bank.changes
    ok = verify(oh, od, nh, nd, changed, restored)
    with open(os.path.join(out, "rebuild_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\nrestored from backups: %d\noutput data bytes: %d\nverify: %s\n" % (len(restored), size, "OK" if ok else "FAILED"))
    print("%d manifest actions applied; output in %s" % (len(log), out))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
