"""patches.ps1's machine code and patch table -> blobs.h for patches.dll (python gen_blobs.py [out]).

patches.ps1 is the one source of the bytes for now (its hex is what tools\\build_patch.py and build_cycle.py made);
this copies them, so the DLL and the script can never disagree. Read: the $Patches table (VA, original bytes, new
bytes, what it is), $CycleCode and $CycleCode2 (the camera cycle block's two code areas)."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); PS = os.path.join(HERE, '..', '..', 'patches.ps1')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'blobs.h')
t = open(PS, encoding='utf-8-sig').read()
def hexvar(name):
    m = re.search(r"^\$%s = '([0-9a-f]+)'" % re.escape(name), t, re.M)
    if not m: raise SystemExit('patches.ps1: $%s not found' % name)
    return bytes.fromhex(m.group(1))
def carr(name, b):
    rows = [', '.join('0x%02x' % x for x in b[i:i + 24]) for i in range(0, len(b), 24)]
    return 'static const unsigned char %s[%d] = {\n    %s\n};\n' % (name, len(b), ',\n    '.join(rows))
pat = re.findall(r"@\{ VA = 0x([0-9A-Fa-f]+); Orig = '([0-9a-f]+)'; New = '([0-9a-f]+)'; Desc = '([^']*)'", t)
if len(pat) != 9: raise SystemExit('patches.ps1: %d entries in $Patches, 9 expected' % len(pat))
import hashlib
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
open(OUT, 'w', newline='\n').write('\n'.join(L))
print('blobs.h: %d patch sites, cycle code %d + %d bytes' % (len(pat), len(hexvar('CycleCode')), len(hexvar('CycleCode2'))))
