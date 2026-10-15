"""Tiles a course and its patch files name that are not in the ROM, made from the vanilla 1995 tiles (<course>/textures) when missing:
    <tile>_dk        the tile at DARK of its brightness, rounded down (roadfill1995 rule T3; gapfill_gen's forest floor)
    sea.tile         course JSON "sea": the tile sea.from scaled per channel by sea.scale, rounded down
They go where the importer looks: <classic>/courses/<game>/<course>/textures and <work>/classic_tex/course<N>/textures.
    python derived_tiles.py <game> <course>"""
import os, sys, re, glob, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
DARK = 0.32                                                           # = roadfill1995.DARK = gapfill_gen.FOREST_DARK

def named(cfg):
    """every material name in the course JSON and its patch files"""
    d = courses_dir(cfg['game']); fs = [os.path.join(d, '%s_%s.json' % (cfg['game'], cfg['course']))] + sorted(glob.glob(os.path.join(d, '%s.%s.patch.*.json' % (cfg['game'], cfg['name']))))
    out = set()
    for f in fs: out |= set(re.findall(r'"((?:tex|col)_[A-Za-z0-9_]+)"', open(f, encoding='utf-8').read()))
    return out

def make(game, course, log=print):
    import course as C
    from PIL import Image
    cfg = C.use(game, course); van = os.path.join(CLASSIC, 'courses', game, cfg.get('gameplay', ''), 'textures')
    dst = [van, os.path.join(WORK, 'classic_tex', 'course%s' % cfg['course'], 'textures')]
    def put(name, rgb):
        for d in dst:
            os.makedirs(d, exist_ok=True); p = os.path.join(d, name + '.png')
            if not os.path.exists(p): Image.fromarray(rgb).save(p)
    def vanilla(tile):
        p = os.path.join(van, tile + '.png')
        return np.asarray(Image.open(p).convert('RGB')).astype(float) if os.path.exists(p) else None
    made = []
    for n in sorted(named(cfg)):
        if n.endswith('_dk') and not all(os.path.exists(os.path.join(d, n + '.png')) for d in dst):
            px = vanilla(n[:-3])
            if px is None: log('   %s: no tile %s to darken' % (n, n[:-3])); continue
            put(n, (px * DARK).clip(0, 255).astype(np.uint8)); made.append(n)
    sea = cfg.get('sea') or {}
    if sea.get('from') and not all(os.path.exists(os.path.join(d, sea['tile'] + '.png')) for d in dst):
        px = vanilla(sea['from'])
        if px is None: log('   sea: no tile %s' % sea['from'])
        else: put(sea['tile'], (px * np.asarray(sea['scale'], float)).clip(0, 255).astype(np.uint8)); made.append(sea['tile'])
    log('%s %s: %d derived tiles made%s' % (game, course, len(made), ''.join('\n   ' + m for m in made)))
    return made

if __name__ == '__main__':
    if len(sys.argv) < 3: print(__doc__); sys.exit(1)
    make(sys.argv[1], sys.argv[2])
