"""Print functions from ../tmp/rally.asm (made by gen_asm.py):  python asmfn.py 5fb180 5f30a0 ...   [-n maxlines]
A function is printed from its address to the first ret that is followed by int3 padding or another function start."""
import os, sys, bisect
from common import *
_L = None
def lines():
    global _L
    if _L is None:
        L = open(os.path.join(TMP, 'rally.asm')).read().split('\n'); _L = (L, [int(l[:8], 16) if l[:8].strip() else 0 for l in L])
    return _L
def fn(a, maxlines=400):
    L, A = lines(); i = bisect.bisect_left(A, a); out = []
    for k in range(i, min(len(L), i + maxlines)):
        out.append(L[k][:100].rstrip())
        if ' ret' in L[k][8:18] and k + 1 < len(L) and ('int3' in L[k + 1] or 'nop' in L[k + 1]): break
    return out
if __name__ == '__main__':
    n = 400; args = sys.argv[1:]
    if '-n' in args: n = int(args[args.index('-n') + 1]); del args[args.index('-n'):args.index('-n') + 2]
    for a in args: print('----', a); print('\n'.join(fn(int(a, 16), n)))
