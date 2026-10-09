"""Decode PS3 Arctic ambience / wind / music and build in-place replacements for the arcade stream bank.
Outputs under audio_arctic/: ps3_decoded/*.wav, ready/*.wav, music_options/*.wav, events_converted/*.bin, plan.csv"""
import os, sys, struct, subprocess, wave, csv, glob, shutil
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ps3_streams as ps3
import sr3_streams as arc
from sfx_bank import Bank
S = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic/audio_arctic/"
DEC = S + "ps3_decoded/"; READY = S + "ready/"; TMP = S + "_tmp/"; MUS = S + "music_options/"; EVC = S + "events_converted/"
for d in (DEC, READY, TMP, MUS, EVC): os.makedirs(d, exist_ok=True)

def rd(path):
    d = open(path, "rb").read(); p = 12; ch = rate = None; data = b""
    while p + 8 <= len(d):
        cid = d[p:p + 4]; n = struct.unpack_from("<I", d, p + 4)[0]
        if cid == b"fmt ": ch, rate = struct.unpack_from("<HI", d, p + 10)
        if cid == b"data": data = d[p + 8:p + 8 + n]; break
        p += 8 + n + (n & 1)
    x = np.frombuffer(data[:len(data) // (2 * ch) * 2 * ch], dtype="<i2").astype(np.float64).reshape(-1, ch)
    return x, rate
def wr(path, x, rate):
    x = np.asarray(x); ch = 1 if x.ndim == 1 else x.shape[1]
    with wave.open(path, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(rate); w.writeframes(np.clip(np.round(x), -32768, 32767).astype("<i2").tobytes())
def ff(args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr)

# ---------- 1. decode PS3 streams ----------
recs = ps3.load()
want = [r for r in recs if r["name"].startswith("Arctic") or r["name"] in ("arctic1_1", "arctic2_1", "GenericQuiet_L", "GenericQuiet_R")]
rows = []
for r in want:
    out = DEC + r["name"] + ".wav"
    rc, err = ps3.decode(r, out, TMP)
    x, rate = rd(out)
    rows.append([r["name"], r["idx"], r["ch"], r["rate"], r["nbytes"], r["loop"], "%.3f" % (len(x) / rate), "ok" if rc == 0 else err])
    print("decoded", rows[-1])
# wind samples from the PS3 per-track bank (same info/payload format as streams)
b = Bank(ps3.P + "id_track_arctic_2.sfx")
t1 = b.table(1); t3 = b.table(3)
for k, (p, o1) in enumerate(t1):
    n = p.split("\\")[-1]
    if "Wind" in n and "Arctic" in n:
        ch, rate, nbytes, _, loop = struct.unpack_from(">5I", b.d, o1 + 192)
        fake = dict(idx=900 + k, ch=ch, rate=rate, nbytes=nbytes)
        data = b.d[t3[k][1] + 192: t3[k][1] + 192 + nbytes]
        ps3.payload = lambda r, data=data: data
        rc, err = ps3.decode(fake, DEC + n + ".wav", TMP)
        x, rate = rd(DEC + n + ".wav")
        rows.append([n + " (bank sample, id_track_arctic_2.sfx)", k, ch, rate, nbytes, loop, "%.3f" % (len(x) / rate), "ok" if rc == 0 else err]); print("decoded", rows[-1])
with open(S + "ps3_decoded/index.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["name", "index", "channels", "rate", "atrac3_bytes", "loop_flag", "seconds", "decode"]); w.writerows(rows)

# ---------- 2. helpers for seamless loops ----------
def to24k(name):
    out = TMP + name + "_24k.wav"
    ff(["-i", DEC + name + ".wav", "-af", "aresample=24000", "-ac", "1", out])
    return rd(out)[0][:, 0]
def xcat(a, b, F):
    """overlap-add b after a with an equal-power cross-fade of F samples"""
    t = np.linspace(0, np.pi / 2, F)
    mid = a[-F:] * np.cos(t) + b[:F] * np.sin(t)
    return np.concatenate([a[:-F], mid, b[F:]])
def extend(src, n, F):
    out = src
    while len(out) < n: out = xcat(out, src, F)
    return out
def make_loop(src, T, F):
    """exactly T samples that loop seamlessly: the head is cross-faded with what follows the tail"""
    x = extend(src, T + F, F)
    t = np.linspace(0, np.pi / 2, F)
    out = x[:T].copy()
    out[:F] = x[T:T + F] * np.cos(t) + x[:F] * np.sin(t)
    return out
def loop_jump(x):
    """discontinuity at the loop point relative to typical sample-to-sample steps"""
    d = np.abs(np.diff(x)); return abs(x[0] - x[-1]) / (np.percentile(d, 99) + 1e-9)

# ---------- 3. arcade slots ----------
h, arecs = arc.load(); offs, _ = arc.data_offsets(arecs)
A = {r["path"].split("\\")[-1]: r for r in arecs}
def arcade_pcm(name):
    r = A[name]
    with open(arc.A + "EnglishStreamData.stm", "rb") as f:
        f.seek(offs[r["idx"]][0]); return np.frombuffer(f.read(r["nbytes"]), dtype="<i2").astype(np.float64)

plan = []
R = 24000
for side in ("L", "R"):
    low = to24k("ArcticLowWind_" + side); high = to24k("ArcticHighWind_" + side)
    lake = to24k("ArcticLake_" + side); port = to24k("ArcticPort_" + side)
    gq = arcade_pcm("GenericQuiet_" + side)      # same asset as the PS3 GenericQuiet; taken from the arcade bank (PCM, no ATRAC loss)
    jobs = [("TropicalSwampNight_" + side, gq, low, 0.9, "GenericQuiet_%s (arcade copy) + ArcticLowWind_%s x0.9" % (side, side), "slot 9 of 10 (index 8, tags %d)" % (78 if side == "L" else 88)),
            ("TropicalForestNight_" + side, lake, high, 0.9, "ArcticLake_%s + ArcticHighWind_%s x0.9" % (side, side), "slot 10 of 10 (index 9, tags %d)" % (79 if side == "L" else 89))]
    for target, base, wind, wg, desc, slot in jobs:
        r = A[target]; T = r["nbytes"] // 2
        F = 2 * R
        base_l = make_loop(base, T, F)
        wind_l = make_loop(wind, T, R // 4)
        mix = base_l + wg * wind_l
        peak = np.abs(mix).max(); g = 1.0
        if peak > 32000: g = 32000 / peak; mix *= g
        wr(READY + target + ".wav", mix, R)
        orig = arcade_pcm(target)
        plan.append([target, r["idx"], r["ch"], r["rate"], r["nbytes"], "%.3f" % (T / R), desc, "%.1f s base, %.1f s wind" % (len(base) / R, len(wind) / R),
                     "looped with 2 s equal-power cross-fade", "%.2f" % g, "%.0f" % np.sqrt(np.mean(mix ** 2)), "%.0f" % np.sqrt(np.mean(orig ** 2)), "%.2f" % loop_jump(mix), slot, "ready/" + target + ".wav"])
        print("ready", plan[-1])
with open(S + "plan.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["arcade_stream", "stream_index", "channels", "rate", "byte_size", "seconds", "new_content", "source_lengths", "loop_method", "gain_applied", "rms_new", "rms_of_stream_being_replaced", "loop_point_jump(1=typical step)", "ambience_slot_in_SFX_AMBIENT_TROPICAL", "file"])
    w.writerows(plan)

# ---------- 4. Events.bin conversion (PS3 big-endian -> arcade little-endian) ----------
def convert_events(src, remap=None):
    d = open(src, "rb").read()
    out = bytearray(b"".join(d[i:i + 4][::-1] for i in range(0, len(d), 4)))
    if remap:
        n = struct.unpack_from("<I", out, 0x1774)[0]
        for i in range(n):
            o = 0x1778 + 12 * i + 8
            v = struct.unpack_from("<I", out, o)[0]
            struct.pack_into("<I", out, o, remap[v])
    return bytes(out)
for f in sorted(glob.glob(ps3.P + "id_track_*_events.bin")):
    name = os.path.basename(f)[:-11].upper()
    open(EVC + name + "_Events.bin", "wb").write(convert_events(f))
# arctic2 on the Tropical donor: PS3 arctic slots -> tropical slots
REMAP = {0: 8, 1: 8, 2: 9, 3: 9, 4: 8, 5: 8, 6: 9, 7: 9}
open(READY + "arctic2_on_TROPICAL_donor_Events.bin", "wb").write(convert_events(ps3.P + "id_track_arctic_2_events.bin", REMAP))
print("events converted:", len(os.listdir(EVC)))

# ---------- 5. music ----------
for name in ("arctic1_1", "arctic2_1"):
    x, rate = rd(DEC + name + ".wav")
    rms = np.sqrt(np.mean(x ** 2, axis=0))
    cent = []
    for c in range(x.shape[1]):
        seg = x[rate * 30: rate * 40, c]; sp = np.abs(np.fft.rfft(seg)) ** 2; fr = np.fft.rfftfreq(len(seg), 1 / rate)
        cent.append(float((fr * sp).sum() / (sp.sum() + 1e-9)))
    print(name, "channels rms", np.round(rms), "spectral centroid", np.round(cent))
    corr = np.corrcoef(x[rate * 30: rate * 60].T); print("   inter-channel correlation\n", np.round(corr, 2))
shutil.rmtree(TMP, ignore_errors=True)
