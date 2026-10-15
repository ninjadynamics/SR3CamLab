"""SR3 pace-note markers: read them from an arcade track and relate them to the corner geometry of its spline, then
write the same kind of markers for an imported centre line.
    python pacenotes.py [Track ...]     -> table of markers with the turn they cover, and the thresholds derived
Marker (0x1C): u16 a, u16 b, u32 0, u16 1, u16 nProps, f32 start, f32 end, f32 small, ptr props ; props = {ptr name, ptr value}."""
import os, sys, struct, collections, json
import numpy as np
from common import *
import sbfw

def cstr(d, o): return d[o:d.index(b'\0', o)].decode('latin1')

def read(track):
    f = sbfw.read_sbf(track_files(os.path.join(TRACKS, track))['master_xdata']); by = f.byid(); r = f.chunks[-1]; c = by[r.u32(0x18)]; d = c.data
    one, ns, nm, ps, pm = struct.unpack_from('<5I', d, 0); pn, npts, pp = struct.unpack_from('<3I', d, ps); P = np.frombuffer(d, '<f4', 3 * npts, pp).reshape(-1, 3).astype(float)
    M = []
    for k in range(nm):
        a, b, z, one_, npr, st, en, sm, ppr = struct.unpack_from('<HHIHHfffI', d, pm + 0x1c * k); props = {}
        for j in range(npr):
            pnm, pv = struct.unpack_from('<II', d, ppr + 8 * j); nm_ = cstr(d, pnm)
            raw = d[pv:pv + 4]; props[nm_] = (struct.unpack('<i', raw)[0], round(struct.unpack('<f', raw)[0], 4), cstr(d, pv) if 32 <= d[pv] < 127 else None)
        M.append(dict(a=a, b=b, start=st, end=en, small=sm, props=props))
    return P, M, int(r.u32(0x30)) if len(r.data) > 0x34 else 1

def turn(P, s, e):
    """signed heading change (degrees, + = left seen from above with x right / z up) and tightest radius between lap fractions s..e"""
    n = len(P) - 1; i0 = int(round(s * n)) % n; i1 = int(round(e * n)) % n; idx = [(i0 + k) % n for k in range(((i1 - i0) % n) + 1)]
    if len(idx) < 3: idx = [(i0 - 1) % n, i0, (i0 + 1) % n]
    Q = P[idx][:, [0, 2]]; D = np.diff(Q, axis=0); h = np.unwrap(np.arctan2(D[:, 1], D[:, 0])); dh = np.diff(h); L = np.linalg.norm(D, axis=1)
    rad = (L[:-1] / np.maximum(np.abs(dh), 1e-6)).min() if len(dh) else 1e9
    return float(np.degrees(h[-1] - h[0])) if len(h) > 1 else 0.0, float(rad), float(L.sum())

def table(track):
    P, M, direction = read(track); rows = []
    for m in M:
        if (m['a'], m['b']) == (0, 5): continue
        t, r, L = turn(P, min(m['start'], m['end']), max(m['start'], m['end'])); rows.append((m['a'], m['b'], {k: v for k, v in m['props'].items()}, round(m['start'], 4), round(m['end'], 4), round(t), round(r), round(L)))
    return rows, direction

# The Direction value of a (3,2) marker is an index 1..102 into two tables of Rally.exe (VERIFIED by disassembly, see
# 03_master_xdata_route.md): 0x70CD28[code] = SP_ speech event (played by 0x5AB0A0), 0x70CB88[code] = HUD icon 0..16.
# code = 17 * variant + type ; variant 0 plain, 1 LONG, 2 VERYLONG, 3 MAYBE, 4 LONG..MAYBE, 5 VERYLONG..MAYBE
TYPES = {1: 'BRIDGE', 2: 'CAUTION', 3: 'EASYLEFT', 4: 'EASYLEFTEASYRIGHT', 5: 'EASYRIGHT', 6: 'EASYRIGHTEASYLEFT', 7: 'HAIRPINLEFT',
         8: 'HAIRPINRIGHT', 9: 'MEDIUMLEFT', 10: 'MEDIUMLEFTMEDIUMRIGHT', 11: 'MEDIUMRIGHT', 12: 'MEDIUMRIGHTMEDIUMLEFT', 13: '90LEFT',
         14: '90RIGHT', 15: 'OVERJUMP', 16: 'ROADNARROWS', 17: 'WATER'}
VARIANTS = ['', 'LONG', 'VERYLONG', 'MAYBE', 'LONG+MAYBE', 'VERYLONG+MAYBE']
def code_name(code):
    if not 1 <= code <= 102: return '?'
    v, t = divmod(code - 1, 17); pre, _, post = VARIANTS[v].partition('+'); post = post or ('MAYBE' if pre == 'MAYBE' else ''); pre = '' if pre == 'MAYBE' else pre
    return 'SP_' + pre + TYPES[t + 1] + post
