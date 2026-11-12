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
- `tools/gridrouter.py`: the project's own two-layer grid router, used for the lower board. Low-speed boards only.
- Block netlist: status LEDs no longer take a +3V3 supply pin (they are driven to ground from the coprocessor), and D30 pin 5 is left open. Floorplan: real courtyard sizes for the two FFC connectors and for D30 (now SOT-666).
- RT-1 protection note corrected: the series resettable fuse preferred earlier cannot trip at the fault currents involved (12-57 mA) and is withdrawn. Rev A uses 2512 resistor footprints instead; surviving a passive injector is still open.

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
