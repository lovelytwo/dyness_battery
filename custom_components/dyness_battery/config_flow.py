"""Config Flow für Dyness Battery Integration."""
import ipaddress
import re
from pathlib import Path

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import DOMAIN, _BMS_SUFFIXES, _MODEL_SCHEMA_MAP, _is_success
from .local.const import (
    CONF_CAPTURE_UNKNOWN_RAW,
    CONF_DEVICE_MODEL,
    CONF_FALLBACK_TO_ENDPOINT,
    CONF_SOURCE,
    CONF_UPSTREAM_HOST,
    CONF_UPSTREAM_PORT,
    DEFAULT_UPSTREAM_PORT,
    LISTENER_SOURCES,
    LOCAL_UNIQUE_ID_PREFIX,
    SOURCE_CLOUD,
    SOURCE_CLOUD_PASSTHRU,
    SOURCE_ENDPOINT,
    SOURCE_PASSTHRU,
    SOURCES,
    UPSTREAM_SOURCES,
)
import hashlib
import hmac
import base64
import aiohttp
from email.utils import formatdate

_HOSTNAME_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")


def _valid_upstream_host(value: str) -> bool:
    """IPv4 address (not loopback/unspecified) or an RFC 1123 hostname."""
    value = (value or "").strip()
    if not value:
        return False
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        return ip.version == 4 and not ip.is_loopback and not ip.is_unspecified
    if re.fullmatch(r"[0-9.]+", value) or len(value) > 253:
        return False
    labels = value.rstrip(".").split(".")
    return value.lower() != "localhost" and all(_HOSTNAME_LABEL.match(label) for label in labels)


async def _trace_discovery(hass, path: str, response) -> None:
    """Write a cloud_passthru discovery call to the trace file."""
    from .local.trace import TRACE_FILENAME, Trace

    trace = Trace(Path(hass.config.path(TRACE_FILENAME)), "config_flow")
    await hass.async_add_executor_job(trace.open)
    trace.api(path, {}, response)
    await hass.async_add_executor_job(trace.close)

# API Domains je Region
API_REGIONS = {
    "europe": "https://open-api.dyness.com",
    "apac":   "https://apacopen-api.dyness.com",
}


def _build_headers_cf(api_id, api_secret, body, path):
    date = formatdate(timeval=None, localtime=False, usegmt=True)
    md5 = base64.b64encode(hashlib.md5(body.encode()).digest()).decode()
    sts = f"POST\n{md5}\napplication/json\n{date}\n{path}"
    sig = base64.b64encode(
        hmac.new(api_secret.encode(), sts.encode(), "sha1").digest()
    ).decode()
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "Content-MD5": md5,
        "Date": date,
        "Authorization": f"API {api_id}:{sig}",
    }


async def _fetch_device_list(api_id: str, api_secret: str, api_base: str,
                             on_response=None) -> list:
    """Gibt alle Geräte auf dem Account zurück."""
    path = "/v1/device/storage/list"
    url = f"{api_base}/openapi/ems-device{path}"
    body = "{}"
    headers = _build_headers_cf(api_id, api_secret, body, path)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, data=body,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json(content_type=None)
                if on_response is not None:
                    await on_response(path, result)
                if _is_success(result):
                    return (result.get("data", {}) or {}).get("list", [])
    except Exception:
        pass
    return []


def _select_bms_devices(device_list: list) -> list:
    """Filtert BMS/BDU Geräte — ein Eintrag pro physischem Gerät."""
    bms_devices = [
        d for d in device_list
        if str(d.get("deviceSn", "")).endswith(_BMS_SUFFIXES)
    ]
    # Fallback: alle Geräte wenn kein BMS-Suffix gefunden
    return bms_devices if bms_devices else device_list


# ── Options: Alarm-Delay ─────────────────────────────────────────────────────
# Konfigurierbare Mindestdauer bevor ein Alarm als Notification gemeldet wird.
# Verhindert Benachrichtigungen bei kurzzeitigen Transient-Ereignissen
# (z.B. Pack-High-Voltage beim Balancing auf 100% SOC).
ALARM_DELAY_OPTIONS = {
    "0":   "Sofort (Standard)",
    "15":  "15 Minuten",
    "30":  "30 Minuten",
    "60":  "60 Minuten",
    "120": "2 Stunden",
}


