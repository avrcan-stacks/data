"""Immich API baseline / verification / queue control for the cutover. Calls go through `docker exec immich_server node` (localhost:2283),
so they work in the "dark launch" phase (Traefik route disabled) and need no extra container or host port.

PREPARED IN PHASE 6, NOT EXECUTED AGAINST PRODUCTION. Keys come from the operator's environment (never stored):
  IMMICH_ADMIN_API_KEY  (queue.read queue.update job.read job.create server.about server.statistics library.read library.statistics)
  IMMICH_USER_API_KEY   (asset.read album.read person.read server.about)  - one data-owning user

  baseline --out FILE                 GET only: statistics, libraries, queues, albums/people/search samples with latency
  verify --baseline FILE [--out F]    same reads after the cutover, compared with PROPOSED thresholds (not approved)
  queues status                       GET only
  queues pause|resume --execute       MUTATES queue state (Redis) - refuses without --execute
  queues wait-drain [--timeout S]     GET only: waits until active==0 on every queue (waiting jobs may remain queued)
  job backup-database --execute       creates the manual database backup job (POST /jobs)
"""
import argparse, hashlib, json, os, statistics, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cutlib import *

SMART_QUERIES = ['a beach at sunset', 'a group of people at a table', 'a dog in the snow', 'a document with text', 'a mountain landscape',
                 'a city street at night', 'a birthday cake', 'a car on a road', 'a child playing', 'food on a plate']
ADMIN, USER = 'IMMICH_ADMIN_API_KEY', 'IMMICH_USER_API_KEY'
UNPAUSABLE = {'backgroundTask'}      # Immich v3.3.5 answers HTTP 400 'The BackgroundTask queue cannot be paused' (verified on the rehearsal stack and in queue.service.js)


def require_keys():
    for name in (ADMIN, USER):
        if not os.environ.get(name):
            raise RuntimeError('environment variable %s is not set' % name)


def get(key, path, **kw):
    response = immich(key, 'GET', path, **kw)
    if response['status'] != 200:
        raise RuntimeError('GET %s -> %s' % (path, response['status']))
    return response


def validate_sample(sample):
    """Reject partial/empty baseline or API error objects before any PASS is possible."""
    def need(ok, label):
        if not ok: raise ValueError('invalid API evidence: ' + label)
    number = lambda x: type(x) in (int, float) and x >= 0 and __import__('math').isfinite(x)
    need(isinstance(sample, dict), 'sample object')
    need(sample.get('version') == 'v3.3.5', 'version')
    stats = sample.get('server_statistics', {})
    need(all(number(stats.get(k)) for k in ('photos', 'videos', 'usage', 'usagePhotos', 'usageVideos')), 'server statistics')
    need(isinstance(stats.get('usage_by_user'), list) and bool(stats['usage_by_user']) and
         all(isinstance(row, list) and len(row) == 3 and all(number(v) for v in row) for row in stats['usage_by_user']), 'per-user statistics')
    libs = sample.get('libraries')
    need(isinstance(libs, list) and len(libs) == 8 and all(isinstance(row, list) and len(row) == 2 and
         isinstance(row[0], str) and row[0] and number(row[1]) for row in libs), 'libraries')
    qs = sample.get('queues')
    need(isinstance(qs, dict) and len(qs) == 19, 'queue set')
    for row in qs.values():
        need(isinstance(row, dict) and type(row.get('isPaused')) is bool and
             all(type(row.get(k)) is int and row[k] >= 0 for k in ('active', 'waiting', 'delayed', 'failed', 'paused')), 'queue statistics')
    albums = sample.get('albums', {})
    need(type(albums.get('count')) is int and isinstance(albums.get('asset_counts'), list) and
         albums['count'] == len(albums['asset_counts']) and all(type(x) is int and x >= 0 for x in albums['asset_counts']), 'albums')
    need(all(type(sample.get('people', {}).get(k)) is int and sample['people'][k] >= 0 for k in ('total', 'hidden')), 'people')
    need(isinstance(sample.get('smart'), dict) and set(sample['smart']) == set(SMART_QUERIES), 'search queries')
    for row in sample['smart'].values():
        need(isinstance(row, dict) and isinstance(row.get('ids'), list) and bool(row['ids']) and
             all(isinstance(x, str) and x for x in row['ids']) and number(row.get('cold_ms')) and
             isinstance(row.get('warm_ms'), list) and len(row['warm_ms']) == 4 and all(number(x) for x in row['warm_ms']), 'search result')


