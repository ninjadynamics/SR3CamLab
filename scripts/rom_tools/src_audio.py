"""SEGA Rally Championship (1995, Model 2A, set `srallyc`): the sound board's data, read from your own ROM zip, and the
co-driver's calls as clips for SEGA Rally 3.

    python src_audio.py info                     what the sound program holds (requests, voice clips, tunes)
    python src_audio.py codriver [--out DIR]     writes one WAV per SEGA Rally 3 pace-note clip that has a 1995 call
                                                 (default: <repository>\\codriver\\src), plus mapping.csv
    python src_audio.py dump --out DIR           every voice clip as it is in the ROM (8-bit, its own rate), for listening
    options: --rom srallyc.zip   --audio <game>\\Rally\\Audio   --originals DIR (repeatable)

Nothing here is SEGA's data: the clips come out of the ROM set on your disk and stay in git-ignored folders.

What the files hold (worked out from the ROM; see docs/kb/audio.md, "SEGA Rally Championship"):
  epr-17890.30   sound program, 68000, bytes swapped in pairs, mapped at 0x600000 (reset: SSP 0x5000, PC 0x600100)
  mpr-17756.31, mpr-17757.32, mpr-17886.36, mpr-17887.37   samples, bytes swapped in pairs, mapped at 0x800000:
                 signed 8-bit mono PCM
  0x609C24       u16 (bytes - 1) then the sample table: 306 records of 20 bytes {start, length, loop start, loop length
                 (0 = one shot), SCSP envelope words (reg 0x08, reg 0x0A)}; addresses are 68000 addresses
  0x602F8E       u16 highest group, then a pointer per request group; a group = u16 (count - 1), pointers.
                 Group 0x10 = tunes, 0x20 = voice, 0x21 = effects. The main board asks with the 3 MIDI bytes AE gg nn.
  voice request  a small track of MIDI bytes: BA 7B 00 (all notes off), 9A kk vv (note on, channel 10) ... FF 2F
  0x606236       -> the tunes' channels at start-up, 0x6061D4 the voice and effect channels (9..14): records of 16 bytes
                 {flags, MIDI channel, program, ...}; flag bit 3 = the channel plays a key map: one sample per key at
                 a fixed pitch. Channel 10 (the voice) has program 0x40, whose key map is at 0x608FF4.
  0x60882E       u16, then a pointer per program; a key map = u16, then 8 bytes per key {sample (negative = none),
                 pitch, pan, effect send, priority, exclusive group}
  pitch word     routine 0x601332: high nibble = SCSP octave (signed), next nibble = semitone, low byte = 1/16
                 semitone steps looked up at 0x603D24. 0xF000 = octave -1 = 22050 Hz. (An earlier note read the word
                 as the SCSP register itself and got 11025 Hz.)
  tune           group 0x10: 4 bytes, then a list of section pointers; FFFFFFFF = stop, FFFFFFF1 + pointer = go on
                 at that list entry (loop). A section is a run of events with delays in ticks; the sequencer runs on
                 SCSP timer A, 50 samples per tick (882 ticks a second), so every length is exact.
Main program (epr-17888c.12 + epr-17889c.13, 16-bit halves of 32-bit words; RAM copy of its data at offset + 0x59F000):
  0x5C48C0 (RAM) 189 pointers to the sound-test names, 0x5C3CE0 the 3 request bytes of each; a pace note's voice id is
                 such a request number (docs/kb/18_src_1995_rom_data.md, section 6)
  0x5BB6E0 (RAM) race tune by course id (0 Desert, 1 Forest, 2 Mountain, 3 Lake Side), played right after "Go";
                 0x5BB700 the same for the other value of the mode flag 0x202230
"""
import os, sys, re, csv, struct, zipfile, argparse, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ROM_ZIP = r"F:\Emulators\SEGA Arcade\Model 2\Games\srallyc.zip"
SND_BASE = 0x600000; SMP_BASE = 0x800000; RAM_OFF = 0x59F000
SAMPLE_TABLE = 0x609C24; GROUP_TABLE = 0x602F8E; PROGRAM_TABLE = 0x60882E; CHANNEL_INIT = 0x606236; CHANNEL_FIXED = 0x6061D4; FNS_TABLE = 0x603D24
NAME_TABLE = 0x5C48C0; CODE_TABLE = 0x5C3CE0; N_REQUESTS = 189
TUNE_TABLE = 0x5BB6E0; TUNE_TABLE_2 = 0x5BB700
TICK_SAMPLES = 50; SCSP_RATE = 44100
COURSES = ["Desert", "Forest", "Mountain", "Lake Side"]


