"""Read-only production preflight for the Immich cutover (postgis -> immich-db).

PREPARED IN PHASE 6, NOT EXECUTED AGAINST PRODUCTION. Run only inside an approved cutover window:
    CUTOVER_ID=... IMMICH_ADMIN_API_KEY=... [IMMICH_USER_API_KEY=...] python3 -I preflight.py [--skip-api] [--ignore-window]

It only reads: docker inspect, read-only SQL on `postgis`, file stats, and (with the keys) GET calls to the Immich API.
It never prints secrets, never pauses queues, never touches the target database.
Exit code 0 only if there is no FAIL.
"""
import argparse, datetime, hashlib, json, os, re, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cutlib import *

ap = argparse.ArgumentParser()
ap.add_argument('--skip-api', action='store_true', help='do not call the Immich API (queue/statistics baseline then missing -> FAIL level downgraded to WARN)')
ap.add_argument('--ignore-window', action='store_true', help='do not fail on cron-collision time windows')
ap.add_argument('--phase', choices=['before-target', 'target-ready'], default='before-target')
args = ap.parse_args()
R = Report('preflight')
BASE, IMMICH = DATA_DIR, IMMICH_DIR
env = {k: v for k, v in (l.split('=', 1) for l in open('cutover.env').read().splitlines() if '=' in l and not l.startswith('#'))} if Path('cutover.env').exists() else {}
EXPECT_SERVER = os.environ.get('EXPECT_SERVER_IMAGE', env.get('EXPECT_SERVER_IMAGE', 'sha256:619fb163d959f4ee2f35f222ef23b2390ccba5e307ade748548834ad77aef463'))
EXPECT_BRIDGE = os.environ.get('EXPECT_BRIDGE_IMAGE', env.get('EXPECT_BRIDGE_IMAGE', 'sha256:33e372cc42ccaa91156d5072e48836abb2e532063dfdc79aa30e17df333a3bf0'))
EXPECT_TARGET = os.environ.get('EXPECT_TARGET_IMAGE', env.get('EXPECT_TARGET_IMAGE', 'sha256:e21ee65b5a53580b8f1e85b21ba0bf16f19c43d4dcc2ad49c4ce68a864a7cf51'))
evid = evidence_dir()
baseline = {}


def sha_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def safe(cid, desc, fn, level='FAIL'):
    try:
        return fn()
    except Exception as e:
        R.check(cid, desc + ' (check crashed)', False, type(e).__name__ + ': ' + str(e)[:200], level)


# ------------------------------------------------------------------ HOST
free = shutil.disk_usage(str(BASE)).free
R.check('H1', 'free disk >= 96 GiB (full dump + sanitized dump + bridge + target + reserve)', free >= 96 * 2**30, '%.1f GiB' % (free / 2**30))
mem = int(open('/proc/meminfo').read().split('MemAvailable:')[1].split()[0]) * 1024
R.check('H2', 'available memory >= 8 GiB', mem >= 8 * 2**30, '%.1f GiB' % (mem / 2**30))
try:
    from zoneinfo import ZoneInfo
    now = datetime.datetime.now(ZoneInfo('Europe/Zagreb'))
    mins = now.hour * 60 + now.minute
    # Immich cron: nightly/library scan 00:00, backup 02:00, integrity 03:00 (up to 1 h), version check hourly, bridge every 300 s
    bad = (mins >= 23 * 60 + 40) or (mins < 4 * 60 + 15)
    R.check('H3', 'local time %s is outside Immich cron collisions (00:00 scan/nightly, 02:00 backup, 03:00 integrity); window 04:30-22:00 advised' % now.strftime('%H:%M'), args.ignore_window or not bad, 'ignored' if args.ignore_window and bad else '')
except Exception as e:
    R.check('H3', 'timezone check', False, str(e), 'WARN')

