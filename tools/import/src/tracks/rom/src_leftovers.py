"""SEGA Rally Championship (Model 2A) leftovers -> ../src/
 (a) sound request names (main program sound-test table) -> request code -> MIDI key -> PCM sample; labelled pace notes
 (b) checkpoint sections, time added, initial time, laps."""
import struct, csv, json, os, re
import numpy as np
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
T = _DATA + r"/"
B = _TMP + r"/"
OUT = B + "sr2_gameplay/src/"; os.makedirs(OUT, exist_ok=True)
d = open(T + "work/tmp/m2/maincpu.bin", "rb").read(); O = 0x59F000      # RAM address = file offset + O
u = lambda a: struct.unpack_from('<I', d, a - O)[0]; s = lambda a: struct.unpack_from('<i', d, a - O)[0]
snd = np.fromfile(B + "sr_classic/roms/srallyc/epr-17890.30", np.uint8).reshape(-1, 2)[:, ::-1].tobytes()   # byte-swapped 68000 image, mapped at 0x600000
NREQ = 189; CODES = 0x5C3CE0; NAMES = 0x5C48C0
names = []
for i in range(NREQ):
    p = u(NAMES + 4 * i) - O; e = d.find(b'\0', p); names.append(d[p:e].decode('latin1'))
codes = [d[CODES - O + 3 * i:CODES - O + 3 * i + 3] for i in range(NREQ)]
# sound driver: group 0x20 track pointer list at 0x30AE (71 tracks); a voice track = BA 7B 00, 9A <key> <vel> ... FF 2F 00
P20 = 0x30AE; tracks = []
i = P20
while True:
    v = struct.unpack_from('>I', snd, i)[0]
    if not (0x603000 <= v < 0x640000): break
    o = v - 0x600000; e = snd.find(b'\xff\x2f\x00', o); tracks.append(snd[o:e + 3]); i += 4
def notes_of(tr):
    out = []; j = 0
    while j < len(tr) - 2:
        if tr[j] & 0xF0 == 0x90 and tr[j + 1] < 0x80 and tr[j + 2] < 0x80 and tr[j + 2] > 0: out.append((tr[j] & 15, tr[j + 1], tr[j + 2])); j += 3
        else: j += 1
    return out
# key map: 8-byte records {u16 global sample slot, u16 0xF000, ...}; key 0 at 0x8FF6. Slots count 20-byte entries from 0x9C26 (tables of 16+1, 49+1, 36+1, 18+1 entries, then table 4)
KEYMAP = 0x8FF6
def slot(key): return struct.unpack_from('>H', snd, KEYMAP + 8 * key)[0]
T4_FIRST_SLOT = 17 + 50 + 37 + 20
files = {}
for r in csv.DictReader(open(T + "classic/music/src_samples/index.csv")):
    if r['table'] == '4': files[int(r['sample_no'])] = r
stt = {int(r['sample_no']): r for r in csv.DictReader(open(T + "classic/music/src_speech_candidates.csv"))}
rows = []; lab = {}
for i in range(NREQ):
    c = codes[i]; row = dict(request=i, name=names[i], code=c.hex(), midi='', sample_table4='', file='')
    if c[0] == 0xAE and c[1] == 0x20 and c[2] < len(tracks):
        nt = notes_of(tracks[c[2]]); row['midi'] = ' '.join('ch%d key%d vel%d' % n for n in nt)
        if nt and nt[0][0] == 10:
            sm = [slot(k) - T4_FIRST_SLOT for ch, k, v in nt if slot(k) != 0xFFFF]; sm = sorted(set(sm))
            row['sample_table4'] = ' '.join(map(str, sm)); row['file'] = ' '.join(files[x]['file'] for x in sm if x in files)
            for x in sm: lab.setdefault(x, []).append(names[i])
    rows.append(row)
w = csv.DictWriter(open(OUT + 'src_sound_requests.csv', 'w', newline=''), fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
with open(OUT + 'src_speech_labels.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['file', 'table4_sample', 'label (sound-test name of the request that plays it)', 'seconds_if_22050', 'earlier speech-recognition guess'])
    for x in sorted(lab): w.writerow([files[x]['file'] if x in files else '', x, ' / '.join(lab[x]), files[x]['seconds_if_22050'] if x in files else '', (stt.get(x) or {}).get('recognised_at_22050 (Windows offline, constrained phrase list)', '')])
hits = [(x, lab[x], stt[x]['recognised_at_22050 (Windows offline, constrained phrase list)']) for x in sorted(lab) if x in stt and stt[x]['recognised_at_22050 (Windows offline, constrained phrase list)']]
print('requests', NREQ, 'voice tracks', len(tracks), 'labelled table-4 samples', len(lab)); print('cross-check with the speech recognition guesses:'); [print('   ', h) for h in hits]
# pace notes with names
COURSE = ['Desert', 'Forest', 'Mountain', 'Lake Side']; NOTE_TABS = [0x40470, 0x40500, 0x405a0, 0x40690]
with open(OUT + 'src_pace_notes_labelled.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['course_id', 'course', 'section', 'voice_request', 'name', 'icon', 'table4_sample', 'file'])
    for c in range(4):
        o = NOTE_TABS[c]
        while True:
            sec, a, b = struct.unpack_from('<3I', d, o)
            if sec == 9999 or sec == 0xffffffff: break
            w.writerow([c, COURSE[c], sec, a, names[a], b, rows[a]['sample_table4'], rows[a]['file']]); o += 12
# (b) checkpoints / times
J = {}
for c in range(4):
    secs = []
    for i in range(8):
        v = s(0x5E5670 + 32 * c + 4 * i)
        if v < 0: break
        secs.append(v)
    def block(base, laps):
        p = u(base + 4 * c); return {'difficulty_%d' % df: [s(p + 4 * (df * 4 + laps * 16 + i)) for i in range(len(secs))] for df in range(4)}
    laps_c = [u(0x5E5570 + 32 * k + 4 * c) for k in range(4)]; laps_p = [u(0x5E55F0 + 32 * k + 4 * c) for k in range(4)]
    J[COURSE[c]] = dict(course_id=c, checkpoint_sections=secs, note='section 0 = start line: its time is the initial time (code 0x1CC70: remaining time RAM 0x20B0B0 = table entry 0). Each later section adds its time (code 0x1D2FC..0x1D4EC: "CheckPoint" sound + voice). Units: frames, 60 = 1 s (LIKELY: 3600 = 60 s).',
        championship=dict(laps_by_setting=laps_c, frames_laps1=block(0x5E5CF0, 1), seconds_laps1={k: [round(x / 60, 1) for x in v] for k, v in block(0x5E5CF0, 1).items()}),
        practice=dict(laps_by_setting=laps_p, frames_by_laps={str(L): block(0x5E6310, L) for L in sorted(set(laps_p)) if L < 3}))
json.dump(J, open(OUT + 'src_checkpoints_times.json', 'w'), indent=1)
for k, v in J.items(): print(k, v['checkpoint_sections'], v['championship']['seconds_laps1'])
