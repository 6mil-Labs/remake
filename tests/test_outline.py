"""Geometry contracts for REMAKE's filleted, 3.5 mm PCB perimeter."""

from collections import defaultdict
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
        cls.parts = {f.GetReference(): f for f in cls.board.GetFootprints()}
        cls.edges = [s for s in cls.board.GetDrawings() if s.GetLayer() == pcbnew.Edge_Cuts]
        cls.joins = defaultdict(list)
        for edge in cls.edges:
            for p in [edge.GetStart(), edge.GetEnd()]:
                cls.joins[(p.x, p.y)].append(edge)

    def test_outline_uses_straight_runs_and_circular_fillets(self):
        self.assertTrue(self.edges)
        self.assertEqual({edge.GetShapeStr() for edge in self.edges}, {'Line', 'Arc'})
        for edge in self.edges:
            if edge.GetShapeStr() == 'Arc':
                self.assertGreater(edge.GetRadius(), 0, 'Degenerate corner fillet')

    def test_fillet_joins_are_connected_and_tangent_to_the_straight_runs(self):
        for point, adjacent in self.joins.items():
            with self.subTest(join=point):
                self.assertEqual(len(adjacent), 2)
                self.assertEqual({edge.GetShapeStr() for edge in adjacent}, {'Line', 'Arc'})
                arc = next(edge for edge in adjacent if edge.GetShapeStr() == 'Arc')
                line = next(edge for edge in adjacent if edge.GetShapeStr() == 'Line')
                centre = arc.GetCenter()
                radius = (self.pcbnew.ToMM(point[0] - centre.x),
                          self.pcbnew.ToMM(point[1] - centre.y))
                a, b = line.GetStart(), line.GetEnd()
                direction = (self.pcbnew.ToMM(b.x - a.x), self.pcbnew.ToMM(b.y - a.y))
                length = math.hypot(*direction)
                self.assertGreater(length, 0, 'Degenerate straight run')
                projection = abs(sum(x*y for x, y in zip(radius, direction)))/length
                # Three-point interactive fillets round their coordinates and
                # derived centres. Permit 1 um of CAD error, not a visible kink.
                self.assertLessEqual(projection, 0.001, 'Non-tangent line/fillet join')

    def matrix_edges(self):
        # The controller bay starts at this existing boundary. The lower
        # diagonal into SW18 and the rotated thumb sides are the other exception.
        controller_start = self.pcbnew.FromMM(175.958621)
        finger_bottom = self.parts['SW11'].GetPosition().y + self.pcbnew.FromMM(10.5)
        return [edge for edge in self.edges
                if edge.GetShapeStr() == 'Line'
                and max(edge.GetStart().x, edge.GetEnd().x) <= controller_start
                and max(edge.GetStart().y, edge.GetEnd().y) <= finger_bottom]

    def test_finger_matrix_edges_are_exactly_horizontal_or_vertical(self):
        self.assertTrue(self.matrix_edges())
        for edge in self.matrix_edges():
            a, b = edge.GetStart(), edge.GetEnd()
            self.assertTrue(a.x == b.x or a.y == b.y,
                            f'Non-orthogonal matrix edge: {a} to {b}')

    @staticmethod
    def point_to_segment_distance(point, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        fraction = ((point[0] - start[0])*dx + (point[1] - start[1])*dy)/(dx*dx + dy*dy)
        fraction = max(0, min(1, fraction))
        return math.hypot(point[0] - start[0] - fraction*dx,
                          point[1] - start[1] - fraction*dy)

    def switch_body(self, ref):
        # Nominal Choc-v1 14 x 14 mm housing, not a keycap or socket courtyard.
        footprint = self.parts[ref]
        centre = footprint.GetPosition()
        cx, cy = self.pcbnew.ToMM(centre.x), self.pcbnew.ToMM(centre.y)
        angle = math.radians(footprint.GetOrientationDegrees())
        return [(cx + x*math.cos(angle) + y*math.sin(angle),
                 cy - x*math.sin(angle) + y*math.cos(angle))
                for x, y in [(-7,-7), (7,-7), (7,7), (-7,7)]]

    def edge_to_body_distance(self, edge, body):
        a, b = edge.GetStart(), edge.GetEnd()
        a = self.pcbnew.ToMM(a.x), self.pcbnew.ToMM(a.y)
        b = self.pcbnew.ToMM(b.x), self.pcbnew.ToMM(b.y)
        return self.segment_to_body_distance(a, b, body)

    def segment_to_body_distance(self, a, b, body):
        return min(min(self.point_to_segment_distance(point, start, end)
                       for point, start, end in [(a,c,d), (b,c,d), (c,a,b), (d,a,b)])
                   for c, d in zip(body, body[1:] + body[:1]))

    def test_each_finger_matrix_edge_has_at_least_three_point_five_mm_to_switch_bodies(self):
        bodies = [self.switch_body(f'SW{i}') for i in range(1,19)]
        for edge in self.matrix_edges():
            gap = min(self.edge_to_body_distance(edge, body) for body in bodies)
            # A short stagger step above a housing corner may be farther away;
            # no finite segment may be closer than the nominal body margin.
            self.assertGreaterEqual(gap, 3.49999,
                                    f'Wrong matrix margin at {edge.GetStart()}')

    def test_switch_bodies_stay_inside_with_three_point_five_mm_clearance(self):
        outline = self.pcbnew.SHAPE_POLY_SET()
        self.assertTrue(self.board.GetBoardPolygonOutlines(outline, False))
        contour = outline.Outline(0)
        boundary = [(self.pcbnew.ToMM(contour.CPoint(i).x),
                     self.pcbnew.ToMM(contour.CPoint(i).y))
                    for i in range(contour.PointCount())]
        for i in range(1,19):
            ref = f'SW{i}'
            body = self.switch_body(ref)
            polygon = self.pcbnew.SHAPE_POLY_SET()
            polygon.NewOutline()
            for x, y in body:
                polygon.Append(self.pcbnew.FromMM(x), self.pcbnew.FromMM(y))
            polygon.BooleanSubtract(outline)
            self.assertEqual(polygon.OutlineCount(), 0, f'{ref} body outside PCB')
            gap = min(self.segment_to_body_distance(a, b, body)
                      for a, b in zip(boundary, boundary[1:] + boundary[:1]))
            self.assertGreaterEqual(gap, 3.49999, f'{ref} body margin too narrow')
            if i in [1,2,3,4,5,6,11,16,18]:
                self.assertAlmostEqual(gap, 3.5, delta=0.00001,
                                       msg=f'{ref} outer margin is not 3.5 mm')

    def test_hotswap_and_diode_copper_pads_keep_half_mm_to_edge_on_both_faces(self):
        outline = self.pcbnew.SHAPE_POLY_SET()
        self.assertTrue(self.board.GetBoardPolygonOutlines(outline, False))
        for ref, footprint in self.parts.items():
            if not (ref.startswith('SW') or (ref.startswith('D') and ref[1:].isdigit())):
                continue
            for layer in [self.pcbnew.F_Cu, self.pcbnew.B_Cu]:
                for pad in footprint.Pads():
                    if not pad.GetNumber() or not pad.IsOnLayer(layer):
                        continue
                    with self.subTest(ref=ref, pad=pad.GetNumber(), layer=layer):
                        envelope = self.pcbnew.SHAPE_POLY_SET()
                        pad.TransformShapeToPolygon(
                            envelope, layer, self.pcbnew.FromMM(0.5),
                            self.pcbnew.FromMM(0.0001), self.pcbnew.ERROR_OUTSIDE)
                        envelope.BooleanSubtract(outline)
                        self.assertEqual(envelope.OutlineCount(), 0,
                                         'Pad or its required edge clearance extends outside PCB')

    def outline_boundary_shape(self, edge):
        if edge.GetShapeStr() == 'Line':
            return self.pcbnew.SHAPE_SEGMENT(edge.GetStart(), edge.GetEnd())
        self.assertEqual(edge.GetShapeStr(), 'Arc')
        # PCB_SHAPE is the native factory for a SHAPE_ARC in the SWIG API.
        # Do not add this temporary shape to the board. Drawing stroke width
        # is not part of the physical board boundary used for clearance.
        curve = self.pcbnew.PCB_SHAPE(self.board, self.pcbnew.SHAPE_T_ARC)
        curve.SetArcGeometry(edge.GetStart(), edge.GetArcMid(), edge.GetEnd())
        curve.SetLayer(self.pcbnew.Edge_Cuts)
        curve.SetWidth(0)
        return curve.GetEffectiveShape()

    def test_saved_ground_fills_keep_half_mm_to_the_updated_outline(self):
        # Check the saved polygons, not DRC's in-memory refilled version. An
        # outline edit must not leave stale copper overlapping its new edges.
        for zone in self.board.Zones():
            if zone.GetIsRuleArea() or zone.IsTeardropArea():
                continue
            for layer in [self.pcbnew.F_Cu, self.pcbnew.B_Cu]:
                if not zone.IsOnLayer(layer):
                    continue
                filled = zone.GetFilledPolysList(layer)
                for edge in self.edges:
                    with self.subTest(layer=layer, edge=edge.GetStart()):
                        shape = self.outline_boundary_shape(edge)
                        self.assertFalse(filled.Collide(shape, self.pcbnew.FromMM(0.49999)),
                                         'Saved copper fill is too close to the board edge')

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