def code_for_name(name):
    """sound-test name of a 1995 SEGA Rally Championship co-driver call (EasyLeft, LongMidRightMaybe, KLeft, CHairpinRight,
    EasyLEasyR, OverJump, ...) -> (SR3 Direction code or None, caution flag). K (the 1995 call between Mid and Hairpin) is
    written as SR3's 90 LEFT / 90 RIGHT (GUESS); a leading C / Caution sets the flag (SR3 has no combined call)."""
    import re
    n = name; caution = False
    if n.startswith('Caution') and len(n) > 7: caution = True; n = n[7:]
    elif re.match(r'C(?=Hairpin|Mid|Easy|K[LR])', n): caution = True; n = n[1:]
    var = 0
    if n.startswith('VeryLong'): var = 2; n = n[8:]
    elif n.startswith('Long'): var = 1; n = n[4:]
    if n.endswith('Maybe'): var += 3; n = n[:-5]
    n = n.replace('EasyLEasyR', 'EasyLeftEasyRight').replace('EasyREasyL', 'EasyRightEasyLeft').replace('MidLMidR', 'MidLeftMidRight').replace('MidRMidL', 'MidRightMidLeft')
    key = n.upper().replace('MID', 'MEDIUM').replace('KLEFT', '90LEFT').replace('KRIGHT', '90RIGHT').replace('WATERSPLASH', 'WATER')
    if key == 'JUMP': key = 'OVERJUMP'
    t = {v: k for k, v in TYPES.items()}.get(key)
    return (17 * var + t if t else None), caution
# geometry fallback (no call names): + turn = left (the sign of d atan2(dz, dx) along the driving direction; checked on the
# arcade tracks: 16 of 19 left-coded and 21 of 21 right-coded markers turn that way over the next 150 m)
CODES = {1: (3, 9, 7), -1: (5, 11, 8)}                                  # gentle, tighter, hairpin
def corners(P, lead=60.0, min_turn=22.0):
    """centre line (1 m steps, closed, driving direction = increasing index) -> [(lap fraction of the note, code, turn deg, min radius)]"""
    Q = P[:, [0, 2]]; n = len(Q); D = np.roll(Q, -1, 0) - Q; h = np.unwrap(np.arctan2(D[:, 1], D[:, 0]))
    w = 9; k = np.ones(2 * w + 1) / (2 * w + 1); hs = np.convolve(np.concatenate([h[-w:] - (h[-1] - h[0] + (h[1] - h[0])), h, h[:w] + (h[-1] - h[0] + (h[1] - h[0]))]), k, 'valid')
    cur = np.gradient(hs)                                              # rad per metre
    out = []; i = 0; thr = 1.0 / 90.0                                  # a corner = stretch tighter than 90 m radius
    while i < n:
        if abs(cur[i]) > thr:
            j = i; sg = np.sign(cur[i])
            while j < n and cur[j] * sg > thr * 0.5: j += 1
            tr = float(np.degrees(hs[min(j, n - 1)] - hs[i])); rad = float(1.0 / np.abs(cur[i:j]).max())
            if abs(tr) >= min_turn:
                c = CODES[1 if tr > 0 else -1]; code = c[2] if (abs(tr) > 75 or rad < 19) else (c[1] if (abs(tr) > 42 and rad < 34) else c[0])
                out.append((((i - lead) % n) / n, code, round(tr), round(rad)))
            i = j + 1
        else: i += 1
    return out

if __name__ == '__main__':
    allrows = []
    for t in sys.argv[1:] or ['Desert4']:
        rows, direction = table(t); print(t, 'direction', direction, 'markers', len(rows), 'types', collections.Counter((r[0], r[1]) for r in rows))
        for r in rows[:60]: print('   type (%d,%d) %s  %.4f..%.4f  turn %5d deg  min radius %4d m  length %4d m' % (r[0], r[1], {k: (v[0] if abs(v[0]) < 100000 else v[1]) for k, v in r[2].items()}, r[3], r[4], r[5], r[6], r[7]))
        allrows += [(t,) + r for r in rows]
    by = collections.defaultdict(list)
    for r in allrows:
        if 'Direction' in r[3]: by[r[3]['Direction'][0]].append((r[6], r[7]))
    for k in sorted(by): a = np.array(by[k]); print('Direction %d: %d markers, turn median %.0f deg (%.0f..%.0f), min radius median %.0f m (%.0f..%.0f)' % (k, len(a), np.median(a[:, 0]), a[:, 0].min(), a[:, 0].max(), np.median(a[:, 1]), a[:, 1].min(), a[:, 1].max()))
