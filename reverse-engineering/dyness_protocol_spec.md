# Reverse-engineered Dyness / Raymon logger TCP protocol

**Status:** independently reverse-engineered from user-provided PCAP captures and cross-checked against a Dyness portal snapshot. **Not a vendor protocol specification.**

## Evidence and scope

- Captures in `captures/`: `dyness.pcap` (10 Oct 2026, includes two logger reconnects with full login), `sunday.pcap`, `sunday-night.pcap`. Earlier revisions of these notes also used `dyness(1).pcap` through `dyness(7).pcap`, which are not in this tree.
- Cross-validation: German portal HTML with 64/64 displayed cell voltages matching PCAP within the displayed 1 mV precision.
- `documents/Dyness_Low-Voltage_Battery_Open_API_Protocol_V1.0.pdf` (2026-04-15): cloud HTTPS/JSON interface, **not** the logger wire format.
- `documents/Dyness Serial Software.zip`: Dyness Monitor 2022 C# source and manuals. CAN and RS232 tool for direct battery connection, **not** this firmware's field IDs or bit positions.
- `cloud_point_names.json`: official point names (`pointNameCn`) from the Dyness cloud's `/v1/device/realTime/data` for this battery (Powerbox Pro, model code 16), fetched 2026-10-12 with `tools/dyness_cloud_points.py`. Cloud point IDs are the wire field IDs, so this is the label source for `dyness_all_fields.md`.

## Transport

- Logger uses IPv4 TCP destination port **5005**; observed hostname `logger.dyness.com`, destination addresses `47.254.174.207` and `8.211.25.186`.
- Server 1 config: `t.raymoniot.com`; Server 2: `logger.dyness.com`; selected server 2 in captures.
- Telemetry roughly every **300 seconds**. TCP may contain segmented frames and retries; reassemble by sequence.
- Application messages have a **4-byte big-endian byte count excluding the prefix**, followed by the message body.
- Logger communications observed unencrypted (including startup credentials). Never publish unredacted packets.
- Capture may lack DNS. Hostname inference relies on reported configuration, not an observed DNS query.

## Application framing (observed)

- `length:u32_be` then `serial_length:u8`, `serial:ASCII[N]`, `opcode:2 bytes`, opcode-dependent body. Every frame in the captures fits this header.
- Opcode families: logger requests and uploads are `91 xx`; server acks are `99 xx`; server-initiated messages are `00 xx`. Replies to `91 00` and `91 22` reuse the request opcode.
- `00 7F`: server greeting. Serial length `0`, then ASCII text: `This is dyness.raymon service. node id is '<uuid>'`. The UUID differs per connection.
- `91 00`: boot login request. Body is 23 printable ASCII bytes with no length prefixes (contents redacted). Server replies `91 00 01`; `01` is consistent with success but not formally documented.
- `91 22`: time-sync request with an empty body. Response body is an 8-byte big-endian epoch millisecond count.
- `91 71`: logger configuration typed-field upload; acknowledgement `99 71` with body `01` only.
- `91 04`: BMS/board typed-field upload; acknowledgement `99 04` with body `01` only. The ack does not echo the measurement code.
- `00 77`: server-initiated command tunnelled to the battery side; logger answers `91 87`. See below.
- Do **not** interpret TCP acknowledgement as cloud account registration or acceptance of telemetry into a regional portal.

### Session sequence (observed)

The logger connects and speaks first. Both full logins in `dyness.pcap` (to `47.254.174.207` and to `8.211.25.186`) follow the same order:

| Step | Direction | Frame |
|---|---|---|
| 1 | logger to server | `91 00` login |
| 2 | server to logger | `00 7F` greeting text |
| 3 | server to logger | `91 00` body `01` |
| 4 | logger to server | `91 22` time request (empty body) |
| 5 | server to logger | `91 22` body: 8-byte epoch ms |
| 6 | about 25 s later, then every ~301 s | upload cycle, below |

Upload cycle:

1. Logger sends `91 71` (logger config); server answers `99 71 01`.
2. Logger sends `91 04` bank summary (`…-BMS`); server answers `99 04 01`.
3. Logger sends one `91 04` per BMS board, each acknowledged with `99 04 01`.

The logger is stop-and-wait. It sends the next frame about 300 ms after it receives a reply. Server replies take about 300 ms.

Time sync repeats inside a long session about every 12 hours (05:36, 17:37, then 05:39 the next day in the Sunday captures). That matches logger field `897000` = 43200 seconds.

