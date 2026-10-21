"""The import stack, one course at a time: your own ROM set -> a track installed in SEGA Rally 3.
    python stack.py <game> <course> [options]
Steps (--steps, comma-separated; default all of them, in this order; a step that fails stops the run):
    unzip     always first, whatever --steps says: the course's patch files, shipped as one zip beside the course settings, unpacked
              beside it (core/patchzip.py; a patch file changed there since it was unpacked is kept)
    rom       the 1995 game's files -> the data folder          tools/import/<game>/tracks/rom/rom_import.py
    light     the importer's first pass: the patch chain, the rounding, and the polygons to light laid out on light-map pages
    rt        ray tracing: the bake of those light maps (C, every worker thread), then their composition
    build     the game files (<work>/out/<name>/Desert4): the importer's second pass, with the baked light of this run or of an
              earlier one (its files in <work>/tmp/stack/<name>); flat-lit when there is none, or with --flat
    install   into SEGA Rally 3 as a Classic mode alternative (core/install_track.ps1; SR3 Extras switches it in)
Settings of every pass (a bake remembers the ones it was made with; a build that would use it with others is refused):
    --patch on|off         the course's numbered patch files (default on; off = the course as the ROM gives it)
    --round <level>        0 = off, 1 / 2 / 4 = R1 / R2 / R4 (default: the recipe's)
    --flat                 build flat-lit (no light maps), whatever has been baked
Exports (--blend, comma-separated, any of rom, patch, round, rt, build): a .blend of what that step made, in
<work>/blend/<name>/, written beside the run (Blender from the settings). patch and round come from the first pass's dumps:
asking for them runs that pass.
Other options:
    --name <folder>        the build's name (default stack_<game>_<course>)
    --title <text>         the name the game's Classic list shows (install; default from the course JSON)
    --threads <n|all|all_but_one>   overrides the settings
Every line that starts with '@@ ' is for the stack window: '@@ step <name> start', '@@ step <name> done <seconds>',
'@@ step <name> fail <message>', '@@ blend <name> <file>', '@@ done <seconds>'."""
import os, sys, json, time, subprocess, shutil, threading
HERE = os.path.dirname(os.path.abspath(__file__)); CORE = os.path.join(HERE, 'core')
sys.path.insert(0, CORE)
import common, patchzip
common.PATCHZIP_AUTO = False                                          # (this process unpacks in its own step, with its own log line)
STEPS = ['rom', 'light', 'rt', 'build', 'install']
OLD = {'patch', 'round'}                                              # (accepted in --steps and ignored: they are settings now)

def say(*a): print('@@ ' + ' '.join(str(x) for x in a), flush=True)

