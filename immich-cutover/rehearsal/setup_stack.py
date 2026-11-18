"""Builds the isolated cutover REHEARSAL stack (immich-apptest-* containers only) and writes <EVROOT>/state.json + <EVROOT>/env.sh.

  python3 -I setup_stack.py setup      # create stack, restore the phase-4 full dump into the stand-in source, passwords, test API keys
  python3 -I setup_stack.py teardown   # remove ONLY this rehearsal's containers/network/test dir (labels and realpath checked)

Every docker command goes through cutlib.run (rehearsal guard: production names/paths/docker.sock are refused, argv is audited).
"""
import json, os, re, secrets, shutil, sys, time
from pathlib import Path

CV = Path('/opt/stacks/data/immich-cutover'); REH = CV / 'rehearsal'
FULL_DUMP = Path('/opt/stacks/data/backups/immich-restore-test-20261114t152235z-1bb3b8/immich.full.dump')
FULL_SHA = '9d901f555df93f909290c6a505e3836ad9dc1d0e97e371227f599797d3632a5e'
IMG = {'R_SRC_IMAGE': 'sha256:33e372cc42ccaa91156d5072e48836abb2e532063dfdc79aa30e17df333a3bf0', 'R_NEW_IMAGE': 'sha256:e21ee65b5a53580b8f1e85b21ba0bf16f19c43d4dcc2ad49c4ce68a864a7cf51',
       'TEST_SERVER_IMAGE': 'sha256:619fb163d959f4ee2f35f222ef23b2390ccba5e307ade748548834ad77aef463', 'TEST_ML_IMAGE': 'sha256:5b28c9352c8374b8a1ed96fbdd8d6755fea6e43510ec43fdf6538aa02ea40f56',
       'TEST_REDIS_IMAGE': 'docker.io/valkey/valkey:9@sha256:3eeb09785cd61ec8e3be35f8804c8892080f3ca21934d628abc24ee4ed1698f6'}
TRICKY_PW = 'S3c$r"et#1 \\!x=y%&;z'            # special characters on purpose ($ " # space backslash ! = % & ;)

cmd = sys.argv[1] if len(sys.argv) > 1 else ''
if cmd == 'setup':
    ID = time.strftime('%Y%m%dt%H%M%Sz', time.gmtime()) + '-' + secrets.token_hex(3)
    ROOT = Path('/tmp/immich-apptest-' + ID); EVROOT = Path('/opt/stacks/data/backups/immich-rehearsal-' + ID)
    STATE = EVROOT / 'state.json'
else:
    EVROOT = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    st = json.loads((EVROOT / 'state.json').read_text()); ID = st['id']; ROOT = Path(st['root'])
PROJ = 'immich-apptest-' + ID
N = {k: 'immich-apptest-%s-%s' % (ID, v) for k, v in (('src', 'pgsrc'), ('db', 'immichdb'), ('server', 'server'), ('redis', 'redis'), ('ml', 'ml'), ('mops', 'mops'), ('brg', 'brg'))}
os.environ.update({'CUTOVER_REHEARSAL': '1', 'REHEARSAL_SRC_CONTAINER': N['src'], 'REHEARSAL_DB_CONTAINER': N['db'], 'REHEARSAL_SERVER_CONTAINER': N['server'], 'REHEARSAL_REDIS_CONTAINER': N['redis'],
                   'REHEARSAL_ML_CONTAINER': N['ml'], 'REHEARSAL_NETWORK': PROJ + '_testnet', 'CUTOVER_AUDIT': str((EVROOT or Path('/tmp')) / 'audit.jsonl')})
sys.path.insert(0, str(CV))
import cutlib
from cutlib import run

ENVF = ROOT / 'rehearsal.env'
def D(*a, **kw): return run(['docker', *a], **kw)
def DC(*a, **kw): return run(['docker', 'compose', '-p', PROJ, '--env-file', str(ENVF), '-f', str(REH / 'docker-compose.rehearsal.yml'), *a], **kw)
def pg(c, sql, db='postgres', env=None): return run(['docker', 'exec', '-i'] + (['-e', 'NEWPW'] if env else []) + [c, 'psql', '-X', '-U', 'postgres', '-d', db, '-At', '-v', 'ON_ERROR_STOP=1'], input=sql, env=env)
def wait_h(c, t=240):
    t0 = time.time()
    while time.time() - t0 < t:
        if run(['docker', 'inspect', '-f', '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}', c]) == 'healthy': return
        time.sleep(3)
    raise RuntimeError('not healthy: ' + c)

