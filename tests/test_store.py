from dyness_battery.local import protocol as p
from dyness_battery.local.store import LocalStore
from frames import BOARDS, LOGGER_SN, TS_MS, bank_frame, board_frame, config_frame

T0 = TS_MS / 1000


def feed(store, raw, received):
    events = []
    for frame in p.FrameBuffer().feed(raw):
        events += store.ingest(frame.serial, p.parse_upload(frame), received)
    return events


def test_config_frame_sets_logger_diagnostics_only():
    store = LocalStore()
    assert feed(store, config_frame(interval=120), T0) == []
    assert store.logger_serial == LOGGER_SN
    assert store.interval_s == 120 and store.timeout_s == 240
    assert store.logger_points[601000] == "LOGGER-FW-1"
    assert store.bank is None and store.last_upload is None


def test_cycle_completes_at_expected_board_count_with_duplicate():
    store = LocalStore()
    feed(store, config_frame(), T0)
    assert feed(store, bank_frame(), T0) == []
    events = feed(store, board_frame(BOARDS[0]), T0)
    events += feed(store, board_frame(BOARDS[0], voltage=60.0), T0)
    events += feed(store, board_frame(BOARDS[1]), T0)
    assert [e["event"] for e in events] == ["duplicate_board"]
    events = feed(store, board_frame(BOARDS[2]), T0 + 1)
    assert events == [{
        "event": "cycle_complete", "boards": list(BOARDS),
        "duplicates": [BOARDS[0]], "expected_boards": 3,
    }]
    assert store.boards[BOARDS[0]].points[13500] == 60.0
    assert store.cycles_completed == 1


def test_shortfall_recorded_when_next_bank_arrives():
    store = LocalStore()
    feed(store, bank_frame(), T0)
    feed(store, board_frame(BOARDS[0]), T0)
    events = feed(store, bank_frame(ts_ms=TS_MS + 300_000), T0 + 300)
    assert events[0]["event"] == "cycle_complete" and events[0]["shortfall"] == 2
    assert store.finish_cycle() == [{
        "event": "cycle_complete", "boards": [], "duplicates": [],
        "expected_boards": 3, "shortfall": 3,
    }]
    assert store.finish_cycle() == []
    assert store.boards[BOARDS[0]].received == T0


def test_freshness_uses_twice_the_interval():
    store = LocalStore()
    assert not store.is_fresh(T0)
    feed(store, bank_frame(), T0)
    assert store.timeout_s == 600
    assert store.is_fresh(T0 + 600) and not store.is_fresh(T0 + 601)
    feed(store, config_frame(interval=60), T0)
    assert not store.is_fresh(T0 + 121)


def test_create_time_tolerance():
    store = LocalStore()
    feed(store, bank_frame(), T0 + 299)
    assert store.create_time() == {"time": T0, "source": "metadata", "offset_s": -299.0}
    feed(store, bank_frame(), T0 + 7200)
    assert store.create_time() == {"time": T0 + 7200, "source": "received", "offset_s": -7200.0}


def test_bits_expanded_on_ingest():
    store = LocalStore()
    feed(store, bank_frame(status=128), T0)
    assert store.bank.points[3208] == 1 and store.bank.points[3201] == 0
