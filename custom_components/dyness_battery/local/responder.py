"""Answers DynessDataCoordinator._call from local logger data.

Local sources (endpoint, passthru) get cloud-shaped JSON built from the
store, so upstream's mapping code runs unchanged. cloud_passthru calls the
real Open API first and overlays fresh local points per the merge rule.

No Home Assistant imports.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .store import CREATE_TIME_TOLERANCE_S, LocalStore, Sample
from .trace import Trace

PATH_STORAGE_LIST = "/v1/device/storage/list"
PATH_STORAGE_DETAIL = "/v1/device/household/storage/detail"
PATH_BIND = "/v1/device/bindSn"
PATH_STATION = "/v1/station/info"
PATH_REALTIME = "/v1/device/realTime/data"
PATH_POWER = "/v1/device/getLastPowerDataBySn"
PATH_RUNNING = "/v1/device/getLastRunningDataBySn"

CLOUD_ONLY_POINTS = ("T", "SUB", "TIME")

CloudCall = Callable[..., Awaitable[Dict[str, Any]]]


def ok(data: Any) -> Dict[str, Any]:
    return {"code": 200, "data": data, "info": "local"}


def fail(code: str, info: str) -> Dict[str, Any]:
    return {"code": code, "data": None, "info": info}


def format_value(value: Any) -> str:
    """Point value as the cloud writes it: ints plain, floats at float32 precision."""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(float(f"{value:.7g}"))
    return "" if value is None else str(value)


def format_time(epoch_s: float) -> str:
    return dt.datetime.fromtimestamp(epoch_s, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_time(text: Any) -> Optional[float]:
    try:
        return dt.datetime.strptime(str(text), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=dt.timezone.utc
        ).timestamp()
    except ValueError:
        return None


def sample_time(sample: Sample) -> float:
    if sample.timestamp_ms is not None:
        metadata = sample.timestamp_ms / 1000
        if abs(metadata - sample.received) <= CREATE_TIME_TOLERANCE_S:
            return metadata
    return sample.received


def point_items(points: Dict[int, Any]) -> List[Dict[str, Any]]:
    return [
        {"flag": False, "pointId": str(pid), "pointValue": format_value(value)}
        for pid, value in points.items()
    ]


def realtime_items(store: LocalStore, sn: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """Cloud-shaped realTime/data list for the bank or a board, or None."""
    if sn is not None and sn in store.boards:
        sample = store.boards[sn]
        return [{"flag": False, "pointId": "T", "pointValue": format_time(sample_time(sample))}] + point_items(sample.points)
    if store.bank is None:
        return None
    boards = store.board_serials()
    return [
        {"flag": False, "pointId": "T", "pointValue": format_time(sample_time(store.bank))},
        {"flag": False, "pointId": "SUB", "pointValue": ",".join(boards)},
        {"flag": False, "pointId": "TIME", "pointValue": ",".join(
            format_time(sample_time(store.boards[b])) for b in boards
        )},
    ] + point_items(store.bank.points)


def power_data(store: LocalStore) -> Optional[Dict[str, Any]]:
    if store.bank is None:
        return None
    points = store.bank.points
    created = store.create_time()
    out: Dict[str, Any] = {"createTime": format_time(created["time"]) if created else None}
    if 800 in points:
        out["soc"] = format_value(points[800])
    voltage, current = points.get(600), points.get(700)
    if isinstance(current, (int, float)):
        out["realTimeCurrent"] = format_value(current)
        if isinstance(voltage, (int, float)):
            out["realTimePower"] = format_value(round(voltage * current, 1))
    return out


def device_entry(store: LocalStore, device_model: str, now: float) -> Dict[str, Any]:
    return {
        "deviceSn": store.bank_sn,
        "collectorSn": store.logger_serial,
        "deviceName": device_model,
        "deviceModelName": device_model,
        "deviceCommunicationStatus": "Online" if store.is_fresh(now) else "Offline",
        "firmwareVersion": format_value(store.bank.points.get(300)) if store.bank else None,
    }


def local_response(
    store: LocalStore,
    path: str,
    body: Dict[str, Any],
    *,
    now: float,
    device_model: str,
    capacity_total: Optional[float],
    n_modules: int,
) -> Dict[str, Any]:
    """Cloud-shaped answer for one Open API path, built from the store."""
    if path == PATH_STORAGE_LIST:
        if store.bank is None:
            return ok({"list": [], "total": 0})
        return ok({"list": [device_entry(store, device_model, now)], "total": 1})
    if path == PATH_STORAGE_DETAIL:
        return ok(device_entry(store, device_model, now)) if store.bank else fail("404", "no local data yet")
    if path == PATH_BIND:
        return ok(None)
    if path == PATH_STATION:
        if capacity_total is None:
            return ok({})
        return ok({"batteryCapacity": format_value(round(capacity_total / max(n_modules, 1), 4))})
    if path == PATH_REALTIME:
        items = realtime_items(store, body.get("deviceSn"))
        return ok(items) if items is not None else fail("404", "no local data yet")
    if path == PATH_POWER:
        data = power_data(store)
        return ok(data) if data is not None else fail("404", "no local data yet")
    if path == PATH_RUNNING:
        return ok({})
    if path.startswith("/v2/Set"):
        return fail("403", "writes are not available on local sources")
    return fail("404", f"{path} has no local source")


# ── cloud_passthru merge ────────────────────────────────────────────────


def _items_to_dict(items: Any) -> Dict[str, Any]:
    if not isinstance(items, list):
        return {}
    return {
        str(item["pointId"]): item.get("pointValue")
        for item in items
        if isinstance(item, dict) and "pointId" in item
    }


def _overlay_points(
    cloud_items: List[Dict[str, Any]], local_points: Dict[int, Any]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Replace cloud values with local ones for every local point ID; add local-only IDs."""
    local = {str(k): v for k, v in local_points.items()}
    used: Dict[str, str] = {}
    out = []
    for item in cloud_items:
        pid = str(item.get("pointId"))
        if pid in local:
            out.append({**item, "pointValue": format_value(local[pid])})
            used[pid] = "local"
        else:
            out.append(item)
            used[pid] = "cloud"
    for pid, value in local.items():
        if pid not in used:
            out.append({"flag": False, "pointId": pid, "pointValue": format_value(value)})
            used[pid] = "local"
    return out, used


