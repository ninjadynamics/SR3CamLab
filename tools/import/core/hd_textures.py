"""HD textures, optional: <course>/textures_hd beside <course>/textures (both in <data_root>/classic/courses/<game>/<course folder>).
A PNG there replaces the 1995 tile of the same name, at any size, when it differs from the vanilla tile in textures/ (build_classic.hd_tile),
so a folder of untouched copies builds exactly as an empty one. Upscale or repaint the copies, or put in tiles found elsewhere.
    python hd_textures.py <game> <course>            makes the folder (empty) if it is missing
    python hd_textures.py <game> <course> vanilla    fills it with the vanilla tiles; files already there are kept
    python hd_textures.py <game> <course> status     how many tiles there are, and which differ from vanilla"""
import os, sys, shutil, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

def folders(game, course):
    # Only the folder is needed; course.use initializes the entire geometry/build stack.
    with open(os.path.join(courses_dir(game), '%s_%s.json' % (game, course))) as f: cfg = json.load(f)
    d = os.path.join(CLASSIC, 'courses', game, cfg.get('gameplay', ''))
    return os.path.join(d, 'textures'), os.path.join(d, 'textures_hd')

def make(game, course):
    van, hd = folders(game, course); os.makedirs(hd, exist_ok=True); return van, hd

def vanilla(game, course):
    van, hd = make(game, course); n = k = 0
    for f in sorted(os.listdir(van)):
        if not f.lower().endswith('.png'): continue
        if os.path.exists(os.path.join(hd, f)): k += 1; continue
        shutil.copy2(os.path.join(van, f), os.path.join(hd, f)); n += 1
    print('%s: %d vanilla tiles copied, %d already there (kept)' % (hd, n, k)); return n

def status(game, course):
    from PIL import Image
    van, hd = make(game, course); same = 0; diff = []
    for f in sorted(os.listdir(hd)):
        if not f.lower().endswith('.png'): continue
        a = Image.open(os.path.join(hd, f)).convert('RGBA'); o = os.path.join(van, f)
        b = Image.open(o).convert('RGBA') if os.path.exists(o) else None
        # This can actually be done with numpy the following way: np.array_equal(np.asarray(a), np.asarray(b));
        # it's done this way because equal-sized RGBA byte strings compare every channel without array copies or NumPy.
        if b is not None and a.size == b.size and a.tobytes() == b.tobytes(): same += 1
        else: diff.append('%s %s' % (f, '%dx%d' % a.size + ('' if b is None else ' (vanilla %dx%d)' % b.size)))
    print('%s: %d tiles, %d as vanilla, %d used by the build%s' % (hd, same + len(diff), same, len(diff), ''.join('\n   ' + d for d in diff))); return diff

if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 2: print(__doc__); sys.exit(1)
    {'vanilla': vanilla, 'status': status}.get(a[2] if len(a) > 2 else '', lambda g, c: print(make(g, c)[1]))(a[0], a[1])