NODE = r"""
const q = JSON.parse(require('fs').readFileSync(0, 'utf8'));
(async () => { const h = {'content-type': 'application/json', accept: 'application/json'}; if (q.token) h.authorization = 'Bearer ' + q.token;
  const r = await fetch('http://127.0.0.1:2283/api' + q.path, {method: q.method || 'GET', headers: h, body: q.body ? JSON.stringify(q.body) : undefined});
  console.log(JSON.stringify({status: r.status, body: await r.text()})); })().catch(e => console.log(JSON.stringify({status: 0, body: String(e)})));
"""
def api(method, path, body=None, token=None):
    out = run(['docker', 'exec', '-i', N['server'], 'node', '-e', NODE], input=json.dumps({'method': method, 'path': path, 'body': body, 'token': token}))
    r = json.loads(out.splitlines()[-1]); r['json'] = json.loads(r['body']) if r['body'] else None; return r

def teardown():
    for n in N.values():
        if run(['docker', 'ps', '-aq', '--filter', 'name=^/%s$' % n]):
            D('rm', '-f', n)
    if run(['docker', 'network', 'ls', '-q', '--filter', 'name=^%s_testnet$' % PROJ]): D('network', 'rm', PROJ + '_testnet')
    leftovers = run(['docker', 'ps', '-aq', '--filter', 'name=immich-apptest-' + ID])
    assert not leftovers, 'containers of this rehearsal still exist: ' + leftovers
    assert str(ROOT.resolve()).startswith('/tmp/immich-apptest-') and ROOT.name == 'immich-apptest-' + ID
    shutil.rmtree(ROOT, ignore_errors=True)
    print('teardown done: containers, network and %s removed; evidence kept in %s' % (ROOT, EVROOT))

if cmd == 'teardown':
    teardown(); sys.exit(0)
assert cmd == 'setup'
os.umask(0o077)
os.umask(0o077)
EVROOT.mkdir(mode=0o700); ROOT.mkdir(mode=0o700)
assert cutlib.run(['sha256sum', str(FULL_DUMP)]).split()[0] == FULL_SHA, 'full dump hash'
assert not [n for n in run(['docker', 'ps', '-a', '--format', '{{.Names}}']).splitlines() if n.startswith('immich-apptest-')], 'another apptest stack exists'
for d in ('src-data', 'new-data', 'ml-cache', 'media', 'results', 'synthetic', 'fixture/data', 'fixture/immich', 'bridge-work'): (ROOT / d).mkdir(parents=True, mode=0o700)
os.chown(ROOT / 'src-data', 999, 999); os.chown(ROOT / 'new-data', 999, 999)
for d in ('upload', 'library', 'thumbs', 'encoded-video', 'profile', 'backups'):
    (ROOT / 'media' / d).mkdir(mode=0o755); (ROOT / 'media' / d / '.immich').write_text(str(int(time.time() * 1000)))
for p in (ROOT / 'media').rglob('*'): os.chmod(p, 0o755 if p.is_dir() else 0o644)
os.chmod(ROOT / 'media', 0o755)
# ML cache: copy of the model cache (read from the production VOLUME path only as plain files; guard does not treat it as a container/mount of production)
run(['cp', '-a', '/var/lib/docker/volumes/immich_model-cache/_data/.', str(ROOT / 'ml-cache')], timeout=900)
run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python', '-v', '%s:/out' % (ROOT / 'synthetic'), '-v', '%s:/tools:ro' % (CV.parent / 'immich-app-test' / 'tools'), IMG['TEST_ML_IMAGE'], '-I', '/tools/gen_synthetic.py', '/out'])
client_img = run(['docker', 'image', 'inspect', '-f', '{{.Id}}', 'python:3.12-slim'])
su_pw = secrets.token_hex(16)
FIX = ROOT / 'fixture'
(FIX / 'immich' / '.env').write_text("DB_HOSTNAME=%s\nDB_USERNAME=immich\nDB_DATABASE_NAME=immich\nDB_PORT=5432\nDB_PASSWORD='%s'\nTZ=Europe/Zagreb\n" % (N['src'], TRICKY_PW))
(FIX / 'data' / '.env').write_text("POSTGRES_USER=postgres\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=postgres\nTZ=Europe/Zagreb\n" % su_pw)
shutil.copy('/opt/stacks/data/docker-compose.postgres-new.yml', FIX / 'data' / 'docker-compose.postgres-new.yml')
shutil.copy(REH / 'docker-compose.rehearsal.yml', FIX / 'immich' / 'docker-compose.yml')
ENVF.write_text('\n'.join(['CASE_ID=' + ID, 'TEST_ROOT=' + str(ROOT), 'R_SU_PW=' + su_pw, 'R_FULL_DUMP=' + str(FULL_DUMP), 'R_EVROOT=' + str(EVROOT), 'R_FIXTURE=' + str(FIX),
                           'R_CONFIG=/opt/stacks/data/immich-app-test/immich-test.stageb.config.json', 'TEST_CLIENT_IMAGE=' + client_img] + ['%s=%s' % kv for kv in IMG.items()]) + '\n')
