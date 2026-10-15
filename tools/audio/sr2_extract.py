"""Decode all SR2 sample-ROM clips; write the co-driver/announcer clips with labels + index.csv,
and every other sample (effects) to audio/sr2_other_samples."""
import os, csv, re, pickle
import numpy as np
import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2_audio import *
A = S + "/audio/"
os.makedirs(A + "sr2_codriver", exist_ok=True); os.makedirs(A + "sr2_other_samples", exist_ok=True)
for dname in ("sr2_codriver", "sr2_other_samples"):
    for f in os.listdir(A + dname):
        if f.endswith(".wav"): os.remove(A + dname + "/" + f)

st = sample_table(); tt = tone_table(); rq = requests(); nm = name_map()

WORDS = {"EL": "easy left", "ER": "easy right", "ML": "medium left", "MR": "medium right", "HL": "hairpin left", "HR": "hairpin right",
         "KL": "K left", "KR": "K right", "L": "long", "VL": "very long", "VVL": "very very long", "M": "maybe", "O": "open",
         "OPEN": "opens", "TIGHTEN": "tightens", "D": "D", "CAUTION": "caution", "OVERCREST": "over crest", "OVERBUMP": "over bump",
         "S": "small", "T": "tight", "J": "jump", "C": "crest", "W": "water", "INGRAVEL": "in gravel", "INTARMAC": "in tarmac",
         "KEEPRIGHT": "keep right", "R": "right"}
def expand(name):
    n = name[3:]
    fixed = {"KEEP_R": "keep right", "KEEP_L": "keep left", "CAUTION_KEEP_R": "caution keep right", "CAUTION_KEEP_L": "caution keep left",
             "IN_GRAVEL": "in gravel", "IN_TARMAC": "in tarmac", "GRATE": "great", "HURRYUP": "hurry up", "WELLDONE": "well done",
             "WATCHOUT": "watch out", "OHNO": "oh no", "YOUARE": "you are", "TURN_AROUND": "turn around", "TITLE": "title call (Sega Rally 2?)",
             "FINISH2": "finish (2)", "T_KINK": "tight kink", "S_CREST": "small crest", "S_CREST_J": "small crest jump", "CREST_J": "crest jump",
             "L_CREST": "long crest", "S_BUMP": "small bump", "LEFT": "left", "RIGHT": "right", "FRONT": "front", "REAR": "rear"}
    if n in fixed: return fixed[n]
    if re.fullmatch(r"\d+", n): return n
    return " ".join(WORDS.get(t, t.lower()) for t in n.split("_"))

# voice index -> uses
uses = {}
seqs = {}
for (g, i), (notes, raw) in sorted(rq.items()):
    name = nm.get((g, i))
    if notes is None or name is None or not name.startswith("VO_"): continue
    vs = [((bank - 1) * 128 + key - 0x1B, d) for (pp, key, vel, bank, d) in notes]
    seqs[name] = vs
    for pos, (v, d) in enumerate(vs): uses.setdefault(v, []).append((name, pos, len(vs)))
print("VO requests:", len(seqs), "single-clip:", sum(1 for v in seqs.values() if len(v) == 1), "distinct voice clips used:", len(uses), "range", min(uses), max(uses))

OVERRIDE = {59: ("VO_CREST_JUMP", "crest jump", "medium", "second clip of VO_CAUTION_CREST_J and VO_CAUTION_C_J_W ('caution' + this [+ 'water']); a single clip, exact wording unverified"),
            86: ("VO_CAUTION", "caution", "high", "first clip of every VO_CAUTION_* request (30+ requests)"),
            81: ("VO_OVERCREST", "over crest", "medium", "last clip of all VO_*_OVERCREST requests"),
            82: ("VO_OPEN", "opens", "medium", "clip following the corner in all VO_*_OPEN* requests"),
            83: ("VO_OVERBUMP", "over bump", "medium", "last clip of all VO_*_OVERBUMP requests"),
            73: ("VO_TIGHTEN", "tightens", "medium", "last clip of all VO_*_TIGHTEN requests"),
            74: ("VO_D_TIGHTEN", "D tightens (meaning of D unknown)", "medium", "last clip of all VO_*_D_TIGHTEN requests")}
