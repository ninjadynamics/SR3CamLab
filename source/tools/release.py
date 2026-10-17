"""The release: two zips, run on the author's PC.
    python tools\\release.py [--name SR3Lab-<date>] [--check <reference build folder>] [--keep]
  dist\\<name>.zip            the mod: every file a commit would hold (scripts, C sources, docs). No binary of any kind.
  dist\\<name>-toolchain.zip  optional, the only binaries: tools\\python (this PC's CPython with the numpy and Pillow the builds
                             were checked with) and tools\\mingw (the part of MinGW-w64 gcc our C needs), with their licenses.
                             Unzipped into the mod's folder; safe to delete when the tools come from winget instead.
The GPL / LGPL parts' source is provided as links (owner, 2026-10-15): tools\\mingw\\licenses\\SOURCES.txt names, for every
component, the unchanged upstream archive and where it is, and WinLibs' build recipes at the commit this build was made
from (GPL v3 section 6d: the source on a third-party server, with clear directions next to the object code). Those links
must keep working while the zip is offered, so a release first checks that every one of them still answers (HEAD
requests only: nothing is downloaded).
Steps: check the source links; stage the files; build tools\\python (python311._pth: PYTHONPATH, PYTHONHOME and other Pythons' packages are ignored;
sr3lab_paths.py puts the running script's folder first, as a normal Python does); copy the gcc subset (what compiling and
linking every C helper in core/cbuild.py touches: headers, programs, link inputs, the DLLs they load); then, with --check, run
the whole stack in the stage on an empty data folder with nothing but the staged tools (PATH = Windows' own folder) and require
every game file to equal the reference build's; then zip (the DLLs that run compiled are not in either zip)."""
import os, sys, re, shutil, subprocess, zipfile, time, json, glob, tempfile, hashlib
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); BASE = sys.base_prefix; MINGW = r'C:\mingw64'
SKIP_LIB = {'test', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip', 'lib2to3', 'venv', 'site-packages', '__pycache__', 'pydoc_data', 'unittest'}
SKIP_DLL = ('_tkinter', 'tcl', 'tk', '_test', '_ctypes_test', '_ssl', '_hashlib', 'libssl', 'libcrypto', '_sqlite3', 'sqlite3', '_decimal', 'pyexpat',
            '_elementtree', '_socket', 'select', '_asyncio', '_overlapped', '_msi', '_uuid', 'winsound', '_zoneinfo', '_multiprocessing', '_wmi',
            'unicodedata', '_bz2', '_lzma')      # nothing of SR3Lab uses them (hashlib falls back to Python's own MD5 / SHA): about 9 MB
SKIP_PKG = ('__pycache__', 'tests', '*.pyi', '*.pxd', '*.h', '*.lib', '*.a', 'distutils', 'f2py', 'include', 'npy-pkg-config', 'doc')      # build-time parts
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
               runtime are under their own permissive licenses. tools\\mingw\\licenses holds the licences and SOURCES.txt,
               which names every component, its version and licence. The complete corresponding source of each is the
               unchanged upstream archive SOURCES.txt links to, and WinLibs' build recipes for this build (also linked
               there) say how they were configured and built.
