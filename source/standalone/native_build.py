"""Direct GCC build: stdlib Python, offline source pins, parallel incremental C.

One WinLibs x64 UCRT GCC builds x86 (-m32, Windows CRT) and x64 (raylib).
No Git, CMake, Visual Studio, second compiler, or download is invoked.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT.parent / 'tools'
ENV = dict(os.environ, SOURCE_DATE_EPOCH='0')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def run(args, **kwargs):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, env=ENV, **kwargs)
    if r.returncode:
        raise RuntimeError(subprocess.list2cmdline([str(a) for a in args]) + '\n' + r.stdout + r.stderr)
    return r.stdout


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def vendor(name, path):
    pin = json.loads((ROOT / (name + '-pin.json')).read_text())
    bad = [name for name, expected in pin['files'].items()
           if not (path / name).is_file() or sha(path / name) != expected]
    if bad:
        raise RuntimeError(f'{pin["version"]}: missing/modified sources in {path}: {bad[:8]}. '
                           'Use the setup source cache or supply --' + name + '-source.')
    return pin


class Build:
    def __init__(self, args):
        self.args = args
        self.out = args.out.resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.gcc = Path(args.gcc or module(TOOLS / 'import/core/cbuild.py').find_gcc()).resolve()
        if not self.gcc.is_file():
            raise RuntimeError('Setup GCC missing; run toolchain setup or pass --gcc.')
        self.dlltool = self.gcc.with_name('dlltool.exe')
        self.implib = module(TOOLS / 'x86/implib.py')
        # implib resolves its assembler through GCC too. Bind that lookup to
        # --gcc, so an isolated package cannot silently use the host compiler.
        self.implib.find_gcc = lambda: str(self.gcc)
        self.identity = {'gcc': sha(self.gcc), 'version': run([self.gcc, '--version']).splitlines()[0]}
        # Hash cc1/as/ld as well as the driver: changing the actual compiler
        # must invalidate objects. Source caches never trust timestamps alone.
        for prog in ('cc1', 'as', 'ld'):
            p = Path(run([self.gcc, '-print-prog-name=' + prog]).strip())
            self.identity[prog] = sha(p)
        self.common = ['-O2', '-std=c11', '-ffunction-sections']
        roots = [(ROOT, '/sr3/standalone'), (self.out, '/sr3/build'),
                 (args.sdl_source.resolve(), '/sr3/SDL'),
                 (args.raylib_source.resolve(), '/sr3/raylib'), (self.gcc.parent.parent, '/sr3/gcc')]
        self.common += ['-ffile-prefix-map=' + str(p) + '=' + dest for p, dest in roots]
        self.x86 = ['-m32', '-march=pentium4', '-msse2', '-mfpmath=sse', '-ffreestanding',
                    '-fno-stack-protector', '-fno-asynchronous-unwind-tables',
                    '-D_UCRT', '-D__USE_MINGW_ANSI_STDIO=0', '-D_CRT_SECURE_NO_WARNINGS']
        # i386pe.x collects .bss but not .bss.*: -fdata-sections puts zero
        # statics into file-backed .data. Keep x86 BSS together; x64 supports
        # the split sections correctly. Function-level collection stays on.
        self.x64 = ['-m64', '-march=x86-64', '-mtune=generic', '-fdata-sections']
        self.own_headers = {p.name: sha(p) for p in ROOT.glob('*.h')}
        self.input_hashes = {}
        self.trace = []

    def hash_input(self, path):
        key = os.path.normcase(os.path.abspath(path))
        if key not in self.input_hashes:
            try:
                self.input_hashes[key] = sha(path)
            except FileNotFoundError:
                self.input_hashes[key] = None
        return self.input_hashes[key]

    def link_command(self, args, target):
        # Windows command lines cap at 32767 characters. A deep install plus
        # 235 SDL objects exceeds that; GCC response files have no such cap.
        response = target.with_suffix(target.suffix + '.rsp')
        response.write_text('\n'.join('"' + str(a).replace('\\', '/').replace('"', '\\"') + '"' for a in args) + '\n')
        trace = run([self.gcc, '@' + str(response), '-Wl,-t'])
        inputs = {str(Path(p.strip()).resolve()): sha(p.strip()) for p in trace.splitlines() if Path(p.strip()).is_file()}
        target.with_suffix(target.suffix + '.link-inputs.json').write_text(json.dumps(inputs, indent=2))

    def link_inputs_valid(self, target):
        trace = target.with_suffix(target.suffix + '.link-inputs.json')
        if not trace.exists():
            return False
        return all(self.hash_input(p) == h for p, h in json.loads(trace.read_text()).items())

    def compile(self, group, sources, flags, headers):
        folder = self.out / 'obj' / group
        folder.mkdir(parents=True, exist_ok=True)
        flags = self.common + flags

        def one(item):
            key, src = item
            obj = folder / (key.replace('/', '_') + '.o')
            stamp = obj.with_suffix('.json')
            sig = digest([self.identity, flags, headers, sha(src), 'dependencies-v1'])
            if obj.exists() and stamp.exists():
                cache = json.loads(stamp.read_text())
                if cache.get('key') == sig and cache.get('object') == sha(obj) and all(
                        self.hash_input(p) == h for p, h in cache.get('dependencies', {}).items()):
                    return obj, False
            # Threads launch independent GCC processes: a Python ProcessPool
            # would add interpreter startup/copying without parallelizing more C.
            temp = obj.with_suffix('.tmp.o')
            dep = obj.with_suffix('.d')
            run([self.gcc, *flags, '-MD', '-MF', dep, '-MT', 'object', '-c', src, '-o', temp])
            deptext = dep.read_text().replace('\\\n', '').split(':', 1)[1]
            # GCC on Windows leaves directory backslashes literal, but quotes
            # spaces with \ . POSIX shlex would erase the directory separators.
            dependencies = [re.sub(r'\\([ \t#])', r'\1', p).replace('$$', '$')
                            for p in re.findall(r'(?:\\[ \t#]|[^\s])+', deptext)]
            os.replace(temp, obj)
            stamp.write_text(json.dumps({'key': sig, 'object': sha(obj),
                                         'dependencies': {p: self.hash_input(p) for p in dependencies}}))
            return obj, True

        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            results = list(pool.map(one, sources))
        print(f'{group}: compiled {sum(changed for _, changed in results)}/{len(results)}, workers={self.args.jobs}', flush=True)
        closure = sorted({p for obj, _ in results for p in json.loads(obj.with_suffix('.json').read_text())['dependencies']})
        self.trace.append({'group': group, 'flags': flags, 'sources': [key for key, _ in sources], 'dependencies': closure})
        return [p for p, _ in results]

    def link32(self, name, objects, entry, dll=False, definitions=None):
        folder = self.out / 'imports' / name
        signature = digest([self.identity, [(p.name, sha(p)) for p in objects], sha(TOOLS / 'x86/implib.py'),
                            sha(self.dlltool), entry, dll, 'image-base=0x62000000', sha(definitions) if definitions else None])
        target = self.out / name
        stamp = self.out / (name + '.json')
        if stamp.exists() and target.exists():
            old = json.loads(stamp.read_text())
            if old.get('key') == signature and old.get('output') == sha(target) and self.link_inputs_valid(target):
                return target
        if self.implib.main(['--out', str(folder), '--dlltool', str(self.dlltool), *map(str, objects)]):
            raise RuntimeError('Unresolved Windows imports for ' + name)
        imports = json.loads((folder / 'imports.json').read_text())
        libs = [folder / d['lib'] for d in imports['dlls']]
        temp = target.with_name(target.stem + '.tmp' + target.suffix)
        flags = ['-m32', '-nostdlib', '-nostartfiles', '-s',
                 '-Wl,-e,' + entry + ',--no-insert-timestamp,--gc-sections,--enable-stdcall-fixup']
        if dll:
            # ld's auto DLL base hashes the output PATH. Set a preferred base
            # explicitly; relocations/ASLR remain enabled, so no address is forced.
            flags += ['-shared', '-Wl,--kill-at,--exclude-all-symbols,--image-base,0x62000000']
        elif name == 'launch.exe':
            flags += ['-mwindows']
        self.link_command([*flags, *objects, *([definitions] if definitions else []), *libs, '-o', temp], target)
        os.replace(temp, target)
        stamp.write_text(json.dumps({'key': signature, 'output': sha(target)}))
        return target

    def runtime(self):
        sdl = self.args.sdl_source.resolve()
        pin = vendor('sdl', sdl)
        paths = [p for p in (ROOT / 'sdl_sources.txt').read_text().splitlines() if p and not p.startswith('#')]
        includes = ['-I' + str(p) for p in (ROOT / 'sdl_config', sdl / 'include', sdl / 'src', sdl / 'include/build_config')]
        sdlflags = self.x86 + includes + ['-DSDL_STATIC_LIB', '-DSDL_BUILDING_LIBRARY', '-DWIN32_LEAN_AND_MEAN']
        headers = {'vendor': pin, 'config': sha(ROOT / 'sdl_config/SDL_build_config.h')}
        sdlobjs = self.compile('sdl', [(p, sdl / p) for p in paths], sdlflags, headers)
        names = ['runtime.c', 'cpu_affinity.c', 'test_cpu_affinity.c', 'pom_native.c', 'pom.c', 'test_pom.c', 'texture_rebind.c', 'test_texture_rebind.c', 'capture.c', 'test_capture.c', 'patch_loader.c', 'settings.c', 'command_line.c', 'test_command_line.c', 'launch.c', 'watch_launcher.c', 'launcher.c', 'launcher_entry.c',
                 'ucrt_stdio.c', 'windows_guids.c', 'test_entry.c', 'test_input.c',
                 'test_settings.c', 'test_ucrt.c', 'test_sdl.c', 'test_guard.c',
                 'test_patch_mock.c', 'test_patch_loader.c']
        objs = self.compile('x86', [(n, ROOT / n) for n in names] + [('builtins.c', TOOLS / 'x86/builtins.c')],
                            self.x86 + includes + ['-DSDL_STATIC_LIB'], self.own_headers)
        o = dict(zip(names + ['builtins.c'], objs))
        base = [o['ucrt_stdio.c'], o['builtins.c']]
        dll = self.link32('dinput8.dll', [o['runtime.c'], o['cpu_affinity.c'], o['pom_native.c'], o['texture_rebind.c'], o['capture.c'], o['patch_loader.c'], o['settings.c'], o['windows_guids.c'], *sdlobjs, *base],
                          '_DllMain@12', True, ROOT / 'runtime.def')
        self.link32('launch.exe', [o[n] for n in ['launcher.c', 'command_line.c', 'launch.c', 'watch_launcher.c', 'settings.c', 'launcher_entry.c']] + base, '_launcher_entry')
        for test in ['test_input', 'test_settings', 'test_ucrt', 'test_sdl', 'test_guard', 'test_pom', 'test_capture', 'test_command_line', 'test_texture_rebind', 'test_cpu_affinity']:
            extras = [o['settings.c']] if test == 'test_settings' else []
            if test == 'test_cpu_affinity':
                extras = [o['cpu_affinity.c']]
            if test == 'test_pom':
                extras = [o['pom.c']]
            if test == 'test_texture_rebind':
                extras = self.compile('texture-test', [('texture_rebind.c', ROOT / 'texture_rebind.c')],
                                      self.x86 + ['-DSR3_TEXTURE_REBIND_TEST'], self.own_headers)
            if test == 'test_command_line':
                extras = [o['command_line.c'], o['launch.c'], o['watch_launcher.c'], o['settings.c']]
            if test == 'test_sdl':
                extras = sdlobjs + [o['windows_guids.c']]
            exe = self.link32(test + '.exe', [o[test + '.c'], o['test_entry.c'], *base, *extras], '_test_entry')
            testdir = self.out / 'test-work' / test
            testdir.mkdir(parents=True, exist_ok=True)
            print(run([exe, *([dll] if test == 'test_guard' else [])], cwd=testdir).strip(), flush=True)
        exports = self.implib.pe_exports(dll)
        if exports != {'DirectInput8Create', 'Out32', 'SR3LabGetOutput', 'sr3rt_grab_backbuffer'}:
            raise RuntimeError('Unexpected runtime exports: ' + str(exports))
        self.patch_tests(o, base)
        shutil.copyfile(sdl / 'LICENSE.txt', self.out / 'SDL-LICENSE.txt')

    def patch_tests(self, o, base):
        mock = self.link32('test_patch_mock.dll', [o['test_patch_mock.c'], *base], '_DllMain@12', True)
        wrong = self.compile('wrong-export', [('mock.c', ROOT / 'test_patch_mock.c')],
                             self.x86 + ['-Dsr3mods_start=wrong_export'], {})
        wrong = self.link32('test_wrong_export.dll', wrong + base, '_DllMain@12', True)
        # Windows' legacy installer heuristic asks for elevation for an x86 EXE
        # named *patch*. This ordinary test host has no installer operations.
        host = self.link32('test_plugin_host.exe', [o['test_patch_loader.c'], o['test_entry.c'], o['patch_loader.c'], *base], '_test_entry')
        # Each case is a fresh process; no DLL unloading or writable global
        # reset stands in for the real Windows loader's once-per-process state.
        cases = [('absent-auto', 0, 0, None, '0'), ('absent-required', 1, -1, None, '0'),
                 ('disabled', 2, 0, mock, '3'), ('started', 0, 1, mock, '0'),
                 ('bad-settings', 0, -1, mock, '1'), ('bad-game', 0, -1, mock, '2'),
                 ('internal-error', 1, -1, mock, '3'), ('bad-export', 0, -1, wrong, '0')]
        for name, mode, expected, plugin, code in cases:
            folder = self.out / 'test-work' / name
            folder.mkdir(parents=True, exist_ok=True)
            exe = folder / host.name
            shutil.copyfile(host, exe)
            if plugin:
                shutil.copyfile(plugin, folder / 'sr3mods.dll')
            env = dict(ENV, SR3_TEST_PATCH_RETURN=code)
            # A different CWD with another DLL proves auto never searches CWD.
            cwd = self.out / 'test-work/foreign-cwd'
            cwd.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(mock, cwd / 'sr3mods.dll')
            path = str(folder / 'caf\u00e9 settings.yaml')
            r = subprocess.run([str(exe), str(mode), str(expected), path], cwd=cwd,
                               env=env, capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError(name + ': ' + r.stdout + r.stderr)
            if expected == 1 and (cwd / 'patch-path.bin').read_bytes() != path.encode('utf-8'):
                raise RuntimeError('Plugin did not receive the absolute UTF-8 path')
        print('Patch loader: absent/required/off, adjacent-only search, UTF-8 path and failure propagation pass.', flush=True)

    def watchdog(self):
        # Windows' installed .NET Framework compiler and PowerShell engine; no SDK download.
        windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
        compiler = windows / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        engines = list((windows / 'Microsoft.NET/assembly/GAC_MSIL/System.Management.Automation').glob('*/System.Management.Automation.dll'))
        if not compiler.is_file() or len(engines) != 1:
            raise RuntimeError('Windows x64 .NET Framework / Windows PowerShell is required for watchdog.exe')
        source = ROOT / 'watchdog_host.cs'
        target = self.out / 'watchdog.exe'
        stamp = self.out / 'watchdog.exe.json'
        key = digest([sha(compiler), sha(engines[0]), sha(source)])
        old = json.loads(stamp.read_text()) if stamp.exists() else {}
        if not target.exists() or old.get('key') != key or old.get('output') != sha(target):
            run([compiler, '/nologo', '/optimize+', '/platform:x64', '/target:exe',
                 '/reference:' + str(engines[0]), '/out:' + str(target), source])
            stamp.write_text(json.dumps({'key': key, 'output': sha(target)}))
        # Canonical deployment beside watchdog.ps1, also for custom --out builds.
        installed = ROOT / 'watchdog.exe'
        if not installed.exists() or sha(installed) != sha(target):
            temporary = ROOT / 'watchdog.next.exe'
            shutil.copyfile(target, temporary)
            os.replace(temporary, installed)
        print(run([target, '--help']).strip(), flush=True)

    def companion(self):
        raylib = self.args.raylib_source.resolve()
        pin = vendor('raylib', raylib)
        flags = self.x64 + ['-DPLATFORM_DESKTOP', '-DGRAPHICS_API_OPENGL_33',
                            '-I' + str(raylib / 'src'), '-I' + str(raylib / 'src/external/glfw/include')]
        names = ['rcore.c', 'rshapes.c', 'rtextures.c', 'rtext.c', 'utils.c', 'rglfw.c']
        objs = self.compile('raylib', [(n, raylib / 'src' / n) for n in names], flags, pin)
        objs += self.compile('companion', [(n, ROOT / n) for n in ['settings_ui.c', 'settings.c', 'command_line.c', 'launch.c', 'watch_launcher.c']], flags, self.own_headers)
        target = self.out / 'settings.exe'
        signature = digest([self.identity, [(p.name, sha(p)) for p in objs]])
        stamp = self.out / 'settings.exe.json'
        old = json.loads(stamp.read_text()) if stamp.exists() else {}
        if not target.exists() or old.get('key') != signature or old.get('output') != sha(target) or not self.link_inputs_valid(target):
            temp = self.out / 'settings.tmp.exe'
            self.link_command(['-m64', '-s', '-static', '-mwindows', '-Wl,--no-insert-timestamp,--gc-sections',
                 *objs, '-lopengl32', '-lgdi32', '-lwinmm', '-o', temp], target)
            os.replace(temp, target)
            stamp.write_text(json.dumps({'key': signature, 'output': sha(target)}))
        shutil.copyfile(raylib / 'LICENSE', self.out / 'raylib-LICENSE.txt')


def main(default_target='all'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gcc')
    parser.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--out', type=Path, default=ROOT / 'build/native')
    parser.add_argument('--sdl-source', type=Path, default=ROOT / 'deps/SDL')
    parser.add_argument('--raylib-source', type=Path, default=ROOT / 'deps/raylib')
    parser.add_argument('--target', choices=['all', 'runtime', 'companion'], default=default_target)
    parser.add_argument('--write-toolchain-closure', type=Path, help='Record compiler/SDK/link inputs for release.py')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.write_toolchain_closure and args.target != 'all':
        parser.error('--write-toolchain-closure requires --target all so no product dependencies are omitted')
    start = time.perf_counter()
    b = Build(args)
    b.watchdog()
    if args.target in ('all', 'runtime'):
        b.runtime()
    if args.target in ('all', 'companion'):
        b.companion()
    if args.write_toolchain_closure:
        compiler = b.gcc.parent.parent.resolve()
        inputs = {Path(p).resolve() for group in b.trace for p in group['dependencies']}
        for trace in b.out.glob('*.link-inputs.json'):
            inputs.update(Path(p).resolve() for p in json.loads(trace.read_text()))
        inputs = {p for p in inputs if p.is_relative_to(compiler)}
        args.write_toolchain_closure.write_text(json.dumps({'compiler_root': str(compiler),
            'files': {p.relative_to(compiler).as_posix(): sha(p) for p in sorted(inputs)}}, indent=2) + '\n')
    (b.out / 'build-provenance.json').write_text(json.dumps({'compiler': b.identity, 'units': b.trace,
        'artifacts': {p.name: sha(p) for p in b.out.glob('*') if p.suffix in ('.exe', '.dll')}}, indent=2))
    print(f'Built and checked {args.target} in {time.perf_counter() - start:.2f}s: {b.out}', flush=True)


if __name__ == '__main__':
    main()
