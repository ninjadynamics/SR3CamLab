"""SEGA Rally Championship (1995): its race tunes, played by the game's own sound board in an emulator and recorded, one
file per course, for the 1995 courses imported into SEGA Rally 3's Classic mode.

The 1995 tunes are not recordings. The sound program (68000) plays them note by note on the SCSP sound chip, from
sequences and instrument samples in ROM, through an effect program on the chip's DSP. Nothing in the ROM can be cut
out as audio (unlike SEGA Rally 2's MPEG music), so the faithful way to get them is to run the sound board in an
emulator and record what it plays. This tool drives MAME for that, with no window and no sound output:

    python src_music.py plan       what would be recorded (reads the ROM only)
    python src_music.py record     runs MAME: about 18 emulated minutes, a few minutes of one CPU thread at idle priority
    python src_music.py build      cuts, converts (stereo 32000 Hz) and levels the recording
                                   -> <repository>\\music\\src\\desert.wav, forest.wav, mountain.wav, lakeside.wav,
                                      tunes.json (where each one's loop starts) and mapping.csv
    python src_music.py all        record, then build
    options: --rom srallyc.zip   --mame mame.exe   --work DIR (default <repository>\\music\\src\\raw)
             --audio <game>\\Rally\\Audio   --out DIR (default <repository>\\music\\src)
             --after-boot  (record only) let the game start the sound board first; try it when `build` reports silence

Then pick "SEGA Rally Championship (1995)" as the music in the settings app (SR3Ultimate.bat, Options), or run
SR3Ultimate.bat -Music src. The app adds the tunes at the end of the game's stream file; only the 1995 courses in the
Classic mode play them, each its own, and SEGA Rally 3's own stages and menus keep their music (extras.ps1,
Set-MusicSource; sr3mods.ps1, Set-CourseTune). A course whose tune is not there plays the Classic mode's own music.
Nothing here is SEGA's data: the recording comes out of the ROM set on your disk and stays in a git-ignored folder.

How the recording is made (see docs/kb/audio.md, "SEGA Rally Championship"):
  - MAME runs the set `srallyc` with -video none (its window is created but never shown), -sound none, -wavwrite.
    MAME 0.229 also wants three small programs of boards that have no part in the sound (drive board, link board,
    billboard); when your set lacks them, blank stand-ins are written to the work folder so that MAME starts.
  - A Lua script (written to the work folder) switches off the sound chip's MIDI-in interrupt every frame, so the sound
    program no longer hears the main board (whose attract mode would play over the tunes and stop them), and asks for
    each tune the way the sound program's own sequencer queues a message: 3 bytes "AE 10 nn" at RAM 0x1000 + the write
    index (0x2504), index + 4, count (0x2506) + 1.
  - Which tune belongs to which course is read from the main program (the table the game itself uses after "Go").
  - Every tune is recorded from its start through two passes of its loop. The script logs when each list entry of the
    tune began; `build` checks those times against the lengths read from the ROM, the silence between the tunes, and
    that the second pass sounds like the first.
What a tune file holds: the tune's first part, then the SECOND pass of its loop (it begins with the ring of the notes
before it, as every later pass does). SEGA Rally 3's stream reader goes from the end of a looping stream to its "loop
start" (routine 0x5681C0), so with the loop start of tunes.json the tune goes round for ever the way the arcade plays
it: first part once, then the loop. Both seams are blended over 20 ms into the samples that precede the second pass.
"""
import os, sys, re, csv, argparse, subprocess, wave, time
import statistics
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import audio_dsp as dsp
import src_audio as sa

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'import', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
MAME = _cm.SETTINGS.get('mame', '')
SOUND_FILES = ("epr-17890", "mpr-17756", "mpr-17757", "mpr-17886", "mpr-17887", "epr-17888", "epr-17889")
# file name <- the 1995 course whose tune it holds (the tune's name comes from the ROM: SrcRom.race_tunes)
COURSES = [("desert", "Desert"), ("forest", "Forest"), ("mountain", "Mountain"), ("lakeside", "Lake Side")]
LEVEL_OF = "Hyper Conditioned Reflex_FullQualityVersion"      # the Classic mode's own tune: the 1995 tunes are made as loud
VOICE_CHECK = "LongEasyRightMaybe"          # one co-driver call is recorded too, to check the clips' rate against the emulator
T0 = 3.0; BOOT = 32.0; GAP = 3.0; TAIL = 2.0; SEAM = 0.02; RATE = 44100      # seconds: first request (plain / --after-boot), pause between items

