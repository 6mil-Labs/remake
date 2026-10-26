#!/usr/bin/env python3
"""Export the schematic and licensed left/right assembly previews."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


FILES = ('remake-schematic.pdf', 'remake-left.png', 'remake-right.png',
         'remake-left.step', 'remake-right.step', 'remake-model-coverage.json')


def _licensed_models(root):
    directory = root / 'cad/components'
    approved = {}
    for entry in json.loads((directory / 'sources.json').read_text()):
        for key in ['file', 'sha256', 'source', 'license', 'attribution', 'notice']:
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise ValueError(f'Model manifest requires {key}: {entry}')
        for key in ['file', 'notice']:
            if Path(entry[key]).name != entry[key] or '\\' in entry[key]:
                raise ValueError(f'Invalid model-manifest path: {entry[key]}')
        model, notice = directory / entry['file'], directory / entry['notice']
        if (model.is_symlink() or not model.is_file() or notice.is_symlink()
                or not notice.is_file() or not model.resolve().is_relative_to(root)):
            raise ValueError(f'Missing regular model/notice: {model}')
        if hashlib.sha256(model.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'Model hash differs from approved source: {model}')
        notice_text = notice.read_text()
        if not notice_text.strip():
            raise ValueError(f'Empty model notice: {notice}')
        if model.resolve() in approved:
            raise ValueError(f'Duplicate model in manifest: {model}')
        approved[model.resolve()] = entry | {'notice_text': notice_text}
    return approved


def _population(footprint, side, count):
    name = str(footprint.GetFPID().GetLibItemName())
    right = side == 'right'
    pairs = {'SW_Hotswap_Kailh_Choc_V1_reversible': (4, (0, 1), (2, 3)),
             'Diode_SOD123_reversible': (2, (0,), (1,)),
             'SW_Power_MSK12C02_reversible': (2, (0,), (1,)),
             'nice_nano_reversible': (2, (0,), (1,))}
    if name in pairs:
        expected, left, back = pairs[name]
        if count != expected:
            raise ValueError(f'{footprint.GetReference()}: expected {expected} assembly models, got {count}')
        return (back if right else left), True
    if name in {'SW_SPST_Panasonic_EVQPUJ02K', 'JST_PH_2mm_side_entry'}:
        active = footprint.IsFlipped() == right
        return (tuple(range(count)) if active else ()), active
    if name == 'nice_view_reversible':
        if count:
            raise ValueError('Display model population needs an explicit assembly mapping')
        return (), True
    if count:
        raise ValueError(f'No assembly-model policy for {footprint.GetReference()} ({name})')
    return (), False


def prepare_assembly(root: Path, output: Path, side: str) -> dict:
    """Save a temporary native-frame PCB with only redistributable selected models."""
    import pcbnew

    root = root.resolve()
    if side not in {'left', 'right'}:
        raise ValueError(f'Unknown assembly: {side}')
    if output.exists() or output.is_symlink() or output.with_suffix('.kicad_pro').exists():
        raise FileExistsError(output)
    approved = _licensed_models(root)
    board = pcbnew.LoadBoard(str(root / 'hw/remake.kicad_pcb'))
    included, omitted = set(), []
    for footprint in board.GetFootprints():
        # Capture values before clearing the native vector: SWIG elements can
        # otherwise refer to invalidated storage.
        records = [(m.m_Filename, m.m_Opacity,
                    tuple(getattr(m.m_Offset, a) for a in 'xyz'),
                    tuple(getattr(m.m_Rotation, a) for a in 'xyz'),
                    tuple(getattr(m.m_Scale, a) for a in 'xyz')) for m in footprint.Models()]
        indices, active = _population(footprint, side, len(records))
        selected = []
        for index in indices:
            record = records[index]
            filename = record[0].replace('${KIPRJMOD}', str(root / 'hw'))
            if '${' in filename:
                raise ValueError(f'Unresolved model variable: {filename}')
            path = Path(filename)
            if not path.is_absolute():
                path = root / 'hw' / path
            path = path.resolve()
            if (footprint.GetReference() == 'U1'
                    and path == root / 'cad/local-models/nice_nano_v2.step'):
                omitted.append({'reference': 'U1', 'reason': 'Local-only controller model has no redistribution licence'})
                continue
            if path not in approved:
                raise ValueError(f'Model is not in the approved redistribution manifest: {path}')
            included.add(approved[path]['file'])
            selected.append((str(path), *record[1:]))
        footprint.Models().clear()
        for filename, opacity, offset, rotation, scale in selected:
            model = pcbnew.FP_3DMODEL()
            model.m_Filename = filename
            model.m_Show = True
            model.m_Opacity = opacity
            for attribute, values in [('m_Offset', offset), ('m_Rotation', rotation), ('m_Scale', scale)]:
                vector = getattr(model, attribute)
                for axis, value in zip('xyz', values):
                    setattr(vector, axis, value)
            footprint.Models().push_back(model)
        if active and not records:
            omitted.append({'reference': footprint.GetReference(), 'reason': 'No model supplied for this part/module/socket'})
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / 'hw/remake.kicad_pro', output.with_suffix('.kicad_pro'))
    pcbnew.SaveBoard(str(output), board)
    return {'png_side': 'top' if side == 'left' else 'bottom',
            'models': sorted(included), 'omitted': sorted(omitted, key=lambda p: p['reference'])}


def _validate_output(path, signature):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Missing, empty or invalid export: {path}')
    with path.open('rb') as exported:
        if exported.read(len(signature)) != signature:
            raise ValueError(f'Missing, empty or invalid export: {path}')


def export(root: Path, output: Path) -> None:
    """Commit a complete preview bundle, or leave no output directory on failure."""
    root, output = root.resolve(), output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.remake-export-', dir=output.parent) as temp:
        work = Path(temp)
        bundle = work / 'bundle'
        bundle.mkdir()
        subprocess.run(['kicad-cli', 'sch', 'export', 'pdf', '--black-and-white',
                        '--output', str(bundle / 'remake-schematic.pdf'),
                        str(root / 'hw/remake.kicad_sch')], check=True)
        assemblies = {}
        for side in ['left', 'right']:
            board = work / f'{side}.kicad_pcb'
            assemblies[side] = prepare_assembly(root, board, side)
            subprocess.run(['kicad-cli', 'pcb', 'render', '--width', '1600', '--height', '1200',
                            '--side', assemblies[side]['png_side'], '--quality', 'basic',
                            '--use-board-stackup-colors', '--output', str(bundle / f'remake-{side}.png'),
                            str(board)], check=True)
            subprocess.run(['kicad-cli', 'pcb', 'export', 'step', '--cut-vias-in-body',
                            '--output', str(bundle / f'remake-{side}.step'), str(board)], check=True)
        used = set().union(*(a['models'] for a in assemblies.values()))
        notices = {v['file']: v for v in _licensed_models(root).values() if v['file'] in used}
        coverage = {
            'complete_mechanical_stack': False,
            'step_coordinate_frame': 'Both STEP files use the native PCB coordinate frame. The right assembly has its typing face on B; flip the entire imported right assembly to place that face upward. PNGs already show each typing face.',
            'provisional_controller_gap_mm': 6,
            'unmodelled_parts': ['controller and socket-header stack', 'display and socket',
                                'protected battery', 'keycaps', 'case retention'],
            'warning': 'Partial geometry only: verify actual parts, tolerances, USB/case access and stack heights before case design or fabrication. No placeholder geometry is substituted.',
            'assemblies': assemblies, 'third_party_models': notices,
        }
        (bundle / 'remake-model-coverage.json').write_text(json.dumps(coverage, indent=2) + '\n')
        _validate_output(bundle / 'remake-schematic.pdf', b'%PDF-')
        for side in ['left', 'right']:
            _validate_output(bundle / f'remake-{side}.png', b'\x89PNG\r\n\x1a\n')
            _validate_output(bundle / f'remake-{side}.step', b'ISO-10303-21;')
        if set(p.name for p in bundle.iterdir()) != set(FILES):
            raise ValueError('Unexpected release-preview file set')
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        bundle.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New output directory (must not exist)')
    args = parser.parse_args()
    try:
        export(Path(__file__).resolve().parents[1], args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Release export failed: {error}\n')
    print(f'Created schematic, assembly PNG/STEP and model coverage in {args.output}')


if __name__ == '__main__':
    main()
