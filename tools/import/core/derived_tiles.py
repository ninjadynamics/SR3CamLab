"""Tiles a course and its patch files name that are not in the ROM, made from the vanilla 1995 tiles (<course>/textures) when missing:
    <tile>_dk        the tile at DARK of its brightness, rounded down (roadfill1995 rule T3; gapfill_gen's forest floor)
    sea.tile         course JSON "sea": the tile sea.from scaled per channel by sea.scale, rounded down
They go where the importer looks: <classic>/courses/<game>/<course>/textures and <work>/classic_tex/course<N>/textures.
    python derived_tiles.py <game> <course>
Without numpy since 2026-10-15 (kb 31): a tile's channel values go through bytes.translate tables, int(v * scale) clipped to 0 .. 255,
which is what numpy's (px * DARK).clip(0, 255).astype(np.uint8) gave for each value; the tiles are byte for byte the numpy version's."""
import os, sys, re, glob, json
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
    if game == 'src': C.use_tex(game, course); cfg = dict(C.CFG)          # (the course's folders only: neither the build nor numpy)
    else: cfg = C.use(game, course)
    van = os.path.join(CLASSIC, 'courses', game, cfg.get('gameplay', ''), 'textures')
    dst = [van, os.path.join(WORK, 'classic_tex', 'course%s' % cfg['course'], 'textures')]
    def put(name, img):
        for d in dst:
            os.makedirs(d, exist_ok=True); p = os.path.join(d, name + '.png')
            if not os.path.exists(p): img.save(p)
    def vanilla(tile):
        p = os.path.join(van, tile + '.png')
        return Image.open(p).convert('RGB') if os.path.exists(p) else None
    def scaled(im, scale):
        """each channel c: int(v * scale[c]) clipped to 0 .. 255 (px.astype(float) * scale, .clip(0, 255).astype(np.uint8))"""
        b = im.tobytes(); out = bytearray(len(b))
        for c in range(3): out[c::3] = b[c::3].translate(bytes(min(max(int(v * scale[c]), 0), 255) for v in range(256)))
        return Image.frombytes('RGB', im.size, bytes(out))
    made = []
    for n in sorted(named(cfg)):
        if n.endswith('_dk') and not all(os.path.exists(os.path.join(d, n + '.png')) for d in dst):
            px = vanilla(n[:-3])
            if px is None: log('   %s: no tile %s to darken' % (n, n[:-3])); continue
            put(n, scaled(px, (DARK,) * 3)); made.append(n)
    sea = cfg.get('sea') or {}
    if sea.get('from') and not all(os.path.exists(os.path.join(d, sea['tile'] + '.png')) for d in dst):
        px = vanilla(sea['from'])
        if px is None: log('   sea: no tile %s' % sea['from'])
        else: sc_ = sea['scale']; put(sea['tile'], scaled(px, [float(sc_)] * 3 if isinstance(sc_, (int, float)) else [float(v) for v in sc_])); made.append(sea['tile'])      # (a number or one per channel, as numpy broadcast it)
    log('%s %s: %d derived tiles made%s' % (game, course, len(made), ''.join('\n   ' + m for m in made)))
    return made

if __name__ == '__main__':
    if len(sys.argv) < 3: print(__doc__); sys.exit(1)
    make(sys.argv[1], sys.argv[2])
