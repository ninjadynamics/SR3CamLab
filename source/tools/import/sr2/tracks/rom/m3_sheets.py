"""SEGA Rally 2: per-course texture sheets (PNG) and per-material tiles named like the OBJ materials.
    python m3_sheets.py  -> ../sr2/course<N>/sheets/*.png, ../sr2/course<N>/textures/<material>.png"""
import os, re, numpy as np
from PIL import Image
import m3_tex as T
COURSE_SET = {0: 'c_a00000', 1: 'v_90d2ba', 2: 'v_a06d8c', 3: 'v_ad8312', 4: 'v_b9b602'}
def rgba(t):
    a = np.where(t & 0x8000, 0, 255).astype(np.uint8)
    return np.dstack([((t >> 10) & 31) * 255 // 31, ((t >> 5) & 31) * 255 // 31, (t & 31) * 255 // 31, a]).astype(np.uint8)
def tile_image(sheets, page, x, y, w, h):
    t = sheets[page][y:y + h, x:x + w]; im = rgba(t)
    return (Image.fromarray(im, 'RGBA') if (im[:, :, 3] == 0).any() else Image.fromarray(im[:, :, :3], 'RGB')), bool((im[:, :, 3] == 0).any())
if __name__ == '__main__':
    # check against the user's save state (menu): common page 0 set
    sheets, placed = T.build(['common_p0']); st = np.fromfile(T.O + 'srally2_st0_texram.bin', '<u2').reshape(2048, 2048)
    same = tot = 0
    for s, a, h in placed:
        A = sheets[0][h['y']:h['y'] + h['h'], h['x']:h['x'] + h['w']]; B = st[h['y']:h['y'] + h['h'], h['x']:h['x'] + h['w']]; tot += 1; same += bool((A == B).all())
    print('common page-0 set vs save-state texture RAM: %d of %d rectangles identical' % (same, tot))
    for ci, sn in COURSE_SET.items():
        out = '../sr2/course%d' % ci; os.makedirs(out + '/sheets', exist_ok=True); os.makedirs(out + '/textures', exist_ok=True)
        sheets, placed = T.build(['common_p0', sn])
        for p in (0, 1): Image.fromarray(rgba(sheets[p])[:, :, :3]).save(out + '/sheets/sheet%d_2048x1024.png' % p)
        n = na = 0
        for r in sorted(T.course_rects(ci)):
            im, al = tile_image(sheets, *r[:5]); im.save(out + '/textures/tex_p%d_x%04d_y%04d_%dx%d_f%d.png' % r); n += 1; na += al
        print('course %d: set %s, %d records placed, %d tiles (%d with transparent texels)' % (ci, sn, len(placed), n, na))