Bank upload gaps are 298–302 s in nearly all cycles, matching field `850000` = 300.

### Duplicate board frames explained

433 of 445 upload cycles across the three captures contain a second, byte-identical copy of board `0100000000000003`. The cause is the server:

1. The logger sends board `…0003`.
2. The server replies with `00 77` (command `0x1303`) instead of `99 04`.
3. The logger resends the identical `…0003` frame.
4. The server then sends the outstanding `99 04` acks and a second `00 77`.

A server that answers every `91 04` with `99 04 01` and sends no `00 77` should therefore see each board once per cycle. The duplicate is not a fifth BMS and not a logger fault.

### `00 77` command tunnel

`00 77` body layout, from 893 commands with 4 distinct payloads (2 command IDs):

| Bytes | Value | Meaning |
|---|---|---|
| 0–3 | `00 00 13 03` or `00 00 12 F8` | command ID; constant across days, so not a per-message counter |
| 4 | `0B` or `13` | length of bytes 5 through the end |
| 5 | `A0` | inner frame start |
| 6–7 | `0A 01` | constant; probably target address and channel (unverified) |
| 8–9 | `0C 01` or `08 02` | inner command |
| 10–11 | `00 00` or `00 08` | inner data length |
| 12… | inner data | |
| next 2 | CRC | CRC-16/XMODEM (poly `0x1021`, init `0`, no reflection), big-endian, over byte 5 through the end of inner data. Verified on all 4 payloads. |
| last 2 | `D0 0D` | inner frame end |

Observed commands:

- `0x1303`, inner `0C 01`, no data. Sent in reply to board `…0003`, once per copy, in nearly every upload cycle. The logger answers `91 87` with body `00 00 13 03 00 01 FF` about 5 s after the first `00 77` of the cycle, once per cycle. Read as: echo of the command ID, 1-byte result, `FF`. The 5 s delay and the `FF` result suggest the logger forwarded the inner frame and timed out waiting for the battery. Meaning of `0C 01` unknown.
- `0x12F8`, inner `08 02`, 8 data bytes: a clock-set command. Data is binary `second, minute, hour, day, month, year-2000, weekday (1 = Monday … 7 = Sunday), 01`. Three samples: `04 24 07 0B 0A 1A 07 01` = Sun 2026-10-11 07:36:04, `21 25 13 0B 0A 1A 07 01` = Sun 2026-10-11 19:37:33, `0C 27 07 0C 0A 1A 01 01` = Mon 2026-10-12 07:39:12. Each is sent about 1 s after a `91 22` time-sync reply and equals that reply’s time plus about one second. The logger answers `91 87` with `00 00 12 F8 00 01 FF`, again about 5 s later.

The Dyness Monitor serial tool in `documents/` uses the same CRC-16/XMODEM but a different frame (`FA 10 …` requests, 88-byte `FA 80 … ED` responses at 9600 or 115200 baud), so it does not identify the `A0 … D0 0D` inner commands.

### Telemetry upload body structure (as implemented in decoder)

1. Logger serial header + 2-byte opcode (`91 04` or `91 71`).
2. 4-byte measurement code. First two bytes big-endian: `3600` (`0E 10`) for `91 71` logger config, `14002` (`36 B2`) for the bank summary, `15002` (`3A 9A`) for boards. `14002` also appears in the logger firmware name (`RSW_14002_…`) and OTA bundle (`r1.dyness.14002.0`), so these look like template IDs. Last two bytes `00 00`.
3. 1-byte measurement name length, ASCII measurement name.
4. 12 metadata bytes: `01`, then an 8-byte big-endian epoch millisecond timestamp, then `00 00 00`. All frames of one upload cycle carry the same timestamp, so it is the cycle sample time. See the clock note below.
5. 1-byte typed-field count.
6. Exactly that many typed fields, with no trailing bytes.

### Clock offset

The capture host clock is correct. The server does not consistently send UTC, and the logger clock follows whatever it sends.

All three captures share one TCP connection (`192.168.1.142:64395` to `8.211.25.186`), opened at 05:31 UTC on 10 Oct 2026.