class Run:
    def __init__(self, game, course, steps, blend, name=None, level=None, title=None, threads=None, flat=False, patch=True):
        self.game, self.course, self.steps, self.blend = game, str(course), steps, blend
        self.name = name or 'stack_%s_%s' % (game, course); self.title = title; self.flat = flat; self.patch = patch
        cd = common.courses_dir(game); self.recipe = json.load(open(os.path.join(cd, '%s_%s.recipe.json' % (game, course)), encoding='utf-8'))
        self.cfg = json.load(open(os.path.join(cd, '%s_%s.json' % (game, course)), encoding='utf-8'))
        self.level = self.recipe.get('round', {}).get('round', 0) if level is None else int(level)
        self.threads = threads or str(common.threads())
        self.G = os.path.join(common.TMP, 'stack', self.name); os.makedirs(self.G, exist_ok=True)       # the passes' hand-over files
        self.B = os.path.join(common.WORK, 'blend', self.name); self.side = []
        self.env = dict(os.environ, PYTHONPATH=CORE + os.pathsep + os.environ.get('PYTHONPATH', ''), PYTHONIOENCODING='utf-8',
                        OMP_NUM_THREADS=self.threads, OPENBLAS_NUM_THREADS=self.threads)      # every step on the threads the settings give (the bytes do not depend on it: 8 and 32 threads, checked 2026-10-15)

    def choice(self):
        # Material classes control rounding and ray-only tree solids; they are bake inputs.
        import hashlib
        sub = '' if self.game == 'src' and self.course == '1' else '%s_%s' % (self.game, self.course)
        labels = os.path.join(common.WORK, 'retex', sub, 'tile_labels.csv')
        saved = os.path.join(common.courses_dir(self.game), '%s_%s.tile_labels.csv' % (self.game, self.course))
        if not os.path.exists(labels) and os.path.isfile(saved):
            os.makedirs(os.path.dirname(labels), exist_ok=True)
            shutil.copyfile(saved, labels)
        digest = hashlib.sha256(open(labels, 'rb').read()).hexdigest() if os.path.isfile(labels) else None
        return dict(patch=bool(self.patch), round=int(self.level), material_labels_sha256=digest)

    def sets(self, which):
        """the importer's --set arguments: the recipe's common values, then the settings, then the pass's own"""
        kv = dict(self.recipe.get('common', {}))
        kv['patch'] = bool(self.patch) and kv.get('patch', True)
        if self.level: kv.update(self.recipe.get('round', {})); kv['round'] = self.level
        else: kv.pop('round', None)
        if which == 'build': kv.update(self.recipe.get('build', {}))
        out = []
        for k, v in kv.items(): out += ['--set', '%s=%s' % (k, json.dumps(v, separators=(',', ':')))]
        return out

    def py(self, args, log, env=None, cwd=CORE):
        with open(log, 'w', encoding='utf-8') as f:
            r = subprocess.run([sys.executable, '-u'] + args, cwd=cwd, env=env or self.env, stdout=f, stderr=subprocess.STDOUT)
        if r.returncode:
            tail = open(log, encoding='utf-8', errors='replace').read()[-1500:]
            raise RuntimeError('%s exited %d; the end of %s:\n%s' % (os.path.basename(args[0]), r.returncode, log, tail))

    def note(self, what, data=None):
        p = os.path.join(self.G, what + '.json')
        if data is None:
            try: return json.load(open(p))
            except (OSError, ValueError): return None
        json.dump(data, open(p, 'w', newline='\n'))

    # ---- steps ----
    def unzip(self):
        """the course's patch files out of their zip (patchzip.py)"""
        d = common.courses_dir(self.game); r = patchzip.unpack(d)
        print('patches: %s' % ('; '.join('%s %s' % x for x in r) if r else 'up to date (%s)' % (', '.join(p for p in sorted(os.listdir(d)) if p.endswith('.patches.zip')) or 'no zip')), flush=True)

    def rom(self):
        self.py([os.path.join(HERE, self.game, 'tracks', 'rom', 'rom_import.py'), self.course], os.path.join(self.G, 'rom.log'))
        if 'rom' in self.blend: self.export_blend('rom')

    def collect(self):
        """the importer's first pass: patches, rounding, the polygons to light (and the dumps the exports read)"""
        G = self.G; env = dict(self.env, GAPFILL_DUMP=os.path.join(G, 'faces.pkl'))
        if 'patch' in self.blend and self.level: env['ROUND_IN'] = os.path.join(G, 'patched.pkl')
        p = os.path.join(G, 'collected.json')                         # (a failed pass leaves no note behind)
        if os.path.exists(p): os.remove(p)
        self.py(['import_classic.py', self.game, self.course, 'classic', '--norender', '--name', self.name + '_collect'] + self.sets('collect') +
                ['--set', 'seen_sides_file="%s"' % self.j(G, 'lm.sides.npz'), '--set', 'gate_dump="%s"' % self.j(G, 'gate.json'),
                 '--set', 'lm_collect="%s"' % self.j(G, 'lm'), '--set', 'car_shade_dump="%s"' % self.j(G, 'lm.carpages.json')], os.path.join(G, 'collect.log'), env=env)
        self.note('collected', self.choice())
        for k in ('patch', 'round'):
            if k in self.blend: self.export_blend(k)

    def bake(self):
        G = self.G; b = self.recipe.get('bake', {}); c = self.note('collected')
        if c is None: raise RuntimeError('nothing to bake: run the light step first')
        if c != self.choice(): raise RuntimeError('the polygons to light were collected with %s, this run asks for %s: run the light step again' % (c, self.choice()))
        p = os.path.join(G, 'baked.json')
        if os.path.exists(p): os.remove(p)
        self.py([os.path.join(CORE, 'rtbake', 'rt_bake_game5.py'), os.path.join(G, 'lm'), os.path.join(G, 'faces.pkl'), b.get('quality', 'slow')], os.path.join(G, 'bake.log'), env=dict(self.env, RTG_CANOPY=b.get('canopy', 'legacy')))
        self.py([os.path.join(CORE, 'rtbake', 'rt_compose_game.py'), os.path.join(G, 'lm'), os.path.join(G, 'lmA'), str(b.get('compose', 0.34))], os.path.join(G, 'compose.log'))
        self.note('baked', c)

    def build(self):
        G = self.G; lit = False
        if not self.flat:
            b = self.note('baked')
            if b is not None and self.baked():
                if b != self.choice(): raise RuntimeError('the light in %s was baked with %s, this build asks for %s: run light and rt again, or build with --flat' % (G, b, self.choice()))
                lit = True
        if not lit: print('building flat-lit (%s)' % ('--flat' if self.flat else 'no baked light for this build yet'), flush=True)
        extra = (['--set', 'car_shade="%s"' % self.j(G, 'lm.carshade.npz'), '--set', 'seen_sides_file="%s"' % self.j(G, 'lm.sides.npz'), '--set', 'lm_table="%s"' % self.j(G, 'lmA')] if lit else [])
        self.py(['import_classic.py', self.game, self.course, 'classic', '--norender', '--name', self.name] + self.sets('build' if lit else 'flat') + extra, os.path.join(G, 'build.log'))
        for k in ('rt', 'build'):
            if k in self.blend and (k == 'build' or lit): self.export_blend(k)

    def install(self):
        ps = os.path.join(CORE, 'install_track.ps1'); title = self.title or self.cfg.get('title') or self.name
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps, '-Build', os.path.join(common.OUT, self.name, 'Desert4'), '-Title', title],
                           capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode: raise RuntimeError('install_track.ps1 exited %d:\n%s' % (r.returncode, (r.stdout + r.stderr)[-1500:]))

    # ---- .blend exports ----
    def export_blend(self, what):
        """beside the run: a thread per export (Blender runs on its own), joined at the end"""
        if not common.BLENDER or not os.path.exists(common.BLENDER): say('blend', what, 'skipped: no Blender in the settings'); return
        os.makedirs(self.B, exist_ok=True); out = os.path.join(self.B, '%s_%s.blend' % (self.name, what))
        def go():
            try:
                subprocess.run([sys.executable, os.path.join(CORE, 'export_blend.py'), what, self.game, self.course, self.name, self.G, out], cwd=CORE, env=self.env,
                               stdout=open(os.path.join(self.B, what + '.log'), 'w', encoding='utf-8'), stderr=subprocess.STDOUT, check=True)
                say('blend', what, out)
            except Exception as e: say('blend', what, 'failed:', e)
        t = threading.Thread(target=go); t.start(); self.side.append(t)

    def baked(self):
        """the light's files: its composed table, the seen sides and the cars' pages"""
        return all(os.path.exists(os.path.join(self.G, f)) for f in ('lmA.lm.table.npz', 'lmA.lm.pages.npy', 'lm.sides.npz', 'lm.carshade.npz'))

    @staticmethod
    def j(*a): return os.path.join(*a).replace('\\', '/')

    def go(self):
        t0 = time.time(); todo = [('unzip', self.unzip)]                   # (every run: the steps read the patch files)
        if 'rom' in self.steps: todo.append(('rom', self.rom))
        if 'light' in self.steps or {'patch', 'round'} & set(self.blend): todo.append(('light', self.collect))
        if 'rt' in self.steps: todo.append(('rt', self.bake))
        if 'build' in self.steps: todo.append(('build', self.build))
        if 'install' in self.steps: todo.append(('install', self.install))
        say('settings', json.dumps(self.choice()))
        for nm, fn in todo:
            say('step', nm, 'start'); t = time.time()
            try: fn()
            except Exception as e:
                say('step', nm, 'fail', str(e).split('\n')[0]); print(e, flush=True)
                for th in self.side: th.join()
                return 1
            say('step', nm, 'done', '%.0f' % (time.time() - t))
        for th in self.side: th.join()
        say('done', '%.0f' % (time.time() - t0)); return 0

def main(argv):
    a = list(argv); opt = {}; flat = '--flat' in a
    if flat: a.remove('--flat')
    for k in ('--steps', '--blend', '--name', '--round', '--title', '--threads', '--patch'):
        if k in a: i = a.index(k); opt[k] = a[i + 1]; del a[i:i + 2]
    if len(a) < 2: print(__doc__); return 2
    steps = [s for s in opt.get('--steps', ','.join(STEPS)).split(',') if s and s not in OLD]; blend = [b for b in opt.get('--blend', '').split(',') if b]
    bad = [s for s in steps if s not in STEPS] + [b for b in blend if b not in ('rom', 'patch', 'round', 'rt', 'build')] + ([opt['--patch']] if opt.get('--patch', 'on') not in ('on', 'off') else [])
    if bad: print('unknown step, export or setting:', bad); return 2
    return Run(a[0], a[1], steps, blend, opt.get('--name'), opt.get('--round'), opt.get('--title'), opt.get('--threads'), flat, opt.get('--patch', 'on') == 'on').go()

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
