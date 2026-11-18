"""Shared helpers for the Immich cutover preflight/validation scripts.

SAFETY: every database access here is a READ ONLY transaction against the two allowed containers. The only mutating
operation in this directory is `api_checks.py queues pause|resume --execute`, which is gated by an explicit flag.
These scripts were prepared in phase 6 and were NOT executed against production.
"""
import json, os, subprocess, sys, time, hashlib, re
from pathlib import Path

SOURCE, TARGET, DB = 'postgis', 'immich-db', 'immich'
SERVER, NETWORK = 'immich_server', 'postgis'
REDIS, ML = 'immich_redis', 'immich_machine_learning'
PROD_NAMES = {'postgis', 'immich_server', 'immich_redis', 'immich_machine_learning', 'immich_media_operations', 'nextcloud_immich_bridge', 'traefik', 'immich-db'}
PROD_CONTAINERS = ['postgis', 'immich_server', 'immich_redis', 'immich_machine_learning', 'immich_media_operations', 'nextcloud_immich_bridge', 'traefik']
IMMICH_DIR = Path(os.environ.get('CUTOVER_IMMICH_DIR', '/opt/stacks/immich'))
DATA_DIR = Path(os.environ.get('CUTOVER_DATA_DIR', '/opt/stacks/data'))
BACKUPS_DIR = Path(os.environ.get('CUTOVER_BACKUPS_DIR', str(IMMICH_DIR / 'docker-data' / 'library' / 'backups')))
TARGET_DATADIR = Path(os.environ.get('CUTOVER_TARGET_DATADIR', str(DATA_DIR / 'immich-postgres' / 'data')))
REHEARSAL = os.environ.get('CUTOVER_REHEARSAL') == '1'
REHEARSAL_PREFIX = 'immich-apptest-'
if REHEARSAL:
    # REHEARSAL PROFILE: only isolated immich-apptest-* containers. Production names are refused by guard() on every command.
    SOURCE, TARGET, SERVER = os.environ['REHEARSAL_SRC_CONTAINER'], os.environ['REHEARSAL_DB_CONTAINER'], os.environ['REHEARSAL_SERVER_CONTAINER']
    REDIS, ML = os.environ['REHEARSAL_REDIS_CONTAINER'], os.environ['REHEARSAL_ML_CONTAINER']
    NETWORK = os.environ['REHEARSAL_NETWORK']
    for n in (SOURCE, TARGET, SERVER, REDIS, ML):
        assert n.startswith(REHEARSAL_PREFIX) and n not in PROD_NAMES, 'rehearsal needs immich-apptest-* containers, got ' + n
    PROD_CONTAINERS = [SOURCE, SERVER, REDIS, ML]
    DB = os.environ.get('CUTOVER_DB', 'immich')
BRIDGE = os.environ.get('CUTOVER_BRIDGE_CONTAINER', '')       # privately named bridge container (immich-cutover-bridge-<ID> / immich-apptest-*-bridge)
ALLOWED_DB_CONTAINERS = {SOURCE, TARGET} | ({BRIDGE} if BRIDGE else set())
EXPECTED_EXT = {'cube': '1.5', 'earthdistance': '1.2', 'pg_trgm': '1.6', 'plpgsql': '1.0', 'unaccent': '1.1', 'uuid-ossp': '1.1', 'vchord': '1.1.1', 'vector': '0.8.2'}
IDX_TEXT_EXCEPTION = 'asset_localDateTime_month_idx'      # phase 4C: pg_get_indexdef formatting differs between 16.13 and 16.16
HERE = Path(__file__).resolve().parent
MANIFEST_SQL = HERE / 'sql' / 'schema-manifest.sql'
GUC = ("SET LOCAL statement_timeout='300s'; SET LOCAL search_path=public,pg_catalog; SET LOCAL TimeZone='UTC';"
       " SET LOCAL DateStyle='ISO'; SET LOCAL extra_float_digits=3;")