| Time (UTC) | Exchange | Server time minus true UTC |
|---|---|---|
| 10 Oct 05:01 | time sync after login (earlier connection, `47.254.174.207`) | 0 |
| 10 Oct 05:31 | time sync after login | 0 |
| 10 Oct 04:36 – 09:58 | logger metadata timestamps | 0 |
| 10 Oct 21:55 onward | logger metadata timestamps | +2 h |
| 11 Oct 05:36 | in-session time sync, then clock-set `00 77` | +2 h |
| 11 Oct 17:37 | in-session time sync, then clock-set `00 77` | +2 h |
| 12 Oct 05:39 | in-session time sync, then clock-set `00 77` | +2 h |

The shift happened on the open connection between 09:58 and 21:55 UTC on 10 Oct, most likely at the 12-hour resync due around 17:31, which is not captured. Pattern so far: time sync answered right after login used UTC; in-session resyncs used UTC+2 and were each followed by a clock-set. UTC+2 is Central European Summer Time, the time zone of the European servers. That pattern rests on 2 login syncs and 3 resyncs.

Consequence: the metadata timestamp is the logger’s clock, which the cloud may have set 2 hours ahead. Do not treat it as UTC without checking it against receive time.

### Typed-field layout

Each field uses `field_id:u32_be`, `type:u8`, followed by a type-dependent value:

| Type byte | Decoder name | Wire representation |
|---|---|---|
| `0x54` (`T`) | Text | `length:u8` + UTF-8 bytes, trailing NUL padding removed for display |
| `0x46` (`F`) | Float | IEEE-754 float32, big-endian |
| `0x49` (`I`) | Integer | unsigned u32, big-endian (signedness not independently verified) |
| `0x53` (`S`) | Short | unsigned u16, big-endian (signedness not independently verified) |

Example: `00 00 28 3C 46 40 5F 1A A0` = field 10300, float32 3.486 V.

## Telegrams and important field IDs

See `dyness_all_fields.csv` / `.md` for all **256** dictionary entries, including synthetic bit expansion IDs.

**Bank summary:** 600 average voltage (V), 700 signed current (A), 800 average SOC (%), 1200 minimum SOH (%), 1300 maximum cell voltage, 1500 minimum, 3600 / 3700 suggested charge voltage upper / lower limit, 3800 maximum charge current, 3900 maximum discharge current. `3200` / `3300` are alarm status words, `3400` / `3500` protection status words, `4000` charge/discharge status (4007 discharge enable, 4008 charge enable), `4100` total alarm status. Names are official (see `cloud_point_names.json`).

**Board telemetry:** 10000 serial; 10200 cell count; 10300..11800 in increments of 100 = cell 1..16 float voltages; 12400 BMS board temperature; 12500..12800 average temperature of cell groups 1–4 … 13–16; 13400 signed current; 13500 voltage; 13900 cycle count; 14000 / 14100 remaining / total capacity Ah; 14200..17500 error codes plus 17300 / 17500 charge / discharge current; 17600..18000 Status1–5 (protection, MOSFET, charge state, per-cell status); 18100..19200 protection limits; 19300..19800 per-board copies of bank 3600..4100.

**Logger configuration:** 600000 manufacturer, 601000 firmware, 602000 hardware rev, 613000/613100 hostnames, 613200 server selector, 614000/614100 ports, 825000 possible uptime, 850000 update interval, 896001 cloud API endpoint.

## Status hypotheses based on Sunday overvoltage recording

These observations predate the official names. Each now has an explanation:

- Combined `3200` transitioned `0x00` → `0x80` → `0xA0` as high-voltage events were reported. `0x80` is `3208` (module total voltage high) and `0xA0` adds `3206` (cell high voltage). Home Assistant alerts had up to 10–15 minutes lag.
- Individual `17800`: `0x80` near charging, `0x40` near discharging, `0x08` at low current. These are Status3 bits `17808` (valid charge current), `17807` (valid discharge current) and `17804` (fully charged).
- `17700` alternates 14/15. It is Status2: 14 is the discharge, charge and pre-charge MOSFETs on; the changing bit 0 is `17701` (using battery module power), not balancing.
- Combined `4000` `0xC0`/`0x40` changes near 100% SOC. It is charge/discharge status: `0xC0` is discharge and charge enabled, `0x40` is discharge only, so charge enable (`4008`) drops at full charge.
- Example event: on Sunday around 14:20 local, pack reached ~56.74 V against reported 56.50 V charge-voltage request; max cell ~3.563 V. The inverter separately reported a zero allowed-charge-current limit: that **inverter CAN value is not present or independently proven in the Raymon upload**.
- Upstream's `ALARM_BITS_1` labels for `3201`…`3208` match the official names. See the upstream cross-reference in `dyness_all_fields.md`.

