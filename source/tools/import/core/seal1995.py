"""seal1995.py - close the hairline gaps between the polygons of a built classic course (course setting "stitch": true).

What was seen (Mountain RT, 4K screenshots of 2026-10-13): 26 to 102 pixels per frame that the game never drew - black with alpha 0, single
pixels on cliffs, parapets and house fronts (an image editor shows them as white dots). Counted in the built file:
    1 684 pairs of corners closer than 1 mm that are not the same number. Most are one float32 step apart (0.03 mm at x = 500 m): a polygon that
          went through the Blender scene was rounded in course coordinates, its untouched 1995 neighbour in the slot's - the two edges that
          should be one are drawn as two.
    9 085 corners that lie ON a neighbour's edge without being one of its corners (T-joints): pieces cut by uv_split beside an uncut polygon,
          two-triangle fronts beside finer ones. The long edge and the two short ones are not filled pixel for pixel alike.
Both are cured in the meshes, after everything else is decided (pictures, light-map rectangles, pages):
    1. corners closer than `tol` become one place, the one most vertices already have ;
    2. a triangle with a corner of something else on one of its edges is cut there, fan-wise from the corner opposite: the same surface, the
       same picture and the same light-map texels (the new vertex takes what the edge has at that point).
Only opaque meshes are touched: boards cross each other and their edges are cut by their pictures.
A mesh holds at most 65 535 indices. One that would pass that with its cuts is written as several (the first keeps its number, the others take new
numbers at the end of `ids`, the list of the scene's meshes): at R4 a mesh of 10 000 rounded pieces was left uncut for that, 1 516 joints in it.
    seal(new, ids=ids)    new = the chunks add_scenery made ; meshes are replaced in the list. -> (corners moved, edges cut, triangles added)
Without numpy since 2026-10-16 (kb 31): the steps on arrays are fastseal.c (seal_unique ... seal_flags, each quoting the numpy it replaced),
the meshes read and written by meshbuf, the cutting below on Python numbers; the same chunks as the numpy code, which stays as
_seal_numpy (SR3_FASTSEAL=0 runs it) and as the reference."""
import struct, collections, math, array
import npexact

def _clusters(U, tol):
    import numpy as np
    """U: n x 3 distinct places -> a label per place; places closer than tol (through a chain too) share one: the lowest number among them.
    The pairs closer than tol are found on arrays (the places sorted by their cell of tol a side, each cell against itself and the 13 cells
    'after' it); the few pairs there are, are joined as _clusters_py joins them. The same labels: a label is the lowest number of its group
    whatever the order the pairs come in, and a pair's distance is the same sum of three squares."""
    n = len(U)
    if n < 2: return np.arange(n, dtype=np.int64)
    K = np.floor(U / tol).astype(np.int64); K -= K.min(0) - 1; span = K.max(0) + 2
    if float(span[0]) * float(span[1]) * float(span[2]) > 9e18: return _clusters_py(U, tol)              # (cells that do not fit one number: the old way)
    code = (K[:, 0] * span[1] + K[:, 1]) * span[2] + K[:, 2]; order = np.argsort(code, kind='stable'); cs = code[order]; t2 = tol * tol; pi = []; pj = []
    for dx, dy, dz in [(0, 0, 0)] + [(a, b, c) for a in (0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) > (0, 0, 0)]:
        tg = code + (dx * span[1] + dy) * span[2] + dz; lo = np.searchsorted(cs, tg, 'left'); cnt = np.searchsorted(cs, tg, 'right') - lo; m = np.nonzero(cnt > (1 if (dx, dy, dz) == (0, 0, 0) else 0))[0]
        if not len(m): continue
        i = np.repeat(m, cnt[m]); j = order[np.repeat(lo[m], cnt[m]) + (np.arange(len(i)) - np.repeat(np.cumsum(cnt[m]) - cnt[m], cnt[m]))]
        ok = (i != j) & (((U[i] - U[j]) ** 2).sum(1) < t2); pi.append(i[ok]); pj.append(j[ok])
    par = np.arange(n, dtype=np.int64)
    if pi and sum(len(x) for x in pi):
        par = par.tolist()
        def find(x):
            while par[x] != x: par[x] = par[par[x]]; x = par[x]
            return x
        for a, b in zip(np.concatenate(pi).tolist(), np.concatenate(pj).tolist()):
            a, b = find(a), find(b)
            if a != b: par[max(a, b)] = min(a, b)
        par = np.array([find(i) for i in range(n)], np.int64)
    return par
