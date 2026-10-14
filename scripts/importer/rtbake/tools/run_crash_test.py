"""One unattended run of a Classic entry with the crash logger attached (the owner asked for it, 2026-10-13: "yeah, you launch the game").
    python run_crash_test.py <entry number = how many View Change presses on Classic>
Starts PLAY.bat in its own window, waits until the launcher says the game has booted and dbg.py (started beforehand, waiting) has attached, then
tools\\autorun.py drives Start -> Classic -> entry -> confirm. Prints what the logger wrote."""
import subprocess, time, os, sys
CAM = r'F:\Jogos\SEGA Rally 3\SR3CamLab'; SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
def running(): return 'rally.exe' in subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Rally.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout.lower()
NOLAUNCH = 'nolaunch' in sys.argv                                     # PLAY.bat was started just before (Start-Process): only wait and drive
if running() and not NOLAUNCH: sys.exit('the game is already running: not started again')
t0 = time.time() - (60 if NOLAUNCH else 0); log = os.path.join(CAM, 'play.log'); ok = False
if not NOLAUNCH: subprocess.Popen('start "SEGA Rally 3" cmd /c PLAY.bat', shell=True, cwd=CAM)
while time.time() - t0 < 150:
    time.sleep(1)
    try: s = open(log, encoding='utf-8', errors='replace').read()
    except OSError: continue
    if os.path.getmtime(log) > t0 - 1 and 'Camera mod is ACTIVE' in s: ok = True; break
    if os.path.getmtime(log) > t0 - 1 and 'Game closed' in s: break
if not ok: print(open(log, encoding='utf-8', errors='replace').read()[-1500:]); sys.exit('the game did not finish booting')
print('booted after %.0f s' % (time.time() - t0), flush=True); cl = os.path.join(SP, 'crash.log')
for _ in range(45):
    if os.path.exists(cl) and 'attached' in open(cl).read(): break
    time.sleep(1)
print('logger:', (open(cl).read().strip().replace('\n', ' | ') if os.path.exists(cl) else 'no crash.log'), flush=True); time.sleep(3)
try:
    r = subprocess.run([sys.executable, os.path.join(CAM, 'tools', 'autorun.py'), str(n), 'hook'], capture_output=True, text=True, timeout=240); print('autorun: exit %d %s %s' % (r.returncode, r.stdout[-200:].strip(), r.stderr[-700:].strip()), flush=True)
except subprocess.TimeoutExpired: print('autorun: still going after 240 s', flush=True)
for _ in range(15):
    if not running(): break
    time.sleep(1)
print('game %s after the run (%.0f s since start)' % ('STILL RUNNING' if running() else 'gone', time.time() - t0))
print('--- launcher log:'); print('\n'.join(l for l in open(log, encoding='utf-8', errors='replace').read().splitlines() if not any(k in l for k in ('Framing', 'Strength', 'View Change cycles', 'popup', "Profile '")))[-1800:])
print('--- crash logger:'); print(open(cl).read()[-6000:] if os.path.exists(cl) else 'nothing written')
