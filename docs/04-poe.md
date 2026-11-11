# 04 - PoE diagnostics

## Signal path

```
RJ45 -> relays (LINK) -> transformer centre taps
        Alt A: CT(1,2), CT(3,6) -> Schottky bridge --+
        Alt B: CT(4,5), CT(7,8) -> Schottky bridge --+--> TVS 58 V --> TPS2372-4 --> INA228 shunt --> load bank
        all four CTs -> dividers -> ADS1115 (sees voltage before the PD interface turns on)
POE island <-> coprocessor:  ISO1640 I2C isolator, isolated 5 V DC/DC
```

The tester behaves as a **powered device** that asks for the maximum and reports what it is given.

## What is measured and how

| Item | Method | Notes |
|---|---|---|
| Voltage present before negotiation | Centre-tap ADC | Distinguishes nothing / PSE detection pulses / steady passive voltage. A compliant PSE stays in the low-voltage detection and classification range until it sees a PD; steady voltage above that range with no PD presented is treated as passive |
| Which pairs carry power, polarity | Centre-tap ADC, per pair set | Alt A, Alt B or both (4-pair) |
| Standard / type / class allocated | TPS2372-4 requests class 8; its PSE-type indicator outputs show what the PSE actually granted | Decode of the indicator pins is per datasheet section 7.3.5 and is **not yet implemented** (coprocessor port layer) |
| Delivered voltage | INA228 bus voltage | Checked against the PD-side minimum for the granted type |
| Power available | Class table in `net/poe.py` | 12.95 / 25.5 / 51 / 71.3 W at the device for af / at / bt Type 3 / bt Type 4 |
| Actual power under load | Switched resistor bank, INA228 V x I | Only with explicit authorization; capped at the granted class |
| LLDP power negotiation | LLDP 802.3 Power-via-MDI TLV parsed from the switch | Parsing implemented and tested; *sending* a PD power request over LLDP is not implemented |
| Negotiation failures | Detection seen but no operating voltage; voltage collapses under load; power removed during load | Mapped to "budget exhausted / port limit / cable resistance" guidance |

## Load bank

Six pulse-rated TO-220 resistors on an aluminium spreader, each switched by a MOSFET from an I/O expander on the isolated bus. Combinations give steps near the class power levels. Provisional values for a 50-54 V bus: 68, 82, 160, 330, 680, 1500 ohm (all on: about 70 W at 52 V). Final values are a Phase 3 calculation against real resistor ratings.

Thermal reality: a handheld cannot dissipate 71 W continuously.

- Default load test: **2 seconds**. 71 W for 2 s is about 140 J; into a 40 g aluminium spreader that is a rise of roughly 4 K per test.
- Firmware enforces a cool-down duty cycle from an NTC on the spreader.
- A comparator on the same NTC kills the gate drive in hardware regardless of firmware.
- Continuous load is limited to a few watts (enough to hold a port up for a long soak).

A 2-second test shows whether the PSE and cable can deliver the power. It does not prove long-term thermal behaviour of the cable bundle or the switch's supply.

## Protection

- Bridges make the input polarity-agnostic on both pair sets: 802.3 Alt A/B, either polarity, and passive injectors.
- TVS 58 V at the bridge output; 100 V-rated bridge diodes, PD interface hot-swap FET and load FETs.
- Everything on the island is referenced to the island. 1500 Vrms transformer, reinforced I2C isolator, isolated DC/DC. Creepage and clearance rules in docs/11.
- **Non-standard high voltage** (some proprietary systems exceed 57 V): above the TVS stand-off the TVS conducts and must be backed by a fuse or PTC ahead of it. The fuse rating is an open item (R-06).
- The data path (PHY) is behind the transformer and a TVS array, as in any PoE device.

## Disruption policy

- Identifying PoE (presenting a PD signature and classifying) is what any PoE device does when plugged in. Auto Diagnose does this.
- A **load test** draws real power and counts against the switch's budget; on a nearly full switch it can cause the switch to shed a lower-priority port. It is never run automatically and the UI asks first.

## Not supported

- Acting as a PSE (injecting power). Out of scope.
- Dual-signature PD behaviour testing.
- Proprietary schemes (pre-standard Cisco inline power, UPOE negotiation over CDP, PoH): voltage is reported; negotiation is not performed.
- Certification of a PSE to 802.3 conformance. This is a field diagnostic.
