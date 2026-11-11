import struct

import pytest

from netscope.net import parsers, poe

# Format taken from the kernel commit that added KSZ9131 cable test support.
CABLE_TEST = """Cable test started for device eth1.
Cable test completed for device eth1.
Pair A code OK
Pair B code Short within Pair
Pair B, fault length: 0.80m
Pair C code Open Circuit
Pair C, fault length: 12.40m
Pair D code Short to another pair
"""

ETHTOOL = """Settings for eth1:
\tSupported link modes:   10baseT/Half 10baseT/Full
\t                        100baseT/Half 100baseT/Full
\t                        1000baseT/Full
\tLink partner advertised link modes:  10baseT/Half 10baseT/Full
\t                                     100baseT/Half 100baseT/Full
\t                                     1000baseT/Full
\tLink partner advertised pause frame use: Symmetric
\tSpeed: 1000Mb/s
\tDuplex: Full
\tAuto-negotiation: on
\tMDI-X: off (auto)
\tLink detected: yes
"""

IW = """BSS a4:5e:60:11:22:30(on wlan0) -- associated
\tfreq: 5180
\tcapability: ESS Privacy SpectrumMgmt (0x0111)
\tsignal: -52.00 dBm
\tSSID: Corp-WiFi
\tRSN:\t * Version: 1
\t\t * Authentication suites: IEEE 802.1X SAE
\tBSS Load:
\t\t * station count: 14
\t\t * channel utilisation: 56/255
\tVHT operation:
\t\t * channel width: 1 (80 MHz)
BSS c8:d9:d2:00:7b:11(on wlan0)
\tfreq: 2412
\tcapability: ESS (0x0401)
\tsignal: -74.00 dBm
\tSSID: HP-Print-7B
BSS 10:da:43:9a:01:02(on wlan0)
\tfreq: 2437
\tcapability: ESS Privacy (0x0411)
\tsignal: -67.00 dBm
\tSSID: NeighborNet
\tRSN:\t * Version: 1
\t\t * Authentication suites: PSK
\tHT operation:
\t\t * secondary channel offset: above
"""


def test_cable_test_parser():
    r = parsers.parse_cable_test(CABLE_TEST)
    assert [(p["pair"], p["code"], p["length_m"]) for p in r] == [
        ("A", "ok", None), ("B", "short", 0.8), ("C", "open", 12.4), ("D", "cross_short", None)]
    assert r[1]["pins"] == "3-6"
    assert parsers.parse_cable_test("netlink error: Operation not supported") == []


def test_ethtool_link_parser():
    st = parsers.parse_ethtool_link(ETHTOOL)
    assert st["up"] and st["speed"] == 1000 and st["duplex"] == "full" and st["autoneg"]
    assert "1000baseT/Full" in st["partner_modes"]
    down = parsers.parse_ethtool_link("\tSpeed: Unknown!\n\tDuplex: Unknown! (255)\n\tLink detected: no\n")
    assert down == dict(up=False, speed=None, duplex=None, autoneg=False, mdix=None,
                        partner_modes=[])


def test_iw_scan_parser():
    aps = parsers.parse_iw_scan(IW)
    assert len(aps) == 3
    a = aps[0]
    assert (a["ssid"], a["channel"], a["rssi"], a["width"]) == ("Corp-WiFi", 36, -52, 80)
    assert a["security"] == "WPA3-Enterprise" and a["stations"] == 14 and a["util_pct"] == 22
    assert aps[1]["security"] == "Open" and aps[1]["channel"] == 1 and aps[1]["util_pct"] is None
    assert aps[2]["security"] == "WPA2-PSK" and aps[2]["width"] == 40


@pytest.mark.parametrize("freq,ch", [(2412, 1), (2437, 6), (2462, 11), (2484, 14), (5180, 36),
                                     (5745, 149), (5955, 1), (6115, 33)])
def test_freq_to_channel(freq, ch):
    assert parsers.freq_to_channel(freq) == ch


def _offer(xid: int) -> bytes:
    b = bytearray(240)
    b[0] = 2
    b[4:8] = struct.pack("!I", xid)
    b[16:20] = bytes([10, 20, 30, 117])
    b[236:240] = parsers.DHCP_MAGIC
    opts = bytes([53, 1, 2, 1, 4, 255, 255, 255, 0, 3, 4, 10, 20, 30, 1,
                  6, 8, 10, 20, 30, 10, 1, 1, 1, 1, 54, 4, 10, 20, 30, 1,
                  51, 4, 0, 1, 0x51, 0x80, 15, 12]) + b"corp.example" + bytes([255])
    return bytes(b) + opts


def test_dhcp_roundtrip():
    mac = bytes.fromhex("02aabbccddee")
    d = parsers.build_dhcp_discover(mac, 0x1234ABCD)
    assert len(d) >= 240 and d[0] == 1 and d[28:34] == mac and d[236:240] == parsers.DHCP_MAGIC
    assert d[10:12] == b"\x80\x00"  # broadcast flag: we have no address yet
    r = parsers.parse_dhcp_reply(_offer(0x1234ABCD))
    assert r == dict(xid=0x1234ABCD, address="10.20.30.117", type="OFFER", prefix=24,
                     gateway="10.20.30.1", dns=["10.20.30.10", "1.1.1.1"], server="10.20.30.1",
                     lease_s=86400, domain="corp.example")
    assert parsers.parse_dhcp_reply(b"\x00" * 300) is None
    assert parsers.parse_dhcp_reply(d) is None  # a request is not a reply