def default_work(): return os.path.join(sa._cm.WORK, "audio", "src-music")
def default_out(): return os.path.join(sa._cm.DATA, "audio", "music", "src")

def course_tunes(rom):
    """[(file key, course, tune dict)] : the tune each 1995 course plays in a championship"""
    tunes = {t["name"]: t for t in rom.tunes()}; play = rom.race_tunes()
    return [(key, course, tunes[play[course][0]]) for key, course in COURSES]

def make_plan(rom, sr3=None):
    """[dict(group, number, name, seconds, ...)] : every course tune once, from its start through two passes of its loop"""
    plan = []
    for key, course, t in course_tunes(rom):
        first = t["intro_ticks"] * sa.TICK_SAMPLES / RATE; loop = t["loop_ticks"] * sa.TICK_SAMPLES / RATE
        need = first + 2 * loop + TAIL if t["loops"] else first + 3.0
        if not any(x["name"] == t["name"] for x in plan): plan.append(dict(group=0x10, number=t["number"], name=t["name"], seconds=need, tune=t))
    voice = rom.voice_clips()[VOICE_CHECK]
    code = next(r["code"] for r in rom.requests() if r["name"] == VOICE_CHECK)
    plan.append(dict(group=code[1], number=code[2], name=VOICE_CHECK, seconds=voice["length"] / voice["rate"] + 1.5, tune=None))
    return plan

def print_plan(rom, sr3=None):
    plan = make_plan(rom)
    print("race tunes by 1995 course, read from the main program (championship / the other mode):")
    for c, (a, b) in rom.race_tunes().items(): print("   %-10s %s%s" % (c, a, "" if a == b else "   / " + b))
    print("recording: %d items, %.0f emulated seconds" % (len(plan), T0 + sum(p["seconds"] + GAP + 0.5 for p in plan)))
    for p in plan: print("   request AE %02X %02X  %-20s %6.1f s" % (p["group"], p["number"], p["name"], p["seconds"]))
    print("the files `build` writes:")
    for key, course, t in course_tunes(rom):
        first = t["intro_ticks"] * sa.TICK_SAMPLES / RATE; loop = t["loop_ticks"] * sa.TICK_SAMPLES / RATE
        print("   %-13s %-9s %-18s first part %7.2f s%s" % (key + ".wav", course, t["name"], first, ", then a loop of %.2f s (file: %.2f s)" % (loop, first + loop) if loop else " (plays once)"))

