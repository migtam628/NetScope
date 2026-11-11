# 11 - PCB design guide (inputs for Phase 3-4)

> Updated 2026-11-11: the design is now two boards (88 x 88 mm six-layer main board, 88 x 56 mm two-layer keypad/USB-C board) joined by two flat-flex cables, and has a 10 Gb SFP+ port. Placement is in `hardware/pcb/`. The rules below apply to the main board. Additions: route the 10 Gb pair from the controller to the SFP+ cage as a short 100-ohm differential pair on one layer with no stubs, following the cage maker's footprint and the controller's layout guide; keep the 5 V flat-flex power conductors paralleled evenly and check voltage drop at 5 A.

No KiCad files exist yet. This is the rule set the schematic and layout must follow. Nothing here has been reviewed by a fabricator.

## Board

About 150 x 88 mm, 1.6 mm, 6 layers, FR-4 Tg 170, ENIG, controlled impedance, 0.1 mm track/space minimum, 0.2 mm drill minimum. Both sides populated; tall parts (RJ45, load resistors, SoM) on the back.

## Stackup (proposal; get the fab's own impedance table)

| Layer | Use | Cu |
|---|---|---|
| L1 | Signals, components (display side) | 1 oz |
| L2 | Solid ground | 1 oz |
| L3 | Signals (RGMII, slow) | 0.5 oz |
| L4 | Power planes: 5 V, 3V3, VSYS | 0.5 oz |
| L5 | Solid ground | 1 oz |
| L6 | Signals, components (back side) | 1 oz |

Targets: 100 ohm differential for Ethernet MDI; 90 ohm differential for USB 3 and USB 2; 100 ohm differential for DSI; 50 ohm single-ended for RGMII.

## Isolation barrier

- Draw the LINE / POE / SYS regions as keep-out zones in layout before placing anything. No copper on any layer crosses the gap except under T1, U20, PS1, the relay bodies and the bridging capacitor.
- **Creepage and clearance** between LINE/POE and SYS: design to at least 2.5 mm on outer layers and 0.4 mm of solid prepreg between layers until the safety-standard working-voltage calculation is done. (Typical PoE designs use 1500 Vrms isolation; the exact distances come from the chosen safety standard and pollution degree. This is a Phase 3 calculation to do with the test lab.)
- No ground plane under the transformer's line side or under the RJ45 line pins.
- Chassis / shield: RJ45 shells tie to a chassis island; island to SYS ground through 1 Mohm in parallel with 1 nF / 2 kV near the jacks.
- Slot the board under U20 and PS1 if creepage is tight.

## Port A front end

- Jack -> relays -> transformer in a straight line, pairs kept as 100 ohm differential pairs, length-matched within a pair to 0.15 mm, no stubs: the relay's unused contact is the only branch and it must be as short as the footprint allows.
- The TEST-side traces (relay NO contacts to PROT1) are LINE domain: keep them inside the LINE region; the protection network sits on the boundary.
- Bob Smith terminations per the transformer's datasheet; for PoE they need per-pair blocking capacitors rated 100 V or more.

## PoE island

- Bridge output, TVS, PD interface and shunt close together; wide copper (1.9 A).
- INA228 Kelvin connection to the shunt.
- Load resistors bolt to the aluminium spreader; thermal pad to the rear shell; NTC bonded to the spreader. Keep electrolytics and the battery away from this area.

## High-speed

- USB 3 (SoM to LAN7801): shortest route, no layer change if possible, AC coupling caps at the transmitter, continuous ground reference. Keep at least 15 mm from the antenna connector and feed; fit a shield-can footprint over the LAN7801. USB 3 radiates around 2.4 GHz.
- RGMII: length-match each direction to within 1 mm; the 2 ns clock skew is added in the PHY (set in device tree), not in copper.
- DSI: follow the SoM design guide; FFC connector at the board edge under the display.
- 25 MHz crystals: guard with ground, no routing underneath.

## Power

- TPS61088 boost: follow the datasheet layout exactly; this is a 10 A switch node. Input and output capacitors within millimetres. Keep the switch node away from the wiremap front end and the fuel-gauge sense lines.
- Battery connector and VSYS traces sized for 9 A.
- Star the analog ground of the wiremap front end to the coprocessor's analog ground.

## ESD and surge

- TVS arrays on the PHY side of the magnetics, close to the transformer.
- USB-C: ESD array at the connector; CC lines protected.
- Keypad lines: series resistors and capacitors at the MCU.
- Surge on LINE (lightning-induced, long outdoor runs) is **not** designed for: indoor use only. State this in the manual.

## Test and debug

- Test point on every rail, on both sides of every isolation part, on the UART between SoM and coprocessor, and on the relay drive.
- Tag-Connect for SWD; SoM `nRPIBOOT` jumper and a USB path for factory flashing; console UART header.
- Fiducials, tooling holes and a 2D barcode area for the serial number.

## Deliverables checklist for Phase 4 (none exist yet)

- [ ] KiCad project: schematic, PCB, project-local symbol/footprint libraries
- [ ] ERC and DRC reports with zero unexplained waivers
- [ ] Gerbers (X2), drill, IPC-356 netlist
- [ ] Pick-and-place, assembly drawings, BOM export that matches `hardware/bom/bom.csv`
- [ ] Fab notes with stackup and impedance table
- [ ] Isolation review signed off against the netlist domain rules
