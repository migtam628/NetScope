# 08 - Development plan

Status as of v0.1.0. "Exit" is the evidence needed to leave a phase.

| Phase | Scope | State | Exit criteria |
|---|---|---|---|
| 1 Feasibility and requirements | Capability matrix, limits, safety concept | **Done (this repo)** | Capability matrix reviewed and accepted by the product owner |
| 2 Processor and measurement hardware selection | SoM, PHY, PoE PD, wiremap method, battery | **Mostly done.** Open: bt magnetics, MagJack, isolated DC/DC, split-pair circuit | Every BOM line "known" or "candidate" with a datasheet check; dev-kit spike passed (below) |
| 3 Electrical architecture and schematics | KiCad schematic from the block netlist | Not started | ERC clean; `tools/check_netlist.py` rules re-expressed against the KiCad netlist; design review |
| 4 PCB layout and mechanical | 6-layer layout, enclosure detail | Enclosure concept only | DRC clean; impedance report from fab; printed enclosure fit-check with real display and jacks |
| 5 Firmware, UI, diagnostics | Engine, UI, coprocessor port, OS image | Engine + UI + simulator done; coprocessor port and OS image not started | All SIM rows have a HOST-IO path exercised on the dev kit |
| 6 Prototype fabrication and assembly | 5 boards | Not started | Boards assembled, visual + X-ray pass |
| 7 Bring-up and calibration | docs/09 | Not started | Every test in docs/09 has a recorded result |
| 8 Field validation and production prep | Pilot with technicians, compliance, fixture | Not started | 30 days of field use; compliance pre-scan passed; production test fixture built |

## Do this before any schematic: the dev-kit spike (1-2 weeks, about $400)

Most of the remaining technical risk can be retired on a bench with bought boards:

1. **CM5 dev kit + 5 inch Touch Display 2.** Run this repo's engine with `--hal linux` and the UI in a kiosk browser. Measure boot time, RAM and idle power. Retires the UI-stack and power questions.
2. **A LAN7801 evaluation board with a KSZ9131 PHY (confirm the current Microchip kit name and PHY fit before ordering) on the dev kit's USB 3.** Run `ethtool --cable-test` on real cables, a reel and against switches. Retires the TDR question and gives real accuracy numbers.
3. **TPS2372-4 evaluation module** against af / at / bt switches and a passive injector. Retires the PoE-identification approach.
4. **Breadboard wiremap**: two analog mux breakouts, an STM32 Nucleo and a hand-built RT-1. Run `firmware/coproc/wiremap.c` for real. Try to break it with a PoE switch on the far end.
5. **Relay insertion test**: a G6K-class relay in series with a gigabit link on a small adapter board; check link stability and error counters over 100 m.

If any of these fail, the architecture changes before money is spent on a board.

## Rough schedule after the spike

| Work | Duration | Notes |
|---|---|---|
| Schematic + review | 4-6 weeks | One experienced EE; the PoE island and front end are the careful parts |
| Layout + review | 4-6 weeks | USB 3, RGMII, gigabit MDI, isolation barrier |
| Fab + assembly | 3-4 weeks | Battery pack ordered in parallel (6-10 weeks) |
| Bring-up, rev B changes | 6-8 weeks | Assume one board respin |
| Coprocessor firmware + OS image | In parallel, 8-10 weeks | |
| Pilot + compliance | 8-12 weeks | |

Roughly 9-12 months to a pilot-ready rev B with one EE, one firmware engineer and part-time mechanical help. That is an estimate from typical projects of this shape, not a commitment.
