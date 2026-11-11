"""LinuxHal glue, exercised with canned tool output and a fake coprocessor.

This checks parsing and plumbing only.  It is not a substitute for running
the backend on a real network (docs/15, step 1).
"""
import json
import socket
import struct
import threading

import pytest

from netscope.engine.tools import run_tool
from netscope.hal import coproc as cp
from netscope.hal import linux
from netscope.hal.base import HalError, HalUnsupported
from netscope.models import Status
from netscope.net import parsers

PING_OK = """PING 10.20.30.1 (10.20.30.1) from 10.20.30.117 eth0: 56(84) bytes of data.
64 bytes from 10.20.30.1: icmp_seq=1 ttl=64 time=0.412 ms

--- 10.20.30.1 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 603ms
rtt min/avg/max/mdev = 0.398/0.451/0.520/0.047 ms
"""
PING_LOST = """PING 10.20.30.1 (10.20.30.1) from 10.20.30.117 eth0: 56(84) bytes of data.

--- 10.20.30.1 ping statistics ---
4 packets transmitted, 0 received, 100% packet loss, time 3060ms
"""
TRACE = """traceroute to 1.1.1.1 (1.1.1.1), 20 hops max, 60 byte packets
 1  10.20.30.1  0.612 ms
 2  *
 3  198.51.100.9  9.801 ms
 4  1.1.1.1  11.640 ms
"""
ETHTOOL = """Settings for eth0:
	Supported ports: [ TP ]
	Link partner advertised link modes:  10baseT/Half 10baseT/Full
	                                     100baseT/Half 100baseT/Full
	                                     1000baseT/Full
	Link partner advertised pause frame use: Symmetric
	Speed: 1000Mb/s
	Duplex: Full
	Auto-negotiation: on
	MDI-X: off (auto)
	Link detected: yes
"""
CABLE_TEST = """Cable test started for device eth0.
Cable test completed for device eth0.
Pair A code OK
Pair B code OK
Pair C code Open Circuit
Pair C, fault length: 17.60m
Pair D code Open Circuit
Pair D, fault length: 17.80m
"""
IW_LINK = """Connected to a4:11:62:10:00:02 (on wlan0)
	SSID: Corp-WiFi
	freq: 5180.0
	RX: 1234 bytes (10 packets)
	signal: -54 dBm
	rx bitrate: 433.3 MBit/s VHT-MCS 9 80MHz short GI VHT-NSS 1
	tx bitrate: 390.0 MBit/s VHT-MCS 8 80MHz short GI VHT-NSS 1
"""


@pytest.fixture
def hal(monkeypatch):
    calls = []

    def fake_run(cmd, timeout=20.0):
        calls.append(cmd)
        return fake_run.out.get(cmd[0], "") if not callable(fake_run.out.get(cmd[0])) \
            else fake_run.out[cmd[0]](cmd)
    fake_run.out = {}
    monkeypatch.setattr(linux, "_run", fake_run)
    h = linux.LinuxHal("eth0", "wlan0")
    h.calls, h.out = calls, fake_run.out
    return h


def test_host_backend_identity(hal):
    assert hal.provenance == "host" and hal.name == "linux"
    assert hal.device_info()["model"].startswith("Linux host")


def test_front_end_functions_are_unsupported_without_coprocessor(hal):
    for fn in (hal.battery, hal.port_voltage_scan, hal.wiremap_scan, hal.poe_status):
        with pytest.raises(HalUnsupported):
            fn()
    with pytest.raises(HalUnsupported):
        hal.poe_load_test(10, 2)
    r = run_tool(hal, "poe")
    assert r.status == Status.NOT_TESTED and r.measurements == {} and r.provenance == "host"


def test_ping(hal):
    hal.out["ping"] = PING_OK
    p = hal.ping("10.20.30.1", 4)
    assert (p["sent"], p["received"], p["loss_pct"]) == (4, 4, 0.0)
    assert (p["rtt_min_ms"], p["rtt_avg_ms"], p["rtt_max_ms"]) == (0.398, 0.451, 0.52)
    assert "-I" in hal.calls[-1] and "eth0" in hal.calls[-1]
    hal.out["ping"] = PING_LOST
    p = hal.ping("10.20.30.1", 4)
    assert p["received"] == 0 and p["loss_pct"] == 100.0 and p["rtt_avg_ms"] is None
    assert run_tool(hal, "ping", {"host": "10.20.30.1"}).status == Status.FAIL
    hal.out["ping"] = "ping: connect: Network is unreachable\n"
    with pytest.raises(HalError):
        hal.ping("10.20.30.1", 4)


