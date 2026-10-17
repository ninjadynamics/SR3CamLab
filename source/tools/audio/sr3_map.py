"""Map SEGA Rally 2 co-driver clips onto SEGA Rally 3 speech streams and render ready-to-install WAVs.
Reads the SR3 files read-only. Outputs audio/sr3_codriver.csv, audio/mapping.csv, audio/sr3_ready/*.wav"""
import os, sys, csv, re, pickle, subprocess, wave, shutil
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2_audio import S, O, sample_table, tone_table, pitch_to_rate, pcm16, write_wav
import sr3_streams
A = S + "/audio/"
READY = A + "sr3_ready/"; TMP = A + "_tmp/"
for d in (READY, TMP):
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d): os.remove(d + f)
vinfo, seqs = pickle.load(open(O + "voice.pkl", "rb"))
st = sample_table(); tt = tone_table()
CODE = {v["code"]: k for k, v in vinfo.items()}
def V(code): return CODE["VO_" + code]

# ---------- SR3 inventory ----------
h, recs = sr3_streams.load()
offs, _ = sr3_streams.data_offsets(recs)
speech = [r for r in sorted(recs, key=lambda r: r["idx"]) if "\\Speech\\" in r["path"]]
def key(name): return re.sub(r"[^a-z0-9]", "", name.lower())

TURN = r"(easy|medium|hairpin|ninety)(left|right)"
def classify(k):
    m = re.fullmatch(r"(verylong|long)?(.+?)(maybe|opens|tightens)?", k)
    if re.fullmatch(r"(verylong|long)?(%s){1,2}(maybe|opens|tightens)?" % TURN, k): return "pace note: corner"
    if re.fullmatch(r"(verylong|long)?(bridge|caution|jump|overjump|roadnarrows|stayleft|stayright|staytight|staywide|waterhazard|watersplash)(maybe)?", k): return "pace note: hazard/instruction"
    if k in ("water", "bigjump", "hugejump", "staycentral", "staystraight", "turnaround") or k.startswith("caution"): return "pace note: hazard/instruction"
    if k.startswith("countdown") or k in ("finish", "checkpoint", "laptwo", "finallap", "lap2", "lap3", "lap4", "timeextended", "timeover", "hurryup"): return "race flow"
    if k in ("woah", "awesomedriving", "greatdriving", "perfectrace", "welldone", "unlucky", "tryagain", "youdidgreat", "congratulations", "courserecord", "fastestlap", "raceleader", "youreinthelead", "youwin", "gameover", "gameoveryeah"): return "praise/result"
    if re.fullmatch(r"(youcame|youfinished)?(first|second|third|fourth|fifth|sixth|last)", k): return "position"
    return "menu/announcer/other"

# ---------- composition rules ----------
SEV = {"easy": "E", "medium": "M", "hairpin": "H", "ninety": "K"}
def turn_clip(sev, d, length, maybe):
    """returns (voice idx, [notes])"""
    D = "L" if d == "left" else "R"; notes = []
    base = SEV[sev] + D
    L = {"": "", "long": "L_", "verylong": "VL_"}[length]
    if sev in ("easy", "medium"):
        return V(L + base + ("_M" if maybe else "")), notes
    if sev == "ninety":
        notes.append("assumes SR2 'K' corner (VO_KL/KR) is the 90-degree call - wording unverified")
        if maybe: notes.append("no SR2 'maybe' version of this corner")
        return V(L + base), notes
    # hairpin
    if length: notes.append("SR2 has no '%s hairpin' - plain hairpin used" % length)
    if maybe: notes.append("no SR2 'hairpin maybe'")
    return V(base), notes

