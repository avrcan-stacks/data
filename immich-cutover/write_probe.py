"""Write-activity probe of a PostgreSQL database (phase 7B): proves, or fails to prove, that nothing was written between two moments.

  python3 -I write_probe.py capture --container C [--db immich] --out FILE
  python3 -I write_probe.py check   --before FILE --after FILE [--allow t1,t2]  -> exit 0 only if every check is PASS; UNKNOWN counts as not proven (exit 4)

What is compared (cumulative statistics + sequences, all read in a READ ONLY transaction; no row content is read):
  C1 postmaster start time unchanged (no restart/crash: statistics could have been reset or lost)
  C2 pg_stat_database.stats_reset unchanged
  C3 same set of tables
  C4 n_tup_ins / n_tup_upd / n_tup_del of every table outside --allow unchanged (an INSERT that was ROLLED BACK still counts)
  C5 every sequence last_value unchanged (nextval() consumed by a failed insert is visible here)
A missing/unreadable file or missing field is UNKNOWN => "not proven" => automatic rollback stays forbidden.
"""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cutlib import *

ALLOW_DEFAULT = 'system_metadata,version_history,plugin,plugin_method'


def capture(container, db, out):
    sql = """SELECT json_build_object(
      'postmaster_start', (SELECT pg_postmaster_start_time()::text),
      'stats_reset', (SELECT COALESCE(stats_reset::text,'never') FROM pg_stat_database WHERE datname=current_database()),
      'tables', (SELECT COALESCE(json_object_agg(relname, json_build_array(n_tup_ins, n_tup_upd, n_tup_del)),'{}') FROM pg_stat_user_tables WHERE schemaname='public'),
      'sequences', (SELECT COALESCE(json_object_agg(sequencename, last_value),'{}') FROM pg_sequences WHERE schemaname='public'));"""
    r = pj(container, sql, db=db)
    Path(out).write_text(json.dumps(r, sort_keys=True, indent=1)); os.chmod(out, 0o600)
    print('write probe captured: %d tables, %d sequences' % (len(r['tables']), len(r['sequences'])))


def check(before, after, allow):
    items = []
    def add(i, desc, status, detail=''): items.append({'id': i, 'desc': desc, 'status': status, 'detail': detail})
    try:
        b, a = json.loads(Path(before).read_text()), json.loads(Path(after).read_text())
        for k in ('postmaster_start', 'stats_reset', 'tables', 'sequences'):
            assert k in b and k in a, 'missing field ' + k
        assert b['postmaster_start'] and a['postmaster_start'] and b['tables'] and a['tables'], 'empty probe'
    except Exception as e:
        add('C0', 'both probes readable and complete', 'UNKNOWN', type(e).__name__ + ' ' + str(e)[:100]); return finish(items)
    add('C0', 'both probes readable and complete', 'PASS')
    add('C1', 'postmaster not restarted between the probes', 'PASS' if b['postmaster_start'] == a['postmaster_start'] else 'FAIL', '%s -> %s' % (b['postmaster_start'], a['postmaster_start']))
    add('C2', 'statistics not reset between the probes', 'PASS' if b['stats_reset'] == a['stats_reset'] else 'FAIL', '%s -> %s' % (b['stats_reset'], a['stats_reset']))
    add('C3', 'same set of tables', 'PASS' if set(b['tables']) == set(a['tables']) else 'FAIL', sorted(set(b['tables']) ^ set(a['tables']))[:10])
    changed = sorted(t for t in set(b['tables']) & set(a['tables']) if b['tables'][t] != a['tables'][t] and t not in allow)
    add('C4', 'no insert/update/delete counted on any table outside the allow-list (%s)' % ','.join(sorted(allow)), 'PASS' if not changed else 'FAIL', changed[:12])
    seq = sorted(s for s in set(b['sequences']) | set(a['sequences']) if b['sequences'].get(s) != a['sequences'].get(s))
    add('C5', 'no sequence value moved (nextval consumed by a failed insert would show here)', 'PASS' if not seq else 'FAIL', seq[:12])
    return finish(items)


def finish(items):
    for i in items: print('%-7s %-3s %s%s' % (i['status'], i['id'], i['desc'], (' | ' + str(i['detail'])) if i['detail'] != '' else ''))
    st = 'FAIL' if any(i['status'] == 'FAIL' for i in items) else ('UNKNOWN' if any(i['status'] == 'UNKNOWN' for i in items) else 'PASS')
    print('PROBE RESULT: ' + st)
    return {'status': st, 'items': items}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); s = p.add_subparsers(dest='cmd', required=True)
    c = s.add_parser('capture'); c.add_argument('--container', required=True); c.add_argument('--db', default=DB); c.add_argument('--out', required=True)
    k = s.add_parser('check'); k.add_argument('--before', required=True); k.add_argument('--after', required=True); k.add_argument('--allow', default=ALLOW_DEFAULT); k.add_argument('--report')
    a = p.parse_args()
    if a.cmd == 'capture':
        if a.container not in ALLOWED_DB_CONTAINERS: sys.exit('refusing container ' + a.container)
        capture(a.container, a.db, a.out)
    else:
        r = check(a.before, a.after, set(x for x in a.allow.split(',') if x))
        if a.report: Path(a.report).write_text(json.dumps(r, indent=1)); os.chmod(a.report, 0o600)
        sys.exit(0 if r['status'] == 'PASS' else 4)
