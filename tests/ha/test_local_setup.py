import asyncio
import socket
import time
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dyness_battery import DOMAIN
from frames import BOARDS, bank_frame, board_frame, config_frame


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_flow_endpoint_and_single_listener(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "endpoint"})
    assert result["step_id"] == "endpoint"
    with patch("custom_components.dyness_battery.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device_model": "POWERBOX-PRO"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"source": "endpoint", "device_model": "POWERBOX-PRO"}

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "passthru"})
    assert result["errors"] == {"base": "listener_exists"}


async def test_flow_passthru_validates_upstream_host(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "passthru"})
    assert result["step_id"] == "upstream"
    for bad in ("127.0.0.1", "localhost", "300.1.1.1", "bad_host!"):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "upstream_host": bad, "upstream_port": 5005, "device_model": "POWERBOX-PRO",
        })
        assert result["errors"] == {"upstream_host": "invalid_upstream_host"}, bad
    with patch("custom_components.dyness_battery.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "upstream_host": "dyness-upstream.lan", "upstream_port": 5005, "device_model": "POWERBOX-PRO",
        })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["upstream_host"] == "dyness-upstream.lan"
    assert result["data"]["source"] == "passthru"


async def test_flow_cloud_passthru_goes_to_credentials(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "cloud_passthru"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "upstream_host": "47.254.174.207", "upstream_port": 5005,
    })
    assert result["step_id"] == "cloud"


async def test_flow_cloud_unchanged(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "cloud"})
    assert result["step_id"] == "cloud"
    with patch("custom_components.dyness_battery.config_flow._fetch_device_list", return_value=[
        {"deviceSn": "X-BMS", "stationName": "Home", "collectorSn": "X"},
    ]), patch("custom_components.dyness_battery.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "api_id": "id", "api_secret": "secret", "region": "europe",
        })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["source"] == "cloud" and result["data"]["device_sn"] == "X-BMS"


async def send_cycle(port: int, ts_ms: int) -> int:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    frames = [config_frame(ts_ms), bank_frame(ts_ms)] + [board_frame(sn, ts_ms) for sn in BOARDS]
    acks = 0
    for raw in frames:
        writer.write(raw)
        await writer.drain()
        reply = await asyncio.wait_for(reader.read(64), 2)
        acks += reply[-3:-1] in (b"\x99\x71", b"\x99\x04")
    writer.close()
    return acks


async def test_endpoint_entry_publishes_sensors(socket_enabled, hass):
    port = free_port()
    entry = MockConfigEntry(
        domain=DOMAIN, title="Dyness local endpoint",
        data={"source": "endpoint", "device_model": "POWERBOX-PRO"},
        options={"battery_capacity_override": "15"},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.dyness_battery.local.ha.LOGGER_PORT", port):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is config_entries.ConfigEntryState.LOADED
        assert not hass.states.async_entity_ids("switch")

        assert await send_cycle(port, int(time.time() * 1000)) == 5
        for _ in range(50):
            await hass.async_block_till_done()
            coordinator = hass.data[DOMAIN][entry.entry_id]
            if coordinator.data:
                break
            await asyncio.sleep(0.05)

        data = coordinator.data
        assert data["_schema"] == "powerbox_pro"
        assert data["soc"] == "95"
        assert float(data["realTimePower"]) == -932.8
        assert data["batteryStatus"] == "Discharging"
        assert data["batteryCapacity"] == 15.0
        assert data["remainingKwh"] == round(15.0 * 0.99 * 0.95, 3)
        assert data["deviceCommunicationStatus"] == "Online"
        assert data["firmwareVersion"] == "24.9-26.9.1"
        assert set(data["module_data"]) == set(BOARDS)
        assert data["module_data"][BOARDS[0]]["voltage"] is not None

        registry = er.async_get(hass)
        soc_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_soc")
        assert hass.states.get(soc_id).state == "95.0"
        for key, value in (("tempMax", "19.7"), ("tempMin", "18.8")):
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
            assert entity_id is not None, key
            assert hass.states.get(entity_id).state == value
        assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_alarmTotal") is not None
        module_entities = [e for e in er.async_entries_for_config_entry(registry, entry.entry_id) if BOARDS[1] in e.unique_id]
        assert module_entities

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        try:
            await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 1)
        except OSError:
            pass
        else:
            raise AssertionError("listener still accepting after unload")
