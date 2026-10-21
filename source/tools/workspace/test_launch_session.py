"""PLAY broker regression checks. All child processes are mocks; no game starts."""
from pathlib import Path
from unittest.mock import patch
import contextlib
import io
import json
import os
import tempfile
import unittest
import launch_session as launch


class Process:
    def __init__(self, code=0):
        self.code = code
        self.running = True
        self.terminated = False
        self.killed = False
        self.waits = []

    def wait(self, timeout=None):
        self.waits.append(timeout)
        self.running = False
        return self.code

    def poll(self):
        return None if self.running else self.code

    def terminate(self):
        self.terminated = True
        self.running = False

    def kill(self):
        self.killed = True
        self.running = False


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "config").mkdir()
        self.run = self.root / "runs" / "unique-run"
        self.run.mkdir(parents=True)
        self.cfg = {"python": "C:/Python Space/python.exe", "game": "game/Rally",
                    "baseline": "config/accepted-baseline.json", "settings": "settings.yaml",
                    "candidate": "content/handling/candidate.json", "pom": True}
        self.save_cfg()
        (self.root / self.cfg["baseline"]).write_text(json.dumps({"pom_native_library_update": True}))
        self.fresh = {"track.gfx": "a" * 64}
        self.preflight = {"verified_files": self.fresh, "started_utc": "2026-10-21T00:00:00Z",
                          "elapsed_ms": 125, "phases_ms": {"accepted_hashes": 100}}
        self.children = []
        self.calls = []
        self.fail_launch = False
        self.fail_second = False

        def popen(command, **options):
            if self.fail_second and len(self.children) == 1:
                raise OSError("recorder spawn failed")
            proc = Process(7 if self.fail_launch and command[0].endswith("launch.exe") else 0)
            self.children.append(proc)
            self.calls.append((command, options))
            return proc

        self.popen_patch = patch.object(launch.subprocess, "Popen", side_effect=popen)
        self.popen = self.popen_patch.start()
        self.addCleanup(self.popen_patch.stop)
        self.verify_patch = patch.object(launch, "verify")
        self.verify = self.verify_patch.start()
        self.addCleanup(self.verify_patch.stop)
        self.addCleanup(patch.stopall)

    def save_cfg(self):
        (self.root / "config/workspace.json").write_text(json.dumps(self.cfg))

    def invoke(self, **overrides):
        args = dict(run=self.run, preflight=self.preflight)
        args.update(overrides)
        with contextlib.redirect_stdout(io.StringIO()):
            return launch.run_session(self.root, **args)

    def test_success_exact_vectors_environment_and_wait_scope(self):
        old = dict(os.environ)
        out = self.invoke(settings=self.root / "run settings.yaml")
        self.verify.assert_called_once_with(self.root, verified_files=self.fresh)
        self.assertEqual(len(self.children), 3)
        host, recorder, native = [row[0] for row in self.calls]
        self.assertEqual(host, [self.cfg['python'], '-B', str(self.root / 'source/tools/handling/candidate_host.py'),
                               '--candidate', str(self.root / self.cfg['candidate']), '--game', str(self.root / 'game/Rally'),
                               '--out', str(self.run / 'candidate.csv')])
        self.assertEqual(recorder[-4:], ['--out', str(self.run / 'steering.csv'), '--seconds', '180'])
        self.assertEqual(native, [str(self.root / 'apps/runtime/launch.exe'), '--settings',
                                  str(self.root / 'run settings.yaml'), '--no-watchdog'])
        # Wait only on native launcher, never on the background helper lifetime.
        self.assertEqual([p.waits for p in self.children], [[], [], [None]])
        self.assertTrue(all(not p.terminated for p in self.children))
        for command, options in self.calls:
            self.assertEqual(options['cwd'], str(self.root))
            self.assertEqual(options['env']['SR3LAB_POM'], '1')
            self.assertTrue(options['close_fds'])
            self.assertEqual(options['stdin'], launch.subprocess.DEVNULL)
            self.assertNotIn('shell', options)
            if os.name == 'nt':
                self.assertEqual(options['creationflags'], launch.subprocess.CREATE_NO_WINDOW)
                self.assertEqual(options['startupinfo'].wShowWindow, launch.subprocess.SW_HIDE)
        self.assertEqual(dict(os.environ), old)
        self.assertTrue(out['game_started'])
        receipt = json.loads((self.run / 'launch-timing.json').read_text())
        self.assertEqual(receipt['preflight_ms'], 125)
        self.assertEqual(receipt['preflight_phases_ms'], {'accepted_hashes': 100})
        self.assertEqual(set(receipt['phases_ms']), {'relief_verified', 'candidate_spawned', 'recorder_spawned',
                                                  'launcher_spawned', 'launcher_returned', 'broker_finished'})
        self.assertTrue(all((self.run / (n + ext)).is_file() for n in ('candidate', 'recorder') for ext in ('.log', '.err')))

    def test_check_never_spawns_or_writes(self):
        before = list(self.root.rglob('*'))
        out = self.invoke(check=True, run=None)
        self.verify.assert_called_once()
        self.popen.assert_not_called()
        self.assertEqual(list(self.root.rglob('*')), before)
        self.assertFalse(out['game_started'])

    def test_invalid_relief_does_not_start_any_child(self):
        self.verify.side_effect = AssertionError('stale maps')
        with self.assertRaisesRegex(AssertionError, 'stale maps'):
            self.invoke()
        self.popen.assert_not_called()

    def test_launcher_failure_stops_only_own_helpers(self):
        self.fail_launch = True
        with self.assertRaisesRegex(RuntimeError, '7'):
            self.invoke()
        self.assertEqual([p.terminated for p in self.children], [True, True, False])
        report = json.loads((self.run / 'launch-timing.json').read_text())
        self.assertFalse(report['game_started'])
        self.assertIn('7', report['error'])

    def test_second_helper_failure_cleans_first(self):
        self.fail_second = True
        with self.assertRaisesRegex(OSError, 'recorder spawn'):
            self.invoke()
        self.assertEqual(len(self.children), 1)
        self.assertTrue(self.children[0].terminated)

    def test_no_candidate_no_helpers(self):
        self.cfg['candidate'] = None
        self.cfg['pom'] = False
        self.save_cfg()
        self.invoke()
        self.verify.assert_not_called()
        self.assertEqual(len(self.children), 1)
        self.assertEqual(self.calls[0][1]['env']['SR3LAB_POM'], '0')

    def test_unknown_receipt_has_no_pom_validation(self):
        (self.root / self.cfg['baseline']).write_text('{}')
        self.invoke(check=True)
        self.verify.assert_not_called()
        self.popen.assert_not_called()

    def test_paths_cannot_escape_workspace(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.invoke(settings=self.root.parent / 'other.yaml')
        self.popen.assert_not_called()

    def test_required_run_before_spawning(self):
        with self.assertRaisesRegex(ValueError, 'required'):
            self.invoke(run=None)
        self.popen.assert_not_called()

    def test_missing_run_before_spawning(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.invoke(run=self.root / 'missing')
        self.popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
