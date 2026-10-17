"""The C helpers: how each one is built, in one place (the "makefile"). A helper is compiled on first use; to build them all at
once, and to see every command:
    python cbuild.py              build what is missing           python cbuild.py --list     the table below and the DLL names
    python cbuild.py --rebuild    build every helper again
The table: helper -> its folder (under tools/import/core), the units it is compiled from with each unit's own flags (a unit that
#includes another file is listed with it in 'hashed'), and every source whose bytes name the DLL (<helper>.<md5>.dll: one file
per version of the sources, as a running build keeps its own DLL loaded and Windows will not replace it).
Flags for every unit: -O3, the target, -fopenmp. '-ffp-contract=off' where the C must do numpy's arithmetic (no fused
multiply-add); elsewhere gcc fuses as the target allows, which is why the target is fixed.
    GCC       SR3_GCC, else the settings' 'gcc', else the toolchain zip's (tools/mingw/bin), else winget's WinLibs, else gcc on
              PATH, else C:\\mingw64\\bin. Only needed when a DLL is missing.
    MARCH     SR3_MARCH, else the settings' 'march', else x86-64-v3 (AVX2 + FMA: every such PC compiles the same code, and on
              the author's PC it gives the native build's bytes, checked 2026-10-15). Other targets than native get their own DLL names.
    runtime() puts the folders of the DLLs' own runtime (OpenMP: libgomp-1.dll, libwinpthread-1.dll, libgcc_s_seh-1.dll) on the
              DLL search path: gcc's folder and tools/python, those that exist."""
import os, sys, glob, json, shutil, hashlib, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.normpath(os.path.join(HERE, '..', '..'))
FOC = ['-ffp-contract=off']
HELPERS = {
    'fastgeo':  dict(dir='.', units=[('fastgeo.c', FOC)], hashed=['fastgeo.c']),
    'nplapack': dict(dir='.', units=[('nplapack.c', FOC)], hashed=['nplapack.c']),
    'round1995': dict(dir='.', units=[('round1995.c', FOC)], hashed=['round1995.c']),
    'fastdxt':  dict(dir='.', units=[('fastdxt.c', [])], hashed=['fastdxt.c']),
    'fastseal': dict(dir='.', units=[('fastseal.c', FOC)], hashed=['fastseal.c']),
    'rays':     dict(dir='.', units=[('rays.c', [])], hashed=['rays.c']),
    'fastlm':   dict(dir='.', units=[('fastlm_rays.c', []), ('fastlm.c', FOC)], hashed=['rays.c', 'fastlm_rays.c', 'fastlm.c']),
    'rtg5':     dict(dir='rtbake', units=[('rtg2_rays.c', []), ('rtg5.c', FOC), ('rtg5prep.c', FOC)], hashed=['rays.c', 'fastlm_rays.c', 'rtg2_rays.c', 'rtg5.c', 'rtg5prep.c']),
    'rtcompose': dict(dir='rtbake', units=[('rtcompose.c', FOC)], hashed=['rtcompose.c']),
    'audio_dsp': dict(dir='../../audio', units=[('audio_dsp.c', FOC)], hashed=['audio_dsp.c', 'pocketfft.h']),
}

def _settings():
    p = os.environ.get('SR3_SETTINGS') or os.path.join(TOOLS, '..', '..', 'config', 'import.json')
    try: return json.load(open(p, encoding='utf-8-sig'))
    except (OSError, ValueError): return {}

