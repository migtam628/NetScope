# KiCad project

**Empty on purpose.** No schematic or PCB has been drawn.

A schematic produced without a datasheet-by-datasheet pin check and an ERC run would look like progress and be wrong in ways that cost a board spin, and KiCad is not available in the environment this repository was started in, so nothing here could have been checked.

What exists instead, and what the schematic must be drawn from:

- `../schematic/netscope-x1-main-board.pdf`: block schematic drawn from the netlist (function-named pins; a reading aid, not a substitute for capture).
- `../netlist/netscope-x1.yaml`: every component and net at block level, with electrical domains.
- `../../tools/check_netlist.py`: isolation, fail-safe and BOM-agreement rules. When the KiCad netlist exists, export it and port these rules to run against it in CI.
- `../bom/bom.csv`: parts, with honest part-number status.
- `../../docs/11-pcb-design-guide.md`: stackup, isolation, routing and test-point rules.

Conventions when starting: KiCad 9 or later; one hierarchical sheet per block in docs/02; project-local libraries committed to the repo; reference designators as in the netlist; net names as in the netlist.
