# 09 - Verification plan

No test here has been run. This is the list of evidence required before any capability's status may be changed to "hardware-verified". Record results in `docs/results/<test-id>.md` with date, board serial, firmware version, equipment used and raw data.

## Equipment

Bench supply and electronic load; calibrated DMM; oscilloscope (>= 200 MHz) with differential probe; USB power meter; thermocouple logger; PoE switches: one af, one at, one bt (Type 4), from at least three vendors in total; one passive 24 V and one passive 48 V injector; managed switch with LLDP and CDP and forced speed/duplex; cable fault box (below); measured reel of Cat5e and Cat6; iperf3 server with a known-good gigabit NIC; hi-pot tester (or test lab); thermal camera.

**Cable fault box**: for each of 1 m, 30 m, 90 m: good; each pin open (8); shorts 1-2, 3-6, 1-3, 4-7; each pair reversed (4); 12/36 crossed; 45/78 crossed; 1<->3 miswire; split 3-6/4-5; 10/100 crossover; gigabit crossover.

## Bring-up (first power)

| ID | Test | Pass |
|---|---|---|
| BU-01 | Visual, X-ray of QFN/BGA, rail-to-ground resistance before power | No shorts |
| BU-02 | Rails from bench supply at current limit, SoM not fitted | All rails in tolerance; sequencing matches design |
| BU-03 | Coprocessor flash over SWD, responds to PING over UART | Frame round-trip |
| BU-04 | SoM boots to console; display shows UI | - |
| BU-05 | Test port enumerates (lan78xx), PHY detected, link at 10/100/1000 | - |
| BU-06 | Battery charge / discharge cycle, gauge tracks within 3 % of a coulomb count | - |

## Safety (do these before anyone plugs it into a live network)

| ID | Test | Pass |
|---|---|---|
| SAFE-01 | Hi-pot LINE to SYS: 1500 Vrms 60 s (relays in LINK) | No breakdown; leakage within limit |
| SAFE-02 | 57 V passive, both polarities, both pair sets, 1 h | No damage; voltage reported; wiremap refused |
| SAFE-03 | **Destructive**: apply 57 V passive during a wiremap scan (relays in TEST), 20 times | Scan aborts; relays drop; front end survives; no SYS rail disturbed > 100 mV |
| SAFE-04 | 60 V and 72 V overvoltage on the PoE input | TVS/fuse act; no damage beyond the fuse |
| SAFE-05 | Load bank: firmware hang during a 71 W load (halt the coprocessor with a debugger) | Hardware cut-off opens the load before spreader exceeds 85 C |
| SAFE-06 | Battery: short circuit, over-charge attempt, charge at 0 C and 50 C | Pack PCM and charger limits act |
| SAFE-07 | ESD contact +/-4 kV, air +/-8 kV on ports, keys and seams | No latch-up or reset that needs a power cycle |

## Cable (CBL)

| ID | Test | Pass |
|---|---|---|
| CBL-01..04 | Every fault-box cable, 5 repeats each | 100 % correct classification; zero false PASS |
| CBL-05 | Split-pair cables vs good cables at 3 lengths | Separation of coupling readings large enough to set a threshold with zero overlap; otherwise the feature ships disabled |
| CBL-06 | Length on the reel at 5, 15, 30, 60, 90 m, Cat5e and Cat6 | Record error; publish the measured accuracy, whatever it is |
| CBL-07 | Fault distance: opens and shorts made at measured points | Same |
| CBL-08 | All 8 RT-1 IDs at 1 m and 90 m, at 0 C and 40 C | Correct ID every time |
| CBL-09 | Wiremap with each PoE switch probing the far end | Correct "equipment" result or clean "busy"; never a false fault |
| CBL-10 | Gigabit link through the relays, 100 m, 12 h | Zero CRC errors; no downshift |

## PoE (POE)

| ID | Test | Pass |
|---|---|---|
| POE-01 | Each af / at source: reported standard, class, voltage | Matches the source's own report |
| POE-02 | bt switch, classes 5-8 | Same |
| POE-03 | Voltage and current vs DMM across 37-57 V, 0-1.5 A | Within 1 % after calibration |
| POE-04 | Load steps vs electronic-load reference | Within 2 % |
| POE-05 | Switch with exhausted budget; port with a power limit below the class | Correct failure reported |
| POE-06 | 50 consecutive 2 s full-class load tests at the allowed duty cycle, 40 C ambient | No thermal cut-off trips; spreader below limit |

## Network (NET), Wi-Fi (WIFI), power (PWR), UI

| ID | Test | Pass |
|---|---|---|
| NET-01..13 | Each tool against a lab network with a packet capture as ground truth | Result matches the capture |
| NET-09 | Forced 10/half, 100/half, 100/full, 1000/full ports | Correct speed/duplex and mismatch warning |
| NET-12 | iperf3 both directions, both ports, vs a reference NIC | Record the ceiling; publish it |
| WIFI-01 | Scan vs a reference analyser in the same spot | Same BSSIDs within 5 dB |
| PWR-01 | Current per mode vs docs/06 | Record; regenerate docs/06 from measurements |
| PWR-04 | Scripted typical-profile discharge, full to shutdown | Record hours. This number, not the estimate, goes in any product claim |
| PWR-05 | Skin temperature after 1 h continuous use at 35 C ambient | Below 48 C on any touchable surface |
| UI-03 | Every dashboard function by keypad only, wearing work gloves | Reachable |
| DROP-01 | 1 m drop to concrete, 6 faces + 4 corners, with bumper | Functional; no display damage |

## Calibration (per unit, in production)

Wiremap resistance against two reference resistors; INA228 gain/offset against a reference load; centre-tap ADC dividers; TDR offset on a 2 m reference cable. Constants are stored on the coprocessor with a CRC and a calibration date; the engine reports "uncalibrated" in every result if they are missing.

## Field validation

Thirty days with at least three technicians. Every Auto Diagnose run is logged with the technician's own conclusion; disagreement between the device's diagnosis and the confirmed root cause is the metric. Target before any production decision: no false "No fault found" on a confirmed cabling fault.
