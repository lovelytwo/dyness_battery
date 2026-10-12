"""Latest local logger values: bank, boards, logger diagnostics, upload cycles.

No Home Assistant imports. Times are epoch seconds passed in by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .protocol import MEASUREMENT_CONFIG, Upload, expand_bits

DEFAULT_INTERVAL_S = 300
CREATE_TIME_TOLERANCE_S = 300
LOGGER_DIAGNOSTIC_FIELDS = (601000, 602000, 613200, 850000, 851000)


@dataclass
class Sample:
    name: str
    points: Dict[int, Any]
    timestamp_ms: Optional[int]
    received: float


@dataclass
class Cycle:
    started: float
    boards: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    complete: bool = False


class LocalStore:
    """Holds the newest sample per bank and board and tracks upload cycles."""

    def __init__(self) -> None:
        self.logger_serial: Optional[str] = None
        self.logger_points: Dict[int, Any] = {}
        self.bank: Optional[Sample] = None
        self.boards: Dict[str, Sample] = {}
        self.cycle: Optional[Cycle] = None
        self.last_upload: Optional[float] = None
        self.cycles_completed = 0

    @property
    def bank_sn(self) -> Optional[str]:
        return self.bank.name if self.bank else None

    @property
    def interval_s(self) -> int:
        value = self.logger_points.get(850000)
        return value if isinstance(value, int) and value > 0 else DEFAULT_INTERVAL_S

    @property
    def timeout_s(self) -> int:
        return 2 * self.interval_s

    @property
    def expected_boards(self) -> Optional[int]:
        for value in ((self.bank.points.get(400) if self.bank else None), self.logger_points.get(851000)):
            if isinstance(value, int) and value > 0:
                return value
        return None

    def is_fresh(self, now: float) -> bool:
        return self.last_upload is not None and now - self.last_upload <= self.timeout_s

    def board_is_fresh(self, sn: str, now: float) -> bool:
        sample = self.boards.get(sn)
        return sample is not None and now - sample.received <= self.timeout_s

    def ingest(self, serial: str, upload: Upload, received: float) -> List[Dict[str, Any]]:
        """Store one parsed upload. Returns trace events (duplicate, shortfall, cycle_complete)."""
        self.logger_serial = serial or self.logger_serial
        points = expand_bits(upload.points())
        sample = Sample(upload.name, points, upload.timestamp_ms, received)

        if upload.measurement_code == MEASUREMENT_CONFIG and not upload.is_bank:
            self.logger_points.update(
                {k: v for k, v in points.items() if k in LOGGER_DIAGNOSTIC_FIELDS}
            )
            return []

        events: List[Dict[str, Any]] = []
        self.last_upload = received
        if upload.is_bank:
            events.extend(self.finish_cycle())
            self.bank = sample
            self.cycle = Cycle(started=received)
            return events

        key = str(points.get(10000) or upload.name)
        self.boards[key] = sample
        if self.cycle is None:
            self.cycle = Cycle(started=received)
        if key in self.cycle.boards:
            self.cycle.duplicates.append(key)
            events.append({"event": "duplicate_board", "board": key})
        else:
            self.cycle.boards.append(key)
        expected = self.expected_boards
        if not self.cycle.complete and expected and len(self.cycle.boards) >= expected:
            self.cycle.complete = True
            self.cycles_completed += 1
            events.append(self._cycle_event())
        return events

    def finish_cycle(self) -> List[Dict[str, Any]]:
        """Close the open cycle (next bank frame or quiet-period timer)."""
        cycle = self.cycle
        if cycle is None or cycle.complete or self.bank is None:
            return []
        cycle.complete = True
        self.cycles_completed += 1
        return [self._cycle_event()]

    def _cycle_event(self) -> Dict[str, Any]:
        assert self.cycle is not None
        expected = self.expected_boards
        event: Dict[str, Any] = {
            "event": "cycle_complete",
            "boards": list(self.cycle.boards),
            "duplicates": list(self.cycle.duplicates),
            "expected_boards": expected,
        }
        if expected and len(self.cycle.boards) < expected:
            event["shortfall"] = expected - len(self.cycle.boards)
        return event

    def create_time(self) -> Optional[Dict[str, Any]]:
        """`createTime` (epoch s) for the bank sample, with the clock offset seen."""
        if self.bank is None:
            return None
        received = self.bank.received
        if self.bank.timestamp_ms is None:
            return {"time": received, "source": "received", "offset_s": None}
        offset = self.bank.timestamp_ms / 1000 - received
        if abs(offset) > CREATE_TIME_TOLERANCE_S:
            return {"time": received, "source": "received", "offset_s": round(offset, 1)}
        return {"time": self.bank.timestamp_ms / 1000, "source": "metadata", "offset_s": round(offset, 1)}

    def board_serials(self) -> List[str]:
        return list(self.boards)
