"""FAST LANE FOR RE-AUTHORED TEXTURES (user, 2026-10-08: "every time I update an HD texture I need to rebake? Can't I just restart the game?").

The game reads pictures from the track's own files, so a changed PNG in <course>/textures_hd needs them rewritten - but only the pictures:
nothing of the track's shape or baked light depends on them. Every build writes texmap.json beside its files (which texture of the file
shows which tile, and how it was made); this tool opens the INSTALLED tracks, rewrites the textures whose tile changed, and saves them.

    python texfast.py            once: every installed Classic alternative that has a texmap.json
    python texfast.py --watch    stays on and does it whenever a PNG in textures_hd is saved

Restart the game (PLAY.bat) to see the result. The game must be closed while a track is rewritten (it holds the files open).
Covered: scenery tiles, cut-outs, gate pictures, and the pictures the importer composes from two tiles (lettering on its panel).
Not covered: the road's tarmac pieces and anything whose shape or see-through outline decides geometry."""
import os, sys, json, time, hashlib, glob, struct, subprocess
import numpy as np

TRACKS = r'F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally\Main_release'
FILES = {'scenery': 'desert4_master_gfx_xdata.sbf', 'finish': 'des_track_route4_game_objects_gfx_data.sbf'}

def sha(p): return hashlib.sha1(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else ''
def hd_hashes(extra_tex): return {os.path.basename(p)[:-4]: sha(p) for p in glob.glob(os.path.join(extra_tex + '_hd', '*.png'))}

def save_map(out_dir, BC, OB, log=print):
    """called at the end of a build"""
    if not os.path.isdir(out_dir) or not BC.TEXMAP: return
    rec = {nm: [k[0], k[1], [float(x) for x in k[2]], (None if k[3] is None else [float(x) for x in k[3]])] for nm, k in OB.RECIPES.items()}
    used = {n: h for n, h in hd_hashes(BC.EXTRA_TEX).items() if BC.HD_USED.get(n) is not None} if BC.EXTRA_TEX else {}
    json.dump(dict(extra_tex=BC.EXTRA_TEX, scenery={str(k): v for k, v in BC.TEXMAP.items()}, finish={str(k): v for k, v in BC.TEXMAP_FINISH.items()}, recipes=rec, hd=used), open(os.path.join(out_dir, 'texmap.json'), 'w'))
    log('       texmap.json: %d scenery textures, %d of the finish gate, %d composed recipes, %d re-authored tiles in use' % (len(BC.TEXMAP), len(BC.TEXMAP_FINISH), len(rec), len(used)))

class Pix:
    """a tile's picture as the build would read it now: the HD file, the 1995 tile, or a composed picture made again from its two tiles"""
    def __init__(self, BC, OB, recipes): self.BC = BC; self.OB = OB; self.rec = recipes; self.memo = {}
    def __call__(self, name):
        name = str(name).split('|')[0]
        if name not in self.memo:
            if name in self.rec:
                lo, up, T, rect = self.rec[name]; self.memo[name] = self.OB._recipe(lo, up, np.array(T, float).reshape(3, 2), self, None if rect is None else tuple(rect))
            else: self.memo[name] = self.BC.tile_pixels(name)
        return self.memo[name]
    def base(self, name, seen=None):
        """the 1995 tiles a picture is made of"""
        name = str(name).split('|')[0]
        if name not in self.rec: return {name}
        return self.base(self.rec[name][0]) | self.base(self.rec[name][1])

def refresh(slot_dir, log=print, force=False):
    import build_classic as BC, overlay_bake as OB, sbfw
    mp = os.path.join(slot_dir, 'texmap.json')
    if not os.path.exists(mp): return None
    M = json.load(open(mp)); BC.EXTRA_TEX = M['extra_tex']; BC.HD_USED.clear(); BC.BAKED.clear(); now = hd_hashes(BC.EXTRA_TEX); was = M.get('hd', {})
    changed = {n for n in set(now) | set(was) if now.get(n, '') != was.get(n, '')}                 # saved again, added or taken away since this track's pictures were written
    changed = {n for n in changed if BC.hd_tile(n) is not None or n in was}                         # (an untouched copy of the original is no change)
    if not changed and not force: return 0
    pix = Pix(BC, OB, M['recipes']); done = 0; t0 = time.time()
    for part, fn in FILES.items():
        todo = {int(k): v for k, v in M.get(part, {}).items() if force or (pix.base(v['tile']) & changed)}
        if not todo: continue
        path = os.path.join(slot_dir, fn); f = sbfw.read_sbf(path); by = {c.id: c for c in f.chunks}
        for tid, r in todo.items():
            old = by.get(tid); px = pix(r['tile'])
            if old is None or px is None: continue
            rgb, hole = px; rgb = np.asarray(rgb); rgb = rgb if rgb.ndim == 3 else np.dstack([rgb] * 3)
            if r.get('unlit'): rgb = np.clip(rgb.astype(np.float32) * r.get('unlit_gain', 1.0), 0, 255).astype(np.uint8)
            if part == 'finish': BC.VIVID = tuple(r['vivid']) if r.get('vivid') else None; BC.SCENE_GAIN = None; rgb = BC.vivid(rgb); BC.VIVID = None      # (finishgate.py colours its tiles itself)
            s = int(r.get('sharp', 1))
            if s > 1: hole = np.repeat(np.repeat(hole, s, 0), s, 1) if hole is not None and hole.shape == rgb.shape[:2] else hole; rgb = np.repeat(np.repeat(rgb, s, 0), s, 1)
            if part == 'scenery':
                BC.VIVID = tuple(r['vivid']) if r.get('vivid') else None; BC.SCENE_GAIN = np.array(r['gain'], float) if r.get('gain') is not None else None; BC._NO_GAIN[0] = bool(r.get('unlit'))
            if r['cut']:
                hole = hole if hole is not None and hole.shape == rgb.shape[:2] else np.zeros(rgb.shape[:2], bool)
                if part == 'scenery' and (~hole).any() and hole.any(): rgb = rgb.copy(); rgb[hole] = rgb[~hole].mean(0).astype(np.uint8)
                new = BC.make_texture_dxt5(old, tid, np.ascontiguousarray(rgb), hole)
            else: new = BC.make_texture(old, tid, np.ascontiguousarray(rgb), None)
            old.data = new.data; done += 1                             # (the old texture is the template: its header - wrap modes and all - is kept, only size and pixels change)
        BC.VIVID = None; BC.SCENE_GAIN = None; BC._NO_GAIN[0] = False
        tmp = path + '.new'; open(tmp, 'wb').write(sbfw.write_sbf(f, compress=True, layout='auto', level=1)); g = sbfw.read_sbf(tmp)
        assert len(g.chunks) == len(f.chunks) and all(a.data == c.data and a.fix == c.fix and a.ref == c.ref for a, c in zip(g.chunks, f.chunks)), 'the rewritten file does not read back the same'
        os.replace(tmp, path)
    M['hd'] = {n: h for n, h in now.items() if BC.hd_tile(n) is not None}; json.dump(M, open(mp, 'w'))
    log('%s: %d textures rewritten for %d changed tiles (%s) in %.1f s' % (os.path.basename(os.path.dirname(slot_dir)), done, len(changed), ', '.join(sorted(changed))[:160], time.time() - t0)); return done

def game_running():
    try: return 'Rally.exe' in subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Rally.exe'], capture_output=True, text=True).stdout
    except Exception: return False

def all_slots(log=print, force=False):
    slots = sorted(glob.glob(os.path.join(TRACKS, 'track*', 'Desert4')))
    have = [s for s in slots if os.path.exists(os.path.join(s, 'texmap.json'))]
    if not have: log('no installed track has a texmap.json yet (it is written by builds from 2026-10-08 on)'); return
    if game_running(): log('the game is running: close it first, its track files cannot be rewritten while it is open'); return
    for s in have:
        try:
            r = refresh(s, log, force)
            if r == 0: log('%s: nothing changed' % os.path.basename(os.path.dirname(s)))
        except Exception as e: log('%s: FAILED %s: %s' % (os.path.basename(os.path.dirname(s)), type(e).__name__, e))

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if '--watch' in sys.argv:
        import build_classic as BC
        last = None; print('watching textures_hd ... (Ctrl+C to stop)', flush=True)
        while True:
            ms = sorted(glob.glob(os.path.join(TRACKS, 'track*', 'Desert4', 'texmap.json')))
            ex = json.load(open(ms[0]))['extra_tex'] if ms else None
            cur = tuple(sorted((p, os.path.getmtime(p)) for p in glob.glob(os.path.join(ex + '_hd', '*.png')))) if ex else None
            if cur != last:
                if last is not None: time.sleep(1.0); all_slots(lambda s: print(time.strftime('%H:%M:%S'), s, flush=True))      # (a second for the editor to finish writing)
                last = tuple(sorted((p, os.path.getmtime(p)) for p in glob.glob(os.path.join(ex + '_hd', '*.png')))) if ex else None
            time.sleep(1.0)
    else: all_slots(force='--force' in sys.argv)
