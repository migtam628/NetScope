# Changelog

## Unreleased

- Fixed `pip install -e firmware` (version source), which failed in the first CI run.
- Added `docs/15-dev-kit-spike.md` and a results template; corrected the spike budget from about $400 to $700-$900.
- Board floorplan: two boards (88 x 88 mm main, 88 x 56 mm keypad/USB-C) with every netlist part placed and checked for fit, height and isolation spacing. Not a routed layout.
- Added a 10 Gb SFP+ fiber port (AQC100 + cage) in place of the optional M.2 slot; main board re-planned with all three ports and the microSD slot on the top end. No fiber software yet.
- Licences added: PolyForm Noncommercial 1.0.0 for software, CC BY-NC-SA 4.0 for documents and design files.
- Spike plan: step 6 and kit items for the 10 Gb fiber controller. BOM: controller price checked ($25, trays of 210, out of stock).
- Length Calibration tool and a length scale for Cable Test (cable types differ in signal speed).
- BOM now includes the second board and the board-to-board cables; Realtek RTL8127ATF recorded as the fallback 10 Gb controller.
- Fiber test tool: SFP module identity, received light against the module's own thresholds, link; four simulator scenarios; SFF-8472 EEPROM parser. Untested on hardware.
- microSD moved to a board tab with a slot in the side wall; power key given a recessed front opening.
- Housing model now includes both boards, standoffs, relocated LED openings and buzzer vents; board-vs-shell-vs-battery clash checks; shaded review images.
- Block schematics as PDF for the main board (10 sheets) and the bench kit (7 sheets), generated from the netlists by `tools/render_schematic.py`. Not KiCad, not ERC-checked.
- Coprocessor: command dispatcher with relay/voltage interlocks, host-tested and cross-checked against the Python protocol code.
- Tests for the Linux backend using canned tool output and a fake coprocessor (125 tests in total). It has still not run on a real network.
- BOM: isolated DC/DC and PoE magnetics moved from "tbd" to "candidate".
- KiCad 9 project for the main board, generated from the block netlist (`tools/gen_kicad.py`): seven hierarchical sheets of block symbols, domain net classes, a 2.5 mm cross-domain clearance rule, and a board file with the outline, mounting holes and placement guides. Checked with KiCad 9.0.9 by `tools/check_kicad.py` (ERC clean, exported netlist identical to the YAML netlist, isolation rules proven to fire). Block level only: function-named pins, no footprints, no layout.
- RT-1 remote terminator rev A: real KiCad capture and a routed two-layer board (17.8 x 39.8 mm), generated from the firmware's terminator definition (`tools/gen_rt1.py`, `tools/layout_rt1.py`) and checked by `tools/check_rt1.py` (ERC, netlist against the firmware, DRC with schematic parity). Gerbers, drill, BOM and placement files in `hardware/remote-terminator/fab-rev-a/`. Not fabricated.
- Lower (keypad and USB-C) board rev A: real KiCad capture and a routed two-layer board, 88 x 56 mm, 49 parts (`tools/gen_lower.py`, `tools/layout_lower.py`, `tools/check_lower.py`). Defines the J50 / J51 cable pin assignments. Gerbers, BOM and placement in `hardware/kicad/netscope-x1-lower/fab-rev-a/`. Not fabricated; USB 2.0 pair impedance is not controlled on this stack.
- Main board, coprocessor sheet captured for real (`tools/main_sheets.py`): STM32G0B1CBU6, support parts, SWD pads, cable connectors; pin plan in `hardware/kicad/coprocessor-pins.md`. The main-board project now mixes real and block sheets, and `tools/check_kicad.py` checks that a real sheet still implements the block netlist. Real footprints of that sheet are on the board file; nothing is routed.
- Main board, processor sheet captured for real: Compute Module 5 as a 200-pin symbol from the data sheet's pin table, display cable connector, display 5 V lead, debug pads. The fiber port and the microSD reader moved to their own block sheets. The checker verifies planned module connections pin by pin and the polarity of 15 differential pairs. Open: module footprint, display lead footprint, three assignments written from memory.
- Main board, power sheet captured for real: BQ25895, MAX17055, TPS61088, TPS62840, TLV62569 and 44 support parts. Three parts without a KiCad library symbol are drawn from their data sheets' pin tables. Not buildable yet: boost compensation values and two footprints (fuel gauge, battery connection) are open, and the checker tracks exactly those. Sense resistor 5 mOhm; fuel gauge on its own thermistor.
- Design changes found during that capture: coprocessor package LQFP-48 to UFQFPN-48 (height); SFP status and transmit-disable lines moved to the SoM (pin count); main-board cable connectors moved to the back (height); debug header split into SWD pads (J40) and SoM test pads (J41). Open: the signal cable between the boards needs a 22.5 mm sideways jog.
- `tools/gridrouter.py`: the project's own two-layer grid router, used for the lower board. Low-speed boards only.
- Block netlist: status LEDs no longer take a +3V3 supply pin (they are driven to ground from the coprocessor), and D30 pin 5 is left open. Floorplan: real courtyard sizes for the two FFC connectors and for D30 (now SOT-666).
- RT-1 protection note corrected: the series resettable fuse preferred earlier cannot trip at the fault currents involved (12-57 mA) and is withdrawn. Rev A uses 2512 resistor footprints instead; surviving a passive injector is still open.
- Main board, test-port Ethernet sheet captured for real: LAN7801 and KSZ9131RNX (pins from the data sheets), support parts per Microchip's LAN7801 checklist, PHY straps, 1.2 V buck for the PHY core, two crystals, two TVS arrays, uplink MagJack (UDE RB1-125B8G1A). 97 parts. Open: two IC exposed-pad sizes and the jack's LED polarity to confirm from drawings; RGMII series resistors and PHY decoupling are starting values.
- Design changes found during that capture: uplink jack shield and termination return moved from the floating CHASSIS net to system ground (the jack's pin layout requires it; only the test port floats); Pulse JK0654219NL rejected (33 mm deep); J11 and U54 moved on the floorplan; D10 split into D10/D11; new block net LAN_NRST (module GPIO6 resets the USB Ethernet bridge).
- Processor sheet: two items closed from the CM5 data sheet. RTC input range 2.5-3.5 V (the always-on 3.3 V is fine); GPIO2/3 have 1.8 k pull-ups on the module, so R81/R82 were removed.
- `tools/check_kicad.py` tracks a third kind of open item: footprints that exist but must be confirmed against the maker's drawing.
- Main board, microSD reader sheet captured for real (option, all 20 parts marked DNP, footprints on the board): USB2244, 24 MHz crystal, Hirose DM3AT-SF-PEJM5 push-push socket, support parts per Microchip's USB2244 checklist. Block netlist correction: U60 is supplied from +3V3, not +5V. The data sheet's pin diagram and pin tables disagree on pins 23-26 (tables used; listed to confirm). Board tab for the socket widened from 15 to 17 mm.
- Power sheet: boost loop compensation chosen (R68 6.19 k, C76 10 nF) with `tools/boost_loop.py`, a peak-current-mode model using the data sheet's GEA and sense resistance; at least 57 degrees of phase margin over battery voltage, load and output capacitance. Calculated, not measured. No values are left open on the captured sheets.

## 0.1.0 - 2026-11-11

First repository baseline. Pre-hardware.

- Diagnostic engine with 16 tools and a 17-scenario simulator, Auto Diagnose (9 steps), offline rules assistant, optional cloud AI hook (off by default, redacting).
- Touch UI (720x1280) served by a local HTTP API; report store with JSON, CSV and PDF export.
- Coprocessor C core: framing and wiremap scan sequencing with the voltage safety gate, host-tested.
- Hardware: architecture, block netlist with isolation/fail-safe checks, BOM and cost roll-up, power budget.
- Mechanical: parametric enclosure concept with STEP/STL/3MF and drawings.
- Documentation 01-14, CI and release workflows.

### Note on the HAL layer

`netscope/__init__.py`, `__main__.py`, `models.py`, `hal/base.py`, `hal/sim.py`, `hal/linux.py` and `hal/coproc.py` were rewritten on 2026-11-11 after the first versions were overwritten by mistake before any commit existed. The rewrite was made to the interfaces the engine, API, UI and tests already used; the full test suite (107 tests) and the C host tests pass, and simulator output was matched against earlier screenshots. Details not covered by tests may differ from the first versions. `hal/linux.py` in particular is unexercised.
