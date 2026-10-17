"""montage.py <dir> <prefix> <out.png>: overview + road_1..8 as a 3x3 sheet (each 640x360)"""
import sys, os
from PIL import Image
d, pre, out = sys.argv[1:4]; names = ['overview'] + ['road_%d' % k for k in range(1, 9)]
W = Image.new('RGB', (1920, 1080))
for i, n in enumerate(names):
    p = os.path.join(d, pre + n + '.png')
    if os.path.exists(p): W.paste(Image.open(p).convert('RGB').resize((640, 360)), ((i % 3) * 640, (i // 3) * 360))
W.save(out)