def find_gcc():
    S = _settings(); cands = [os.environ.get('SR3_GCC'), S.get('gcc'), os.path.join(TOOLS, '..', '..', 'toolchain', 'mingw', 'bin', 'gcc.exe')]
    cands += sorted(glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WinGet', 'Packages', 'BrechtSanders.WinLibs*', 'mingw64', 'bin', 'gcc.exe')))
    cands += [shutil.which('gcc'), r'C:\mingw64\bin\gcc.exe']
    return next((c for c in cands if c and os.path.isfile(c)), cands[-1])

GCC = find_gcc()
TARGET = os.environ.get('SR3_MARCH') or _settings().get('march') or 'x86-64-v3'      # the same code on every PC (any AVX2 CPU); 'native' for this PC's own
MARCH = '-march=' + TARGET
XFLAGS = os.environ.get('SR3_CFLAGS', '').split()                       # (tests) more flags for every unit; such DLLs get names of their own
_DONE = []

def runtime():
    """the OpenMP runtime's folders on the DLL search path (once per process)"""
    if _DONE: return
    for d in (os.path.dirname(GCC), os.path.join(TOOLS, 'python')):
        if os.path.isdir(d): os.add_dll_directory(os.path.abspath(d))
    _DONE.append(1)

def name(helper):
    h = HELPERS[helper]; d = os.path.normpath(os.path.join(HERE, h['dir'])); m = hashlib.md5()
    for f in h['hashed']: m.update(open(os.path.join(d, f), 'rb').read())
    xf = ('.' + hashlib.md5(' '.join(XFLAGS).encode()).hexdigest()[:6]) if XFLAGS else ''
    return os.path.join(TOOLS, '..', '..', 'scratchpad', 'build', 'helpers', '%s.%s%s%s.dll' % (helper, m.hexdigest()[:8], '' if TARGET == 'native' else '.' + TARGET, xf))

def commands(helper, out, tmpdir):
    h = HELPERS[helper]; d = os.path.join(HERE, h['dir'])
    if len(h['units']) == 1:
        src, fl = h['units'][0]; return [[GCC, '-O3', MARCH] + fl + XFLAGS + ['-fopenmp', '-shared', '-o', out, os.path.join(d, src)]]
    objs = [os.path.join(tmpdir, '%d.o' % k) for k in range(len(h['units']))]
    return ([[GCC, '-O3', MARCH] + fl + XFLAGS + ['-fopenmp', '-c', '-o', o, os.path.join(d, src)] for (src, fl), o in zip(h['units'], objs)] +
            [[GCC, '-shared', '-fopenmp', '-o', out] + objs])

def dll(helper, rebuild=False, log=None):
    """the helper's DLL, built when it is not there; old versions nobody has loaded any more are removed"""
    path = name(helper)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if rebuild or not os.path.exists(path):
        if not os.path.isfile(GCC): raise RuntimeError('%s needs building and there is no C compiler (%s): run the toolchain setup (IMPORT.bat) or set "gcc" in tools/import/settings.json' % (os.path.basename(path), GCC))
        td = tempfile.mkdtemp(prefix='.build_%s_' % helper, dir=os.path.dirname(path)); tmp = os.path.join(td, 'out.dll')      # beside the DLL: os.replace cannot cross drives
        try:
            for cmd in commands(helper, tmp, td):
                if log: log(' '.join('"%s"' % c if ' ' in c else c for c in cmd))
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(path))
                if r.returncode != 0: raise RuntimeError('%s does not compile: %s' % (helper, r.stderr[-1500:]))
            try: os.replace(tmp, path)
            except OSError:
                if not os.path.exists(path): raise                       # (it is there: another build got there first and has it loaded)
        finally: shutil.rmtree(td, ignore_errors=True)
        for old in glob.glob(os.path.join(os.path.dirname(path), helper + '.*.dll')):
            if old != path and not XFLAGS and (TARGET == 'native') == (os.path.basename(old).count('.') == 2):      # the same target's older versions only
                try: os.remove(old)
                except OSError: pass
    return path

if __name__ == '__main__':
    a = sys.argv[1:]
    print('gcc %s, target %s' % (GCC, TARGET))
    for h in HELPERS:
        if '--list' in a: print('  %-9s %-60s %s' % (h, os.path.relpath(name(h), HERE), ' + '.join('%s %s' % (s, ' '.join(f)) for s, f in HELPERS[h]['units'])))
        else: p = dll(h, rebuild='--rebuild' in a, log=lambda s: print('   ' + s)); print('  %-9s %s' % (h, os.path.relpath(p, HERE)))
