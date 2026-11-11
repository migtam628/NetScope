"""Simulator HAL.

Produces the raw readings the hardware would produce for a described
situation (a cable, a PoE source, a network), using the same electrical
models the analyser is tested against.  The engine then interprets them
exactly as it would interpret real readings.

Everything from this backend has provenance "simulated".  It is a model of
the instrument, not evidence that the instrument works.
"""
from __future__ import annotations

import math

from ..cable.model import CableModel, simulate_crosstalk, simulate_matrix
from ..cable.terminator import PAIRS
from ..net.poe import CLASSES
from .base import Hal, HalError

SUBNET = "10.20.30."
LEASE = dict(address="10.20.30.117", prefix=24, gateway="10.20.30.1",
             dns=["10.20.30.10", "10.20.30.11"], server="10.20.30.10", lease_s=28800,
             domain="corp.example")
POE_AT = dict(kind="ieee", cls=4, volts=53.4, loop_ohms=5.0, four_pair=False)
SWITCH_CABLE = dict(length_m=38.0, far_end="equipment")

# Each scenario overrides these defaults.
DEFAULTS = dict(
    cable=SWITCH_CABLE, poe=POE_AT,
    link=dict(up=True, speed=1000, duplex="full"),
    lldp=dict(system_name="IDF2-SW03", port_id="Gi1/0/14", port_description="Office 214 drop B",
              vlan=30, mgmt_address="10.20.0.3"),
    dhcp=True, gateway_ok=True, dns_local_ok=True, internet_ok=True, captive=False)

SCENARIOS: dict[str, dict] = {
    "healthy": dict(title="Healthy drop on a PoE+ switch"),
    "rt1_pass": dict(title="Good 42 m cable on RT-1 terminator #3",
                     cable=dict(length_m=42.0, terminator_id=3), poe=None),
    "open_pair": dict(title="Pair 7-8 open 18 m away (RT-1 fitted)",
                      cable=dict(length_m=42.0, wiring={7: None, 8: None}, fault_distance_m=18.0),
                      poe=None),
    "short": dict(title="Pins 4-5 shorted 23 m away (RT-1 fitted)",
                  cable=dict(length_m=42.0, shorts=[(4, 5)], fault_distance_m=23.0), poe=None),
    "reversed": dict(title="Pair 1-2 reversed (RT-1 fitted)",
                     cable=dict(length_m=25.0, wiring={1: 2, 2: 1}), poe=None),
    "split": dict(title="Split pair 3-6 / 4-5 (RT-1 fitted)",
                  cable=dict(length_m=30.0, split_pairs=("3-6", "4-5")), poe=None),
    "two_pair_100": dict(title="Only two pairs continuous: links at 100 Mb/s",
                         cable=dict(length_m=38.0, far_end="equipment", equipment_pairs=2),
                         link=dict(up=True, speed=100, duplex="full"), poe=None),
    "no_link": dict(title="Switch port shut down: cable good, no link",
                    link=dict(up=False), poe=None),
    "duplex": dict(title="Duplex mismatch: port forced, tester at half duplex",
                   link=dict(up=True, speed=100, duplex="half", partner_modes=[]), poe=None),
    "no_dhcp": dict(title="Wrong VLAN: link up, no DHCP", dhcp=False,
                    lldp=dict(system_name="IDF2-SW03", port_id="Gi1/0/22",
                              port_description="unused", vlan=999, mgmt_address="10.20.0.3")),
    "gateway_down": dict(title="Default gateway not answering", gateway_ok=False,
                         internet_ok=False),
    "dns_fail": dict(title="Internal DNS servers down", dns_local_ok=False),
    "no_internet": dict(title="ISP / WAN outage: LAN is fine", internet_ok=False),
    "passive_poe": dict(title="24 V passive injector on the line",
                        poe=dict(kind="passive", volts=24.1, alt="B")),
    "poe_denied": dict(title="PoE detected but power never delivered",
                       poe=dict(kind="ieee", denied=True)),
    "poe_bt": dict(title="802.3bt Type 4 port (90 W)",
                   poe=dict(kind="ieee", cls=8, volts=54.6, loop_ohms=2.5, four_pair=True)),
    "poe_sag": dict(title="PoE+ over a long, high-resistance run",
                    cable=dict(length_m=96.0, far_end="equipment"),
                    poe=dict(kind="ieee", cls=4, volts=51.0, loop_ohms=15.0, four_pair=False)),
}

