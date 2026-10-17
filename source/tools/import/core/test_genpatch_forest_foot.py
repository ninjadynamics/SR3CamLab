"""Forest floor meets local kerb feet, including sloping kerbs; no scenery moves."""
import copy
import unittest
from types import SimpleNamespace
import numpy as np
from genpatch1995 import CFG, forest_foot


def scene(triangles, kerb=None):
    kerb = kerb or [(0, 1, 0), (4, 2, 0), (4, 1, 0), (0, 0, 0)]
    return SimpleNamespace(cfg=dict(CFG), N=1, cut=[False], role=['paving'],
                           n=np.array([[0, 0, 1]]), P=[np.array(kerb, float)],
                           add=[('soil', list(t), [(0, 0)]*3, 'F') for t in triangles],
                           note=lambda *args: None)


class ForestFootTests(unittest.TestCase):
    def test_sloping_kerb_both_ends_and_shared_vertices(self):
        sc = scene([[(0, 1, 0), (0, 0, 3), (1, 0, 3)],
                    [(4, 2, 0), (4, 1, 3), (3, 1, 3)],
                    [(1, 0, 3), (0, 1, 0), (2, 0, 3)]])
        original = sc.P[0].copy()
        forest_foot(sc)
        self.assertEqual(sc.add[0][1][0], (0, 0, 0))
        self.assertEqual(sc.add[1][1][0], (4, 1, 0))
        self.assertEqual(sc.add[2][1][1], (0, 0, 0))
        np.testing.assert_array_equal(sc.P[0], original)

    def test_level_floor_is_not_pulled_down(self):
        sc = scene([[(0, 1, 0), (0, 1, 3), (1, 1, 3)]])
        before = copy.deepcopy(sc.add); forest_foot(sc)
        self.assertEqual(sc.add, before)

    def test_tall_wall_and_unrelated_fill_are_untouched(self):
        sc = scene([[(0, 3, 0), (0, 0, 3), (1, 0, 3)]],
                   [(0, 3, 0), (4, 3, 0), (4, 0, 0), (0, 0, 0)])
        before = copy.deepcopy(sc.add); forest_foot(sc)
        self.assertEqual(sc.add, before)
        sc = scene([[(0, 1, 0), (0, 0, 3), (1, 0, 3)]])
        t, p, uv, _ = sc.add[0]; sc.add[0] = (t, p, uv, 'P')
        before = copy.deepcopy(sc.add); forest_foot(sc)
        self.assertEqual(sc.add, before)

    def test_triangle_order_cannot_trigger_a_cascade(self):
        # High end qualifies; lowering it must not then qualify the low end.
        a = [(4, 2, 0), (3, 0, 3), (4, 0, 3)]
        b = [(0, 1.5, 0), (4, 2, 0), (0, 0, 3)]
        kerb = [(0, 1.5, 0), (4, 2, 0), (4, 1, 0), (0, .5, 0)]
        first, second = scene([a, b], kerb), scene([b, a], kerb)
        # Separate level kerb pieces make both corners eligible in the old
        # highest-corner filter, isolating visit order from the slope defect.
        for sc in (first, second):
            sc.N = 2; sc.cut = [False, False]; sc.role = ['paving', 'paving']
            sc.n = np.array([[0, 0, 1], [0, 0, 1]])
            sc.P = [np.array([(0, 1.5, 0), (-1, 1.5, 0), (-1, .5, 0), (0, .5, 0)]),
                    np.array([(4, 2, 0), (5, 2, 0), (5, 1, 0), (4, 1, 0)])]
        forest_foot(first); forest_foot(second)
        self.assertEqual(first.add, list(reversed(second.add)))
        self.assertEqual(first.add[1][1][0], (0, 1.5, 0))


if __name__ == '__main__':
    unittest.main()
