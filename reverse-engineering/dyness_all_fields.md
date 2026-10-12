# Dyness / Raymon telemetry: complete field dictionary

This dictionary has **256 field IDs** observed in the supplied captures. It includes expanded *synthetic* bit IDs (these are decoder-derived, not separately transmitted wire fields).

**Confidence:** Confirmed = compared with portal or directly readable; Official = meaning settled by the Dyness cloud's own point name; Official name; values unverified = the name is official but the units or value meaning are not yet understood; Strong inference = clear numerical/temporal evidence; Correlated only = observed association, **not proof**; Unknown = insufficient evidence.

**Official names.** The bank and board tables have an "Official name" column. It holds the `pointNameCn` label that the Dyness Open API returns with every point from `POST /v1/device/realTime/data`, fetched on 2026-10-12 for this Powerbox Pro (device model code 16, host `Battery-L`, firmware `24.9-26.9.1`). The full list is in [`cloud_point_names.json`](cloud_point_names.json) and can be refreshed with `tools/dyness_cloud_points.py`. Chinese labels are followed by an English translation in brackets; labels the cloud already gives in English are kept as-is. Cloud point IDs are the same numbers as the wire field IDs. Wire fields absent from the cloud list are marked "not in cloud list". The logger fields (500100 and up) are not cloud points.

## Logger information (31 fields)

| ID | Type | Observed example | Meaning / hypothesis | Confidence |
|---:|:---:|---|---|---|
| 500100 | I | 0 | Collector state/reserved | Tentative |
| 600000 | T | Raymon | Logger manufacturer | Confirmed |
| 601000 | T | RSW_14002_0_V4.0.185 | Logger firmware | Confirmed |
| 602000 | T | R1 | Hardware revision | Confirmed |
| 609000 | T | AABBCCDDEEFF | Logger MAC address without colons | Strong |
| 613000 | T | t.raymoniot.com | Configured server 1 | Confirmed |
| 613100 | T | logger.dyness.com | Configured server 2 | Confirmed |
| 613200 | I | 2 | Selected server slot | Confirmed |
| 614000 | I | 5005 | Server 1 port | Confirmed |
| 614100 | I | 5005 | Server 2 port | Confirmed |
| 800000 | I | 61 | Wi-Fi signal strength / RSSI quality | Tentative |
| 807000 | I | 2005 | Network or communication diagnostic counter | Tentative |
| 807001 | I | 52856 | Network diagnostic value | Tentative |
| 811000 | I | 1 | Network status flag | Tentative |
| 812000 | I | 424 | Communication counter A | Strong |
| 813000 | I | 477 | Communication counter B | Strong |
| 819000 | I | 1 | Logger connectivity state flag | Tentative |
| 825000 | I | 16025 | Uptime seconds | Strong |
| 828000 | I | 0 | Restart/diagnostic state | Tentative |
| 850000 | I | 300 | Upload interval seconds | Confirmed |
| 851000 | I | 4 | BMS devices reported (count) | Strong |
| 853000 | I | 0 | Reserved diagnostic indicator | Tentative |
| 860000 | I | 20 | Device/config setting | Tentative |
| 894000 | I | 0 | Reserved setting | Tentative |
| 895000 | I | 0 | Reserved setting | Tentative |
| 896000 | T | DHCP,192.168.1.142,255.255.255.0,192.168.1.1 | DHCP/network interface configuration | Confirmed |
| 896001 | T | http://cloud.raymoniot.com:9002/prod-api | Firmware/cloud API base URL | Confirmed |
| 896003 | T | r1.dyness.14002.0 | Firmware bundle identifier | Confirmed |
| 896004 | T |  | Optional configuration string (blank) | Tentative |
| 896005 | T |  | Optional configuration string (blank) | Tentative |
| 897000 | I | 43200 | Other time interval/timer (seconds?) | Tentative |

## Combined bank summary (80 fields)

