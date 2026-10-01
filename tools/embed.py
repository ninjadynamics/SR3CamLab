"""Copies the camera-cycle block built by build_cycle.py (cycle.json) into ../patch.ps1:
its code ($CycleCode) and entry offsets ($CycleSize, $CycleDraw, $CycleLost, $CycleRot,
$CycleFree). Run build_cycle.py first; test with cycle_emu.py and cycle_mocktest.ps1 after."""
import json, os, re, sys

here = os.path.dirname(os.path.abspath(__file__))
cyc = json.load(open(os.path.join(here, 'cycle.json')))
path = os.path.join(here, '..', 'patch.ps1')
with open(path, 'rb') as f:
    text = f.read().decode('utf-8')
text, n1 = re.subn(r"\$CycleCode = '[0-9a-f]+'", lambda m: "$CycleCode = '%s'" % cyc['code'], text)
text, n2 = re.subn(r"\$CycleSize = 0x[0-9a-f]+; \$CycleDraw = 0x[0-9a-f]+; \$CycleLost = 0x[0-9a-f]+; "
                   r"\$CycleRot = 0x[0-9a-f]+; \$CycleFree = 0x[0-9a-f]+",
                   "$CycleSize = %s; $CycleDraw = %s; $CycleLost = %s; $CycleRot = %s; $CycleFree = %s"
                   % (hex(cyc['size']), hex(cyc['drawOff']), hex(cyc['lostOff']), hex(cyc['rotOff']), hex(cyc['freeOff'])), text)
if n1 != 1 or n2 != 1:
    sys.exit('patch.ps1: could not find the $CycleCode / $CycleSize lines')
with open(path, 'wb') as f:
    f.write(text.encode('utf-8'))
print('patch.ps1 updated: %d code bytes, draw %#x lost %#x rot %#x free %#x'
      % (len(cyc['code']) // 2, cyc['drawOff'], cyc['lostOff'], cyc['rotOff'], cyc['freeOff']))
