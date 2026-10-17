"""xref tool.  python -I xref.py refs ADDR [ADDR2(range end)]   -> all code referencing address (or range)
                python -I xref.py idx VARADDR [window]      -> tables indexed shortly after a load of VARADDR
                python -I xref.py callers FUNC
                python -I xref.py func ADDR                 -> print the function containing ADDR"""
import sys, pickle, re, bisect
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
B = _TMP + r"/sr2_gameplay/work/"
xr, calls = pickle.load(open(B + "xref.pkl", "rb"))
L = None
def lines():
    global L
    if L is None:
        L = {}
        for ln in open(B + "sr2.lst"):
            if len(ln) > 7 and ln[6] == ':': L[int(ln[:6], 16)] = ln.rstrip()
    return L
def funcstart(a):
    Ls = lines()
    while a > 0 and not (Ls.get(a, '').find('stwu     r1,-') > 0 or Ls.get(a - 4, '').find(' blr') > 0): a -= 4
    return a
def funcend(a):
    Ls = lines()
    while a in Ls and Ls[a].find(' blr ') < 0: a += 4
    return a
cmd = sys.argv[1]
if cmd == 'refs':
    a = int(sys.argv[2], 16); b = int(sys.argv[3], 16) if len(sys.argv) > 3 else a
    for k in sorted(xr):
        if a <= k <= b:
            for pc, rw, m in xr[k]: print('%08X  %s at %06X (func %06X) %s' % (k, rw, pc, funcstart(pc), m))
elif cmd == 'idx':
    v = int(sys.argv[2], 16); win = int(sys.argv[3]) if len(sys.argv) > 3 else 24; Ls = lines(); seen = {}
    for pc, rw, m in xr.get(v, []):
        if rw != 'r': continue
        for q in range(pc, pc + 4 * win, 4):
            s = Ls.get(q, '')
            if ' blr' in s: break
            mm = re.search(r'; (tbl|=|\[)([0-9A-F]{8})', s)
            if mm and q != pc:
                t = int(mm.group(2), 16)
                if 0x8D000 <= t < 0x800000 or mm.group(1) == 'tbl': seen.setdefault(t, []).append((pc, q, mm.group(1)))
    for t in sorted(seen): print('%08X  %s' % (t, ' '.join('%06X>%06X%s' % (p, q, 'T' if k == 'tbl' else '') for p, q, k in seen[t][:8])))
elif cmd == 'callers':
    f = int(sys.argv[2], 16)
    for pc in calls.get(f, []): print('%06X (func %06X)' % (pc, funcstart(pc)))
elif cmd == 'func':
    a = int(sys.argv[2], 16); s = funcstart(a); e = funcend(a); Ls = lines()
    for q in range(s, e + 4, 4): print(Ls[q])