def merge_bank(
    store: LocalStore, cloud: Dict[str, Any], now: float
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Bank realTime/data: local values while the session is fresh; SUB/TIME merged per board."""
    items = cloud.get("data") if _success(cloud) else None
    cloud_points = _items_to_dict(items)
    info: Dict[str, Any] = {"cloud_T": cloud_points.get("T")}
    if store.bank is None or not store.is_fresh(now):
        info["used"] = "cloud"
        return cloud, info
    merged, used = _overlay_points(list(items or []), store.bank.points)
    cloud_sub = [s for s in str(cloud_points.get("SUB") or "").split(",") if s]
    cloud_time = str(cloud_points.get("TIME") or "").split(",")
    times = dict(zip(cloud_sub, cloud_time))
    boards = list(dict.fromkeys(store.board_serials() + cloud_sub))
    board_times = []
    for sn in boards:
        if store.board_is_fresh(sn, now):
            board_times.append(format_time(sample_time(store.boards[sn])))
        else:
            board_times.append(times.get(sn) or format_time(sample_time(store.boards[sn])))
    replacements = {
        "T": format_time(sample_time(store.bank)),
        "SUB": ",".join(boards),
        "TIME": ",".join(board_times),
    }
    present = set()
    for item in merged:
        if item.get("pointId") in replacements:
            item["pointValue"] = replacements[item["pointId"]]
            present.add(item["pointId"])
    head = [{"flag": False, "pointId": k, "pointValue": v} for k, v in replacements.items() if k not in present]
    info["used"] = used
    return {**cloud, "code": 200, "data": head + merged}, info


def board_choice(
    store: LocalStore, sn: str, cloud_time: Optional[float], now: float
) -> str:
    """'local' or 'cloud' for one board's realTime/data."""
    sample = store.boards.get(sn)
    if sample is None:
        return "cloud"
    if store.board_is_fresh(sn, now):
        return "local"
    if cloud_time is not None and cloud_time > sample_time(sample):
        return "cloud"
    return "local"


def merge_board(
    store: LocalStore, sn: str, cloud: Dict[str, Any], now: float
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    cloud_items = cloud.get("data") if _success(cloud) else None
    cloud_points = _items_to_dict(cloud_items)
    choice = board_choice(store, sn, parse_time(cloud_points.get("T")) if cloud_items else None, now)
    info = {"board": sn, "cloud_T": cloud_points.get("T"), "used": choice}
    if choice == "cloud":
        return cloud, info
    sample = store.boards[sn]
    merged, _ = _overlay_points(list(cloud_items or []), sample.points)
    stamp = format_time(sample_time(sample))
    if any(item.get("pointId") == "T" for item in merged):
        for item in merged:
            if item.get("pointId") == "T":
                item["pointValue"] = stamp
    else:
        merged.insert(0, {"flag": False, "pointId": "T", "pointValue": stamp})
    return {**cloud, "code": 200, "data": merged}, info


def merge_power(store: LocalStore, cloud: Dict[str, Any], now: float) -> Tuple[Dict[str, Any], str]:
    local = power_data(store)
    if local is None or not store.is_fresh(now):
        return cloud, "cloud"
    data = cloud.get("data") if _success(cloud) else None
    if isinstance(data, list):
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("soc") is not None), {})
    base = dict(data) if isinstance(data, dict) else {}
    base.update({k: v for k, v in local.items() if v is not None})
    return {**cloud, "code": 200, "data": base}, "local"