DC('config', '-q')
print('compose config ok; starting source, redis, ml')
DC('up', '-d', 'pgsrc', 'redis', 'ml', timeout=600); wait_h(N['src']); wait_h(N['redis'])
DC('create', 'server')
app_pw = cutlib.container_env(N['server'], 'DB_PASSWORD')
assert app_pw == TRICKY_PW, 'compose altered the single-quoted special-character password (%d vs %d chars)' % (len(app_pw), len(TRICKY_PW))
env = dict(os.environ, NEWPW=app_pw)
pg(N['src'], "\\getenv pw NEWPW\nCREATE ROLE immich LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'pw';\nCREATE DATABASE immich WITH OWNER immich TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';", env=env)
t0 = time.time()
p = run(['docker', 'exec', N['src'], 'pg_restore', '-U', 'postgres', '--dbname=immich', '--exit-on-error', '--jobs=2', '/full.dump'], check=False)
assert p.returncode == 0 and not (p.stdout + p.stderr).strip(), 'source restore: ' + (p.stderr or '')[-300:]
pg(N['src'], "SET ROLE immich; REVOKE ALL ON DATABASE immich FROM PUBLIC; GRANT CONNECT,TEMPORARY ON DATABASE immich TO PUBLIC; GRANT CREATE,CONNECT,TEMPORARY ON DATABASE immich TO immich; RESET ROLE;\n"
                "ALTER SEQUENCE public.naturalearth_countries_tmp_id_seq1 AS bigint MINVALUE 1 MAXVALUE 2147483647 START WITH 1 INCREMENT BY 1 CACHE 1 NO CYCLE;", db='immich')
print('source restored in %.1fs; sequence normalised to bigint (as on production)' % (time.time() - t0))
# --- users: existing administrator (owns nothing) + the data-owning user chosen by the same criteria as phase 5C; random test passwords, test copy only
adm = pg(N['src'], 'SELECT id||\'|\'||email FROM "user" WHERE "isAdmin" AND "deletedAt" IS NULL;', db='immich').splitlines(); assert len(adm) == 1
cand = json.loads(pg(N['src'], """SELECT COALESCE(json_agg(x ORDER BY x.assets DESC),'[]') FROM (SELECT u.id::text id, u.email,
  (SELECT count(*) FROM asset a WHERE a."ownerId"=u.id AND a."deletedAt" IS NULL) assets,
  (SELECT count(*) FROM album_user au JOIN album al ON al.id=au."albumId" WHERE au."userId"=u.id AND au.role='owner' AND al."deletedAt" IS NULL AND EXISTS (SELECT 1 FROM album_asset aa WHERE aa."albumId"=al.id)) albums,
  (SELECT count(*) FROM person p WHERE p."ownerId"=u.id AND p.name<>'' AND NOT p."isHidden") named,
  (SELECT count(*) FROM smart_search s JOIN asset a ON a.id=s."assetId" WHERE a."ownerId"=u.id) emb
  FROM "user" u WHERE u."deletedAt" IS NULL AND NOT u."isAdmin") x;""", db='immich'))
usr = [c for c in cand if c['assets'] > 0 and c['albums'] > 0 and c['named'] > 0 and c['emb'] > 0][0]
adm_id, adm_email = adm[0].split('|', 1); pw_admin, pw_user = secrets.token_hex(12), secrets.token_hex(12)
def bcrypt(pw): return run(['docker', 'run', '--rm', '-i', '--network', 'none', '--entrypoint', 'node', IMG['TEST_SERVER_IMAGE'], '-e', "const b=require('/usr/src/app/server/node_modules/bcrypt');let s='';process.stdin.on('data',d=>s+=d).on('end',()=>console.log(b.hashSync(s.trim(),10)))"], input=pw)
for uid, pw in ((adm_id, pw_admin), (usr['id'], pw_user)):
    h = bcrypt(pw)
    assert pg(N['src'], "\\set h '%s'\n\\set u '%s'\nWITH u AS (UPDATE \"user\" SET password=:'h' WHERE id=:'u'::uuid RETURNING 1) SELECT count(*) FROM u;" % (h, uid), db='immich').strip() == '1'
# synthetic Immich-style backup (the rehearsal has no 02:00 job): stands in for the newest production backup in the local-backup gate tests
import gzip, base64
bk = ROOT / 'media' / 'backups' / ('immich-db-backup-%s-v3.3.5-pg16.13.sql.gz' % time.strftime('%Y%m%dT%H%M%S', time.gmtime()))
bk.write_bytes(gzip.compress(b'-- synthetic rehearsal backup\n' + base64.b64encode(secrets.token_bytes(200000)))); os.chmod(bk, 0o644)
DC('up', '-d', 'server', timeout=600); wait_h(N['server'], 300)
for k in ('mops', 'brg'):        # stand-ins for immich_media_operations / nextcloud_immich_bridge: plain sleeping containers on the isolated network (phase 7B: stop order of the freeze)
    run(['docker', 'run', '-d', '--name', N[k], '--network', PROJ + '_testnet', '--label', 'immich.cutover.rehearsal=' + ID, '--restart', 'no', '--entrypoint', 'sleep', IMG['TEST_REDIS_IMAGE'], '100000'])
