"""Manufacturing-output contracts for hand-bridged selection jumpers."""

import importlib.util
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


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

    def test_hand_solder_jumpers_do_not_receive_stencil_paste(self):
        # Catch accidentally adding F.Paste/B.Paste when editing the footprint.
        for layer in ['F_Paste', 'B_Paste']:
            components = set(re.findall(r'%TO\.C,([^*]+)\*%', self.gerbers[layer]))
            self.assertFalse(components & self.jumpers.keys(), layer)


if __name__ == '__main__':
    unittest.main()
