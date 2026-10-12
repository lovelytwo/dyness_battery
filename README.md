# Dyness Battery – Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/lovelytwo/dyness_battery.svg)](https://github.com/lovelytwo/dyness_battery/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Eine Community-Integration für Home Assistant für **Dyness Batteriespeicher** über die Dyness Cloud API.

> **Hinweis / Note:** Diese Integration nutzt die Dyness Open API (Cloud). Eine Internetverbindung ist erforderlich. Daten werden alle 5 Minuten aktualisiert (API-Limit).\
> This integration uses the Dyness Open API (Cloud). An internet connection is required. Data is updated every 5 minutes (API limit).

---

## Local logger sources (this fork)

This fork of [shopf/dyness_battery](https://github.com/shopf/dyness_battery) adds three sources that read the Wi-Fi logger directly. The logger uploads plaintext TCP to `logger.dyness.com` port **5005** about every 300 seconds; when that name resolves to Home Assistant, the integration receives each upload as it happens. Design and protocol notes: [`spec/local-listener.md`](spec/local-listener.md) and [`reverse-engineering/`](reverse-engineering/).

| Source | What it does | Cloud still gets data | Needs API credentials |
|---|---|---|---|
| Cloud API | upstream behaviour, Open API poll every 5–15 minutes | yes | yes |
| Local endpoint | Home Assistant answers the logger itself | no | no |
| Local passthru | relays the logger connection to the real Dyness server and parses a copy | yes | no |
| Cloud and passthru | passthru plus the cloud poll; fresh local values win; writes a full traffic trace | yes | yes |

**Install.** The fork keeps the domain `dyness_battery`, so it replaces upstream rather than running beside it. Existing cloud entries and entity IDs carry over. Remove the upstream repository from HACS first, then add `https://github.com/lovelytwo/dyness_battery` as a custom repository (category Integration). The manifest says `local_push`; cloud entries still poll every five minutes.

**Add a local entry.** Settings → Devices & Services → Add Integration → Dyness Battery, then pick the source. Endpoint and passthru ask for the device model (for a Powerbox Pro choose `POWERBOX-PRO`), because the logger does not send one. Passthru and cloud-and-passthru ask for the upstream server as an IPv4 address or a hostname; addresses seen so far are `47.254.174.207` and `8.211.25.186`. Only one local entry is possible, because they all listen on port 5005.

**Switch an existing entry.** You do not need a second entry. On the integration entry, open the ⋮ menu → **Reconfigure** and pick another source; the same steps as adding an entry follow, with the current values filled in. Entity IDs, history and the battery device are kept, and so are the stored API credentials, so switching back to the cloud API asks no questions. Reconfigure also changes the upstream address or model without switching source. A new local entry learns the battery serial from the first upload and uses the same device identifiers as a cloud entry. Requires Home Assistant 2024.11 or later.

After switching to endpoint or passthru, the Junior Box write controls show as *no longer provided* and the cloud-only sensors as unavailable. They come back when you switch back. To drop them for good, delete them under Settings → Devices & Services → Entities.

**DNS.** Make `logger.dyness.com` resolve to Home Assistant's LAN address **for the logger only**:

- AdGuard Home: Filters → DNS rewrites, or a per-client rule in Filters → Custom filtering rules (`||logger.dyness.com^$client=192.168.1.50,dnsrewrite=192.168.1.10`, logger first, Home Assistant second) so only the logger gets the rewrite.
- Pi-hole, a router DNS override, or a DHCP-assigned DNS server for the logger work the same way.
- For passthru, Home Assistant itself must still reach the real server. Enter an IP address, or a hostname that resolves to the real server for Home Assistant (with a per-client rule, Home Assistant keeps the real answer). A hostname that resolves to Home Assistant is refused at connect time, so the relay cannot loop.
- The logger only reconnects after its current session ends; power-cycling the logger makes it pick up the new address straight away.

**Networking.** TCP port 5005 must reach Home Assistant. Home Assistant OS and Supervised need nothing extra. In Docker, use `network_mode: host` or publish `5005:5005/tcp`. Allow 5005 inbound if a firewall runs on the host.

**Capacity.** The logger sends no station capacity. Set the option *Battery Capacity Override (kWh)* to get usable and remaining kWh. Do not derive it from the board amp-hour fields: on some systems they are misreported (two 100 Ah modules in one battery each report about 200 Ah).

**Not available locally** (endpoint and passthru): daily and lifetime energy counters, PV, grid, load and inverter sensors, and the Junior Box write controls. If no upload arrives for twice the logger's interval (10 minutes by default), the entities become unavailable until the next upload.

**Upstream down.** Passthru closes the logger connection when the upstream cannot be reached; after five failures in a row a repair issue names the address. Fix it with Reconfigure. The option *Answer the logger locally when the upstream is down* keeps data flowing in that case (those uploads never reach the cloud).

**Trace (cloud and passthru only).** `config/dyness_cloud_passthru.log` gets one JSON line per frame and per Open API call, plus comparison records of cloud and local values. Login bodies are replaced with `redacted` and the API secret is never written, but the file still contains serial numbers, the logger MAC and LAN address and all telemetry. Do not share it unredacted. It rotates at 10 MB with 5 backups.

**Testing without Home Assistant.** `python3 tools/dyness_local_runner.py --port 15005` runs the listener on its own; `python3 tools/dyness_replay.py capture.pcap --port 15005` replays the logger side of a capture against it. `pytest` runs the protocol, store and responder tests (Python 3.9+, no Home Assistant needed); with `pytest-homeassistant-custom-component` installed it also runs the tests in `tests/ha/`.

---

## 🇩🇪 Deutsch

### Unterstützte Geräte

| Gerät | Status |
|-------|--------|
| Dyness Cygni 10.0HS | ✅ Getestet |
| Dyness DL5.0C | ✅ Getestet |
| Dyness Junior Box | ✅ Getestet + Steuerung möglich |
| Dyness Powerbox G2 / Pro | ✅ Getestet |
| Dyness PowerBrick / Plus / PRO / SC | ✅ Getestet |
| Dyness PowerDepot G2 / H5B | ✅ Getestet |
| Dyness PowerHaus | ✅ Getestet |
| Dyness Stack100 | ✅ Getestet |
| Dyness Tower Pro TP7 / TP11 / TP15 | ✅ Getestet |
| Dyness Tower T14 / T17 | ✅ Getestet |
| Andere Dyness-Modelle mit WiFi-Dongle | ⚠️ Nicht getestet – Feedback willkommen |

> Die Integration erkennt das Gerät automatisch über die API und registriert nur die Sensoren, die für das jeweilige Gerät verfügbar sind.

---

### Verfügbare Sensoren

#### Pack-Ebene (Haupt-Device)

Die folgenden Sensoren sind für **alle Geräte** verfügbar:

| Sensor | Einheit |
|--------|---------|
| Ladestand (SOC) | % |
| Leistung | W |
| Strom | A |
| Batteriestatus (Charging / Discharging / Standby) | – |
| Letzte Aktualisierung | Zeitstempel |
| Verbindungsstatus | Online / Offline |
| Betriebsstatus | – |
| Firmware-Version | – |

Weitere Sensoren werden automatisch aktiviert, sofern das Gerät die Daten liefert:

| Sensor | Einheit | Junior Box | Tower T14/T17/TP | DL5.0C / Stack100 / PowerBox Pro | PowerDepot G2 / H5B | PowerHaus | Powerbox G2 | PowerBrick / PRO | PowerBrick SC / Plus |
|--------|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Pack-Spannung | V | ✅ | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Batteriezustand (SOH) | % | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | – |
| Temperatur | °C | – | – | – | – | – | ✅ | – | – |
| Temperatur Max | °C | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Temperatur Min | °C | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MOSFET-Temperatur | °C | ✅ | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| BMS-Temperatur Max | °C | ✅ | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| BMS-Temperatur Min | °C | ✅ | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Zellspannung Max | V | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Zellspannung Min | V | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Zellspannungsdifferenz | mV | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Zelle 01–16 (Einzelspannungen) | V | – | – | – | – ³ | – | – | ✅ ² | ✅ ² |
| Nutzbare Kapazität | kWh | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Verbleibende Energie | kWh | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ladezyklen | – | – | ✅ | ✅ | ✅ | ✅ | – | ✅ | ✅ |
| Heute geladen | kWh | ✅ | – | ✅ | – | – | – | – | – |
| Heute entladen | kWh | ✅ | – | ✅ | – | – | – | – | – |
| Gesamt geladen | kWh | ✅ | ✅ | ✅ | – | – | – | – | – |
| Gesamt entladen | kWh | ✅ | – | ✅ | – | – | – | – | – |
| Balancing-Status | – | ✅ | – | ✅ | – | – | – | – | – |
| Alarmstatus | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | – |
| Ladespannungsgrenze | V | – | – | ✅ | ✅ | – | ✅ | ✅ | ✅ |
| Entladespannungsgrenze | V | – | – | ✅ | ✅ | – | ✅ | ✅ | ✅ |
| Max. Ladestrom | A | – | – | ✅ | ✅ | – | ✅ | ✅ | ✅ |
| Max. Entladestrom | A | – | – | ✅ | ✅ | – | ✅ | ✅ | ✅ |

> ² Einzelne Zellspannungen (Zelle 01–16) sind standardmäßig **deaktiviert** und können in HA unter Einstellungen → Geräte & Dienste → Dyness Battery → Gerät → Entitäten aktiviert werden.

> ³ PowerDepot G2 / H5B: Einzelzellspannungen (Zelle 01–16) sind auf Modul-Ebene (Sub-Module Devices) verfügbar — nicht auf Pack-Ebene.

#### Modul-Ebene (Sub-Module Devices)

Geräte mit mehreren Modulen (DL5.0C, Stack100, PowerBox Pro, Tower T14, Tower Pro TP7/TP11/TP15) erstellen automatisch ein eigenes Device pro Modul:

| Sensor | Einheit | DL5.0C / Stack100 / PowerBox Pro / PowerDepot | Tower T14/T17 / TP |
|--------|---------|:---:|:---:|
| Ladestand Modul (SOC) | % | ✅ | – ¹ |
| Batteriezustand Modul (SOH) | % | ✅ | – ¹ |
| Modul-Spannung | V | ✅ | – ¹ |
| Modul-Strom | A | ✅ | – ¹ |
| Ladezyklen Modul | – | ✅ | – ¹ |
| Zellspannung Max | V | ✅ | ✅ |
| Zellspannung Min | V | ✅ | ✅ |
| Zellspannungsdifferenz | mV | ✅ | ✅ |
| Zelltemperatur 1 | °C | ✅ | ✅ |
| Zelltemperatur 2 | °C | ✅ | ✅ |
| Zelle 01–16 (DL5.0C / Stack100 / PowerBox Pro) | V | ✅ ² | – |
| Zelle 01–30 (Tower T14/T17 / TP7/TP11/TP15) | V | – | ✅ ² |

> ¹ Tower T14/T17 / TP: SOC, SOH, Spannung, Strom und Zyklen sind nur auf Systemebene (Haupt-Device) verfügbar — die API liefert diese Werte nicht pro Modul.

> ² Einzelne Zellspannungen sind standardmäßig **deaktiviert** und können in HA unter Einstellungen → Geräte & Dienste → Dyness Battery → Gerät → Entitäten aktiviert werden.

---

### Voraussetzungen

1. Dyness Batterie ist bereits in der **Dyness App** eingerichtet und online

### Schritt 1: API-Zugangsdaten im Dyness Portal erstellen

1. Öffne **Dyness Benutzer Smart Monitoring** [https://ems.dyness.com/login](https://ems.dyness.com/login)
2. Melde dich mit deinem Dyness-Konto an (dasselbe wie in der App)
3. Wähle im Menü links **Entwicklerzentrum** → **API-Verwaltung**
4. Klicke auf **API Key erstellen**
5. Notiere **App ID** und **App Secret** – das Secret wird nur einmal angezeigt!

### Installation

#### Via HACS (empfohlen)

1. Öffne HACS in Home Assistant
2. Klicke auf **Integrationen** → **⋮** → **Benutzerdefinierte Repositories**
3. Repository-URL: `https://github.com/lovelytwo/dyness_battery` — Kategorie: **Integration**
4. Suche nach **Dyness Battery** und installiere
5. Home Assistant neu starten

#### Manuelle Installation

1. Lade die ZIP von [Releases](https://github.com/lovelytwo/dyness_battery/releases) herunter
2. Entpacke und kopiere `custom_components/dyness_battery/` nach `config/custom_components/`
3. Home Assistant neu starten

### Konfiguration

1. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen**
2. Nach **Dyness Battery** suchen
3. Nur **API ID** und **API Secret** eintragen — das Gerät wird automatisch erkannt

> **Mehrere Batterien:** Bei mehreren Batterien auf einem Account einfach die Integration erneut hinzufügen — dieselben API-Zugangsdaten, das zweite Gerät wird separat erkannt.

### API Rate Limit & Scan-Intervall

| Module | Intervall |
|--------|-----------|
| 1–2 | 5 Minuten |
| 3–4 | 10 Minuten |
| 5+ | 15 Minuten |

### Bekannte Einschränkungen

- **Nur Monitoring** – Steuerung (Ladezeiten, SOC-Grenzen) wird von der API nicht unterstützt
- **Internetabhängig** – Keine lokale Verbindung möglich

### Neues Modell hinzufügen

Du hast ein anderes Dyness-Modell und möchtest es hinzufügen lassen? Erstelle ein [Issue](https://github.com/shopf/dyness_battery/issues) mit der Ausgabe des API-Testscripts `tools/dyness_test.py`.

---

## 🇬🇧 English

### Supported Devices

| Device | Status |
|--------|--------|
| Dyness Cygni 10.0HS | ✅ Tested |
| Dyness DL5.0C | ✅ Tested |
| Dyness Junior Box | ✅ Tested + controllable |
| Dyness Powerbox G2 / Pro | ✅ Tested |
| Dyness PowerBrick / Plus / PRO / SC | ✅ Tested |
| Dyness PowerDepot G2 / H5B | ✅ Tested |
| Dyness PowerHaus | ✅ Tested |
| Dyness Stack100 | ✅ Tested |
| Dyness Tower Pro TP7 / TP11 / TP15 | ✅ Tested |
| Dyness Tower T14 / T17 | ✅ Tested |
| Other Dyness models with WiFi dongle | ⚠️ Not tested – feedback welcome |

> The integration automatically detects the device via the API and only registers sensors available for that specific device.

---

### Available Sensors

#### Pack Level (Main Device)

Available for **all devices**:

| Sensor | Unit |
|--------|------|
| State of Charge (SOC) | % |
| Power | W |
| Current | A |
| Battery Status (Charging / Discharging / Standby) | – |
| Last Update | Timestamp |
| Communication Status | Online / Offline |
| Work Status | – |
| Firmware Version | – |

Additional sensors enabled automatically if provided by the device:

| Sensor | Unit | Junior Box | Tower T14/T17/TP | DL5.0C / Stack100 / PowerBox Pro | PowerDepot G2 / H5B | PowerHaus | Powerbox G2 | PowerBrick / PRO | PowerBrick SC / Plus |
|--------|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Pack Voltage | V | ✅ | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| State of Health (SOH) | % | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | – |
| Temperature | °C | – | – | – | – | – | ✅ | – | – |
| Temperature Max | °C | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Temperature Min | °C | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MOSFET Temperature | °C | ✅ | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| BMS Temperature Max | °C | ✅ | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| BMS Temperature Min | °C | ✅ | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cell Voltage Max | V | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cell Voltage Min | V | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cell Voltage Spread | mV | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cell 01–16 (individual voltages) | V | – | – | – | – ³ | – | – | ✅ ² | ✅ ² |
| Usable Capacity | kWh | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Energy Remaining | kWh | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cycle Count | – | – | ✅ | ✅ | ✅ | ✅ | – | ✅ | ✅ |
| Energy Charged Today | kWh | ✅ | – | ✅ | – | – | – | – | – |
| Energy Discharged Today | kWh | ✅ | – | ✅ | – | – | – | – | – |
| Energy Charged Total | kWh | ✅ | ✅ | ✅ | – | – | – | – | – |
| Energy Discharged Total | kWh | ✅ | – | ✅ | – | – | – | – | – |
| Balancing Status | – | ✅ | – | ✅ | – | – | – | – | – |
| Alarm Status | – | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | – |
| Charge Voltage Limit | V | – | – | ✅ | ✅ | – | ✅ | ✅ | ✅ |
| Discharge Voltage Limit | V | – | – | ✅ | ✅ | – | ✅ | ✅ | ✅ |
| Max Charge Current | A | – | – | ✅ | ✅ | – | ✅ | ✅ | ✅ |
| Max Discharge Current | A | – | – | ✅ | ✅ | – | ✅ | ✅ | ✅ |

> ² Individual cell voltages (Cell 01–16) are **disabled by default** and can be enabled in HA under Settings → Devices & Services → Dyness Battery → Device → Entities.

> ³ PowerDepot G2 / H5B: Individual cell voltages (Cell 01–16) are available at module level (Sub-Module Devices) — not at pack level.

#### Module Level (Sub-Module Devices)

Devices with multiple modules (DL5.0C, Stack100, PowerBox Pro, Tower T14, Tower Pro TP7/TP11/TP15) automatically create a separate device per module:

| Sensor | Unit | DL5.0C / Stack100 / PowerBox Pro / PowerDepot | Tower T14/T17 / TP |
|--------|------|:---:|:---:|
| Module SOC | % | ✅ | – ¹ |
| Module SOH | % | ✅ | – ¹ |
| Module Voltage | V | ✅ | – ¹ |
| Module Current | A | ✅ | – ¹ |
| Module Cycle Count | – | ✅ | – ¹ |
| Cell Voltage Max | V | ✅ | ✅ |
| Cell Voltage Min | V | ✅ | ✅ |
| Cell Voltage Spread | mV | ✅ | ✅ |
| Cell Temperature 1 | °C | ✅ | ✅ |
| Cell Temperature 2 | °C | ✅ | ✅ |
| Cell 01–16 (DL5.0C / Stack100 / PowerBox Pro) | V | ✅ ² | – |
| Cell 01–30 (Tower T14/T17 / TP7/TP11/TP15) | V | – | ✅ ² |

> ¹ Tower T14/T17 / TP: SOC, SOH, Voltage, Current and Cycle Count are only available at system level (main device) — the API does not provide these values per module.

> ² Individual cell voltages are **disabled by default** and can be enabled in HA under Settings → Devices & Services → Dyness Battery → Device → Entities.

---

### Step 1: Create API Credentials in the Dyness Portal

1. Open **Dyness User Smart Monitoring** [https://ems.dyness.com/login](https://ems.dyness.com/login)
2. Log in with your Dyness account (same as the app)
3. Select **Developer Center** → **API Management** from the left menu
4. Click **Create API Key**
5. Note down **App ID** and **App Secret** – the secret is only shown once!

### Installation

#### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Click **Integrations** → **⋮** → **Custom repositories**
3. Add URL: `https://github.com/lovelytwo/dyness_battery` — Category: **Integration**
4. Search for **Dyness Battery** and install
5. Restart Home Assistant

#### Manual Installation

1. Download the ZIP from [Releases](https://github.com/lovelytwo/dyness_battery/releases)
2. Extract and copy `custom_components/dyness_battery/` to `config/custom_components/`
3. Restart Home Assistant

### Configuration

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Dyness Battery**
3. Enter only your **API ID** and **API Secret** — the device is discovered automatically

> **Multiple batteries:** Simply add the integration again with the same credentials to set up additional batteries on the same account.

### API Rate Limit & Scan Interval

| Modules | Interval |
|---------|----------|
| 1–2 | 5 minutes |
| 3–4 | 10 minutes |
| 5+ | 15 minutes |

### Known Limitations

- **Monitoring only** – Control (charge schedules, SOC limits) is not supported via the API
- **Cloud dependent** – No local connection possible

### Adding a New Model

Open an [Issue](https://github.com/shopf/dyness_battery/issues) with the output of the API test script `tools/dyness_test.py`.

---

## Technical Details

Uses the **Dyness Open API v1.1** with HmacSHA1 authentication.

Endpoints used:
- `POST /v1/device/storage/list` – Auto-discover device SN and work status
- `POST /v1/device/bindSn` – Bind device to API key
- `POST /v1/device/realTime/data` – Real-time BMS data (every 5 min)
- `POST /v1/device/getLastPowerDataBySn` – Current power data (every 5 min)
- `POST /v1/station/info` – Station info (battery capacity)
- `POST /v1/device/household/storage/detail` – Device details (firmware, status)
- `POST /v1/device/getLastRunningDataBySn` – Runtime data (firmware version)

---

## Community & Support

| | |
|---|---|
| 💬 **Questions & Ideas** | [GitHub Discussions](https://github.com/shopf/dyness_battery/discussions) |
| 🐛 **Bug Reports** | [GitHub Issues](https://github.com/lovelytwo/dyness_battery/issues) |
| 🔌 **New Device** | Open an Issue with your `dyness_test.py` output |

---

## Languages

| Language | Code | Status |
|----------|------|--------|
| German | `de` | ✅ Complete |
| English | `en` | ✅ Complete |
| French | `fr` | ✅ Complete |
| Spanish | `es` | ✅ Complete |
| Portuguese | `pt` | ✅ Complete |

Want a new language or spotted a small translation error? Just open a [Discussion](https://github.com/shopf/dyness_battery/discussions) or submit a Pull Request directly – contributions are very welcome!

---

## License

MIT License – see [LICENSE](LICENSE)
