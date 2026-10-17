"""Find alpha-tested scenery materials and what distinguishes them from opaque ones.
    python matscan.py [Track]   (default Alpine4)
A material (kind 2) of the 'Uber' family: word 0 = shader ref, then 16-byte parameter records {ptr name, ...}; parameter
names are strings at the end (gbUberATEST, gbUberABLEND, gbUberDSIDE, ...). This prints, for materials whose diffuse
texture (+0x1BC) has transparent texels, the value words of the boolean parameters next to an opaque material's."""
import os, sys, struct, collections, json
import numpy as np
from common import *
import sbfw

def cstr(d, o):
    e = d.index(b'\0', o); return d[o:e].decode('latin1')

def params(c):
    """{name: (record offset, 3 value words)} for every fixup that points at a parameter name string"""
    d = c.data; out = collections.OrderedDict()
    for o in sorted(c.fix):
        v = c.u32(o)
        if v < len(d) and 0x20 < d[v] < 0x7f:
            try: nm = cstr(d, v)
            except ValueError: continue
            if nm.startswith('g') or nm.startswith('tex') or nm.startswith('_'):
                out[nm] = (o, struct.unpack_from('<3I', d, o + 4) if o + 16 <= len(d) else ())
    return out

def tex_alpha(c):
    """fraction of transparent texels on the top mip (DXT1 punch-through or DXT5 alpha < 128)"""
    d = c.data; w, h = struct.unpack_from('<II', d, 8); four = d[48 + 80:48 + 84]; base = 48 + 124; n = max(1, w // 4) * max(1, h // 4)
    if four == b'DXT1':
        b = np.frombuffer(d, np.dtype([('c0', '<u2'), ('c1', '<u2'), ('ix', '<u4')]), n, base)
        three = b['c0'] <= b['c1']; ix = (b['ix'][:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
        return float(((ix == 3) & three[:, None]).mean()), 'DXT1'
    if four == b'DXT5':
        b = np.frombuffer(d, np.uint8, 16 * n, base).reshape(n, 16); return float(((b[:, 0] < 128) & (b[:, 1] < 128)).mean()), 'DXT5'
    return 0.0, four.decode('latin1')

def main(track='Alpine4'):
    f = sbfw.read_sbf(track_files(os.path.join(TRACKS, track))['master_gfx_xdata']); by = f.byid()
    use = collections.Counter()
    for c in f.kinds(1):
        h = struct.unpack_from('<18I', c.data, 0)
        if h[11] % 0x48: continue
        for l in range(h[11] // 0x48):
            hh = struct.unpack_from('<18I', c.data, 0x48 * l)
            for k in range(hh[8]):
                g = struct.unpack_from('<5I', c.data, hh[11] + 20 * k); use[g[4]] += g[1]
    rows = []
    for mid, n in use.most_common():
        m = by.get(mid)
        if m is None or m.kind != 2 or len(m.data) < 0x1c0 or 0x1bc not in m.ref: continue
        t = by.get(m.u32(0x1bc))
        if t is None or t.kind != 4: continue
        a, fm = tex_alpha(t); rows.append((mid, n, len(m.data), m.u32(0), a, fm, t.id))
    alpha = [r for r in rows if r[4] > 0.05]; opaque = [r for r in rows if r[4] == 0 and r[2] == 1848]
    print(track, 'materials with diffuse at +0x1BC:', len(rows), 'with transparent texels:', len(alpha), 'sizes', collections.Counter(r[2] for r in alpha), 'shaders', collections.Counter('%08x' % r[3] for r in alpha))
    print('opaque size-1848 shaders', collections.Counter('%08x' % r[3] for r in opaque).most_common(4))
    if not alpha or not opaque: return
    don = next((r for r in alpha if r[2] == 1848), alpha[0]); ref = opaque[0]
    pd = params(by[don[0]]); pr = params(by[ref[0]])
    print('donor %08x (verts %d, size %d, shader %08x, tex %08x %s, transparent %.2f)  vs opaque %08x (shader %08x)' % (don[0], don[1], don[2], don[3], don[6], don[5], don[4], ref[0], ref[3]))
    for nm in pd:
        if nm in pr and pd[nm][1] != pr[nm][1]: print('   %-28s donor %s   opaque %s' % (nm, ['%08x' % x for x in pd[nm][1]], ['%08x' % x for x in pr[nm][1]]))
    # all alpha materials: values of the boolean switches
    sw = ('gbUberATEST', 'gbUberABLEND', 'gbUberABLENDAdd', 'gbUberDSIDE', 'gbUberTWOS')
    cnt = collections.Counter()
    for r in alpha:
        p = params(by[r[0]]); cnt[tuple((p[s][1][1] if s in p else None) for s in sw)] += 1
    print('alpha materials: second value word of', sw, '->', cnt.most_common(6))
    cnt = collections.Counter()
    for r in opaque[:200]:
        p = params(by[r[0]]); cnt[tuple((p[s][1][1] if s in p else None) for s in sw)] += 1
    print('opaque materials:', cnt.most_common(4))
    json.dump(dict(track=track, donor='%08x' % don[0], donor_tex='%08x' % don[6], fmt=don[5], size=don[2]), open(os.path.join(TMP, 'alpha_donor.json'), 'w'))
    # byte-level difference outside pointers/refs for same-size pair
    if don[2] == ref[2]:
        a, b = by[don[0]], by[ref[0]]; skip = set(a.fix) | set(a.ref)
        df = [o for o in range(0, len(a.data) - 3, 4) if o not in skip and a.data[o:o + 4] != b.data[o:o + 4]]
        print('differing non-pointer words (offset: donor / opaque):', [(hex(o), a.data[o:o + 4].hex(), b.data[o:o + 4].hex()) for o in df][:24])

if __name__ == '__main__':
    main(*sys.argv[1:2])