# ---------------------------------------------------------------- record
LUA = r'''-- Written by tools/audio/src_music.py. Plays tunes of SEGA Rally Championship on the emulated sound board, one
-- after the other, and notes in record_log.txt when each began. MAME's -wavwrite records what the board plays.
local PLAN = {
%PLAN%}
local ALLOFF = {
%ALLOFF%}
local T0, GAP, MASK_FROM = %T0%, %GAP%, %MASK%
local log = io.open("record_log.txt", "w")
local function L(fmt, ...) log:write(string.format(fmt, ...), "\n"); log:flush() end
local snd
local phase, idx, t_mark, t_start, last_list, tries, stopped = "boot", 0, 0, 0, -1, 0, false
-- one message for the sound program, queued the way its own sequencer does it (0x6028FA): 3 bytes at RAM 0x1000 + the
-- write index (word at 0x2504, 12 bits), then index + 4 and the count (byte at 0x2506) + 1
local function message(a, b, c)
  local w = snd:read_u16(0x2504) & 0xFFF
  snd:write_u8(0x1000 + w, a); snd:write_u8(0x1001 + w, b); snd:write_u8(0x1002 + w, c)
  snd:write_u16(0x2504, (w + 4) & 0xFFF); snd:write_u8(0x2506, (snd:read_u8(0x2506) + 1) & 0xFF)
end
local function request(g, n) message(0xAE, g, n) end
local function finish(t, why)
  phase = "done"; L("%.5f %s", t, why); log:close()
  pcall(function() manager.machine:exit() end)
end
local last_t = -1
local function tick()
  if phase == "done" then return end
  local t = emu.time()
  if t == last_t then return end
  last_t = t
  -- SCSP interrupt enable (0x10041E): timer A and timer B only. Without the MIDI-in interrupt the sound program does
  -- not hear the main board any more.
  if t >= MASK_FROM then snd:write_u16(0x10041E, 0x00C0) end
  if phase == "boot" then
    if t >= T0 and snd:read_u32(0x5000) == 0x00800000 and (MASK_FROM > 0 or snd:read_u8(0x2506) == 0) then
      -- with MASK_FROM > 0 the game was heard until now: what its own "all sound off" routine (0x26150) sends
      if MASK_FROM > 0 then for _, m in ipairs(ALLOFF) do message(m[1], m[2], m[3]) end end
      L("%.5f ready", t); phase = "gap"; t_mark = t + (MASK_FROM > 0 and GAP or 0)
    elseif t > 120 then finish(t, "ERROR the sound program did not come up") end
  elseif phase == "gap" then
    if t >= t_mark then
      idx = idx + 1
      if idx > #PLAN then finish(t, "done"); return end
      request(PLAN[idx][1], PLAN[idx][2]); t_start = t; tries = 0; last_list = -1; stopped = false; phase = "play"
      L("%.5f start %02X %02X %s", t, PLAN[idx][1], PLAN[idx][2], PLAN[idx][3])
    end
  elseif phase == "play" then
    local p = PLAN[idx]
    if p[1] == 0x10 then                                   -- a tune: the music slot is at RAM 0x3000
      local flags, list = snd:read_u8(0x3000), snd:read_u32(0x3008)
      if flags & 0x80 ~= 0 and list ~= last_list then L("%.5f list %08X %02X", t, list, flags); last_list = list end
      if flags & 0x80 == 0 and not stopped then
        if t - t_start < 1.0 and t - t_start > 0.25 and tries < 3 then      -- the request was lost: once more
          tries = tries + 1; request(p[1], p[2]); t_start = t; last_list = -1; L("%.5f start %02X %02X %s (again)", t, p[1], p[2], p[3])
        elseif t - t_start >= 1.0 then stopped = true; L("%.5f ended %s", t, p[3]) end
      end
    end
    if t >= t_start + p[4] then
      request(0x10, 0x00); L("%.5f stop %s", t, p[3]); t_mark = t; tries = 0; phase = "stopping"
    end
  elseif phase == "stopping" then
    local flags = snd:read_u8(0x3000)
    if flags & 0x80 == 0 or t - t_mark > 1.0 then
      if flags & 0x80 ~= 0 then L("%.5f ERROR the tune did not stop", t) end
      L("%.5f quiet", t); t_mark = t + GAP; phase = "gap"
    elseif t - t_mark > 0.25 and tries < 2 then tries = tries + 1; request(0x10, 0x00); L("%.5f stop (again)", t) end
  end
end
local ok, err = pcall(function()
  snd = manager.machine.devices[":audiocpu"].spaces["program"]
  local hooks = 0
  for _, name in ipairs({"register_frame_done", "register_frame", "register_periodic"}) do
    if emu[name] and pcall(emu[name], function() local good, e = pcall(tick); if not good and phase ~= "done" then finish(-1, "ERROR " .. tostring(e)) end end) then hooks = hooks + 1 end
  end
  L("0 script loaded, %d hooks", hooks)
end)
if not ok then L("ERROR %s", tostring(err)) end
'''

ALL_OFF = (154, 173, 181, 184, 186, 151, 70)      # what the game's "all sound off" routine (main program 0x26150) asks for, parameter 0
def write_lua(plan, path, rom, after_boot=False):
    rows = "".join('  {0x%02X, 0x%02X, "%s", %.3f},\n' % (p["group"], p["number"], p["name"], p["seconds"]) for p in plan)
    req = rom.requests()
    off = "".join("  {0x%02X, 0x%02X, 0x%02X},     -- %s\n" % (req[i]["code"][0], req[i]["code"][1], 0 if req[i]["code"][2] == 0xFF else req[i]["code"][2], req[i]["name"]) for i in ALL_OFF)
    t0 = BOOT if after_boot else T0
    text = LUA.replace("%PLAN%", rows).replace("%ALLOFF%", off).replace("%T0%", "%.1f" % t0).replace("%GAP%", "%.1f" % GAP).replace("%MASK%", "%.1f" % (t0 - 0.5 if after_boot else 0.0))
    open(path, "w", newline="\n").write(text)