# ------------------------------------------------------------------ PRODUCTION CONTAINERS
for n in PROD_CONTAINERS:
    def f(n=n):
        c = json.loads(run(['docker', 'inspect', n]))[0]
        st = c['State']; h = (st.get('Health') or {}).get('Status', 'none')
        R.check('C-' + n, '%s running%s' % (n, ' and healthy' if h != 'none' else ''), st['Running'] and h in ('healthy', 'none'), 'status=%s health=%s restarts=%s' % (st['Status'], h, c['RestartCount']))
        baseline[n] = {'Id': c['Id'], 'Image': c['Image'], 'StartedAt': st['StartedAt'], 'Restart': c['RestartCount'], 'Mounts': sorted(json.dumps(m, sort_keys=True) for m in c['Mounts']),
                       'Networks': sorted(c['NetworkSettings']['Networks']), 'Config': hashlib.sha256(json.dumps(c['Config'], sort_keys=True).encode()).hexdigest()}
        return c
    safe('C-' + n, n + ' inspect', f)
c = json.loads(run(['docker', 'inspect', SERVER]))[0]
R.check('C-img', 'application container runs the patched production build image', c['Image'] == EXPECT_SERVER, c['Image'][:19])
envmap = dict(e.split('=', 1) for e in c['Config']['Env'] if '=' in e)
R.check('C-dbhost', 'application DB_HOSTNAME is still the source database host', envmap.get('DB_HOSTNAME') == SOURCE and envmap.get('DB_DATABASE_NAME') == 'immich' and envmap.get('DB_USERNAME') == 'immich', 'DB_HOSTNAME=%s' % envmap.get('DB_HOSTNAME'))
R.check('C-nets', 'application container is on the database network%s' % ('' if REHEARSAL else ' and proxy'), ({NETWORK} if REHEARSAL else {'postgis', 'proxy'}) <= set(c['NetworkSettings']['Networks']), sorted(c['NetworkSettings']['Networks']))
if not REHEARSAL:
    mo = json.loads(run(['docker', 'inspect', 'immich_media_operations']))[0]
    moenv = dict(e.split('=', 1) for e in mo['Config']['Env'] if '=' in e)
    R.check('M1', 'media-operations DB_HOSTNAME is postgis (it runs `docker exec <DB_HOSTNAME> psql`)', moenv.get('DB_HOSTNAME') == 'postgis', 'DB_HOSTNAME=%s' % moenv.get('DB_HOSTNAME'))
    dyn = Path('/opt/stacks/traefik/dynamic')
    hits = [f.name for f in dyn.glob('*') if f.is_file() and f.suffix in ('.yml', '.yaml', '.toml') and re.search(r'immich|media\.finestar', f.read_text(errors='ignore'), re.I)] if dyn.is_dir() else ['<dynamic dir missing>']
    R.check('TR1', 'Traefik file provider has NO static Immich route (dark launch hides the route only if routing is label-based)', not hits, hits)
lab = c['Config']['Labels'].get('traefik.enable')
R.check('TR2', 'application container currently has traefik.enable=true (route active before the cutover)', lab == 'true', 'traefik.enable=%s' % lab)
rd = json.loads(run(['docker', 'inspect', REDIS]))[0]
R.info('RD1', 'Redis has no persistence volume: queue state is lost if immich_redis is recreated or restarted (DO NOT touch it)', 'mounts=%d' % len(rd['Mounts']))

# ------------------------------------------------------------------ IMAGES / TARGET SERVICE
def img(tag_or_id):
    return run(['docker', 'image', 'inspect', '-f', '{{.Id}}', tag_or_id])
safe('I1', 'target image present with the validated ID', lambda: R.check('I1', 'target image immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1 has the validated ID', img('immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1') == EXPECT_TARGET))
safe('I2', 'bridge image present', lambda: R.check('I2', 'bridge image (existing postgis image) present', img(EXPECT_BRIDGE) == EXPECT_BRIDGE))
if run(['docker', 'inspect', SOURCE, '-f', '{{.Image}}']) != EXPECT_BRIDGE:
    R.check('I3', 'source database container still runs the bridge image ID', False, 'image changed since validation')
else:
    R.check('I3', 'source database container runs the bridge image ID', True)
exists = run(['docker', 'ps', '-a', '--filter', 'name=^/%s$' % TARGET, '--format', '{{.Names}} {{.Status}}'])
datadir = TARGET_DATADIR
if args.phase == 'before-target':
    R.check('T1', 'no container named %s exists yet' % TARGET, not exists, exists)
    R.check('T2', 'target data directory exists and is EMPTY (nothing has been initialised)', datadir.is_dir() and not any(datadir.iterdir()), 'entries=%d' % (len(list(datadir.iterdir())) if datadir.is_dir() else -1))
