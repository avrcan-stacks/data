"""Read-only catalog + content snapshot and the source->target comparison for the Immich cutover.

PREPARED IN PHASE 6, NOT EXECUTED AGAINST PRODUCTION.
  python3 -I db_snapshot.py snapshot --container postgis|immich-db --out DIR      # one READ ONLY snapshot (metadata, 72 table hashes, sequences)
  python3 -I db_snapshot.py compare  --source DIR_SRC --target DIR_DST [--report FILE]

`compare` is strict: metadata identical (PostGIS members of the source ignored; the single documented text-format exception for
asset_localDateTime_month_idx; identity sequence must be bigint on both sides), all 72 table hashes identical, extension versions
exactly the 8 retained ones on the target, sequences not lower than the source. Exit code 0 only if everything matches.
No row content is ever printed or stored: only counts and SHA-256 hashes.
"""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cutlib import *


def snapshot(container, out, db=DB):
    out = Path(out); out.mkdir(parents=True, exist_ok=False, mode=0o700)
    meta = pj(container, MANIFEST_SQL.read_text(), db=db)
    (out / 'metadata.json').write_text(json.dumps(meta, indent=1, sort_keys=True))
    tables = [r for r in meta['relations'] if r['kind'] in ('r', 'p') and r['extension'] is None]
    assert len(tables) == 72, ('expected 72 application tables', len(tables))
    hashes = {}
    for r in tables:
        order = ','.join(qid(c) for c in r['pk']) if r['pk'] else '(to_jsonb(t)::text) COLLATE "C"'
        hashes[r['name']] = stream_hash(container, 'COPY (SELECT to_jsonb(t)::text FROM public.%s t ORDER BY %s) TO STDOUT;' % (qid(r['name']), order), db=db)
    (out / 'tables.json').write_text(json.dumps(hashes, indent=1, sort_keys=True))
    seq = pj(container, "SELECT COALESCE(json_agg(s),'[]') FROM (SELECT sequencename,data_type,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY 1) s;", db=db)
    (out / 'sequences.json').write_text(json.dumps(seq, indent=1))
    for p in out.iterdir(): os.chmod(p, 0o600)
    print('snapshot ok: %d tables, %d rows' % (len(hashes), sum(v['rows'] for v in hashes.values())))


MODES = {
    # restored target (PG 16.16, PostGIS removed): PostGIS members of the source are ignored, documented index-text exception applies, exactly the 8 retained extensions
    'source-target': dict(strip=True, mask=True, ext=EXPECTED_EXT),
    # bridge copy right after restore and BEFORE `DROP EXTENSION postgis RESTRICT`: strict equality incl. PostGIS members, no exception (same 16.13 image)
    'source-bridge': dict(strip=False, mask=False, ext=dict(EXPECTED_EXT, postgis='3.6.2')),
    # bridge copy after `DROP EXTENSION postgis RESTRICT`: only PostGIS members may differ
    'source-bridge-after': dict(strip=True, mask=False, ext=EXPECTED_EXT),
}


def compare(src, dst, mode='source-target'):
    cfg = MODES[mode]
    S, D = Path(src), Path(dst)
    problems = []
    ms, md = json.loads((S / 'metadata.json').read_text()), json.loads((D / 'metadata.json').read_text())
    a = strip_postgis(ms) if cfg['strip'] else ms
    b = md
    # The database-level ACL is not part of a dump and the source is FENCED (CONNECT revoked) when it is snapshotted. It is therefore not compared here:
    # validate_target.py (V4) checks the target ACL against the ACL recorded by preflight BEFORE the fence (found by the rehearsal: fenced source != target ACL).
    for m_ in (a, b):
        if isinstance(m_.get('database'), dict): m_['database'] = {k: v for k, v in m_['database'].items() if k != 'acl'}
    if cfg['mask']: a, b = mask_idx_text(a), mask_idx_text(b)
    sections = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    if sections: problems.append(('metadata sections differ (owners, ACLs, definitions, indexes, functions, constraints ...)', sections))
    ext = {e['name']: e['version'] for e in md['extensions']}
    if ext != cfg['ext']: problems.append(('extensions differ from the expected set for mode ' + mode, ext))
    ts, td = json.loads((S / 'tables.json').read_text()), json.loads((D / 'tables.json').read_text())
    if len(ts) != 72 or set(ts) != set(td): problems.append(('table sets differ or not 72', sorted(set(ts) ^ set(td))))
    diff = sorted(k for k in ts if td.get(k) != ts[k])
    if diff: problems.append(('table content hashes differ', diff))
    ss = {x['sequencename']: x for x in json.loads((S / 'sequences.json').read_text())}
    sd = {x['sequencename']: x for x in json.loads((D / 'sequences.json').read_text())}
    low = [k for k in ss if k not in sd or (sd[k]['last_value'] is None and ss[k]['last_value'] is not None) or (sd[k]['last_value'] or 0) < (ss[k]['last_value'] or 0)]
    if low: problems.append(('sequences lower than source or missing', low))
    nb = [k for k, v in sd.items() if k == 'naturalearth_countries_tmp_id_seq1' and v['data_type'] != 'bigint']
    if nb: problems.append(('identity sequence is not bigint (run the normalisation step)', nb))
    return {'mode': mode, 'tables_compared': len(ts), 'rows': sum(v['rows'] for v in ts.values()), 'problems': [{'what': w, 'detail': d} for w, d in problems], 'status': 'FAIL' if problems else 'PASS'}


def delta(before, after, allow):
    tb, ta = json.loads((Path(before) / 'tables.json').read_text()), json.loads((Path(after) / 'tables.json').read_text())
    mb, ma = json.loads((Path(before) / 'metadata.json').read_text()), json.loads((Path(after) / 'metadata.json').read_text())
    changed = sorted(k for k in set(tb) | set(ta) if tb.get(k) != ta.get(k))
    meta = [k for k in sorted(set(mb) | set(ma)) if mb.get(k) != ma.get(k)]
    outside = [k for k in changed if k not in allow]
    return {'changed_tables': changed, 'outside_allow_list': outside, 'metadata_sections_changed': meta, 'status': 'FAIL' if (outside or meta) else 'PASS'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('snapshot'); s.add_argument('--container', required=True); s.add_argument('--db', default=DB); s.add_argument('--out', required=True)
    c = sub.add_parser('compare'); c.add_argument('--source', required=True); c.add_argument('--target', required=True); c.add_argument('--mode', choices=sorted(MODES), default='source-target'); c.add_argument('--report')
    d = sub.add_parser('delta'); d.add_argument('--before', required=True); d.add_argument('--after', required=True); d.add_argument('--allow', default='system_metadata,session,plugin,plugin_method,version_history')
    a = p.parse_args()
    if a.cmd == 'delta':
        r = delta(a.before, a.after, set(a.allow.split(','))); print(json.dumps(r, indent=1)); sys.exit(0 if r['status'] == 'PASS' else 1)
    if a.cmd == 'snapshot':
        if a.container not in ALLOWED_DB_CONTAINERS: sys.exit('refusing container %s (allowed: %s)' % (a.container, sorted(ALLOWED_DB_CONTAINERS)))
        snapshot(a.container, a.out, a.db)
    else:
        r = compare(a.source, a.target, a.mode)
        print(json.dumps(r, indent=1))
        if a.report: Path(a.report).write_text(json.dumps(r, indent=1)); os.chmod(a.report, 0o600)
        sys.exit(0 if r['status'] == 'PASS' else 1)
