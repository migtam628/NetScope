"""Local rules-based troubleshooting assistant.

Works entirely offline.  Input is the set of TestResults from a session;
output is a diagnosis: which layer the problem is in, why, what probably
caused it and what to do next.  Rules are ordered from the physical layer
upward and the first failing layer becomes the primary finding - a broken
cable explains a DNS failure, never the other way round.

Rules only reason from results that were actually measured.  NOT_TESTED is
never treated as a pass or a fail.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from ..models import Status, TestResult


@dataclass
class Diagnosis:
    layer: str = "none"
    headline: str = ""
    explanation: str = ""
    likely_causes: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    completion_note: str = ""
    source: str = "local-rules"

    def to_dict(self) -> dict:
        return asdict(self)


def _st(r: dict[str, TestResult], key: str) -> Status:
    return r[key].status if key in r else Status.NOT_TESTED


def _m(r: dict[str, TestResult], key: str) -> dict:
    return r[key].measurements if key in r else {}


def diagnose(results: dict[str, TestResult]) -> Diagnosis:
    d = Diagnosis()
    S = Status
    cable, link, speed = _st(results, "cable"), _st(results, "link"), _st(results, "link_speed")
    dhcp, gw, dns, inet = (_st(results, k) for k in ("dhcp", "gateway", "dns", "internet"))
    poe = _st(results, "poe")
    nb = (_m(results, "neighbors").get("neighbors") or [None])[0]
    port = f"{nb['system_name']} port {nb['port_id']}" if nb else "the switch port"

    # ---- primary finding: lowest failing layer ---------------------------
    if cable == S.FAIL:
        d.layer = "cable"
        d.headline = "Cabling fault"
        d.explanation = results["cable"].summary + " " + " ".join(
            f for f in results["cable"].findings if "certification" not in f)
        d.likely_causes = ["Bad termination at a jack, patch panel or plug",
                           "Cable damaged along the run (crush, staple, rodent, pulled too hard)"]
        d.next_steps = list(results["cable"].recommendations) + [
            "Re-run Cable Test with an RT-1 terminator after the repair."]
    elif link == S.FAIL:
        d.layer = "switch_port"
        d.headline = "No link: cable looks sound, far end is not bringing the port up"
        far = _m(results, "cable").get("wiremap", {}).get("far_end")
        if far == "open":
            d.explanation = ("Nothing is connected at the far end of this cable (TDR sees an "
                             "open end and there is no equipment signature).")
            d.likely_causes = ["Drop is not patched to a switch at the closet",
                               "Wrong patch-panel port"]
            d.next_steps = ["Trace and patch the drop at the IDF/MDF.",
                            "Use an RT-1 terminator ID to confirm which panel port this is."]
        else:
            d.explanation = ("The cable reaches network equipment but the port does not "
                             "negotiate a link.")
            d.likely_causes = ["Switch port administratively shut down or err-disabled",
                               "Port forced to a speed this tester/cable cannot do",
                               "Failed switch port"]
            d.next_steps = ["Check port status on the switch (shutdown, err-disable, port-security).",
                            "Move the patch to a known-good port to confirm."]
    elif dhcp == S.FAIL:
        d.layer = "vlan_ip"
        d.headline = "Link is up but no DHCP address"
        vlan = nb.get("vlan") if nb else None
        d.explanation = (f"Physical layer and link are good on {port}"
                         + (f" (untagged VLAN {vlan})" if vlan else "")
                         + ", but no DHCP server answered.")
        d.likely_causes = [
            (f"VLAN {vlan} has no DHCP scope or relay" if vlan
             else "Port is in a VLAN with no DHCP scope or relay"),
            "802.1X / port security / MAC filtering is blocking this device",
            "DHCP scope exhausted or server down"]
        d.next_steps = [
            (f"Confirm VLAN {vlan} is the intended VLAN for this drop." if vlan
             else "Identify the port's VLAN on the switch (LLDP/CDP was not heard)."),
            "Check the DHCP server/relay for that VLAN and its free leases.",
            "Assign a static address in the expected subnet and re-run to test the rest of the path."]
    elif gw == S.FAIL:
        d.layer = "gateway"
        d.headline = "Address obtained but the default gateway does not answer"
        cfg = _m(results, "dhcp")
        d.explanation = (f"DHCP gave {cfg.get('address')} with gateway {cfg.get('gateway')}, "
                         f"but the gateway does not reply to ping or ARP.")
        d.likely_causes = ["Router / L3 switch interface for this VLAN is down",
                           "Wrong gateway in the DHCP scope",
                           "Client isolation or an ACL blocking the gateway (ping only)"]
        d.next_steps = ["Check ARP Table: if the gateway has a MAC entry it is alive and only "
                        "ICMP is filtered.",
                        "Verify the VLAN interface (SVI) / router port is up.",
                        "Compare the scope's gateway with the real router address."]
    elif dns == S.FAIL:
        d.layer = "dns"
        dm = _m(results, "dns")
        if dm.get("public_ok"):
            d.headline = "Local DNS server is failing; the internet path is fine"
            d.explanation = (f"{dm.get('server')} did not resolve names, but a public resolver "
                             f"({dm.get('public_server')}) answered.")
            d.likely_causes = ["Internal DNS server down or its service stopped",
                               "Firewall/ACL between this VLAN and the DNS server",
                               "DHCP scope hands out a stale DNS address"]
            d.next_steps = [f"Check the DNS service on {dm.get('server')}.",
                            "Verify the DNS addresses in the DHCP scope.",
                            "As a workaround, clients can use another resolver if policy allows."]
        else:
            d.headline = "DNS resolution failing on every resolver tried"
            d.explanation = "Neither the assigned DNS server nor a public resolver answered."
            d.likely_causes = ["UDP/TCP 53 blocked by a firewall", "Upstream internet outage"]
            d.next_steps = ["Check the Internet step: if raw IP also fails, the fault is upstream.",
                            "Check firewall rules for outbound DNS."]
    elif inet == S.FAIL:
        d.layer = "upstream"
        d.headline = "LAN is healthy; the fault is upstream"
        d.explanation = ("Cable, link, DHCP, gateway and local DNS all work, but hosts on the "
                         "internet are unreachable.")
        d.likely_causes = ["ISP / WAN circuit down", "Firewall or edge router fault",
                           "No default route / NAT problem on the router"]
        d.next_steps = ["Run Traceroute to see the last hop that answers.",
                        "Check WAN status on the router/firewall and the modem/ONT lights.",
                        "Contact the ISP with the last responding hop."]
    elif inet == S.WARNING and _m(results, "internet").get("captive_portal"):
        d.layer = "upstream"
        d.headline = "Captive portal is intercepting traffic"
        d.explanation = "The network answers web requests with a sign-in page."
        d.next_steps = ["Complete the portal sign-in or use a network without one."]
    else:
        tested = [k for k in ("cable", "link", "dhcp", "gateway", "dns", "internet")
                  if _st(results, k) != S.NOT_TESTED]
        if "internet" in tested and inet == S.PASS:
            d.headline = "No fault found: wired path works end to end"
            d.explanation = f"Every test from the cable to the internet passed on {port}."
        elif tested:
            d.headline = "No fault found in the tests that could run"
            d.explanation = "Tests run: " + ", ".join(tested) + "."
        else:
            d.headline = "Nothing was tested"

    # ---- secondary notes ----------------------------------------------------
    if d.layer != "cable" and cable == S.WARNING:
        d.notes.append("Cable: " + results["cable"].summary)
    if speed == S.WARNING:
        lm = _m(results, "link_speed")
        if lm.get("duplex") == "half":
            d.notes.append("Half duplex: the switch port is probably forced to a fixed "
                           "speed/duplex. Set it to auto. Expect slow, lossy transfers until fixed.")
        elif lm.get("speed", 1000) < 1000:
            wm = _m(results, "cable").get("wiremap", {})
            if wm.get("far_end") == "equipment" and len(wm.get("equipment_pairs", [])) < 4:
                d.notes.append(f"Link is only {lm.get('speed')} Mb/s because pairs 4-5/7-8 are "
                               f"not continuous. Repair the cable for gigabit.")
            else:
                d.notes.append(f"Link is {lm.get('speed')} Mb/s. Check the switch port speed "
                               f"setting and whether the far device is gigabit-capable.")
    if poe == S.FAIL:
        d.notes.append("PoE: " + results["poe"].summary + " Check the switch PoE budget and "
                       "the port's PoE configuration.")
        if d.layer == "none":
            d.layer, d.headline = "poe", "Data works but PoE power is not delivered"
            d.explanation = results["poe"].summary
            d.next_steps = list(results["poe"].recommendations)
    elif poe == S.WARNING:
        d.notes.append("PoE: " + results["poe"].summary)
    elif poe == S.PASS:
        d.notes.append("PoE: " + results["poe"].summary)
    if nb and nb.get("vlan"):
        d.notes.append(f"Switch port: {nb['system_name']} {nb['port_id']}, VLAN {nb['vlan']}"
                       + (f" ({nb['port_description']})" if nb.get("port_description") else "") + ".")

    d.completion_note = completion_note(results, d)
    return d


def completion_note(results: dict[str, TestResult], d: Diagnosis) -> str:
    """Plain-ASCII field-service note the technician can paste into a work order."""
    prov = {r.provenance for r in results.values()}
    lines = [f"NetScope X1 auto-diagnosis, {time.strftime('%Y-%m-%d %H:%M')}."]
    if prov == {"simulated"}:
        lines.append("*** SIMULATED DATA - NOT A FIELD MEASUREMENT ***")
    order = ["cable", "link", "link_speed", "poe", "neighbors", "dhcp", "gateway", "dns", "internet"]
    for k in order:
        if k in results:
            r = results[k]
            lines.append(f"- {r.title}: {r.status.value.replace('_', ' ')} - {r.summary}")
    lines.append(f"Finding: {d.headline}.")
    if d.likely_causes:
        lines.append("Likely cause: " + d.likely_causes[0] + ".")
    if d.next_steps:
        lines.append("Recommended action: " + d.next_steps[0])
    lines.append("Action taken: ")
    return "\n".join(lines)
