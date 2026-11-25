#!/usr/bin/env python3
"""Export final left/right case solids using FreeCAD's headless Python modules."""

import argparse
import math
from pathlib import Path
import tempfile


VERSIONS = ('v0.2', 'v1.0')
# STEP import heals the source's micron-scale offset edges. One part per
# million permits that conversion, not a different body or assembly.
ROUND_TRIP_TOLERANCE = 1e-6


def export(root: Path, output: Path, versions=VERSIONS) -> None:
    """Publish a complete STEP bundle, without saving or modifying CAD sources."""
    import FreeCAD as App
    import Part

    root, output = root.resolve(), output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.case-export-', dir=output.parent) as temp:
        bundle = Path(temp) / 'bundle'
        bundle.mkdir()
        for version in versions:
            if version not in VERSIONS:
                raise ValueError(f'Unsupported case version: {version}')
            source = root / f'cad/case/Case-{version}.FCStd'
            if not source.is_file():
                raise FileNotFoundError(source)
            doc = App.openDocument(str(source))
            try:
                doc.recompute(None, True, True)
                for obj in doc.Objects:
                    if 'Invalid' in obj.State:
                        raise ValueError(f'{source.name}: {obj.Name}: {obj.getStatusString()}')
                for side, name in [('left', 'Body'), ('right', 'Right')]:
                    obj = doc.getObject(name)
                    if obj is None or not hasattr(obj, 'Shape'):
                        raise ValueError(f'{source.name}: missing {side} case body')
                    shape = obj.Shape
                    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 0:
                        raise ValueError(f'{source.name}: {side} case must be one valid solid')
                    path = bundle / f'case-{version}-{side}.step'
                    Part.export([obj], str(path))
                    exported = Part.read(str(path))
                    if (not exported.isValid() or len(exported.Solids) != 1
                            or not math.isclose(exported.Volume, shape.Volume, rel_tol=ROUND_TRIP_TOLERANCE, abs_tol=1e-5)
                            or not math.isclose(exported.Area, shape.Area, rel_tol=ROUND_TRIP_TOLERANCE, abs_tol=1e-5)):
                        raise ValueError(f'{path.name}: STEP round-trip changed the case solid')
            finally:
                App.closeDocument(doc.Name)
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        bundle.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New output directory (must not exist)')
    parser.add_argument('--version', choices=VERSIONS, help='Export only this case version')
    args = parser.parse_args()
    try:
        export(Path(__file__).resolve().parents[1], args.output,
               (args.version,) if args.version else VERSIONS)
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'Case export failed: {error}\n')
    print(f'Created case-body STEP files in {args.output}')


if __name__ == '__main__':
    main()
