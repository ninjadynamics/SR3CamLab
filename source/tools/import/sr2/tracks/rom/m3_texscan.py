"""Scan SEGA Rally 2 ROM regions for texture upload records in texture-FIFO form: {length, header, texel data}."""
import numpy as np, sys, pickle
O = '../../out/m3/'
def nwords(H):
    typ = H >> 24; W = 32 << ((H >> 14) & 7); Ht = 32 << ((H >> 17) & 7); s16 = (H >> 23) & 1
    if typ not in (0, 1, 2): return None
    tex = 0; w, h = W, Ht
    if typ in (0, 1): tex += w * h
    if typ in (0, 2):
        while w >= 4 and h >= 4:
            w //= 2; h //= 2; tex += w * h
    b = tex * (2 if s16 else 1)
    return 2 + (b + 3) // 4
def scan(name, dtype):
    w = np.fromfile(O + name, dtype); n = len(w); out = []; i = 0
    L = w[:-1].astype(np.int64); H = w[1:].astype(np.int64)
    cand = np.nonzero((L > 0x100) & (L < 0x1000000) & ((H >> 26) == 0) & ((L & 3) == 0))[0]
    chain = []
    for i in cand:
        nw = nwords(int(H[i]))
        if nw is None: continue
        if (2 + int(L[i]) // 2) // 4 == nw: chain.append((int(i), int(L[i]), int(H[i]), nw))
    return w, chain
if __name__ == '__main__':
    res = {}
    for name, dt in (('crom.bin', '>u4'), ('banked_crom.bin', '>u4'), ('vrom_le.bin', '<u4')):
        w, ch = scan(name, dt); idx = {c[0] for c in ch}
        linked = sum(1 for c in ch if (c[0] + c[3]) in idx)
        print(name, 'records', len(ch), 'followed directly by another record', linked)
        for c in ch[:6]: print('   word %07x len %x header %08x words %d' % c)
        res[name] = ch
    pickle.dump(res, open('../tmp/m3/texrecords.pkl', 'wb'))
