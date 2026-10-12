"""JSON-lines traffic trace for cloud_passthru entries.

One record per frame, Open API call and comparison. File writes happen on a
QueueListener thread, so callers on the event loop never touch the disk.
`open()` builds the file handler and must run in an executor.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import logging.handlers
import queue
from pathlib import Path
from typing import Any, Dict, Optional

from .protocol import (
    OP_COMMAND,
    OP_COMMAND_RESULT,
    OP_CONFIG,
    OP_LOGIN,
    OP_TIME,
    OP_UPLOAD,
    FieldError,
    Frame,
    decode_command,
    decode_command_result,
    parse_upload,
)

TRACE_FILENAME = "dyness_cloud_passthru.log"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5
SENSITIVE_KEYS = ("api_secret", "apiSecret", "Authorization", "authorization", "secret")
HEADER = (
    "Dyness cloud_passthru trace. Contains serial numbers, the logger MAC and LAN "
    "address, and full telemetry. Do not share it unredacted."
)

PARSED_OPCODES = {
    b"\x91\x00", b"\x00\x7f", b"\x91\x22", b"\x91\x71", b"\x91\x04", b"\x99\x71", b"\x99\x04",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("redacted" if k in SENSITIVE_KEYS else redact(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def load_point_names(path: Path) -> Dict[str, Dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"bank": {}, "board": {}}
    return {"bank": data.get("bank", {}), "board": data.get("board", {})}


class Trace:
    def __init__(self, path: Path, entry_id: str, capture_unknown_raw: bool = True) -> None:
        self.path = path
        self.capture_unknown_raw = capture_unknown_raw
        self._names: Dict[str, Dict[str, str]] = {"bank": {}, "board": {}}
        self._logger = logging.getLogger(f"{__name__}.{entry_id}")
        self._logger.propagate = False
        self._logger.setLevel(logging.INFO)
        self._listener: Optional[logging.handlers.QueueListener] = None
        self._queue_handler: Optional[logging.handlers.QueueHandler] = None
        self._pending_commands: Dict[int, float] = {}

    def open(self) -> None:
        """Create the rotating file handler (blocking; run in an executor)."""
        self._names = load_point_names(Path(__file__).with_name("point_names.json"))
        handler = logging.handlers.RotatingFileHandler(
            self.path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        q: "queue.SimpleQueue[logging.LogRecord]" = queue.SimpleQueue()
        self._queue_handler = logging.handlers.QueueHandler(q)
        self._logger.addHandler(self._queue_handler)
        self._listener = logging.handlers.QueueListener(q, handler)
        self._listener.start()
        self.write({"source": "trace", "status": "parsed", "event": "start", "note": HEADER})

    def close(self) -> None:
        """Flush and close (blocking; run in an executor)."""
        if self._listener is not None:
            self._listener.stop()
            for handler in self._listener.handlers:
                handler.close()
            self._listener = None
        if self._queue_handler is not None:
            self._logger.removeHandler(self._queue_handler)
            self._queue_handler = None

    def write(self, record: Dict[str, Any]) -> None:
        if self._queue_handler is None:
            return
        record = {"time": _now(), **record}
        self._logger.info(json.dumps(redact(record), ensure_ascii=False, default=str))

    def _label(self, kind: str, point_id: Any) -> Optional[str]:
        return self._names.get(kind, {}).get(str(point_id))

    # ── local frames ────────────────────────────────────────────────────

    def frame(self, direction: str, peer: str, frame: Frame, received: float) -> None:
        record: Dict[str, Any] = {
            "source": "local",
            "direction": direction,
            "peer": peer,
            "opcode": frame.opcode_hex,
            "serial": frame.serial,
            "length": len(frame.raw),
        }
        if frame.opcode == OP_LOGIN and direction == "logger_to_upstream":
            record.update(status="parsed", body="redacted")
        elif frame.opcode in (OP_UPLOAD, OP_CONFIG) and direction == "logger_to_upstream":
            try:
                upload = parse_upload(frame)
            except FieldError as exc:
                record.update(status="unknown", error=str(exc))
                self._raw(record, frame.raw)
            else:
                kind = "bank" if upload.is_bank else "board"
                record.update(
                    status="parsed",
                    measurement_code=upload.measurement_code,
                    name=upload.name,
                    timestamp_ms=upload.timestamp_ms,
                    fields=[
                        {"id": f.id, "type": f.type, "value": f.value, "label": self._label(kind, f.id)}
                        for f in upload.fields
                    ],
                )
        elif frame.opcode == OP_TIME:
            record["status"] = "parsed"
            if len(frame.body) == 8:
                carried = int.from_bytes(frame.body, "big") / 1000
                record.update(
                    carried=dt.datetime.fromtimestamp(carried, dt.timezone.utc).isoformat(),
                    offset_s=round(carried - received, 1),
                )
        elif frame.opcode == OP_COMMAND:
            decoded = decode_command(frame.body)
            record.update(status=decoded.pop("status"), body=frame.body.hex(), tunnel=decoded)
            if "command_id" in decoded:
                self._pending_commands[decoded["command_id"]] = received
            if "clock" in decoded:
                record["offset_s"] = round(
                    dt.datetime.fromisoformat(decoded["clock"]).replace(tzinfo=dt.timezone.utc).timestamp()
                    - received,
                    1,
                )
            if record["status"] == "unknown":
                self._raw(record, frame.raw)
        elif frame.opcode == OP_COMMAND_RESULT:
            decoded = decode_command_result(frame.body)
            record.update(status=decoded.pop("status"), body=frame.body.hex(), result=decoded)
            sent = self._pending_commands.pop(decoded.get("command_id", -1), None)
            if sent is not None:
                record["delay_s"] = round(received - sent, 3)
        elif frame.opcode in PARSED_OPCODES:
            record.update(status="parsed", body=frame.body.hex())
            if frame.opcode == b"\x00\x7f":
                record["text"] = frame.body.decode("ascii", "replace")
        else:
            record["status"] = "unknown"
            self._raw(record, frame.raw)
        self.write(record)

    def unframed(self, direction: str, peer: str, data: bytes, error: str) -> None:
        record: Dict[str, Any] = {
            "source": "local", "direction": direction, "peer": peer,
            "status": "unknown", "length": len(data), "error": error,
        }
        self._raw(record, data)
        self.write(record)

    def _raw(self, record: Dict[str, Any], data: bytes) -> None:
        if self.capture_unknown_raw:
            record["hex"] = data.hex()

    def event(self, record: Dict[str, Any]) -> None:
        self.write({"source": "local", "status": "parsed", **record})

    # ── cloud calls ─────────────────────────────────────────────────────

    def api(self, path: str, body: Any, response: Any, status: Optional[int] = None) -> None:
        self.write({
            "source": "cloud", "status": "parsed" if isinstance(response, dict) else "unknown",
            "path": path, "request": body, "http_status": status, "response": response,
        })

    def compare(self, record: Dict[str, Any]) -> None:
        self.write({"source": "cloud", "status": "parsed", "event": "compare", **record})
