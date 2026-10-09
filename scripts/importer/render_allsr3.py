"""Renders of step24 (all-SR3 version): blender_allsr3_*.png and blender_final_*.png (classic colour left, all-SR3 right).
    python render_allsr3.py [step]"""
import os, sys
from PIL import Image, ImageDraw
from common import *
import preview_obj, render_all as RA
STEP = sys.argv[1] if len(sys.argv) > 1 else 'step24_classic_all_sr3_desert4'
if __name__ == '__main__':
    RA.render(preview_obj.main(STEP), 'blender_allsr3_')
    views = ['road_%d' % i for i in range(1, 9)] + ['overview']
    for k, v in enumerate(views):
        a = Image.open(os.path.join(RA.PV, 'blender_classic_%s.png' % v)).convert('RGB'); b = Image.open(os.path.join(RA.PV, 'blender_allsr3_%s.png' % v)).convert('RGB')
        W = Image.new('RGB', (2560, 720 + 44), (0, 0, 0)); W.paste(a, (0, 44)); W.paste(b, (1280, 44)); d = ImageDraw.Draw(W)
        d.text((16, 14), 'SEGA RALLY CHAMPIONSHIP (1995) - Mountain course, original textures and colours', fill=(255, 255, 255))
        d.text((1296, 14), 'the same course rebuilt as a SEGA RALLY 3 track, all textures from SR3 (%s)' % STEP.split('_')[0], fill=(255, 255, 255))
        W.save(os.path.join(RA.PV, 'blender_final_%d_%s.png' % (k + 1, v)))
    print('done')