else:
    R.check('T1', 'immich-db container running and healthy', 'healthy' in run(['docker', 'inspect', '-f', '{{.State.Health.Status}} {{.State.Status}}', TARGET], check=False).stdout if exists else False, exists)
    if exists:
        R.check('T3', 'target image ID is the validated one', run(['docker', 'inspect', '-f', '{{.Image}}', TARGET]) == EXPECT_TARGET)
        cn = json.loads(run(['docker', 'inspect', TARGET]))[0]
        R.check('T4', 'target is only on the database network and publishes no port', sorted(cn['NetworkSettings']['Networks']) == [NETWORK] and not cn['HostConfig']['PortBindings'], sorted(cn['NetworkSettings']['Networks']))
        R.check('T5', 'target mounts: its own data dir and /backups only', {m['Destination'] for m in cn['Mounts']} == {'/var/lib/postgresql/data', '/backups'}, sorted(m['Destination'] for m in cn['Mounts']))
net = json.loads(run(['docker', 'network', 'inspect', NETWORK]))[0]
R.check('N1', 'database network %s exists%s' % (NETWORK, ' and is internal (rehearsal)' if REHEARSAL else ' and is not internal'), net['Name'] == NETWORK and (net['Internal'] if REHEARSAL else not net['Internal']), 'containers=%d' % len(net['Containers']))
R.check('T6', 'compose file for immich-db present', (BASE / 'docker-compose.postgres-new.yml').is_file(), sha_file(BASE / 'docker-compose.postgres-new.yml')[:16] if (BASE / 'docker-compose.postgres-new.yml').is_file() else '')
dkeys = {l.split('=', 1)[0] for l in (BASE / '.env').read_text().splitlines() if '=' in l and not l.startswith('#')}
ikeys = {l.split('=', 1)[0]: l.split('=', 1)[1] for l in (IMMICH / '.env').read_text().splitlines() if '=' in l and not l.startswith('#')}
R.check('E1', '/opt/stacks/data/.env has POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB (values not read)', {'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB'} <= dkeys)
R.check('E2', 'immich .env has DB_PASSWORD and DB_HOSTNAME=<source host> (password not read)', 'DB_PASSWORD' in ikeys and ikeys.get('DB_HOSTNAME') == SOURCE, 'DB_HOSTNAME=%s' % ikeys.get('DB_HOSTNAME'))
baseline['files'] = {}
for _p in [BASE / 'docker-compose.yml', BASE / 'docker-compose.postgres-new.yml', BASE / '.env', IMMICH / 'docker-compose.yml', IMMICH / '.env']:
    try: baseline['files'][str(_p)] = sha_file(_p)
    except Exception as e: baseline['files'][str(_p)] = None; R.check('F-' + _p.name, 'cannot hash %s (needed for the production-unchanged comparison)' % _p, False, type(e).__name__, 'WARN')

