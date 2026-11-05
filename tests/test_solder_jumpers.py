"""Native/export contracts for dual-use 0402 resistor and solder-bridge links."""

import importlib.util
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def mask_regions(text):
    """Read component-tagged linear regions from native KiCad mask exports.

    This deliberately is not a general Gerber renderer: unexpected units,
    polarity or curved regions must fail rather than be silently misread.
    Coordinates are converted to PCB space (Gerber's Y axis is inverted).
    """
    if '%FSLAX46Y46*%' not in text or '%MOMM*%' not in text:
        raise AssertionError('Expected absolute 4.6 mm Gerber coordinates')
    if '%LPD*%' not in text or '%LPC*%' in text:
        raise AssertionError('Expected dark mask-opening primitives only')
    regions = {}
    blocks = re.finditer(r'%TO\.C,([^*]+)\*%(.*?)(?=%TO\.C,|%TD\*%|\Z)',
                         text, re.S)
    for block in blocks:
        reference, body = block.groups()
        if not reference.startswith(('JPL_', 'JPR_')):
            continue
        for region in re.findall(r'G36\*(.*?)G37\*', body, re.S):
            if re.search(r'G0?[23](?:\*|X|Y)', region):
                raise AssertionError('Expected linear jumper mask regions')
            points = [(int(x) / 1e6, -int(y) / 1e6)
                      for x, y in re.findall(r'X(-?\d+)Y(-?\d+)D0[12]\*', region)]
            if len(points) < 4 or points[0] != points[-1]:
                raise AssertionError('Expected a closed jumper mask region')
            regions.setdefault(reference, []).append(points)
    return regions


def contains(polygon, point):
    """Point-in-polygon, including edges shared with adjacent pad openings."""
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:]):
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if (abs(cross) < 1e-8
                and min(ax, bx) - 1e-8 <= x <= max(ax, bx) + 1e-8
                and min(ay, by) - 1e-8 <= y <= max(ay, by) + 1e-8):
            return True
        if (ay > y) != (by > y):
            if x < ax + (y - ay) * (bx - ax) / (by - ay):
                inside = not inside
    return inside


def point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if not length_squared:
        return math.dist(point, start)
    projection = ((point[0] - start[0]) * dx
                  + (point[1] - start[1]) * dy) / length_squared
    fraction = max(0, min(1, projection))
    return math.hypot(point[0] - start[0] - fraction * dx,
                      point[1] - start[1] - fraction * dy)


@unittest.skipUnless(importlib.util.find_spec('pcbnew') and shutil.which('kicad-cli'),
                     'requires native KiCad tools')
class SolderJumperGerberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew

        cls.k = pcbnew
        board_path = ROOT / 'hw/remake.kicad_pcb'
        cls.board = pcbnew.LoadBoard(str(board_path))
        cls.jumpers = {f.GetReference(): f for f in cls.board.GetFootprints()
                       if f.GetReference().startswith(('JPL_', 'JPR_'))}
        with tempfile.TemporaryDirectory(prefix='remake-jumper-gerbers-') as tmp:
            subprocess.run([
                'kicad-cli', 'pcb', 'export', 'gerbers',
                '--layers', 'F.Mask,B.Mask,F.Paste,B.Paste',
                '--output', tmp, str(board_path),
            ], check=True, capture_output=True, text=True)
            cls.gerbers = {layer: (Path(tmp) / f'remake-{layer}.{extension}').read_text()
                           for layer, extension in [('F_Mask', 'gts'), ('B_Mask', 'gbs'),
                                                    ('F_Paste', 'gtp'), ('B_Paste', 'gbp')]}
            netlist = Path(tmp) / 'netlist.xml'
            subprocess.run([
                'kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                '--output', str(netlist), str(ROOT / 'hw/remake.kicad_sch'),
            ], check=True, capture_output=True, text=True)
            cls.components = {c.attrib['ref']: c for c in
                              ET.parse(netlist).getroot().findall('./components/comp')}

    def test_selection_links_are_zero_ohm_resistors_and_dnp_in_the_shared_master(self):
        # Catch fitting both banks by default or losing the resistor/DNP
        # semantics when updating symbols or transferring them to the PCB.
        self.assertEqual(len(self.jumpers), 44)
        for ref, footprint in self.jumpers.items():
            with self.subTest(reference=ref):
                component = self.components[ref]
                self.assertEqual(component.findtext('value'), '0R')
                self.assertEqual(component.find('libsource').attrib['part'], 'R_0402_Link')
                self.assertIn('dnp', {p.attrib['name'] for p in component.findall('property')})
                self.assertEqual(footprint.GetValue(), '0R')
                self.assertTrue(footprint.IsDNP(), ref)
                self.assertEqual(component.findtext('footprint'), footprint.GetFPIDAsString())
                pads = {p.GetNumber(): p for p in footprint.Pads()}
                self.assertEqual(set(pads), {'1', '2'})
                self.assertNotEqual(pads['1'].GetNetCode(), pads['2'].GetNetCode())

    def test_mask_gerbers_open_the_full_gap_on_each_populated_face(self):
        # Catch a missing, wrong-face, unfilled, shifted or undersized opening.
        # Probe the entire 0.30 mm gap across a useful 0.80 mm bridge height,
        # not just the midpoint. This also covers the rotated display jumpers.
        self.assertEqual(len(self.jumpers), 44)
        for bank, layer in [('JPL_', 'B_Mask'), ('JPR_', 'F_Mask')]:
            regions = mask_regions(self.gerbers[layer])
            expected = {ref for ref in self.jumpers if ref.startswith(bank)}
            self.assertEqual(set(regions), expected)
            self.assertEqual(len(expected), 22)
            for ref in sorted(expected):
                with self.subTest(jumper=ref, layer=layer):
                    pads = {p.GetNumber(): p for p in self.jumpers[ref].Pads()}
                    a, b = [pads[number].GetPosition() for number in ['1', '2']]
                    dx, dy = self.k.ToMM(b.x - a.x), self.k.ToMM(b.y - a.y)
                    distance = math.hypot(dx, dy)
                    ux, uy = dx / distance, dy / distance
                    cx, cy = self.k.ToMM((a.x + b.x) / 2), self.k.ToMM((a.y + b.y) / 2)
                    for along in [-0.15, -0.075, 0, 0.075, 0.15]:
                        for across in [-0.4, 0, 0.4]:
                            point = (cx + along * ux - across * uy,
                                     cy + along * uy + across * ux)
                            self.assertTrue(any(contains(polygon, point)
                                                for polygon in regions[ref]),
                                            (ref, layer, point))

    def test_each_link_has_two_separate_0402_paste_apertures_on_its_own_face(self):
        # Catch missing apertures, opposite-face paste, or a continuous paste
        # stripe that could short a link without a resistor. These are raw
        # footprint exports, not a population-selected factory stencil.
        for bank, layer in [('JPL_', 'B_Paste'), ('JPR_', 'F_Paste')]:
            regions = mask_regions(self.gerbers[layer])
            expected = {ref for ref in self.jumpers if ref.startswith(bank)}
            self.assertEqual(set(regions), expected)
            for ref in sorted(expected):
                with self.subTest(jumper=ref, layer=layer):
                    polygons = regions[ref]
                    self.assertEqual(len(polygons), 2)
                    footprint = self.jumpers[ref]
                    pads = {p.GetNumber(): p for p in footprint.Pads()}
                    a, b = [pads[number].GetPosition() for number in ['1', '2']]
                    dx, dy = self.k.ToMM(b.x - a.x), self.k.ToMM(b.y - a.y)
                    distance = math.hypot(dx, dy)
                    ux, uy = dx / distance, dy / distance
                    cx, cy = self.k.ToMM((a.x + b.x) / 2), self.k.ToMM((a.y + b.y) / 2)
                    self.assertFalse(any(contains(polygon, (cx, cy)) for polygon in polygons))
                    # Hand-derived KiCad nominal 0402 apertures: 0.54 x 0.64 mm,
                    # centred at +/-0.51 mm; 0.48 mm between paste deposits.
                    occupied = set()
                    for along in [-0.51, 0.51]:
                        for x in [-0.27, 0, 0.27]:
                            for y in [-0.32, 0, 0.32]:
                                point = (cx + (along + x) * ux - y * uy,
                                         cy + (along + x) * uy + y * ux)
                                hits = [i for i, polygon in enumerate(polygons)
                                        if contains(polygon, point)]
                                self.assertEqual(len(hits), 1, (ref, point))
                                occupied.update(hits)
                    self.assertEqual(occupied, {0, 1})
                    for polygon in polygons:
                        area = abs(sum(ax * by - bx * ay
                                       for (ax, ay), (bx, by)
                                       in zip(polygon, polygon[1:]))) / 2
                        self.assertAlmostEqual(area, 0.3456, places=6)

    def test_link_paste_apertures_do_not_overlap_open_via_drills(self):
        # Copper beneath a stencil opening is not sufficient support if an
        # unfilled via barrel is open there: solder can wick out of the joint.
        vias = [item for item in self.board.GetTracks()
                if isinstance(item, self.k.PCB_VIA)]
        for layer, copper in [('F_Paste', self.k.F_Cu), ('B_Paste', self.k.B_Cu)]:
            for ref, polygons in mask_regions(self.gerbers[layer]).items():
                for via in vias:
                    if not via.IsOnLayer(copper):
                        continue
                    position = via.GetPosition()
                    centre = self.k.ToMM(position.x), self.k.ToMM(position.y)
                    radius = self.k.ToMM(via.GetDrillValue()) / 2
                    for polygon in polygons:
                        distance = min(point_segment_distance(centre, a, b)
                                       for a, b in zip(polygon, polygon[1:]))
                        with self.subTest(link=ref, layer=layer,
                                          via=via.m_Uuid.AsString()):
                            self.assertFalse(contains(polygon, centre), centre)
                            self.assertGreater(distance, radius + 1e-6,
                                               'Paste aperture overlaps an open via drill')

    def test_visible_link_values_are_separated_from_neighboring_references(self):
        # Catch the newly visible 0R values occupying the next row's reference
        # position. Compare field geometry, not a particular text formatting.
        schematic = (ROOT / 'hw/remake.kicad_sch').read_text()
        references, values = {}, {}
        for symbol in re.findall(r'^\t\(symbol\n.*?^\t\)\n', schematic, re.M | re.S):
            reference = re.search(r'\(property "Reference" "([^"]+)"', symbol)
            if not reference or reference[1] not in self.jumpers:
                continue
            for field, output in [('Reference', references), ('Value', values)]:
                position = re.search(r'\(property "' + field + r'" "[^"]*"\s+'
                                     r'\(at ([-\d.]+) ([-\d.]+) [^)]*\)', symbol)
                self.assertIsNotNone(position, (reference[1], field))
                output[reference[1]] = tuple(map(float, position.groups()))
        self.assertEqual(len(values), 44)
        for owner, value in values.items():
            for other, reference in references.items():
                if owner != other:
                    with self.subTest(value=owner, reference=other):
                        self.assertGreater(math.dist(value, reference), 1.0,
                                           'Value intrudes on a neighboring reference')


if __name__ == '__main__':
    unittest.main()
