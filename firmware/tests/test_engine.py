"""Engine, auto-diagnose and rules against simulator scenarios."""
import pytest

from netscope.engine import autodiag, cloud_ai
from netscope.engine.tools import TOOLS, run_tool
from netscope.hal.base import Hal
from netscope.hal.sim import SCENARIOS, SimHal
from netscope.models import Status


def diag(scenario):
    out = autodiag.run(SimHal(scenario))
    return out, {r["test_id"]: r for r in out["results"]}


# scenario -> (overall, diagnosis layer, {step: status})
EXPECT = {
    "healthy": ("PASS", "none", {"cable": "PASS", "link": "PASS", "poe": "PASS",
                                 "dhcp": "PASS", "dns": "PASS", "internet": "PASS"}),
    "rt1_pass": ("PASS", "none", {"cable": "PASS", "link": "NOT_TESTED"}),
    "open_pair": ("FAIL", "cable", {"cable": "FAIL", "link": "NOT_TESTED"}),
    "short": ("FAIL", "cable", {"cable": "FAIL"}),
    "reversed": ("FAIL", "cable", {"cable": "FAIL"}),
    "split": ("FAIL", "cable", {"cable": "FAIL"}),
    "two_pair_100": ("WARNING", "none", {"cable": "WARNING", "link_speed": "WARNING",
                                         "internet": "PASS"}),
    "no_link": ("FAIL", "switch_port", {"cable": "PASS", "link": "FAIL", "dhcp": "NOT_TESTED"}),
    "duplex": ("WARNING", "none", {"link_speed": "WARNING"}),
    "no_dhcp": ("FAIL", "vlan_ip", {"link": "PASS", "dhcp": "FAIL", "gateway": "NOT_TESTED",
                                    "internet": "NOT_TESTED"}),
    "gateway_down": ("FAIL", "gateway", {"dhcp": "PASS", "gateway": "FAIL",
                                         "internet": "NOT_TESTED"}),
    "dns_fail": ("FAIL", "dns", {"gateway": "PASS", "dns": "FAIL", "internet": "PASS"}),
    "no_internet": ("FAIL", "upstream", {"gateway": "PASS", "dns": "PASS", "internet": "FAIL"}),
    "passive_poe": ("WARNING", "none", {"cable": "WARNING", "poe": "WARNING"}),
    "poe_denied": ("FAIL", "poe", {"poe": "FAIL", "internet": "PASS"}),
    "poe_bt": ("PASS", "none", {"poe": "PASS"}),
    "poe_sag": ("PASS", "none", {"poe": "PASS"}),
}


def test_every_scenario_has_an_expectation():
    assert set(EXPECT) == set(SCENARIOS)


@pytest.mark.parametrize("scenario", sorted(EXPECT))
def test_autodiag(scenario):
    overall, layer, steps = EXPECT[scenario]
    out, r = diag(scenario)
    assert out["overall"] == overall
    assert out["diagnosis"]["layer"] == layer
    for k, st in steps.items():
        assert r[k]["status"] == st, (k, r[k]["summary"])
    assert [x["test_id"] for x in out["results"]] == [k for k, _ in autodiag.STEPS]
    assert out["provenance"] == ["simulated"]
    assert "SIMULATED DATA" in out["diagnosis"]["completion_note"]


def test_failures_do_not_cascade_into_false_failures():
    """A cable fault must leave upper layers NOT_TESTED, never FAIL."""
    _, r = diag("open_pair")
    assert all(r[k]["status"] == "NOT_TESTED" for k in ("dhcp", "gateway", "dns", "internet"))


def test_dns_failure_is_localised_with_public_resolver():
    out, r = diag("dns_fail")
    assert r["dns"]["measurements"]["public_ok"] is True
    assert "Local DNS" in out["diagnosis"]["headline"]


def test_two_pair_note_explains_100mb():
    out, _ = diag("two_pair_100")
    assert any("pairs 4-5/7-8" in n for n in out["diagnosis"]["notes"])


