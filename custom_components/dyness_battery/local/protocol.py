"""Dyness / Raymon logger TCP protocol (port 5005).

Wire format: reverse-engineering/dyness_protocol_spec.md. No Home Assistant
imports, so the decoder tests can run without Home Assistant installed.
"""
from __future__ import annotations

import datetime as dt
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_FRAME = 1_048_576

OP_LOGIN = b"\x91\x00"
OP_TIME = b"\x91\x22"
OP_CONFIG = b"\x91\x71"
OP_UPLOAD = b"\x91\x04"
OP_COMMAND_RESULT = b"\x91\x87"
OP_GREETING = b"\x00\x7f"
OP_COMMAND = b"\x00\x77"
OP_ACK_CONFIG = b"\x99\x71"
OP_ACK_UPLOAD = b"\x99\x04"

ACK_FOR = {OP_CONFIG: OP_ACK_CONFIG, OP_UPLOAD: OP_ACK_UPLOAD}

MEASUREMENT_CONFIG = 3600
MEASUREMENT_BANK = 14002
MEASUREMENT_BOARD = 15002

COMMAND_CLOCK_SET = 0x12F8
INNER_CLOCK_SET = b"\x08\x02"

BITMASK_FIELDS = (3200, 3300, 3400, 3500, 4000, 17600, 17700, 17800, 17900, 18000, 19700)

GREETING_TEXT = "This is dyness.raymon service. node id is '{}'"


class FrameError(ValueError):
    """The byte stream cannot be split into frames; the session must close."""


class FieldError(ValueError):
    """A frame's typed fields do not parse."""


@dataclass
class Frame:
    raw: bytes
    serial: str
    opcode: bytes
    body: bytes

    @property
    def opcode_hex(self) -> str:
        return self.opcode.hex()


@dataclass
class TypedField:
    id: int
    type: str
    value: Any
    raw: bytes


@dataclass
class Upload:
    measurement_code: int
    name: str
    timestamp_ms: Optional[int]
    fields: List[TypedField] = field(default_factory=list)

    @property
    def is_bank(self) -> bool:
        return self.name.endswith("-BMS")

    def points(self) -> Dict[int, Any]:
        return {f.id: f.value for f in self.fields}


def parse_header(raw: bytes) -> Frame:
    """Parse length prefix, serial header and opcode of one complete frame."""
    if len(raw) < 7:
        raise FrameError(f"frame too short ({len(raw)} bytes)")
    serial_len = raw[4]
    end = 5 + serial_len
    if serial_len > 48 or end + 2 > len(raw):
        raise FrameError("invalid serial header")
    return Frame(
        raw=raw,
        serial=raw[5:end].decode("ascii", "replace"),
        opcode=raw[end:end + 2],
        body=raw[end + 2:],
    )


