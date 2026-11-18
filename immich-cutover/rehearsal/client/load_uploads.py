"""Rehearsal load generator: logs in as the given user and uploads N uniquely-checksummed copies of the SYNTHETIC images, so that Immich queues
have real work while the cutover scripts pause/drain them. Stdlib only; prints counts only."""
import hashlib, json, os, sys, urllib.request, uuid, random, time
BASE = os.environ.get("IMMICH_BASE_URL", "http://server:2283") + "/api"
email, pw, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
def call(m, p, body=None, token=None, raw=None, hdr=None):
    h = dict(hdr or {}); data = raw
    if body is not None: data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
    if token: h["Authorization"] = "Bearer " + token
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + p, data=data, method=m, headers=h), timeout=120) as r: return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, None
s, r = call("POST", "/auth/login", {"email": email, "password": pw}); tok = r["accessToken"]
man = [m for m in json.load(open("/synthetic/manifest.json"))["files"] if m["file"].endswith(".jpg")]
ok = 0
for i in range(n):
    m = man[i % len(man)]; content = open("/synthetic/" + m["file"], "rb").read() + (b"\xff\xfe" + hashlib.sha256(b"rehearsal%d-%f" % (i, time.time())).digest())   # unique checksum, still a valid JPEG
    b = uuid.uuid4().hex; ts = "2026-10-%02dT10:00:00.000Z" % (1 + i % 27)
    fields = {"deviceAssetId": "rehearsal-%d-%s" % (i, b[:6]), "deviceId": "cutover-rehearsal", "fileCreatedAt": ts, "fileModifiedAt": ts}
    body = b"".join([f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()] +
                    [f'--{b}\r\nContent-Disposition: form-data; name="assetData"; filename="r{i}.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode(), content, f"\r\n--{b}--\r\n".encode()])
    s, r = call("POST", "/assets", raw=body, token=tok, hdr={"Content-Type": "multipart/form-data; boundary=" + b}); ok += s in (200, 201) and r and r.get("status") == "created"
print(json.dumps({"uploaded": ok, "requested": n}))
sys.exit(0 if ok == n else 1)
