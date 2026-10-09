"""TrackDeform chunk (master_gfx root +0x0C) parser. See ../../04_trackdeform.md"""
import struct, zlib, collections
import numpy as np
from common import *
import sbfw

VDT = np.dtype([('pos', '<f4', 3), ('w0c', '<u4'), ('w10', '<u4'), ('b14', 'u1', 4), ('surf', 'u1', 4), ('w1c', '<u4'),
                ('w20', '<u4'), ('w24', '<u4'), ('w28', '<u4'), ('w2c', '<u4')])
assert VDT.itemsize == 0x30

class TD: pass
def parse_td(c, byid=None):
    d = c.data; t = TD(); t.c = c
    (t.ver, t.w04, t.n, t.nsurf, t.w10, t.zsize, t.blob_id, t.p_slices, t.p_tex, t.p_rec11, t.p_hash, t.p_pages) = struct.unpack_from('<12I', d, 0)
    n = t.n; S = t.p_slices
    t.A = np.array([d[S + 0x88 * i + 0x6c] for i in range(n + 2)], np.int32)
    t.off = np.array([struct.unpack_from('b', d, S + 0x88 * i + 0x6d)[0] for i in range(n + 2)], np.int32)
    t.b6e = np.array([struct.unpack_from('b', d, S + 0x88 * i + 0x6e)[0] for i in range(n + 2)], np.int32)
    t.b6f = np.array([d[S + 0x88 * i + 0x6f] for i in range(n + 2)], np.int32)
    t.B = np.array([d[S + 0x88 * i + 0x75] for i in range(n + 2)], np.int32)
    t.ptr = np.array([c.u32(S + 0x88 * i + 0x78) for i in range(n + 2)], np.int64)
    t.tail = [struct.unpack_from('<fII', d, S + 0x88 * i + 0x7c) for i in range(n + 2)]
    t.slice_raw = [d[S + 0x88 * i:S + 0x88 * (i + 1)] for i in range(n + 2)]
    t.hdr = []; t.verts = []
    for i in range(n + 2):
        p = int(t.ptr[i]); t.hdr.append(d[p:p + 0x30])
        t.verts.append(np.frombuffer(d, VDT, int(t.B[i]), p + 0x30))
    t.rec11 = [d[t.p_rec11 + 11 * i:t.p_rec11 + 11 * i + 11] for i in range((n + 3) // 4)]
    t.hashes = list(struct.unpack_from('<%dI' % t.nsurf, d, t.p_hash))
    t.texids = list(struct.unpack_from('<%dI' % t.nsurf, d, t.p_tex))
    npages = max(r[10] for r in t.rec11) + 1
    t.pages = [struct.unpack_from('<II4f', d, t.p_pages + 0x18 * i) for i in range(npages)]
    return t

def columns(t, i):
    """lateral column number of every vertex record of slice i (1..n): records start at min(off, previous slice's off)"""
    return int(t.off[i]) - max(int(t.b6e[i]), 0) + np.arange(int(t.B[i]))

def road_frame(t):
    """-> (centre points n x 3 (column 0), lateral unit vectors n x 3, left edge (negative), right edge) read from a parsed TD"""
    n = t.n; cen = np.zeros((n, 3)); lat = np.zeros((n, 3)); lo = np.zeros(n); hi = np.zeros(n)
    for i in range(1, n + 1):
        v = t.verts[i]['pos'].astype(float); c = columns(t, i); cen[i - 1] = v[list(c).index(0)]
        d = v[-1] - v[0]; d[1] = 0; d /= np.linalg.norm(d); lat[i - 1] = d; lo[i - 1] = (v[0] - cen[i - 1]) @ d; hi[i - 1] = (v[-1] - cen[i - 1]) @ d
    return cen, lat, lo, hi

def load_td(track):
    f = sbfw.read_sbf(track_files(os.path.join(TRACKS, track))['master_gfx_xdata'])
    by = f.byid(); r = f.chunks[-1]
    return parse_td(by[r.u32(0xc)]), f, by

if __name__ == '__main__':
    import sys
    for tr in sys.argv[1:] or ['Stadium4']:
        t, f, by = load_td(tr)
        n = t.n
        print(tr, 'n', n, 'nsurf', t.nsurf, 'w04', t.w04, 'w10', t.w10)
        V = np.concatenate(t.verts[1:n + 1])
        for fld in ('w0c', 'w10', 'w1c', 'w20', 'w24', 'w28', 'w2c'):
            cnt = collections.Counter(V[fld].tolist()); print('  ', fld, len(cnt), [('%08x' % k, v) for k, v in cnt.most_common(8)])
        for fld in ('b14', 'surf'):
            for k in range(4):
                cnt = collections.Counter(V[fld][:, k].tolist()); print('  ', fld, k, len(cnt), cnt.most_common(8))
        print('   hdr bytes distinct:', collections.Counter(h.hex() for h in t.hdr).most_common(3))
        print('   b6e', collections.Counter(t.b6e.tolist()), 'b6f', collections.Counter(t.b6f.tolist()), 'tail', collections.Counter(t.tail).most_common(3))
        print('   off', collections.Counter(t.off.tolist()).most_common(6), 'A', collections.Counter(t.A.tolist()).most_common(6))
        print('   rec11', collections.Counter(r.hex() for r in t.rec11).most_common(6))
        print('   hashes', ['%08x' % h for h in t.hashes], 'tex', ['%08x' % h for h in t.texids])
        # geometry: spacing across, along
        for i in (1, 2, 100):
            v = t.verts[i]['pos']; dd = np.linalg.norm(np.diff(v, axis=0), axis=1)
            print('   slice', i, 'A', t.A[i], 'off', t.off[i], 'B', t.B[i], 'across spacing', dd.round(3).tolist()[:30])
            print('      first', v[0], 'last', v[-1])
        cen = np.array([t.verts[i]['pos'][min(-t.off[i], t.B[i] - 1)] for i in range(1, n + 1)])
        st = np.linalg.norm(np.diff(cen, axis=0), axis=1)
        print('   centre col: step min/med/max', st.min(), np.median(st), st.max(), 'total', st.sum(), 'closing gap', np.linalg.norm(cen[0] - cen[-1]))

# ------------------------------------------------------------------ builder
def pad16(b):
    return b + b'\0' * (-len(b) % 16)

def build_td(m, blob_id, blob_zsize):
    """m: dict with keys
         slices: list (index 1..n) of dict(A, off, b6e, b6f, B, water, verts=np.array(VDT, B))   [index 0 unused]
         rec11 : list of 11-byte records ((n+3)//4 + 1)
         texids, hashes: lists of nsurf u32 ; pages: list of (texA, texB, u0, v0, su, sv) ; w10 (2)
       returns (data, fix, ref)"""
    sl = m['slices']; n = len(sl) - 1; nsurf = len(m['hashes'])
    assert len(m['rec11']) == (n + 3) // 4 + 1 and len(m['texids']) == nsurf
    order = [n] + list(range(1, n + 1)) + [1]                     # slice 0 = slice n, slice n+1 = slice 1
    p_slices = 0x30
    p_rec = p_slices + 0x88 * (n + 2)
    rec = pad16_at(b''.join(m['rec11']) + bytes(1), p_rec)
    p_tex = p_rec + len(rec)
    tex = pad16(struct.pack('<%dI' % nsurf, *m['texids']) + bytes(4)); p_hash = p_tex + len(tex)
    hsh = pad16(struct.pack('<%dI' % nsurf, *m['hashes']) + bytes(4)); p_blocks = p_hash + len(hsh)
    blocks = bytearray(); ptr = {}
    def block(s):
        A, B = s['A'], s['B']; v = s['verts']; assert len(v) == B and B >= A + 1
        h = bytearray(0x30); struct.pack_into('<H', h, 0, A); struct.pack_into('bBbB', h, 0x10, s['off'], 0xff, s.get('b6e', 0), 1 if s.get('b6e', 0) else 0)
        return bytes(h) + v.tobytes() + b'\0' * ((A + 1) * 0x100)
    for i in range(1, n + 1):
        ptr[i] = p_blocks + len(blocks); blocks += block(sl[i])
    ptr_dup = p_blocks + len(blocks); blocks += block(sl[1])
    p_pages = p_blocks + len(blocks)
    pages = b''.join(struct.pack('<II4f', *p) for p in m['pages'])
    out = bytearray(struct.pack('<12I', 5, max(s['A'] for s in sl[1:]), n, nsurf, m.get('w10', 2), blob_zsize, blob_id, p_slices, p_tex, p_rec, p_hash, p_pages))
    fix = [0x1c, 0x20, 0x24, 0x28, 0x2c]; ref = [0x18]
    for j, i in enumerate(order):
        s = sl[i]; rec88 = bytearray(0x88)
        struct.pack_into('<BbbB', rec88, 0x6c, s['A'], s['off'], s.get('b6e', 0), s.get('b6f', 0))
        rec88[0x70:0x78] = s.get('raw70', bytes(5) + bytes([s['B'], 0, 0]))
        rec88[0x75] = s['B']
        p = ptr_dup if j == n + 1 else ptr[i]
        struct.pack_into('<IfII', rec88, 0x78, p, s.get('water', -99999.0), s.get('w80', 1), s.get('w84', 2))
        fix.append(p_slices + 0x88 * j + 0x78); out += rec88
    out += rec + tex + hsh + blocks + pages
    ref += [p_tex + 4 * i for i in range(nsurf)] + [p_pages + 0x18 * i + k for i in range(len(m['pages'])) for k in (0, 4)]
    return bytes(out), fix, ref

def pad16_at(b, at):
    return b + b'\0' * (-(at + len(b)) % 16)

def td_to_model(t):
    """parsed TD -> model accepted by build_td (lossless for SEGA's files)"""
    d = t.c.data; n = t.n; sl = [None]
    for i in range(1, n + 1):
        raw = t.slice_raw[i]
        sl.append(dict(A=int(t.A[i]), off=int(t.off[i]), b6e=int(t.b6e[i]), b6f=int(t.b6f[i]), B=int(t.B[i]), raw70=raw[0x70:0x78],
                       water=t.tail[i][0], w80=t.tail[i][1], w84=t.tail[i][2], verts=t.verts[i].copy()))
    nrec = (n + 3) // 4 + 1
    rec = [d[t.p_rec11 + 11 * i:t.p_rec11 + 11 * i + 11] for i in range(nrec)]
    return dict(slices=sl, rec11=rec, texids=t.texids, hashes=t.hashes, pages=t.pages, w10=t.w10)

def blob_size(m):
    return sum(s['A'] for s in m['slices'][1:]) * 256