PAIR_LETTER = dict(zip(PAIRS, "ABCD"))
TDR_JITTER = dict(A=-0.4, B=0.4, C=0.3, D=-0.3)  # fixed, so results are repeatable


class SimHal(Hal):
    name = "sim"
    provenance = "simulated"

    def __init__(self, scenario: str = "healthy"):
        self.set_scenario(scenario)

    def set_scenario(self, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise KeyError(f"unknown scenario '{scenario}'")
        self.scenario = scenario
        self.cfg = {**DEFAULTS, **SCENARIOS[scenario]}
        c = dict(self.cfg["cable"])
        wiring = {i: i for i in range(1, 9)}
        wiring.update(c.pop("wiring", {}))
        self.cable = CableModel(wiring=wiring, **c)
        self.net: dict | None = None  # IP configuration of the test port

    # -- device ------------------------------------------------------------
    def device_info(self) -> dict:
        return dict(model="NetScope X1 (simulator)", serial="SIM-000001", hw_rev="sim")

    def battery(self) -> dict:
        return dict(percent=78, voltage_v=3.87, current_ma=-950, temp_c=31.5, health_pct=97,
                    cycles=41, charging=False, time_to_empty_min=462)

    # -- cable -------------------------------------------------------------
    def port_voltage_scan(self) -> dict:
        p = self.cfg["poe"]
        if p and p["kind"] == "passive":
            a, b = (p["volts"], 0.0) if p.get("alt") == "A" else (0.0, p["volts"])
            return dict(alt_a_v=a, alt_b_v=b, pulsing=False)
        if p and p["kind"] == "ieee":  # detection pulses from a compliant PSE
            return dict(alt_a_v=4.4, alt_b_v=4.4 if p.get("four_pair") else 0.0, pulsing=True)
        return dict(alt_a_v=0.0, alt_b_v=0.0, pulsing=False)

    def wiremap_scan(self) -> dict:
        xt = simulate_crosstalk(self.cable) if self.cable.far_end == "terminator" else None
        return dict(matrix=simulate_matrix(self.cable), crosstalk_db=xt)

    def tdr(self) -> list[dict]:
        c, out = self.cable, []
        fault_at = c.fault_distance_m if c.fault_distance_m is not None else c.length_m
        shorted = {p for s in c.shorts for p in s}
        for i, pair in enumerate(PAIRS):
            letter = PAIR_LETTER[pair]
            a, b = pair
            jit = TDR_JITTER[letter]
            if pair in c.shorts or pair[::-1] in c.shorts:
                code, length = "short", fault_at + jit
            elif a in shorted or b in shorted:
                code, length = "cross_short", fault_at + jit
            elif c.wiring.get(a) is None or c.wiring.get(b) is None:
                code, length = "open", fault_at + jit
            elif c.far_end == "equipment" and i < c.equipment_pairs:
                code, length = "ok", None
            else:  # RT-1 or nothing: the end of the cable reflects like an open
                code, length = "open", c.length_m + jit
            out.append(dict(pair=letter, pins=f"{a}-{b}", code=code,
                            length_m=None if length is None else round(length, 1)))
        return out

    # -- PoE ---------------------------------------------------------------
    def _on_switch(self) -> bool:
        return self.cable.far_end == "equipment"

    def poe_status(self) -> dict:
        p = self.cfg["poe"]
        if not p or not self._on_switch():
            return dict(kind="none", voltage_v=0.0, alt=None, allocated_class=None,
                        four_pair=False, denied=False)
        if p["kind"] == "passive":
            return dict(kind="passive", voltage_v=p["volts"], alt=p.get("alt", "B"),
                        allocated_class=None, four_pair=False, denied=False)
        if p.get("denied"):
            return dict(kind="ieee", voltage_v=0.0, alt="A", allocated_class=None,
                        four_pair=False, denied=True)
        return dict(kind="ieee", voltage_v=p["volts"], alt="A", allocated_class=p["cls"],
                    four_pair=p["four_pair"], denied=False)

    def poe_load_test(self, load_w: float, seconds: float) -> dict:
        p = self.cfg["poe"]
        if not p or p["kind"] != "ieee" or p.get("denied") or not self._on_switch():
            raise HalError("PoE is not powered")
        v0, r = p["volts"], p["loop_ohms"]
        out = dict(requested_w=load_w, no_load_v=v0, held=False, voltage_v=0.0, current_a=0.0,
                   power_w=0.0, reason=None)
        disc = v0 * v0 - 4 * r * load_w           # V*I = P with V = v0 - I*r
        if disc < 0:
            out["reason"] = "voltage collapsed: the run cannot carry this power"
            return out
        amps = (v0 - math.sqrt(disc)) / (2 * r)
        if v0 * amps > CLASSES[p["cls"]][0] * 1.05:
            out["reason"] = "PSE cut power at its class limit"
            return out
        volts = v0 - amps * r
        out.update(held=True, voltage_v=round(volts, 1), current_a=round(amps, 3),
                   power_w=round(volts * amps, 1))
        return out

    # -- link / IP ---------------------------------------------------------
    def _link_up(self) -> bool:
        return self._on_switch() and bool(self.cfg["link"].get("up"))

    def link_status(self) -> dict:
        l = self.cfg["link"]
        if not self._link_up():
            return dict(up=False, speed=None, duplex=None, autoneg=True, mdix=None,
                        partner_modes=[])
        modes = ["10baseT/Full", "100baseT/Full"] + (["1000baseT/Full"] if l["speed"] >= 1000 else [])
        return dict(up=True, speed=l["speed"], duplex=l["duplex"], autoneg=True, mdix="off",
                    partner_modes=l.get("partner_modes", modes))

    def dhcp_discover(self) -> dict | None:
        if not self._link_up() or not self.cfg["dhcp"]:
            return None
        self.net = {k: LEASE[k] for k in ("address", "prefix", "gateway", "dns")}
        return dict(LEASE, dns=list(LEASE["dns"]))

    def set_static(self, address: str, prefix: int, gateway: str, dns: list[str]) -> dict:
        self.net = dict(address=address, prefix=prefix, gateway=gateway, dns=list(dns))
        return dict(self.net)

    def net_config(self) -> dict | None:
        return dict(self.net) if self.net else None

    def _reachable(self, host: str) -> bool:
        if not self._link_up() or not self.net:
            return False
        if host == self.net.get("gateway") or host == LEASE["gateway"]:
            return self.cfg["gateway_ok"]
        if host.startswith(SUBNET):
            return True
        return self.cfg["gateway_ok"] and self.cfg["internet_ok"] and not self.cfg["captive"]

    def ping(self, host: str, count: int) -> dict:
        ok = self._reachable(host)
        local = host.startswith("10.")
        base = 0.6 if local else 11.8
        return dict(host=host, sent=count, received=count if ok else 0,
                    loss_pct=0.0 if ok else 100.0,
                    rtt_min_ms=base - 0.2 if ok else None, rtt_avg_ms=base if ok else None,
                    rtt_max_ms=round(base * 1.6, 1) if ok else None)

    def traceroute(self, host: str) -> list[dict]:
        if not self._link_up() or not self.net:
            return []
        gw = self.cfg["gateway_ok"]
        hops = [dict(hop=1, address=LEASE["gateway"] if gw else None, rtt_ms=0.7 if gw else None)]
        if gw and self.cfg["internet_ok"]:
            hops += [dict(hop=2, address="100.64.0.1", rtt_ms=6.1),
                     dict(hop=3, address="198.51.100.9", rtt_ms=9.8),
                     dict(hop=4, address=host, rtt_ms=11.6)]
        else:
            hops += [dict(hop=n, address=None, rtt_ms=None) for n in (2, 3, 4)]
        return hops

    def dns_lookup(self, name: str, server: str | None) -> dict:
        server = server or (self.net or {}).get("dns", [None])[0]
        out = dict(ok=False, addresses=[], server=server, error=None, time_ms=None)
        if not server or not self._link_up() or not self.net:
            out["error"] = "no DNS server reachable"
        elif server.startswith(SUBNET):
            if self.cfg["dns_local_ok"]:
                out.update(ok=True, addresses=["93.184.215.14"], time_ms=4)
            else:
                out["error"] = "timeout"
        elif self._reachable(server):
            out.update(ok=True, addresses=["93.184.215.14"], time_ms=19)
        else:
            out["error"] = "timeout"
        return out

    def http_check(self, url: str) -> dict:
        out = dict(url=url, ok=False, status=None, time_ms=None, error=None, captive_portal=False)
        if self.cfg["captive"] and self._link_up() and self.net:
            out.update(status=302, time_ms=35, captive_portal=True, error="redirected to a sign-in page")
        elif not self._reachable("1.1.1.1"):
            out["error"] = "timeout"
        elif not self.cfg["dns_local_ok"]:
            out["error"] = "could not resolve host name"
        else:
            out.update(ok=True, status=204, time_ms=48)
        return out

    def arp_table(self) -> list[dict]:
        if not self._link_up() or not self.net:
            return []
        rows = [dict(address="10.20.30.10", mac="00:15:5d:01:0a:10", vendor="Microsoft (Hyper-V)"),
                dict(address="10.20.30.42", mac="3c:52:82:4b:19:7e", vendor="Hewlett Packard"),
                dict(address="10.20.30.61", mac="00:04:f2:9a:33:01", vendor="Polycom")]
        if self.cfg["gateway_ok"]:
            rows.insert(0, dict(address="10.20.30.1", mac="00:00:5e:00:01:1e", vendor="VRRP virtual router"))
        return rows

    def neighbors(self) -> list[dict]:
        l = self.cfg["lldp"]
        if not self._link_up() or not l:
            return []
        p = self.cfg["poe"]
        return [dict(protocol="LLDP", chassis_id="70:10:6f:3a:c2:00",
                     system_description="Managed access switch (simulated)",
                     poe_mdi=bool(p and p["kind"] == "ieee"), pse_allocated_w=None, **l)]

    def throughput(self, server: str, seconds: int) -> dict:
        if not self._link_up():
            raise HalError(f"iperf3 server {server} is not reachable: no link")
        l = self.cfg["link"]
        half = l["duplex"] == "half"
        rate = l["speed"] * (0.31 if half else 0.94)
        return dict(server=server, seconds=seconds, tx_mbps=round(rate), rx_mbps=round(rate * 0.99),
                    retransmits=1840 if half else 3)

    def capture(self, seconds: int) -> dict:
        return dict(file=None, packets=0,
                    note="Packet capture is not simulated: there are no real packets to save.")

    # -- Wi-Fi -------------------------------------------------------------
    def wifi_scan(self) -> list[dict]:
        def ap(ssid, bssid, freq, ch, width, rssi, sec, util=None, sta=None):
            return dict(ssid=ssid, bssid=bssid, freq=freq, channel=ch, width=width, rssi=rssi,
                        security=sec, util_pct=util, stations=sta)
        return [
            ap("Corp-WiFi", "a4:11:62:10:00:01", 2437, 6, 20, -47, "WPA3-Enterprise", 61, 23),
            ap("Corp-WiFi", "a4:11:62:10:00:02", 5180, 36, 80, -54, "WPA3-Enterprise", 22, 14),
            ap("Corp-Guest", "a4:11:62:10:00:03", 5180, 36, 80, -55, "WPA2-PSK"),
            ap("NeighborNet", "9c:3d:cf:aa:10:20", 2437, 6, 20, -66, "WPA2-PSK"),
            ap("Corp-WiFi", "a4:11:62:10:00:12", 5745, 149, 80, -70, "WPA3-Enterprise", 9, 4),
            ap("HP-Print-7B", "f4:39:09:22:19:7b", 2412, 1, 20, -72, "Open"),
            ap("Suite210", "08:36:c9:0b:77:10", 2462, 11, 20, -82, "WPA2-PSK", 35, 6),
        ]

    def wifi_status(self) -> dict:
        return dict(connected=True, ssid="Corp-WiFi", bssid="a4:11:62:10:00:02", freq=5180,
                    channel=36, rssi=-54, tx_rate_mbps=433, security="WPA3-Enterprise",
                    roam_events=[dict(from_bssid="a4:11:62:10:00:12", to_bssid="a4:11:62:10:00:02",
                                      rssi_before=-76, rssi_after=-54, seconds_ago=140)])
