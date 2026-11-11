"""Auto Diagnose: one-button wired workflow.

Order (each step only runs if the steps it depends on make it meaningful;
otherwise it is recorded as NOT_TESTED with the reason):

  1 cable        voltage safety scan, DC wiremap, TDR
  2 link         Ethernet link establishment
  3 poe          PoE identification (no load test - that needs authorization)
  4 link_speed   speed / duplex verification
  5 neighbors    LLDP/CDP listen (passive) for switch, port and VLAN
  6 dhcp         DHCP discovery
  7 gateway      ping default gateway
  8 dns          resolve via assigned DNS; compare with a public resolver
  9 internet     ping + HTTP to the internet

Nothing here transmits more than a normal client would: no load tests, no
throughput floods, no scans of other hosts.
"""
from __future__ import annotations

from typing import Callable

from ..hal.base import Hal
from ..models import Status, TestResult, not_tested, worst
from . import rules
from .tools import run_tool

PUBLIC_DNS = "1.1.1.1"
PUBLIC_IP = "1.1.1.1"
TEST_NAME = "example.com"
TEST_URL = "https://www.gstatic.com/generate_204"

STEPS = [("cable", "Cable Test"), ("link", "Ethernet Link"), ("poe", "PoE Analyzer"),
         ("link_speed", "Speed / Duplex"), ("neighbors", "Switch Port / VLAN"),
         ("dhcp", "DHCP Discovery"), ("gateway", "Gateway"), ("dns", "DNS Resolution"),
         ("internet", "Internet")]
TITLES = dict(STEPS)


def run(hal: Hal, on_step: Callable[[TestResult], None] | None = None,
        on_start: Callable[[str], None] | None = None) -> dict:
    results: dict[str, TestResult] = {}

    def begin(key: str) -> None:
        if on_start:
            on_start(key)

    def done(key: str, r: TestResult) -> TestResult:
        r.test_id, r.title = key, TITLES[key]
        results[key] = r
        if on_step:
            on_step(r)
        return r

    def skip(key: str, why: str) -> None:
        done(key, not_tested(key, TITLES[key], why, hal.provenance))

    begin("cable")
    cable = done("cable", run_tool(hal, "cable"))
    if cable.measurements.get("wiremap", {}).get("far_end") == "terminator":
        for k, _ in STEPS[1:]:
            skip(k, "Far end is an RT-1 terminator, not network equipment.")
        return _finish(results)

    begin("link")
    raw = run_tool(hal, "link")
    up = bool(raw.measurements.get("up"))
    link = TestResult("link", TITLES["link"], provenance=raw.provenance,
                      measurements=dict(raw.measurements), duration_s=raw.duration_s)
    if raw.status == Status.NOT_TESTED:
        link.summary = raw.summary
    elif up:
        link.status, link.summary = Status.PASS, "Link established."
    else:
        link.status, link.summary = Status.FAIL, raw.summary
        link.recommendations = raw.recommendations
    done("link", link)

    begin("poe")
    done("poe", run_tool(hal, "poe"))

    begin("link_speed")
    if up:
        sp = TestResult("link_speed", TITLES["link_speed"], raw.status, raw.summary,
                        dict(raw.measurements), list(raw.findings), list(raw.recommendations),
                        raw.provenance)
        done("link_speed", sp)
    else:
        skip("link_speed", "No link.")

    if not up:
        for k in ("neighbors", "dhcp", "gateway", "dns", "internet"):
            skip(k, "No link.")
        return _finish(results)

    begin("neighbors")
    done("neighbors", run_tool(hal, "neighbors"))

    begin("dhcp")
    dhcp = done("dhcp", run_tool(hal, "dhcp"))
    if dhcp.status in (Status.FAIL, Status.NOT_TESTED):
        for k in ("gateway", "dns", "internet"):
            skip(k, "No IP configuration.")
        return _finish(results)
    lease = dhcp.measurements

    begin("gateway")
    if lease.get("gateway"):
        gw = done("gateway", run_tool(hal, "ping", {"host": lease["gateway"], "count": 4}))
    else:
        skip("gateway", "Lease has no default gateway.")
        gw = results["gateway"]

    begin("dns")
    servers = lease.get("dns") or []
    if servers:
        dns = run_tool(hal, "dns", {"name": TEST_NAME, "server": servers[0]})
        if dns.status == Status.FAIL:
            pub = run_tool(hal, "dns", {"name": TEST_NAME, "server": PUBLIC_DNS})
            dns.measurements["public_server"] = PUBLIC_DNS
            dns.measurements["public_ok"] = pub.status == Status.PASS
            dns.findings.append(f"Public resolver {PUBLIC_DNS}: "
                                f"{'answered' if pub.status == Status.PASS else 'no answer'}.")
        done("dns", dns)
    else:
        skip("dns", "Lease has no DNS servers.")

    begin("internet")
    if gw.status == Status.FAIL:
        skip("internet", "Gateway unreachable.")
    else:
        ping = run_tool(hal, "ping", {"host": PUBLIC_IP, "count": 4})
        http = run_tool(hal, "http", {"url": TEST_URL})
        inet = TestResult("internet", TITLES["internet"], provenance=hal.provenance,
                          measurements=dict(ping=ping.measurements, http=http.measurements,
                                            captive_portal=http.measurements.get("captive_portal")),
                          duration_s=round(ping.duration_s + http.duration_s, 3))
        tested = [x for x in (ping, http) if x.status != Status.NOT_TESTED]
        if not tested:
            inet.summary = "Could not be tested on this backend."
        elif any(x.status == Status.PASS for x in tested):
            inet.status = Status.WARNING if http.status == Status.WARNING else Status.PASS
            inet.summary = "Internet reachable (" + "; ".join(
                x.summary for x in tested if x.status == Status.PASS) + ")"
            if ping.status == Status.FAIL and http.status == Status.PASS:
                inet.findings.append("ICMP to the internet is filtered; web traffic works.")
        else:
            inet.status = Status.WARNING if http.status == Status.WARNING else Status.FAIL
            inet.summary = http.summary if http.status == Status.WARNING else \
                "No reply from the internet (ping and HTTP both failed)."
        done("internet", inet)
    return _finish(results)


def _finish(results: dict[str, TestResult]) -> dict:
    diag = rules.diagnose(results)
    ordered = [results[k] for k, _ in STEPS if k in results]
    core = [r.status for r in ordered if r.test_id != "poe" or r.status == Status.FAIL]
    return dict(overall=worst(core).value,
                results=[r.to_dict() for r in ordered],
                diagnosis=diag.to_dict(),
                provenance=sorted({r.provenance for r in ordered}))
