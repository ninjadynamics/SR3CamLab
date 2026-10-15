"""The release: two zips, run on the author's PC.
    python tools\\release.py [--name SR3Lab-<date>] [--check <reference build folder>] [--keep]
  dist\\<name>.zip            the mod: every file a commit would hold (scripts, C sources, docs). No binary of any kind.
  dist\\<name>-toolchain.zip  optional, the only binaries: tools\\python (this PC's CPython with the numpy and Pillow the builds
                             were checked with) and tools\\mingw (the part of MinGW-w64 gcc our C needs), with their licenses.
                             Unzipped into the mod's folder; safe to delete when the tools come from winget instead.
Steps: stage the files; build tools\\python (python311._pth: PYTHONPATH, PYTHONHOME and other Pythons' packages are ignored;
sr3lab_paths.py puts the running script's folder first, as a normal Python does); copy the gcc subset (what compiling and
linking every C helper in core/cbuild.py touches: headers, programs, link inputs, the DLLs they load); then, with --check, run
the whole stack in the stage on an empty data folder with nothing but the staged tools (PATH = Windows' own folder) and require
every game file to equal the reference build's; then zip (the DLLs that run compiled are not in either zip)."""
import os, sys, re, shutil, subprocess, zipfile, time, json, glob, tempfile
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); BASE = sys.base_prefix; MINGW = r'C:\mingw64'
SKIP_LIB = {'test', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip', 'lib2to3', 'venv', 'site-packages', '__pycache__', 'pydoc_data', 'unittest'}
SKIP_DLL = ('_tkinter', 'tcl', 'tk')
PATHS_PY = '''"""SR3Lab's Python (tools\\\\python, python311._pth): at start-up, after site, the running script's own folder goes first on
sys.path (the current folder for -c / -m), as a normal Python has it, and the user's own site-packages comes off it, so that
nothing installed elsewhere on the PC is imported instead of this Python's own numpy and Pillow."""
import os, sys, site
_user = os.path.normcase(os.path.abspath(site.getusersitepackages()))
for _p in list(sys.path):
    if os.path.normcase(os.path.abspath(_p)) == _user: sys.path.remove(_p)
_a = sys.argv[0] if sys.argv else ''
sys.path.insert(0, os.path.dirname(os.path.abspath(_a)) if _a and _a not in ('-c', '-m') else os.getcwd())
'''
NOTICE = '''SR3Lab toolchain - the only binaries SR3Lab ships, and only for those who want them.
Unzip into the SR3Lab folder (it adds tools\\python and tools\\mingw). Delete it again whenever you like: IMPORT.bat can
fetch the same tools with winget instead.

tools\\python   CPython %(py)s (Python Software Foundation License: LICENSE-Python.txt), numpy %(np)s and Pillow %(pil)s (their
               licenses are in Lib\\site-packages\\*.dist-info). Unchanged, from python.org / PyPI builds.
tools\\mingw    part of GCC %(gcc)s for MinGW-w64, as built by WinLibs (Brecht Sanders, https://winlibs.com): the C compiler,
               assembler, linker, headers and libraries SR3Lab's C helpers need, unchanged. GCC and binutils are free software
               under the GNU GPL version 3 (the libraries under the GCC Runtime Library Exception); the MinGW-w64 headers and
               runtime are under their own permissive licenses. See tools\\mingw\\licenses. The complete corresponding
               source is available from https://winlibs.com, https://gcc.gnu.org, https://sourceware.org/binutils and
               https://www.mingw-w64.org.
'''

def stage(dst):
    if os.path.exists(dst): shutil.rmtree(dst)
    files = [f for f in subprocess.run(['git', '-C', REPO, 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], capture_output=True, text=True, check=True).stdout.split('\0') if f]
    for f in files:
        s = os.path.join(REPO, f); d = os.path.join(dst, f)
        if os.path.isfile(s): os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy2(s, d)
    bins = [f for f in files if f.lower().endswith(('.exe', '.dll', '.pyd', '.o', '.a', '.lib', '.so'))]
    if bins: raise SystemExit('binaries among the files a commit would hold: %s' % bins)
    print('stage: %d files, no binaries' % len(files))

def python(dst):
    py = os.path.join(dst, 'tools', 'python'); os.makedirs(py, exist_ok=True)
    for f in os.listdir(BASE):
        if f.lower().endswith(('.exe', '.dll')): shutil.copy2(os.path.join(BASE, f), py)
    for f in os.listdir(os.path.join(BASE, 'DLLs')):
        if f.lower().endswith(('.pyd', '.dll')) and not f.lower().startswith(SKIP_DLL): shutil.copy2(os.path.join(BASE, 'DLLs', f), py)
    ver = 'python%d%d' % sys.version_info[:2]; lib = os.path.join(BASE, 'Lib'); n = 0
    with zipfile.ZipFile(os.path.join(py, ver + '.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for root, ds, fs in os.walk(lib):
            ds[:] = [d for d in ds if d not in SKIP_LIB]
            for f in fs:
                if f.endswith('.py'): z.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), lib)); n += 1
    sp = os.path.join(py, 'Lib', 'site-packages')
    for p in ('numpy', 'PIL'): shutil.copytree(os.path.join(lib, 'site-packages', p), os.path.join(sp, p), ignore=shutil.ignore_patterns('__pycache__', 'tests'))
    for d in glob.glob(os.path.join(lib, 'site-packages', '*.dist-info')):
        if os.path.basename(d).split('-')[0].lower() in ('numpy', 'pillow'): shutil.copytree(d, os.path.join(sp, os.path.basename(d)))
    open(os.path.join(sp, 'sr3lab_paths.py'), 'w', newline='\n').write(PATHS_PY)
    open(os.path.join(sp, 'sr3lab_paths.pth'), 'w', newline='\n').write('import sr3lab_paths\n')
    open(os.path.join(py, ver + '._pth'), 'w', newline='\n').write('%s.zip\n.\nLib\\site-packages\nimport site\n' % ver)
    shutil.copy2(os.path.join(BASE, 'LICENSE.txt'), os.path.join(py, 'LICENSE-Python.txt'))
    print('python: %d library files zipped' % n)
    return os.path.join(py, 'python.exe')