def _clusters_py(U, tol):
    """(as it was written: the reference)"""
    import numpy as np
    n = len(U); par = list(range(n))
    def find(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    K = np.floor(U / tol).astype(np.int64); d = collections.defaultdict(list)
    for i, k in enumerate(map(tuple, K.tolist())): d[k].append(i)
    offs = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)]; t2 = tol * tol
    for k, ii in d.items():
        for o in offs:
            jj = d.get((k[0] + o[0], k[1] + o[1], k[2] + o[2]))
            if not jj: continue
            for i in ii:
                for j in jj:
                    if i < j and float(((U[i] - U[j]) ** 2).sum()) < t2:
                        a, b = find(i), find(j)
                        if a != b: par[max(a, b)] = min(a, b)
    return np.array([find(i) for i in range(n)], np.int64)

def _rint(x):
    r = float(round(x)); return math.copysign(r, x) if r == 0.0 else r                 # np.round(x): half to even
def seal(new, log=print, tol=0.001, ids=None):
    import fastseal
    if not fastseal.ON: return _seal_numpy(new, log, tol, ids)
    import meshbuf
    from npyio import Arr
    L = fastseal.lib(); ad = lambda a: a.buffer_info()[0]; I8 = lambda n: array.array('q', bytes(8 * n))
    mats = {c.id: c for c in new if c.kind == 2}
    def opaque(mid):
        m = mats.get(mid); return not (m is not None and len(m.data) == 1848 and (struct.unpack_from('<I', m.data, 0x4d4)[0] or struct.unpack_from('<I', m.data, 0x4e4)[0]))
    items = []
    for q, c in enumerate(new):
        if c.kind != 1 or (c.id >> 16) != 0xc1a7: continue
        m = meshbuf.parse_mesh(c); mid = m['groups'][0][4]
        if m['stride'] != 48 or (m['ni'] + 2) % 6 or m['nv'] == 0 or not opaque(mid): continue
        items.append([q, c, m['nv'], bytes(m['idx'].buf), mid, bytes(m['verts'].buf)])
    if not items: return 0, 0, 0
    # ---- 1. one place for corners that are meant to be one
    voff = array.array('q', [0]); ioff = array.array('q', [0])
    for it in items: voff.append(voff[-1] + it[2]); ioff.append(ioff[-1] + len(it[3]) // 2)
    nv = voff[-1]; V = bytearray(b''.join(it[5] for it in items))      # all their vertex records, in order
    P = array.array('f', bytes(12 * nv)); L.seal_gather(nv, ad_b(V), ad(P))
    inv = I8(nv); first = I8(nv); cnt = I8(nv); nu = L.seal_unique(nv, ad(P), ad(inv), ad(first), ad(cnt))      # allp + 0.0f, np.unique of the 12-byte rows
    U = array.array('d', bytes(24 * nu)); L.seal_places(nu, ad(P), ad(first), ad(U))                            # U = allp[first] as float64
    lab = I8(nu); L.seal_clusters(nu, ad(U), float(tol), ad(lab))                                               # _clusters(U, tol)
    rp = I8(nu); cid = I8(nv); moved = L.seal_reps(nu, ad(lab), ad(cnt), ad(rp), nv, ad(inv), ad(cid))          # the place most vertices have; cid = rep[inv]
    L.seal_scatter(nv, ad_b(V), ad(P), ad(first), ad(cid))                                                      # it[2]['p'][:, :3] = U32[it[5]]
    # ---- 2. corners on the inside of an edge
    idx = array.array('H', b''.join(it[3] for it in items)); cn = array.array('q', [0, 0])
    L.seal_joints(nu, ad(U), float(tol), len(items), ad(idx), ad(ioff), ad(cid), ad(voff), ad(cn)); ne, jn = cn[0], cn[1]
    E = I8(2 * ne); je = I8(jn); jt = array.array('d', bytes(8 * jn)); jv = I8(jn); L.seal_joints_get(ad(E), ad(je) if jn else None, ad(jt) if jn else None, ad(jv) if jn else None)
    J = {}
    for e, t, v in zip(je, jt, jv): J.setdefault((E[2 * e], E[2 * e + 1]), []).append((t, v))
    nj = jn
    if not J and not moved: return 0, 0, 0
    Jk = array.array('q', sorted(a * nu + b for a, b in J)); added = 0; skipped = 0; nparted = 0; nempty = 0
    qoff = array.array('q', [0])
    for k in range(len(items)): qoff.append(qoff[-1] + (ioff[k + 1] - ioff[k] + 2) // 6)
    flag = bytearray(qoff[-1]); L.seal_flags(nu, ad(Jk) if len(Jk) else None, len(Jk), len(items), ad(idx), ad(ioff), ad(cid), ad(voff), ad(qoff), ad_b(flag))
    U32 = memoryview(P).cast('B'); fst = first; U32b = P.buffer_info()[0]          # (the places as float32: seal_newverts reads them)
    def clone(ch, cid_, recs, strip, mid):
        return meshbuf.clone_mesh(ch, cid_, Arr('|V48', (len(recs) // 48,), recs), Arr('<u2', (len(strip),), array.array('H', strip).tobytes()), mid)
    for k, it in enumerate(items):
        q, ch, nvk, ib, mid = it[:5]; Vk = bytes(V[48 * voff[k]:48 * voff[k + 1]]); il = idx[ioff[k]:ioff[k + 1]].tolist()
        nq = qoff[k + 1] - qoff[k]; fl = flag[qoff[k]:qoff[k + 1]]
        if not any(fl):
            if moved: new[q] = clone(ch, ch.id, Vk, il, mid)
            continue
        cl = cid[voff[k]:voff[k + 1]].tolist(); cache = {}; nv0 = nvk; ep = array.array('q'); er = array.array('q'); et = array.array('d'); ev = array.array('q')
        def newvert(p, r, t, v):
            """a new corner at place v on the edge p - r: its number now, its record made by fastseal.c seal_newverts once the mesh is cut (the
            numpy lines are quoted there; a corner refers only to corners made before it)"""
            key = (p, r, v)
            if key in cache: return cache[key]
            ep.append(p); er.append(r); et.append(t); ev.append(v); cl.append(v); cache[key] = nv0 + len(ep) - 1; return cache[key]
        def cut(tri):
            out = []; stack = [tri]; guard = 0
            while stack:
                a, b, c = stack.pop(); guard += 1
                if len({cl[a], cl[b], cl[c]}) < 3: continue
                for p, r, o in ((a, b, c), (b, c, a), (c, a, b)):
                    ca, cb = cl[p], cl[r]; js = J.get((ca, cb) if ca < cb else (cb, ca)) if guard < 400 else None
                    if js:
                        seq = js if ca < cb else [(1.0 - t, v) for t, v in reversed(js)]; chain = [p] + [newvert(p, r, t, v) for t, v in seq] + [r]
                        for x, y in zip(chain[:-1], chain[1:]): stack.append((x, y, o))
                        break
                else: out.append((a, b, c))
            return out
        units = []; nt0 = 0; nt1 = 0
        for j in range(nq):
            s0, s1, s2, s3 = il[6 * j:6 * j + 4]
            if not fl[j]: units.append([s0, s1, s2, s3]); continue
            a = cut((s0, s1, s2)); b = cut((s2, s1, s3)) if cl[s3] != cl[s2] and cl[s3] != cl[s1] else []
            nt0 += 1 + (1 if b or (cl[s3] != cl[s2] and cl[s3] != cl[s1]) else 0); nt1 += len(a) + len(b)
            for x, y, z in a + b: units.append([x, y, z, z])
        strip = []
        for u in units:
            if strip: strip += [strip[-1], u[0]]
            strip += u
        if not strip:                                              # every triangle of this mesh is gone (a sliver under 1 mm whose corners became one place): it keeps its own
            new[q] = clone(ch, ch.id, Vk, il, mid); nempty += 1; continue          # indices, on the moved corners (see _seal_numpy: a mesh with NO indices kills the game)
        xr = bytearray(48 * len(ep))
        if len(ep): L.seal_newverts(nv0, Vk, len(ep), ad(ep), ad(er), ad(et), ad(ev), U32b, ad(fst), ad_b(xr))
        V2 = Vk + bytes(xr); nv2 = len(V2) // 48
        if nv2 >= 65536 or len(strip) >= 65536:
            if ids is None: skipped += 1; new[q] = clone(ch, ch.id, Vk, il, mid); continue
            npart = -(-len(units) * 6 // 54000); per = -(-len(units) // npart); nparted += 1          # too many indices for one mesh: several, each with the corners it uses
            for pi in range(npart):
                us = units[pi * per:(pi + 1) * per]; uq_ = sorted({x for u in us for x in u}); pos = {x: i for i, x in enumerate(uq_)}; sp = []      # np.unique(us, return_inverse=True)
                for u in us:
                    u = [pos[x] for x in u]
                    if sp: sp += [sp[-1], u[0]]
                    sp += u
                recs = b''.join(V2[48 * x:48 * x + 48] for x in uq_)
                if pi == 0: new[q] = clone(ch, ch.id, recs, sp, mid)
                else: nid = 0xc1a70000 + len(ids); new.append(clone(ch, nid, recs, sp, mid)); ids.append(nid)
            added += nt1 - nt0; continue
        new[q] = clone(ch, ch.id, V2, strip, mid); added += nt1 - nt0
    log('       gaps sealed (seal1995): %d opaque meshes ; %d corners moved onto their neighbour (under %.1f mm) ; %d edges cut at %d corners that lay on them, %d triangles added%s'
        % (len(items), moved, tol * 1000, len(J), nj, added, (' ; %d meshes left uncut (too large)' % skipped if skipped else '') + (' ; %d meshes written as several (index limit)' % nparted if nparted else '') + (' ; %d meshes with no triangle left keep their own (of no area)' % nempty if nempty else '')))
    return moved, nj, added
def ad_b(b):
    import ctypes
    return ctypes.addressof((ctypes.c_char * len(b)).from_buffer(b)) if len(b) else None
def _seal_numpy(new, log=print, tol=0.001, ids=None):
    """the numpy seal (the reference; SR3_FASTSEAL=0)"""
    import numpy as np, meshgen
    mats = {c.id: c for c in new if c.kind == 2}
    def opaque(mid):
        m = mats.get(mid); return not (m is not None and len(m.data) == 1848 and (struct.unpack_from('<I', m.data, 0x4d4)[0] or struct.unpack_from('<I', m.data, 0x4e4)[0]))
    items = []
    for q, c in enumerate(new):
        if c.kind != 1 or (c.id >> 16) != 0xc1a7: continue
        m = meshgen.parse_mesh(c); mid = m['groups'][0][4]
        if m['stride'] != 48 or (m['ni'] + 2) % 6 or m['nv'] == 0 or not opaque(mid): continue
        items.append([q, c, m['verts'].copy(), np.asarray(m['idx']).astype(np.int64), mid])
    if not items: return 0, 0, 0
    # ---- 1. one place for corners that are meant to be one
    allp = np.concatenate([it[2]['p'][:, :3] for it in items]).astype(np.float32) + np.float32(0.0)
    raw = np.ascontiguousarray(allp).view(np.dtype((np.void, 12))).ravel(); uq, first, inv, cnt = np.unique(raw, return_index=True, return_inverse=True, return_counts=True); inv = inv.ravel()
    U32 = allp[first]; U = U32.astype(np.float64); lab = _clusters(U, tol); order = np.lexsort((np.arange(len(U)), -cnt, lab)); ls = lab[order]; head = np.r_[True, ls[1:] != ls[:-1]]
    rep_of = np.empty(len(U), np.int64); rep_of[ls[head]] = order[head]; rep = rep_of[lab]; cid_all = rep[inv]; moved = int((cid_all != inv).sum()); off = 0
    for it in items:
        k = len(it[2]); it.append(cid_all[off:off + k].copy()); it[2]['p'][:, :3] = U32[it[5]]; off += k
    # ---- 2. corners on the inside of an edge
    tris = []
    for it in items:
        s = np.concatenate([it[3], [0, 0]]).reshape(-1, 6)[:, :4]; c = it[5]; t = np.concatenate([c[s[:, [0, 1, 2]]], c[s[:, [2, 1, 3]]]]); tris.append(t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])])
    T = np.concatenate(tris); E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]); E.sort(axis=1); E = np.unique(E, axis=0)
    used = np.unique(T); xo = used[np.argsort(U[used, 0], kind='stable')]; xs = U[xo, 0]; J = {}; nj = 0
    lo_ = np.minimum(U[E[:, 0], 0], U[E[:, 1], 0]) - tol; hi_ = np.maximum(U[E[:, 0], 0], U[E[:, 1], 0]) + tol; i0s = np.searchsorted(xs, lo_); i1s = np.searchsorted(xs, hi_)
    import fastseal                                                    # the corners that are nowhere near an edge are thrown away in C (fastseal.c); what is left is measured below as ever
    if fastseal.ON:
        cnt_, off_, cand_ = fastseal.candidates(U, E, xo, i0s, i1s, tol); it_ = ((int(E[k_, 0]), int(E[k_, 1]), cand_[off_[k_]:off_[k_ + 1]]) for k_ in np.nonzero(cnt_)[0].tolist())
    else: it_ = ((a, b, xo[i0:i1]) for (a, b), i0, i1 in zip(E.tolist(), i0s.tolist(), i1s.tolist()) if i1 - i0 > 2)
    for a, b, c in it_:
        A = U[a]; ab = U[b] - A; L2 = float(ab @ ab)
        if L2 < 4 * tol * tol: continue
        Q = U[c] - A; t = (Q @ ab) / L2; e = tol / np.sqrt(L2); m = (t > e) & (t < 1 - e)
        if not m.any(): continue
        d = np.linalg.norm(Q[m] - t[m, None] * ab, axis=1); ok = d < tol
        if not ok.any(): continue
        js = sorted((float(tt), int(v)) for tt, v in zip(t[m][ok], c[m][ok]) if v != a and v != b)
        if js: J[(a, b)] = js; nj += len(js)
    if not J and not moved: return 0, 0, 0
    Jk = np.array(sorted(a * len(U) + b for a, b in J), np.int64) if J else np.zeros(0, np.int64); added = 0; skipped = 0; nparted = 0; nempty = 0
    for it in items:
        q, ch, V, idx, mid, cid = it; s = np.concatenate([idx, [0, 0]]).reshape(-1, 6)[:, :4]; c4 = cid[s]; flag = np.zeros(len(s), bool)
        for x, y in ((0, 1), (1, 2), (2, 0), (1, 3), (3, 2)):
            lo = np.minimum(c4[:, x], c4[:, y]); hi = np.maximum(c4[:, x], c4[:, y]); flag |= np.isin(lo * len(U) + hi, Jk) & (lo != hi)
        if not flag.any():
            if moved: new[q] = meshgen.clone_mesh(ch, ch.id, V, idx.tolist(), mid)
            continue
        cl = cid.tolist(); extra = []; cache = {}; nv0 = len(V)
        def newvert(p, r, t, v):
            k = (p, r, v)
            if k in cache: return cache[k]
            a = V[p] if p < nv0 else extra[p - nv0]; b = V[r] if r < nv0 else extra[r - nv0]; w = np.zeros(1, meshgen.VTX)[0]
            w['p'][:3] = U32[v]; w['p'][3] = a['p'][3]
            for f_ in ('n', 't'):
                x = a[f_].astype(np.float64) * (1 - t) + b[f_].astype(np.float64) * t; l = np.linalg.norm(x); w[f_] = (x / l if l > 1e-9 else a[f_]).astype(np.float32)
            u0 = a['uv0'].view(np.int16).astype(np.float64) * (1 - t) + b['uv0'].view(np.int16).astype(np.float64) * t; w['uv0'] = np.clip(np.round(u0), -32768, 32767).astype(np.int16).view(np.uint16)
            w['uv1'] = np.clip(np.round(a['uv1'].astype(np.float64) * (1 - t) + b['uv1'].astype(np.float64) * t), 0, 65535).astype(np.uint16)
            extra.append(w); cl.append(v); cache[k] = nv0 + len(extra) - 1; return cache[k]
        def cut(tri):
            out = []; stack = [tri]; guard = 0
            while stack:
                a, b, c = stack.pop(); guard += 1
                if len({cl[a], cl[b], cl[c]}) < 3: continue
                for p, r, o in ((a, b, c), (b, c, a), (c, a, b)):
                    ca, cb = cl[p], cl[r]; js = J.get((ca, cb) if ca < cb else (cb, ca)) if guard < 400 else None
                    if js:
                        seq = js if ca < cb else [(1.0 - t, v) for t, v in reversed(js)]; chain = [p] + [newvert(p, r, t, v) for t, v in seq] + [r]
                        for x, y in zip(chain[:-1], chain[1:]): stack.append((x, y, o))
                        break
                else: out.append((a, b, c))
            return out
        units = []; nt0 = 0; nt1 = 0
        for k in range(len(s)):
            s0, s1, s2, s3 = s[k].tolist()
            if not flag[k]: units.append([s0, s1, s2, s3]); continue
            a = cut((s0, s1, s2)); b = cut((s2, s1, s3)) if cl[s3] != cl[s2] and cl[s3] != cl[s1] else []
            nt0 += 1 + (1 if b or (cl[s3] != cl[s2] and cl[s3] != cl[s1]) else 0); nt1 += len(a) + len(b)
            for x, y, z in a + b: units.append([x, y, z, z])
        strip = []
        for u in units:
            if strip: strip += [strip[-1], u[0]]
            strip += u
        if not strip:                                              # every triangle of this mesh is gone (a sliver under 1 mm whose corners became one place): it keeps its own
            new[q] = meshgen.clone_mesh(ch, ch.id, V, idx.tolist(), mid); nempty += 1; continue          # indices, on the moved corners - triangles of no area, nothing drawn. A mesh with NO indices kills the game when
                                                                   # the track loads (access violation at 0x580B24: routine 0x584130 makes no index buffer for a count of 0 and then locks it; caught
                                                                   # with the crash logger on 2026-10-13, mesh c1a701a0 of the first sealed builds, 16 vertices and 0 indices)
        V2 = np.concatenate([V, np.array(extra, meshgen.VTX)]) if extra else V
        if len(V2) >= 65536 or len(strip) >= 65536:
            if ids is None: skipped += 1; new[q] = meshgen.clone_mesh(ch, ch.id, V, idx.tolist(), mid); continue
            npart = -(-len(units) * 6 // 54000); per = -(-len(units) // npart); nparted += 1          # too many indices for one mesh: several, each with the corners it uses
            for pi in range(npart):
                us = np.array(units[pi * per:(pi + 1) * per], np.int64); uq_, inv_ = np.unique(us, return_inverse=True); sp = []
                for u in inv_.reshape(-1, 4).tolist():
                    if sp: sp += [sp[-1], u[0]]
                    sp += u
                if pi == 0: new[q] = meshgen.clone_mesh(ch, ch.id, V2[uq_], sp, mid)
                else: nid = 0xc1a70000 + len(ids); new.append(meshgen.clone_mesh(ch, nid, V2[uq_], sp, mid)); ids.append(nid)
            added += nt1 - nt0; continue
        new[q] = meshgen.clone_mesh(ch, ch.id, V2, strip, mid); added += nt1 - nt0
    log('       gaps sealed (seal1995): %d opaque meshes ; %d corners moved onto their neighbour (under %.1f mm) ; %d edges cut at %d corners that lay on them, %d triangles added%s'
        % (len(items), moved, tol * 1000, len(J), nj, added, (' ; %d meshes left uncut (too large)' % skipped if skipped else '') + (' ; %d meshes written as several (index limit)' % nparted if nparted else '') + (' ; %d meshes with no triangle left keep their own (of no area)' % nempty if nempty else '')))
    return moved, nj, added
