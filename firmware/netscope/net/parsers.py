"""Pure parsers and packet builders (no I/O) so they can be unit-tested.

Covers: ethtool text, iw scan text, DHCP, DNS, LLDP, CDP.
"""
from __future__ import annotations

import ipaddress
import re
import struct

# --------------------------------------------------------------------------
# ethtool
# --------------------------------------------------------------------------
_CABLE_CODES = {
    "ok": "ok",
    "open circuit": "open",
    "short within pair": "short",
    "short to another pair": "cross_short",
}
_PAIR_PINS = {"A": "1-2", "B": "3-6", "C": "4-5", "D": "7-8"}


def parse_cable_test(text: str) -> list[dict]:
    """Parse `ethtool --cable-test <dev>` output."""
    pairs: dict[str, dict] = {}
    for line in text.splitlines():
        m = re.match(r"\s*Pair ([A-D]) code (.+?)\s*$", line)
        if m:
            code = _CABLE_CODES.get(m.group(2).strip().lower(), "unknown")
            pairs[m.group(1)] = dict(pair=m.group(1), pins=_PAIR_PINS[m.group(1)],
                                     code=code, length_m=None)
            continue
        m = re.match(r"\s*Pair ([A-D]),? fault length: ([\d.]+)m", line)
        if m and m.group(1) in pairs:
            pairs[m.group(1)]["length_m"] = float(m.group(2))
    return [pairs[k] for k in sorted(pairs)]


def parse_ethtool_link(text: str) -> dict:
    """Parse `ethtool <dev>` output."""
    def field(name: str) -> str | None:
        m = re.search(rf"^\s*{name}:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else None

    up = field("Link detected") == "yes"
    speed_s, duplex_s = field("Speed"), field("Duplex")
    m = re.match(r"(\d+)Mb/s", speed_s or "")
    partner = []
    block = re.search(r"Link partner advertised link modes:(.*?)(?:\n\s*Link partner advertised pause|\Z)",
                      text, re.S)
    if block:
        partner = re.findall(r"\d+base\w+/\w+", block.group(1))
    return dict(
        up=up,
        speed=int(m.group(1)) if (m and up) else None,
        duplex=(duplex_s or "").lower() if up and duplex_s in ("Full", "Half") else None,
        autoneg=field("Auto-negotiation") == "on",
        mdix=field("MDI-X"),
        partner_modes=partner,
    )


# --------------------------------------------------------------------------
# Wi-Fi
# --------------------------------------------------------------------------
def freq_to_channel(freq: int) -> int:
    if freq == 2484:
        return 14
    if 2412 <= freq <= 2472:
        return (freq - 2407) // 5
    if 5160 <= freq <= 5885:
        return (freq - 5000) // 5
    if 5955 <= freq <= 7115:
        return (freq - 5950) // 5
    return 0


def parse_iw_scan(text: str) -> list[dict]:
    """Parse `iw dev <wlan> scan` output."""
    aps: list[dict] = []
    cur: dict | None = None
    rsn = wpa = privacy = sae = eap = False

    def close() -> None:
        nonlocal cur
        if cur is None:
            return
        if rsn:
            base = "WPA3" if sae else "WPA2"
            cur["security"] = f"{base}-Enterprise" if eap else (
                "WPA3-SAE" if sae else "WPA2-PSK")
        elif wpa:
            cur["security"] = "WPA"
        elif privacy:
            cur["security"] = "WEP"
        else:
            cur["security"] = "Open"
        aps.append(cur)
        cur = None

    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"BSS ([0-9a-f:]{17})", line)
        if m and raw.startswith("BSS"):
            close()
            rsn = wpa = privacy = sae = eap = False
            cur = dict(ssid="", bssid=m.group(1), freq=0, channel=0, width=20, rssi=None,
                       security="Open", util_pct=None, stations=None)
            continue
        if cur is None:
            continue
        if line.startswith("freq:"):
            cur["freq"] = int(float(line.split()[1]))
            cur["channel"] = freq_to_channel(cur["freq"])
        elif line.startswith("signal:"):
            cur["rssi"] = round(float(line.split()[1]))
        elif line.startswith("SSID:"):
            cur["ssid"] = line[5:].strip()
        elif line.startswith("capability:") and "Privacy" in line:
            privacy = True
        elif line.startswith("RSN:"):
            rsn = True
        elif line.startswith("WPA:"):
            wpa = True
        elif "Authentication suites:" in line:
            sae = sae or "SAE" in line
            eap = eap or "802.1X" in line
        elif line.startswith("* station count:"):
            cur["stations"] = int(line.split(":")[1])
        elif line.startswith("* channel utilisation:"):
            num = int(line.split(":")[1].split("/")[0])
            cur["util_pct"] = round(num * 100 / 255)
        elif line.startswith("* channel width:"):
            m = re.search(r"\((\d+) MHz\)", line)
            if m:
                cur["width"] = max(cur["width"], int(m.group(1)))
        elif line.startswith("* secondary channel offset:") and "no secondary" not in line:
            cur["width"] = max(cur["width"], 40)
    close()
    return aps


