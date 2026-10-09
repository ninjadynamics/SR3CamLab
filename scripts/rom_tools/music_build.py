"""SEGA Rally 2 music: read the DSB2 program's tune table, cut/decode every tune with its loop, prepare SR3 replacements,
write manifests and build two rebuilt banks. Also decodes the PS3 Revo tunes (optional part). Scratch output only."""
import os, sys, csv, struct, subprocess, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rebuild_bank import StreamBank, read_wav, GAME_AUDIO
import ps3_streams as ps3
S = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic/"
M = S + "music/"; SND = S + "out/snd/"
ORIG = r"F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally\Main_release\tracks\_SR3Extras\original"
for d in ("sr2_music", "sr3_wav", "ps3_wav", "_tmp", "out"): os.makedirs(M + d, exist_ok=True)
TMP = M + "_tmp/"

def ff(args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr)
def rd(path):
    ch, rate, data = read_wav(path); return np.frombuffer(data, dtype="<i2").astype(np.float64).reshape(-1, ch), rate
def wr(path, x, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(rate); w.writeframes(np.clip(np.round(x), -32768, 32767).astype("<i2").tobytes())
def rms(x): return float(np.sqrt(np.mean(x ** 2)) + 1e-9)
def loud(x, rate):
    """level of the louder half of 1-second frames (music has quiet intros/outros)"""
    n = rate; k = len(x) // n
    if k < 2: return rms(x)
    e = np.sort(np.sqrt(np.mean(x[:k * n].reshape(k, -1) ** 2, axis=1)))[k // 2:]
    return float(np.mean(e))
def match(x, target, rate):
    g = target / loud(x, rate); y = x * g
    if np.abs(y).max() > 32000: y = 32000.0 * np.tanh(y / 32000.0)
    return y, g

# ---------- 1. the tune table in the DSB2 program (epr-20641.2, byte pairs swapped) ----------
prog = open(SND + "dsbprog.bin", "rb").read(); mpeg = open(SND + "mpeg.bin", "rb").read()
names, cmds = __import__("pickle").load(open(SND + "soundnames.pkl", "rb"))
bm = {c[2]: n for n, c in zip(names, cmds) if c[0] == 0xAE and c[1] == 0x10}
HUMAN = {"BM_ADV1": "attract / advertise 1", "BM_ADV2": "attract / advertise 2", "BM_MOUNTAIN": "Mountain course", "BM_FINISH": "finish / goal",
         "BM_SNOWY": "Snowy course", "BM_N_MOUNTAIN": "Mountain course, second version (N = night? unconfirmed)", "BM_RESERVE1": "reserve 1 (same data as N_MOUNTAIN, other loop/end)",
         "BM_ENDING": "ending", "BM_RESULT": "result screen", "BM_DESERT": "Desert course", "BM_SELECT": "select screens", "BM_IGNITION": "'ignition' (race tune length; Riviera course? unconfirmed)",
         "BM_GAMEOVER": "game over", "BM_RESERVE2": "reserve 2 (first part of ADV1)"}
count = struct.unpack_from(">H", prog, 0x8006)[0]
tunes = []
for k in range(1, count):
    p = struct.unpack_from(">I", prog, 0x8008 + 4 * (k - 1))[0]
    flags = struct.unpack_from(">H", prog, p)[0]; route = prog[p + 2:p + 6].hex()
    start, end = struct.unpack_from(">II", prog, p + 6); vol = prog[p + 16]
    loop = struct.unpack_from(">I", prog, p + 20)[0] if flags & 0x80 else None
    tunes.append(dict(code=k, name=bm.get(k, "?"), start=start, end=end, loop=loop, vol=vol, route=route))
rows = []
for t in tunes:
    assert (t["end"] - t["start"]) % 576 == 0 and mpeg[t["start"]:t["start"] + 3] == b"\xff\xfd\x88"
    if t["loop"] is not None: assert (t["loop"] - t["start"]) % 576 == 0
    fn = "%02d_%s.mp2" % (t["code"], t["name"])
    open(M + "sr2_music/" + fn, "wb").write(mpeg[t["start"]:t["end"]])
    dur = (t["end"] - t["start"]) / 576 * 1152 / 32000
    intro = (t["loop"] - t["start"]) / 576 * 1152 / 32000 if t["loop"] is not None else None
    t["dur"] = dur; t["intro"] = intro; t["file"] = fn
    rows.append([fn, "AE 10 %02X" % t["code"], t["name"], HUMAN.get(t["name"], ""), "0x%06X" % t["start"], "0x%06X" % t["end"], "" if t["loop"] is None else "0x%06X" % t["loop"],
                 "%.2f" % dur, "no" if t["loop"] is None else "yes", "" if intro is None else "%.2f" % intro, "" if intro is None else "%.2f" % (dur - intro), t["vol"], t["route"]])
with open(M + "sr2_music/index.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["file", "request_code", "bm_name", "human_name", "start_offset(16MB MPEG image)", "end_offset", "loop_start_offset", "seconds_start_to_end", "loops", "intro_seconds(played once)", "loop_length_seconds", "volume_byte", "routing_bytes"]); w.writerows(rows)
for r in rows: print(r[:11])

# ---------- 2. SR3 originals (loudness reference) ----------
sb = StreamBank(GAME_AUDIO + r"\EnglishStreamHeader.stm", GAME_AUDIO + r"\EnglishStreamData.stm")
def sr3_music(name):
    s = sb.find(name); return np.frombuffer(sb.original_samples(s), dtype="<i2").astype(np.float64).reshape(-1, 2), s
SR3 = {"MU_RACE_ID_TRACK_DESERT_1": "Hyper Conditioned Reflex_FullQualityVersion", "MU_RACE_ID_TRACK_ALPINE_1": "coastal1_1", "MU_RACE_ID_TRACK_CANYON_1": "alpine2_1",
       "MU_RACE_ID_TRACK_TROPICAL_1": "alpine1_1", "MU_RACE_ID_TRACK_LAKESIDE_1": "coastal2_1", "MU_MENU": "Menu 1", "MU_MENU_2": "Menu 2", "MU_GameOverYeah": "GameOverYeah"}
ref = {}
for ev, st in SR3.items():
    x, s = sr3_music(st); ref[st] = (loud(x, 32000), len(x) / 32000.0, s["loop"])
    print("SR3 %-28s %-45s %.1f s loop=%d loud-half level %.0f peak %.0f" % (ev, st, len(x) / 32000.0, s["loop"], ref[st][0], np.abs(x).max()))

# ---------- 3. decode SR2 tunes; build loop-correct files ----------
def decode(t):
    """returns (whole pass start..end, loop region taken from a second pass so the seam has the decoder's real state)"""
    src = TMP + "t.mp2"; dst = TMP + "t.wav"
    body = mpeg[t["start"]:t["end"]]; second = mpeg[t["loop"]:t["end"]] if t["loop"] is not None else b""
    open(src, "wb").write(body + second)
    ff(["-f", "mp3", "-i", src, "-c:a", "pcm_s16le", dst])
    x, rate = rd(dst); assert rate == 32000 and x.shape[1] == 2
    n1 = len(body) // 576 * 1152
    return x[:n1], (x[n1:n1 + len(second) // 576 * 1152] if second else None)
PROPOSAL = [  # (SR3 event, SR3 stream, SR2 tune, fit, comment)
 ("MU_RACE_ID_TRACK_DESERT_1", "BM_DESERT", "natural", "SR2 Desert tune for the Classic / Desert stage"),
 ("MU_RACE_ID_TRACK_ALPINE_1", "BM_SNOWY", "natural", "snow course tune for the Alpine stage"),
 ("MU_RACE_ID_TRACK_CANYON_1", "BM_MOUNTAIN", "natural", "mountain course tune for the Canyon stage"),
 ("MU_RACE_ID_TRACK_TROPICAL_1", "BM_IGNITION", "no natural fit", "SR2 has no tropical course; the remaining race-length tune"),
 ("MU_RACE_ID_TRACK_LAKESIDE_1", "BM_N_MOUNTAIN", "no natural fit", "second mountain tune; SR2 has no lakeside course"),
 ("MU_MENU", "BM_SELECT", "natural", "select-screen tune for the menus"),
 ("MU_MENU_2", "BM_ADV1", "weak", "attract tune for the second menu tune"),
 ("MU_GameOverYeah", "BM_GAMEOVER", "natural", "game over jingle (no loop in either game)"),
]
byname = {t["name"]: t for t in tunes}
prep = []; made = {}
for t in tunes:
    if t["name"] in ("BM_RESERVE1", "BM_RESERVE2"): continue
    whole, loopseg = decode(t)
    if t["loop"] is None: variants = {"": (whole, 0, "plays once, as in SR2")}
    elif t["intro"] < 0.1: variants = {"": (loopseg, 1, "whole tune loops (SR2 loop point is 1 frame after the start); nothing lost")}
    else: variants = {"": (loopseg, 1, "loop part only: starts at SR2's loop point and repeats seamlessly; the %.1f s intro is NOT in this file" % t["intro"]),
                      "_with_intro": (np.concatenate([whole[:int(round(t["intro"] * 32000))], loopseg]), 1, "intro + loop part; in SR3 every repeat replays the intro (SR3 always restarts at 0)")}
    for suf, (x, lp, note) in variants.items():
        fn = t["name"] + suf + ".wav"
        made[t["name"] + suf] = (x, lp, note, fn)
used = {p[1]: p for p in PROPOSAL}
for key, (x, lp, note, fn) in made.items():
    base = key.replace("_with_intro", "")
    target_stream = SR3[used[base][0]] if base in used else "Hyper Conditioned Reflex_FullQualityVersion"
    y, g = match(x, ref[target_stream][0], 32000)
    y = y[:len(y) // 16 * 16]
    wr(M + "sr3_wav/" + fn, y, 32000)
    prep.append([fn, base, "%.2f" % (len(y) / 32000.0), lp, note, target_stream, "%.2f" % g, "%.0f" % loud(y, 32000), "%.0f" % np.abs(y).max()])
with open(M + "sr3_wav/index.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["file", "sr2_tune", "seconds", "loop_flag", "what_the_file_holds", "level_matched_to_sr3_stream", "gain", "loud_half_level", "peak"]); w.writerows(prep)
with open(M + "sr3_mapping_proposal.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["sr3_event", "sr3_stream", "sr3_seconds", "sr2_tune", "sr2_file", "sr2_seconds", "fit", "comment"])
    for ev, tune, fit, c in PROPOSAL:
        st = SR3[ev]; w.writerow([ev, st, "%.1f" % ref[st][1], tune, "sr3_wav/%s.wav" % tune, [p[2] for p in prep if p[0] == tune + ".wav"][0], fit, c])
FIELDS = ["action", "stream", "wav", "loop", "group", "event", "entry", "space", "template", "tags", "note"]
def manifest(path, items):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
        for ev, tune, fit, c in items:
            w.writerow(dict(action="replace", stream=SR3[ev], wav="sr3_wav/%s.wav" % tune, loop=str(made[tune][1]), note="%s <- %s (%s)" % (ev, tune, c)))
manifest(M + "manifest_sr2_music_classic_only.csv", PROPOSAL[:1]); manifest(M + "manifest_sr2_music_full.csv", PROPOSAL)

# ---------- 4. PS3 Revo tunes (stereo 32 kHz, level-matched to SR3 race music, loop flag as on the disc) ----------
PAN = "pan=stereo|c0=0.60*c0+0.42*c1+0.42*c3+0.30*c5|c1=0.60*c2+0.42*c1+0.42*c4+0.30*c5"
race_level = float(np.mean([ref[SR3[e]][0] for e in SR3 if "RACE" in e]))
recs = {r["name"]: r for r in ps3.load()}; prow = []
for n in ("arctic1_1", "arctic2_1", "safari1_1", "safari2_1", "canyon1_1", "canyon2_1", "lakeside1_1", "tropical1_1", "tropical2_1", "Championship", "Victory"):
    six = TMP + "six.wav"; st = TMP + "st.wav"
    rc, err = ps3.decode(recs[n], six, TMP)
    ff(["-i", six, "-af", PAN + ",aresample=32000", "-c:a", "pcm_s16le", st])
    x, _ = rd(st); y, g = match(x, race_level, 32000); y = y[:len(y) // 16 * 16]
    wr(M + "ps3_wav/" + n + ".wav", y, 32000)
    prow.append([n + ".wav", "%.2f" % (len(y) / 32000.0), recs[n]["loop"], "%.2f" % g, "%.0f" % loud(y, 32000), "%.0f" % np.abs(y).max()]); print("ps3", prow[-1])
with open(M + "ps3_wav/index.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["file", "seconds", "loop_flag_on_disc", "gain", "loud_half_level", "peak"]); w.writerows(prow)
import shutil; shutil.rmtree(TMP, ignore_errors=True)

# ---------- 5. rebuilt banks ----------
py = [sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "rebuild_bank.py")]
orig = sum((["--originals", d] for d in (ORIG, ORIG + r"\codriver", ORIG + r"\sounds")), [])
for name in ("sr2_music_classic_only", "sr2_music_full"):
    r = subprocess.run(py + ["--out", M + "out/" + name, "--manifest", M + "manifest_%s.csv" % name] + orig, capture_output=True, text=True)
    print("=====", name); print(r.stdout[-700:], r.stderr[-700:])