class FrameBuffer:
    """Reassembles length-prefixed frames from a TCP byte stream."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> List[Frame]:
        self._buf.extend(data)
        frames = []
        while len(self._buf) >= 4:
            n = int.from_bytes(self._buf[:4], "big")
            if n < 3 or n > MAX_FRAME:
                raise FrameError(f"invalid frame length {n}")
            if len(self._buf) < 4 + n:
                break
            raw = bytes(self._buf[:4 + n])
            del self._buf[:4 + n]
            frames.append(parse_header(raw))
        return frames

    @property
    def pending(self) -> int:
        return len(self._buf)


def read_fields(data: bytes, start: int, count: int) -> List[TypedField]:
    fields = []
    pos = start
    for _ in range(count):
        if pos + 5 > len(data):
            raise FieldError("truncated field header")
        fid = int.from_bytes(data[pos:pos + 4], "big")
        typ = chr(data[pos + 4])
        pos += 5
        if typ == "T":
            if pos >= len(data):
                raise FieldError("missing text length")
            n = data[pos]
            pos += 1
        elif typ in ("F", "I"):
            n = 4
        elif typ == "S":
            n = 2
        else:
            raise FieldError(f"unknown type 0x{ord(typ):02X} for field {fid}")
        if pos + n > len(data):
            raise FieldError(f"truncated data for field {fid}")
        raw = data[pos:pos + n]
        pos += n
        if typ == "T":
            value: Any = raw.rstrip(b"\x00").decode("utf-8", "replace")
        elif typ == "F":
            value = struct.unpack(">f", raw)[0]
        else:
            value = int.from_bytes(raw, "big")
        fields.append(TypedField(fid, typ, value, raw))
    if pos != len(data):
        raise FieldError(f"fields ended at {pos} of {len(data)} bytes")
    return fields


def parse_upload(frame: Frame) -> Upload:
    """Parse a `91 04` or `91 71` body: code, name, metadata, typed fields."""
    body = frame.body
    if len(body) < 5:
        raise FieldError("truncated measurement code")
    code = int.from_bytes(body[0:2], "big")
    name_len = body[4]
    name_end = 5 + name_len
    count_pos = name_end + 12
    if count_pos >= len(body):
        raise FieldError("truncated measurement header")
    name = body[5:name_end].decode("ascii", "replace")
    meta = body[name_end:count_pos]
    timestamp_ms = int.from_bytes(meta[1:9], "big") if meta[0] == 0x01 else None
    return Upload(code, name, timestamp_ms, read_fields(body, count_pos + 1, body[count_pos]))


def expand_bits(points: Dict[int, Any]) -> Dict[int, Any]:
    """Add sub-points `<id + n>` for bit `n - 1` of each bitmask field, when absent."""
    out = dict(points)
    for word in BITMASK_FIELDS:
        value = points.get(word)
        if not isinstance(value, int):
            continue
        for bit in range(8):
            out.setdefault(word + bit + 1, (value >> bit) & 1)
    return out


def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def decode_command(body: bytes) -> Dict[str, Any]:
    """Decode a `00 77` tunnel body. `status` is parsed, opaque or unknown."""
    out: Dict[str, Any] = {"status": "unknown"}
    if len(body) < 5:
        return out
    command_id = int.from_bytes(body[0:4], "big")
    length = body[4]
    inner = body[5:]
    out.update(command_id=command_id, length=length)
    if len(inner) != length or len(inner) < 11 or inner[0] != 0xA0 or inner[-2:] != b"\xd0\x0d":
        return out
    data_len = int.from_bytes(inner[5:7], "big")
    if 7 + data_len + 4 != len(inner):
        return out
    data = inner[7:7 + data_len]
    crc = int.from_bytes(inner[7 + data_len:9 + data_len], "big")
    crc_ok = crc16_xmodem(inner[:7 + data_len]) == crc
    out.update(
        address=inner[1:3].hex(),
        inner_command=inner[3:5].hex(),
        data=data.hex(),
        crc_ok=crc_ok,
    )
    if not crc_ok:
        return out
    out["status"] = "opaque"
    if command_id == COMMAND_CLOCK_SET and inner[3:5] == INNER_CLOCK_SET and data_len == 8:
        sec, minute, hour, day, month, year, weekday = data[:7]
        try:
            out["clock"] = dt.datetime(2000 + year, month, day, hour, minute, sec).isoformat()
            out["weekday"] = weekday
            out["status"] = "parsed"
        except ValueError:
            pass
    return out


def decode_command_result(body: bytes) -> Dict[str, Any]:
    """Decode a `91 87` reply: echoed command ID and trailing result byte."""
    if len(body) < 5:
        return {"status": "unknown"}
    return {
        "status": "parsed" if int.from_bytes(body[0:4], "big") == COMMAND_CLOCK_SET else "opaque",
        "command_id": int.from_bytes(body[0:4], "big"),
        "data": body[4:-1].hex(),
        "result": body[-1],
    }


def build_frame(serial: str, opcode: bytes, body: bytes = b"") -> bytes:
    sn = serial.encode("ascii")
    payload = bytes([len(sn)]) + sn + opcode + body
    return len(payload).to_bytes(4, "big") + payload


def build_greeting(node_id: Optional[str] = None) -> bytes:
    text = GREETING_TEXT.format(node_id or str(uuid.uuid4()))
    return build_frame("", OP_GREETING, text.encode("ascii"))


def build_login_ok(serial: str) -> bytes:
    return build_frame(serial, OP_LOGIN, b"\x01")


def build_time_reply(serial: str, epoch_ms: int) -> bytes:
    return build_frame(serial, OP_TIME, epoch_ms.to_bytes(8, "big"))


def build_ack(serial: str, opcode: bytes) -> bytes:
    return build_frame(serial, ACK_FOR[opcode], b"\x01")


def endpoint_replies(frame: Frame, now_ms: int) -> List[bytes]:
    """Endpoint-mode replies for one logger frame.

    Uploads are acknowledged by opcode alone, whether or not their fields
    parse, so the stop-and-wait logger does not stall. Unexpected opcodes get
    no reply.
    """
    if frame.opcode == OP_LOGIN:
        return [build_greeting(), build_login_ok(frame.serial)]
    if frame.opcode == OP_TIME:
        return [build_time_reply(frame.serial, now_ms)]
    if frame.opcode in ACK_FOR:
        return [build_ack(frame.serial, frame.opcode)]
    return []
