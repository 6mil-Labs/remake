# Component sources and models

REMAKE's reversible Choc-v1 footprint was created from the supplied Kailh
datasheet. It and the project-authored controller/display socket arrangements,
symbols and artwork are Felipe Balbi's designs under [CERN-OHL-S-2.0](../LICENSE);
see [COPYRIGHT](../COPYRIGHT). Imported Choc models are separate assets, not
the source or licence of REMAKE's footprint.

## Imported footprint sources

These local library sources retain **KiCad Library Team/contributor** attribution
and **CC-BY-SA-4.0 with the KiCad libraries exception**, not the project licence.
The notice is in [LICENSE-KICAD.txt](../cad/components/LICENSE-KICAD.txt).

| Local footprint | KiCad source |
|---|---|
| `JST_PH_2mm_side_entry` | `Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal` |
| `SW_SPST_Panasonic_EVQPUJ02K` | `Button_Switch_SMD:Panasonic_EVQPUJ_EVQPUA` |
| `R_0402_1005Metric_SolderJumper` | Geometry derived from `Resistor_SMD:R_0402_1005Metric`, adapted for manual bridging |

The JST copy is renamed, hides reference/value fields and omits the unresolved
3D link; lands are unchanged. The reset copy is renamed and moves clipping silk
strokes to fabrication; copper, pin numbering and courtyard are unchanged.
Reset is side-actuated, momentary SPST-NO, without locating bosses.

Sources: [KiCad footprints](https://gitlab.com/kicad/libraries/kicad-footprints),
[JST PH drawing](https://www.jst-mfg.com/product/pdf/eng/ePH.pdf),
[Panasonic EVQPUJ02K](https://industry.panasonic.com/global/en/products/control/switch/light-touch/number/evqpuj02k).

## Dual-use 0402 selection links

The hybrid footprint derives its nominal resistor geometry from KiCad's
[`R_0402_1005Metric`](https://gitlab.com/kicad/libraries/kicad-footprints/-/blob/master/Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod)
(installed library format version 20260206). It retains KiCad Library
Team/contributor attribution and the licence/exception noted above. It is
not an unmodified standard footprint or a manufacturer-qualified land pattern.

- Resistor body outline: 1.05 × 0.54 mm, centred at the footprint origin.
- Two rectangular paste apertures: **0.54 × 0.64 mm**, centred at X = ±0.51 mm,
  matching the nominal standard pad centres and extents; **0.48 mm paste gap**.
  Rectangular paste replaces the standard footprint's rounded pad apertures.
- Extended roundrect copper pads: **0.63 × 1.00 mm**, centred at X = ±0.465 mm.
  These contain the nominal resistor lands and provide extra copper toward
  the centre for a **0.30 mm hand-solder gap**. Pad 1 is at negative X; pad 2
  is at positive X. The old routed endpoints remain within the new copper.
- One filled, zero-stroke mask rectangle joins the pad openings across the
  gap. Paste is defined independently from copper/mask, so it never spans
  that gap as a continuous deposit.
- Courtyard: 2.06 × 1.50 mm. The footprint is defined on F and is flipped
  normally for the B-side bank; no opposite-side paste is added.

The local `R_0402_Link` symbol uses a resistor body while preserving the old
passive pin endpoints and the `JPL_*`/`JPR_*` reference scheme. All links are
DNP in the shared master. The extended copper and rectangular paste are a
deliberate hybrid: select the actual resistor, obtain assembler DFM feedback,
and prototype both resistor reflow and manual bridging before treating the
footprint as production-validated. No particular MPN, current rating, or
assembly yield is approved by the generic `0R` value.

## Bundled models

Models in `cad/components/` are unmodified. Exact source URLs and SHA-256 hashes
are pinned in [sources.json](../cad/components/sources.json). Local extensions
are normalized to `.step`; upstream URLs retain their original filenames.

| File | Source | Licence/notice |
|---|---|---|
| `SW_Hotswap_Kailh_Choc_V1.step` | perigoso/KiSwitch contributors | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KISWITCH.txt) |
| `SW_Kailh_Choc_V1.step` | perigoso/KiSwitch contributors | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KISWITCH.txt) |
| `D_SOD123.step` | KiCad Library Team | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KICAD.txt) |
| `R_0402_1005Metric.step` | kicad StepUp / KiCad Library Team | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KICAD.txt) |
| `Panasonic_EVQPUJ_EVQPUA.step` | KiCad Library Team | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KICAD.txt) |
| `SW_MSK12C02.step` | ebastler/marbastlib contributors | [CERN-OHL-P-2.0](../cad/components/LICENSE-MARBASTLIB.txt) |

The KiCad exception permits use of library data in PCB designs without forcing
the design to adopt the library licence; redistribution of the library sources
still requires their notices. The project licence does not relicense these assets.

## Model limitations

- The 0402 links use a bundled nominal KiCad resistor model with unit scale
  and zero local offset/rotation. KiCad flips it with the B-side footprint.
  All links remain DNP in the shared master: enable **SMD models** and
  **Models marked DNP** in the 3D Viewer's Appearance controls to inspect them.
  Left/right release previews show only that half's 22-link bank, including
  the optional display links, by changing DNP only on a temporary preview
  board. These previews are not factory assembly variants or proof of the
  exact selected resistor's dimensions.
- The viewer defaults to the **left assembly**. Right-assembly entries are hidden;
  show only the selected population, not both at once. Their transforms assume
  the 1.6 mm PCB; revisit offsets if thickness changes.
- The nice!nano candidate at ignored `cad/local-models/nice_nano_v2.step` is for
  **local inspection only**. Its [upstream repository](https://github.com/jusdisgi/KiCad_3D/blob/ccce873bb751949f668eac6013199e854c5d005f/nice_nano_v2.step)
  supplies no licence. A fresh clone will not include it; do not redistribute
  it in releases without permission. Its **6 mm board gap is provisional**, not
  a selected socket or proof of USB, battery or case clearance.
- Exact SMT PH connector, nice!view, socket-header, protected-battery, keycap and
  case coverage is incomplete. Missing geometry must not be treated as clearance.
- In particular, SW17's 26.5 × 16.5 mm cap and the relocated lower-corner H2
  require a physical screw-head/key-travel check. The photo-guided battery
  arrangement uses a 26 mm **overall lead-plus-plug** measurement; the exact
  plug engagement and protected-pack outline are not qualified by the current
  models. See the [layout notes](assembly.md#long-thumb-key-and-battery-bay-layout).
- The MSK12C02-HB model shows a mechanical candidate only. It does not approve
  another variant's actuator, terminal layout or electrical current rating.

Use the live PCB outline and component positions for mechanical design. Complete
both-assembly fit, insulation, access and RF checks in [assembly](assembly.md).
