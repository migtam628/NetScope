# 15 - Dev-kit spike: kit list, procedures, pass criteria

This is the next phase. It needs hardware on a bench; nothing here can be done in software alone. The purpose is to prove or kill the five riskiest assumptions in `docs/02` before a schematic is drawn. Record every result in `docs/spike/RESULTS.md` (template provided) and commit it.

Wiring for the whole kit is drawn in `hardware/schematic/bench-kit.pdf` (source `hardware/spike/bench-kit.yaml`).

## Budget correction

The first estimate for this spike was about $400. That was too low. The LAN7801 evaluation platform alone was listed at about EUR 259 at one distributor when checked on 2026-11-11. **Plan for $700-$900** and quote each line before ordering. Prices below are marked "checked" only where a current listing was seen.

## Kit list

| # | Item | Part / order code | Price | Status |
|---|---|---|---|---|
| 1 | Compute Module 5, wireless, 2 GB / 16 GB | CM5102016 | see `docs/14` | In BOM |
| 2 | CM5 IO board, 27 W USB-C supply, CM5 cooler | Raspberry Pi | quote | Not checked |
| 3 | Touch Display 2, 5 inch | Raspberry Pi | $40 list, checked | Production stated to Jan 2030 (risk R-09) |
| 4 | LAN7801 USB 3 to RGMII host board | Microchip EVB-LAN7801-EDS (EV88E76A), or the newer EVB-LAN7801-EDS2 (EV16Z95A) | about EUR 259 seen for EV88E76A | **Confirm which host/daughter pair is in stock before ordering; the two generations use different connectors** |
| 5 | KSZ9131 PHY daughter card | EVB-KSZ9131RNX for the EDS host, or KSZ9131 EDS2 Daughter Card (EV35H80A) for the EDS2 host | quote | EV35H80A showed a 12-week lead time at DigiKey |
| 6 | PoE PD evaluation module | TI TPS2372-4EVM-006 | quote | Listed by TI |
| 7 | MCU board | ST NUCLEO-G0B1RE | quote | Not checked |
| 8 | Wiremap breadboard parts | 2x 8:1 analog mux breakouts, op-amp, resistors per `hardware/remote-terminator/README.md`, 2 RJ45 breakouts | about $40 | Generic |
| 9 | Relay test adapter | 4x DPDT signal relay from the BOM on a small board between two RJ45 breakouts | about $30 | Generic |
| 10 | Things to test against | 802.3af, 802.3at and 802.3bt switches or injectors; one 24 V passive injector; cables of 2, 30 and 90-100 m; a cable with a known open and a known short; USB power meter; bench multimeter | borrow | From field stock |