| ID | Type | Observed example | Official name | Meaning / hypothesis | Confidence |
|---:|:---:|---|---|---|---|
| 100 | T | Battery-L  | 主机设备名称 (host device name) | Host device name | Confirmed |
| 200 | T | Dyness TECHNOLOGY    | 主机厂商名称 (host manufacturer name) | Manufacturer | Confirmed |
| 300 | T | 24.9-26.9.1 | 主机软件版本 (host software version) | Host firmware/version | Confirmed |
| 400 | S | 4 | 电池的总数量 (total number of batteries) | Total battery count (modules in the system) | Official |
| 600 | F | 53.0 | 平均电压 (average voltage) | Average voltage V (equals bank voltage) | Official |
| 700 | F | -17.6 | 总电流 (total current) | Total current A, positive is charge | Official |
| 800 | S | 95 | 平均SOC (average SOC) | Average SOC % | Official |
| 1200 | S | 99 | 最小SOH (minimum SOH) | Minimum SOH % across modules | Official |
| 1300 | F | 3.315 | 单芯最高电压 (highest cell voltage) | Highest cell voltage V | Confirmed |
| 1400 | S | 524 | 单芯最高电压的编号最小的模块 (lowest-numbered module with the highest cell voltage) | Lowest-numbered module with the highest cell voltage, packed module × 256 + cell (515 = module 2, cell 3) | Official |
| 1401 | S | 2 | 最高单压模块 (module of highest cell voltage) | Module holding the highest cell voltage | Official |
| 1402 | S | 12 | 最高单压电芯 (cell of highest cell voltage) | Cell number of the highest cell voltage | Official |
| 1500 | F | 3.307 | 单芯最低电压 (lowest cell voltage) | Lowest cell voltage V | Official |
| 1600 | S | 528 | 单芯最低电压的编号最小的模块 (lowest-numbered module with the lowest cell voltage) | Lowest-numbered module with the lowest cell voltage, packed module × 256 + cell | Official |
| 1601 | S | 2 | 最低单压模块 (module of lowest cell voltage) | Module holding the lowest cell voltage | Official |
| 1602 | S | 16 | 最低单压电芯 (cell of lowest cell voltage) | Cell number of the lowest cell voltage | Official |
| 1800 | F | 19.700001 | 单芯最高温度 (highest cell temperature) | Highest cell temperature C | Confirmed |
| 1900 | S | 769 | 单芯最高温度的编号最小的模块 (lowest-numbered module with the highest cell temperature) | Lowest-numbered module with the highest cell temperature, packed module × 256 + NTC | Official |
| 1901 | S | 3 | 最高温度模块 (module of highest temperature) | Module holding the highest cell temperature | Official |
| 1902 | S | 1 | 最高温度NTC (NTC of highest temperature) | NTC number of the highest cell temperature | Official |
| 2000 | F | 18.799999 | 单芯最低温度 (lowest cell temperature) | Lowest cell temperature C | Confirmed |
| 2100 | S | 258 | 单芯最低温度的编号最小的模块 (lowest-numbered module with the lowest cell temperature) | Lowest-numbered module with the lowest cell temperature, packed module × 256 + NTC | Official |
| 2101 | S | 1 | 最低温度模块 (module of lowest temperature) | Module holding the lowest cell temperature | Official |
| 2102 | S | 2 | 最低温度NTC (NTC of lowest temperature) | NTC number of the lowest cell temperature | Official |
| 2300 | F | 17.299999 | MOSFET最高温度 (highest MOSFET temperature) | Highest MOS temperature C | Confirmed |
| 2400 | S | 1 | MOSFET最高温度的编号最小的模块 (lowest-numbered module with the highest MOSFET temperature) | Lowest-numbered module with the highest MOSFET temperature | Official |
| 2800 | F | 25.1 | BMS最高温度 (highest BMS temperature) | Highest BMS temperature C | Confirmed |
| 2900 | S | 1 | BMS最高温度所在模块及序号 (module and index of highest BMS temperature) | Module and index of the highest BMS temperature | Official |
| 3000 | F | 23.700001 | BMS最低温度 (lowest BMS temperature) | Lowest BMS temperature C | Confirmed |
| 3100 | S | 2 | BMS最低温度所在模块及序号 (module and index of lowest BMS temperature) | Module and index of the lowest BMS temperature | Official |
| 3200 | S | 0 | 系统告警状态1 (system alarm status 1) | Alarm status 1, bits 3201–3208. Sunday event 0x80 = 3208, 0xA0 = 3208 + 3206; live cloud 128 with only 3208 set | Official |
| 3201 | S | 0 | 单芯电压一致性告警 (cell voltage consistency alarm) | Bit 0 of field 3200: cell voltage consistency alarm | Official |
| 3202 | S | 0 | MOSFET高温 (MOSFET high temperature) | Bit 1 of field 3200: MOSFET high temperature | Official |
| 3203 | S | 0 | 单芯温度低温 (cell low temperature) | Bit 2 of field 3200: cell low temperature | Official |
| 3204 | S | 0 | 单芯温度高温 (cell high temperature) | Bit 3 of field 3200: cell high temperature | Official |
| 3205 | S | 0 | 单芯电压低压 (cell low voltage) | Bit 4 of field 3200: cell low voltage | Official |
| 3206 | S | 0 | 单芯电压高压 (cell high voltage) | Bit 5 of field 3200: cell high voltage | Official |
| 3207 | S | 0 | 模块总压低压 (module total voltage low) | Bit 6 of field 3200: module total voltage low | Official |
| 3208 | S | 0 | 模块总压高压 (module total voltage high) | Bit 7 of field 3200: module total voltage high | Official |
| 3300 | S | 0 | 系统告警状态2 (system alarm status 2) | Alarm status 2, bits 3301–3308 | Official |
| 3301 | S | 0 | 空 (empty) | Bit 0 of field 3300: empty | Official |
| 3302 | S | 0 | 空 (empty) | Bit 1 of field 3300: empty | Official |
| 3303 | S | 0 | 空 (empty) | Bit 2 of field 3300: empty | Official |
| 3304 | S | 0 | 空 (empty) | Bit 3 of field 3300: empty | Official |
| 3305 | S | 0 | 内部通信错误 (internal communication error) | Bit 4 of field 3300: internal communication error | Official |
| 3306 | S | 0 | 放电过流告警 (discharge overcurrent alarm) | Bit 5 of field 3300: discharge overcurrent alarm | Official |
| 3307 | S | 0 | 充电过流告警 (charge overcurrent alarm) | Bit 6 of field 3300: charge overcurrent alarm | Official |
| 3308 | S | 0 | 单芯温度一致性告警 (cell temperature consistency alarm) | Bit 7 of field 3300: cell temperature consistency alarm | Official |
| 3400 | S | 0 | 系统保护状态1 (system protection status 1) | Protection status 1, bits 3401–3408 | Official |
| 3401 | S | 0 | 空 (empty) | Bit 0 of field 3400: empty | Official |
| 3402 | S | 0 | MOSFET过温 (MOSFET over-temperature) | Bit 1 of field 3400: MOSFET over-temperature | Official |
| 3403 | S | 0 | 单芯温度欠温 (cell under-temperature) | Bit 2 of field 3400: cell under-temperature | Official |
| 3404 | S | 0 | 单芯温度过温 (cell over-temperature) | Bit 3 of field 3400: cell over-temperature | Official |
| 3405 | S | 0 | 单芯电压欠压 (cell undervoltage) | Bit 4 of field 3400: cell undervoltage | Official |
| 3406 | S | 0 | 单芯电压过压 (cell overvoltage) | Bit 5 of field 3400: cell overvoltage | Official |
| 3407 | S | 0 | 模块总压欠压 (module total undervoltage) | Bit 6 of field 3400: module total undervoltage | Official |
| 3408 | S | 0 | 模块总压过压 (module total overvoltage) | Bit 7 of field 3400: module total overvoltage | Official |
| 3500 | S | 0 | 系统保护状态2 (system protection status 2) | Protection status 2, bits 3501–3508 | Official |
| 3501 | S | 0 | 空 (empty) | Bit 0 of field 3500: empty | Official |
| 3502 | S | 0 | 空 (empty) | Bit 1 of field 3500: empty | Official |
| 3503 | S | 0 | 空 (empty) | Bit 2 of field 3500: empty | Official |
| 3504 | S | 0 | 系统故障保护 (system fault protection) | Bit 3 of field 3500: system fault protection | Official |
| 3505 | S | 0 | 空 (empty) | Bit 4 of field 3500: empty | Official |
| 3506 | S | 0 | 放电过流保护 (discharge overcurrent protection) | Bit 5 of field 3500: discharge overcurrent protection | Official |
| 3507 | S | 0 | 充电过流保护 (charge overcurrent protection) | Bit 6 of field 3500: charge overcurrent protection | Official |
| 3508 | S | 0 | 空 (empty) | Bit 7 of field 3500: empty | Official |
| 3600 | F | 56.5 | 充电电压建议上限 (suggested charge voltage upper limit) | Suggested charge voltage upper limit V | Official |
| 3700 | F | 48.0 | 充电电压建议下限 (suggested charge voltage lower limit) | Suggested charge voltage lower limit V (not a discharge cutoff) | Official |
| 3800 | F | 80.0 | 最大充电电流 (maximum charge current) | Maximum charge current A | Confirmed |
| 3900 | F | 200.0 | 最大放电电流 (maximum discharge current) | Maximum discharge current A | Confirmed |
| 4000 | S | 192 | 充放电状态 (charge/discharge status) | Charge/discharge status, bits 4001–4008. The bit 7 change near 100% SOC is charge enable (4008) dropping | Official |
| 4001 | S | 0 | 空 (empty) | Bit 0 of field 4000: empty | Official |
| 4002 | S | 0 | 空 (empty) | Bit 1 of field 4000: empty | Official |
| 4003 | S | 0 | 空 (empty) | Bit 2 of field 4000: empty | Official |
| 4004 | S | 0 | 满充请求 (full-charge request) | Bit 3 of field 4000: full-charge request | Official |
| 4005 | S | 0 | 强充2 (force charge 2) | Bit 4 of field 4000: force charge 2 | Official |
| 4006 | S | 0 | 强充1 (force charge 1) | Bit 5 of field 4000: force charge 1 | Official |
| 4007 | S | 1 | Discharge enable | Bit 6 of field 4000: Discharge enable | Official |
| 4008 | S | 1 | Charge enable | Bit 7 of field 4000: Charge enable | Official |
| 4100 | S | 0 | 总报警状态 (total alarm status) | Total alarm status | Official |