def guard(args):
    """Rehearsal safety net: refuse any command that names a production container, mounts/reads production paths or uses the Docker socket."""
    if not REHEARSAL:
        return
    for a in args:
        if a in PROD_NAMES:
            raise PermissionError('REHEARSAL GUARD: production container name: ' + a)
        if 'docker.sock' in a or '/opt/stacks/immich' in a or '/opt/stacks/nextcloud' in a or '/opt/stacks/data/postgres/' in a or '/opt/stacks/data/immich-postgres' in a:
            raise PermissionError('REHEARSAL GUARD: production path or Docker socket: ' + a)
    if len(args) > 2 and args[0] == 'docker' and args[1] in ('exec', 'inspect', 'logs', 'stop', 'start', 'rm', 'kill', 'restart', 'cp', 'pause', 'unpause', 'stats'):
        if not any(a.startswith(REHEARSAL_PREFIX) for a in args[2:]):
            raise PermissionError('REHEARSAL GUARD: docker %s must target an %s* container: %s' % (args[1], REHEARSAL_PREFIX, ' '.join(args[:5])))


def audit(args):
    p = os.environ.get('CUTOVER_AUDIT')
    if p:
        with open(p, 'a') as f: f.write(json.dumps({'t': round(time.time(), 2), 'argv': args}) + '\n')


def run(args, input=None, timeout=300, check=True, env=None):
    guard(args); audit(args)
    p = subprocess.run(args, input=input, text=True, capture_output=True, timeout=timeout, env=env)
    if check and p.returncode:
        raise RuntimeError('%s exited %d: %s' % (' '.join(args[:6]), p.returncode, (p.stderr or p.stdout)[-400:]))
    return p.stdout.strip() if check else p


def psql(container, sql, db=DB, user='postgres'):
    """Always inside BEGIN READ ONLY ... ROLLBACK."""
    assert container in ALLOWED_DB_CONTAINERS, 'refusing container ' + container
    guard(['docker', 'exec', container])
    assert re.fullmatch(r'[A-Za-z0-9_]+', db)
    text = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; " + GUC + "\n" + sql + "\nROLLBACK;"
    return run(['docker', 'exec', '-i', container, 'psql', '-Xq', '-U', user, '-d', db, '-At', '-v', 'ON_ERROR_STOP=1'], input=text, timeout=600)


def pj(container, sql, **kw):
    return json.loads(psql(container, sql, **kw))


