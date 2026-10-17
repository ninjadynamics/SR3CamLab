"""List callers of the sound request function 0x1788 (r3 = request index) with how r3 was set."""
import sys, os, struct, pickle, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2common import *
xr, calls = pickle.load(open(W + "xref.pkl", "rb"))
L = {}
for ln in open(W + "sr2.lst"):
    if len(ln) > 7 and ln[6] == ':': L[int(ln[:6], 16)] = ln.rstrip()
for f in (0x1788, 0x1824):
    for pc in calls[f]:
        q = pc - 4; src = '?'
        while q > pc - 80:
            s = L[q]
            m = re.search(r'\s(\S+)\s+r3,(\S+)', s[16:])
            if m: src = s[26:].strip(); break
            if ' bl ' in s or ' blr' in s: break
            q -= 4
        m = re.match(r'li\s+r3,(\d+)', src)
        nm = REQ[int(m.group(1))] if m and int(m.group(1)) < len(REQ) else ''
        print('%06X -> %04X : %-40s %s' % (pc, f, src, nm))
