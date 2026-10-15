"""How far the light-map pages of a bake with fewer sky rays are from the full bake's, against what the game's texture compression (DXT1) does to the
full bake's own pages anyway.   python turns_compare.py <full lmA> <fewer lmA> <pack of the bake (lm)> <out picture>     (from the importer folder)"""
import sys, os
import numpy as np
sys.path.insert(0, os.getcwd())
import fastdxt, build_classic as BC
A = np.load(sys.argv[1] + '.lm.pages.npy', mmap_mode='r'); B = np.load(sys.argv[2] + '.lm.pages.npy', mmap_mode='r'); K = np.load(sys.argv[3] + '.pack.npz'); OUT = sys.argv[4]
def undxt1(blob, h, w):
    b = np.frombuffer(blob, np.dtype([('c0', '<u2'), ('c1', '<u2'), ('ix', '<u4')])); c0 = b['c0'].astype(np.int32); c1 = b['c1'].astype(np.int32)
    un = lambda v: np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31], 1)
    p0 = un(c0); p1 = un(c1); four = (c0 > c1)[:, None]; p2 = np.where(four, (2 * p0 + p1) // 3, (p0 + p1) // 2); p3 = np.where(four, (p0 + 2 * p1) // 3, 0); pal = np.stack([p0, p1, p2, p3], 1)
    ix = (b['ix'][:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3; px = pal[np.arange(len(b))[:, None], ix]      # n, 16, 3
    return px.reshape(h // 4, w // 4, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(h, w, 3).astype(np.uint8)
used = np.zeros(A.shape[:3], bool)
for pg, x, y, u, v in zip(K['page'], K['x0'], K['y0'], K['nu'], K['nv']): used[pg - 1, y:y + (v + 3) // 4 * 4, x:x + (u + 3) // 4 * 4] = True
dAB = []; dAC = []; dBC = []
for p in range(len(A)):
    a = np.asarray(A[p]); b = np.asarray(B[p]); m = used[p]; ca = undxt1(fastdxt.dxt1_rgb(a, None, BC._dxt1_rgb_np), a.shape[0], a.shape[1]); cb = undxt1(fastdxt.dxt1_rgb(b, None, BC._dxt1_rgb_np), a.shape[0], a.shape[1])
    dAB.append(np.abs(a[m].astype(np.int16) - b[m]).max(1)); dAC.append(np.abs(a[m].astype(np.int16) - ca[m]).max(1)); dBC.append(np.abs(ca[m].astype(np.int16) - cb[m]).max(1))
dAB = np.concatenate(dAB); dAC = np.concatenate(dAC); dBC = np.concatenate(dBC)
st = lambda d: 'mean %.2f, 99 %% under %d, 99.9 %% under %d, largest %d ; texels off by more than 4: %.3f %%, by more than 8: %.4f %%' % (d.mean(), np.percentile(d, 99), np.percentile(d, 99.9), d.max(), 100.0 * (d > 4).mean(), 100.0 * (d > 8).mean())
print('texels compared: %.1f million (of 255 grey levels, the largest of the three colours)' % (len(dAB) / 1e6))
print('   fewer sky rays against the full bake, before compression:   ' + st(dAB))
print('   the full bake against ITSELF after the game\'s compression:   ' + st(dAC))
print('   fewer sky rays against the full bake, both as the game has them (compressed): ' + st(dBC))
# a picture: the region of a page with the most shadow edges, full / fewer / difference x 8
from PIL import Image
best = None
for p in range(len(A)):
    a = np.asarray(A[p]).astype(np.int16); g = np.abs(np.diff(a[..., 1], axis=1))
    for y in range(0, 2048 - 512, 256):
        for x in range(0, 2048 - 512, 256):
            if used[p, y:y + 512, x:x + 512].mean() > 0.9:
                s = float(g[y:y + 512, x:x + 511].mean())
                if best is None or s > best[0]: best = (s, p, y, x)
s, p, y, x = best; a = np.asarray(A[p])[y:y + 512, x:x + 512]; b = np.asarray(B[p])[y:y + 512, x:x + 512]; d = np.clip(np.abs(a.astype(np.int16) - b) * 8, 0, 255).astype(np.uint8)
im = Image.new('RGB', (512 * 3 + 16, 512), (40, 40, 40)); im.paste(Image.fromarray(a), (0, 0)); im.paste(Image.fromarray(b), (520, 0)); im.paste(Image.fromarray(d), (1040, 0)); im = im.resize((im.size[0] * 2, im.size[1] * 2), Image.NEAREST); im.save(OUT)
print('picture: page %d at (%d, %d): full bake | a third of the sky rays | difference x 8 -> %s' % (p + 1, x, y, OUT))
