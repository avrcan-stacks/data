"""Catalog + content snapshot and strict before/after comparison for an ISOLATED test PostgreSQL container.

Plan artifact (phase 5): NOT executed yet. Derived from the validated phase 4/4B/4C harness.

  snapshot  --container NAME --db immich --out DIR            -> DIR/metadata.json, DIR/tables.json, DIR/sequences.json
  diff      --before DIR0 --after DIR1 [--allow t1,t2,...]    -> exit 0 only if metadata is identical and every
                                                                  changed table is on the allow-list

Safety: container name must start with the expected test prefix; only read-only transactions are used;
table content is streamed into SHA-256 (no row is printed or stored). Run with: python3 -I tools/compare_db.py ...
"""
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path

PREFIX = "immich-apptest-"                      # compose project prefix; production names never match
MANIFEST = Path(__file__).resolve().parent.parent / "sql" / "schema-manifest.sql"
GUC = ("SET LOCAL statement_timeout='300s'; SET LOCAL search_path=public,pg_catalog; SET LOCAL TimeZone='UTC';"
       " SET LOCAL DateStyle='ISO'; SET LOCAL extra_float_digits=3;")


def psql(container, db, query, stream=False):
    assert container.startswith(PREFIX), "refusing non-test container: " + container
    assert re.fullmatch(r"[A-Za-z0-9_]+", db)
    args = ["docker", "exec", "-i", container, "psql", "-Xq", "-U", "postgres", "-d", db, "-At", "-v", "ON_ERROR_STOP=1"]
    text = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; " + GUC + "\n" + query + "\nCOMMIT;"
    if not stream:
        p = subprocess.run(args, input=text, text=True, capture_output=True, check=True, timeout=600)
        return p.stdout.strip()
    h, rows, size = hashlib.sha256(), 0, 0
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write(text.encode()); p.stdin.close()
    for block in iter(lambda: p.stdout.read(1 << 20), b""):
        h.update(block); rows += block.count(b"\n"); size += len(block)
    if p.wait(timeout=600):
        raise RuntimeError("stream failed for " + container)
    return {"rows": rows, "sha256": h.hexdigest(), "bytes": size}


def q(name):
    return '"' + name.replace('"', '""') + '"'


def snapshot(a):
    out = Path(a.out); out.mkdir(parents=True, mode=0o700, exist_ok=False)
    meta = json.loads(psql(a.container, a.db, MANIFEST.read_text()))
    (out / "metadata.json").write_text(json.dumps(meta, indent=1, sort_keys=True))
    tables = [r for r in meta["relations"] if r["kind"] in ("r", "p") and r["extension"] is None]
    assert len(tables) == 72, ("expected 72 application tables", len(tables))
    hashes = {}
    for r in tables:
        order = ",".join(q(c) for c in r["pk"]) if r["pk"] else '(to_jsonb(t)::text) COLLATE "C"'
        hashes[r["name"]] = psql(a.container, a.db, "COPY (SELECT to_jsonb(t)::text FROM public.%s t ORDER BY %s) TO STDOUT;"
                                 % (q(r["name"]), order), stream=True)
    (out / "tables.json").write_text(json.dumps(hashes, indent=1, sort_keys=True))
    seq = json.loads(psql(a.container, a.db, "SELECT COALESCE(json_agg(s),'[]') FROM (SELECT sequencename, last_value FROM pg_sequences WHERE schemaname='public' ORDER BY 1) s;"))
    (out / "sequences.json").write_text(json.dumps(seq, indent=1))
    print("snapshot ok: %d tables, %d rows" % (len(hashes), sum(v["rows"] for v in hashes.values())))


def diff(a):
    b, c = Path(a.before), Path(a.after)
    allow = {x for x in (a.allow or "").split(",") if x}
    bad = []
    m0, m1 = json.loads((b / "metadata.json").read_text()), json.loads((c / "metadata.json").read_text())
    sections = [k for k in sorted(set(m0) | set(m1)) if m0.get(k) != m1.get(k)]
    if sections:
        bad.append(("metadata sections differ", sections))
    t0, t1 = json.loads((b / "tables.json").read_text()), json.loads((c / "tables.json").read_text())
    changed = sorted(k for k in set(t0) | set(t1) if t0.get(k) != t1.get(k))
    unexpected = [k for k in changed if k not in allow]
    if unexpected:
        bad.append(("tables changed outside allow-list", unexpected))
    s0, s1 = json.loads((b / "sequences.json").read_text()), json.loads((c / "sequences.json").read_text())
    seq = [x["sequencename"] for x in s1 if x not in s0]
    print("changed tables (allowed):", [k for k in changed if k in allow])
    print("changed sequences (informational, review manually):", seq)
    for title, items in bad:
        print("FAIL:", title, items)
    print("RESULT:", "FAIL" if bad else "PASS")
    sys.exit(1 if bad else 0)


p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd", required=True)
s = sub.add_parser("snapshot"); s.add_argument("--container", required=True); s.add_argument("--db", default="immich"); s.add_argument("--out", required=True); s.set_defaults(f=snapshot)
d = sub.add_parser("diff"); d.add_argument("--before", required=True); d.add_argument("--after", required=True); d.add_argument("--allow", default=""); d.set_defaults(f=diff)
args = p.parse_args(); args.f(args)
