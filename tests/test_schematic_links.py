"""Schematic UUID associations used by KiCad's normal PCB update operation.

Electrical parity alone is insufficient: KiCad10's BOARD_NETLIST_UPDATER
matches sheet-path + symbol UUID, not a reference/net-name coincidence.
"""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('pcbnew') and shutil.which('kicad-cli'),
                     'requires KiCad CLI and pcbnew')
class SchematicLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew

        cls.k = pcbnew
        cls.board = pcbnew.LoadBoard(str(ROOT / 'hw/remake.kicad_pcb'))
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.path = Path(cls.temp.name)
        for name in ['remake.kicad_sch','remake.kicad_pro']:
            shutil.copy2(ROOT / 'hw' / name,cls.path / name)
        result = subprocess.run(
            ['kicad-cli','sch','export','netlist','--format','kicadxml',
             '--output',str(cls.path / 'netlist.xml'),str(cls.path / 'remake.kicad_sch')],
            capture_output=True,text=True,check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        xml = ET.parse(cls.path / 'netlist.xml').getroot()
        cls.expected = {}
        cls.symbol_pins = {}
        library_pins = {
            (part.attrib['lib'], part.attrib['part']): {
                pin.attrib['num'] for pin in part.findall('./pins/pin')
            }
            for part in xml.findall('./libparts/libpart')
        }
        for comp in xml.findall('./components/comp'):
            if any(p.attrib['name']=='exclude_from_board' for p in comp.findall('property')):
                continue
            # The exported root sheet path is '/', NOT the schematic's root UUID.
            sheet = comp.find('sheetpath').attrib['tstamps'].rstrip('/')
            cls.expected[comp.attrib['ref']] = {
                sheet+'/'+stamp for stamp in comp.findtext('tstamps').split()
            }
            source = comp.find('libsource')
            cls.symbol_pins[comp.attrib['ref']] = library_pins[
                (source.attrib['lib'], source.attrib['part'])
            ]

    def test_every_numbered_board_pad_has_a_matching_symbol_pin(self):
        for footprint in self.board.GetFootprints():
            if footprint.GetAttributes() & self.k.FP_BOARD_ONLY:
                continue
            ref = footprint.GetReference()
            for pad in footprint.Pads():
                number = pad.GetNumber()
                if number:
                    with self.subTest(reference=ref, pad=number, uuid=pad.m_Uuid.AsString()):
                        self.assertIn(number, self.symbol_pins[ref])

    def test_mechanical_pad_cleanup_is_retained_in_source_footprints(self):
        for ref, name, anchors in [
            ('PWR1', 'SW_Power_MSK12C02_reversible', 8),
            ('JBAT_L1', 'JST_PH_2mm_side_entry', 2),
            ('JBAT_R1', 'JST_PH_2mm_side_entry', 2),
        ]:
            library = self.k.FootprintLoad(str(ROOT / 'hw/lib'), name)
            placed = next(f for f in self.board.GetFootprints() if f.GetReference() == ref)
            for kind, footprint in [('library', library), ('board', placed)]:
                with self.subTest(reference=ref, footprint=kind):
                    self.assertIsNotNone(footprint)
                    pads = list(footprint.Pads())
                    mounting = [p for p in pads if p.GetAttribute() == self.k.PAD_ATTRIB_SMD
                                and not p.GetNumber()]
                    self.assertEqual(len(mounting), anchors)
                    self.assertTrue(all(not p.GetNetname() for p in mounting))
                    self.assertTrue(all(p.GetNumber() in self.symbol_pins[ref]
                                        for p in pads if p.GetNumber()))

    def test_every_symbol_matches_one_existing_footprint_by_uuid_path(self):
        parts = list(self.board.GetFootprints())
        for ref,paths in self.expected.items():
            matches = [f for f in parts if f.GetPath().AsString() in paths
                       and not f.GetAttributes() & self.k.FP_BOARD_ONLY]
            self.assertEqual(len(matches),1,
                             f'{ref}: normal UUID-based update would add or duplicate a footprint; expected {paths}')
            self.assertEqual(matches[0].GetReference(),ref)

    def test_only_pcb_only_items_are_unlinked_and_circuit_paths_are_unique(self):
        seen = set()
        for f in self.board.GetFootprints():
            path = f.GetPath().AsString()
            if f.GetAttributes() & self.k.FP_BOARD_ONLY:
                self.assertFalse(path,f.GetReference())
            else:
                self.assertIn(f.GetReference(),self.expected)
                self.assertIn(path,self.expected[f.GetReference()])
                self.assertNotIn(path,seen,'Two circuit footprints share one symbol association')
                seen.add(path)
        self.assertEqual(len(seen),len(self.expected))

    def test_associations_survive_native_board_save_and_reload(self):
        board = self.k.LoadBoard(str(ROOT / 'hw/remake.kicad_pcb'))
        output = self.path / 'roundtrip.kicad_pcb'
        self.k.SaveBoard(str(output),board)
        reloaded = self.k.LoadBoard(str(output))
        actual = {f.GetReference():f.GetPath().AsString() for f in reloaded.GetFootprints()
                  if not f.GetAttributes() & self.k.FP_BOARD_ONLY}
        self.assertEqual(set(actual),set(self.expected))
        for ref,paths in self.expected.items():
            self.assertIn(actual[ref],paths)


if __name__ == '__main__':
    unittest.main()
