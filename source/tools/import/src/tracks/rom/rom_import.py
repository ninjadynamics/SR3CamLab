"""SEGA Rally Championship: everything the importer reads from the 1995 game, made from your own srallyc.zip (settings 'roms').
    python rom_import.py [course numbers, default 1] [--only stage,stage,...]
Stages, in order (each one's files are listed in STAGES):
    regions    the ROM chips -> region images                     <work>/tmp/m2/*.bin                       (m2_build.py)
    colour     palette, luma RAM, colour translation table        <work>/tmp/m2/*.npy  (core: m2colour.py, m2xlat.py: the game's
               own routines run in the i960 interpreter)
    collision  collision polygons and centre lines, all courses   <classic>/obj/                             (m2_collision.py)
    courses    visual objects, sky, low detail, tiles, props      <classic>/courses/src/course<N>_<name>/   (src_all.py, all four:
               the gameplay stage needs every course folder)
    gameplay   start grid, sections, AI line, pace notes          .../gameplay.json                          (m2_gameplay.py)
    export     the importer's own copy of the course              <work>/classic_tex/course<N>/              (core: classic_tex.py)
    gates      the 1995 checkpoint and finish gates               .../src_course<N>_gates.obj + tiles        (core: gates1995.py)
    derived    tiles the course and its patches name that the ROM does not hold: dark copies, the sea   (core: derived_tiles.py)
    labels     the retexture labels shipped beside the course JSON -> <work>/retex/ (only when there are none: yours are kept)
    times      checkpoint times, labelled pace notes              <classic>/sr2_gameplay/src/                (src_leftovers.py)
    hd         the optional HD texture folder, empty              .../textures_hd/                           (core: hd_textures.py)
Nothing outside the data folder is written."""
import os, sys, shutil, subprocess, time, glob
HERE = os.path.dirname(os.path.abspath(__file__)); CORE = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'core'))
sys.path.insert(0, CORE)
import common
NAMES = {1: 'mountain', 2: 'desert', 3: 'lakeside', 4: 'forest'}

def run(script, *args, cwd=HERE):
    """one tool as its own process (most of them do their work at import time and keep module state)"""
    env = dict(os.environ, PYTHONPATH=CORE + os.pathsep + os.environ.get('PYTHONPATH', ''))
    r = subprocess.run([sys.executable, script] + [str(a) for a in args], cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode: raise SystemExit('%s failed:\n%s' % (script, (r.stdout + r.stderr)[-3000:]))
    return r.stdout

def course_dir(n): return os.path.join(common.CLASSIC, 'courses', 'src', 'course%d_%s' % (n, NAMES[n]))

def regions(courses):
    import m2_build; m2_build.build()
def colour(courses):
    for f in ('colorxlat.npy', 'lumaram.npy', 'palette.npy'):          # the routines write their tables only when they are not there
        p = os.path.join(common.TMP, 'm2', f)
        if os.path.exists(p): os.remove(p)
    run('m2xlat.py', cwd=CORE); run('m2colour.py', cwd=CORE)
def collision(courses):
    run('m2_collision.py')
def courses_(courses):
    run('src_all.py', 1, 2, 3, 4)
    for n in (1, 2, 3, 4):                                             # the course folder keeps its own copy of the centre line and collision
        for k in ('centreline.csv', 'collision.obj'):
            shutil.copy2(os.path.join(common.CLASSIC, 'obj', 'src_course%d_%s' % (n, k)), course_dir(n))
def gameplay(courses):
    run('m2_gameplay.py')
def export(courses):
    for n in courses: run('-c', 'import course, classic_tex; course.use_tex("src", "%d"); classic_tex.main()' % n, cwd=CORE)      # (use_tex: the export's folders only, not the whole build)
def gates(courses):
    for n in courses:
        if n == 1: run('gates1995.py', n, cwd=CORE)                     # the gate table is known for Mountain only (gates1995.TABLES)
def derived(courses):
    for n in courses: run('derived_tiles.py', 'src', n, cwd=CORE)
def labels(courses):
    for n in courses:
        src = os.path.join(common.courses_dir('src'), 'src_%d.tile_labels.csv' % n)
        dst = os.path.join(common.WORK, 'retex', '' if n == 1 else 'src_%d' % n, 'tile_labels.csv')     # where course.use() points retex
        if os.path.exists(src) and not os.path.exists(dst): os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(src, dst)
def times(courses):
    run('src_leftovers.py')
def hd(courses):
    for n in courses: run('hd_textures.py', 'src', n, cwd=CORE)

STAGES = [('regions', regions), ('colour', colour), ('collision', collision), ('courses', courses_), ('gameplay', gameplay),
          ('export', export), ('gates', gates), ('derived', derived), ('labels', labels), ('times', times), ('hd', hd)]

def main(argv):
    only = None
    if '--only' in argv: k = argv.index('--only'); only = argv[k + 1].split(','); argv = argv[:k] + argv[k + 2:]
    courses = [int(a) for a in argv] or [1]
    zp = common.rom_zip('srallyc')
    if not os.path.exists(zp): raise SystemExit('no ROM set at %s (settings "roms" = the folder with your srallyc.zip)' % zp)
    print('SEGA Rally Championship from %s -> %s, courses %s' % (zp, common.DATA, courses), flush=True)
    t0 = time.time()
    for name, fn in STAGES:
        if only and name not in only: continue
        t = time.time(); fn(courses); print('  %-9s %6.1f s' % (name, time.time() - t), flush=True)
    print('done in %.0f s' % (time.time() - t0))

if __name__ == '__main__':
    main(sys.argv[1:])