def check_result(path):
    result = json.loads(Path(path).read_text())
    if not isinstance(result, dict) or result.get('name') != 'api-verify' or result.get('status') != 'PASS':
        raise ValueError('invalid API result')
    if type(result.get('fail')) is not int or result['fail'] != 0 or type(result.get('warn')) is not int or result['warn'] != 0:
        raise ValueError('API result has failures, warnings or missing counters')
    items = result.get('items')
    if not isinstance(items, list) or len(items) != 10 or {x.get('id') for x in items} != {'Q%d' % n for n in range(1, 11)} or any(x.get('status') != 'PASS' for x in items):
        raise ValueError('API result must prove Q1-Q10 PASS')
    validate_sample(result.get('sample'))



def queues():
    r = get(ADMIN, '/queues')
    if r['status'] != 200: raise RuntimeError('GET /queues -> %s' % r['status'])
    rows = r['json']
    if not isinstance(rows, list) or len(rows) != 19 or len({x['name'] for x in rows}) != 19:
        raise ValueError('invalid queue set (expected 19 distinct queues)')
    for row in rows:
        if type(row.get('isPaused')) is not bool or not all(type(row.get('statistics', {}).get(k)) is int and row['statistics'][k] >= 0 for k in ('active', 'waiting', 'delayed', 'failed', 'paused')):
            raise ValueError('invalid queue statistics')
    return {x['name']: {**{k: x['statistics'][k] for k in ('active', 'waiting', 'delayed', 'failed', 'paused')}, 'isPaused': x['isPaused']} for x in rows}


