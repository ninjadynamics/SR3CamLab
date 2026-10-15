"""Coloured contact sheet of the classic tiles with their index and current class label (../retex/tile_labels.csv).
    python retex_contact.py   -> ../retex/classic_tiles_contact_colour.png"""
import os, json
import numpy as np
from PIL import Image, ImageDraw
from common import *
import classic_tex, retex

def main():
    idx = json.load(open(os.path.join(retex.RT, 'classic_tiles_index.json'))); lab = retex.labels()
    pages = classic_tex.load_pages(); tiles = classic_tex.usable(pages, classic_tex.materials()); cell = 128; cols = 13; rows = (len(idx) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * (cell + 14)), (30, 30, 50)); dr = ImageDraw.Draw(sheet)
    for i, n in enumerate(idx):
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        if tiles.get(n):
            t = classic_tex.tile(pages, tiles[n]); rgb = classic_tex.tile_rgb(t, tiles[n]).copy()
            if tiles[n]['alpha']: rgb[t == 15] = (200, 0, 200)
            sheet.paste(Image.fromarray(rgb).resize((cell - 2, cell - 2), Image.NEAREST), (x + 1, y + 1))
        dr.text((x + 2, y + cell), '%d %s' % (i, lab.get(n, ('?',))[0]), fill=(255, 255, 0))
    p = os.path.join(retex.RT, 'classic_tiles_contact_colour.png'); sheet.save(p); print(p)

if __name__ == '__main__':
    main()