# ------------------------------------------------------------------ SOURCE DATABASE (read only)
def source():
    v = psql(SOURCE, 'SHOW server_version;', db='postgres')
    R.check('S1', 'source PostgreSQL is 16.13', v.startswith('16.13'), v)
    info = pj(SOURCE, """SELECT json_build_object(
      'size_bytes',pg_database_size(current_database()),
      'app_tables',(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e')),
      'extensions',(SELECT json_object_agg(extname,extversion) FROM pg_extension),
      'migrations',(SELECT json_build_object('n',count(*),'last',max(name)) FROM kysely_migrations),
      'mountChecks',(SELECT value::json->'mountChecks' FROM system_metadata WHERE key='system-flags'),
      'invalid_indexes',(SELECT count(*) FROM pg_index i WHERE NOT (i.indisvalid AND i.indisready)),
      'role',(SELECT json_build_object('super',rolsuper,'createdb',rolcreatedb,'createrole',rolcreaterole,'repl',rolreplication,'bypassrls',rolbypassrls,'login',rolcanlogin,'inherit',rolinherit) FROM pg_roles WHERE rolname='immich'),
      'db',(SELECT json_build_object('owner',pg_get_userbyid(datdba),'enc',pg_encoding_to_char(encoding),'collate',datcollate,'allow',datallowconn,'acl',(SELECT json_agg(json_build_array(COALESCE(g.rolname,'PUBLIC'),x.privilege_type) ORDER BY 1,2) FROM aclexplode(COALESCE(datacl,acldefault('d',datdba))) x LEFT JOIN pg_roles g ON g.oid=x.grantee)) FROM pg_database WHERE datname=current_database()),
      'seq',(SELECT json_build_object('type',data_type,'last',last_value) FROM pg_sequences WHERE schemaname='public' AND sequencename='naturalearth_countries_tmp_id_seq1'),
      'sys_config_sha256',(SELECT encode(sha256(convert_to((value::jsonb)::text,'UTF8')),'hex') FROM system_metadata WHERE key='system-config'),
      'counts',(SELECT json_build_object('users',(SELECT count(*) FROM "user"),'assets',(SELECT count(*) FROM asset),'albums',(SELECT count(*) FROM album),'libraries',(SELECT count(*) FROM library),'persons',(SELECT count(*) FROM person),'smart_search',(SELECT count(*) FROM smart_search),'face_search',(SELECT count(*) FROM face_search),'api_keys',(SELECT count(*) FROM api_key)))
      );""")
    ex = dict(EXPECTED_EXT, postgis='3.6.2')
    R.check('S2', 'source has exactly the 9 validated extensions at the validated versions', info['extensions'] == ex, info['extensions'])
    R.check('S3', 'source has 72 application tables', info['app_tables'] == 72, info['app_tables'])
    files = run(['docker', 'exec', SERVER, 'sh', '-c', 'ls /usr/src/app/server/dist/schema/migrations/*.js'], check=True).splitlines()
    names = sorted(re.sub(r'\.js$', '', f.split('/')[-1]) for f in files)
    applied = sorted(psql(SOURCE, 'SELECT name FROM kysely_migrations;').splitlines())
    R.check('S4', 'no pending migrations: image migration files == applied (101 == 101)', names == applied and len(names) == 101, 'files=%d applied=%d' % (len(names), len(applied)))
    R.check('S5', 'system flags: all six mount checks true', info['mountChecks'] and all(info['mountChecks'].values()) and len(info['mountChecks']) == 6, info['mountChecks'])
    R.check('S6', 'no invalid/not-ready indexes on source', info['invalid_indexes'] == 0, info['invalid_indexes'])
    R.check('S7', 'role immich has no SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS', info['role'] and not any(info['role'][k] for k in ('super', 'createdb', 'createrole', 'repl', 'bypassrls')) and info['role']['login'], info['role'])
    R.check('S8', 'database immich: owner immich, UTF8, en_US.utf8, connections allowed', info['db']['owner'] == 'immich' and info['db']['enc'] == 'UTF8' and info['db']['collate'] == 'en_US.utf8' and info['db']['allow'], info['db'])
    R.check('S9', 'identity sequence is bigint on the source (will be integer after restore until normalised)', info['seq']['type'] == 'bigint', info['seq'])
    conns = psql(SOURCE, "SELECT coalesce(host(client_addr),'local')||'|'||usename||'|'||count(*) FROM (SELECT client_addr,usename FROM pg_stat_activity WHERE datname='immich') q GROUP BY client_addr,usename;", db='postgres').splitlines()
    srv_ips = {v['IPAddress'] for v in c['NetworkSettings']['Networks'].values() if v['IPAddress']}
    R.check('S10', 'only immich_server holds connections to the source immich database (no other consumer)', conns and all(l.split('|')[0] in srv_ips for l in conns), conns)
    baseline['source'] = info; baseline['source_connections'] = conns
    return info
safe('S0', 'source database inspection', source)