keys = {}
for who, email, pw, perms in (('admin', adm_email, pw_admin, ["queue.read", "queue.update", "job.create", "server.about", "server.statistics", "library.read", "library.statistics"]),
                              ('user', usr['email'], pw_user, ["asset.read", "album.read", "person.read"]),
                              ('restricted', adm_email, pw_admin, ["server.about"])):
    r = api('POST', '/auth/login', {'email': email, 'password': pw}); assert r['status'] in (200, 201), 'login %s %s' % (who, r['status'])
    k = api('POST', '/api-keys', {'name': 'cutover-rehearsal-' + who, 'permissions': perms}, token=r['json']['accessToken']); assert k['status'] in (200, 201), 'key %s %s %s' % (who, k['status'], k['body'][:120])
    keys[who] = k['json']['secret']
state = {'id': ID, 'project': PROJ, 'root': str(ROOT), 'evroot': str(EVROOT), 'names': N, 'user_stats': {k: usr[k] for k in ('assets', 'albums', 'named', 'emb')}, 'emails': {'admin': adm_email, 'user': usr['email']},
         'passwords': {'admin': pw_admin, 'user': pw_user}, 'keys': keys, 'su_pw': su_pw}
(EVROOT / 'state.json').write_text(json.dumps(state, indent=1)); os.chmod(EVROOT / 'state.json', 0o600)
(EVROOT / 'env.sh').write_text('''# source this in the rehearsal shell
export CV=%(cv)s CUTOVER_REHEARSAL=1 CASE_ID=%(id)s R_PROJECT=%(proj)s R_ENVFILE=%(envf)s EVROOT=%(evroot)s ROOT=%(root)s
export REHEARSAL_SRC_CONTAINER=%(src)s REHEARSAL_DB_CONTAINER=%(db)s REHEARSAL_SERVER_CONTAINER=%(server)s REHEARSAL_REDIS_CONTAINER=%(redis)s REHEARSAL_ML_CONTAINER=%(ml)s REHEARSAL_NETWORK=%(proj)s_testnet
export CUTOVER_AUDIT=%(evroot)s/audit.jsonl CUTOVER_IMMICH_DIR=%(root)s/fixture/immich CUTOVER_DATA_DIR=%(root)s/fixture/data CUTOVER_BACKUPS_DIR=%(root)s/media/backups CUTOVER_TARGET_DATADIR=%(root)s/new-data
export LB_ROOT=%(root)s/lb-home IMMICH_BACKUPS=%(root)s/media/backups LB_MIN_FREE_GIB=5
export PG_SRC=%(src)s PG_NEW=%(db)s SRV=%(server)s MOPS=%(mops)s BRG=%(brg)s IMMICH_ENV_FILE=%(root)s/fixture/immich/.env HEALTH_TIMEOUT=60 DRAIN_TIMEOUT=300
idc()  { docker compose -p "$R_PROJECT" --env-file "$R_ENVFILE" -f "$CV/rehearsal/docker-compose.rehearsal.yml" "$@"; }
idcd() { docker compose -p "$R_PROJECT" --env-file "$R_ENVFILE" -f "$CV/rehearsal/docker-compose.rehearsal.yml" -f "$CV/rehearsal/docker-compose.rehearsal-dark.yml" "$@"; }
idb_up() { idc --profile target up -d --no-build --pull never immichdb; }
idcf() { docker compose -p "$R_PROJECT" --env-file "$R_ENVFILE" -f "$CV/rehearsal/docker-compose.rehearsal.yml" -f "$CV/rehearsal/docker-compose.rehearsal-frozen.yml" "$@"; }
_start_mops() { docker start "$MOPS"; }
_svc_name() { echo server; }
export -f idc idcd idcf idb_up _svc_name _start_mops 2>/dev/null || true
''' % {'cv': CV, 'id': ID, 'proj': PROJ, 'envf': ENVF, 'evroot': EVROOT, 'root': ROOT, 'src': N['src'], 'db': N['db'], 'server': N['server'], 'redis': N['redis'], 'ml': N['ml'], 'mops': N['mops'], 'brg': N['brg']})
print(json.dumps({'id': ID, 'evroot': str(EVROOT), 'root': str(ROOT), 'data_user_stats': state['user_stats']}))
