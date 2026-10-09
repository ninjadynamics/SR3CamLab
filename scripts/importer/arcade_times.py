"""Stage time limits of SEGA Rally 3 = the ArcadeDatabase, not the track files.
    python arcade_times.py dump                       -> table of every stage / mode / laps / difficulty
    python arcade_times.py classic <game> <course>    -> ../out/arcadedb_<course>/arcadedatabase_xdata.sbf : a COPY of the
                                                         database whose Desert4 ("Classic" slot) records hold times for
                                                         that classic course's checkpoint markers. Never touches GAME.
File <game>/Rally/ArcadeDatabase/arcadedatabase_xdata.sbf, chunk e9e6b4fb (19012 bytes) = u32 2, then
    [track 0..5][mode 0..2][laps setting 0..2] blocks of 0x160 bytes = 3 x (difficulty) { u32 nLaps, 4 x { u32 lap, u32 t[6] } } + u32
track = position in the track list (Tropical, Canyon, Alpine, Lakeside, Desert, Stadium); t[k-1] = SECONDS granted by
checkpoint marker k of that lap (marker 1 = the gate just after the start line: lap 1's t[0] is the initial time).
Reader: exe 0x661AA0 (called by 0x5ABD40, which adds seconds * 1000 to the limit at [0x9DB4C8]); see 03_master_xdata_route.md."""
import os, sys, struct, json
from common import *
import sbfw
DB = os.path.join(GAME, 'ArcadeDatabase', 'arcadedatabase_xdata.sbf'); CID = 0xe9e6b4fb
NAMES = ['Tropical4', 'Canyon4', 'Alpine4', 'Lakeside4', 'Desert4', 'Stadium4']

def off(track, mode, laps, diff): return 4 + 0x160 * (laps + 3 * (mode + 3 * track)) + 0x74 * diff
def get(d, track, mode, laps, diff):
    o = off(track, mode, laps, diff); n = struct.unpack_from('<I', d, o)[0]
    return [struct.unpack_from('<7I', d, o + 4 + 0x1c * k) for k in range(min(n, 4))]
def put(d, track, mode, laps, diff, recs):
    o = off(track, mode, laps, diff); struct.pack_into('<I', d, o, len(recs))
    for k in range(4): struct.pack_into('<7I', d, o + 4 + 0x1c * k, *(list(recs[k]) + [0] * 7)[:7] if k < len(recs) else [0] * 7)

def dump():
    d = sbfw.read_sbf(DB).byid()[CID].data
    for t in range(6):
        for mode in range(3):
            for laps in range(3):
                rows = [get(d, t, mode, laps, k) for k in range(3)]
                if any(rows): print('%-10s mode %d laps-setting %d: %s' % (NAMES[t], mode, laps, ' | '.join(' '.join('L%d:%s' % (r[0], '+'.join(str(v) for v in r[1:] if v) or '0') for r in row) for row in rows)))

def classic_times(game, crs):
    """seconds per marker for the BUILT classic step: lap 1 and later laps, three difficulties (GUESS, see 14_importer.md)"""
    import course, pacenotes as PN
    cfg = course.use(game, crs); name = 'step%02d_%s_classic_desert4' % (cfg['steps']['classic'], cfg['name'])
    PN.TRACKS = OUT; P, M, _ = PN.read(os.path.join(name, 'Desert4')); nmark = sum(1 for m in M if (m['a'], m['b']) == (0, 5))
    cname = {'mountain': 'Mountain', 'desert': 'Desert', 'lakeside': 'Lake Side', 'forest': 'Forest'}[cfg['name']]
    T = json.load(open(os.path.join(os.path.dirname(WORK), 'classic', 'sr2_gameplay', game, 'src_checkpoints_times.json')))[cname]
    pr = T['practice']['frames_by_laps']; key = sorted(pr)[0]; out = []
    for dk in ('difficulty_0', 'difficulty_1', 'difficulty_2'):        # 1995 practice mode, its shortest lap setting, frames / 60
        v = [f / 60.0 for f in pr[key][dk]]; t0, ext = v[0], v[1:]
        if len(ext) == nmark - 1: lap1 = [t0] + ext
        else: lap1 = [t0] + ([sum(ext)] if nmark > 1 else []) + [0] * max(0, nmark - 2); lap1[0] += sum(ext) if nmark == 1 else 0
        later = [max(ext) if ext else round(0.6 * t0)] + lap1[1:]      # at the line on later laps: the largest 1995 extension (GUESS)
        out.append(([int(round(x)) for x in lap1], [int(round(x)) for x in later]))
    return cfg, name, nmark, out

def classic(game, crs):
    cfg, name, nmark, times = classic_times(game, crs)
    f = sbfw.read_sbf(DB); c = f.byid()[CID]; d = bytearray(c.data); assert len(d) == 19012 and struct.unpack_from('<I', d, 0)[0] == 2
    b0 = sbfw.write_sbf(f, compress=True); g0 = sbfw.read_sbf(b0)
    assert all(a.data == b.data and a.fix == b.fix and a.ref == b.ref and a.kind == b.kind and a.id == b.id for a, b in zip(f.chunks, g0.chunks)), 'writer round trip'
    for laps in range(3):                                              # laps setting 0..2 = 2, 3, 4 laps
        for diff in range(3):
            lap1, later = times[diff]; put(d, 4, 0, laps, diff, [[1] + lap1] + [[k + 2] + later for k in range(laps + 1)])
    c.data = bytes(d); out = os.path.join(OUT, 'arcadedb_%s' % cfg['name']); os.makedirs(out, exist_ok=True)
    open(os.path.join(out, 'arcadedatabase_xdata.sbf'), 'wb').write(sbfw.write_sbf(f, compress=True))
    g = sbfw.read_sbf(os.path.join(out, 'arcadedatabase_xdata.sbf')); assert g.byid()[CID].data == c.data
    print('%s: %d checkpoint markers in %s; Desert4 arcade records (mode 0) now: lap 1 %s, later laps %s (easy / normal / hard) -> %s' %
          (cfg['name'], nmark, name, [t[0] for t in times], [t[1] for t in times], out))

if __name__ == '__main__':
    if sys.argv[1:2] == ['classic']: classic(*sys.argv[2:4])
    else: dump()
