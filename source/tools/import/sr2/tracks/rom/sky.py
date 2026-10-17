"""Sky dome + start/goal banner models of each course -> ../course<N>/sr2_course<N>_sky.obj (+.mtl, textures/), _banners.obj
Sky = model table (0xA4BA8, 16 bytes/entry) index stored in the stage record +8; banners = +12 (start) and +16 (goal)."""
import sys, os, json
import numpy as np
from PIL import Image
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'core')); import common as _cm   # tools/import/settings.json
_TMP = _cm.TMP.replace('\\', '/'); _DATA = _cm.DATA.replace('\\', '/')
SC = _TMP + r"/sr_classic/"
sys.path.insert(1, SC + "scripts"); sys.path.insert(1, SC + "courses/scripts")
from sr2course import *
from skyprobe import model_addr, texinfo, vrom, decode_model
import m3_tex as T
T.O = SC + 'out/m3/'
from extract import MAIN_STAGE
COURSE_SET = {0: 'c_a00000', 1: 'v_90d2ba', 2: 'v_a06d8c', 3: 'v_ad8312', 4: 'v_b9b602'}
def s24(v):
    v >>= 8; return v - 0x1000000 if v & 0x800000 else v
def rgba(t):
    a = np.where(t & 0x8000, 0, 255).astype(np.uint8)
    return np.dstack([((t >> 10) & 31) * 255 // 31, ((t >> 5) & 31) * 255 // 31, (t & 31) * 255 // 31, a]).astype(np.uint8)

def write_obj(path, name, models, sheets, covered, texdir, offset=(0, 0, 0)):
    fo = open(path + '.obj', 'w'); fm = open(path + '.mtl', 'w'); fo.write('# %s  (x, y, -gameZ)\nmtllib %s.mtl\n' % (name, os.path.basename(path)))
    mats = {}; nv = nt = 0; rep = []
    for label, addr in models:
        polys, ok = decode_model(vrom, addr); fo.write('o %s_%06X\n' % (label, addr)); cur = None
        for vs, h in polys:
            ti = texinfo(h)
            if ti:
                page, tx, ty, tw, th, fmt = ti; m = 'tex_p%d_x%04d_y%04d_%dx%d_f%d' % ti
                if m not in mats:
                    mats[m] = 1; t = sheets[page][ty:ty + th, tx:tx + tw]; im = rgba(t); alpha = (im[:, :, 3] == 0).any()
                    (Image.fromarray(im, 'RGBA') if alpha else Image.fromarray(im[:, :, :3], 'RGB')).save(texdir + m + '.png')
                    fm.write('newmtl %s\nKd 0.8 0.8 0.8\nmap_Kd textures/%s.png\n' % (m, m))
                    cov = covered[page][ty:ty + th, tx:tx + tw].mean(); rep.append((m, round(float(cov), 3), int((t != 0).mean() * 100)))
            else:
                col = ((h[4] >> 24) / 255.0, ((h[4] >> 16) & 255) / 255.0, ((h[4] >> 8) & 255) / 255.0); m = 'col_%06X' % (h[4] >> 8)
                if m not in mats: mats[m] = 1; fm.write('newmtl %s\nKd %.3f %.3f %.3f\n' % ((m,) + col))
                tw = th = 32
            if m != cur: fo.write('usemtl %s\n' % m); cur = m
            uvs = 1.0 if (h[1] & 0x40) else 0.125; idx = []; P = []
            for (x, y, z, u, v) in vs:
                p = (x + offset[0], y + offset[1], -(z + offset[2])); P.append(p)
                fo.write('v %.4f %.4f %.4f\nvt %.5f %.5f\n' % (p[0], p[1], p[2], u * uvs / tw, 1.0 - v * uvs / th)); nv += 1; idx.append(nv)
            P = np.array(P); nrm = np.cross(P[1] - P[0], P[2] - P[0]); hn = np.array([s24(h[1]), s24(h[2]), -s24(h[3])], dtype=float)
            if np.dot(nrm, hn) < 0: idx = idx[::-1]
            fo.write('f ' + ' '.join('%d/%d' % (i, i) for i in idx) + '\n')
    fo.close(); fm.close(); return rep

if __name__ == '__main__':
    info = {}
    for k in range(5):
        st = stage(MAIN_STAGE[k]); out = OUT + 'course%d/' % k; os.makedirs(out + 'textures', exist_ok=True)
        sheets, placed = T.build(['common_p0', COURSE_SET[k]])
        covered = np.zeros((2, 1024, 2048), np.uint8)
        for s, a, h in placed:
            if s != 'common_p0': covered[h['page']][h['y']:h['y'] + h['h'], h['x']:h['x'] + h['w']] = 1
        rep = write_obj(out + 'sr2_course%d_sky' % k, 'SEGA Rally 2 course index %d sky dome: model table index %d, VROM 0x%06X' % (k, st['w2'], model_addr(st['w2'])), [('sky', model_addr(st['w2']))], sheets, covered, out + 'textures/')
        rep2 = write_obj(out + 'sr2_course%d_banners' % k, 'start (+12) and goal (+16) banner models', [('start_banner', model_addr(st['w3'])), ('goal_banner', model_addr(st['w4']))], sheets, covered, out + 'textures/')
        print('course', k, 'sky idx', st['w2'], '%06X' % model_addr(st['w2']), 'tiles (name, share covered by the course texture set, % non-zero texels):', rep, '| banners', rep2)
        info[k] = dict(sky_model_index=st['w2'], sky_vrom_addr='0x%06X' % model_addr(st['w2']), sky_tiles=rep, start_banner_index=st['w3'], goal_banner_index=st['w4'], texture_set=COURSE_SET[k])
    json.dump(info, open(OUT + 'work/sky_info.json', 'w'), indent=1)