# --------------------------------------------------------------------------
# DHCP
# --------------------------------------------------------------------------
DHCP_MAGIC = b"\x63\x82\x53\x63"
DHCP_TYPES = {1: "DISCOVER", 2: "OFFER", 3: "REQUEST", 5: "ACK", 6: "NAK"}


def build_dhcp_discover(mac: bytes, xid: int) -> bytes:
    """BOOTP/DHCP payload (UDP data) for a DHCPDISCOVER."""
    if len(mac) != 6:
        raise ValueError("mac must be 6 bytes")
    hdr = struct.pack("!BBBBIHH4s4s4s4s", 1, 1, 6, 0, xid, 0, 0x8000,
                      b"\0" * 4, b"\0" * 4, b"\0" * 4, b"\0" * 4)
    hdr += mac + b"\0" * 10 + b"\0" * 192
    opts = bytes([53, 1, 1]) + bytes([55, 6, 1, 3, 6, 15, 51, 54]) + \
        bytes([61, 7, 1]) + mac + bytes([255])
    return hdr + DHCP_MAGIC + opts


def parse_dhcp_reply(data: bytes) -> dict | None:
    if len(data) < 240 or data[236:240] != DHCP_MAGIC or data[0] != 2:
        return None
    xid = struct.unpack("!I", data[4:8])[0]
    out: dict = dict(xid=xid, address=str(ipaddress.IPv4Address(data[16:20])), type=None,
                     prefix=None, gateway=None, dns=[], server=None, lease_s=None, domain=None)
    i = 240
    while i < len(data):
        code = data[i]
        if code == 255:
            break
        if code == 0:
            i += 1
            continue
        if i + 1 >= len(data):
            break
        ln = data[i + 1]
        val = data[i + 2:i + 2 + ln]
        i += 2 + ln
        if code == 53 and ln == 1:
            out["type"] = DHCP_TYPES.get(val[0], str(val[0]))
        elif code == 1 and ln == 4:
            out["prefix"] = bin(int.from_bytes(val, "big")).count("1")
        elif code == 3 and ln >= 4:
            out["gateway"] = str(ipaddress.IPv4Address(val[:4]))
        elif code == 6:
            out["dns"] = [str(ipaddress.IPv4Address(val[j:j + 4])) for j in range(0, ln - 3, 4)]
        elif code == 54 and ln == 4:
            out["server"] = str(ipaddress.IPv4Address(val))
        elif code == 51 and ln == 4:
            out["lease_s"] = int.from_bytes(val, "big")
        elif code == 15:
            out["domain"] = val.rstrip(b"\0").decode("ascii", "replace")
    return out


# --------------------------------------------------------------------------
# DNS
# --------------------------------------------------------------------------
def build_dns_query(name: str, txid: int, qtype: int = 1) -> bytes:
    q = struct.pack("!HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    for label in name.rstrip(".").split("."):
        raw = label.encode("idna")
        if not 0 < len(raw) < 64:
            raise ValueError(f"bad DNS label in {name!r}")
        q += bytes([len(raw)]) + raw
    return q + b"\0" + struct.pack("!HH", qtype, 1)


def _skip_name(data: bytes, i: int) -> int:
    while i < len(data):
        ln = data[i]
        if ln == 0:
            return i + 1
        if ln & 0xC0 == 0xC0:
            return i + 2
        i += 1 + ln
    raise ValueError("truncated DNS name")


def parse_dns_response(data: bytes, txid: int) -> dict:
    if len(data) < 12:
        raise ValueError("short DNS response")
    rid, flags, qd, an, _, _ = struct.unpack("!HHHHHH", data[:12])
    if rid != txid:
        raise ValueError("DNS transaction id mismatch")
    rcode = flags & 0xF
    i = 12
    for _ in range(qd):
        i = _skip_name(data, i) + 4
    addrs = []
    for _ in range(an):
        i = _skip_name(data, i)
        rtype, _, _, rdlen = struct.unpack("!HHIH", data[i:i + 10])
        i += 10
        if rtype == 1 and rdlen == 4:
            addrs.append(str(ipaddress.IPv4Address(data[i:i + 4])))
        elif rtype == 28 and rdlen == 16:
            addrs.append(str(ipaddress.IPv6Address(data[i:i + 16])))
        i += rdlen
    names = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 5: "REFUSED"}
    return dict(rcode=names.get(rcode, str(rcode)), addresses=addrs)