'''
# What tools\mingw holds, from the DLLs' and programs' own version strings (WinLibs gcc-13.2.0-mingw-w64ucrt-11.0.1-r5, 2024-02-03),
# and where each one's source comes from. The GPL / LGPL ones need their source offered; the permissive ones are there for their notices.
SOURCES = [
    ('GCC (gcc, cc1, collect2, lto-wrapper, liblto_plugin, libgcc_s_seh-1, libgomp-1, headers, libgcc)', '13.2.0', 'GPL-3.0-or-later; the runtime libraries with the GCC Runtime Library Exception 3.1', 'https://ftp.gnu.org/gnu/gcc/gcc-13.2.0/gcc-13.2.0.tar.xz'),
    ('GNU Binutils (as, ld)', '2.42', 'GPL-3.0-or-later', 'https://ftp.gnu.org/gnu/binutils/binutils-2.42.tar.xz'),
    ('GMP (libgmp-10)', '6.3.0', 'LGPL-3.0-or-later or GPL-2.0-or-later', 'https://ftp.gnu.org/gnu/gmp/gmp-6.3.0.tar.xz'),
    ('MPFR (libmpfr-6)', '4.2.1', 'LGPL-3.0-or-later', 'https://ftp.gnu.org/gnu/mpfr/mpfr-4.2.1.tar.xz'),
    ('MPC (libmpc-3)', '1.3.1', 'LGPL-3.0-or-later', 'https://ftp.gnu.org/gnu/mpc/mpc-1.3.1.tar.gz'),
    ('GNU libiconv (libiconv-2)', '1.17', 'LGPL-2.1-or-later', 'https://ftp.gnu.org/gnu/libiconv/libiconv-1.17.tar.gz'),
    ('GNU gettext (libintl-8)', '0.22.4', 'LGPL-2.1-or-later (libintl)', 'https://ftp.gnu.org/gnu/gettext/gettext-0.22.4.tar.xz'),
    ('MinGW-w64 (headers, CRT import libraries, winpthreads: libwinpthread-1)', '11.0.1', 'ZPL-2.1, MIT and public domain parts', 'https://github.com/mingw-w64/mingw-w64/archive/refs/tags/v11.0.1.tar.gz'),
    ('isl (libisl-23)', '0.26', 'MIT', 'https://libisl.sourceforge.io/isl-0.26.tar.xz'),
    ('zlib (zlib1)', '1.3.1', 'Zlib', 'https://zlib.net/fossils/zlib-1.3.1.tar.gz'),
    ('Zstandard (libzstd)', '1.5.5', 'BSD-3-Clause', 'https://github.com/facebook/zstd/releases/download/v1.5.5/zstd-1.5.5.tar.gz'),
    ('dlfcn-win32 (libdl)', '1.4.1', 'MIT', 'https://github.com/dlfcn-win32/dlfcn-win32/archive/refs/tags/v1.4.1.tar.gz'),
    # how WinLibs configured and built all of the above for r5 (published 2024-02-03 12:38 UTC): the recipes at that day's commit
    ('WinLibs build recipes (configure options, patches)', 'r5', 'MIT', 'https://github.com/brechtsanders/winlibs_recipes/tree/05c3acf4d286fb6d6a944456901988afa915f8e8'),
]

def licences(out):
    """tools\\mingw\\licenses: SOURCES.txt, the GPL v3 and the GCC Runtime Library Exception (as numpy's licence file carries
    them) and the two LGPLs (tools\\licenses, the SPDX texts)"""
    os.makedirs(out, exist_ok=True)
    t = open(os.path.join(sys.base_prefix, 'Lib', 'site-packages', 'numpy-%s.dist-info' % __import__('numpy').__version__, 'LICENSE.txt'), encoding='utf-8').read()
    i = t.index('GCC RUNTIME LIBRARY EXCEPTION'); j = t.index('GNU GENERAL PUBLIC LICENSE', i)
    open(os.path.join(out, 'GCC-RUNTIME-LIBRARY-EXCEPTION-3.1.txt'), 'w', newline='\n').write(t[i:j].strip() + '\n')
    open(os.path.join(out, 'GPL-3.0.txt'), 'w', newline='\n').write(t[j:].strip() + '\n')
    for f in ('LGPL-2.1-or-later.txt', 'LGPL-3.0-or-later.txt'): shutil.copy2(os.path.join(REPO, 'tools', 'licenses', f), out)
    rows = ['Component | version | licence | source: the unchanged upstream archive (or the recipes) at this link']
    rows += ['%s | %s | %s | %s' % s for s in SOURCES]
    open(os.path.join(out, 'SOURCES.txt'), 'w', newline='\n').write('\n'.join(rows) + '\n')

def linkcheck():
    """every link in SOURCES still answers: HEAD requests, redirects followed by hand (a GET would download the archive)"""
    import urllib.request, urllib.error, urllib.parse
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    op = urllib.request.build_opener(NoRedirect); bad = []
    for comp, ver, lic, url in SOURCES:
        u = url
        for hop in range(8):
            loc = None
            try:
                r = op.open(urllib.request.Request(u, method='HEAD', headers={'User-Agent': 'SR3Lab-release'}), timeout=30); code = r.status; r.close()
            except urllib.error.HTTPError as e: code = e.code; loc = e.headers.get('Location')
            except OSError as e: code = 'no answer (%s)' % e
            if code in (301, 302, 303, 307, 308) and loc: u = urllib.parse.urljoin(u, loc); continue
            break
        if code != 200: bad.append('%s: %s' % (url, code))
    if bad: raise SystemExit('source links that no longer answer (the toolchain zip must point at working source):\n  ' + '\n  '.join(bad))
    print('links: all %d source links answer' % len(SOURCES))

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
    for p in ('numpy', 'PIL'): shutil.copytree(os.path.join(lib, 'site-packages', p), os.path.join(sp, p), ignore=shutil.ignore_patterns(*SKIP_PKG))
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
    for src in glob.glob(os.path.join(REPO, 'tools', 'x86', '*.c')):   # the 32-bit builds (gcc -m32): their headers too
        r = subprocess.run([G, '-m32', '-MG', '-M', src], capture_output=True, text=True, cwd=os.path.dirname(src))
        for tok in r.stdout.replace('\\\n', ' ').split(): add(tok)
    for f in glob.glob(os.path.join(MINGW, 'x86_64-w64-mingw32', 'lib', 'ldscripts', 'i386pe.*')): add(f)   # ld -m i386pe reads its script from
    # a file (the 64-bit default is built in), and --trace does not name it
    # Other components' builds (Codex's standalone\: the runtime, SDL, raylib, the settings app) name the compiler files they
    # use in a closure file: {"compiler_root": ..., "files": {path under it: sha256}}. Each must be the file this MINGW has.
    for cj in [os.path.join(REPO, 'standalone', 'toolchain-closure.json')] + [p for p in os.environ.get('SR3_CLOSURES', '').split(os.pathsep) if p]:
        if not os.path.exists(cj): continue
        for rel, want in json.load(open(cj, encoding='utf-8'))['files'].items():
            p = os.path.join(MINGW, rel)
            if not os.path.isfile(p) or hashlib.sha256(open(p, 'rb').read()).hexdigest() != want: raise SystemExit('%s: %s is not the file it names' % (cj, rel))
            add(p)
    shutil.rmtree(td, ignore_errors=True)
    for prog in ('cc1', 'collect2', 'lto-wrapper', 'as', 'ld', 'liblto_plugin.dll'): add(subprocess.run([G, '-print-prog-name=' + prog], capture_output=True, text=True).stdout.strip())
    for f in ('gcc.exe', 'ld.bfd.exe', 'dlltool.exe', 'libgomp-1.dll', 'libwinpthread-1.dll', 'libgcc_s_seh-1.dll'): add(os.path.join(MINGW, 'bin', f))
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
    lic = os.path.join(out, 'licenses'); licences(lic); shutil.copy2(os.path.join(MINGW, 'version_info.txt'), lic)
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
    if subprocess.run([py, stack, 'src', '1', '--steps', 'light,rt,build'], env=env).returncode: raise SystemExit('the staged stack failed')
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
        b.writestr(os.path.join(name, 'TOOLCHAIN-README.txt'), NOTICE % dict(py=sys.version.split()[0], np=__import__('numpy').__version__, pil=__import__('PIL').__version__, gcc='13.2.0', name=name))
    for k, z in zs.items(): print('zip: %s, %.1f MB' % (z, os.path.getsize(z) / 1e6))

def main(argv):
    a = list(argv); opt = {}
    for k in ('--name', '--check'):
        if k in a: i = a.index(k); opt[k] = a[i + 1]; del a[i:i + 2]
    name = opt.get('--name', 'SR3Lab-' + time.strftime('%Y-%m-%d')); dst = os.path.join(REPO, 'dist', 'stage', name)
    linkcheck(); stage(dst); python(dst); mingw(dst); data = check(dst, opt['--check']) if '--check' in opt else None; pack(dst, name)
    if data and '--keep' not in a: shutil.rmtree(data, ignore_errors=True)

if __name__ == '__main__':
    main(sys.argv[1:])
