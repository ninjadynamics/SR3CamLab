"""The recorded tunes' own clock against the lengths read from the ROM: is the emulated sound board a little faster or slower than computed?
    python music_tempo.py     (run from SR3CamLab\scripts\rom_tools)"""
import os, sys
import numpy as np
sys.path.insert(0, os.getcwd())
import src_music as M, src_audio as sa
rom = sa.SrcRom(sa.ROM_ZIP)
work = M.default_work(); items, errors, hooks = M.read_log(os.path.join(work, 'record_log.txt')); rec = M.Recording(os.path.join(work, 'src_tunes.wav')); tunes = {t['name']: t for t in rom.tunes()}
for it in items:
    if it['group'] != 0x10: continue
    t = tunes[it['name']]; base = rom.group(0x10)[t['number']] + 4; n = len(t['sections']); exp = {}; tick = 0; k = 0; played = 0
    while tick * sa.TICK_SAMPLES / M.RATE < (it['stop'] - it['start']) * 1.05 and played < 400:
        exp.setdefault(base + 4 * (k + 1), []).append(tick * sa.TICK_SAMPLES / M.RATE); tick += t['ticks'][k]; played += 1; k += 1
        if k == n:
            if t['loop'] is None: break
            k = t['loop']
    seen = {}; pts = []
    for tm, ptr, flags in it['lists']:
        j = seen.get(ptr, 0); seen[ptr] = j + 1
        if ptr in exp and j < len(exp[ptr]): pts.append((exp[ptr][j], tm - it['start']))
    pts = np.array(pts); a, b = np.polyfit(pts[:, 0], pts[:, 1], 1); res = pts[:, 1] - (a * pts[:, 0] + b)
    first = t['intro_ticks'] * sa.TICK_SAMPLES / M.RATE; loop = t['loop_ticks'] * sa.TICK_SAMPLES / M.RATE
    print('%-18s %2d entries ; recorded time = %.6f x ROM time + %.3f s ; left over after that: worst %.0f ms ; first part %.3f -> %.3f s, loop %.3f -> %.3f s' % (it['name'], len(pts), a, b, 1000 * np.abs(res).max(), first, a * first, loop, a * loop))
    # does the loop come round after a x loop? the loudness curve of the second pass against the first, tried at shifts round it
    x = rec.get(it['start'] - 0.1, it['stop'] + 0.4); x = x[M.onset(x):]; span = 30.0; best = (-2, 0)
    e1 = M.envelope(x[int((a * first + 0.3) * M.RATE):int((a * first + 0.3 + span) * M.RATE)])
    for sh in np.arange(-2.0, 2.0001, 0.01):
        s0 = int((a * first + a * loop + 0.3 + sh) * M.RATE)
        if s0 < 0 or s0 + int(span * M.RATE) > len(x): continue
        e2 = M.envelope(x[s0:s0 + int(span * M.RATE)]); m = min(len(e1), len(e2)); c = float(np.corrcoef(e1[:m], e2[:m])[0, 1])
        if c > best[0]: best = (c, sh)
    s0 = int((first + loop + 0.3) * M.RATE); e2 = M.envelope(x[s0:s0 + int(span * M.RATE)]); e1r = M.envelope(x[int((first + 0.3) * M.RATE):int((first + 0.3 + span) * M.RATE)]); m = min(len(e1r), len(e2))
    print('   loudness of the two passes agrees %.2f with the ROM lengths ; %.2f with the measured clock, best at a shift of %+.2f s from it' % (float(np.corrcoef(e1r[:m], e2[:m])[0, 1]), best[0], best[1]))
