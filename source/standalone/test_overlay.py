"""Safety and independence tests using tiny synthetic assets, never game data."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import overlay

class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sr3lab-test-")
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "Rally.exe").write_bytes(b"test-executable")
        (self.source / "config.ini").write_text("original")
        (self.source / "assets").mkdir()
        (self.source / "assets/track.sbf").write_bytes(b"original-track")
        self.dll = self.root / "dinput8.dll"
        self.dll.write_bytes(b"test-runtime")
        (self.root / "SDL-LICENSE.txt").write_text("test license")
        for name in ('launch.exe', 'settings.exe', 'raylib-LICENSE.txt'):
            (self.root / name).write_bytes(b'test companion')
        self.version = patch.object(overlay, "EXE_SHA256", overlay.digest(self.source / "Rally.exe"))
        self.version.start()

    def tearDown(self):
        self.version.stop()
        self.tmp.cleanup()

    def test_copy_is_independent(self):
        target = self.root / "copy"
        overlay.create(self.source, target, dll=self.dll)
        (target / "assets/track.sbf").write_bytes(b"modified")
        (target / "config.ini").write_text("modified")
        self.assertEqual((self.source / "assets/track.sbf").read_bytes(), b"original-track")
        self.assertEqual((self.source / "config.ini").read_text(), "original")
        self.assertTrue(json.loads((target / overlay.MARKER).read_text())["complete"])
        settings = (target / "settings.yaml").read_text(encoding="utf-8")
        suite = overlay.ROOT.parent.resolve().as_posix().replace("'", "''")
        self.assertIn(f"mod_folder: '{suite}'", settings)
        self.assertIn("watchdog: on", settings)

    def test_hardlink_materializes_before_modification(self):
        target = self.root / "linked"
        overlay.create(self.source, target, mode="hardlink", dll=self.dll)
        self.assertTrue(os.path.samefile(self.source / "assets/track.sbf", target / "assets/track.sbf"))
        self.assertFalse(os.path.samefile(self.source / "Rally.exe", target / "Rally.exe"))
        overlay.materialize(target)
        self.assertFalse(os.path.samefile(self.source / "assets/track.sbf", target / "assets/track.sbf"))
        (target / "assets/track.sbf").write_bytes(b"modified")
        self.assertEqual((self.source / "assets/track.sbf").read_bytes(), b"original-track")

    @unittest.skipUnless(os.name == "nt", "Windows junctions")
    def test_junction_materializes_without_touching_source(self):
        target = self.root / "junction"
        overlay.create(self.source, target, mode="junction", dll=self.dll)
        self.assertEqual((target / "assets").resolve(), (self.source / "assets").resolve())
        overlay.materialize(target)
        self.assertNotEqual((target / "assets").resolve(), (self.source / "assets").resolve())
        (target / "assets/track.sbf").write_bytes(b"modified")
        self.assertEqual((self.source / "assets/track.sbf").read_bytes(), b"original-track")

    def test_existing_nested_and_wrong_version_rejected(self):
        for target in (self.source, self.source / "nested", self.root):
            with self.assertRaises(ValueError):
                overlay.create(self.source, target, dll=self.dll)
        (self.source / "Rally.exe").write_bytes(b"wrong-version")
        target = self.root / "wrong"
        with self.assertRaises(ValueError):
            overlay.create(self.source, target, dll=self.dll)
        self.assertFalse(target.exists())

    def test_missing_dependency_does_not_create_destination(self):
        (self.root / "SDL-LICENSE.txt").unlink()
        target = self.root / "incomplete"
        with self.assertRaises(ValueError):
            overlay.create(self.source, target, dll=self.dll)
        self.assertFalse(target.exists())

if __name__ == "__main__":
    unittest.main()
