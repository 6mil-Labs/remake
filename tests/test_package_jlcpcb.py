"""Public CLI contract for the JLCPCB fabrication archive."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/package-jlcpcb.py'
FILES = (
    'remake-F_Cu.gtl', 'remake-B_Cu.gbl',
    'remake-F_Mask.gts', 'remake-B_Mask.gbs',
    'remake-F_Silkscreen.gto', 'remake-B_Silkscreen.gbo',
    'remake-F_Paste.gtp', 'remake-B_Paste.gbp',
    'remake-Edge_Cuts.gm1', 'remake-PTH.drl', 'remake-NPTH.drl',
)


class FabricationArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'gerbers'
        self.source.mkdir()
        self.output = self.root / 'release/remake-jlcpcb.zip'
        for name in FILES:
            (self.source / name).write_bytes(f'fixture: {name}\n'.encode())

    def package(self, output=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), str(output or self.output)],
            capture_output=True, text=True, check=False,
        )

    def test_archive_contains_all_layers_and_both_drill_files_without_extra_files(self):
        # Catch glob-based packaging that includes drill maps/reports or omits NPTH.
        (self.source / 'remake-PTH-drl_map.gbr').write_text('not a copper layer')
        (self.source / 'drc.rpt').write_text('not fabrication input')
        (self.source / 'remake-job.gbrjob').write_text('{}')
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), set(FILES))
            self.assertIsNone(archive.testzip())
            for name in FILES:
                self.assertEqual(archive.read(name), f'fixture: {name}\n'.encode())

    def test_missing_drill_file_refuses_to_create_archive(self):
        # Catch manufacturing ZIPs silently missing the non-plated holes.
        (self.source / 'remake-NPTH.drl').unlink()
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('remake-NPTH.drl', result.stderr)
        self.assertFalse(self.output.exists())

    def test_second_design_and_preview_assets_are_not_packaged(self):
        # JLCPCB must receive one design, even if another half or release
        # previews accidentally share the export directory.
        for name in FILES:
            (self.source / name.replace('remake-', 'remake-right-', 1)).write_text('second design')
        for name in ['remake-schematic.pdf', 'remake-left.png', 'remake-right.png',
                     'remake-left.step', 'remake-right.step', 'remake-model-coverage.json']:
            (self.source / name).write_text('release preview, not fabrication input')
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), set(FILES))
            self.assertEqual(len(archive.namelist()), 11)

    def test_empty_layer_refuses_to_create_archive(self):
        # Catch an interrupted export leaving an empty board outline.
        (self.source / 'remake-Edge_Cuts.gm1').write_bytes(b'')
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('remake-Edge_Cuts.gm1', result.stderr)
        self.assertFalse(self.output.exists())

    def test_symlink_is_not_accepted_as_an_export(self):
        # Catch inclusion of a file from outside the generated export directory.
        target = self.root / 'outside.drl'
        target.write_text('not an export')
        path = self.source / 'remake-PTH.drl'
        path.unlink()
        path.symlink_to(target)
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('remake-PTH.drl', result.stderr)
        self.assertFalse(self.output.exists())

    def test_same_exports_produce_identical_archives_despite_file_timestamps(self):
        # Catch ZIP metadata making identical releases differ between runs.
        first = self.package()
        self.assertEqual(first.returncode, 0, first.stderr)
        for path in self.source.iterdir():
            os.utime(path, (1700000000, 1700000000))
        second_path = self.root / 'second.zip'
        second = self.package(second_path)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.output.read_bytes(), second_path.read_bytes())

    def test_existing_archive_is_not_overwritten(self):
        # Catch an accidental replacement of an already-produced artifact.
        self.output.parent.mkdir()
        self.output.write_bytes(b'keep this existing artifact')
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(self.output.name, result.stderr)
        self.assertEqual(self.output.read_bytes(), b'keep this existing artifact')


if __name__ == '__main__':
    unittest.main()
