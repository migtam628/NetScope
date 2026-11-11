"""Diagnostic tools.  Each tool takes (hal, params) and returns a TestResult.

Rules every tool follows:
  * never fabricate: if the HAL cannot measure something the result is
    NOT_TESTED with the reason;
  * tools marked disruptive refuse to run unless params["authorized"] is
    true (the UI asks the technician first; Auto Diagnose never sets it);
  * results inherit the HAL's provenance.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Callable

from ..cable import wiremap
from ..hal.base import Hal, HalError, HalUnsupported
from ..models import Status, TestResult
from ..net import poe as poe_tables

ToolFn = Callable[[Hal, dict], TestResult]


@dataclass
class Tool:
    id: str
    title: str
    category: str
    fn: ToolFn
    disruptive: bool = False
    params: tuple[tuple[str, str, object], ...] = ()  # (name, type, default)


TOOLS: dict[str, Tool] = {}


def tool(id: str, title: str, category: str, disruptive: bool = False, params=()):
    def deco(fn: ToolFn) -> ToolFn:
        TOOLS[id] = Tool(id, title, category, fn, disruptive, tuple(params))
        return fn
    return deco


def run_tool(hal: Hal, tool_id: str, params: dict | None = None) -> TestResult:
    t = TOOLS[tool_id]
    params = dict(params or {})
    for name, _, default in t.params:
        params.setdefault(name, default)
    res = TestResult(t.id, t.title, provenance=hal.provenance)
    if t.disruptive and not params.get("authorized"):
        res.summary = "Not run: this test can disrupt the network and needs explicit authorization."
        return res
    t0 = time.monotonic()
    try:
        out = t.fn(hal, params)
        out.started, out.provenance = res.started, hal.provenance
        res = out
    except HalUnsupported as e:
        res.status, res.summary = Status.NOT_TESTED, str(e)
    except HalError as e:
        res.status, res.summary = Status.FAIL, f"Measurement error: {e}"
        res.recommendations = ["Repeat the test. If it persists, run Settings > Self-test."]
    res.duration_s = round(time.monotonic() - t0, 3)
    return res


def _r(tid: str, **kw) -> TestResult:
    return TestResult(tid, TOOLS[tid].title, **kw)


# ---------------------------------------------------------------------------
# Cable
# ---------------------------------------------------------------------------
_FIX = {
    "short": "Re-terminate both ends; inspect for crushed cable or staples at the reported distance.",
    "open": "Check the punch-down / plug at both ends first (most opens are at a termination), "
            "then inspect the run at the TDR distance.",
    "reversed": "Re-terminate one end of the affected pair: its two conductors are swapped.",
    "crossed": "Re-terminate one end to the same standard (T568A or T568B) as the other end.",
    "miswire": "Re-terminate to T568A/B at both ends; conductors land on the wrong pins.",
    "split": "Re-terminate both ends keeping each twisted pair on its pin pair "
             "(1-2, 3-6, 4-5, 7-8). Split pairs pass continuity but fail at speed.",
    "resistive": "Look for water ingress, corrosion or damaged insulation; replace the run if it persists.",
}


@tool("cable", "Cable Test", "cable")
def cable_test(hal: Hal, p: dict) -> TestResult:
    res = _r("cable")
    v = hal.port_voltage_scan()
    vclass = poe_tables.classify_port_voltage(v["alt_a_v"], v["alt_b_v"], v["pulsing"])
    res.measurements.update(port_voltage=v, voltage_class=vclass)

    analysis = None
    if vclass == "passive":
        peak = max(abs(v["alt_a_v"]), abs(v["alt_b_v"]))
        res.findings.append(f"{peak:.1f} V DC is present on the cable (passive / non-802.3 "
                            f"power). DC wiremap was skipped to protect the measurement "
                            f"front end; TDR runs through the isolation transformer.")
    else:
        scan = hal.wiremap_scan()
        analysis = wiremap.analyse(scan["matrix"], scan.get("crosstalk_db"))
        res.measurements["wiremap"] = analysis.to_dict()
        res.measurements["crosstalk_db"] = scan.get("crosstalk_db")
        if vclass == "pse_probing":
            res.findings.append("A PoE switch/injector is probing this cable (low-voltage "
                                "802.3 detection pulses).")

    tdr = None
    try:
        tdr = hal.tdr()
        res.measurements["tdr"] = tdr
    except HalUnsupported as e:
        res.findings.append(f"TDR not available: {e}")

    by_pins = {t["pins"]: t for t in (tdr or [])}
    kinds: set[str] = set()
    if analysis:
        for f in analysis.faults:
            kinds.add(f["kind"])
            detail = f["detail"]
            pins = f["pins"]
            hit = next((t for name, t in by_pins.items()
                        if pins and {int(x) for x in name.split("-")} & set(pins)
                        and t["code"] in ("open", "short", "cross_short")
                        and t["length_m"] is not None), None)
            if hit and f["kind"] in ("open", "short"):
                detail += f" TDR places a fault about {hit['length_m']:.0f} m from this end."
            res.findings.append(detail)

    # With RT-1 or nothing at the far end, a healthy pair still reads "open":
    # that reflection is the end of the cable, not a fault.  Say so.
    if tdr and analysis and analysis.far_end in ("terminator", "open"):
        bad_pins = {p for f in analysis.faults if f["kind"] in ("open", "short") for p in f["pins"]}
        for t in tdr:
            if t["code"] == "open" and not {int(x) for x in t["pins"].split("-")} & bad_pins:
                t["meaning"] = "end of cable"

    # Length: pairs that end in an open at the far end (terminator or nothing).
    if tdr and analysis and analysis.far_end in ("terminator", "open"):
        lens = [t["length_m"] for t in tdr if t["code"] == "open" and t["length_m"] is not None]
        if lens and not kinds & {"open", "short"}:
            res.measurements["length_m"] = round(statistics.median(lens), 1)

    # TDR faults when the far end is live equipment (DC cannot see pin order).
    tdr_bad = []
    if tdr and (analysis is None or analysis.far_end == "equipment"):
        tdr_bad = [t for t in tdr if t["code"] != "ok"]
        for t in tdr_bad:
            where = f" at about {t['length_m']:.0f} m" if t["length_m"] is not None else ""
            res.findings.append(f"TDR: pair {t['pins']} reports {t['code'].replace('_', ' ')}{where}.")

    for k in sorted(kinds):
        res.recommendations.append(_FIX[k])

    if kinds:
        res.status = Status.FAIL
        res.summary = f"{len(analysis.faults)} wiring fault(s): " + ", ".join(sorted(kinds)) + "."
    elif analysis is None:
        res.status = Status.WARNING
        res.summary = "Powered cable: wiremap skipped, TDR only."
        res.recommendations.append("Disconnect the injector to run a full wiremap.")
    elif analysis.far_end == "terminator":
        tid = f" #{analysis.terminator_id}" if analysis.terminator_id else ""
        length = res.measurements.get("length_m")
        ltxt = f", about {length:.0f} m" if length is not None else ""
        if analysis.cable_type == "crossover":
            res.status = Status.WARNING
            res.summary = f"Crossover cable to RT-1{tid}{ltxt}."
            res.recommendations.append("Crossover cables work with auto-MDIX equipment but are "
                                       "non-standard for permanent links; replace if unintended.")
        else:
            res.status = Status.PASS
            res.summary = f"Wiremap correct to RT-1{tid}{ltxt}."
        if not analysis.split_checked:
            res.findings.append("Split-pair check not performed.")
    elif analysis.far_end == "equipment":
        n = len(analysis.equipment_pairs)
        hard = [t for t in tdr_bad if t["pair"] in ("A", "B")]
        if hard:
            res.status = Status.FAIL
            res.summary = "Fault on a data pair between here and the far-end equipment."
            res.recommendations.append(_FIX["open"])
        elif n < 4 or tdr_bad:
            res.status = Status.WARNING
            res.summary = (f"Continuity to far-end equipment on {n} of 4 pairs "
                           f"({', '.join(analysis.equipment_pairs)}).")
            res.findings.append("Either the far device is 10/100-only or pairs 4-5/7-8 are "
                                "open. Gigabit needs all four pairs.")
            res.recommendations.append("If gigabit is expected, test the run with an RT-1 "
                                       "terminator to check all eight conductors.")
        else:
            res.status = Status.PASS
            res.summary = "Continuity to far-end network equipment on all four pairs."
            res.findings.append("Pin order cannot be verified against live equipment; use an "
                                "RT-1 terminator for a full wiremap.")
    else:
        res.status = Status.WARNING
        res.summary = "No terminator or equipment detected at the far end; no shorts found."
        res.recommendations.append("Fit an RT-1 terminator at the far end for a full wiremap.")
        if "length_m" in res.measurements:
            res.summary += f" Cable is about {res.measurements['length_m']:.0f} m (open end)."
    res.findings.append("Continuity/TDR verification only. This is not a TIA/ISO "
                        "certification test.")
    return res


# ---------------------------------------------------------------------------
# Link
# ---------------------------------------------------------------------------
@tool("link", "Link Speed / Duplex", "network")
def link_test(hal: Hal, p: dict) -> TestResult:
    res = _r("link")
    st = hal.link_status()
    res.measurements.update(st)
    if not st["up"]:
        res.status, res.summary = Status.FAIL, "No Ethernet link."
        res.recommendations = [
            "Confirm the far end is patched to an active switch port.",
            "Check that the switch port is enabled (not shutdown / err-disabled).",
            "Run Cable Test to rule out the cable."]
        return res
    res.summary = f"Link up at {st['speed']} Mb/s {st['duplex']} duplex."
    res.status = Status.PASS
    if st["duplex"] == "half":
        res.status = Status.WARNING
        res.findings.append("Half duplex on a switched network almost always means a duplex "
                            "mismatch: the far port is forced to a fixed speed/duplex and is "
                            "not auto-negotiating.")
        res.recommendations.append("Set the switch port to auto-negotiate (or force both ends "
                                   "identically).")
    elif st["speed"] is not None and st["speed"] < 1000:
        res.status = Status.WARNING
        res.findings.append(f"Link negotiated {st['speed']} Mb/s, below gigabit.")
        res.recommendations.append("If gigabit is expected: check all four pairs with Cable "
                                   "Test and check the switch port speed setting.")
    return res


# ---------------------------------------------------------------------------
# PoE
# ---------------------------------------------------------------------------
@tool("poe", "PoE Analyzer", "poe",
      params=(("load_w", "number", 0), ("load_seconds", "number", 2)))
def poe_test(hal: Hal, p: dict) -> TestResult:
    res = _r("poe")
    st = hal.poe_status()
    res.measurements.update(st)
    if st["kind"] == "none":
        res.status, res.summary = Status.NOT_TESTED, "No PoE detected on this port."
        res.findings.append("The port did not respond to a valid PD signature and no DC "
                            "voltage is present.")
        return res
    if st["kind"] == "passive":
        res.status = Status.WARNING
        pairs = "4-5/7-8" if st.get("alt") != "A" else "1-2/3-6"
        res.summary = f"Passive PoE: {st['voltage_v']:.1f} V on pairs {pairs} (no 802.3 negotiation)."
        res.findings.append("Voltage is always present and is not negotiated. It can damage "
                            "equipment that is not designed for this injector.")
        res.recommendations.append("Label this drop. Only connect devices rated for this "
                                   "voltage and pinout.")
        return res
    if st.get("denied") or st["allocated_class"] is None:
        res.status = Status.FAIL
        res.summary = "PSE detected the tester but did not deliver power."
        res.findings.append("Detection succeeded but the port never reached operating voltage.")
        res.recommendations = [
            "Check the switch PoE budget (total allocated vs. available).",
            "Check the port's PoE admin state and per-port power limit.",
            "Look for a PoE fault/overload log entry on this port."]
        return res

    cls = poe_tables.describe_class(st["allocated_class"])
    res.measurements.update(cls)
    v = st["voltage_v"]
    vmin = poe_tables.PD_MIN_V[cls["type"]]
    res.summary = (f"{cls['standard']} Type {cls['type']}, class {cls['poe_class']}: "
                   f"{cls['pd_w']:g} W available at the device, {v:.1f} V"
                   f"{', 4-pair' if st['four_pair'] else ''}.")
    res.status = Status.PASS
    if not vmin <= v <= poe_tables.PD_MAX_V:
        res.status = Status.WARNING
        res.findings.append(f"Voltage {v:.1f} V is outside the {vmin:g}-{poe_tables.PD_MAX_V:g} V "
                            f"range for Type {cls['type']}.")

    load_w = float(p.get("load_w") or 0)
    if load_w > 0:
        if not p.get("authorized"):
            res.findings.append("Load test not run: needs authorization (it draws real power "
                                "from the switch's PoE budget).")
        else:
            load_w = min(load_w, cls["pd_w"])
            lt = hal.poe_load_test(load_w, float(p.get("load_seconds") or 2))
            res.measurements["load_test"] = lt
            if not lt["held"]:
                res.status = Status.FAIL
                res.findings.append(f"Port dropped power under a {load_w:g} W load "
                                    f"({lt.get('reason', 'power removed')}).")
                res.recommendations += [
                    "Check cable length and conductor quality (CCA cable has ~1.6x the resistance).",
                    "Check the switch per-port power limit and total budget."]
            else:
                drop = lt.get("no_load_v", v) - lt["voltage_v"]
                res.findings.append(f"Held {lt['power_w']:.1f} W: {lt['voltage_v']:.1f} V at "
                                    f"{lt['current_a'] * 1000:.0f} mA (drop {drop:.1f} V).")
                if lt["voltage_v"] < vmin:
                    res.status = Status.WARNING
                    res.findings.append(f"Voltage under load is below the {vmin:g} V minimum.")
                    res.recommendations.append("Shorten or replace the run; high loop "
                                               "resistance is starving the device.")
    return res


# ---------------------------------------------------------------------------
# IP layer
# ---------------------------------------------------------------------------
@tool("dhcp", "DHCP Discovery", "network")
def dhcp_test(hal: Hal, p: dict) -> TestResult:
    res = _r("dhcp")
    lease = hal.dhcp_discover()
    if not lease:
        res.status, res.summary = Status.FAIL, "No DHCP offer received."
        res.recommendations = [
            "Confirm the port's VLAN has a DHCP scope / relay (ip helper).",
            "Check for port security, 802.1X or MAC filtering on the switch port.",
            "Check whether the DHCP scope is exhausted.",
            "Try a static address to test the rest of the path."]
        return res
    res.measurements.update(lease)
    res.status = Status.PASS
    res.summary = (f"Offered {lease['address']}/{lease['prefix']}, gateway {lease['gateway']}, "
                   f"DNS {', '.join(lease['dns']) or 'none'}.")
    if not lease.get("gateway"):
        res.status = Status.WARNING
        res.findings.append("Lease has no default gateway (option 3).")
    if not lease.get("dns"):
        res.status = Status.WARNING
        res.findings.append("Lease has no DNS servers (option 6).")
    return res


@tool("static", "Static IP", "network",
      params=(("address", "text", ""), ("prefix", "number", 24), ("gateway", "text", ""),
              ("dns", "text", "1.1.1.1")))
def static_ip(hal: Hal, p: dict) -> TestResult:
    res = _r("static")
    cfg = hal.set_static(p["address"], int(p["prefix"]), p["gateway"],
                         [d.strip() for d in str(p["dns"]).split(",") if d.strip()])
    res.measurements.update(cfg)
    res.status, res.summary = Status.PASS, f"Static {cfg['address']}/{cfg['prefix']} applied."
    return res


@tool("ping", "Ping", "network", params=(("host", "text", "gateway"), ("count", "number", 5)))
def ping_test(hal: Hal, p: dict) -> TestResult:
    res = _r("ping")
    if p["host"] == "gateway":
        cfg = hal.net_config()
        if not cfg or not cfg.get("gateway"):
            res.summary = "No default gateway known yet (run DHCP or set a static address)."
            return res
        p["host"] = cfg["gateway"]
    out = hal.ping(p["host"], int(p["count"]))
    res.measurements.update(out)
    loss = out["loss_pct"]
    if out["received"] == 0:
        res.status, res.summary = Status.FAIL, f"{p['host']}: no replies ({out['sent']} sent)."
    elif loss > 0:
        res.status = Status.WARNING
        res.summary = f"{p['host']}: {loss:.0f}% loss, avg {out['rtt_avg_ms']} ms."
    else:
        res.status = Status.PASS
        res.summary = f"{p['host']}: 0% loss, avg {out['rtt_avg_ms']} ms."
    return res


@tool("traceroute", "Traceroute", "network", params=(("host", "text", "1.1.1.1"),))
def traceroute_test(hal: Hal, p: dict) -> TestResult:
    res = _r("traceroute")
    hops = hal.traceroute(p["host"])
    res.measurements["hops"] = hops
    if not hops:
        res.status, res.summary = Status.FAIL, "No route: not connected to a network."
        return res
    reached = hops[-1]["address"] == p["host"]
    last = next((h for h in reversed(hops) if h["address"]), None)
    res.status = Status.PASS if reached else Status.FAIL
    res.summary = (f"Reached {p['host']} in {len(hops)} hops." if reached else
                   f"Path stops after {last['address'] if last else 'the first hop'}.")
    return res


@tool("dns", "DNS Lookup", "network",
      params=(("name", "text", "example.com"), ("server", "text", "")))
def dns_test(hal: Hal, p: dict) -> TestResult:
    res = _r("dns")
    out = hal.dns_lookup(p["name"], p.get("server") or None)
    res.measurements.update(out)
    if out["ok"]:
        res.status = Status.PASS
        res.summary = f"{p['name']} -> {', '.join(out['addresses'])} via {out['server']}."
    else:
        res.status = Status.FAIL
        res.summary = f"{out['server'] or 'DNS'} did not resolve {p['name']} ({out['error']})."
    return res


@tool("http", "HTTP/HTTPS Check", "network",
      params=(("url", "text", "https://www.gstatic.com/generate_204"),))
def http_test(hal: Hal, p: dict) -> TestResult:
    res = _r("http")
    out = hal.http_check(p["url"])
    res.measurements.update(out)
    if out.get("captive_portal"):
        res.status, res.summary = Status.WARNING, "Captive portal is intercepting web traffic."
        res.recommendations.append("Complete the portal sign-in, or use a port/SSID without one.")
    elif out["ok"]:
        res.status = Status.PASS
        res.summary = f"HTTP {out['status']} in {out['time_ms']:.0f} ms."
    else:
        res.status, res.summary = Status.FAIL, f"Request failed: {out['error']}."
    return res


@tool("arp", "ARP Table", "discovery")
def arp_test(hal: Hal, p: dict) -> TestResult:
    res = _r("arp")
    rows = hal.arp_table()
    res.measurements["entries"] = rows
    res.status = Status.PASS if rows else Status.WARNING
    res.summary = f"{len(rows)} neighbour(s) on the local segment."
    macs: dict[str, list[str]] = {}
    for r in rows:
        macs.setdefault(r["address"], []).append(r["mac"])
    for ip, ms in macs.items():
        if len(set(ms)) > 1:
            res.status = Status.WARNING
            res.findings.append(f"{ip} answers from {len(set(ms))} MAC addresses: possible "
                                f"duplicate IP.")
    return res


@tool("neighbors", "Switch Port / VLAN (LLDP/CDP)", "discovery")
def neighbor_test(hal: Hal, p: dict) -> TestResult:
    res = _r("neighbors")
    ns = hal.neighbors()
    res.measurements["neighbors"] = ns
    if not ns:
        res.status = Status.WARNING
        res.summary = "No LLDP/CDP advertisement heard."
        res.findings.append("The switch may have LLDP/CDP disabled, or this is an unmanaged "
                            "switch. VLAN cannot be identified without it.")
        return res
    n = ns[0]
    res.status = Status.PASS
    vlan = f", VLAN {n['vlan']}" if n.get("vlan") else ""
    res.summary = f"{n['protocol']}: {n['system_name']} port {n['port_id']}{vlan}."
    return res


@tool("throughput", "Throughput (iperf3)", "network", disruptive=True,
      params=(("server", "text", ""), ("seconds", "number", 5)))
def throughput_test(hal: Hal, p: dict) -> TestResult:
    res = _r("throughput")
    if not p.get("server"):
        res.summary = "Needs the address of an iperf3 server on the network."
        return res
    out = hal.throughput(p["server"], int(p["seconds"]))
    res.measurements.update(out)
    res.status = Status.PASS
    res.summary = f"TX {out['tx_mbps']} Mb/s, RX {out['rx_mbps']} Mb/s to {out['server']}."
    if out.get("retransmits", 0) > 100:
        res.status = Status.WARNING
        res.findings.append(f"{out['retransmits']} TCP retransmits: errors or duplex mismatch.")
    return res


@tool("capture", "Packet Capture", "network", disruptive=True,
      params=(("seconds", "number", 5),))
def capture_test(hal: Hal, p: dict) -> TestResult:
    res = _r("capture")
    out = hal.capture(int(p["seconds"]))
    res.measurements.update(out)
    if not out.get("file"):
        res.summary = out.get("note", "No capture produced.")
        return res
    res.status, res.summary = Status.PASS, f"{out['packets']} packets saved to {out['file']}."
    return res


# ---------------------------------------------------------------------------
# Fiber (SFP+ port)
# ---------------------------------------------------------------------------
_FIBER_CLEAN = ("Clean both connector end-faces and inspect them; a dirty connector is the most "
                "common cause of low light.")


@tool("fiber", "Fiber Port (SFP+)", "fiber")
def fiber_test(hal: Hal, p: dict) -> TestResult:
    """Module identity, received light and link.  Light levels are the module's own
    diagnostics (typically +/-3 dB), not a calibrated optical power meter."""
    res = _r("fiber")
    st = hal.sfp_status()
    res.measurements.update(st)
    if not st.get("present"):
        res.summary = "No SFP module fitted in the fiber port."
        return res
    ident = f"{st.get('type') or 'SFP'} {st.get('wavelength_nm') or '?'} nm ({st.get('vendor') or 'unknown vendor'})"
    rx, lo_alarm, lo_warn = st.get("rx_power_dbm"), st.get("rx_low_alarm_dbm"), st.get("rx_low_warn_dbm")
    hi_alarm = st.get("rx_high_alarm_dbm")
    res.findings.append("Light levels are the module's own readings (typically +/-3 dB), not a "
                        "calibrated power meter.")
    if not st.get("ddm"):
        res.findings.append("This module does not report optical power; only link state is known.")

    no_light = bool(st.get("los")) or (st.get("ddm") and rx is None) or \
        (rx is not None and lo_alarm is not None and rx < lo_alarm)
    if no_light:
        res.status = Status.FAIL
        level = "no light" if rx is None or st.get("los") else f"{rx} dBm"
        res.summary = f"{ident}: received light too low ({level})."
        res.recommendations = [
            "Check transmit/receive are not swapped: swap the two fibers at one end.",
            _FIBER_CLEAN,
            "Confirm the far end is powered, its port is enabled and it uses the same fiber type "
            "and wavelength as this module.",
            "If light is still missing, the fiber is broken or badly bent: test it with a light "
            "source or fault locator."]
        return res
    if not st.get("link"):
        res.status = Status.FAIL
        res.summary = f"{ident}: light is received ({rx} dBm) but there is no link."
        res.findings.append("Light without link means the two ends do not agree on the signal, "
                            "not that the fiber is broken.")
        res.recommendations = [
            "Check both ends are the same speed (a 1 Gb port will not link to a 10 Gb module).",
            "Check both ends use the same wavelength and fiber type; single-fiber modules must be "
            "a matched pair.",
            "Check the far port is not administratively down."]
        return res
    speed = st.get("speed")
    res.status = Status.PASS
    res.summary = f"{ident}: link up at {speed} Mb/s" + (f", receiving {rx} dBm." if rx is not None else ".")
    if rx is not None and hi_alarm is not None and rx > hi_alarm:
        res.status = Status.WARNING
        res.findings.append(f"Received light {rx} dBm is above the module's maximum ({hi_alarm} dBm).")
        res.recommendations.append("Fit an attenuator: a long-reach module on a short fiber can "
                                   "overload the receiver.")
    elif rx is not None and lo_warn is not None and rx < lo_warn:
        res.status = Status.WARNING
        res.findings.append(f"Received light {rx} dBm is below the module's warning level "
                            f"({lo_warn} dBm): the link works but has little margin.")
        res.recommendations += [_FIBER_CLEAN, "Check for tight bends and count the patch points "
                                              "in the run; each connector costs light."]
    if speed and speed >= 10000:
        res.findings.append("This port links at 10 Gb, but the tester can only pass about "
                            "3.5-6 Gb/s of traffic. A throughput test here cannot prove a full "
                            "10 Gb circuit.")
    return res


# ---------------------------------------------------------------------------
# Wi-Fi
# ---------------------------------------------------------------------------
def channel_summary(aps: list[dict]) -> list[dict]:
    chans: dict[tuple[str, int], dict] = {}
    for ap in aps:
        band = "2.4" if ap["freq"] < 3000 else "5" if ap["freq"] < 5950 else "6"
        c = chans.setdefault((band, ap["channel"]), dict(
            band=band, channel=ap["channel"], aps=0, strongest_rssi=-200, util_pct=None))
        c["aps"] += 1
        c["strongest_rssi"] = max(c["strongest_rssi"], ap["rssi"] if ap["rssi"] is not None else -200)
        if ap.get("util_pct") is not None:
            c["util_pct"] = max(c["util_pct"] or 0, ap["util_pct"])
    return sorted(chans.values(), key=lambda c: (float(c["band"]), c["channel"]))


@tool("wifi_scan", "Wi-Fi Scan", "wifi")
def wifi_scan(hal: Hal, p: dict) -> TestResult:
    res = _r("wifi_scan")
    aps = sorted(hal.wifi_scan(), key=lambda a: -(a["rssi"] or -200))
    chans = channel_summary(aps)
    res.measurements.update(aps=aps, channels=chans)
    res.status = Status.PASS if aps else Status.WARNING
    res.summary = f"{len(aps)} BSSIDs on {len(chans)} channels."
    off = sorted({c["channel"] for c in chans if c["band"] == "2.4" and c["channel"] not in (1, 6, 11)})
    if off:
        res.status = Status.WARNING
        res.findings.append(f"2.4 GHz APs on non-standard channel(s) {off}: these overlap two "
                            f"of channels 1/6/11.")
    for c in chans:
        if c["util_pct"] is not None and c["util_pct"] >= 50:
            res.status = Status.WARNING
            res.findings.append(f"Channel {c['channel']} ({c['band']} GHz) reports "
                                f"{c['util_pct']}% utilisation (AP-advertised BSS Load).")
    for a in aps:
        if a["security"] in ("Open", "WEP", "WPA"):
            res.findings.append(f"'{a['ssid'] or '(hidden)'}' uses weak/no security ({a['security']}).")
    res.findings.append("Utilisation is what APs advertise (BSS Load); APs that do not "
                        "advertise it show no value. Non-Wi-Fi interference is not measured.")
    return res


@tool("wifi_status", "Wi-Fi Connection", "wifi")
def wifi_status(hal: Hal, p: dict) -> TestResult:
    res = _r("wifi_status")
    st = hal.wifi_status()
    res.measurements.update(st)
    if not st.get("connected"):
        res.status, res.summary = Status.NOT_TESTED, "Not connected to a Wi-Fi network."
        return res
    rssi = st["rssi"]
    res.summary = f"{st['ssid']} ch {st['channel']} at {rssi} dBm, {st['tx_rate_mbps']} Mb/s."
    res.status = Status.PASS if rssi >= -67 else Status.WARNING if rssi >= -75 else Status.FAIL
    if rssi < -67:
        res.findings.append("Signal below -67 dBm: marginal for voice/video; expect roaming "
                            "and rate drops.")
    for ev in st.get("roam_events", []):
        if ev["rssi_before"] < -72:
            res.findings.append(f"Roamed late: left {ev['from_bssid']} at {ev['rssi_before']} dBm "
                                f"(sticky client or roaming threshold too low).")
    return res


@tool("battery", "Battery", "device")
def battery(hal: Hal, p: dict) -> TestResult:
    res = _r("battery")
    b = hal.battery()
    res.measurements.update(b)
    res.status = Status.PASS
    res.summary = f"{b['percent']}%, health {b['health_pct']}%, {b['temp_c']} C."
    if b["health_pct"] < 80:
        res.status = Status.WARNING
        res.recommendations.append("Battery is below 80% of design capacity: plan a replacement.")
    if b["temp_c"] > 50:
        res.status = Status.WARNING
        res.findings.append("Battery is hot; charging is suspended above 45 C.")
    return res
