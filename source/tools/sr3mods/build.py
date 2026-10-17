"""Builds sr3mods.dll with the toolchain's own 64-bit gcc as 32-bit code (tools\\x86: import libraries, libgcc helpers).
    python build.py [--out DIR]          DIR default: tools\\patches\\build (sr3mods.dll and its import libraries)
The same flags as the TeknoParrot-free runtime (standalone\\native_build.py, Codex's): -m32 -march=pentium4 -msse2
-mfpmath=sse, UCRT, no C runtime start-up of mingw's; settings.c and ucrt_stdio.c are that runtime's own (read, not changed)."""
import os, sys, subprocess, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE); REPO = os.path.dirname(TOOLS); STAND = os.path.join(REPO, 'standalone')
sys.path.insert(0, os.path.join(TOOLS, 'import', 'core')); sys.path.insert(0, os.path.join(TOOLS, 'x86')); sys.path.insert(0, HERE)
import cbuild, implib
GCC = cbuild.GCC
X86 = ['-m32', '-march=pentium4', '-msse2', '-mfpmath=sse', '-ffreestanding', '-D_UCRT', '-D__USE_MINGW_ANSI_STDIO=0', '-D_CRT_SECURE_NO_WARNINGS',
       '-O2', '-std=c11', '-ffunction-sections', '-fno-asynchronous-unwind-tables', '-Wall', '-Wno-unused-function']   # (no .eh_frame: plain C, SEH on x86 is on the stack; 8 KB less)
def run(cmd, **k):
    r = subprocess.run(cmd, capture_output=True, text=True, **k)
    if r.returncode: raise SystemExit('failed: %s\n%s' % (' '.join(cmd), (r.stdout + r.stderr)[-3000:]))
    if r.stderr.strip(): print(r.stderr.strip()[-2000:])
def main(argv):
    out = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(HERE, 'build'); os.makedirs(out, exist_ok=True)
    run([sys.executable, os.path.join(HERE, 'gen_blobs.py'), os.path.join(out, 'blobs.h')])
    units = [(os.path.join(HERE, 'patchcore.c'), 'patchcore.o'), (os.path.join(HERE, 'pc_live.c'), 'pc_live.o'), (os.path.join(HERE, 'pc_json.c'), 'pc_json.o'),
             (os.path.join(HERE, 'pc_host.c'), 'pc_host.o'), (os.path.join(HERE, 'sr3mods_dll.c'), 'sr3mods_dll.o'), (os.path.join(HERE, 'sr3mods_exe.c'), 'sr3mods_exe.o'),
             (os.path.join(STAND, 'watch_launcher.c'), 'watch_launcher.o'), (os.path.join(STAND, 'settings.c'), 'settings.o'), (os.path.join(STAND, 'ucrt_stdio.c'), 'ucrt_stdio.o'), (os.path.join(TOOLS, 'x86', 'builtins.c'), 'builtins.o'),
             (os.path.join(HERE, 'livetest.c'), 'livetest.o')]                    # (livetest.exe: the live loop on fake games, for live_lockstep.py; never shipped)
    maps = ['-ffile-prefix-map=%s=.' % p for p in (out, HERE, STAND, os.path.join(TOOLS, 'x86'))]          # no build paths in the DLL
    o = {}
    for src, name in units:
        op = os.path.join(out, name); run([GCC] + X86 + maps + ['-I', out, '-I', STAND, '-I', HERE, '-c', src, '-o', op]); o[name] = op
    shared = [o[k] for k in ('patchcore.o', 'pc_live.o', 'pc_json.o', 'pc_host.o', 'watch_launcher.o', 'settings.o', 'ucrt_stdio.o', 'builtins.o')]   # patchcore: the one implementation both run
    imp = os.path.join(out, 'imp')
    if implib.main(['--out', imp] + sum((['--dll', d] for d in ('kernel32', 'user32', 'gdi32', 'ole32', 'shell32', 'ucrtbase')), []) + list(o.values())): raise SystemExit('implib: unresolved imports')
    libs = ['-l' + f[3:-2] for f in sorted(os.listdir(imp)) if f.startswith('lib') and f.endswith('.a')]
    link = [GCC, '-m32', '-nostdlib', '-nostartfiles', '-s', '-Wl,--no-insert-timestamp,--gc-sections']
    dll = os.path.join(out, 'sr3mods.dll'); exe = os.path.join(out, 'sr3mods.exe')
    run(link + ['-shared', '-Wl,-e,_DllMain@12', '-Wl,--kill-at,--exclude-all-symbols,--image-base,0x63000000', o['sr3mods_dll.o']] + shared + ['-L', imp] + libs + ['-o', dll])
    run(link + ['-Wl,-e,_entry@0', o['sr3mods_exe.o']] + shared + ['-L', imp] + libs + ['-o', exe])
    run(link + ['-Wl,-e,_entry@0', o['livetest.o']] + shared + ['-L', imp] + libs + ['-o', os.path.join(out, 'livetest.exe')])
    print('sr3mods.dll: %d bytes, sr3mods.exe: %d bytes -> %s' % (os.path.getsize(dll), os.path.getsize(exe), out))
    gate_obj = os.path.join(out, 'test_startup_gate.o'); gate_exe = os.path.join(out, 'test_startup_gate.exe')
    run([GCC] + X86 + ['-I', HERE, '-c', os.path.join(HERE, 'test_startup_gate.c'), '-o', gate_obj])
    run(link + ['-mwindows', '-Wl,-e,_gate_entry', gate_obj, '-L', imp, '-lkernel32', '-o', gate_exe])
    run([os.path.abspath(gate_exe)])
    print('Startup readiness: all 16 checks passed.')
    if '--no-lockstep' not in argv:                                     # the DLL must do exactly what sr3mods.ps1 does, or the build fails
        import lockstep, live_lockstep
        if lockstep.main(['--dll', dll]): raise SystemExit('lockstep: sr3mods.dll and sr3mods.ps1 differ; nothing is to be installed')
        if live_lockstep.main(['--exe', os.path.join(out, 'livetest.exe')]): raise SystemExit('live lockstep: pc_live.c and sr3mods.ps1 differ; nothing is to be installed')
        run([sys.executable, os.path.join(HERE, 'test_delayed_card.py'), '--out', os.path.abspath(out)])
        print('Delayed Hornet: five-second acknowledgment binds video; C/PS traces match.')
    return dll
if __name__ == '__main__':
    main(sys.argv[1:])
