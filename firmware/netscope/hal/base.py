"""Hardware abstraction layer interface.

Tools call these methods and never touch hardware directly.  Every method
returns plain dicts/lists (JSON-serialisable) so results flow unchanged to
the API, the UI and saved reports.

A backend implements what it can measure.  Anything it cannot measure raises
HalUnsupported, which the engine reports as NOT_TESTED with the reason - it
is never papered over with made-up data.  The base class supports nothing.
"""
from __future__ import annotations


class HalError(Exception):
    """A measurement was attempted and failed."""


class HalUnsupported(HalError):
    """This backend has no way to make the measurement."""


def _no(what: str):
    raise HalUnsupported(f"{what} is not available on this backend.")


class Hal:
    name = "none"
    provenance = "none"  # simulated | host | hardware

    # -- device ------------------------------------------------------------
    def device_info(self) -> dict:
        """model, serial, hw_rev"""
        _no("Device information")

    def battery(self) -> dict:
        """percent, voltage_v, current_ma, temp_c, health_pct, cycles, charging, time_to_empty_min"""
        _no("Battery monitoring")

    # -- cable -------------------------------------------------------------
    def port_voltage_scan(self) -> dict:
        """alt_a_v, alt_b_v, pulsing - high-impedance scan made before anything is connected."""
        _no("Port voltage scan")

    def wiremap_scan(self) -> dict:
        """matrix (8x8 ohms, None = open), crosstalk_db (dict or None)"""
        _no("Wiremap")

    def tdr(self) -> list[dict]:
        """per pair: pair (A-D), pins, code (ok|open|short|cross_short|unknown), length_m"""
        _no("TDR")

    # -- PoE ---------------------------------------------------------------
    def poe_status(self) -> dict:
        """kind (none|passive|ieee), voltage_v, alt, allocated_class, four_pair, denied"""
        _no("PoE measurement")

    def poe_load_test(self, load_w: float, seconds: float) -> dict:
        """requested_w, held, voltage_v, current_a, power_w, no_load_v, reason"""
        _no("PoE load test")

    # -- link / IP ---------------------------------------------------------
    def link_status(self) -> dict:
        """up, speed, duplex, autoneg, mdix, partner_modes"""
        _no("Link status")

    def dhcp_discover(self) -> dict | None:
        """address, prefix, gateway, dns, server, lease_s, domain - or None if no offer"""
        _no("DHCP")

    def set_static(self, address: str, prefix: int, gateway: str, dns: list[str]) -> dict:
        _no("Static IP configuration")

    def net_config(self) -> dict | None:
        """Current address/prefix/gateway/dns of the test port, or None."""
        _no("IP configuration")

    def ping(self, host: str, count: int) -> dict:
        """sent, received, loss_pct, rtt_min_ms, rtt_avg_ms, rtt_max_ms"""
        _no("Ping")

    def traceroute(self, host: str) -> list[dict]:
        """hop, address, rtt_ms"""
        _no("Traceroute")

    def dns_lookup(self, name: str, server: str | None) -> dict:
        """ok, addresses, server, error, time_ms"""
        _no("DNS lookup")

    def http_check(self, url: str) -> dict:
        """ok, status, time_ms, error, captive_portal"""
        _no("HTTP check")

    def arp_table(self) -> list[dict]:
        """address, mac, vendor"""
        _no("ARP table")

    def neighbors(self) -> list[dict]:
        """LLDP/CDP records as produced by netscope.net.parsers"""
        _no("LLDP/CDP")

    def throughput(self, server: str, seconds: int) -> dict:
        """server, tx_mbps, rx_mbps, retransmits"""
        _no("Throughput test")

    def capture(self, seconds: int) -> dict:
        """file, packets, note"""
        _no("Packet capture")

    # -- Wi-Fi -------------------------------------------------------------
    def wifi_scan(self) -> list[dict]:
        """ssid, bssid, freq, channel, width, rssi, security, util_pct, stations"""
        _no("Wi-Fi scan")

    def wifi_status(self) -> dict:
        """connected, ssid, bssid, channel, freq, rssi, tx_rate_mbps, roam_events"""
        _no("Wi-Fi status")