def test_traceroute_does_not_mistake_the_banner_for_a_hop(hal):
    hal.out["traceroute"] = TRACE
    hops = hal.traceroute("1.1.1.1")
    assert [h["hop"] for h in hops] == [1, 2, 3, 4]
    assert hops[1] == dict(hop=2, address=None, rtt_ms=None)
    assert hops[3] == dict(hop=4, address="1.1.1.1", rtt_ms=11.64)
    assert run_tool(hal, "traceroute", {"host": "1.1.1.1"}).status == Status.PASS


def test_link_and_tdr(hal):
    hal.out["ethtool"] = lambda cmd: CABLE_TEST if "--cable-test" in cmd else ETHTOOL
    st = hal.link_status()
    assert st["up"] and st["speed"] == 1000 and st["duplex"] == "full"
    assert "1000baseT/Full" in st["partner_modes"]
    pairs = hal.tdr()
    assert [(p["pins"], p["code"], p["length_m"]) for p in pairs] == [
        ("1-2", "ok", None), ("3-6", "ok", None), ("4-5", "open", 17.6), ("7-8", "open", 17.8)]
    hal.out["ethtool"] = "netlink error: Operation not supported\n"
    with pytest.raises(HalUnsupported):
        hal.tdr()


def test_net_config_and_arp(hal):
    def ip(cmd):
        if "addr" in cmd:
            return json.dumps([{"ifname": "eth0", "addr_info": [
                {"family": "inet", "local": "10.20.30.117", "prefixlen": 24}]}])
        if "route" in cmd:
            return json.dumps([{"dst": "default", "gateway": "10.20.30.1", "dev": "eth0"}])
        return json.dumps([{"dst": "10.20.30.1", "lladdr": "00:00:5e:00:01:1e", "state": ["REACHABLE"]},
                           {"dst": "10.20.30.9", "state": ["FAILED"]},
                           {"dst": "fe80::1", "lladdr": "00:00:5e:00:01:1e"}])
    hal.out["ip"] = ip
    assert hal.net_config() == dict(address="10.20.30.117", prefix=24, gateway="10.20.30.1", dns=[])
    assert hal.arp_table() == [dict(address="10.20.30.1", mac="00:00:5e:00:01:1e", vendor=None)]
    hal.out["ip"] = "[]"
    assert hal.net_config() is None


def test_throughput_and_wifi_status(hal, monkeypatch):
    def iperf(cmd):
        return json.dumps({"end": {"sum_sent": {"bits_per_second": 941e6, "retransmits": 2},
                                   "sum_received": {"bits_per_second": 938e6}}})
    hal.out["iperf3"] = iperf
    t = hal.throughput("10.20.30.10", 5)
    assert t["tx_mbps"] == 941 and t["rx_mbps"] == 938 and t["retransmits"] == 2
    hal.out["iperf3"] = json.dumps({"error": "unable to connect to server"})
    with pytest.raises(HalError, match="unable to connect"):
        hal.throughput("10.20.30.10", 5)

    monkeypatch.setattr(linux.os.path, "exists", lambda p: True)
    hal.out["iw"] = IW_LINK
    w = hal.wifi_status()
    assert w["connected"] and w["ssid"] == "Corp-WiFi" and w["channel"] == 36
    assert w["rssi"] == -54 and w["tx_rate_mbps"] == 390.0
    hal.out["iw"] = "Not connected.\n"
    assert hal.wifi_status() == dict(connected=False)


def test_missing_tool_is_unsupported_not_a_crash(monkeypatch):
    monkeypatch.setattr(linux.shutil, "which", lambda name: None)
    h = linux.LinuxHal("eth0", None)
    r = run_tool(h, "link")
    assert r.status == Status.NOT_TESTED and "not installed" in r.summary


def _can_bind_lo() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"lo")
        s.close()
        return True
    except (OSError, AttributeError):
        return False


@pytest.mark.skipif(not _can_bind_lo(), reason="needs Linux and CAP_NET_RAW")
def test_dns_lookup_over_a_real_socket():
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 53535))
    replies = iter(["answer", "servfail"])

    def serve():
        for kind in replies:
            q, peer = srv.recvfrom(512)
            head = q[:2] + (b"\x81\x80" if kind == "answer" else b"\x81\x82")
            if kind == "answer":
                rr = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + bytes([93, 184, 215, 14])
                srv.sendto(head + struct.pack("!HHHH", 1, 1, 0, 0) + q[12:] + rr, peer)
            else:
                srv.sendto(head + struct.pack("!HHHH", 1, 0, 0, 0) + q[12:], peer)
    threading.Thread(target=serve, daemon=True).start()

    h = linux.LinuxHal("lo", None)
    real = socket.socket.sendto
    # The HAL always talks to port 53; redirect to the test server.
    orig = socket.socket.sendto

    class S(socket.socket):
        def sendto(self, data, addr):
            return orig(self, data, (addr[0], 53535))
    import netscope.hal.linux as mod
    mod.socket.socket, keep = S, mod.socket.socket
    try:
        ok = h.dns_lookup("example.com", "127.0.0.1")
        bad = h.dns_lookup("example.com", "127.0.0.1")
    finally:
        mod.socket.socket = keep
        srv.close()
    assert real is orig
    assert ok["ok"] and ok["addresses"] == ["93.184.215.14"] and ok["time_ms"] is not None
    assert not bad["ok"] and bad["error"] == "SERVFAIL"


