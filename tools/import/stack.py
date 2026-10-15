"""The import stack, one course at a time: your own ROM set -> a track installed in SEGA Rally 3.
    python stack.py <game> <course> [options]
Steps (--steps, comma-separated; default all of them, in this order; a step that fails stops the run):
    rom       the 1995 game's files -> the data folder          tools/import/<game>/tracks/rom/rom_import.py
    patch     the course's numbered patch files (in the importer's first pass; off = the course as the ROM has it)
    round     rounding (--round <level>, the recipe's by default; off = flat polygons)
    light     light maps: the polygons to light, collected in the importer's first pass
    rt        ray tracing: the bake of those light maps (C, every worker thread), then their composition
    build     the game files (<work>/out/<name>/Desert4); without light / rt the track is built flat-lit in one pass
    install   into SEGA Rally 3 as a Classic mode alternative (core/install_track.ps1; SR3 Extras switches it in)
Exports (--blend, comma-separated, any of rom, patch, round, rt, build): a .blend of what that step made, in
<work>/blend/<name>/, written beside the run (Blender from the settings; the step does not wait for it unless it is the last).
Other options:
    --name <folder>        the build's name (default stack_<game>_<course>)
    --round <level>        0 = off, 1 / 2 / 4 = R1 / R2 / R4
    --title <text>         the name the game's Classic list shows (install; default from the course JSON)
    --threads <n|all|all_but_one>   overrides the settings
Every line that starts with '@@ ' is for the stack window: '@@ step <name> start', '@@ step <name> done <seconds>',
'@@ step <name> fail <message>', '@@ blend <name> <file>', '@@ done <seconds>'."""
import os, sys, json, time, subprocess, shutil, threading
HERE = os.path.dirname(os.path.abspath(__file__)); CORE = os.path.join(HERE, 'core')
sys.path.insert(0, CORE)
import common
STEPS = ['rom', 'patch', 'round', 'light', 'rt', 'build', 'install']

def say(*a): print('@@ ' + ' '.join(str(x) for x in a), flush=True)