# ---------------------------------------------------------------- the ROM set
class SrcRom:
    def __init__(self, path=ROM_ZIP):
        if not os.path.exists(path): raise SystemExit("ROM set not found: %s  (give it with --rom)" % path)
        self.path = path
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            def get(prefix):
                c = [n for n in names if os.path.basename(n).lower().startswith(prefix)]
                if len(c) != 1: raise SystemExit("%s: expected one file starting with '%s', found %s" % (path, prefix, c))
                return z.read(c[0])
            swap = lambda b: np.frombuffer(b, np.uint8).reshape(-1, 2)[:, ::-1].tobytes()
            self.snd = swap(get("epr-17890."))
            self.smp = np.frombuffer(b"".join(swap(get(p)) for p in ("mpr-17756.", "mpr-17757.", "mpr-17886.", "mpr-17887.")), np.int8)
            lo = np.frombuffer(get("epr-17888c."), "<u2"); hi = np.frombuffer(get("epr-17889c."), "<u2")
            m = np.zeros(2 * len(lo), "<u2"); m[0::2] = lo; m[1::2] = hi
            self.main = m.tobytes()
        if struct.unpack_from(">II", self.snd, 0) != (0x5000, 0x600100): raise SystemExit("epr-17890 is not the sound program this tool knows")
    # sound program (big-endian, 68000 addresses)
    def w(self, a): return struct.unpack_from(">H", self.snd, a - SND_BASE)[0]
    def l(self, a): return struct.unpack_from(">I", self.snd, a - SND_BASE)[0]
    def b(self, a): return self.snd[a - SND_BASE]
    # main program data (little-endian, RAM addresses)
    def ml(self, ram): return struct.unpack_from("<I", self.main, ram - RAM_OFF)[0]

    def samples(self):
        n = (self.w(SAMPLE_TABLE) + 1) // 20; out = []
        for i in range(n):
            st, ln, ls, ll, env = struct.unpack_from(">5I", self.snd, SAMPLE_TABLE + 2 - SND_BASE + 20 * i)
            out.append(dict(index=i, start=st, length=ln, loop_start=ls, loop_length=ll, env=env, rom=st - SMP_BASE))
        return out
    def pcm(self, s): return self.smp[s["rom"]: s["rom"] + s["length"]].astype(np.float64) * 256.0

    def requests(self):
        """[{number, name, code (3 bytes)}] from the main program's sound-test tables"""
        out = []
        for i in range(N_REQUESTS):
            p = self.ml(NAME_TABLE + 4 * i) - RAM_OFF
            if not 0 <= p < len(self.main): raise SystemExit("the sound-test name table is not where this tool expects it")
            name = self.main[p:self.main.index(b"\0", p)].decode("latin1")
            out.append(dict(number=i, name=name, code=self.main[CODE_TABLE - RAM_OFF + 3 * i: CODE_TABLE - RAM_OFF + 3 * i + 3]))
        return out
    def group(self, g):
        """addresses of the tracks of a request group"""
        if g > self.w(GROUP_TABLE): return []
        t = self.l(GROUP_TABLE + 2 + 4 * g)
        return [self.l(t + 2 + 4 * i) for i in range(self.w(t) + 1)]

    def channel_program(self, channel):
        """start-up program of a MIDI channel and whether it plays a key map (flag bit 3)"""
        a = self.l(CHANNEL_INIT + 2)                                 # the tunes' channels: a byte (count - 1), then the records
        recs = [a + 1 + 16 * i for i in range(self.b(a) + 1)]
        recs += [CHANNEL_FIXED + 1 + 16 * i for i in range(self.b(CHANNEL_FIXED))]   # voice and effect channels: a byte (count), records
        for p in recs:
            r = self.snd[p - SND_BASE: p - SND_BASE + 16]
            if r[0] & 0x80 and r[1] == channel: return r[2] & 0x7F, bool(r[0] & 8)
        raise SystemExit("no start-up record for MIDI channel %d" % channel)
    def keymap(self, program, key):
        """the 8-byte key map record of a key-map program: (sample or None, pitch word, pan, send, priority, group)"""
        t = self.l(PROGRAM_TABLE + 2 + 4 * program); a = t + 2 + 8 * key
        smp, pitch, pan, send, prio, grp = struct.unpack_from(">HHBBBB", self.snd, a - SND_BASE)
        return (None if smp & 0x8000 else smp & 0x7FF), pitch, pan, send, prio, grp
    def pitch_rate(self, word):
        """what routine 0x601332 writes to the SCSP pitch register for a key-map pitch word, as a sample rate"""
        hi, lo = word >> 8, word & 0xFF
        if hi & 0xF == 0 and lo & 0x80: hi = (hi + 0xFC) & 0x1FF
        octv = (hi >> 4) & 0xF
        if octv & 8: octv -= 16
        fns = self.w(FNS_TABLE + 2 * ((((hi & 0xF) << 4) + lo) & 0xFF))
        return SCSP_RATE * (2.0 ** octv) * (1.0 + fns / 1024.0)

    def voice_clips(self):
        """{request name: dict(request, key, velocity, sample, rate, pcm)} for the voice requests (AE 20 nn)"""
        tracks = self.group(0x20); smp = self.samples(); prog, is_map = self.channel_program(10)
        if not is_map: raise SystemExit("MIDI channel 10 is not a key-map channel in this sound program")
        out = {}
        for r in self.requests():
            c = r["code"]
            if c[0] != 0xAE or c[1] != 0x20 or c[2] >= len(tracks): continue
            a = tracks[c[2]]; flags = self.b(a)
            if not flags & 0x80: continue
            ev = self.section(a + 1)[1]
            notes = [(d1, d2) for t, s, d1, d2 in ev if s == 0x9A and d2]
            if not notes: continue
            key, vel = notes[0]; si, pitch = self.keymap(prog, key)[:2]
            if si is None: continue
            out[r["name"]] = dict(request=r["number"], key=key, velocity=vel, sample=si, rate=self.pitch_rate(pitch), pitch=pitch, pcm=self.pcm(smp[si]),
                                  rom=smp[si]["rom"], length=smp[si]["length"], notes=len(notes))
        return out

    # ---- the sequencer's data (routine 0x602770) ----
    def section(self, addr):
        """(ticks, [(tick, status, data1, data2)], end address) of the run of events at addr"""
        d = self.snd; o = addr - SND_BASE; status = 0; ticks = 0; ev = []
        while True:
            if d[o] & 0x80: status = d[o]; o += 1
            hi = status & 0xF0; chain = False
            if hi == 0x80: v = d[o]; o += 1; chain = bool(v & 0x80); ev.append((ticks, status, v & 0x7F, 0x7F))
            elif hi in (0xC0, 0xD0): v = d[o]; o += 1; chain = bool(v & 0x80); ev.append((ticks, status, v & 0x7F, 0))
            elif hi == 0xF0:
                if status == 0xF7: o += 1 + d[o]
                elif status == 0xF0: o = d.index(b"\xf7", o) + 1
                elif status == 0xFF:
                    t = d[o]; o += 1
                    if t == 0x2F: return ticks, ev, o + SND_BASE
                    o += 1 + d[o]
                else: return ticks, ev, o + SND_BASE
            else: d1 = d[o]; v = d[o + 1]; o += 2; chain = bool(v & 0x80); ev.append((ticks, status, d1, v & 0x7F))
            if chain: continue                                       # bit 7 of the last data byte: the next event follows at once
            dl = d[o]; o += 1
            if dl & 0x80: dl = ((dl & 0x7F) << 7) | d[o]; o += 1
            ticks += dl
    def tune(self, number):
        """dict(sections=[addresses], ticks=[...], loop=index of the list entry the tune goes back to, or None)"""
        a = self.group(0x10)[number] + 4; lst = []; loop = None
        while True:
            v = self.l(a)
            if v == 0xFFFFFFFF: break
            if v == 0xFFFFFFF1: loop = (self.l(a + 4) - (self.group(0x10)[number] + 4)) // 4; break
            if v == 0xFFFFFFF2 or not SND_BASE <= v < SND_BASE + len(self.snd): break
            lst.append(v); a += 4
        return dict(sections=lst, ticks=[self.section(s)[0] for s in lst], loop=loop)
    def tunes(self):
        """the tunes with their sound-test names: [{number, name, request, intro_ticks, loop_ticks, ...}]"""
        out = []
        for r in self.requests():
            c = r["code"]
            if c[0] != 0xAE or c[1] != 0x10 or c[2] == 0: continue
            t = self.tune(c[2]); k = t["loop"]
            intro = sum(t["ticks"][:k]) if k is not None else sum(t["ticks"]); loop = sum(t["ticks"][k:]) if k is not None else 0
            out.append(dict(number=c[2], name=r["name"], request=r["number"], intro_ticks=intro, loop_ticks=loop, loops=k is not None, **t))
        return out
    def race_tunes(self):
        """{course: (request name in a championship, request name with the other mode flag)}"""
        names = [r["name"] for r in self.requests()]
        return {COURSES[c]: (names[self.ml(TUNE_TABLE + 4 * c)], names[self.ml(TUNE_TABLE_2 + 4 * c)]) for c in range(4)}