def label_for(v):
    if v in OVERRIDE: return OVERRIDE[v]
    u = uses.get(v, [])
    single = [n for n, pos, ln in u if ln == 1]
    if single:
        return single[0], expand(single[0]), "high", "sound-test name of a single-clip request (%s) in main ROM; request->tone->sample chain parsed" % single[0]
    # derive from compound names: common tokens
    if not u: return "UNUSED_%03d" % v, "unused voice slot", "low", "no request uses this tone entry"
    # position-aware derivation: remove tokens that belong to the other clip when that clip is single-labelled
    cands = []
    for n, pos, ln in u:
        other = [x for k, x in enumerate(seqs[n]) if k != pos]
        toks = n[3:]
        for (ov, _) in other:
            os_ = [m for m, p2, l2 in uses.get(ov, []) if l2 == 1]
            if os_:
                t = os_[0][3:]
                if pos == 0 and toks.endswith("_" + t): toks = toks[: -len(t) - 1]
                elif pos > 0 and toks.startswith(t + "_"): toks = toks[len(t) + 1:]
                elif ("_" + t + "_") in toks:
                    a, b = toks.split("_" + t + "_", 1); toks = a if pos == 0 else b
        cands.append(toks)
    from collections import Counter
    best, cnt = Counter(cands).most_common(1)[0]
    conf = "medium" if cnt == len(cands) else "low"
    return "VO_" + best, expand("VO_" + best), conf, "derived from multi-clip requests %s (residual tokens: %s)" % ("; ".join(n for n, _, _ in u[:4]), ",".join(sorted(set(cands))))

def active_ms(x, rate):
    e = np.abs(x.astype(float)); thr = max(e.max() * 0.04, 300)
    idx = np.nonzero(e > thr)[0]
    return (0, 0) if len(idx) == 0 else (idx[0] / rate * 1000, idx[-1] / rate * 1000)

def f0(x, rate):
    x = x.astype(float); n = len(x)
    seg = x[n // 4: n // 4 + 2048]
    if len(seg) < 1024: return 0
    seg = seg - seg.mean(); ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
    lo, hi = int(rate / 400), int(rate / 50)
    k = lo + int(np.argmax(ac[lo:hi]))
    return rate / k

rows = []
voice_samples = set()
vinfo = {}
for v in range(113):
    t = tt[155 + v]; s = st[t[0]]; rate = pitch_to_rate(t[1])
    code, text, conf, how = label_for(v)
    x = pcm16(s)
    a0, a1 = active_ms(x, rate)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:48]
    fn = "%03d_%s.wav" % (v, safe)
    write_wav(A + "sr2_codriver/" + fn, x, rate)
    voice_samples.add(t[0])
    used_in = [n for n, _, _ in uses.get(v, [])]
    rows.append([fn, v, code, text, conf, t[0], "0x%06X" % s["rom"], "mpr-20614.22" if s["rom"] < 0x400000 else "mpr-20615.24", "0x%06X" % (s["rom"] & 0x3FFFFF),
                 int(round(rate)), s["length"], "%.3f" % (s["length"] / rate), "%.0f-%.0f" % (a0, a1), "%.0f" % f0(x, rate), "0x%04X" % t[1], how, len(used_in), " ".join(used_in[:12])])
    vinfo[v] = dict(file=fn, code=code, text=text, conf=conf, rate=rate, length=s["length"], sample=t[0])
with open(A + "sr2_codriver/index.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["file", "voice_index", "label_code", "label_text", "confidence", "sample_no", "rom_offset(combined 8MB image)", "rom_file", "offset_in_rom_file", "rate_hz", "length_samples", "seconds", "active_ms", "f0_estimate_hz", "scsp_pitch_word", "how_identified", "n_requests_using", "requests_using"])
    w.writerows(rows)
pickle.dump((vinfo, seqs), open(O + "voice.pkl", "wb"))
# every request as a playlist (for compound calls)
with open(A + "sr2_requests.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["request_name", "expanded", "group", "number", "clips (voice_index:file @delay_ticks)"])
    for (g, i), (notes, raw) in sorted(rq.items()):
        name = nm.get((g, i))
        if name in seqs:
            w.writerow([name, expand(name), "0x%02X" % g, "0x%02X" % i, " + ".join("%d:%s%s" % (v, vinfo[v]["file"], "" if d is None else " @%d" % d) for v, d in seqs[name])])
# other samples
tone_of = {}
for k, t in enumerate(tt): tone_of.setdefault(t[0], t)
n_other = 0
for s in st:
    if s["idx"] in voice_samples: continue
    t = tone_of.get(s["idx"]); rate = pitch_to_rate(t[1]) if t else 11025
    write_wav(A + "sr2_other_samples/smp%03d_%06X%s.wav" % (s["idx"], s["rom"], "_loop" if s["loop"] else ""), pcm16(s), rate); n_other += 1
from collections import Counter
print("voice clips written:", len(rows), "confidence:", Counter(r[4] for r in rows), "other samples:", n_other)
print("rates:", Counter(r[9] for r in rows), "total voice seconds %.1f" % sum(float(r[11]) for r in rows))
f0s = np.array([float(r[13]) for r in rows]); print("f0 estimate median %.0f Hz (10-90%%: %.0f-%.0f)" % (np.median(f0s), np.percentile(f0s, 10), np.percentile(f0s, 90)))
for r in rows: print(r[1], r[2], "|", r[3], "|", r[4], "|", r[11], "s", "| act", r[12])
