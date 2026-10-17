"""Which code reads field +OFF of the object held in global G?   python rootuse.py 9db48c c [window]
Looks for 'mov reg, [G]' followed within a few lines by '[reg + OFF]' (before reg is overwritten)."""
import os, sys, re
from common import *
def uses(G, off, win=12):
    L = open(os.path.join(TMP, 'rally.asm')).read().split('\n'); out = []
    pat = re.compile(r'mov\s+(e\w\w), dword ptr \[0x%x\]' % G)
    for i, l in enumerate(L):
        m = pat.search(l)
        if not m: continue
        r = m.group(1); tgt = '[%s + 0x%x]' % (r, off) if off else '[%s]' % r
        for k in range(i + 1, min(len(L), i + 1 + win)):
            if tgt in L[k]: out.append((L[i][:8], L[k].strip()[:90])); break
            if re.search(r'^\w{8}\s+(mov|lea|pop|xor|movzx)\s+%s,' % r, L[k]) or ' call ' in L[k] or ' ret' in L[k][8:16]: break
    return out
if __name__ == '__main__':
    for a, b in uses(int(sys.argv[1], 16), int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 12): print(a, '->', b)