def collect():
    require_keys()
    out = {'taken_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    about = get(ADMIN, '/server/about'); out['version'] = (about['json'] or {}).get('version')
    st = get(ADMIN, '/server/statistics'); j = st['json'] or {}
    out['server_statistics'] = {k: j.get(k) for k in ('photos', 'videos', 'usage', 'usagePhotos', 'usageVideos')}
    out['server_statistics']['usage_by_user'] = sorted((u.get('photos'), u.get('videos'), u.get('usage')) for u in (j.get('usageByUser') or []))
    libs = get(ADMIN, '/libraries')['json'] or []
    out['libraries'] = sorted((l['id'][:8], (get(ADMIN, '/libraries/%s/statistics' % l['id'])['json'] or {}).get('total')) for l in libs)
    out['queues'] = queues()
    if os.environ.get(USER):
        al = get(USER, '/albums')['json'] or []
        out['albums'] = {'count': len(al), 'asset_counts': sorted(a.get('assetCount', 0) for a in al)}
        pp = get(USER, '/people?size=1&withHidden=true')['json'] or {}
        out['people'] = {'total': pp.get('total'), 'hidden': pp.get('hidden')}
        sm = {}
        for q in SMART_QUERIES:
            lat, ids = [], None
            for i in range(5):
                r = immich(USER, 'POST', '/search/smart', {'query': q, 'size': 20}); lat.append(r['ms'])
                if r['status'] != 200: raise RuntimeError('POST /search/smart -> %s' % r['status'])
                items = (((r['json'] or {}).get('assets') or {}).get('items')) or []
                if ids is None: ids = [x['id'] for x in items]; first_ms = r['ms']
            sm[q] = {'ids': ids, 'cold_ms': first_ms, 'warm_ms': sorted(lat[1:])}
        out['smart'] = sm
    out = json.loads(json.dumps(out))
    validate_sample(out)
    return out #      # normalise tuples/lists so that a re-read baseline compares equal to a fresh collection


def verify(base, now, th, allow_paused=False):
    validate_sample(base); validate_sample(now)
    if set(base['queues']) != set(now['queues']): raise ValueError('API queue set changed')
    R = Report('api-verify')
    R.check('Q1', 'server version unchanged (v3.3.5)', now['version'] == base['version'] == 'v3.3.5', now['version'])
    R.check('Q2', 'server statistics (photos, videos, usage, per-user usage) identical to the pre-freeze baseline', now['server_statistics'] == base['server_statistics'], {k: (base['server_statistics'][k], now['server_statistics'][k]) for k in base['server_statistics'] if base['server_statistics'][k] != now['server_statistics'][k]} or 'equal')
    R.check('Q3', 'library statistics identical (8 libraries)', now['libraries'] == base['libraries'] and len(now['libraries']) == 8)
    # phase 8D: failed jobs must not INCREASE in any queue relative to the baseline (known baseline: facialRecognition = 1, a stalled FacialRecognitionQueueAll job from 4 Apr 2026, doc 24).
    # A queue that is missing from the baseline counts as 0, so any new failure in any queue (and a second one in facialRecognition) still FAILS.
    bf = {k: v.get('failed', 0) for k, v in base['queues'].items()}
    R.check('Q4', 'no queue has more failed jobs than the baseline (known: facialRecognition=1)', all(v['failed'] <= bf.get(k, 0) for k, v in now['queues'].items()), {k: '%d (baseline %d)' % (v['failed'], bf.get(k, 0)) for k, v in now['queues'].items() if v['failed'] > bf.get(k, 0)} or {k: v['failed'] for k, v in now['queues'].items() if v['failed']} or '')
    R.check('Q5', 'no queue is left paused%s' % (' (dark phase: all queues must STILL be paused)' if allow_paused else ''), (all(v['isPaused'] for k, v in now['queues'].items() if k not in UNPAUSABLE) if allow_paused else not any(v['isPaused'] for v in now['queues'].values())), [k for k, v in now['queues'].items() if k not in UNPAUSABLE and v['isPaused'] != allow_paused] or '')
    if 'albums' in base and 'albums' in now:
        R.check('Q6', 'albums (count and per-album asset counts) identical', now['albums'] == base['albums'])
        R.check('Q7', 'people total/hidden identical', now['people'] == base['people'], '%s vs %s' % (base['people'], now['people']))
        ov, cold, warm = [], [], []
        for q in SMART_QUERIES:
            b, n = base['smart'][q], now['smart'][q]
            ov.append(len(set(b['ids']) & set(n['ids'])) / max(1, len(b['ids']))); cold.append(n['cold_ms']); warm += n['warm_ms']
        R.check('Q8', 'smart search: top-20 overlap with the pre-freeze result >= %.2f for every one of %d queries (PROPOSED)' % (th['overlap'], len(SMART_QUERIES)), min(ov) >= th['overlap'], 'min=%.2f mean=%.2f' % (min(ov), statistics.mean(ov)))
        wb = sorted(w for q in SMART_QUERIES for w in base['smart'][q]['warm_ms']); wn = sorted(warm)
        p95 = lambda v: v[min(len(v) - 1, int(len(v) * 0.95))]
        R.check('Q9', 'smart search warm p95 <= max(%.0f ms, 2 x baseline p95 %.0f ms) (PROPOSED)' % (th['warm_ms'], p95(wb)), p95(wn) <= max(th['warm_ms'], 2 * p95(wb)), 'now p95=%d ms baseline p95=%d ms' % (p95(wn), p95(wb)))
        R.check('Q10', 'smart search cold (first) query, ML model reloaded after idle <= %.0f ms (PROPOSED)' % th['cold_ms'], max(cold) <= th['cold_ms'], 'max=%d ms' % max(cold))
    else:
        R.check('Q6', 'IMMICH_USER_API_KEY baseline/verify missing: album/people/search checks NOT performed', False, '', 'FAIL')
    return R


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('baseline'); b.add_argument('--out', required=True)
    v = sub.add_parser('verify'); v.add_argument('--baseline', required=True); v.add_argument('--out')
    v.add_argument('--allow-paused', action='store_true', help='dark phase: queues are expected to be paused'); v.add_argument('--min-overlap', type=float, default=0.90); v.add_argument('--max-warm-ms', type=float, default=250.0); v.add_argument('--max-cold-ms', type=float, default=5000.0)
    v.add_argument('--result', help='machine-readable complete Q1-Q10 receipt')
    c = sub.add_parser('check-result'); c.add_argument('path')
    c = sub.add_parser('check-sample'); c.add_argument('path')
    q = sub.add_parser('queues'); q.add_argument('action', choices=['status', 'pause', 'resume', 'wait-drain']); q.add_argument('--execute', action='store_true'); q.add_argument('--timeout', type=int, default=600)
    j = sub.add_parser('job'); j.add_argument('name', choices=['backup-database']); j.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if a.cmd == 'check-sample':
        validate_sample(json.loads(Path(a.path).read_text())); sys.exit(0)
    if a.cmd == 'check-result':
        check_result(a.path); sys.exit(0)
    if a.cmd == 'baseline':
        d = collect(); Path(a.out).write_text(json.dumps(d, indent=1)); os.chmod(a.out, 0o600); print('baseline written:', a.out, '| photos/videos:', d['server_statistics']['photos'], d['server_statistics']['videos'])
    elif a.cmd == 'verify':
        base = json.loads(Path(a.baseline).read_text()); now = collect()
        if a.out: Path(a.out).write_text(json.dumps(now, indent=1)); os.chmod(a.out, 0o600)
        R = verify(base, now, {'overlap': a.min_overlap, 'warm_ms': a.max_warm_ms, 'cold_ms': a.max_cold_ms}, a.allow_paused)
        rc = R.finish(evidence_dir() if os.environ.get('CUTOVER_ID') else None)
        if a.result:
            result = {'name': 'api-verify', 'status': 'FAIL' if rc else 'PASS',
                      'fail': sum(x['status'] == 'FAIL' for x in R.items), 'warn': sum(x['status'] == 'WARN' for x in R.items),
                      'items': R.items, 'sample': now}
            Path(a.result).write_text(json.dumps(result, indent=1)); os.chmod(a.result, 0o600)
        sys.exit(rc)
    elif a.cmd == 'queues':
        if a.action == 'status':
            for k, v_ in queues().items(): print('%-26s active=%-3d waiting=%-5d delayed=%-3d failed=%-3d held=%-5d paused=%s' % (k, v_['active'], v_['waiting'], v_['delayed'], v_['failed'], v_['paused'], v_['isPaused']))   # held = jobs kept back by a paused queue (BullMQ reports them as `paused`)
        elif a.action in ('pause', 'resume'):
            if not a.execute: sys.exit('refusing: %s changes production queue state; add --execute' % a.action)
            failed, skipped = [], []
            for k in queues():                      # attempt EVERY queue; never stop half-way through
                r = immich(ADMIN, 'PUT', '/queues/' + k, {'isPaused': a.action == 'pause'}); print(k, r['status'])
                if r['status'] in (200, 201): continue
                if a.action == 'pause' and k in UNPAUSABLE and r['status'] == 400 and 'cannot be paused' in (r.get('body') or ''): skipped.append(k)
                else: failed.append((k, r['status']))
            if os.environ.get('CUTOVER_ID') and a.action == 'pause':
                d = evidence_dir(); d.mkdir(parents=True, exist_ok=True, mode=0o700); (d / 'unpausable-queues.json').write_text(json.dumps(skipped))
            print('%s: %d queue(s) not pausable by design: %s' % (a.action, len(skipped), skipped))
            if failed: sys.exit('FAILED to %s: %s (queues may be half-paused: STOP, run `queues status`, then `queues resume --execute`)' % (a.action, failed))
        else:
            t0 = time.time()
            while time.time() - t0 < a.timeout:
                qs = queues(); act = {k: v_['active'] for k, v_ in qs.items() if v_['active']}
                notpaused = [k for k, v_ in qs.items() if k not in UNPAUSABLE and not v_['isPaused']]
                print('%4ds active=%s not-paused=%s backlog(waiting+held)=%d' % (time.time() - t0, act or 0, notpaused or 0, sum(v_['waiting'] + v_['paused'] for v_ in qs.values())), flush=True)
                if not act and not notpaused: print('DRAINED: every pausable queue is paused and active==0 on all queues'); sys.exit(0)
                time.sleep(5)
            sys.exit('TIMEOUT: queues not drained after %ds (STOP-condition of the runbook)' % a.timeout)
    else:
        if not a.execute: sys.exit('refusing: creates a backup job; add --execute')
        r = immich(ADMIN, 'POST', '/jobs', {'name': 'backup-database'}); print('POST /jobs backup-database ->', r['status'])
