"""Export real FreeCAD case solids, without assembly models or partial bundles."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
# Native distro installs keep the module outside Python's default search path.
if importlib.util.find_spec('FreeCAD') is None:
    for location in ['/usr/lib/freecad/lib', '/usr/lib/freecad-python3/lib']:
        if Path(location).is_dir():
            sys.path.append(location)


@unittest.skipUnless(importlib.util.find_spec('FreeCAD'), 'requires FreeCAD Python modules')
class CaseExportTests(unittest.TestCase):
    def setUp(self):
        import FreeCAD
        import Part
        self.app, self.part = FreeCAD, Part
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def exporter(self):
        path = ROOT / 'scripts/export-cases.py'
        self.assertTrue(path.is_file(), 'case exporter is not implemented')
        spec = importlib.util.spec_from_file_location('case_exporter', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fixture(self, right=True, multiple_solids=False):
        root = self.folder / 'project'
        (root / 'cad/case').mkdir(parents=True)
        doc = self.app.newDocument('CaseFixture')
        try:
            body = doc.addObject('PartDesign::Body', 'Body')
            tip = body.newObject('PartDesign::Feature', 'Final')
            tip.Shape = self.part.makeBox(10, 8, 3)
            if multiple_solids:
                tip.Shape = self.part.makeCompound([
                    tip.Shape, self.part.makeBox(1, 1, 1, self.app.Vector(20, 0, 0)),
                ])
            body.Tip = tip
            if right:
                mirror = doc.addObject('Part::Mirroring', 'Right')
                mirror.Source = body
                mirror.Normal = self.app.Vector(1, 0, 0)
                mirror.Placement.Base = self.app.Vector(30, 0, 0)
            pcb = doc.addObject('Part::Feature', 'PCB')
            pcb.Shape = self.part.makeBox(50, 40, 1.6)
            doc.recompute()
            doc.saveAs(str(root / 'cad/case/Case-v0.2.FCStd'))
        finally:
            self.app.closeDocument(doc.Name)
        return root

    def test_only_case_bodies_are_exported_with_mirror_placement(self):
        exporter = self.exporter()
        root = self.fixture()
        output = self.folder / 'steps'
        source = (root / 'cad/case/Case-v0.2.FCStd').read_bytes()
        exporter.export(root, output, ('v0.2',))
        self.assertEqual({p.name for p in output.iterdir()},
                         {'case-v0.2-left.step', 'case-v0.2-right.step'})
        for side, xmin, xmax in [('left', 0, 10), ('right', 20, 30)]:
            shape = self.part.read(str(output / f'case-v0.2-{side}.step'))
            self.assertTrue(shape.isValid())
            self.assertEqual(len(shape.Solids), 1)
            self.assertAlmostEqual(shape.Volume, 240, places=5)
            self.assertAlmostEqual(shape.BoundBox.XMin, xmin, places=5)
            self.assertAlmostEqual(shape.BoundBox.XMax, xmax, places=5)
        self.assertEqual((root / 'cad/case/Case-v0.2.FCStd').read_bytes(), source)

    def test_both_checked_in_versions_round_trip_as_single_case_solids(self):
        exporter = self.exporter()
        output = self.folder / 'steps'
        versions = ('v0.2', 'v1.0')
        source = {v: (ROOT / f'cad/case/Case-{v}.FCStd').read_bytes() for v in versions}
        exporter.export(ROOT, output)
        self.assertEqual({p.name for p in output.iterdir()},
                         {f'case-{v}-{s}.step' for v in versions for s in ['left', 'right']})
        for version in versions:
            doc = self.app.openDocument(str(ROOT / f'cad/case/Case-{version}.FCStd'))
            try:
                doc.recompute(None, True, True)
                for side, obj in [('left', doc.Body), ('right', doc.Right)]:
                    shape = self.part.read(str(output / f'case-{version}-{side}.step'))
                    self.assertTrue(shape.isValid())
                    self.assertEqual(len(shape.Solids), 1)
                    # Real offset geometry contains micron-scale edges healed
                    # during STEP import; the measured conversion is <0.01 mm³.
                    self.assertAlmostEqual(shape.Volume, obj.Shape.Volume, delta=0.02)
                    self.assertAlmostEqual(shape.Area, obj.Shape.Area, delta=0.02)
                    for extent in ['XMin', 'XMax', 'YMin', 'YMax', 'ZMin', 'ZMax']:
                        self.assertAlmostEqual(getattr(shape.BoundBox, extent),
                                               getattr(obj.Shape.BoundBox, extent), delta=0.003)
            finally:
                self.app.closeDocument(doc.Name)
            self.assertEqual((ROOT / f'cad/case/Case-{version}.FCStd').read_bytes(), source[version])

    def test_missing_mirror_does_not_leave_a_left_only_bundle(self):
        exporter = self.exporter()
        root = self.fixture(right=False)
        output = self.folder / 'steps'
        with self.assertRaises(ValueError):
            exporter.export(root, output, ('v0.2',))
        self.assertFalse(output.exists())

    def test_disconnected_case_solids_are_rejected(self):
        exporter = self.exporter()
        root = self.fixture(multiple_solids=True)
        output = self.folder / 'steps'
        with self.assertRaises(ValueError):
            exporter.export(root, output, ('v0.2',))
        self.assertFalse(output.exists())

    def test_missing_second_version_leaves_no_partial_bundle(self):
        exporter = self.exporter()
        root = self.fixture()
        output = self.folder / 'steps'
        with self.assertRaises((OSError, ValueError)):
            exporter.export(root, output)
        self.assertFalse(output.exists())

    def test_existing_output_is_not_overwritten(self):
        exporter = self.exporter()
        output = self.folder / 'steps'
        output.mkdir()
        sentinel = output / 'keep'
        sentinel.write_text('user data')
        with self.assertRaises(FileExistsError):
            exporter.export(ROOT, output)
        self.assertEqual(sentinel.read_text(), 'user data')
