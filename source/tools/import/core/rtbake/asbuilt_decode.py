"""A BUILT classic track, read back from its own files WITH its light maps (preview_obj.py reads geometry and pictures only).
    python asbuilt_decode.py <step folder name under work/out> <faces.pkl of the build (for the course origin)> <out dir>
-> <out>/asbuilt.npz: per triangle corner the place (course coordinates), uv0, uv1 ; per triangle its picture, its light-map page (-1 = none) and
   whether it is a cut-out ; <out>/tex/<id>.png pictures at full size (light-map pages too).
Run from tools/import/core (it uses the importer's own file readers)."""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..')))      # tools/import/core
import os, sys, struct, pickle, collections
import numpy as np
from PIL import Image
from common import *
import sbfw, scene11, meshgen, preview_obj as PO
step, dump, out = sys.argv[1], sys.argv[2], sys.argv[3]
if os.path.isdir(os.path.join(out, 'tex')):                          # pictures of an EARLIER decode in this folder must go: light-map pages keep their ids from build to build, and a kept page under new uv showed a tower lit from all sides (2026-10-13)
    import shutil; shutil.rmtree(os.path.join(out, 'tex'))
os.makedirs(os.path.join(out, 'tex'), exist_ok=True)
import nfpickle; rd = nfpickle.load(dump, numpy=True)['rd']; ox, oz = float(rd['ox']), float(rd['oz'])
tf = track_files(os.path.join(OUT, step, 'Desert4')); f = sbfw.read_sbf(tf['master_gfx_xdata']); by = f.byid(); r = f.chunks[-1]; s = scene11.parse11(by[r.u32(4)])
mids = []; seen = set()
for nd in s.nodes:
    for m in nd.meshes:
        if m not in seen: seen.add(m); mids.append(m)
def save_tex(tid):
    p = os.path.join(out, 'tex', '%08x.png' % tid)
    if os.path.exists(p + '.cut'): return True
    if os.path.exists(p): return False
    d = by[tid].data; w, h = struct.unpack_from('<II', d, 8); four = d[48 + 80:48 + 84]; base = 48 + 124; bw, bh = max(1, w // 4), max(1, h // 4); cut = False
    if four == b'DXT1': img = PO.dxt_colour(d[base:base + 8 * bw * bh], bw, bh)
    else:
        blk = np.frombuffer(d, np.uint8, 16 * bw * bh, base).reshape(-1, 16); img = PO.dxt_colour(blk[:, 8:].copy().tobytes(), bw, bh, punch=False); ab = blk[:, :8].astype(np.uint64)
        a0 = ab[:, 0].astype(np.int32); a1 = ab[:, 1].astype(np.int32); bits = sum(ab[:, 2 + k] << np.uint64(8 * k) for k in range(6)); ix = ((bits[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))) & np.uint64(7)).astype(np.int32)
        lv = np.zeros((len(ab), 8), np.int32); lv[:, 0] = a0; lv[:, 1] = a1
        for k in range(2, 8): lv[:, k] = np.where(a0 > a1, ((8 - k) * a0 + (k - 1) * a1) // 7, np.where(k < 6, ((6 - k) * a0 + (k - 1) * a1) // 5, 0 if k == 6 else 255))
        img[:, :, 3] = np.take_along_axis(lv, ix, 1).reshape(bh, bw, 4, 4).transpose(0, 2, 1, 3).reshape(bh * 4, bw * 4)
    Image.fromarray(img[:h, :w], 'RGBA').save(p); cut = bool((img[:h, :w, 3] < 128).mean() > 0.02)
    if cut: open(p + '.cut', 'w').close()
    return cut
P = []; U0 = []; U1 = []; TEX = []; LMP = []; CUT = []; ONE = []; nm = 0; stat = collections.Counter()
for mid in mids:
    m = meshgen.parse_mesh(by[mid]); vv = m['verts']; I = np.asarray(m['idx']).astype(np.int64); mat = by[m['groups'][0][4]]; tid = mat.u32(0x1bc)
    if tid not in by: stat['meshes without a picture'] += 1; continue
    alpha = len(mat.data) == 1848 and bool(mat.u32(0x4d4) or mat.u32(0x4e4)); has = save_tex(tid); cut = bool(alpha and has)
    lm = mat.u32(0x1fc) if len(mat.data) > 0x200 else 0; pg = -1
    if (lm & 0xffff0000) == 0xc1ad0000 and lm in by: save_tex(lm); pg = lm
    pos = np.c_[vv['p'][:, 0] - ox, vv['p'][:, 1], -(vv['p'][:, 2] - oz)].astype(np.float32)
    u0 = np.c_[vv['uv0'][:, 0].astype(np.int16) / 32768.0, 1.0 - vv['uv0'][:, 1].astype(np.int16) / 32768.0].astype(np.float32); u1 = np.c_[vv['uv1'][:, 0] / 32768.0, 1.0 - vv['uv1'][:, 1] / 32768.0].astype(np.float32)
    a, b, c = I[:-2].copy(), I[1:-1].copy(), I[2:].copy(); odd = (np.arange(len(a)) % 2) == 1; a[odd], b[odd] = b[odd].copy(), a[odd].copy(); ok = (a != b) & (b != c) & (a != c); t = np.stack([a[ok], b[ok], c[ok]], 1)          # counter-clockwise seen from the front (preview_obj writes c b a: clockwise)
    one = len(mat.data) == 1848 and not mat.u32(0x50c)                 # DSIDE off: the game draws this mesh from its front only (the front / back boards of a tree)
    P.append(pos[t]); U0.append(u0[t]); U1.append(u1[t]); TEX += [tid] * len(t); LMP += [pg] * len(t); CUT += [cut] * len(t); ONE += [bool(one)] * len(t); nm += 1; stat['with a light map' if pg >= 0 else ('cut-outs, no light map' if cut else 'solid, no light map')] += len(t)
np.savez_compressed(os.path.join(out, 'asbuilt.npz'), P=np.concatenate(P), U0=np.concatenate(U0), U1=np.concatenate(U1), TEX=np.array(TEX, np.int64), LMP=np.array(LMP, np.int64), CUT=np.array(CUT, bool), ONE=np.array(ONE, bool), centre=np.asarray(rd['V'][:, rd['hw']], float)[:, [0, 2]] - [ox, oz])
print('ASBUILT %s: %d meshes, %d triangles %s ; drawn from the front only %d ; pictures %d ; light-map pages %d' % (step, nm, len(TEX), dict(stat), int(np.sum(ONE)), len(set(TEX)), len({p for p in LMP if p >= 0})))
