"""Preserve the 18-key matrix's pin-level contract when redrawing it."""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]

# Original matrix assignments, including the three thumb keys.
MATRIX = (
    (1, 0, 0), (2, 0, 1), (3, 0, 2), (4, 0, 3), (5, 0, 4),
    (6, 1, 0), (7, 1, 1), (8, 1, 2), (9, 1, 3), (10, 1, 4),
    (11, 2, 0), (12, 2, 1), (13, 2, 2), (14, 2, 3), (15, 2, 4),
    (16, 3, 3), (17, 3, 4), (18, 3, 2),
)


class PowerSymbolTests(unittest.TestCase):
    def test_ground_and_battery_rails_use_power_symbols_instead_of_global_labels(self):
        schematic = (ROOT / 'hw/remake.kicad_sch').read_text()
        labels = re.findall(r'\(global_label "([^"]+)"', schematic)
        for net in ['GND', 'BAT+', 'BAT_SW']:
            with self.subTest(net=net):
                self.assertNotIn(net, labels)
        symbols = re.findall(r'^\t\(symbol\n.*?^\t\)', schematic, re.M | re.S)
        for library, net in [('power:GND', 'GND'), ('power:+BATT', 'BAT+'),
                             ('power:+VSW', 'BAT_SW')]:
            with self.subTest(symbol=library):
                self.assertTrue(any(f'(lib_id "{library}")' in symbol
                                    and f'(property "Value" "{net}"' in symbol
                                    for symbol in symbols))


@unittest.skipUnless(shutil.which('kicad-cli'), 'requires KiCad CLI')
class MatrixConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        for name in ['remake.kicad_sch', 'remake.kicad_pro']:
            shutil.copy2(ROOT / 'hw' / name, path / name)
        subprocess.run(
            ['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
             '--output', str(path / 'netlist.xml'), str(path / 'remake.kicad_sch')],
            capture_output=True, text=True, check=True,
        )
        xml = ET.parse(path / 'netlist.xml').getroot()
        cls.nets = {
            net.attrib['name']: {
                (node.attrib['ref'], node.attrib['pin'])
                for node in net.findall('node')
            }
            for net in xml.findall('./nets/net')
        }

    def test_each_switch_is_in_series_with_its_own_diode(self):
        for key, row, col in MATRIX:
            with self.subTest(key=key):
                self.assertEqual(self.nets.get(f'KEY{key:02d}'),
                                 {(f'SW{key}', '2'), (f'D{key}', '2')})

    def test_columns_connect_only_switch_inputs_and_both_selection_banks(self):
        for col, left, right in [(0, 17, 8), (1, 16, 9), (2, 15, 10),
                                 (3, 14, 11), (4, 13, 12)]:
            with self.subTest(column=col):
                expected = {(f'SW{key}', '1') for key, row, c in MATRIX if c == col}
                expected.update({(f'JPL_U{left:02d}', '2'), (f'JPR_U{right:02d}', '2')})
                self.assertEqual(self.nets.get(f'COL{col}'), expected)

    def test_rows_connect_only_diode_cathodes_and_both_selection_banks(self):
        for row, left, right in [(0, 9, 16), (1, 10, 15), (2, 11, 14), (3, 12, 13)]:
            with self.subTest(row=row):
                expected = {(f'D{key}', '1') for key, r, col in MATRIX if r == row}
                expected.update({(f'JPL_U{left:02d}', '2'), (f'JPR_U{right:02d}', '2')})
                self.assertEqual(self.nets.get(f'ROW{row}'), expected)

    def test_raw_and_switched_battery_rails_remain_separate(self):
        self.assertEqual(self.nets.get('BAT+'),
                         {('JBAT_L1', '2'), ('JBAT_R1', '2'), ('PWR1', '2')})
        self.assertEqual(self.nets.get('BAT_SW'),
                         {('PWR1', '3'), ('JPL_U24', '2'), ('JPR_U01', '2')})

    def test_schematic_passes_the_required_gated_erc(self):
        # A developer's global library tables must not hide missing project libraries.
        home = Path(self.temp.name) / 'erc-home'
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'))
        result = subprocess.run(
            ['kicad-cli', 'sch', 'erc', '--format', 'json', '--exit-code-violations',
             '--output', str(Path(self.temp.name) / 'erc.json'),
             str(ROOT / 'hw/remake.kicad_sch')],
            capture_output=True, text=True, check=False, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
