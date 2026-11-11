"""Serial protocol to the STM32 coprocessor.  Mirrors firmware/coproc/proto.h.

Frame: 0x7E | LEN | CMD | SEQ | payload[LEN] | CRC16-CCITT(LEN..payload), big-endian
115200 8N1.  Replies echo the command and sequence number; CMD_ERROR carries
a one-byte code.  CMD_KEY frames arrive unsolicited.
"""
from __future__ import annotations

import struct
import time

from .base import HalError

SOF = 0x7E
MAX_PAYLOAD = 255

CMD_PING, CMD_VSCAN, CMD_WIREMAP, CMD_XTALK, CMD_RELAY = 0x01, 0x10, 0x11, 0x12, 0x13
CMD_POE_STATUS, CMD_POE_LOAD, CMD_BATTERY = 0x20, 0x21, 0x30
CMD_KEY, CMD_LED, CMD_BUZZ, CMD_ERROR = 0x40, 0x41, 0x42, 0x7F

RELAY_LINK, RELAY_TEST, RELAY_ISOLATE = 0, 1, 2

ERRORS = {1: "unknown command", 2: "bad payload length",
          3: "unsafe voltage on the cable: measurement refused",
          4: "PoE load over temperature", 5: "busy: the line never went quiet",
          6: "PoE is not powered"}

OPEN = 0xFFFFFFFF
XTALK_KEYS = ("1-2/3-6", "1-2/4-5", "1-2/7-8", "3-6/4-5", "3-6/7-8", "4-5/7-8")


class ProtoError(HalError):
    def __init__(self, code: int):
        self.code = code
        super().__init__(f"Coprocessor error {code}: {ERRORS.get(code, 'unknown')}")


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode(cmd: int, seq: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too long")
    body = bytes([len(payload), cmd & 0xFF, seq & 0xFF]) + payload
    return bytes([SOF]) + body + struct.pack(">H", crc16(body))


def decode(buf: bytes) -> tuple[tuple[int, int, bytes] | None, bytes]:
    """Find one valid frame in buf.

    Returns ((cmd, seq, payload), remaining bytes) or (None, bytes to keep).
    Bytes that cannot start a frame are discarded; a possible partial frame is
    kept so that more data can complete it.  Same behaviour as ns_decode().
    """
    n = len(buf)
    keep = n
    for i in range(n):
        if buf[i] != SOF:
            continue
        rest = n - i
        if rest < 2 or rest < buf[i + 1] + 6:
            if keep == n:
                keep = i
            continue
        plen = buf[i + 1]
        crc = (buf[i + 4 + plen] << 8) | buf[i + 5 + plen]
        if crc16(buf[i + 1:i + 4 + plen]) != crc:
            continue
        return (buf[i + 2], buf[i + 3], bytes(buf[i + 4:i + 4 + plen])), bytes(buf[i + plen + 6:])
    return None, bytes(buf[keep:])


def pack_wiremap(matrix: list[list[float | None]]) -> bytes:
    """56 x u32 ohms, order a=1..8, b=1..8, a != b (a driven positive)."""
    vals = [OPEN if matrix[a][b] is None else min(round(matrix[a][b]), OPEN - 1)
            for a in range(8) for b in range(8) if a != b]
    return struct.pack("<56I", *vals)


def unpack_wiremap(payload: bytes) -> list[list[float | None]]:
    if len(payload) != 224:
        raise HalError(f"wiremap reply is {len(payload)} bytes, expected 224")
    vals = iter(struct.unpack("<56I", payload))
    m: list[list[float | None]] = [[None] * 8 for _ in range(8)]
    for a in range(8):
        for b in range(8):
            if a != b:
                v = next(vals)
                m[a][b] = None if v == OPEN else float(v)
    return m


def unpack_vscan(payload: bytes) -> dict:
    a_mv, b_mv, flags = struct.unpack("<iiB", payload[:9])
    return dict(alt_a_v=a_mv / 1000, alt_b_v=b_mv / 1000, pulsing=bool(flags & 1))


def unpack_xtalk(payload: bytes) -> dict[str, float]:
    return {k: v / 100 for k, v in zip(XTALK_KEYS, struct.unpack("<6h", payload[:12]))}


def unpack_poe_status(payload: bytes) -> dict:
    mv, kind, cls, flags = struct.unpack("<iBBB", payload[:7])
    return dict(kind={0: "none", 1: "ieee", 2: "passive"}.get(kind, "none"),
                voltage_v=mv / 1000, allocated_class=None if cls == 0xFF else cls,
                four_pair=bool(flags & 1), denied=bool(flags & 2),
                alt="B" if flags & 4 else "A")


def unpack_poe_load(payload: bytes, requested_w: float) -> dict:
    mv, ma, noload_mv, held = struct.unpack("<iiiB", payload[:13])
    v, a = mv / 1000, ma / 1000
    return dict(requested_w=requested_w, held=bool(held), voltage_v=round(v, 2),
                current_a=round(a, 3), power_w=round(v * a, 1), no_load_v=round(noload_mv / 1000, 2),
                reason=None if held else "power removed by the PSE")


def unpack_battery(payload: bytes) -> dict:
    pct, mv, ma, temp, health, cycles, flags, minutes = struct.unpack("<BHhhBHBH", payload[:13])
    return dict(percent=pct, voltage_v=mv / 1000, current_ma=ma, temp_c=temp / 10,
                health_pct=health, cycles=cycles, charging=bool(flags & 1),
                time_to_empty_min=None if minutes == 0xFFFF else minutes)


class Coproc:
    """Request/response client.  `port` needs write(bytes) and read(n) -> bytes."""

    def __init__(self, port, on_key=None):
        self.port, self.on_key = port, on_key
        self.seq = 0
        self.buf = b""

    def request(self, cmd: int, payload: bytes = b"", timeout: float = 3.0) -> bytes:
        self.seq = self.seq % 255 + 1  # 1..255; 0 is reserved for unsolicited frames
        self.port.write(encode(cmd, self.seq, payload))
        deadline = time.monotonic() + timeout
        while True:
            frame, self.buf = decode(self.buf)
            if frame is None:
                if time.monotonic() > deadline:
                    raise HalError(f"Coprocessor did not answer command 0x{cmd:02x}.")
                chunk = self.port.read(256)
                if chunk:
                    self.buf += chunk
                else:
                    time.sleep(0.005)
                continue
            rcmd, rseq, body = frame
            if rcmd == CMD_KEY:
                if self.on_key and len(body) >= 2:
                    self.on_key(body[0], body[1])
                continue
            if rseq != self.seq:
                continue  # stale reply to an earlier, timed-out request
            if rcmd == CMD_ERROR:
                raise ProtoError(body[0] if body else 0)
            if rcmd == cmd:
                return body
