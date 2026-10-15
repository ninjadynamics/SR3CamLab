"""patches.ps1's machine code and patch tables -> blobs.h for patchcore (python gen_blobs.py [out]).

patches.ps1 is the one source of the bytes for now (its hex is what tools\\build_patch.py, build_cycle.py, build_trackdir.py,
build_carlist.py, build_cardhook.py, build_flavorhooks.py and build_srcport.py made); this copies them, and the address
tables the live loop walks, so the DLL / sr3mods.exe and the script can never disagree on them. Read:
  the cameras: the $Patches table (VA, original bytes, new bytes, what it is), $CycleCode and $CycleCode2;
  the live loop (pc_live.c): $TrackDirCode / $TrackDirHooks / $TrackDirSites, $TrackBannerSites, $MenuTimerSites,
  $TimerDraw*, $CarListCode / $CarListSites, $CardHookCode / $CardHookExit / $ExtraCards, $CarPathCode / $CarPathBytes /
  $CarPathOrder / $HandlingCarNames, $SteerBytes, $SrcPortCode / $SrcPortRelocs.
Single addresses (0x9D6E3C and the like) are written by hand in pc_live.c; tools\\patches\\live_lockstep.py runs both on
the same fake games and compares every write, so a wrong one shows there."""
import os, re, sys, hashlib
HERE = os.path.dirname(os.path.abspath(__file__)); PS = os.path.join(HERE, '..', '..', 'patches.ps1')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'blobs.h')
t = open(PS, encoding='utf-8-sig').read()
def one(rx, what):
    m = re.findall(rx, t, re.M)
    if len(m) != 1: raise SystemExit('patches.ps1: %s found %d times, once expected' % (what, len(m)))
    return m[0]
def hexvar(name): return bytes.fromhex(one(r"\$%s = '([0-9a-f]*)'" % re.escape(name), '$' + name))
def line(name): return one(r"^\$%s = (.*)$" % re.escape(name), '$' + name)
def carr(name, b):
    rows = [', '.join('0x%02x' % x for x in b[i:i + 24]) for i in range(0, len(b), 24)]
    return 'static const unsigned char %s[%d] = {\n    %s\n};\n' % (name, max(1, len(b)), ',\n    '.join(rows) if rows else '0')
def uarr(name, vals, ty='unsigned'):
    return 'static const %s %s[%d] = { %s };\n' % (ty, name, len(vals), ', '.join('0x%X' % v for v in vals))
def sarr(name, vals): return 'static const char *const %s[%d] = { %s };\n' % (name, len(vals), ', '.join('"%s"' % v for v in vals))

pat = re.findall(r"@\{ VA = 0x([0-9A-Fa-f]+); Orig = '([0-9a-f]+)'; New = '([0-9a-f]+)'; Desc = '([^']*)'", t)
if len(pat) != 9: raise SystemExit('patches.ps1: %d entries in $Patches, 9 expected' % len(pat))
SOURCE = hashlib.sha256(open(PS, 'rb').read()).hexdigest()           # the DLL carries it (patches_source): lockstep.py refuses a DLL built from another patches.ps1
L = ['/* Made by gen_blobs.py from patches.ps1: do not edit. */', '#pragma once', '#define PATCHES_SOURCE "%s"' % SOURCE, '']
for k, (va, orig, new, desc) in enumerate(pat):
    o, n = bytes.fromhex(orig), bytes.fromhex(new)
    if len(o) != len(n): raise SystemExit('patches.ps1: $Patches[%d] original and new differ in length' % k)
    L.append(carr('P%d_ORIG' % k, o)); L.append(carr('P%d_NEW' % k, n))
L.append('typedef struct { unsigned va; const unsigned char *orig, *neu; unsigned len; const char *what; } PatchSite;')
L.append('static const PatchSite PATCHES[%d] = {' % len(pat))
for k, (va, orig, new, desc) in enumerate(pat):
    L.append('    { 0x%s, P%d_ORIG, P%d_NEW, %d, "%s" },' % (va.upper(), k, k, len(bytes.fromhex(orig)), desc.replace('"', "'")))
L += ['};', '']
L.append(carr('CYCLE_CODE', hexvar('CycleCode'))); L.append(carr('CYCLE_CODE2', hexvar('CycleCode2')))

