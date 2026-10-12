import pytest

from dyness_battery.local import protocol as p
from frames import BANK_SN, LOGGER_SN, TS_MS, bank_frame, board_frame, config_frame, tunnel


def test_frame_buffer_reassembles_split_and_joined_frames():
    data = bank_frame() + board_frame("0100000000000001")
    buf = p.FrameBuffer()
    frames = []
    for i in range(0, len(data), 7):
        frames += buf.feed(data[i:i + 7])
    assert [f.opcode for f in frames] == [p.OP_UPLOAD, p.OP_UPLOAD]
    assert frames[0].serial == LOGGER_SN
    assert frames[0].raw + frames[1].raw == data
    assert buf.pending == 0


@pytest.mark.parametrize("prefix", [b"\x00\x00\x00\x02", b"\x7f\xff\xff\xff", b"GET "])
def test_frame_buffer_rejects_bad_length(prefix):
    with pytest.raises(p.FrameError):
        p.FrameBuffer().feed(prefix + b"\x00" * 8)


def test_frame_buffer_rejects_bad_serial_header():
    raw = (5).to_bytes(4, "big") + b"\x30" + b"abcd"
    with pytest.raises(p.FrameError):
        p.FrameBuffer().feed(raw)


def test_parse_upload_typed_fields_and_metadata():
    upload = p.parse_upload(p.FrameBuffer().feed(bank_frame())[0])
    assert upload.measurement_code == 14002
    assert upload.name == BANK_SN and upload.is_bank
    assert upload.timestamp_ms == TS_MS
    pts = upload.points()
    assert pts[300] == "24.9-26.9.1"
    assert pts[400] == 3 and pts[800] == 95
    assert pts[600] == pytest.approx(53.0)
    assert pts[700] == pytest.approx(-17.6, abs=1e-5)
    assert [f.type for f in upload.fields] == ["T", "S", "F", "F", "S", "S", "F", "F", "S", "S"]


def test_parse_upload_rejects_trailing_bytes_and_unknown_type():
    frame = p.FrameBuffer().feed(config_frame())[0]
    with pytest.raises(p.FieldError):
        p.parse_upload(p.Frame(frame.raw, frame.serial, frame.opcode, frame.body + b"\x00"))
    bad = bytearray(frame.body)
    bad[bad.index(b"I")] = ord("X")
    with pytest.raises(p.FieldError):
        p.parse_upload(p.Frame(frame.raw, frame.serial, frame.opcode, bytes(bad)))


def test_expand_bits_adds_missing_bit_points_only():
    out = p.expand_bits({3200: 128, 4000: 64, 4007: 9})
    assert [out[3201 + n] for n in range(8)] == [0, 0, 0, 0, 0, 0, 0, 1]
    assert out[4007] == 9
    assert out[4006] == 0 and out[4008] == 0
    assert 3300 not in out and 3301 not in out


def test_crc16_xmodem_check_value():
    assert p.crc16_xmodem(b"123456789") == 0x31C3


def test_decode_clock_set_command():
    data = bytes([4, 36, 7, 11, 10, 26, 0, 1])
    out = p.decode_command(tunnel(p.COMMAND_CLOCK_SET, p.INNER_CLOCK_SET, data))
    assert out["status"] == "parsed"
    assert out["crc_ok"] is True
    assert out["clock"] == "2026-10-11T07:36:04"


def test_decode_opaque_and_bad_crc_commands():
    opaque = p.decode_command(tunnel(0x1303, b"\x0c\x01", b"\x00\x00"))
    assert opaque["status"] == "opaque" and opaque["inner_command"] == "0c01"
    bad = p.decode_command(tunnel(0x1303, b"\x0c\x01", b"\x00\x00", corrupt=True))
    assert bad["status"] == "unknown" and bad["crc_ok"] is False
    assert p.decode_command(b"\x00\x01")["status"] == "unknown"


def test_decode_command_result():
    out = p.decode_command_result(bytes.fromhex("0000130300" "01ff"))
    assert out["command_id"] == 0x1303 and out["result"] == 0xFF and out["status"] == "opaque"


def test_endpoint_reply_bytes():
    sn = LOGGER_SN.encode()
    head = bytes([len(sn)]) + sn

    def frame(op, body=b""):
        return p.FrameBuffer().feed(p.build_frame(LOGGER_SN, op, body))[0]

    assert p.endpoint_replies(frame(p.OP_CONFIG), 0) == [(20).to_bytes(4, "big") + head + b"\x99\x71\x01"]
    assert p.endpoint_replies(frame(p.OP_UPLOAD), 0) == [(20).to_bytes(4, "big") + head + b"\x99\x04\x01"]
    assert p.endpoint_replies(frame(p.OP_TIME), TS_MS) == [
        (27).to_bytes(4, "big") + head + b"\x91\x22" + TS_MS.to_bytes(8, "big")
    ]
    greeting, login_ok = p.endpoint_replies(frame(p.OP_LOGIN, b"secret"), 0)
    assert login_ok == (20).to_bytes(4, "big") + head + b"\x91\x00\x01"
    g = p.FrameBuffer().feed(greeting)[0]
    assert g.serial == "" and g.opcode == p.OP_GREETING
    assert g.body.startswith(b"This is dyness.raymon service. node id is '") and g.body.endswith(b"'")
    assert p.endpoint_replies(frame(b"\x91\x99"), 0) == []
    assert p.endpoint_replies(frame(p.OP_COMMAND_RESULT), 0) == []


def test_unparseable_upload_is_still_acked():
    raw = p.build_frame(LOGGER_SN, p.OP_UPLOAD, b"\x36\xb2\x00\x01\x05garbage")
    frame = p.FrameBuffer().feed(raw)[0]
    with pytest.raises(p.FieldError):
        p.parse_upload(frame)
    assert p.endpoint_replies(frame, 0)[0].endswith(b"\x99\x04\x01")