# --------------------------------------------------------------------------
# LLDP / CDP
# --------------------------------------------------------------------------
def parse_lldp(payload: bytes) -> dict:
    """Parse an LLDPDU (bytes after the 0x88cc ethertype)."""
    out: dict = dict(protocol="LLDP", system_name=None, port_id=None, port_description=None,
                     vlan=None, mgmt_address=None, system_description=None, poe_mdi=None,
                     chassis_id=None, pse_allocated_w=None)
    i = 0
    while i + 2 <= len(payload):
        head = struct.unpack("!H", payload[i:i + 2])[0]
        typ, ln = head >> 9, head & 0x1FF
        val = payload[i + 2:i + 2 + ln]
        i += 2 + ln
        if typ == 0:
            break
        if typ == 1 and ln > 1:
            out["chassis_id"] = val[1:].hex(":") if val[0] == 4 else val[1:].decode("utf-8", "replace")
        elif typ == 2 and ln > 1:
            sub = val[0]
            out["port_id"] = val[1:].hex(":") if sub == 3 else val[1:].decode("utf-8", "replace")
        elif typ == 4:
            out["port_description"] = val.decode("utf-8", "replace")
        elif typ == 5:
            out["system_name"] = val.decode("utf-8", "replace")
        elif typ == 6:
            out["system_description"] = val.decode("utf-8", "replace")
        elif typ == 8 and ln >= 6 and val[1] == 1 and val[0] == 5:
            out["mgmt_address"] = str(ipaddress.IPv4Address(val[2:6]))
        elif typ == 127 and ln >= 4:
            oui, sub = val[:3], val[3]
            if oui == b"\x00\x80\xc2" and sub == 1 and ln >= 6:
                out["vlan"] = struct.unpack("!H", val[4:6])[0]
            elif oui == b"\x00\x12\x0f" and sub == 2 and ln >= 7:
                out["poe_mdi"] = bool(val[4] & 0x02)  # PSE MDI power supported
                if ln >= 12:
                    out["pse_allocated_w"] = struct.unpack("!H", val[10:12])[0] / 10
    return out


def parse_cdp(payload: bytes) -> dict:
    """Parse a CDP packet (bytes after the LLC/SNAP header)."""
    out: dict = dict(protocol="CDP", system_name=None, port_id=None, port_description=None,
                     vlan=None, mgmt_address=None, system_description=None, poe_mdi=None)
    i = 4  # version, ttl, checksum
    while i + 4 <= len(payload):
        typ, ln = struct.unpack("!HH", payload[i:i + 4])
        if ln < 4:
            break
        val = payload[i + 4:i + ln]
        i += ln
        if typ == 0x0001:
            out["system_name"] = val.decode("utf-8", "replace")
        elif typ == 0x0003:
            out["port_id"] = val.decode("utf-8", "replace")
        elif typ == 0x0006:
            out["system_description"] = val.decode("utf-8", "replace")
        elif typ == 0x000A and len(val) >= 2:
            out["vlan"] = struct.unpack("!H", val[:2])[0]
        elif typ == 0x001A:
            out["poe_mdi"] = True
    return out


# --------------------------------------------------------------------------
# SFP / SFP+ module EEPROM (SFF-8472)
# --------------------------------------------------------------------------
_SFP_CONNECTOR = {0x01: "SC", 0x07: "LC", 0x0B: "optical pigtail", 0x21: "copper pigtail",
                  0x22: "RJ45", 0x23: "no separable connector"}


def _dbm(raw: int) -> float | None:
    """SFF-8472 optical power: unsigned, 0.1 uW per count."""
    import math
    return None if raw == 0 else round(10 * math.log10(raw / 10000.0), 1)


def parse_sff8472(a0: bytes, a2: bytes | None = None) -> dict:
    """Decode the identity page (I2C 0x50) and, if given, the diagnostics page (0x51)."""
    if len(a0) < 96:
        raise ValueError("SFP identity page must be at least 96 bytes")

    def text(lo: int, hi: int) -> str:
        return a0[lo:hi].decode("ascii", "replace").strip()

    ten_g, one_g = a0[3], a0[6]
    kind = ("10GBASE-SR" if ten_g & 0x10 else "10GBASE-LR" if ten_g & 0x20 else
            "10GBASE-LRM" if ten_g & 0x40 else "10GBASE-ER" if ten_g & 0x80 else
            "1000BASE-SX" if one_g & 0x01 else "1000BASE-LX" if one_g & 0x02 else
            "1000BASE-CX" if one_g & 0x04 else "1000BASE-T" if one_g & 0x08 else "unknown")
    out = dict(present=True, vendor=text(20, 36), part_number=text(40, 56), serial=text(68, 84),
               type=kind, wavelength_nm=struct.unpack("!H", a0[60:62])[0] or None,
               connector=_SFP_CONNECTOR.get(a0[2], f"code 0x{a0[2]:02x}"),
               nominal_mbps=a0[12] * 100, ddm=bool(a0[92] & 0x40),
               tx_power_dbm=None, rx_power_dbm=None, temp_c=None,
               rx_low_alarm_dbm=None, rx_low_warn_dbm=None, rx_high_alarm_dbm=None)
    if out["ddm"] and a2 and len(a2) >= 106:
        u16 = lambda i: struct.unpack("!H", a2[i:i + 2])[0]   # noqa: E731
        out.update(temp_c=round(struct.unpack("!h", a2[96:98])[0] / 256, 1),
                   tx_power_dbm=_dbm(u16(102)), rx_power_dbm=_dbm(u16(104)),
                   rx_high_alarm_dbm=_dbm(u16(32)), rx_low_alarm_dbm=_dbm(u16(34)),
                   rx_low_warn_dbm=_dbm(u16(38)))
    return out