# ---- coprocessor path ---------------------------------------------------
class FakeMcu:
    """Answers like the STM32 would, using the payload layouts in docs/13."""

    def __init__(self, vscan_mv=(0, 0, 0)):
        self.out, self.log, self.vscan = b"", [], vscan_mv

    def write(self, data):
        (cmd, seq, payload), _ = cp.decode(data)
        self.log.append((cmd, payload))
        from netscope.cable.model import CableModel, simulate_matrix
        reply = {
            cp.CMD_PING: b"\x00\x01\x00",
            cp.CMD_RELAY: b"",
            cp.CMD_VSCAN: struct.pack("<iiB", *self.vscan),
            cp.CMD_WIREMAP: cp.pack_wiremap(simulate_matrix(CableModel(30, terminator_id=5))),
            cp.CMD_XTALK: struct.pack("<6h", *[-4400] * 6),
            cp.CMD_POE_STATUS: struct.pack("<iBBB", 53400, 1, 4, 0),
            cp.CMD_POE_LOAD: struct.pack("<iiiB", 51500, 388, 53400, 1),
            cp.CMD_BATTERY: struct.pack("<BHhhBHBH", 78, 3870, -950, 315, 97, 41, 0, 462),
        }[cmd]
        self.out += cp.encode(cmd, seq, reply)

    def read(self, n):
        d, self.out = self.out[:n], self.out[n:]
        return d


def _with_mcu(hal, mcu):
    hal.mcu = cp.Coproc(mcu)
    hal.provenance = "hardware-uncalibrated"
    return hal


def test_front_end_through_the_protocol(hal):
    mcu = FakeMcu()
    _with_mcu(hal, mcu)
    hal.out["ethtool"] = "netlink error: Operation not supported\n"
    r = run_tool(hal, "cable")
    assert r.status == Status.PASS and r.provenance == "hardware-uncalibrated"
    assert r.measurements["wiremap"]["terminator_id"] == 5
    cmds = [c for c, _ in mcu.log]
    # relay goes to TEST only around the scan and always returns to LINK
    i = cmds.index(cp.CMD_WIREMAP)
    assert mcu.log[i - 1] == (cp.CMD_RELAY, bytes([cp.RELAY_TEST]))
    assert mcu.log[-1] == (cp.CMD_RELAY, bytes([cp.RELAY_LINK]))
    assert any("TDR not available" in f for f in r.findings)

    p = run_tool(hal, "poe", {"load_w": 20, "authorized": True})
    assert p.status == Status.PASS and p.measurements["pd_w"] == 25.5
    lt = p.measurements["load_test"]
    assert lt["held"] and lt["voltage_v"] == 51.5 and lt["current_a"] == 0.388
    assert (cp.CMD_POE_LOAD, struct.pack("<IH", 20000, 2000)) in mcu.log
    assert hal.battery()["percent"] == 78 and hal.battery()["time_to_empty_min"] == 462


def test_relay_returns_to_link_even_when_the_scan_is_refused(hal):
    class Refusing(FakeMcu):
        def write(self, data):
            (cmd, seq, payload), _ = cp.decode(data)
            if cmd == cp.CMD_WIREMAP:
                self.log.append((cmd, payload))
                self.out += cp.encode(cp.CMD_ERROR, seq, bytes([3]))
            else:
                super().write(data)
    mcu = Refusing()
    _with_mcu(hal, mcu)
    with pytest.raises(cp.ProtoError, match="unsafe voltage"):
        hal.wiremap_scan()
    assert mcu.log[-1] == (cp.CMD_RELAY, bytes([cp.RELAY_LINK]))


def test_passive_poe_never_switches_the_relay(hal):
    mcu = FakeMcu(vscan_mv=(0, 24100, 0))
    _with_mcu(hal, mcu)
    hal.out["ethtool"] = CABLE_TEST.replace("Open Circuit", "OK")
    r = run_tool(hal, "cable")
    assert r.status == Status.WARNING and "wiremap" not in r.measurements
    assert cp.CMD_RELAY not in [c for c, _ in mcu.log]
    assert parsers.parse_cable_test(hal.out["ethtool"])[2]["code"] == "ok"
