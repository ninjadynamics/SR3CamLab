"""Builds the ladder of SEGA Rally 3 test tracks in ..\\out (see ..\\out\\README.txt, written by this script).

    python build_testtrack.py            # everything
    python build_testtrack.py step5      # only the folders whose name starts with the given text

Nothing is read from or written to the game folder except READING the original Stadium4 / Desert4 files
(the user's own copy) as the source of the borrowed chunks.
"""
import os, sys, struct, zlib, math, shutil, collections
import numpy as np
from common import *
import sbfw, grid as G, trackdeform as TDm, scene11

SUFFIXES = ('master_gfx_xdata', 'master_xdata', 'game_objects_gfx_data', 'gameobj_gfx_dis_data', 'pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata')
SLOTS = {'Stadium4': ('stadium4', 'sta_track_route4', 'Sta_track_route4'), 'Desert4': ('desert4', 'des_track_route4', 'des_track_route4')}
LOG = []
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.append(s)

# ---------------------------------------------------------------- source + output helpers
class Track:
    """the six sbf files of a slot, parsed"""
    def __init__(self, slot):
        self.slot = slot; self.folder = os.path.join(TRACKS, slot); self.paths = track_files(self.folder)
        self.files = {s: sbfw.read_sbf(self.paths[s]) for s in SUFFIXES if s in self.paths}
    def copy(self):
        t = Track.__new__(Track); t.slot = self.slot; t.folder = self.folder; t.paths = self.paths; t.files = {}
        for s, f in self.files.items():
            g = sbfw.SbfFile(); g.hdr = f.hdr; g.first = f.first; g.tail = f.tail; g.compressed = f.compressed
            g.chunks = [c.copy() for c in f.chunks]; t.files[s] = g
        return t

def file_name(slot, suffix):
    env, route, proc = SLOTS[slot]
    return ('%s_%s.sbf' % (env, suffix)) if suffix in ('master_gfx_xdata', 'master_xdata') else ('%s_%s.sbf' % (route, suffix))

def write_track(name, trk, layout='auto', omit=(), note=''):
    """writes a full folder, then re-reads and validates every file"""
    out = os.path.join(OUT, name, trk.slot); os.makedirs(out, exist_ok=True)
    for old in os.listdir(out): os.remove(os.path.join(out, old))
    allids = set()
    for s, f in trk.files.items(): allids |= {c.id for c in f.chunks}
    nprob = 0
    for s, f in trk.files.items():
        if s in omit: continue
        import reforder; reforder.topo(f)                               # loader rule: no forward references (reforder.py)
        b = sbfw.write_sbf(f, compress=True, layout=layout, level=6)
        p = os.path.join(out, file_name(trk.slot, s)); open(p, 'wb').write(b)
        g = sbfw.read_sbf(p)                                           # read back with the independent reader
        assert len(g.chunks) == len(f.chunks) and all(a.data == c.data and a.fix == c.fix and a.ref == c.ref and a.z == c.z for a, c in zip(g.chunks, f.chunks))
        probs = [q for q in sbfw.validate(g, quiet=True, extern_ids=allids) if 'ffffffff' not in q]   # FFFFFFFF = null marker in kind 11
        nprob += len(probs)
        for q in probs[:5]: log('   PROBLEM', name, s, q)
    if 'proc' not in omit and 'proc' in trk.paths:
        shutil.copyfile(trk.paths['proc'], os.path.join(out, SLOTS[trk.slot][2] + '_proc_cached.bin'))
        for fn in os.listdir(trk.folder):                                 # files the reader does not parse (Desert4: ..._procobj_plac_gfx_xdata.sbf) travel with the props
            if 'procobj' in fn.lower(): shutil.copyfile(os.path.join(trk.folder, fn), os.path.join(out, fn))
    log('%-34s written: %d files, %d consistency problems %s' % (name + '/' + trk.slot, len(os.listdir(out)), nprob, note))
    return out

