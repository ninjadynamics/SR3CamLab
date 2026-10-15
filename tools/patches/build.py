"""Builds patches.dll with the toolchain's own 64-bit gcc as 32-bit code (tools\\x86: import libraries, libgcc helpers).
    python build.py [--out DIR]          DIR default: tools\\patches\\build (patches.dll and its import libraries)
The same flags as the TeknoParrot-free runtime (standalone\\native_build.py, Codex's): -m32 -march=pentium4 -msse2
-mfpmath=sse, UCRT, no C runtime start-up of mingw's; settings.c and ucrt_stdio.c are that runtime's own (read, not changed)."""
import os, sys, subprocess, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE); REPO = os.path.dirname(TOOLS); STAND = os.path.join(REPO, 'standalone')
sys.path.insert(0, os.path.join(TOOLS, 'import', 'core')); sys.path.insert(0, os.path.join(TOOLS, 'x86')); sys.path.insert(0, HERE)
import cbuild, implib
GCC = cbuild.GCC
X86 = ['-m32', '-march=pentium4', '-msse2', '-mfpmath=sse', '-ffreestanding', '-D_UCRT', '-D__USE_MINGW_ANSI_STDIO=0', '-D_CRT_SECURE_NO_WARNINGS',
       '-O2', '-std=c11', '-ffunction-sections', '-Wall', '-Wno-unused-function']
def run(cmd, **k):
    r = subprocess.run(cmd, capture_output=True, text=True, **k)
    if r.returncode: raise SystemExit('failed: %s\n%s' % (' '.join(cmd), (r.stdout + r.stderr)[-3000:]))
    if r.stderr.strip(): print(r.stderr.strip()[-2000:])
def main(argv):
    out = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(HERE, 'build'); os.makedirs(out, exist_ok=True)
    run([sys.executable, os.path.join(HERE, 'gen_blobs.py'), os.path.join(out, 'blobs.h')])
    units = [(os.path.join(HERE, 'patches.c'), 'patches.o'), (os.path.join(STAND, 'settings.c'), 'settings.o'), (os.path.join(STAND, 'ucrt_stdio.c'), 'ucrt_stdio.o'),
             (os.path.join(TOOLS, 'x86', 'builtins.c'), 'builtins.o')]
    maps = ['-ffile-prefix-map=%s=.' % p for p in (out, HERE, STAND, os.path.join(TOOLS, 'x86'))]          # no build paths in the DLL
    objs = []
    for src, o in units:
        op = os.path.join(out, o); run([GCC] + X86 + maps + ['-I', out, '-I', STAND, '-c', src, '-o', op]); objs.append(op)
    imp = os.path.join(out, 'imp')
    if implib.main(['--out', imp] + objs): raise SystemExit('implib: unresolved imports')
    libs = ['-l' + f[3:-2] for f in sorted(os.listdir(imp)) if f.startswith('lib') and f.endswith('.a')]
    dll = os.path.join(out, 'patches.dll')
    run([GCC, '-m32', '-nostdlib', '-nostartfiles', '-s', '-shared', '-Wl,-e,_DllMain@12', '-Wl,--kill-at,--exclude-all-symbols,--image-base,0x63000000,--no-insert-timestamp',
         '-Wl,--gc-sections'] + objs + ['-L', imp] + libs + ['-o', dll])
    print('patches.dll: %d bytes -> %s' % (os.path.getsize(dll), dll))
    if '--no-lockstep' not in argv:                                     # the DLL must plan exactly what patches.ps1 does, or the build fails
        import lockstep
        if lockstep.main(['--dll', dll]): raise SystemExit('lockstep: patches.dll and patches.ps1 differ; nothing is to be installed')
    return dll
if __name__ == '__main__':
    main(sys.argv[1:])
