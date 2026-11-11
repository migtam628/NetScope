# RT-1 remote terminator

Passive plug-in terminator for wiremap, cable ID and length. Electrical definition: docs/03 and `firmware/netscope/cable/terminator.py` (the firmware file wins if they ever differ).

| Element | Between pins (anode -> cathode) | Value |
|---|---|---|
| D1 + R1 | 1 -> 2 | 1.0 k, 1 % |
| D2 + R2 | 3 -> 6 | 2.2 k, 1 % |
| D3 + R3 | 4 -> 5 | 4.7 k, 1 % |
| D4 + R4 | 7 -> 8 | ID: 10 k / 15 k / 22 k / 33 k / 47 k / 68 k / 100 k / 150 k for #1-#8 |

Diodes: small-signal, 100 V or more reverse rating (1N4148W class).

## Open design choice: surviving a passive injector

If someone plugs an RT-1 into a drop fed by a passive 48-57 V injector, the voltage appears between pair sets (for example pins 4,5 positive and 7,8 negative), not across a single pair, and the RT-1 has no element between pair sets, so in the common wiring no current flows. A miswired or split run can put voltage across one element; 57 V across 1 k is 3.2 W. Options: (a) 3 W flameproof resistors on R1-R3, or (b) a 60 V resettable fuse in series with each element. (b) is preferred; its resistance must be included in the matching tolerance. Decide in Phase 3 and test.

## Build

Two-layer 15 x 30 mm board, RJ45 plug or short pigtail, overmould or printed shell, large ID number on the shell. A kit of eight (IDs 1-8) is the useful field quantity. No KiCad files yet.

## Acceptance test

Measure each element both ways with a DMM diode/resistance range: forward within 2 % of nominal (plus diode drop on low-current ranges), reverse open.
