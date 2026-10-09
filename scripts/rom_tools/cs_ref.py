"""Python reference for the C# port (csport/sr2audio.cs): same algorithm, numpy. Writes csport/pyref/{fit,natural}/*.wav
Differences from sr3_map_v2.py: resampling 22050 -> 32000 is the documented windowed-sinc (not ffmpeg) unless the clip
needs time compression; the loudness target is the ORIGINAL SR3 clip (backup .bin when present)."""
import os, sys, csv, re, subprocess, wave, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2_audio import S, sample_table, tone_table, pcm16
from rebuild_bank import StreamBank, GAME_AUDIO
OUT = S + "/csport/pyref/"; AUD = S + "/audio/"
ORIG = r"F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally\Main_release\tracks\_SR3Extras\original\codriver"
RATE = 22050
K = 24; L = 640; M = 441; FC = 0.94; BETA = 10.0

def i0(x):
    s = 1.0; t = 1.0
    for k in range(1, 60):
        t *= (x / 2.0) / k; s += t * t
    return s
def table():
    c = np.zeros((L, 2 * K))
    for ph in range(L):
        for j in range(-K + 1, K + 1):
            u = j - ph / float(L); a = abs(u) / K
            if a >= 1.0: v = 0.0
            else:
                w = i0(BETA * math.sqrt(1.0 - a * a)) / i0(BETA)
                z = math.pi * FC * u
                v = FC * (1.0 if abs(z) < 1e-12 else math.sin(z) / z) * w
            c[ph, j + K - 1] = v
        c[ph] /= c[ph].sum()
    return c
TAB = table()
def resample(x):
    n_out = (len(x) * L + M - 1) // M
    xp = np.concatenate([np.zeros(K), x, np.zeros(K + 2)])
    out = np.zeros(n_out)
    for n in range(n_out):
        pos = n * M; i = pos // L; ph = pos % L
        seg = xp[i + 1: i + 1 + 2 * K]          # x[i-K+1 .. i+K]
        acc = 0.0
        for j in range(2 * K): acc += seg[j] * TAB[ph, j]
        out[n] = acc
    return out

st = sample_table(); tt = tone_table()
def trimmed(v, pad_ms=20):
    t = tt[155 + v]; s = st[t[0]]; rate = RATE
    x = pcm16(s).astype(np.float64)
    e = np.abs(x); thr = max(e.max() * 0.03, 250)
    idx = np.nonzero(e > thr)[0]
    a = max(0, idx[0] - int(pad_ms * rate / 1000)); b = min(len(x), idx[-1] + int(pad_ms * rate / 1000))
    y = x[a:b].copy()
    n = int(0.005 * rate); ramp = np.linspace(0, 1, n)
    y[:n] *= ramp; y[-n:] *= ramp[::-1]
    return y
def loud_half(x):
    n = 1600; fr = sorted(float(np.sqrt(np.mean(x[i:i+n] ** 2))) for i in range(0, max(len(x) - n, 1), n))
    fr = [v for v in fr if v > 0]
    return float(np.mean(fr[len(fr) // 2:])) if fr else 0.0
def write_wav(path, data, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(np.asarray(data, dtype="<i2").tobytes())

sb = StreamBank(GAME_AUDIO + r"\EnglishStreamHeader.stm", GAME_AUDIO + r"\EnglishStreamData.stm")
backups = {f[:-4].lower(): os.path.join(ORIG, f) for f in os.listdir(ORIG) if f.lower().endswith(".bin")}
def original(name):
    s = sb.find(name); k = name.lower()
    raw = open(backups[k], "rb").read() if k in backups and os.path.getsize(backups[k]) == s["nbytes"] else sb.original_samples(s)
    return np.frombuffer(raw, dtype="<i2").astype(np.float64), s

def render(clips, slot_samples, target, fit, tag):
    parts = []
    for i, v in enumerate(clips):
        if i: parts.append(np.zeros(int(0.045 * RATE)))
        parts.append(trimmed(v))
    x = np.concatenate(parts)
    xi = np.asarray(np.clip(x, -32768, 32767), dtype="<i2").astype(np.float64)       # what a 16-bit file would hold (truncated)
    natural = len(x) / RATE; slot = slot_samples / 32000.0
    tempo = 1.0
    if fit and natural > slot: tempo = min(natural / slot * 1.01, 1.6)
    if tempo > 1.0:
        src = OUT + "_t_src.wav"; dst = OUT + "_t_out.wav"; write_wav(src, xi, RATE)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", "atempo=%.4f,aresample=32000" % tempo, "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)
        w = wave.open(dst); y = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64); w.close()
        os.remove(src); os.remove(dst)
    else:
        y = np.clip(np.round(resample(xi)), -32768, 32767)
    if fit and len(y) > slot_samples:
        y = y[:slot_samples].copy(); n = min(960, len(y)); y[-n:] *= np.linspace(1, 0, n)
    rms = loud_half(y)
    if rms > 0 and target > 0:
        for _ in range(3):
            z = 32000.0 * np.tanh(y * (target / rms) / 32000.0)
            got = loud_half(z)
            if got <= 0 or abs(got / target - 1) < 0.03: break
            rms *= got / target
        y = z
    if fit:
        out = np.zeros(slot_samples); out[:len(y)] = y
    else: out = y
    return np.clip(np.round(out), -32768, 32767), tempo

if __name__ == "__main__":
    for d in ("fit", "natural"): os.makedirs(OUT + d, exist_ok=True)
    rows = [r for r in csv.DictReader(open(AUD + "mapping.csv", encoding="utf-8")) if r["sr2_clips"]]
    tempos = []
    with open(OUT + "clips.csv", "w", newline="") as f:
        w = csv.writer(f)
        for r in rows:
            vs = [int(x.strip()[:3]) for x in r["sr2_clips"].split("+")]
            o, s = original(r["sr3_stream"]); tgt = loud_half(o)
            fn = re.sub(r'[<>:"/\\|?*]', "_", r["sr3_stream"]) + ".wav"
            y, tempo = render(vs, s["nbytes"] // 2, tgt, True, "x"); write_wav(OUT + "fit/" + fn, y, 32000)
            if tempo > 1: tempos.append((r["sr3_stream"], round(tempo, 4)))
            y, _ = render(vs, s["nbytes"] // 2, tgt, False, "x"); write_wav(OUT + "natural/" + fn, y, 32000)
            w.writerow([r["sr3_stream"], "+".join(str(v) for v in vs)])
    print("reference clips:", len(rows), "time-compressed with ffmpeg:", tempos)
