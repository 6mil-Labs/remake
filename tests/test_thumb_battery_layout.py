"""Geometry gates for the long thumb cap and the photo-guided battery bay."""

import importlib.util
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('pcbnew'), 'requires native KiCad')
class ThumbBatteryLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew

        cls.k = pcbnew
        cls.board = pcbnew.LoadBoard(str(ROOT / 'hw/remake.kicad_pcb'))
        cls.parts = {f.GetReference(): f for f in cls.board.GetFootprints()}

    def rectangle(self, footprint, width, height):
        polygon = self.k.SHAPE_POLY_SET()
        polygon.NewOutline()
        centre = footprint.GetPosition()
        angle = math.radians(footprint.GetOrientationDegrees())
        for x, y in [(-width/2, -height/2), (width/2, -height/2),
                     (width/2, height/2), (-width/2, height/2)]:
            polygon.Append(self.k.VECTOR2I(
                centre.x + self.k.FromMM(x*math.cos(angle) + y*math.sin(angle)),
                centre.y + self.k.FromMM(-x*math.sin(angle) + y*math.cos(angle))))
        return polygon

    def test_long_thumb_cap_does_not_overhang_the_existing_pcb_outline(self):
        # Catch rotating the long cap in place without moving its switch up.
        board_outline = self.k.SHAPE_POLY_SET()
        self.assertTrue(self.board.GetBoardPolygonOutlines(board_outline, False))
        cap = self.rectangle(self.parts['SW17'], 26.5, 16.5)
        cap.BooleanSubtract(board_outline)
        self.assertEqual(cap.OutlineCount(), 0, 'Long thumb cap extends past the PCB')

    def test_battery_jack_is_beside_headers_and_controls_are_below_its_lead(self):
        # Catch leaving the jack below the controller, or a switch in the
        # cable/plug space shown by the user's physical 26 mm lead.
        pins = [p for p in self.parts['U1'].Pads() if p.GetDrillSize().x]
        top, bottom = min(p.GetPosition().y for p in pins), max(p.GetPosition().y for p in pins)
        for ref in ['JBAT_L1', 'JBAT_R1']:
            jack = self.parts[ref].GetPosition()
            self.assertGreater(jack.y, top)
            self.assertLess(jack.y, bottom)
            self.assertGreater(jack.x, max(p.GetPosition().x for p in pins))
            self.assertGreater(self.parts['PWR1'].GetPosition().y, jack.y)
        for ref in ['RST_L1', 'RST_R1']:
            self.assertGreater(self.parts[ref].GetPosition().y,
                               self.parts['PWR1'].GetPosition().y)

    def test_header_annular_copper_retains_one_mm_to_choc_socket_lands(self):
        # Unlike keycap/module boxes, these are the actual copper pad shapes
        # on BOTH faces, including the header's plated annular lands.
        headers = [p for p in self.parts['U1'].Pads() if p.GetDrillSize().x]
        for layer in [self.k.F_Cu, self.k.B_Cu]:
            for ref in ['SW5', 'SW10', 'SW15']:
                for pad in self.parts[ref].Pads():
                    if not pad.GetNumber() or not pad.IsOnLayer(layer):
                        continue
                    for header in headers:
                        with self.subTest(layer=layer, switch=ref, pad=pad.GetNumber(),
                                          header=header.GetNumber()):
                            self.assertFalse(header.GetEffectiveShape(layer).Collide(
                                pad.GetEffectiveShape(layer), self.k.FromMM(1)),
                                'Header copper too close to Choc socket land')

    def test_lower_corner_mount_clears_the_rotated_switch_housing(self):
        # H2 moves down out of the switch body; screw-head/cap-travel
        # clearance is a separate physical stack check, not implied here.
        mount, switch = self.parts['H2'], self.parts['SW17']
        self.assertGreater(mount.GetPosition().y,
                           switch.GetPosition().y + self.k.FromMM(10))
        body = self.rectangle(switch, 14, 14)
        hole = next(p for p in mount.Pads() if p.GetDrillSize().x)
        self.assertFalse(body.Collide(hole.GetEffectiveHoleShape(), self.k.FromMM(0.5)))
