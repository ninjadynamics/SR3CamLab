"""Reimport of Mountain from the ROM archive, stage by stage, each stage compared with what the importer has been reading.
Nothing the daily work reads is overwritten: every fresh result goes to scratchpad/repro."""
import os, sys, zipfile, hashlib, subprocess, shutil, time
import numpy as np
SP = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(SP, 'repro'); os.makedirs(os.path.join(R, 'm2'), exist_ok=True)
W = 'F:/Jogos/SEGA Rally 3/SR3 track format/work'; ZIP = 'F:/Emulators/SEGA Arcade/Model 2/Games/srallyc.zip'
sha = lambda b: hashlib.sha1(b).hexdigest()
def same(a, b, what):
    x = open(a, 'rb').read(); y = open(b, 'rb').read(); ok = x == y
    print('   %-34s %s (%d bytes, sha1 %s%s)' % (what, 'IDENTICAL' if ok else 'DIFFERENT', len(x), sha(x)[:12], '' if ok else ' against %d bytes %s' % (len(y), sha(y)[:12]))); return ok
print('0. ROM archive', ZIP, '(sha1 %s)' % sha(open(ZIP, 'rb').read())[:16])
z = zipfile.ZipFile(ZIP); chips = {n: z.read(n) for n in z.namelist()}; print('   %d files in the archive' % len(chips))
un = os.path.join(SP, 'sr_classic', 'roms', 'srallyc'); diff = [n for n in chips if not os.path.exists(os.path.join(un, n)) or open(os.path.join(un, n), 'rb').read() != chips[n]]
print('   unpacked copy the extracts were made from: %d of %d files identical to the archive%s' % (len(chips) - len(diff), len(chips), '' if not diff else ' ; DIFFERENT: %s' % diff))
print('1. region images built from the archive (as classic/scripts/m2_build.py does)')
def find(prefix):
    c = [n for n in chips if n.startswith(prefix)]; assert len(c) == 1, (prefix, c); return np.frombuffer(chips[c[0]], '<u2')
def load32(pairs, size):
    buf = np.zeros(size // 2, '<u2')
    for off, lo, hi in pairs: a = find(lo); b = find(hi); buf[off // 2: off // 2 + 2 * len(a): 2] = a; buf[off // 2 + 1: off // 2 + 1 + 2 * len(b): 2] = b
    return buf
img = dict(maincpu=load32([(0, 'epr-17888c', 'epr-17889c')], 0x200000), main_data=load32([(0, 'mpr-17746', 'mpr-17747'), (0x400000, 'mpr-17744', 'mpr-17745'), (0x800000, 'mpr-17884', 'mpr-17885')], 0xC00000),
           polygons=load32([(0, 'mpr-17748', 'mpr-17750'), (0x400000, 'mpr-17749', 'mpr-17751')], 0x800000), textures=load32([(0, 'mpr-17753', 'mpr-17752')], 0x400000))
ok1 = True
for n, a in img.items(): a.tofile(os.path.join(R, 'm2', n + '.bin')); ok1 &= same(os.path.join(R, 'm2', n + '.bin'), os.path.join(W, 'tmp', 'm2', n + '.bin'), n + '.bin')
print('2. the course exported from those images (classic_export.py, objects from the course settings)')
sys.path.insert(0, W + '/scripts'); os.chdir(W + '/scripts')
import course, classic_export
cfg = course.use('src', '1'); real_out = classic_export.OUT; classic_export.OUT = os.path.join(R, 'export'); classic_export.M2 = os.path.join(R, 'm2'); os.makedirs(classic_export.OUT, exist_ok=True)
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf): classic_export.export()
print('   ' + buf.getvalue().strip()[:200]); ok2 = True
for f in ('src_course1_hi.obj', 'src_course1_hi.mtl', 'materials.json'): ok2 &= same(os.path.join(R, 'export', f), os.path.join(real_out, f), f)
print('RESULT stages 0-2:', 'the importer\'s inputs are exactly what the ROM archive gives' if (ok1 and ok2 and not diff) else 'SOMETHING DIFFERS')