def stand_ins(mame, rompath, work):
    """blank files for ROMs MAME asks for that the set lacks and that have no part in the sound"""
    r = subprocess.run([mame, "-noreadconfig", "-rompath", rompath, "-verifyroms", "srallyc"], capture_output=True, text=True, creationflags=0x08000000)
    made = []
    for m in re.finditer(r"^srallyc\s*:\s*(\S+) \((\d+) bytes\) - NOT FOUND(?: \((\w+)\))?", r.stdout + r.stderr, re.M):
        name, size, dev = m.group(1), int(m.group(2)), m.group(3)
        if name.lower().startswith(SOUND_FILES): raise SystemExit("your ROM set lacks %s, which the recording needs" % name)
        for d in ["srallyc"] + ([dev] if dev else []):
            os.makedirs(os.path.join(work, "roms", d), exist_ok=True)
            with open(os.path.join(work, "roms", d, name), "wb") as f: f.write(b"\0" * size)
        made.append(name)
    return made

def record(rom, sr3, mame, work, after_boot=False):
    if not os.path.exists(mame): raise SystemExit("MAME not found: %s  (give it with --mame)" % mame)
    os.makedirs(work, exist_ok=True)
    plan = make_plan(rom, sr3); total = (BOOT + GAP if after_boot else T0) + sum(p["seconds"] + GAP + 0.5 for p in plan)
    romdir = os.path.dirname(os.path.abspath(rom.path)); rompath = os.path.join(work, "roms") + ";" + romdir
    made = stand_ins(mame, rompath, work)
    if made: print("blank stand-ins written for board programs your set lacks (no part in the sound): " + ", ".join(made))
    write_lua(plan, os.path.join(work, "record.lua"), rom, after_boot)
    for f in ("src_tunes.wav", "record_log.txt"):
        if os.path.exists(os.path.join(work, f)): os.remove(os.path.join(work, f))
    cmd = [mame, "srallyc", "-noreadconfig", "-rompath", rompath, "-video", "none", "-sound", "none", "-window", "-noswitchres", "-nothrottle",
           "-frameskip", "10", "-samplerate", str(RATE), "-wavwrite", "src_tunes.wav", "-seconds_to_run", str(int(total + 60)),
           "-autoboot_script", "record.lua", "-autoboot_delay", "0", "-skip_gameinfo", "-noplugins", "-output", "none",
           "-keyboardprovider", "none", "-mouseprovider", "none", "-lightgunprovider", "none", "-joystickprovider", "none",
           "-uifontprovider", "none", "-numprocessors", "1", "-priority", "-15"]
    print("recording %d items, %.0f emulated seconds, with MAME (no window, no sound, one thread at idle priority)..." % (len(plan), total))
    print("   " + subprocess.list2cmdline(cmd)); sys.stdout.flush()
    t0 = time.time()
    with open(os.path.join(work, "mame_output.txt"), "w") as out:
        rc = subprocess.run(cmd, cwd=work, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=0x40 | 0x08000000).returncode   # idle priority, no console
    log = os.path.join(work, "record_log.txt")
    done = os.path.exists(log) and any(l.split()[1:2] == ["done"] for l in open(log))
    print("MAME ended after %.0f s (exit code %d); the recording is %s" % (time.time() - t0, rc, "complete" if done else "NOT complete: see %s and %s" % (log, os.path.join(work, "mame_output.txt"))))
    return done

# ---------------------------------------------------------------- build
def read_log(path):
    items = []; errors = []; cur = None; hooks = None
    for line in open(path):
        f = line.split()
        if len(f) < 2: continue
        if "ERROR" in line: errors.append(line.strip())
        try: t = float(f[0])
        except ValueError: continue
        if f[1] == "script": hooks = line.strip()
        elif f[1] == "start": cur = dict(start=t, group=int(f[2], 16), number=int(f[3], 16), name=f[4], lists=[], stop=None, ended=None); items.append(cur)
        elif cur is None: continue
        elif f[1] == "list": cur["lists"].append((t, int(f[2], 16), int(f[3], 16)))
        elif f[1] == "stop" and cur["stop"] is None: cur["stop"] = t
        elif f[1] == "ended": cur["ended"] = t
    last = {}
    for it in items: last[it["name"]] = it                                # a request sent again replaces the first try
    return list(last.values()), errors, hooks

