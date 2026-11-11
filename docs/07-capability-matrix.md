# 07 - Capability matrix

One row per capability in the product brief. Read the status column literally.

**Status key**

- **SIM**: engine logic implemented and unit-tested against the simulator or recorded tool output. No hardware involved.
- **HOST-IO**: additionally has a Linux I/O path written (sockets / `ethtool` / `iw` ...). That path has **not been run on NetScope hardware**; some of it can be exercised on any Linux PC.
- **DESIGN**: hardware approach chosen and captured in the block netlist; no schematic, no firmware port.
- **EXPERIMENTAL**: approach unproven; may not survive contact with real cable.
- **NOT STARTED** / **OUT OF SCOPE**: as it says.

Nothing in this table is hardware-verified, because no hardware has been built.

## Cable testing

| Capability | Hardware required | Status | Validation method | Limitations |
|---|---|---|---|---|
| Wiremap, 8 conductors | Wiremap front end, relays, RT-1 | SIM + DESIGN | CBL-01: fault box, every fault x 3 lengths | Needs RT-1 for pin order |
| Open detection | Same + PHY TDR | SIM + DESIGN | CBL-02 | Per pair, not per conductor |
| Short detection | Same | SIM + DESIGN | CBL-03 | Works without RT-1 |
| Crossed / reversed / miswire | Same + RT-1 | SIM + DESIGN | CBL-04 | Needs RT-1 |
| Split pair | Coupling front end (U33) | EXPERIMENTAL | CBL-05: made-up split cables, 3 lengths | Threshold provisional; circuit not detailed |
| Length estimate | KSZ9131 TDR | SIM + HOST-IO | CBL-06: measured reel, 5 lengths | About a metre error; NVP dependent; needs open or RT-1 far end |
| Distance to fault | KSZ9131 TDR | SIM + HOST-IO | CBL-07 | Same; blind zone on short cables |
| Cable ID via remote | RT-1 ID resistor | SIM + DESIGN | CBL-08: all 8 IDs at 1 m and 90 m | 8 IDs |
| Cat5e/6/6A troubleshooting | All of the above | as above | as above | Finds wiring faults only. Does not grade or certify category |
| Certification | Swept-frequency analyser | OUT OF SCOPE | - | Never claimed; enforced in firmware text and tests |

## PoE

| Capability | Hardware required | Status | Validation method | Limitations |
|---|---|---|---|---|
| 802.3af / at detection and class | TPS2372-4 island | SIM + DESIGN | POE-01: af, at switches and injectors from 3 vendors | Indicator-pin decode not written |
| 802.3bt Type 3 / 4 | Same, bt-rated magnetics | SIM + DESIGN | POE-02: bt switch, class 5-8 | Magnetics not yet selected |
| Delivered voltage | INA228 | SIM + DESIGN | POE-03 vs calibrated DMM | - |
| Power available | Class tables | SIM | Unit tests vs. standard values | Reports allocation, not PSE headroom |
| Power under test load | Resistor bank | SIM + DESIGN | POE-04 vs electronic load reference | 2 s pulses; stepped, not continuous |
| Negotiation failures | INA228 + PD indicators | SIM + DESIGN | POE-05: budget-limited switch | LLDP power request not sent |
| Fault conditions | Centre-tap ADC, TVS | SIM + DESIGN | POE-06 | - |
| Passive / non-standard injector protection | Bridges, TVS, isolation | SIM + DESIGN | SAFE-01..04, including destructive tests | Fuse rating open (R-06) |

## Network tools

| Capability | Hardware required | Status | Validation method | Limitations |
|---|---|---|---|---|
| DHCP discovery / lease inspection | Any Ethernet | SIM + HOST-IO | NET-01 vs packet capture | Probe does not take the lease; OS client configures the port |
| Static IP | Any Ethernet | SIM + HOST-IO | NET-02 | DNS not written to resolver yet |
| Ping / loss | Any | SIM + HOST-IO | NET-03 | - |
| Traceroute | Any | SIM + HOST-IO | NET-04 | - |
| DNS lookup | Any | SIM + HOST-IO | NET-05 | A records; UDP only |
| Gateway discovery | Any | SIM + HOST-IO | NET-06 | - |
| ARP inspection | Any | SIM + HOST-IO | NET-07 | Passive table only; no active sweep (would be disruptive) |
| VLAN identification | Any + managed switch | SIM + HOST-IO | NET-08 | From LLDP/CDP only; no tagged-frame detection yet |
| LLDP / CDP neighbour | Any + managed switch | SIM + HOST-IO | NET-08 | - |
| Link speed / duplex | PHY | SIM + HOST-IO | NET-09: forced-mode switch ports | - |
| Internet check | Any | SIM + HOST-IO | NET-10 | - |
| HTTP/HTTPS + captive portal | Any | SIM + HOST-IO | NET-11 | - |
| Throughput | iperf3 endpoint | SIM + HOST-IO | NET-12 vs known-good NIC | Needs a server; test port is USB 3 bridged (R-04) |
| Packet capture | tcpdump | SIM + HOST-IO | NET-13 | No on-device viewer; pcap export only |

