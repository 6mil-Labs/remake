"""Assembly-specific, redistributable release exports and failure isolation."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FILES = {'remake-schematic.pdf', 'remake-left.png', 'remake-right.png',
         'remake-left.step', 'remake-right.step', 'remake-model-coverage.json'}


@unittest.skipUnless(importlib.util.find_spec('pcbnew'), 'requires pcbnew')
class ReleaseExportTests(unittest.TestCase):
    def setUp(self):
        import pcbnew
        self.k = pcbnew
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def exporter(self):
        path = ROOT / 'scripts/export-release.py'
        self.assertTrue(path.is_file(), 'release exporter is not implemented')
        spec = importlib.util.spec_from_file_location('release_exporter', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_each_assembly_contains_only_its_licensed_population(self):
        exporter = self.exporter()
        source = (ROOT / 'hw/remake.kicad_pcb').read_bytes()
        for side in ['left', 'right']:
            output = self.path / f'{side}.kicad_pcb'
            coverage = exporter.prepare_assembly(ROOT, output, side)
            board = self.k.LoadBoard(str(output))
            parts = {f.GetReference(): f for f in board.GetFootprints()}
            self.assertEqual(sum(len(f.Models()) for f in parts.values()), 78)
            self.assertEqual(len(parts['U1'].Models()), 0)
            self.assertNotIn('cad/local-models', output.read_text())
            self.assertEqual({p['reference'] for p in coverage['omitted']},
                             {'U1', 'Display1', 'JBAT_L1' if side == 'left' else 'JBAT_R1'})
            self.assertEqual(len(parts['RST_L1' if side == 'left' else 'RST_R1'].Models()), 1)
            self.assertEqual(len(parts['RST_R1' if side == 'left' else 'RST_L1'].Models()), 0)
            for model in parts['SW1'].Models():
                self.assertTrue(model.m_Show)
                self.assertEqual(model.m_Offset.z, 0 if side == 'left' else -1.6)
                self.assertEqual(model.m_Rotation.x, 0 if side == 'left' else 180)
            diode = list(parts['D1'].Models())[0]
            self.assertEqual(diode.m_Offset.z, -1.6 if side == 'left' else 0)
            power = list(parts['PWR1'].Models())[0]
            self.assertEqual(power.m_Rotation.y, 0 if side == 'left' else 180)
            links = {ref: f for ref, f in parts.items() if ref.startswith(('JPL_', 'JPR_'))}
            self.assertEqual(len(links), 44)
            bank = 'JPL_' if side == 'left' else 'JPR_'
            for ref, footprint in links.items():
                with self.subTest(side=side, link=ref):
                    active = ref.startswith(bank)
                    self.assertEqual(len(footprint.Models()), 1 if active else 0)
                    self.assertEqual(footprint.IsDNP(), not active)
                    if active:
                        self.assertEqual(footprint.IsFlipped(), side == 'left')
                        model = list(footprint.Models())[0]
                        self.assertEqual(Path(model.m_Filename).name, 'R_0402_1005Metric.step')
            self.assertIn('R_0402_1005Metric.step', coverage['models'])
            for f in board.GetFootprints():
                for model in f.Models():
                    self.assertEqual(Path(model.m_Filename).parent, ROOT / 'cad/components')
                    self.assertEqual(Path(model.m_Filename).suffix, '.step')
        self.assertEqual((ROOT / 'hw/remake.kicad_pcb').read_bytes(), source)

    def test_master_links_have_visible_project_local_models_without_clearing_dnp(self):
        # Catch a model linked only in the library, a machine-specific path,
        # or clearing DNP merely to make components appear in the viewer.
        library = self.k.FootprintLoad(str(ROOT / 'hw/lib'),
                                      'R_0402_1005Metric_SolderJumper')
        board = self.k.LoadBoard(str(ROOT / 'hw/remake.kicad_pcb'))
        links = [f for f in board.GetFootprints()
                 if f.GetReference().startswith(('JPL_', 'JPR_'))]
        self.assertEqual(len(links), 44)
        for footprint in [library, *links]:
            with self.subTest(reference=footprint.GetReference()):
                self.assertEqual(len(footprint.Models()), 1)
                model = list(footprint.Models())[0]
                self.assertEqual(model.m_Filename,
                                 '${KIPRJMOD}/../cad/components/R_0402_1005Metric.step')
                self.assertTrue(model.m_Show)
                self.assertEqual(tuple(getattr(model.m_Scale, axis) for axis in 'xyz'),
                                 (1, 1, 1))
                self.assertEqual(tuple(getattr(model.m_Offset, axis) for axis in 'xyz'),
                                 (0, 0, 0))
                self.assertEqual(tuple(getattr(model.m_Rotation, axis) for axis in 'xyz'),
                                 (0, 0, 0))
        self.assertTrue(all(f.IsDNP() for f in links))

    def copy_project(self):
        root = self.path / 'project'
        (root / 'hw').mkdir(parents=True)
        for name in ['remake.kicad_pcb', 'remake.kicad_pro', 'remake.kicad_sch']:
            shutil.copy2(ROOT / 'hw' / name, root / 'hw' / name)
        shutil.copytree(ROOT / 'cad/components', root / 'cad/components')
        return root

    def test_changed_or_missing_licensed_geometry_is_rejected(self):
        exporter = self.exporter()
        root = self.copy_project()
        model = root / 'cad/components/D_SOD123.step'
        model.write_bytes(model.read_bytes() + b'changed')
        with self.assertRaises(ValueError):
            exporter.prepare_assembly(root, self.path / 'bad.kicad_pcb', 'left')
        model.unlink()
        with self.assertRaises(ValueError):
            exporter.prepare_assembly(root, self.path / 'missing.kicad_pcb', 'right')

    def fake_cli(self):
        folder = self.path / 'bin'
        folder.mkdir()
        cli = folder / 'kicad-cli'
        cli.write_text(
            '#!/usr/bin/env python3\n'
            'import base64,os,pathlib,sys\n'
            'p=pathlib.Path(sys.argv[sys.argv.index("--output")+1])\n'
            'if os.environ.get("FAIL_EXPORT")==p.name: sys.exit(9)\n'
            'p.parent.mkdir(parents=True,exist_ok=True)\n'
            'if os.environ.get("EMPTY_EXPORT")==p.name: p.write_bytes(b"");sys.exit(0)\n'
            'data={".pdf":b"%PDF-1.4\\nfixture", ".step":b"ISO-10303-21;\\nEND-ISO-10303-21;"}\n'
            'data[".png"]=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jP1sAAAAASUVORK5CYII=")\n'
            'p.write_bytes(data[p.suffix])\n'
        )
        cli.chmod(0o755)
        return folder

    def test_complete_bundle_and_coverage_are_committed_together(self):
        exporter = self.exporter()
        cli = self.fake_cli()
        output = self.path / 'release'
        with patch.dict(os.environ, {'PATH': str(cli) + os.pathsep + os.environ['PATH']}):
            exporter.export(ROOT, output)
        self.assertEqual({p.name for p in output.iterdir()}, FILES)
        coverage = json.loads((output / 'remake-model-coverage.json').read_text())
        self.assertFalse(coverage['complete_mechanical_stack'])
        self.assertIn('native PCB', coverage['step_coordinate_frame'])
        self.assertEqual(coverage['assemblies']['left']['png_side'], 'top')
        self.assertEqual(coverage['assemblies']['right']['png_side'], 'bottom')
        self.assertIn('keycaps', coverage['unmodelled_parts'])

    def test_export_failure_or_empty_output_leaves_no_partial_bundle(self):
        exporter = self.exporter()
        cli = self.fake_cli()
        for flag in ['FAIL_EXPORT', 'EMPTY_EXPORT']:
            with self.subTest(failure=flag):
                output = self.path / flag
                env = {'PATH': str(cli) + os.pathsep + os.environ['PATH'], flag: 'remake-right.step'}
                with patch.dict(os.environ, env):
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        exporter.export(ROOT, output)
                self.assertFalse(output.exists())

    def test_existing_output_is_not_overwritten(self):
        exporter = self.exporter()
        output = self.path / 'existing'
        output.mkdir()
        sentinel = output / 'keep'
        sentinel.write_bytes(b'user output')
        with self.assertRaises((ValueError, FileExistsError)):
            exporter.export(ROOT, output)
        self.assertEqual(sentinel.read_bytes(), b'user output')

    @unittest.skipUnless(shutil.which('kicad-cli'), 'requires native KiCad CLI')
    def test_real_kicad_exports_pdf_both_pngs_and_both_steps_headlessly(self):
        exporter = self.exporter()
        root = self.path / 'minimal'
        (root / 'hw').mkdir(parents=True)
        (root / 'cad/components').mkdir(parents=True)
        (root / 'cad/components/sources.json').write_text('[]')
        board = self.k.BOARD()
        for a, b in [((0, 0), (20, 0)), ((20, 0), (20, 15)),
                     ((20, 15), (0, 15)), ((0, 15), (0, 0))]:
            edge = self.k.PCB_SHAPE()
            edge.SetShape(self.k.SHAPE_T_SEGMENT)
            edge.SetStart(self.k.VECTOR2I(*(self.k.FromMM(v) for v in a)))
            edge.SetEnd(self.k.VECTOR2I(*(self.k.FromMM(v) for v in b)))
            edge.SetWidth(self.k.FromMM(.05));edge.SetLayer(self.k.Edge_Cuts)
            board.Add(edge)
        self.k.SaveBoard(str(root / 'hw/remake.kicad_pcb'), board)
        shutil.copy2(ROOT / 'hw/remake.kicad_pro', root / 'hw/remake.kicad_pro')
        (root / 'hw/remake.kicad_sch').write_text(
            '(kicad_sch (version 20250114) (generator "eeschema") '
            '(uuid 11111111-1111-4111-8111-111111111111) (paper "A4") '
            '(lib_symbols) (sheet_instances (path "/" (page "1"))))\n')
        output = self.path / 'native'
        with patch.dict(os.environ):
            os.environ.pop('DISPLAY', None);os.environ.pop('WAYLAND_DISPLAY', None)
            exporter.export(root, output)
        self.assertEqual({p.name for p in output.iterdir()}, FILES)
        self.assertTrue((output / 'remake-schematic.pdf').read_bytes().startswith(b'%PDF-'))
        for side in ['left', 'right']:
            self.assertTrue((output / f'remake-{side}.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertIn(b'ISO-10303-21', (output / f'remake-{side}.step').read_bytes()[:100])
