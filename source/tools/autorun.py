"""Unattended test run: Start -> Classic -> View Change n times -> confirm -> drive a fixed pattern.
    python autorun.py <n view-change presses> [hook]
Needs pad.py's hook in TeknoParrotUi ('hook' installs it first). Screenshots are taken by a separate loop."""
import subprocess, sys, time, os
HERE = os.path.dirname(os.path.abspath(__file__))
def pad(*a): subprocess.run([sys.executable, os.path.join(HERE, 'pad.py')] + [str(x) for x in a], check=True)
def gas_tap(): pad('set', 'gas=1'); time.sleep(0.6); pad('set')
n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
if 'hook' in sys.argv: pad('hook'); time.sleep(2)
pad('tap', 'start', 0.3); time.sleep(6)
for _ in range(2): pad('set', 'steer=1'); time.sleep(1); pad('set'); time.sleep(3)      # Championship -> Quick Race -> Classic
for _ in range(n): pad('tap', 'view', 0.2); time.sleep(1.5)
gas_tap(); time.sleep(5); gas_tap(); time.sleep(5); gas_tap()                            # mode, car, transmission
time.sleep(24)                                                                           # load, panorama, countdown
for state, secs in ((('gas=1',), 9), (('gas=0.7', 'steer=-0.2'), 3), (('gas=0.9',), 5), (('gas=0.6', 'steer=0.15'), 2), (('gas=0.9',), 6), ((), 1)):
    pad('set', *state); time.sleep(secs)
print('done')
