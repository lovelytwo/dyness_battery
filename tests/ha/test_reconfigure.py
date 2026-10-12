import asyncio
import time
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dyness_battery import DOMAIN
from frames import BANK_SN, BOARDS, LOGGER_SN
from test_local_setup import free_port, send_cycle

CLOUD_DATA = {
    "api_id": "id", "api_secret": "secret", "api_base": "https://open-api.dyness.com",
    "device_sn": BANK_SN, "dongle_sn": LOGGER_SN, "known_module_sns": list(BOARDS),
}


def no_setup():
    return patch("custom_components.dyness_battery.async_setup_entry", return_value=True), \
        patch("custom_components.dyness_battery.async_unload_entry", return_value=True)


async def start_reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )


async def test_cloud_to_endpoint_and_back_keeps_credentials(hass):
    entry = MockConfigEntry(domain=DOMAIN, title="Home", unique_id=f"id_{BANK_SN}", data=dict(CLOUD_DATA))
    entry.add_to_hass(hass)
    setup, unload = no_setup()
    with setup, unload:
        result = await start_reconfigure(hass, entry)
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "endpoint"})
        assert result["step_id"] == "endpoint"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device_model": "POWERBOX-PRO"})
        assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
        assert entry.data["source"] == "endpoint"
        assert entry.data["device_sn"] == BANK_SN and entry.data["api_secret"] == "secret"
        assert entry.data["known_module_sns"] == list(BOARDS)
        assert entry.unique_id == f"local_{BANK_SN}"

        result = await start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "cloud"})
        assert result["step_id"] == "cloud_keep"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"keep_credentials": True})
        assert result["reason"] == "reconfigure_successful"
        assert entry.data["source"] == "cloud" and entry.data["device_model"] == "POWERBOX-PRO"
        assert entry.unique_id == f"id_{BANK_SN}"


async def test_cloud_to_cloud_passthru_keeps_device(hass):
    entry = MockConfigEntry(domain=DOMAIN, title="Home", unique_id=f"id_{BANK_SN}", data=dict(CLOUD_DATA))
    entry.add_to_hass(hass)
    setup, unload = no_setup()
    with setup, unload:
        result = await start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "cloud_passthru"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "upstream_host": "47.254.174.207", "upstream_port": 5005,
        })
        assert result["step_id"] == "cloud_keep"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"keep_credentials": True})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["source"] == "cloud_passthru" and entry.data["upstream_host"] == "47.254.174.207"
    assert entry.data["device_sn"] == BANK_SN


async def test_passthru_host_change_in_place(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "passthru", "upstream_host": "old.lan", "upstream_port": 5005, "device_model": "POWERBOX-PRO",
    })
    entry.add_to_hass(hass)
    setup, unload = no_setup()
    with setup, unload:
        result = await start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "passthru"})
        assert result["step_id"] == "upstream"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "upstream_host": "new.lan", "upstream_port": 5005, "device_model": "POWERBOX-PRO",
        })
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["upstream_host"] == "new.lan"


async def test_local_to_cloud_different_battery_asks_first(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "endpoint", "device_model": "POWERBOX-PRO", "device_sn": BANK_SN,
    })
    entry.add_to_hass(hass)
    setup, unload = no_setup()
    with setup, unload, patch(
        "custom_components.dyness_battery.config_flow._fetch_device_list",
        return_value=[{"deviceSn": "OTHER-BMS", "collectorSn": "OTHER"}],
    ):
        result = await start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "cloud"})
        assert result["step_id"] == "cloud"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "api_id": "id", "api_secret": "secret", "region": "europe",
        })
        assert result["step_id"] == "confirm_replace"
        assert entry.data["device_sn"] == BANK_SN
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["device_sn"] == "OTHER-BMS" and entry.unique_id == "id_OTHER-BMS"


async def test_reconfigure_refuses_second_listener_and_duplicate(hass):
    MockConfigEntry(domain=DOMAIN, data={"source": "endpoint", "device_model": "POWERBOX-PRO"}).add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, unique_id="id_OTHER-BMS", data={**CLOUD_DATA, "device_sn": "OTHER-BMS"}).add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=f"id_{BANK_SN}", data=dict(CLOUD_DATA))
    entry.add_to_hass(hass)

    result = await start_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "passthru"})
    assert result["errors"] == {"base": "listener_exists"}

    with patch(
        "custom_components.dyness_battery.config_flow._fetch_device_list",
        return_value=[{"deviceSn": "OTHER-BMS"}],
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "cloud"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"keep_credentials": False})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "api_id": "id", "api_secret": "secret", "region": "europe",
        })
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data["device_sn"] == BANK_SN


async def wait_for_data(hass, entry):
    for _ in range(50):
        await hass.async_block_till_done()
        if hass.data[DOMAIN][entry.entry_id].data:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("no coordinator data")


async def test_new_local_entry_learns_serial(socket_enabled, hass):
    port = free_port()
    entry = MockConfigEntry(domain=DOMAIN, data={"source": "endpoint", "device_model": "POWERBOX-PRO"})
    entry.add_to_hass(hass)
    with patch("custom_components.dyness_battery.local.ha.LOGGER_PORT", port):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = dr.async_get(hass)
        registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)})

        assert await send_cycle(port, int(time.time() * 1000)) == 5
        await wait_for_data(hass, entry)

        assert entry.data["device_sn"] == BANK_SN and entry.data["dongle_sn"] == LOGGER_SN
        assert entry.unique_id == f"local_{BANK_SN}"
        identifiers = {i for d in dr.async_entries_for_config_entry(registry, entry.entry_id) for i in d.identifiers}
        assert (DOMAIN, BANK_SN) in identifiers
        assert (DOMAIN, f"{BANK_SN}_{BOARDS[0]}") in identifiers
        assert not any(entry.entry_id in ident for _, ident in identifiers)
        assert len(dr.async_entries_for_config_entry(registry, entry.entry_id)) == 1 + len(BOARDS)

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_serial_mismatch_keeps_stored_serial(socket_enabled, hass):
    port = free_port()
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "endpoint", "device_model": "POWERBOX-PRO", "device_sn": "OTHER-BMS",
    })
    entry.add_to_hass(hass)
    with patch("custom_components.dyness_battery.local.ha.LOGGER_PORT", port):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await send_cycle(port, int(time.time() * 1000)) == 5
        await wait_for_data(hass, entry)

        assert entry.data["device_sn"] == "OTHER-BMS"
        assert hass.data[DOMAIN][entry.entry_id].device_sn == "OTHER-BMS"
        issue = ir.async_get(hass).async_get_issue(DOMAIN, f"serial_mismatch_{entry.entry_id}")
        assert issue is not None and issue.translation_placeholders["received"] == BANK_SN

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert ir.async_get(hass).async_get_issue(DOMAIN, f"serial_mismatch_{entry.entry_id}") is None