def mingw(dst):
    """the files of MINGW that compiling and linking every helper touches, and the DLLs those programs load"""
    sys.path.insert(0, os.path.join(REPO, 'tools', 'import', 'core')); import cbuild
    G = os.path.join(MINGW, 'bin', 'gcc.exe'); OBJDUMP = os.path.join(MINGW, 'bin', 'objdump.exe'); need = set(); M = os.path.normcase(MINGW)
    def add(p):
        p = os.path.normcase(os.path.abspath(p))
        if p.startswith(M) and os.path.isfile(p): need.add(p)
    td = tempfile.mkdtemp()
    for h, spec in cbuild.HELPERS.items():
        d = os.path.join(REPO, 'tools', 'import', 'core', spec['dir']); objs = []
        for k, (src, fl) in enumerate(spec['units']):
            r = subprocess.run([G, '-O3', '-march=x86-64-v3'] + fl + ['-fopenmp', '-M', os.path.join(d, src)], capture_output=True, text=True, cwd=d)
            for tok in r.stdout.replace('\\\n', ' ').split(): add(tok)
            o = os.path.join(td, '%s%d.o' % (h, k)); objs.append(o)
            r = subprocess.run([G, '-v', '-O3', '-march=x86-64-v3'] + fl + ['-fopenmp', '-c', '-o', o, os.path.join(d, src)], capture_output=True, text=True, cwd=d)
            for tok in re.findall(r'[A-Za-z]:[\\/][^\s"]+', r.stderr): add(tok.strip('"'))
        r = subprocess.run([G, '-v', '-shared', '-fopenmp', '-Wl,--trace', '-o', os.path.join(td, h + '.dll')] + objs, capture_output=True, text=True)
        for tok in re.findall(r'[A-Za-z]:[\\/][^\s"();]+', r.stdout + r.stderr): add(tok.strip('"'))       # (paths end at white space; LIBRARY_PATH lists are ;-separated)
    shutil.rmtree(td, ignore_errors=True)
    for prog in ('cc1', 'collect2', 'lto-wrapper', 'as', 'ld', 'liblto_plugin.dll'): add(subprocess.run([G, '-print-prog-name=' + prog], capture_output=True, text=True).stdout.strip())
    for f in ('gcc.exe', 'ld.bfd.exe', 'libgomp-1.dll', 'libwinpthread-1.dll', 'libgcc_s_seh-1.dll'): add(os.path.join(MINGW, 'bin', f))
    todo = [p for p in need if p.endswith(('.exe', '.dll'))]
    while todo:
        p = todo.pop()
        for dl in re.findall(r'DLL Name: (\S+)', subprocess.run([OBJDUMP, '-p', p], capture_output=True, text=True).stdout):
            for d in (os.path.dirname(p), os.path.join(MINGW, 'bin')):
                q = os.path.normcase(os.path.join(d, dl))
                if os.path.isfile(q):
                    if q not in need: need.add(q); todo.append(q)
                    break
    out = os.path.join(dst, 'tools', 'mingw')
    for p in need:
        q = os.path.join(out, os.path.relpath(p, M)); os.makedirs(os.path.dirname(q), exist_ok=True); shutil.copy2(p, q)
    lic = os.path.join(out, 'licenses'); os.makedirs(lic, exist_ok=True)
    for f in glob.glob(os.path.join(MINGW, 'share', 'licenses', '*')) + glob.glob(os.path.join(MINGW, 'version_info.txt')):
        (shutil.copytree if os.path.isdir(f) else shutil.copy2)(f, os.path.join(lic, os.path.basename(f)))
    print('mingw: %d files, %.1f MB' % (len(need), sum(os.path.getsize(p) for p in need) / 1e6))

