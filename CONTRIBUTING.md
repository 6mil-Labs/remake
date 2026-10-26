# Contributing to REMAKE

REMAKE is development hardware, not a fabrication-ready release.

## Keep sources organized

- `hw/`: KiCad projects, schematics, boards, symbols, footprints and library tables.
- `cad/`: editable mechanical designs and component models used by KiCad.
- `docs/`: assembly instructions, design notes, provenance and other documentation.
- `docs/assets/`: logos, source artwork, diagrams and documentation images.
- `.github/workflows/`: automation configuration.
- `scripts/`: build and fabrication tooling.
- `tests/`: regression tests for that tooling.

Keep generated board exports in ignored `cad/exports/`, reports and CI artifacts
in ignored `build/`, and temporary investigation files outside the repository.
Do not ignore all STEP files: the component models in `cad/components/` are
intentional source dependencies.

## Hardware changes

Preserve the reversible assembly scheme and validate both populated faces.
Never route copper across the solder-selection gaps. Changes to footprints
must identify their source drawings, dimensions, pad numbering and orientation.
Keep schematic footprints, library sources and placed PCB copies consistent.

Run the checks in [README.md](README.md#checks). Compare findings with the
existing baseline and report remaining problems honestly; do not suppress
unconnected items or weaken manufacturing constraints to obtain a clean report.
CAD checks do not replace physical fit, battery-safety or prototype validation.

Use project-relative library/model references. Keep provenance and applicable
third-party notices with imported components. Remove obsolete, unreferenced
assets rather than keeping alternative source files that do not describe the
active design. Do not remove a local-only model merely because it is ignored:
check the actual PCB/library references first.

REMAKE's project-authored materials are copyright Felipe Balbi and licensed
under CERN-OHL-S-2.0; see [COPYRIGHT](COPYRIGHT) and [LICENSE](LICENSE).
Imported components keep their separate licences and redistribution limits.

## Release tooling

Run `python3 -m unittest discover -s tests -v` and lint both workflows with
`actionlint` when changing CI or fabrication packaging. Tag releases reuse the
same required CI and create drafts only after successful checks and packaging;
never add a bypass for a failed, cancelled or skipped prerequisite. See
[the manufacturing guide](docs/manufacturing.md).
