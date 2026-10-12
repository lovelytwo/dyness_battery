import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dyness_battery import DOMAIN, DynessDataCoordinator
from frames import BANK_SN, BOARDS, LOGGER_SN
from test_local_setup import free_port, send_cycle


def cloud_points(items):
    return [{"flag": False, "pointId": k, "pointValue": v, "pointNameCn": ""} for k, v in items]


async def fake_cloud(self, session, path, body, max_retries=0):
    t = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 3600))
    if path == "/v1/device/storage/list":
        return {"code": 200, "data": {"list": [{
            "deviceSn": BANK_SN, "collectorSn": LOGGER_SN, "deviceModelName": "Powerbox Pro",
            "deviceCommunicationStatus": "Online",
        }]}}
    if path == "/v1/device/household/storage/detail":
        return {"code": 200, "data": {"deviceModelName": "Powerbox Pro", "stationName": "Home"}}
    if path == "/v1/station/info":
        return {"code": 200, "data": {"batteryCapacity": "5"}}
    if path == "/v1/device/realTime/data" and body.get("deviceSn") == BANK_SN:
        return {"code": 200, "data": cloud_points([
            ("T", t), ("SUB", ",".join(BOARDS[:2])), ("TIME", f"{t},{t}"),
            ("600", "52.0"), ("800", "90"), ("1200", "99"), ("7100", "321.0"),
        ])}
    if path == "/v1/device/realTime/data":
        return {"code": 200, "data": cloud_points([("T", t), ("10000", body["deviceSn"]), ("13500", "52.0")])}
    if path == "/v1/device/getLastPowerDataBySn":
        return {"code": 200, "data": [{"soc": "90", "realTimePower": "100", "createTime": t}]}
    return {"code": 200, "data": {}}


async def test_cloud_passthru_merges_fresh_local_values(socket_enabled, hass):
    port = free_port()
    entry = MockConfigEntry(
        domain=DOMAIN, title="Home",
        data={
            "source": "cloud_passthru", "api_id": "id", "api_secret": "secret",
            "api_base": "https://open-api.dyness.com", "device_sn": BANK_SN,
            "dongle_sn": LOGGER_SN, "upstream_host": "localhost", "upstream_port": 5005,
        },
        options={"fallback_to_endpoint": True},
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, "persistent_notification", {})
    with patch("custom_components.dyness_battery.local.ha.LOGGER_PORT", port), \
            patch.object(DynessDataCoordinator, "_call", fake_cloud):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is config_entries.ConfigEntryState.LOADED
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.data["soc"] == "90"

        for _ in range(5):
            assert await send_cycle(port, int(time.time() * 1000)) == 5
        await asyncio.sleep(0.05)
        issue = ir.async_get(hass).async_get_issue(DOMAIN, f"upstream_unreachable_{entry.entry_id}")
        assert issue is not None and issue.translation_placeholders["host"] == "localhost"

        await coordinator.async_refresh()
        data = coordinator.data
        assert data["soc"] == "95"
        assert data["packVoltage"] == "53.0"
        assert set(data["module_data"]) == set(BOARDS)

        trace_path = Path(hass.config.path("dyness_cloud_passthru.log"))
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    text = trace_path.read_text()
    assert "secret" not in text
    assert any(r.get("path") == "/v1/device/realTime/data" for r in records)
    compares = [r for r in records if r.get("event") == "compare" and r.get("device") == BANK_SN and "points" in r]
    assert compares and compares[-1]["points"]["800"] == {"cloud": "90", "local": 95}
    assert any(r.get("opcode") == "9104" and r.get("status") == "parsed" for r in records)
    assert any(r.get("event") == "cycle_complete" for r in records)