# ---- the live loop
L.append('#ifdef PC_LIVE_BLOBS')
L.append(carr('TRACKDIR_CODE', hexvar('TrackDirCode')))
hooks = re.findall(r"@\((0x[0-9A-Fa-f]+), '([0-9a-f]+)', (0x[0-9A-Fa-f]+)\)", line('TrackDirHooks'))
if len(hooks) != 3: raise SystemExit('patches.ps1: $TrackDirHooks has %d entries, 3 expected' % len(hooks))
for i, (s, b, e) in enumerate(hooks): L.append(carr('TRACKDIR_HOOK%d' % i, bytes.fromhex(b)))
L.append('static const struct { unsigned site; const unsigned char *bytes; unsigned len, entry; } TRACKDIR_HOOKS[3] = { %s };' %
         ', '.join('{ %s, TRACKDIR_HOOK%d, %d, %s }' % (s, i, len(b) // 2, e) for i, (s, b, e) in enumerate(hooks)))
for nm in ('TrackDirSites', 'TrackBannerSites'):
    v = [int(x, 16) for x in re.match(r"((?:0x[0-9A-Fa-f]+(?:, )?)+)", line(nm)).group(1).split(', ')]
    L.append(uarr(re.sub(r'(?<!^)([A-Z])', r'_\1', nm).upper(), v))
m = re.search(r"^\$MenuTimerSites = \[ordered\]@\{\n(.*?)^\}$", t, re.M | re.S)
if not m: raise SystemExit('patches.ps1: $MenuTimerSites block not found')
mt = [(int(a, 16), int(b)) for a, b in re.findall(r"(0x[0-9A-Fa-f]+) = (\d+)", re.sub(r'#.*', '', m.group(1)))]
L.append('static const struct { unsigned va; int ms; } MENU_TIMERS[%d] = { %s };' % (len(mt), ', '.join('{ 0x%X, %d }' % x for x in mt)))
L.append(carr('TIMER_DRAW_ORIG', hexvar('TimerDrawOrig'))); L.append(carr('TIMER_DRAW_NEW', hexvar('TimerDrawNew')))
L.append(carr('CARLIST_CODE', hexvar('CarListCode')))
cl = re.findall(r"@\((0x[0-9A-Fa-f]+), (\d+), '([0-9a-f]+)'\)", line('CarListSites'))
for i, (s, e, b) in enumerate(cl): L.append(carr('CARLIST_SITE%d' % i, bytes.fromhex(b)))
L.append('static const struct { unsigned site, entry; const unsigned char *bytes; } CARLIST_SITES[%d] = { %s };' %
         (len(cl), ', '.join('{ %s, %s, CARLIST_SITE%d }' % (s, e, i) for i, (s, e, b) in enumerate(cl))))
L.append(carr('CARDHOOK_CODE', hexvar('CardHookCode'))); L.append(carr('CARDHOOK_EXIT', hexvar('CardHookExit')))
ec = re.findall(r"@\('([A-Za-z0-9_]+)', (0x[0-9A-Fa-f]+), '([^']*)'\)", line('ExtraCards'))
L.append('static const struct { const char *name; unsigned cell; const char *file; } EXTRA_CARDS[%d] = { %s };' %
         (len(ec), ', '.join('{ "%s", %s, "%s" }' % x for x in ec)))
L.append(carr('CARPATH_CODE', hexvar('CarPathCode'))); L.append(carr('CARPATH_BYTES', hexvar('CarPathBytes'))); L.append(carr('STEER_BYTES', hexvar('SteerBytes')))
for nm in ('HandlingCarNames', 'CarPathOrder'):
    v = re.findall(r"'([^']*)'", re.sub(r'#.*', '', line(nm)))
    if len(v) != 10: raise SystemExit('patches.ps1: $%s has %d names, 10 expected' % (nm, len(v)))
    L.append(sarr(re.sub(r'(?<!^)([A-Z])', r'_\1', nm).upper(), v))
sp = hexvar('SrcPortCode'); rel = one(r"\$SrcPortRelocs = '([0-9a-f]*)'", '$SrcPortRelocs')
if len(rel) % 4: raise SystemExit('patches.ps1: $SrcPortRelocs is not 4-digit offsets')
L.append(carr('SRCPORT_CODE', sp)); L.append(uarr('SRCPORT_RELOCS', [int(rel[i:i + 4], 16) for i in range(0, len(rel), 4)], 'unsigned short'))
L.append('#endif')
open(OUT, 'w', newline='\n').write('\n'.join(L) + '\n')
print('blobs.h: %d patch sites, cycle code %d + %d bytes; live: %d menu timers, %d car-list sites, %d extra cards, src port %d bytes / %d relocations'
      % (len(pat), len(hexvar('CycleCode')), len(hexvar('CycleCode2')), len(mt), len(cl), len(ec), len(sp), len(rel) // 4))
