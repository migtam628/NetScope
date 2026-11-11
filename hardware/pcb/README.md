# Board floorplan

`floorplan.yaml` places every part of the netlist on two boards. `tools/render_floorplan.py` checks it and draws `floorplan.pdf`; `mechanical/enclosure.py` builds the same placement in 3D inside the housing and checks for clashes.

**This is a floorplan, not a PCB layout.** Nothing is routed, there are no Gerbers, and no board can be ordered from it. It answers one question: do all the parts physically fit, on which side, with the isolation spacing and the height available.

## Result

| Board | Size | Layers | Carries |
|---|---|---|---|
| Main | 88 x 88 mm + 6 x 15 mm card tab | 6 | Processor module, both Ethernet ports, relays, PoE island, wiremap front end, coprocessor, charger, 5 V boost, M.2, microSD |
| Keypad and USB-C | 88 x 56 mm | 2 | Eight keys + power key, four LEDs, buzzer, USB-C |

Total 127.6 cm2, against 174 cm2 for a single board long enough to reach both the RJ45 jacks and the USB-C port. No feature was removed. The two boards join with a 30-way signal cable and a 20-way power cable (flat flex); nine nets cross (`floorplan_report.md`).

The earlier single 88 x 150 mm outline in the CAD could not have worked: it stopped short of the keys and the USB-C port.

Why it will not go much smaller: the main board's back is 40 % covered by part bodies before any passive or trace, and the processor module, M.2 card, two jacks and PoE load resistors are fixed-size blocks.

## What the checks cover

Inside the outline; no overlaps on a side; through-hole parts block both sides; height limits (1.5 mm on the main board's front, which faces the display 2 mm away; 1 mm on the lower board's back, which faces the battery cells); 2.5 mm between cable-side, PoE-side and system-side parts unless the part is a declared isolation barrier; mounting-hole keep-outs; every netlist part placed. The 3D model then checks boards against shells, display and cells.

## What is approximate or open

- **Part envelopes are package-class sizes**, not the selected parts' land patterns. 14 parts have no part number yet.
- **Small passives are not placed.** Several hundred capacitors and resistors have to fit in the remaining area.
- **microSD slot is a concept.** The socket now sits on a 6 x 15 mm tab at the main board's right edge, in line with a slot through the side wall and a window in the bumper, so a card can be changed without opening the case. Card protrusion, the latch travel of the chosen socket and a dust plug are not worked out, and the slot leaves a thin section at the shell split line.
- **Power key** is now a ninth front key in a smaller recessed opening. Accidental-press protection (long press in firmware) is assumed.
- **PoE load resistors stand upright** against a metal fin to fit; the thermal path to the rear shell is not designed or tested.
- **Display cable position is assumed.** The display's connector location was not taken from its mechanical drawing.
- **Front-side parts must be 1.5 mm or lower.** The bridge diodes and a few ICs need low-profile package variants; confirm when parts are selected.
- **Flat-flex for 5 V power**: 10 conductors each way at 0.5 A is 5 A on paper; check connector ratings and voltage drop.

## Next step toward a real board

Schematic capture in KiCad with real symbols (`hardware/kicad/README.md`), then layout starting from this placement. Do the dev-kit spike first (`docs/15`).
