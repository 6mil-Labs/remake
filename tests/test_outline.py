"""Geometry contracts for REMAKE's straight-sided, radiused PCB perimeter."""

from collections import Counter, defaultdict
import importlib.util
import math
from pathlib import Path
import unittest


BOARD_PATH = Path(__file__).resolve().parents[1] / 'hw/remake.kicad_pcb'


@unittest.skipUnless(importlib.util.find_spec('pcbnew'), 'requires KiCad pcbnew Python module')
class OutlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew

        cls.pcbnew = pcbnew
        cls.board = pcbnew.LoadBoard(str(BOARD_PATH))
        cls.edges = [s for s in cls.board.GetDrawings() if s.GetLayer() == pcbnew.Edge_Cuts]
        cls.joins = defaultdict(list)
        for edge in cls.edges:
            for p in [edge.GetStart(), edge.GetEnd()]:
                cls.joins[(p.x, p.y)].append(edge)

    def test_corners_use_nominal_one_or_two_mm_arcs_not_chamfers(self):
        counts = Counter(s.GetShapeStr() for s in self.edges)
        self.assertEqual(set(counts), {'Line', 'Arc'})
        self.assertGreater(counts['Arc'], 0)
        self.assertEqual(counts['Line'], counts['Arc'])
        for edge in self.edges:
            if edge.GetShapeStr() == 'Arc':
                # Interactive R2 fillets have three-point rounding amplified
                # on shallow arcs. Allow1um, not a forced uniformR1 outline.
                radius = self.pcbnew.ToMM(edge.GetRadius())
                self.assertLessEqual(min(abs(radius-r) for r in [1.0,2.0]),0.001)

    def test_every_straight_to_arc_join_is_tangent(self):
        for p, edges in self.joins.items():
            self.assertEqual(len(edges), 2)
            self.assertEqual({s.GetShapeStr() for s in edges}, {'Line', 'Arc'})
            arc = next(s for s in edges if s.GetShapeStr() == 'Arc')
            line = next(s for s in edges if s.GetShapeStr() == 'Line')
            center = arc.GetCenter()
            radius = (p[0] - center.x, p[1] - center.y)
            a, b = line.GetStart(), line.GetEnd()
            direction = (b.x - a.x, b.y - a.y)
            product = math.hypot(*radius) * math.hypot(*direction)
            self.assertGreater(product, 0)
            normalized_dot = sum(x * y for x, y in zip(radius, direction)) / product
            self.assertAlmostEqual(normalized_dot, 0, delta=0.0001, msg=f'Non-tangent join at {p}')

    def test_perimeter_is_one_connected_closed_kicad_contour(self):
        self.assertTrue(self.joins)
        self.assertTrue(all(len(edges) == 2 for edges in self.joins.values()))
        seen = set()
        pending = [next(iter(self.joins))]
        while pending:
            p = pending.pop()
            if p in seen:
                continue
            seen.add(p)
            for edge in self.joins[p]:
                pending.extend((v.x, v.y) for v in [edge.GetStart(), edge.GetEnd()])
        self.assertEqual(len(seen), len(self.joins))
        polygons = self.pcbnew.SHAPE_POLY_SET()
        self.assertTrue(self.board.GetBoardPolygonOutlines(polygons, False))
        self.assertEqual(polygons.OutlineCount(), 1)


if __name__ == '__main__':
    unittest.main()
