# Manufacturing

Use `hw/remake.kicad_pro` with **KiCad 10.0.7 or newer**. Manufacture two separate,
identical, **two-layer** half PCBs; do not mirror a second layout or panelize them.
The current board/model stack assumes **1.6 mm PCB thickness**.

## Before ordering

- Resolve the findings in the [project checks](../README.md#checks), run the full
  regression suite, and complete the component/physical checks in [assembly](assembly.md).
- Run ERC and refilled DRC with `--exit-code-violations`; DRC also needs
  `--refill-zones --schematic-parity`. Do not waive findings for a release.
- Preserve the current rules: 0.3048 mm signal / 0.6096 mm Power tracks,
  0.2032 mm class clearance, 0.60/0.30 mm via diameter/drill, 0.25 mm minimum
  hole clearance and 0.5 mm copper-edge clearance. Keep both GND pours, thermals,
  antenna keepout and solder-selection gaps intact.
- Refill **and save** the checked PCB before exporting. Inspect both faces,
  Gerbers and drills in a CAM viewer and verify the fabricator's interpretation.
  CAD checks alone do not approve the battery, stack, keycap fit or RF performance.

## Fabrication archive

**Upload only `remake-jlcpcb.zip` to JLCPCB.** It contains exactly one design's
Gerbers and drills—not separate left/right designs or presentation files.
Select the quantity needed for two identical halves per keyboard.

The flat archive contains:

| Layers/files | Extensions |
|---|---|
| Front/back copper | `.gtl`, `.gbl` |
| Front/back solder mask | `.gts`, `.gbs` |
| Front/back silkscreen | `.gto`, `.gbo` |
| Front/back solder paste | `.gtp`, `.gbp` |
| Board outline | `.gm1` |
| Separate plated/non-plated drills | `remake-PTH.drl`, `remake-NPTH.drl` |

Use Protel Gerber extensions, X2 metadata, millimetres, 4.6 Gerber coordinates
and absolute-origin decimal Excellon drills. Paste is included for stencils;
this is not a PCB-assembly package with a BOM and placement file.

Generate the design previews, then package an already-generated Gerber directory
from the repository root:

```sh
python3 scripts/export-release.py build/release
python3 scripts/package-jlcpcb.py build/jlcpcb build/release/remake-jlcpcb.zip
```

The preview directory must not already exist; the fabrication ZIP must not
already exist. The packager rejects missing, empty or symlinked required files
and excludes all previews, reports, drill maps and additional designs. It checks
the file set, **not manufacturability or CI status**. Outputs stay in ignored `build/`.

## Releases

Pushing a tag runs the required CI on that commit. Only successful CI and
fabrication packaging permit a checksum-verified **draft** release. Publication
is manual; failed, cancelled or skipped prerequisites do not create a draft.
Treat tags as immutable; use a new tag for fixes rather than moving an existing
release tag. Review all outputs and physical-validation gates before publishing.

Separate release attachments are the fabrication ZIP, `remake-schematic.pdf`,
`remake-left.png`, `remake-right.png`, `remake-left.step`, `remake-right.step`,
`remake-model-coverage.json` and `SHA256SUMS`. The checksum gate requires and
verifies every payload before draft creation. None of the previews go in the
JLCPCB ZIP.

PNGs show each half's typing face. STEP files use the **same native PCB frame**;
the right population is on B, so flip the entire imported right assembly to
put its typing face upward. Both are **partial mechanical models**: the coverage
JSON identifies missing geometry, the provisional controller gap and model
licences/notices. Do not design a tight case without checking the real stack.

When distributing boards or source, provide the source/source-location
information required by [CERN-OHL-S-2.0](../LICENSE).

Export settings reference:
[JLCPCB's KiCad Gerber/drill guide](https://jlcpcb.com/help/article/how-to-generate-gerber-and-drill-files-in-kicad-9).
