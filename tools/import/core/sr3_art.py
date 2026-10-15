"""Survey of SR3's own art for the all-SR3 retexture: every texture (kind 4) of a track file as PNG + contact sheets.
    python sr3_art.py Track [file suffix]     -> ../retex/art/<Track>/<id>.png, ../retex/art_<Track>_<n>.png"""
import os, sys, struct, json
import numpy as np
from PIL import Image, ImageDraw
from common import *
import sbfw, preview_obj
RT = os.path.join(WORK, 'retex')

def full_png(c, path):
    """like preview_obj.texture_png but full size, alpha kept"""
    d = c.data; w, h = struct.unpack_from('<II', d, 8); four = d[48 + 80:48 + 84]; base = 48 + 124; bw, bh = max(1, w // 4), max(1, h // 4)
    if four == b'DXT1': img = preview_obj.dxt_colour(d[base:base + 8 * bw * bh], bw, bh)
    elif four in (b'DXT5', b'DXT3'):
        raw = np.frombuffer(d, np.uint8, 16 * bw * bh, base).reshape(-1, 16); img = preview_obj.dxt_colour(raw[:, 8:].tobytes(), bw, bh, punch=False)
        if four == b'DXT5':
            ab = raw[:, :8].astype(np.uint64); a0 = ab[:, 0].astype(np.int32); a1 = ab[:, 1].astype(np.int32); bits = sum(ab[:, 2 + k] << np.uint64(8 * k) for k in range(6))
            ix = ((bits[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))) & np.uint64(7)).astype(np.int32)
            lv = np.zeros((len(ab), 8), np.int32); lv[:, 0] = a0; lv[:, 1] = a1
            for k in range(2, 8): lv[:, k] = np.where(a0 > a1, ((8 - k) * a0 + (k - 1) * a1) // 7, np.where(k < 6, ((6 - k) * a0 + (k - 1) * a1) // 5, 0 if k == 6 else 255))
            img[:, :, 3] = np.take_along_axis(lv, ix, 1).reshape(bh, bw, 4, 4).transpose(0, 2, 1, 3).reshape(bh * 4, bw * 4)
    else: return None
    Image.fromarray(img[:h, :w], 'RGBA').save(path); return (w, h, four.decode(), float((img[:h, :w, 3] < 128).mean()))

def main(track, suffix='master_gfx_xdata', minw=128):
    f = sbfw.read_sbf(track_files(os.path.join(TRACKS, track))[suffix]); out = os.path.join(RT, 'art', track); os.makedirs(out, exist_ok=True); info = {}
    for c in f.kinds(4):
        w, h = struct.unpack_from('<II', c.data, 8)
        if w < minw or h < 64: continue
        r = full_png(c, os.path.join(out, '%08x.png' % c.id))
        if r: info['%08x' % c.id] = r
    json.dump(info, open(os.path.join(out, 'index_%s.json' % suffix), 'w'))
    ids = sorted(info, key=lambda k: (-info[k][0] * info[k][1], k)); cols, cell, per = 8, 200, 40
    for pg in range(0, len(ids), per):
        part = ids[pg:pg + per]; W = Image.new('RGB', (cols * cell, ((len(part) + cols - 1) // cols) * (cell + 14)), (60, 30, 60)); dr = ImageDraw.Draw(W)
        for i, k in enumerate(part):
            im = Image.open(os.path.join(out, k + '.png')); bg = Image.new('RGBA', im.size, (200, 0, 200, 255)); bg.alpha_composite(im)
            x, y = (i % cols) * cell, (i // cols) * (cell + 14); W.paste(bg.convert('RGB').resize((cell - 2, cell - 2)), (x, y))
            dr.text((x + 2, y + cell - 1), '%s %dx%d' % (k, info[k][0], info[k][1]), fill=(255, 255, 0))
        W.save(os.path.join(RT, 'art_%s_%s_%d.png' % (track, suffix.split('_')[0] if suffix != 'master_gfx_xdata' else 'gfx', pg // per + 1)))
    print(track, suffix, len(ids), 'textures')

if __name__ == '__main__':
    main(*sys.argv[1:3])
