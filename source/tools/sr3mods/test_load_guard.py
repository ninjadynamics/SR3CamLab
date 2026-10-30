"""Build test_load_guard.exe and check load_guard.c's logs, dumps and exit.

A stalled load must write a readable minidump (all threads with stacks, the
modules, handles and the executable's globals), at most two per session; a
process that outlives its window must write one and end itself; a normal quit
must write none. Runs only the small test program; no game is launched.

Usage: python -B source/tools/sr3mods/test_load_guard.py --out scratchpad/guard-tests
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import build
from minidump_threads import Dump, HANDLES

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1]


def compile_test(out):
    out.mkdir(parents=True, exist_ok=True)
    objects = []
    for src in (HERE / 'test_load_guard.c', SOURCE / 'tools/x86/builtins.c', SOURCE / 'standalone/ucrt_stdio.c'):
        obj = out / (src.stem + '.o')
        build.run([build.GCC, *build.X86, '-I', str(HERE), '-c', str(src), '-o', str(obj)])
        objects.append(str(obj))
    imp = out / 'imp'
    if build.implib.main(['--out', str(imp), '--dll', 'kernel32', '--dll', 'user32', '--dll', 'ucrtbase'] + objects):
        raise SystemExit('Unresolved load guard test imports')
    libs = ['-l' + p.name[3:-2] for p in sorted(imp.glob('lib*.a'))]
    exe = out / 'test_load_guard.exe'
    build.run([build.GCC, '-m32', '-nostdlib', '-nostartfiles', '-mwindows', '-Wl,-e,_load_guard_test_entry,--gc-sections',
               *objects, '-L', str(imp), *libs, '-o', str(exe)])
    return exe


def run(exe, mode, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('*'):
        old.unlink()
    env = dict(os.environ, LG_TEST_MODE=mode, LG_TEST_DIR=str(folder))
    code = subprocess.run([str(exe)], env=env, timeout=30).returncode
    return code, (folder / 'guard.log').read_text(), sorted(folder.glob('sr3lab-*.dmp'))


def check_dump(path, exe_name, phase):
    d = Dump(path)
    assert len(d.threads) >= 2, path
    assert all(t['stack'][1] and t['regs'].get('eip') for t in d.threads), 'every thread has a stack and registers'
    assert any(name.lower().endswith(exe_name) for _, _, name in d.modules), 'the executable is listed'
    assert any(name.lower().endswith('kernel32.dll') for _, _, name in d.modules)
    assert HANDLES in d.streams, 'open handles are recorded'
    assert d.covers(phase, 1), "the executable's globals are included"
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    exe = compile_test(out / 'build')

    code, log, dumps = run(exe, 'load', out / 'load')
    phase = int(log.split('phase at ', 1)[1].split()[0], 16)
    assert code == 0, (code, log)
    assert log.count('Race load: menus left') == 4 and log.count('Race load: race running after') == 1, log
    assert log.count('Race load: back in the menus after') == 3, log
    assert log.count('still loading after 0 s') == 4 and 'loading animation not seen' in log, log
    assert log.count('Race load: no race after') == 3, log
    assert log.count('Diagnostics: load dump written') == 2 and 'Diagnostics: load dump skipped' in log, log
    assert len(dumps) == 2, dumps
    for path in dumps:
        check_dump(path, exe.name, phase)
    size = max(p.stat().st_size for p in dumps)

    code, log, dumps = run(exe, 'exit', out / 'exit')
    assert code == 0x5352, (code, log)
    assert 'Game window closed; waiting for the process to exit.' in log and 'recording every thread, then ending the process' in log, log
    assert 'Diagnostics: exit dump written' in log and len(dumps) == 1, (log, dumps)
    d = check_dump(dumps[0], exe.name, phase)

    code, log, dumps = run(exe, 'quit', out / 'quit')
    assert code == 0 and not dumps and 'ending the process' not in log, (code, log, dumps)
    assert 'Game window closed; waiting for the process to exit.' in log, log

    print('PASS: load guard logs loads, dumps a stalled load (cap of two) and a stuck exit, then ends it; a normal quit '
          'writes nothing. Dumps hold %d threads with stacks, modules, handles and globals (largest %.1f MB).'
          % (len(d.threads), size / 2**20))


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    main()