| 11 | 10 Gb fiber controller on a card | A PCIe SFP+ card built on the Marvell/Aquantia **AQC100** (Marvell's own AQN-100 adapter is one). Confirm the chip before buying: listings for other cards disagree about which chip they use. **Also buy a Realtek RTL8127ATF SFP+ card** (seen at about $68) and run the same step on it: it is the fallback if the AQC100 cannot be sourced | quote | AQC100 card not checked |
| 12 | Adapter to fit that card to the CM5 IO board | M.2 M-key to PCIe slot adapter with external power for the card | about $20 | Generic |
| 13 | Fiber parts | One 10GBASE-SR module, one 1000BASE-SX module, one LC-LC multimode patch lead, a second device with a 10 Gb SFP+ port and one with a 1 Gb SFP port | borrow | From field stock |

Items 4 and 5 are the long-lead and expensive ones. If they cannot be had, do not substitute an ordinary USB Ethernet adapter and call the step passed: the question is whether *this* MAC + PHY reports usable TDR through Linux.

## Step 1 - Linux engine and UI on the real SoM

Setup: Raspberry Pi OS Lite 64-bit on the CM5; clone this repo; `pip install -e "firmware[device]"`; attach the display.

```
sudo python -m netscope --hal linux --iface eth0 run autodiag --json > step1-autodiag.json
sudo python -m netscope --hal linux --iface eth0 serve --host 0.0.0.0
```

This is the first time `firmware/netscope/hal/linux.py` runs against a real network. Expect to fix bugs in it; that is part of the step.

| Check | Pass |
|---|---|
| Link, DHCP, gateway, DNS, internet steps return real values on a normal office port | All five produce a result that matches what a laptop sees on the same port |
| LLDP or CDP neighbour is reported on a managed switch | Switch name, port and VLAN correct |
| Wiremap, PoE, battery | Report "not tested", never invented values |
| UI in a kiosk browser on the 5 inch panel, operated with a gloved finger | Every home-screen item reachable; note any target that is too small |
| Cold boot to usable UI | Record seconds. Target under 20 s |
| Power at the 5 V input: idle with display on, and during a test | Record watts. Compare with `docs/06` (3.39 W idle, 7.56 W active from battery). If idle is above about 4.5 W the runtime claim fails |

## Step 2 - TDR through LAN7801 + KSZ9131

```
sudo ethtool --cable-test eth1
sudo python -m netscope --hal linux --iface eth1 run cable
```

| Check | Pass |
|---|---|
| Kernel reports per-pair codes and fault lengths | Yes on the kernel version to be shipped; record the version |
| Open-ended cables of 2, 30 and 90-100 m | Length within +-(1 m + 3 %) on at least 3 of 4 pairs. Record the raw numbers; they become the accuracy claim |
| Known open, known short | Correct code, distance within 2 m |
| Against a live switch port | "ok" on all pairs, or a clean refusal; never a false fault |
| Shortest cable that still reads correctly | Record it (dead zone) |

Fail action: evaluate another PHY with mainline cable-test support before changing anything else.

## Step 3 - PoE identification with the TPS2372-4 EVM

| Check | Pass |
|---|---|
| af, at and bt sources | Type indicators (TPH/TPL/BT) decode to the right type and class each time, 10 plug cycles each |
| Voltage at the PD | Within 0.5 V of a multimeter |
| 24 V passive injector | Voltage is visible on a high-impedance divider **before** the PD interface; the EVM is not damaged. Do this last |
| Load steps of 5, 13 and 25 W for 2 s | Port holds; voltage and current readable; note the temperature rise of the load |

## Step 4 - Wiremap on a breadboard

Build the RT-1 terminator and the mux front end; port `firmware/coproc/wiremap.c` to the Nucleo by implementing the three `ns_afe_t` callbacks.

| Check | Pass |
|---|---|
| Good cable at 2, 30 and 90-100 m, each terminator ID | Correct map and ID every time |
| Each fault: open, short, reversed pair, crossed pairs, miswire | Matches `firmware/tests/test_wiremap.py` expectations |
| PoE switch on the far end instead of RT-1 | Scan measures in the gaps or returns "busy"; never a false fault, never damage |
| 24 V on any pin | Scan refused (unsafe voltage) |

## Step 5 - Relay in the gigabit path

| Check | Pass |
|---|---|
| Gigabit link through the relay adapter over 90-100 m | Links at 1000 Mb/s; zero CRC errors in a 10-minute iperf3 run |
| Same with the relay cycled 1,000 times | No change |

## Step 6 - 10 Gb fiber controller on the SoM

```
lspci -vv | grep -A3 -i ethernet          # card present, link speed and width
sudo ethtool eth2                          # link, speed
sudo ethtool -m eth2                       # module identity and light levels, if the driver supports it
iperf3 -c <10 Gb host> -t 30 ; iperf3 -c <10 Gb host> -t 30 -R
sudo python -m netscope --hal linux --fiber-iface eth2 --sfp-bus <n> run fiber
```

| Check | Pass |
|---|---|
| Driver loads and the card works on the SoM's single PCIe lane at the default (Gen 2) setting | Yes, with the kernel to be shipped; record the version |
| 10GBASE-SR module, 10 Gb far end | Links at 10 Gb |
| Throughput each way | Record it. Expected roughly 3.5 Gb/s at Gen 2; this number becomes the published limit |
| Same with the lane forced to Gen 3 | Record throughput and whether it is stable for 30 minutes. Only use Gen 3 in the product if it is |
| **1000BASE-SX module, 1 Gb far end** | Links at 1 Gb. **If it does not, the product cannot serve 1 Gb fiber sites and the controller choice must be revisited** |
| Module identity and light levels readable from Linux | Yes by `ethtool -m`, or note that the product must read the module over I2C itself (the design wires the cage's I2C to the SoM for this) |
| Extra power with the port active | Record watts at the 5 V input |

A bought card does not expose the cage's I2C pins, so the engine's own module-reading path cannot be tested here; that waits for the first board.

## Exit

All six steps recorded. Any failed row has either a fix or an architecture change written into `docs/02` and `docs/10`. Then, and only then, start the schematic (`hardware/kicad/README.md`).
