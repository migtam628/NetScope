# 13 - Firmware and software

## Run it now (no hardware)

```
cd firmware
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m netscope serve                           # open http://127.0.0.1:8080/
python -m netscope scenarios                       # list simulated faults
python -m netscope --scenario dns_fail run autodiag
pytest                                             # engine + API tests
make -C coproc test                                # coprocessor C core (needs a C compiler)
```

Works on Linux, macOS and Windows (the simulator has no OS-specific code). The banner "Simulated data" is shown whenever the simulator HAL is active, and reports carry the same mark.

Keyboard in the simulator = keypad on the device: arrows, Enter, Escape (Back), F1 (Home), F2 (context key). Double-click a text field to try the on-screen keyboard.

## Running against a real network from a Linux PC

```
sudo python -m netscope --hal linux --iface eth0 serve
```

Results are labelled provenance `host`. Wiremap, PoE and battery report "not available" because there is no measurement front end. TDR works only if the PC's NIC driver supports `ethtool --cable-test`. This path is the quickest way to exercise the HOST-IO code and is step 1 of the dev-kit spike.

## Layout

| Path | Contents |
|---|---|
| `firmware/netscope/hal/` | `base.py` interface, `sim.py` simulator (21 scenarios), `linux.py` real backend, `coproc.py` serial protocol |
| `firmware/netscope/cable/` | RT-1 model, cable model, wiremap analyser |
| `firmware/netscope/net/` | PoE tables; DHCP, DNS, LLDP, CDP, ethtool and iw parsers |
| `firmware/netscope/engine/` | Tools, Auto Diagnose, rules assistant, optional cloud AI |
| `firmware/netscope/reports/` | Report store, CSV and PDF export |
| `firmware/netscope/api/` | HTTP API |
| `firmware/ui/` | Touch UI (plain HTML/CSS/JS, no build step) |
| `firmware/coproc/` | Coprocessor C core + host tests |
| `firmware/os/` | Device OS integration (units and notes; image not built) |

## HTTP API (127.0.0.1 only on the device)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/info` | Version, provenance, device, battery |
| GET | `/api/tools` | Tool list with parameters and the `disruptive` flag |
| POST | `/api/jobs` `{tool, params}` | Start a tool or `autodiag`; returns `{id}` |
| GET | `/api/jobs/{id}` | Progress and result |
| POST | `/api/assistant` | Local diagnosis; `cloud: true` adds cloud analysis if configured |
| GET/POST | `/api/reports` | List / save |
| GET | `/api/reports/{id}/export.{json,csv,pdf}` | Export |
| GET/POST | `/api/sim/scenarios`, `/api/sim/scenario` | Simulator only |

One measurement runs at a time (single worker), because there is one test port.

## Coprocessor protocol

Frame: `0x7E | LEN | CMD | SEQ | payload | CRC16-CCITT`, 115200 8N1.

| Cmd | Name | Request | Response |
|---|---|---|---|
| 0x01 | PING | - | version |
| 0x10 | VSCAN | - | alt A mV (i32), alt B mV (i32), flags |
| 0x11 | WIREMAP | - | 56 x u32 ohms, `0xFFFFFFFF` = open |
| 0x12 | XTALK | - | 6 x i16 centi-dB |
| 0x13 | RELAY | mode | - |
| 0x20 | POE_STATUS | - | mV, kind, class, flags |
| 0x21 | POE_LOAD | mW, ms | mV, mA, no-load mV, held |
| 0x30 | BATTERY | - | %, mV, mA, 0.1 C, health, cycles, flags, minutes |
| 0x40 | KEY | (unsolicited) | key code, state |
| 0x7F | ERROR | - | code |

Both sides are tested against the same vectors.

Payloads are little-endian. Exact layouts (as implemented in `coproc/dispatch.c` and `hal/coproc.py`):