# ---------------------------------------------------------------- audio helpers (numpy only)
def resample_long(x, src, dst, edge=0.93):
    """Band-limited rate change of long audio (minutes) through one Fourier transform: the spectrum is kept up to
    `edge` of the narrower band and rolled off to nothing at its end (raised cosine), then read back at the new rate.
    x: float array (frames, channels). The result has round(len * dst / src) frames."""
    from math import gcd
    g = gcd(int(src), int(dst)); L = int(dst) // g; M = int(src) // g
    k = 1
    while M * k < len(x) + 4096: k *= 2                             # M * 2^k input samples <-> L * 2^k output samples, both quick to transform
    nin, nout = M * k, L * k; keep = min(nin, nout) // 2            # bins below the narrower band's end
    f = np.arange(keep + 1) / keep
    w = np.where(f <= edge, 1.0, 0.5 * (1 + np.cos(np.pi * np.clip((f - edge) / (1 - edge), 0, 1))))
    out = np.zeros((int(round(len(x) * L / M)), x.shape[1]))
    for ch in range(x.shape[1]):
        X = np.fft.rfft(x[:, ch], nin)[:keep + 1] * w
        out[:, ch] = np.fft.irfft(X, nout)[:len(out)] * (nout / nin)
    return out

def resample(x, src, dst, taps=64, att=80.0):
    """Band-limited rate change. Short clips: polyphase Kaiser-windowed sinc, `taps` per phase, stop band `att` dB;
    long audio goes to resample_long. x: float array, mono or (frames, channels); round(len * dst / src) frames come back."""
    from math import gcd
    x = np.asarray(x, np.float64)
    if src == dst: return x.copy()
    if len(x) * taps * dst / src > 8_000_000: return resample_long(x[:, None], src, dst)[:, 0] if x.ndim == 1 else resample_long(x, src, dst)
    g = gcd(int(src), int(dst)); L = int(dst) // g; M = int(src) // g
    beta = 0.1102 * (att - 8.7) if att > 50 else 0.5842 * (att - 21) ** 0.4 + 0.07886 * (att - 21)
    width = (att - 7.95) / (2.285 * 2 * np.pi * taps)                # transition width, in cycles per input sample
    fc = min(0.5, 0.5 * L / M) - width / 2                           # cut-off, cycles per input sample (centre of the transition)
    n = np.arange(taps * L) - (taps * L) // 2                        # centred on a whole sample: no delay in the result
    h = 2 * fc * np.sinc(2 * fc * n / L) * np.kaiser(taps * L + 1, beta)[:-1]   # prototype at L times the input rate
    mono = x.ndim == 1
    if mono: x = x[:, None]
    nout = int(round(len(x) * L / M)); pad = taps + 1
    xp = np.concatenate([np.zeros((pad, x.shape[1])), x, np.zeros((pad + M, x.shape[1]))])
    out = np.zeros((nout, x.shape[1])); c = (taps * L) // 2
    H = h.reshape(taps, L).T.copy(); H /= H.sum(axis=1, keepdims=True)      # H[phase, tap], every phase with gain 1
    q, r = np.divmod(np.arange(nout, dtype=np.int64) * M + c, L)
    idx = q[:, None] - np.arange(taps)[None, :] + pad
    for ch in range(x.shape[1]): out[:, ch] = np.einsum("ij,ij->i", xp[idx, ch], H[r])
    return out[:, 0] if mono else out