## Open questions

Resolved from the captures: handshake order, greeting format, ack bodies (`01` only), metadata timestamp layout, and the cause of duplicate board frames. See the sections above.

Resolved from the cloud point names: the bit order of the status words (sub-point *n*01 is bit 0; the cloud reported `3200` = 128 with only `3208` = 1 and `4000` = 64 with only `4007` = 1), and the meanings of `3200`–`4100`, `17600`–`18000` and `19700`. The synthetic bit IDs are cloud points; they have not been seen as separate fields on the wire.

Still open:

- **Greeting required?** The logger always received `00 7F` before `91 00 01`. Whether it accepts a `91 00 01` without the greeting is untested; endpoint mode sends one.
- **`00 77` required?** The logger uploaded every cycle with `00 77` present. No capture shows a session without it. Expected to be optional, because the logger only answers it with a timeout result.
- **Inner command `0C 01`** and the `0A 01` bytes. Unknown. The `FF` result suggests no device on the logger’s serial side answered.
- **`91 87` result byte.** Only `FF` observed.
- **Clock offset.** The server sends UTC in some exchanges and UTC+2 in others (see Clock offset). Whether the split is login sync versus in-session resync, or a server-side change on 10 Oct, needs more resync samples.
- **Units of `13600` / `13800`** (remaining / total capacity 1) and the values of the error codes `14200` (16) and `17400` (2).

## OTA traffic (separate HTTP protocol)

After reboot the collector queried `cloud.raymoniot.com:9002` via HTTP `GET /prod-api/romRelease/checkVersion?bundle=r1.dyness.14002.0&version=4.0.185`. A response reported `no released version in r1.dyness.14002.0`. This is not evidence of mandatory update or device rejection.

## Distinct Dyness OpenAPI (not port 5005)

The vendor PDF describes regional HTTPS JSON POST APIs, authenticated by `Authorization: API {apiId}:{HMAC-SHA1}`, `Content-MD5`, and date, with endpoints `/v2/GetRealTimeDataBySN`, `/v2/GetParallelInfBySN`, `/v2/GetAlarmInfBySN`, `/v2/GetDeviceInfBySN`, and one control endpoint `/v2/SetBatterySetting` (battery heating periods). Regions are separate; cross-region calls unsupported. Rate limit is 2 calls per second. Credentials need explicit partner access.

Details relevant to the logger fields:

- Regional domains in the PDF are `eu-openapi.dyness.com`, `na-`, `latam-`, `me-`, `af-`, `sa-`, `global-openapi.dyness.com`, `openapi.dyness.com.cn`, and `apacopen-api.dyness.com`. The upstream Home Assistant integration uses `open-api.dyness.com` for Europe, which the PDF does not list.
- The v2 responses use named JSON fields, not point IDs. `/v2/GetRealTimeDataBySN` names match this dictionary’s board labels: `moduleHighVoltageUpperLimit`, `moduleLowVoltage`, `moduleUnderVoltage`, charge and discharge temperature limits, `bmsBoardTemp`, `cellVoltageList`, `cellTempList`.
- `batteryStatus` and `chargeDischargeStatus` codes: `0` shutdown, `2` discharge, `3` charge.
- `/v2/GetAlarmInfBySN` example returns `eventCode: "E3201"`. That is consistent with alarm codes being point IDs such as `3201`.
- Example names in the PDF are `RAYMOND001` (serial) and `RAY-LV-BMS` (host device name), consistent with the Raymon logger platform.

The `/v1/...` endpoints the upstream integration uses (including `/v1/device/realTime/data`, which returns point IDs) are not in this PDF.

## Limits and decoder safety

- PCAP classic format supported, IPv4 TCP, Ethernet/Linux cooked links; no PCAPNG, IPv6 or IP-fragment reassembly.
- Session reconstruction and retransmission suppression, but stops a direction when TCP bytes are missing.
- Current captures contain four BMS boards in three physical batteries; one battery holds two modules, and each of its boards misreports about 200 Ah for a module of about 100 Ah. The repeated `…0003` frames are resends caused by the server’s `00 77`, see Duplicate board frames explained.
- No validated 90% DoD field, internal 0 A dynamic CAN request, or cumulative lifetime Ah/kWh counter in cloud uploads.
- Credentials removed from parsed login records, but do not distribute source PCAPs publicly.
- Unknown fields are retained with numeric ID, raw hex and type; reserve the right to revise interpretations.