# ------------------------------------------------------------------ IMMICH BACKUP (02:00 job) evidence
def backup():
    d = BACKUPS_DIR
    files = sorted(d.glob('immich-db-backup-*.sql.gz'))
    R.check('B1', 'Immich backup directory has backups', len(files) > 0, 'count=%d' % len(files))
    if not files:
        return
    last = files[-1]; age_h = (time.time() - last.stat().st_mtime) / 3600
    R.check('B2', 'newest Immich backup is younger than 26 h', age_h < 26, '%s (%.1f h)' % (last.name, age_h))
    R.check('B3', 'newest Immich backup name matches immich-db-backup-<ts>-v3.3.5-pg16.x.sql.gz', bool(re.fullmatch(r'immich-db-backup-\d{8}T\d{6}-v3\.3\.5-pg16\.\d+\.sql\.gz', last.name)), last.name)
    p = run(['gzip', '-t', str(last)], check=False)
    R.check('B4', 'newest Immich backup passes gzip -t', p.returncode == 0, p.stderr[-100:])
    bins = run(['docker', 'exec', SERVER, 'sh', '-c', '/usr/lib/postgresql/16/bin/pg_dump --version']).strip()
    R.check('B5', 'server image ships the pg_dump 16 client Immich selects for PostgreSQL 16.x', bins.startswith('pg_dump (PostgreSQL) 16.'), bins)
safe('B0', 'backup inspection', backup)

# ------------------------------------------------------------------ IMMICH API (needs temporary keys; GET only)
if not args.skip_api:
    def api():
        lvl = 'FAIL'
        r = immich('IMMICH_ADMIN_API_KEY', 'GET', '/server/about')
        R.check('A1', 'admin API key works (GET /server/about) and server is v3.3.5', r['status'] == 200 and (r['json'] or {}).get('version') == 'v3.3.5', 'status=%s' % r['status'])
        q = immich('IMMICH_ADMIN_API_KEY', 'GET', '/queues')
        ok = q['status'] == 200 and isinstance(q['json'], list)
        R.check('A2', 'admin key has queue.read (GET /queues)', ok, 'status=%s' % q['status'])
        if ok:
            stats = {x['name']: {k: x['statistics'].get(k) for k in ('active', 'waiting', 'delayed', 'failed', 'paused')} | {'isPaused': x.get('isPaused')} for x in q['json']}
            baseline['queues'] = stats
            R.info('A3', 'queue snapshot (active/waiting/delayed/failed)', {k: (v['active'], v['waiting'], v['delayed'], v['failed']) for k, v in stats.items() if any((v['active'], v['waiting'], v['delayed'], v['failed']))} or 'all idle')
            R.check('A4', 'no queue is currently paused (nobody else is already in a maintenance state)', not any(v['isPaused'] for v in stats.values()), [k for k, v in stats.items() if v['isPaused']], 'WARN')
        st = immich('IMMICH_ADMIN_API_KEY', 'GET', '/server/statistics')
        R.check('A5', 'admin key has server.statistics (aggregate counts baseline)', st['status'] == 200, 'status=%s' % st['status'])
        if st['status'] == 200:
            baseline['server_statistics'] = {k: st['json'].get(k) for k in ('photos', 'videos', 'usage', 'usagePhotos', 'usageVideos')}
            baseline['server_statistics']['users'] = len(st['json'].get('usageByUser') or [])
        lb = immich('IMMICH_ADMIN_API_KEY', 'GET', '/libraries')
        R.check('A6', 'admin key can list libraries (8 expected)', lb['status'] == 200 and isinstance(lb['json'], list) and len(lb['json']) == 8, 'status=%s count=%s' % (lb['status'], len(lb['json']) if isinstance(lb['json'], list) else '?'))
        if os.environ.get('IMMICH_USER_API_KEY'):
            al = immich('IMMICH_USER_API_KEY', 'GET', '/albums')
            R.check('A7', 'data-user key can read albums', al['status'] == 200 and isinstance(al['json'], list) and len(al['json']) > 0, 'status=%s' % al['status'])
        else:
            R.check('A7', 'IMMICH_USER_API_KEY not set: search/people/album baseline will be skipped', False, '', 'WARN')
    safe('A0', 'API checks', api)
else:
    R.check('A0', 'API checks skipped (--skip-api): queue/statistics baseline missing', False, '', 'WARN')

# ------------------------------------------------------------------ evidence
R.info('Z1', 'baseline recorded for the post-cutover production-unchanged comparison', 'containers=%d files=%d' % (len([k for k in baseline if k in PROD_CONTAINERS]), len(baseline.get('files', {}))))
(evid).mkdir(parents=True, exist_ok=True, mode=0o700)
p = evid / ('baseline-%s.json' % time.strftime('%Y%m%dT%H%M%S')); p.write_text(json.dumps(baseline, indent=1)); os.chmod(p, 0o600)
sys.exit(R.finish(evid))
