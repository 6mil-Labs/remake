"""Native copper/connectivity gates for the reversible REMAKE PCB."""

import importlib.util
import fnmatch
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('pcbnew') and shutil.which('kicad-cli'),
                     'requires native KiCad tools')
class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew

        cls.k = pcbnew
        cls.board = pcbnew.LoadBoard(str(ROOT / 'hw/remake.kicad_pcb'))
        cls.project = json.loads((ROOT / 'hw/remake.kicad_pro').read_text())
        # Check the real routed board, not the placement-only stripped copy.
        with tempfile.TemporaryDirectory(prefix='remake-routing-') as tmp:
            report = Path(tmp) / 'drc.json'
            subprocess.run([
                'kicad-cli', 'pcb', 'drc', '--format', 'json', '--refill-zones',
                '--schematic-parity', '--output', str(report),
                str(ROOT / 'hw/remake.kicad_pcb'),
            ], check=True, capture_output=True, text=True)
            cls.drc = json.loads(report.read_text())

    def test_all_bare_board_connections_are_routed_without_solder_bridges(self):
        self.assertEqual(self.drc['unconnected_items'], [])
        self.assertEqual(self.drc['schematic_parity'], [])

    def test_native_routed_copper_has_no_electrical_or_geometry_errors(self):
        # Hole-to-hole, isolated copper and net conflicts can be warnings in
        # KiCad. Severity must not turn an electrical finding into acceptance.
        findings = [v for v in self.drc['violations']
                    if not (v['type'] == 'silk_over_copper' and v['severity'] == 'warning')]
        self.assertEqual(findings, [])
        self.assertEqual({v['key'] for v in self.drc['ignored_checks']},
                         {'track_not_centered_on_via', 'tuning_profile_track_geometries'})

    def test_project_retains_the_requested_routing_contract_without_waivers(self):
        design = self.project['board']['design_settings']
        self.assertEqual(design['drc_exclusions'], [])
        for name, expected in {'min_clearance': .2, 'min_copper_edge_clearance': .5,
                               'min_hole_clearance': .25, 'min_hole_to_hole': .25,
                               'min_track_width': .2, 'min_via_diameter': .5,
                               'min_through_hole_diameter': .3,
                               'min_via_annular_width': .1}.items():
            self.assertGreaterEqual(design['rules'][name], expected, name)
        for name in ['clearance', 'copper_edge_clearance', 'unconnected_items',
                     'shorting_items', 'items_not_allowed', 'annular_width',
                     'drill_out_of_range', 'via_diameter', 'track_width',
                     'solder_mask_bridge', 'starved_thermal', 'invalid_outline']:
            self.assertEqual(design['rule_severities'].get(name, 'error'), 'error', name)
        for name in ['hole_to_hole', 'isolated_copper', 'net_conflict',
                     'track_dangling', 'via_dangling']:
            self.assertIn(design['rule_severities'][name], ['warning', 'error'], name)
        classes = {c['name']: c for c in self.project['net_settings']['classes']}
        self.assertEqual(set(classes), {'Default', 'Power', 'Row', 'Column'})
        for name, width in [('Default', .3048), ('Power', .6096),
                            ('Row', .3048), ('Column', .3048)]:
            self.assertEqual(classes[name]['track_width'], width, name)
            self.assertEqual(classes[name]['clearance'], .2032, name)
            self.assertEqual(classes[name]['via_diameter'], .6, name)
            self.assertEqual(classes[name]['via_drill'], .3, name)
        self.assertEqual(self.project['net_settings']['netclass_patterns'], [
            {'netclass': 'Power', 'pattern': '*3V3*'},
            {'netclass': 'Power', 'pattern': 'BAT*'},
            {'netclass': 'Column', 'pattern': 'COL*'},
            {'netclass': 'Row', 'pattern': 'ROW*'},
            {'netclass': 'Default', 'pattern': '*'},
        ])

    def test_each_selected_bank_gives_the_same_controller_and_display_mapping(self):
        # Logical module contact -> board signal, independently from the
        # routed geometry. Right population reverses physical contact order.
        controller = {1: 'NVCS', 3: 'GND', 4: 'GND', 5: 'MOSI', 6: 'SCK',
                      9: 'ROW0', 10: 'ROW1', 11: 'ROW2', 12: 'ROW3',
                      13: 'COL4', 14: 'COL3', 15: 'COL2', 16: 'COL1', 17: 'COL0',
                      21: '+3V3', 22: 'RESET', 23: 'GND', 24: 'BAT_SW'}
        display = {1: 'MOSI', 2: 'SCK', 4: 'GND', 5: 'NVCS'}
        parts = {f.GetReference(): f for f in self.board.GetFootprints()}
        for bank, layer in [('JPL', self.k.B_Cu), ('JPR', self.k.F_Cu)]:
            for group, mapping, last in [('U', controller, 24), ('D', display, 5)]:
                for logical, signal in mapping.items():
                    physical = logical if bank == 'JPL' else last + 1 - logical
                    ref = f'{bank}_{group}{physical:02d}' if group == 'U' else f'{bank}_{group}{physical}'
                    pads = {p.GetNumber(): p for p in parts[ref].Pads()}
                    contact = f'U_SOCKET_{physical:02d}' if group == 'U' else f'D_SOCKET_{physical}'
                    with self.subTest(jumper=ref):
                        self.assertEqual(pads['1'].GetNetname(), contact)
                        self.assertEqual(pads['2'].GetNetname(), signal)
                        self.assertTrue(all(p.IsOnLayer(layer) for p in pads.values()))
                        self.assertNotEqual(pads['1'].GetNetCode(), pads['2'].GetNetCode())
        supply = next(p for p in parts['Display1'].Pads() if p.GetNumber() == '3')
        self.assertEqual(supply.GetNetname(), '+3V3')

    def test_via_defaults_and_placed_vias_meet_board_manufacturing_minima(self):
        rules = self.project['board']['design_settings']['rules']
        dimensions = [(c['name'], c['via_diameter'], c['via_drill'])
                      for c in self.project['net_settings']['classes']]
        dimensions.extend((v.m_Uuid.AsString(), self.k.ToMM(v.GetWidth(self.k.F_Cu)),
                           self.k.ToMM(v.GetDrillValue()))
                          for v in self.board.GetTracks() if isinstance(v, self.k.PCB_VIA))
        for name, diameter, drill in dimensions:
            with self.subTest(item=name):
                self.assertAlmostEqual(diameter, .6, places=6)
                self.assertAlmostEqual(drill, .3, places=6)
                self.assertGreaterEqual(diameter, rules['min_via_diameter'])
                self.assertGreaterEqual(drill, rules['min_through_hole_diameter'])
                self.assertGreaterEqual((diameter - drill) / 2 + 1e-9,
                                        rules['min_via_annular_width'])

    def test_routing_does_not_neck_down_below_current_netclass_widths(self):
        settings = self.project['net_settings']
        widths = {c['name']: c['track_width'] for c in settings['classes']}
        for track in self.board.GetTracks():
            if isinstance(track, self.k.PCB_VIA):
                continue
            matching = [widths[p['netclass']] for p in settings['netclass_patterns']
                        if fnmatch.fnmatchcase(track.GetNetname(), p['pattern'])]
            required = max(matching, default=widths['Default'])
            self.assertGreaterEqual(self.k.ToMM(track.GetWidth()) + 1e-9, required,
                                    track.GetNetname())

    def test_both_faces_have_filled_ground_with_thermals_and_no_isolated_islands(self):
        # Teardrops are solid pad/via reinforcements, not thermal ground
        # planes. Native DRC still checks their copper and connectivity.
        pours = [z for z in self.board.Zones()
                 if not z.GetIsRuleArea() and not z.IsTeardropArea()]
        for layer in [self.k.F_Cu, self.k.B_Cu]:
            zones = [z for z in pours if z.IsOnLayer(layer) and z.GetNetname() == 'GND']
            self.assertTrue(zones, self.board.GetLayerName(layer))
            for zone in zones:
                self.assertTrue(zone.HasFilledPolysForLayer(layer))
                self.assertGreater(zone.GetFilledArea(), 0)
                self.assertEqual(zone.GetPadConnection(), self.k.ZONE_CONNECTION_THERMAL)
        # Accept any island-removal policy that produces clean copper. Check
        # the refilled result, not the editor setting (e.g. area-based removal).
        self.assertEqual([v for v in self.drc['violations']
                          if v['type'] == 'isolated_copper'], [])
        keepouts = [z for z in self.board.Zones() if z.GetIsRuleArea()]
        self.assertTrue(any(z.IsOnLayer(self.k.F_Cu) and z.IsOnLayer(self.k.B_Cu)
                            and z.GetDoNotAllowTracks() and z.GetDoNotAllowVias()
                            and z.GetDoNotAllowZoneFills() for z in keepouts))


if __name__ == '__main__':
    unittest.main()
