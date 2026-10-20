"""Regression checks: invalid/stale edits, active-game refusal, rollback."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from relief_apply import ROOT, YAML, RECEIPT, BASELINE, JOURNAL, atomic, checked_install, request_settings, revision, load, yaml_text

class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for rel in (YAML, RECEIPT, BASELINE, "scratchpad/pom-depth-tuner-20261020/inventory.json"):
            dest = self.root / rel; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes((ROOT / rel).read_bytes())
        cfg = load(self.root / YAML)
        self.payload = dict(revision=revision(self.root), families=cfg["families"], excluded_variants=cfg["excluded_variants"],
                            global_depth_initial=.6, live_tuner=True)
    def tearDown(self): self.temp.cleanup()
    def test_accepted_and_empty_exclusions(self):
        p = copy.deepcopy(self.payload); p["excluded_variants"] = []
        cfg = request_settings(p, self.root)
        path = self.root / "new.yaml"; path.write_text(yaml_text(cfg, self.root))
        self.assertEqual(load(path)["excluded_variants"], [])
    def test_invalid_and_stale(self):
        for key, value in [("revision","stale"), ("global_depth_initial",float("nan")), ("global_depth_initial",.65),
                           ("live_tuner","true"), ("excluded_variants",["../../bad"]), ("families",{})]:
            p = copy.deepcopy(self.payload); p[key] = value
            with self.assertRaises(ValueError): request_settings(p,self.root)
        p = copy.deepcopy(self.payload); p["families"][next(iter(p["families"]))] = 13
        with self.assertRaises(ValueError): request_settings(p,self.root)
    def test_atomic_failure_restores_all(self):
        (self.root / "a").write_bytes(b"old-a"); (self.root / "b").write_bytes(b"old-b")
        (self.root / "new").write_bytes(b"new")
        count = 0
        def fail(path,data):
            nonlocal count
            count += 1
            if count == 2: raise OSError("injected failure")
            atomic(path,data)
        with self.assertRaises(OSError):
            checked_install(self.root, {"a":self.root/"new","b":self.root/"new"}, self.root/"backup",
                            is_closed=lambda:True,replace=fail)
        self.assertEqual((self.root/"a").read_bytes(),b"old-a")
        self.assertEqual((self.root/"b").read_bytes(),b"old-b")
        self.assertFalse((self.root/JOURNAL).exists())
    def test_game_running_blocks_writes(self):
        (self.root/"a").write_bytes(b"old");(self.root/"new").write_bytes(b"new")
        with self.assertRaises(RuntimeError):
            checked_install(self.root,{"a":self.root/"new"},self.root/"backup",is_closed=lambda:False)
        self.assertEqual((self.root/"a").read_bytes(),b"old")
        self.assertFalse((self.root/"backup").exists())
    def test_success_verifies_backup(self):
        (self.root/"a").write_bytes(b"old");(self.root/"new").write_bytes(b"new")
        checked_install(self.root,{"a":self.root/"new"},self.root/"backup",is_closed=lambda:True)
        self.assertEqual((self.root/"a").read_bytes(),b"new")
        self.assertEqual((self.root/"backup/a").read_bytes(),b"old")
        self.assertFalse((self.root/JOURNAL).exists())

if __name__ == "__main__": unittest.main()