def loud_half_rms(x, rate, frame=0.05):
    """level of the louder half of the frames (50 ms for speech, 1 s for music: the measure the SEGA Rally 2 clips and
    tunes were matched with before); all channels of a frame count together"""
    x = np.asarray(x, np.float64)
    n = int(frame * rate); k = len(x) // n
    if k < 2: return float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    e = np.sort(np.sqrt(np.mean(x[:k * n].reshape(k, -1) ** 2, axis=1)))[k // 2:]
    return float(np.sqrt(np.mean(e ** 2)) + 1e-9)
def soft_limit(x): return 32000.0 * np.tanh(np.asarray(x, np.float64) / 32000.0)
def match_level(x, target, rate, frame=0.05, always_limit=True):
    """gain x to the target level. Speech goes through the soft ceiling as a whole (the gain is corrected for what the
    ceiling takes, 3 rounds); music only when its peaks would clip (always_limit=False)."""
    g = target / loud_half_rms(x, rate, frame)
    if not always_limit and np.abs(x).max() * g <= 32000.0: return x * g, g
    for _ in range(3):
        y = soft_limit(x * g); got = loud_half_rms(y, rate, frame)
        if abs(got / target - 1) < 0.02: break
        g *= target / got
    return y, g
def trim(x, rate, pad_ms=15.0, ramp_ms=4.0):
    """cut the silence before and after a clip (threshold 3 % of its peak), keep a short pad, ramp both ends"""
    e = np.abs(x); thr = max(e.max() * 0.03, 250.0); idx = np.nonzero(e > thr)[0]
    if len(idx) == 0: return x[:0]
    p = int(pad_ms * rate / 1000); a = max(0, idx[0] - p); b = min(len(x), idx[-1] + p)
    y = x[a:b].copy(); n = min(int(ramp_ms * rate / 1000), len(y) // 2)
    if n: r = np.linspace(0, 1, n); y[:n] *= r; y[-n:] *= r[::-1]
    return y
def write_wav(path, x, rate):
    x = np.asarray(x); ch = 1 if x.ndim == 1 else x.shape[1]
    with wave.open(path, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(int(rate)); w.writeframes(np.clip(np.round(x), -32768, 32767).astype("<i2").tobytes())
def safe_name(stream): return re.sub(r'[<>:"/\\|?*]', "_", stream)


# ---------------------------------------------------------------- SEGA Rally 3's clips <- the 1995 calls
SEV = {"easy": "Easy", "medium": "Mid", "ninety": "K", "hairpin": "Hairpin"}
TURN = r"(easy|medium|hairpin|ninety)(left|right)"
# calls that are not corners: SR3 clip (letters and digits only, lower case) -> (1995 requests, quality, note)
OTHER = {
    "caution": (["Caution"], "exact", ""), "overjump": (["OverJump"], "exact", ""), "turnaround": (["TurnAround"], "exact", ""),
    "stayleft": (["KeepLeft"], "close", "1995 says 'keep left'"), "stayright": (["KeepRight"], "close", "1995 says 'keep right'"),
    "bigjump": (["Jump"], "approximate", "1995 says 'jump'"), "hugejump": (["Jump"], "approximate", "1995 says 'jump'"), "jump": (["Jump"], "exact", ""),
    "countdownthree": (["Three"], "exact", ""), "countdowntwo": (["Two"], "exact", ""), "countdownone": (["One"], "exact", ""), "countdowngo": (["Go"], "exact", ""),
    "checkpoint": (["CheckPoint"], "exact", ""), "finish": (["Finish"], "exact", ""), "hurryup": (["HurryUp"], "exact", ""),
    "woah": (["Wow1"], "close", "1995 'wow'"),
    "segarallychampionship": (["SRC2"], "close", "one of the four 1995 title calls (SRC0..SRC3); which is the plain one is not known"),
}
for _h in ("dirt", "gravel", "ice", "mud", "sand", "snow", "water", "maybe"):
    OTHER["caution" + _h] = (["Caution"], "approximate", "1995 has only 'caution'")

def corner(have, sev, d, length, maybe):
    """the 1995 request for one corner call, the closest that exists: (name or None, [what was given up])"""
    base = SEV[sev] + d.capitalize(); notes = []
    if sev == "ninety": notes.append("K (the 1995 call between medium and hairpin) taken as SR3's 90 degrees: a guess")
    order = {"verylong": ["VeryLong", "Long", ""], "long": ["Long", ""], "": [""]}[length]
    for want_maybe in ([True, False] if maybe else [False]):
        for L in order:
            name = L + base + ("Maybe" if want_maybe else "")
            if name in have:
                if L != {"verylong": "VeryLong", "long": "Long", "": ""}[length]: notes.append("1995 has no '%s' form of this call" % {"verylong": "very long", "long": "long"}[length])
                if maybe and not want_maybe: notes.append("1995 has no 'maybe' form of this call")
                return name, notes
    return None, notes

def compose(have, key):
    """SR3 clip key -> ([1995 request names], quality, note) or None when the 1995 game has nothing for it"""
    m = re.fullmatch(r"(verylong|long)?(%s)(%s)?(maybe|opens|tightens)?" % (TURN, TURN), key)
    if m:
        length = m.group(1) or ""; s1, d1 = m.group(3), m.group(4); s2, d2 = m.group(6), m.group(7); suf = m.group(8) or ""
        notes = []; maybe = suf == "maybe"
        if s2:
            single = SEV[s1] + d1.capitalize() + SEV[s2] + d2.capitalize(); short = SEV[s1] + d1[0].upper() + SEV[s2] + d2[0].upper()
            one = single if single in have else (short if short in have else None)
            if one and not length and not maybe: clips = [one]                       # the 1995 game recorded this pair as one call
            else:
                a, n1 = corner(have, s1, d1, length, False); b, n2 = corner(have, s2, d2, "", maybe)
                if not a or not b: return None
                clips = [a, b]; notes += n1 + [x for x in n2 if x not in n1]
        else:
            a, n1 = corner(have, s1, d1, length, maybe)
            if not a: return None
            clips = [a]; notes += n1
        if suf in ("opens", "tightens"): notes.append("1995 has no '%s'" % suf)
        q = "exact" if not notes else ("close" if all("guess" in n for n in notes) else "approximate")
        return clips, q, "; ".join(notes)
    m = re.fullmatch(r"(verylong|long)?(.+?)(maybe)?", key)
    if key in OTHER: return OTHER[key]
    if m and m.group(2) in OTHER and (m.group(1) or m.group(3)):
        clips, q, note = OTHER[m.group(2)]
        extra = (["1995 has no '%s' form of this call" % {"verylong": "very long", "long": "long"}[m.group(1)]] if m.group(1) else []) + (["1995 has no 'maybe' form of this call"] if m.group(3) else [])
        return clips, "approximate", "; ".join([x for x in [note] + extra if x])
    return None

def is_call(key):
    """True for the clips a co-driver / race announcer says during a race (the ones worth listing when nothing matches)"""
    if re.fullmatch(r"(verylong|long)?(%s){1,2}(maybe|opens|tightens)?" % TURN, key): return True
    if re.fullmatch(r"(verylong|long)?(bridge|caution|jump|overjump|roadnarrows|stayleft|stayright|staytight|staywide|waterhazard|watersplash)(maybe)?", key): return True
    return key in ("water", "bigjump", "hugejump", "staycentral", "staystraight", "turnaround", "finish", "checkpoint", "hurryup", "laptwo", "finallap", "lap2", "lap3", "lap4",
                   "timeextended", "timeover") or key.startswith(("caution", "countdown"))

GAP_S = 0.06                                                          # pause between the two calls of a pair
def render(clips_pcm, slot_samples, target, out_rate=32000):
    """two or one 1995 clips -> samples for an SR3 slot. Returns (samples, natural seconds, gain, how it fits)"""
    parts = []
    for i, (x, rate) in enumerate(clips_pcm):
        y = resample(trim(x, rate), int(round(rate)), out_rate)
        if i: parts.append(np.zeros(int(GAP_S * out_rate)))
        parts.append(y)
    y = np.concatenate(parts); natural = len(y) / out_rate; fit = "fits"
    if len(y) > slot_samples:
        over = y[slot_samples:]; lost = float(np.sum(over ** 2) / (np.sum(y ** 2) + 1e-9))
        if lost > 0.02: return None, natural, 0.0, "too long for the clip it would replace (%.2f s in %.2f s)" % (natural, slot_samples / out_rate)
        y = y[:slot_samples].copy(); n = min(int(0.03 * out_rate), len(y)); y[-n:] *= np.linspace(1, 0, n); fit = "tail cut (quiet part only)"
    y, g = match_level(y, target, out_rate)
    return y, natural, g, fit

def default_originals(audio):
    """the folders where the settings app keeps the game's own samples of clips it has replaced"""
    o = os.path.join(os.path.dirname(audio), "Main_release", "tracks", "_SR3Extras", "original")
    return [d for d in (o, os.path.join(o, "codriver"), os.path.join(o, "sounds")) if os.path.isdir(d)]

class Sr3Clips:
    """SEGA Rally 3's stream bank, read only; the game's OWN samples of a stream even when another voice is installed"""
    def __init__(self, audio, originals=None):
        from rebuild_bank import StreamBank
        self.sb = StreamBank(os.path.join(audio, "EnglishStreamHeader.stm"), os.path.join(audio, "EnglishStreamData.stm"))
        self.backup = {}
        for d in (originals if originals else default_originals(audio)):
            for fn in os.listdir(d):
                if fn.lower().endswith(".bin"):
                    k = fn[:-4].lower(); k = k[10:] if k.startswith("announcer_") else k
                    self.backup.setdefault(k, []).append(os.path.join(d, fn))
    def name(self, s): return s["path"].split(b"\0")[0].decode("latin1").split("\\")[-1]
    def speech(self): return [s for s in self.sb.streams if b"\\Speech\\" in s["path"]]
    def music(self): return [s for s in self.sb.streams if b"\\Music" in s["path"]]
    def find(self, name): return self.sb.find(name)
    def original(self, s):
        p = [f for f in self.backup.get(self.name(s).lower(), []) if os.path.getsize(f) == s["nbytes"]]     # a name can be a clip and a tune
        raw = open(p[0], "rb").read() if p else self.sb.original_samples(s)
        return np.frombuffer(raw, "<i2").astype(np.float64).reshape(-1, s["ch"])

def build_codriver(rom, sr3, out_dir, log=print):
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.lower().endswith(".wav"): os.remove(os.path.join(out_dir, f))
    voice = rom.voice_clips(); have = set(voice); rows = []; n = {"exact": 0, "close": 0, "approximate": 0}; used = set()
    for s in sr3.speech():
        name = sr3.name(s); key = re.sub(r"[^a-z0-9]", "", name.lower()); slot = s["nbytes"] // 2
        c = compose(have, key)
        if c and not all(x in voice for x in c[0]): c = None
        if c is None:
            if is_call(key): rows.append([name, "%.3f" % (slot / 32000.0), "", "none", "", "", "", "keeps SEGA Rally 3's voice", ""])
            continue
        if s["ch"] != 1 or s["rate"] != 32000: continue
        clips, q, note = c
        target = loud_half_rms(sr3.original(s)[:, 0], 32000)
        y, natural, g, fit = render([(voice[x]["pcm"], voice[x]["rate"]) for x in clips], slot, target)
        if y is None:
            rows.append([name, "%.3f" % (slot / 32000.0), " + ".join(clips), "none", "%.3f" % natural, "", "", fit + "; keeps SEGA Rally 3's voice", note]); continue
        fn = safe_name(name) + ".wav"; write_wav(os.path.join(out_dir, fn), y, 32000)
        n[q] += 1; used.update(clips)
        rows.append([name, "%.3f" % (slot / 32000.0), " + ".join(clips), q, "%.3f" % natural, "%.2f" % g, fn, fit, note])
    with open(os.path.join(out_dir, "mapping.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["sr3_clip", "sr3_seconds", "src_1995_requests", "match", "src_seconds", "gain", "file", "fit", "note"]); w.writerows(rows)
    none = [r[0] for r in rows if r[3] == "none"]
    log("co-driver clips written to %s: %d (exact %d, close %d, approximate %d); race calls with no 1995 counterpart: %d"
        % (out_dir, sum(n.values()), n["exact"], n["close"], n["approximate"], len(none)))
    log("1995 voice requests used: %d of %d; not used: %s" % (len(used), len(voice), " ".join(sorted(have - used, key=lambda k: voice[k]["request"]))))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=["info", "codriver", "dump"])
    ap.add_argument("--rom", default=ROM_ZIP); ap.add_argument("--audio", default=None); ap.add_argument("--originals", action="append")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rom = SrcRom(a.rom)
    if a.what == "info":
        smp = rom.samples(); voice = rom.voice_clips(); prog, is_map = rom.channel_program(10)
        print("samples: %d   voice requests: %d (MIDI channel 10, program %d, key map at 0x%06X)" % (len(smp), len(voice), prog, rom.l(PROGRAM_TABLE + 2 + 4 * prog)))
        for k, v in sorted(voice.items(), key=lambda kv: kv[1]["request"]):
            print("  %3d %-24s key %2d vel %3d sample %3d rom 0x%06X  %6d samples  %5.0f Hz  %.2f s" % (v["request"], k, v["key"], v["velocity"], v["sample"], v["rom"], v["length"], v["rate"], v["length"] / v["rate"]))
        print("tunes (group 0x10), lengths in seconds = ticks x %d / %d:" % (TICK_SAMPLES, SCSP_RATE))
        for t in rom.tunes():
            print("  %2d %-20s %2d sections  %s  first part %7.3f s  loop %7.3f s" % (t["number"], t["name"], len(t["sections"]), "loops" if t["loops"] else "once ", t["intro_ticks"] * TICK_SAMPLES / SCSP_RATE, t["loop_ticks"] * TICK_SAMPLES / SCSP_RATE))
        print("race tunes by course (championship / other mode):", rom.race_tunes())
        return
    if a.what == "dump":
        if not a.out: raise SystemExit("dump needs --out DIR")
        os.makedirs(a.out, exist_ok=True)
        for k, v in rom.voice_clips().items(): write_wav(os.path.join(a.out, "%02d_%s.wav" % (v["request"], k)), v["pcm"], v["rate"])
        print("voice clips written to", a.out); return
    sys.path.insert(0, HERE)
    from rebuild_bank import GAME_AUDIO
    audio = a.audio or GAME_AUDIO
    build_codriver(rom, Sr3Clips(audio, a.originals), a.out or os.path.join(REPO, "codriver", "src"))

if __name__ == "__main__":
    main()