class Recording:
    def __init__(self, path):
        self.w = wave.open(path, "rb")
        if (self.w.getnchannels(), self.w.getframerate(), self.w.getsampwidth()) != (2, RATE, 2): raise SystemExit("%s is not a stereo %d Hz 16-bit WAV" % (path, RATE))
        self.n = self.w.getnframes()
    def get(self, t0, t1):
        a = max(0, int(round(t0 * RATE))); b = min(self.n, int(round(t1 * RATE)))
        if b <= a: return dsp.PCM(0, 2)
        self.w.setpos(a); return dsp.from_pcm(self.w.readframes(b - a), 16, 2)

# This can actually be done with numpy the following way: percentile/max,
# sqrt(mean(x*x)), and frame reshapes; it's done this way because contiguous C
# scans avoid intermediate arrays while retaining the same frame boundaries.
onset = dsp.onset
def envelope(x, hop=441): return dsp.envelope(x, hop)
rms = dsp.rms

def entry_times(rom, it, tunes):
    """[(seconds from the tune's start by the ROM's lengths, seconds from its start as logged)] of the list entries of a recorded tune, and how many were played"""
    t = tunes[it["name"]]; base = rom.group(0x10)[t["number"]] + 4
    # the playlist pointer (0x3008) holds the address of the NEXT entry: entry k is playing once it reads base + 4 (k + 1)
    n = len(t["sections"]); exp = {}; tick = 0; k = 0; played = 0
    while tick * sa.TICK_SAMPLES / RATE < (it["stop"] - it["start"]) * 1.05 and played < 400:
        exp.setdefault(base + 4 * (k + 1), []).append(tick * sa.TICK_SAMPLES / RATE); tick += t["ticks"][k]; played += 1
        k += 1
        if k == n:
            if t["loop"] is None: break
            k = t["loop"]
    out = []; seen = {}
    for (tm, ptr, flags) in it["lists"]:
        j = seen.get(ptr, 0); seen[ptr] = j + 1
        if ptr in exp and j < len(exp[ptr]): out.append((exp[ptr][j], tm - it["start"]))
    return out, played

def recording_clock(rom, items):
    """How long a tick of the sound program is in THIS recording, as a factor on the length assumed from the ROM (50 samples): the slope of the logged
    entry times over the computed ones, all tunes together (each with its own start). The emulated board need not keep the assumed time to the
    sample: MAME 0.229 gives 0.99301 (49.65 samples a tick). 1.0 when the log holds too little to tell."""
    tunes = {t["name"]: t for t in rom.tunes()}; num = den = 0.0; n = 0
    for it in items:
        if it["group"] != 0x10 or it["stop"] is None: continue
        p = entry_times(rom, it, tunes)[0]
        if len(p) < 3: continue
        # This can actually be done with numpy the following way: (p-p.mean(0)).T @ (p-p.mean(0));
        # it's done this way because these lists contain only a few dozen entries.
        mx=sum(a for a,b in p)/len(p); my=sum(b for a,b in p)/len(p)
        x=[a-mx for a,b in p]; y=[b-my for a,b in p]
        num += sum(a*b for a,b in zip(x,y)); den += sum(a*a for a in x); n += len(p)
    k = num / den if den > 100.0 and n >= 6 else 1.0
    return k if 0.95 < k < 1.05 else 1.0

