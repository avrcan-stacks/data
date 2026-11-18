"""Immich API smoke test for the ISOLATED test network. Stdlib only. Plan artifact: NOT executed in phase 5.

Run inside the `client` service:  python -I /tests/smoke_test.py
Writes only counts, status codes and timings to /results/smoke.json (no names, e-mails, ids or embeddings).
Optional expectations (counts taken from the baseline DB snapshot) via EXPECT_* env variables.
"""
import json, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get("IMMICH_BASE_URL", "http://server:2283").rstrip("/") + "/api"
EMAIL, PASSWORD = os.environ.get("TEST_ADMIN_EMAIL", ""), os.environ.get("TEST_ADMIN_PASSWORD", "")
OUT = {"checks": [], "ok": True}


def call(method, path, body=None, token=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, None, (time.monotonic() - t0) * 1000


def check(name, ok, **info):
    OUT["checks"].append({"name": name, "ok": bool(ok), **info})
    OUT["ok"] = OUT["ok"] and bool(ok)
    print(("PASS " if ok else "FAIL ") + name, info, flush=True)


def expect(name, value):
    want = os.environ.get("EXPECT_" + name)
    if want is not None and want != "":
        check("expect_" + name.lower(), str(value) == want, got=value, want=int(want))


def main():
    for _ in range(60):
        try:
            if call("GET", "/server/ping", timeout=5)[0] == 200:
                break
        except Exception:
            time.sleep(2)
    else:
        check("server_ping", False)
        return
    check("server_ping", True)
    s, feat, _ = call("GET", "/server/features")
    check("features_isolated", s == 200 and feat and feat.get("configFile") is True and feat.get("oauth") is False
          and feat.get("passwordLogin") is True and feat.get("email") is False,
          smartSearch=feat and feat.get("smartSearch"), facialRecognition=feat and feat.get("facialRecognition"))
    if not EMAIL or not PASSWORD:
        check("credentials_present", False)
        return
    s, login, ms = call("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})
    token = login and login.get("accessToken")
    check("login", s in (200, 201) and bool(token), status=s, ms=round(ms, 1))
    if not token:
        return
    s, about, _ = call("GET", "/server/about", token=token)
    check("server_about_version", s == 200 and about and about.get("version") == "v3.3.5", status=s)
    s, albums, ms = call("GET", "/albums", token=token)
    check("albums_list", s == 200 and isinstance(albums, list), status=s, count=len(albums or []), ms=round(ms, 1))
    expect("ALBUMS", len(albums or []))
    if albums:
        first = max(albums, key=lambda a: a.get("assetCount", 0))
        s, detail, ms = call("GET", "/albums/" + first["id"], token=token)
        # v3.3.5: GET /albums/{id} returns metadata and assetCount only (withAssets=false); assets come from search.
        check("album_detail", s == 200 and detail is not None and detail.get("assetCount") == first.get("assetCount") and first.get("assetCount", 0) > 0,
              status=s, assetCount=detail.get("assetCount") if detail else None, ms=round(ms, 1))
        expect("ALBUM_MAX_ASSETS", first.get("assetCount"))
        s, inalb, ms = call("POST", "/search/metadata", {"albumIds": [first["id"]], "size": 20}, token=token)
        aitems = ((inalb or {}).get("assets") or {}).get("items") or []
        check("album_assets_search", s in (200, 201) and len(aitems) > 0, status=s, returned=len(aitems), ms=round(ms, 1))
    s, meta, ms = call("POST", "/search/metadata", {"size": 20, "type": "IMAGE", "order": "desc"}, token=token)
    items = ((meta or {}).get("assets") or {}).get("items") or []
    check("search_metadata", s in (200, 201) and len(items) > 0, status=s, returned=len(items), ms=round(ms, 1))
    s, smart, ms = call("POST", "/search/smart", {"query": os.environ.get("SMART_QUERY", "beach"), "size": 20},
                        token=token, timeout=180)
    sitems = ((smart or {}).get("assets") or {}).get("items") or []
    check("search_smart_ml", s in (200, 201) and len(sitems) > 0, status=s, returned=len(sitems), ms=round(ms, 1))
    s, people, ms = call("GET", "/people?size=500&withHidden=true", token=token)
    plist = (people or {}).get("people") or []
    check("people_list", s == 200 and len(plist) > 0, status=s, count=len(plist), total=(people or {}).get("total"), ms=round(ms, 1))
    expect("PEOPLE_TOTAL", (people or {}).get("total"))
    named = [p for p in plist if p.get("name")]
    if named:
        s, st, ms = call("GET", "/people/%s/statistics" % named[0]["id"], token=token)
        check("person_statistics", s == 200 and st and st.get("assets", 0) > 0, status=s, assets=st and st.get("assets"))
        s, byp, ms = call("POST", "/search/metadata", {"personIds": [named[0]["id"]], "size": 20}, token=token)
        pitems = ((byp or {}).get("assets") or {}).get("items") or []
        check("search_by_person", s in (200, 201) and len(pitems) > 0, status=s, returned=len(pitems), ms=round(ms, 1))
        if pitems:
            s, faces, _ = call("GET", "/faces?id=" + pitems[0]["id"], token=token)
            check("asset_faces", s == 200 and isinstance(faces, list) and len(faces) > 0, status=s, faces=len(faces or []))
    call("POST", "/auth/logout", token=token)


try:
    main()
except Exception as exc:  # report, never hide
    check("unexpected_exception", False, error=type(exc).__name__)
os.makedirs("/results", exist_ok=True)
json.dump(OUT, open("/results/smoke.json", "w"), indent=2)
sys.exit(0 if OUT["ok"] else 1)
