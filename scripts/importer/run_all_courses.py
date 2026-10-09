"""Every course and variant through import_classic.py, one after the other (log: ../tmp/run_all.log).
    python run_all_courses.py [course ...]"""
import subprocess, sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__)); log = open(os.path.join(HERE, '..', 'tmp', 'run_all.log'), 'a')
for c in sys.argv[1:] or ['3', '4', '2', '1']:
    for v in ('allsr3', 'mixed', 'classic'):
        t = time.time(); r = subprocess.run([sys.executable, os.path.join(HERE, 'import_classic.py'), 'src', c, v], capture_output=True, text=True, cwd=HERE)
        keep = [l for l in r.stdout.split('\n') if any(k in l for k in ('written', 'renders', 'FAILED', 'all-SR3', 'retextured', 'classic visual', 'facade walls', 'faces by'))]
        log.write('== src %s %s (%.0f s, exit %d)\n%s\n%s\n' % (c, v, time.time() - t, r.returncode, '\n'.join(keep), r.stderr[-1500:] if r.returncode else '')); log.flush()
print('done')
