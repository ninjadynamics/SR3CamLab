"""Build/run isolated frontend component tests; does not launch or modify SR3.

Usage: python -B source/tools/sr3mods/test_frontend.py --out scratchpad/frontend-tests
"""
import argparse
from pathlib import Path
import sys

import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    source = here.parents[1]
    for name, entry, units in [
        ('video_pool', 'video_pool_test_entry', ['test_video_pool.c']),
        ('frontend_video', 'frontend_video_test_entry', ['test_frontend_video.c']),
        ('frontend_model', 'frontend_model_test_entry',
         ['frontend_model.c', 'pc_json.c', 'test_frontend_model.c']),
        ('frontend_native', 'frontend_native_test_entry',
         ['frontend_model.c', 'pc_json.c', 'test_frontend_native.c']),
    ]:
        out = (args.out / name).resolve()
        out.mkdir(parents=True, exist_ok=True)
        sources = [here / unit for unit in units]
        sources += [source / 'tools/x86/builtins.c', source / 'standalone/ucrt_stdio.c']
        objects = []
        for src in sources:
            obj = out / (src.stem + '.o')
            build.run([build.GCC, *build.X86, '-I', str(here), '-c', str(src), '-o', str(obj)])
            objects.append(str(obj))
        imp = out / 'imp'
        imports = ['--out', str(imp)]
        for dll in ('kernel32', 'ucrtbase', 'user32', 'ole32'):
            imports += ['--dll', dll]
        if build.implib.main(imports + objects):
            raise SystemExit('Unresolved frontend test imports')
        libs = ['-l' + p.name[3:-2] for p in sorted(imp.glob('lib*.a'))]
        exe = out / (name + '.exe')
        build.run([build.GCC, '-m32', '-nostdlib', '-nostartfiles', '-mwindows',
                   '-Wl,-e,_' + entry + ',--gc-sections', *objects, '-L', str(imp),
                   *libs, '-o', str(exe)])
        build.run([str(exe)])
        print('PASS:', name)
    build.run([sys.executable, '-B', str(here / 'test_video_pool_emu.py')])
    build.run([sys.executable, '-B', str(here / 'test_frontend_native_emu.py')])
    build.run([sys.executable, '-B', str(here / 'test_frontend_carousel_emu.py')])
    build.run([sys.executable, '-B', str(here / 'test_load_guard.py'), '--out', str((args.out / 'load_guard').resolve())])
    build.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s',
               str(source / 'standalone'), '-p', 'test_frontend_catalog.py'])


if __name__ == '__main__':
    main()
