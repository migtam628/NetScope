# Coprocessor firmware (STM32G0B1)

The coprocessor owns everything that must work before Linux is up or that
must never depend on Linux being healthy: power sequencing, the power
button, battery/charger supervision, the port relays, the wiremap front end
and the isolated PoE measurement bus.

## What is here

| File | Status |
|---|---|
| `proto.c/.h` | Serial framing. Host-tested (`make test`), vectors shared with the Python side. |
| `wiremap.c/.h` | Scan sequencing and the voltage safety gate. Host-tested against a fake front end. |
| `test_host.c` | Host unit test. Runs in CI. |

## What is not here yet

The STM32 port layer (`port_stm32g0/`): clock/GPIO/ADC/UART setup, the
`ns_afe_t` implementation for the real front end, relay drivers, the I2C
drivers for the isolated INA228 + ADC, charger and fuel gauge, the
TPS2372-4 `TPH/TPL/BT` decode (datasheet section 7.3.5), key scanning and
the command dispatcher. It cannot be written credibly before the schematic
pinout is frozen (Phase 3) and cannot be verified before boards exist
(Phase 7). Nothing in this directory has run on a microcontroller.

## Safety rules the port layer must keep

1. Relays default (unpowered) to LINK: the cable only ever sees the
   isolation transformer. TEST position is entered only for the duration of
   a scan and only after the voltage gate passes.
2. `ns_wiremap_scan` refuses to run above 12 V on any pin and aborts if
   voltage appears mid-scan. Do not bypass it from the dispatcher.
3. The PoE load is disabled by hardware over-temperature comparator; firmware
   limits are in addition to that, not instead of it.