## Individual BMS board (145 fields)

| ID | Type | Observed example | Official name | Meaning / hypothesis | Confidence |
|---:|:---:|---|---|---|---|
| 10000 | T | 0100000000000001 | 序列号 (serial number) | BMS board serial | Confirmed |
| 10001 | T | 0 | Battery序列号 (battery serial number) | Battery SN / internal slot string | Strong |
| 10100 | T | 24.9-26.9.1 | 软件版本号 (software version) | BMS software version | Confirmed |
| 10150 | T | R00TEST000000001-BMS | 所属电池系统SN (SN of the battery system it belongs to) | Battery system SN this board belongs to | Official |
| 10200 | S | 16 | 电芯节数 (cell count) | Cell count | Confirmed |
| 10300 | F | 3.307 | Cell 1 voltage | Cell 01 voltage V | Confirmed |
| 10400 | F | 3.313 | Cell 2 voltage | Cell 02 voltage V | Confirmed |
| 10500 | F | 3.313 | Cell 3 voltage | Cell 03 voltage V | Confirmed |
| 10600 | F | 3.313 | Cell 4 voltage | Cell 04 voltage V | Confirmed |
| 10700 | F | 3.312 | Cell 5 voltage | Cell 05 voltage V | Confirmed |
| 10800 | F | 3.313 | Cell 6 voltage | Cell 06 voltage V | Confirmed |
| 10900 | F | 3.313 | Cell 7 voltage | Cell 07 voltage V | Confirmed |
| 11000 | F | 3.313 | Cell 8 voltage | Cell 08 voltage V | Confirmed |
| 11100 | F | 3.313 | Cell 9 voltage | Cell 09 voltage V | Confirmed |
| 11200 | F | 3.313 | Cell 10 voltage | Cell 10 voltage V | Confirmed |
| 11300 | F | 3.313 | Cell 11 voltage | Cell 11 voltage V | Confirmed |
| 11400 | F | 3.314 | Cell 12 voltage | Cell 12 voltage V | Confirmed |
| 11500 | F | 3.313 | Cell 13 voltage | Cell 13 voltage V | Confirmed |
| 11600 | F | 3.314 | Cell 14 voltage | Cell 14 voltage V | Confirmed |
| 11700 | F | 3.313 | Cell 15 voltage | Cell 15 voltage V | Confirmed |
| 11800 | F | 3.31 | Cell 16 voltage | Cell 16 voltage V | Confirmed |
| 11900 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 12000 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 12100 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 12200 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 12300 | S | 3 | 温度点数量 (temperature point count) | Temperature point count | Official |
| 12400 | F | 25.0 | Temperature of BMS board | BMS board temperature C | Confirmed |
| 12500 | F | 18.799999 | Avg temperature of cell 1 to 4 | Average temperature of cells 1–4 C | Official |
| 12600 | F | 18.9 | Avg temperature of cell 5 to 8 | Average temperature of cells 5–8 C | Official |
| 12700 | F | 0.0 | Avg temperature of cell 9 to 12 | Average temperature of cells 9–12 C; 0 means no sensor | Official |
| 12800 | F | 0.0 | Avg temperature of cell 13 to 16 | Average temperature of cells 13–16 C; 0 means no sensor | Official |
| 12900 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 13000 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 13100 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 13200 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 13300 | F | 0.0 | not in cloud list | Unused temperature/voltage/current slot; not in cloud point list | Tentative |
| 13400 | F | -5.5 | Current | Board current A | Confirmed |
| 13500 | F | 53.0 | Module voltage | Module voltage V | Confirmed |
| 13600 | F | 58.928001 | Remain capacity 1 | Remaining capacity 1, units unknown. Equals 13800 in every cloud poll (1.392 on 0106… boards, 3.392 on 0601… boards) and does not track SOC like 14000 | Official name; values unverified |
| 13700 | S | 4 | 用户自定义个数 (user-defined count) | User-defined count (4 on every board); not documented as module count | Official name; values unverified |
| 13800 | F | 3.392 | Module total capacity 1 | Module total capacity 1, units unknown | Official name; values unverified |
| 13900 | S | 99 | Cycle number | Cycle count | Confirmed |
| 14000 | F | 190.0 | Remain capacity 2 | Remaining capacity 2, Ah (190 at 95% SOC, 198–200 at 100%). Misreported on the two-module battery, see caveats | Official |
| 14100 | F | 200.0 | Module total capacity 2 | Module total capacity 2, Ah. Misreported on the two-module battery, see caveats | Official |
| 14200 | S | 16 | 电芯节数 error code (cell count error code) | Cell count error code; first entry of the error-code block (value 16 here, meaning of the value unknown) | Official name; values unverified |
| 14300 | S | 0 | Cell 1 error code | Cell 1 error code; 0 = no error | Official |
| 14400 | S | 0 | Cell 2 error code | Cell 2 error code; 0 = no error | Official |
| 14500 | S | 0 | Cell 3 error code | Cell 3 error code; 0 = no error | Official |
| 14600 | S | 0 | Cell 4 error code | Cell 4 error code; 0 = no error | Official |
| 14700 | S | 0 | Cell 5 error code | Cell 5 error code; 0 = no error | Official |
| 14800 | S | 0 | Cell 6 error code | Cell 6 error code; 0 = no error | Official |
| 14900 | S | 0 | Cell 7 error code | Cell 7 error code; 0 = no error | Official |
| 15000 | S | 0 | Cell 8 error code | Cell 8 error code; 0 = no error | Official |
| 15100 | S | 0 | Cell 9 error code | Cell 9 error code; 0 = no error | Official |
| 15200 | S | 0 | Cell 10 error code | Cell 10 error code; 0 = no error | Official |
| 15300 | S | 0 | Cell 11 error code | Cell 11 error code; 0 = no error | Official |
| 15400 | S | 0 | Cell 12 error code | Cell 12 error code; 0 = no error | Official |
| 15500 | S | 0 | Cell 13 error code | Cell 13 error code; 0 = no error | Official |
| 15600 | S | 0 | Cell 14 error code | Cell 14 error code; 0 = no error | Official |
| 15700 | S | 0 | Cell 15 error code | Cell 15 error code; 0 = no error | Official |
| 15800 | S | 0 | Cell 16 error code | Cell 16 error code; 0 = no error | Official |
| 15900 | S | 0 | not in cloud list | Reserved cell/status slot; not in cloud point list | Unknown |
| 16000 | S | 0 | not in cloud list | Reserved cell/status slot; not in cloud point list | Unknown |
| 16100 | S | 0 | not in cloud list | Reserved cell/status slot; not in cloud point list | Unknown |
| 16200 | S | 0 | not in cloud list | Reserved cell/status slot; not in cloud point list | Unknown |
| 16300 | S | 0 | Temperature of BMS board error code | BMS board temperature error code | Official |
| 16400 | S | 0 | Avg temperature of cell 1 to 4 error code | Cells 1–4 average temperature error code | Official |
| 16500 | S | 0 | Avg temperature of cell 5 to 8 error code | Cells 5–8 average temperature error code | Official |
| 16600 | S | 0 | Avg temperature of cell 9 to 12 error code | Cells 9–12 average temperature error code | Official |
| 16700 | S | 0 | Avg temperature of cell 13 to 16 error code | Cells 13–16 average temperature error code | Official |
| 16800 | S | 0 | Avg temperature of cell 17 to 20 error code | Cells 17–20 average temperature error code (no such cells on a 16-cell board) | Official |
| 16900 | S | 0 | not in cloud list | Reserved cell/status slot; not in cloud point list | Unknown |
| 17000 | S | 0 | not in cloud list | Reserved cell/status slot; not in cloud point list | Unknown |
| 17100 | S | 0 | not in cloud list | Reserved cell/status slot; not in cloud point list | Unknown |
| 17200 | S | 0 | not in cloud list | Reserved cell/status slot; not in cloud point list | Unknown |
| 17300 | S | 0 | Charge current | Charge current A | Official |
| 17400 | S | 0 | Module voltage error code | Module voltage error code (2 on every board, meaning of the value unknown) | Official name; values unverified |
| 17500 | S | 0 | Discharge current | Discharge current A | Official |
| 17600 | S | 0 | Status1 | Status1: protection bits 17601–17608 | Official |
| 17601 | S | 0 | 总压过压/module over voltage: OV | Bit 0 of field 17600: module over voltage: OV | Official |
| 17602 | S | 0 | 单芯欠压/cell under voltage | Bit 1 of field 17600: cell under voltage | Official |
| 17603 | S | 0 | 充电过流/charge over current: COC | Bit 2 of field 17600: charge over current: COC | Official |
| 17604 | S | 0 | 空1 (empty) | Bit 3 of field 17600: empty | Official |
| 17605 | S | 0 | 放电过流/discharge over current: DOC | Bit 4 of field 17600: discharge over current: DOC | Official |
| 17606 | S | 0 | 放电过温/discharge over temperature | Bit 5 of field 17600: discharge over temperature | Official |
| 17607 | S | 0 | 充电过温/charge over temperature | Bit 6 of field 17600: charge over temperature | Official |
| 17608 | S | 0 | 总压欠压/module under voltage: UV | Bit 7 of field 17600: module under voltage: UV | Official |
| 17700 | S | 14 | Status2 | Status2: power and MOSFET bits 17701–17704. 14 (0x0E) = discharge, charge and pre-charge MOSFETs on; the bit that changes is 17701 | Official |
| 17701 | S | 0 | 使用模块供电/using battery module power | Bit 0 of field 17700: using battery module power | Official |
| 17702 | S | 1 | Discharge MOSFET | Bit 1 of field 17700: Discharge MOSFET | Official |
| 17703 | S | 1 | Charge MOSFEET | Bit 2 of field 17700: Charge MOSFEET | Official |
| 17704 | S | 1 | Pre MOSFET（for some products） | Bit 3 of field 17700: Pre MOSFET（for some products） | Official |
| 17800 | S | 64 | Status3 | Status3: bits 17801–17808. The earlier correlation (0x80 charging, 0x40 discharging, 0x08 near low current) matches 17808 / 17807 / 17804 | Official |
| 17801 | S | 0 | 蜂鸣器功能/buzzer | Bit 0 of field 17800: buzzer | Official |
| 17802 | S | 0 | 空2 (empty) | Bit 1 of field 17800: empty | Official |
| 17803 | S | 0 | 空3 (empty) | Bit 2 of field 17800: empty | Official |
| 17804 | S | 0 | 充满状态指示/fully charged (SOC=100%) | Bit 3 of field 17800: fully charged (SOC=100%) | Official |
| 17805 | S | 0 | 空4 (empty) | Bit 4 of field 17800: empty | Official |
| 17806 | S | 0 | 加热膜启动 (heating film on) | Bit 5 of field 17800: heating film on | Official |
| 17807 | S | 1 | 有效放电电流 (valid discharge current) | Bit 6 of field 17800: valid discharge current | Official |
| 17808 | S | 0 | 有效充电电流 (valid charge current) | Bit 7 of field 17800: valid charge current | Official |
| 17900 | S | 0 | Status4 | Status4: cell 1–8 status bits | Official |
| 17901 | S | 0 | Cell 1 status | Cell 1 status (bit 0 of 17900) | Official |
| 17902 | S | 0 | Cell 2 status | Cell 2 status (bit 1 of 17900) | Official |
| 17903 | S | 0 | Cell 3 status | Cell 3 status (bit 2 of 17900) | Official |
| 17904 | S | 0 | Cell 4 status | Cell 4 status (bit 3 of 17900) | Official |
| 17905 | S | 0 | Cell 5 status | Cell 5 status (bit 4 of 17900) | Official |
| 17906 | S | 0 | Cell 6 status | Cell 6 status (bit 5 of 17900) | Official |
| 17907 | S | 0 | Cell 7 status | Cell 7 status (bit 6 of 17900) | Official |
| 17908 | S | 0 | Cell 8 status | Cell 8 status (bit 7 of 17900) | Official |
| 18000 | S | 0 | Status5 | Status5: cell 9–16 status bits | Official |
| 18001 | S | 0 | Cell 9 status | Cell 9 status (bit 0 of 18000) | Official |
| 18002 | S | 0 | Cell 10 status | Cell 10 status (bit 1 of 18000) | Official |
| 18003 | S | 0 | Cell 11 status | Cell 11 status (bit 2 of 18000) | Official |
| 18004 | S | 0 | Cell 12 status | Cell 12 status (bit 3 of 18000) | Official |
| 18005 | S | 0 | Cell 13 status | Cell 13 status (bit 4 of 18000) | Official |
| 18006 | S | 0 | Cell 14 status | Cell 14 status (bit 5 of 18000) | Official |
| 18007 | S | 0 | Cell 15 status | Cell 15 status (bit 6 of 18000) | Official |
| 18008 | S | 0 | Cell 16 status | Cell 16 status (bit 7 of 18000) | Official |
| 18100 | F | 3.6 | 单芯高压上限 (cell high voltage upper limit) | Cell high voltage limit V | Confirmed |
| 18200 | F | 2.9 | 单芯低压 (cell low voltage) | Cell low voltage limit V | Confirmed |
| 18300 | F | 2.85 | 单芯欠压 (cell undervoltage) | Cell undervoltage limit V | Confirmed |
| 18400 | F | 65.0 | 充电温度上限 (charge temperature upper limit) | Charge high temperature limit C | Confirmed |
| 18500 | F | 0.0 | 充电温度下限 (charge temperature lower limit) | Charge low temperature limit C | Confirmed |
| 18600 | F | 120.0 | 充电电流限值 (charge current limit) | Charge current limit A | Official |
| 18700 | F | 57.599998 | 模块高压上限 (module high voltage upper limit) | Module high voltage upper limit V (protection threshold, not a charge voltage request) | Official |
| 18800 | F | 48.0 | 模块低压 (module low voltage) | Module low voltage limit V (protection threshold) | Official |
| 18900 | F | 44.799999 | 模块欠压 (module undervoltage) | Module undervoltage limit V | Confirmed |
| 19000 | F | 65.0 | 放电温度上限 (discharge temperature upper limit) | Discharge high temperature limit C | Confirmed |
| 19100 | F | -20.0 | 放电温度下限 (discharge temperature lower limit) | Discharge low temperature limit C | Confirmed |
| 19200 | F | 120.0 | 放电电流限值 (discharge current limit) | Discharge current limit A | Official |
| 19300 | F | 0.0 | 充电电压建议上限 (suggested charge voltage upper limit) | Per-board suggested charge voltage upper limit V (0 on boards; bank 3600 carries the value) | Official |
| 19400 | F | 0.0 | 充电电压建议下限 (suggested charge voltage lower limit) | Per-board suggested charge voltage lower limit V (0 on boards) | Official |
| 19500 | F | 0.0 | 最大充电电流 (maximum charge current) | Per-board maximum charge current A (0 on boards) | Official |
| 19600 | F | 0.0 | 最大放电电流 (maximum discharge current) | Per-board maximum discharge current A (0 on boards) | Official |
| 19700 | S | 0 | 充放电状态 (charge/discharge status) | Per-board charge/discharge status, same bits as 4000 | Official |
| 19701 | S | 0 | 空5 (empty) | Bit 0 of field 19700: empty | Official |
| 19702 | S | 0 | 空6 (empty) | Bit 1 of field 19700: empty | Official |
| 19703 | S | 0 | 空7 (empty) | Bit 2 of field 19700: empty | Official |
| 19704 | S | 0 | 满充请求 (full-charge request) | Bit 3 of field 19700: full-charge request | Official |
| 19705 | S | 0 | 强充2 (force charge 2) | Bit 4 of field 19700: force charge 2 | Official |
| 19706 | S | 0 | 强充1 (force charge 1) | Bit 5 of field 19700: force charge 1 | Official |
| 19707 | S | 0 | Discharge enable | Bit 6 of field 19700: Discharge enable | Official |
| 19708 | S | 0 | Charge enable | Bit 7 of field 19700: Charge enable | Official |
| 19800 | S | 0 | 总报警状态 (total alarm status) | Per-board total alarm status | Official |

