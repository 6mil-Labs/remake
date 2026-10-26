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

The JST copy is renamed, hides reference/value fields and omits the unresolved
3D link; lands are unchanged. The reset copy is renamed and moves clipping silk
strokes to fabrication; copper, pin numbering and courtyard are unchanged.
Reset is side-actuated, momentary SPST-NO, without locating bosses.

Sources: [KiCad footprints](https://gitlab.com/kicad/libraries/kicad-footprints),
[JST PH drawing](https://www.jst-mfg.com/product/pdf/eng/ePH.pdf),
[Panasonic EVQPUJ02K](https://industry.panasonic.com/global/en/products/control/switch/light-touch/number/evqpuj02k).

## Bundled models

Models in `cad/components/` are unmodified. Exact source URLs and SHA-256 hashes
are pinned in [sources.json](../cad/components/sources.json). Local extensions
are normalized to `.step`; upstream URLs retain their original filenames.

| File | Source | Licence/notice |
|---|---|---|
| `SW_Hotswap_Kailh_Choc_V1.step` | perigoso/KiSwitch contributors | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KISWITCH.txt) |
| `SW_Kailh_Choc_V1.step` | perigoso/KiSwitch contributors | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KISWITCH.txt) |
| `D_SOD123.step` | KiCad Library Team | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KICAD.txt) |
| `Panasonic_EVQPUJ_EVQPUA.step` | KiCad Library Team | [CC-BY-SA-4.0 + KiCad exception](../cad/components/LICENSE-KICAD.txt) |
| `SW_MSK12C02.step` | ebastler/marbastlib contributors | [CERN-OHL-P-2.0](../cad/components/LICENSE-MARBASTLIB.txt) |

The KiCad exception permits use of library data in PCB designs without forcing
the design to adopt the library licence; redistribution of the library sources
still requires their notices. The project licence does not relicense these assets.

## Model limitations

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
- The MSK12C02-HB model shows a mechanical candidate only. It does not approve
  another variant's actuator, terminal layout or electrical current rating.

Use the live PCB outline and component positions for mechanical design. Complete
both-assembly fit, insulation, access and RF checks in [assembly](assembly.md).