def check_recording(rom, items, rec, log=print, clock=1.0):
    """the tunes' own timing against the ROM (at the recording's clock), silence between items, the loop repeating, the voice clip's rate"""
    ok = True; tunes = {t["name"]: t for t in rom.tunes()}
    for i, it in enumerate(items):
        if it["group"] != 0x10: continue
        t = tunes[it["name"]]; pts, played = entry_times(rom, it, tunes)
        dev = [got - clock * want for want, got in pts]
        worst = max(abs(d - statistics.median(dev)) for d in dev) if dev else 9.9
        good = len(dev) >= min(played, 2) and worst < 0.06
        ok &= good
        log("   %-18s %3d list entries logged, %3d match the ROM's lengths; worst difference %.0f ms (a frame is 17 ms)  %s" % (it["name"], len(it["lists"]), len(dev), 1000 * worst, "ok" if good else "NOT AS EXPECTED"))
        level = rms(rec.get(it["start"] + 1.0, min(it["stop"], it["start"] + 20.0)))
        nxt = items[i + 1]["start"] if i + 1 < len(items) else it["stop"] + GAP
        quiet = rms(rec.get(it["stop"] + 1.5, nxt - 0.1))
        good = level > 30 and quiet < 0.02 * level
        ok &= good
        log("   %-18s level %.0f while it plays, %.1f in the pause after it  %s" % ("", level, quiet, "ok" if good else "NOT AS EXPECTED"))
        if t["loops"]:
            first = clock * t["intro_ticks"] * sa.TICK_SAMPLES / RATE; loop = clock * t["loop_ticks"] * sa.TICK_SAMPLES / RATE
            span = min(30.0, it["stop"] - it["start"] - first - loop - 2.5)
            if span > 5:
                # the loudness curve of the second pass against the first, at the computed place and at shifts of up to 2 s round it: the best
                # agreement must be AT the computed place (a pass begins with the ring of other notes than the first did, so the curves are
                # alike, not equal: 0.77 to 0.97 on the first real recording, against 0.02 to 0.34 a second off)
                a = envelope(rec.get(it["start"] + first + 0.3, it["start"] + first + 0.3 + span)); best = (-2.0, 0.0); c = 0.0
                for shift in range(401):
                    sh = -2.0 + shift * (-1.99 - -2.0)  # np.arange retains the rounded step
                    b = envelope(rec.get(it["start"] + first + loop + 0.3 + sh, it["start"] + first + loop + 0.3 + sh + span)); m = min(len(a), len(b))
                    cc = dsp.correlation(a[:m], b[:m]) if m > 10 else 0.0
                    if abs(sh) < 0.005: c = cc
                    if cc > best[0]: best = (cc, float(sh))
                good = c > 0.6 and abs(best[1]) <= 0.025; ok &= good
                log("   %-18s the loop comes round after %.3f s: loudness curves of the two passes agree %.2f there, and best (%.2f) at %+.2f s from there  %s" % ("", loop, c, best[0], best[1], "ok" if good else "NOT AS EXPECTED"))
    v = [it for it in items if it["group"] != 0x10]
    if v:
        it = v[0]; clip = rom.voice_clips()[it["name"]]; x = rec.get(it["start"] - 0.05, it["stop"] + 0.5).column(-1)
        res = {}
        for rate in (11025, 22050, 44100):
            ref = sa.resample(clip["pcm"], rate, RATE, taps=32)
            if len(ref) + 10 >= len(x): res[rate] = 0.0; continue
            res[rate] = dsp.voice_score(x, ref)
        best = max(res, key=res.get); good = best == int(round(clip["rate"])) and res[best] > 0.8
        ok &= good
        log("   co-driver clip %s as the emulator plays it against the ROM clip at 11025 / 22050 / 44100 Hz: %.2f / %.2f / %.2f -> %d Hz  %s"
            % (it["name"], res[11025], res[22050], res[44100], best, "ok (the clips' rate, %d Hz, is right)" % round(clip["rate"]) if good else "NOT AS EXPECTED"))
    return ok

def tune_file(x, t, clock=1.0):
    """recording of a tune from its first sample (stereo, 44100 Hz) -> (stereo 32000 Hz samples, loop start in frames)
    clock: the length of a tick in this recording over the 50 samples assumed from the ROM (recording_clock).
    First part + the second pass of the loop; the end of the first part and the end of the loop are blended into the
    samples that precede the second pass in the recording, so both lead into its first sample without a step.
    Loop start and loop length are whole multiples of 16 frames, as the sizes of the game's own streams are."""
    n_first = int(round(clock * t["intro_ticks"] * sa.TICK_SAMPLES)); n_loop = int(round(clock * t["loop_ticks"] * sa.TICK_SAMPLES)); r = 32000.0 / RATE
    if not t["loops"]: return sa.resample(x[:n_first + RATE], RATE, 32000), 0
    if len(x) < n_first + 2 * n_loop: return None, 0
    y = sa.resample(x[:n_first + 2 * n_loop + 4096], RATE, 32000)
    a = 16 * int(round(n_first * r / 16)); length = 16 * int(round(n_loop * r / 16)); s2 = a + int(round(n_loop * r))
    head = y[:a].copy(); body = y[s2:s2 + length].copy(); n = min(int(SEAM * 32000), a, length)
    if n:
        before = y[s2 - n:s2]
        dsp.blend(head[-n:], before); dsp.blend(body[-n:], before)
    return dsp.concat([head, body]), a