## Cloud-only points

The cloud lists these points, but they never appear in the captured logger uploads. On this battery the cloud returns them blank, so there is no wire evidence for them. They may be filled on other models or firmware.

| IDs | Scope | Official names |
|---|---|---|
| T, TIME | bank and board | 数据采集时间 (data collection time); 子设备最后一包时间 (last packet time per sub-device, comma-separated) |
| SUB | bank | 子设备列表 (sub-device list, comma-separated board serials) |
| 500 | bank | 序列号SN (serial number) |
| 900 / 1000 / 1100 | bank | 平均循环次数 / 最大循环次数 / 平均SOH (average cycles / maximum cycles / average SOH) |
| 1700 | bank | 单芯平均温度 (average cell temperature) |
| 2200 / 2500 / 2600 | bank | MOSFET average temperature / lowest temperature / lowest-numbered module with the lowest MOSFET temperature |
| 2700 | bank | BMS平均温度 (average BMS temperature) |
| 6000 – 6006 | bank | battery type, battery function, program type, main-controller type, hardware type, program subtype, module count |
| 21000 – 21006 | board | same seven type fields as 6000 – 6006 |
| 22100 – 22400 | board | BOOT version, parameter version, DIP-switch state, protocol type |
| 22500 – 23200 | board | 切断报警FLAG1 – FLAG8 (cut-off alarm flags 1–8). Bits include level-2 and level-3 voltage, current and temperature alarms, invalid cell voltage / temperature / current, AFE / BMS / PCS communication faults, pre-charge failure, parallel-connection failure, breaker trip, charge or discharge MOSFET failure, short circuit and MOSFET over-temperature |
| 23300 | board | 烟感/气体检测值 (smoke / gas sensor value) |
| 23400 / 23500 | board | 累计充电电量 / 累计放电电量 (cumulative charged / discharged energy) |
| 23600 / 23700 | board | suggested charge / discharge current |
| 23800 / 23900 / 24000 | board | SOC / SOH / 额定电量 (rated capacity) |
| 24100 – 25700 | board | 从设备数量 (slave-device count) and, for slave devices 1–4, version, hardware info 1, hardware info 2 and product ID |
| 25800 – 26700 | board | 预留1 – 预留10 (reserved 1–10) |

