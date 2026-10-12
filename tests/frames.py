"""Hand-built, sanitized logger frames for the tests."""
from __future__ import annotations

import struct
from typing import Any, Iterable, Tuple

from dyness_battery.local.protocol import OP_CONFIG, OP_UPLOAD, build_frame, crc16_xmodem

LOGGER_SN = "R00TEST000000001"
BANK_SN = f"{LOGGER_SN}-BMS"
BOARDS = ("0100000000000001", "0100000000000002", "0200000000000003")
TS_MS = 1_791_606_970_000


def field(fid: int, typ: str, value: Any) -> bytes:
    head = fid.to_bytes(4, "big") + typ.encode()
    if typ == "T":
        data = value.encode() + b"\x00"
        return head + bytes([len(data)]) + data
    if typ == "F":
        return head + struct.pack(">f", value)
    if typ == "I":
        return head + int(value).to_bytes(4, "big")
    if typ == "S":
        return head + int(value).to_bytes(2, "big")
    raise ValueError(typ)


def upload_body(code: int, name: str, ts_ms: int, fields: Iterable[Tuple[int, str, Any]]) -> bytes:
    fields = list(fields)
    meta = b"\x01" + ts_ms.to_bytes(8, "big") + b"\x00\x00\x00"
    return (
        code.to_bytes(2, "big") + b"\x00\x01"
        + bytes([len(name)]) + name.encode()
        + meta + bytes([len(fields)])
        + b"".join(field(*f) for f in fields)
    )


def config_frame(ts_ms: int = TS_MS, interval: int = 300, boards: int = 3) -> bytes:
    return build_frame(LOGGER_SN, OP_CONFIG, upload_body(3600, LOGGER_SN, ts_ms, [
        (601000, "T", "LOGGER-FW-1"),
        (850000, "I", interval),
        (851000, "I", boards),
    ]))


def bank_frame(ts_ms: int = TS_MS, soc: int = 95, voltage: float = 53.0, current: float = -17.6,
               boards: int = 3, status: int = 128) -> bytes:
    return build_frame(LOGGER_SN, OP_UPLOAD, upload_body(14002, BANK_SN, ts_ms, [
        (300, "T", "24.9-26.9.1"),
        (400, "S", boards),
        (600, "F", voltage),
        (700, "F", current),
        (800, "S", soc),
        (1200, "S", 99),
        (3200, "S", status),
    ]))


def board_frame(sn: str, ts_ms: int = TS_MS, voltage: float = 53.1) -> bytes:
    return build_frame(LOGGER_SN, OP_UPLOAD, upload_body(15002, sn, ts_ms, [
        (10000, "T", sn),
        (10300, "F", 3.312),
        (13500, "F", voltage),
        (13900, "S", 98),
        (14000, "F", 200.0),
    ]))


def tunnel(command_id: int, inner_cmd: bytes, data: bytes, corrupt: bool = False) -> bytes:
    inner = b"\xa0" + b"\x0a\x01" + inner_cmd + len(data).to_bytes(2, "big") + data
    crc = crc16_xmodem(inner) ^ (1 if corrupt else 0)
    inner += crc.to_bytes(2, "big") + b"\xd0\x0d"
    return command_id.to_bytes(4, "big") + bytes([len(inner)]) + inner
