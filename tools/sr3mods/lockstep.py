"""sr3mods.ps1 and sr3mods.dll in lockstep (Bruno, 2026-10-15: "everytime something changes, the changes should cascade
straight to .ps1 and .dll ... automated via script, so no ambiguity remains"):

    python lockstep.py [--dll <sr3mods.dll>]          (build.py runs it after every build; a difference fails the build)

For a matrix of settings (every profile in profiles.yaml, the built-in SR3 cameras, the default; the popup size, mouse
smoothing, camera blend at off / default / other values; canary; a profiles file with hiddenCameras: false and its
own fallbacks), both are asked what they would write into a freshly started game:
  sr3mods.ps1  through plan_ps1.ps1 (its own code against a fake game holding the original bytes)
  sr3mods.dll  through plan32.exe -> sr3mods_plan (the code sr3mods_start runs)
and the two plans must be the same: every patch site's bytes, every hook and pointer (as block + offset), the camera
block's 16 KB image, the profile and the camera list. The bytes themselves come from sr3mods.ps1 in both (gen_blobs.py
copies them into the DLL at each build), so what this checks is the logic around them."""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, '..', 'import', 'core')); sys.path.insert(0, os.path.join(HERE, '..', 'x86'))
import cbuild, implib

def runner(out):
    exe = os.path.join(out, 'plan32.exe')
    if not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(os.path.join(HERE, 'plan32.c')):
        o = os.path.join(out, 'plan32.o'); imp = os.path.join(out, 'plan32_imp')
        subprocess.run([cbuild.GCC, '-m32', '-O2', '-c', os.path.join(HERE, 'plan32.c'), '-o', o], check=True)
        if implib.main(['--out', imp, '--dll', 'kernel32', '--dll', 'shell32', o]): raise SystemExit('implib failed for plan32')
        subprocess.run([cbuild.GCC, '-m32', '-nostdlib', '-nostartfiles', '-Wl,-e,_start@0', o, '-L', imp, '-lkernel32', '-lshell32', '-o', exe], check=True)
    return exe

def profiles():
    names = []
    for ln in open(os.path.join(REPO, 'profiles.yaml'), encoding='utf-8'):
        s = ln.split('#', 1)[0].rstrip()
        if s.startswith('  ') and not s.startswith('   ') and s.strip().endswith(':'): names.append(s.strip()[:-1].strip('"\''))
    return names

def cases(tmp):
    alt = os.path.join(tmp, 'alt_profiles.yaml')                     # hiddenCameras off, no mouseSmoothing / cameraBlend of its own (falls back to profiles.yaml's)
    src = open(os.path.join(REPO, 'profiles.yaml'), encoding='utf-8').read().splitlines()
    open(alt, 'w', newline='\n').write('\n'.join([l for l in src if not l.lower().startswith(('mousesmoothing', 'camerablend', 'hiddencameras'))] + ['hiddenCameras: false', '']))
    C = [dict()] + [dict(CameraProfile=p) for p in profiles() + ['SR3 Chase', 'SR3 Chase Far', 'Baseline']]
    C += [dict(Overlay=0), dict(Overlay=120), dict(MouseSmoothing=0), dict(MouseSmoothing=0.02), dict(CameraBlend=0), dict(CameraBlend=1.5), dict(Canary=True),
          dict(ProfilesFile=alt), dict(ProfilesFile=alt, CameraProfile='SR3 Chase Far', MouseSmoothing=0.3, Overlay=200)]
    return C

def settings_yaml(path, c):
    keys = {'CameraProfile': 'camera_profile', 'ProfilesFile': 'profiles_file', 'Overlay': 'overlay', 'MouseSmoothing': 'mouse_smoothing', 'CameraBlend': 'camera_blend', 'Canary': 'canary'}
    base = open(os.path.join(REPO, 'standalone', 'settings.yaml'), encoding='utf-8').read().replace('\r\n', '\n').rstrip('\n')
    lines = [base, 'patches:', "  mod_folder: '%s'" % REPO]
    for k, v in c.items(): lines.append("  %s: %s" % (keys[k], ("'%s'" % v) if isinstance(v, str) else ('true' if v is True else repr(v))))
    open(path, 'w', newline='\n').write('\n'.join(lines) + '\n')

