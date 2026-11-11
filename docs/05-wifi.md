# 05 - Wi-Fi diagnostics

The radio is the Compute Module 5's on-board 802.11ac (2.4 / 5 GHz) + Bluetooth module. It is an ordinary client adapter, and that sets the ceiling.

## What an ordinary Wi-Fi adapter can do (supported)

| Feature | How | Status |
|---|---|---|
| SSID / BSSID discovery | `iw scan`, parsed by `net/parsers.py` | Parser tested; I/O unverified on hardware |
| Signal strength (dBm) | RSSI from scan and from the associated link | Same |
| Channel, band, width | Frequency and HT/VHT operation elements | Same |
| Security type | RSN / WPA elements: Open, WEP, WPA, WPA2-PSK, WPA3-SAE, Enterprise | Same |
| Channel occupancy | Count of BSSIDs per channel and strongest signal | Implemented |
| Channel utilisation | **AP-advertised** BSS Load element (the AP's own estimate) | Implemented. APs that do not advertise it show no value |
| Connected AP details | `iw link`: BSSID, channel, rates, RSSI | Implemented |
| Roaming diagnostics | Roam events from the supplicant: from/to BSSID and RSSI before/after; "roamed late" rule | Rule implemented; the supplicant event listener is **not yet written** |
| Signal history | Periodic RSSI samples of the associated AP | **Not yet implemented** (UI graph and sampler) |
| Connectivity and throughput | Same ping / DNS / HTTP / iperf3 tools on the wireless interface | Tools exist; interface selection in the UI is **not yet implemented** |
| Channel comparison graph | Per-band bar graph | Implemented in the UI |

## What needs different hardware (not supported, and not claimed)

| Feature | Why an ordinary adapter cannot do it | What it would take |
|---|---|---|
| True channel utilisation / airtime | Needs the radio to report busy-time counters while sitting on each channel. Whether this adapter's driver exposes survey data is unverified | A radio with survey support (mt76-class card in the optional M.2 slot) |
| Non-Wi-Fi interference (microwave ovens, Bluetooth, video senders, radar) | A Wi-Fi chip only decodes Wi-Fi frames | A spectrum analyser front end or SDR |
| Monitor-mode capture of other clients' frames, retries, rates | Not supported in normal operation on this adapter | Monitor-mode capable card |
| 6 GHz (Wi-Fi 6E/7) | Radio is 2.4 / 5 GHz only | USB radio; the M.2 slot was given up for the fiber port |
| Site-survey heatmaps | Needs location input and a mapping workflow | Software feature, out of scope for rev A |

The UI states the utilisation caveat on every scan result.

## Regulatory note

The module's radio certification applies when it is used with the antenna it was certified with. Rev A uses the maker's own antenna kit for that reason. Any other antenna, or adding a second radio, changes the compliance picture (docs/10).
