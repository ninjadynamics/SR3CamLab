"""Montage of chosen SR3 textures with a pixel grid (for picking sub-rectangles of atlases).
    python art_grid.py out.png Track:id Track:id ...   (each shown 512 px wide, grid every 1/8 of the texture, labelled 0..8)"""
import os, sys
from PIL import Image, ImageDraw
from common import *
def main(out, items, cell=512, cols=3):
    rows = (len(items) + cols - 1) // cols; W = Image.new('RGB', (cols * (cell + 8), rows * (cell + 24)), (20, 20, 20)); dr = ImageDraw.Draw(W)
    for i, it in enumerate(items):
        trk, tid = it.split(':'); im = Image.open(os.path.join(WORK, 'retex', 'art', trk, tid + '.png')); w, h = im.size
        bg = Image.new('RGBA', im.size, (200, 0, 200, 255)); bg.alpha_composite(im); sc = cell / max(w, h); im2 = bg.convert('RGB').resize((int(w * sc), int(h * sc)))
        x, y = (i % cols) * (cell + 8), (i // cols) * (cell + 24); W.paste(im2, (x, y + 14)); dr.text((x + 2, y + 1), '%s %s %dx%d' % (trk, tid, w, h), fill=(255, 255, 0))
        for k in range(9):
            gx = x + int(k * im2.size[0] / 8); gy = y + 14 + int(k * im2.size[1] / 8)
            dr.line([gx, y + 14, gx, y + 14 + im2.size[1]], fill=(0, 255, 255)); dr.line([x, gy, x + im2.size[0], gy], fill=(0, 255, 255))
            dr.text((gx + 2, y + 15), str(k), fill=(255, 255, 255)); dr.text((x + 2, gy + 1), str(k), fill=(255, 255, 255))
    W.save(os.path.join(WORK, 'retex', out)); print(out)
if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