class Run:
    def __init__(self, game, course, steps, blend, name, level, title, threads):
        self.game, self.course, self.steps, self.blend = game, str(course), steps, blend
        self.name = name or 'stack_%s_%s' % (game, course); self.title = title
        cd = common.courses_dir(game); self.recipe = json.load(open(os.path.join(cd, '%s_%s.recipe.json' % (game, course)), encoding='utf-8'))
        self.cfg = json.load(open(os.path.join(cd, '%s_%s.json' % (game, course)), encoding='utf-8'))
        self.level = self.recipe.get('round', {}).get('round', 0) if level is None else int(level)
        self.threads = threads or str(common.threads())
        self.G = os.path.join(common.TMP, 'stack', self.name); os.makedirs(self.G, exist_ok=True)       # the passes' hand-over files
        self.B = os.path.join(common.WORK, 'blend', self.name); self.side = []
        self.env = dict(os.environ, PYTHONPATH=CORE + os.pathsep + os.environ.get('PYTHONPATH', ''), PYTHONIOENCODING='utf-8')

    def sets(self, which):
        """the importer's --set arguments: the recipe's common values, then the step choices, then the pass's own"""
        kv = dict(self.recipe.get('common', {}))
        kv['patch'] = 'patch' in self.steps and kv.get('patch', True)
        if 'round' in self.steps and self.level: kv.update(self.recipe.get('round', {})); kv['round'] = self.level
        else: kv.pop('round', None)
        if which in ('build', 'flat'): kv.update(self.recipe.get('build', {}) if which == 'build' else {})
        out = []
        for k, v in kv.items():
            if k == 'round' and not v: continue
            out += ['--set', '%s=%s' % (k, json.dumps(v, separators=(',', ':')))]
        return out

    def py(self, args, log, env=None, cwd=CORE):
        with open(log, 'w', encoding='utf-8') as f:
            r = subprocess.run([sys.executable, '-u'] + args, cwd=cwd, env=env or self.env, stdout=f, stderr=subprocess.STDOUT)
        if r.returncode:
            tail = open(log, encoding='utf-8', errors='replace').read()[-1500:]
            raise RuntimeError('%s exited %d; the end of %s:\n%s' % (os.path.basename(args[0]), r.returncode, log, tail))

    # ---- steps ----
    def rom(self):
        self.py([os.path.join(HERE, self.game, 'tracks', 'rom', 'rom_import.py'), self.course], os.path.join(self.G, 'rom.log'))
        if 'rom' in self.blend: self.export_blend('rom')

    def collect(self):
        """the importer's first pass: patches, rounding, the polygons to light (and the dumps the exports read)"""
        G = self.G; env = dict(self.env, GAPFILL_DUMP=os.path.join(G, 'faces.pkl'))
        if 'patch' in self.blend and self.level: env['ROUND_IN'] = os.path.join(G, 'patched.pkl')
        self.py(['import_classic.py', self.game, self.course, 'classic', '--norender', '--name', self.name + '_collect'] + self.sets('collect') +
                ['--set', 'seen_sides_file="%s"' % self.j(G, 'lm.sides.npz'), '--set', 'gate_dump="%s"' % self.j(G, 'gate.json'),
                 '--set', 'lm_collect="%s"' % self.j(G, 'lm'), '--set', 'car_shade_dump="%s"' % self.j(G, 'lm.carpages.json')], os.path.join(G, 'collect.log'), env=env)
        for k in ('patch', 'round'):
            if k in self.blend: self.export_blend(k)

    def bake(self):
        G = self.G; b = self.recipe.get('bake', {})
        self.py([os.path.join(CORE, 'rtbake', 'rt_bake_game5.py'), os.path.join(G, 'lm'), os.path.join(G, 'faces.pkl'), b.get('quality', 'slow')], os.path.join(G, 'bake.log'),
                env=dict(self.env, OMP_NUM_THREADS=self.threads))
        self.py([os.path.join(CORE, 'rtbake', 'rt_compose_game.py'), os.path.join(G, 'lm'), os.path.join(G, 'lmA'), str(b.get('compose', 0.34))], os.path.join(G, 'compose.log'))

    def build(self):
        G = self.G; lit = 'light' in self.steps and 'rt' in self.steps
        extra = (['--set', 'car_shade="%s"' % self.j(G, 'lm.carshade.npz'), '--set', 'seen_sides_file="%s"' % self.j(G, 'lm.sides.npz'), '--set', 'lm_table="%s"' % self.j(G, 'lmA')] if lit else [])
        self.py(['import_classic.py', self.game, self.course, 'classic', '--norender', '--name', self.name] + self.sets('build' if lit else 'flat') + extra, os.path.join(G, 'build.log'))
        for k in ('rt', 'build'):
            if k in self.blend: self.export_blend(k)

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

    @staticmethod
    def j(*a): return os.path.join(*a).replace('\\', '/')

    def go(self):
        t0 = time.time(); todo = []
        if 'rom' in self.steps: todo.append(('rom', self.rom))
        lit = 'light' in self.steps and 'rt' in self.steps
        if lit or ({'patch', 'round'} & set(self.blend) and 'build' in self.steps): todo.append(('patch / round / light', self.collect))
        if lit: todo.append(('rt', self.bake))
        if 'build' in self.steps: todo.append(('build', self.build))
        if 'install' in self.steps: todo.append(('install', self.install))
        for nm, fn in todo:
            say('step', nm.replace(' ', ''), 'start'); t = time.time()
            try: fn()
            except Exception as e:
                say('step', nm.replace(' ', ''), 'fail', str(e).split('\n')[0]); print(e, flush=True)
                for th in self.side: th.join()
                return 1
            say('step', nm.replace(' ', ''), 'done', '%.0f' % (time.time() - t))
        for th in self.side: th.join()
        say('done', '%.0f' % (time.time() - t0)); return 0

def main(argv):
    a = list(argv); opt = {}
    for k in ('--steps', '--blend', '--name', '--round', '--title', '--threads'):
        if k in a: i = a.index(k); opt[k] = a[i + 1]; del a[i:i + 2]
    if len(a) < 2: print(__doc__); return 2
    steps = opt.get('--steps', ','.join(STEPS)).split(','); blend = [b for b in opt.get('--blend', '').split(',') if b]
    bad = [s for s in steps if s not in STEPS] + [b for b in blend if b not in ('rom', 'patch', 'round', 'rt', 'build')]
    if bad: print('unknown step or export:', bad); return 2
    return Run(a[0], a[1], steps, blend, opt.get('--name'), opt.get('--round'), opt.get('--title'), opt.get('--threads')).go()

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
