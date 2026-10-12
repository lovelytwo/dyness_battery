#!/usr/bin/env python3
"""Decode Raymon/Dyness logger PCAPs (including boot/login and OTA check).

No third-party modules required. Supports classic Ethernet PCAP (not PCAPNG),
Raymon's length-prefixed TCP/5005 messages, and plaintext HTTP update checks.

Usage:
    python3 dyness_decode.py 'dyness(3).pcap' --outdir decoded --tz Australia/Melbourne

Creates:
    dyness_events.csv    All recognised transactions, including startup and HTTP
    dyness_fields.csv    Raw field IDs, values and type-specific bytes
    dyness_cells.csv     Per-reported-BMS-board cell voltages (NOT battery count)
    dyness_decoded.json  Full parsed events and telemetry, sans login credentials

Protocol field names and status-code meanings not documented by vendor are
intentionally NOT guessed. Login credentials present in the plaintext packets
are omitted from exports, logging, and errors.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import ipaddress
import json
import struct
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
MAX_FRAME = 1_048_576

# Labels confirmed by comparing the raw BMS messages with the Dyness EU
# partner portal on 2026-10-10. Unknown IDs are deliberately left unlabeled.
SUMMARY_FIELD_LABELS = {
    100: 'host_device_name', 200: 'manufacturer_name', 300: 'host_version',
    400: 'reported_bms_board_count',
    600: 'battery_bank_voltage_V', 700: 'battery_bank_current_A',
    800: 'battery_bank_SOC_pct', 1200: 'battery_bank_SOH_pct',
    1300: 'battery_bank_max_cell_voltage_V',
    1500: 'battery_bank_min_cell_voltage_V',
    1800: 'battery_bank_max_temp_C', 2000: 'battery_bank_min_temp_C',
    2300: 'battery_bank_max_MOS_temp_C',
    2800: 'battery_bank_max_BMS_temp_C', 3000: 'battery_bank_min_BMS_temp_C',
    3600: 'bms_charge_voltage_limit_V_inferred',
    3700: 'bms_discharge_voltage_limit_V_inferred',
    3800: 'max_charge_current_A', 3900: 'max_discharge_current_A',
    3200: 'raw_bank_status_3200', 4000: 'raw_bank_status_4000',
}
MODULE_FIELD_LABELS = {
    10000: 'bms_serial_number', 10100: 'software_version',
    10200: 'cell_count',
    **{10300 + 100 * i: f'cell_{i+1:02d}_voltage_V' for i in range(16)},
    12400: 'bms_board_temperature_C',
    12500: 'temperature_1_C', 12600: 'temperature_2_C',
    13400: 'bms_board_current_A', 13500: 'bms_board_voltage_V',
    13900: 'bms_board_cycle_count',
    14000: 'remaining_capacity_Ah_inferred', 14100: 'full_capacity_Ah_inferred',
    17700: 'raw_bms_status_17700', 17800: 'raw_bms_status_17800',
    18100: 'cell_high_voltage_limit_V',
    18200: 'cell_low_voltage_limit_V',
    18300: 'cell_undervoltage_limit_V',
    18400: 'charge_temperature_upper_limit_C',
    18500: 'charge_temperature_lower_limit_C',
    18600: 'current_protection_limit_A',
    18700: 'module_high_voltage_limit_V',
    18800: 'module_low_voltage_limit_V',
    18900: 'module_undervoltage_limit_V',
    19000: 'discharge_temperature_upper_limit_C',
    19100: 'discharge_temperature_lower_limit_C',
}


def parse_pcap(path):
    """Return IPv4 TCP packets, including SYN/FIN flags needed for sessions."""
    buf = Path(path).read_bytes()
    if len(buf) < 24:
        raise ValueError('PCAP is too short')
    magic = buf[:4].hex()
    endian = {'d4c3b2a1': '<', 'a1b2c3d4': '>',
              '4d3cb2a1': '<', 'a1b23c4d': '>'}.get(magic)
    if endian is None:
        raise ValueError('Expected classic .pcap (PCAPNG must be converted first)')
    linktype = struct.unpack_from(endian + 'I', buf, 20)[0]
    if linktype not in (1, 101, 113, 276):
        raise ValueError(f'Unsupported PCAP link type {linktype}')
    divisor = 1e9 if magic in ('4d3cb2a1', 'a1b23c4d') else 1e6
    pos = 24
    packets = []
    while pos + 16 <= len(buf):
        sec, frac, caplen, _origlen = struct.unpack_from(endian + 'IIII', buf, pos)
        pos += 16
        if pos + caplen > len(buf):
            break  # Capture copied before tcpdump finished writing
        raw = buf[pos:pos + caplen]
        pos += caplen
        if linktype == 1:  # Ethernet, including VLAN tags
            if len(raw) < 14:
                continue
            ethertype = int.from_bytes(raw[12:14], 'big')
            off = 14
            while ethertype in (0x8100, 0x88a8, 0x9100):
                if len(raw) < off + 4:
                    break
                ethertype = int.from_bytes(raw[off + 2:off + 4], 'big')
                off += 4
            if ethertype != 0x0800:
                continue
        elif linktype == 101:  # raw IP
            off = 0
        elif linktype == 113:  # Linux cooked SLL
            if len(raw) < 16 or raw[14:16] != b'\x08\x00':
                continue
            off = 16
        else:  # Linux cooked SLL2
            if len(raw) < 20 or raw[:2] != b'\x08\x00':
                continue
            off = 20
        ip = raw[off:]
        if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
            continue
        ihl = (ip[0] & 15) * 4
        if ihl < 20 or len(ip) < ihl + 20:
            continue
        if int.from_bytes(ip[6:8], 'big') & 0x1fff:
            continue  # non-first IPv4 fragment
        total = min(int.from_bytes(ip[2:4], 'big'), len(ip))
        if total < ihl + 20:
            continue
        src_port, dst_port, seq, _ack, offsetflags = struct.unpack_from('!HHIIH', ip, ihl)
        tcp_len = (offsetflags >> 12) * 4
        if tcp_len < 20 or ihl + tcp_len > total:
            continue
        packets.append({
            'time': dt.datetime.fromtimestamp(sec + frac / divisor, UTC),
            'src': str(ipaddress.IPv4Address(ip[12:16])),
            'dst': str(ipaddress.IPv4Address(ip[16:20])),
            'sport': src_port, 'dport': dst_port,
            'seq': seq, 'flags': offsetflags & 0x1ff,
            'payload': ip[ihl + tcp_len:total],
        })
    return packets


def session_groups(packets):
    """Separate streams by 4-tuple AND TCP SYN so reconnects do not merge."""
    latest = {}
    sessions = []
    for pkt in packets:  # In capture order
        a, b = (pkt['src'], pkt['sport']), (pkt['dst'], pkt['dport'])
        conn_key = tuple(sorted((a, b)))
        session = latest.get(conn_key)
        syn = bool(pkt['flags'] & 0x02) and not bool(pkt['flags'] & 0x10)
        if session is None or (syn and pkt['seq'] != session.get('syn_seq')):
            session = {'id': len(sessions) + 1, 'flows': collections.defaultdict(list),
                       'syn_seq': pkt['seq'] if syn else None, 'pair': conn_key}
            latest[conn_key] = session
            sessions.append(session)
        session['flows'][(pkt['src'], pkt['sport'], pkt['dst'], pkt['dport'])].append(pkt)
    return sessions


def tcp_stream(packets):
    """Reassemble in-order bytes; deduplicate retransmits; report lost gaps."""
    payload_packets = [p for p in packets if p['payload']]
    if not payload_packets:
        return b'', [], []
    # Offsets are relative to first observed payload sequence.  Handle wrap.
    first_seq = payload_packets[0]['seq']
    segments = sorted(((((p['seq'] - first_seq) & 0xffffffff), p)
                      for p in payload_packets), key=lambda row: row[0])
    out = bytearray()
    intervals = []
    problems = []
    for offset, packet in segments:
        if offset > len(out):
            problems.append(f'Missing {offset - len(out)} TCP bytes; stopped decoding this direction')
            break
        overlap = len(out) - offset
        if overlap >= len(packet['payload']):
            continue
        tail = packet['payload'][overlap:]
        intervals.append((len(out), len(out) + len(tail), packet['time']))
        out.extend(tail)
    return bytes(out), intervals, problems


def timestamp_at(offset, intervals):
    for begin, end, when in intervals:
        if begin <= offset < end:
            return when.isoformat()
    return None


def split_frames(data, intervals):
    """Length prefix counts bytes AFTER 4-byte prefix."""
    pos = 0
    while pos + 4 <= len(data):
        n = int.from_bytes(data[pos:pos + 4], 'big')
        if n < 3 or n > MAX_FRAME:
            yield None, timestamp_at(pos, intervals), f'Invalid frame length {n} at byte {pos}'
            return
        if pos + 4 + n > len(data):
            yield None, timestamp_at(pos, intervals), f'Incomplete last frame ({4+n} bytes expected, {len(data)-pos} available)'
            return
        yield data[pos:pos + 4 + n], timestamp_at(pos, intervals), None
        pos += 4 + n
    if pos != len(data):
        yield None, timestamp_at(pos, intervals), f'{len(data)-pos} trailing bytes'


def read_fields(frame, start, count):
    fields = []
    pos = start
    for _ in range(count):
        if pos + 5 > len(frame):
            raise ValueError('Truncated TLV field header')
        fid = int.from_bytes(frame[pos:pos+4], 'big')
        typ = chr(frame[pos+4])
        pos += 5
        if typ == 'T':
            if pos >= len(frame):
                raise ValueError('Missing text length')
            n = frame[pos]
            pos += 1
        elif typ in ('F', 'I'):
            n = 4
        elif typ == 'S':
            n = 2
        else:
            raise ValueError(f'Unknown type 0x{ord(typ):02X} for field {fid}')
        if pos + n > len(frame):
            raise ValueError(f'Truncated data for field {fid}')
        raw = frame[pos:pos + n]
        pos += n
        if typ == 'T':
            value = raw.rstrip(b'\x00').decode('utf-8', 'replace')
        elif typ == 'F':
            value = struct.unpack('>f', raw)[0]
        else:
            value = int.from_bytes(raw, 'big')
        fields.append({'id': fid, 'type': typ, 'value': value, 'raw_hex': raw.hex()})
    if pos != len(frame):
        raise ValueError(f'TLV ended at {pos} of {len(frame)} bytes')
    return fields


def decoded_frame(frame, time_utc, direction, session_id, src, dst):
    """All intentionally unknown status bytes are displayed WITHOUT interpretation."""
    msg = {
        'time_utc': time_utc, 'session_id': session_id,
        'source': src, 'destination': dst, 'direction': direction,
        'protocol': 'raymon_tcp', 'bytes': len(frame), 'kind': 'unknown',
        'logger_serial': '', 'module_serial': '', 'opcode': '',
        'detail': '', 'status_hex': '', 'fields': [],
    }
    if len(frame) < 7:
        msg['detail'] = 'Short application message'
        return msg
    # Server greeting does not have the common logger SN field.
    if frame[4:7] == b'\x00\x00\x7f':
        msg['kind'] = 'server_greeting'
        msg['detail'] = frame[7:].decode('ascii', 'replace')
        return msg
    if len(frame) < 23:
        msg['detail'] = 'Short logger message'
        return msg
    serial_len = frame[4]
    if serial_len > 48 or 5 + serial_len + 2 > len(frame):
        msg['detail'] = 'Unexpected logger serial header'
        return msg
    msg['logger_serial'] = frame[5:5+serial_len].decode('ascii', 'replace')
    cmdpos = 5 + serial_len
    cmd = frame[cmdpos:cmdpos+2]
    msg['opcode'] = cmd.hex()
    body = frame[cmdpos+2:]
    if direction == 'to_cloud' and cmd == b'\x91\x00':
        msg['kind'] = 'login_request'
        msg['detail'] = 'Startup login; plaintext credentials deliberately REDACTED'
        return msg
    if direction == 'from_cloud' and cmd == b'\x91\x00':
        msg['kind'] = 'login_reply'
        msg['status_hex'] = body.hex()
        msg['detail'] = 'Login reply; status semantics unverified'
        return msg
    if cmd == b'\x91\x22':
        msg['kind'] = 'time_sync_reply' if direction == 'from_cloud' else 'time_sync_request'
        if len(body) == 8:
            stamp = int.from_bytes(body, 'big') / 1000
            try:
                msg['detail'] = 'Server epoch milliseconds: ' + dt.datetime.fromtimestamp(stamp, UTC).isoformat()
            except (ValueError, OverflowError, OSError):
                msg['detail'] = 'Server timestamp out of range'
        else:
            msg['detail'] = 'Time sync exchange'
        return msg
    if direction == 'from_cloud' and cmd[0] == 0x99:
        msg['kind'] = 'telemetry_ack'
        msg['status_hex'] = body.hex()
        msg['detail'] = f'Ack for operation 0x{cmd[1]:02X}; meaning of status not formally verified'
        return msg
    if direction == 'from_cloud' and cmd == b'\x00\x77':
        msg['kind'] = 'server_command_77'
        msg['detail'] = 'Server-issued command, undetermined meaning'
        return msg
    if direction == 'to_cloud' and cmd == b'\x91\x87':
        msg['kind'] = 'command_response_87'
        msg['status_hex'] = body[-1:].hex()
        msg['detail'] = 'Logger response to server command; trailing status meaning unknown'
        return msg
    if direction == 'to_cloud' and cmd in (b'\x91\x04', b'\x91\x71'):
        # Header: 4-byte length, 1+16-byte logger ID, 2-byte command,
        # 4-byte measurement code, 1-byte name length, N-byte name,
        # 12-byte metadata, 1-byte field count, TLVs.
        npos = cmdpos + 2 + 4
        if npos >= len(frame):
            msg['detail'] = 'Truncated telemetry header'
            return msg
        name_length = frame[npos]
        namestart = npos + 1
        namend = namestart + name_length
        count_pos = namend + 12
        if count_pos >= len(frame):
            msg['detail'] = 'Truncated measurement header'
            return msg
        reported_name = frame[namestart:namend].decode('ascii', 'replace')
        count = frame[count_pos]
        try:
            fields = read_fields(frame, count_pos + 1, count)
        except ValueError as exc:
            msg['kind'] = 'invalid_telemetry'
            msg['detail'] = str(exc)
            return msg
        msg['fields'] = fields
        if cmd == b'\x91\x71':
            msg['kind'] = 'logger_info'
            msg['detail'] = f'Logger configuration: {count} fields'
        else:
            code = frame[cmdpos+2:npos].hex()
            if reported_name.endswith('-BMS'):
                msg['kind'] = 'bms_summary'
            else:
                msg['kind'] = 'module'
                values = {f['id']: f['value'] for f in fields}
                msg['module_serial'] = str(values.get(10000, reported_name))
            msg['detail'] = f'Measurement 0x{code}, {count} fields; ID {reported_name}'
        return msg
    msg['detail'] = 'Unrecognised opcode; payload omitted to avoid leaking secrets'
    return msg


def safe_url(url):
    """Preserve useful OTA metadata without including future auth tokens."""
    parts = urlsplit(url)
    safe = [(k, v if k.lower() in ('bundle', 'version') else '[redacted]')
            for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe), ''))


def decode_chunked(data):
    out = bytearray()
    pos = 0
    while True:
        eol = data.find(b'\r\n', pos)
        if eol < 0:
            return bytes(out)
        try:
            size = int(data[pos:eol].split(b';', 1)[0], 16)
        except ValueError:
            return bytes(out)
        pos = eol + 2
        if size == 0 or len(data) < pos + size:
            return bytes(out)
        out.extend(data[pos:pos+size])
        pos += size + 2


def http_events(data, time_utc, direction, session, src, dst):
    """Decode HTTP version check (including chunked JSON responses)."""
    if not (data.startswith(b'GET ') or data.startswith(b'POST ') or data.startswith(b'HTTP/')):
        return []
    idx = data.find(b'\r\n\r\n')
    if idx < 0:
        return []
    lines = data[:idx].decode('iso-8859-1', 'replace').split('\r\n')
    headers = {}
    for line in lines[1:]:
        if ':' in line:
            k, v = line.split(':', 1)
            headers[k.lower()] = v.strip()
    body = data[idx+4:]
    msg = {
        'time_utc': time_utc, 'session_id': session, 'source': src,
        'destination': dst, 'direction': direction, 'protocol': 'http',
        'bytes': len(data), 'kind': 'http_request' if direction == 'to_cloud' else 'http_response',
        'opcode': '', 'logger_serial': '', 'module_serial': '', 'status_hex': '',
        'fields': [], 'detail': '',
    }
    if direction == 'to_cloud':
        tokens = lines[0].split(' ')
        if len(tokens) >= 2:
            url = 'http://' + headers.get('host', dst) + tokens[1]
            msg['method'] = tokens[0]
            msg['url'] = safe_url(url)
            msg['detail'] = f'{tokens[0]} {msg["url"]}'
    else:
        parts = lines[0].split(' ', 2)
        if len(parts) >= 2:
            try:
                msg['http_status'] = int(parts[1])
            except ValueError:
                pass
        if headers.get('transfer-encoding', '').lower() == 'chunked':
            body = decode_chunked(body)
        if 'json' in headers.get('content-type', '').lower():
            try:
                obj = json.loads(body)
                # Deliberately allowlist safe diagnostic fields only
                if isinstance(obj, dict):
                    msg['response_message'] = str(obj.get('msg', ''))
                    msg['is_error'] = obj.get('isError')
                    msg['detail'] = f'HTTP {msg.get("http_status", "?")}; isError={obj.get("isError")}; msg={obj.get("msg")}'
            except (ValueError, UnicodeDecodeError):
                pass
        if not msg['detail']:
            msg['detail'] = f'HTTP {msg.get("http_status", "?")}'
    return [msg]


def extract_events(pcap_path):
    events = []
    warnings = []
    for session in session_groups(parse_pcap(pcap_path)):
        for (src, sport, dst, dport), packets in session['flows'].items():
            data, intervals, problems = tcp_stream(packets)
            warnings += [f'Session {session["id"]} {src}:{sport} -> {dst}:{dport}: {x}' for x in problems]
            if not data:
                continue
            direction = 'to_cloud' if dport in (5005, 9002, 80, 8080) else 'from_cloud'
            if sport == 5005 or dport == 5005:
                for frame, when, problem in split_frames(data, intervals):
                    if problem:
                        warnings.append(f'Session {session["id"]} {src}:{sport}: {problem}')
                        continue
                    events.append(decoded_frame(frame, when, direction, session['id'], src, dst))
            elif data.startswith((b'GET ', b'POST ', b'HTTP/')):
                events.extend(http_events(data, intervals[0][2].isoformat(), direction,
                                          session['id'], src, dst))
    events.sort(key=lambda e: (e['time_utc'] or '', e['session_id']))
    return events, warnings


def report(pcap_path, outdir, tz=None):
    events, warnings = extract_events(pcap_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if tz:
        zone = ZoneInfo(tz)
        for m in events:
            m['time_local'] = dt.datetime.fromisoformat(m['time_utc']).astimezone(zone).isoformat() if m['time_utc'] else ''

    with (outdir / 'dyness_events.csv').open('w', newline='', encoding='utf-8') as fp:
        cols = ['time_utc', 'time_local', 'session_id', 'source', 'destination',
                'direction', 'protocol', 'kind', 'opcode', 'logger_serial',
                'module_serial', 'bytes', 'status_hex', 'http_status', 'is_error', 'detail']
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for m in events:
            w.writerow(m)

    with (outdir / 'dyness_fields.csv').open('w', newline='', encoding='utf-8') as fp:
        cols = ['time_utc', 'kind', 'logger_serial', 'module_serial',
                'field_id', 'field_label', 'type', 'value', 'raw_hex']
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for m in events:
            for f in m['fields']:
                v = round(f['value'], 6) if isinstance(f['value'], float) else f['value']
                label_map = (SUMMARY_FIELD_LABELS if m['kind'] == 'bms_summary' else
                             MODULE_FIELD_LABELS if m['kind'] == 'module' else {})
                w.writerow(dict(time_utc=m['time_utc'], kind=m['kind'],
                                logger_serial=m['logger_serial'], module_serial=m['module_serial'],
                                field_id=f['id'], field_label=label_map.get(f['id'], ''),
                                type=f['type'], value=v, raw_hex=f['raw_hex']))

    with (outdir / 'dyness_cells.csv').open('w', newline='', encoding='utf-8') as fp:
        cols = ['time_utc', 'module_serial', 'pack_voltage_V', 'module_current_A',
                'temperature_1_C', 'temperature_2_C', 'temperature_3_C',
                'voltage_min_V', 'voltage_max_V', 'spread_mV', 'cell_sum_V',
                'cycle_count', 'bms_board_temp_C', 'cell_temp_1_C', 'cell_temp_2_C',
                'raw_field_13900', 'raw_field_17700', 'raw_field_17800',
                'remaining_capacity_Ah_inferred', 'full_capacity_Ah_inferred']
        cols += [f'cell_{i:02d}_V' for i in range(1, 17)]
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for m in events:
            if m['kind'] != 'module':
                continue
            d = {f['id']: f['value'] for f in m['fields']}
            voltages = [d.get(10300 + 100 * i) for i in range(16)]
            valid = [v for v in voltages if isinstance(v, (int, float))]
            cell_row = {f'cell_{i+1:02d}_V': round(v, 3) if v is not None else ''
                        for i, v in enumerate(voltages)}
            row = dict(time_utc=m['time_utc'], module_serial=m['module_serial'],
                       pack_voltage_V=round(d[13500], 3) if 13500 in d else '',
                       module_current_A=round(d[13400], 3) if 13400 in d else '',
                       temperature_1_C=round(d[12400], 2) if 12400 in d else '',
                       temperature_2_C=round(d[12500], 2) if 12500 in d else '',
                       temperature_3_C=round(d[12600], 2) if 12600 in d else '',
                       voltage_min_V=round(min(valid), 3) if valid else '',
                       voltage_max_V=round(max(valid), 3) if valid else '',
                       spread_mV=round((max(valid)-min(valid))*1000) if valid else '',
                       cell_sum_V=round(sum(valid), 3) if valid else '',
                       cycle_count=d.get(13900, ''),
                       bms_board_temp_C=round(d[12400], 2) if 12400 in d else '',
                       cell_temp_1_C=round(d[12500], 2) if 12500 in d else '',
                       cell_temp_2_C=round(d[12600], 2) if 12600 in d else '',
                       raw_field_13900=d.get(13900, ''), raw_field_17700=d.get(17700, ''),
                       raw_field_17800=d.get(17800, ''),
                       remaining_capacity_Ah_inferred=d.get(14000, ''),
                       full_capacity_Ah_inferred=d.get(14100, ''))
            row.update(cell_row)
            w.writerow(row)

    # Time-series exports: keep signed currents and raw flags, never silently
    # merge duplicate BMS reports or infer physical enclosure membership.
    for kind, filename, ids in (
        ('bms_summary', 'dyness_bank_timeline.csv',
         [600,700,800,1200,1300,1500,3200,3300,3400,3500,3600,3700,3800,3900,4000]),
        ('module', 'dyness_board_timeline.csv',
         [13400,13500,13900,14000,14100,17400,17500,17600,17700,17800,17900,18000,19700]),
    ):
        columns = ['time_utc', 'time_local', 'module_serial'] + [str(i) for i in ids]
        with (outdir / filename).open('w', newline='', encoding='utf-8') as fp:
            writer = csv.DictWriter(fp, fieldnames=columns)
            writer.writeheader()
            for event in events:
                if event['kind'] != kind:
                    continue
                values = {str(f['id']): f['value'] for f in event['fields']}
                writer.writerow({'time_utc': event['time_utc'],
                                 'time_local': event.get('time_local', ''),
                                 'module_serial': event['module_serial'],
                                 **{str(i): values.get(str(i), '') for i in ids}})

    with (outdir / 'dyness_decoded.json').open('w', encoding='utf-8') as fp:
        json.dump(events, fp, ensure_ascii=False, indent=2)

    counts = collections.Counter(m['kind'] for m in events)
    print(f'{Path(pcap_path).name}: {len(events)} messages across '
          f'{len({m["session_id"] for m in events})} TCP sessions')
    for name, count in sorted(counts.items()):
        print(f'  {name:22s} {count}')
    for m in events:
        if m['kind'] in ('login_request', 'login_reply', 'server_greeting',
                         'time_sync_request', 'time_sync_reply', 'http_request', 'http_response'):
            print(f'  {m.get("time_local") or m["time_utc"]}: {m["kind"]}: {m["detail"]}')
    for msg in warnings:
        print('WARNING:', msg)
    print('Exported', ', '.join(str(outdir / n) for n in
          ('dyness_events.csv', 'dyness_fields.csv', 'dyness_cells.csv', 'dyness_bank_timeline.csv', 'dyness_board_timeline.csv', 'dyness_decoded.json')))
    return events, warnings


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pcap', help='Classic .pcap capture file (Ethernet or Linux cooked)')
    parser.add_argument('--outdir', default='.', help='Output directory (default: current directory)')
    parser.add_argument('--tz', help='Optional IANA timezone for local event timestamps (e.g. Australia/Melbourne)')
    opts = parser.parse_args()
    report(opts.pcap, opts.outdir, tz=opts.tz)
