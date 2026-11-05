# Assembly

REMAKE uses two identical, non-panelized PCBs for a 36-key keyboard: 18 keys per
half. Build one with the front face upward and the other with the back upward.

**Development hardware—not fabrication-approved or prototype-validated.**
Resolve the findings listed in the [project checks](../README.md#checks) and
approve the power-switch rating, battery and mechanical stack before ordering
or powering a board. A rendering is not proof of fit.

## Parts per half

| Quantity | Part |
|---:|---|
| 1 | REMAKE half PCB |
| 18 | Kailh Choc v1 switches and matching hotswap sockets |
| 18 | Keycaps, 17.5 × 16.5 mm outside envelopes |
| 18 | 1N4148W switching diodes, SOD-123 |
| 18, or 22 with a display | 0 Ω links, 0402 imperial / 1005 metric; manual solder bridges may be used instead |
| 1 | Genuine nice!nano v2 |
| 2 × 12 | Controller socket contacts and matching pins; height must be validated |
| 1 | Optional nice!view and matching five-pin socket/header |
| 1 | MSK12C02 slide switch; exact manufacturer/variant and rating need approval |
| 1 | Panasonic EVQPUJ02K side-actuated, momentary SPST-NO reset switch |
| 1 | JST S2B-PH-SM4-TB, two-pin side-entry SMT, 2.0 mm pitch |
| 1 | Protected 3.7 V, 110 mAh 301230 battery with PH 2.0 connector |
| As needed | Battery insulation and suitable case/plate retention |

**Do not approve a power switch by its family name or footprint alone.** Some
MSK12C02 variants are rated only 50 mA, below the nice!nano's nominal default
charging current through this path. Verify the exact part's maximum charge/load
current rating, common/throw numbering, terminal positions and actuator travel.

## Choose the assembly

**Left/right means the finished keyboard half. F/B means the KiCad PCB face.**
The nice!nano's component side faces the keyboard PCB in both assemblies; the
nice!view screen faces upward. USB points toward the stepped upper edge.

| Part or operation | Left half | Right half |
|---|---|---|
| Switches and controller sockets | F, upward | B, upward |
| Choc hotswap sockets | B, `L SOCKET` | F, `R SOCKET` |
| nice!view socket | F | B |
| Controller links | Fit 0 Ω resistors or bridge `JPL_U*` on B | Fit 0 Ω resistors or bridge `JPR_U*` on F |
| Optional display links | Fit 0 Ω resistors or bridge `JPL_D*` on B | Fit 0 Ω resistors or bridge `JPR_D*` on F |
| Battery connector | `JBAT_L1` on F | `JBAT_R1` on B |
| Power switch | `PWR1` F pads | `PWR1` B pads |
| Reset switch | `RST_L1` on F | `RST_R1` on B |
| Diodes | Prefer B, beneath keys | Prefer F, beneath keys |

**Never connect both banks: this shorts signals, including 3.3 V and ground.**
The shared schematic and PCB deliberately mark **all 44 selection links DNP**
(do not populate). This is the safe, unconfigured master, not the population
of a finished keyboard. Existing `JPL_*`/`JPR_*` references are retained for
the 0 Ω resistors so the left/right selection remains explicit.

For each PCB, fit the chosen bank's **18 controller links** and its **four
display links only if fitting a display**. That is **22 fitted / 22 DNP** with
a display, or **18 fitted / 26 DNP** without one. Leave every opposite-bank
link open. If omitting the display, leave both display banks open.

Each link accepts either a **0402 imperial (1005 metric, nominal 1.0 × 0.5 mm)
0 Ω resistor** or a hand-soldered bridge, not both. For manual assembly, bridge
the two pads **within that one pair**, not adjacent links or socket holes.
Pad 1 is the module-contact side; pad 2 is the board-signal side. The copper
gap remains 0.30 mm with a continuous mask opening for hand bridging; it must
not be closed with PCB routing.

For factory assembly, choose an exact 0402 jumper part and check its current
rating, reflow requirements, and suitability for the custom hybrid land pattern
described in [component sources](components.md#dual-use-0402-selection-links).
Only the selected bank may receive paste and parts. **DNP is not a stencil
mask:** the raw master paste Gerbers contain apertures for both banks. They
are not population-selected assembly stencils; prepare and inspect explicit
left/right, display/no-display assembly outputs before ordering PCBA. This
repository does not yet generate those production assembly variants.

Populate only **one** battery connector, power switch and reset switch per PCB.
`PWR1` has shared locating holes and needs no selection jumper. Fit one diode
per key on the chosen face, with its cathode stripe matching the pad-1 bar.

Choc contact patterns are asymmetric. Fit the switch from the upward face into
the selected socket; do not force pins into the unused hole pattern. The two
assemblies use opposite north/south switch patterns, so differing moulded
lettering orientation is intentional. Dry-fit a switch/socket on each face first.

## Battery and mechanical safety

- **Connector pin 1 = GND; pin 2 = BAT+.** Verify the actual pack with a meter
  before connecting it. A matching PH plug does not guarantee matching polarity.
  If reversed, do not plug it in or short contacts while correcting it.
- Check the pack's charge limits and protection circuit. Leave the nice!nano
  **charge-boost jumper open**; verify that its default charging current is safe
  for the selected pack before the first charge.
- The nominal pack is 3 × 12 × 30 mm. Allow for protection electronics, tape,
  wire exit, insulation and cable bends. Never compress or puncture the pouch.
- Insulate the battery from solder joints and pin ends. Select socket height
  only after checking the battery and face-down controller components. The
  model's **6 mm PCB-to-PCB gap is provisional**, not an approved header height.
- Keep access to USB, both side actuators and the connector housing. Do not
  pinch wires under modules or case parts. The longer-lead battery variant is
  preferred; do not assume shorter leads will reach.
- Preserve the antenna keepout on both copper faces. Verify wireless performance
  with the actual battery, display and case fitted.
- The PCB has **no dedicated mounting holes**. Component locating holes are not
  case-fastener positions. Design any case/plate against the live PCB outline.
- The minimum nominal thumb-to-row gap is **0.676 mm** for the specified keycap
  envelopes. Production variance, stem wobble, tilt and key travel need physical
  checks; this is not a worst-case tolerance guarantee.

The power switch disconnects battery positive, including charging through that
path. **It does not disconnect USB power.** For battery replacement, unplug USB
and switch off first; pull the connector housing, not the wires. Use a replacement
with verified polarity and charge limits, refit insulation and avoid pressure on
the pouch. Never solder with the battery connected.

## Assembly and first power

1. Keep USB and battery disconnected. Choose one column of the assembly table.
2. Fit the chosen-face diodes, sockets, power/reset and battery connector. Check
   diode polarity and dry-fit switch/socket orientation before completing all keys.
3. Solder only the selected jumper bank. Inspect every pair for accidental
   adjacent-pad bridges; leave the other bank open.
4. Install module sockets straight. Before fitting modules or battery, meter the
   selected contact-to-signal mappings and check for supply-to-ground shorts.
   Verify the power switch opens/closes BAT+ to BAT_SW and reset momentarily
   connects RESET to GND.
5. Verify pack polarity, insulation, socket height and cable/case access. Fit the
   controller and initially test with the battery disconnected; connect it only
   after these checks pass.
6. Test all 18 keys on each half, simultaneous presses, display, wireless, reset,
   power and charging. Check actual cap travel and both mechanical assemblies.
   Stop if the battery or electronics heat unexpectedly, swell or show damage.

## Firmware mapping

Firmware is maintained separately and has not been built or validated here.
Configure an 18-key-per-half, 4-row × 5-column matrix with `col2row` diodes:
switch column → diode anode/pad 2 → cathode/pad 1 → row.

| Signal | nice!nano / Pro Micro alias | nRF52840 GPIO |
|---|---|---|
| ROW0 | D6 | P1.00 |
| ROW1 | D7 | P0.11 |
| ROW2 | D8 | P1.04 |
| ROW3 | D9 | P1.06 |
| COL0 | D18 | P0.15 |
| COL1 | D15 | P1.13 |
| COL2 | D14 | P1.11 |
| COL3 | D16 | P0.10 |
| COL4 | D10 | P0.09 |
| nice!view MOSI | D2 | P0.17 |
| nice!view SCK | D3 | P0.20 |
| nice!view CS | D1 | P0.06 |

SW1–SW5 use row 0, SW6–SW10 row 1 and SW11–SW15 row 2, each with columns 0–4.
Thumb keys SW18/SW16/SW17 use row 3, columns 2/3/4. Row 3 columns 0/1 are unused.
The right assembly mirrors physical column order; verify its physical-key
transform instead of assuming the left-half layout applies unchanged.

Display module contacts are MOSI / SCK / 3.3 V / GND / CS; only the middle supply
contact is fixed directly. `U1` numbers identify physical socket contacts, not
the same module pins in both orientations; selection jumpers perform the remapping.

References: [nice!nano pinout](https://nicekeyboards.com/docs/nice-nano/pinout-schematic),
[nice!view pinout](https://nicekeyboards.com/docs/nice-view/pinout-schematic),
[target battery](https://typeractive.xyz/products/lithium-battery-110mah),
[component sources and model limitations](components.md).