def test_fault_distance_reported():
    r = run_tool(SimHal("open_pair"), "cable")
    assert any("about 18 m" in f or "about 17 m" in f or "about 19 m" in f for f in r.findings)
    good = run_tool(SimHal("rt1_pass"), "cable")
    assert good.status == Status.PASS and abs(good.measurements["length_m"] - 42) < 1.5
    assert good.measurements["wiremap"]["terminator_id"] == 3


def test_cable_result_never_claims_certification():
    for s in SCENARIOS:
        r = run_tool(SimHal(s), "cable")
        assert any("not a TIA/ISO certification" in f for f in r.findings)


def test_passive_poe_skips_dc_wiremap():
    r = run_tool(SimHal("passive_poe"), "cable")
    assert "wiremap" not in r.measurements and r.status == Status.WARNING


def test_disruptive_tools_need_authorization():
    hal = SimHal("healthy")
    for tid, t in TOOLS.items():
        if t.disruptive:
            r = run_tool(hal, tid, {"server": "10.20.30.10"})
            assert r.status == Status.NOT_TESTED and "authorization" in r.summary
    ok = run_tool(hal, "throughput", {"server": "10.20.30.10", "authorized": True})
    assert ok.status == Status.PASS and ok.measurements["tx_mbps"] > 900


def test_poe_load_test_gated_then_measured():
    hal = SimHal("healthy")
    gated = run_tool(hal, "poe", {"load_w": 20})
    assert "load_test" not in gated.measurements
    assert any("needs authorization" in f for f in gated.findings)
    run = run_tool(hal, "poe", {"load_w": 20, "authorized": True})
    assert run.measurements["load_test"]["held"] and run.status == Status.PASS
    capped = run_tool(hal, "poe", {"load_w": 90, "authorized": True})
    assert capped.measurements["load_test"]["requested_w"] == 25.5  # never above the class


def test_poe_sag_under_load_is_flagged():
    r = run_tool(SimHal("poe_sag"), "poe", {"load_w": 25.5, "authorized": True})
    assert r.status in (Status.WARNING, Status.FAIL)


def test_poe_bt_and_denied():
    bt = run_tool(SimHal("poe_bt"), "poe")
    assert bt.measurements["type"] == 4 and bt.measurements["pd_w"] == 71.3
    assert run_tool(SimHal("poe_denied"), "poe").status == Status.FAIL


def test_unsupported_hal_gives_not_tested_not_fake_data():
    hal = Hal()
    for tid in TOOLS:
        r = run_tool(hal, tid, {"authorized": True, "server": "x", "address": "1.2.3.4",
                                "gateway": "1.2.3.1"})
        assert r.status == Status.NOT_TESTED, tid
        assert r.measurements == {}, tid
    out = autodiag.run(hal)
    assert out["overall"] == "NOT_TESTED"
    assert out["diagnosis"]["headline"] == "Nothing was tested"


def test_static_ip_path():
    hal = SimHal("no_dhcp")
    assert run_tool(hal, "ping", {"host": "gateway"}).status == Status.NOT_TESTED
    run_tool(hal, "static", {"address": "10.20.30.50", "prefix": 24, "gateway": "10.20.30.1"})
    assert run_tool(hal, "ping", {"host": "gateway"}).status == Status.PASS


def test_wifi_scan_findings():
    r = run_tool(SimHal(), "wifi_scan")
    assert len(r.measurements["aps"]) == 7
    chans = {(c["band"], c["channel"]): c for c in r.measurements["channels"]}
    assert chans[("2.4", 6)]["aps"] == 2 and chans[("2.4", 6)]["util_pct"] == 61
    assert any("61% utilisation" in f for f in r.findings)
    assert any("HP-Print-7B" in f and "Open" in f for f in r.findings)


def test_cloud_ai_is_optional_and_redacts(monkeypatch):
    for k in ("NETSCOPE_AI_URL", "NETSCOPE_AI_KEY", "NETSCOPE_AI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert not cloud_ai.configured()
    with pytest.raises(RuntimeError):
        cloud_ai.analyse([], None)
    out, _ = diag("dns_fail")
    req = cloud_ai.build_request(out["results"], out["diagnosis"])
    text = req["messages"][0]["content"]
    assert "IDF2-SW03" not in text and "10.20.30.117" not in text
    assert "10.x.x.117" in text and "1.1.1.1" in text