def compare_record(
    store: LocalStore, sn: Optional[str], cloud: Dict[str, Any], info: Dict[str, Any]
) -> Dict[str, Any]:
    cloud_points = _items_to_dict(cloud.get("data"))
    sample = store.boards.get(sn) if sn in store.boards else (store.bank if sn == store.bank_sn else None)
    local = {str(k): v for k, v in (sample.points.items() if sample else [])}
    points = {}
    never_local = []
    for pid, value in cloud_points.items():
        if pid in CLOUD_ONLY_POINTS:
            continue
        if pid in local:
            points[pid] = {"cloud": value, "local": local[pid]}
        else:
            never_local.append(pid)
    return {
        "device": sn,
        "cloud_T": cloud_points.get("T"),
        "SUB": cloud_points.get("SUB"),
        "TIME": cloud_points.get("TIME"),
        "local_time": format_time(sample_time(sample)) if sample else None,
        "points": points,
        "cloud_only": never_local,
        "used": info.get("used"),
    }


def _success(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    code = result.get("code")
    return str(code) in ("0", "200") or code == 0


class LocalResponder:
    """Stand-in for DynessDataCoordinator._call."""

    def __init__(
        self,
        store: LocalStore,
        *,
        device_model: str,
        bank_sn: Callable[[], Optional[str]],
        capacity_total: Callable[[], Optional[float]],
        n_modules: Callable[[], int],
        cloud_call: Optional[CloudCall] = None,
        trace: Optional[Trace] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.device_model = device_model
        self._bank_sn = bank_sn
        self._capacity_total = capacity_total
        self._n_modules = n_modules
        self.cloud_call = cloud_call
        self.trace = trace
        self.clock = clock
        self._last_cloud_t: Optional[str] = None

    async def __call__(self, session: Any, path: str, body_dict: Dict[str, Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
        now = self.clock()
        if self.cloud_call is None:
            return local_response(
                self.store, path, body_dict or {}, now=now,
                device_model=self.device_model,
                capacity_total=self._capacity_total(),
                n_modules=self._n_modules(),
            )
        try:
            cloud = await self.cloud_call(session, path, body_dict, *args, **kwargs)
        except Exception as exc:
            if self.trace:
                self.trace.api(path, body_dict, {"error": repr(exc)})
            raise
        if self.trace:
            self.trace.api(path, body_dict, cloud)
        return self._merge(path, body_dict or {}, cloud, now)

    def _merge(self, path: str, body: Dict[str, Any], cloud: Dict[str, Any], now: float) -> Dict[str, Any]:
        if path == PATH_REALTIME:
            sn = body.get("deviceSn")
            if sn and sn in self.store.boards:
                merged, info = merge_board(self.store, sn, cloud, now)
            elif sn == self._bank_sn() or (sn and sn == self.store.bank_sn):
                merged, info = merge_bank(self.store, cloud, now)
                cloud_t = info.get("cloud_T")
                info["cloud_T_advanced"] = cloud_t != self._last_cloud_t
                self._last_cloud_t = cloud_t
            else:
                return cloud
            if self.trace:
                record = compare_record(self.store, sn if sn in self.store.boards else self.store.bank_sn, cloud, info)
                if "cloud_T_advanced" in info:
                    record["cloud_T_advanced"] = info["cloud_T_advanced"]
                self.trace.compare(record)
            return merged
        if path == PATH_POWER:
            merged, used = merge_power(self.store, cloud, now)
            if self.trace:
                self.trace.compare({"device": body.get("deviceSn"), "path": path, "used": used})
            return merged
        return cloud
