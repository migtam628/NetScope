# 03 - Ethernet cable testing

## What this instrument is and is not

NetScope X1 is a **verifier**: it proves continuity, pin order and approximate length, and locates opens and shorts. It is **not a certifier**. Certification to TIA-568 / ISO 11801 means swept-frequency measurement of insertion loss, NEXT, PSNEXT, ACR-F, return loss and delay skew to 100 / 250 / 500 MHz with a calibrated analog front end and traceable accuracy. Nothing in this design measures those. The firmware prints "not a TIA/ISO certification test" on every cable result and a unit test enforces it.

"Cat5e/Cat6/Cat6A troubleshooting" therefore means: find the wiring fault on such a cable. It does not mean telling the categories apart or grading them.

## Three measurement methods

| Method | Hardware | Finds | Cannot find |
|---|---|---|---|
| DC wiremap | Coprocessor front end + RT-1 remote | Opens (per pair), shorts (which pins), reversed pairs, crossed pairs, miswires, crossover cables, terminator ID | Which conductor of a pair is open; split pairs; anything at frequency |
| PHY TDR | KSZ9131 LinkMD via `ethtool --cable-test` | Per-pair open / short and distance; cable length (open far end) | Pin order; faults close to the far end of a terminated, linked pair |
| Pair-coupling test | Tone injected on one pair, level detected on another | Split pairs (probable) | **Experimental.** Threshold not yet set from real cable |

### DC wiremap

The coprocessor drives a small current into pin *a* and returns it from pin *b* through two 8:1 multiplexers, for all 56 ordered pin pairs, and reports resistance (diode drop compensated by measuring at two currents). `netscope/cable/wiremap.py` turns that matrix into a result:

- low resistance both ways between two pins: metallic connection (a short, or a transformer winding);
- an RT-1 resistor value one way and open the other: that pin pair is the remote pair with that value, with the polarity given by the diode;
- low resistance inside two or more nominal pairs and nothing between pairs: far-end network equipment, not shorts.

Honest limits, each reflected in the result text:

- **One open conductor looks like an open pair.** DC sees the loop, not the wire. The TDR distance is attached to help.
- **Against live equipment, pin order cannot be verified** (every pair looks like a winding). The result says to use an RT-1.
- **No RT-1, no equipment:** only shorts are checked; pins are reported "unverified", status WARNING, never PASS.
- **A two-pair (10/100) device and a cable with pairs 4-5/7-8 open look the same** from this end. Reported as WARNING with both explanations.
- **PSE detection pulses** (a PoE switch probing the line) disturb DC readings. The scan measures in the gaps and gives up as "busy" if the line never goes quiet. Needs validation against real switches (test CBL-09).

### PHY TDR

The KSZ9131's LinkMD reports open / short per pair with a distance. The mainline driver converts the PHY's reading to distance in steps of 0.4 m, and a published kernel test log shows a 2 m cable reported as about 1.2 m on three pairs and 0.0 m on the fourth. So: resolution well under a metre, error on the order of a metre, and a blind zone on very short cables. Treat a result as "about 18 m", not "17.7 m". Accuracy also depends on the cable's velocity factor (NVP), which varies by cable type; the UI will need an NVP setting and a calibrate-on-known-length function (not yet implemented).

With an RT-1 or nothing at the far end every healthy pair reflects at the end of the cable. That reflection is the length measurement; the UI labels it "end of cable", not "open".

### Split pairs

A split pair is DC-correct: all eight pins connect straight through, but two conductors from different twisted pairs are used as a "pair". It passes wiremap and fails at speed. The only way to see it is at AC. The design injects a tone on one pair and measures what couples into each other pair; properly twisted pairs couple weakly, a split couples strongly.

Status: **block reserved in the netlist (U33), analysis implemented and unit-tested against a model, threshold provisional, circuit not designed in detail.** Until it is validated on real split cables of several lengths, results are labelled "probable" and the capability matrix lists it as experimental.

## RT-1 remote terminator

Passive, no battery. One series diode + resistor per pair; the diode anode is on the first pin listed.

| Pair | Anode -> cathode | Resistor |
|---|---|---|
| 1-2 | 1 -> 2 | 1.0 k |
| 3-6 | 3 -> 6 | 2.2 k |
| 4-5 | 4 -> 5 | 4.7 k |
| 7-8 | 7 -> 8 | ID resistor: 10 k, 15 k, 22 k, 33 k, 47 k, 68 k, 100 k, 150 k for ID 1-8 |

Values are the single source of truth in `firmware/netscope/cable/terminator.py`. Adjacent values are at least 1.47x apart; the matcher accepts +/-12 %, which covers 1 % resistors plus cable loop resistance on a 100 m run. Build notes are in `hardware/remote-terminator/`.

Because the terminations are kilohms, a TDR sees them as an open end, so length works with the RT-1 fitted.

**PoE interaction:** an RT-1 is not a valid PD signature (25 k across the powered pairs), so a compliant PSE will not power it. A passive injector would put its full voltage across the diodes and resistors; the parts are rated for 60 V continuous (1 k at 57 V dissipates 3.2 W, so the resistors must be flameproof 3 W types or the pair protected by a series PTC - open design choice, see `hardware/remote-terminator/README.md`).

## Validation

See docs/09, tests CBL-01 to CBL-10: a fault-box of known cables (each fault type, three lengths), a reel for length accuracy, and live switches from at least three vendors.