def build(rom, sr3, work, out_dir, log=print):
    import json
    wav = os.path.join(work, "src_tunes.wav"); lg = os.path.join(work, "record_log.txt")
    if not (os.path.exists(wav) and os.path.exists(lg)): raise SystemExit("no recording in %s: run  python src_music.py record  first" % work)
    items, errors, hooks = read_log(lg); rec = Recording(wav); byname = {it["name"]: it for it in items}
    log("recording: %.0f s, %d items; %s" % (rec.n / RATE, len(items), hooks or "no script line in the log"))
    for e in errors: log("   LOG " + e)
    missing = [p["name"] for p in make_plan(rom) if p["name"] not in byname or byname[p["name"]]["stop"] is None]
    if missing: raise SystemExit("the recording is not complete (missing: %s). Run  python src_music.py record  again." % ", ".join(missing))
    clock = recording_clock(rom, items)
    log("   the sound program's tick in this recording: %.5f of the 50 samples assumed from the ROM (%.2f samples); everything below is cut by the recording's clock" % (clock, clock * sa.TICK_SAMPLES))
    ok = check_recording(rom, items, rec, log, clock) and not errors
    if not ok: log("   The checks above did not all pass: listen to the result before trusting it.")
    os.makedirs(out_dir, exist_ok=True)
    target = sa.loud_half_rms(sr3.original(sr3.find(LEVEL_OF)), 32000, 1.0); notes = {}; rows = []
    for key, course, t in course_tunes(rom):
        it = byname[t["name"]]; x = rec.get(it["start"] - 0.1, it["stop"] + 0.4); x = x[onset(x):]
        y, start = tune_file(x, t, clock)
        if y is None:
            note = "the recording holds less than two passes of the loop: no file (the course keeps the Classic mode's music)"
            rows.append([key + ".wav", course, t["name"], "", "", "", "", note]); log("   %-13s %s" % (key + ".wav", note)); ok = False; continue
        y, g = sa.match_level(y, target, 32000, 1.0, always_limit=False)
        sa.write_wav(os.path.join(out_dir, key + ".wav"), y, 32000)
        step, usual = dsp.seam(y, start)
        notes[key] = dict(file=key + ".wav", course=course, tune=t["name"], frames=int(len(y)), loop_start=int(start), seconds=round(len(y) / 32000.0, 3),
                          loop_seconds=round((len(y) - start) / 32000.0, 3), gain=round(g, 3))
        holds = "first part %.2f s, then the loop %.2f s (loop start at frame %d); step at the seam %.0f against %.0f between neighbouring samples" % (start / 32000.0, (len(y) - start) / 32000.0, start, step, usual)
        rows.append([key + ".wav", course, t["name"], "%.3f" % (len(y) / 32000.0), "%.3f" % (start / 32000.0), "%.2f" % g, "%.0f" % dsp.peak(y), holds])
        log("   %-13s <- %-18s gain %.2f, peak %5.0f; %s" % (key + ".wav", t["name"], g, dsp.peak(y), holds))
    with open(os.path.join(out_dir, "tunes.json"), "w", encoding="utf-8") as f: json.dump(notes, f, indent=1)
    with open(os.path.join(out_dir, "mapping.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["file", "src_1995_course", "src_1995_tune", "seconds", "loop_start_seconds", "gain", "peak", "what_the_file_holds"]); w.writerows(rows)
    log("tunes written to %s%s" % (out_dir, "" if ok else "  (with warnings, see above)"))
    return ok

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=["plan", "record", "build", "all"])
    ap.add_argument("--rom", default=sa.ROM_ZIP); ap.add_argument("--mame", default=MAME); ap.add_argument("--work", default=None)
    ap.add_argument("--audio", default=None); ap.add_argument("--originals", action="append"); ap.add_argument("--out", default=None)
    ap.add_argument("--after-boot", action="store_true")
    a = ap.parse_args()
    from rebuild_bank import GAME_AUDIO
    rom = sa.SrcRom(a.rom)
    work = a.work or default_work(); out = a.out or default_out()
    if a.what == "plan": print_plan(rom); return
    sr3 = sa.Sr3Clips(a.audio or GAME_AUDIO, a.originals) if a.what in ("build", "all") else None
    if a.what in ("record", "all"):
        if not record(rom, sr3, a.mame, work, a.after_boot): sys.exit(1)
    if a.what in ("build", "all"):
        sys.exit(0 if build(rom, sr3, work, out) else 2)

if __name__ == "__main__":
    main()
