#!/usr/bin/env python3
"""Package this two-layer board's fabrication exports, not maps or reports."""

import argparse
from pathlib import Path
import zipfile


FABRICATION_FILES = (
    'remake-F_Cu.gtl', 'remake-B_Cu.gbl',
    'remake-F_Mask.gts', 'remake-B_Mask.gbs',
    'remake-F_Silkscreen.gto', 'remake-B_Silkscreen.gbo',
    'remake-F_Paste.gtp', 'remake-B_Paste.gbp',
    'remake-Edge_Cuts.gm1', 'remake-PTH.drl', 'remake-NPTH.drl',
)


def package(source: Path, output: Path) -> None:
    exports = {}
    for name in FABRICATION_FILES:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing regular export file: {path}')
        data = path.read_bytes()
        if not data:
            raise ValueError(f'Empty export file: {path}')
        exports[name] = data

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, mode='x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in exports.items():
            # Fixed metadata makes the same export bytes produce the same ZIP.
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='KiCad Gerber/drill export directory')
    parser.add_argument('output', type=Path, help='New ZIP archive (must not already exist)')
    args = parser.parse_args()
    try:
        package(args.source, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Packaging failed: {error}\n')
    print(f'Created {args.output} with {len(FABRICATION_FILES)} fabrication files')


if __name__ == '__main__':
    main()