| Reply | Layout |
|---|---|
| PING | major u8, minor u8, patch u8 |
| VSCAN | alt A mV i32, alt B mV i32, flags u8 (bit0 pulsing) |
| WIREMAP | 56 x u32 ohms, order a=1..8, b=1..8, a != b |
| XTALK | 6 x i16 centi-dB: 1-2/3-6, 1-2/4-5, 1-2/7-8, 3-6/4-5, 3-6/7-8, 4-5/7-8 |
| POE_STATUS | mV i32, kind u8 (0 none, 1 IEEE, 2 passive), class u8 (0xFF none), flags u8 (bit0 four-pair, bit1 denied, bit2 alt B) |
| POE_LOAD | request: mW u32, ms u16. Reply: mV i32, mA i32, no-load mV i32, held u8 |
| BATTERY | % u8, mV u16, mA i16, 0.1 C i16, health u8, cycles u16, flags u8 (bit0 charging), minutes u16 (0xFFFF unknown) |
| LED | request: index u8, state u8 |
| BUZZ | request: Hz u16, ms u16 |

Interlocks enforced by the dispatcher: the relay enters TEST only when every pin is under 12 V; WIREMAP and XTALK need the relay in TEST; a refused scan forces the relay back to LINK; POE_LOAD needs the relay in LINK; the relay never moves while a load is applied.

## Device OS (planned, not built)

- **Base**: Raspberry Pi OS Lite (64-bit) for bring-up, moving to a Buildroot or Yocto image for production (read-only root, smaller, reproducible).
- **Device tree overlay**: Touch Display 2; LAN7801 with the KSZ9131 on its MDIO bus; UART to the coprocessor.
- **Services**: `netscope.service` (engine), `netscope-kiosk.service` (cog on the DSI panel), `netscope-keys.service` (coprocessor key events to `uinput`), systemd-networkd for the test port, wpa_supplicant for Wi-Fi. Example units are in `firmware/os/`.
- **Engine privileges**: dedicated user with `CAP_NET_RAW` and `CAP_NET_ADMIN`, not root.
- **Updates**: RAUC with A/B root partitions, signed bundles, automatic rollback if the engine does not report healthy after boot. Bundles install from USB storage or over HTTPS. The coprocessor is updated by the engine over its ROM bootloader (the SoM controls BOOT0 and reset), with the image and CRC carried inside the same bundle so the two never get out of step.
- **USB transfer**: USB-C in device mode exposing a read-only mass-storage view of an export partition (simplest and works on every OS).
- **Wireless sync**: HTTPS push of report JSON/PDF to an endpoint the owner configures (self-hosted is the intended default), authenticated with a per-device token, retried from a local queue. Not written.
- **Time**: SoM RTC kept alive from the always-on rail; reports use local time with offset.

## Flashing (planned)

SoM: hold `nRPIBOOT`, connect USB-C, run `rpiboot`, write the image with the standard imager. Coprocessor: SWD on the bench; in the field through the engine as above. None of this has been done for NetScope.

## Versioning and releases

`VERSION` is the single source. Tag `vX.Y.Z` to trigger `.github/workflows/release.yml`, which runs the tests and attaches the Python wheel/sdist and a source archive to a GitHub release. Until a device image exists, a "firmware release" is the engine package. Keep `CHANGELOG.md` current.

## Cloud AI

Off by default. Set `NETSCOPE_AI_URL`, `NETSCOPE_AI_KEY`, `NETSCOPE_AI_MODEL` to enable an "Ask AI" button on the Auto Diagnose result. The device asks before sending; IP host parts, MAC addresses and site names are masked unless `NETSCOPE_AI_REDACT=0`. The local rules diagnosis is always shown and never replaced. The HTTP call has not been exercised against a live endpoint.

## Known state of the HAL files (v0.1.0)

`hal/base.py`, `hal/sim.py`, `hal/linux.py`, `hal/coproc.py`, `models.py` and the CLI were rewritten on 2026-11-11 (see `CHANGELOG.md`). The simulator and protocol code are covered by the test suite. `hal/linux.py` imports and constructs but has not been run against a network: its first run on a Linux PC is its first test.
