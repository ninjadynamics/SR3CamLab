"""Decode a BUILT classic step back into a textured OBJ (what the SR3 files contain), for Blender rendering.
    python preview_obj.py [step]   -> ../previews/sr3_decoded/<step>.obj + .mtl + textures/
Scenery meshes: vertices, strip triangles, uv0 and the diffuse texture of their material (DXT1 decoded from the file).
Road: TrackDeform cells, textured with the TOP layer texture of each cell (DXT5 colour decoded from the file) at an
arbitrary 6 m tiling (the game's own road mapping is not known). Walls are not written (invisible in game).
Axes: the classic OBJ's (x - ox, y, -(z - oz)) so the same camera path (centre line CSV) can be used."""
import os, sys, json, struct
import numpy as np
from PIL import Image
from common import *
import sbfw, trackdeform as TDm, scene11, meshgen

XFORM = os.path.join(TMP, 'classic_xform.json')                      # set per course by course.use()
def dxt_colour(blocks, bw, bh, punch=True):
    """DXT1 colour blocks -> RGBA uint8 (h, w, 4)"""
    b = np.frombuffer(blocks, np.dtype([('c0', '<u2'), ('c1', '<u2'), ('ix', '<u4')]), bw * bh)
    def rgb(c): return np.stack([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31], 1).astype(np.int32)
    c0 = rgb(b['c0'].astype(np.int32)); c1 = rgb(b['c1'].astype(np.int32)); four = (b['c0'] > b['c1'])[:, None]
    p2 = np.where(four, (2 * c0 + c1) // 3, (c0 + c1) // 2); p3 = np.where(four, (c0 + 2 * c1) // 3, 0)
    pal = np.stack([c0, c1, p2, p3], 1)                                # n, 4, 3
    ix = (b['ix'][:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3   # n, 16
    px = np.take_along_axis(pal, ix[:, :, None].astype(np.int64).repeat(3, 2), 1)   # n,16,3
    a = np.where((ix == 3) & ~four & punch, 0, 255)
    img = np.concatenate([px, a[:, :, None]], 2).reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return img.astype(np.uint8)

def texture_png(c, path):
    d = c.data; w, h = struct.unpack_from('<II', d, 8); four = d[48 + 80:48 + 84]; base = 48 + 124
    bw, bh = max(1, w // 4), max(1, h // 4)
    if four == b'DXT1': img = dxt_colour(d[base:base + 8 * bw * bh], bw, bh)
    else:                                                             # DXT5: 8 alpha bytes + DXT1-style colour block (always 4-colour)
        blk = np.frombuffer(d, np.uint8, 16 * bw * bh, base).reshape(-1, 16)[:, 8:].copy()
        img = dxt_colour(blk.tobytes(), bw, bh, punch=False); img[:, :, 3] = 255
        ab = np.frombuffer(d, np.uint8, 16 * bw * bh, base).reshape(-1, 16)[:, :8].astype(np.uint64)      # alpha block: a0, a1, 16 x 3-bit indices
        a0 = ab[:, 0].astype(np.int32); a1 = ab[:, 1].astype(np.int32); bits = sum(ab[:, 2 + k] << np.uint64(8 * k) for k in range(6))
        ix = ((bits[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))) & np.uint64(7)).astype(np.int32)
        lv = np.zeros((len(ab), 8), np.int32); lv[:, 0] = a0; lv[:, 1] = a1
        for k in range(2, 8):
            lv[:, k] = np.where(a0 > a1, ((8 - k) * a0 + (k - 1) * a1) // 7, np.where(k < 6, ((6 - k) * a0 + (k - 1) * a1) // 5, 0 if k == 6 else 255))
        al = np.take_along_axis(lv, ix, 1).reshape(bh, bw, 4, 4).transpose(0, 2, 1, 3).reshape(bh * 4, bw * 4)
        if (al < 128).mean() > 0.02: img[:, :, 3] = np.where(al < 128, 0, 255)                        # only treat as a cut-out when it really has holes
    im = Image.fromarray(img[:h, :w], 'RGBA')
    if w > 256: im = im.resize((256, 256 * h // w))
    has_alpha = bool((img[:, :, 3] == 0).any()); im.save(path); return has_alpha

def main(step='step17_classic_scenery_textured_desert4', slot='Desert4'):
    xf = json.load(open(XFORM)); ox, oz = xf['ox'], xf['oz']
    out = os.path.join(WORK, 'previews', 'sr3_decoded'); os.makedirs(os.path.join(out, 'textures'), exist_ok=True)
    tf = track_files(os.path.join(OUT, step, slot)); f = sbfw.read_sbf(tf['master_gfx_xdata']); by = f.byid(); r = f.chunks[-1]
    td = TDm.parse_td(by[r.u32(0xc)]); s = scene11.parse11(by[r.u32(4)])
    V = []; VT = []; F = []; mtl = {}
    def tex_of(tex_id, cut=False):
        # the alpha channel counts only when the material tests or blends it (road layers and some SR3 ground textures keep a blend height there)
        name = 'tex_%08x%s' % (tex_id, '_a' if cut else '')
        if name not in mtl:
            has = texture_png(by[tex_id], os.path.join(out, 'textures', name + '.png')) if tex_id in by else None
            mtl[name] = (has and cut) if has is not None else None
        return name
    def P(p): return (p[0] - ox, p[1], -(p[2] - oz))
    # scenery
    nm = 0
    for mid in s.nodes[0].meshes:
        m = meshgen.parse_mesh(by[mid]); vv = m['verts']; I = m['idx']; mat = by[m['groups'][0][4]]
        name = tex_of(mat.u32(0x1bc), len(mat.data) == 1848 and bool(mat.u32(0x4d4) or mat.u32(0x4e4))); base = len(V); F.append('usemtl ' + name); nm += 1
        for v in vv:
            V.append(P(v['p'][:3])); VT.append((float(np.int16(v['uv0'][0])) / 32768.0, 1.0 - float(np.int16(v['uv0'][1])) / 32768.0))     # uv is signed
        for k in range(len(I) - 2):
            a, b, c = int(I[k]), int(I[k + 1]), int(I[k + 2])
            if len({a, b, c}) < 3: continue
            if k % 2: a, b = b, a
            F.append('f %d/%d %d/%d %d/%d' % (base + c + 1, base + c + 1, base + b + 1, base + b + 1, base + a + 1, base + a + 1))
    # road
    n = td.n; cur = None; tile = 6.0
    for i in range(1, n + 1):
        a = td.verts[i]; b = td.verts[i % n + 1]; ca = TDm.columns(td, i); cb = {int(c): j for j, c in enumerate(TDm.columns(td, i % n + 1))}
        for k in range(len(a) - 1):
            if int(ca[k]) not in cb or int(ca[k]) + 1 not in cb: continue      # cells are matched by column number (variable width)
            k2 = cb[int(ca[k])]; k3 = cb[int(ca[k]) + 1]
            top = td.hashes[int(a[k]['surf'][1])]; name = tex_of(top)
            if name != cur: F.append('usemtl ' + name); cur = name
            q = [a[k]['pos'], a[k + 1]['pos'], b[k3]['pos'], b[k2]['pos']]; base = len(V)
            for p in q: V.append(P(p)); VT.append((p[0] / tile, p[2] / tile))
            F.append('f %d/%d %d/%d %d/%d %d/%d' % tuple(x for j in (0, 1, 2, 3) for x in (base + j + 1, base + j + 1)))
    with open(os.path.join(out, step + '.mtl'), 'w') as fm:
        for name, alpha in mtl.items():
            fm.write('newmtl %s\nKd 0.8 0.8 0.8\n' % name)
            if alpha is not None:
                fm.write('map_Kd textures/%s.png\n' % name)
                if alpha: fm.write('map_d textures/%s.png\n' % name)
    with open(os.path.join(out, step + '.obj'), 'w') as fo:
        fo.write('# decoded back from %s\\%s (SR3 files)\nmtllib %s.mtl\n' % (step, slot, step))
        fo.write('\n'.join('v %.4f %.4f %.4f' % v for v in V) + '\n' + '\n'.join('vt %.5f %.5f' % t for t in VT) + '\n' + '\n'.join(F) + '\n')
    print('decoded %s: %d scenery meshes, %d road slices, %d vertices, %d textures -> %s' % (step, nm, n, len(V), len(mtl), os.path.join(out, step + '.obj')))
    return os.path.join(out, step + '.obj')

if __name__ == '__main__':
    main(*sys.argv[1:2])
