"""Reply payloads produced by the C dispatcher (firmware/coproc/test_dispatch.c
asserts these exact bytes) decoded with the Python unpackers."""
import struct

from netscope.hal import coproc as cp

H = bytes.fromhex


def test_vscan():
    assert cp.unpack_vscan(H("30110000dca1ffff01")) == dict(alt_a_v=4.4, alt_b_v=-24.1, pulsing=True)


def test_poe_status():
    s = cp.unpack_poe_status(H("98d00000010400"))
    assert s == dict(kind="ieee", voltage_v=53.4, allocated_class=4, four_pair=False,
                     denied=False, alt="A")


def test_poe_load_request_and_reply():
    assert struct.pack("<IH", 20000, 2000) == H("204e0000d007")   # what LinuxHal sends
    r = cp.unpack_poe_load(H("2cc900008401000098d0000001"), 20.0)
    assert r["held"] and r["voltage_v"] == 51.5 and r["current_a"] == 0.388
    assert r["no_load_v"] == 53.4 and r["power_w"] == 20.0 and r["requested_w"] == 20.0


def test_battery():
    b = cp.unpack_battery(H("4e1e0f4afc3b0161290000ce01"))
    assert b == dict(percent=78, voltage_v=3.87, current_ma=-950, temp_c=31.5, health_pct=97,
                     cycles=41, charging=False, time_to_empty_min=462)


def test_xtalk():
    x = cp.unpack_xtalk(H("d0ee34ef98effcef60f0c4f0"))
    assert list(x) == list(cp.XTALK_KEYS)
    assert x["1-2/3-6"] == -44.0 and x["4-5/7-8"] == -39.0