def test_dns_roundtrip():
    q = parsers.build_dns_query("example.com", 0xBEEF)
    assert q[:2] == b"\xbe\xef" and b"\x07example\x03com\x00" in q
    resp = (struct.pack("!HHHHHH", 0xBEEF, 0x8180, 1, 2, 0, 0) + q[12:]
            + b"\xc0\x0c" + struct.pack("!HHIH", 5, 1, 60, 2) + b"\xc0\x0c"
            + b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + bytes([93, 184, 215, 14]))
    assert parsers.parse_dns_response(resp, 0xBEEF) == dict(rcode="NOERROR",
                                                            addresses=["93.184.215.14"])
    nx = struct.pack("!HHHHHH", 0xBEEF, 0x8183, 1, 0, 0, 0) + q[12:]
    assert parsers.parse_dns_response(nx, 0xBEEF)["rcode"] == "NXDOMAIN"
    with pytest.raises(ValueError):
        parsers.parse_dns_response(resp, 0x0001)


def _tlv(t: int, v: bytes) -> bytes:
    return struct.pack("!H", (t << 9) | len(v)) + v


def test_lldp_parser():
    pdu = (_tlv(1, b"\x04" + bytes.fromhex("001c73aa1001")) + _tlv(2, b"\x05Gi1/0/17")
           + _tlv(3, b"\x00\x78") + _tlv(4, b"USER-DATA") + _tlv(5, b"IDF2-SW03")
           + _tlv(8, bytes([5, 1, 10, 20, 0, 23, 2, 0, 0, 0, 1, 0]))
           + _tlv(127, b"\x00\x80\xc2\x01" + struct.pack("!H", 30))
           + _tlv(127, b"\x00\x12\x0f\x02" + bytes([0x07, 1, 4, 0, 0, 0]) + struct.pack("!H", 255))
           + _tlv(0, b""))
    n = parsers.parse_lldp(pdu)
    assert n["system_name"] == "IDF2-SW03" and n["port_id"] == "Gi1/0/17"
    assert n["vlan"] == 30 and n["mgmt_address"] == "10.20.0.23"
    assert n["poe_mdi"] is True and n["pse_allocated_w"] == 25.5
    assert n["chassis_id"] == "00:1c:73:aa:10:01"


def test_cdp_parser():
    def t(typ, v):
        return struct.pack("!HH", typ, len(v) + 4) + v
    pkt = b"\x02\xb4\x00\x00" + t(1, b"IDF2-SW03") + t(3, b"GigabitEthernet1/0/17") + \
        t(0x0A, struct.pack("!H", 30))
    n = parsers.parse_cdp(pkt)
    assert (n["system_name"], n["port_id"], n["vlan"]) == ("IDF2-SW03", "GigabitEthernet1/0/17", 30)


def test_poe_tables_and_voltage_classes():
    assert poe.describe_class(4) == dict(poe_class=4, pse_w=30.0, pd_w=25.5, type=2,
                                         standard="802.3at")
    assert poe.describe_class(8)["pd_w"] == 71.3
    assert poe.classify_port_voltage(0.0, 0.1, False) == "none"
    assert poe.classify_port_voltage(4.4, 0.0, True) == "pse_probing"
    assert poe.classify_port_voltage(0.0, 24.1, False) == "passive"
    assert poe.classify_port_voltage(-48.0, 0.0, False) == "passive"


def test_sff8472_identity_and_diagnostics():
    import math
    a0 = bytearray(96)
    a0[0], a0[2], a0[3], a0[12] = 0x03, 0x07, 0x10, 103          # SFP, LC, 10GBASE-SR, 10.3 Gb/s
    a0[20:36] = b"ACME OPTICS     "
    a0[40:56] = b"AO-10G-SR       "
    a0[60:62] = struct.pack("!H", 850)
    a0[68:84] = b"SN12345         "
    a0[92] = 0x68                                                # diagnostics implemented
    a2 = bytearray(128)
    a2[32:34] = struct.pack("!H", 11220)                         # rx high alarm  +0.5 dBm
    a2[34:36] = struct.pack("!H", 407)                           # rx low alarm  -13.9 dBm
    a2[38:40] = struct.pack("!H", 1023)                          # rx low warn    -9.9 dBm
    a2[96:98] = struct.pack("!h", int(41.5 * 256))
    a2[102:104] = struct.pack("!H", 5754)                        # tx -2.4 dBm
    a2[104:106] = struct.pack("!H", 4898)                        # rx -3.1 dBm
    m = parsers.parse_sff8472(bytes(a0), bytes(a2))
    assert (m["vendor"], m["part_number"], m["serial"]) == ("ACME OPTICS", "AO-10G-SR", "SN12345")
    assert m["type"] == "10GBASE-SR" and m["wavelength_nm"] == 850 and m["connector"] == "LC"
    assert m["nominal_mbps"] == 10300 and m["ddm"] and m["temp_c"] == 41.5
    assert (m["tx_power_dbm"], m["rx_power_dbm"]) == (-2.4, -3.1)
    assert (m["rx_low_alarm_dbm"], m["rx_low_warn_dbm"], m["rx_high_alarm_dbm"]) == (-13.9, -9.9, 0.5)
    assert round(10 * math.log10(4898 / 10000), 1) == -3.1

    a2[104:106] = b"\0\0"                                        # no light at all
    assert parsers.parse_sff8472(bytes(a0), bytes(a2))["rx_power_dbm"] is None
    a0[92] = 0x00                                                # module without diagnostics
    plain = parsers.parse_sff8472(bytes(a0), bytes(a2))
    assert not plain["ddm"] and plain["rx_power_dbm"] is None
    a0[3], a0[6], a0[2] = 0x00, 0x02, 0x01                       # 1000BASE-LX, SC
    lx = parsers.parse_sff8472(bytes(a0))
    assert lx["type"] == "1000BASE-LX" and lx["connector"] == "SC"
    with pytest.raises(ValueError):
        parsers.parse_sff8472(b"\x03" * 10)
