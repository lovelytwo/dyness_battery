"""protocol.py and reverse-engineering/dyness_decode.py must decode fields identically."""
import importlib.util
import sys
from pathlib import Path

import pytest

from dyness_battery.local import protocol as p
from frames import BOARDS, bank_frame, board_frame, config_frame

REVERSE_ENGINEERING = Path(__file__).resolve().parents[1] / "reverse-engineering"
CAPTURES = REVERSE_ENGINEERING / "captures"


def load_reference():
    if sys.version_info < (3, 9):
        pytest.skip("reference decoder needs zoneinfo")
    spec = importlib.util.spec_from_file_location("dyness_decode", REVERSE_ENGINEERING / "dyness_decode.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(ref, frame):
    body_start = len(frame.raw) - len(frame.body)
    upload = p.parse_upload(frame)
    name_end = 5 + frame.body[4]
    start = body_start + name_end + 12 + 1
    count = frame.body[name_end + 12]
    expected = ref.read_fields(frame.raw, start, count)
    assert [(f["id"], f["type"], f["value"], f["raw_hex"]) for f in expected] == [
        (f.id, f.type, f.value, f.raw.hex()) for f in upload.fields
    ]


@pytest.mark.parametrize("raw", [config_frame(), bank_frame(), board_frame(BOARDS[0])])
def test_fixture_parity(raw):
    compare(load_reference(), p.FrameBuffer().feed(raw)[0])


@pytest.mark.skipif(not (CAPTURES / "dyness.pcap").exists(), reason="private captures not present")
def test_capture_parity():
    ref = load_reference()
    checked = 0
    for name in ("dyness.pcap", "sunday.pcap", "sunday-night.pcap"):
        path = CAPTURES / name
        if not path.exists():
            continue
        for session in ref.session_groups(ref.parse_pcap(path)):
            for (src, sport, dst, dport), packets in session["flows"].items():
                if dport != 5005:
                    continue
                data, _, _ = ref.tcp_stream(packets)
                for frame in p.FrameBuffer().feed(data):
                    if frame.opcode in (p.OP_UPLOAD, p.OP_CONFIG):
                        compare(ref, frame)
                        checked += 1
    assert checked > 0
