# Changelog

## Unreleased

- Fixed `pip install -e firmware` (version source), which failed in the first CI run.
- Added `docs/15-dev-kit-spike.md` and a results template; corrected the spike budget from about $400 to $700-$900.
- Block schematics as PDF for the main board (10 sheets) and the bench kit (7 sheets), generated from the netlists by `tools/render_schematic.py`. Not KiCad, not ERC-checked.
- Coprocessor: command dispatcher with relay/voltage interlocks, host-tested and cross-checked against the Python protocol code.
- Tests for the Linux backend using canned tool output and a fake coprocessor (125 tests in total). It has still not run on a real network.
- BOM: isolated DC/DC and PoE magnetics moved from "tbd" to "candidate".

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