def stream_hash(container, sql, db=DB):
    """SHA-256 of a COPY ... TO STDOUT stream without storing a single row."""
    assert container in ALLOWED_DB_CONTAINERS
    guard(['docker', 'exec', container]); audit(['docker', 'exec', '-i', container, 'psql', '<stream %s>' % db])
    text = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; " + GUC + "\n" + sql + "\nROLLBACK;"
    pr = subprocess.Popen(['docker', 'exec', '-i', container, 'psql', '-Xq', '-U', 'postgres', '-d', db, '-At', '-v', 'ON_ERROR_STOP=1'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    pr.stdin.write(text.encode()); pr.stdin.close()
    h, rows, size = hashlib.sha256(), 0, 0
    for blk in iter(lambda: pr.stdout.read(1 << 20), b''):
        h.update(blk); rows += blk.count(b'\n'); size += len(blk)
    if pr.wait(timeout=900):
        raise RuntimeError('stream failed')
    return {'rows': rows, 'sha256': h.hexdigest(), 'bytes': size}


def qid(name): return '"' + name.replace('"', '""') + '"'


def strip_postgis(m):
    m = json.loads(json.dumps(m))
    m['extensions'] = [e for e in m['extensions'] if e['name'] != 'postgis']
    for k in ['relations', 'indexes', 'constraints', 'functions', 'types', 'triggers']:
        if m.get(k): m[k] = [x for x in m[k] if x.get('extension') != 'postgis'] or None
    return m


def identity(m): return m


def mask_idx_text(m):
    m = json.loads(json.dumps(m))
    for x in (m.get('indexes') or []):
        if x['name'] == IDX_TEXT_EXCEPTION: x['definition'] = '<<allowed text-format exception>>'
    return m


def container_env(container, key):
    """Value of `key` exactly as the running container received it (Compose has already applied env_file/quoting/interpolation).
    The value is returned in memory only: never printed, never logged, never written to disk."""
    guard(['docker', 'inspect', container])
    env = json.loads(run(['docker', 'inspect', container]))[0]['Config']['Env']
    vals = [e.split('=', 1)[1] for e in env if e.startswith(key + '=')]
    if len(vals) != 1:
        raise RuntimeError('%s: %d entries for %s' % (container, len(vals), key))
    return vals[0]


# ---------------------------------------------------------------- Immich API through `docker exec immich_server node` (no extra containers, no host port)
NODE_CALL = r"""
const req = JSON.parse(require('fs').readFileSync(0, 'utf8'));
(async () => {
  const t0 = Date.now();
  const r = await fetch('http://127.0.0.1:2283/api' + req.path, {method: req.method || 'GET',
    headers: {'x-api-key': process.env.IMMICH_API_KEY, 'content-type': 'application/json', 'accept': 'application/json'},
    body: req.body ? JSON.stringify(req.body) : undefined});
  const text = await r.text();
  console.log(JSON.stringify({status: r.status, ms: Date.now() - t0, body: text.slice(0, 6000000)}));
})().catch(e => { console.log(JSON.stringify({status: 0, ms: 0, error: String(e)})); });
"""


def immich(keyname, method, path, body=None, container=SERVER):
    """Calls the Immich API from inside the server container (localhost). The key comes from the operator's environment."""
    key = os.environ.get(keyname)
    if not key:
        raise RuntimeError('environment variable %s is not set' % keyname)
    env = dict(os.environ, IMMICH_API_KEY=key)
    out = run(['docker', 'exec', '-i', '-e', 'IMMICH_API_KEY', container, 'node', '-e', NODE_CALL], input=json.dumps({'method': method, 'path': path, 'body': body}), env=env, timeout=300)
    r = json.loads(out.splitlines()[-1])
    try: r['json'] = json.loads(r['body']) if r.get('body') else None
    except Exception: r['json'] = None
    return r


class Report:
    def __init__(self, name):
        self.name, self.items, self.t0 = name, [], time.time()

    def check(self, cid, desc, ok, detail='', level='FAIL'):
        status = 'PASS' if ok else level
        self.items.append({'id': cid, 'desc': desc, 'status': status, 'detail': str(detail)[:600]})
        print('%-5s %-5s %s%s' % (status, cid, desc, (' | ' + str(detail)[:160]) if detail != '' else ''), flush=True)
        return ok

    def info(self, cid, desc, detail=''):
        self.items.append({'id': cid, 'desc': desc, 'status': 'INFO', 'detail': str(detail)[:600]})
        print('INFO  %-5s %s%s' % (cid, desc, (' | ' + str(detail)[:160]) if detail != '' else ''), flush=True)

    def finish(self, outdir=None):
        fails = [i for i in self.items if i['status'] == 'FAIL']
        warns = [i for i in self.items if i['status'] == 'WARN']
        res = {'name': self.name, 'seconds': round(time.time() - self.t0, 1), 'fail': len(fails), 'warn': len(warns), 'items': self.items}
        if outdir:
            Path(outdir).mkdir(parents=True, exist_ok=True, mode=0o700)
            p = Path(outdir) / ('%s-%s.json' % (self.name, time.strftime('%Y%m%dT%H%M%S')))
            p.write_text(json.dumps(res, indent=1)); os.chmod(p, 0o600)
            print('evidence:', p)
        print('RESULT: %s (%d FAIL, %d WARN)' % ('FAIL' if fails else 'PASS', len(fails), len(warns)))
        return 1 if fails else 0


def evidence_dir():
    cid = os.environ.get('CUTOVER_ID')
    if not cid or not re.fullmatch(r'[A-Za-z0-9._-]{6,64}', cid):
        raise SystemExit('set CUTOVER_ID (see cutover.env.example)')
    return Path(os.environ.get('EVIDENCE_ROOT', '/opt/stacks/data/backups')) / ('immich-cutover-' + cid)