def check(dst, ref):
    """the whole stack in the stage, on an empty data folder, with only the staged Python and gcc"""
    data = os.path.abspath(dst + '_data')
    if os.path.exists(data): shutil.rmtree(data)
    S = json.load(open(os.path.join(REPO, 'tools', 'import', 'settings.json'), encoding='utf-8')); os.makedirs(data)
    st = os.path.join(data, 'settings.json')
    json.dump(dict(data_root=os.path.join(data, 'data'), roms=S['roms'], sr3_game=S.get('sr3_game', ''), threads=S.get('threads', 'all_but_one'), march='x86-64-v3'), open(st, 'w', newline='\n'), indent=1)
    hd = os.path.join(S.get('data_root', ''), 'classic', 'courses', 'src', 'course1_mountain', 'textures_hd')
    env = {'SystemRoot': os.environ['SystemRoot'], 'PATH': os.path.join(os.environ['SystemRoot'], 'System32'), 'TEMP': os.environ['TEMP'], 'TMP': os.environ['TMP'],
           'LOCALAPPDATA': os.path.join(data, 'no_localappdata'), 'SR3_SETTINGS': st, 'NUMBER_OF_PROCESSORS': os.environ.get('NUMBER_OF_PROCESSORS', '1')}
    py = os.path.join(dst, 'tools', 'python', 'python.exe'); stack = os.path.join(dst, 'tools', 'import', 'stack.py'); t = time.time()
    if subprocess.run([py, stack, 'src', '1', '--steps', 'rom'], env=env).returncode: raise SystemExit('the staged rom step failed')
    if os.path.isdir(hd):                                              # the owner's own HD tiles that differ from vanilla, as a user would add them
        r = subprocess.run([py, os.path.join(dst, 'tools', 'import', 'core', 'hd_textures.py'), 'src', '1', 'status'], env=dict(env, SR3_SETTINGS=os.path.join(REPO, 'tools', 'import', 'settings.json')), capture_output=True, text=True)
        out = os.path.join(data, 'data', 'classic', 'courses', 'src', 'course1_mountain', 'textures_hd')
        for ln in r.stdout.splitlines()[1:]:
            f = ln.strip().split(' ')[0]
            if f.endswith('.png'): shutil.copy2(os.path.join(hd, f), out)
    if subprocess.run([py, stack, 'src', '1', '--steps', 'patch,round,light,rt,build'], env=env).returncode: raise SystemExit('the staged stack failed')
    mine = os.path.join(data, 'data', 'work', 'out', 'stack_src_1', 'Desert4'); bad = []
    for f in sorted(os.listdir(ref)):
        if f == 'texmap.json': continue                                # it records the textures folder's path
        if not os.path.exists(os.path.join(mine, f)) or open(os.path.join(ref, f), 'rb').read() != open(os.path.join(mine, f), 'rb').read(): bad.append(f)
    print('check (%.0f s): %s' % (time.time() - t, 'every game file the same as %s' % ref if not bad else 'DIFFERENT: %s' % bad))
    if bad: raise SystemExit('the release build is not the reference build')
    return data

def pack(dst, name):
    tool = ('tools' + os.sep + 'python', 'tools' + os.sep + 'mingw')
    zs = {name: os.path.join(REPO, 'dist', name + '.zip'), name + '-toolchain': os.path.join(REPO, 'dist', name + '-toolchain.zip')}
    for z in zs.values():
        if os.path.exists(z): os.remove(z)
    with zipfile.ZipFile(zs[name], 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as a, zipfile.ZipFile(zs[name + '-toolchain'], 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as b:
        for root, ds, fs in os.walk(dst):
            ds[:] = [d for d in ds if d != '__pycache__']
            for f in fs:
                p = os.path.join(root, f); rel = os.path.relpath(p, dst); in_tool = rel.startswith(tool)
                if not in_tool and f.lower().endswith(('.dll', '.pyc', '.o', '.tmp', '.exe')): continue      # what the check compiled
                (b if in_tool else a).write(p, os.path.join(name, rel))
        b.writestr(os.path.join(name, 'TOOLCHAIN-README.txt'), NOTICE % dict(py=sys.version.split()[0], np=__import__('numpy').__version__, pil=__import__('PIL').__version__, gcc='13.2.0'))
    for k, z in zs.items(): print('zip: %s, %.1f MB' % (z, os.path.getsize(z) / 1e6))

def main(argv):
    a = list(argv); opt = {}
    for k in ('--name', '--check'):
        if k in a: i = a.index(k); opt[k] = a[i + 1]; del a[i:i + 2]
    name = opt.get('--name', 'SR3Lab-' + time.strftime('%Y-%m-%d')); dst = os.path.join(REPO, 'dist', 'stage', name)
    stage(dst); python(dst); mingw(dst); data = check(dst, opt['--check']) if '--check' in opt else None; pack(dst, name)
    if data and '--keep' not in a: shutil.rmtree(data, ignore_errors=True)

if __name__ == '__main__':
    main(sys.argv[1:])
