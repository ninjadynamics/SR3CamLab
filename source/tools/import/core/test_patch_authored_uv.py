"""Explicit authored UVs survive; ordinary unmapped hand patches still get mapping."""
import tempfile
import unittest
from pathlib import Path

import coursepatch


class AuthoredUVTest(unittest.TestCase):
    def test_mapping_policy(self):
        patch = dict(format='sr3lab course patch', version=3, base={}, move=[], remove=[],
                     add=[dict(tile='test', p=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                               uv=[[0, 0], [0, 0], [0, 0]])])
        with tempfile.TemporaryDirectory() as folder:
            export = Path(folder) / 'source.obj'
            export.write_text('# fixture\nv 0 0 0\n')
            mapped = coursepatch.apply([], patch, 0, 0, export, lambda _: None)
            preserved = coursepatch.apply([], dict(patch, preserve_authored_uv=True),
                                          0, 0, export, lambda _: None)
        self.assertGreater(coursepatch._uvarea(mapped[0][3]), 0)
        self.assertEqual(preserved[0][3], [(0, 0)] * 3)
        self.assertEqual(mapped[0][2], preserved[0][2])


if __name__ == '__main__':
    unittest.main()