Bit sub-points (for example 22501, 23001) follow the same scheme as the wire bitmasks: the last two digits are the bit number plus one. The full labels are in `cloud_point_names.json`.

## Upstream integration cross-reference

The Dyness Open API realtime endpoint (`/v1/device/realTime/data`) returns `pointId` / `pointValue` / `pointNameCn` entries that use the same numeric IDs as this dictionary. The upstream Home Assistant integration ([shopf/dyness_battery](https://github.com/shopf/dyness_battery) `v2.6.0`, `custom_components/dyness_battery/__init__.py`) maps those points to sensors, but it ignores `pointNameCn`; its labels come from the maintainer's work and community dumps (issues [#1](https://github.com/shopf/dyness_battery/issues/1) and [#2](https://github.com/shopf/dyness_battery/issues/2) list the Chinese names). The Agreement column below now judges upstream against the official names.

References are to upstream symbols: `PB-A` is the PowerBrick variant A branch of `DynessDataCoordinator._async_update_data`, `PB-B` is PowerBrick variant B, `DL5` is the `is_dl5` branch of `_parse_module_points`, and `ALARM_BITS_1` / `ALARM_BITS_2` are the alarm label tables used for `alarmText`.

### Bank summary

| ID | Official meaning | Upstream mapping | Agreement |
|---:|---|---|---|
| 300 | Host software version | not read by PB-A | n/a |
| 400 | Total battery count; in practice the board count (4 boards in 3 batteries here) | PB-A module count, multiplies `batteryCapacity` | agrees it counts boards; multiplying a per-battery capacity by it over-counts when a battery holds two boards |
| 600 | Average voltage | PB-A `packVoltage` | agrees |
| 700 | Total current | PB-A `realTimeCurrent`; `workStatus` Charging above +1 A, Discharging below -1 A | agrees, positive is charge |
| 800 | Average SOC | PB-A `soc` | agrees |
| 900 | Average cycle count (cloud-only, blank here) | PB-A `cycleCount` | agrees on meaning; no value on this battery |
| 1200 | Minimum SOH | PB-A `soh` | close: upstream treats it as the bank SOH, the official name is the minimum across modules |
| 1300 / 1500 | Highest / lowest cell voltage | PB-A `cellVoltageMax` / `cellVoltageMin` | agrees |
| 1401 / 1402 | Module / cell of the highest cell voltage | PB-A `cellVoltageMaxModule` / `cellVoltageMaxCell` | agrees |
| 1601 / 1602 | Module / cell of the lowest cell voltage | PB-A `cellVoltageMinModule` / `cellVoltageMinCell` | agrees |
| 1800 / 2000 | Highest / lowest cell temperature | PB-A `tempMax` / `tempMin` | agrees |
| 2300 | Highest MOSFET temperature | PB-A `tempMosfet` | agrees |
| 2800 / 3000 | Highest / lowest BMS temperature | PB-A `tempBmsMax` / `tempBmsMin` | agrees |
| 3200 | Alarm status 1 | PB-A `alarmStatus1` | agrees |
| 3201 | Cell voltage consistency alarm | ALARM_BITS_1 "Cell voltage consistency warning"; PB-A `alarmSpreadV` | ALARM_BITS_1 agrees; PB-A name is close |
| 3202 | MOSFET high temperature | ALARM_BITS_1 "MOSFET high temperature"; PB-A `alarmSpreadT` | ALARM_BITS_1 agrees; PB-A wrong |
| 3203 | Cell low temperature | ALARM_BITS_1 "Cell low temperature"; PB-A `alarmAfe` | ALARM_BITS_1 agrees; PB-A wrong |
| 3204 | Cell high temperature | ALARM_BITS_1 "Cell high temperature"; PB-A `alarmBms` | ALARM_BITS_1 agrees; PB-A wrong |
| 3205 | Cell low voltage | ALARM_BITS_1 "Cell low voltage"; PB-A `alarmInsul` | ALARM_BITS_1 agrees; PB-A wrong |
| 3206 | Cell high voltage | ALARM_BITS_1 "Cell high voltage" | agrees |
| 3207 | Module total voltage low | ALARM_BITS_1 "Pack low voltage" | agrees |
| 3208 | Module total voltage high | ALARM_BITS_1 "Pack high voltage" | agrees |
| 3300 | Alarm status 2 | PB-A `alarmStatus2` | agrees |
| 3305 – 3308 | Internal communication error, discharge overcurrent, charge overcurrent, cell temperature consistency | ALARM_BITS_2, same four labels | agrees |
| 3600 | Suggested charge voltage upper limit | PB-A `chargeVoltageLimit` | agrees |
| 3700 | Suggested charge voltage lower limit | PB-A `dischargeVoltageLimit` | wrong: it is a charge-voltage request, not a discharge limit |
| 3800 / 3900 | Maximum charge / discharge current | PB-A `chargeCurrentLimit` / `dischargeCurrentLimit` | agrees |
| 4000 | Charge/discharge status (4007 discharge enable, 4008 charge enable) | `balancingStatus` = value is nonzero, for JUNIOR and DL5 schemas only | wrong on this family: nonzero means charge or discharge is enabled, not balancing. Balancing (均衡状态) is the Tower meaning of 4000 |
| 4100 | Total alarm status | PB-A `alarmSys`, the total-alarm flag that gates notifications | agrees |

**Upstream conflict on 3201–3205, resolved.** `ALARM_BITS_1` matches the official names for all eight bits. The PowerBrick branch's Tower names (voltage spread, temperature spread, AFE, BMS, insulation) belong to the Tower point layout, where those meanings sit at 5001–5104, and are wrong for this family.

**Sunday overvoltage event.** Field `3200` went `0x00`, then `0x80`, then `0xA0` while the pack reached about 56.74 V against a 56.50 V charge-voltage request, with a maximum cell of about 3.563 V. `0x80` is bit 7 (`3208`, module total voltage high) and `0xA0` adds bit 5 (`3206`, cell high voltage). The bit order is now confirmed by the cloud itself: on 2026-10-12 it reported `3200` = 128 with only `3208` = 1, and `4000` = 64 with only `4007` = 1. So sub-point *n*01 is bit 0 and *n*08 is bit 7.

### Individual BMS board

| ID | Official meaning | Upstream mapping | Agreement |
|---:|---|---|---|
| 10000 | Serial number | presence selects the DL5 branch | agrees |
| 10001 | Battery serial number | PB-B serial passed to `/v2/GetRealTimeDataBySN` | agrees |
| 10100 | Software version | DL5 and PB-B `firmwareVersion` | agrees |
| 10300 – 11800 | Cell 1–16 voltage | DL5 `cell_01` … `cell_16`; PB-A and PB-B `cellVoltage01` … `16` | agrees |
| 12400 | BMS board temperature | DL5 `bms_temp`; PB-B `tempBmsMax` | agrees |
| 12500 / 12600 | Average temperature of cells 1–4 / 5–8 | DL5 `cell_temp_1` / `cell_temp_2` | agrees; the official names say they are group averages |
| 12700 / 12800 | Average temperature of cells 9–12 / 13–16 | PB-B reads `12500 + i*100` for `i` in 0–3 as cell temperatures, ignoring zeros | agrees, zero means absent |
| 13400 | Current | DL5 `current`; PB-B `realTimeCurrent` | agrees |
| 13500 | Module voltage | DL5 `voltage`; PB-B `packVoltage` | agrees |
| 13600 / 13800 | Remaining / total capacity 1, units unknown | DL5 fallback `remain_ah` / `total_ah`, used only when 14000 ≤ 100 | not exercised on this battery (14000 is 190–200) |
| 13900 | Cycle number | DL5 `cycle_count`; PB-B `cycleCount` | agrees |
| 14000 / 14100 | Remaining / total capacity 2, Ah | DL5: SOC / SOH percent when ≤ 100, otherwise `remain_ah` / `total_ah` | agrees for this hardware; the percent branch has no basis in the official names |
| 14300 – 15800 | Cell 1–16 error code | DL5 `has_alarm` = any of the 16 values nonzero | agrees |
| 18600 | Charge current limit | PB-B `chargeCurrentLimit` | agrees |
| 18700 | Module high voltage upper limit (protection) | PB-B `chargeVoltageLimit` | wrong: protection threshold (57.6 V), not the charge voltage request (bank 3600) |
| 18800 | Module low voltage (protection) | PB-B `dischargeVoltageLimit` | wrong: protection threshold, not the bank's suggested limits |
| 19200 | Discharge current limit | PB-B `dischargeCurrentLimit` | agrees |

Upstream reads none of the board status words. Their official meanings are now in the board table: `17600` Status1 (protection bits), `17700` Status2 (module power and MOSFET states), `17800` Status3 (buzzer, fully charged, heating film, valid discharge and charge current), `17900` / `18000` Status4 / Status5 (cell 1–16 status), and `19700` per-board charge/discharge status.

### Other community guesses

The [uppaljs/dyness_battery](https://github.com/uppaljs/dyness_battery) fork describes `13600` as DC internal resistance, `13700` as module count and `14000` as SOH %. The official names are remaining capacity 1, user-defined count and remaining capacity 2. `13700` happens to equal the module count (4) on this battery, but that is not what the name says.

## Interpretation caveats

- Never add duplicate records for board `0709`. The duplicates are logger resends triggered by the server’s `00 77` command (see `dyness_protocol_spec.md`, Duplicate board frames explained).
- Four boards, three physical batteries (owner-confirmed). One 200 Ah battery holds two modules with one board each; the other two batteries have one board each. `400` = 4 counts boards. The two-board battery is probably `0005`/`0496` (same generation and cycle count); the packets do not say which boards share a battery.
- Cloud current polarity observed: positive is charge, negative discharge.
- Fields `14000` and `14100` are wrong on the two-module battery: each of its boards reports 198 Ah although each module is about 100 Ah (owner-confirmed). The single-module batteries report a plausible 200 Ah. Summing `14100` across boards therefore gives 800 Ah instead of the real 600 Ah.
- The cloud `SUB` list drops boards intermittently while `400` stays 4. On 2026-10-12 (bank data time, UTC), `0709` was missing at 07:14; all four were listed at 07:19, 07:24 and 07:29; `0005` was missing at 07:39; `0005` and `0496` at 07:44; `0496` at 07:49 and 07:54. The 07:34 upload is absent from the cloud entirely. Treat `400`, not the length of `SUB`, as the board count, and expect cloud board data to have gaps. The cause is unknown and not being pursued.
- Two board generations are present. The `0106…` boards (`0496`, `0005`) show about 530 cycles, `14000`/`14100` = 198 Ah and `13600` = 1.392. The `0601…` boards (`0115`, `0709`) show about 100 cycles, 200 Ah and `13600` = 3.392.
- Wire fields 11900–12200, 12900–13300, 15900–16200 and 16900–17200 are absent from the cloud point list. They are zero in every capture and have no official name.
- No verified 90% DoD parameter or lifetime kWh counter in the Raymon upload.
- Older Dyness Monitor serial/CAN definitions are a **different protocol** and cannot be mapped by bit position automatically.
