import base64, hashlib, hmac, json, os, sys, time, urllib.request
from email.utils import formatdate

API_ID = os.environ["DYNESS_API_ID"]
API_SECRET = os.environ["DYNESS_API_SECRET"]
BASES = [
    "https://open-api.dyness.com",
    "https://apacopen-api.dyness.com",
]
OUT = sys.argv[1]


def call(base, path, body_dict):
    body = json.dumps(body_dict, separators=(",", ":"))
    md5 = base64.b64encode(hashlib.md5(body.encode()).digest()).decode()
    date = formatdate(usegmt=True)
    sts = f"POST\n{md5}\napplication/json\n{date}\n{path}"
    sig = base64.b64encode(hmac.new(API_SECRET.encode(), sts.encode(), "sha1").digest()).decode()
    req = urllib.request.Request(
        f"{base}/openapi/ems-device{path}",
        data=body.encode(),
        method="POST",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Content-MD5": md5,
            "Date": date,
            "Authorization": f"API {API_ID}:{sig}",
        },
    )
    time.sleep(1.5)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"code": str(e.code), "info": e.read().decode(errors="replace")}


result = {}
for base in BASES:
    lst = call(base, "/v1/device/storage/list", {})
    print(base, "storage/list ->", lst.get("code"), lst.get("info"))
    devices = ((lst.get("data") or {}).get("list")) or []
    if devices:
        break
else:
    sys.exit("no devices found in any region")

result["base"] = base
result["storage_list"] = lst
for dev in devices:
    sn, coll = dev["deviceSn"], dev.get("collectorSn")
    print("device", sn, dev.get("deviceModelName"))
    body = {"deviceSn": sn, "collectorSn": coll}
    print(" bind:", call(base, "/v1/device/bindSn", body).get("info"))
    rt = call(base, "/v1/device/realTime/data", body)
    print(" realTime:", rt.get("code"), rt.get("info"), len(rt.get("data") or []))
    result[sn] = rt
    subs = next((p["pointValue"] for p in rt.get("data") or [] if p.get("pointId") == "SUB"), "")
    for sub in filter(None, (subs or "").split(",")):
        sb = {"deviceSn": sub, "collectorSn": coll}
        print(" sub", sub, "bind:", call(base, "/v1/device/bindSn", sb).get("info"))
        srt = call(base, "/v1/device/realTime/data", sb)
        print("  realTime:", srt.get("code"), srt.get("info"), len(srt.get("data") or []))
        result[sub] = srt

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print("wrote", OUT)