## Fiber (added 2026-11-11)

| Capability | Status | Validation | Limits |
|---|---|---|---|
| 10 Gb SFP+ link | DESIGN (in netlist, BOM, floorplan, housing) | Link against 10G-SR and 10G-LR switch ports | Throughput capped by the single PCIe lane at about 3.5-6 Gb/s; cannot prove a full 10 Gb circuit |
| 1 Gb SFP modules | LIKELY, UNPROVEN | Spike step 6 | The chip maker's own adapter built on this controller lists a 1 Gb module as supported; not shown at chip level or on this platform |
| Optical power, wavelength, module identity (from the module's own diagnostics) | SIM + HOST-IO (EEPROM parser unit-tested; I2C read path never run) | Compare with an optical power meter | Only modules that report diagnostics; accuracy is the module's, typically +/-3 dB |
| Fiber test in the engine and UI | SIM, 5 scenarios | Dirty connector, swapped fibers, speed mismatch against real switches | Diagnoses from light level and link only; no loss measurement, no fault distance |

## Wi-Fi

See docs/05 for the full supported / needs-other-hardware split.

| Capability | Status | Limitations |
|---|---|---|
| SSID, RSSI, channel, security | SIM + HOST-IO | 2.4 / 5 GHz only |
| Channel utilisation | SIM + HOST-IO | AP-advertised value only |
| Connected AP info | SIM + HOST-IO | - |
| Roaming diagnostics | SIM (rule only) | Event listener not written |
| Signal history | NOT STARTED | - |
| Wireless throughput | NOT STARTED (tool exists, no interface selection) | - |
| Channel graphs | SIM (UI) | - |
| Interference / spectrum, 6 GHz, monitor mode | OUT OF SCOPE for rev A | Needs other radio hardware |

## UI, automation, assistant, reports

| Capability | Status | Validation | Limitations |
|---|---|---|---|
| Dashboard with the seven sections | SIM (runs in desktop simulator, exercised in headless Chrome) | UI-01 on device | Not yet run on the real panel |
| PASS / FAIL / WARNING / NOT TESTED everywhere | SIM | Unit tests | - |
| Graphical wiremap, channel graph | SIM | UI-02 | Connection diagrams beyond wiremap not drawn |
| Glove use | DESIGN | UI-03 with gloves on hardware | Capacitive touch is poor in thick gloves: every function is reachable from the keypad, which is the real answer |
| Auto Diagnose (9 steps) | SIM, 17 scenarios | AUTO-01..03 in the field | - |
| Local rules assistant | SIM | Scenario tests | Rule base is small (about a dozen diagnoses) |
| Completion notes | SIM | - | Plain text |
| Cloud AI (optional) | Request builder + redaction tested | AI-01 against a live endpoint | HTTP call never exercised; needs owner's key |
| Step-by-step repair guidance | Partial (recommendation lists) | - | No guided, interactive procedures |
| Reports: JSON / CSV / PDF | SIM (generated and parsed in tests) | RPT-01 | - |
| USB transfer | NOT STARTED | RPT-02 | Needs USB gadget (mass-storage or MTP) setup |
| Secure wireless sync | NOT STARTED | RPT-03 | Design only (docs/13) |

## Power, PCB, mechanical, manufacturing

| Capability | Status | Limitations |
|---|---|---|
| USB-C charging, power path | DESIGN | 5 V input (up to ~3 A with BC1.2); no USB PD negotiation |
| Battery level / health | SIM + DESIGN | Gauge driver not written |
| Auto sleep, standby, safe shutdown | DESIGN | Standby = SoM off; needs coprocessor firmware |
| Thermal monitoring | DESIGN | - |
| Replaceable battery | DESIGN (door in CAD) | Pack is custom |
| 8 h runtime | ESTIMATE (docs/06): about 10 h typical on 1S3P | Unmeasured |
| Schematic (KiCad) | NOT STARTED | Block netlist + rules exist |
| PCB layout, Gerbers, drill, pick-and-place, ERC/DRC reports | NOT STARTED | Depends on schematic |
| Stackup, layout rules, EMC plan | Written (docs/11) | Not reviewed by a fab |
| Enclosure CAD: STEP / STL / 3MF, drawings | Concept geometry, passes solid and interference checks | No draft, seals, snaps; display dimensions TBC |
| Realistic renders | NOT DONE | Line drawings only |
| BOM with MPNs, alternates, risks | Draft: 19 known, 11 candidate, 16 TBD part numbers | Prices are estimates |
| Cost at 1 / 10 / 100 / 1,000 | Estimate (docs/14) | Not quoted |
| Firmware build / flash / OTA | Documented design (docs/13); image not built | - |
| CI, automated tests, releases | Workflows written; every command they run passes locally. Not yet run on GitHub | No hardware-in-loop |
| Desktop simulator | Working | - |
