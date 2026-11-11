# 01 - Requirements and feasibility

This maps each section of the product brief to a feasibility verdict and to the document that holds the detail. Verdicts are engineering judgement before any hardware exists; `docs/07-capability-matrix.md` tracks the status of each individual capability.

| Brief section | Verdict | Main constraint or conflict | Detail |
|---|---|---|---|
| 1 Hardware platform | Feasible | An MCU alone (STM32, ESP32-S3) cannot run the network stack, UI and gigabit/5 GHz diagnostics; a Linux SoM cannot be trusted with safety and power sequencing. Resolved with a SoM plus a coprocessor | 02 |
| 2 Cable testing | Feasible as verification; certification is out of scope | Wiremap needs a direct DC path to the cable, PoE safety needs isolation. Resolved with relays that rest in the isolated position and a voltage gate before any scan. Split-pair detection is experimental | 03 |
| 3 PoE diagnostics | Feasible for af/at; bt Type 4 feasible with short load pulses | A handheld cannot dissipate 71 W continuously. Load tests are stepped pulses with thermal limits | 04 |
| 4 Network tools | Feasible | All standard Linux capabilities; throughput needs an iperf3 endpoint | 13 |
| 5 Wi-Fi analysis | Feasible for scan-based survey | A client radio cannot measure non-Wi-Fi interference or true airtime; utilisation is what APs advertise | 05 |
| 6 UI | Feasible | Glove use: large targets plus a keypad that reaches every function | 13 |
| 7 Auto Diagnose | Done in simulation | Disruptive tests are excluded unless the technician authorises them | 13 |
| 8 AI assistant | Local rules done; cloud optional | Reports contain site data: redaction by default, ask before sending | 13 |
| 9 Reports | Done in simulation | - | 13 |
| 10 Battery | Feasible with a three-cell pack | Two cells give about 6.7 h typical; three give about 10 h. No reliable suspend on the SoM, so standby is power-off with a fast boot | 06 |
| 11 PCB | Not started, by decision | Block netlist and design rules exist; schematic waits for the dev-kit spike | 11, hardware/kicad |
| 12 Enclosure | Concept only | Depth margin at the battery is too tight for a real pack | 12 |
| 13 Sourcing and cost | Estimated | 16 of 46 parts still "tbd"; prices unverified | 14 |
| 14 Firmware | Engine, UI, simulator done; coprocessor port and OS image not started | - | 13 |
| 15 Verification | Planned | Nothing can be verified before boards exist | 08, 09 |

## Requirements that were narrowed

- "Cable certification": not offered. The brief asks for this distinction and the UI, reports and documents carry it.
- "Channel utilisation": reported only where access points advertise it.
- "Eight hours": applies to the typical-use profile, by calculation, until measured.
- "Production-ready": not claimed for anything in this repository.

Risks and open questions are in `docs/10-risks-and-limitations.md`.