# ---------------------------------------------------------------- textures
def tex_fill(c, rgb, alpha=255, checker=None):
    """same header, new pixels: every 4x4 block one colour (DXT1 or DXT5). checker=(rgb2, squares_px) on the top mip."""
    d = bytearray(c.data); base = 48 + 124
    h, w, mips = struct.unpack_from('<I', d, 48 + 8)[0], struct.unpack_from('<I', d, 48 + 12)[0], struct.unpack_from('<I', d, 48 + 24)[0]
    fourcc = bytes(d[48 + 80:48 + 84]); bs = 8 if fourcc == b'DXT1' else 16
    def c565(r, g, b): return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    def blocks(n, col):
        v = c565(*col); col8 = struct.pack('<HHI', v, v, 0)
        one = col8 if bs == 8 else bytes([alpha, alpha, 0, 0, 0, 0, 0, 0]) + col8
        return one * n
    p = base
    for m in range(max(mips, 1)):
        bw, bh = max(1, (w >> m) // 4), max(1, (h >> m) // 4); n = bw * bh
        if p + n * bs > len(d): break
        if m == 0 and checker:
            rgb2, sq = checker; a = blocks(1, rgb); b2 = blocks(1, rgb2); rows = []
            for by in range(bh):
                rows.append(b''.join((a if ((bx * 4 // sq) + (by * 4 // sq)) % 2 == 0 else b2) for bx in range(bw)))
            d[p:p + n * bs] = b''.join(rows)
        else:
            mix = rgb if not checker else tuple((x + y) // 2 for x, y in zip(rgb, checker[0]))
            d[p:p + n * bs] = blocks(n, mix)
        p += n * bs
    assert len(d) == len(c.data)
    return bytes(d)

# ---------------------------------------------------------------- geometry of the authored loop
def oval(n=1000, radius=60.0, centre=(0.0, 0.0, 450.0)):
    """closed centre line with exactly n points 1 m apart: two straights joined by half circles. Returns (pos[n,3], dir[n,3]).
    Travel direction = increasing index. Point 0 is the middle of the +z straight heading +x."""
    L = (n - 2 * math.pi * radius) / 2.0; assert L > 0
    P = []; D = []
    for i in range(n):
        s = (i + L / 2.0) % n
        if s < L: x, z, a = -L / 2 + s, radius, 0.0
        elif s < L + math.pi * radius:
            t = (s - L) / radius; x, z, a = L / 2 + radius * math.sin(t), radius * math.cos(t), -t
        elif s < 2 * L + math.pi * radius:
            u = s - L - math.pi * radius; x, z, a = L / 2 - u, -radius, math.pi
        else:
            t = (s - 2 * L - math.pi * radius) / radius; x, z, a = -L / 2 - radius * math.sin(t), -radius * math.cos(t), math.pi - t
        P.append((centre[0] + x, centre[1], centre[2] + z)); D.append((math.cos(a), 0.0, math.sin(a)))
    return np.array(P), np.array(D)

def lateral(D):
    """unit vector of increasing column number: (d x lat).y > 0 on all 6 SEGA tracks, i.e. lat = (d.z, 0, -d.x)"""
    return np.stack([D[:, 2], np.zeros(len(D)), -D[:, 0]], 1)

def uniform_pattern(t):
    """the most common fully-uniform cell of an existing TrackDeform (surf bytes, hash word, weight word) and the rec11
    of slices that use it: the authored road repeats exactly this."""
    cnt = collections.Counter(); n = t.n
    for i in range(2, n - 1):
        if not (t.rec11[(i - 1) // 4] == t.rec11[i // 4] == t.rec11[min((i + 1) // 4, len(t.rec11) - 1)]): continue
        v = t.verts[i][:-1]
        same = (v['w20'] == v['w24']) & (v['w20'] == v['w28']) & (v['w20'] == v['w2c'])
        for x in v[same]:
            cnt[(bytes(t.rec11[i // 4][:10]), bytes(x['b14']), bytes(x['surf']), int(x['w1c']), int(x['w20']))] += 1
    (rec, b14, surf, w1c, w), k = cnt.most_common(1)[0]
    return dict(rec=rec, b14=b14, surf=surf, w1c=w1c, w=w, count=k)

def td_model_flat(P, D, half_width, pat, hashes, texids, page, water=-99999.0, lat=None):
    """uniform road: every slice has A = 2*half_width quads, columns -half_width..+half_width, 1 m apart.
    lat: optional per-slice lateral unit vectors (banking); default = horizontal normal of D."""
    n = len(P); A = 2 * half_width; B = A + 1; sl = [None]
    if lat is None: lat = lateral(D)
    for i in range(n):
        v = np.zeros(B, TDm.VDT)
        for k in range(B):
            v[k]['pos'] = P[i] + lat[i] * (k - half_width)
        v['w10'] = 0xffffffff; v['surf'] = np.frombuffer(pat['surf'], np.uint8); v['w1c'] = pat['w1c']
        for fld in ('w20', 'w24', 'w28', 'w2c'): v[fld] = pat['w']
        v['b14'][:-1] = np.frombuffer(pat['b14'], np.uint8)          # the last vertex owns no cell (0 in SEGA's data)
        sl.append(dict(A=A, off=-half_width, b6e=0, b6f=0, B=B, water=water, verts=v))
    rec = [pat['rec'] + bytes([0])] * ((n + 3) // 4 + 1)                # page index 0 everywhere
    return dict(slices=sl, rec11=rec, texids=list(texids), hashes=list(hashes), pages=[page], w10=2)

def page_for(P, margin=40.0, texa=0, texb=0):
    """one overlay page covering the whole loop: u = x*su+u0, v = z*sv+v0 inside 0..1"""
    x0, x1 = P[:, 0].min() - margin, P[:, 0].max() + margin; z0, z1 = P[:, 2].min() - margin, P[:, 2].max() + margin
    su, sv = 1.0 / (x1 - x0), 1.0 / (z1 - z0)
    return (texa, texb, -x0 * su, -z0 * sv, su, sv)

def td_rows(m):
    """per slice: (array of vertex positions, column offset)"""
    return [(s['verts']['pos'].astype(np.float64), s['off'], s['A']) for s in m['slices'][1:]]

def aimap_cells(rows, band=0.4):
    """AI map for a road: 8 lanes spread over the central `band` of the width; lane k marks bit k of all three mask bytes
    in the 2 m cell under it (SEGA: bit 0 = highest column side, verified on Desert4/Lakeside4)."""
    cells = {}
    for pos, off, A in rows:
        w = band * A
        for k in range(8):
            c = w / 2 - k * w / 7.0                                   # lateral column (0 = centre line)
            f = min(max(c - off, 0.0), len(pos) - 1.0); j = min(int(f), len(pos) - 2); t = f - j
            p = pos[j] * (1 - t) + pos[j + 1] * t
            key = (math.floor(p[0] / 2.0) * 2.0 + 1.0, math.floor(p[2] / 2.0) * 2.0 + 1.0)
            cells[key] = cells.get(key, 0) | (0x010101 << k)
    return [(x, z, fl) for (x, z), fl in cells.items()]

SPLINE_EXTRA = {}                                                     # importer: dict(splits=[lap fractions], notes=[(lap fraction, Direction code)])
def build_spline(P, splits=(1 / 3.0, 2 / 3.0), notes=()):
    """'DesignRouteSpline' chunk: centre points 2 m apart (slices 1,3,5..), closed (first point repeated), one type (0,5)
    marker per sector split and one type (3,2) marker with the property Direction per pace note, sorted by position."""
    splits = SPLINE_EXTRA.get('splits', splits); notes = SPLINE_EXTRA.get('notes', notes)
    pts = np.concatenate([P[0::2], P[:1]]).astype('<f4'); name = b'DesignRouteSpline\0\0\0'
    marks = sorted([(float(t), None) for t in splits] + [(float(t), int(c)) for t, c in notes], key=lambda m: (m[0], m[1] is not None)); nm = len(marks)
    p_name = 0x20; p_pts = p_name + len(name); p_mark = p_pts + pts.nbytes; p_props = p_mark + 0x1c * nm; nn = sum(1 for m in marks if m[1] is not None)
    p_str = p_props + 8 * max(nn, 1)                                   # per note: 'Direction\0' padded to 12, then the i32 value
    d = bytearray(struct.pack('<5I', 1, 1, nm, 0x14, p_mark) + struct.pack('<3I', p_name, len(pts), p_pts) + name + pts.tobytes())
    fix = [0x0c, 0x10, 0x14, 0x1c]; k = 0; props = bytearray(); strs = bytearray()
    for t, code in marks:
        o = len(d)
        if code is None: d += struct.pack('<HHIHHfffI', 0, 5, 0, 1, 0, t, t, 0.0, p_props)
        else:
            d += struct.pack('<HHIHHfffI', 3, 2, 0, 1, 1, t, t, 0.0, p_props + 8 * k)
            props += struct.pack('<II', p_str + 16 * k, p_str + 16 * k + 12); fix += [p_props + 8 * k, p_props + 8 * k + 4]; strs += b'Direction\0\0\0' + struct.pack('<i', code); k += 1
        fix.append(o + 0x18)
    assert len(d) == p_props
    d += (props if nn else bytes(8)) + strs
    return bytes(d), sorted(fix)

# ---------------------------------------------------------------- chunk surgery
def gfx_root(f): return f.chunks[-1]
def replace(f, cid, data, fix, ref):
    c = f.get(cid); c.data = bytes(data); c.fix = list(fix); c.ref = list(ref); c.gap = None

def gc(f, trk=None):
    """drop chunks not reachable from the root chunk through id references. Ids referenced from the track's OTHER files
    are roots too (the pobj files point at materials/textures that live in master_gfx)."""
    by = f.byid(); keep = set(); st = [f.chunks[-1].id]
    if trk is not None:
        for g in trk.files.values():
            if g is not f:
                for c in g.chunks: st += [i for i in c.refs() if i in by]
    while st:
        i = st.pop()
        if i in keep or i not in by: continue
        keep.add(i); st += by[i].refs()
    before = len(f.chunks); f.chunks = [c for c in f.chunks if c.id in keep]
    return before - len(f.chunks)

def drop_boundary(f):
    r = gfx_root(f); d = bytearray(r.data); bid = r.u32(0x34)
    struct.pack_into('<I', d, 8, 0); struct.pack_into('<I', d, 0x34, 0)
    r.data = bytes(d); r.fix = [o for o in r.fix if o != 8]; r.ref = [o for o in r.ref if o != 0x34]
    f.chunks = [c for c in f.chunks if c.id != bid]

def two_pages(model, limit=110.0, margin=5.0, least=60.0):
    """Overlay pages the way SEGA lays them out.
    1. TrackDeform init 0x4E28F0 counts the pages as (highest page index of the batch records) + 1 ONLY when that index
       is not 0: a road whose batch records all use page 0 gets a page count of 0 and 0x5D27B0 (nearest page to a car)
       dereferences an uninitialised record (crash 0x5D2D3F, first in-game runs).
    2. A page is a LOCAL patch: in the six arcade tracks every page spans 39..120 m a side (about 100 m of road each,
       Desert4 27 pages, Alpine4 35). One page stretched over the whole track (760 x 1080 m) crashed the game when the
       road was drawn (0x40201A, bad texture pointer); the same road with SEGA's mapping numbers ran (in-game runs S1/S2).
    So: consecutive batch records (4 slices each) share a page until their bounding box would pass `limit` metres;
    the page maps that box (padded, at least `least` m a side) to 0..1. All pages use the single page's textures."""
    if len(model['pages']) != 1 or any(r[10] for r in model['rec11']): return False
    texa, texb = model['pages'][0][0], model['pages'][0][1]
    sl = model['slices'][1:]; nrec = len(model['rec11']); pages = []; recpage = []
    def box(k):
        pts = [s['verts']['pos'] for s in sl[4 * k:4 * k + 4]]
        if not pts: return None
        q = np.concatenate(pts).astype(np.float64); return q[:, 0].min(), q[:, 0].max(), q[:, 2].min(), q[:, 2].max()
    cur = None
    def close(c):
        x0, x1, z0, z1 = c; cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        w = max(x1 - x0 + 2 * margin, least); h = max(z1 - z0 + 2 * margin, least)
        su, sv = 1.0 / w, 1.0 / h
        pages.append((texa, texb, 0.5 - cx * su, 0.5 - cz * sv, su, sv))
    for k in range(nrec):
        bx = box(k)
        if bx is None: recpage.append(max(len(pages) - (0 if cur else 1), 0)); continue
        if cur is None: cur = bx
        else:
            m = (min(cur[0], bx[0]), max(cur[1], bx[1]), min(cur[2], bx[2]), max(cur[3], bx[3]))
            if max(m[1] - m[0], m[3] - m[2]) + 2 * margin > limit and len(pages) < 254: close(cur); cur = bx
            else: cur = m
        recpage.append(len(pages))
    if cur is not None: close(cur)
    if len(pages) == 1: pages.append(pages[0]); recpage = [1 if k >= nrec // 2 else 0 for k in range(nrec)]
    recpage = [min(i, len(pages) - 1) for i in recpage]
    model['pages'] = pages; model['rec11'] = [bytes(r[:10]) + bytes([recpage[k]]) for k, r in enumerate(model['rec11'])]
    return True

TWO_PAGES = True                                                       # build_road_ladder.py switches it off for the control step
def set_td(f, model, tex_edit=None):
    """rebuild the TrackDeform chunk + its height blob from a model"""
    if TWO_PAGES: two_pages(model)
    r = gfx_root(f); by = f.byid(); td = by[r.u32(0xc)]; blob = by[td.u32(0x18)]
    raw = b'\xbf' * TDm.blob_size(model); z = zlib.compress(raw, 9)
    blob.data = z; blob.gap = None
    data, fix, ref = TDm.build_td(model, blob.id, len(z))
    replace(f, td.id, data, fix, ref)

def set_scene(f, leaves, meshes):
    r = gfx_root(f); data, fix, ref = scene11.build11(leaves, meshes)
    replace(f, r.u32(4), data, fix, ref)

def set_aimap(fx, cells):
    root = fx.chunks[-1]; data, fix = G.build_grid(cells); replace(fx, root.u32(8), data, fix, [])

def set_route(fx, start, direction, gridtab):
    root = fx.chunks[-1]; d = bytearray(root.data)
    struct.pack_into('<ii', d, 0x2c, start, direction); struct.pack_into('<16i', d, 0x34, *gridtab); root.data = bytes(d)

def add_spline(fx, P):
    root = fx.chunks[-1]; data, fix = build_spline(P)
    if root.u32(0x18):
        replace(fx, root.u32(0x18), data, fix, [])
    else:
        cid = 0x5a11e001                                              # any id not used in the file
        fx.chunks.insert(len(fx.chunks) - 1, sbfw.Ch(5, cid, data, fix, []))
        d = bytearray(root.data); struct.pack_into('<I', d, 0x18, cid); root.data = bytes(d); root.ref = sorted(root.ref + [0x18])

LAKESIDE_GRID = (2, 2, 2, -2, 14, 2, 14, -2, 26, 2, 26, -2, 38, 2, 38, -2)

# ---------------------------------------------------------------- self checks on authored data
def check_authored(name, trk):
    f = trk.files['master_gfx_xdata']; fx = trk.files['master_xdata']; by = f.byid(); r = gfx_root(f)
    t = TDm.parse_td(by[r.u32(0xc)]); n = t.n
    raw = zlib.decompress(by[t.blob_id].data)
    cen = np.array([t.verts[i]['pos'][-t.off[i]] for i in range(1, n + 1)], float)
    step = np.linalg.norm(np.roll(cen, -1, 0) - cen, axis=1)
    msg = ['TD n=%d centre step %.3f..%.3f m, lap %.1f m' % (n, step.min(), step.max(), step.sum()),
           'blob %d bytes (expected %d), zsize field ok %s' % (len(raw), TDm.blob_size(TDm.td_to_model(t)), t.zsize == len(by[t.blob_id].data))]
    m2 = TDm.td_to_model(t); d2, fx2, rf2 = TDm.build_td(m2, t.blob_id, t.zsize); msg.append('TD parse->rebuild identical %s' % (d2 == t.c.data))
    root = fx.chunks[-1]; g = G.parse_grid(fx.get(root.u32(8))); cells = G.grid_cells(g)
    V = np.concatenate([t.verts[i]['pos'][:, [0, 2]] for i in range(1, n + 1)])
    idx, dist = nearest2d(V, np.array([(x, z) for x, z, fl in cells]))
    msg.append('AIMap %d cells, max distance to a road vertex %.2f m, lanes present %s' % (len(cells), dist.max(), sorted({k for x, z, fl in cells for k in range(8) if fl >> k & 1})))
    start, dirn = struct.unpack_from('<ii', root.data, 0x2c); msg.append('start slice %d dir %d grid %s' % (start, dirn, struct.unpack_from('<16i', root.data, 0x34)))
    if root.u32(0x18):
        sp = fx.get(root.u32(0x18)); rec = sp.u32(0xc); npts = sp.u32(rec + 4); S = np.frombuffer(sp.data, '<f4', npts * 3, sp.u32(rec + 8)).reshape(npts, 3)
        dev = max(np.linalg.norm(cen - p, axis=1).min() for p in S); seg = np.linalg.norm(np.diff(S, axis=0), axis=1)
        msg.append('spline %d pts, step %.2f..%.2f, closed %s, max distance to centre line %.3f' % (npts, seg.min(), seg.max(), bool((S[0] == S[-1]).all()), dev))
    s = scene11.parse11(by[r.u32(4)]); msg.append('scene tree %d nodes %d leaves, root meshes %d' % (s.nnode, s.nleaf, len(s.nodes[0].meshes)))
    for q in msg: log('      ', q)

# ---------------------------------------------------------------- the ladder
def authored_loop(src, centre, with_spline, half_width=7, keep_objects=True, checker=True, road=None, info=None):
    """fully authored road + route on top of the chunks borrowed from `src` (a Track).
    road: optional dict(P=centre points 1 m apart [n,3], D=unit directions, lat=lateral unit vectors or None, start=slice)
    info: optional dict that receives P, D, lat, model for later steps (walls, meshes)."""
    trk = src.copy(); f = trk.files['master_gfx_xdata']; fx = trk.files['master_xdata']
    by = f.byid(); r = gfx_root(f); t = TDm.parse_td(by[r.u32(0xc)])
    pat = uniform_pattern(t)
    if road is None: P, D = oval(1000, 60.0, centre); latv = None; start = 100
    else: P, D, latv, start = road['P'], road['D'], road.get('lat'), road.get('start', 100)
    # page texture: a 32x32 DXT1 of the mean colour of SEGA's pages (red 205, green 49) - authored pixels, borrowed header
    small = [c for c in f.kinds(4) if len(c.data) == 868 and c.data[48 + 80:48 + 84] == b'DXT1']
    pg_a, pg_b = t.pages[0][0], t.pages[0][1]
    if small:
        tpl = small[0]
        a = sbfw.Ch(4, 0xa07e0001, tex_fill(tpl, (0, 255, 0)), [], []); b = sbfw.Ch(4, 0xa07e0002, tex_fill(tpl, (128, 128, 128)), [], [])
        f.chunks.insert(0, a); f.chunks.insert(1, b); pg_a, pg_b = a.id, b.id
    model = td_model_flat(P, D, half_width, pat, t.hashes, t.texids, page_for(P, texa=pg_a, texb=pg_b), lat=latv)
    set_td(f, model)
    if checker:                                                      # authored pixels for the two surface layers actually used
        cols = [((150, 150, 150), (110, 110, 110)), ((120, 95, 70), (95, 75, 55))]
        for k, s in enumerate(pat['surf'][:2]):
            c = f.get(t.texids[s]); c.data = tex_fill(c, cols[k][0], checker=(cols[k][1], 128))
    # scene: no scenery meshes; leaves under the road so the camera always sits in a leaf with an all-visible list
    lv = set()
    for p in P:
        for dx in (-30, 0, 30):
            for dz in (-30, 0, 30):
                lv.add((int((p[0] + dx + 750) // 46.875), int((p[2] + dz + 750) // 46.875)))
    set_scene(f, lv, [])
    drop_boundary(f)
    dropped = gc(f, trk)
    set_aimap(fx, aimap_cells(td_rows(model)))
    set_route(fx, start, 1, LAKESIDE_GRID)
    if with_spline: add_spline(fx, P)
    if info is not None: info.update(P=P, D=D, lat=(lateral(D) if latv is None else latv), model=model, leaves=lv, half_width=half_width)
    return trk, dropped, pat

def main(only=''):
    os.makedirs(OUT, exist_ok=True)
    sta = Track('Stadium4'); steps = []
    def want(n): return n.startswith(only)

    n = 'step0_rewrite_identical'
    if want(n):
        t = sta.copy(); same = []
        for s, f in sta.files.items():
            raw = sbfw.write_raw(f.chunks, f.first, f.tail, f.hdr, 'keep'); same.append(raw == f.raw)
        write_track(n, sta, layout='keep', note='| decompressed bytes identical to the original: %s' % all(same))
    n = 'step1_writer_layout'
    if want(n): write_track(n, sta.copy(), layout='auto', note='| same chunks, padding computed by the writer rules')

    n = 'step2_authored_aimap'
    if want(n):
        t = sta.copy(); f = t.files['master_gfx_xdata']; td = TDm.parse_td(f.byid()[gfx_root(f).u32(0xc)])
        set_aimap(t.files['master_xdata'], aimap_cells(td_rows(TDm.td_to_model(td))))
        write_track(n, t); check_authored(n, t)
    n = 'step3_no_boundary'
    if want(n):
        t = sta.copy(); drop_boundary(t.files['master_gfx_xdata']); write_track(n, t)
    n = 'step4_authored_scene'
    if want(n):
        t = sta.copy(); f = t.files['master_gfx_xdata']
        s = scene11.parse11(f.byid()[gfx_root(f).u32(4)])
        lv = {(nd.gx - 1, nd.gz - 1) for nd in s.nodes if nd.leafp}
        set_scene(f, lv, []); d = gc(f, t); write_track(n, t, note='| %d unreferenced chunks dropped' % d); check_authored(n, t)
    n = 'step5_authored_road_surface'
    if want(n):
        t = sta.copy(); f = t.files['master_gfx_xdata']; by = f.byid(); td = TDm.parse_td(by[gfx_root(f).u32(0xc)])
        m = TDm.td_to_model(td); pat = uniform_pattern(td)
        allp = np.concatenate([s['verts']['pos'] for s in m['slices'][1:]])
        for s in m['slices'][1:]:
            v = s['verts']; v['surf'] = np.frombuffer(pat['surf'], np.uint8); v['w1c'] = pat['w1c']
            for fld in ('w20', 'w24', 'w28', 'w2c'): v[fld] = pat['w']
        m['rec11'] = [pat['rec'] + bytes([0])] * len(m['rec11'])
        m['pages'] = [page_for(allp, texa=td.pages[0][0], texb=td.pages[0][1])]
        set_td(f, m); d = gc(f, t); write_track(n, t, note='| %d unreferenced chunks dropped' % d); check_authored(n, t)
    n = 'step6_added_spline'
    if want(n):
        t = sta.copy(); f = t.files['master_gfx_xdata']; td = TDm.parse_td(f.byid()[gfx_root(f).u32(0xc)])
        cen = np.array([td.verts[i]['pos'][-td.off[i]] for i in range(1, td.n + 1)], float)
        add_spline(t.files['master_xdata'], cen); write_track(n, t); check_authored(n, t)
    n = 'step7_flat_loop_no_spline'
    if want(n):
        t, d, pat = authored_loop(sta, (0.0, 0.0, 450.0), False); write_track(n, t, note='| %d unreferenced chunks dropped' % d); check_authored(n, t)
    n = 'step8_flat_loop'
    if want(n):
        t, d, pat = authored_loop(sta, (0.0, 0.0, 450.0), True); write_track(n, t, note='| pattern %s' % {k: (v.hex() if isinstance(v, bytes) else v) for k, v in pat.items()}); check_authored(n, t)
    n = 'step9_flat_loop_bare'
    if want(n):
        t, d, pat = authored_loop(sta, (0.0, 0.0, 450.0), True)
        write_track(n, t, omit=('pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata', 'proc'), note='| no pobj files, no grass cache')
    n = 'step8_flat_loop_desert4'
    if want(n) and os.path.isdir(os.path.join(TRACKS, 'Desert4')):
        des = Track('Desert4')
        t, d, pat = authored_loop(des, (0.0, 0.0, 600.0), True); write_track(n, t, note='| pattern %s' % {k: (v.hex() if isinstance(v, bytes) else v) for k, v in pat.items()}); check_authored(n, t)
    open(os.path.join(OUT, 'build_log.txt'), 'w').write('\n'.join(LOG) + '\n')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '')
