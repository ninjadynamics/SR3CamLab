"""All Blender previews (headless):  python render_all.py
  blender_classic_*.png  - the classic course with its ROM textures (classic_tex/course1 OBJ)
  blender_sr3tex_*.png   - step20 (retextured with SR3 textures) DECODED BACK from the built SR3 files
  blender_sr3_step17_*.png - step17 (classic textures inside SR3 files) decoded back, 4 views
  blender_sr3trees_*.png - step23 (step20 + SR3 tree rows) decoded back
  blender_compare_*.png  - classic left / SR3-retextured right, 1280 px wide; 5.. = step20 left / step23 right"""
import os, subprocess, sys
from PIL import Image, ImageDraw
from common import *
import preview_obj
BL = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
TREEVIEWS = sys.argv[1:] or ['road_3']
PV = os.path.join(WORK, 'previews'); CSV = os.path.join(os.path.dirname(WORK), 'classic', 'obj', 'src_course1_centreline.csv')
def render(obj, prefix, views=()):
    r = subprocess.run([BL, '-b', '--factory-startup', '--python', os.path.join(HERE, 'bl_render.py'), '--', obj, prefix, CSV] + [str(v) for v in views],
                       capture_output=True, text=True, timeout=1200)
    print(prefix, 'done' if 'done' in r.stdout else ('FAILED: ' + r.stdout[-400:] + r.stderr[-400:]))
def compare(name, view, left='classic', right='sr3tex', lt='CLASSIC (1995 ROM textures, colours through the game\'s own colour table)', rt='SR3 RETEXTURED (step20, decoded back from the SR3 files)'):
    a = Image.open(os.path.join(PV, 'blender_%s_%s.png' % (left, view))).convert('RGB').resize((640, 360))
    b = Image.open(os.path.join(PV, 'blender_%s_%s.png' % (right, view))).convert('RGB').resize((640, 360))
    W = Image.new('RGB', (1280, 396), (0, 0, 0)); W.paste(a, (0, 36)); W.paste(b, (640, 36)); d = ImageDraw.Draw(W)
    d.text((10, 10), lt, fill=(255, 255, 255))
    d.text((650, 10), rt, fill=(255, 255, 255))
    W.save(os.path.join(PV, 'blender_compare_%s.png' % name))
if __name__ == '__main__':
    render(os.path.join(WORK, 'classic_tex', 'course1', 'src_course1_hi.obj'), 'blender_classic_')          # Mountain; other courses: import_classic.py
    render(preview_obj.main('step20_classic_retextured_sr3_desert4'), 'blender_sr3tex_')
    render(preview_obj.main('step17_classic_scenery_textured_desert4'), 'blender_sr3_step17_', (5, 110, 150, 230))
    render(preview_obj.main('step23_classic_sr3_trees_desert4'), 'blender_sr3trees_')
    for name, view in (('1_start_town', 'road_1'), ('2_rock_section', 'road_4'), ('3_road', 'road_6'), ('4_overview', 'overview')): compare(name, view)
    for k, view in enumerate(TREEVIEWS): compare('%d_sr3_trees' % (5 + k), view, 'sr3tex', 'sr3trees', 'step20: classic tree boards (alpha-tested)', 'step23: SR3 tree row texture on the tree walls')
    for fn in os.listdir(PV):
        if fn.startswith('blender_mountain_'): os.remove(os.path.join(PV, fn))      # superseded by blender_classic_*
    print(sorted(fn for fn in os.listdir(PV) if fn.startswith('blender_')))