def compose(k):
    """returns (list of voice idx, quality, note) or None"""
    m = re.fullmatch(r"(verylong|long)?(%s)(%s)?(maybe|opens|tightens)?" % (TURN, TURN), k)
    if m:
        length = m.group(1) or ""; sev1, d1 = m.group(3), m.group(4); second = m.group(5); suf = m.group(8)
        notes = []; clips = []
        if second:
            sev2, d2 = m.group(6), m.group(7)
            c, n = turn_clip(sev1, d1, length, False); clips.append(c); notes += n
            c, n = turn_clip(sev2, d2, "", suf == "maybe"); clips.append(c); notes += n
        else:
            c, n = turn_clip(sev1, d1, length, suf == "maybe"); clips.append(c); notes += n
        if suf == "opens": clips.append(V("OPEN"))
        if suf == "tightens": clips.append(V("TIGHTEN"))
        q = "exact" if not notes else ("close" if all("assumes" in x for x in notes) else "approximate")
        return clips, q, "; ".join(notes)
    m = re.fullmatch(r"(verylong|long)?(bridge|caution|jump|overjump|roadnarrows|stayleft|stayright|staywide|waterhazard|watersplash)(maybe)?", k)
    if m:
        length, core, maybe = m.group(1), m.group(2), m.group(3)
        table = {"bridge": ([V("BRIDGE")], "exact", ""), "caution": ([V("CAUTION")], "exact", ""),
                 "jump": ([V("JUMP")], "exact", ""), "overjump": ([V("JUMP")], "close", "SR2 says 'jump' (no 'over jump')"),
                 "roadnarrows": ([V("NARROW")], "close", "SR2 says 'narrow'"), "stayleft": ([V("KEEP_L")], "close", "SR2 says 'keep left'"),
                 "stayright": ([V("KEEP_R")], "close", "SR2 says 'keep right'"), "staywide": ([V("WIDE")], "close", "SR2 says 'wide'"),
                 "waterhazard": ([V("WATER"), V("HAZARD")], "close", "built from 'water' + 'hazard'"),
                 "watersplash": ([V("WATER")], "approximate", "SR2 has only 'water'")}
        clips, q, note = table[core]
        extra = []
        if length: extra.append("no SR2 '%s' word for this call" % length)
        if maybe: extra.append("no standalone SR2 'maybe'")
        if extra: q = "approximate"; note = "; ".join([x for x in [note] + extra if x])
        return clips, q, note
    simple = {
        "water": ([V("WATER")], "exact", ""), "bigjump": ([V("CREST_JUMP")], "approximate", "SR2 'crest jump' clip (label medium confidence)"),
        "hugejump": ([V("CREST_JUMP")], "approximate", "SR2 'crest jump' clip (label medium confidence)"),
        "cautionwater": ([V("CAUTION"), V("WATER")], "exact", ""), "cautionice": ([V("CAUTION"), V("ICE")], "exact", ""),
        "cautiongravel": ([V("CAUTION"), V("IN_GRAVEL")], "close", "'caution' + 'in gravel'"),
        "cautiondirt": ([V("CAUTION"), V("SLIPPERY")], "approximate", "'caution slippery' substituted"),
        "cautionmud": ([V("CAUTION"), V("SLIPPERY")], "approximate", "'caution slippery' substituted"),
        "cautionsand": ([V("CAUTION"), V("SLIPPERY")], "approximate", "'caution slippery' substituted"),
        "cautionsnow": ([V("CAUTION"), V("SLIPPERY")], "approximate", "'caution slippery' substituted"),
        "cautionmaybe": ([V("CAUTION")], "approximate", "no standalone SR2 'maybe'"),
        "turnaround": ([V("TURN_AROUND")], "exact", ""), "countdownone": ([V("ONE")], "exact", ""), "countdowntwo": ([V("TWO")], "exact", ""),
        "countdownthree": ([V("THREE")], "exact", ""), "countdowngo": ([V("GO")], "exact", ""),
        "finish": ([V("FINISH2")], "exact", "VO_FINISH2 used (2.7 s); VO_FINISH is 4.3 s"), "checkpoint": ([V("CHECKPOINT")], "exact", ""),
        "congratulations": ([V("CONGRATULATIONS")], "exact", ""), "welldone": ([V("WELLDONE")], "exact", ""), "hurryup": ([V("HURRYUP")], "exact", ""),
        "woah": ([V("WOW1")], "close", "SR2 'wow'"), "perfectrace": ([V("PERFECT")], "close", "SR2 'perfect'"),
        "greatdriving": ([V("GRATE")], "approximate", "SR2 'great'"), "youdidgreat": ([V("GRATE")], "approximate", "SR2 'great'"),
        "awesomedriving": ([V("OUTSTANDING")], "approximate", "SR2 'outstanding'"), "unlucky": ([V("OHNO")], "approximate", "SR2 'oh no'"),
    }
    return simple.get(k)

# ---------- audio helpers ----------
def trimmed(v, pad_ms=20):
    t = tt[155 + v]; s = st[t[0]]; rate = pitch_to_rate(t[1])
    x = pcm16(s).astype(np.float64)
    e = np.abs(x); thr = max(e.max() * 0.03, 250)
    idx = np.nonzero(e > thr)[0]
    a = max(0, idx[0] - int(pad_ms * rate / 1000)); b = min(len(x), idx[-1] + int(pad_ms * rate / 1000))
    y = x[a:b].copy()
    n = int(0.005 * rate); ramp = np.linspace(0, 1, n)
    y[:n] *= ramp; y[-n:] *= ramp[::-1]
    return y, rate

def sr3_pcm(r):
    with open(sr3_streams.A + "EnglishStreamData.stm", "rb") as f:
        f.seek(offs[r["idx"]][0]); return np.frombuffer(f.read(r["nbytes"]), dtype="<i2").astype(np.float64)

def active_rms(x):
    e = np.abs(x)
    if e.max() <= 0: return 0.0
    sel = x[e > e.max() * 0.05]
    return float(np.sqrt(np.mean(sel ** 2))) if len(sel) else 0.0