def main(argv):
    dll = argv[argv.index('--dll') + 1] if '--dll' in argv else os.path.join(HERE, 'build', 'sr3mods.dll')
    tmp = tempfile.mkdtemp(prefix='lockstep_'); exe = runner(os.path.dirname(dll)); bad = 0; n = 0
    import hashlib
    want = hashlib.sha256(open(os.path.join(REPO, 'sr3mods.ps1'), 'rb').read()).hexdigest()
    got = subprocess.run([exe, dll], capture_output=True, text=True).stdout.strip()
    if got != want: print('STALE: %s was built from another sr3mods.ps1 (%s, now %s): build it again (tools\\patches\\build.py)' % (dll, got[:12] or '?', want[:12])); return 2
    for k, c in enumerate(cases(tmp)):
        sy = os.path.join(tmp, 's%d.yaml' % k); pd = os.path.join(tmp, 'dll%d.json' % k); pp = os.path.join(tmp, 'ps%d.json' % k); settings_yaml(sy, c)
        rd = subprocess.run([exe, dll, sy, pd]).returncode
        a = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(HERE, 'plan_ps1.ps1'), '-Out', pp]
        for key, v in c.items(): a += ['-' + key] if v is True else ['-' + key, str(v)]
        rp = subprocess.run(a, capture_output=True, text=True)
        D = json.load(open(pd, encoding='utf-8')) if os.path.exists(pd) else {'error': 'no plan (exit %d)' % rd}
        P = json.load(open(pp, encoding='utf-8-sig')) if os.path.exists(pp) else {'error': 'no plan: ' + (rp.stdout + rp.stderr).strip()[-300:]}
        sx = os.path.join(os.path.dirname(dll), 'sr3mods.exe')          # the outside front end, its settings as switches (CamLab's way)
        if os.path.exists(sx):
            pe = os.path.join(tmp, 'exe%d.json' % k); flags = {'CameraProfile': '--camera-profile', 'ProfilesFile': '--profiles-file', 'Overlay': '--overlay',
                                                            'MouseSmoothing': '--mouse-smoothing', 'CameraBlend': '--camera-blend', 'Canary': '--canary'}
            xa = [sx, 'plan', pe, '--mod', REPO]
            for key, v in c.items(): xa += [flags[key]] if v is True else [flags[key], str(v)]
            subprocess.run(xa, capture_output=True)
            E = json.load(open(pe, encoding='utf-8')) if os.path.exists(pe) else {'error': 'no plan from sr3mods.exe'}
            if E != D: D = dict(D, sr3mods_differs_from_dll=[key for key in sorted(set(D) | set(E)) if D.get(key) != E.get(key)])
        n += 1; diffs = [key for key in sorted(set(D) | set(P)) if D.get(key) != P.get(key)]
        if diffs:
            bad += 1; print('DIFFERENT %s: %s' % (c or '(defaults)', ', '.join(diffs)))
            for key in diffs[:3]:
                x, y = D.get(key), P.get(key)
                if isinstance(x, str) and isinstance(y, str) and len(x) == len(y): j = next(i for i in range(len(x)) if x[i] != y[i]); print('   %s first differs at byte %d: dll %s ps1 %s' % (key, j // 2, x[j & ~1:j + 16], y[j & ~1:j + 16]))
                else: print('   %s: dll %s | ps1 %s' % (key, str(x)[:200], str(y)[:200]))
        else: print('same      %s' % (c or '(defaults)'))
    print('LOCKSTEP: %d settings, %d the same, %d different' % (n, n - bad, bad))
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