class DynessOptionsFlow(config_entries.OptionsFlow):
    """Options-Dialog: Alarm-Delay konfigurieren."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            cap_raw = str(user_input.get("battery_capacity_override", "")).strip()
            if cap_raw:
                try:
                    cap_val = float(cap_raw.replace(",", "."))
                    if cap_val <= 0:
                        raise ValueError
                except ValueError:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=self._build_schema(user_input),
                        errors={"battery_capacity_override": "invalid_capacity"},
                    )
            # Integration neu laden, damit neue Optionen sofort wirksam werden
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.config_entry.entry_id)
            )
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_schema(),
        )

    def _build_schema(self, prefill=None):
        prefill = prefill or {}
        current_delay = str(
            prefill.get("alarm_delay_minutes")
            or self.config_entry.options.get("alarm_delay_minutes", "0")
        )
        current_cap = str(
            prefill.get("battery_capacity_override", "")
            or self.config_entry.options.get("battery_capacity_override", "")
        )
        fields = {
            vol.Required(
                "alarm_delay_minutes",
                default=current_delay,
            ): vol.In(ALARM_DELAY_OPTIONS),
            # suggested_value zeigt aktuellen Wert an, erzwingt ihn aber nicht —
            # damit kann der User das Feld leeren (leerer String = kein Override)
            vol.Optional(
                "battery_capacity_override",
                description={"suggested_value": current_cap},
            ): str,
        }
        source = self.config_entry.data.get(CONF_SOURCE, SOURCE_CLOUD)
        if source in UPSTREAM_SOURCES:
            fields[vol.Required(
                CONF_FALLBACK_TO_ENDPOINT,
                default=bool(prefill.get(
                    CONF_FALLBACK_TO_ENDPOINT,
                    self.config_entry.options.get(CONF_FALLBACK_TO_ENDPOINT, False),
                )),
            )] = bool
        if source == SOURCE_CLOUD_PASSTHRU:
            fields[vol.Required(
                CONF_CAPTURE_UNKNOWN_RAW,
                default=bool(prefill.get(
                    CONF_CAPTURE_UNKNOWN_RAW,
                    self.config_entry.options.get(CONF_CAPTURE_UNKNOWN_RAW, True),
                )),
            )] = bool
        return vol.Schema(fields)


STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("api_id"): str,
    vol.Required("api_secret"): str,
    vol.Required("region", default="europe"): vol.In(["europe", "apac"]),
})


class DynessConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow für Dyness Battery."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Options-Dialog für bestehende Einträge (Zahnrad-Button auf der Integrationskachel).
        
        Hinweis: config_entry wird NICHT an den Konstruktor übergeben — HA 2024.x setzt
        self.config_entry automatisch. Übergabe als Argument würde einen 500-Fehler auslösen.
        """
        return DynessOptionsFlow()

    def __init__(self):
        self._api_id = None
        self._api_secret = None
        self._api_base = None
        self._devices = []      # alle gefundenen Geräte
        self._region = "europe"
        self._source = SOURCE_CLOUD
        self._upstream: dict = {}
        self._pending_device: dict | None = None

    @property
    def _reconfiguring(self) -> bool:
        return self.source == config_entries.SOURCE_RECONFIGURE

    def _current(self, key, default=None):
        """Stored value of the entry being reconfigured (default for a new entry)."""
        if not self._reconfiguring:
            return default
        return self._get_reconfigure_entry().data.get(key, default)

    def _other_entries(self):
        own = self._get_reconfigure_entry().entry_id if self._reconfiguring else None
        return [e for e in self._async_current_entries() if e.entry_id != own]

    def _listener_entry_exists(self) -> bool:
        return any(
            entry.data.get(CONF_SOURCE, SOURCE_CLOUD) in LISTENER_SOURCES
            for entry in self._other_entries()
        )

    def _unique_id_taken(self, unique_id: str) -> bool:
        return any(entry.unique_id == unique_id for entry in self._other_entries())

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        """Bestehenden Eintrag ändern: Quelle, Upstream, Modell oder Zugangsdaten."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Schritt 0: Datenquelle wählen."""
        errors = {}
        if user_input is not None:
            self._source = user_input[CONF_SOURCE]
            if self._source in LISTENER_SOURCES and self._listener_entry_exists():
                errors["base"] = "listener_exists"
            elif self._source == SOURCE_CLOUD:
                return await self.async_step_cloud_keep()
            elif self._source == SOURCE_ENDPOINT:
                return await self.async_step_endpoint()
            else:
                return await self.async_step_upstream()

        return self.async_show_form(
            step_id="reconfigure" if self._reconfiguring else "user",
            data_schema=vol.Schema({
                vol.Required(CONF_SOURCE, default=self._current(CONF_SOURCE, SOURCE_CLOUD)): SelectSelector(
                    SelectSelectorConfig(
                        options=list(SOURCES),
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_SOURCE,
                    )
                ),
            }),
            errors=errors,
        )

    def _model_schema(self) -> dict:
        default = self._current(CONF_DEVICE_MODEL, "POWERBOX-PRO")
        if default not in _MODEL_SCHEMA_MAP:
            default = "POWERBOX-PRO"
        return {vol.Required(CONF_DEVICE_MODEL, default=default): vol.In(list(_MODEL_SCHEMA_MAP))}

    async def async_step_cloud_keep(self, user_input=None) -> FlowResult:
        """Reconfigure: gespeicherte Zugangsdaten und Gerät behalten oder neu eingeben."""
        stored = {k: self._current(k) for k in ("api_id", "api_secret", "api_base", "device_sn")}
        if not all(stored.values()):
            return await self.async_step_cloud()
        if user_input is None:
            return self.async_show_form(
                step_id="cloud_keep",
                data_schema=vol.Schema({vol.Required("keep_credentials", default=True): bool}),
                description_placeholders={"device_sn": stored["device_sn"]},
            )
        if not user_input["keep_credentials"]:
            return await self.async_step_cloud()
        self._api_id = stored["api_id"]
        self._api_secret = stored["api_secret"]
        self._api_base = stored["api_base"]
        return await self._update_cloud_entry({
            "deviceSn": stored["device_sn"], "collectorSn": self._current("dongle_sn"),
        })

    async def async_step_confirm_replace(self, user_input=None) -> FlowResult:
        """Reconfigure: Discovery liefert eine andere Batterie als gespeichert."""
        if user_input is not None:
            return await self._update_cloud_entry(self._pending_device, replace=True)
        return self.async_show_form(
            step_id="confirm_replace",
            data_schema=vol.Schema({}),
            description_placeholders={
                "stored": str(self._current("device_sn")),
                "new": str(self._pending_device.get("deviceSn")),
            },
        )

    async def _update_cloud_entry(self, device: dict, replace: bool = False) -> FlowResult:
        sn = device.get("deviceSn", "")
        unique_id = f"{self._api_id}_{sn}"
        if self._unique_id_taken(unique_id):
            return self.async_abort(reason="already_configured")
        data_updates = {
            "api_id":     self._api_id,
            "api_secret": self._api_secret,
            "api_base":   self._api_base,
            "device_sn":  sn,
            "dongle_sn":  device.get("collectorSn") or None,
            CONF_SOURCE:  self._source,
            **self._upstream,
        }
        if replace:
            data_updates["known_module_sns"] = []
        return self.async_update_reload_and_abort(
            self._get_reconfigure_entry(), unique_id=unique_id, data_updates=data_updates,
        )

    async def async_step_endpoint(self, user_input=None) -> FlowResult:
        """Lokaler Endpoint: nur Gerätemodell."""
        if user_input is not None:
            return self._create_local_entry({CONF_DEVICE_MODEL: user_input[CONF_DEVICE_MODEL]})
        return self.async_show_form(step_id="endpoint", data_schema=vol.Schema(self._model_schema()))

    async def async_step_upstream(self, user_input=None) -> FlowResult:
        """Passthru / Cloud+Passthru: Upstream-Adresse (IPv4 oder Hostname)."""
        errors = {}
        if user_input is not None:
            host = str(user_input.get(CONF_UPSTREAM_HOST, "")).strip()
            port = user_input.get(CONF_UPSTREAM_PORT, DEFAULT_UPSTREAM_PORT)
            if not _valid_upstream_host(host):
                errors[CONF_UPSTREAM_HOST] = "invalid_upstream_host"
            if not (1 <= int(port) <= 65535):
                errors[CONF_UPSTREAM_PORT] = "invalid_port"
            if not errors:
                self._upstream = {CONF_UPSTREAM_HOST: host, CONF_UPSTREAM_PORT: int(port)}
                if self._source == SOURCE_PASSTHRU:
                    return self._create_local_entry({
                        **self._upstream, CONF_DEVICE_MODEL: user_input[CONF_DEVICE_MODEL],
                    })
                return await self.async_step_cloud_keep()

        fields = {
            vol.Required(
                CONF_UPSTREAM_HOST,
                default=(user_input or {}).get(CONF_UPSTREAM_HOST, self._current(CONF_UPSTREAM_HOST, "")),
            ): str,
            vol.Required(
                CONF_UPSTREAM_PORT, default=self._current(CONF_UPSTREAM_PORT, DEFAULT_UPSTREAM_PORT),
            ): vol.Coerce(int),
        }
        if self._source == SOURCE_PASSTHRU:
            fields.update(self._model_schema())
        return self.async_show_form(
            step_id="upstream", data_schema=vol.Schema(fields), errors=errors,
        )

    def _create_local_entry(self, data: dict) -> FlowResult:
        if self._reconfiguring:
            kwargs = {}
            sn = self._current("device_sn")
            if sn:
                kwargs["unique_id"] = f"{LOCAL_UNIQUE_ID_PREFIX}{sn}"
                if self._unique_id_taken(kwargs["unique_id"]):
                    return self.async_abort(reason="already_configured")
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates={CONF_SOURCE: self._source, **data},
                **kwargs,
            )
        titles = {SOURCE_ENDPOINT: "Dyness local endpoint", SOURCE_PASSTHRU: "Dyness local passthru"}
        return self.async_create_entry(
            title=titles[self._source],
            data={CONF_SOURCE: self._source, **data},
        )

    async def async_step_cloud(self, user_input=None) -> FlowResult:
        """Schritt 1: API-Zugangsdaten + Region."""
        errors = {}

        if user_input is not None:
            self._api_id     = user_input["api_id"]
            self._api_secret = user_input["api_secret"]
            self._region     = user_input["region"]
            self._api_base   = API_REGIONS[self._region]

            on_response = None
            if self._source == SOURCE_CLOUD_PASSTHRU:
                async def on_response(path, result):
                    await _trace_discovery(self.hass, path, result)

            device_list = await _fetch_device_list(
                self._api_id, self._api_secret, self._api_base, on_response
            )
            self._devices = _select_bms_devices(device_list)

            if not self._devices:
                errors["base"] = "discovery_failed"
            elif len(self._devices) == 1:
                # Nur ein Gerät → direkt anlegen
                return await self._create_entry_for_device(self._devices[0])
            else:
                # Mehrere Geräte → Auswahl anbieten
                return await self.async_step_select_device()

        schema = STEP_USER_DATA_SCHEMA
        if self._reconfiguring:
            stored_base = self._current("api_base")
            region = next((r for r, url in API_REGIONS.items() if url == stored_base), "europe")
            schema = vol.Schema({
                vol.Required("api_id", default=self._current("api_id") or ""): str,
                vol.Required("api_secret"): str,
                vol.Required("region", default=region): vol.In(["europe", "apac"]),
            })
        return self.async_show_form(
            step_id="cloud",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_select_device(self, user_input=None) -> FlowResult:
        """Schritt 2: Gerät auswählen (bei mehreren Geräten auf dem Account)."""
        errors = {}

        if user_input is not None:
            sn = user_input["device_sn"]
            device = next(
                (d for d in self._devices if d.get("deviceSn") == sn), None
            )
            if device:
                return await self._create_entry_for_device(device)
            errors["base"] = "device_not_found"

        # Auswahl-Liste aufbauen
        device_options = {
            d["deviceSn"]: (
                f"{d.get('deviceModelName', 'Dyness')} — "
                f"{d.get('stationName', d['deviceSn'])} "
                f"({d.get('workStatus', '?')})"
            )
            for d in self._devices
            if d.get("deviceSn")
        }

        schema = vol.Schema({
            vol.Required("device_sn"): vol.In(device_options),
        })

        return self.async_show_form(
            step_id="select_device",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "count": str(len(self._devices)),
            },
        )

    async def _create_entry_for_device(self, device: dict) -> FlowResult:
        """Legt einen Config Entry für ein Gerät an."""
        sn = device.get("deviceSn", "")
        station_name = device.get("stationName") or "Dyness Battery"

        if self._reconfiguring:
            stored = self._current("device_sn")
            if stored and sn != stored:
                self._pending_device = device
                return await self.async_step_confirm_replace()
            return await self._update_cloud_entry(device)

        # unique_id = api_id + deviceSN → jedes Gerät separat konfigurierbar
        await self.async_set_unique_id(f"{self._api_id}_{sn}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=station_name,
            data={
                "api_id":     self._api_id,
                "api_secret": self._api_secret,
                "api_base":   self._api_base,
                "device_sn":  sn,
                "dongle_sn":  device.get("collectorSn") or None,
                CONF_SOURCE:  self._source,
                **self._upstream,
            },
        )

    async def async_step_manual(self, user_input=None) -> FlowResult:
        """Fallback: Manuelle SN-Eingabe."""
        errors = {}

        if user_input is not None:
            sn     = user_input["device_sn"]
            region = user_input.get("region", "europe")
            await self.async_set_unique_id(f"{user_input['api_id']}_{sn}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Dyness Battery",
                data={
                    "api_id":     user_input["api_id"],
                    "api_secret": user_input["api_secret"],
                    "api_base":   API_REGIONS.get(region, API_REGIONS["europe"]),
                    "device_sn":  sn,
                    "dongle_sn":  user_input.get("dongle_sn") or None,
                    CONF_SOURCE:  self._source,
                    **self._upstream,
                },
            )

        schema = vol.Schema({
            vol.Required("api_id",     default=self._api_id     or ""): str,
            vol.Required("api_secret", default=self._api_secret or ""): str,
            vol.Required("region",     default="europe"): vol.In(["europe", "apac"]),
            vol.Required("device_sn"): str,
            vol.Optional("dongle_sn", default=""): str,
        })

        return self.async_show_form(
            step_id="manual",
            data_schema=schema,
            errors=errors,
        )
