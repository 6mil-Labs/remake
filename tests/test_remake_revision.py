"""Acceptance contracts for the 36-key placement/branding revision."""

import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('pcbnew'), 'requires KiCad pcbnew')
class RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew

        cls.pcbnew = pcbnew
        cls.board = pcbnew.LoadBoard(str(ROOT / 'hw/remake.kicad_pcb'))
        cls.parts = {f.GetReference(): f for f in cls.board.GetFootprints()}

    def test_third_thumb_has_a_real_switch_diode_and_unused_matrix_slot(self):
        self.assertEqual(len([r for r in self.parts if re.fullmatch(r'SW\d+', r)]), 18)
        self.assertEqual(len([r for r in self.parts if re.fullmatch(r'D\d+', r)]), 18)
        for ref, expected in [('SW18', {'1': 'COL2', '2': 'KEY18'}),
                              ('D18', {'1': 'ROW3', '2': 'KEY18'})]:
            for pad in self.parts[ref].Pads():
                if pad.GetNumber():
                    self.assertEqual(pad.GetNetname(), expected[pad.GetNumber()])

    def test_thumb_ordering_and_fan_angles_are_retained(self):
        # Absolute coordinates are editable layout data, not the old placement
        # generator's permanent API. Geometry clearance is checked separately.
        for ref,angle in [('SW18',0),('SW16',-15),('SW17',-30)]:
            f=self.parts[ref]
            self.assertAlmostEqual(f.GetOrientationDegrees(), angle)
        self.assertLess(self.parts['SW18'].GetPosition().x, self.parts['SW16'].GetPosition().x)
        self.assertLess(self.parts['SW16'].GetPosition().x,self.parts['SW17'].GetPosition().x)

    def test_thumb_switch_body_edge_gaps_are_even(self):
        # Catch SW18 drifting away from SW16. Compare the nearest edges of
        # the nominal 14 x 14 mm switch bodies, not centre-to-centre pitch:
        # the fanned switches have different orientations.
        def body(index):
            part = self.parts[f'SW{index}']
            position = part.GetPosition()
            cx, cy = self.pcbnew.ToMM(position.x), self.pcbnew.ToMM(position.y)
            angle = math.radians(part.GetOrientationDegrees())
            return [(cx + x * math.cos(angle) + y * math.sin(angle),
                     cy - x * math.sin(angle) + y * math.cos(angle))
                    for x, y in [(-7, -7), (7, -7), (7, 7), (-7, 7)]]

        def point_segment_distance(point, start, end):
            dx, dy = end[0] - start[0], end[1] - start[1]
            projection = ((point[0] - start[0]) * dx
                          + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
            fraction = max(0, min(1, projection))
            return math.hypot(point[0] - start[0] - fraction * dx,
                              point[1] - start[1] - fraction * dy)

        def gap(first, second):
            a, b = body(first), body(second)
            # Bodies are disjoint (also enforced by the larger keycap
            # envelope test). Their closest points include a vertex.
            return min(point_segment_distance(point, polygon[i], polygon[(i + 1) % 4])
                       for vertices, polygon in [(a, b), (b, a)]
                       for point in vertices for i in range(4))

        gap_18_16, gap_16_17 = gap(18, 16), gap(16, 17)
        self.assertGreater(gap_18_16, 0)
        self.assertGreater(gap_16_17, 0)
        self.assertAlmostEqual(gap_18_16, gap_16_17, delta=0.01,
                               msg='Thumb switch-body edge gaps must match within 0.01 mm')

    def test_selected_keycap_envelopes_do_not_overlap_the_thumb_cluster(self):
        # User-selected17.5x16.5mm outside envelopes, centred on the stems.
        # This is a nominal plan-view check, not a tolerance/travel validation.
        def cap(index):
            part=self.parts[f'SW{index}'];p=part.GetPosition()
            cx,cy=self.pcbnew.ToMM(p.x),self.pcbnew.ToMM(p.y)
            angle=math.radians(part.GetOrientationDegrees())
            return [(cx+x*math.cos(angle)+y*math.sin(angle),
                     cy-x*math.sin(angle)+y*math.cos(angle))
                    for x,y in [(-8.75,-8.25),(8.75,-8.25),(8.75,8.25),(-8.75,8.25)]]

        def overlap(a,b):
            for shape in [a,b]:
                for i in range(4):
                    p,q=shape[i],shape[(i+1)%4]
                    axis=(p[1]-q[1],q[0]-p[0])
                    aa=[x*axis[0]+y*axis[1] for x,y in a]
                    bb=[x*axis[0]+y*axis[1] for x,y in b]
                    if max(aa)<=min(bb)+1e-8 or max(bb)<=min(aa)+1e-8:
                        return False
            return True

        for thumb in [16,17,18]:
            for other in range(1,19):
                if thumb!=other:
                    self.assertFalse(overlap(cap(thumb),cap(other)),(thumb,other))

    def test_five_mounting_holes_have_plated_holes_and_grounded_pads_on_both_faces(self):
        mounts = {ref: part for ref,part in self.parts.items()
                  if re.fullmatch(r'H\d+',ref)
                  or str(part.GetFPID().GetLibItemName()).startswith('MountingHole')}
        self.assertEqual(set(mounts), {f'H{i}' for i in range(1,6)})
        for ref,part in mounts.items():
            with self.subTest(reference=ref):
                self.assertTrue(str(part.GetFPID().GetLibItemName()).startswith('MountingHole'))
                pads = list(part.Pads())
                self.assertTrue(pads)
                self.assertTrue(all(p.GetNumber() == '1' for p in pads))
                self.assertTrue(all(p.GetNetname() == 'GND' for p in pads))
                holes = [p for p in pads if p.GetAttribute() == self.pcbnew.PAD_ATTRIB_PTH]
                self.assertEqual(len(holes), 1)
                self.assertGreater(holes[0].GetDrillSize().x, 0)
                self.assertGreater(holes[0].GetDrillSize().y, 0)
                for layer in [self.pcbnew.F_Cu, self.pcbnew.B_Cu]:
                    self.assertTrue(any(p.IsOnLayer(layer) for p in pads))

    def test_battery_alternatives_preserve_polarity_and_opposite_face_alignment(self):
        left,right=self.parts['JBAT_L1'],self.parts['JBAT_R1']
        self.assertEqual(left.GetPosition(),right.GetPosition())
        self.assertAlmostEqual((left.GetOrientationDegrees()-right.GetOrientationDegrees())%360,180)
        for part,layer in [(left,self.pcbnew.F_Cu),(right,self.pcbnew.B_Cu)]:
            for pad in part.Pads():
                if pad.GetNumber() in ['1','2']:
                    self.assertTrue(pad.IsOnLayer(layer))
                    self.assertEqual(pad.GetNetname(),{'1':'GND','2':'BAT+'}[pad.GetNumber()])

    @unittest.skipUnless(shutil.which('kicad-cli'), 'requires KiCad CLI')
    def test_schematic_exports_the_third_key_and_matches_every_pcb_pin_net(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name in ['remake.kicad_sch','remake.kicad_pro']:
                shutil.copy2(ROOT / 'hw' / name,path / name)
            result = subprocess.run(
                ['kicad-cli','sch','export','netlist','--format','kicadxml',
                 '--output',str(path / 'netlist.xml'),str(path / 'remake.kicad_sch')],
                capture_output=True,text=True,check=False,
            )
            self.assertEqual(result.returncode,0,result.stderr)
            xml = ET.parse(path / 'netlist.xml').getroot()
            mounts = {c.attrib['ref'] for c in xml.findall('./components/comp')
                      if re.fullmatch(r'H\d+',c.attrib['ref'])}
            self.assertEqual(mounts, {f'H{i}' for i in range(1,6)})
            nets = {n.attrib['name']:n for n in xml.findall('./nets/net')}
            self.assertEqual({(n.attrib['ref'],n.attrib['pin']) for n in nets['GND']
                              if n.attrib['ref'] in mounts},
                             {(ref,'1') for ref in mounts})
            self.assertIn('KEY18',nets)
            self.assertEqual({(n.attrib['ref'],n.attrib['pin']) for n in nets['KEY18']},
                             {('SW18','2'),('D18','2')})
            for name,net in nets.items():
                for node in net.findall('node'):
                    part = self.parts[node.attrib['ref']]
                    pads = [p for p in part.Pads() if p.GetNumber()==node.attrib['pin']]
                    self.assertTrue(pads,(node.attrib,name))
                    if 'no_connect' in node.attrib.get('pintype','').split('+'):
                        # KiCad can give alternative footprint pads separate
                        # no-connect nets. Only numeric disambiguation is allowed;
                        # assigning an unused pad to a signal net must still fail.
                        pattern = re.escape(name)+r'(?:_\d+)?'
                        # PCB net names escape '/' in pin names as '{slash}'.
                        self.assertTrue(all(re.fullmatch(pattern,p.GetNetname().replace('{slash}','/'))
                                            for p in pads),
                                        (node.attrib,name,[p.GetNetname() for p in pads]))
                    else:
                        self.assertTrue(all(p.GetNetname()==name for p in pads),(node.attrib,name))

    @unittest.skipUnless(shutil.which('kicad-cli'), 'requires KiCad CLI')
    def test_placement_has_no_new_part_collisions_or_clipped_branding(self):
        # Inspect placement in isolation, without tracks, vias OR copper pours.
        # Leaving pours behind after deleting their routing creates artificial
        # thermal/connectivity failures. Keep rule areas (antenna clearance).
        # test_routing checks the real routed/refilled board independently.
        # Only the explicitly provisional thumb/outline intersections are allowed
        # here; the real release gate still rejects every DRC finding.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            shutil.copytree(ROOT / 'hw',path / 'hw',
                            ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','fp-info-cache'))
            source = path / 'hw/remake.kicad_pcb'
            placement = re.sub(r'^\t\((?:segment|via)\n.*?^\t\)\n','',
                               source.read_text(),flags=re.M|re.S)
            placement = re.sub(r'^\t\(zone\n.*?^\t\)\n',
                               lambda m: m[0] if '(keepout' in m[0] else '',
                               placement,flags=re.M|re.S)
            source.write_text(placement)
            result = subprocess.run(
                ['kicad-cli','pcb','drc','--format','json','--schematic-parity',
                 '--output',str(path / 'drc.json'),str(source)],
                capture_output=True,text=True,check=False,
            )
            self.assertEqual(result.returncode,0,result.stderr)
            report = json.loads((path / 'drc.json').read_text())
            self.assertFalse(report['schematic_parity'])
            unexpected = []
            for finding in report['violations']:
                permitted = finding['type'] in {'copper_edge_clearance','silk_edge_clearance'}
                permitted = permitted and any(re.search(r'\bSW(?:17|18)\b',item['description'])
                                               for item in finding['items'])
                if not permitted:
                    unexpected.append((finding['type'],finding['description']))
            self.assertFalse(unexpected,unexpected)

    def test_reversible_switch_library_and_matrix_identities_are_retained(self):
        for ref, f in self.parts.items():
            if not re.fullmatch(r'SW\d+', ref):
                continue
            self.assertEqual(str(f.GetFPID().GetLibNickname()), 'remake-footprints')
            self.assertEqual(str(f.GetFPID().GetLibItemName()), 'SW_Hotswap_Kailh_Choc_V1_reversible')
            i = int(ref[2:])
            for p in f.Pads():
                if p.GetNumber() == '2':
                    self.assertEqual(p.GetNetname(), f'KEY{i:02d}')
        for i in range(1,16):
            f = self.parts[f'SW{i}']
            self.assertEqual(f.GetOrientationDegrees(),0)

    def test_both_faces_have_revision_copyright_and_vector_logo_without_old_title(self):
        texts = [t for t in self.board.GetDrawings() if isinstance(t, self.pcbnew.PCB_TEXT)]
        self.assertFalse(any('/ REV 17' in t.GetText() for t in texts))
        for layer in [self.pcbnew.F_SilkS, self.pcbnew.B_SilkS]:
            actual = {t.GetText(): t for t in texts if t.GetLayer() == layer}
            for value in ['REV ${REVISION}', '(c) 2026 Felipe Balbi']:
                self.assertIn(value, actual)
                self.assertGreaterEqual(self.pcbnew.ToMM(actual[value].GetTextHeight()), 1.2)
                self.assertGreaterEqual(self.pcbnew.ToMM(actual[value].GetTextThickness()), 0.2)
        logo = self.parts.get('LOGO1')
        self.assertIsNotNone(logo)
        self.assertEqual(str(logo.GetFPID().GetLibNickname()), 'remake-artwork')
        for layer in [self.pcbnew.F_SilkS, self.pcbnew.B_SilkS]:
            self.assertTrue(any(g.GetLayer() == layer for g in logo.GraphicalItems()))

    def test_revision_and_author_metadata_are_shared_by_pcb_and_schematic(self):
        project = json.loads((ROOT / 'hw/remake.kicad_pro').read_text())
        self.assertEqual(project['text_variables'].get('REVISION'), '0.2-RC3')
        title = self.board.GetTitleBlock()
        self.assertEqual(title.GetTitle(), 'REMAKE')
        self.assertEqual(title.GetRevision(), '${REVISION}')
        self.assertIn('Felipe Balbi', title.GetComment(0))
        self.assertIn('(c) 2026 Felipe Balbi', title.GetComment(1))
        schematic = (ROOT / 'hw/remake.kicad_sch').read_text()
        self.assertRegex(schematic, r'\(title_block\s+\(title "REMAKE"\)')
        self.assertIn('(rev "${REVISION}")', schematic)
        self.assertIn('(comment 1 "Author: Felipe Balbi")', schematic)
        self.assertIn('(comment 2 "(c) 2026 Felipe Balbi")', schematic)


if __name__ == '__main__':
    unittest.main()
