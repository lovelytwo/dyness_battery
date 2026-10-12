"""Home Assistant glue for the endpoint, passthru and cloud_passthru sources."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_CAPACITY_OVERRIDE,
    CONF_CAPTURE_UNKNOWN_RAW,
    CONF_DEVICE_MODEL,
    CONF_FALLBACK_TO_ENDPOINT,
    CONF_SOURCE,
    CONF_UPSTREAM_HOST,
    CONF_UPSTREAM_PORT,
    DEFAULT_UPSTREAM_PORT,
    ISSUE_UPSTREAM_UNREACHABLE,
    LOCAL_ONLY_SOURCES,
    LOGGER_PORT,
    SOURCE_CLOUD_PASSTHRU,
    SOURCE_ENDPOINT,
)
from .listener import MODE_ENDPOINT, MODE_PASSTHRU, REPAIR_AFTER_FAILURES, LoggerListener
from .responder import LocalResponder
from .store import LocalStore
from .trace import TRACE_FILENAME, Trace

_LOGGER = logging.getLogger(__name__)

DOMAIN = "dyness_battery"
LOCAL_DATA = f"{DOMAIN}_local"
STALE_CHECK_INTERVAL = timedelta(seconds=60)
LOCAL_ONLY_PLATFORMS = [Platform.SENSOR]


@dataclass
class LocalRuntime:
    listener: LoggerListener
    store: LocalStore
    trace: Optional[Trace]
    platforms: List[Platform]
    unsubs: List[Callable[[], None]]

    async def async_stop(self, hass: HomeAssistant) -> None:
        for unsub in self.unsubs:
            unsub()
        self.unsubs.clear()
        await self.listener.stop()
        if self.trace is not None:
            await hass.async_add_executor_job(self.trace.close)
            self.trace = None


def capacity_override(entry: ConfigEntry) -> Optional[float]:
    raw = str(entry.options.get(CONF_CAPACITY_OVERRIDE, "") or "").strip()
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


async def _own_addresses(hass: HomeAssistant) -> List[str]:
    try:
        from homeassistant.components import network

        return [str(ip) for ip in await network.async_get_enabled_source_ips(hass)]
    except Exception:  # noqa: BLE001 - the loop guard still checks loopback and the socket address
        return []


async def async_setup_local_entry(
    hass: HomeAssistant, entry: ConfigEntry, coordinator_cls, platforms: List[Platform]
):
    """Build the coordinator, responder and listener. Returns (coordinator, platforms)."""
    source = entry.data[CONF_SOURCE]
    local_only = source in LOCAL_ONLY_SOURCES
    store = LocalStore()

    if local_only:
        coordinator = coordinator_cls(
            hass, "local", "local", "local",
            device_sn=entry.data.get("device_sn") or entry.entry_id,
            config_entry=entry,
        )
        coordinator.update_interval = None
        coordinator._update_scan_interval = lambda: None
    else:
        coordinator = coordinator_cls(
            hass,
            entry.data["api_id"],
            entry.data["api_secret"],
            entry.data["api_base"],
            device_sn=entry.data.get("device_sn"),
            dongle_sn=entry.data.get("dongle_sn"),
            config_entry=entry,
        )

    trace: Optional[Trace] = None
    if source == SOURCE_CLOUD_PASSTHRU:
        trace = Trace(
            Path(hass.config.path(TRACE_FILENAME)),
            entry.entry_id,
            capture_unknown_raw=entry.options.get(CONF_CAPTURE_UNKNOWN_RAW, True),
        )
        await hass.async_add_executor_job(trace.open)
        _LOGGER.info("Dyness cloud_passthru trace: %s (sensitive, do not share unredacted)", trace.path)

    coordinator._call = LocalResponder(
        store,
        device_model=entry.data.get(CONF_DEVICE_MODEL, ""),
        bank_sn=lambda: coordinator.device_sn,
        capacity_total=lambda: capacity_override(entry),
        n_modules=lambda: len(set(coordinator._module_sns) | set(store.board_serials())),
        cloud_call=None if local_only else coordinator._call,
        trace=trace,
    )

    if local_only:
        upstream_update = coordinator._async_update_data

        async def _local_update():
            if store.bank is None:
                raise UpdateFailed("Dyness: waiting for the first logger upload")
            if not store.is_fresh(time.time()):
                raise UpdateFailed(
                    f"Dyness: no logger upload for more than {store.timeout_s} s"
                )
            return await upstream_update()

        coordinator._async_update_data = _local_update

    issue_id = f"{ISSUE_UPSTREAM_UNREACHABLE}_{entry.entry_id}"
    host = entry.data.get(CONF_UPSTREAM_HOST)
    port = int(entry.data.get(CONF_UPSTREAM_PORT, DEFAULT_UPSTREAM_PORT))

    @callback
    def _on_upstream(ok: bool, failures: int, error: Optional[str]) -> None:
        if ok:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
        elif failures >= REPAIR_AFTER_FAILURES:
            ir.async_create_issue(
                hass, DOMAIN, issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_UPSTREAM_UNREACHABLE,
                translation_placeholders={
                    "host": str(host), "port": str(port),
                    "failures": str(failures), "error": error or "",
                },
            )

    @callback
    def _on_update() -> None:
        if local_only:
            hass.async_create_task(coordinator.async_request_refresh())

    listener = LoggerListener(
        store,
        MODE_ENDPOINT if source == SOURCE_ENDPOINT else MODE_PASSTHRU,
        port=LOGGER_PORT,
        upstream_host=host,
        upstream_port=port,
        fallback_to_endpoint=bool(entry.options.get(CONF_FALLBACK_TO_ENDPOINT, False)),
        trace=trace,
        on_update=_on_update,
        on_upstream=_on_upstream,
        own_addresses=await _own_addresses(hass),
    )
    try:
        await listener.start()
    except OSError as err:
        if trace is not None:
            await hass.async_add_executor_job(trace.close)
        raise ConfigEntryNotReady(f"Dyness: cannot listen on port {LOGGER_PORT}: {err}") from err

    runtime = LocalRuntime(
        listener, store, trace,
        LOCAL_ONLY_PLATFORMS if local_only else list(platforms), [],
    )

    if local_only:
        @callback
        def _check_stale(_now) -> None:
            if coordinator.last_update_success and store.bank is not None and not store.is_fresh(time.time()):
                hass.async_create_task(coordinator.async_request_refresh())

        runtime.unsubs.append(async_track_time_interval(hass, _check_stale, STALE_CHECK_INTERVAL))

    async def _on_stop(_event) -> None:
        runtime.unsubs.remove(stop_unsub)
        await runtime.async_stop(hass)

    stop_unsub = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop)
    runtime.unsubs.append(stop_unsub)

    if not local_only:
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception:
            await runtime.async_stop(hass)
            raise

    hass.data.setdefault(LOCAL_DATA, {})[entry.entry_id] = runtime
    return coordinator, runtime.platforms


async def async_unload_local_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    runtime = hass.data.get(LOCAL_DATA, {}).pop(entry.entry_id, None)
    if runtime is not None:
        await runtime.async_stop(hass)
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_UPSTREAM_UNREACHABLE}_{entry.entry_id}")


def local_platforms(hass: HomeAssistant, entry: ConfigEntry, default: List[Platform]) -> List[Platform]:
    runtime = hass.data.get(LOCAL_DATA, {}).get(entry.entry_id)
    return runtime.platforms if runtime is not None else default
