"""Linux backend: the real device, or any Linux PC for the host-side tools.

Two parts:

* HOST-IO - what Linux itself can do on a network interface: link state,
  PHY TDR (`ethtool --cable-test`), DHCP discovery, ping, traceroute, DNS,
  HTTP, ARP, LLDP/CDP listen, iperf3, tcpdump, `iw` scan.  Works on a PC.
* Coprocessor - port voltage scan, wiremap, crosstalk, PoE and battery.  Only
  present on a NetScope X1 (pass `coproc_path`).  Without it those methods
  raise HalUnsupported and the engine reports NOT_TESTED.

STATUS: this file was rewritten in one pass and has NOT been run against a
network or a board.  The parsers and packet builders it calls are unit
tested; the subprocess, socket and serial plumbing here is not.  Treat the
first run on a Linux PC (dev-kit spike, step 1) as its first test.

Needs CAP_NET_RAW + CAP_NET_ADMIN (or root).  External tools: ethtool >= 5.8,
iproute2, iputils-ping, traceroute, iw, and optionally iperf3 and tcpdump.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request

from ..net import parsers
from . import coproc as cp
from .base import Hal, HalError, HalUnsupported

LLDP_ETHERTYPE = b"\x88\xcc"
CDP_DST = bytes.fromhex("01000ccccccc")
CDP_SNAP = bytes.fromhex("aaaa0300000c2000")


def _run(cmd: list[str], timeout: float = 20.0) -> str:
    if not shutil.which(cmd[0]):
        raise HalUnsupported(f"'{cmd[0]}' is not installed on this system.")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise HalError(f"{cmd[0]} timed out after {timeout:.0f} s") from None
    return p.stdout + p.stderr


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class LinuxHal(Hal):
    name = "linux"

    def __init__(self, iface: str = "eth0", wlan: str | None = "wlan0",
                 coproc_path: str | None = None, fiber_iface: str | None = None,
                 sfp_i2c_bus: int | None = None):
        self.iface, self.wlan = iface, wlan
        self.fiber_iface, self.sfp_i2c_bus = fiber_iface, sfp_i2c_bus
        self.mcu: cp.Coproc | None = None
        if coproc_path:
            try:
                import serial  # pyserial, "device" extra
            except ImportError:
                raise HalError("pyserial is required to talk to the coprocessor") from None
            self.mcu = cp.Coproc(serial.Serial(coproc_path, 115200, timeout=0.05))
            self.mcu.request(cp.CMD_PING)
        # Until Phase 7 calibration is signed off nothing is called "hardware-verified".
        self.provenance = "hardware-uncalibrated" if self.mcu else "host"
        self._static: dict | None = None
        self._lease: dict | None = None

    def _need_mcu(self, what: str) -> cp.Coproc:
        if not self.mcu:
            raise HalUnsupported(f"{what} needs the NetScope measurement front end "
                                 f"(not present on this host).")
        return self.mcu

    # -- device ------------------------------------------------------------
    def device_info(self) -> dict:
        serial_no = None
        for path in ("/sys/firmware/devicetree/base/serial-number", "/etc/machine-id"):
            try:
                with open(path) as f:
                    serial_no = f.read().strip("\0\n ")[-12:].upper()
                break
            except OSError:
                continue
        return dict(model="NetScope X1" if self.mcu else "Linux host (no front end)",
                    serial=serial_no, hw_rev="A (unverified)" if self.mcu else None)

    def battery(self) -> dict:
        return cp.unpack_battery(self._need_mcu("Battery monitoring").request(cp.CMD_BATTERY))

    # -- cable -------------------------------------------------------------
    def port_voltage_scan(self) -> dict:
        return cp.unpack_vscan(self._need_mcu("Port voltage scan").request(cp.CMD_VSCAN))

    def wiremap_scan(self) -> dict:
        mcu = self._need_mcu("Wiremap")
        mcu.request(cp.CMD_RELAY, bytes([cp.RELAY_TEST]))
        try:
            matrix = cp.unpack_wiremap(mcu.request(cp.CMD_WIREMAP, timeout=8.0))
            try:
                xt = cp.unpack_xtalk(mcu.request(cp.CMD_XTALK, timeout=4.0))
            except HalError:
                xt = None  # split-pair circuit is optional / experimental
        finally:
            mcu.request(cp.CMD_RELAY, bytes([cp.RELAY_LINK]))
        return dict(matrix=matrix, crosstalk_db=xt)

    def tdr(self) -> list[dict]:
        out = _run(["ethtool", "--cable-test", self.iface], timeout=20)
        pairs = parsers.parse_cable_test(out)
        if not pairs:
            raise HalUnsupported("This network interface's driver does not support "
                                 "ethtool --cable-test.")
        return pairs

    # -- PoE ---------------------------------------------------------------
    def poe_status(self) -> dict:
        return cp.unpack_poe_status(self._need_mcu("PoE measurement").request(cp.CMD_POE_STATUS,
                                                                              timeout=6.0))

    def poe_load_test(self, load_w: float, seconds: float) -> dict:
        mcu = self._need_mcu("PoE load test")
        payload = struct.pack("<IH", round(load_w * 1000), round(seconds * 1000))
        return cp.unpack_poe_load(mcu.request(cp.CMD_POE_LOAD, payload, timeout=seconds + 4), load_w)

    # -- link / IP ---------------------------------------------------------
    def link_status(self) -> dict:
        return parsers.parse_ethtool_link(_run(["ethtool", self.iface]))

    def _mac(self) -> bytes:
        try:
            with open(f"/sys/class/net/{self.iface}/address") as f:
                return bytes.fromhex(f.read().strip().replace(":", ""))
        except OSError as e:
            raise HalError(f"cannot read MAC of {self.iface}: {e}") from None

    def _bound_socket(self, kind: int) -> socket.socket:
        s = socket.socket(socket.AF_INET, kind)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.iface.encode())
        except (PermissionError, OSError) as e:
            s.close()
            raise HalError(f"cannot bind to {self.iface} (needs CAP_NET_RAW): {e}") from None
        return s

    def dhcp_discover(self) -> dict | None:
        """Broadcast a DISCOVER and report the first OFFER.  Does not take the lease."""
        xid = int.from_bytes(os.urandom(4), "big")
        s = self._bound_socket(socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", 68))
            s.settimeout(0.5)
            deadline = time.monotonic() + 8.0
            sent = 0.0
            while time.monotonic() < deadline:
                if time.monotonic() - sent > 2.5:  # retransmit: first packet often lost to STP
                    s.sendto(parsers.build_dhcp_discover(self._mac(), xid), ("255.255.255.255", 67))
                    sent = time.monotonic()
                try:
                    data, _ = s.recvfrom(2048)
                except socket.timeout:
                    continue
                r = parsers.parse_dhcp_reply(data)
                if r and r["xid"] == xid and r["type"] == "OFFER":
                    self._lease = {k: r[k] for k in ("address", "prefix", "gateway", "dns",
                                                     "server", "lease_s", "domain")}
                    return dict(self._lease)
        except OSError as e:
            raise HalError(f"DHCP socket error: {e}") from None
        finally:
            s.close()
        return None

    def set_static(self, address: str, prefix: int, gateway: str, dns: list[str]) -> dict:
        _run(["ip", "addr", "flush", "dev", self.iface])
        out = _run(["ip", "addr", "add", f"{address}/{prefix}", "dev", self.iface])
        if "Error" in out or "RTNETLINK" in out:
            raise HalError(out.strip())
        if gateway:
            _run(["ip", "route", "replace", "default", "via", gateway, "dev", self.iface])
        self._static = dict(address=address, prefix=prefix, gateway=gateway, dns=list(dns))
        return dict(self._static)

    def net_config(self) -> dict | None:
        if self._static:
            return dict(self._static)
        try:
            addrs = json.loads(_run(["ip", "-j", "-4", "addr", "show", "dev", self.iface]) or "[]")
            routes = json.loads(_run(["ip", "-j", "-4", "route", "show", "default",
                                      "dev", self.iface]) or "[]")
        except ValueError:
            return None
        info = next((a for d in addrs for a in d.get("addr_info", [])), None)
        if not info:
            return dict(self._lease) if self._lease else None
        return dict(address=info["local"], prefix=info["prefixlen"],
                    gateway=routes[0].get("gateway") if routes else None,
                    dns=(self._lease or {}).get("dns", []))

    def ping(self, host: str, count: int) -> dict:
        out = _run(["ping", "-n", "-c", str(count), "-i", "0.2", "-W", "1", "-I", self.iface, host],
                   timeout=count * 1.5 + 5)
        m = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received", out)
        if not m:
            raise HalError(out.strip().splitlines()[-1] if out.strip() else "ping produced no output")
        sent, rx = int(m.group(1)), int(m.group(2))
        t = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)", out)
        return dict(host=host, sent=sent, received=rx,
                    loss_pct=round(100 * (sent - rx) / sent, 1) if sent else 100.0,
                    rtt_min_ms=float(t.group(1)) if t else None,
                    rtt_avg_ms=float(t.group(2)) if t else None,
                    rtt_max_ms=float(t.group(3)) if t else None)

    def traceroute(self, host: str) -> list[dict]:
        out = _run(["traceroute", "-n", "-q", "1", "-w", "1", "-m", "20", "-i", self.iface, host],
                   timeout=50)
        hops = []
        for line in out.splitlines():
            m = re.match(r"\s*(\d+)\s+(\S+)(?:\s+([\d.]+) ms)?", line)
            if m:
                star = m.group(2) == "*"
                hops.append(dict(hop=int(m.group(1)), address=None if star else m.group(2),
                                 rtt_ms=float(m.group(3)) if m.group(3) else None))
        return hops

    def dns_lookup(self, name: str, server: str | None) -> dict:
        server = server or ((self.net_config() or {}).get("dns") or [None])[0]
        out = dict(ok=False, addresses=[], server=server, error=None, time_ms=None)
        if not server:
            out["error"] = "no DNS server configured"
            return out
        txid = int.from_bytes(os.urandom(2), "big")
        s = self._bound_socket(socket.SOCK_DGRAM)
        s.settimeout(2.5)
        t0 = time.monotonic()
        try:
            s.sendto(parsers.build_dns_query(name, txid), (server, 53))
            data, _ = s.recvfrom(2048)
            r = parsers.parse_dns_response(data, txid)
        except socket.timeout:
            out["error"] = "timeout"
            return out
        except (OSError, ValueError) as e:
            out["error"] = str(e)
            return out
        finally:
            s.close()
        out["time_ms"] = round((time.monotonic() - t0) * 1000)
        out["addresses"] = r["addresses"]
        out["ok"] = r["rcode"] == "NOERROR" and bool(r["addresses"])
        if not out["ok"]:
            out["error"] = r["rcode"] if r["rcode"] != "NOERROR" else "no address records"
        return out

    def http_check(self, url: str) -> dict:
        # Note: uses the system resolver and routing table, not strictly the test port.
        out = dict(url=url, ok=False, status=None, time_ms=None, error=None, captive_portal=False)
        t0 = time.monotonic()
        try:
            with urllib.request.build_opener(_NoRedirect).open(url, timeout=8) as resp:
                body = resp.read(256)
                out.update(status=resp.status, time_ms=round((time.monotonic() - t0) * 1000))
                # generate_204 must return an empty 204; anything else is an interception.
                if "generate_204" in url and (resp.status != 204 or body):
                    out["captive_portal"] = True
                    out["error"] = "unexpected content: captive portal"
                else:
                    out["ok"] = 200 <= resp.status < 400
        except urllib.error.HTTPError as e:
            out.update(status=e.code, error=f"HTTP {e.code}",
                       captive_portal=e.code in (301, 302, 303, 307, 308, 511))
        except Exception as e:  # DNS failure, timeout, TLS error: all are a failed check
            out["error"] = f"{type(e).__name__}: {e}"[:120]
        return out

    def arp_table(self) -> list[dict]:
        try:
            rows = json.loads(_run(["ip", "-j", "neigh", "show", "dev", self.iface]) or "[]")
        except ValueError:
            rows = []
        return [dict(address=r["dst"], mac=r["lladdr"], vendor=None)
                for r in rows if r.get("lladdr") and ":" not in r["dst"]]

    def neighbors(self) -> list[dict]:
        """Passive listen: LLDP is sent every 30 s by default, CDP every 60 s."""
        try:
            s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
            s.bind((self.iface, 0))
        except (PermissionError, OSError) as e:
            raise HalError(f"cannot open a raw socket on {self.iface}: {e}") from None
        s.settimeout(1.0)
        found: dict[str, dict] = {}
        deadline = time.monotonic() + 35.0
        try:
            while time.monotonic() < deadline and "LLDP" not in found:
                try:
                    frame = s.recv(4096)
                except socket.timeout:
                    continue
                if frame[12:14] == LLDP_ETHERTYPE:
                    found["LLDP"] = parsers.parse_lldp(frame[14:])
                elif frame[:6] == CDP_DST and frame[14:22] == CDP_SNAP:
                    found["CDP"] = parsers.parse_cdp(frame[22:])
                    deadline = min(deadline, time.monotonic() + 5.0)  # give LLDP a moment more
        finally:
            s.close()
        return [found[k] for k in ("LLDP", "CDP") if k in found]

    def throughput(self, server: str, seconds: int) -> dict:
        def run(reverse: bool) -> dict:
            cmd = ["iperf3", "-J", "-c", server, "-t", str(seconds)] + (["-R"] if reverse else [])
            try:
                d = json.loads(_run(cmd, timeout=seconds + 15))
            except ValueError:
                raise HalError("iperf3 returned no result") from None
            if d.get("error"):
                raise HalError(f"iperf3: {d['error']}")
            return d["end"]
        tx, rx = run(False), run(True)
        return dict(server=server, seconds=seconds,
                    tx_mbps=round(tx["sum_sent"]["bits_per_second"] / 1e6),
                    rx_mbps=round(rx["sum_received"]["bits_per_second"] / 1e6),
                    retransmits=tx["sum_sent"].get("retransmits", 0))

    def capture(self, seconds: int) -> dict:
        path = time.strftime("/var/lib/netscope/captures/%Y%m%d-%H%M%S.pcap")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError as e:
            return dict(file=None, packets=0, note=f"Cannot write captures: {e}")
        out = _run(["timeout", str(seconds), "tcpdump", "-i", self.iface, "-s", "256", "-c", "20000",
                    "-w", path], timeout=seconds + 10)
        m = re.search(r"(\d+) packets captured", out)
        if not m or not os.path.exists(path):
            return dict(file=None, packets=0, note=(out.strip().splitlines() or ["tcpdump failed"])[-1])
        return dict(file=path, packets=int(m.group(1)), note=None)

    # -- fiber ---------------------------------------------------------------
    def sfp_status(self) -> dict:
        """Read the module EEPROM over I2C and the link state from the fiber interface.
        Not run on hardware: there is no board with an SFP+ cage yet."""
        if self.fiber_iface is None or self.sfp_i2c_bus is None:
            raise HalUnsupported("No fiber port is configured on this backend.")
        try:
            from smbus2 import SMBus  # optional dependency, device only
        except ImportError:
            raise HalUnsupported("Reading the SFP module needs the smbus2 package.") from None

        def page(bus, addr: int, length: int) -> bytes:
            return bytes(b for off in range(0, length, 32)
                         for b in bus.read_i2c_block_data(addr, off, min(32, length - off)))
        try:
            with SMBus(self.sfp_i2c_bus) as bus:
                try:
                    a0 = page(bus, 0x50, 96)
                except OSError:
                    return dict(present=False)
                try:
                    a2 = page(bus, 0x51, 128)
                except OSError:
                    a2 = None
        except OSError as e:
            raise HalError(f"cannot open I2C bus {self.sfp_i2c_bus}: {e}") from None
        out = parsers.parse_sff8472(a0, a2)
        link = parsers.parse_ethtool_link(_run(["ethtool", self.fiber_iface]))
        out.update(link=link["up"], speed=link["speed"],
                   los=out["ddm"] and out["rx_power_dbm"] is None)
        return out

    # -- Wi-Fi -------------------------------------------------------------
    def _wlan(self) -> str:
        if not self.wlan or not os.path.exists(f"/sys/class/net/{self.wlan}"):
            raise HalUnsupported("No Wi-Fi interface is present.")
        return self.wlan

    def wifi_scan(self) -> list[dict]:
        return parsers.parse_iw_scan(_run(["iw", "dev", self._wlan(), "scan"], timeout=25))

    def wifi_status(self) -> dict:
        out = _run(["iw", "dev", self._wlan(), "link"])
        if "Connected to" not in out:
            return dict(connected=False)

        def grab(pattern: str):
            m = re.search(pattern, out)
            return m.group(1) if m else None
        freq = int(float(grab(r"freq: ([\d.]+)") or 0))
        rate = grab(r"tx bitrate: ([\d.]+)")
        sig = grab(r"signal: (-?\d+)")
        return dict(connected=True, ssid=grab(r"SSID: (.+)"), bssid=grab(r"Connected to ([0-9a-f:]{17})"),
                    freq=freq, channel=parsers.freq_to_channel(freq),
                    rssi=int(sig) if sig else None, tx_rate_mbps=float(rate) if rate else None,
                    roam_events=[])  # roam history needs a wpa_supplicant event listener: not written
