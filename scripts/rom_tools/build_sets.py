"""Build the WAVs + manifests for the three rebuilt-bank sets (bank_rebuild/src_*), then run rebuild_bank.py."""
import os, sys, csv, struct, subprocess, wave, pickle, re, shutil
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2_audio import S, O, sample_table, tone_table, pcm16
import ps3_streams as ps3
from rebuild_bank import StreamBank, read_wav, GAME_AUDIO, cs
BR = S + "/bank_rebuild/"; AUD = S + "/audio/"; ARC = S + "/audio_arctic/"
ORIG = r"F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally\Main_release\tracks\_SR3Extras\original"
ORIG_DIRS = [ORIG, ORIG + r"\codriver", ORIG + r"\sounds"]
VOICE_RATE = 22050            # user's in-game listen: 11025 Hz is an octave too low
TMP = BR + "_tmp/"; os.makedirs(TMP, exist_ok=True)

def wr(path, x, rate):
    x = np.asarray(x); ch = 1 if x.ndim == 1 else x.shape[1]
    with wave.open(path, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(rate); w.writeframes(np.clip(np.round(x), -32768, 32767).astype("<i2").tobytes())
def rd(path):
    ch, rate, data = read_wav(path); return np.frombuffer(data, dtype="<i2").astype(np.float64).reshape(-1, ch), rate
def ff(args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr)
def loud_half_rms(x, rate):
    n = int(0.05 * rate); k = len(x) // n
    if k < 2: return float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    e = np.sqrt(np.mean(x[:k * n].reshape(k, n) ** 2, axis=1)); e = np.sort(e)[k // 2:]
    return float(np.sqrt(np.mean(e ** 2)) + 1e-9)
def limit(x): return 32000.0 * np.tanh(x / 32000.0)

# ---------- originals ----------
sb = StreamBank(GAME_AUDIO + r"\EnglishStreamHeader.stm", GAME_AUDIO + r"\EnglishStreamData.stm")
backup = {}
for d in ORIG_DIRS:
    for fn in os.listdir(d):
        if fn.lower().endswith(".bin"):
            k = fn[:-4].lower(); k = k[10:] if k.startswith("announcer_") else k
            backup[k] = os.path.join(d, fn)
def original_pcm(name):
    s = sb.find(name); k = name.lower()
    raw = open(backup[k], "rb").read() if k in backup and os.path.getsize(backup[k]) == s["nbytes"] else sb.original_samples(s)
    return np.frombuffer(raw, dtype="<i2").astype(np.float64), s

# ---------- (a) co-driver at natural speed ----------
st = sample_table(); tt = tone_table()
def trimmed(v, pad_ms=15):
    t = tt[155 + v]; s = st[t[0]]; rate = VOICE_RATE
    x = pcm16(s).astype(np.float64); e = np.abs(x); thr = max(e.max() * 0.03, 250); idx = np.nonzero(e > thr)[0]
    a = max(0, idx[0] - int(pad_ms * rate / 1000)); b = min(len(x), idx[-1] + int(pad_ms * rate / 1000))
    y = x[a:b].copy(); n = int(0.004 * rate); ramp = np.linspace(0, 1, n); y[:n] *= ramp; y[-n:] *= ramp[::-1]
    return y
def render_codriver(dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    rows = []; nofit = []
    for r in csv.DictReader(open(AUD + "mapping.csv", encoding="utf-8")):
        if not r["sr2_clips"]: continue
        vs = [int(x.strip()[:3]) for x in r["sr2_clips"].split("+")]
        parts = []
        for i, v in enumerate(vs):
            if i: parts.append(np.zeros(int(0.03 * VOICE_RATE)))
            parts.append(trimmed(v))
        x = np.concatenate(parts)
        src = TMP + "c_src.wav"; dst = TMP + "c_out.wav"; wr(src, x, VOICE_RATE)
        ff(["-i", src, "-af", "aresample=32000", "-ac", "1", "-c:a", "pcm_s16le", dst])
        y = rd(dst)[0][:, 0]
        o, s = original_pcm(r["sr3_stream"])
        g = loud_half_rms(o, 32000) / loud_half_rms(y, 32000)
        y = limit(y * g)
        fn = re.sub(r'[<>:"/\\|?*]', "_", r["sr3_stream"]) + ".wav"
        wr(dst_dir + fn, y, 32000)
        slot = s["nbytes"] / 2 / 32000; nat = len(y) / 32000
        if nat > slot + 0.002: nofit.append((r["sr3_stream"], round(slot, 3), round(nat, 3)))
        rows.append(dict(action="replace", stream=r["sr3_stream"], wav=os.path.relpath(dst_dir + fn, BR), loop="", note="%s | SR3 slot %.3f s -> natural %.3f s | gain %.2f" % (r["sr2_words"], slot, nat, g)))
    return rows, nofit

FIELDS = ["action", "stream", "wav", "loop", "group", "event", "entry", "space", "template", "tags", "note"]
def write_manifest(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in FIELDS})

co_rows, nofit = render_codriver(BR + "src_codriver/")
write_manifest(BR + "manifest_codriver_natural.csv", co_rows)
print("co-driver clips rendered at %d Hz: %d ; longer than their SR3 slot: %d" % (VOICE_RATE, len(co_rows), len(nofit)))
print("   do not fit:", nofit)
with open(BR + "codriver_22050_fit.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["sr3_stream", "slot_seconds", "natural_seconds_at_22050"]); w.writerows(nofit)

# ---------- (c) minimal test ----------
o, s = original_pcm("Checkpoint!")
extra = int(len(o) * 0.5); t = np.arange(extra) / 32000.0
beeps = np.zeros(extra); seg = extra // 3
for k, fq in enumerate((880, 1320, 1760)):
    a = k * seg; n = int(seg * 0.7); env = np.minimum(1, np.minimum(np.arange(n), n - np.arange(n)) / 200.0)
    beeps[a:a + n] = 12000 * np.sin(2 * np.pi * fq * np.arange(n) / 32000.0) * env
os.makedirs(BR + "src_minimal/", exist_ok=True)
wr(BR + "src_minimal/Checkpoint!.wav", np.concatenate([o, beeps]), 32000)
write_manifest(BR + "manifest_minimal_test.csv", [dict(action="replace", stream="Checkpoint!", wav="src_minimal/Checkpoint!.wav", note="original 'Checkpoint!' (%.3f s) followed by three rising beeps; 50%% longer" % (len(o) / 32000))])

# ---------- (b) Arctic as new streams ----------
AD = BR + "src_arctic/"; os.makedirs(AD, exist_ok=True)
def to_rate(src, rate, extra=None):
    out = TMP + "r.wav"; ff(["-i", src, "-af", (extra + "," if extra else "") + "aresample=%d" % rate, "-c:a", "pcm_s16le", out]); return rd(out)[0]
def xcat(a, b, F):
    t = np.linspace(0, np.pi / 2, F); return np.concatenate([a[:-F], a[-F:] * np.cos(t) + b[:F] * np.sin(t), b[F:]])
def make_loop(src, T, F):
    x = src
    while len(x) < T + F: x = xcat(x, src, F)
    t = np.linspace(0, np.pi / 2, F); out = x[:T].copy(); out[:F] = x[T:T + F] * np.cos(t) + x[:F] * np.sin(t); return out
R = 24000; rows_b = []; mono = {}
names = ["ArcticFarm", "ArcticBathingLake", "ArcticLake", "ArcticPort", "ArcticFactory_Close", "ArcticFactory_Distant", "ArcticLowWind", "ArcticHighWind"]
for n in names:
    for side in ("L", "R"):
        x = to_rate(ARC + "ps3_decoded/%s_%s.wav" % (n, side), R)[:, 0]
        F = R if "Wind" not in n else R // 4
        y = make_loop(x, len(x) - F, F); y = y[:len(y) // 32 * 32]
        mono[n + "_" + side] = y; wr(AD + "%s_%s.wav" % (n, side), y, R)
        rows_b.append(dict(action="add", stream="%s_%s" % (n, side), wav="src_arctic/%s_%s.wav" % (n, side), loop="1", group="Environment\\Ambience", note="PS3 stream decoded, 24 kHz, loop cross-faded"))
gq = {side: original_pcm("GenericQuiet_" + side)[0] for side in ("L", "R")}
mixes = [("ArcticMix_QuietLowWind", lambda sd: gq[sd], "ArcticLowWind"), ("ArcticMix_LakeHighWind", lambda sd: mono["ArcticLake_" + sd], "ArcticHighWind"), ("ArcticMix_PortHighWind", lambda sd: mono["ArcticPort_" + sd], "ArcticHighWind")]
for mname, basef, wind in mixes:
    for side in ("L", "R"):
        base = basef(side); T = len(base) // 32 * 32
        w = make_loop(mono[wind + "_" + side], T, R // 4)
        y = limit(base[:T] + 0.9 * w)
        wr(AD + "%s_%s.wav" % (mname, side), y, R)
        rows_b.append(dict(action="add", stream="%s_%s" % (mname, side), wav="src_arctic/%s_%s.wav" % (mname, side), loop="1", group="Environment\\Ambience", note="stream + wind x0.9 pre-mixed (the PS3 event mixes these at run time)"))
# music: decode the two safari tunes too, stereo 32 kHz downmix (channel order L C R Ls Rs LFE assumed)
PAN = "pan=stereo|c0=0.60*c0+0.42*c1+0.42*c3+0.30*c5|c1=0.60*c2+0.42*c1+0.42*c4+0.30*c5"
recs = {r["name"]: r for r in ps3.load()}
for n in ("arctic1_1", "arctic2_1", "safari1_1", "safari2_1"):
    six = ARC + "ps3_decoded/%s.wav" % n
    if not os.path.exists(six): ps3.decode(recs[n], six, TMP)
    y = to_rate(six, 32000, PAN); y = y[:len(y) // 16 * 16]
    wr(AD + n + ".wav", y, 32000)
    rows_b.append(dict(action="add", stream=n, wav="src_arctic/%s.wav" % n, loop="1", group="Music 2\\Stereo", note="PS3 5.1 music, stereo 32 kHz downmix, %.1f s" % (len(y) / 32000)))
ev = [
 dict(action="setevent", event="SFX_AMBIENT_ID_TRACK_ALPINE_2", template="SFX_AMBIENT_ALPINE", space="SFX_AMBIENT_ID_TRACK_ALPINE_7;SFX_AMBIENT_ID_TRACK_ALPINE_6",
      stream="ArcticMix_QuietLowWind_L;ArcticMix_QuietLowWind_R;ArcticMix_LakeHighWind_L;ArcticMix_LakeHighWind_R;ArcticMix_PortHighWind_L;ArcticMix_PortHighWind_R", tags="70;80;71;81;72;82",
      note="becomes the Arctic environment event (3 zones) in the space of three unused Alpine alias events"),
 dict(action="setevent", event="SFX_AMBIENT_ID_TRACK_TROPICAL_7", template="SFX_AMBIENT_ID_TRACK_TROPICAL_7", stream="@SFX_AMBIENT_ID_TRACK_ALPINE_2", note="alias now references the Arctic environment event"),
 dict(action="setevent", event="SFX_AMBIENT_ID_TRACK_CANYON_2", template="MU_RACE_ID_TRACK_CANYON_1", stream="arctic2_1", note="plays the arctic2_1 tune (music header copied from MU_RACE_ID_TRACK_CANYON_1)"),
 dict(action="setevent", event="SFX_AMBIENT_ID_TRACK_CANYON_3", template="MU_RACE_ID_TRACK_CANYON_1", stream="arctic1_1", note="plays arctic1_1"),
 dict(action="setevent", event="SFX_AMBIENT_ID_TRACK_DESERT_3", template="MU_RACE_ID_TRACK_CANYON_1", stream="safari1_1", note="plays safari1_1"),
 dict(action="setevent", event="SFX_AMBIENT_ID_TRACK_DESERT_6", template="MU_RACE_ID_TRACK_CANYON_1", stream="safari2_1", note="plays safari2_1"),
]
write_manifest(BR + "manifest_arctic_full.csv", co_rows + rows_b + ev)
# Events file for arctic2 with the 3-zone Arctic event
d = open(ps3.P + "id_track_arctic_2_events.bin", "rb").read()
out = bytearray(b"".join(d[i:i + 4][::-1] for i in range(0, len(d), 4)))
REMAP = {0: 0, 1: 0, 2: 1, 3: 2, 4: 0, 5: 0, 6: 2, 7: 2}
n = struct.unpack_from("<I", out, 0x1774)[0]
for i in range(n):
    o_ = 0x1778 + 12 * i + 8; struct.pack_into("<I", out, o_, REMAP[struct.unpack_from("<I", out, o_)[0]])
os.makedirs(BR + "out/arctic_full", exist_ok=True)
open(BR + "out/arctic_full/ID_TRACK_TROPICAL_7_Events.bin", "wb").write(bytes(out))
shutil.rmtree(TMP, ignore_errors=True)

# ---------- run the rebuilder ----------
py = [sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "rebuild_bank.py")]
orig = sum((["--originals", d] for d in ORIG_DIRS), [])
for name, man, bank in (("minimal_test", "manifest_minimal_test.csv", False), ("codriver_natural", "manifest_codriver_natural.csv", False), ("arctic_full", "manifest_arctic_full.csv", True)):
    print("=====", name)
    r = subprocess.run(py + ["--out", BR + "out/" + name, "--manifest", BR + man] + orig + (["--bank"] if bank else []), capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-1500:])
