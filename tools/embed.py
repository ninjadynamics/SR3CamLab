"""Copies the camera-cycle block built by build_cycle.py (cycle.json) into ../patch.ps1:
its code ($CycleCode) and entry offsets ($CycleSize, $CycleDraw, $CycleLost, $CycleRot,
$CycleFree), and its second code area ($CycleCode2, $CycleCode2At, $CycleBlend). Run
build_cycle.py first; test with cycle_emu.py and cycle_mocktest.ps1 after."""
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
text, n3 = re.subn(r"\$CycleCode2 = '[0-9a-f]+'", lambda m: "$CycleCode2 = '%s'" % cyc['code2'], text)
text, n4 = re.subn(r"\$CycleCode2At = 0x[0-9a-f]+; \$CycleBlend = 0x[0-9a-f]+",
                   "$CycleCode2At = %s; $CycleBlend = %s" % (hex(cyc['code2Off']), hex(cyc['blendOff'])), text)
text, n5 = re.subn(r"\$CycleQol = 0x[0-9a-f]+", "$CycleQol = %s" % hex(cyc['data']['K_LOOKTAU']), text)
if n1 != 1 or n2 != 1:
    sys.exit('patch.ps1: could not find the $CycleCode / $CycleSize lines')
if n3 != 1 or n4 != 1 or n5 != 1:
    sys.exit('patch.ps1: could not find the $CycleCode2 / $CycleCode2At / $CycleQol lines')
d = cyc['data']                              # patch.ps1 writes the three settings as one run of floats
assert d['K_MOVETAU'] == d['K_LOOKTAU'] + 4 and d['K_BLEND'] == d['K_LOOKTAU'] + 8
with open(path, 'wb') as f:
    f.write(text.encode('utf-8'))
print('patch.ps1 updated: %d code bytes, draw %#x lost %#x rot %#x free %#x; second area %d bytes at %#x, blend %#x'
      % (len(cyc['code']) // 2, cyc['drawOff'], cyc['lostOff'], cyc['rotOff'], cyc['freeOff'],
         len(cyc['code2']) // 2, cyc['code2Off'], cyc['blendOff']))
