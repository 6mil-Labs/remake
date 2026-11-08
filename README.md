# REMAKE

![REMAKE keyboard logo](docs/assets/remake-logo.svg)

REMAKE is a **36-key wireless split keyboard** designed by **Felipe Balbi**
around RMK firmware. Its name includes **RMK**.

Each half has 15 finger keys and a three-key thumb cluster. The stepped board
outline follows the column stagger and thumb fan. Both halves use the same
reversible PCB: manufacture **two separate, identical boards** and populate
them in opposite orientations. No panelization or mouse bites are required.

## Revision validation status

| Revision | Status |
|---|---|
| REV 0.1 | Fully validated |
| REV 0.2 | Under development |

> **REV 0.2: development hardware — do not fabricate yet.** The current design has
> **18 keys per half / 36 total.** Routing is complete, ground pours are filled,
> and the outline is closed and
> tangent. SW17 supports a **26.5×16.5 mm cap**, rotated
> 90° relative to its original thumb fan; other caps use **17.5×16.5 mm** envelopes.
> The minimum nominal thumb-to-row gap is approximately **0.660 mm**.
> Production tolerances and moving-key fit have not been physically validated.
> Component selection and physical validation are incomplete. Firmware
> lives in a separate repository and has not been built or validated here.

## Repository layout

| Path | Contents |
|---|---|
| [`hw/`](hw/) | KiCad project, schematic, PCB, local libraries and library tables |
| [`cad/`](cad/) | Component models, source manifest and third-party notices |
| [`docs/`](docs/) | Assembly, manufacturing and component references |
| [`docs/assets/`](docs/assets/) | Vector logo and source artwork |
| [`.github/workflows/`](.github/workflows/) | KiCad checks; no automatic source commits |

The root contains project-level documentation and licensing. Generated reports
and exports belong in ignored output directories, not alongside source files.

## Open the hardware

Use **KiCad 10.0.7 or newer** and open [`hw/remake.kicad_pro`](hw/remake.kicad_pro).
Local library tables and project-relative model paths travel with the project.

On this machine, use the following workaround for the native Wayland issue:

```sh
GDK_BACKEND=x11 kicad hw/remake.kicad_pro
```

Read [assembly](docs/assembly.md) before building. The
[component reference](docs/components.md) records sources, licences and model
limitations; a rendering is not proof of fit. The regression suite checks
schematic-to-PCB associations separately from electrical parity.

## Checks

Run from the repository root, with reports outside the source tree:

```sh
mkdir -p .remake-checks
kicad-cli pcb drc --format json --refill-zones --schematic-parity \
  --output .remake-checks/drc.json hw/remake.kicad_pcb
kicad-cli sch erc --format json \
  --output .remake-checks/erc.json hw/remake.kicad_sch
```

Before fabrication, require clean refilled DRC, zero unconnected items and
schematic parity, and review all ERC findings. Use `--exit-code-violations` for
gated checks. Do not hide findings, weaken rules or bridge selection jumpers
to make checks pass. Component-rating, physical assembly, battery-safety and
prototype/RF checks remain required even when CAD checks pass.

Run the regression suite as well:

```sh
python3 -m unittest discover -s tests -v
```

## Draft releases

Pushing a tag runs the same required CI on that exact commit. Only after CI
and fabrication packaging succeed does the workflow create a **draft** GitHub
Release containing one-design JLCPCB fabrication ZIP, a schematic PDF,
left/right PNG and STEP previews, model-coverage notes and checksums. Preview
files are separate attachments, never additional designs inside the JLCPCB ZIP.
The STEP assemblies are partial; check their coverage notes before case design.
Review and publish the draft manually; failed, cancelled or skipped prerequisites
block release creation. Passing CI is not physical/fabrication approval.

See [manufacturing and release details](docs/manufacturing.md) for archive
contents, validation limits and retry behavior.

## Contributing and licensing

See [CONTRIBUTING.md](CONTRIBUTING.md) for source organization and validation
expectations.

**Copyright © 2026 Felipe Balbi.** REMAKE is licensed under the
**CERN Open Hardware Licence Version 2 — Strongly Reciprocal**
([CERN-OHL-S-2.0](LICENSE)); see [COPYRIGHT](COPYRIGHT) for the project notice.
Imported third-party component models and library sources retain their
documented licences and notices. Local-only models with unresolved
redistribution rights are not covered by the project licence grant.

### Manufacturing and sales

Interested in manufacturing or selling REMAKE boards or kits? I'd love to hear
from you! Please [open a manufacturing and sales issue](https://github.com/6mil-Labs/remake/issues/new?template=manufacturing-and-sales.yml)
to discuss revisions, manufacturing feedback, and opportunities to collaborate.
You can also opt in to a future seller list to help people find bare PCBs, kits,
or assembled keyboards without building everything themselves.

Commercial manufacture and sale are permitted under [CERN-OHL-S-2.0](LICENSE),
subject to its requirements. Contacting the maintainer is encouraged, but is not
a condition of exercising those rights. Third-party products must not be
presented as officially endorsed without permission.
