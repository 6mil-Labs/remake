"""Execute workflow shell steps offline; use real KiCad when installed."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def run_step(name):
    """Read a literal run block without requiring a YAML dependency in CI."""
    lines = (ROOT / '.github/workflows/release.yml').read_text().splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == f'- name: {name}'), None)
    if start is None:
        raise AssertionError(f'Missing workflow step: {name}')
    block = []
    for line in lines[start + 1:]:
        if not block:
            if line.strip() == 'run: |':
                block.append('')
            continue
        if line.strip() and not line.startswith('          '):
            break
        block.append(line[10:])
    if not block:
        raise AssertionError(f'No literal run block for {name}')
    return '\n'.join(block[1:]) + '\n'


@unittest.skipUnless(shutil.which('bash') and shutil.which('jq'), 'requires bash and jq')
class DraftCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'build/release').mkdir(parents=True)
        # Only the GitHub network boundary is replaced; execute the actual shell.
        gh = self.root / 'gh'
        gh.write_text(
            '#!/usr/bin/env python3\n'
            'import json,os,sys\n'
            'if sys.argv[1]=="api":\n'
            '    if os.environ.get("LOOKUP_FAIL"): sys.exit(1)\n'
            '    pages=json.loads(os.environ["RELEASE_PAGES"])\n'
            '    if not isinstance(pages,list):\n'
            '        print(json.dumps(pages)); sys.exit(0)\n'
            '    if "--paginate" not in sys.argv: pages=pages[:1]\n'
            '    print(json.dumps(pages if "--slurp" in sys.argv else pages[0]))\n'
            'elif sys.argv[1:3]==["release","create"]:\n'
            '    open("created.json","w").write(json.dumps(sys.argv[3:]))\n'
            'else: sys.exit(2)\n'
        )
        gh.chmod(0o755)
        self.env = os.environ | {
            'PATH': str(self.root) + os.pathsep + os.environ['PATH'],
            'GH_TOKEN': 'offline-test-token', 'GH_REPO': 'example/remake',
            'RELEASE_TAG': 'v0.1', 'CHECKED_COMMIT': 'a' * 40,
            'RELEASE_PAGES': '[[]]',
        }

    def create(self):
        return subprocess.run(
            ['bash', '-e', '-o', 'pipefail', '-c', run_step('Create draft release with fabrication assets')],
            cwd=self.root, env=self.env, capture_output=True, text=True, check=False,
        )

    def test_existing_draft_on_later_page_prevents_another_creation(self):
        # Catch missing pagination and gh create's lack of draft uniqueness checks.
        self.env['RELEASE_PAGES'] = json.dumps([
            [{'id': 1, 'tag_name': 'v0.0', 'draft': False}],
            [{'id': 2, 'tag_name': 'v0.1', 'draft': True}],
        ])
        result = self.create()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'created.json').exists())

    def test_existing_published_release_is_not_replaced(self):
        self.env['RELEASE_PAGES'] = '[[{"id":1,"tag_name":"v0.1","draft":false}]]'
        result = self.create()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'created.json').exists())

    def test_lookup_failure_is_fatal_before_creation(self):
        # Catch a permission/network failure being mistaken for no existing draft.
        self.env['LOOKUP_FAIL'] = '1'
        result = self.create()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'created.json').exists())

    def test_malformed_lookup_is_fatal_before_creation(self):
        self.env['RELEASE_PAGES'] = '{"message":"not a release listing"}'
        result = self.create()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'created.json').exists())

    def test_absent_tag_requests_draft_and_keeps_shell_characters_literal(self):
        self.env['RELEASE_TAG'] = 'v0.1;$(touch${IFS}UNEXPECTED)'
        result = self.create()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads((self.root / 'created.json').read_text())
        self.assertIn('--draft', args)
        self.assertIn('--verify-tag', args)
        self.assertEqual(args[args.index('--') + 1], self.env['RELEASE_TAG'])
        self.assertFalse((self.root / 'UNEXPECTED').exists())

    def test_draft_attaches_all_design_exports_and_checksums(self):
        result = self.create()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads((self.root / 'created.json').read_text())
        for name in ['remake-jlcpcb.zip', 'remake-schematic.pdf', 'remake-left.png',
                     'remake-right.png', 'remake-left.step', 'remake-right.step',
                     'remake-model-coverage.json', 'SHA256SUMS']:
            self.assertIn('build/release/' + name, args)

    def test_checksum_gate_detects_tampering_in_non_fabrication_assets(self):
        assets = ['remake-jlcpcb.zip', 'remake-schematic.pdf', 'remake-left.png',
                  'remake-right.png', 'remake-left.step', 'remake-right.step',
                  'remake-model-coverage.json']
        folder = self.root / 'build/release'
        for name in assets:
            (folder / name).write_text('fixture ' + name)
        created = subprocess.run(['bash', '-ec', run_step('Create checksums')], cwd=folder,
                                 capture_output=True, text=True)
        self.assertEqual(created.returncode, 0, created.stderr)
        lines = (folder / 'SHA256SUMS').read_text().splitlines()
        self.assertEqual({line.split(maxsplit=1)[1] for line in lines}, set(assets))
        (folder / 'remake-right.step').write_text('tampered geometry')
        checked = subprocess.run(['bash', '-ec', run_step('Verify downloaded release checksums')],
                                 cwd=folder, capture_output=True, text=True)
        self.assertNotEqual(checked.returncode, 0)

    def test_checksum_gate_rejects_a_manifest_missing_a_required_asset(self):
        folder = self.root / 'build/release'
        for name in ['remake-jlcpcb.zip', 'remake-schematic.pdf', 'remake-left.png',
                     'remake-right.png', 'remake-left.step', 'remake-right.step',
                     'remake-model-coverage.json']:
            (folder / name).write_text('fixture ' + name)
        result = subprocess.run(['bash', '-ec', run_step('Create checksums')], cwd=folder,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = folder / 'SHA256SUMS'
        manifest.write_text(''.join(line for line in manifest.read_text().splitlines(True)
                                    if 'remake-right.step' not in line))
        checked = subprocess.run(['bash', '-ec', run_step('Verify downloaded release checksums')],
                                 cwd=folder, capture_output=True, text=True)
        self.assertNotEqual(checked.returncode, 0)


@unittest.skipUnless(
    shutil.which('kicad-cli') and importlib.util.find_spec('pcbnew'),
    'requires KiCad CLI and its pcbnew Python module',
)
class RefilledCopperHandoffTests(unittest.TestCase):
    def test_export_reloads_the_copper_that_passed_drc(self):
        # Catch DRC refilling only its in-memory board while export reloads stale copper.
        import pcbnew

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'hw').mkdir()
            (root / 'build/kicad').mkdir(parents=True)
            board = pcbnew.BOARD()
            for start, end in [((0, 0), (20, 0)), ((20, 0), (20, 20)),
                               ((20, 20), (0, 20)), ((0, 20), (0, 0))]:
                edge = pcbnew.PCB_SHAPE()
                edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
                edge.SetStart(pcbnew.VECTOR2I(*(pcbnew.FromMM(v) for v in start)))
                edge.SetEnd(pcbnew.VECTOR2I(*(pcbnew.FromMM(v) for v in end)))
                edge.SetWidth(pcbnew.FromMM(0.05))
                edge.SetLayer(pcbnew.Edge_Cuts)
                board.Add(edge)
            ground = pcbnew.NETINFO_ITEM(board, 'GND', 1)
            board.Add(ground)
            anchor = pcbnew.FOOTPRINT(board)
            anchor.SetReference('J1')
            anchor.SetValue('ZoneAnchor')
            anchor.SetAttributes(pcbnew.FP_BOARD_ONLY)
            anchor.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(10), pcbnew.FromMM(10)))
            anchor.Reference().SetVisible(False)
            anchor.Value().SetVisible(False)
            pad = pcbnew.PAD(anchor)
            pad.SetNumber('1')
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(2), pcbnew.FromMM(2)))
            pad.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(1), pcbnew.FromMM(1)))
            pad.SetLayerSet(pcbnew.PAD.PTHMask())
            pad.SetPosition(anchor.GetPosition())
            pad.SetNet(ground)
            anchor.Add(pad)
            board.Add(anchor)
            zone = pcbnew.ZONE(board)
            zone.SetLayer(pcbnew.F_Cu)
            zone.SetNet(ground)
            zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
            zone.SetLocalClearance(pcbnew.FromMM(0.2))
            zone.SetThermalReliefGap(pcbnew.FromMM(0.3))
            zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.3))
            zone.SetMinThickness(pcbnew.FromMM(0.2))
            outline = zone.Outline()
            outline.NewOutline()
            for x, y in [(2, 2), (18, 2), (18, 18), (2, 18)]:
                outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
            board.Add(zone)
            board_path = root / 'hw/remake.kicad_pcb'
            pcbnew.SaveBoard(str(board_path), board)
            (root / 'hw/remake.kicad_sch').write_text(
                '(kicad_sch (version 20250114) (generator "eeschema") '
                '(uuid 11111111-1111-4111-8111-111111111111) (paper "A4") '
                '(lib_symbols) (sheet_instances (path "/" (page "1"))))\n'
            )
            initial = pcbnew.LoadBoard(str(board_path))
            self.assertTrue(list(initial.Zones())[0].GetFilledPolysList(pcbnew.F_Cu).IsEmpty())
            # Docker is not installed locally. Translate only the container boundary
            # to native execution of the same real kicad-cli and all its arguments.
            docker = root / 'docker'
            docker.write_text(
                '#!/usr/bin/env python3\nimport subprocess,sys\n'
                'start=sys.argv.index("kicad/kicad:10.0")+1\n'
                'sys.exit(subprocess.run(sys.argv[start:]).returncode)\n'
            )
            docker.chmod(0o755)
            env = os.environ | {'PATH': str(root) + os.pathsep + os.environ['PATH']}
            result = subprocess.run(
                ['bash', '-e', '-o', 'pipefail', '-c', run_step('Check and refill the board before export')],
                cwd=root, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            reloaded = pcbnew.LoadBoard(str(board_path))
            self.assertFalse(list(reloaded.Zones())[0].GetFilledPolysList(pcbnew.F_Cu).IsEmpty())
            exported = subprocess.run(
                ['kicad-cli', 'pcb', 'export', 'gerbers', '--layers', 'F.Cu',
                 '--output', str(root / 'gerbers'), str(board_path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertIn('G36*', (root / 'gerbers/remake-F_Cu.gtl').read_text())


if __name__ == '__main__':
    unittest.main()
