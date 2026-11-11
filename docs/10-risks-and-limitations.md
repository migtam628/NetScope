# 10 - Risks, limitations and open conflicts

## Design conflicts found and how they were resolved

| Conflict | Resolution |
|---|---|
| "Two RJ45 ports" vs "PHY with cable diagnostics": the SoM's built-in PHY cannot do TDR under Linux and cannot be replaced | Port A (test) gets its own MAC + PHY chosen for cable test; the SoM's port becomes Port B (uplink) |
| Wiremap needs a direct DC connection to the cable; PoE safety needs isolation | Relays: default position is isolated; direct connection only during a scan on a cable already measured as unpowered, behind a protection network |
| PHY magnetics short each pair at DC, which would blind the wiremap | The same relays disconnect the magnetics during a scan (this is why solid-state taps are not enough) |
| 802.3bt load test (71 W) vs a handheld's thermal limits | 2-second pulsed tests with a duty-cycle limit and a hardware cut-off; continuous load limited to a few watts |
| 8 h runtime vs a Linux SoM | Three-cell pack instead of two; CPU capped on battery. Estimated about 10 h typical, unmeasured |
| "Removable microSD" vs eMMC SoM (the SD interface is used by eMMC) | Optional USB card-reader chip on the spare USB port; not populated on rev A |
| Glove operation vs capacitive touch | Full keypad navigation; touch is a convenience |
| "Certification" language in the market vs what this hardware measures | Verifier only; stated on every result |
| Suspend / low-power standby vs CM5 | Standby is SoM-off with the coprocessor alive; resume is a cold boot |

## Risk register

| ID | Risk | Likelihood | Impact | Mitigation / next step |
|---|---|---|---|---|
| R-01 | CM5 single source; price rose in 2026 | Medium | High | Engine is hardware-agnostic above the HAL; keep an i.MX 8M Plus / AM62 SoM as plan B |
| R-02 | Protection network does not survive a hot-plugged passive injector during a scan | Medium | High | SAFE-03 on the first boards; breadboard it during the spike |
| R-03 | Relays in the MDI path degrade gigabit return loss | Medium | High | Spike item 5; fallback is RF-grade relays or accepting 100 Mb/s on the test port with gigabit on Port B |
| R-04 | USB 3 bridged MAC does not sustain full gigabit both ways | Medium | Medium | Measure in the spike; document the ceiling; throughput on Port B is native |
| R-05 | 1S pack + boost cannot hold 5 V at SoM peak current at low state of charge | Medium | Medium | CPU cap on battery; fallback is a 2S pack with a buck-boost charger (BQ25798 class) |
| R-06 | Fuse / PTC coordination with the PoE TVS for over-voltage sources | Medium | Medium | Phase 3 calculation + SAFE-04 |
| R-07 | Split-pair detection does not separate cleanly | High | Low | Ships disabled unless CBL-05 passes |
| R-08 | USB 3 noise desensitises 2.4 GHz Wi-Fi | Medium | Medium | Layout rules (docs/11); shield can over the MAC; measure scan sensitivity |
| R-09 | Display end of life (maker states Jan 2030) | Certain, later | Medium | Second-source 5 inch DSI panel and driver before volume |
| R-10 | bt-rated magnetics with all four centre taps accessible are a narrow market | Medium | Medium | Select and sample in Phase 2 |
| R-11 | TDR accuracy disappoints users who expect centimetres | Medium | Low | Publish measured accuracy; NVP calibration |
| R-12 | PSE detection pulses corrupt wiremap readings | Medium | Medium | Quiet-gap measurement (implemented, host-tested); CBL-09 |
| R-13 | Python engine + browser too slow to boot | Low | Medium | Measure in the spike; LVGL client is the fallback |
| R-14 | Regulatory scope underestimated | Medium | High | See below; talk to a test lab before layout |

## Regulatory and shipping (not legal advice; confirm with a test lab)

- **EMC**: the product is an unintentional radiator and contains a certified radio module. Expect FCC Part 15 Subpart B testing for the product, and conditions on using the module's grant (antenna type, host labelling). Adding a second radio or a different antenna reopens intentional-radiator testing.
- **Safety**: the product connects to 57 V network power and contains a lithium pack. A safety standard evaluation (IEC/UL 62368-1 class) is normally expected by commercial customers even where not legally mandated.
- **Battery**: lithium packs need a UN 38.3 test report to ship by air; the pack vendor should supply it for the exact pack.
- **Network use**: packet capture and active tests on networks you do not own need the owner's permission. The UI gates them; policy is still the technician's responsibility.

## Honest summary of what exists

Software that runs and is tested without hardware; a hardware design at block level with its safety rules machine-checked; a concept enclosure; estimates. No schematic, no board, no measured data.
