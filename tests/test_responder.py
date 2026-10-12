import asyncio

from dyness_battery.local import protocol as p
from dyness_battery.local import responder as r
from dyness_battery.local.store import LocalStore
from frames import BANK_SN, BOARDS, LOGGER_SN, TS_MS, bank_frame, board_frame, config_frame

T0 = TS_MS / 1000


def make_store(received=T0):
    store = LocalStore()
    for raw in [config_frame(), bank_frame()] + [board_frame(sn) for sn in BOARDS]:
        frame = p.FrameBuffer().feed(raw)[0]
        store.ingest(frame.serial, p.parse_upload(frame), received)
    return store


def local(store, path, body=None, now=T0 + 5, capacity=None, n=3):
    return r.local_response(
        store, path, body or {}, now=now, device_model="POWERBOX-PRO",
        capacity_total=capacity, n_modules=n,
    )


def as_dict(result):
    return {i["pointId"]: i["pointValue"] for i in result["data"]}


def test_format_value_matches_cloud_style():
    assert r.format_value(100) == "100"
    assert r.format_value(53.040000915527344) == "53.04"
    assert r.format_value(18.0) == "18.0"
    assert r.format_value("Battery-L") == "Battery-L"
    assert r.format_value(None) == ""


def test_storage_list_and_detail():
    store = make_store()
    device = local(store, r.PATH_STORAGE_LIST)["data"]["list"][0]
    assert device["deviceSn"] == BANK_SN and device["collectorSn"] == LOGGER_SN
    assert device["deviceModelName"] == "POWERBOX-PRO"
    assert device["deviceCommunicationStatus"] == "Online"
    assert device["firmwareVersion"] == "24.9-26.9.1"
    assert local(store, r.PATH_STORAGE_DETAIL, now=T0 + 601)["data"]["deviceCommunicationStatus"] == "Offline"
    assert local(LocalStore(), r.PATH_STORAGE_LIST)["data"]["list"] == []


def test_bank_realtime_shape():
    result = local(make_store(), r.PATH_REALTIME, {"deviceSn": BANK_SN})
    assert result["code"] == 200
    ids = [i["pointId"] for i in result["data"]]
    assert ids[:3] == ["T", "SUB", "TIME"]
    pts = as_dict(result)
    assert pts["T"] == "2026-10-10 04:36:10"
    assert pts["SUB"] == ",".join(BOARDS)
    assert pts["TIME"].count(",") == 2
    assert pts["600"] == "53.0" and pts["700"] == "-17.6" and pts["800"] == "95"
    assert pts["3200"] == "128" and pts["3208"] == "1"


def test_board_realtime_shape():
    pts = as_dict(local(make_store(), r.PATH_REALTIME, {"deviceSn": BOARDS[1]}))
    assert pts["10000"] == BOARDS[1] and pts["13500"] == "53.1" and pts["14000"] == "200.0"
    assert "SUB" not in pts


def test_power_data_and_station_capacity():
    store = make_store()
    data = local(store, r.PATH_POWER)["data"]
    assert data == {
        "createTime": "2026-10-10 04:36:10", "soc": "95",
        "realTimeCurrent": "-17.6", "realTimePower": "-932.8",
    }
    assert local(store, r.PATH_STATION)["data"] == {}
    assert local(store, r.PATH_STATION, capacity=15.0, n=3)["data"] == {"batteryCapacity": "5.0"}


def test_missing_data_and_writes():
    empty = LocalStore()
    assert local(empty, r.PATH_REALTIME, {"deviceSn": BANK_SN})["code"] == "404"
    assert local(empty, r.PATH_POWER)["code"] == "404"
    assert local(empty, r.PATH_RUNNING)["data"] == {}
    assert local(empty, "/v2/SetBaseSetting")["code"] == "403"
    assert local(empty, r.PATH_BIND)["code"] == 200


def cloud_bank(t="2026-10-10 04:30:00", sub=BOARDS[:2], soc="90"):
    return {"code": 200, "data": [
        {"flag": False, "pointId": "T", "pointValue": t},
        {"flag": False, "pointId": "SUB", "pointValue": ",".join(sub)},
        {"flag": False, "pointId": "TIME", "pointValue": ",".join([t] * len(sub))},
        {"flag": False, "pointId": "800", "pointValue": soc},
        {"flag": False, "pointId": "7100", "pointValue": "123.4"},
    ]}


def test_merge_bank_prefers_fresh_local_and_unions_sub():
    store = make_store()
    merged, info = r.merge_bank(store, cloud_bank(), T0 + 10)
    pts = as_dict(merged)
    assert pts["800"] == "95"
    assert pts["7100"] == "123.4"
    assert pts["SUB"].split(",") == list(BOARDS)
    assert pts["600"] == "53.0"
    assert info["used"]["800"] == "local" and info["used"]["7100"] == "cloud"


def test_merge_bank_uses_cloud_when_local_stale():
    store = make_store()
    cloud = cloud_bank()
    merged, info = r.merge_bank(store, cloud, T0 + 601)
    assert merged is cloud and info["used"] == "cloud"


def test_board_choice_rule():
    store = make_store()
    sn = BOARDS[0]
    assert r.board_choice(store, sn, T0 + 9999, T0 + 10) == "local"
    assert r.board_choice(store, sn, T0 + 700, T0 + 700) == "cloud"
    assert r.board_choice(store, sn, T0 - 100, T0 + 700) == "local"
    assert r.board_choice(store, sn, None, T0 + 700) == "local"
    assert r.board_choice(store, "0999999999999999", None, T0) == "cloud"


def test_merge_board_overlays_cloud_omission():
    store = make_store()
    merged, info = r.merge_board(store, BOARDS[2], {"code": "500", "data": None}, T0 + 10)
    assert merged["code"] == 200 and info["used"] == "local"
    assert as_dict(merged)["13500"] == "53.1"


def test_merge_power():
    store = make_store()
    cloud = {"code": 200, "data": [{"soc": "90", "realTimePower": "10", "extra": "x"}]}
    merged, used = r.merge_power(store, cloud, T0 + 10)
    assert used == "local"
    assert merged["data"]["soc"] == "95" and merged["data"]["extra"] == "x"
    assert r.merge_power(store, cloud, T0 + 601) == (cloud, "cloud")


def test_responder_local_and_cloud_passthru_paths():
    store = make_store()

    async def run():
        local_only = r.LocalResponder(
            store, device_model="POWERBOX-PRO", bank_sn=lambda: "entry-id",
            capacity_total=lambda: None, n_modules=lambda: 3, clock=lambda: T0 + 5,
        )
        assert (await local_only(None, r.PATH_REALTIME, {"deviceSn": "entry-id"}))["code"] == 200

        calls = []

        async def cloud_call(session, path, body, *args, **kwargs):
            calls.append((path, kwargs))
            return cloud_bank() if path == r.PATH_REALTIME else {"code": 200, "data": {"x": 1}}

        passthru = r.LocalResponder(
            store, device_model="", bank_sn=lambda: BANK_SN,
            capacity_total=lambda: None, n_modules=lambda: 3,
            cloud_call=cloud_call, clock=lambda: T0 + 5,
        )
        merged = await passthru(None, r.PATH_REALTIME, {"deviceSn": BANK_SN}, max_retries=0)
        assert as_dict(merged)["800"] == "95"
        assert calls == [(r.PATH_REALTIME, {"max_retries": 0})]
        assert (await passthru(None, r.PATH_STATION, {}))["data"] == {"x": 1}

    asyncio.run(run())