def render(clips, slot_samples, target_rms, tag):
    parts = []
    for i, v in enumerate(clips):
        y, rate = trimmed(v)
        if i: parts.append(np.zeros(int(0.045 * rate)))
        parts.append(y)
    x = np.concatenate(parts)
    natural = len(x) / rate
    slot = slot_samples / 32000.0
    tempo = 1.0
    if natural > slot: tempo = min(natural / slot * 1.01, 1.6)
    src = TMP + tag + "_src.wav"; dst = TMP + tag + "_out.wav"
    write_wav(src, np.clip(x, -32768, 32767), rate)
    af = ("atempo=%.4f," % tempo if tempo > 1.0 else "") + "aresample=32000:resampler=soxr"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", af, "-ac", "1", "-c:a", "pcm_s16le", dst], capture_output=True, text=True)
    if r.returncode != 0:
        af = af.replace(":resampler=soxr", "")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", af, "-ac", "1", "-c:a", "pcm_s16le", dst], capture_output=True, text=True)
        if r.returncode != 0: raise RuntimeError(r.stderr)
    w = wave.open(dst); y = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64); w.close()
    truncated = 0.0
    if len(y) > slot_samples:
        truncated = (len(y) - slot_samples) / 32000.0
        y = y[:slot_samples].copy(); n = min(960, len(y)); y[-n:] *= np.linspace(1, 0, n)
    rms = active_rms(y)
    if rms > 0 and target_rms > 0:
        g = target_rms / rms
        g = min(g, 30000.0 / max(np.abs(y).max(), 1))
        y = y * g
    out = np.zeros(slot_samples); out[:len(y)] = y
    return out, natural, tempo, truncated

# ---------- run ----------
inv = []; maprows = []
stats = {"exact": 0, "close": 0, "approximate": 0, "none": 0}
for r in speech:
    name = r["path"].split("\\")[-1]; k = key(name)
    cat = classify(k)
    slot_samples = r["nbytes"] // 2
    inv.append([r["idx"], name, cat, r["rate"], r["ch"], r["nbytes"], "%.3f" % (slot_samples / r["rate"]), hex(offs[r["idx"]][0]), r["src"]])
    comp = compose(k)
    if comp is None:
        if cat.startswith("pace note") or cat in ("race flow", "praise/result"):
            maprows.append([name, cat, r["nbytes"], "%.3f" % (slot_samples / 32000), "", "", "none", "", "", "", "", "", "no SR2 equivalent"])
            stats["none"] += 1
        else:
            maprows.append([name, cat, r["nbytes"], "%.3f" % (slot_samples / 32000), "", "", "none", "", "", "", "", "", "not a co-driver call / no SR2 equivalent"])
        continue
    clips, q, note = comp
    orig = sr3_pcm(r)
    out, natural, tempo, trunc = render(clips, slot_samples, active_rms(orig), "%03d" % r["idx"])
    fn = re.sub(r'[<>:"/\\|?*]', "_", name) + ".wav"
    write_wav(READY + fn, np.clip(np.round(out), -32768, 32767), 32000)
    fit = "fits as-is" if tempo == 1.0 and trunc == 0 else ("fits with tempo x%.2f" % tempo if trunc == 0 else "tempo x%.2f + tail cut %.2f s" % (tempo, trunc))
    stats[q] += 1
    maprows.append([name, cat, r["nbytes"], "%.3f" % (slot_samples / 32000), " + ".join(vinfo[v]["file"] for v in clips), " + ".join(vinfo[v]["text"] for v in clips), q,
                    "%.3f" % natural, "yes" if natural <= slot_samples / 32000 else "no", "%.2f" % tempo, "%.2f" % trunc, fit, note, fn])
with open(A + "sr3_codriver.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["stream_index", "stream_name", "group", "rate_hz", "channels", "byte_size(max)", "seconds", "data_offset_in_EnglishStreamData", "source_path_in_header"]); w.writerows(inv)
with open(A + "mapping.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["sr3_stream", "sr3_group", "sr3_bytes", "sr3_seconds", "sr2_clips", "sr2_words", "match_quality", "sr2_natural_seconds(trimmed,concatenated)", "fits_without_change", "tempo_factor_applied", "tail_cut_seconds", "fit_result", "notes", "ready_file"]); w.writerows(maprows)
shutil.rmtree(TMP, ignore_errors=True)
from collections import Counter
print("SR3 speech streams:", len(speech), Counter(i[2] for i in inv))
print("mapped:", stats, "ready files:", len(os.listdir(READY)))
m = [x for x in maprows if x[6] != "none"]
print("fit:", Counter("as-is" if x[11] == "fits as-is" else ("tempo only" if x[11].startswith("fits with") else "tempo+cut") for x in m))
tp = np.array([float(x[9]) for x in m]); print("tempo factor: median %.2f, >1.3: %d, at cap 1.6: %d" % (np.median(tp), (tp > 1.3).sum(), (tp >= 1.6).sum()))
print("unmapped pace/race/praise:", [x[0] for x in maprows if x[6] == "none" and x[1] in ("pace note: corner", "pace note: hazard/instruction", "race flow", "praise/result")])
print("cut:", [(x[0], x[11]) for x in m if "cut" in x[11]])
